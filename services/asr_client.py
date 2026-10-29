"""
services/asr_client.py
语音识别：本地离线，三种后端，按「谁可用」自动挑。

优先级（backend="auto"）：
1. sensevoice —— sherpa-onnx + SenseVoice 多语模型（中英日韩粤），
   中文明显强于 Vosk 小模型，还自带标点；CPU 上 5 秒语音约 0.1 秒解完。
   模型约 230MB，放 models/sense-voice/（model.int8.onnx + tokens.txt）。
2. paraformer —— sherpa-onnx + Paraformer 中文模型（备选，同样是 230MB 量级），
   放 models/paraformer/（model.int8.onnx + tokens.txt）。
3. vosk —— 老后端（44MB），精度弱，只作兜底：models/vosk-small-cn/。

为什么换掉 Vosk 小模型：实测同一段「今天天气真好，我们一起去河边散步」，
Vosk 只给出「今天 天气 真好 我们 一起 去 河边 散步」（无标点、断词硬），
真实麦克风录音还会退化成「已经 呀」这种；SenseVoice 直接给出
「今天天气真好，我们一起去河边散步。」

云端接口（ASR_API_KEY）保持原来的预留位置，未实现。
"""
from __future__ import annotations

import json
import math
import os
import wave

import numpy as np
from scipy import signal as _sig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT, "models")
TARGET_RATE = 16000

SENSEVOICE_DIR = os.path.join(MODELS_DIR, "sense-voice")
PARAFORMER_DIR = os.path.join(MODELS_DIR, "paraformer")
VOSK_DIR = os.path.join(MODELS_DIR, "vosk-small-cn")

BACKEND_ORDER = ("sensevoice", "paraformer", "vosk")
BACKEND_LABELS = {
    "sensevoice": "SenseVoice（sherpa-onnx）",
    "paraformer": "Paraformer（sherpa-onnx）",
    "vosk": "Vosk 小模型",
}


def _onnx_dir_ready(path):
    return (os.path.isfile(os.path.join(path, "tokens.txt"))
            and (os.path.isfile(os.path.join(path, "model.int8.onnx"))
                 or os.path.isfile(os.path.join(path, "model.onnx"))))


def available_backends():
    """当前这台机器上真正可用的后端（按优先级）。"""
    found = []
    if _onnx_dir_ready(SENSEVOICE_DIR):
        found.append("sensevoice")
    if _onnx_dir_ready(PARAFORMER_DIR):
        found.append("paraformer")
    if os.path.isfile(os.path.join(VOSK_DIR, "am", "final.mdl")):
        found.append("vosk")
    return found


def pick_backend(requested="auto"):
    found = available_backends()
    requested = (requested or "auto").strip().lower()
    if requested in BACKEND_ORDER:
        return requested if requested in found else None
    return found[0] if found else None


def _read_wav(path):
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        ch = wf.getnchannels()
        raw = wf.readframes(n)
        data = np.frombuffer(raw, dtype=np.int16)
    if ch > 1:  # 多声道 → 平均降为单声道
        data = data.reshape(-1, ch).mean(axis=1).astype(np.int16)
    return data, sr


def _resample(data: np.ndarray, sr: int) -> np.ndarray:
    """重采样到 TARGET_RATE，保持 int16（输入输出均为 int16 PCM）。"""
    if sr == TARGET_RATE:
        return data
    g = int(np.gcd(sr, TARGET_RATE))
    f = data.astype(np.float32) / 32768.0
    f = _sig.resample_poly(f, TARGET_RATE // g, sr // g)
    return (np.clip(f, -1.0, 1.0) * 32767).astype(np.int16)


class ASRClient:
    def __init__(self, model_path=None, backend="auto"):
        self.backend = (backend or "auto").strip().lower()
        self.is_local = self.backend != "cloud"   # 目前只实现了本地识别
        self.model_path = model_path
        self._rec = None               # vosk
        self._recognizer = None        # sherpa-onnx
        self.engine = None             # 实际生效的后端
        self.last_error = ""

    # ---------- 加载 ----------
    def initialize(self):
        if self.engine is not None:
            return
        target = pick_backend(self.backend)
        if target is None:
            self.last_error = ("没有可用的本地语音识别模型：请在 models/ 下放 "
                               "sense-voice/（model.int8.onnx + tokens.txt）"
                               "或 vosk-small-cn/")
            return
        try:
            if target in ("sensevoice", "paraformer"):
                self._load_sherpa(target)
            else:
                self._load_vosk()
            self.engine = target
            print(f"[asr] 使用后端：{BACKEND_LABELS.get(target, target)}", flush=True)
        except Exception as exc:                       # 加载失败就降级
            self.last_error = f"{target} 加载失败：{exc}"
            print(f"[asr] {self.last_error}", flush=True)
            if target == "sensevoice":
                self.backend = "auto"
                self._recognizer = None
                return self.initialize()               # 试下一个后端
            self.engine = None

    def _load_sherpa(self, backend):
        import sherpa_onnx

        folder = SENSEVOICE_DIR if backend == "sensevoice" else PARAFORMER_DIR
        model = os.path.join(folder, "model.int8.onnx")
        if not os.path.isfile(model):
            model = os.path.join(folder, "model.onnx")
        tokens = os.path.join(folder, "tokens.txt")
        threads = max(1, min(4, (os.cpu_count() or 4)))
        if backend == "sensevoice":
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=model, tokens=tokens, num_threads=threads,
                use_itn=True,                     # 数字/标点规范化
            )
        else:
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
                model=model, tokens=tokens, num_threads=threads,
            )

    def _load_vosk(self):
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        self._model = Model(self.model_path or VOSK_DIR)
        self._rec = KaldiRecognizer(self._model, TARGET_RATE)

    # ---------- 识别 ----------
    def transcribe_wav(self, wav_path):
        """识别 WAV 文件，返回文本（失败返回空串）。"""
        if not self.is_local:
            return self._transcribe_cloud(wav_path)
        if self.engine is None:
            self.initialize()
        if self.engine is None:
            return ""
        try:
            data, sr = _read_wav(wav_path)
            data = _resample(data, sr)
            if self.engine in ("sensevoice", "paraformer"):
                return self._sherpa_decode(data)
            return self._vosk_decode(data)
        except Exception as exc:
            self.last_error = f"识别失败：{exc}"
            print(f"[asr] {self.last_error}", flush=True)
            return ""

    def _sherpa_decode(self, data):
        samples = data.astype(np.float32) / 32768.0
        stream = self._recognizer.create_stream()
        stream.accept_waveform(TARGET_RATE, samples)
        self._recognizer.decode_stream(stream)
        return (stream.result.text or "").strip()

    def _vosk_decode(self, data):
        pcm = data.tobytes()
        chunk = 8000
        self._rec.Reset()
        for i in range(0, len(pcm), chunk):
            self._rec.AcceptWaveform(pcm[i:i + chunk])
        return json.loads(self._rec.FinalResult()).get("text", "").strip()

    def _transcribe_cloud(self, wav_path):
        """预留云端接口：配置 ASR_API_KEY 后启用。未配置则返回空。"""
        if not os.environ.get("ASR_API_KEY", ""):
            return ""
        # TODO: 接入云端 ASR（当前未实现，返回空串而不是假装识别成功）
        return ""

    # ---------- 供界面显示 ----------
    def describe(self):
        if self.engine is None:
            self.initialize()
        if self.engine is None:
            return self.last_error or "未加载"
        return BACKEND_LABELS.get(self.engine, self.engine)


def get_client(backend="auto"):
    return ASRClient(backend=backend)


def transcribe_audio(wav_path):
    return get_client().transcribe_wav(wav_path)
