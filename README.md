# bilibili-mcp-server

B 站 MCP Server，为 AI 助手提供查询 B 站数据的能力。

## 功能

| Tool | 描述 |
|------|------|
| `search_user` | 按用户名搜索用户，返回 UID、昵称、粉丝数等 |
| `get_live_status` | 查询主播直播间开播状态（未开播/直播中/轮播中） |
| `get_user_medals` | 查询用户持有的粉丝牌列表 |
| `get_user_comments` | 查询用户历史评论记录 |
| `get_user_danmaku` | 查询用户在视频中发送的历史弹幕 |
| `get_user_live_danmaku` | 查询用户在直播间发送的历史弹幕 |
| `get_live_content` | 录制直播片段，ASR 语音转录 + 视觉画面分析，描述直播内容 |

> 粉丝牌、历史评论、历史弹幕数据来源于 [aicu.cc](https://www.aicu.cc/)，数据非实时，有更新延迟。
> `get_live_content` 需要硅基流动 API Key，通过环境变量 `SILICONFLOW_API_KEY` 配置。

---

## 本地安装（Cursor / Claude Desktop）

需要 Python 3.10+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
cd bilibili-mcp-server
uv venv
uv pip install -e .
```

### 配置到 Cursor

在 `~/.cursor/mcp.json` 或项目级 `.cursor/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "bilibili": {
      "command": "uv",
      "args": ["run", "--directory", "D:/projects/bilibili-mcp-server", "bilibili-mcp"],
      "env": {
        "SILICONFLOW_API_KEY": "sk-你的硅基流动Key"
      }
    }
  }
}
```

### 配置到 Claude Desktop

在 `%APPDATA%\Claude\claude_desktop_config.json` 中添加（内容同上）。

---

## 云端部署（ModelScope MCP 广场）

### 1. 上传代码到 ModelScope

将项目推送到 ModelScope 的 Studio 仓库（类似 Hugging Face Space）。

### 2. 配置环境变量 / Secret

在 ModelScope Studio 的「**设置 → 环境变量**」中添加：

| 变量名 | 说明 |
|--------|------|
| `SILICONFLOW_API_KEY` | 硅基流动 API Key（**设为 Secret，不对外展示**） |
| `MCP_TRANSPORT` | 设为 `sse`（ModelScope 使用 SSE 模式） |
| `MCP_PORT` | 设为 `7860`（ModelScope Studio 默认端口，可不填） |

### 3. 启动命令

在 Studio 配置中设置启动命令为：

```bash
python app.py
```

或者使用 uv：

```bash
uv run python app.py
```

### 4. 获取 SSE 地址并在客户端配置

ModelScope 会为你的服务生成一个专属 SSE 地址，格式类似：

```
https://modelscope.cn/studios/你的用户名/bilibili-mcp/sse
```

在 Cursor / Claude Desktop 中配置远程 MCP：

```json
{
  "mcpServers": {
    "bilibili": {
      "url": "https://modelscope.cn/studios/你的用户名/bilibili-mcp/sse"
    }
  }
}
```

> **注意**：SSE URL 是你的专属地址，包含鉴权信息，请勿对外泄露。

---

## 关于 `get_live_content` 的 API Key

`SILICONFLOW_API_KEY` 的优先级：

1. 调用工具时显式传入的 `api_key` 参数（最高）
2. 环境变量 `SILICONFLOW_API_KEY`（推荐，在 MCP 配置或云端 Secret 中设置）

**推荐做法**：在 MCP 配置的 `env` 或云端 Secret 中配置，对话中无需每次传入 Key。

---

## 使用示例

- "帮我查一下 xxx 主播现在有没有在直播"
- "查一下 UID 为 12345 的用户最近发了哪些评论"
- "xxx 用户持有哪些粉丝牌"
- "510 直播间现在在播什么内容？"（触发 `get_live_content`，录制 15 秒分析）

---

## 数据说明

- **直播状态**：B 站官方 API，实时数据，无需登录
- **粉丝牌、历史评论、历史弹幕**：aicu.cc，非实时，有更新延迟
- **直播内容分析**：ffmpeg 录制 + 硅基流动 SenseVoiceSmall（ASR）+ Qwen3-VL（视觉），需 API Key
