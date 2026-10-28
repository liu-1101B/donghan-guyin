"""
robot/main.py
机器人主循环（按键说话版，第一版）

用法：
    python -m robot.main            # 交互模式：按 Enter 开始录音，再按 Enter 结束
    python -m robot.main --selftest # 自检：录 2 秒并回放
    python -m robot.main --text "今天天气如何"   # 免麦克风测试：直接给文本
    python -m robot.main --mode ancient  # 默认东汉古韵模式

按键约定：
    Enter  录音 5 秒（说完再按 Enter 也可提前按，录满 5 秒为止）
    m      切换 自然语音/东汉古韵 模式
    r      重播上一条回答
    c      清空对话历史
    q      退出
    直接输入文字  免麦克风测试
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import yaml
import miniaudio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "audio_out")
os.makedirs(OUT_DIR, exist_ok=True)

from robot.audio_io import AudioIO
from robot.session import Session
from robot.voice_router import VoiceRouter
from services.asr_client import ASRClient


def load_config():
    path = os.path.join(ROOT, "config", "settings.yaml")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_components(cfg):
    audio_cfg = cfg.get("audio", {})
    ai = AudioIO(
        capture_device=audio_cfg.get("capture_device", "plughw:2,0"),
        playback_device=audio_cfg.get("playback_device", "plughw:0,3"),
        sample_rate=audio_cfg.get("sample_rate", 16000),
    )
    session = Session(max_turns=cfg.get("session", {}).get("max_turns", 8))
    router = VoiceRouter(
        default_mode=cfg.get("voice", {}).get("default_mode", "natural"),
        pitch=cfg.get("voice", {}).get("pitch", 130),
    )
    asr = ASRClient(backend=cfg.get("asr", {}).get("backend", "local"))
    asr.initialize()
    return ai, session, router, asr


def play_turn_audio(ai, turn):
    if not turn.audio:
        return False
    if turn.audio_kind == "wav":
        return ai.play_wav(turn.audio)
    if turn.audio_kind == "mp3":
        return ai.play_mp3(turn.audio)
    return False


def handle_user_text(ai, asr, router, session, text, save=True):
    """处理一条用户文本：翻译 → 回答 → 合成 → 播放"""
    t0 = time.time()
    print(f"\n[你] {text}")
    turn = router.route(text, history=session.history())
    session.add(text, turn.reply)
    if turn.error:
        print(f"[机器人] 出错: {turn.error}")
        return turn
    print(f"[译文] {turn.translation}")
    print(f"[答] {turn.reply}  (来源: {turn.source}, 模式: {router.label()})")
    if turn.mode == "ancient" and not turn.audio_kind == "mp3":
        print(f"[古韵覆盖] {turn.coverage_pct}% 已收录，"
              f"{turn.approx_chars} 字为拼音近似")
    if save:
        safe = "".join(c for c in text if c.isalnum())[:8] or "turn"
        p = os.path.join(OUT_DIR, f"{int(time.time())}_{turn.audio_kind}_{safe}.{turn.audio_kind}")
        with open(p, "wb") as f:
            f.write(turn.audio)
        print(f"[音频] {p}")
    play_turn_audio(ai, turn)
    print(f"[耗时] {time.time() - t0:.1f}s")
    return turn


def _mp3_to_16k_wav(mp3_bytes, out_path):
    """MP3 → 16kHz mono WAV（供 Vosk 识别用）"""
    from robot.audio_io import _pcm_to_wav, MINIAUDIO_AVAILABLE
    if not MINIAUDIO_AVAILABLE:
        return None
    d = miniaudio.decode(mp3_bytes, nchannels=1, sample_rate=16000)
    with open(out_path, "wb") as f:
        f.write(_pcm_to_wav(bytes(d.samples), 16000, 1))
    return out_path


def run_selftest(ai, asr, router):
    """自检：音频链路 + 本地识别(用合成参考句做基准) + 文言双模式合成"""
    print("=== 自检 1/3：麦克风 + 扬声器 ===")
    if not ai.selftest(os.path.join(OUT_DIR, "selftest.wav")):
        print("!! 音频链路自检失败，请检查麦克风/扬声器")

    print("=== 自检 2/3：本地语音识别（Vosk）===")
    # 用一句 Edge TTS 合成的话做参考基准，验证"音频→文本"链路
    ref = "你好，今天天气真好，我们一起去散步吧。"
    probe_wav = None
    mp3 = __import__("services.tts_client", fromlist=["speak_natural"]).speak_natural(ref)
    if mp3:
        probe_wav = _mp3_to_16k_wav(mp3, os.path.join(OUT_DIR, "selftest_asr_probe.wav"))
        print(f"参考句: {ref}")
    else:
        print("!! Edge TTS 不可用（断网？），改用麦克风录音做识别样本")
    # 识别对象：优先合成参考，否则麦克风录音
    target = probe_wav or os.path.join(OUT_DIR, "selftest.wav")
    if os.path.exists(target):
        text = asr.transcribe_wav(target)
        print(f"识别结果: {text or '(空)'}")
    else:
        print("!! 无可用识别样本")

    print("=== 自检 3/3：文言生成 + 双模式合成 ===")
    from language.ancient_tts import synthesize_ancient
    sentence = "善哉。洛阳近日天朗气清，惠风和畅。"
    wav, res = synthesize_ancient(sentence)
    p = os.path.join(OUT_DIR, "selftest_ancient.wav")
    with open(p, "wb") as f:
        f.write(wav)
    print(f"古韵合成: {len(wav)} 字节, 覆盖 {res.coverage_pct}% -> {p}")
    if ai.play_file(p):
        print("古韵播放 OK")
    mp3 = __import__("services.tts_client", fromlist=["speak_natural"]).speak_natural(sentence)
    if mp3:
        p2 = os.path.join(OUT_DIR, "selftest_natural.mp3")
        with open(p2, "wb") as f:
            f.write(mp3)
        print(f"自然语音合成 OK -> {p2}")
        ai.play_file(p2)
    else:
        print("!! Edge TTS 不可用（断网？）")
    print("=== 自检完成 ===")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="链路自检")
    ap.add_argument("--text", help="免麦克风：直接处理一条文本")
    ap.add_argument("--mode", choices=["natural", "ancient"])
    ap.add_argument("--pitch", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config()
    ai, session, router, asr = build_components(cfg)
    if args.mode:
        router.set_mode(args.mode)
    if args.pitch:
        router.pitch = args.pitch

    if args.selftest:
        run_selftest(ai, asr, router)
        return

    if args.text:
        # 一次性免交互测试：处理一条文本后退出
        handle_user_text(ai, asr, router, session, args.text)
        ai.stop()
        return

    print("=" * 46)
    print(" 东汉古韵机器人  (按键说话版)")
    print(f" 当前模式: {router.label()}   对话容量: {session.max_turns} 轮")
    print(" Enter=录音  m=切换模式  r=重播  c=清空历史  q=退出")
    print("=" * 46)

    last_turn = None
    rec_path = os.path.join(OUT_DIR, "rec.wav")

    while True:
        try:
            cmd = input(f"[{router.label()}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        low = cmd.lower()
        if low == "q":
            break
        if low == "m":
            router.toggle()
            print(f"模式已切换: {router.label()}")
            continue
        if low == "c":
            session.reset()
            print("对话历史已清空")
            continue
        if low == "r" and last_turn:
            print(">> 重播上一条回答...")
            play_turn_audio(ai, last_turn)
            continue
        if not cmd:
            # 空行 = 录音 5 秒
            print(">> 录音中（5 秒），请说话...")
            ai.stop()
            if ai.record(5.0, rec_path):
                text = asr.transcribe_wav(rec_path)
                if text:
                    last_turn = handle_user_text(ai, asr, router, session, text)
                else:
                    print("[识别] 未听清，请再说一次")
            else:
                print("[录音] 失败：请检查麦克风是否连接")
            continue
        # 直接输入文字
        last_turn = handle_user_text(ai, asr, router, session, cmd)

    print("再见。")
    ai.stop()


if __name__ == "__main__":
    main()
