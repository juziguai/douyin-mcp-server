"""Douyin Video MCP Server — for Claude Code CLI and other agents."""

import logging
import os
import re
import sys

# All logs go to stderr to avoid corrupting stdio JSON-RPC protocol
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[douyin-mcp] %(levelname)s %(message)s",
)

from mcp.server.fastmcp import FastMCP

import douyin_parser as parser

mcp = FastMCP("douyin-video")

_DEFAULT_SAVE_DIR = os.path.join(os.path.dirname(__file__), "videos")


def _sanitize_filename(name: str) -> str:
    """Clean title into a valid filename: remove hashtags, illegal chars, trim."""
    name = re.sub(r'#\S+', '', name)
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:60] or "video"


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


@mcp.tool()
def parse_douyin_video(share_url: str, ratio: str = None) -> dict:
    """Parse a Douyin (抖音) share URL and return video metadata + quality options.

    Use this tool when a user provides a Douyin share link (e.g. https://v.douyin.com/xxx)
    and wants to get the video's download link, title, author, cover image, etc.

    Args:
        share_url: A Douyin share URL, e.g. "https://v.douyin.com/xxxxxx"
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
def parse_batch(share_urls: list[str], ratio: str = None) -> list[dict]:
    """Parse multiple Douyin share URLs in batch.

    Args:
        share_urls: A list of Douyin share URLs.
        ratio: Optional quality. If omitted, probes all available qualities per video.

    Returns:
        A list of dicts, each with video info or error.
    """
    return [parser.parse_douyin_video(url, ratio=ratio) for url in share_urls]


@mcp.tool()
def download_video(share_url: str, filename: str = None, save_dir: str = None, ratio: str = None) -> dict:
    """Parse a Douyin video and download it to local disk.

    Args:
        share_url: A Douyin share URL, e.g. "https://v.douyin.com/xxxxxx"
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
    _ensure_dir(save_dir)

    name = filename or _sanitize_filename(result.get("video_title", "video"))
    save_path = os.path.join(save_dir, f"{name}.mp4")

    dl_result = parser.download_video_file(result["download_link"], save_path)
    if "error" in dl_result:
        return dl_result

    return {
        "path": dl_result["path"],
        "size_mb": dl_result["size_mb"],
        "video_title": result.get("video_title", ""),
        "nickname": result.get("nickname", ""),
        "ratio": result.get("ratio", ""),
    }


@mcp.tool()
def download_batch(share_urls: list[str], save_dir: str = None, ratio: str = None) -> list[dict]:
    """Parse and download multiple Douyin videos in batch.

    Args:
        share_urls: A list of Douyin share URLs.
        save_dir: Directory to save videos. If None, uses the default videos/ directory.
        ratio: Video quality (e.g. "720p"). If None, uses highest available per video.

    Returns:
        A list of dicts, each with path/size or error.
    """
    return [download_video(url, save_dir=save_dir, ratio=ratio) for url in share_urls]


if __name__ == "__main__":
    mcp.run()
