"""B站官方公开 API 封装：用户搜索、直播开播状态查询。"""

import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}

# 缓存从 B 站主页获取的 buvid3 cookie，避免每次请求都重新获取
_buvid3_cache: str | None = None


async def _get_buvid3(client: httpx.AsyncClient) -> str:
    """从 B 站主页获取 buvid3 cookie（用于绕过搜索接口的 412 限制）。"""
    global _buvid3_cache
    if _buvid3_cache:
        return _buvid3_cache
    resp = await client.get("https://www.bilibili.com/", follow_redirects=True)
    buvid3 = resp.cookies.get("buvid3", "")
    if buvid3:
        _buvid3_cache = buvid3
    return buvid3


async def search_user(keyword: str, page: int = 1) -> dict:
    """按关键词搜索 B 站用户，返回匹配的用户列表。

    Args:
        keyword: 搜索关键词（用户名）
        page: 页码，从 1 开始

    Returns:
        包含用户列表的字典，每个用户含 uid、uname、fans、videos 等字段
    """
    url = "https://api.bilibili.com/x/web-interface/search/type"
    params = {
        "search_type": "bili_user",
        "keyword": keyword,
        "page": page,
    }
    async with httpx.AsyncClient(headers=HEADERS, timeout=10) as client:
        buvid3 = await _get_buvid3(client)
        cookies = {"buvid3": buvid3} if buvid3 else {}
        resp = await client.get(url, params=params, cookies=cookies)
        resp.raise_for_status()
        data = resp.json()

    if data.get("code") != 0:
        raise ValueError(f"B站API错误: {data.get('message', '未知错误')}")

    result = data.get("data", {})
    users = result.get("result", [])
    return {
        "total": result.get("numResults", 0),
        "page": page,
        "users": [
            {
                "uid": u.get("mid"),
                "uname": u.get("uname"),
                "fans": u.get("fans"),
                "videos": u.get("videos"),
                "sign": u.get("usign", ""),
                "level": u.get("level"),
            }
            for u in users
        ],
    }


async def get_live_status(uid: int | None = None, room_id: int | None = None) -> dict:
    """获取 B 站主播的直播间开播状态。

    可传入主播的 UID 或直播间 ID，二选一。

    Args:
        uid: 主播的 B 站用户 UID
        room_id: 直播间 ID（短号或长号均可）

    Returns:
        包含直播状态的字典：
        - live_status: 0=未开播, 1=直播中, 2=轮播中
        - title: 直播间标题
        - live_time: 开播时间（直播中时有值）
        - online: 在线人数
        - room_id: 直播间 ID
        - uid: 主播 UID
        - uname: 主播昵称
    """
    if uid is None and room_id is None:
        raise ValueError("uid 和 room_id 至少需要提供一个")

    async with httpx.AsyncClient(headers=HEADERS, timeout=10) as client:
        # 若只有 uid，先转换为 room_id
        if room_id is None:
            resp = await client.get(
                "https://api.live.bilibili.com/room/v1/Room/getRoomInfoOld",
                params={"mid": uid},
            )
            resp.raise_for_status()
            info = resp.json()
            if info.get("code") != 0:
                raise ValueError(f"获取直播间信息失败: {info.get('message', '该用户可能没有直播间')}")
            room_id = info["data"]["roomid"]
            if room_id == 0:
                return {
                    "uid": uid,
                    "room_id": 0,
                    "live_status": 0,
                    "title": "",
                    "live_time": "",
                    "online": 0,
                    "uname": "",
                    "message": "该用户没有直播间",
                }

        # 查询直播间详情
        resp = await client.get(
            "https://api.live.bilibili.com/room/v1/Room/get_info",
            params={"room_id": room_id},
        )
        resp.raise_for_status()
        data = resp.json()

    if data.get("code") != 0:
        raise ValueError(f"获取直播状态失败: {data.get('message', '未知错误')}")

    d = data["data"]
    status_map = {0: "未开播", 1: "直播中", 2: "轮播中"}
    live_status = d.get("live_status", 0)

    return {
        "uid": d.get("uid"),
        "room_id": d.get("room_id"),
        "short_id": d.get("short_id"),
        "live_status": live_status,
        "live_status_text": status_map.get(live_status, "未知"),
        "title": d.get("title", ""),
        "live_time": d.get("live_time", ""),
        "online": d.get("online", 0),
        "description": d.get("description", ""),
        "area_name": d.get("area_name", ""),
        "parent_area_name": d.get("parent_area_name", ""),
    }
