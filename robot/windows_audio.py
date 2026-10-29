"""
Windows audio backend for the robot UI.

Uses PortAudio via sounddevice instead of Linux-only arecord/pw-play/wpctl.
Linux keeps using robot.audio_io's existing PipeWire/ALSA path.
"""
from __future__ import annotations

import io
import os
import re
import sys
import threading
import wave
from collections import defaultdict
from typing import Any

# PortAudio 在 Windows 上会通过多个 host API 暴露同一个物理端点
# （MME / DirectSound / WASAPI / WDM-KS），于是同一只音箱会出现 3–4 次；
# 音质与可控性以 WASAPI 最好，WDM-KS 覆盖蓝牙等 WASAPI 不列出的端点。
_HOST_API_PREFERENCE = ("wasapi", "wdm-ks", "directsound", "mme")

# 蓝牙免提端点暴露的是驱动字符串：
# '耳机 (@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0\r\n;(Relink脑机接口))'
_BTHFENUM_RE = re.compile(
    r"\(@System32\\+drivers\\+bthhfenum\.sys[^()]*;\s*\(([^()]*)\)\s*\)\s*$",
    re.IGNORECASE,
)
_INDEX_SUFFIX_RE = re.compile(r"\s*·\s*#(\d+)\s*$")

# 别名端点：语义等同于「自动跟随系统默认」，有真实设备时不进下拉框
_ALIAS_LABELS = {
    "Microsoft 声音映射器 - Output",
    "Microsoft Sound Mapper - Output",
    "主声音驱动程序",
    "Primary Sound Driver",
}


def _clean_device_name(name: Any) -> str:
    """把 PortAudio 的原始设备名变成人能选的名字。

    - 折叠 \\r\\n 与多余空白（否则下拉框里会出现换行）
    - 蓝牙免提的驱动串 → '设备名（蓝牙·免提）'
    - '耳机 ()' → '耳机（未命名）'
    """
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    match = _BTHFENUM_RE.search(text)
    if match:
        tail = match.group(1).strip()
        if tail:
            return f"{tail}（蓝牙·免提）"
        kind = "耳机" if text.startswith(("耳机", "Headphones", "Headset")) else "输出"
        return f"{kind}（蓝牙·免提）"
    if text.endswith("()"):
        return f"{text[:-2].strip()}（未命名）"
    return text


def _host_api_ranks(sd) -> dict:
    """hostapi 索引 → 偏好排名（0 最好）。认不出的一律排最后。"""
    try:
        apis = list(sd.query_hostapis())
    except Exception:
        return {}
    ranks = {}
    for index, api in enumerate(apis):
        label = str(api.get("name", "")).lower()
        for rank, key in enumerate(_HOST_API_PREFERENCE):
            if key in label:
                ranks[index] = rank
                break
        else:
            ranks[index] = len(_HOST_API_PREFERENCE)
    return ranks


def _output_rows(sd) -> list:
    """(index, cleaned name, hostapi rank, hostapi index) for every output device."""
    devices = sd.query_devices()
    ranks = _host_api_ranks(sd)
    rows = []
    for index, device in enumerate(devices):
        if int(device.get("max_output_channels", 0) or 0) <= 0:
            continue
        api = int(device.get("hostapi", 0) or 0)
        rows.append(
            (index, _clean_device_name(device.get("name")), ranks.get(api, 99), api)
        )
    return rows


def _unique_output_rows(sd) -> list:
    """同一个物理端点只留一条，保证蓝牙等只在 WDM-KS 出现的端点不丢。

    - 跨 host API 同名 → 只留偏好最高的那条（避免 K02BS 出现 4 次）
    - 同一 host API 内同名 → 全部保留（是不同的端点，靠 #index 区分）
    - MME 把长名字截断到 31 字符，会与完整名并存 → 丢掉被截断的那条
    """
    grouped = defaultdict(list)
    for row in _output_rows(sd):
        grouped[row[1]].append(row)

    picked = []
    for rows in grouped.values():
        if len({row[3] for row in rows}) > 1:
            picked.append(min(rows, key=lambda row: (row[2], row[0])))
        else:
            picked.extend(rows)
    picked.sort(key=lambda row: row[0])

    names = [row[1] for row in picked]
    truncated = set()
    for name in names:
        for other in names:
            if other != name and len(name) >= 12 and other.startswith(name):
                truncated.add(name)
                break
    if truncated:
        picked = [row for row in picked if row[1] not in truncated]

    seen = defaultdict(int)
    for row in picked:
        seen[row[1]] += 1
    unique = []
    for index, name, _rank, _api in picked:
        label = f"{name} · #{index}" if seen[name] > 1 else name
        unique.append((index, label))

    # MME/DirectSound 的「声音映射器 / 主声音驱动程序」只是别名，
    # 语义等同于「自动跟随系统默认」；有真实设备时不必占位。
    if len(unique) > 1:
        unique = [row for row in unique
                  if row[1].strip() not in _ALIAS_LABELS]
    return unique


def _safe_print(message: str) -> None:
    """Avoid letting a non-UTF-8 Windows console turn successful I/O into failure."""
    try:
        print(message)
    except UnicodeEncodeError:
        safe = message.encode("ascii", "backslashreplace").decode("ascii")
        try:
            print(safe)
        except Exception:
            pass


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
        # 界面里的名字可能带 ' · #12' 后缀（同名端点区分用）：能回指就精确回指
        suffix = _INDEX_SUFFIX_RE.search(configured)
        base = _INDEX_SUFFIX_RE.sub("", configured).strip()
        if suffix:
            index = int(suffix.group(1))
            try:
                device = devices[index]
                if (int(device.get(direction_key, 0) or 0) > 0
                        and _clean_device_name(device.get("name")) == base):
                    return index
            except Exception:
                pass

        wanted = base.casefold()
        # 输出设备以「下拉框里显示的那条」为准——否则同名端点会被
        # 按 devices 顺序解析回 MME 的第一条，和界面显示的(比如) WASAPI 不一致。
        if kind == "output":
            rows = _unique_output_rows(sd)
            for index, label in rows:
                if label == configured:
                    return index
            for index, label in rows:
                if wanted in label.casefold():
                    return index

        exact = None
        partial = None
        for index, device in enumerate(devices):
            if int(device.get(direction_key, 0) or 0) <= 0:
                continue
            name = _clean_device_name(device.get("name")).casefold()
            raw = str(device.get("name", "")).casefold()
            if wanted == name:
                exact = index if exact is None else exact
            elif partial is None and (wanted in name or wanted in raw):
                partial = index
        if exact is not None:
            return exact
        if partial is not None:
            return partial

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
        default_name = None
        if default_id is not None:
            try:
                default_name = _clean_device_name(
                    sd.query_devices(default_id).get("name")
                )
            except Exception:
                default_name = None

        rows = _unique_output_rows(sd)
        occurrences = {}
        for _index, label in rows:
            base = _INDEX_SUFFIX_RE.sub("", label)
            occurrences[base] = occurrences.get(base, 0) + 1

        result = []
        for index, label in rows:
            base = _INDEX_SUFFIX_RE.sub("", label)
            is_default = index == default_id or (
                default_name is not None
                and base == default_name
                and occurrences.get(base, 0) == 1
            )
            result.append((index, label, is_default, None))
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
                _safe_print(f"[audio] Recorded {out_path} ({seconds}s, {used_rate} Hz)")
            return ok
        except Exception as exc:
            _safe_print(f"[audio] Windows recording failed: {exc}")
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
        """Open the selected output device without playing an audible test tone."""
        try:
            sd = _get_sounddevice()
            name = self.playback_target or self.playback_device
            device = resolve_device(name, "output", sd)
            info = sd.query_devices(device, "output") if device is not None else {}
            sample_rate = int(float(info.get("default_samplerate", 48000) or 48000))
            with sd.OutputStream(
                samplerate=sample_rate, channels=1, dtype="int16", device=device
            ):
                pass
            return True
        except Exception as exc:
            _safe_print(f"[audio] Windows output probe failed: {exc}")
            return False

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
            _safe_print(f"[audio] Windows playback failed: {exc}")
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
