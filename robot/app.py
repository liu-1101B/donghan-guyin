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
import threading

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
from robot.audio_io import AudioIO, bt_status, BT_MAC
from services import tts_client
from language.ancient_tts import text_to_ipa, synthesize_ancient
from phonology_db import lookup_char, EASTERN_HAN_DB

OUT_DIR = os.path.join(ROOT, "audio_out")
os.makedirs(OUT_DIR, exist_ok=True)


# ---------- 后台生成（线程内不碰 Streamlit API，状态写 job 字典） ----------
def _gen_worker(job, session, cfg):
    """后台线程：LLM 生成 + 三类语音合成 + 自动朗读，结果只写进 job。

    一次生成三段音频（互不干扰，各占独立播放对象）：
      user      我的话·东汉古音（文言翻译，无翻译则用原话）
      reply_anc 回答·东汉古音
      reply_mod 回答·现代汉语（Edge TTS，需网络；失败则该段为空+说明）
    线程内不碰 st.session_state / st.*（避免跨线程上下文问题），
    所有状态落盘由主线程的轮询 fragment 在 result 就绪时统一完成。
    """
    from services import llm_client
    try:
        job["phase"] = "qwen"
        gen = llm_client.generate_turn(cfg["text"], session.history())
        translation = (gen.get("translation") or "").strip()
        reply = (gen.get("reply") or "").strip() or "善。"
        reply_modern = (gen.get("reply_modern") or "").strip() or reply
        source = gen.get("source", "local")

        user_text = translation or cfg["text"]

        def _do_user():
            return "user", synthesize_ancient(
                user_text, pitch=cfg["pitch"], speed=cfg["speed"])

        def _do_reply_anc():
            return "reply_anc", synthesize_ancient(
                reply, pitch=cfg["pitch"], speed=cfg["speed"])

        def _do_reply_mod():
            # 现代汉语只做真 Edge TTS（断网则该段为空），绝不共振峰兜底
            return "reply_mod", tts_client.speak_natural(
                reply_modern, voice=cfg["voice"], rate=cfg["rate"])

        # 三段并行合成（Orin 12 核，各自独立：formant 吃 CPU、Edge 等网络）
        job["phase"] = "synth"
        done = {"user": (b"", None), "reply_anc": (b"", None),
                "reply_mod": (b"", None)}
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(f) for f in (_do_user, _do_reply_anc,
                                           _do_reply_mod)]
            for fut in concurrent.futures.as_completed(futs):
                key, val = fut.result()
                if key in ("user", "reply_anc"):
                    wav, result = val
                    done[key] = (wav, result)
                else:  # reply_mod：直接是 mp3 字节（失败为 None）
                    done["reply_mod"] = (val or b"", None)
                job["phase"] = f"synth_{key}"
        (wav_u, _), (wav_r, result_r), (mp3_m, _) = (
            done["user"], done["reply_anc"], done["reply_mod"])
        if not wav_r:
            # 古音合成失败（极个别文本）→ 标注兜底，不装腔
            source = f"{source}+ancient_fallback"

        job["result"] = ("ok", {
            "user": cfg["text"],
            "translation": translation,
            "reply": reply,
            "reply_modern": reply_modern,
            "source": source,
            "mode": cfg["mode"],
            "coverage": result_r.coverage_pct if wav_r else 0.0,
            "approx": result_r.approx if wav_r else 0,
            "audios": {
                "user": {"data": wav_u, "kind": "wav", "text": user_text},
                "reply_anc": {"data": wav_r, "kind": "wav", "text": reply},
                "reply_mod": {"data": mp3_m, "kind": "mp3",
                              "text": reply_modern},
            },
            "ms": time.time(),
        })
        if not (wav_u or wav_r or mp3_m):
            return
        # 自动朗读：按模式选主段（自然语音→现代段；东汉古音→古音段），
        # 主段缺失时按 古音回答 → 现代回答 → 我的话 顺序退
        job["phase"] = "play"
        a = job["result"][1]["audios"]
        pref = a["reply_mod"] if cfg["mode"] == "natural" else a["reply_anc"]
        main = pref if pref["data"] else next(
            (x for x in (a["reply_anc"], a["reply_mod"], a["user"])
             if x["data"]), None)
        try:
            ai = get_audio_io()
            job["play_ok"] = _ensure_playable(ai, spinner=False)
            if job["play_ok"]:
                ai.play_async(main["data"])
        except Exception:
            job["play_ok"] = False
    except Exception as e:
        job["result"] = ("error", str(e))


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


def _bt_healthy() -> bool:
    """蓝牙音箱通道是否可播：A2DP sink 存在 + 是默认输出。

    只查这两项（~2s）；probe 另跑（~0.4s）。sink 消失（A2DP profile
    断开）是"无声但不报错"的主因，必须显式查——探测音发给空接口
    也会"成功"，不可单独依赖。
    """
    s = bt_status(BT_MAC)
    return bool(s["sink_id"] and s["is_default"])


def _ensure_playable(ai, spinner=True) -> bool:
    """确保蓝牙音箱可播：sink 检查 → 通道探测 →(异常则)自动重连。

    正常时 ~2.5s；仅异常时触发一次 bt_reset.sh（断开→重连→设默认，
    ~20s）。重连后复检 sink+探测。spinner=False 用于自动朗读路径
    （避免每次生成都闪转圈）。
    """
    if _bt_healthy() and ai.probe():
        return True
    if spinner:
        with st.spinner("蓝牙通道异常，正在自动重连…"):
            subprocess.run([os.path.join(ROOT, "robot", "bt_reset.sh")],
                           capture_output=True, timeout=120)
    else:
        subprocess.run([os.path.join(ROOT, "robot", "bt_reset.sh")],
                       capture_output=True, timeout=120)
    return _bt_healthy() and ai.probe()


# ---------- 页面（简约素雅版） ----------
st.set_page_config(page_title="古音机器人 · 东汉洛阳官音",
                   page_icon="🏛️", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;900&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
    :root { --paper:#f5f2ea; --card:#fffefb; --line:#e4dccb; --ink:#26221a; --ink2:#5c5546; --ink3:#9a917e; --seal:#a63d2a; }
    html, body, [class*="css"] { font-family:'Noto Sans SC','PingFang SC',sans-serif; }
    .stApp { background:var(--paper); }
    .block-container { max-width:1060px; padding-top:2.4rem; padding-bottom:3rem; }

    .gi-title { font-family:'Noto Serif SC',serif; font-weight:900; font-size:2.1rem; color:var(--ink); letter-spacing:0.35em; }
    .gi-title::before { content:''; display:inline-block; width:0.55rem; height:0.55rem; background:var(--seal); margin-right:0.7rem; }
    .gi-sub { color:var(--ink3); font-size:0.85rem; letter-spacing:0.25em; margin:0.3rem 0 2.2rem 0; }

    .gi-h { font-size:0.78rem; color:var(--ink3); letter-spacing:0.22em; margin:1.4rem 0 0.55rem 0; font-weight:500; }
    .gi-gap { height:1.1rem; }

    /* ============ 根治整页变暗 ============
       Streamlit 在任何整页 rerun 时会把全部元素标记 data-stale=true，
       内联 style 打上 opacity:0.33 + transition:1s（1.66 前端
       styled-components 里 {opacity:a.stale}，stale=0.33）。
       无论 rerun 多快，用户都会看到"整页缓缓变暗再恢复"。
       该样式不只落在容器上，按钮/expander/tabs 自身也会各自内联
       同一对象（opacity 沿 DOM 链相乘）→ 容器和后代都要覆盖。
       !important 压过内联样式，彻底禁用；等待感改由下方
       .gi-thinking 对话式动效表达（页面保持全亮可操作）。*/
    [data-stale="true"], [data-stale="true"] * { opacity:1 !important; }
    .gi-meta { font-size:0.78rem; color:var(--ink3); letter-spacing:0.1em; margin-bottom:0.6rem; }
    .gi-status { display:flex; align-items:center; gap:0.6rem; font-size:0.95rem; color:var(--ink2); padding:0.9rem 0.4rem 0.3rem; }
    .gi-status::before { content:""; width:0.9rem; height:0.9rem; border:2px solid var(--line); border-top-color:var(--ink); border-radius:50%; animation:gi-spin 0.9s linear infinite; flex:none; }
    @keyframes gi-spin { to { transform:rotate(360deg); } }

    /* 对话式"构思中"（参考主流聊天产品：气泡+呼吸点，不打暗整页） */
    .gi-thinking { padding:1.2rem 0.4rem 0.4rem; }
    .gi-thinking-user { font-family:'Noto Serif SC',serif; font-size:1.02rem; color:var(--ink);
        letter-spacing:0.06em; margin:0 0 0.65rem 0.2rem; padding-left:0.8rem;
        border-left:2px solid var(--seal); line-height:1.9; }
    .gi-thinking-line { display:inline-flex; align-items:center; gap:0.6rem;
        font-family:'Noto Serif SC',serif; font-size:1rem; color:var(--ink2);
        letter-spacing:0.12em; padding:0.55rem 1.1rem;
        background:var(--card); border:1px solid var(--line); border-radius:14px 14px 14px 4px; }
    .gi-dot { display:inline-flex; gap:0.22rem; align-items:center; }
    .gi-dot i { width:0.32rem; height:0.32rem; border-radius:50%; background:var(--seal);
        display:inline-block; animation:gi-breathe 1.2s ease-in-out infinite; }
    .gi-dot i:nth-child(2) { animation-delay:0.2s; }
    .gi-dot i:nth-child(3) { animation-delay:0.4s; }
    @keyframes gi-breathe { 0%,100% { opacity:0.25; transform:scale(0.8); }
        50% { opacity:1; transform:scale(1.15); } }

    /* 音频卡片（三段语音各占一卡：标题+文本+播放器+操作） */
    .gi-audio-card { margin:0.9rem 0 0.3rem; padding:0.75rem 1rem 0.85rem;
        background:var(--card); border:1px solid var(--line); border-radius:10px; }
    .gi-audio-title { font-size:0.78rem; color:var(--ink3); letter-spacing:0.2em; margin-bottom:0.45rem; font-weight:500; }
    .gi-audio-text { font-family:'Noto Serif SC',serif; font-size:0.98rem; line-height:1.9; color:var(--ink2); margin-bottom:0.35rem; }
    .gi-audio-off .gi-audio-text { display:none; }
    .gi-audio-offline { color:var(--ink3); font-size:0.82rem; letter-spacing:0.05em; padding:0.15rem 0 0.1rem; }
    .gi-audio-off { background:transparent; border-style:dashed; }
    .gi-classical { font-family:'Noto Serif SC',serif; font-size:1.42rem; line-height:2.05; color:var(--ink); letter-spacing:0.05em; padding:0.1rem 0 0.1rem 1.1rem; border-left:2px solid #d8cfbc; margin:0.4rem 0; }
    .gi-classical.gi-small { font-size:1.1rem; }
    .gi-muteline { color:var(--ink2); font-size:0.92rem; line-height:1.9; margin:0.2rem 0; }

    .gi-ipa { font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace; font-size:0.85rem; color:var(--ink2); background:#efe9db; padding:0.6rem 0.9rem; border-radius:8px; line-height:1.9; word-break:break-all; margin:0.4rem 0; }

    .gi-empty { color:var(--ink3); font-family:'Noto Serif SC',serif; font-size:1rem; line-height:2.4; text-align:center; margin-top:5rem; letter-spacing:0.1em; }

    .gi-hist { border-bottom:1px solid var(--line); padding:0.55rem 0.1rem; font-size:0.88rem; color:var(--ink2); }
    .gi-hist .a { font-family:'Noto Serif SC',serif; color:var(--ink); }
    .gi-hist .m { color:var(--ink3); font-size:0.72rem; margin-left:0.4rem; }

    .gi-phon { width:100%; border-collapse:collapse; font-size:0.82rem; }
    .gi-phon th { color:var(--ink3); font-weight:500; text-align:left; padding:0.45rem 0.5rem; border-bottom:1px solid var(--line); font-size:0.75rem; letter-spacing:0.05em; }
    .gi-phon td { padding:0.42rem 0.5rem; border-bottom:1px solid #f0eadd; color:var(--ink2); }
    .gi-phon td.ch { font-family:'Noto Serif SC',serif; font-weight:600; font-size:1.02rem; color:var(--ink); }
    .gi-phon td.ipa { font-family:ui-monospace,Menlo,monospace; font-size:0.8rem; }
    .gi-phon tr:hover td { background:#faf7f0; }
    .tone-tag { display:inline-block; font-size:0.7rem; padding:0.08rem 0.45rem; border-radius:4px; }
    .tone-平声 { color:#4a7a5a; background:rgba(74,122,90,.12); }
    .tone-上声 { color:#4a6a9a; background:rgba(74,106,154,.12); }
    .tone-去声 { color:#a0442c; background:rgba(160,68,44,.10); }
    .tone-入声 { color:#b06a2c; background:rgba(176,106,44,.10); }

    /* 输入框 */
    .stApp [data-testid="stTextArea"] { background:var(--card) !important; border:1px solid var(--line) !important; border-radius:10px !important; }
    .stTextArea textarea { font-size:0.98rem; color:var(--ink) !important; caret-color:var(--seal) !important; }
    .stTextArea textarea::placeholder { color:var(--ink3) !important; opacity:1 !important; }
    .stTextArea textarea:focus { border-color:var(--ink2) !important; box-shadow:none !important; }

    /* 按钮 */
    .stButton > button, .stDownloadButton > button {
        font-family:'Noto Sans SC',sans-serif; border-radius:8px; padding:0.42rem 0.8rem;
        background:var(--card); border:1px solid var(--line); color:var(--ink2);
        font-size:0.84rem; letter-spacing:0.02em; box-shadow:none; }
    .stButton > button:hover, .stDownloadButton > button:hover {
        border-color:var(--ink2); color:var(--ink); background:#fff; box-shadow:none; }
    .stButton > button:disabled { background:var(--paper); color:var(--ink3); cursor:not-allowed; }
    .stButton > button[kind="primary"] {
        background:var(--ink); border-color:var(--ink); color:var(--paper);
        font-weight:600; font-size:1rem; letter-spacing:0.3em; padding:0.62rem 1.2rem; }
    .stButton > button[kind="primary"]:hover { background:#3d382d; border-color:#3d382d; }

    /* 模式分段控件 */
    .stRadio [role="radiogroup"] { display:flex; gap:0.5rem; }
    .stRadio [role="radiogroup"] label {
        flex:1; border:1px solid var(--line); border-radius:8px; background:var(--card);
        padding:0.42rem 1rem; cursor:pointer; transition:all .15s ease; position:relative; }
    .stRadio [role="radiogroup"] input[type="radio"] { position:absolute; opacity:0; pointer-events:none; }
    .stRadio [role="radiogroup"] [data-testid="stRadioLabel"] {
        width:100%; text-align:center; font-weight:500; color:var(--ink2); letter-spacing:0.12em; }
    .stRadio [role="radiogroup"] label:has(input:checked) {
        border-color:var(--ink); background:var(--ink); color:var(--paper) !important; }
    .stRadio [role="radiogroup"] label:has(input:checked) * { color:var(--paper) !important; }

    /* 滑杆 */
    .stSlider [data-baseweb="slider"] input { background:var(--ink2) !important; }

    /* 折叠面板 */
    .stExpander { background:var(--card) !important; border:1px solid var(--line) !important; border-radius:10px !important; box-shadow:none !important; }
    .stExpander summary { font-size:0.88rem; color:var(--ink2); font-weight:500; }
    .stExpander summary:hover { color:var(--ink); }

    /* 提示条 */
    div[data-testid="stSuccess"], div[data-testid="stError"],
    div[data-testid="stWarning"], div[data-testid="stInfo"] {
        border-radius:10px; padding:0.5rem 0.9rem; font-size:0.85rem; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="gi-title">古音</div>', unsafe_allow_html=True)
st.markdown('<div class="gi-sub">东汉 · 洛阳官音 · QWEN 对谈</div>', unsafe_allow_html=True)

if st.session_state.get("_reload_warn"):
    st.warning(st.session_state._reload_warn)
    st.session_state._reload_warn = None
if st.session_state.get("_reloaded"):
    st.info(f"检测到代码更新，已热重载：{st.session_state._reloaded}")
    st.session_state._reloaded = None

if "turns" not in st.session_state:
    st.session_state.turns = []       # [(user, reply, mode_label)]
if "last_result" not in st.session_state:
    st.session_state.last_result = None

session = get_session()
router = get_router()

# 设置项初始化（切模式时控件不渲染也要有值，防止 KeyError）
voices = tts_client.available_voices()
voice_ids = [v[1] for v in voices]
cur_voice = router.voice if router.voice in voice_ids else voice_ids[0]
voice_idx = voice_ids.index(cur_voice)

col1, col2 = st.columns([5, 7], gap="large")

# ================= 左栏：输入与设置 =================
with col1:
    st.markdown('<div class="gi-h">输入</div>', unsafe_allow_html=True)
    st.text_area("输入", placeholder="说点什么，白话或文言都可以…",
                 height=120, key="robot_input", label_visibility="collapsed")

    def _mic_record():
        ai = get_audio_io()
        rec_path = os.path.join(OUT_DIR, "app_rec.wav")
        if not ai.record(5.0, rec_path):
            st.toast("录音失败：请检查麦克风", icon="⚠️")
            return
        asr = get_asr()
        text = asr.transcribe_wav(rec_path)
        if text:
            st.session_state.robot_input = text
            st.toast(f"识别：{text}")
        else:
            st.toast("未听清，请再说一次", icon="⚠️")

    st.button("录音 5 秒", on_click=_mic_record, use_container_width=True,
              help="对麦克风说话 5 秒，本地识别后填入输入框")

    st.markdown('<div class="gi-h">语音模式</div>', unsafe_allow_html=True)
    st.radio("模式", ["自然语音", "东汉古音"],
             index=0 if router.mode == "natural" else 1,
             horizontal=True, label_visibility="collapsed", key="robot_mode")

    with st.expander("语音设置"):
        _m = st.session_state.get("robot_mode", "自然语音")
        if _m == "自然语音":
            st.selectbox("音色", [v[0] for v in voices],
                         index=voice_idx, key="robot_voice")
            st.slider("语速", -50, 50, -10, 5, format="%+d%%", key="robot_rate")
            st.caption("正数加快，负数放慢。音色与语速仅自然语音模式生效。")
        else:
            st.slider("语速", 0.5, 2.0, 1.0, 0.1, format="×%.1f", key="robot_speed")
            st.slider("基频（Hz，越低越沉）", 80, 180, int(router.pitch), 5,
                      key="robot_pitch")
            st.caption("语速与基频仅东汉古音模式生效。")

    def _generate():
        """登记后台任务并立即返回（LLM+TTS 在后台线程跑，
        轮询 fragment 跟进进度）→ 生成期间整页不再变暗、控件可用"""
        text = (st.session_state.get("robot_input") or "").strip()
        if not text:
            st.session_state.gen_error = "请输入文本（或录音）"
            return
        ss = st.session_state
        # 防连点：上一次生成未完成则忽略
        _prev = ss.get("gen_job")
        if _prev is not None and _prev.get("result") is None:
            return
        # 设置控件按当前模式渲染，另一模式的 key 可能未创建 → 用 .get 兜底
        name_to_id = {v[0]: v[1] for v in voices}
        mode = "natural" if ss["robot_mode"] == "自然语音" else "ancient"
        cfg = {
            "text": text,
            "mode": mode,
            "mode_label": "自然语音" if mode == "natural" else "东汉古音",
            "voice": name_to_id.get(ss.get("robot_voice"), voice_ids[0]),
            "rate": f"{int(ss.get('robot_rate', -10)):+d}%",
            "speed": float(ss.get("robot_speed", 1.0)),
            "pitch": int(ss.get("robot_pitch", router.pitch)),
        }
        # 同步 router（供扩展朗读按钮复用当前设置）
        router.set_mode(mode)
        router.voice, router.rate = cfg["voice"], cfg["rate"]
        router.speed, router.pitch = cfg["speed"], cfg["pitch"]
        ss.gen_error = None
        ss.robot_input = ""
        job = {"phase": "start", "result": None, "play_ok": None,
               "user": text}
        ss.gen_job = job
        threading.Thread(target=_gen_worker,
                         args=(job, session, cfg),
                         daemon=True).start()

    st.markdown('<div class="gi-gap"></div>', unsafe_allow_html=True)
    st.button("生成并朗读", type="primary", use_container_width=True,
              on_click=_generate,
              help="Qwen 构思文言应答 → 按当前模式合成并自动朗读")

    with st.expander("关于本项目"):
        st.markdown(f"""- 对话引擎：本地 Qwen3-30B-A3B（llama-server :8080）
- 东汉古音库：{len(EASTERN_HAN_DB)} 字（郑张尚芳体系，洛阳官音重建）
- 自然语音：Edge TTS（需网络，断网回退古音合成）
- 设备播放：PipeWire 默认输出（蓝牙），异常自动重连
- 多轮对话：保留最近 {session.max_turns} 轮上下文""")

# ================= 右栏：结果 =================
with col2:
    if st.session_state.get("gen_error"):
        st.error(st.session_state.gen_error)
        st.session_state.gen_error = None

    # 后台生成状态区（独立 fragment 轮询，只刷新这一小块）
    _PHASE_LABEL = {
        "start": "正在构思…",
        "qwen": "构思文言应答…",
        "synth": "合成语音…",
        "synth_user": "合成语音中 · 我的话…",
        "synth_reply_anc": "合成语音中 · 古音回答…",
        "synth_reply_mod": "合成语音中 · 现代回答…",
        "play": "准备朗读…",
    }

    @st.fragment(run_every=1)
    def _gen_status():
        job = st.session_state.get("gen_job")
        if not job or job["result"] is None:
            if job:
                import html as _html
                label = _PHASE_LABEL.get(job["phase"], "生成中…")
                user = _html.escape((job.get("user") or "").strip())
                # 对话式等待（参考主流聊天产品：页面保持全亮可操作，
                # 等待感靠气泡动效表达——先回显用户那句话，再跟呼吸点）
                user_html = (f'<div class="gi-thinking-user">{user}</div>'
                             if user else "")
                st.markdown(
                    f'<div class="gi-thinking">{user_html}'
                    f'<div class="gi-thinking-line">{label}'
                    f'<span class="gi-dot"><i></i><i></i><i></i></span></div>'
                    f'</div>',
                    unsafe_allow_html=True)
            return
        kind, payload = job["result"]
        ss = st.session_state
        ss.gen_job = None
        if kind == "error":
            ss.gen_error = payload
            return
        session.add(payload["user"], payload["reply"])   # LLM 上下文
        ss.last_result = payload
        ss.turns.append((payload["user"], payload["reply"],
                         "自然语音" if payload["mode"] == "natural" else "东汉古音"))
        ss.turns = ss.turns[-session.max_turns:]
        if job.get("play_ok") is True:
            ss.play_note = "已朗读到默认输出设备"
        elif job.get("play_ok") is False:
            ss.play_note = "已生成（自动朗读失败，可点「设备播放」重试）"
        st.rerun(scope="app")

    _gen_status()

    res = st.session_state.last_result
    if not res:
        st.markdown('<div class="gi-empty">说一句话试试。<br>机器人以文言应答，并按所选模式朗读。</div>',
                    unsafe_allow_html=True)
    else:
        # 元信息（一行，替代徽章堆）
        src = res["source"]
        src_name = {"local-qwen": "本地 Qwen", "cloud": "云端",
                    "local-rules": "本地规则", "fallback": "兜底"} \
            .get(src.split("+")[0], src)
        if "ancient_fallback" in src:
            src_name += " · 古音兜底"
        meta = f'模式 {res["mode"] if res["mode"] == "natural" else "东汉古音"} · 来源 {src_name}'
        if res["mode"] == "ancient":
            meta += f' · 古音覆盖 {res["coverage"]}%'
        st.markdown(f'<div class="gi-meta">{meta}</div>', unsafe_allow_html=True)

        if res["translation"]:
            st.markdown(f'<div class="gi-muteline">我的话 · 古汉语：{res["translation"]}</div>',
                        unsafe_allow_html=True)
        st.markdown(f'<div class="gi-classical">{res["reply"]}</div>',
                    unsafe_allow_html=True)
        if res.get("reply_modern") and res["reply_modern"] != res["reply"]:
            st.markdown(f'<div class="gi-muteline">白话：{res["reply_modern"]}</div>',
                        unsafe_allow_html=True)

        # 三段音频（每次生成都产出：我的话·古音 / 回答·古音 / 回答·现代）
        st.markdown('<div class="gi-h">语音</div>', unsafe_allow_html=True)
        if st.session_state.get("play_note"):
            st.caption(st.session_state.play_note)
        audios = res.get("audios") or {}
        _CARD_ORDER = [
            ("user", "我的话 · 东汉古音"),
            ("reply_anc", "回答 · 东汉古音"),
            ("reply_mod", "回答 · 现代汉语"),
        ]
        for key, label in _CARD_ORDER:
            item = audios.get(key)
            if not item or not item["data"]:
                if key == "reply_mod":
                    st.markdown(
                        f'<div class="gi-audio-card gi-audio-off">'
                        f'<div class="gi-audio-title">{label}</div>'
                        f'<div class="gi-audio-offline">网络不可用，未生成'
                        f'（现代汉语不做本地兜底合成）</div></div>',
                        unsafe_allow_html=True)
                elif key in ("user", "reply_anc"):
                    st.markdown(
                        f'<div class="gi-audio-card gi-audio-off">'
                        f'<div class="gi-audio-title">{label}</div>'
                        f'<div class="gi-audio-offline">合成失败'
                        f'（无有效汉字？）</div></div>',
                        unsafe_allow_html=True)
                continue
            st.markdown(
                f'<div class="gi-audio-card">'
                f'<div class="gi-audio-title">{label}</div>'
                f'<div class="gi-audio-text">{item["text"]}</div>'
                f'</div>',
                unsafe_allow_html=True)
            fmt = "audio/wav" if item["kind"] == "wav" else "audio/mpeg"
            st.audio(item["data"], format=fmt)
            cb1, cb2 = st.columns([3, 2], gap="small")
            with cb1:
                if st.button("设备播放", key=f"dev_play_{key}",
                             use_container_width=True,
                             help="检查并修复蓝牙通道后，用默认输出设备播放"):
                    ai = get_audio_io()
                    if _ensure_playable(ai):
                        ai.play_async(item["data"])
                        st.session_state.play_note = f"已发送到默认输出设备（{label}）"
                    else:
                        st.error("播放通道异常：自动重连后仍无法播放，请检查设备电源/距离")
            with cb2:
                fname = f"guyin_{key}_{int(res['ms'])}.{item['kind']}"
                st.download_button("下载", item["data"], file_name=fname,
                                   mime=fmt, use_container_width=True,
                                   key=f"dl_{key}")

        # 东汉 IPA（古音模式）
        if res["mode"] == "ancient":
            r = text_to_ipa(res["reply"])
            st.markdown('<div class="gi-h">东汉洛阳音 IPA</div>',
                        unsafe_allow_html=True)
            st.markdown(f'<div class="gi-ipa">{r.ipa_text}</div>',
                        unsafe_allow_html=True)

        # 逐字音韵分析（古音模式，收进折叠面板）
        if res["mode"] == "ancient":
            rows = analyze_reply(res["reply"])
            if rows:
                with st.expander(f"逐字音韵分析（{len(rows)} 字）"):
                    trs = []
                    for a in rows:
                        tc = (f"tone-{a['tone']}"
                              if any(t in a["tone"] for t in "平上去入") else "")
                        tt = f'<span class="tone-tag {tc}">{a["tone"]}</span>'
                        src_color = "#4a7a5a" if a["src"] == "收录" else "#9a917e"
                        trs.append(
                            f"<tr><td class=\"ch\">{a['char']}</td>"
                            f"<td class=\"ipa\">{a['ipa']}</td>"
                            f"<td>{tt}</td>"
                            f"<td style=\"color:{src_color};font-size:0.75rem\">{a['src']}</td></tr>")
                    st.markdown(
                        '<table class="gi-phon"><thead><tr>'
                        "<th>字</th><th>东汉 IPA</th><th>声调</th><th>来源</th>"
                        f"</tr></thead><tbody>{''.join(trs)}</tbody></table>",
                        unsafe_allow_html=True)

        # 对话历史（收进折叠面板）
        if st.session_state.turns:
            with st.expander(f"对话历史（{len(st.session_state.turns)} 轮）"):
                for u, a, m in reversed(st.session_state.turns[-6:]):
                    st.markdown(
                        f'<div class="gi-hist"><span class="u">{u}</span><br>'
                        f'<span class="a">{a}</span>'
                        f'<span class="m">{m}</span></div>',
                        unsafe_allow_html=True)
                if st.button("清空历史", key="clear_hist"):
                    session.reset()
                    st.session_state.turns = []
                    st.rerun()
