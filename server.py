"""Douyin Video MCP Server — for Claude Code CLI and other agents."""

import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

# All logs go to stderr to avoid corrupting stdio JSON-RPC protocol
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[douyin-mcp] %(levelname)s %(message)s",
)

from mcp.server.fastmcp import FastMCP

import douyin_parser as parser
import history

mcp = FastMCP("douyin-video")

_DEFAULT_SAVE_DIR = os.path.join(os.path.dirname(__file__), "videos")


def _sanitize_filename(name: str) -> str:
    """Clean title into a valid filename: remove hashtags, illegal chars, trim."""
    name = re.sub(r'#\S+', '', name)
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = name[:60] or "video"
    name = name.replace('..', '_')
    return os.path.basename(name)


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


@mcp.tool()
def parse_douyin_video(share_url: str, ratio: str | None = None) -> dict:
    """Parse a Douyin (抖音) share URL and return video metadata + quality options.

    Use this tool when a user provides a Douyin share link (e.g. https://v.douyin.com/xxx)
    and wants to get the video's download link, title, author, cover image, etc.

    Args:
        share_url: A Douyin share URL, e.g. "https://v.douyin.com/xxxxxx"
                   or a full URL like "https://www.douyin.com/video/xxx"
        ratio: Optional. If specified (e.g. "720p"), resolve download link for that quality.
               If omitted, automatically probes all available qualities and returns them
               with recommended_ratio (highest quality with valid content).

    Returns:
        A dict with: video_title, video_id, width, height, duration_ms,
        nickname, avatar_url, cover_url, watermark_free_url.
        If ratio specified: download_link, ratio, size_mb.
        If ratio omitted: available_qualities (list), recommended_ratio, download_link, ratio, size_mb.
        On failure: {"error": "description"}
    """
    return parser.parse_douyin_video(share_url, ratio=ratio)


@mcp.tool()
def parse_batch(share_urls: list[str], ratio: str | None = None) -> list[dict]:
    """Parse multiple Douyin share URLs in batch.

    Args:
        share_urls: A list of Douyin share URLs.
        ratio: Optional quality. If omitted, probes all available qualities per video.

    Returns:
        A list of dicts, each with video info or error.
    """
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda url: parser.parse_douyin_video(url, ratio=ratio), share_urls))


@mcp.tool()
def download_video(share_url: str, filename: str | None = None, save_dir: str | None = None, ratio: str | None = None) -> dict:
    """Parse a Douyin video and download it to local disk.

    Args:
        share_url: A Douyin share URL, e.g. "https://v.douyin.com/xxxxxx"
                   or a full URL like "https://www.douyin.com/video/xxx"
        filename: Custom filename (without extension). If None, uses video title.
        save_dir: Directory to save the video. If None, uses the default videos/ directory.
        ratio: Video quality (e.g. "720p", "1080p"). If None, uses the highest available quality.

    Returns:
        A dict with "path", "size_mb", "video_title", "ratio" on success, or "error" on failure.
    """
    result = parser.parse_douyin_video(share_url, ratio=ratio)
    if "error" in result:
        return result

    if not result.get("download_link"):
        return {"error": "解析成功但未获取到下载链接"}

    save_dir = save_dir or _DEFAULT_SAVE_DIR
    # Prevent path traversal: resolve to real path and ensure under allowed directory
    real_save_dir = os.path.realpath(save_dir)
    real_default = os.path.realpath(_DEFAULT_SAVE_DIR)
    if not real_save_dir.startswith(real_default) and not os.path.isabs(save_dir):
        save_dir = _DEFAULT_SAVE_DIR
        real_save_dir = real_default
    _ensure_dir(real_save_dir)

    name = filename or _sanitize_filename(result.get("video_title", "video"))
    save_path = os.path.join(real_save_dir, f"{name}.mp4")

    # Skip download if file already exists on disk or in history
    video_id = result.get("video_id", "")
    existing = history.is_downloaded(video_id, "video") if video_id else None
    if existing and os.path.exists(existing["file_path"]):
        return {
            "path": existing["file_path"],
            "size_mb": existing["size_mb"],
            "video_title": existing["video_title"],
            "nickname": existing["nickname"],
            "ratio": existing["ratio"],
            "cached": True,
        }

    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        size_mb = round(os.path.getsize(save_path) / (1024 * 1024), 2)
        history.record_download(video_id, result.get("video_title", ""), result.get("nickname", ""),
                                share_url, save_path, "video", size_mb, result.get("ratio", ""))
        return {
            "path": save_path,
            "size_mb": size_mb,
            "video_title": result.get("video_title", ""),
            "nickname": result.get("nickname", ""),
            "ratio": result.get("ratio", ""),
            "cached": True,
        }

    dl_result = parser.download_video_file(result["download_link"], save_path)
    if "error" in dl_result:
        return dl_result

    history.record_download(video_id, result.get("video_title", ""), result.get("nickname", ""),
                            share_url, dl_result["path"], "video", dl_result["size_mb"], result.get("ratio", ""))

    return {
        "path": dl_result["path"],
        "size_mb": dl_result["size_mb"],
        "video_title": result.get("video_title", ""),
        "nickname": result.get("nickname", ""),
        "ratio": result.get("ratio", ""),
    }


@mcp.tool()
def download_batch(share_urls: list[str], save_dir: str | None = None, ratio: str | None = None) -> list[dict]:
    """Parse and download multiple Douyin videos in batch.

    Args:
        share_urls: A list of Douyin share URLs.
        save_dir: Directory to save videos. If None, uses the default videos/ directory.
        ratio: Video quality (e.g. "720p"). If None, uses highest available per video.

    Returns:
        A list of dicts, each with path/size or error.
    """
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda url: download_video(url, save_dir=save_dir, ratio=ratio), share_urls))


@mcp.tool()
def download_user_batch(user_url: str, max_count: int = 10, save_dir: str | None = None, ratio: str | None = None) -> dict:
    """Batch download videos from a Douyin user's profile.

    Args:
        user_url: A Douyin user profile URL, e.g. "https://www.douyin.com/user/xxx"
                  or a short link that redirects to a user page.
        max_count: Maximum number of videos to download (default 10, max 50).
        save_dir: Directory to save videos. If None, uses the default videos/ directory.
        ratio: Video quality (e.g. "720p"). If None, uses highest available per video.

    Returns:
        A dict with user info, "total" count, and "results" list (each with path/size or error).
    """
    max_count = min(max_count, 50)
    user_info = parser.fetch_user_videos(user_url, max_count=max_count)
    if "error" in user_info:
        return user_info

    videos = user_info.get("videos", [])
    if not videos:
        return {"error": "该用户没有视频"}

    share_urls = [v["share_url"] for v in videos if v.get("share_url")]
    if not share_urls:
        return {"error": "无法获取视频分享链接"}

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda url: download_video(url, save_dir=save_dir, ratio=ratio), share_urls))

    return {
        "nickname": user_info.get("nickname", ""),
        "user_id": user_info.get("user_id", ""),
        "total": len(results),
        "success": sum(1 for r in results if "error" not in r),
        "results": results,
    }


@mcp.tool()
def download_cover(share_url: str, save_dir: str | None = None, filename: str | None = None) -> dict:
    """Download the cover image of a Douyin video.

    Args:
        share_url: A Douyin share URL, e.g. "https://v.douyin.com/xxxxxx"
        save_dir: Directory to save the cover. If None, uses the default videos/ directory.
        filename: Custom filename (without extension). If None, uses video title.

    Returns:
        A dict with "path", "size_kb", "video_title" on success, or "error" on failure.
    """
    result = parser.parse_douyin_video(share_url)
    if "error" in result:
        return result

    cover_url = result.get("cover_url")
    if not cover_url:
        return {"error": "该视频没有封面图"}

    save_dir = save_dir or _DEFAULT_SAVE_DIR
    real_save_dir = os.path.realpath(save_dir)
    real_default = os.path.realpath(_DEFAULT_SAVE_DIR)
    if not real_save_dir.startswith(real_default) and not os.path.isabs(save_dir):
        save_dir = _DEFAULT_SAVE_DIR
        real_save_dir = real_default
    _ensure_dir(real_save_dir)

    name = filename or _sanitize_filename(result.get("video_title", "cover"))
    save_path = os.path.join(real_save_dir, f"{name}.jpg")

    dl_result = parser.download_cover_file(cover_url, save_path)
    if "error" in dl_result:
        return dl_result

    video_id = result.get("video_id", "")
    history.record_download(video_id, result.get("video_title", ""), result.get("nickname", ""),
                            share_url, dl_result["path"], "cover", dl_result["size_kb"] / 1024)

    return {
        "path": dl_result["path"],
        "size_kb": dl_result["size_kb"],
        "video_title": result.get("video_title", ""),
    }


@mcp.tool()
def extract_audio(share_url: str, save_dir: str | None = None, filename: str | None = None, ratio: str | None = None) -> dict:
    """Download a Douyin video and extract its audio as MP3.

    Requires ffmpeg to be installed and available in PATH.

    Args:
        share_url: A Douyin share URL, e.g. "https://v.douyin.com/xxxxxx"
        save_dir: Directory to save the audio. If None, uses the default videos/ directory.
        filename: Custom filename (without extension). If None, uses video title.
        ratio: Video quality to download before extraction. If None, uses highest available.

    Returns:
        A dict with "path", "size_mb", "video_title" on success, or "error" on failure.
    """
    # First download the video
    dl = download_video(share_url, save_dir=save_dir, ratio=ratio)
    if "error" in dl:
        return dl

    video_path = dl["path"]
    save_dir = save_dir or _DEFAULT_SAVE_DIR
    name = filename or _sanitize_filename(dl.get("video_title", "audio"))
    audio_path = os.path.join(save_dir, f"{name}.mp3")

    result = parser.extract_audio_file(video_path, audio_path)
    if "error" in result:
        return result

    history.record_download("", dl.get("video_title", ""), dl.get("nickname", ""),
                            share_url, result["path"], "audio", result["size_mb"])

    return {
        "path": result["path"],
        "size_mb": result["size_mb"],
        "video_title": dl.get("video_title", ""),
    }


@mcp.tool()
def parse_user_videos(user_url: str, max_count: int = 20) -> dict:
    """Fetch video list from a Douyin user profile page.

    Args:
        user_url: A Douyin user profile URL, e.g. "https://www.douyin.com/user/MS4wLjABAAAA..."
                  or a short link that redirects to a user page.
        max_count: Maximum number of videos to return (default 20, max 50).

    Returns:
        A dict with user info (nickname, avatar, signature) and a "videos" list.
        Each video contains: video_id, video_title, cover_url, width, height, duration_ms, share_url.
        On failure: {"error": "description"}
    """
    max_count = min(max_count, 50)
    return parser.fetch_user_videos(user_url, max_count=max_count)


@mcp.tool()
def get_video_comments(share_url: str, max_count: int = 20) -> dict:
    """Fetch top comments for a Douyin video.

    Args:
        share_url: A Douyin share URL, e.g. "https://v.douyin.com/xxxxxx"
                   or a full URL like "https://www.douyin.com/video/xxx"
        max_count: Maximum number of comments to return (default 20, max 50).

    Returns:
        A dict with video_title, comment_count, and a "comments" list.
        Each comment: text, nickname, digg_count, reply_count, create_time.
        On failure: {"error": "description"}
    """
    max_count = min(max_count, 50)
    return parser.fetch_video_comments(share_url, max_count=max_count)


@mcp.tool()
def list_download_history(limit: int = 20, file_type: str | None = None, keyword: str | None = None) -> list[dict]:
    """List download history, optionally filtered by type or keyword.

    Args:
        limit: Maximum number of records to return (default 20).
        file_type: Filter by type: "video", "cover", or "audio". If None, returns all.
        keyword: Search keyword in video title or nickname. If None, no filtering.

    Returns:
        A list of download records with: video_id, video_title, nickname, share_url,
        file_path, file_type, size_mb, ratio, downloaded_at (unix timestamp).
    """
    if keyword:
        return history.search_history(keyword, limit=limit)
    return history.list_history(limit=limit, file_type=file_type)


@mcp.tool()
def delete_history(record_id: int | None = None, file_type: str | None = None, delete_file: bool = False) -> dict:
    """Delete download history records.

    Args:
        record_id: Delete a specific record by ID. If specified, file_type is ignored.
        file_type: Delete all records of this type ("video", "cover", "audio"). If None and record_id is None, clears all.
        delete_file: If True, also delete the local file. Default False (only removes DB record).

    Returns:
        A dict with "deleted" count or "error" on failure.
    """
    if record_id is not None:
        record = history.delete_record(record_id)
        if not record:
            return {"error": f"记录 ID {record_id} 不存在"}
        deleted = 1
        if delete_file and record.get("file_path") and os.path.exists(record["file_path"]):
            try:
                os.remove(record["file_path"])
            except OSError:
                pass
    else:
        # Get records first if we need to delete files
        if delete_file:
            records = history.list_history(limit=9999, file_type=file_type)
            for r in records:
                if r.get("file_path") and os.path.exists(r["file_path"]):
                    try:
                        os.remove(r["file_path"])
                    except OSError:
                        pass
        deleted = history.clear_history(file_type=file_type)

    return {"deleted": deleted}


if __name__ == "__main__":
    mcp.run()
