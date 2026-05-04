# 抖音视频 MCP Server - 项目交接文档

## 项目概述

将 `flask_watermark_mvc`（微信云托管 Flask 服务）重构为 MCP Server，供 Claude Code CLI 通过 MCP 协议直接调用抖音视频去水印解析功能。

## 当前状态

- **MCP Server 已创建并注册** — `douyin-video` (user scope，全局可用)
- **服务器连接正常** — `claude mcp list` 显示 ✓ Connected
- **已修复 2026-05-05** — 旧 API `iesdouyin.com/web/api/v2/aweme/iteminfo/` 返回 `encrypt_data_miss`，改用分享页 `_ROUTER_DATA` 方案
- **已优化 2026-05-05** — 全面重构：自适应清晰度、合并工具、新增下载/批量功能、自动重载

## 项目结构

```
D:\Tools\AI\Claude-code\douyin-mcp-server\
├── server.py              # MCP 服务器入口 (FastMCP, stdio 传输)
├── reload_wrapper.py      # 自动重载包装器 (watchdog 监听 .py 变化重启进程)
├── douyin_parser.py       # 核心解析逻辑（清晰度探测、CDN 解析、下载）
├── constants.py           # User-Agent、超时、重试常量
├── requirements.txt       # mcp[cli], requests, jsonpath, watchdog
├── videos/                # 解析后下载的视频存放目录
├── README.md              # 使用说明
└── HANDOVER.md            # 本文档
```

## MCP 工具

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `parse_douyin_video` | `share_url, ratio?` | 解析抖音链接。不指定 ratio 时自动探测所有可用清晰度；指定时返回对应 CDN 链接 |
| `parse_batch` | `share_urls, ratio?` | 批量解析多个抖音链接 |
| `download_video` | `share_url, filename?, save_dir?, ratio?` | 解析 + 下载视频到本地（带历史去重） |
| `download_batch` | `share_urls, save_dir?, ratio?` | 批量下载多个视频 |
| `download_cover` | `share_url, save_dir?, filename?` | 下载视频封面图 |
| `extract_audio` | `share_url, save_dir?, filename?, ratio?` | 从视频提取音频为 MP3（需 ffmpeg） |
| `parse_user_videos` | `user_url, max_count?` | 获取用户主页视频列表 |
| `list_download_history` | `limit?, file_type?, keyword?` | 查询下载历史 |

### ratio 参数

| 值 | 说明 |
|----|------|
| `None`（默认） | 自动探测所有可用清晰度，返回 `available_qualities` 列表，推荐最高画质 |
| `"720p"` | 指定 720p 转码版本 |
| `"540p"` | 指定 540p 转码版本 |
| `"original"` | 原始画质（未转码，文件最大） |

### available_qualities 返回示例

```json
{
  "available_qualities": [
    {"ratio": "540p", "size_mb": 34.18, "cdn_url": "..."},
    {"ratio": "720p", "size_mb": 33.74, "cdn_url": "..."},
    {"ratio": "original", "size_mb": 44.88, "cdn_url": "..."}
  ],
  "recommended_ratio": "original"
}
```

**去重逻辑**：抖音对不存在的清晰度会回退到原始流（同文件大小）。探测时按文件大小分组，相同大小的合并为 "original"，只保留真正转码的不同清晰度。

## MCP 注册信息

```bash
# 已注册命令（使用自动重载包装器）
claude mcp add --transport stdio --scope user douyin-video -- python D:\Tools\AI\Claude-code\douyin-mcp-server\reload_wrapper.py

# 配置位置
C:\Users\juzi\.claude.json (user scope)

# 查看状态
claude mcp list
```

> **自动重载**：通过 `reload_wrapper.py` + `watchdog` 监听 `.py` 文件变化，代码修改后 MCP 进程自动重启，无需手动操作。
> **注意**：首次配置后需要重启 Claude Code 会话，`reload_wrapper.py` 才会生效。
> **限制**：自动重载仅对已有工具的代码修改生效（bug 修复、逻辑优化）。**新增工具需要重启 Claude Code 会话**，因为 MCP 客户端在启动时缓存工具列表，运行中不会重新发现。

## 依赖

```
mcp[cli]>=1.2.0
requests>=2.28.0
jsonpath>=0.82
watchdog>=3.0.0
```

已通过 `pip install -r requirements.txt` 安装完成。

## 架构特点

- **自适应清晰度**：并行探测所有比率（240p~4k），按文件大小去重，返回真实可用选项
- **Session 复用**：模块级 `requests.Session()` 复用 TCP 连接
- **LRU 缓存**：`_fetch_video_info` 和 `_probe_qualities` 使用 `@lru_cache(maxsize=128)`
- **超时控制**：所有请求统一 `timeout=10s`（解析）、`timeout=60s`（下载）
- **退避重试**：CDN 链接解析使用指数退避 `0.5 * 2^i` 秒，最多 5 次
- **URL 校验**：入口校验链接格式，不合法直接返回错误
- **代理支持**：自动读取 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量
- **文件名清理**：自动去掉 `#标签`、非法字符，截断至 60 字符

## 修复记录

### 2026-05-05: 旧 API 失效修复

**问题**：`iesdouyin.com/web/api/v2/aweme/iteminfo/` 返回 `encrypt_data_miss`（状态码 11110），抖音反爬策略升级。

**修复**：改用分享页 `_ROUTER_DATA` 方案提取视频信息。

### 2026-05-05: 全面优化重构

**变更**：
1. **合并工具**：`parse_douyin_video` 直接返回最终 CDN 链接，无需再调 `extract_download_link`
2. **新增工具**：`parse_batch`、`download_video`、`download_batch`
3. **代码质量**：删除未使用的 `DOUYIN_CDN_DOMAINS`（89 个域名）、合并重复逻辑
4. **健壮性**：所有请求加 timeout、URL 校验、指数退避重试
5. **性能**：`requests.Session()` 复用、`@lru_cache` 缓存
6. **代理**：自动从环境变量读取代理配置

### 2026-05-05: 自适应清晰度

**发现**：抖音对不同比率的处理不一致：
- 存在的比率返回转码版本（文件更小）
- 不存在的比率有的返回原始流（同大小），有的返回 0 字节
- `bit_rate` 字段始终为 None，无法从 API 直接获取可用清晰度

**方案**：
1. 并行探测 8 个比率（240p/360p/480p/540p/720p/1080p/1440p/4k）
2. 通过 HEAD 请求获取每个比率的 CDN 文件大小
3. 按文件大小分组，相同大小的归为"原始流回退"
4. 去重后保留：实际转码选项 + 原始画质（标记为 "original"）
5. `ratio="original"` 时直接使用探测到的 CDN URL，不重新解析

## 验证结果（2026-05-05）

| 测试项 | 结果 |
|--------|------|
| URL 校验（无效链接） | `{'error': '无效的抖音链接...'}` |
| 真实链接解析 | 成功，返回标题/作者/CDN 链接 |
| download_video 下载 | 33.74MB，路径正确 |
| LRU 缓存 | 首次 11s → 缓存命中 0.0000s |
| 清晰度探测 | 拉丁舞：540p/720p/original；兰陵王：540p/720p/original |
| ratio="original" | 正确返回原始画质 CDN 链接（44.88MB） |
| MCP 工具注册 | 4 个工具全部注册成功 |

## 新会话待办

1. **必须**：重启 Claude Code 会话让 `reload_wrapper.py` 生效（首次配置后需要）
2. 之后代码改动会自动重载，无需手动操作
3. 如果抖音 API 再次变更，检查 `_ROUTER_DATA` 提取逻辑和页面结构

## 源项目

原始 Flask 项目位于 `D:\Tools\AI\Claude-code\flask_watermark_mvc`，本项目从中重构而来，去除了 Flask/MySQL/模板等依赖。

## 功能拓展路线图

### 已规划

| 功能 | 工具名 | 说明 | 优先级 | 状态 |
|------|--------|------|--------|------|
| 封面下载 | `download_cover` | 单独下载视频封面图 | P0 | ✅ 已完成 |
| 音频提取 | `extract_audio` | 从视频中分离音频（需 ffmpeg） | P0 | ✅ 已完成 |
| 用户主页解析 | `parse_user_videos` | 输入用户主页链接，批量获取该用户所有视频 | P1 | ✅ 已完成 |
| 下载历史记录 | `list_download_history` | SQLite 记录已下载视频，支持去重和查询 | P1 | ✅ 已完成 |

### 待评估

| 功能 | 说明 | 难度 |
|------|------|------|
| 视频评论抓取 | 获取视频的热门评论内容 | 中 |
| 视频搜索 | 按关键词搜索抖音视频（需登录态） | 高 |
| 直播流录制 | 抓取直播间 m3u8 流并录制 | 高 |
| 字幕提取 | 提取视频中的自动字幕（如有） | 中 |
