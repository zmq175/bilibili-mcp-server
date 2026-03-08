"""live_content.py 单元测试：_get_api_key / _get_stream_url / _record_video / _asr_transcribe / _vl_analyze / get_live_content。"""

import base64
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import httpx
import pytest

from bilibili_mcp import live_content
from bilibili_mcp.live_content import (
    DEFAULT_ASR_MODEL,
    DEFAULT_VL_MODEL,
    _get_api_key,
    _get_stream_url,
    _asr_transcribe,
    _vl_analyze,
    get_live_content,
)


# ─── 辅助工厂 ────────────────────────────────────────────────────────────────

def _mock_http_response(json_data: dict = None, text: str = None, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text or ""
    resp.raise_for_status = MagicMock()
    return resp


LIVE_STATUS_ONLINE = {
    "uid": 7706705, "room_id": 80397, "short_id": 510,
    "live_status": 1, "live_status_text": "直播中",
    "title": "看看lpl", "live_time": "2026-03-08 12:00:00",
    "online": 200000, "description": "", "area_name": "虚拟Gamer",
    "parent_area_name": "虚拟主播",
}

LIVE_STATUS_OFFLINE = {
    **LIVE_STATUS_ONLINE,
    "live_status": 0, "live_status_text": "未开播",
    "live_time": "0000-00-00 00:00:00", "online": 0,
}

PLAY_INFO_RESPONSE = {
    "code": 0,
    "data": {
        "playurl_info": {
            "playurl": {
                "stream": [
                    {
                        "protocol_name": "http_hls",
                        "format": [{
                            "format_name": "ts",
                            "codec": [{
                                "base_url": "/live/test.m3u8",
                                "url_info": [{"host": "https://cdn.example.com", "extra": "?token=abc"}],
                            }]
                        }]
                    }
                ]
            }
        }
    }
}


# ─── _get_api_key ─────────────────────────────────────────────────────────────

def test_get_api_key_from_env(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test-key")
    assert _get_api_key() == "sk-test-key"


def test_get_api_key_missing_raises(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    with pytest.raises(ValueError, match="未配置硅基流动 API Key"):
        _get_api_key()


def test_get_api_key_empty_raises(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "")
    with pytest.raises(ValueError, match="未配置硅基流动 API Key"):
        _get_api_key()


# ─── _get_stream_url ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_stream_url_hls_preferred():
    with patch("bilibili_mcp.live_content.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_http_response(PLAY_INFO_RESPONSE))
        MockClient.return_value = mock_client

        url = await _get_stream_url(80397)

    assert url == "https://cdn.example.com/live/test.m3u8?token=abc"


@pytest.mark.asyncio
async def test_get_stream_url_fallback_to_flv():
    """当没有 hls 流时，回退到 http_stream(flv)。"""
    flv_response = {
        "code": 0,
        "data": {
            "playurl_info": {
                "playurl": {
                    "stream": [
                        {
                            "protocol_name": "http_stream",
                            "format": [{
                                "format_name": "flv",
                                "codec": [{
                                    "base_url": "/live/test.flv",
                                    "url_info": [{"host": "https://cdn.example.com", "extra": ""}],
                                }]
                            }]
                        }
                    ]
                }
            }
        }
    }
    with patch("bilibili_mcp.live_content.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_http_response(flv_response))
        MockClient.return_value = mock_client

        url = await _get_stream_url(80397)

    assert url == "https://cdn.example.com/live/test.flv"


@pytest.mark.asyncio
async def test_get_stream_url_api_error():
    error_resp = {"code": -400, "message": "直播间不存在"}
    with patch("bilibili_mcp.live_content.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_http_response(error_resp))
        MockClient.return_value = mock_client

        with pytest.raises(ValueError, match="获取直播流失败"):
            await _get_stream_url(99999)


@pytest.mark.asyncio
async def test_get_stream_url_no_streams():
    empty_resp = {"code": 0, "data": {"playurl_info": {"playurl": {"stream": []}}}}
    with patch("bilibili_mcp.live_content.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=_mock_http_response(empty_resp))
        MockClient.return_value = mock_client

        with pytest.raises(ValueError, match="未找到可用的直播流地址"):
            await _get_stream_url(80397)


# ─── _record_video ────────────────────────────────────────────────────────────

def test_record_video_success(tmp_path):
    output = str(tmp_path / "out.mp4")
    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("bilibili_mcp.live_content.imageio_ffmpeg.get_ffmpeg_exe", return_value="/fake/ffmpeg"), \
         patch("bilibili_mcp.live_content.subprocess.run", return_value=mock_result) as mock_run:
        live_content._record_video("https://cdn.example.com/live.m3u8", 10, output)

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "/fake/ffmpeg"
    assert "-i" in cmd
    assert "https://cdn.example.com/live.m3u8" in cmd
    assert "-t" in cmd
    assert "10" in cmd
    assert output in cmd


def test_record_video_ffmpeg_failure(tmp_path):
    output = str(tmp_path / "out.mp4")
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "ffmpeg error: connection refused"

    with patch("bilibili_mcp.live_content.imageio_ffmpeg.get_ffmpeg_exe", return_value="/fake/ffmpeg"), \
         patch("bilibili_mcp.live_content.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="ffmpeg 录制失败"):
            live_content._record_video("https://bad.url/live.m3u8", 10, output)


# ─── _asr_transcribe ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_asr_transcribe_success(tmp_path):
    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 40)  # 伪造 WAV 头

    asr_resp = _mock_http_response({"text": "测试语音内容"})

    with patch("bilibili_mcp.live_content.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=asr_resp)
        MockClient.return_value = mock_client

        result = await _asr_transcribe(str(audio_file), "sk-test", DEFAULT_ASR_MODEL)

    assert result == "测试语音内容"
    post_call = mock_client.post.call_args
    assert "audio/transcriptions" in post_call[0][0]
    assert post_call[1]["data"]["model"] == DEFAULT_ASR_MODEL


@pytest.mark.asyncio
async def test_asr_transcribe_api_error(tmp_path):
    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"\x00" * 44)

    error_resp = _mock_http_response(status_code=401, text="Unauthorized")

    with patch("bilibili_mcp.live_content.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=error_resp)
        MockClient.return_value = mock_client

        with pytest.raises(ValueError, match="ASR 错误 401"):
            await _asr_transcribe(str(audio_file), "sk-bad", DEFAULT_ASR_MODEL)


# ─── _vl_analyze ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vl_analyze_success(tmp_path):
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"\x00" * 100)  # 伪造视频文件

    vl_resp = _mock_http_response({
        "choices": [{"message": {"content": "主播正在打游戏"}}]
    })

    with patch("bilibili_mcp.live_content.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=vl_resp)
        MockClient.return_value = mock_client

        result = await _vl_analyze(str(video_file), "sk-test", DEFAULT_VL_MODEL, "描述画面")

    assert result == "主播正在打游戏"
    post_call = mock_client.post.call_args
    payload = post_call[1]["json"]
    assert payload["model"] == DEFAULT_VL_MODEL
    assert payload["messages"][0]["content"][0]["type"] == "video_url"
    # 验证 base64 编码正确
    expected_b64 = base64.b64encode(b"\x00" * 100).decode()
    assert expected_b64 in payload["messages"][0]["content"][0]["video_url"]["url"]


@pytest.mark.asyncio
async def test_vl_analyze_api_error(tmp_path):
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"\x00" * 100)

    error_resp = _mock_http_response(status_code=500, text='{"code":50507,"message":"Unknown error"}')

    with patch("bilibili_mcp.live_content.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=error_resp)
        MockClient.return_value = mock_client

        with pytest.raises(ValueError, match="视觉分析错误 500"):
            await _vl_analyze(str(video_file), "sk-test", DEFAULT_VL_MODEL, "描述")


# ─── get_live_content ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_live_content_offline(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")

    with patch("bilibili_mcp.live_content.get_live_status", return_value=LIVE_STATUS_OFFLINE):
        result = await get_live_content(room_id=21195828)

    assert result["live_status"] == 0
    assert result["transcript"] is None
    assert result["visual"] is None
    assert "未开播" in result["message"]


@pytest.mark.asyncio
async def test_get_live_content_success(monkeypatch, tmp_path):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")

    # 创建假视频和音频文件（tempfile 内部会用到）
    fake_video = b"\x00" * 1024
    fake_audio = b"RIFF" + b"\x00" * 40

    def fake_record_video(stream_url, duration, output_path):
        Path(output_path).write_bytes(fake_video)

    def fake_subprocess_run(cmd, **kwargs):
        # 模拟从视频提取音频
        audio_path = cmd[-1]
        Path(audio_path).write_bytes(fake_audio)
        result = MagicMock()
        result.returncode = 0
        return result

    with patch("bilibili_mcp.live_content.get_live_status", return_value=LIVE_STATUS_ONLINE), \
         patch("bilibili_mcp.live_content._get_stream_url", return_value="https://cdn.example.com/live.m3u8"), \
         patch("bilibili_mcp.live_content._record_video", side_effect=fake_record_video), \
         patch("bilibili_mcp.live_content.subprocess.run", side_effect=fake_subprocess_run), \
         patch("bilibili_mcp.live_content.imageio_ffmpeg.get_ffmpeg_exe", return_value="/fake/ffmpeg"), \
         patch("bilibili_mcp.live_content._asr_transcribe", return_value="解说内容"), \
         patch("bilibili_mcp.live_content._vl_analyze", return_value="画面描述"):

        result = await get_live_content(room_id=80397, duration=10)

    assert result["live_status"] == 1
    assert result["live_status_text"] == "直播中"
    assert result["title"] == "看看lpl"
    assert result["transcript"] == "解说内容"
    assert result["visual"] == "画面描述"
    assert result["recorded_duration_sec"] == 10
    assert result["room_id"] == 80397


@pytest.mark.asyncio
async def test_get_live_content_no_api_key(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)

    with pytest.raises(ValueError, match="未配置硅基流动 API Key"):
        await get_live_content(room_id=80397)


@pytest.mark.asyncio
async def test_get_live_content_custom_models(monkeypatch, tmp_path):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")

    fake_video = b"\x00" * 512
    fake_audio = b"RIFF" + b"\x00" * 40

    def fake_record_video(stream_url, duration, output_path):
        Path(output_path).write_bytes(fake_video)

    def fake_subprocess_run(cmd, **kwargs):
        audio_path = cmd[-1]
        Path(audio_path).write_bytes(fake_audio)
        result = MagicMock()
        result.returncode = 0
        return result

    asr_mock = AsyncMock(return_value="转录结果")
    vl_mock = AsyncMock(return_value="视觉结果")

    with patch("bilibili_mcp.live_content.get_live_status", return_value=LIVE_STATUS_ONLINE), \
         patch("bilibili_mcp.live_content._get_stream_url", return_value="https://cdn.example.com/live.m3u8"), \
         patch("bilibili_mcp.live_content._record_video", side_effect=fake_record_video), \
         patch("bilibili_mcp.live_content.subprocess.run", side_effect=fake_subprocess_run), \
         patch("bilibili_mcp.live_content.imageio_ffmpeg.get_ffmpeg_exe", return_value="/fake/ffmpeg"), \
         patch("bilibili_mcp.live_content._asr_transcribe", asr_mock), \
         patch("bilibili_mcp.live_content._vl_analyze", vl_mock):

        await get_live_content(
            room_id=80397,
            vl_model="Qwen/Qwen3-VL-32B-Instruct",
            asr_model="TeleAI/TeleSpeechASR",
        )

    # 验证自定义模型被正确透传
    asr_call_args = asr_mock.call_args
    assert asr_call_args[0][2] == "TeleAI/TeleSpeechASR"

    vl_call_args = vl_mock.call_args
    assert vl_call_args[0][2] == "Qwen/Qwen3-VL-32B-Instruct"
