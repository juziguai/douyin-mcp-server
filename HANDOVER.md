# 抖音视频 CLI - 项目交接文档

## 项目概述

将 `flask_watermark_mvc`（微信云托管 Flask 服务）重构为 CLI 工具，供 Claude Code 或终端直接调用抖音视频去水印解析功能。同时保留 MCP 模式作为备选。

## 当前状态

- **CLI 模式已就绪** — `python cli.py <command>` 直接调用
- **10 个子命令** — 解析、下载、封面、音频、用户主页、历史记录、批量操作
- **MCP 模式可选** — `server.py` 保留，需额外安装 `mcp[cli]`
- **GitHub 仓库** — https://github.com/juziguai/douyin-mcp-server

## 项目结构

```
D:\Tools\AI\Claude-code\douyin-mcp-server\
├── cli.py               # CLI 入口（argparse 子命令）
├── server.py            # MCP 模式入口（FastMCP, 可选）
├── douyin_parser.py     # 核心解析逻辑（清晰度探测、CDN 解析、下载）
├── history.py           # SQLite 下载历史记录
├── constants.py         # 请求头、超时、重试常量
├── reload_wrapper.py    # MCP 模式自动重载包装器（可选）
├── requirements.txt     # 依赖：requests, cachetools
├── README.md            # 使用说明 + 架构图
├── HANDOVER.md          # 本文档
└── videos/              # 下载目录 + history.db
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `douyin parse <url>` | 解析抖音链接，返回元数据 + CDN 链接 |
| `douyin parse-batch <urls...>` | 批量解析（并行执行） |
| `douyin download <url>` | 解析 + 下载，自动记录历史并去重 |
| `douyin download-batch <urls...>` | 批量下载（并行执行） |
| `douyin download-cover <url>` | 下载视频封面图 |
| `douyin download-user <user-url>` | 批量下载用户主页视频 |
| `douyin audio <url>` | 提取音频为 MP3（需 ffmpeg） |
| `douyin user-videos <user-url>` | 获取用户主页视频列表（最多 50 个） |
| `douyin history` | 查询下载历史（按类型/关键词筛选） |
| `douyin delete-history` | 删除下载记录（可选删除本地文件） |

### 通用选项

| 选项 | 说明 |
|------|------|
| `--pretty` | 美化 JSON 输出 |
| `--ratio` | 指定清晰度：`720p`、`540p`、`original` 等 |
| `--save-dir` | 自定义保存目录 |
| `--filename` | 自定义文件名（不含扩展名） |

## 用法示例

```bash
# 解析视频（查看清晰度列表）
python cli.py parse "https://v.douyin.com/kp6deD7Gta8/" --pretty

# 下载最高画质
python cli.py download "https://v.douyin.com/kp6deD7Gta8/" --pretty

# 下载指定画质
python cli.py download "https://v.douyin.com/kp6deD7Gta8/" --ratio 720p

# 下载封面
python cli.py download-cover "https://v.douyin.com/kp6deD7Gta8/"

# 提取音频（需 ffmpeg）
python cli.py audio "https://v.douyin.com/kp6deD7Gta8/" --pretty

# 查看下载历史
python cli.py history --pretty

# 按关键词搜索历史
python cli.py history --keyword "声笙" --pretty

# 删除记录（同时删除文件）
python cli.py delete-history --id 1 --delete-file
```

## 配置 Claude Code

直接在会话中使用：

```
下载抖音视频: python D:\Tools\AI\Claude-code\douyin-mcp-server\cli.py download "<url>" --pretty
```

## 依赖

| 包 | 版本 | 用途 |
|----|------|------|
| `requests` | >=2.28.0 | HTTP 请求 |
| `cachetools` | >=5.0.0 | TTL 缓存（30 分钟过期） |

可选：`ffmpeg`（音频提取功能需要）

## 架构特点

- **自适应清晰度**：并行探测 8 个比率（240p~4k），按字节大小精确去重
- **TTL 缓存**：`cachetools.TTLCache`（30 分钟过期），避免 CDN 链接失效
- **括号计数 JSON 提取**：替代正则匹配，避免 `</script>` 截断问题
- **断点续传**：下载支持 `Range` 请求头，网络中断后可继续
- **路径安全**：`_sanitize_filename` + `os.path.basename` + `os.path.realpath` 三重防护
- **Session 复用**：模块级 `requests.Session()` 复用 TCP 连接
- **指数退避**：CDN 解析重试使用 `0.5 * 2^i` 秒，429 状态码额外等待 5 秒
- **批量并行**：`parse-batch` / `download-batch` 使用 `ThreadPoolExecutor` 并行执行
- **SQLite 历史**：自动记录下载记录，支持去重和关键词搜索

## 代码审查修复记录

### 2026-05-05 初始审查

| 编号 | 问题 | 修复 |
|------|------|------|
| C-1 | `_probe_qualities` 重复定义 | 删除死代码，重命名为 `_probe_qualities_impl` |
| C-2 | 路径遍历漏洞 | 添加 `realpath` 校验 |
| I-1 | `_ROUTER_DATA` 正则截断 | 改用括号计数法 |
| I-2 | `@lru_cache` 无 TTL | 替换为 `TTLCache` |
| I-3 | 文件大小去重精度不够 | 改用字节数比较 |
| I-4 | 下载静默覆盖 | 写入前检查文件存在 |
| I-5 | 请求头不完整 | 补充 Accept/Accept-Language/Referer |

### 2026-05-08 CLI 重构

| 编号 | 问题 | 修复 |
|------|------|------|
| B-1 | `download_cover` 路径遍历 | 添加 `realpath` + `startswith` 校验 |
| B-2 | `aweme_id` 格式不匹配 | 新增 `_DOUYIN_FULL_URL_RE`，支持完整 URL |
| B-3 | URL 验证只接受短链 | 同时接受 `v.douyin.com` 和 `www.douyin.com/video/` |
| — | MCP → CLI 重构 | 新增 `cli.py`，10 个子命令 |
| — | 评论 API 需登录态 | 移除 comments 功能（公开 API 不可用） |

## 验证结果

| 测试项 | 结果 |
|--------|------|
| `parse` 命令 | 成功解析，返回 3 个清晰度 |
| `download` 命令 | 2.57MB，下载成功 |
| `download-cover` 命令 | 18KB，下载成功 |
| `history` 命令 | 正确显示历史记录 |
| `delete-history` 命令 | 成功删除指定记录 |
| `--pretty` 输出 | JSON 格式化正常 |
| URL 校验（短链 + 完整链接） | 两种格式均通过 |

## MCP 模式（可选）

如需 MCP 模式：

```bash
pip install "mcp[cli]>=1.2.0"
claude mcp add --transport stdio --scope user douyin-video -- python D:\Tools\AI\Claude-code\douyin-mcp-server\server.py
```

## 待评估功能

| 功能 | 说明 | 难度 |
|------|------|------|
| 视频搜索 | 按关键词搜索抖音视频（需登录态） | 高 |
| 直播流录制 | 抓取直播间 m3u8 流并录制 | 高 |
| 字幕提取 | 提取视频中的自动字幕（如有） | 中 |

## 源项目

原始 Flask 项目位于 `D:\Tools\AI\Claude-code\flask_watermark_mvc`，本项目从中重构而来。
