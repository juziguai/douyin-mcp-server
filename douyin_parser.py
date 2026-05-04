"""Douyin video parsing logic — refactored to use share page + _ROUTER_DATA."""

import functools
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from constants import HEADERS, MAX_RETRIES, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

_SHARE_PAGE_RE = re.compile(r"_ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>", re.DOTALL)
_SHORT_URL_RE = re.compile(r"https://v\.douyin\.com/(\w+)")
_VIDEO_ID_RE = re.compile(r"video/(\d+)")
_DOUYIN_URL_RE = re.compile(r"https?://v\.douyin\.com/\w+")
_RATIO_RE = re.compile(r"ratio=[^&]*")

# Ratios to probe for availability
_PROBE_RATIOS = ["240p", "360p", "480p", "540p", "720p", "1080p", "1440p", "4k"]

# Module-level session for TCP connection reuse
_session = requests.Session()
_session.headers.update(HEADERS)


def _validate_share_url(share_url: str) -> str | None:
    if not share_url or not _DOUYIN_URL_RE.match(share_url.strip()):
        return "无效的抖音链接，需要 https://v.douyin.com/xxx 格式"
    return None


def _resolve_cdn_link(url: str) -> str | None:
    """Resolve CDN download link with exponential backoff retry."""
    for i in range(MAX_RETRIES):
        try:
            resp = _session.get(url, allow_redirects=False, timeout=REQUEST_TIMEOUT)
            location = resp.headers.get("location", "")
            if location and "douyinvod.com" in location:
                return location
            match = re.search(r"https://[^\s\"]*douyinvod\.com[^\s\"]*", resp.text)
            if match:
                return match.group()
        except requests.RequestException as e:
            logger.warning("CDN 解析失败 (%d/%d): %s", i + 1, MAX_RETRIES, e)
        if i < MAX_RETRIES - 1:
            time.sleep(0.5 * (2 ** i))
    return None


def _probe_ratio(base_url: str, ratio: str) -> dict | None:
    """Probe a single ratio, return quality info or None if unavailable."""
    try:
        url = _RATIO_RE.sub(f"ratio={ratio}", base_url)
        resp = _session.get(url, allow_redirects=False, timeout=REQUEST_TIMEOUT)
        cdn_url = resp.headers.get("location", "")
        if not cdn_url or "douyinvod" not in cdn_url:
            return None
        head = _session.head(cdn_url, timeout=REQUEST_TIMEOUT)
        size_str = head.headers.get("Content-Length")
        if not size_str or int(size_str) == 0:
            return None
        size_mb = round(int(size_str) / (1024 * 1024), 2)
        return {"ratio": ratio, "size_mb": size_mb, "cdn_url": cdn_url}
    except (requests.RequestException, ValueError):
        return None


def _probe_qualities(base_url: str) -> list[dict]:
    """Probe all ratios in parallel, deduplicate, return real available qualities."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_probe_ratio, base_url, r): r for r in _PROBE_RATIOS}
        raw = []
        for f in futures:
            r = f.result()
            if r:
                raw.append(r)

    if not raw:
        return []

    # Group by file size to detect original-stream fallback
    from collections import Counter
    size_counts = Counter(r["size_mb"] for r in raw)
    fallback_size = size_counts.most_common(1)[0][0]  # most common size = fallback

    # Separate: actual transcodes vs original fallback
    order = {r: i for i, r in enumerate(_PROBE_RATIOS)}
    transcodes = [r for r in raw if r["size_mb"] != fallback_size]
    fallbacks = [r for r in raw if r["size_mb"] == fallback_size]

    # For fallback group, label as "original" with the largest CDN URL
    if fallbacks:
        fallbacks.sort(key=lambda x: order.get(x["ratio"], 99))
        orig = fallbacks[-1]
        orig["ratio"] = "original"
        result = transcodes + [orig]
    else:
        result = transcodes

    result.sort(key=lambda x: 999 if x["ratio"] == "original" else order.get(x["ratio"], 99))
    return result


@functools.lru_cache(maxsize=128)
def _probe_qualities(base_url: str) -> list[dict]:
    """Probe all ratios in parallel, deduplicate, return real available qualities. Cached."""
    return _probe_qualities_uncached(base_url)


# Cache for quality probe results, keyed by base_url
_quality_cache: dict[str, list[dict]] = {}


def _probe_qualities_uncached(base_url: str) -> list[dict]:
    """Probe all ratios in parallel, deduplicate, return real available qualities."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_probe_ratio, base_url, r): r for r in _PROBE_RATIOS}
        raw = []
        for f in futures:
            r = f.result()
            if r:
                raw.append(r)

    if not raw:
        return []

    # Group by file size to detect original-stream fallback
    from collections import Counter
    size_counts = Counter(r["size_mb"] for r in raw)
    fallback_size = size_counts.most_common(1)[0][0]  # most common size = fallback

    # Separate: actual transcodes vs original fallback
    order = {r: i for i, r in enumerate(_PROBE_RATIOS)}
    transcodes = [r for r in raw if r["size_mb"] != fallback_size]
    fallbacks = [r for r in raw if r["size_mb"] == fallback_size]

    # For fallback group, label as "original" with the largest CDN URL
    if fallbacks:
        fallbacks.sort(key=lambda x: order.get(x["ratio"], 99))
        orig = fallbacks[-1]
        orig["ratio"] = "original"
        result = transcodes + [orig]
    else:
        result = transcodes

    result.sort(key=lambda x: 999 if x["ratio"] == "original" else order.get(x["ratio"], 99))
    return result


@functools.lru_cache(maxsize=128)
def _fetch_video_info(share_url: str) -> dict:
    """Fetch video metadata from share page. Cached internally."""
    try:
        err = _validate_share_url(share_url)
        if err:
            return {"error": err}

        match = _SHORT_URL_RE.findall(share_url)
        if not match:
            return {"error": "无法从链接中提取抖音短链，请检查 URL 格式"}
        min_url = "https://v.douyin.com/" + match[0]

        resp = _session.get(min_url, allow_redirects=False, timeout=REQUEST_TIMEOUT)
        location = resp.headers.get("location", "")
        video_ids = _VIDEO_ID_RE.findall(location)
        if not video_ids:
            return {"error": "无法从重定向中提取视频 ID"}
        video_id = video_ids[0]

        page_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
        page_resp = _session.get(page_url, timeout=REQUEST_TIMEOUT)
        if page_resp.status_code != 200:
            return {"error": f"分享页请求失败，状态码: {page_resp.status_code}"}

        match = _SHARE_PAGE_RE.search(page_resp.text)
        if not match:
            return {"error": "无法从分享页提取视频数据（_ROUTER_DATA 未找到）"}

        router_data = json.loads(match.group(1))

        try:
            item_list = router_data["loaderData"]["video_(id)/page"]["videoInfoRes"]["item_list"]
            item = item_list[0]
        except (KeyError, IndexError, TypeError):
            return {"error": "无法从 _ROUTER_DATA 中提取视频信息"}

        video = item.get("video", {})
        play_addr = video.get("play_addr", {})
        play_urls = play_addr.get("url_list", [])

        if not play_urls:
            return {"error": "无法提取视频播放地址"}

        play_url = play_urls[0]
        no_wm_url = play_url.replace("playwm", "play")

        return {
            "video_title": item.get("desc", ""),
            "video_id": play_addr.get("uri", ""),
            "nickname": item.get("author", {}).get("nickname", ""),
            "avatar_url": item.get("author", {}).get("avatar_larger", {}).get("url_list", [None])[0],
            "cover_url": video.get("cover", {}).get("url_list", [None])[0],
            "width": video.get("width"),
            "height": video.get("height"),
            "duration_ms": video.get("duration"),
            "watermark_free_url": no_wm_url,
        }

    except requests.RequestException as e:
        return {"error": f"网络请求失败: {e}"}
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        return {"error": f"解析数据失败: {e}"}


def parse_douyin_video(share_url: str, ratio: str = None) -> dict:
    """Parse a Douyin share URL and return video metadata.

    Args:
        share_url: A Douyin share URL like "https://v.douyin.com/xxxxxx"
        ratio: If specified (e.g. "720p"), resolve CDN link for that quality.
               If None, probe all available qualities and return them.

    Returns:
        dict with video info. If ratio specified: includes download_link.
        If ratio None: includes available_qualities list.
    """
    info = _fetch_video_info(share_url)
    if "error" in info:
        return info

    base_url = info["watermark_free_url"]

    if ratio:
        if ratio == "original":
            # Use probed CDN URL for original quality
            qualities = _probe_qualities(base_url)
            orig = next((q for q in qualities if q["ratio"] == "original"), None)
            if not orig:
                return {**info, "error": "未找到原始画质"}
            return {**info, "download_link": orig["cdn_url"], "ratio": "original", "size_mb": orig["size_mb"]}
        else:
            # Resolve specific quality
            target_url = _RATIO_RE.sub(f"ratio={ratio}", base_url)
            download_link = _resolve_cdn_link(target_url)
            result = {**info, "download_link": download_link, "ratio": ratio}
            if download_link:
                try:
                    head = _session.head(download_link, timeout=REQUEST_TIMEOUT)
                    size_str = head.headers.get("Content-Length")
                    if size_str and int(size_str) > 0:
                        result["size_mb"] = round(int(size_str) / (1024 * 1024), 2)
                except (requests.RequestException, ValueError):
                    pass
            return result
    else:
        # Probe all available qualities
        qualities = _probe_qualities(base_url)
        best = qualities[-1] if qualities else None
        result = {
            **info,
            "available_qualities": qualities,
            "recommended_ratio": best["ratio"] if best else None,
        }
        # Include download link for recommended quality
        if best:
            result["download_link"] = best["cdn_url"]
            result["ratio"] = best["ratio"]
            result["size_mb"] = best["size_mb"]
        return result


def download_video_file(cdn_url: str, save_path: str) -> dict:
    """Download a video file from CDN URL to local path."""
    try:
        resp = _session.get(cdn_url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size_mb = round(os.path.getsize(save_path) / (1024 * 1024), 2)
        return {"path": save_path, "size_mb": size_mb}
    except requests.RequestException as e:
        return {"error": f"下载失败: {e}"}
    except OSError as e:
        return {"error": f"文件写入失败: {e}"}
