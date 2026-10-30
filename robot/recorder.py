"""按住说话：浏览器侧录音组件。

Streamlit 原生没有「按住说、松开停」的控件（st.button 只在抬起时触发一次，
服务端根本收不到按下事件），而服务端 arecord 又要求固定录制时长。这里用
`declare_component` 挂一个本地静态前端：

- 按下：`getUserMedia` + `AudioContext` + `ScriptProcessor` 直接取 PCM；
- 松开：在浏览器里编码成 16-bit 单声道 WAV，经组件协议把 base64 交回 Python。

不走 MediaRecorder，是因为它输出 webm/opus，本地没有解码器；PCM 直出可以
直接喂给 Vosk（`ASRClient` 自己会重采样到 16 kHz）。
"""
from __future__ import annotations

import base64
import os

import streamlit.components.v1 as components

_HERE = os.path.dirname(os.path.abspath(__file__))
_COMPONENT_PATH = os.path.join(_HERE, os.pardir, "components", "hold_to_record")

_component = components.declare_component(
    "hold_to_record", path=os.path.abspath(_COMPONENT_PATH)
)


def hold_to_record(key: str = "hold_to_record"):
    """渲染按住说话按钮，返回 {wav: base64, sample_rate, duration_ms, nonce} 或 None。"""
    return _component(key=key, default=None, height=64)


def decode_wav(value: dict, out_path: str) -> tuple[str, float]:
    """把组件返回值落盘成 WAV，返回 (路径, 时长秒)。"""
    raw = base64.b64decode(value.get("wav") or "")
    if not raw.startswith(b"RIFF"):
        raise ValueError("录音数据不是 WAV")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as handle:
        handle.write(raw)
    seconds = float(value.get("duration_ms") or 0) / 1000.0
    return out_path, seconds
