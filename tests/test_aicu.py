"""aicu.py 单元测试：get_user_medals / get_user_comments / get_user_danmaku / get_user_live_danmaku。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bilibili_mcp import aicu


# ─── 辅助工厂 ────────────────────────────────────────────────────────────────

def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


def _patch_get(json_data: dict, status_code: int = 200):
    """直接 patch aicu._get，返回指定数据。"""
    return patch(
        "bilibili_mcp.aicu._get",
        new=AsyncMock(return_value={"code": 0, **json_data} if status_code == 200 else {}),
    )


def _patch_get_raw(return_value: dict):
    """patch _get 返回完整 dict（含 code 字段）。"""
    return patch("bilibili_mcp.aicu._get", new=AsyncMock(return_value=return_value))


def _patch_get_error(message: str = "查询失败"):
    """patch _get 抛出 ValueError。"""
    return patch("bilibili_mcp.aicu._get", new=AsyncMock(side_effect=ValueError(f"aicu.cc 错误: {message}")))


# ─── get_user_medals ─────────────────────────────────────────────────────────

MEDALS_DATA = {
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
    with _patch_get_raw(MEDALS_DATA):
        result = await aicu.get_user_medals(uid=12345)

    assert result["uid"] == 12345
    assert result["total"] == 2
    assert result["medals"][0]["name"] == "小破站"
    assert result["medals"][0]["level"] == 21
    assert result["medals"][0]["ruid"] == 111


@pytest.mark.asyncio
async def test_get_user_medals_empty():
    with _patch_get_raw({"code": 0, "data": {"list": []}}):
        result = await aicu.get_user_medals(uid=12345)

    assert result["total"] == 0
    assert result["medals"] == []


@pytest.mark.asyncio
async def test_get_user_medals_api_error():
    with _patch_get_error("用户不存在"):
        with pytest.raises(ValueError, match="aicu.cc 错误"):
            await aicu.get_user_medals(uid=0)


# ─── get_user_comments ───────────────────────────────────────────────────────

COMMENTS_DATA = {
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
    with _patch_get_raw(COMMENTS_DATA):
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
    mock_get = AsyncMock(return_value=COMMENTS_DATA)
    with patch("bilibili_mcp.aicu._get", mock_get):
        result = await aicu.get_user_comments(uid=12345, page=2, page_size=10, mode=1)

    assert result["page"] == 2
    assert result["page_size"] == 10
    assert result["mode"] == 1
    # 验证请求参数透传
    call_args = mock_get.call_args
    params = call_args[0][1]
    assert params["pn"] == 2
    assert params["ps"] == 10
    assert params["mode"] == 1


@pytest.mark.asyncio
async def test_get_user_comments_api_error():
    with _patch_get_error("查询失败"):
        with pytest.raises(ValueError, match="aicu.cc 错误"):
            await aicu.get_user_comments(uid=0)


# ─── get_user_danmaku ─────────────────────────────────────────────────────────

DANMAKU_DATA = {
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
    with _patch_get_raw(DANMAKU_DATA):
        result = await aicu.get_user_danmaku(uid=12345)

    assert result["uid"] == 12345
    assert result["total"] == 500
    assert len(result["danmaku"]) == 2
    assert result["danmaku"][0]["content"] == "哈哈哈"
    assert result["danmaku"][0]["progress_ms"] == 12000
    assert result["danmaku"][0]["oid"] == 77777


@pytest.mark.asyncio
async def test_get_user_danmaku_empty():
    with _patch_get_raw({"code": 0, "data": {"cursor": {"all_count": 0, "is_end": True}, "videodmlist": []}}):
        result = await aicu.get_user_danmaku(uid=12345)

    assert result["total"] == 0
    assert result["danmaku"] == []
    assert result["is_end"] is True


@pytest.mark.asyncio
async def test_get_user_danmaku_api_error():
    with _patch_get_error("服务异常"):
        with pytest.raises(ValueError, match="aicu.cc 错误"):
            await aicu.get_user_danmaku(uid=0)


# ─── get_user_live_danmaku ────────────────────────────────────────────────────

LIVE_DANMAKU_DATA = {
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
    with _patch_get_raw(LIVE_DANMAKU_DATA):
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
    with _patch_get_raw({"code": 0, "data": {"cursor": {"all_count": 0, "is_end": True}, "list": []}}):
        result = await aicu.get_user_live_danmaku(uid=12345)

    assert result["total"] == 0
    assert result["live_danmaku"] == []


@pytest.mark.asyncio
async def test_get_user_live_danmaku_api_error():
    with _patch_get_error("查询失败"):
        with pytest.raises(ValueError, match="aicu.cc 错误"):
            await aicu.get_user_live_danmaku(uid=0)
