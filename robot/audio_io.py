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
        self._play_proc = None

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
        """播放 WAV 字节串（阻塞直到播完；可被 stop() 打断）

        优先 pw-play（PipeWire 默认输出，跟随当前选择的设备）；
        失败回退 aplay 直连 playback_device。
        """
        wav_bytes = self._to_wav_bytes(wav_bytes)
        self.stop()
        # 1) pw-play（写临时文件）
        tmp = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(wav_bytes)
            tmp.close()
            self._play_proc = subprocess.Popen(["pw-play", tmp.name])
            self._play_proc.wait()
            if self._play_proc.returncode == 0:
                return True
            print(f"[audio] pw-play 返回 {self._play_proc.returncode}，尝试 aplay")
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
        # 2) aplay 直连回退
        try:
            self._play_proc = subprocess.Popen(
                ["aplay", "-q", "-D", self.playback_device, "-"],
                stdin=subprocess.PIPE,
            )
            self._play_proc.stdin.write(wav_bytes)
            self._play_proc.stdin.close()
            self._play_proc.wait()
            return self._play_proc.returncode == 0
        except Exception as e:
            print(f"[audio] aplay 失败: {e}")
            return False

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
        """打断当前播放"""
        if self._play_proc and self._play_proc.poll() is None:
            self._play_proc.kill()
            try:
                self._play_proc.wait(timeout=2)
            except Exception:
                pass

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
