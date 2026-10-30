"""
guyun_app.py
古韵 - 东汉洛阳官音合成器
白话到古文到IPA标注到三轨音频
"""

import streamlit as st
import sys, os, asyncio, tempfile, json, re
import numpy as np
from io import BytesIO
import base64

# PyInstaller 打包环境下的路径修正
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from phonology_db import EASTERN_HAN_DB, lookup_char
from classical_translator import simple_translate
from sound_synth import synthesize_text, audio_to_wav_bytes, audio_to_base64, SAMPLE_RATE, ESPEAK_AVAILABLE

try: from pypinyin import pinyin as _pypinyin, Style; PYPINYIN_AVAILABLE = True
except: PYPINYIN_AVAILABLE = False

def get_pinyin_fallback(char):
    if not PYPINYIN_AVAILABLE: return None
    try: return re.sub(r'[0-9]', '', _pypinyin(char, style=Style.TONE3)[0][0])
    except: return None

def estimate_ipa_from_pinyin(py):
    if not py: return None
    init_map = {'b': 'p', 'p': 'pʰ', 'm': 'm', 'f': 'f', 'd': 't', 't': 'tʰ', 'n': 'n', 'l': 'l', 'g': 'k', 'k': 'kʰ', 'h': 'h', 'j': 'tɕ', 'q': 'tɕʰ', 'x': 'ɕ', 'zh': 'tʂ', 'ch': 'tʂʰ', 'sh': 'ʂ', 'r': 'ȵ', 'z': 'ts', 'c': 'tsʰ', 's': 's', 'y': 'j', 'w': 'ʔ'}
    final_map = {'iang': 'iaŋ', 'uang': 'uaŋ', 'iong': 'yuŋ', 'uai': 'uai', 'ang': 'ɑŋ', 'eng': 'əŋ', 'ing': 'iŋ', 'ong': 'uŋ', 'ian': 'ian', 'uan': 'uan', 'iao': 'iau', 'iou': 'iou', 'ai': 'ai', 'ei': 'ei', 'ui': 'uei', 'ao': 'au', 'ou': 'ou', 'iu': 'iou', 'an': 'an', 'en': 'ən', 'in': 'in', 'un': 'uən', 'vn': 'yn', 'ia': 'ia', 'ie': 'ie', 'ua': 'ua', 'uo': 'uo', 've': 'ye', 'van': 'yan', 'ue': 'ye', 'a': 'a', 'o': 'o', 'e': 'ə', 'i': 'i', 'u': 'u', 'v': 'y'}
    init_list, init_ipa, rest = ['zh','ch','sh','b','p','m','f','d','t','n','l','g','k','h','j','q','x','r','z','c','s','y','w'], '', py
    for init in init_list:
        if py.startswith(init): init_ipa = init_map.get(init, ''); rest = py[len(init):]; break
    final_ipa = rest
    for f_len in range(5, 0, -1):
        if len(rest) >= f_len and rest[:f_len] in final_map: final_ipa = final_map[rest[:f_len]]; break
    if rest in final_map: final_ipa = final_map[rest]
    return f"{init_ipa}{final_ipa}" if (init_ipa or final_ipa) else None

def pinyin_analyze_diffs(char):
    return [("拼音回退", "该字未收录东汉音数据库，暂以现代拼音近似")]

try:
    from Qieyun import 字頭2音韻地位_出處們
    QIEYUN_AVAILABLE, QIEYUN_ERROR = True, None
except Exception as _qieyun_exc:  # 缺包或 numpy/networkx 版本冲突（np.float_ 已于 numpy 2.0 移除）
    QIEYUN_AVAILABLE, QIEYUN_ERROR = False, f"{type(_qieyun_exc).__name__}: {_qieyun_exc}"
    print(f"[guyun_app] 切韵对照不可用 -> {QIEYUN_ERROR}", file=sys.stderr)

try:
    import edge_tts
    EDGE_TTS_AVAILABLE, EDGE_TTS_ERROR = True, None
except Exception as _tts_exc:
    EDGE_TTS_AVAILABLE, EDGE_TTS_ERROR = False, f"{type(_tts_exc).__name__}: {_tts_exc}"
    print(f"[guyun_app] 现代朗读（Edge-TTS）不可用 -> {EDGE_TTS_ERROR}", file=sys.stderr)

PINYIN_MAP = {
    "天":"tian","地":"di","人":"ren","日":"ri","月":"yue","风":"feng","云":"yun","雨":"yu",
    "山":"shan","水":"shui","火":"huo","木":"mu","金":"jin","石":"shi","花":"hua","草":"cao",
    "河":"he","海":"hai","星":"xing","雪":"xue","春":"chun","夏":"xia","秋":"qiu","冬":"dong",
    "东":"dong","南":"nan","西":"xi","北":"bei","中":"zhong","前":"qian","后":"hou",
    "上":"shang","下":"xia","左":"zuo","右":"you","大":"da","小":"xiao","多":"duo","少":"shao",
    "一":"yi","二":"er","三":"san","四":"si","五":"wu","六":"liu","七":"qi","八":"ba","九":"jiu","十":"shi",
    "父":"fu","母":"mu","子":"zi","女":"nv","夫":"fu","君":"jun","臣":"chen","民":"min",
    "不":"bu","之":"zhi","者":"zhe","也":"ye","乎":"hu","兮":"xi","哉":"zai","矣":"yi",
    "心":"xin","身":"shen","手":"shou","目":"mu","口":"kou","耳":"er","头":"tou","面":"mian",
    "行":"xing","走":"zou","坐":"zuo","立":"li","视":"shi","听":"ting","言":"yan","食":"shi",
    "明":"ming","清":"qing","白":"bai","黄":"huang","青":"qing",
    "道":"dao","德":"de","仁":"ren","义":"yi","礼":"li","智":"zhi","信":"xin","名":"ming",
    "爱":"ai","情":"qing","意":"yi","故":"gu","新":"xin","旧":"jiu",
    "飞":"fei","鸣":"ming","流":"liu","光":"guang",
    "龙":"long","凤":"feng","马":"ma","牛":"niu","羊":"yang","鱼":"yu","鸟":"niao","虎":"hu",
    "今":"jin","古":"gu","时":"shi","年":"nian","岁":"sui",
    "气":"qi","真":"zhen","善":"shan","笑":"xiao","歌":"ge","酒":"jiu",
    "余":"yu","吾":"wu","汝":"ru","尔":"er","其":"qi","何":"he","谁":"shui",
    "乃":"nai","则":"ze","既":"ji","已":"yi","或":"huo","皆":"jie","相":"xiang","自":"zi","因":"yin",
    "而":"er","所":"suo","能":"neng","当":"dang","犹":"you","可":"ke","非":"fei","莫":"mo",
    "为":"wei","在":"zai","有":"you","无":"wu","来":"lai","去":"qu","出":"chu","入":"ru","归":"gui",
}

def get_pinyin(char): return PINYIN_MAP.get(char, "?")

def analyze_diffs(char_data):
    diffs = []
    old = char_data["ipa"]; init_ipa = char_data.get("init_ipa", ""); tone = char_data.get("tone", "")
    if "m" in old:
        ending = old.rstrip(chr(0x0294) + chr(0x02B0))[-1:]
        if ending == "m": diffs.append(("闭唇 -m", "东汉保留闭唇鼻音 -m，现代已变为 -n"))
    if tone == "入声": diffs.append(("入声塞尾", "东汉短促收音，现代已消失"))
    if init_ipa in ("b","d","g","dz","d"+chr(0x02D1),"d"+chr(0x0292),chr(0x0266)):
        diffs.append(("全浊声母", "东汉读浊音，现代已清化"))
    if "ŋ" in init_ipa: diffs.append(("疑母 ng-", "东汉保留舌根鼻音，现代脱落"))
    if "ȵ" in init_ipa: diffs.append(("日母 ny-", "东汉读舌面鼻音，现代变为 r-"))
    return diffs

def generate_edge_tts(text):
    if not EDGE_TTS_AVAILABLE: return None
    try:
        import concurrent.futures
        tts = edge_tts.Communicate(text, "zh-CN-YunxiNeural")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3"); tmp.close()
        def _run(): return asyncio.run(tts.save(tmp.name))
        with concurrent.futures.ThreadPoolExecutor() as ex: ex.submit(_run).result(timeout=10)
        with open(tmp.name, "rb") as f: data = f.read()
        os.unlink(tmp.name)
        return base64.b64encode(data).decode("ascii")
    except: return None

@st.cache_data(show_spinner=False)
def query_qieyun(char):
    if not QIEYUN_AVAILABLE: return None
    try:
        result = 字頭2音韻地位_出處們(char)
        if result:
            entry = result[0]
            if hasattr(entry, "__iter__") and len(entry) == 2: pos, _ = entry; return str(pos)
            return str(entry)
    except: pass
    return None

def process_input_scholar(classical, system_id, pitch=130):
    """v5 第三阶段③：用所选学者体系逐字拟音并合成。

    与旧路径的区别：
    - 缺字计 unknown，**不补现代拼音**（不伪造该体系读音）；
    - 每个字给出「重建状态（数据侧）」与「合成能力（引擎侧）」两列，
      缺的音段逐字显式报出，不静默缩短音节。
    """
    from language.ancient_tts import text_to_ipa
    from language.phoneme_capability import assess_ipa, ESPEAK_LEVEL_ZH
    from language.history import get_system
    result = text_to_ipa(classical, system_id=system_id)
    valid_ipa = result.ipa_text
    audio_dh, audio_mec = None, None
    if valid_ipa.strip():
        try:
            audio = synthesize_text(valid_ipa, pitch=pitch)
            if audio is not None and len(audio) > 0 and np.max(np.abs(audio)) > 0.001:
                audio_dh = audio_to_base64(audio)
        except: pass
        try:
            audio_m = synthesize_text(valid_ipa, pitch=max(100, pitch - 30))
            if audio_m is not None and len(audio_m) > 0 and np.max(np.abs(audio_m)) > 0.001:
                audio_mec = audio_to_base64(audio_m)
        except: pass
    mod = generate_edge_tts(classical)
    if not mod:
        try:
            from gtts import gTTS
            tts = gTTS(classical, lang="zh-CN", slow=False)
            buf = BytesIO(); tts.write_to_fp(buf); buf.seek(0)
            mod = base64.b64encode(buf.read()).decode("ascii")
        except: pass
    level_counts = {"full": 0, "approx": 0, "partial": 0, "untested": 0, "silent": 0}
    rows = []
    for ch, ipa, tag in result.characters:
        if tag == "unknown":
            rows.append({"char": ch, "ipa": None,
                         "status": "缺字（不补拼音）", "cap": "—"})
            continue
        a = assess_ipa(ipa)
        level_counts[a.espeak_level] = level_counts.get(a.espeak_level, 0) + 1
        cap = ESPEAK_LEVEL_ZH.get(a.espeak_level, a.espeak_level)
        if a.dropped_tokens:
            cap += "（丢 " + " ".join(sorted(set(a.dropped_tokens))) + "）"
        rows.append({"char": ch, "ipa": ipa,
                     "status": "收录" if tag == "covered" else "拼音近似",
                     "cap": cap})
    scholar_info = {
        "system_id": system_id,
        "system_name": get_system(system_id).name,
        "rows": rows,
        "level_counts": level_counts,
        "coverage": result.coverage,
        "unknown": result.unknown,
    }
    return classical, valid_ipa, audio_dh, mod, audio_mec, rows, scholar_info


def process_input(inp, skip_translate=False, pitch=130, system_id=None):
    if skip_translate:
        classical = inp
    else:
        classical = simple_translate(inp)
    if system_id:
        return process_input_scholar(classical, system_id=system_id, pitch=pitch)
    analyses, ipa_parts = [], []
    for ch in classical:
        if ch in '。！？':
            ipa_parts.append(".")
        elif ch in '，、；：':
            ipa_parts.append(",")
        elif ch.strip() and ch not in '""\'\'（）—…·':
            data = lookup_char(ch)
            if not data:
                py = get_pinyin_fallback(ch)
                est_ipa = estimate_ipa_from_pinyin(py) if py else None
                if est_ipa: data = {"ipa": est_ipa, "init": "拼音近似", "final": "现代音", "tone": "今音", "init_ipa": ""}
            if data:
                ipa_parts.append(data["ipa"])
                diffs = analyze_diffs(data) if data.get("init") != "拼音近似" else pinyin_analyze_diffs(ch)
                qy = query_qieyun(ch) if QIEYUN_AVAILABLE else None
                analyses.append({"char": ch, "old_ipa": data["ipa"], "init_cls": data.get("init",""), "final_cls": data.get("final",""), "tone": data.get("tone",""), "init_ipa": data.get("init_ipa",""), "pinyin": get_pinyin(ch), "qieyun": qy, "differences": diffs})
            else: ipa_parts.append("?"); analyses.append(None)
        else: ipa_parts.append("")
    valid_ipa = " ".join(p for p in ipa_parts if p not in ("", "?"))
    # 过滤掉含有中文字符的非法 IPA 片段
    import unicodedata
    clean_ipa = []
    for part in valid_ipa.split():
        if not any('一' <= c <= '鿿' or '㐀' <= c <= '䶿' for c in part):
            clean_ipa.append(part)
    valid_ipa = " ".join(clean_ipa)
    audio_dh, audio_mec, audio_mod = None, None, None
    if valid_ipa.strip():
        try:
            audio = synthesize_text(valid_ipa, pitch=pitch)
            if audio is not None and len(audio) > 0 and np.max(np.abs(audio)) > 0.001:
                audio_dh = audio_to_base64(audio)
        except: pass
        try:
            audio_m = synthesize_text(valid_ipa, pitch=max(100, pitch - 30))
            if audio_m is not None and len(audio_m) > 0 and np.max(np.abs(audio_m)) > 0.001:
                audio_mec = audio_to_base64(audio_m)
        except: pass
    mod = generate_edge_tts(classical)
    if not mod:
        try:
            from gtts import gTTS
            tts = gTTS(classical, lang="zh-CN", slow=False)
            buf = BytesIO(); tts.write_to_fp(buf); buf.seek(0)
            mod = base64.b64encode(buf.read()).decode("ascii")
        except: pass
    audio_mod = mod
    return classical, " ".join(ipa_parts), audio_dh, audio_mod, audio_mec, analyses, None

# ===== UI =====
st.set_page_config(page_title="古韵 - 东汉洛阳官音", page_icon=":classical_building:", layout="wide")

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
    .main-header { font-family:'Noto Serif SC',serif; font-size:2.8rem; font-weight:900; color:var(--gold)!important; text-align:center; padding:2rem 0 0.2rem 0; letter-spacing:0.08em; }
    .main-header::after { content:''; display:block; width:60px; height:2px; background:var(--gold); margin:0.5rem auto 0; opacity:0.5; }
    .sub-header { font-family:'Noto Sans SC',sans-serif; font-size:0.9rem; color:var(--text-muted)!important; text-align:center; margin-bottom:2rem; font-weight:300; letter-spacing:0.2em; }
    .classical-text { font-family:'Noto Serif SC',serif; font-size:1.4rem; line-height:2.2; color:#f0e8d8!important; padding:1.2rem 1.5rem; background:linear-gradient(135deg,var(--bg-card) 0%,var(--bg-elevated) 100%); border-radius:8px; border-left:3px solid var(--gold); margin:0.5rem 0; letter-spacing:0.08em; }
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
                        st.markdown(f'<div class="feature-card"><strong>{tag}</strong><br><span style="color:#7a6a5a;font-size:0.75rem">{info["desc"]}</span><br><span style="font-size:0.8rem;color:#d4c4a8">{", ".join(info["chars"])}</span></div>', unsafe_allow_html=True)
                        st.markdown(f'<div class="feature-card"><strong>{tag}</strong><br><span style="color:#7a6a5a;font-size:0.75rem">{info["desc"]}</span><br><span style="font-size:0.8rem;color:#d4c4a8">{", ".join(info["chars"])}</span></div>', unsafe_allow_html=True)
    h4,h5 { color:var(--gold)!important; }
st.markdown('<div class="footer-note">基於鄭張尚芳上古音體系 · 東漢洛陽官音重建 · 僅供參考非學術標準</div>', unsafe_allow_html=True)
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">古 音</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">東漢·洛陽·官音合成器 │ 聽千年回響</div>', unsafe_allow_html=True)

col1, col2 = st.columns([2, 3], gap="large")

with col1:
    input_mode = st.radio("输入类型", ["白话文转古文", "直接输入古文"], horizontal=True, label_visibility="collapsed")
    st.markdown("#### ✍️ 输入文本")
    input_text = st.text_area("输入文本", placeholder="输入现代白话文或文言文…", height=100, label_visibility="collapsed")

    # 语调选择器：影响 pitch
    tone_pitch_map = {"平直": 120, "稳重": 130, "昂扬": 150, "悲慨": 100}
    tone_setting = st.select_slider("语调", options=list(tone_pitch_map.keys()), value="稳重")

    # v5 第三阶段③：发音引擎按所选体系切换，缺音段显式报出
    from language.history import SCHOLAR_SYSTEMS_ALL as _SCH_ALL
    _SYNTH_OPTIONS = {"东汉洛阳官音（默认）": None}
    _SYNTH_OPTIONS.update({f"{name}（{sid}）": sid for sid, name in _SCH_ALL.items()})
    system_choice = st.selectbox("拟音体系", list(_SYNTH_OPTIONS.keys()), key="guyun_system")
    if _SYNTH_OPTIONS[system_choice]:
        st.caption("所选为学者拟音体系：逐字查该体系 Sinica 拟音表，缺字不补现代拼音；"
                   "每个字的「重建状态」与「合成能力」分别显示，引擎发不出的音段逐字标注。")

    generate_btn = st.button("\U0001f399️ 生成", use_container_width=True, type="primary")
    with st.expander("\U0001f4d6 关于本项目"):
        st.markdown("基于郑张尚芳上古韵体系，以东汉洛阳音为目标音系。数据库当前收录 "+str(len(EASTERN_HAN_DB))+" 字。")
        # 降级说明：这两项依赖缺失时界面不会报错，但相应功能会整块消失，必须显式告知
        if not QIEYUN_AVAILABLE:
            st.caption(f"⚠️ 切韵对照不可用：{QIEYUN_ERROR}")
            st.caption("安装提示：`pip install -r requirements.txt`（numpy<2 与 scipy<1.14 需同时满足）")
        if not EDGE_TTS_AVAILABLE:
            st.caption(f"⚠️ 现代朗读不可用：{EDGE_TTS_ERROR}")

with col2:
    if generate_btn and input_text.strip():
        selected_system_id = _SYNTH_OPTIONS[system_choice]
        with st.spinner("处理中…"):
            skip_translate = (input_mode == "直接输入古文")
            selected_pitch = tone_pitch_map.get(tone_setting, 130)
            try:
                result = process_input(input_text.strip(), skip_translate=skip_translate,
                                       pitch=selected_pitch, system_id=selected_system_id)
            except ValueError as e:
                st.warning(str(e))
                result = None
            if result is not None:
                st.session_state.display_data = result
                st.session_state.audio_version = st.session_state.get("audio_version", 0) + 1
                st.session_state.tone_setting = tone_setting
        st.rerun()

    if "display_data" in st.session_state:
        d = st.session_state.display_data
        classical, ipa_text, audio_dh, audio_mod, audio_mec, analyses, scholar_info = d
        ver = st.session_state.get("audio_version", 0)
        _sys_label = scholar_info["system_name"] if scholar_info else "东汉洛阳音"

        # 语调信息显示
        tone_val = st.session_state.get("tone_setting", "稳重")
        st.markdown("#### \U0001f4dc 古文翻译")
        st.markdown(f'<div class="classical-text">{classical}</div>', unsafe_allow_html=True)

        st.markdown(f"#### \U0001f50a {_sys_label} IPA")
        st.markdown(f'<div class="ipa-display">{ipa_text}</div>', unsafe_allow_html=True)

        st.markdown("#### \U0001f50a 三轨音频")
        c1, c2, c3 = st.columns(3)
        with c1:
            _track_label = "东汉官音" if not scholar_info else f"{scholar_info['system_name']} 官音"
            st.markdown(f'<div class="audio-card"><strong>\U0001f3db️ {_track_label}</strong></div>', unsafe_allow_html=True)
            if audio_dh:
                st.audio(base64.b64decode(audio_dh), format="audio/wav")
        with c2:
            st.markdown('<div class="audio-card"><strong>\U0001f5e3️ 现代朗读</strong></div>', unsafe_allow_html=True)
            if audio_mod:
                st.audio(base64.b64decode(audio_mod), format="audio/mp3")
        with c3:
            st.markdown('<div class="audio-card"><strong>⚙️ 机械参考</strong></div>', unsafe_allow_html=True)
            if audio_mec:
                st.audio(base64.b64decode(audio_mec), format="audio/wav")

        if audio_dh:
            _dl_name = f"guyun_v{ver}.wav" if not scholar_info else f"guyun_{scholar_info['system_id']}_v{ver}.wav"
            _dl_label = "下载东汉官音 WAV" if not scholar_info else f"下载 {scholar_info['system_name']} 官音 WAV"
            st.download_button(f"\U0001f4be {_dl_label}", base64.b64decode(audio_dh), file_name=_dl_name, mime="audio/wav")

        if scholar_info:
            from language.phoneme_capability import ESPEAK_LEVEL_ZH
            rows_all = scholar_info["rows"]
            st.markdown("---")
            st.markdown(f"#### \U0001f4ca 逐字对照（{scholar_info['system_name']}）")

            rows_per_page = 15
            total_pages = max(1, (len(rows_all) + rows_per_page - 1) // rows_per_page)
            if "phonology_page" not in st.session_state:
                st.session_state.phonology_page = 0
            st.session_state.phonology_page = min(st.session_state.phonology_page, total_pages - 1)

            c_prev, c_page, c_next = st.columns([1, 3, 1])
            with c_prev:
                if st.button("◀ 上一页", disabled=(st.session_state.phonology_page == 0), use_container_width=True, key="scholar_prev"):
                    st.session_state.phonology_page = max(0, st.session_state.phonology_page - 1)
                    st.rerun()
            with c_page:
                st.markdown(f'<div style="text-align:center;color:var(--gold)!important;padding-top:0.3rem">第 {st.session_state.phonology_page + 1} / {total_pages} 页（共 {len(rows_all)} 字）</div>', unsafe_allow_html=True)
            with c_next:
                if st.button("下一页 ▶", disabled=(st.session_state.phonology_page >= total_pages - 1), use_container_width=True, key="scholar_next"):
                    st.session_state.phonology_page = min(total_pages - 1, st.session_state.phonology_page + 1)
                    st.rerun()

            start = st.session_state.phonology_page * rows_per_page
            trs = []
            for r in rows_all[start:start + rows_per_page]:
                ipa_disp = r["ipa"] or "—"
                miss = r["status"].startswith("缺")
                color = "#d85a4a" if miss else "#7a6a5a"
                trs.append(
                    f'<tr><td style="padding:0.3rem;text-align:center;font-weight:700">{r["char"]}</td>'
                    f'<td style="padding:0.3rem;text-align:center;font-family:monospace">{ipa_disp}</td>'
                    f'<td style="padding:0.3rem;text-align:center;color:{color}">{r["status"]}</td>'
                    f'<td style="padding:0.3rem;text-align:center;font-size:0.75rem">{r["cap"]}</td></tr>')
            st.markdown(
                '<table class="phonology-table"><thead><tr><th>字</th><th>体系拟音</th>'
                f'<th>重建状态（数据侧）</th><th>合成能力（引擎侧）</th></tr></thead><tbody>{"".join(trs)}</tbody></table>',
                unsafe_allow_html=True)

            lc = scholar_info["level_counts"]
            lc_summary = " · ".join(f"{ESPEAK_LEVEL_ZH[k]}：{v} 字" for k, v in lc.items() if v)
            st.caption(f"合成能力汇总：{lc_summary or '—'}")
            st.caption(
                "两列相互独立：**重建状态** = 该学者体系在 Sinica 工作簿里是否有此字的拟音记录"
                f"（缺字 {len(scholar_info['unknown'])} 个，不用现代拼音补）；"
                "**合成能力** = 本机 eSpeak-ng 能否发出拟音中的音段——引擎丢掉的音段逐字标注，"
                "且「能渲染」不等于音值准确（近似符号按原音素近似发音）。")

        valid = [a for a in analyses if a is not None] if not scholar_info else []
        if valid:
            st.markdown("---")
            st.markdown("#### \U0001f4ca 逐字音韵分析")

            # 翻页：每页15个字
            rows_per_page = 15
            total_pages = max(1, (len(valid) + rows_per_page - 1) // rows_per_page)
            if "phonology_page" not in st.session_state:
                st.session_state.phonology_page = 0

            c_prev, c_page, c_next = st.columns([1, 3, 1])
            with c_prev:
                if st.button("◀ 上一页", disabled=(st.session_state.phonology_page == 0), use_container_width=True):
                    st.session_state.phonology_page = max(0, st.session_state.phonology_page - 1)
                    st.rerun()
            with c_page:
                st.markdown(f'<div style="text-align:center;color:var(--gold)!important;padding-top:0.3rem">第 {st.session_state.phonology_page + 1} / {total_pages} 页（共 {len(valid)} 字）</div>', unsafe_allow_html=True)
            with c_next:
                if st.button("下一页 ▶", disabled=(st.session_state.phonology_page >= total_pages - 1), use_container_width=True):
                    st.session_state.phonology_page = min(total_pages - 1, st.session_state.phonology_page + 1)
                    st.rerun()

            start = st.session_state.phonology_page * rows_per_page
            page_valid = valid[start:start + rows_per_page]

            rows = []
            for a in page_valid:
                tc = f"tone-{a['tone']}" if any(t in a.get('tone','') for t in "平上去入") else ""
                tt = f'<span class="tone-tag {tc}">{a["tone"]}</span>' if a.get("tone") else ""
                dd = "; ".join([f'<span style="color:#d85a4a">{d[0]}</span>' for d in a["differences"][:2]])
                qy = a.get("qieyun") or "—"
                row_html = f"<tr><td style=\"padding:0.3rem;text-align:center;font-weight:700\">{a['char']}</td><td style=\"padding:0.3rem;text-align:center;font-family:monospace\">{a['old_ipa']}</td><td style=\"padding:0.3rem;text-align:center\">{a['init_cls']}</td><td style=\"padding:0.3rem;text-align:center\">{a['final_cls']}</td><td style=\"padding:0.3rem;text-align:center\">{tt}</td><td style=\"padding:0.3rem;text-align:center;color:#7a6a5a;font-size:0.75rem\">{qy}</td><td style=\"padding:0.3rem;text-align:center;font-size:0.75rem\">{dd}</td></tr>"
                rows.append(row_html)
            st.markdown(f'<table class="phonology-table"><thead><tr><th>字</th><th>东汉IPA</th><th>声母</th><th>韵母</th><th>声调</th><th>切韵音</th><th>古今差异</th></tr></thead><tbody>{"".join(rows)}</tbody></table>', unsafe_allow_html=True)

            feats = {}
            for a in valid:
                for d in a["differences"]:
                    tag, desc = d[0], d[1]
                    if tag not in feats: feats[tag] = {"desc": desc, "chars": []}
                    feats[tag]["chars"].append(a["char"])
            if feats:
                st.markdown("#### \U0001f9ec 语音史特征")
                cols = st.columns(min(3, len(feats)))
                for i, (tag, info) in enumerate(sorted(feats.items())):
                    col = cols[i % 3]
                    with col:
                        st.markdown(f'<div class="feature-card"><strong>{tag}</strong><br><span style="color:#7a6a5a;font-size:0.75rem">{info["desc"]}</span><br><span style="font-size:0.8rem;color:#d4c4a8">{", ".join(info["chars"])}</span></div>', unsafe_allow_html=True)


# ===== 历史音系探索（独立研究视图，不改变原有东汉合成流程）=====
with st.expander("🧭 历史音系探索（研究预览）", expanded=False):
    from language.history import (
        get_period, systems_for_period, lookup_reading,
        lookup_qieyun_positions, lookup_phono_ml, lookup_zhongyuan,
    )

    st.markdown(
        "按历史时期与学者方案查询已接入的离线数据。这里显示的是韵书记录、"
        "音韵地位或学者转写；**不等于真实录音，也不保证可以直接送入 TTS**。"
    )
    period_labels = {
        "上古汉语 / 东汉实验区": "old_chinese",
        "中古汉语 / 《广韵》系": "middle_chinese",
        "元明时期 / 《中原音韵》": "early_mandarin",
    }
    selected_period_label = st.selectbox(
        "历史时期", list(period_labels.keys()), key="historical_explorer_period"
    )
    selected_period = period_labels[selected_period_label]
    systems = systems_for_period(selected_period, include_metadata_only=False)
    if not systems:
        st.info("该时期暂无可查询的已接入数据。")
    else:
        selected_system_id = st.selectbox(
            "数据 / 拟音方案",
            [s.id for s in systems],
            format_func=lambda sid: next(
                f"{s.name} · {s.scholar}" for s in systems if s.id == sid
            ),
            key="historical_explorer_system",
        )
        query_char = st.text_input(
            "查询单个汉字", value="東", max_chars=1,
            key="historical_explorer_character",
        ).strip()
        if st.button("查询历史音系", key="historical_explorer_lookup"):
            if not query_char:
                st.warning("请先输入一个汉字。")
            else:
                rows = []
                source_url = ""
                if selected_system_id == "guangyun_qieyun_position":
                    from language.history.qieyun_data import SOURCE_URL
                    source_url = SOURCE_URL
                    for rec in lookup_qieyun_positions(query_char):
                        rows.append({
                            "汉字": rec.head_character,
                            "小韵号": rec.xiaoyun_id,
                            "反切上字": rec.fanqie_upper,
                            "反切下字": rec.fanqie_lower,
                            "音韵地位（原始描述）": rec.position_description,
                            "数据类型": "韵书音韵地位，不是 IPA",
                        })
                elif selected_system_id == "phono_ml_baxter_sagart_mc":
                    from language.history.phono_ml_data import SOURCE_URL
                    source_url = SOURCE_URL
                    for rec in lookup_phono_ml(query_char):
                        rows.append({
                            "汉字": rec.character,
                            "转写方案": rec.transcription_scheme,
                            "转写": rec.transcription,
                            "反切": rec.fanqie,
                            "音韵地位": rec.phonological_position,
                            "源条目标识": rec.identifiers,
                            "数据类型": "Baxter–Sagart 风格转写；非 IPA 音频",
                        })
                elif selected_system_id.startswith("zhongyuan_"):
                    from language.history.zhongyuan_data import SOURCE_URL
                    source_url = SOURCE_URL
                    for rec in lookup_zhongyuan(query_char, selected_system_id):
                        value = dict(rec.transcriptions).get(selected_system_id, "")
                        rows.append({
                            "汉字": rec.character,
                            "小韵": rec.xiaoyun,
                            "声母": rec.initial,
                            "韵母": rec.final,
                            "声调": rec.tone,
                            "学者方案": selected_system_id,
                            "转写 / 拟音": value,
                            "数据类型": "《中原音韵》学者方案转写",
                        })
                else:
                    reading = lookup_reading(query_char, selected_system_id)
                    source_url = reading.provenance.source_url or ""
                    rows.append({
                        "汉字": reading.character,
                        "体系": reading.system_id,
                        "记录状态": reading.source_status,
                        "IPA 字段": reading.ipa or "—",
                        "音韵地位": reading.phonological_position or "—",
                        "转写": reading.transcription or "—",
                        "说明": reading.note,
                    })

                if rows:
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                    if source_url:
                        st.markdown(f"数据来源：[查看上游记录 / 数据集]({source_url})")
                    st.caption(
                        "多音字会显示该数据集可查到的多条记录。不同学者方案是不同模型，"
                        "请勿把它们拼接为一个未经说明的“标准古音”。"
                    )
                else:
                    st.info("该字在所选数据集中没有查到记录。")


# ===== 同字跨体系对照（第二阶段②争议项视图 + ③覆盖率进 UI）=====
with st.expander("🔀 同字跨体系对照（争议项）", expanded=False):
    from language.history import (
        compare_character, scholar_coverage,
        SCHOLAR_SYSTEMS_ALL as SCHOLAR_ALL,
    )

    st.markdown(
        "把同一个字在所选时期**全部已接入体系**里的值并排陈列。"
        "**各体系不可混用**：差异是各方案模型的直接证据；"
        "缺字、源表缺陷一律如实报出，不用其他体系补值。"
    )
    cmp_period_label = st.selectbox(
        "历史时期", list(period_labels.keys()),
        key="historical_compare_period",
    )
    cmp_period = period_labels[cmp_period_label]
    cmp_char = st.text_input(
        "要对照的字", value="融", max_chars=1,
        key="historical_compare_character",
    ).strip()
    if cmp_char:
        cmp = compare_character(cmp_char, cmp_period)
        kind_labels = {"ipa": "IPA", "transcription": "转写",
                       "position": "音韵地位", "none": "—"}

        def _fmt_values(values):
            """重复值折叠为「v ×n」，条数信息不丢。"""
            seen, order = {}, []
            for v in values:
                if v not in seen:
                    order.append(v)
                seen[v] = seen.get(v, 0) + 1
            return " / ".join(
                f"{v} ×{seen[v]}" if seen[v] > 1 else v for v in order)

        rows = []
        for r in cmp.rows:
            extra = ("；上游備註：" + r.upstream_note) if r.upstream_note else ""
            rows.append({
                "体系": f"{r.system_name}（{r.system_id}）",
                "读音 / 转写": _fmt_values(r.values) if r.values else "—",
                "值类型": kind_labels[r.value_kind],
                "韻部": r.rhyme_group or "—",
                "状态": r.source_status,
                "说明": (r.note + extra).strip() or "—",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
        n_present = len(cmp.system_ids_with_values)
        if cmp.disagrees:
            st.markdown(
                f"**{len(cmp.distinct_values)} 个不同值**（{n_present} 个体系有值）："
                + " / ".join(f"`{v}`" for v in cmp.distinct_values)
                + " —— 同一字在各方案下的分歧，各体系不可混用。"
            )
        elif n_present:
            st.markdown(f"{n_present} 个体系有值且一致：`{cmp.distinct_values[0]}`。")
        else:
            st.info(f"{cmp_period_label} 的已接入体系里都查不到「{cmp_char}」。")
        if cmp.system_ids_without_values:
            missing_names = "、".join(
                r.system_name for r in cmp.rows if not r.has_value)
            st.caption("无记录体系：" + missing_names + "（如实报缺，不编造值）。")

        st.markdown("#### 各体系覆盖率（所选时期）")
        cov_rows = []
        for system in systems_for_period(cmp_period, include_metadata_only=False):
            if system.id in SCHOLAR_ALL:
                c = scholar_coverage(system.id)
                cov_rows.append({
                    "体系": system.name,
                    "字数": c["characters"],
                    "记录": c["records"],
                    "缺陷行": c["skipped_suspect_initial"],
                    "空韻母": c["skipped_empty_final"],
                    "韻部数": c["rhyme_group_count"],
                    "備註行": c["upstream_note_rows"],
                    "零声母行": c["zero_initial"] + c["glide_onset"],
                    "说明": "",
                })
            elif system.id == "han_eastern_experimental":
                try:
                    from phonology_db import EASTERN_HAN_DB
                    n = len(EASTERN_HAN_DB)
                except ImportError:
                    n = 0
                cov_rows.append({
                    "体系": system.name, "字数": n, "记录": n,
                    "缺陷行": "—", "空韻母": "—", "韻部数": "—", "備註行": "—",
                    "零声母行": "—", "说明": "项目旧实验字表，来源未逐字审计",
                })
            else:
                cov_rows.append({
                    "体系": system.name, "字数": "—", "记录": "—",
                    "缺陷行": "—", "空韻母": "—", "韻部数": "—", "備註行": "—",
                    "零声母行": "—",
                    "说明": "原始资料/转写数据集，非逐字拟音表（见上方探索器）",
                })
        st.dataframe(cov_rows, use_container_width=True, hide_index=True)
        st.caption(
            "覆盖率口径：缺陷行＝源表声母列错位/缺损（保留但不给 IPA）；"
            "空韻母＝韵母列为空或「?」（不计入）；零声母行＝上游以 0／· 标记无辅音的行。"
        )


# ===== 中央研究院古今音资料库：独立下载的 PDM 声韵数据 =====
with st.expander("🏛️ 中央研究院古今音资料库（来源可追溯的原始记录）", expanded=False):
    from language.history.sinica_ccr_data import (
        DATA_PATH as SINICA_CCR_DATA_PATH,
        dataset_available as sinica_ccr_dataset_available,
        lookup_sinica_ccr_records,
        sinica_ccr_record_count,
    )

    st.markdown(
        "该模块查询中央研究院／台大官方独立下载的声韵资料。每条结果保留原始工作簿、"
        "工作表、行号、原始字段及 SHA-256。韵部标签、学者转写和拟音是不同数据类型；"
        "页面不会把韵部标签自动转换成 IPA。"
    )
    if not sinica_ccr_dataset_available():
        st.warning("当前代码已支持查询，但规范化数据文件尚未放入仓库目录。")
        st.code(
            "mkdir -p data/historical/sinica_ccr_import\n"
            "unzip sinica_ccr_import_bundle.zip -d data/historical/sinica_ccr_import",
            language="bash",
        )
        st.markdown(
            "将本次提供的 sinica_ccr_import_bundle.zip 解压到上述目录后，重新启动页面即可启用。"
            "完整数据包包含 26 个工作簿、34 个工作表，共 378,214 条数据记录。"
        )
        st.markdown(
            "[官方授权与来源说明](https://xiaoxue.iis.sinica.edu.tw/ccrdata/) · "
            "[项目数据说明](data/historical/README.md)"
        )
    else:
        package_labels = {
            "全部数据集": None,
            "上古音／两汉": "sinica_ccr_old_chinese",
            "中古时期": "sinica_ccr_middle_chinese",
            "历代韵书": "sinica_ccr_rhyme_books",
        }
        p1, p2 = st.columns(2)
        with p1:
            package_label = st.selectbox(
                "资料包", list(package_labels), key="sinica_ccr_package"
            )
        with p2:
            period_labels = [
                "全部时期", "先秦", "西汉", "东汉", "魏", "晋",
                "南北朝", "隋唐", "韵书资料",
            ]
            period_label = st.selectbox(
                "时期／资料类别", period_labels, key="sinica_ccr_period"
            )
        workbook_keyword = st.text_input(
            "学者／韵书名称过滤（可留空）",
            placeholder="例如：王力、董同龢、廣韻、中原音韻",
            key="sinica_ccr_workbook_keyword",
        ).strip()
        c1, c2 = st.columns([1, 2])
        with c1:
            character = st.text_input(
                "查询单个汉字", value="東", max_chars=1, key="sinica_ccr_character"
            ).strip()
        with c2:
            st.caption(
                "首次查询会在本机临时目录建立 SQLite 检索索引；原始数据文件不会被修改。"
            )
        if st.button("查询古今音资料", key="sinica_ccr_lookup"):
            if not character:
                st.warning("请先输入一个汉字。")
            else:
                try:
                    records = lookup_sinica_ccr_records(
                        character,
                        dataset_id=package_labels[package_label],
                        period=None if period_label == "全部时期" else period_label,
                        workbook_keyword=workbook_keyword or None,
                        limit=200,
                    )
                    if records:
                        rows = []
                        for rec in records:
                            rows.append({
                                "汉字": rec.character,
                                "时期": rec.period,
                                "体系／韵书": rec.system,
                                "数据类型": rec.record_type,
                                "原始字段": "；".join(
                                    f"{key}={value}" for key, value in rec.fields.items()
                                    if value != ""
                                ),
                                "来源工作簿": rec.source_workbook,
                                "工作表": rec.source_sheet,
                                "源行号": rec.source_row,
                                "许可标记": rec.license_mark,
                                "工作簿 SHA-256": rec.source_workbook_sha256,
                            })
                        st.dataframe(rows, use_container_width=True, hide_index=True)
                        st.caption(
                            f"显示 {len(records)} 条记录（最多 200 条）。结果按源工作簿、工作表和行号排序；"
                            "多读与异读均保留。"
                        )
                        total_count = sinica_ccr_record_count(
                            dataset_id=package_labels[package_label]
                        ) if package_labels[package_label] else sinica_ccr_record_count()
                        st.markdown(
                            f"[查看官方资料库]({records[0].source_url}) · "
                            f"资料包记录总数：{total_count:,}"
                        )
                    else:
                        st.info("该字在当前筛选条件下没有记录。可清除学者／韵书过滤后重试。")
                except (FileNotFoundError, ValueError) as exc:
                    st.error(str(exc))
