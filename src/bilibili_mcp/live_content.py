"""直播内容分析：录制直播片段 → ASR 语音识别 + 视觉分析 → 综合描述。"""

import asyncio
import base64
import os
import subprocess
import tempfile
from pathlib import Path

import httpx
import imageio_ffmpeg

from bilibili_mcp.bilibili import HEADERS, get_live_status

# 硅基流动 API 配置
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"

# 默认模型：VL 用 Qwen3-VL-8B（稳定快速），ASR 用 SenseVoiceSmall（中文效果好）
DEFAULT_VL_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
DEFAULT_ASR_MODEL = "FunAudioLLM/SenseVoiceSmall"

# 从环境变量读取 API Key，MCP client 通过 env 配置注入
_ENV_KEY = "SILICONFLOW_API_KEY"


def _get_api_key() -> str:
    """从环境变量 SILICONFLOW_API_KEY 读取硅基流动 API Key。"""
    key = os.environ.get(_ENV_KEY, "")
    if not key:
        raise ValueError(
            "未配置硅基流动 API Key。\n"
            "本地部署：在 MCP 客户端配置的 env 中添加 SILICONFLOW_API_KEY=sk-xxx\n"
            "云端部署：在 ModelScope Studio 的「环境变量/Secret」中添加 SILICONFLOW_API_KEY"
        )
    return key


async def _get_stream_url(room_id: int) -> tuple[str, str]:
    """获取直播间的流地址，返回 (stream_url, buvid3)。优先返回 m3u8（HLS），更稳定。"""
    url = "https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo"
    params = {
        "room_id": room_id,
        "protocol": "0,1",   # 0=http_stream(flv), 1=http_hls(m3u8)
        "format": "0,1,2",   # 0=flv, 1=ts, 2=fmp4
        "codec": "0",        # 0=avc，兼容性最好
        "qn": 80,            # 流畅画质
        "platform": "web",
        "ptype": 8,
    }
    async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
        # 先获取 buvid3，让 B 站识别为正常浏览器请求，返回可访问的 CDN 节点
        buvid3 = ""
        try:
            r0 = await client.get("https://www.bilibili.com/", follow_redirects=True)
            buvid3 = r0.cookies.get("buvid3", "")
        except Exception:
            pass
        cookies = {"buvid3": buvid3} if buvid3 else {}
        resp = await client.get(url, params=params, cookies=cookies)
        resp.raise_for_status()
        data = resp.json()

    if data.get("code") != 0:
        raise ValueError(f"获取直播流失败: {data.get('message', '未知错误')}")

    try:
        streams = data["data"]["playurl_info"]["playurl"]["stream"]
        # 优先选 http_hls + ts 格式（m3u8），对短暂延迟更宽容
        for protocol_name in ("http_hls", "http_stream"):
            for stream in streams:
                if stream.get("protocol_name") != protocol_name:
                    continue
                for fmt in stream.get("format", []):
                    fmt_name = fmt.get("format_name", "")
                    if protocol_name == "http_hls" and fmt_name not in ("ts", "fmp4"):
                        continue
                    for codec in fmt.get("codec", []):
                        url_infos = codec.get("url_info", [])
                        base_url = codec.get("base_url", "")
                        if url_infos and base_url:
                            host = url_infos[0]["host"]
                            extra = url_infos[0].get("extra", "")
                            return f"{host}{base_url}{extra}", buvid3
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"解析直播流地址失败: {e}") from e

    raise ValueError("未找到可用的直播流地址")


_FFMPEG_HEADERS = (
    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36\r\n"
    "Referer: https://live.bilibili.com/\r\n"
    "Origin: https://live.bilibili.com\r\n"
    "Accept: */*\r\n"
    "Accept-Language: zh-CN,zh;q=0.9\r\n"
    # 每行必须以 \r\n 结尾，ffmpeg 要求
)


def _record_video(stream_url: str, duration: int, output_path: str, buvid3: str = "") -> None:
    """录制视频片段（含音视频）。"""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    headers = _FFMPEG_HEADERS
    if buvid3:
        headers += f"Cookie: buvid3={buvid3}\r\n"
    cmd = [
        ffmpeg_exe, "-y",
        "-headers", headers,
        "-rw_timeout", "10000000",   # 读写超时 10s（微秒），适用于 HLS/HTTP
        "-i", stream_url,
        "-t", str(duration),
        "-c:v", "libx264", "-c:a", "aac",
        "-preset", "ultrafast", "-crf", "35",
        "-vf", "scale=640:360",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 50)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 录制失败:\n{result.stderr[-2000:]}")


def _extract_audio(stream_url: str, duration: int, output_path: str) -> None:
    """只提取音频，输出 16kHz 单声道 WAV（ASR 标准格式）。"""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, "-y",
        "-headers", _FFMPEG_HEADERS,
        "-rw_timeout", "8000000",  # 读写超时 8s（微秒），适用于 HLS/HTTP
        "-i", stream_url,
        "-t", str(duration),
        "-vn",                    # 不要视频
        "-ar", "16000",           # 16kHz 采样率
        "-ac", "1",               # 单声道
        "-c:a", "pcm_s16le",      # 16bit PCM
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 40)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 音频提取失败:\n{result.stderr[-2000:]}")


async def _asr_transcribe(audio_path: str, api_key: str, model: str) -> str:
    """调用硅基流动 ASR 接口转录音频。"""
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{SILICONFLOW_BASE_URL}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("audio.wav", audio_bytes, "audio/wav")},
            data={"model": model},
        )
        if resp.status_code != 200:
            raise ValueError(f"ASR 错误 {resp.status_code}: {resp.text[:300]}")
        return resp.json().get("text", "")


async def _vl_analyze(video_path: str, api_key: str, model: str, prompt: str) -> str:
    """调用硅基流动视觉语言模型分析视频画面。"""
    with open(video_path, "rb") as f:
        video_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video_b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        "max_tokens": 1024,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{SILICONFLOW_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        if resp.status_code != 200:
            raise ValueError(f"视觉分析错误 {resp.status_code}: {resp.text[:500]}")
        return resp.json()["choices"][0]["message"]["content"]


async def get_live_content(
    room_id: int,
    duration: int = 15,
    vl_model: str = DEFAULT_VL_MODEL,
    asr_model: str = DEFAULT_ASR_MODEL,
) -> dict:
    """录制直播片段，同时进行 ASR 语音识别和视觉画面分析，综合描述直播内容。

    Args:
        room_id: 直播间 ID
        duration: 录制时长（秒），默认 15 秒，建议 10-30
        vl_model: 视觉语言模型，默认 Qwen3-VL-8B-Instruct
        asr_model: 语音识别模型，默认 FunAudioLLM/SenseVoiceSmall

    Returns:
        包含直播内容描述的字典，含 transcript（语音转录）和 visual（画面描述）

    硅基流动 API Key 从环境变量 SILICONFLOW_API_KEY 读取。
    本地部署在 MCP 配置的 env 中设置；云端部署在平台的 Secret/环境变量中设置。
    """
    key = _get_api_key()

    # 先检查是否在播
    live_info = await get_live_status(room_id=room_id)
    if live_info.get("live_status") != 1:
        return {
            "room_id": room_id,
            "live_status": live_info.get("live_status"),
            "live_status_text": live_info.get("live_status_text", "未开播"),
            "transcript": None,
            "visual": None,
            "message": f"直播间当前状态：{live_info.get('live_status_text', '未开播')}，无法分析内容",
        }

    stream_url, buvid3 = await _get_stream_url(room_id)
    loop = asyncio.get_event_loop()

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "segment.mp4")
        audio_path = os.path.join(tmpdir, "audio.wav")

        # 先录视频（含音频），再从视频中提取音频，避免两次请求流地址
        await loop.run_in_executor(None, _record_video, stream_url, duration, video_path, buvid3)

        # 从已录制的视频中提取音频（不再请求网络）
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        extract_cmd = [
            ffmpeg_exe, "-y", "-i", video_path,
            "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            audio_path,
        ]
        await loop.run_in_executor(
            None,
            lambda: subprocess.run(extract_cmd, capture_output=True, timeout=30),
        )

        video_size_mb = Path(video_path).stat().st_size / 1024 / 1024
        audio_size_kb = Path(audio_path).stat().st_size / 1024

        # 并行执行 ASR 和视觉分析
        vl_prompt = (
            "请描述这段直播画面：主播的虚拟形象是什么样的？"
            "画面中有什么内容（游戏/歌曲/聊天/其他）？"
            "弹幕里观众在说什么？请用中文简洁描述，不超过200字。"
        )
        transcript_task = asyncio.create_task(
            _asr_transcribe(audio_path, key, asr_model)
        )
        visual_task = asyncio.create_task(
            _vl_analyze(video_path, key, vl_model, vl_prompt)
        )
        transcript, visual = await asyncio.gather(transcript_task, visual_task)

    return {
        "room_id": room_id,
        "live_status": 1,
        "live_status_text": "直播中",
        "title": live_info.get("title", ""),
        "area": f"{live_info.get('parent_area_name', '')} / {live_info.get('area_name', '')}",
        "recorded_duration_sec": duration,
        "video_size_mb": round(video_size_mb, 2),
        "audio_size_kb": round(audio_size_kb, 0),
        "transcript": transcript,   # ASR 语音转录原文
        "visual": visual,           # 视觉画面描述
    }
