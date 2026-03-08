"""bilibili.py 单元测试：search_user / get_live_status。"""

import pytest
import pytest_asyncio
import httpx

from unittest.mock import AsyncMock, MagicMock, patch
from bilibili_mcp import bilibili


# ─── 辅助工厂 ────────────────────────────────────────────────────────────────

def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.cookies = {}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_response_with_cookie(json_data: dict, cookie_val: str) -> MagicMock:
    resp = _mock_response(json_data)
    resp.cookies = {"buvid3": cookie_val}
    return resp


# ─── _get_buvid3 ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_buvid3_returns_cookie():
    bilibili._buvid3_cache = None
    mock_resp = _mock_response_with_cookie({}, "test-buvid3-value")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    result = await bilibili._get_buvid3(mock_client)
    assert result == "test-buvid3-value"
    assert bilibili._buvid3_cache == "test-buvid3-value"


@pytest.mark.asyncio
async def test_get_buvid3_uses_cache():
    bilibili._buvid3_cache = "cached-value"
    mock_client = AsyncMock()

    result = await bilibili._get_buvid3(mock_client)
    assert result == "cached-value"
    mock_client.get.assert_not_called()
    bilibili._buvid3_cache = None  # 清理


@pytest.mark.asyncio
async def test_get_buvid3_missing_cookie_returns_empty():
    bilibili._buvid3_cache = None
    mock_resp = _mock_response({})
    mock_resp.cookies = {}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    result = await bilibili._get_buvid3(mock_client)
    assert result == ""


# ─── search_user ─────────────────────────────────────────────────────────────

SEARCH_RESPONSE = {
    "code": 0,
    "data": {
        "numResults": 2,
        "result": [
            {"mid": 123, "uname": "TestUser", "fans": 1000, "videos": 50, "usign": "签名", "level": 5},
            {"mid": 456, "uname": "TestUser2", "fans": 500, "videos": 10, "usign": "", "level": 3},
        ],
    },
}


@pytest.mark.asyncio
async def test_search_user_success():
    bilibili._buvid3_cache = "buvid3-val"

    with patch("bilibili_mcp.bilibili.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(SEARCH_RESPONSE))
        MockClient.return_value = mock_client

        result = await bilibili.search_user("TestUser")

    assert result["total"] == 2
    assert len(result["users"]) == 2
    assert result["users"][0]["uid"] == 123
    assert result["users"][0]["uname"] == "TestUser"
    assert result["users"][0]["fans"] == 1000
    assert result["page"] == 1
    bilibili._buvid3_cache = None


@pytest.mark.asyncio
async def test_search_user_api_error():
    bilibili._buvid3_cache = "buvid3-val"
    error_resp = {"code": -400, "message": "请求错误"}

    with patch("bilibili_mcp.bilibili.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(error_resp))
        MockClient.return_value = mock_client

        with pytest.raises(ValueError, match="B站API错误"):
            await bilibili.search_user("xxx")
    bilibili._buvid3_cache = None


@pytest.mark.asyncio
async def test_search_user_empty_result():
    bilibili._buvid3_cache = "buvid3-val"
    empty_resp = {"code": 0, "data": {"numResults": 0, "result": []}}

    with patch("bilibili_mcp.bilibili.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(empty_resp))
        MockClient.return_value = mock_client

        result = await bilibili.search_user("不存在的用户")

    assert result["total"] == 0
    assert result["users"] == []
    bilibili._buvid3_cache = None


# ─── get_live_status ──────────────────────────────────────────────────────────

ROOM_INFO_RESPONSE = {
    "code": 0,
    "data": {
        "uid": 999,
        "room_id": 88888,
        "short_id": 510,
        "live_status": 1,
        "title": "测试直播",
        "live_time": "2026-03-08 12:00:00",
        "online": 10000,
        "description": "描述",
        "area_name": "虚拟Gamer",
        "parent_area_name": "虚拟主播",
    },
}


@pytest.mark.asyncio
async def test_get_live_status_by_room_id():
    with patch("bilibili_mcp.bilibili.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(ROOM_INFO_RESPONSE))
        MockClient.return_value = mock_client

        result = await bilibili.get_live_status(room_id=88888)

    assert result["live_status"] == 1
    assert result["live_status_text"] == "直播中"
    assert result["title"] == "测试直播"
    assert result["online"] == 10000
    assert result["room_id"] == 88888


@pytest.mark.asyncio
async def test_get_live_status_by_uid():
    uid_resp = {"code": 0, "data": {"roomid": 88888}}

    with patch("bilibili_mcp.bilibili.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        # 第一次调用返回 uid→room_id，第二次返回房间详情
        mock_client.get = AsyncMock(
            side_effect=[_mock_response(uid_resp), _mock_response(ROOM_INFO_RESPONSE)]
        )
        MockClient.return_value = mock_client

        result = await bilibili.get_live_status(uid=999)

    assert result["live_status"] == 1
    assert result["room_id"] == 88888


@pytest.mark.asyncio
async def test_get_live_status_no_live_room():
    uid_resp = {"code": 0, "data": {"roomid": 0}}

    with patch("bilibili_mcp.bilibili.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(uid_resp))
        MockClient.return_value = mock_client

        result = await bilibili.get_live_status(uid=999)

    assert result["live_status"] == 0
    assert result["room_id"] == 0
    assert "没有直播间" in result["message"]


@pytest.mark.asyncio
async def test_get_live_status_offline():
    offline_resp = {
        "code": 0,
        "data": {**ROOM_INFO_RESPONSE["data"], "live_status": 0, "live_time": "0000-00-00 00:00:00"},
    }

    with patch("bilibili_mcp.bilibili.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(offline_resp))
        MockClient.return_value = mock_client

        result = await bilibili.get_live_status(room_id=88888)

    assert result["live_status"] == 0
    assert result["live_status_text"] == "未开播"


@pytest.mark.asyncio
async def test_get_live_status_requires_uid_or_room_id():
    with pytest.raises(ValueError, match="至少需要提供一个"):
        await bilibili.get_live_status()


@pytest.mark.asyncio
async def test_get_live_status_api_error():
    error_resp = {"code": -400, "message": "房间不存在"}

    with patch("bilibili_mcp.bilibili.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_response(error_resp))
        MockClient.return_value = mock_client

        with pytest.raises(ValueError, match="获取直播状态失败"):
            await bilibili.get_live_status(room_id=99999)
