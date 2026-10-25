"""
robot/app.py
东汉古音机器人 · 使用界面（Streamlit，风格对齐原项目 guyun_app.py）

启动：
    cd donghan-guyin && source .venv/bin/activate
    streamlit run robot/app.py
    # 浏览器打开 http://localhost:8501

功能：
    - 输入白话文/古文（或点按钮录 5 秒麦克风），Qwen 生成文言应答
    - 模式：自然语音（Edge TTS）/ 东汉古音（音韵库合成）
    - 可调：音色（自然模式）、语速（两模式各自）、语调基频（古音模式）
    - 浏览器内播放 + 一键"设备播放"（走 PipeWire 默认输出，如蓝牙音箱）
    - 多轮对话历史（默认 8 轮）
"""
import os
import subprocess
import sys
import time
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

import streamlit as st
import importlib

# 代码热重载：Streamlit 只会重跑 app.py，但其它模块缓存在进程里。
# 这里按依赖顺序检查各核心模块的 mtime，变了就 reload，使改代码后
# 刷新页面即可生效（无需重启服务）。文件有语法错误时跳过该模块并提示。
_RELOAD_ORDER = [
    "phonology_db", "sound_synth", "classical_translator",
    "language.style_prompt", "language.ancient_tts",
    "services.llm_client", "services.tts_client", "services.asr_client",
    "language.turn_engine",
    "robot.session", "robot.voice_router", "robot.audio_io",
]


# 基线存全局文件（跨浏览器会话/跨刷新）：进程首次运行 app.py 时记录的
# 各模块 mtime = 进程当前内存里加载的版本。任何文件比基线新 → 需重载。
_RELOAD_STATE = os.path.join(ROOT, ".reload_state.json")


def _autoreload_changed_modules():
    """核心模块 mtime 晚于基线 → 按依赖顺序整体重载（保证引用链一致）"""
    import json
    try:
        with open(_RELOAD_STATE, encoding="utf-8") as f:
            seen = json.load(f)
    except Exception:
        seen = None
    mtimes, changed = {}, []
    for name in _RELOAD_ORDER:
        try:
            mod = importlib.import_module(name)
            path = getattr(mod, "__file__", None)
            mtimes[name] = os.path.getmtime(path) if path else None
        except Exception:
            continue
    if seen is None:
        # 无基线：无法证明内存版本 == 磁盘版本 → 全量重载（约 2 秒，安全）
        changed = [n for n in mtimes if mtimes[n] is not None]
        seen = {}
    else:
        for name, m in mtimes.items():
            if m is not None and seen.get(name) is not None and m > seen[name]:
                changed.append(name)
    if changed:
        for name in _RELOAD_ORDER:   # 全部按依赖顺序重载
            try:
                importlib.reload(importlib.import_module(name))
            except Exception as e:
                st.session_state._reload_warn = f"重载 {name} 失败：{e}"
        st.session_state._reloaded = ", ".join(changed)
        st.session_state._changed_mods = set(changed)
        seen = dict(mtimes)
    try:
        with open(_RELOAD_STATE, "w", encoding="utf-8") as f:
            json.dump(seen, f)
    except OSError:
        pass
    return changed


_autoreload_changed_modules()

import yaml
from robot.session import Session
from robot.voice_router import VoiceRouter
from robot.audio_io import AudioIO
from services import tts_client
from language.ancient_tts import text_to_ipa, synthesize_ancient
from phonology_db import lookup_char, EASTERN_HAN_DB

OUT_DIR = os.path.join(ROOT, "audio_out")
os.makedirs(OUT_DIR, exist_ok=True)


# ---------- 全局组件（跨 rerun 持久） ----------
@st.cache_resource(show_spinner=False)
def get_session():
    cfg = {}
    p = os.path.join(ROOT, "config", "settings.yaml")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    return Session(max_turns=cfg.get("session", {}).get("max_turns", 8))


@st.cache_resource(show_spinner=False)
def get_router():
    cfg = {}
    p = os.path.join(ROOT, "config", "settings.yaml")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    v = cfg.get("voice", {})
    return VoiceRouter(default_mode=v.get("default_mode", "natural"),
                       pitch=v.get("pitch", 130))


@st.cache_resource(show_spinner=False)
def get_asr():
    from services.asr_client import ASRClient
    asr = ASRClient(backend="local")
    asr.initialize()
    return asr


@st.cache_resource(show_spinner=False)
def get_audio_io():
    cfg = {}
    p = os.path.join(ROOT, "config", "settings.yaml")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    a = cfg.get("audio", {})
    return AudioIO(capture_device=a.get("capture_device", "plughw:2,0"),
                   playback_device=a.get("playback_device", "plughw:2,0"),
                   sample_rate=a.get("sample_rate", 16000))


# 代码重载后必须重建缓存实例：旧实例的方法仍绑定旧类（如旧 Turn 没有
# reply_modern），仅重载模块不够。Session 一并重建（开发期可接受丢上下文）。
if st.session_state.get("_changed_mods"):
    get_router.clear()
    get_audio_io.clear()
    get_session.clear()
    if "services.asr_client" in st.session_state["_changed_mods"]:
        get_asr.clear()
    st.session_state["_changed_mods"] = None


# ---------- 音韵分析（逐字，供表格展示） ----------
def analyze_reply(classical: str):
    rows = []
    for ch in classical:
        if not ch.strip() or ch in '。！？，、；：""''（）…—·':
            continue
        data = lookup_char(ch)
        if data:
            rows.append({"char": ch, "ipa": data["ipa"],
                         "tone": data.get("tone", ""),
                         "src": "收录"})
        else:
            from language.ancient_tts import get_pinyin_fallback, estimate_ipa_from_pinyin
            py = get_pinyin_fallback(ch)
            ipa = estimate_ipa_from_pinyin(py) if py else None
            if ipa:
                rows.append({"char": ch, "ipa": ipa,
                             "tone": "今音", "src": "拼音近似"})
    return rows


# ---------- 扩展朗读合成（白话回答 / 古文翻译） ----------
def synth_extended(kind: str, text: str, router: VoiceRouter):
    """按设置合成一段扩展朗读音频。

    kind = "modern" → 现代汉语读回答（Edge TTS；断网回退古音合成）
    kind = "ancient_trans" → 古汉语朗读翻译（东汉音合成）
    返回 (audio_bytes, kind)；失败返回 (b"", kind)。
    """
    if kind == "modern":
        mp3 = tts_client.speak_natural(text, voice=router.voice,
                                       rate=router.rate)
        if mp3:
            return mp3, "mp3"
        wav, _ = synthesize_ancient(text, pitch=router.pitch,
                                    speed=router.speed)
        return (wav, "wav") if wav else (b"", "wav")
    # kind == "ancient_trans"
    wav, _ = synthesize_ancient(text, pitch=router.pitch,
                                speed=router.speed)
    return (wav, "wav") if wav else (b"", "wav")


def play_to_device(kind: str, text: str, router: VoiceRouter) -> bool:
    """合成扩展朗读并后台发送到设备（不阻塞界面）"""
    audio, fmt = synth_extended(kind, text, router)
    if not audio:
        return False
    get_audio_io().play_async(audio)
    return True


# ---------- 页面 ----------
st.set_page_config(page_title="古音机器人 · 东汉洛阳官音",
                   page_icon=":classical_building:", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700;900&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
    :root { --bg-deep: #1a1410; --bg-card: #2a2018; --bg-elevated: #322818; --gold: #c9a96e; --gold-dim: #8b6914; --text-primary: #e8dcc8; --text-secondary: #d4c4a8; --text-muted: #7a6a5a; --border: #4a3a2a; }
    .stApp { background-color: var(--bg-deep) !important; }
    .stApp * { color: var(--text-primary) !important; }
    .stTextArea textarea { font-family:'Noto Sans SC',sans-serif!important; font-size:1rem!important; background-color:var(--bg-card)!important; color:var(--text-primary)!important; border:1px solid var(--border)!important; border-radius:8px!important; caret-color:var(--gold)!important; }
    .stTextArea textarea:focus { border-color:var(--gold)!important; box-shadow:0 0 0 1px var(--gold)!important; }
    .stTextArea textarea::placeholder { color:var(--text-muted)!important; opacity:1!important; }
    .stButton button { background:linear-gradient(135deg,var(--gold-dim) 0%,var(--gold) 100%)!important; color:#1a1410!important; font-weight:700!important; border:none!important; border-radius:6px!important; padding:0.5rem 1.5rem!important; font-size:1rem!important; letter-spacing:0.05em!important; }
    .stButton button:hover { background:linear-gradient(135deg,#a07a1a 0%,#d4b87e 100%)!important; transform:translateY(-1px); }
    .stButton button:disabled { background:#4a3a2a!important; color:#7a6a5a!important; cursor:not-allowed; }
    .stDownloadButton button { background:transparent!important; border:1px solid var(--gold)!important; color:var(--gold)!important; }
    .stSlider [data-baseweb="slider"] input { background:linear-gradient(90deg,var(--gold-dim),var(--gold))!important; }
    .main-header { font-family:'Noto Serif SC',serif; font-size:2.8rem; font-weight:900; color:var(--gold)!important; text-align:center; padding:2rem 0 0.2rem 0; letter-spacing:0.08em; }
    .main-header::after { content:''; display:block; width:60px; height:2px; background:var(--gold); margin:0.5rem auto 0; opacity:0.5; }
    .sub-header { font-family:'Noto Sans SC',sans-serif; font-size:0.9rem; color:var(--text-muted)!important; text-align:center; margin-bottom:2rem; font-weight:300; letter-spacing:0.2em; }
    .classical-text { font-family:'Noto Serif SC',serif; font-size:1.4rem; line-height:2.2; color:#f0e8d8!important; padding:1.2rem 1.5rem; background:linear-gradient(135deg,var(--bg-card) 0%,var(--bg-elevated) 100%); border-radius:8px; border-left:3px solid var(--gold); margin:0.5rem 0; letter-spacing:0.08em; }
    .modern-text { font-family:'Noto Sans SC',sans-serif; font-size:0.95rem; line-height:1.8; color:var(--text-secondary)!important; padding:0.8rem 1.2rem; background:var(--bg-card); border-radius:8px; border:1px solid var(--border); margin:0.3rem 0; }
    .ipa-display { font-family:'Noto Sans SC',sans-serif; font-size:1.0rem; color:var(--text-secondary)!important; background:var(--bg-card); padding:0.7rem 1rem; border-radius:8px; border:1px solid var(--border); margin:0.3rem 0; word-break:break-all; }
    .tone-tag { display:inline-block; padding:0.08rem 0.5rem; border-radius:3px; font-size:0.65rem; font-weight:500; letter-spacing:0.05em; }
    .tone-平声 { background:rgba(122,154,122,0.2); color:#7a9a7a!important; border:1px solid rgba(122,154,122,0.3); }
    .tone-上声 { background:rgba(100,130,170,0.2); color:#7a9aba!important; border:1px solid rgba(100,130,170,0.3); }
    .tone-去声 { background:rgba(192,57,43,0.15); color:#d85a4a!important; border:1px solid rgba(192,57,43,0.3); }
    .tone-入声 { background:rgba(180,68,42,0.15); color:#d46a4a!important; border:1px solid rgba(180,68,42,0.3); }
    .phonology-table { width:100%; font-size:0.8rem; border-collapse:collapse; background:var(--bg-card); border-radius:8px; overflow:hidden; }
    .phonology-table thead { background:var(--bg-deep); }
    .phonology-table th { padding:0.5rem 0.4rem; text-align:center; color:var(--gold)!important; font-weight:500; font-size:0.75rem; letter-spacing:0.05em; border-bottom:1px solid var(--border); }
    .phonology-table td { padding:0.4rem; text-align:center; color:var(--text-primary)!important; border-bottom:1px solid #3a2a1a; }
    .phonology-table tr:hover td { background:rgba(201,169,110,0.05); }
    .audio-card { background:var(--bg-card); border-radius:8px; padding:0.6rem; border:1px solid var(--border); text-align:center; }
    .audio-card strong { color:var(--gold)!important; font-size:0.85rem; }
    .badge { display:inline-block; padding:0.15rem 0.7rem; border-radius:12px; font-size:0.75rem; background:rgba(201,169,110,0.12); border:1px solid var(--border); color:var(--gold)!important; margin-right:0.4rem; }
    .history-item { background:var(--bg-card); border:1px solid var(--border); border-radius:6px; padding:0.5rem 0.8rem; margin:0.4rem 0; font-size:0.85rem; }
    .history-item .u { color:var(--text-secondary); }
    .history-item .a { color:var(--text-primary); font-family:'Noto Serif SC',serif; }
    h4,h5 { color:var(--gold)!important; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">古 音</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">東漢·洛陽·官音機器人 │ Qwen3 對談 · 雙軌語音</div>', unsafe_allow_html=True)

if st.session_state.get("_reload_warn"):
    st.warning(st.session_state._reload_warn)
    st.session_state._reload_warn = None
if st.session_state.get("_reloaded"):
    st.info(f"🔄 检测到代码更新，已热重载：{st.session_state._reloaded}")
    st.session_state._reloaded = None

if "turns" not in st.session_state:
    st.session_state.turns = []       # [(user, translation, reply, mode, source)]
if "last_result" not in st.session_state:
    st.session_state.last_result = None

session = get_session()
router = get_router()

col1, col2 = st.columns([2, 3], gap="large")

# ================= 左栏：输入与设置 =================
with col1:
    st.markdown("#### ✍️ 输入文本")
    input_text = st.text_area("输入", placeholder="输入现代白话文或文言文…",
                              height=110, key="robot_input",
                              label_visibility="collapsed")

    # 麦克风录音（回调在 widget 实例化前运行，可安全预填输入框）
    def _mic_record():
        ai = get_audio_io()
        rec_path = os.path.join(OUT_DIR, "app_rec.wav")
        if not ai.record(5.0, rec_path):
            st.session_state.mic_msg = ("error", "录音失败：请检查麦克风（USB 耳麦采集端）")
            return
        asr = get_asr()
        text = asr.transcribe_wav(rec_path)
        if text:
            st.session_state.robot_input = text
            st.session_state.mic_msg = ("ok", f"识别：{text}")
        else:
            st.session_state.mic_msg = ("warn", "未听清，请再说一次或改用文字输入")

    st.button("🎤 录音 5 秒（对麦克风说话）", use_container_width=True,
              on_click=_mic_record,
              help="点击后录 5 秒，本地 Vosk 识别，结果自动填入输入框")
    if st.session_state.get("mic_msg"):
        kind, msg = st.session_state.mic_msg
        fn = {"ok": st.success, "warn": st.warning, "error": st.error}[kind]
        fn(msg)
        st.session_state.mic_msg = None

    st.markdown("#### 🎭 语音模式")
    st.radio("模式", ["自然语音", "东汉古音"],
             index=0 if router.mode == "natural" else 1,
             horizontal=True, label_visibility="collapsed",
             key="robot_mode")

    # 音色（自然语音）
    voices = tts_client.available_voices()
    voice_ids = [v[1] for v in voices]
    cur_voice = router.voice if router.voice in voice_ids else voice_ids[0]
    voice_idx = voice_ids.index(cur_voice)
    _mode_now = st.session_state.get("robot_mode",
                                     "自然语音" if router.mode == "natural" else "东汉古音")
    st.selectbox("🎙 音色（自然语音生效）", [v[0] for v in voices],
                 index=voice_idx, key="robot_voice",
                 disabled=(_mode_now != "自然语音"))

    # 语速
    st.slider("⏱ 语速（自然语音生效）", -50, 50, -10, 5,
              format="%+d%%", key="robot_rate",
              help="正数加快，负数放慢。自然语音（Edge TTS）生效。")
    st.slider("⏳ 语速（东汉古音生效）", 0.5, 2.0, 1.0, 0.1,
              format="×%.1f", key="robot_speed",
              help="1.0 正常；调小更慢、调大更快。古音模式生效。")

    # 语调（古音基频）
    st.slider("🎚 语调基频（东汉古音生效）", 80, 180, int(router.pitch), 5,
              help="Hz。数值越低声音越低沉。古音模式生效。",
              key="robot_pitch")

    # 生成（回调在 widget 实例化前运行，可安全读写状态）
    def _generate():
        text = (st.session_state.get("robot_input") or "").strip()
        if not text:
            st.session_state.gen_error = "请输入文本（或录音）"
            return
        ss = st.session_state
        # 应用界面上的设置
        router.set_mode("natural" if ss["robot_mode"] == "自然语音" else "ancient")
        name_to_id = {v[0]: v[1] for v in voices}
        router.voice = name_to_id.get(ss["robot_voice"], voice_ids[0])
        router.rate = f"{ss['robot_rate']:+d}%"
        router.speed = ss["robot_speed"]
        router.pitch = ss["robot_pitch"]
        st.session_state.gen_error = None
        try:
            turn = router.route(text, history=session.history())
        except Exception as e:
            st.session_state.gen_error = str(e)
            return
        if turn.error:
            st.session_state.gen_error = f"生成失败：{turn.error}"
            return
        session.add(text, turn.reply)
        st.session_state.last_result = {
            "translation": turn.translation,
            "reply": turn.reply,
            "reply_modern": turn.reply_modern,
            "source": turn.source,
            "mode": turn.mode,
            "audio": turn.audio,
            "audio_kind": turn.audio_kind,
            "coverage": turn.coverage_pct,
            "approx": turn.approx_chars,
            "user": text,
            "ms": time.time(),
        }
        st.session_state.turns.append(
            (text, turn.reply,
             "自然语音" if turn.mode == "natural" else "东汉古音"))
        st.session_state.turns = st.session_state.turns[-session.max_turns:]
        st.session_state.robot_input = ""   # 清空输入框

    st.button("🎵 生成并朗读", type="primary", use_container_width=True,
              on_click=_generate,
              help="Qwen 构思文言应答 → 按当前模式合成为自然语音或东汉古音")

    with st.expander("📖 关于本项目"):
        st.markdown(f"""
- 对话引擎：本地 **Qwen3-30B-A3B**（llama-server :8080），离线可用
- 东汉古音库：**{len(EASTERN_HAN_DB)}** 字（郑张尚芳体系，洛阳官音重建）
- 自然语音：Edge TTS（需网络，断网自动回退古音合成）
- 语音播放：浏览器内播放，或点"设备播放"走 PipeWire 默认输出（蓝牙音箱）
- 多轮对话：保留最近 **{session.max_turns}** 轮上下文
        """)

# ================= 右栏：结果 =================
with col2:
    if st.session_state.get("gen_error"):
        st.error(st.session_state.gen_error)
        st.session_state.gen_error = None

    res = st.session_state.last_result
    if res:
        st.markdown("#### 📜 应答")
        if res["translation"]:
            st.markdown(f'<div class="modern-text"><b>我的话·古汉语</b>：{res["translation"]}</div>',
                        unsafe_allow_html=True)
        st.markdown(f'<div class="classical-text">{res["reply"]}</div>',
                    unsafe_allow_html=True)
        # 白话版回答（与文言不同时显示）
        if res.get("reply_modern") and res["reply_modern"] != res["reply"]:
            st.markdown(f'<div class="modern-text"><b>白话</b>：{res["reply_modern"]}</div>',
                        unsafe_allow_html=True)

        # 徽标
        badges = f'<span class="badge">来源 {res["source"]}</span>'
        badges += f'<span class="badge">模式 {res["mode"]}</span>'
        if res["mode"] == "ancient":
            badges += (f'<span class="badge">古音覆盖 {res["coverage"]}%</span>'
                       f'<span class="badge">{res["approx"]} 字拼音近似</span>')
        st.markdown(badges, unsafe_allow_html=True)

        # IPA（古音模式）
        if res["mode"] == "ancient":
            r = text_to_ipa(res["reply"])
            st.markdown("#### 🔊 东汉洛阳音 IPA")
            st.markdown(f'<div class="ipa-display">{r.ipa_text}</div>',
                        unsafe_allow_html=True)

        # 音频
        st.markdown("#### 🔊 音频")
        fmt = "audio/wav" if res["audio_kind"] == "wav" else "audio/mpeg"
        c1, c2, c3 = st.columns([2, 1, 1], gap="small")
        with c1:
            st.audio(res["audio"], format=fmt)
        with c2:
            st.markdown(f'<div class="audio-card"><strong>设备播放</strong></div>',
                        unsafe_allow_html=True)
            # 后台发送：不阻塞界面（pw-play 不再等待播完）。
            # 先探测通道（0.3s）；若 A2DP 假连接(通道挂死)则自动重连再播。
            if st.button("▶ 蓝牙/默认设备", use_container_width=True,
                         key="dev_play"):
                ai = get_audio_io()
                if ai.probe():
                    ai.play_async(res["audio"])
                    st.success("已发送到默认输出设备（后台播放）")
                else:
                    with st.spinner("播放通道异常，正在重连蓝牙…"):
                        r = subprocess.run(
                            [os.path.join(ROOT, "robot", "bt_reset.sh")],
                            capture_output=True, timeout=90)
                    if ai.probe():
                        ai.play_async(res["audio"])
                        st.warning("蓝牙通道已重连，正在播放")
                    else:
                        st.error("重连后仍无法播放，请检查音箱电源/距离")
        with c3:
            fname = f"guyin_{int(res['ms'])}.{res['audio_kind']}"
            st.download_button("⬇ 下载", res["audio"],
                               file_name=fname, mime=fmt,
                               use_container_width=True)

        # 扩展朗读：现代汉语读回答 / 古汉语读我的话（翻译）
        cA, cB = st.columns(2, gap="small")
        with cA:
            st.markdown(f'<div class="audio-card"><strong>🗣 回答·现代汉语读</strong><br><span style="font-size:0.7rem;color:#7a6a5a">把回答翻成白话，用普通话念</span></div>',
                        unsafe_allow_html=True)
            if st.button("🗣 用现代汉语读回答", use_container_width=True,
                         key="tts_modern"):
                text = res.get("reply_modern") or res["reply"]
                with st.spinner("合成现代汉语朗读…"):
                    audio, k = synth_extended("modern", text, router)
                if audio:
                    get_audio_io().play_async(audio)
                    st.session_state.ext_audio = (audio, k)
                    st.session_state.ext_label = "回答·现代汉语"
                    st.success("正在播放：回答（现代汉语）")
                else:
                    st.warning("合成失败（网络不可用且古音合成失败）")
        with cB:
            st.markdown(f'<div class="audio-card"><strong>📜 我的话·古汉语读</strong><br><span style="font-size:0.7rem;color:#7a6a5a">把你的话翻成文言，用东汉音念</span></div>',
                        unsafe_allow_html=True)
            if st.button("📜 用古汉语读我的翻译", use_container_width=True,
                         key="tts_ancient_trans"):
                text = res.get("translation") or res["user"]
                audio, k = synth_extended("ancient_trans", text, router)
                if audio:
                    get_audio_io().play_async(audio)
                    st.session_state.ext_audio = (audio, k)
                    st.session_state.ext_label = "我的翻译·东汉古音"
                    st.success("正在播放：我的古汉语翻译（东汉音）")
                else:
                    st.warning("古音合成失败（无有效字符？）")

        # 扩展朗读的浏览器内回放（点过按钮后可在浏览器里再听）
        if st.session_state.get("ext_audio"):
            ea, ek = st.session_state.ext_audio
            st.markdown(f'##### 回放：{st.session_state.get("ext_label", "扩展朗读")}')
            efmt = "audio/wav" if ek == "wav" else "audio/mpeg"
            st.audio(ea, format=efmt)

        # 逐字音韵分析（古音模式）
        if res["mode"] == "ancient":
            rows = analyze_reply(res["reply"])
            if rows:
                st.markdown("---")
                st.markdown("#### 📊 逐字音韵分析")
                trs = []
                for a in rows:
                    tc = (f"tone-{a['tone']}"
                          if any(t in a["tone"] for t in "平上去入") else "")
                    tt = f'<span class="tone-tag {tc}">{a["tone"]}</span>'
                    src_color = "#7a9a7a" if a["src"] == "收录" else "#d4c4a8"
                    trs.append(
                        f"<tr><td style=\"font-weight:700\">{a['char']}</td>"
                        f"<td style=\"font-family:monospace\">{a['ipa']}</td>"
                        f"<td>{tt}</td>"
                        f"<td style=\"color:{src_color};font-size:0.75rem\">{a['src']}</td></tr>")
                st.markdown(
                    '<table class="phonology-table"><thead><tr>'
                    "<th>字</th><th>东汉IPA</th><th>声调</th><th>来源</th>"
                    f"</tr></thead><tbody>{''.join(trs)}</tbody></table>",
                    unsafe_allow_html=True)

        # 历史
        if len(st.session_state.turns) > 1:
            st.markdown("---")
            st.markdown(f"#### 🕰 对话历史（最近 {len(st.session_state.turns)} 轮）")
            for u, a, m in reversed(st.session_state.turns[-6:]):
                st.markdown(
                    f'<div class="history-item"><span class="u">〔{u}〕</span><br>'
                    f'<span class="a">{a}</span> '
                    f'<span style="color:#7a6a5a;font-size:0.7rem">· {m}</span></div>',
                    unsafe_allow_html=True)
            if st.button("🧹 清空对话历史"):
                session.reset()
                st.session_state.turns = []
                st.rerun()
