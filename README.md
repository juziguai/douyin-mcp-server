# Douyin Video MCP Server

抖音视频去水印解析 MCP Server，供 Claude Code CLI 或其他 AI Agent 使用。

## 功能

| MCP 工具 | 说明 |
|----------|------|
| `parse_douyin_video` | 解析抖音分享链接，返回视频标题、作者、封面、无水印下载地址等 |
| `parse_batch` | 批量解析多个抖音链接 |
| `download_video` | 解析并下载视频到本地（带历史去重） |
| `download_batch` | 批量下载多个视频 |
| `download_cover` | 下载视频封面图 |
| `extract_audio` | 从视频中提取音频为 MP3（需 ffmpeg） |
| `parse_user_videos` | 获取用户主页视频列表 |
| `list_download_history` | 查询下载历史（支持按类型/关键词筛选） |

## 安装

```bash
cd D:\Tools\AI\Claude-code\douyin-mcp-server
pip install -r requirements.txt
```

开发环境（含自动重载）：

```bash
pip install -r requirements-dev.txt
```

## 配置 Claude Code

```bash
claude mcp add --transport stdio --scope user douyin-video -- python D:\Tools\AI\Claude-code\douyin-mcp-server\reload_wrapper.py
```

## 直接运行

```bash
python server.py
```

服务器通过 stdio 传输运行，日志输出到 stderr。

## 项目来源

从 [flask_watermark_mvc](../flask_watermark_mvc) 重构而来，去除了 Flask/MySQL 依赖，保留核心解析逻辑。

## 功能拓展路线图

| 功能 | 工具名 | 说明 | 状态 |
|------|--------|------|------|
| 封面下载 | `download_cover` | 单独下载视频封面图 | 待实现 |
| 音频提取 | `extract_audio` | 从视频中分离音频（需 ffmpeg） | 待实现 |
| 用户主页解析 | `parse_user_videos` | 批量获取用户主页视频列表 | 待实现 |
| 下载历史记录 | — | SQLite 去重与查询 | 待实现 |
