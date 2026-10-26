"""
robot/audio_io.py
本地采音与播放（Jetson AGX Orin 实测可用）

- 录制：arecord（16kHz mono WAV）。
- 播放：优先 pw-play（走 PipeWire 默认输出，自动跟随当前选择的设备，
  如蓝牙音箱）；pw-play 不可用时回退 aplay 直连（用 playback_device 指定卡）。
  MP3/其它格式先经 miniaudio 解码为 WAV 再播。
设备编号从 config/settings.yaml 读取（aplay 回退用）。
"""
import io
import os
import subprocess
import tempfile
import threading
import time
import wave

try:
    import miniaudio
    MINIAUDIO_AVAILABLE = True
except ImportError:
    MINIAUDIO_AVAILABLE = False


def _pcm_to_wav(pcm: bytes, sample_rate: int, nchannels: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


class AudioIO:
    def __init__(self, capture_device="plughw:2,0",
                 playback_device="plughw:2,0",
                 sample_rate=16000):
        self.capture_device = capture_device
        self.playback_device = playback_device
        self.sample_rate = sample_rate
        # 播放进程改为**每次播放独立**（存进 _Playback 句柄，不再是
        # 实例共享属性）：旧实现里 play_async 开多个线程共享
        # self._play_proc/self._play_tmp，后一次播放的 stop() 会误杀
        # 前一次的 pw-play、被杀的线程还会落回 aplay 乱播
        # （症状：听完一段就听不了另一段）。
        self._last_playback = None

    # ---------- 录制 ----------
    def record(self, seconds: float, out_path: str) -> bool:
        """录制指定时长的 16kHz mono WAV。成功返回 True。"""
        cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(self.sample_rate),
               "-c", "1", "-d", str(int(seconds)),
               "-D", self.capture_device, out_path]
        try:
            subprocess.run(cmd, timeout=seconds + 15, capture_output=True)
            ok = os.path.exists(out_path) and os.path.getsize(out_path) > 1000
            if ok:
                print(f"[audio] 已录制 {out_path} ({seconds}s)")
            return ok
        except Exception as e:
            print(f"[audio] 录制失败: {e}")
            return False

    # ---------- 播放 ----------
    def _to_wav_bytes(self, data: bytes) -> bytes:
        """任意音频（mp3/wav/ogg）→ WAV 字节串"""
        if data[:4] == b"RIFF":  # 已是 WAV
            return data
        if MINIAUDIO_AVAILABLE:
            try:
                d = miniaudio.decode(data)
                return _pcm_to_wav(bytes(d.samples), d.sample_rate, d.nchannels)
            except Exception as e:
                print(f"[audio] miniaudio 解码失败: {e}")
        return data

    def play_wav(self, wav_bytes: bytes) -> bool:
        """播放 WAV 字节串（**阻塞**直到播完；可被 stop() 打断）

        优先 pw-play（PipeWire 默认输出，跟随当前选择的设备）；
        失败回退 aplay 直连 playback_device。
        界面按钮请用 play_async()，避免 UI 卡到播完。
        """
        self.stop()
        pb = _Playback(wav_bytes, self.playback_device)
        self._last_playback = pb
        return pb.wait()

    def play_async(self, wav_bytes: bytes) -> bool:
        """后台播放（立即返回，音频在后台播完；可被 stop() 打断）。

        任何音频格式（mp3/wav 自动解码）。
        每次播放独立（不干扰彼此）：想同时放两段可以连点，
        想打断当前播放调 stop()。
        """
        pb = _Playback(wav_bytes, self.playback_device)
        self._last_playback = pb
        t = threading.Thread(target=pb.run, daemon=True)
        t.start()
        return True

    def probe(self, timeout: float = 6.0) -> bool:
        """探测播放通道是否活着：生成 0.3s 正弦波试播，限时等待。

        返回 True = 通道正常；False = 疑似 A2DP 假连接（通道挂死）。
        探测音人耳几乎不可闻（300Hz 短音、低音量），仅作自检。
        """
        import math
        sr = 16000
        n = int(sr * 0.3)
        pcm = bytearray()
        for i in range(n):
            v = int(8000 * math.sin(2 * math.pi * 300 * i / sr))
            pcm += v.to_bytes(2, "little", signed=True)
        wav = _pcm_to_wav(bytes(pcm), sr, 1)
        tmp = None
        proc = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(wav)
            tmp.close()
            proc = subprocess.Popen(["pw-play", tmp.name])
            proc.wait(timeout=timeout)
            return proc.returncode == 0
        except subprocess.TimeoutExpired:
            return False
        except Exception:
            return False
        finally:
            if proc and proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    pass
            if tmp and os.path.exists(tmp.name):
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

    def play_mp3(self, mp3_bytes: bytes) -> bool:
        """播放 MP3 字节串（先解码为 WAV 再播）"""
        return self.play_wav(self._to_wav_bytes(mp3_bytes))

    def play_file(self, path: str) -> bool:
        """按扩展名播放本地文件"""
        ext = os.path.splitext(path)[1].lower()
        with open(path, "rb") as f:
            data = f.read()
        if ext in (".mp3", ".m4a", ".ogg", ".flac"):
            return self.play_mp3(data)
        return self.play_wav(data)

    def stop(self):
        """打断最近一次播放"""
        pb = self._last_playback
        if pb:
            pb.cancel()


class _Playback:
    """一次独立播放（线程安全）：pw-play 优先，失败回退 aplay。

    每个实例持有自己的子进程和临时文件，互不干扰；
    cancel() 只影响自己。
    """

    def __init__(self, wav_bytes: bytes, playback_device: str):
        self.wav_bytes = wav_bytes
        self.playback_device = playback_device
        self._proc = None

    def run(self) -> bool:
        """实际播放（阻塞直到播完/被打断）。"""
        wav = self._wav()
        # 1) pw-play（临时文件，本实例独占）
        tmp = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(wav)
            tmp.close()
            self._proc = subprocess.Popen(["pw-play", tmp.name])
            self._proc.wait()
            if self._proc.returncode == 0:
                return True
            print(f"[audio] pw-play 返回 {self._proc.returncode}，尝试 aplay")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[audio] pw-play 失败: {e}")
        finally:
            if tmp and os.path.exists(tmp.name):
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
            self._proc = None
        # 2) aplay 直连回退
        try:
            p = subprocess.Popen(
                ["aplay", "-q", "-D", self.playback_device, "-"],
                stdin=subprocess.PIPE,
            )
            self._proc = p
            p.stdin.write(wav)
            p.stdin.close()
            p.wait()
            return p.returncode == 0
        except Exception as e:
            print(f"[audio] aplay 失败: {e}")
            return False
        finally:
            self._proc = None

    def wait(self) -> bool:
        """阻塞播放（play_wav 用）。"""
        return self.run()

    def cancel(self):
        """打断本次播放（stop() 用）。"""
        p = self._proc
        if p and p.poll() is None:
            p.kill()
            try:
                p.wait(timeout=2)
            except Exception:
                pass

    def _wav(self) -> bytes:
        if self.wav_bytes[:4] == b"RIFF":
            return self.wav_bytes
        if MINIAUDIO_AVAILABLE:
            try:
                d = miniaudio.decode(self.wav_bytes)
                return _pcm_to_wav(bytes(d.samples), d.sample_rate,
                                   d.nchannels)
            except Exception as e:
                print(f"[audio] miniaudio 解码失败: {e}")
        return self.wav_bytes


# ---------- 蓝牙播放通道检查 ----------
# 实测记录（Jetson + Relink 音箱 F8:D3:F0:A9:08:68）：
# 1) A2DP 音频 profile 会偶发断开而 L2CAP 连接仍在（bluez 日志
#    a2dp-sink: connected -> disconnected）→ PipeWire 蓝牙 sink 消失 →
#    默认输出掉回无喇叭的空接口，pw-play 不报错但全程无声。
# 2) A2DP sink 被 WirePlumber 空闲挂起后，重协商可能卡死
#    （"假连接"：pw-play 永久阻塞）。
# 3) 持续静音流"保活"不可行：该音箱约 1.5 分钟后主动断开 A2DP。
# 因此不做常驻保活，改为**按需检查**：sink 存在 + 是默认 + 通道探测
# 三项都过才播；任一失败 → 跑 bt_reset.sh（断开→重连→设默认）→ 复检。

BT_MAC = os.environ.get("BT_DEVICE_MAC", "F8:D3:F0:A9:08:68")
_BT_RESET_SH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "bt_reset.sh")


def bt_status(mac: str = BT_MAC) -> dict:
    """蓝牙播放状态快照。

    返回 {connected, bt_name, sink_id, sink_name, is_default}：
      connected  设备 L2CAP 是否已连接
      sink_id    PipeWire 里该设备 A2DP sink 的 id（不在 = None）
      is_default 该 sink 是否为当前默认输出
    """
    import re
    out = {"connected": False, "bt_name": None, "sink_id": None,
           "sink_name": None, "is_default": False}
    try:
        info = subprocess.run(["bluetoothctl", "--timeout", "5",
                               "info", mac],
                              capture_output=True, text=True,
                              timeout=10).stdout
        out["connected"] = "Connected: yes" in info
        for line in info.splitlines():
            if "Name:" in line:
                out["bt_name"] = line.split(":", 1)[1].strip()
                break
    except Exception:
        return out
    if not out["bt_name"]:
        return out
    try:
        status = subprocess.run(["wpctl", "status"], capture_output=True,
                                text=True, timeout=10).stdout
    except Exception:
        return out
    # 只解析 Sinks: 区块（Sources 区块也有 [vol:，且行首带 │ 边框字符，
    # 用 search 而非 match）
    start = status.find("Sinks:")
    end = status.find("Sink endpoints", start) if start >= 0 else -1
    block = status[start:end] if start >= 0 and end > start else ""
    default_id = None
    for line in block.splitlines():
        m = re.search(r"(\*?)\s*(\d+)\.\s+(.+?)\s+\[vol:", line)
        if not m:
            continue
        is_def, sid, sname = (m.group(1) == "*", int(m.group(2)),
                              m.group(3).strip())
        if is_def:
            default_id = sid
        if out["sink_id"] is None and out["bt_name"] in sname:
            out["sink_id"], out["sink_name"] = sid, sname
    out["is_default"] = (out["sink_id"] is not None
                         and default_id == out["sink_id"])
    return out

    # ---------- 自检 ----------
    def selftest(self, path: str = "audio_out/selftest.wav") -> bool:
        """录制 2 秒并回放，验证麦克风+扬声器链路"""
        print("[audio] 自检：请对麦克风说话（2 秒）...")
        if not self.record(2.0, path):
            print("[audio] 自检失败：无法录制")
            return False
        ok = self.play_file(path)
        print("[audio] 自检回放完成" if ok else "[audio] 自检回放失败")
        return ok
