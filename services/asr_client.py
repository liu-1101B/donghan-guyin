"""
services/asr_client.py
语音识别客户端（默认本地 Vosk，可插拔云端）

输入：16-bit mono WAV（任意采样率，内部重采样到 16kHz）。
输出：现代汉语文本。
"""
import json
import os
import wave
import numpy as np
import scipy.signal as _sig

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
DEFAULT_MODEL = os.path.join(MODEL_DIR, "vosk-small-cn")
TARGET_RATE = 16000


class ASRClient:
    def __init__(self, model_path=DEFAULT_MODEL, backend="local"):
        self.model_path = model_path
        self.backend = backend
        self._rec = None

    def initialize(self):
        if self.backend != "local" or self._rec is not None:
            return
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        self._model = Model(self.model_path)
        self._rec = KaldiRecognizer(self._model, TARGET_RATE)

    @staticmethod
    def _read_wav(path):
        with wave.open(path, "rb") as wf:
            sr = wf.getframerate()
            n = wf.getnframes()
            ch = wf.getnchannels()
            raw = wf.readframes(n)
            data = np.frombuffer(raw, dtype=np.int16)
        if ch > 1:  # 多声道 → 取平均降为单声道
            data = data.reshape(-1, ch).mean(axis=1).astype(np.int16)
        return data, sr

    def _resample(self, data: np.ndarray, sr: int) -> np.ndarray:
        """重采样到 TARGET_RATE，保持 int16（输入输出均为 int16 PCM）"""
        if sr == TARGET_RATE:
            return data
        g = int(np.gcd(sr, TARGET_RATE))
        f = data.astype(np.float32) / 32768.0  # 归一化到 [-1,1]
        f = _sig.resample_poly(f, TARGET_RATE // g, sr // g)
        return (np.clip(f, -1.0, 1.0) * 32767).astype(np.int16)

    def transcribe_wav(self, wav_path):
        """识别 WAV 文件，返回现代汉语文本（失败返回空串）"""
        if self.backend != "local":
            return self._transcribe_cloud(wav_path)
        if self._rec is None:
            self.initialize()
        if self._rec is None:
            return ""
        try:
            data, sr = self._read_wav(wav_path)
            data = self._resample(data, sr)
            pcm = data.tobytes()
            # 分块送入
            chunk = 8000
            self._rec.Reset()
            for i in range(0, len(pcm), chunk):
                self._rec.AcceptWaveform(pcm[i:i + chunk])
            final = self._rec.FinalResult()
            return json.loads(final).get("text", "").strip()
        except Exception as e:
            print(f"[asr] 识别失败: {e}")
            return ""

    def _transcribe_cloud(self, wav_path):
        # 预留云端接口：配置 ASR_API_KEY 后启用。未配置则返回空。
        key = os.environ.get("ASR_API_KEY", "")
        if not key:
            return ""
        # TODO: 接入 Deepgram / 其他 ASR 服务
        return ""


_client = None


def get_client(backend="local"):
    global _client
    if _client is None:
        _client = ASRClient(backend=backend)
        _client.initialize()
    return _client


def transcribe_audio(wav_path):
    """模块级便捷接口"""
    return get_client().transcribe_wav(wav_path)
