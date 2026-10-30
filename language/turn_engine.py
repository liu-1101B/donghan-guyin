"""
language/turn_engine.py
单轮对话统一处理：

    用户文本 → LLM(translation+reply) → 语音路由(自然/古韵) → 音频字节

不直接碰麦克风与扬声器，只负责"文本进、音频出"。
"""
from dataclasses import dataclass
from typing import Optional

from services import llm_client, tts_client
from language.ancient_tts import synthesize_ancient, db_coverage


MODE_NATURAL = "natural"    # 自然语音（Edge TTS 普通话）
MODE_ANCIENT = "ancient"    # 东汉古韵（音韵库 + 合成器）


@dataclass
class Turn:
    user_text: str
    translation: str          # 用户原话 → 东汉文言
    reply: str                # 机器人回答（东汉文言）
    reply_modern: str = ""    # 机器人回答的现代白话版
    source: str = ""          # cloud | local
    mode: str = ""            # natural | ancient
    audio: bytes = b""        # mp3 或 wav
    audio_kind: str = ""      # "mp3" | "wav"
    coverage_pct: float = 100.0   # 古韵模式覆盖率；自然模式恒 100
    approx_chars: int = 0
    error: Optional[str] = None


def make_turn(user_text: str, mode: str = MODE_NATURAL,
              history=None, pitch: int = 130,
              voice: str = None, rate: str = None,
              speed: float = None) -> Turn:
    """单轮处理。音色/语速参数：

    voice : 自然语音的 Edge TTS 音色 id（None=用默认）
    rate  : 自然语音语速（如 "-10%"；None=用默认）
    speed : 古韵语速倍率（1.0 正常；None=用默认）
    pitch : 古韵基频 Hz（两种模式下都生效：古韵直接合成，
            自然模式断网回退古韵时同样使用）
    """
    turn = Turn(user_text=user_text, translation="", reply="",
                reply_modern="", source="", mode=mode,
                audio=b"", audio_kind="", error=None)
    if not user_text or not user_text.strip():
        turn.error = "empty_input"
        return turn

    # 1) 文言文翻译 + 回答（含白话版回答）
    try:
        gen = llm_client.generate_turn(user_text, history)
        turn.translation = gen.get("translation", "")
        turn.reply = gen.get("reply", "")
        turn.reply_modern = gen.get("reply_modern", "")
        turn.source = gen.get("source", "local")
    except Exception as e:
        turn.error = f"llm_error: {e}"
        return turn

    # 词典没有匹配回答时不补造"善"等默认话语，只合成用户输入的古汉语翻译。
    if not turn.reply.strip():
        turn.reply = ""
        turn.reply_modern = ""
        if not turn.translation.strip():
            turn.error = "dictionary_miss_no_translation"
            return turn
        wav, result = synthesize_ancient(
            turn.translation, pitch=pitch, speed=speed or 1.0
        )
        if wav:
            turn.audio, turn.audio_kind = wav, "wav"
            turn.coverage_pct = result.coverage_pct
            turn.approx_chars = result.approx
        else:
            turn.error = "translation_synth_failed"
        return turn

    # 白话版回答缺失时，不编造白话内容；有文言回答时自然语音可回退读文言。
    if not turn.reply_modern.strip():
        turn.reply_modern = turn.reply

    # 2) 语音路由
    if mode == MODE_ANCIENT:
        wav, result = synthesize_ancient(turn.reply, pitch=pitch,
                                         speed=speed or 1.0)
        if wav:
            turn.audio, turn.audio_kind = wav, "wav"
            turn.coverage_pct = result.coverage_pct
            turn.approx_chars = result.approx
        else:
            # 古韵合成失败 → 回退自然语音
            mp3 = tts_client.speak_natural(turn.reply, voice=voice, rate=rate)
            if mp3:
                turn.audio, turn.audio_kind = mp3, "mp3"
                turn.coverage_pct = 0.0
            else:
                turn.error = "ancient_synth_failed"
    else:
        mp3 = tts_client.speak_natural(turn.reply, voice=voice, rate=rate)
        if mp3:
            turn.audio, turn.audio_kind = mp3, "mp3"
        else:
            # Edge TTS 不可用（断网）→ 回退本地古韵合成
            wav, result = synthesize_ancient(turn.reply, pitch=pitch,
                                             speed=speed or 1.0)
            if wav:
                turn.audio, turn.audio_kind = wav, "wav"
                turn.coverage_pct = result.coverage_pct
                turn.approx_chars = result.approx
                turn.source = f"{turn.source}+ancient_fallback"
            else:
                turn.error = "tts_failed"
    return turn
