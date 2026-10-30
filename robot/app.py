"""
robot/app.py
东汉古韵机器人 · 使用界面（Streamlit，风格对齐原项目 guyun_app.py）

启动：
    cd donghan-guyin && source .venv/bin/activate
    streamlit run robot/app.py
    # 浏览器打开 http://localhost:8501

功能：
    - 输入白话文/古文（或点按钮录 5 秒麦克风），Qwen 生成文言应答
    - 模式：自然语音（Edge TTS）/ 东汉古韵（音韵库合成）
    - 可调：音色（自然模式）、语速（两模式各自）、语调基频（古韵模式）
    - 浏览器内播放 + 一键"设备播放"（走 PipeWire 默认输出，如蓝牙音箱）
    - 多轮对话历史（默认 8 轮）
"""
import os
import subprocess
import sys
import time
import base64
import threading
import json

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
    "robot.session", "robot.voice_router", "robot.windows_audio",
    "robot.audio_io", "robot.recorder",
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
        failed = []
        for name in _RELOAD_ORDER:   # 全部按依赖顺序重载
            try:
                importlib.reload(importlib.import_module(name))
            except Exception as e:
                failed.append(name)
                st.session_state._reload_warn = f"重载 {name} 失败：{e}"
        if failed:
            # 有模块重载失败：**不推进基线**（旧基线保留 → 下次仍判定为
            # "需重载"并重试）。若照旧推进，会出现 磁盘新 / 内存旧 /
            # 基线已新 的错位——之后 m>seen 永远不成立，热重载彻底
            # 停摆，app.py 顶层 import 持续命中旧缓存模块 → ImportError
            # 卡死（10/27 ensure_audible 事故根因）。
            st.session_state._reload_failed = ", ".join(failed)
        else:
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
from robot.audio_io import (AudioIO, bt_status, BT_MAC, _list_pw_sinks,
                            ensure_audible)
from robot.recorder import hold_to_record, decode_wav
from services.asr_client import (available_backends as asr_available_backends,
                                 BACKEND_LABELS as _ASR_LABELS)
from services import tts_client
from language.ancient_tts import text_to_ipa, synthesize_ancient
from language.era_audio import MIDDLE_SYSTEM_DEFAULT, middle_system_label
from phonology_db import lookup_char, EASTERN_HAN_DB

OUT_DIR = os.path.join(ROOT, "audio_out")
os.makedirs(OUT_DIR, exist_ok=True)
PREFERENCES_FILE = os.path.join(ROOT, ".robot_preferences.json")
LLM_MODE_LABELS = {
    "api": "大模型 API（高质量回答）",
    "dictionary": "本地词典（简单回复）",
}


def _load_robot_preferences():
    try:
        with open(PREFERENCES_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_robot_preferences(preferences):
    """Persist per-device UI preferences atomically, without storing secrets."""
    temp_path = PREFERENCES_FILE + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(preferences, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, PREFERENCES_FILE)
        return True
    except OSError as exc:
        print(f"[ui] 无法保存用户设置：{exc.__class__.__name__}")
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except OSError:
            pass
        return False


def _persist_llm_mode():
    mode = st.session_state.get("llm_mode", "dictionary")
    if mode not in LLM_MODE_LABELS:
        mode = "dictionary"
    preferences = _load_robot_preferences()
    preferences["llm_mode"] = mode
    _save_robot_preferences(preferences)


# ---------- .env 读写（界面里直接填 API，不用去改文件） ----------
ENV_FILE = os.path.join(ROOT, ".env")
_ENV_KEYS = ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")
_DEFAULT_BASE = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o-mini"


def _read_env_file():
    values = {}
    try:
        with open(ENV_FILE, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


def _write_env_values(updates):
    """只改这三个键；注释和其他键原样保留，写临时文件再原子替换。"""
    try:
        with open(ENV_FILE, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        lines = [
            "# 大模型 API 设置（由界面写入；此文件已在 .gitignore 中，不要提交）",
        ]
    out, seen = [], set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            if out and out[-1].strip():
                out.append("")
            out.append(f"{key}={value}")
    tmp = ENV_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out).rstrip() + "\n")
    os.replace(tmp, ENV_FILE)
    for key, value in updates.items():
        os.environ[key] = value
    try:
        from services import llm_client
        llm_client.refresh_credentials()      # 立即生效，不必重启
    except Exception:
        pass


def _current_llm_settings():
    env = _read_env_file()
    key = (os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
           or env.get("LLM_API_KEY") or "")
    return {
        "base": os.environ.get("LLM_BASE_URL") or env.get("LLM_BASE_URL") or _DEFAULT_BASE,
        "model": os.environ.get("LLM_MODEL") or env.get("LLM_MODEL") or _DEFAULT_MODEL,
        "key": key,
    }


def _mask_key(key):
    if not key:
        return "未配置"
    return f"已配置（末四位 {key[-4:]}）" if len(key) >= 8 else "已配置（密钥太短？）"


def _input_key():
    """输入框的 key 带版本号（见 _set_input）。"""
    return f"robot_input_v{st.session_state.get('_input_ver', 0)}"


def _set_input(text):
    """把文字放进输入框。

    不能直接写 st.session_state["robot_input"]：用户一旦在页面上编辑过这个
    输入框（比如删掉旧内容），客户端会把自己的值回传，覆盖掉服务端的赋值 →
    录音识别结果就"写不进去"（实测：第一次能用，删一次内容之后再也不回填）。
    换一个新 key 等价于换一个新控件，值必然生效。
    """
    st.session_state["_input_ver"] = int(st.session_state.get("_input_ver", 0)) + 1
    st.session_state[_input_key()] = text


def asr_backend_label(name):
    return _ASR_LABELS.get(name, name)


def _wav_levels(path):
    """返回 (峰值 dBFS, 均方根 dBFS)。

    用来把「麦克风根本没声音」和「有声音但没识别对」分开——否则两种情况
    在界面上都是"没反应"，只能靠猜。
    """
    import math
    import wave as _wave

    import numpy as _np

    try:
        with _wave.open(path, "rb") as wf:
            width = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())
    except Exception:
        return -120.0, -120.0
    if width != 2 or not frames:
        return -120.0, -120.0
    data = _np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
    if data.size == 0:
        return -120.0, -120.0
    peak = float(_np.max(_np.abs(data)))
    rms = float(_np.sqrt(_np.mean(_np.square(data))))
    db = lambda v: 20.0 * math.log10(v) if v > 1e-6 else -120.0
    return db(peak), db(rms)


# ---------- 后台生成（线程内不碰 Streamlit API，状态写 job 字典） ----------
def _gen_worker(job, session, cfg):
    """后台线程：LLM 生成 + 三类语音合成 + 自动朗读，结果只写进 job。

    一次生成三段音频（互不干扰，各占独立播放对象）：
      user      我的话·东汉古韵（文言翻译，无翻译则用原话）
      reply_anc 回答·东汉古韵
      reply_mod 回答·现代汉语（Edge TTS，需网络；失败则该段为空+说明）
    线程内不碰 st.session_state / st.*（避免跨线程上下文问题），
    所有状态落盘由主线程的轮询 fragment 在 result 就绪时统一完成。
    """
    from services import llm_client
    try:
        job["phase"] = "qwen"
        gen = llm_client.generate_turn(
            cfg["text"], session.history(), mode=cfg.get("llm_mode"),
            allow_llm_translate=bool(cfg.get("allow_llm_translate"))
        )
        translation = (gen.get("translation") or "").strip()
        reply = (gen.get("reply") or "").strip()
        reply_modern = (gen.get("reply_modern") or "").strip() if reply else ""
        source = gen.get("source", "local")
        translation_source = gen.get("translation_source", "")
        missed_chars = gen.get("missed_chars") or []
        middle_system = cfg.get("middle_system") or MIDDLE_SYSTEM_DEFAULT

        # 词典无匹配时，不创建虚构回答；只合成输入内容的古汉语翻译。
        user_text = translation or cfg["text"]

        def _do_user():
            return "user", synthesize_ancient(
                user_text, pitch=cfg["pitch"], speed=cfg["speed"])

        def _do_reply_anc():
            return "reply_anc", synthesize_ancient(
                reply, pitch=cfg["pitch"], speed=cfg["speed"])

        def _do_reply_mc():
            # 中古音（默认王力体系）回答音频：与东汉/现代做三时期对照
            return "reply_mc", synthesize_ancient(
                reply, pitch=cfg["pitch"], speed=cfg["speed"],
                system_id=middle_system)

        def _do_reply_mod():
            # 现代汉语只做真 Edge TTS（断网则该段为空），绝不共振峰兜底
            return "reply_mod", tts_client.speak_natural(
                reply_modern, voice=cfg["voice"], rate=cfg["rate"])

        # 有应答时生成四段音频；无词典匹配时只生成输入翻译的古汉语音频。
        job["phase"] = "synth"
        done = {"user": (b"", None), "reply_anc": (b"", None),
                "reply_mc": (b"", None), "reply_mod": (b"", None)}
        tasks = [_do_user]
        if reply:
            tasks.append(_do_reply_anc)
            tasks.append(_do_reply_mc)
        if reply and reply_modern:
            tasks.append(_do_reply_mod)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as ex:
            futs = [ex.submit(task) for task in tasks]
            for fut in concurrent.futures.as_completed(futs):
                key, val = fut.result()
                if key in ("user", "reply_anc", "reply_mc"):
                    wav, result = val
                    done[key] = (wav, result)
                else:
                    done["reply_mod"] = (val or b"", None)
                job["phase"] = f"synth_{key}"
        (wav_u, _), (wav_r, result_r), (wav_mc, result_mc), (mp3_m, _) = (
            done["user"], done["reply_anc"], done["reply_mc"],
            done["reply_mod"])
        if reply and not wav_r:
            source = f"{source}+ancient_fallback"

        job["result"] = ("ok", {
            "user": cfg["text"],
            "translation": translation,
            "translation_source": translation_source,
            "missed_chars": missed_chars,
            "reply": reply,
            "reply_modern": reply_modern,
            "source": source,
            "mode": cfg["mode"],
            "coverage": result_r.coverage_pct if result_r and wav_r else 0.0,
            "approx": result_r.approx if result_r and wav_r else 0,
            "audios": {
                "user": {"data": wav_u, "kind": "wav", "text": user_text},
                "reply_anc": {"data": wav_r, "kind": "wav", "text": reply},
                "reply_mc": {
                    "data": wav_mc, "kind": "wav", "text": reply,
                    "system": middle_system,
                    "system_label": middle_system_label(middle_system),
                    "ipa": result_mc.ipa_text if result_mc and wav_mc else "",
                    "coverage": result_mc.coverage_pct
                    if result_mc and wav_mc else 0.0,
                    "approx": result_mc.approx if result_mc and wav_mc else 0,
                    "unknown": list(result_mc.unknown)
                    if result_mc else [],
                },
                "reply_mod": {"data": mp3_m, "kind": "mp3",
                              "text": reply_modern},
            },
            "ms": time.time(),
        })
        # 有回答时按语音模式播放回答；词典未命中时只播放输入翻译的古汉语。
        job["phase"] = "play"
        a = job["result"][1]["audios"]
        if not reply:
            main = a["user"]
        else:
            pref = a["reply_mod"] if cfg["mode"] == "natural" else a["reply_anc"]
            main = pref if pref["data"] else next(
                (x for x in (a["reply_anc"], a["reply_mod"], a["user"])
                 if x["data"]), None)
        try:
            if main and main["data"]:
                ai = get_audio_io()
                job["play_ok"], job["vol_note"] = \
                    _ensure_playable(ai, spinner=False)
                if job["play_ok"]:
                    ai.play_async(main["data"])
                    # 记录实际投递目标，供 play_note 如实描述（选了具体设备
                    # 就不该再写「默认输出设备」）
                    job["play_target"] = getattr(ai, "playback_target", None)
            else:
                job["play_ok"] = None
                job["vol_note"] = None
        except Exception as e:
            # 不再静默吞异常：把原因带到 play_note，否则用户只看到
            # "没声音"却无从排查（10/27 解包 bug 就是这样被藏的）
            job["play_ok"] = False
            job["vol_note"] = f"自动朗读出错：{e}"
        # 朗读就绪标记：fragment 以此为"整轮完成"信号落盘
        # （避免先落盘后朗读，导致 play_note 永远取不到值）
        job["play_done"] = True
    except Exception as e:
        job["result"] = ("error", str(e))
        job["play_done"] = True


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
    # 播放目标 sink（界面选择框持久化）：存**显示名**而非 serial——
    # serial 每次重启漂移，显示名稳定
    t = None
    try:
        with open(os.path.join(OUT_DIR, "playback_target.txt"),
                  encoding="utf-8") as f:
            t = f.read().strip() or None
    except Exception:
        t = None
    return AudioIO(capture_device=a.get("capture_device", "plughw:2,0"),
                   playback_device=a.get("playback_device", "plughw:2,0"),
                   sample_rate=a.get("sample_rate", 16000),
                   playback_target=t)


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


def _ensure_playable(ai, spinner=True):
    """确保播放目标可出声 → (ok: bool, vol_note: str|None)。

    两层"无声但不报错"的坑都要查（否则 pw-play rc=0、你听不见）：
      1) 音量为 0：BT 音箱常把自己面板音量同步过来（可能为 0）→
         ensure_audible 自动抬到 45% 并给提示
      2) 通道假死：默认输出是蓝牙 A2DP sink 且 probe 失败 → bt_reset.sh
         自动重连一次；非蓝牙默认只探测、绝不触发蓝牙重连（重连会把
         默认抢回耳机）
    vol_note 非空 = 本次播放前动过/发现音量问题，供 play_note 展示。
    spinner=False 用于自动朗读路径（避免每次生成都闪转圈）。
    """
    vol_note = ensure_audible(ai.playback_name, ai.playback_target)
    s = bt_status(BT_MAC)
    if not s["is_default"]:
        # 默认输出不是蓝牙（用户切到 USB/内置等，或蓝牙未连）：
        # 只探测默认通道，绝不触发蓝牙重连
        return (bool(ai.probe()), vol_note)
    if ai.probe():
        return (True, vol_note)
    # 蓝牙是默认输出但探测失败（A2DP 假连接/挂死）→ 自动重连一次
    _bt_reset = os.path.join(ROOT, "robot", "bt_reset.sh")
    if spinner:
        with st.spinner("蓝牙通道异常，正在自动重连…"):
            subprocess.run(["bash", _bt_reset], cwd=ROOT,
                           capture_output=True, timeout=120)
    else:
        subprocess.run(["bash", _bt_reset], cwd=ROOT,
                       capture_output=True, timeout=120)
    return (_bt_healthy() and bool(ai.probe()), vol_note)


# ---------- 页面（简约素雅版） ----------
st.set_page_config(page_title="古韵机器人 · 东汉洛阳官音",
                   page_icon="🏛️", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;900&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
    :root { --paper:#f5f2ea; --card:#fffefb; --line:#e4dccb; --ink:#26221a; --ink2:#5c5546; --ink3:#9a917e; --seal:#a63d2a; }
    html, body, [class*="css"] { font-family:'Noto Sans SC','PingFang SC',sans-serif; }
    /* 底色为宣纸时必须显式给文字上墨色：一旦 Streamlit 跟随系统切到深色主题，
       它会往 .stApp 注入近白色的字色，浅字压浅底 = 标签全看不清。 */
    .stApp { background:var(--paper); color:var(--ink); }
    .block-container { max-width:1060px; padding-top:2.4rem; padding-bottom:3rem; }

    .gi-title { font-family:'Noto Serif SC',serif; font-weight:900; font-size:2.1rem; color:var(--ink); letter-spacing:0.35em; }
    .gi-title::before { content:''; display:inline-block; width:0.55rem; height:0.55rem; background:var(--seal); margin-right:0.7rem; }
    .gi-sub { color:var(--ink3); font-size:0.85rem; letter-spacing:0.25em; margin:0.3rem 0 2.2rem 0; }

    .gi-h { font-size:0.78rem; color:var(--ink2); letter-spacing:0.22em; margin:1.4rem 0 0.55rem 0; font-weight:500; }
    .gi-gap { height:1.1rem; }

    /* ============ 根治整页变暗 ============
       Streamlit 在任何整页 rerun 时会把全部元素标记 data-stale=true，
       内联 style 打上 opacity:0.33 + transition:1s（1.66 前端
       styled-components 里 {opacity:a.stale}，stale=0.33）。
       无论 rerun 多快，用户都会看到"整页缓缓变暗再恢复"。
       该样式不只落在容器上，按钮/expander/tabs 自身也会各自内联
       同一对象（opacity 沿 DOM 链相乘）→ 容器和后代都要覆盖。
       !important 压过内联样式，彻底禁用；等待感改由下方
        .gi-loading 加载面板表达（进度条+跳动秒数，页面保持全亮）。*/
    [data-stale="true"], [data-stale="true"] * { opacity:1 !important; }
    .gi-meta { font-size:0.78rem; color:var(--ink3); letter-spacing:0.1em; margin-bottom:0.6rem; }
    .gi-status { display:flex; align-items:center; gap:0.6rem; font-size:0.95rem; color:var(--ink2); padding:0.9rem 0.4rem 0.3rem; }
    .gi-status::before { content:""; width:0.9rem; height:0.9rem; border:2px solid var(--line); border-top-color:var(--ink); border-radius:50%; animation:gi-spin 0.9s linear infinite; flex:none; }
    @keyframes gi-spin { to { transform:rotate(360deg); } }

    /* 生成加载面板：进度条+阶段+跳动秒数——秒数在走就不像卡死。
       生成期间页面其余部分冻结（Streamlit 全量 rerun 阻塞），
       这个面板必须自己"活"起来，否则观感=整个程序卡住 */
    .gi-loading { margin:1.4rem 0 0.6rem; padding:1.4rem 1.5rem 1.5rem;
        background:var(--card); border:1px solid var(--line); border-radius:14px; }
    .gi-loading-head { display:flex; align-items:center; gap:0.7rem; margin-bottom:1.1rem; }
    .gi-loading-echo { font-family:'Noto Serif SC',serif; font-size:1rem; color:var(--ink);
        letter-spacing:0.06em; line-height:1.7; padding-left:0.75rem;
        border-left:2px solid var(--seal); }
    .gi-loading-body { display:flex; align-items:center; gap:1rem; }
    .gi-loading-seal { width:2.6rem; height:2.6rem; flex:none; border-radius:8px;
        background:var(--seal); color:#fff; display:flex; align-items:center;
        justify-content:center; font-family:'Noto Serif SC',serif; font-size:1.5rem;
        font-weight:600; box-shadow:0 2px 10px rgba(166,61,42,.35);
        animation:gi-seal-pulse 1.8s ease-in-out infinite; }
    @keyframes gi-seal-pulse { 0%,100% { transform:scale(1); box-shadow:0 2px 10px rgba(166,61,42,.35); }
        50% { transform:scale(1.06); box-shadow:0 4px 18px rgba(166,61,42,.5); } }
    .gi-loading-text { flex:1; }
    .gi-loading-phase { font-family:'Noto Serif SC',serif; font-size:1.06rem;
        color:var(--ink); letter-spacing:0.1em; display:flex; align-items:center; gap:0.6rem; }
    .gi-dot { display:inline-flex; gap:0.22rem; align-items:center; }
    .gi-dot i { width:0.34rem; height:0.34rem; border-radius:50%; background:var(--seal);
        display:inline-block; animation:gi-breathe 1.2s ease-in-out infinite; }
    .gi-dot i:nth-child(2) { animation-delay:0.2s; }
    .gi-dot i:nth-child(3) { animation-delay:0.4s; }
    @keyframes gi-breathe { 0%,100% { opacity:0.25; transform:scale(0.8); }
        50% { opacity:1; transform:scale(1.15); } }
    .gi-loading-sub { font-size:0.78rem; color:var(--ink3); letter-spacing:0.14em; margin-top:0.35rem; }
    .gi-loading-sec { flex:none; font-family:ui-monospace,Menlo,monospace; font-size:1.5rem;
        color:var(--seal); font-weight:600; min-width:3.2rem; text-align:right; }
    .gi-loading-sec small { font-size:0.7rem; color:var(--ink3); font-weight:400; margin-left:0.2rem; }

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

st.markdown('<div class="gi-title">古韵</div>', unsafe_allow_html=True)
st.markdown('<div class="gi-sub">东汉 · 洛阳官音 · 文言对谈</div>', unsafe_allow_html=True)

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

# 首次进入时使用合理默认值并保存；之后始终读取本机上次选择。
_preferences = _load_robot_preferences()
if "llm_mode" not in st.session_state:
    _stored_mode = _preferences.get("llm_mode")
    if _stored_mode not in LLM_MODE_LABELS:
        _stored_mode = "api" if (os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")) else "dictionary"
        _preferences["llm_mode"] = _stored_mode
        _save_robot_preferences(_preferences)
    st.session_state["llm_mode"] = _stored_mode

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
    # 录音识别结果在组件回调里落进 _pending_input，这里换成新输入框落地
    if st.session_state.get("_pending_input"):
        _pend = st.session_state.pop("_pending_input")
        print(f"[rec] 回填输入框: {_pend!r}", flush=True)
        _set_input(_pend)

    st.markdown('<div class="gi-h">对话模式</div>', unsafe_allow_html=True)
    st.radio(
        "对话模式",
        options=["api", "dictionary"],
        format_func=lambda value: LLM_MODE_LABELS[value],
        key="llm_mode",
        on_change=_persist_llm_mode,
        help="大模型 API：使用你配置的密钥获取高质量回答。\n本地词典：不调用大模型；词典无匹配时只播放输入的古汉语翻译。",
        label_visibility="collapsed",
    )
    _llm_now = _current_llm_settings()

    if "allow_llm_translate" not in st.session_state:
        st.session_state["allow_llm_translate"] = bool(_llm_now["key"])
    st.checkbox(
        "词典未命中时允许 LLM 辅助翻译",
        key="allow_llm_translate",
        help="只在「本地词典」模式下生效：词典没有覆盖的字时，用大模型补「翻译」"
             "一层（界面标注 翻译来源=LLM）。回答永远不靠 LLM 编造：未命中仍不回答。",
    )
    if (st.session_state.get("llm_mode") == "dictionary"
            and st.session_state.get("allow_llm_translate")
            and not _llm_now["key"]):
        st.caption("提示：未配置密钥时 LLM 辅助翻译不可用，仍只使用本地词典。")

    def _save_api_settings():
        """button callback：改 .env 与 os.environ。

        两句都不能省：
        1) 必须在回调里写 session_state["api_key_input"]——在主脚本里写会撞上
           「widget 已实例化，不能再改它的状态」，异常一抛 st.rerun() 就不执行，
           页面会一直显示保存前的状态（文件其实已经写好了）。
        2) 必须在回调里从 session_state 读值，不能靠 on_click 的 args：
           用户打完字直接点按钮时，args 还是上一次渲染的旧值（实测把密钥吞了）。
        """
        base = st.session_state.get("api_base_input", "")
        model = st.session_state.get("api_model_input", "")
        key = st.session_state.get("api_key_input", "")
        updates = {"LLM_BASE_URL": (base or "").strip() or _DEFAULT_BASE,
                   "LLM_MODEL": (model or "").strip() or _DEFAULT_MODEL}
        if (key or "").strip():
            updates["LLM_API_KEY"] = key.strip()
        try:
            _write_env_values(updates)
            st.session_state["_api_notice"] = ("ok", "已写入 .env，立即生效。")
            st.session_state["api_key_input"] = ""
        except Exception as exc:
            st.session_state["_api_notice"] = ("err", f"保存失败：{exc}")

    def _clear_api_key():
        try:
            _write_env_values({"LLM_API_KEY": ""})
            st.session_state["_api_notice"] = ("ok", "已清除密钥，会自动退回本地词典。")
        except Exception as exc:
            st.session_state["_api_notice"] = ("err", f"清除失败：{exc}")

    _notice = st.session_state.pop("_api_notice", None)
    if _notice:
        (st.success if _notice[0] == "ok" else st.error)(_notice[1])
    if st.session_state["llm_mode"] == "api" and not _llm_now["key"]:
        st.warning("当前选择了大模型 API，但还没有密钥。在下面「大模型 API 设置」里填写即可，"
                   "不用改文件；未配置时暂时使用本地词典。")
    with st.expander("大模型 API 设置", expanded=(
        st.session_state["llm_mode"] == "api" and not _llm_now["key"]
    )):
        st.caption(f"当前：{_mask_key(_llm_now['key'])}｜{_llm_now['model']}｜{_llm_now['base']}")
        _base_in = st.text_input("接口地址", value=_llm_now["base"],
                                 key="api_base_input",
                                 help="OpenAI 兼容的 /v1 地址，例如 https://api.deepseek.com/v1")
        _model_in = st.text_input("模型名", value=_llm_now["model"],
                                  key="api_model_input",
                                  help="例如 deepseek-chat、gpt-4o-mini、qwen-plus")
        _key_in = st.text_input("密钥", value="", type="password",
                                key="api_key_input",
                                placeholder="粘贴你的 API Key（留空 = 不修改当前密钥）",
                                help="只写进本机 .env，不会提交到 Git")
        _c1, _c2 = st.columns(2)
        _c1.button("保存", use_container_width=True, key="api_save_btn",
                   on_click=_save_api_settings,
                   help="写入 .env 并立即生效")
        _c2.button("清除密钥", use_container_width=True, key="api_clear_btn",
                   on_click=_clear_api_key)
    st.markdown('<div class="gi-h">输入</div>', unsafe_allow_html=True)
    st.text_area("输入", placeholder="说点什么，白话或文言都可以…",
                 height=120, key=_input_key(), label_visibility="collapsed")

    # 按住说话：浏览器采音（PCM）→ 松手 → 本地 Vosk 识别 → 回填输入框。
    # 服务端 arecord 只能录固定时长，且要服务器上有麦克风；改成浏览器录音后
    # 固定 5 秒的限制没有了，也不依赖服务器音频输入设备。
    _rec_value = hold_to_record()
    if (isinstance(_rec_value, dict) and _rec_value.get("nonce")
            and _rec_value.get("nonce") != st.session_state.get("_rec_nonce")):
        st.session_state["_rec_nonce"] = _rec_value.get("nonce")
        print(f"[rec] 收到录音 nonce={_rec_value.get('nonce')} "
              f"bytes={len(_rec_value.get('wav') or '')} "
              f"ms={_rec_value.get('duration_ms')}", flush=True)
        _engines_now = asr_available_backends()
        if not _engines_now:
            st.session_state["_rec_status"] = (
                "err", "本地语音识别模型未安装（models/sense-voice/），语音输入不可用。")
        else:
            _text = ""
            _level = ""
            _secs = 0.0
            try:
                _path, _secs = decode_wav(
                    _rec_value, os.path.join(OUT_DIR, "ui_rec.wav")
                )
                _peak, _rms = _wav_levels(_path)
                _level = (f"峰值 {_peak:.0f} dBFS / 均方根 {_rms:.0f} dBFS")
                _text = get_asr().transcribe_wav(_path)
            except Exception as exc:
                st.session_state["_rec_status"] = ("err", f"识别失败：{exc}")
                _text = None
            print(f"[rec] 时长 {_secs:.1f}s {_level} 识别={_text!r}", flush=True)
            if _text is None:
                pass
            elif _text:
                st.session_state["_rec_status"] = (
                    "ok", f"已录 {_secs:.1f} 秒（{_level}）· 识别：{_text}")
                st.session_state["_pending_input"] = _text
                st.rerun()
            elif _peak < -45:
                st.session_state["_rec_status"] = (
                    "err",
                    f"录到 {_secs:.1f} 秒，但几乎没有声音（{_level}）。"
                    "检查 Windows「声音设置」里的默认输入设备，以及 Chrome 的麦克风权限。")
            else:
                st.session_state["_rec_status"] = (
                    "warn",
                    f"已录 {_secs:.1f} 秒（{_level}），但没识别出字词。"
                    "靠近麦克风、说得慢一点再试；小模型对生僻词本来就弱。")
    _rec_status = st.session_state.get("_rec_status")
    if _rec_status:
        {"ok": st.success, "warn": st.warning, "err": st.error}.get(
            _rec_status[0], st.info)(_rec_status[1])
    # 只做目录探测，不加载模型（加载要 1 秒多，别拖慢首屏）
    _engines = asr_available_backends()
    st.caption("识别引擎：" + (
        asr_backend_label(_engines[0]) if _engines else "未安装模型（models/ 下缺 sense-voice）"))

    st.markdown('<div class="gi-h">播放设备</div>', unsafe_allow_html=True)
    # 列出当前系统可用的输出设备；"自动"=跟随系统默认输出。
    # Linux 使用 PipeWire 定向，Windows 使用 sounddevice/PortAudio 设备索引。
    # 持久化存显示名，避免设备索引随重启变化。
    _sinks = [(s[1], s[0], s[2]) for s in _list_pw_sinks()]
    _opts = ["自动（跟随系统默认输出）"] + [s[0] for s in _sinks]
    try:
        with open(os.path.join(OUT_DIR, "playback_target.txt"),
                  encoding="utf-8") as f:
            _persist = f.read().strip()
    except Exception:
        _persist = ""
    _init_idx = _opts.index(_persist) if _persist in _opts else 0
    _p = st.selectbox("输出到", _opts, index=_init_idx, key="robot_play_dev",
                      help="自动：系统默认输出是什么就发到哪。\n"
                           "选具体设备：固定发到它，不随系统默认变。\n"
                           "（仅改机器人的定向播放，不动系统默认输出）")
    _desired = None if _p == _opts[0] else _p
    _ai = get_audio_io()
    if _ai.playback_target != _desired:
        _ai.playback_target = _desired          # 立即对后续播放生效
        try:                                    # 持久化（None=清空）
            with open(os.path.join(OUT_DIR, "playback_target.txt"),
                      "w", encoding="utf-8") as f:
                f.write(_desired or "")
        except Exception:
            pass

    st.markdown('<div class="gi-h">语音模式</div>', unsafe_allow_html=True)
    st.radio("模式", ["自然语音", "东汉古韵"],
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
            st.caption("语速与基频仅东汉古韵模式生效。")

    def _generate():
        """登记后台任务并立即返回（LLM+TTS 在后台线程跑，
        轮询 fragment 跟进进度）→ 生成期间整页不再变暗、控件可用"""
        text = (st.session_state.get(_input_key()) or "").strip()
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
            "mode_label": "自然语音" if mode == "natural" else "东汉古韵",
            "llm_mode": ss.get("llm_mode", "dictionary"),
            "allow_llm_translate": bool(ss.get("allow_llm_translate", False)),
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
        ss.pop("_rec_status", None)   # 已经拿去生成了，录音状态行就没意义了
        _set_input("")     # 换成空的新输入框（同 _set_input 的理由）
        job = {"phase": "start", "result": None, "play_ok": None,
               "user": text, "started": time.time()}
        ss.gen_job = job
        threading.Thread(target=_gen_worker,
                         args=(job, session, cfg),
                         daemon=True).start()

    st.markdown('<div class="gi-gap"></div>', unsafe_allow_html=True)
    st.button("生成并朗读", type="primary", use_container_width=True,
              on_click=_generate,
              help="按所选对话模式生成翻译/应答，再合成并自动朗读")

    with st.expander("关于本项目"):
        st.markdown(f"""- 对话模式：大模型 API / 本地词典（可在左侧切换并记住上次选择）
- 无 API 或 API 不可用时：只使用词典预设应答；未匹配则只朗读输入的古汉语翻译
- 东汉古韵库：{len(EASTERN_HAN_DB)} 字（郑张尚芳体系，洛阳官音重建）
- 自然语音：Edge TTS（需网络，失败时可回退古韵合成）
- 音频设备：Linux 使用 PipeWire/ALSA，Windows 使用系统音频设备
- 多轮对话：保留最近 {session.max_turns} 轮有效回答上下文""")

# ================= 右栏：结果 =================
with col2:
    if st.session_state.get("gen_error"):
        st.error(st.session_state.gen_error)
        st.session_state.gen_error = None

    # 后台生成状态区（独立 fragment 轮询，只刷新这一小块）
    _PHASE_LABEL = {
        "start": "正在构思…",
        "qwen": "翻译与生成应答…",
        "synth": "合成语音…",
        "synth_user": "合成语音中 · 我的话…",
        "synth_reply_anc": "合成语音中 · 古韵回答…",
        "synth_reply_mc": "合成语音中 · 中古回答…",
        "synth_reply_mod": "合成语音中 · 现代回答…",
        "play": "准备朗读…",
    }

    @st.fragment(run_every=1)
    def _gen_status():
        job = st.session_state.get("gen_job")
        # 完成信号是 play_done（合成+朗读就绪），不是 result——
        # 若只认 result，会在自动朗读还在跑时就落盘，play_note 取不到值
        if not job or not job.get("play_done"):
            if job:
                import html as _html
                label = _PHASE_LABEL.get(job["phase"], "生成中…")
                user = _html.escape((job.get("user") or "").strip())
                # 秒数计时：worker 写入 started，片段每秒刷新 → 数字在走
                t0 = job.get("started") or time.time()
                secs = max(0, int(time.time() - t0))
                # 阶段 → 进度：构思→合成→朗读，给个可见的推进感
                _PROGRESS = {"start": 0.06, "qwen": 0.30, "synth": 0.55,
                             "synth_user": 0.66, "synth_reply_anc": 0.80,
                             "synth_reply_mc": 0.88,
                             "synth_reply_mod": 0.92, "play": 0.97}
                pct = int(_PROGRESS.get(job["phase"], 0.05) * 100)
                echo_html = (f'<div class="gi-loading-echo">{user}</div>'
                             if user else "")
                st.markdown(
                    f'<div class="gi-loading">{echo_html}'
                    f'<div class="gi-loading-body">'
                    f'<div class="gi-loading-seal">韵</div>'
                    f'<div class="gi-loading-text">'
                    f'<div class="gi-loading-phase">{label}'
                    f'<span class="gi-dot"><i></i><i></i><i></i></span></div>'
                    f'<div class="gi-loading-sub">构思 → 合成 → 朗读，请勿关闭本页</div>'
                    f'</div>'
                    f'<div class="gi-loading-sec">{secs}<small>秒</small></div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True)
                st.progress(pct / 100, text=f"{label}（{secs} 秒）")
            return
        kind, payload = job["result"]
        ss = st.session_state
        ss.gen_job = None
        if kind == "error":
            ss.gen_error = payload
            return
        # 无应答的词典未命中轮次不进入 LLM 上下文。
        if payload["reply"]:
            session.add(payload["user"], payload["reply"])
        ss.last_result = payload
        display_reply = payload["reply"] or "（本地词典未匹配，未生成回答）"
        ss.turns.append((payload["user"], display_reply,
                         "自然语音" if payload["mode"] == "natural" else "东汉古韵"))
        ss.turns = ss.turns[-session.max_turns:]
        vol = job.get("vol_note")
        if job.get("play_ok") is True:
            dest = job.get("play_target")
            where = f"「{dest}」" if dest else "默认输出设备"
            core = "已朗读输入的古汉语翻译到" if not payload["reply"] else "已朗读到"
            ss.play_note = core + where + (f"（{vol}）" if vol else "")
        elif job.get("play_ok") is False:
            ss.play_note = "已生成（自动朗读失败，可点「设备播放」重试）"
        st.rerun(scope="app")

    _gen_status()

    res = st.session_state.last_result
    # 生成中不显示空状态（加载面板已占据此区，"说句话试试"会误导）
    if not res and not st.session_state.get("gen_job"):
        st.markdown('<div class="gi-empty">说一句话试试。<br>机器人以文言应答，并按所选模式朗读。</div>',
                    unsafe_allow_html=True)
    elif res:
        # 元信息（一行，替代徽章堆）
        src = res["source"]
        src_name = {
            "local-qwen": "本地 Qwen",
            "local-model": "模型服务",
            "cloud": "云端大模型",
            "local-rules": "本地规则",
            "local-dictionary": "本地词典",
            "local-dictionary-miss": "词典未匹配",
            "fallback": "兜底",
        }.get(src.split("+")[0], src)
        if "ancient_fallback" in src:
            src_name += " · 古韵兜底"
        meta = f'模式 {res["mode"] if res["mode"] == "natural" else "东汉古韵"} · 来源 {src_name}'
        if res["mode"] == "ancient":
            meta += f' · 古韵覆盖 {res["coverage"]}%'
        if res.get("translation_source") == "llm":
            meta += " · 翻译 LLM"
        st.markdown(f'<div class="gi-meta">{meta}</div>', unsafe_allow_html=True)

        if res["translation"]:
            _trans_note = ""
            if res.get("translation_source") == "llm":
                _missed = res.get("missed_chars") or []
                if _missed:
                    _shown = "、".join(_missed[:8]) + ("…" if len(_missed) > 8 else "")
                    _trans_note = f'（LLM 补译 · 词典缺 {len(_missed)} 字：{_shown}）'
                else:
                    _trans_note = "（LLM 补译）"
            st.markdown(f'<div class="gi-muteline">我的话 · 古汉语：{res["translation"]}{_trans_note}</div>',
                        unsafe_allow_html=True)
        if res.get("reply"):
            st.markdown(f'<div class="gi-classical">{res["reply"]}</div>',
                        unsafe_allow_html=True)
        elif res.get("source") == "local-dictionary-miss":
            st.info("本地词典没有匹配到应答。本轮不生成回答，只播放输入内容的古汉语翻译。")
        if res.get("reply_modern") and res["reply_modern"] != res["reply"]:
            st.markdown(f'<div class="gi-muteline">白话：{res["reply_modern"]}</div>',
                        unsafe_allow_html=True)

        # 三段音频（每次生成都产出：我的话·古韵 / 回答·古韵 / 回答·现代）
        st.markdown('<div class="gi-h">语音</div>', unsafe_allow_html=True)
        if st.session_state.get("play_note"):
            st.caption(st.session_state.play_note)
        audios = res.get("audios") or {}
        if not res.get("reply"):
            _CARD_ORDER = [("user", "输入翻译 · 古汉语")]
        else:
            _CARD_ORDER = [
                ("user", "我的话 · 东汉古韵"),
                ("reply_anc", "回答 · 东汉古韵"),
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
                    ok, vol = _ensure_playable(ai)
                    if ok:
                        ai.play_async(item["data"])
                        st.session_state.play_note = \
                            f"已发送到默认输出设备（{label}）" + \
                            (f"（{vol}）" if vol else "")
                    else:
                        st.error("播放通道异常：自动重连后仍无法播放，请检查设备电源/距离")
            with cb2:
                fname = f"guyun_{key}_{int(res['ms'])}.{item['kind']}"
                st.download_button("下载", item["data"], file_name=fname,
                                   mime=fmt, use_container_width=True,
                                   key=f"dl_{key}")

        # 三时期对照：同一回答三版音频（东汉 / 中古 / 现代），各自独立合成
        st.markdown('<div class="gi-h">三时期对照 · 同一回答</div>',
                    unsafe_allow_html=True)
        if not res.get("reply"):
            st.caption("本轮没有应答（词典未命中）——不生成对照；"
                       "输入翻译的东汉古韵见上方「语音」。")
        else:
            _mc_item = audios.get("reply_mc") or {}
            _era_cols = st.columns(3, gap="small")
            _r_anc = text_to_ipa(res["reply"])   # 仅查表，与 worker 同源
            _era_specs = (
                (_era_cols[0], "reply_anc", "东汉（洛阳官音拟音）",
                 _r_anc.ipa_text, _r_anc.coverage_pct,
                 list(_r_anc.unknown),
                 "合成失败（无有效汉字？）"),
                (_era_cols[1], "reply_mc",
                 f"中古（{_mc_item.get('system_label') or '王力系统'}）",
                 _mc_item.get("ipa", ""), _mc_item.get("coverage", 0.0),
                 _mc_item.get("unknown") or [],
                 "合成失败（无有效汉字？）"),
                (_era_cols[2], "reply_mod", "现代汉语",
                 None, None, None,
                 "网络不可用，未生成（现代汉语不做本地兜底合成）"),
            )
            for _col, _era_key, _era_title, _ipa, _cov, _unk, _off in \
                    _era_specs:
                with _col:
                    _item = audios.get(_era_key) or {}
                    _data = _item.get("data") or b""
                    st.caption(_era_title)
                    if not _data:
                        st.caption(_off)
                        continue
                    _fmt = "audio/wav" if _item.get("kind") == "wav" \
                        else "audio/mpeg"
                    st.audio(_data, format=_fmt)
                    if _ipa is not None:
                        _line = f"IPA：{_ipa} · 覆盖 {_cov}%"
                        if _unk:
                            _line += " · 缺字：" + " ".join(_unk)
                        st.caption(_line)
                    elif _era_key == "reply_mod":
                        st.caption("（以白话文本朗读）")
                    st.download_button(
                        "下载", _data,
                        file_name=(f"guyun_era_{_era_key}_"
                                   f"{int(res['ms'])}.{_item.get('kind', 'wav')}"),
                        mime=_fmt, use_container_width=True,
                        key=f"dl_era_{_era_key}")

        # 东汉 IPA（古韵模式）
        if res["mode"] == "ancient" and res.get("reply"):
            r = text_to_ipa(res["reply"])
            st.markdown('<div class="gi-h">东汉洛阳音 IPA</div>',
                        unsafe_allow_html=True)
            st.markdown(f'<div class="gi-ipa">{r.ipa_text}</div>',
                        unsafe_allow_html=True)

        # 逐字音韵分析（古韵模式，收进折叠面板）
        if res["mode"] == "ancient" and res.get("reply"):
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
