# 抖音视频 MCP Server - 项目交接文档

## 项目概述

将 `flask_watermark_mvc`（微信云托管 Flask 服务）重构为 MCP Server，供 Claude Code CLI 通过 MCP 协议直接调用抖音视频去水印解析功能。

## 当前状态

- **MCP Server 已创建并注册** — `douyin-video` (user scope，全局可用)
- **服务器连接正常** — `claude mcp list` 显示 ✓ Connected
- **8 个工具已注册** — 解析、下载、封面、音频、用户主页、历史记录
- **代码审查已完成** — 17 个问题全部修复（2 严重 + 5 中等 + 10 轻微）
- **GitHub 仓库** — https://github.com/juziguai/douyin-mcp-server

## 项目结构

```
D:\Tools\AI\Claude-code\douyin-mcp-server\
├── server.py              # MCP 工具定义（FastMCP, stdio 传输）
├── douyin_parser.py       # 核心解析逻辑（清晰度探测、CDN 解析、下载）
├── history.py             # SQLite 下载历史记录
├── constants.py           # 请求头、超时、重试常量
├── reload_wrapper.py      # 自动重载包装器（watchdog 监听 .py 变化）
├── requirements.txt       # 生产依赖：mcp[cli], requests, cachetools
├── requirements-dev.txt   # 开发依赖：watchdog
├── README.md              # 使用说明 + 架构图
├── HANDOVER.md            # 本文档
└── videos/                # 下载目录 + history.db
```

## MCP 工具

| 工具名 | 参数 | 功能 |
|--------|------|------|
| `parse_douyin_video` | `share_url, ratio?` | 解析抖音链接，返回元数据 + CDN 链接 |
| `parse_batch` | `share_urls, ratio?` | 批量解析（并行执行） |
| `download_video` | `share_url, filename?, save_dir?, ratio?` | 解析 + 下载，自动记录历史并去重 |
| `download_batch` | `share_urls, save_dir?, ratio?` | 批量下载（并行执行） |
| `download_cover` | `share_url, save_dir?, filename?` | 下载视频封面图 |
| `extract_audio` | `share_url, save_dir?, filename?, ratio?` | 提取音频为 MP3（需 ffmpeg） |
| `parse_user_videos` | `user_url, max_count?` | 获取用户主页视频列表（最多 50 个） |
| `list_download_history` | `limit?, file_type?, keyword?` | 查询下载历史（按类型/关键词筛选） |

### ratio 参数

| 值 | 说明 |
|----|------|
| `None`（默认） | 自动探测所有可用清晰度，返回 `available_qualities` 列表 |
| `"720p"` / `"540p"` 等 | 指定转码版本 |
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

**去重逻辑**：抖音对不存在的清晰度会回退到原始流（同文件大小）。探测时按字节大小精确分组，相同大小的合并为 "original"，只保留真正转码的不同清晰度。

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

| 包 | 版本 | 用途 |
|----|------|------|
| `mcp[cli]` | >=1.2.0 | MCP 协议 |
| `requests` | >=2.28.0 | HTTP 请求 |
| `cachetools` | >=5.0.0 | TTL 缓存（30 分钟过期） |
| `watchdog` | >=3.0.0 | 文件监听（仅开发，`requirements-dev.txt`） |

可选：`ffmpeg`（音频提取功能需要）

## 架构特点

- **自适应清晰度**：并行探测 8 个比率（240p~4k），按字节大小精确去重
- **TTL 缓存**：`cachetools.TTLCache`（30 分钟过期），避免 CDN 链接失效
- **括号计数 JSON 提取**：替代正则匹配，避免 `</script>` 截断问题
- **断点续传**：下载支持 `Range` 请求头，网络中断后可继续
- **路径安全**：`_sanitize_filename` + `os.path.basename` + `os.path.realpath` 三重防护
- **Session 复用**：模块级 `requests.Session()` 复用 TCP 连接
- **指数退避**：CDN 解析重试使用 `0.5 * 2^i` 秒，429 状态码额外等待 5 秒
- **批量并行**：`parse_batch` / `download_batch` 使用 `ThreadPoolExecutor` 并行执行
- **SQLite 历史**：自动记录下载记录，支持去重和关键词搜索
- **请求头补全**：Accept、Accept-Language、Referer 等，降低反爬风险

## 代码审查修复记录（2026-05-05）

### 严重

| 编号 | 问题 | 修复 |
|------|------|------|
| C-1 | `_probe_qualities` 重复定义，第一次是死代码 | 删除死代码，重命名为 `_probe_qualities_impl` |
| C-2 | `filename` / `save_dir` 路径遍历漏洞 | 添加 `..` 过滤 + `os.path.basename` + `realpath` 校验 |

### 中等

| 编号 | 问题 | 修复 |
|------|------|------|
| I-1 | `_ROUTER_DATA` 正则匹配到 `</script>` 截断 | 改用括号计数法提取完整 JSON |
| I-2 | `@lru_cache` 无 TTL，CDN 链接过期后失效 | 替换为 `cachetools.TTLCache`（30 分钟） |
| I-3 | 文件大小去重用 MB 四舍五入，精度不够 | 改用精确字节数比较 |
| I-4 | 下载文件静默覆盖 | 写入前检查文件是否存在 |
| I-5 | 请求头只有 User-Agent | 补充 Accept/Accept-Language/Referer |

### 轻微

| 编号 | 问题 | 修复 |
|------|------|------|
| S-1 | URL 正则 `\w+` 过于宽松 | 收紧为 `[a-zA-Z0-9]{6,12}` |
| S-2 | `Counter` 在函数内重复导入 | 移至文件顶部 |
| S-3 | 重试逻辑未处理 429 状态码 | 检测 429 时额外等待 5 秒 |
| S-4 | README.md 仍列出已移除的工具 | 更新工具列表 |
| S-5 | `jsonpath` 依赖未使用 | 从 requirements.txt 移除 |
| S-6 | `watchdog` 应分离为开发依赖 | 移至 requirements-dev.txt |
| S-7 | 类型标注 `str = None` 不规范 | 改为 `str \| None = None` |
| S-8 | `parse_batch` 串行执行 | 使用 `ThreadPoolExecutor` 并行化 |
| S-9 | 下载不支持断点续传 | 支持 `Range` 请求头 |
| S-10 | `reload_wrapper.py` 缺防抖 | 加入 1 秒防抖 |

## 验证结果

| 测试项 | 结果 |
|--------|------|
| URL 校验（无效链接） | `{'error': '无效的抖音链接...'}` |
| 真实链接解析 | 成功，返回标题/作者/CDN 链接 |
| download_video 下载 | 33.74MB，路径正确 |
| TTL 缓存 | 首次解析后缓存命中，30 分钟后自动过期 |
| 清晰度探测 | 540p/720p/original 按字节去重 |
| ratio="original" | 正确返回原始画质 CDN 链接（44.88MB） |
| MCP 工具注册 | 8 个工具全部注册成功 |
| 路径遍历防护 | `../../etc/passwd` → `____etc_passwd` |
| 断点续传 | Range 请求头正确处理 206/416 状态码 |
| 批量并行 | parse_batch / download_batch 并行执行 |
| 下载历史 | SQLite 记录正确，去重和搜索功能正常 |

## 新会话待办

1. **必须**：重启 Claude Code 会话让新工具生效（首次配置后需要）
2. 之后代码改动会自动重载，无需手动操作
3. 如果抖音 API 再次变更，检查 `_ROUTER_DATA` 提取逻辑和页面结构
4. 音频提取功能需要安装 ffmpeg

## 源项目

原始 Flask 项目位于 `D:\Tools\AI\Claude-code\flask_watermark_mvc`，本项目从中重构而来，去除了 Flask/MySQL/模板等依赖。

## 待评估功能

| 功能 | 说明 | 难度 |
|------|------|------|
| 视频评论抓取 | 获取视频的热门评论内容 | 中 |
| 视频搜索 | 按关键词搜索抖音视频（需登录态） | 高 |
| 直播流录制 | 抓取直播间 m3u8 流并录制 | 高 |
| 字幕提取 | 提取视频中的自动字幕（如有） | 中 |
