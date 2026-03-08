"""B站 MCP Server 主入口，注册所有 MCP tools。"""

import asyncio
import os
from typing import Annotated

from fastmcp import FastMCP

from bilibili_mcp.bilibili import get_live_status as _get_live_status
from bilibili_mcp.bilibili import search_user as _search_user
from bilibili_mcp.aicu import get_user_comments as _get_user_comments
from bilibili_mcp.aicu import get_user_danmaku as _get_user_danmaku
from bilibili_mcp.aicu import get_user_live_danmaku as _get_user_live_danmaku
from bilibili_mcp.aicu import get_user_medals as _get_user_medals
from bilibili_mcp.live_content import DEFAULT_ASR_MODEL, DEFAULT_VL_MODEL
from bilibili_mcp.live_content import get_live_content as _get_live_content

mcp = FastMCP(
    name="bilibili-mcp-server",
    instructions=(
        "B站工具集，可查询主播开播状态、用户粉丝牌、历史评论、历史弹幕、直播弹幕，以及分析直播内容。\n"
        "如果只知道用户名而不知道 UID，请先调用 search_user 查找 UID。\n"
        "如需了解主播正在直播什么内容，使用 get_live_content（需提供硅基流动 API Key）。"
    ),
)


@mcp.tool()
async def search_user(
    keyword: Annotated[str, "搜索关键词，即用户昵称"],
    page: Annotated[int, "页码，从 1 开始"] = 1,
) -> dict:
    """搜索 B 站用户，返回匹配的用户列表（含 UID、昵称、粉丝数等）。

    当只知道用户名而不知道 UID 时，先调用此工具获取 UID，再调用其他工具查询详细数据。
    """
    return await _search_user(keyword=keyword, page=page)


@mcp.tool()
async def get_live_status(
    uid: Annotated[int | None, "主播的 B 站用户 UID（与 room_id 二选一）"] = None,
    room_id: Annotated[int | None, "直播间 ID（与 uid 二选一）"] = None,
) -> dict:
    """获取 B 站主播的直播间开播状态。

    返回直播状态（未开播/直播中/轮播中）、直播间标题、开播时间、在线人数等信息。
    uid 和 room_id 至少提供一个。
    """
    return await _get_live_status(uid=uid, room_id=room_id)


@mcp.tool()
async def get_user_medals(
    uid: Annotated[int, "B 站用户 UID"],
) -> dict:
    """获取指定用户持有的粉丝牌列表。

    返回该用户持有的所有粉丝牌，包含牌名、等级和对应主播的 UID。
    数据来源：aicu.cc（非实时，有更新延迟）。
    注意：aicu.cc 封锁云服务器 IP，此工具在云端部署时不可用，请使用本地部署。
    """
    return await _get_user_medals(uid=uid)


@mcp.tool()
async def get_user_comments(
    uid: Annotated[int, "B 站用户 UID"],
    page: Annotated[int, "页码，从 1 开始"] = 1,
    page_size: Annotated[int, "每页数量，最大 20"] = 20,
    mode: Annotated[int, "评论类型：0=全部, 1=主评论, 2=回复"] = 0,
) -> dict:
    """获取指定用户发表过的历史评论记录。

    返回评论内容、发送时间、所在视频/动态 ID 等信息。
    数据来源：aicu.cc（非实时，有更新延迟）。
    注意：aicu.cc 封锁云服务器 IP，此工具在云端部署时不可用，请使用本地部署。
    """
    return await _get_user_comments(uid=uid, page=page, page_size=page_size, mode=mode)


@mcp.tool()
async def get_user_danmaku(
    uid: Annotated[int, "B 站用户 UID"],
    page: Annotated[int, "页码，从 1 开始"] = 1,
    page_size: Annotated[int, "每页数量，最大 20"] = 20,
) -> dict:
    """获取指定用户在视频中发送过的历史弹幕记录。

    返回弹幕内容、发送时间、所在视频 ID、弹幕在视频中的时间轴位置（毫秒）。
    数据来源：aicu.cc（非实时，有更新延迟）。
    注意：aicu.cc 封锁云服务器 IP，此工具在云端部署时不可用，请使用本地部署。
    """
    return await _get_user_danmaku(uid=uid, page=page, page_size=page_size)


@mcp.tool()
async def get_user_live_danmaku(
    uid: Annotated[int, "B 站用户 UID"],
    page: Annotated[int, "页码，从 1 开始"] = 1,
    page_size: Annotated[int, "每页数量，最大 20"] = 20,
) -> dict:
    """获取指定用户在直播间发送过的历史弹幕记录。

    结果按直播间分组，每组包含主播信息和该直播间的弹幕列表。
    数据来源：aicu.cc（非实时，有更新延迟）。
    注意：aicu.cc 封锁云服务器 IP，此工具在云端部署时不可用，请使用本地部署。
    """
    return await _get_user_live_danmaku(uid=uid, page=page, page_size=page_size)


@mcp.tool()
async def get_live_content(
    room_id: Annotated[int, "直播间 ID"],
    duration: Annotated[int, "录制时长（秒），建议 10-30，默认 15"] = 15,
    vl_model: Annotated[str, f"视觉语言模型，默认 {DEFAULT_VL_MODEL}"] = DEFAULT_VL_MODEL,
    asr_model: Annotated[str, f"语音识别模型，默认 {DEFAULT_ASR_MODEL}"] = DEFAULT_ASR_MODEL,
) -> dict:
    """录制直播片段，同时进行 ASR 语音识别和视觉画面分析，综合描述直播内容。

    工作流程：
    1. 检查直播间是否在播；
    2. 获取直播流地址并用 ffmpeg 录制片段（无需系统安装 ffmpeg）；
    3. 并行执行：ASR 语音转录（SenseVoiceSmall）+ 视觉画面分析（Qwen3-VL）；
    4. 返回语音转录原文（transcript）和画面描述（visual）。

    硅基流动 API Key 通过服务端环境变量 SILICONFLOW_API_KEY 配置，无需在调用时传入。
    """
    return await _get_live_content(
        room_id=room_id,
        duration=duration,
        vl_model=vl_model,
        asr_model=asr_model,
    )


def main() -> None:
    # 支持通过环境变量切换传输协议，方便云端部署
    # MCP_TRANSPORT=sse        → SSE 模式（旧版 ModelScope/Claude Desktop 远程）
    # MCP_TRANSPORT=http       → Streamable HTTP 模式（新版标准，推荐）
    # MCP_TRANSPORT=stdio      → 标准 stdio（本地 Cursor/Claude Desktop，默认）
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    # ModelScope Studio 默认暴露 7860 端口；本地默认 8000
    port = int(os.environ.get("MCP_PORT", "7860"))

    if transport in ("sse", "http"):
        mcp.run(transport=transport, host=host, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
