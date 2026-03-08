"""aicu.py 单元测试：get_user_medals / get_user_comments / get_user_danmaku / get_user_live_danmaku。"""

import pytest
import httpx

from unittest.mock import AsyncMock, MagicMock, patch
from bilibili_mcp import aicu


# ─── 辅助工厂 ────────────────────────────────────────────────────────────────

def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _patch_client(json_data: dict):
    """返回 patch 上下文，mock httpx.AsyncClient.get 返回指定数据。"""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=_mock_response(json_data))
    return patch("bilibili_mcp.aicu.httpx.AsyncClient", return_value=mock_client), mock_client


# ─── get_user_medals ─────────────────────────────────────────────────────────

MEDALS_RESPONSE = {
    "code": 0,
    "data": {
        "list": [
            {"name": "小破站", "level": 21, "ruid": 111},
            {"name": "老粉丝", "level": 5, "ruid": 222},
        ]
    },
}


@pytest.mark.asyncio
async def test_get_user_medals_success():
    ctx, _ = _patch_client(MEDALS_RESPONSE)
    with ctx:
        result = await aicu.get_user_medals(uid=12345)

    assert result["uid"] == 12345
    assert result["total"] == 2
    assert result["medals"][0]["name"] == "小破站"
    assert result["medals"][0]["level"] == 21
    assert result["medals"][0]["ruid"] == 111


@pytest.mark.asyncio
async def test_get_user_medals_empty():
    ctx, _ = _patch_client({"code": 0, "data": {"list": []}})
    with ctx:
        result = await aicu.get_user_medals(uid=12345)

    assert result["total"] == 0
    assert result["medals"] == []


@pytest.mark.asyncio
async def test_get_user_medals_api_error():
    ctx, _ = _patch_client({"code": -1, "message": "用户不存在"})
    with ctx:
        with pytest.raises(ValueError, match="aicu.cc 错误"):
            await aicu.get_user_medals(uid=0)


# ─── get_user_comments ───────────────────────────────────────────────────────

COMMENTS_RESPONSE = {
    "code": 0,
    "data": {
        "cursor": {"all_count": 100, "is_end": False},
        "replies": [
            {"rpid": 1001, "message": "好视频", "time": 1700000000, "dyn": {"oid": 9999, "type": 1}},
            {"rpid": 1002, "message": "支持一下", "time": 1700000001, "dyn": {"oid": 8888, "type": 1}},
        ],
    },
}


@pytest.mark.asyncio
async def test_get_user_comments_success():
    ctx, _ = _patch_client(COMMENTS_RESPONSE)
    with ctx:
        result = await aicu.get_user_comments(uid=12345)

    assert result["uid"] == 12345
    assert result["total"] == 100
    assert result["is_end"] is False
    assert len(result["comments"]) == 2
    assert result["comments"][0]["rpid"] == 1001
    assert result["comments"][0]["message"] == "好视频"
    assert result["comments"][0]["oid"] == 9999


@pytest.mark.asyncio
async def test_get_user_comments_pagination():
    ctx, mock_client = _patch_client(COMMENTS_RESPONSE)
    with ctx:
        result = await aicu.get_user_comments(uid=12345, page=2, page_size=10, mode=1)

    assert result["page"] == 2
    assert result["page_size"] == 10
    assert result["mode"] == 1
    # 验证请求参数
    call_kwargs = mock_client.get.call_args
    assert call_kwargs.kwargs["params"]["pn"] == 2
    assert call_kwargs.kwargs["params"]["ps"] == 10
    assert call_kwargs.kwargs["params"]["mode"] == 1


@pytest.mark.asyncio
async def test_get_user_comments_api_error():
    ctx, _ = _patch_client({"code": -1, "message": "查询失败"})
    with ctx:
        with pytest.raises(ValueError, match="aicu.cc 错误"):
            await aicu.get_user_comments(uid=0)


# ─── get_user_danmaku ─────────────────────────────────────────────────────────

DANMAKU_RESPONSE = {
    "code": 0,
    "data": {
        "cursor": {"all_count": 500, "is_end": False},
        "videodmlist": [
            {"id": 2001, "content": "哈哈哈", "ctime": 1700000000, "oid": 77777, "progress": 12000},
            {"id": 2002, "content": "666", "ctime": 1700000010, "oid": 77777, "progress": 30000},
        ],
    },
}


@pytest.mark.asyncio
async def test_get_user_danmaku_success():
    ctx, _ = _patch_client(DANMAKU_RESPONSE)
    with ctx:
        result = await aicu.get_user_danmaku(uid=12345)

    assert result["uid"] == 12345
    assert result["total"] == 500
    assert len(result["danmaku"]) == 2
    assert result["danmaku"][0]["content"] == "哈哈哈"
    assert result["danmaku"][0]["progress_ms"] == 12000
    assert result["danmaku"][0]["oid"] == 77777


@pytest.mark.asyncio
async def test_get_user_danmaku_empty():
    ctx, _ = _patch_client({"code": 0, "data": {"cursor": {"all_count": 0, "is_end": True}, "videodmlist": []}})
    with ctx:
        result = await aicu.get_user_danmaku(uid=12345)

    assert result["total"] == 0
    assert result["danmaku"] == []
    assert result["is_end"] is True


@pytest.mark.asyncio
async def test_get_user_danmaku_api_error():
    ctx, _ = _patch_client({"code": -1, "message": "服务异常"})
    with ctx:
        with pytest.raises(ValueError, match="aicu.cc 错误"):
            await aicu.get_user_danmaku(uid=0)


# ─── get_user_live_danmaku ────────────────────────────────────────────────────

LIVE_DANMAKU_RESPONSE = {
    "code": 0,
    "data": {
        "cursor": {"all_count": 3, "is_end": True},
        "list": [
            {
                "roominfo": {"roomid": 80397, "upname": "主播A", "upuid": 7706705, "roomname": "看看lpl"},
                "danmu": [
                    {"text": "666", "ts": 1700000000},
                    {"text": "牛啊", "ts": 1700000005},
                ],
            },
            {
                "roominfo": {"roomid": 21195828, "upname": "主播B", "upuid": 271887040, "roomname": "杂谈"},
                "danmu": [
                    {"text": "哈哈", "ts": 1700001000},
                ],
            },
        ],
    },
}


@pytest.mark.asyncio
async def test_get_user_live_danmaku_success():
    ctx, _ = _patch_client(LIVE_DANMAKU_RESPONSE)
    with ctx:
        result = await aicu.get_user_live_danmaku(uid=12345)

    assert result["uid"] == 12345
    assert result["total"] == 3
    assert result["is_end"] is True
    assert len(result["live_danmaku"]) == 2

    first = result["live_danmaku"][0]
    assert first["room_id"] == 80397
    assert first["up_name"] == "主播A"
    assert first["up_uid"] == 7706705
    assert first["room_name"] == "看看lpl"
    assert len(first["danmaku"]) == 2
    assert first["danmaku"][0]["text"] == "666"


@pytest.mark.asyncio
async def test_get_user_live_danmaku_empty():
    ctx, _ = _patch_client({"code": 0, "data": {"cursor": {"all_count": 0, "is_end": True}, "list": []}})
    with ctx:
        result = await aicu.get_user_live_danmaku(uid=12345)

    assert result["total"] == 0
    assert result["live_danmaku"] == []


@pytest.mark.asyncio
async def test_get_user_live_danmaku_api_error():
    ctx, _ = _patch_client({"code": -1, "message": "查询失败"})
    with ctx:
        with pytest.raises(ValueError, match="aicu.cc 错误"):
            await aicu.get_user_live_danmaku(uid=0)
