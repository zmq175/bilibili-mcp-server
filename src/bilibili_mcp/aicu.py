"""aicu.cc 接口封装：查询 B 站用户的粉丝牌、历史评论、历史弹幕、直播弹幕。

aicu.cc 是第三方数据平台，数据非实时。
该站使用 Cloudflare Bot 检测，需要 curl_cffi 模拟真实浏览器 TLS 指纹。
"""

from curl_cffi.requests import AsyncSession

BASE_URL = "https://api.aicu.cc/api/v3"

# curl_cffi 通过 impersonate 参数模拟真实浏览器，无需手动设置 headers
_IMPERSONATE = "chrome124"


async def _get(url: str, params: dict) -> dict:
    """用 curl_cffi 发起 GET 请求，绕过 Cloudflare TLS 指纹检测。"""
    async with AsyncSession(impersonate=_IMPERSONATE) as session:
        resp = await session.get(
            url,
            params=params,
            headers={"Referer": "https://www.aicu.cc/"},
            timeout=15,
        )
    if resp.status_code != 200:
        raise ValueError(f"aicu.cc 请求失败: HTTP {resp.status_code}")
    data = resp.json()
    if data.get("code") != 0:
        raise ValueError(f"aicu.cc 错误: {data.get('message', '未知错误')}")
    return data


async def get_user_medals(uid: int) -> dict:
    """获取指定用户持有的粉丝牌列表。

    Args:
        uid: B 站用户 UID

    Returns:
        包含粉丝牌列表的字典，每个粉丝牌含：
        - name: 粉丝牌名称
        - level: 粉丝牌等级
        - ruid: 对应主播的 UID
    """
    data = await _get(f"{BASE_URL}/user/getmedal", {"uid": uid})
    medals = data.get("data", {}).get("list", [])
    return {
        "uid": uid,
        "total": len(medals),
        "medals": [
            {
                "name": m.get("name"),
                "level": m.get("level"),
                "ruid": m.get("ruid"),
            }
            for m in medals
        ],
    }


async def get_user_comments(
    uid: int,
    page: int = 1,
    page_size: int = 20,
    mode: int = 0,
) -> dict:
    """获取指定用户的历史评论记录。

    Args:
        uid: B 站用户 UID
        page: 页码，从 1 开始
        page_size: 每页数量，最大 20
        mode: 评论类型筛选，0=全部, 1=主评论, 2=回复

    Returns:
        包含评论列表的字典，每条评论含：
        - rpid: 评论 ID
        - message: 评论内容
        - time: 发送时间戳（Unix 秒）
        - oid: 所在视频/动态的 ID
        - type: 内容类型（1=视频, 11=动态等）
    """
    data = await _get(f"{BASE_URL}/search/getreply", {"uid": uid, "pn": page, "ps": page_size, "mode": mode})
    cursor = data.get("data", {}).get("cursor", {})
    replies = data.get("data", {}).get("replies", [])
    return {
        "uid": uid,
        "page": page,
        "page_size": page_size,
        "mode": mode,
        "total": cursor.get("all_count", 0),
        "is_end": cursor.get("is_end", True),
        "comments": [
            {
                "rpid": r.get("rpid"),
                "message": r.get("message"),
                "time": r.get("time"),
                "oid": r.get("dyn", {}).get("oid"),
                "type": r.get("dyn", {}).get("type"),
            }
            for r in replies
        ],
    }


async def get_user_danmaku(uid: int, page: int = 1, page_size: int = 20) -> dict:
    """获取指定用户发送过的历史视频弹幕记录。

    Args:
        uid: B 站用户 UID
        page: 页码，从 1 开始
        page_size: 每页数量，最大 20

    Returns:
        包含弹幕列表的字典，每条弹幕含：
        - id: 弹幕 ID
        - content: 弹幕内容
        - ctime: 发送时间戳（Unix 秒）
        - oid: 所在视频的 AV 号
        - progress_ms: 弹幕出现的视频时间轴位置（毫秒）
    """
    data = await _get(f"{BASE_URL}/search/getvideodm", {"uid": uid, "pn": page, "ps": page_size})
    cursor = data.get("data", {}).get("cursor", {})
    dmlist = data.get("data", {}).get("videodmlist", [])
    return {
        "uid": uid,
        "page": page,
        "page_size": page_size,
        "total": cursor.get("all_count", 0),
        "is_end": cursor.get("is_end", True),
        "danmaku": [
            {
                "id": dm.get("id"),
                "content": dm.get("content"),
                "ctime": dm.get("ctime"),
                "oid": dm.get("oid"),
                "progress_ms": dm.get("progress"),
            }
            for dm in dmlist
        ],
    }


async def get_user_live_danmaku(uid: int, page: int = 1, page_size: int = 20) -> dict:
    """获取指定用户在直播间发送过的历史弹幕记录。

    Args:
        uid: B 站用户 UID
        page: 页码，从 1 开始
        page_size: 每页数量，最大 20

    Returns:
        包含直播弹幕列表的字典，按直播间分组，每组含：
        - room_id: 直播间 ID
        - up_name: 主播昵称
        - up_uid: 主播 UID
        - room_name: 直播间标题
        - danmaku: 该直播间的弹幕列表，每条含 text（内容）和 ts（时间戳）
    """
    data = await _get(f"{BASE_URL}/search/getlivedm", {"uid": uid, "pn": page, "ps": page_size})
    cursor = data.get("data", {}).get("cursor", {})
    items = data.get("data", {}).get("list", [])
    return {
        "uid": uid,
        "page": page,
        "page_size": page_size,
        "total": cursor.get("all_count", 0),
        "is_end": cursor.get("is_end", True),
        "live_danmaku": [
            {
                "room_id": item.get("roominfo", {}).get("roomid"),
                "up_name": item.get("roominfo", {}).get("upname"),
                "up_uid": item.get("roominfo", {}).get("upuid"),
                "room_name": item.get("roominfo", {}).get("roomname"),
                "danmaku": [
                    {"text": dm.get("text"), "ts": dm.get("ts")}
                    for dm in item.get("danmu", [])
                ],
            }
            for item in items
        ],
    }
