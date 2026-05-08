# Douyin Video CLI

抖音视频去水印解析命令行工具，供 Claude Code CLI 或终端直接使用。

## 功能

| 命令 | 说明 |
|------|------|
| `douyin parse <url>` | 解析抖音链接，返回元数据 + 无水印 CDN 链接 |
| `douyin parse-batch <urls...>` | 批量解析，内部并行执行 |
| `douyin download <url>` | 解析 + 下载，自动记录历史并去重 |
| `douyin download-batch <urls...>` | 批量下载，内部并行执行 |
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

## 安装

```bash
cd D:\Tools\AI\Claude-code\douyin-mcp-server
pip install -r requirements.txt
```

## 配置 Claude Code

将以下内容添加到 Claude Code 的 CLAUDE.md 或直接在会话中使用：

```
下载抖音视频: python D:\Tools\AI\Claude-code\douyin-mcp-server\cli.py download "<url>" --pretty
```

## 架构

```
douyin-mcp-server/
├── cli.py               # CLI 入口（argparse 子命令）
├── server.py            # MCP 模式入口（FastMCP, 可选）
├── douyin_parser.py     # 核心解析逻辑（清晰度探测、CDN 解析、下载）
├── history.py           # SQLite 下载历史记录
├── constants.py         # 请求头、超时、重试常量
├── requirements.txt     # 依赖：requests, cachetools
└── videos/              # 下载目录 + history.db
```

### 关键设计

- **自适应清晰度**：并行探测 8 个比率（240p~4k），按字节大小精确去重
- **TTL 缓存**：`cachetools.TTLCache`（30 分钟过期），避免 CDN 链接失效
- **断点续传**：下载支持 `Range` 请求头，网络中断后可继续
- **路径安全**：`_sanitize_filename` + `os.path.basename` + `os.path.realpath` 三重防护
- **Session 复用**：模块级 `requests.Session()` 复用 TCP 连接
- **指数退避**：CDN 解析重试使用 `0.5 * 2^i` 秒退避，429 状态码额外等待
- **SQLite 历史**：自动记录下载，支持去重和关键词搜索

## 依赖

| 包 | 用途 |
|----|------|
| `requests>=2.28.0` | HTTP 请求 |
| `cachetools>=5.0.0` | TTL 缓存 |

可选：`ffmpeg`（音频提取功能需要）

## MCP 模式

如需 MCP 模式（供 Claude Code MCP 协议使用），额外安装：

```bash
pip install "mcp[cli]>=1.2.0"
claude mcp add --transport stdio --scope user douyin-video -- python D:\Tools\AI\Claude-code\douyin-mcp-server\server.py
```

## 待评估功能

| 功能 | 说明 | 难度 |
|------|------|------|
| 视频搜索 | 按关键词搜索（需登录态） | 高 |
| 直播流录制 | 抓取直播间 m3u8 流 | 高 |
| 字幕提取 | 提取自动字幕（如有） | 中 |
