#!/usr/bin/env python3
"""音频链路诊断：确认哪个后端真的把数据送进了 USB 硬件"""
import os, time, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TONE = os.path.join(ROOT, "audio_out", "tone440.wav")
print("tone 文件:", TONE, "存在:", os.path.exists(TONE))


def usb_state():
    p = "/proc/asound/card2/pcm0p/sub0/hw_params"
    try:
        t = open(p).read().strip()
        if not t or t.split()[0] == "closed":
            return "closed"
        bs = [l.strip() for l in t.splitlines() if l.startswith("bytes_sent")]
        return bs[0] if bs else t.split()[0]
    except Exception as e:
        return f"err:{e}"


def probe(label, stream):
    print(f"\n### {label} ###")
    stream.start()
    for i in range(1, 5):
        time.sleep(0.8)
        print(f"  @{i*0.8:4.1f}s  USB hw: {usb_state()}")
    stream.stop()


try:
    import miniaudio
    print("miniaudio:", miniaudio.get_backend_info() if hasattr(miniaudio, 'get_backend_info') else 'ok')
    try:
        dev = miniaudio.get_default_playback_device()
        print("默认播放设备:", dev.name, "| id", dev.id)
        all_dev = miniaudio.get_playback_devices()
        print(f"全部播放设备 {len(all_dev)} 个:")
        for d in all_dev:
            mark = " <== default" if d.id == dev.id else ""
            print("   ", d.id, d.name, mark)
    except Exception as e:
        print("设备查询失败:", e)
    s = miniaudio.stream_file(TONE)
    probe("miniaudio 默认后端(应走 PipeWire/Pulse)", s)
except Exception as e:
    print("miniaudio 失败:", e)
