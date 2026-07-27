# -*- coding: utf-8 -*-
"""
guyun_app.py
古韵 - 东汉洛阳官音合成器
白话到古文到IPA标注到三轨音频
"""

import streamlit as st
import streamlit.components.v1 as components
import sys, os, asyncio, tempfile, json, re, unicodedata
import numpy as np
from io import BytesIO
import base64

# PyInstaller 打包环境下的路径修正
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    # 关键：同时把 _internal 加入 path（PyInstaller 5.x+ 的文件都在这里）
    _internal = os.path.join(BASE_DIR, '_internal')
    if os.path.isdir(_internal):
        sys.path.insert(0, _internal)
    sys.path.insert(0, BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, BASE_DIR)

from phonology_db import EASTERN_HAN_DB, lookup_char
from classical_translator import simple_translate
from sound_synth import synthesize_text, audio_to_wav_bytes, audio_to_base64, SAMPLE_RATE, ESPEAK_AVAILABLE

try: from pypinyin import pinyin as _pypinyin, Style; PYPINYIN_AVAILABLE = True
except: PYPINYIN_AVAILABLE = False

# ====== 统一的 CJK 检测函数（覆盖所有中文区间）======
_CJK_PATTERN = re.compile(
    r'[㐀-䶿一-鿿豈-﫿'
    r'\U00020000-\U0002a6df\U0002a700-\U0002ebef'
    r'\U0002f800-\U0002fa1f]'
)
def contains_cjk(s):
    """检测字符串是否包含任何中日韩汉字"""
    if not s:
        return False
    return bool(_CJK_PATTERN.search(str(s)))

def clean_ipa(s):
    """如果字符串包含中文，返回 '?'；否则原样返回"""
    if s is None:
        return "?"
    s = str(s)
    if contains_cjk(s):
        return "?"
    return s


def to_html_entities(text):
    """把非ASCII字符转成HTML数字实体"""
    if not text:
        return text
    result = []
    for ch in str(text):
        if ord(ch) > 127:
            result.append(f'&#{ord(ch)};')
        else:
            result.append(ch)
    return ''.join(result)


def get_pinyin_fallback(char):
    """拼音回退，只在本地硬编码字典中查找"""
    if char in PINYIN_MAP:
        py = PINYIN_MAP[char]
        py = re.sub(r'[0-9]', '', py)
        if py.isascii() and py.isalpha():
            return py
    # 不再使用 pypinyin，避免跨系统兼容问题
    return None

def estimate_ipa_from_pinyin(py):
    if not py or not py.isascii() or not py.isalpha():
        return None

    init_map = {'b': 'p', 'p': 'pʰ', 'm': 'm', 'f': 'f', 'd': 't', 't': 'tʰ', 'n': 'n', 'l': 'l', 'g': 'k', 'k': 'kʰ', 'h': 'h', 'j': 'tɕ', 'q': 'tɕʰ', 'x': 'ɕ', 'zh': 'tʂ', 'ch': 'tʂʰ', 'sh': 'ʂ', 'r': 'ȵ', 'z': 'ts', 'c': 'tsʰ', 's': 's', 'y': 'j', 'w': 'ʔ'}
    final_map = {'iang': 'iaŋ', 'uang': 'uaŋ', 'iong': 'yuŋ', 'uai': 'uai', 'ang': 'ɑŋ', 'eng': 'əŋ', 'ing': 'iŋ', 'ong': 'uŋ', 'ian': 'ian', 'uan': 'uan', 'iao': 'iau', 'iou': 'iou', 'ai': 'ai', 'ei': 'ei', 'ui': 'uei', 'ao': 'au', 'ou': 'ou', 'iu': 'iou', 'an': 'an', 'en': 'ən', 'in': 'in', 'un': 'uən', 'vn': 'yn', 'ia': 'ia', 'ie': 'ie', 'ua': 'ua', 'uo': 'uo', 've': 'ye', 'van': 'yan', 'ue': 'ye', 'a': 'a', 'o': 'o', 'e': 'ə', 'i': 'i', 'u': 'u', 'v': 'y'}

    init_list = ['zh','ch','sh','b','p','m','f','d','t','n','l','g','k','h','j','q','x','r','z','c','s','y','w']
    init_ipa, rest = '', py

    for init in init_list:
        if py.startswith(init):
            init_ipa = init_map.get(init, '')
            rest = py[len(init):]
            break

    final_ipa = rest
    for f_len in range(5, 0, -1):
        if len(rest) >= f_len and rest[:f_len] in final_map:
            final_ipa = final_map[rest[:f_len]]
            break
    if rest in final_map:
        final_ipa = final_map[rest]

    result = f"{init_ipa}{final_ipa}" if (init_ipa or final_ipa) else None

    # 统一使用 contains_cjk 检测
    if result and contains_cjk(result):
        return None

    return result

def pinyin_analyze_diffs(char):
    return [("拼音回退", "该字未收录东汉音数据库，暂以现代拼音近似")]

try: from Qieyun import 字頭2音韻地位_出處們; QIEYUN_AVAILABLE = True
except: QIEYUN_AVAILABLE = False

try: import edge_tts; EDGE_TTS_AVAILABLE = True
except: EDGE_TTS_AVAILABLE = False

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
    "而":"er","所":"suo","能":"neng","当":"dang","犹":"you","可":"ke","非":"fei","莫":"mo","再":"zai",
    "为":"wei","在":"zai","有":"you","无":"wu","来":"lai","去":"qu","出":"chu","入":"ru","归":"gui",
    "等":"deng","彼":"bi","己":"ji","饮":"yin","曰":"yue","奔":"ben","寝":"qin","恶":"e","欲":"yu","予":"yu",
    "令":"ling","呼":"hu","寻":"xun","市":"shi","鬻":"yu","教":"jiao","若":"ruo","虽":"sui","将":"jiang","孰":"shu",
    "几":"ji","昨":"zuo","昔":"xi","忽":"hu","尝":"chang","侧":"ce","遍":"bian","短":"duan","疾":"ji","美":"mei",
    "丑":"chou","伪":"wei","悲":"bei","怒":"nu","惧":"ju","邪":"xie","再":"zai",
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

def process_input(inp, skip_translate=False, pitch=130):
    if skip_translate:
        classical = inp
    else:
        classical = simple_translate(inp)
    analyses, ipa_parts = [], []
    for ch in classical:
        if ch in '。！？':
            ipa_parts.append(".")
        elif ch in '，、；：':
            ipa_parts.append(",")
        elif ch.strip() and ch not in '""\'\'（）—…·':
            data = lookup_char(ch)
            # 【修复BUG5】对数据库返回值做 IPA 合法性校验（DB ipa损坏时视为查不到）
            if data and contains_cjk(data.get("ipa", "")):
                print(f"[DEBUG] DB返回含中文IPA: char={ch!r} ipa={data.get('ipa')!r}")
                data = None
            if not data:
                py = get_pinyin_fallback(ch)
                est_ipa = estimate_ipa_from_pinyin(py) if py else None
                if est_ipa:
                    ipa_val = clean_ipa(est_ipa)
                    data = {"ipa": ipa_val, "init": "拼音近似", "final": "现代音", "tone": "今音", "init_ipa": ""}
            if data:
                # 【修复BUG1】ipa_parts 和 analyses 都用清洗后的值
                clean_val = clean_ipa(data["ipa"])
                ipa_parts.append(clean_val)
                diffs = analyze_diffs(data) if data.get("init") != "拼音近似" else pinyin_analyze_diffs(ch)
                qy = query_qieyun(ch) if QIEYUN_AVAILABLE else None
                analyses.append({
                    "char": ch,
                    "old_ipa": clean_val,  # 【关键修复】存清洗后的值，不是原始 data["ipa"]
                    "init_cls": data.get("init", ""),
                    "final_cls": data.get("final", ""),
                    "tone": data.get("tone", ""),
                    "init_ipa": data.get("init_ipa", ""),
                    "pinyin": get_pinyin(ch),
                    "qieyun": qy,
                    "differences": diffs
                })
            else:
                ipa_parts.append("?")
                analyses.append(None)
        else:
            ipa_parts.append("")

    # ===== 【修复BUG2/3】统一清洗：构建 valid_ipa 之前，全量过滤中文 =====
    # 1. 清洗 ipa_parts
    for i, p in enumerate(ipa_parts):
        if p and p not in ("", "?", ",", ".") and contains_cjk(p):
            print(f"[CLEAN] ipa_parts[{i}]={str(p)!r} -> ?")
            ipa_parts[i] = "?"

    # 2. 清洗 analyses 中的 old_ipa（修复表格显示中文！）
    if analyses:
        for a in analyses:
            if a and contains_cjk(a.get("old_ipa", "")):
                print(f"[CLEAN] analyses old_ipa={a.get('old_ipa')!r} -> ?")
                a["old_ipa"] = "?"

    # 3. 构建 display_ipa（在清洗之后！）
    display_ipa = " ".join(p for p in ipa_parts if p not in ("", "?", ",", "."))

    # 4. 构建用于音频合成的 valid_ipa（双重防御——再扫一遍）
    valid_ipa = " ".join(p for p in ipa_parts if p not in ("", "?", ",", "."))
    clean_ipa_list = []
    for part in valid_ipa.split():
        if not contains_cjk(part):
            clean_ipa_list.append(part)
    valid_ipa = " ".join(clean_ipa_list)

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

    return classical, display_ipa, audio_dh, audio_mod, audio_mec, analyses

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
    .classical-text { font-family:'Noto Serif SC','SimSun','STSong',serif; font-size:1.4rem; line-height:2.2; color:#f0e8d8!important; padding:1.2rem 1.5rem; background:linear-gradient(135deg,var(--bg-card) 0%,var(--bg-elevated) 100%); border-radius:8px; border-left:3px solid var(--gold); margin:0.5rem 0; letter-spacing:0.08em; }
    .ipa-display { font-family:'Segoe UI','Arial Unicode MS','DejaVu Sans',sans-serif; font-size:1.1rem; color:var(--text-secondary)!important; background:var(--bg-card); padding:0.7rem 1rem; border-radius:8px; border:1px solid var(--border); margin:0.3rem 0; word-break:break-all; letter-spacing:0.02em; }
    .tone-tag { display:inline-block; padding:0.08rem 0.5rem; border-radius:3px; font-size:0.65rem; font-weight:500; letter-spacing:0.05em; }
    .tone-平声 { background:rgba(122,154,122,0.2); color:#7a9a7a!important; border:1px solid rgba(122,154,122,0.3); }
    .tone-上声 { background:rgba(100,130,170,0.2); color:#7a9aba!important; border:1px solid rgba(100,130,170,0.3); }
    .tone-去声 { background:rgba(192,57,43,0.15); color:#d85a4a!important; border:1px solid rgba(192,57,43,0.3); }
    .tone-入声 { background:rgba(180,68,42,0.15); color:#d46a4a!important; border:1px solid rgba(180,68,42,0.3); }
    .phonology-table { width:100%; font-size:0.8rem; border-collapse:collapse; background:var(--bg-card); border-radius:8px; overflow:hidden; }
    .phonology-table thead { background:var(--bg-deep); }
    .phonology-table th { padding:0.5rem 0.4rem; text-align:center; color:var(--gold)!important; font-weight:500; font-size:0.75rem; letter-spacing:0.05em; border-bottom:1px solid var(--border); }
    .phonology-table td { padding:0.4rem; text-align:center; color:var(--text-primary)!important; border-bottom:1px solid #3a2a1a; font-family:monospace; }
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
    input_text = st.text_area("", placeholder="输入现代白话文或文言文…", height=100, label_visibility="collapsed")

    # 语调选择器：影响 pitch
    tone_pitch_map = {"平直": 120, "稳重": 130, "昂扬": 150, "悲慨": 100}
    tone_setting = st.select_slider("语调", options=list(tone_pitch_map.keys()), value="稳重")
    generate_btn = st.button("\U0001f399️ 生成", use_container_width=True, type="primary")
    with st.expander("\U0001f4d6 关于本项目"):
        st.markdown("基于郑张尚芳上古韵体系，以东汉洛阳音为目标音系。数据库当前收录 "+str(len(EASTERN_HAN_DB))+" 字。")

with col2:
    if generate_btn and input_text.strip():
        with st.spinner("处理中…"):
            skip_translate = (input_mode == "直接输入古文")
            selected_pitch = tone_pitch_map.get(tone_setting, 130)
            result = process_input(input_text.strip(), skip_translate=skip_translate, pitch=selected_pitch)
            st.session_state.display_data = result
            st.session_state.audio_version = st.session_state.get("audio_version", 0) + 1
            st.session_state.tone_setting = tone_setting
        st.rerun()

    if "display_data" in st.session_state:
        d = st.session_state.display_data
        classical, ipa_text, audio_dh, audio_mod, audio_mec, analyses = d
        ver = st.session_state.get("audio_version", 0)
        ver = st.session_state.get("audio_version", 0)

        # 语调信息显示
        tone_val = st.session_state.get("tone_setting", "稳重")
        st.markdown("#### \U0001f4dc 古文翻译")
        st.markdown(f'<div class="classical-text">{classical}</div>', unsafe_allow_html=True)

        st.markdown("#### \U0001f50a 东汉洛阳音 IPA")
        safe_ipa = to_html_entities(ipa_text)
        ipa_html_str = f'<div style="font-family:Segoe UI,Arial Unicode MS,DejaVu Sans,sans-serif; font-size:1.1rem; color:#d4c4a8; background:#2a2018; padding:0.7rem 1rem; border-radius:8px; border:1px solid #4a3a2a; word-break:break-all;">{safe_ipa}</div>'
        components.html(ipa_html_str, height=60)

        st.markdown("#### \U0001f50a 三轨音频")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown('<div class="audio-card"><strong>\U0001f3db️ 东汉官音</strong></div>', unsafe_allow_html=True)
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
            st.download_button("\U0001f4be 下载东汉官音 WAV", base64.b64decode(audio_dh), file_name=f"donghan_guyun_v{ver}.wav", mime="audio/wav")

        valid = [a for a in analyses if a is not None]
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

            # 构建表格 HTML
            table_html = '<table style="width:100%; font-size:0.8rem; border-collapse:collapse; background:#2a2018; color:#e8dcc8; border-radius:8px; overflow:hidden;">'
            table_html += '<thead><tr style="background:#1a1410;"><th style="padding:0.5rem; color:#c9a96e;">字</th><th style="padding:0.5rem; color:#c9a96e;">东汉IPA</th><th style="padding:0.5rem; color:#c9a96e;">声母</th><th style="padding:0.5rem; color:#c9a96e;">韵母</th><th style="padding:0.5rem; color:#c9a96e;">声调</th><th style="padding:0.5rem; color:#c9a96e;">切韵音</th><th style="padding:0.5rem; color:#c9a96e;">古今差异</th></tr></thead>'
            table_html += '<tbody>'

            for a in page_valid:
                safe_old_ipa = to_html_entities(a['old_ipa'])
                tc = ""
                tone = a.get('tone', '')
                if "平" in tone: tc = "background:rgba(122,154,122,0.2); color:#7a9a7a;"
                elif "上" in tone: tc = "background:rgba(100,130,170,0.2); color:#7a9aba;"
                elif "去" in tone: tc = "background:rgba(192,57,43,0.15); color:#d85a4a;"
                elif "入" in tone: tc = "background:rgba(180,68,42,0.15); color:#d46a4a;"

                tt = f'<span style="{tc} padding:0.08rem 0.5rem; border-radius:3px;">{tone}</span>' if tone else ""
                dd = "; ".join([f'<span style="color:#d85a4a">{d[0]}</span>' for d in a["differences"][:2]])
                qy = a.get("qieyun") or "—"

                table_html += f'<tr><td style="padding:0.4rem; text-align:center; font-weight:700;">{a["char"]}</td><td style="padding:0.4rem; text-align:center; font-family:monospace;">{safe_old_ipa}</td><td style="padding:0.4rem; text-align:center;">{a["init_cls"]}</td><td style="padding:0.4rem; text-align:center;">{a["final_cls"]}</td><td style="padding:0.4rem; text-align:center;">{tt}</td><td style="padding:0.4rem; text-align:center; color:#7a6a5a; font-size:0.75rem;">{qy}</td><td style="padding:0.4rem; text-align:center; font-size:0.75rem;">{dd}</td></tr>'

            table_html += '</tbody></table>'
            components.html(table_html, height=600, scrolling=True)

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
