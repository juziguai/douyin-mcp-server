# Douyin Video MCP Server

抖音视频去水印解析 MCP Server，供 Claude Code CLI 或其他 AI Agent 使用。

## 功能

| MCP 工具 | 说明 |
|----------|------|
| `parse_douyin_video` | 解析抖音分享链接，返回视频标题、作者、封面、无水印下载地址等 |
| `extract_download_link` | 从无水印 URL 提取最终 CDN 下载链接 |

## 安装

```bash
cd D:\Tools\AI\Claude-code\douyin-mcp-server
pip install -r requirements.txt
```

## 配置 Claude Code

```bash
claude mcp add --transport stdio --scope user douyin-video -- python D:\Tools\AI\Claude-code\douyin-mcp-server\server.py
```

## 直接运行

```bash
python server.py
```

服务器通过 stdio 传输运行，日志输出到 stderr。

## 项目来源

从 [flask_watermark_mvc](../flask_watermark_mvc) 重构而来，去除了 Flask/MySQL 依赖，保留核心解析逻辑。
