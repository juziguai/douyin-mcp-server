#!/usr/bin/env python3
"""Douyin Video CLI — 命令行版抖音视频解析/下载工具."""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import douyin_parser as parser
import history

_DEFAULT_SAVE_DIR = os.path.join(os.path.dirname(__file__), "videos")


def _sanitize_filename(name: str) -> str:
    """Clean title into a valid filename."""
    import re
    name = re.sub(r'#\S+', '', name)
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = name[:60] or "video"
    name = name.replace('..', '_')
    return os.path.basename(name)


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _safe_save_dir(save_dir: str | None) -> str:
    """Resolve save dir with path traversal protection."""
    save_dir = save_dir or _DEFAULT_SAVE_DIR
    real_save_dir = os.path.realpath(save_dir)
    real_default = os.path.realpath(_DEFAULT_SAVE_DIR)
    if not real_save_dir.startswith(real_default) and not os.path.isabs(save_dir):
        real_save_dir = real_default
    _ensure_dir(real_save_dir)
    return real_save_dir


def _output(data, pretty=False):
    """Print JSON output."""
    print(json.dumps(data, ensure_ascii=False, indent=2 if pretty else None))


# ── 子命令实现 ──────────────────────────────────────────────

def cmd_parse(args):
    """解析抖音链接，返回元数据 + 清晰度列表."""
    result = parser.parse_douyin_video(args.url, ratio=args.ratio)
    _output(result, args.pretty)


def cmd_parse_batch(args):
    """批量解析多个抖音链接."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda url: parser.parse_douyin_video(url, ratio=args.ratio), args.urls))
    _output(results, args.pretty)


def cmd_download(args):
    """解析 + 下载视频."""
    result = parser.parse_douyin_video(args.url, ratio=args.ratio)
    if "error" in result:
        _output(result, args.pretty)
        return

    if not result.get("download_link"):
        _output({"error": "解析成功但未获取到下载链接"}, args.pretty)
        return

    save_dir = _safe_save_dir(args.save_dir)
    name = args.filename or _sanitize_filename(result.get("video_title", "video"))
    save_path = os.path.join(save_dir, f"{name}.mp4")

    # 去重检查
    video_id = result.get("video_id", "")
    existing = history.is_downloaded(video_id, "video") if video_id else None
    if existing and os.path.exists(existing["file_path"]):
        _output({**existing, "cached": True}, args.pretty)
        return

    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        size_mb = round(os.path.getsize(save_path) / (1024 * 1024), 2)
        history.record_download(video_id, result.get("video_title", ""), result.get("nickname", ""),
                                args.url, save_path, "video", size_mb, result.get("ratio", ""))
        _output({"path": save_path, "size_mb": size_mb, "cached": True}, args.pretty)
        return

    dl_result = parser.download_video_file(result["download_link"], save_path)
    if "error" in dl_result:
        _output(dl_result, args.pretty)
        return

    history.record_download(video_id, result.get("video_title", ""), result.get("nickname", ""),
                            args.url, dl_result["path"], "video", dl_result["size_mb"], result.get("ratio", ""))
    _output(dl_result, args.pretty)


def cmd_download_batch(args):
    """批量下载多个视频."""
    def _dl(url):
        result = parser.parse_douyin_video(url, ratio=args.ratio)
        if "error" in result:
            return result
        if not result.get("download_link"):
            return {"error": "未获取到下载链接", "url": url}
        save_dir = _safe_save_dir(args.save_dir)
        name = _sanitize_filename(result.get("video_title", "video"))
        save_path = os.path.join(save_dir, f"{name}.mp4")
        dl_result = parser.download_video_file(result["download_link"], save_path)
        if "error" not in dl_result:
            history.record_download(result.get("video_id", ""), result.get("video_title", ""),
                                    result.get("nickname", ""), url, dl_result["path"],
                                    "video", dl_result["size_mb"], result.get("ratio", ""))
        return dl_result

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_dl, args.urls))
    _output(results, args.pretty)


def cmd_download_cover(args):
    """下载视频封面图."""
    result = parser.parse_douyin_video(args.url)
    if "error" in result:
        _output(result, args.pretty)
        return
    cover_url = result.get("cover_url")
    if not cover_url:
        _output({"error": "该视频没有封面图"}, args.pretty)
        return

    save_dir = _safe_save_dir(args.save_dir)
    name = args.filename or _sanitize_filename(result.get("video_title", "cover"))
    save_path = os.path.join(save_dir, f"{name}.jpg")

    dl_result = parser.download_cover_file(cover_url, save_path)
    if "error" in dl_result:
        _output(dl_result, args.pretty)
        return

    history.record_download(result.get("video_id", ""), result.get("video_title", ""),
                            result.get("nickname", ""), args.url, dl_result["path"],
                            "cover", dl_result["size_kb"] / 1024)
    _output(dl_result, args.pretty)


def cmd_audio(args):
    """下载视频并提取音频为 MP3."""
    # 先下载视频
    result = parser.parse_douyin_video(args.url, ratio=args.ratio)
    if "error" in result:
        _output(result, args.pretty)
        return
    if not result.get("download_link"):
        _output({"error": "未获取到下载链接"}, args.pretty)
        return

    save_dir = _safe_save_dir(args.save_dir)
    name = _sanitize_filename(result.get("video_title", "video"))
    video_path = os.path.join(save_dir, f"{name}.mp4")

    dl_result = parser.download_video_file(result["download_link"], video_path)
    if "error" in dl_result:
        _output(dl_result, args.pretty)
        return

    audio_name = args.filename or name
    audio_path = os.path.join(save_dir, f"{audio_name}.mp3")

    audio_result = parser.extract_audio_file(video_path, audio_path)
    if "error" in audio_result:
        _output(audio_result, args.pretty)
        return

    history.record_download("", result.get("video_title", ""), result.get("nickname", ""),
                            args.url, audio_result["path"], "audio", audio_result["size_mb"])
    _output(audio_result, args.pretty)


def cmd_user_videos(args):
    """获取用户主页视频列表."""
    result = parser.fetch_user_videos(args.url, max_count=args.max)
    _output(result, args.pretty)


def cmd_download_user(args):
    """批量下载用户主页视频."""
    user_info = parser.fetch_user_videos(args.url, max_count=args.max)
    if "error" in user_info:
        _output(user_info, args.pretty)
        return

    videos = user_info.get("videos", [])
    if not videos:
        _output({"error": "该用户没有视频"}, args.pretty)
        return

    share_urls = [v["share_url"] for v in videos if v.get("share_url")]
    if not share_urls:
        _output({"error": "无法获取视频分享链接"}, args.pretty)
        return

    def _dl(url):
        result = parser.parse_douyin_video(url, ratio=args.ratio)
        if "error" in result:
            return result
        if not result.get("download_link"):
            return {"error": "未获取到下载链接"}
        save_dir = _safe_save_dir(args.save_dir)
        name = _sanitize_filename(result.get("video_title", "video"))
        save_path = os.path.join(save_dir, f"{name}.mp4")
        dl_result = parser.download_video_file(result["download_link"], save_path)
        if "error" not in dl_result:
            history.record_download(result.get("video_id", ""), result.get("video_title", ""),
                                    result.get("nickname", ""), url, dl_result["path"],
                                    "video", dl_result["size_mb"], result.get("ratio", ""))
        return dl_result

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_dl, share_urls))

    _output({
        "nickname": user_info.get("nickname", ""),
        "user_id": user_info.get("user_id", ""),
        "total": len(results),
        "success": sum(1 for r in results if "error" not in r),
        "results": results,
    }, args.pretty)


def cmd_history(args):
    """查询下载历史."""
    if args.keyword:
        results = history.search_history(args.keyword, limit=args.limit)
    else:
        results = history.list_history(limit=args.limit, file_type=args.type)
    _output(results, args.pretty)


def cmd_delete_history(args):
    """删除下载记录."""
    if args.id is not None:
        record = history.delete_record(args.id)
        if not record:
            _output({"error": f"记录 ID {args.id} 不存在"}, args.pretty)
            return
        if args.delete_file and record.get("file_path") and os.path.exists(record["file_path"]):
            try:
                os.remove(record["file_path"])
            except OSError:
                pass
        _output({"deleted": 1}, args.pretty)
    else:
        if args.delete_file:
            records = history.list_history(limit=9999, file_type=args.type)
            for r in records:
                if r.get("file_path") and os.path.exists(r["file_path"]):
                    try:
                        os.remove(r["file_path"])
                    except OSError:
                        pass
        deleted = history.clear_history(file_type=args.type)
        _output({"deleted": deleted}, args.pretty)


# ── CLI 定义 ────────────────────────────────────────────────

def _add_pretty(s):
    """Add --pretty flag to a subcommand parser."""
    s.add_argument("--pretty", action="store_true", help="美化 JSON 输出")
    return s


def build_parser():
    p = argparse.ArgumentParser(
        prog="douyin",
        description="抖音视频去水印解析 CLI 工具",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # parse
    s = sub.add_parser("parse", help="解析抖音链接")
    s.add_argument("url", help="抖音分享链接")
    s.add_argument("--ratio", help="指定清晰度 (如 720p, original)")
    _add_pretty(s)
    s.set_defaults(func=cmd_parse)

    # parse-batch
    s = sub.add_parser("parse-batch", help="批量解析")
    s.add_argument("urls", nargs="+", help="多个抖音分享链接")
    s.add_argument("--ratio", help="指定清晰度")
    _add_pretty(s)
    s.set_defaults(func=cmd_parse_batch)

    # download
    s = sub.add_parser("download", help="下载视频")
    s.add_argument("url", help="抖音分享链接")
    s.add_argument("--filename", help="自定义文件名（不含扩展名）")
    s.add_argument("--save-dir", help="保存目录")
    s.add_argument("--ratio", help="指定清晰度")
    _add_pretty(s)
    s.set_defaults(func=cmd_download)

    # download-batch
    s = sub.add_parser("download-batch", help="批量下载")
    s.add_argument("urls", nargs="+", help="多个抖音分享链接")
    s.add_argument("--save-dir", help="保存目录")
    s.add_argument("--ratio", help="指定清晰度")
    _add_pretty(s)
    s.set_defaults(func=cmd_download_batch)

    # download-cover
    s = sub.add_parser("download-cover", help="下载封面图")
    s.add_argument("url", help="抖音分享链接")
    s.add_argument("--save-dir", help="保存目录")
    s.add_argument("--filename", help="自定义文件名")
    _add_pretty(s)
    s.set_defaults(func=cmd_download_cover)

    # audio
    s = sub.add_parser("audio", help="提取音频为 MP3")
    s.add_argument("url", help="抖音分享链接")
    s.add_argument("--save-dir", help="保存目录")
    s.add_argument("--filename", help="自定义文件名")
    s.add_argument("--ratio", help="指定清晰度")
    _add_pretty(s)
    s.set_defaults(func=cmd_audio)

    # user-videos
    s = sub.add_parser("user-videos", help="获取用户视频列表")
    s.add_argument("url", help="用户主页链接")
    s.add_argument("--max", type=int, default=20, help="最大数量 (默认 20, 最多 50)")
    _add_pretty(s)
    s.set_defaults(func=cmd_user_videos)

    # download-user
    s = sub.add_parser("download-user", help="批量下载用户视频")
    s.add_argument("url", help="用户主页链接")
    s.add_argument("--max", type=int, default=10, help="最大下载数 (默认 10, 最多 50)")
    s.add_argument("--save-dir", help="保存目录")
    s.add_argument("--ratio", help="指定清晰度")
    _add_pretty(s)
    s.set_defaults(func=cmd_download_user)

    # history
    s = sub.add_parser("history", help="查询下载历史")
    s.add_argument("--limit", type=int, default=20, help="返回条数")
    s.add_argument("--type", choices=["video", "cover", "audio"], help="按类型筛选")
    s.add_argument("--keyword", help="关键词搜索")
    _add_pretty(s)
    s.set_defaults(func=cmd_history)

    # delete-history
    s = sub.add_parser("delete-history", help="删除下载记录")
    s.add_argument("--id", type=int, help="删除指定记录 ID")
    s.add_argument("--type", choices=["video", "cover", "audio"], help="按类型删除")
    s.add_argument("--delete-file", action="store_true", help="同时删除本地文件")
    _add_pretty(s)
    s.set_defaults(func=cmd_delete_history)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
