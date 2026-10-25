"""
language/turn_engine.py
单轮对话统一处理：

    用户文本 → LLM(translation+reply) → 语音路由(自然/古音) → 音频字节

不直接碰麦克风与扬声器，只负责"文本进、音频出"。
"""
from dataclasses import dataclass
from typing import Optional

from services import llm_client, tts_client
from language.ancient_tts import synthesize_ancient, db_coverage


MODE_NATURAL = "natural"    # 自然语音（Edge TTS 普通话）
MODE_ANCIENT = "ancient"    # 东汉古音（音韵库 + 合成器）


@dataclass
class Turn:
    user_text: str
    translation: str
    reply: str
    source: str          # cloud | local
    mode: str            # natural | ancient
    audio: bytes         # mp3 或 wav
    audio_kind: str      # "mp3" | "wav"
    coverage_pct: float = 100.0   # 古音模式覆盖率；自然模式恒 100
    approx_chars: int = 0
    error: Optional[str] = None


def make_turn(user_text: str, mode: str = MODE_NATURAL,
              history=None, pitch: int = 130) -> Turn:
    turn = Turn(user_text=user_text, translation="", reply="",
                source="", mode=mode, audio=b"", audio_kind="",
                error=None)
    if not user_text or not user_text.strip():
        turn.error = "empty_input"
        return turn

    # 1) 文言文翻译 + 回答
    try:
        gen = llm_client.generate_turn(user_text, history)
        turn.translation = gen.get("translation", "")
        turn.reply = gen.get("reply", "")
        turn.source = gen.get("source", "local")
    except Exception as e:
        turn.error = f"llm_error: {e}"
        return turn

    if not turn.reply.strip():
        turn.reply = "善。"
        turn.source = "fallback"

    # 2) 语音路由
    if mode == MODE_ANCIENT:
        wav, result = synthesize_ancient(turn.reply, pitch=pitch)
        if wav:
            turn.audio, turn.audio_kind = wav, "wav"
            turn.coverage_pct = result.coverage_pct
            turn.approx_chars = result.approx
        else:
            # 古音合成失败 → 回退自然语音
            mp3 = tts_client.speak_natural(turn.reply)
            if mp3:
                turn.audio, turn.audio_kind = mp3, "mp3"
                turn.coverage_pct = 0.0
            else:
                turn.error = "ancient_synth_failed"
    else:
        mp3 = tts_client.speak_natural(turn.reply)
        if mp3:
            turn.audio, turn.audio_kind = mp3, "mp3"
        else:
            # Edge TTS 不可用（断网）→ 回退本地古音合成
            wav, result = synthesize_ancient(turn.reply, pitch=pitch)
            if wav:
                turn.audio, turn.audio_kind = wav, "wav"
                turn.coverage_pct = result.coverage_pct
                turn.approx_chars = result.approx
                turn.source = f"{turn.source}+ancient_fallback"
            else:
                turn.error = "tts_failed"
    return turn
