"""
language/era_audio.py
同一句话的三时期音频对照（东汉 / 中古 / 现代）。

- 东汉：旧实验字表（703 字，洛阳官音重建）synthesize_ancient()
- 中古：Sinica 学者体系（默认王力，可切换）synthesize_ancient(system_id=...)
- 现代：只做真 Edge TTS；断网则该段为空并如实说明，绝不共振峰兜底

三个时期各自独立合成，一个失败不影响其他；每个 EraAudio 都带诚实状态
（ok / text_empty / synth_empty / tts_unavailable），绝不伪造音频。
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple

from language.ancient_tts import synthesize_ancient
from services import tts_client

ERA_EASTERN = "eastern_han"
ERA_MIDDLE = "middle_chinese"
ERA_MODERN = "modern"

MIDDLE_SYSTEM_DEFAULT = "wangli_mc"


@dataclass(frozen=True)
class EraAudio:
    """一个时期的合成结果（含诚实状态，缺音频时 data 为空）。"""

    key: str
    label: str
    data: bytes = b""
    kind: str = ""                      # "wav" | "mp3"
    status: str = "text_empty"          # ok | text_empty | synth_empty | tts_unavailable
    note: str = ""
    ipa: str = ""                       # 古韵两期：IPA 文本；现代期为 ""
    coverage_pct: float = 0.0
    approx: int = 0
    unknown: tuple = ()

    @property
    def has_audio(self) -> bool:
        return bool(self.data)


def middle_system_label(system_id: str) -> str:
    """学者体系 id → 中文名（未知 id 原样返回，不猜）。"""
    from language.history import SCHOLAR_SYSTEMS_ALL
    return SCHOLAR_SYSTEMS_ALL.get(system_id, system_id)


def _ancient_era(key: str, label: str, text: str, *,
                 system_id: Optional[str] = None,
                 pitch: int = 130, speed: float = 1.0) -> EraAudio:
    if not (text or "").strip():
        return EraAudio(key=key, label=label, status="text_empty",
                        note="文本为空")
    wav, result = synthesize_ancient(text, pitch=pitch, speed=speed,
                                     system_id=system_id)
    if not wav:
        return EraAudio(key=key, label=label, status="synth_empty",
                        note="合成未产出有效音频（文本无有效汉字？）")
    return EraAudio(
        key=key, label=label, data=wav, kind="wav", status="ok",
        ipa=result.ipa_text, coverage_pct=result.coverage_pct,
        approx=result.approx, unknown=tuple(result.unknown),
    )


def _modern_era(text: str, *, voice: Optional[str] = None,
                rate: Optional[str] = None) -> EraAudio:
    if not (text or "").strip():
        return EraAudio(key=ERA_MODERN, label="现代汉语",
                        status="text_empty", note="文本为空")
    # 未指定的参数不传，走 tts_client 模块默认音色/语速（不传 None）
    kwargs = {}
    if voice:
        kwargs["voice"] = voice
    if rate:
        kwargs["rate"] = rate
    mp3 = tts_client.speak_natural(text, **kwargs)
    if not mp3:
        return EraAudio(key=ERA_MODERN, label="现代汉语",
                        status="tts_unavailable",
                        note="网络不可用，未生成（现代汉语不做本地兜底合成）")
    return EraAudio(key=ERA_MODERN, label="现代汉语",
                    data=mp3, kind="mp3", status="ok")


def make_era_comparison(sentence: str, *,
                        middle_system: str = MIDDLE_SYSTEM_DEFAULT,
                        pitch: int = 130, speed: float = 1.0,
                        voice: Optional[str] = None,
                        rate: Optional[str] = None
                        ) -> Tuple[EraAudio, EraAudio, EraAudio]:
    """同一句话 → (东汉, 中古, 现代) 三段独立音频。

    middle_system: Sinica 学者体系 id（默认 wangli_mc）；
    未知 id 会由 synthesize_ancient 显式抛错，不静默换体系。
    """
    middle = _ancient_era(
        ERA_MIDDLE, f"中古（{middle_system_label(middle_system)}）",
        sentence, system_id=middle_system, pitch=pitch, speed=speed)
    eastern = _ancient_era(ERA_EASTERN, "东汉（洛阳官音拟音）",
                           sentence, pitch=pitch, speed=speed)
    modern = _modern_era(sentence, voice=voice, rate=rate)
    return eastern, middle, modern
