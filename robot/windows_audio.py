"""
Windows audio backend for the robot UI.

Uses PortAudio via sounddevice instead of Linux-only arecord/pw-play/wpctl.
Linux keeps using robot.audio_io's existing PipeWire/ALSA path.
"""
from __future__ import annotations

import io
import os
import threading
import wave
from typing import Any


def _get_sounddevice(sd_module=None):
    if sd_module is not None:
        return sd_module
    try:
        import sounddevice as sd
        return sd
    except ImportError as exc:
        raise RuntimeError(
            "Windows 音频依赖未安装。请在仓库目录运行 "
            "start.bat，或执行 .venv\\Scripts\\python -m pip install "
            "-r requirements-robot.txt"
        ) from exc


def _default_device_id(sd, kind: str):
    try:
        default = sd.default.device
        index = 0 if kind == "input" else 1
        device_id = default[index]
        if device_id is not None and int(device_id) >= 0:
            return int(device_id)
    except Exception:
        pass
    return None


def resolve_device(configured: str | None, kind: str, sd_module=None):
    """Resolve an input/output device by name, falling back to Windows default."""
    sd = _get_sounddevice(sd_module)
    direction_key = "max_input_channels" if kind == "input" else "max_output_channels"
    devices = sd.query_devices()

    configured = (configured or "").strip()
    # Linux ALSA names are not meaningful on Windows; use the system default.
    if configured.lower().startswith(("plughw:", "hw:", "plug:")):
        configured = ""

    if configured and configured.lower() not in {"default", "auto", "自动"}:
        wanted = configured.casefold()
        for index, device in enumerate(devices):
            if int(device.get(direction_key, 0) or 0) > 0:
                if wanted in str(device.get("name", "")).casefold():
                    return index

    default_id = _default_device_id(sd, kind)
    if default_id is not None:
        try:
            if int(sd.query_devices(default_id).get(direction_key, 0) or 0) > 0:
                return default_id
        except Exception:
            pass

    # If the OS did not advertise a valid default, take the first suitable device.
    for index, device in enumerate(devices):
        if int(device.get(direction_key, 0) or 0) > 0:
            return index
    return None


def list_output_devices(sd_module=None) -> list[tuple[int, str, bool, None]]:
    """Return (device index, display name, is default, volume=None) for the UI."""
    try:
        sd = _get_sounddevice(sd_module)
        default_id = _default_device_id(sd, "output")
        result = []
        for index, device in enumerate(sd.query_devices()):
            if int(device.get("max_output_channels", 0) or 0) > 0:
                result.append((
                    index,
                    str(device.get("name", f"Output {index}")),
                    index == default_id,
                    None,
                ))
        return result
    except Exception:
        # The UI can still launch without audio drivers; recording/playback will
        # show an actionable error when the user requests audio.
        return []


def _wav_to_int16(data: bytes):
    """Decode WAV/MP3 bytes to (int16 samples, sample_rate, channels)."""
    import numpy as np

    wav_bytes = data
    if not wav_bytes.startswith(b"RIFF"):
        try:
            import miniaudio
            decoded = miniaudio.decode(wav_bytes)
            wav_bytes = _pcm_to_wav(bytes(decoded.samples),
                                    decoded.sample_rate, decoded.nchannels)
        except Exception as exc:
            raise RuntimeError(f"无法解码音频数据：{exc}") from exc

    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            sample_width = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())
    except Exception as exc:
        raise RuntimeError(f"音频不是可读取的 WAV/MP3：{exc}") from exc

    if sample_width != 2:
        try:
            import miniaudio
            decoded = miniaudio.decode(
                wav_bytes, nchannels=channels, sample_rate=sample_rate
            )
            frames = bytes(decoded.samples)
            channels = int(decoded.nchannels)
            sample_rate = int(decoded.sample_rate)
            sample_width = 2
        except Exception as exc:
            raise RuntimeError(
                f"需要 16-bit PCM WAV 或可用的 miniaudio 解码器：{exc}"
            ) from exc

    samples = np.frombuffer(frames, dtype="<i2")
    if channels > 1:
        usable = len(samples) - (len(samples) % channels)
        samples = samples[:usable].reshape((-1, channels))
    else:
        samples = samples.reshape((-1, 1))
    return samples, int(sample_rate), int(channels)


def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(int(channels))
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm)
    return out.getvalue()


class WindowsAudioIO:
    """Drop-in Windows implementation of the AudioIO methods used by the app."""

    def __init__(self, capture_device="default", playback_device="default",
                 sample_rate=16000, playback_target=None):
        self.capture_device = capture_device
        self.playback_device = playback_device
        self.sample_rate = int(sample_rate)
        self.playback_target = playback_target
        self._last_playback = None

    def record(self, seconds: float, out_path: str) -> bool:
        try:
            import numpy as np
            sd = _get_sounddevice()
            device = resolve_device(self.capture_device, "input", sd)
            info = sd.query_devices(device, "input") if device is not None else {}
            default_rate = int(float(info.get("default_samplerate", 48000) or 48000))
            rates = [self.sample_rate]
            if default_rate not in rates:
                rates.append(default_rate)

            last_error = None
            recording = None
            used_rate = self.sample_rate
            for rate in rates:
                try:
                    recording = sd.rec(
                        max(1, int(float(seconds) * rate)),
                        samplerate=rate, channels=1, dtype="int16",
                        device=device, blocking=True,
                    )
                    used_rate = rate
                    break
                except Exception as exc:
                    last_error = exc
            if recording is None:
                raise RuntimeError(
                    f"麦克风打开失败（已尝试 {rates} Hz）：{last_error}"
                )

            parent = os.path.dirname(os.path.abspath(out_path))
            os.makedirs(parent, exist_ok=True)
            with wave.open(out_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(used_rate)
                wf.writeframes(np.asarray(recording, dtype=np.int16).tobytes())

            ok = os.path.exists(out_path) and os.path.getsize(out_path) > 1000
            if ok:
                print(f"[audio] 已录制 {out_path} ({seconds}s, {used_rate} Hz)")
            return ok
        except Exception as exc:
            print(f"[audio] Windows 录音失败：{exc}")
            return False

    def _make_playback(self, data: bytes):
        playback = _WindowsPlayback(
            data,
            self.playback_target or self.playback_device,
        )
        self._last_playback = playback
        return playback

    def play_wav(self, wav_bytes: bytes) -> bool:
        self.stop()
        return self._make_playback(wav_bytes).run()

    def play_async(self, audio_bytes: bytes) -> bool:
        playback = self._make_playback(audio_bytes)
        thread = threading.Thread(target=playback.run, daemon=True)
        thread.start()
        return True

    def probe(self, timeout: float = 6.0) -> bool:
        import math
        sample_rate = 16000
        count = int(sample_rate * 0.3)
        pcm = bytearray()
        for i in range(count):
            value = int(3000 * math.sin(2 * math.pi * 300 * i / sample_rate))
            pcm.extend(value.to_bytes(2, "little", signed=True))
        return self.play_wav(_pcm_to_wav(bytes(pcm), sample_rate, 1))

    def play_mp3(self, mp3_bytes: bytes) -> bool:
        return self.play_wav(mp3_bytes)

    def play_file(self, path: str) -> bool:
        with open(path, "rb") as handle:
            data = handle.read()
        return self.play_wav(data)

    def stop(self):
        if self._last_playback is not None:
            self._last_playback.cancel()

    def selftest(self, path: str = "audio_out/selftest.wav") -> bool:
        print("[audio] 自检：请对麦克风说话（2 秒）...")
        if not self.record(2.0, path):
            print("[audio] 自检失败：无法录制")
            return False
        ok = self.play_file(path)
        print("[audio] 自检回放完成" if ok else "[audio] 自检回放失败")
        return ok


class _WindowsPlayback:
    def __init__(self, audio_bytes: bytes, device_name: str | None):
        self.audio_bytes = audio_bytes
        self.device_name = device_name
        self._cancelled = threading.Event()
        self._stream = None

    def run(self) -> bool:
        try:
            import numpy as np
            sd = _get_sounddevice()
            samples, sample_rate, channels = _wav_to_int16(self.audio_bytes)
            device = resolve_device(self.device_name, "output", sd)

            if device is not None:
                info = sd.query_devices(device, "output")
                max_channels = int(info.get("max_output_channels", channels) or channels)
                if channels > max_channels:
                    # Preserve speech intelligibility on mono-only devices.
                    samples = np.asarray(samples, dtype=np.int32).mean(
                        axis=1, keepdims=True
                    ).astype(np.int16)
                    channels = 1

            with sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype="int16",
                device=device,
            ) as stream:
                self._stream = stream
                for start in range(0, len(samples), 4096):
                    if self._cancelled.is_set():
                        break
                    stream.write(samples[start:start + 4096])
            return not self._cancelled.is_set()
        except Exception as exc:
            print(f"[audio] Windows 播放失败：{exc}")
            return False
        finally:
            self._stream = None

    def cancel(self):
        self._cancelled.set()
        stream = self._stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass
