"""
services/tts_client.py
自然语音合成（Edge TTS 优先，云端接口可插拔）

输入：文言文（或任意中文）文本。
输出：MP3 字节串（失败返回 None）。

网络说明：本机外网经代理（HTTPS_PROXY）访问；代理不可用时自动直连。
edge-tts 底层是 aiohttp，不自动读环境变量，需显式传 proxy。
"""
import asyncio
import concurrent.futures
import os
import tempfile
import socket

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

VOICE = os.environ.get("TTS_VOICE", "zh-CN-YunxiNeural")
RATE = os.environ.get("TTS_RATE", "-10%")  # 稍慢一点，古风一点


def _candidate_proxies():
    """按可用性排序的代理候选：可达的代理在前，None(直连)兜底"""
    env_proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or
                 os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"))
    cands = []
    if env_proxy:
        host, port = _parse_proxy(env_proxy)
        if host and _port_open(host, port, timeout=1.0):
            cands.append(env_proxy)
    cands.append(None)  # 直连
    return cands


def _parse_proxy(p):
    try:
        from urllib.parse import urlparse
        u = urlparse(p if "://" in p else "http://" + p)
        return u.hostname, u.port
    except Exception:
        return None, None


def _port_open(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _edge_tts_sync(text: str, voice: str):
    last_err = None
    for proxy in _candidate_proxies():
        try:
            tts = edge_tts.Communicate(text, voice, rate=RATE, proxy=proxy)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            tmp.close()
            try:
                asyncio.run(tts.save(tmp.name))
                with open(tmp.name, "rb") as f:
                    data = f.read()
                if data:
                    return data
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
        except Exception as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("Edge TTS 无可用网络路径")


def speak_natural(text: str, voice: str = VOICE):
    """文言文 → MP3 字节串。Edge TTS 失败返回 None（调用方可回退到古音合成）。"""
    if not EDGE_TTS_AVAILABLE:
        return None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_edge_tts_sync, text, voice).result(timeout=30)
    except Exception as e:
        print(f"[tts] Edge TTS 失败: {e}")
        return None


def is_cloud_configured() -> bool:
    return bool(os.environ.get("TTS_API_KEY", ""))
