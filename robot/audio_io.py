"""
robot/audio_io.py
本地采音与播放（Jetson AGX Orin 实测可用）

- 录制：arecord（16kHz mono WAV）。
- 播放：统一走 aplay。MP3/其它格式先用 miniaudio 解码为 WAV。
  这样 stop() 可以统一打断播放（杀掉 aplay 进程）。
设备编号从 config/settings.yaml 读取，默认按本机实测：
  麦克风+扬声器 = USB 音频一体机 (plughw:2,0)
"""
import io
import os
import subprocess
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
    def play_wav(self, wav_bytes: bytes) -> bool:
        """播放 WAV 字节串（阻塞直到播完；可被 stop() 打断）"""
        self.stop()
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
            print(f"[audio] WAV 播放失败: {e}")
            return False

    def _to_wav_bytes(self, data: bytes) -> bytes:
        """任意音频（mp3/wav/ogg）→ WAV 字节串"""
        if MINIAUDIO_AVAILABLE:
            try:
                d = miniaudio.decode(data)
                return _pcm_to_wav(bytes(d.samples), d.sample_rate, d.nchannels)
            except Exception as e:
                print(f"[audio] miniaudio 解码失败: {e}")
        # 已是 WAV 则原样返回
        return data

    def play_mp3(self, mp3_bytes: bytes) -> bool:
        """播放 MP3 字节串（先解码为 WAV 再走 aplay）"""
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
