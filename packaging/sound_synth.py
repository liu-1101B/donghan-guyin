# -*- coding: utf-8 -*-
""" sound_synth.py 东汉洛阳官音 双引擎合成器 (eSpeak-ng 优先，回退共振峰) """

import struct, math, wave, io, base64, subprocess, tempfile, os
import sys
import numpy as np

SAMPLE_RATE = 22050


def get_base_dir():
    """获取项目根目录，兼容 PyInstaller 打包和源码运行"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def get_espeak_executable():
    """定位 espeak-ng 可执行文件"""
    base = get_base_dir()

    # 存放路径列表：exe 目录和 _internal 子目录都查
    search_bases = [base]
    internal = os.path.join(base, '_internal')
    if os.path.isdir(internal):
        search_bases.append(internal)

    # 1. 先找 espeak-ng/ 子目录
    for sb in search_bases:
        local_dir = os.path.join(sb, "espeak-ng")
        if sys.platform == "win32":
            local_exe = os.path.join(local_dir, "espeak-ng.exe")
        else:
            local_exe = os.path.join(local_dir, "espeak-ng")
        if os.path.isfile(local_exe):
            return local_exe, local_dir

    # 1b. 找 espeak-ng.exe 直接在根目录
    if sys.platform == "win32":
        for sb in search_bases:
            root_exe = os.path.join(sb, "espeak-ng.exe")
            if os.path.isfile(root_exe):
                return root_exe, sb

    # 2. 找系统全局安装的 espeak-ng
    import shutil
    system_espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if system_espeak:
        return system_espeak, os.path.dirname(system_espeak)

    # Windows MSI 默认路径
    if sys.platform == "win32":
        msi_paths = [
            r"C:\Program Files\eSpeak NG\espeak-ng.exe",
            r"C:\Program Files (x86)\eSpeak NG\espeak-ng.exe",
        ]
        for p in msi_paths:
            if os.path.isfile(p):
                return p, os.path.dirname(p)

    return None, None

# ============================================================
# 引擎 1：eSpeak-ng 调用封装 (返回 numpy 数组)
# ============================================================

def preprocess_ipa(ipa_str):
    """将 IPA 转换为 eSpeak-ng 的 [[ipa]] 语法可识别的 ASCII 字符"""
    if not ipa_str:
        return ""
    ipa_str = ipa_str.replace('ʰ', 'h')
    ipa_str = ipa_str.replace('ʷ', 'w')
    ipa_str = ipa_str.replace('ʲ', 'j')
    ipa_str = ipa_str.replace('ɨ', '1')
    ipa_str = ipa_str.replace('ə', '@')
    ipa_str = ipa_str.replace('ɛ', 'E')
    ipa_str = ipa_str.replace('ɔ', 'O')
    ipa_str = ipa_str.replace('ɑ', 'A')
    ipa_str = ipa_str.replace('ɐ', 'V')
    ipa_str = ipa_str.replace('ɒ', 'Q')
    ipa_str = ipa_str.replace('æ', '{')
    ipa_str = ipa_str.replace('ŋ', 'N')
    ipa_str = ipa_str.replace('ȵ', 'J')
    ipa_str = ipa_str.replace('ʑ', 'Z')
    ipa_str = ipa_str.replace('ɕ', 'S')
    ipa_str = ipa_str.replace('ʂ', 's`')
    ipa_str = ipa_str.replace('ʐ', 'z`')
    ipa_str = ipa_str.replace('ʔ', '?')
    ipa_str = ipa_str.replace('ɦ', 'h')
    ipa_str = ipa_str.replace('ʌ', 'V')
    ipa_str = ipa_str.replace('ɤ', '7')
    ipa_str = ipa_str.replace('ɯ', 'u')
    ipa_str = ipa_str.replace('ʉ', 'u')
    return ipa_str


def synth_with_espeak(ipa_parts, pitch=130):
    """调用 eSpeak-ng 并返回 numpy 数组，使用 [[ipa]] 原生语法"""
    if not ipa_parts:
        return None

    ipa_segments = []
    for ipa in ipa_parts:
        if ipa in (".", ",", "?", "") or not ipa.strip():
            continue
        clean_ipa = preprocess_ipa(ipa)
        ipa_segments.append(f"[[{clean_ipa}]]")

    if not ipa_segments:
        return None

    input_text = " ".join(ipa_segments)

    # 关键修改：用 get_espeak_executable() 定位
    espeak_exe, espeak_dir = get_espeak_executable()
    if not espeak_exe:
        print("[sound_synth] 未找到 espeak-ng，回退共振峰")
        return None

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        wav_path = tmp_wav.name

    try:
        espeak_pitch = max(0, min(99, int((pitch - 100) / 2)))

        # 关键修复：eSpeak-ng 的 C 代码遇到中文路径会报 Illegal byte sequence
        # 解决方案：把 espeak-ng 复制到纯英文的临时目录运行
        temp_espeak_dir = os.path.join(tempfile.gettempdir(), "guyun_espeak")
        temp_exe = os.path.join(temp_espeak_dir, "espeak-ng.exe")
        temp_data = os.path.join(temp_espeak_dir, "espeak-ng-data")

        # 如果临时目录不存在或已损坏，重新复制
        if not os.path.isfile(temp_exe) or not os.path.isdir(temp_data):
            if os.path.exists(temp_espeak_dir):
                import shutil
                shutil.rmtree(temp_espeak_dir, ignore_errors=True)
            # 复制整个 espeak-ng 目录到纯英文路径
            import shutil
            shutil.copytree(espeak_dir, temp_espeak_dir,
                          ignore_dangling_symlinks=True)

        # 构建环境变量
        env = os.environ.copy()
        env["ESPEAK_DATA_PATH"] = temp_espeak_dir

        cmd = [
            temp_exe,
            "-v", "zh",
            "-p", str(espeak_pitch),
            "-s", "140",
            "-w", wav_path,
            input_text
        ]

        subprocess.run(cmd, check=True, capture_output=True, text=True,
                       timeout=15, env=env, cwd=temp_espeak_dir)

        with wave.open(wav_path, 'rb') as wf:
            n_frames = wf.getnframes()
            audio_bytes = wf.readframes(n_frames)
            sr = wf.getframerate()

        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        audio_array = audio_array / 32768.0

        if sr != SAMPLE_RATE:
            ratio = SAMPLE_RATE / sr
            new_len = int(len(audio_array) * ratio)
            x_old = np.linspace(0, 1, len(audio_array))
            x_new = np.linspace(0, 1, new_len)
            audio_array = np.interp(x_new, x_old, audio_array)

        return audio_array

    except subprocess.CalledProcessError as e:
        print(f"[sound_synth] eSpeak-ng 执行失败: {e.stderr[:200] if e.stderr else '无输出'}")
        return None
    except Exception as e:
        print(f"[sound_synth] eSpeak-ng 异常: {e}")
        return None
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


# ============================================================
# 引擎 2：纯 Python 共振峰合成 (回退方案)
# ============================================================

VOWEL_FORMANTS = {
    "i": (300, 2300, 3000), "y": (300, 2100, 2600), "e": (400, 2000, 2800),
    "ɛ": (500, 1800, 2600), "æ": (600, 1700, 2500), "a": (750, 1500, 2500),
    "ɨ": (380, 1700, 2800), "ə": (500, 1500, 2600), "ɐ": (650, 1300, 2500),
    "u": (300, 1000, 2300), "o": (420, 1000, 2500), "ɔ": (550, 1000, 2600),
    "ʌ": (600, 1200, 2600), "ɑ": (700, 1200, 2600), "ɒ": (750, 1100, 2500),
    "ʉ": (350, 1600, 2400), "ɯ": (380, 1300, 2500), "ɤ": (450, 1300, 2500),
}
CONSONANT_PARAMS = {
    "p": {"type": "stop", "voiced": False, "place": "bilabial", "noise_start": 2000, "noise_end": 5000},
    "b": {"type": "stop", "voiced": True, "place": "bilabial", "noise_start": 1500, "noise_end": 4000},
    "t": {"type": "stop", "voiced": False, "place": "alveolar", "noise_start": 3500, "noise_end": 6000},
    "d": {"type": "stop", "voiced": True, "place": "alveolar", "noise_start": 3000, "noise_end": 5500},
    "k": {"type": "stop", "voiced": False, "place": "velar", "noise_start": 2000, "noise_end": 4000},
    "g": {"type": "stop", "voiced": True, "place": "velar", "noise_start": 1500, "noise_end": 3500},
    "ʔ": {"type": "stop", "voiced": False, "place": "glottal", "noise_start": 500, "noise_end": 1500},
    "s": {"type": "fricative", "voiced": False, "place": "alveolar", "center": 6000, "bandwidth": 2000},
    "z": {"type": "fricative", "voiced": True, "place": "alveolar", "center": 5500, "bandwidth": 2000},
    "ʃ": {"type": "fricative", "voiced": False, "place": "postalveolar", "center": 4000, "bandwidth": 1800},
    "ʒ": {"type": "fricative", "voiced": True, "place": "postalveolar", "center": 3500, "bandwidth": 1800},
    "ɕ": {"type": "fricative", "voiced": False, "place": "alveolopalatal", "center": 5000, "bandwidth": 2000},
    "ʑ": {"type": "fricative", "voiced": True, "place": "alveolopalatal", "center": 4500, "bandwidth": 2000},
    "f": {"type": "fricative", "voiced": False, "place": "labiodental", "center": 5000, "bandwidth": 2500},
    "v": {"type": "fricative", "voiced": True, "place": "labiodental", "center": 4500, "bandwidth": 2500},
    "x": {"type": "fricative", "voiced": False, "place": "velar", "center": 3000, "bandwidth": 2000},
    "ɣ": {"type": "fricative", "voiced": True, "place": "velar", "center": 2500, "bandwidth": 2000},
    "h": {"type": "fricative", "voiced": False, "place": "glottal", "center": 1000, "bandwidth": 3000},
    "ɦ": {"type": "fricative", "voiced": True, "place": "glottal", "center": 800, "bandwidth": 2500},
    "ts": {"type": "affricate", "stop": "t", "fricative": "s"}, "dz": {"type": "affricate", "stop": "d", "fricative": "z"},
    "tʃ": {"type": "affricate", "stop": "t", "fricative": "ʃ"}, "dʒ": {"type": "affricate", "stop": "d", "fricative": "ʒ"},
    "tɕ": {"type": "affricate", "stop": "t", "fricative": "ɕ"}, "dʑ": {"type": "affricate", "stop": "d", "fricative": "ʑ"},
    "m": {"type": "nasal", "place": "bilabial", "f1": 300, "f2": 1200, "f3": 2200, "pole_bandwidth": 100},
    "n": {"type": "nasal", "place": "alveolar", "f1": 350, "f2": 1300, "f3": 2500, "pole_bandwidth": 100},
    "ŋ": {"type": "nasal", "place": "velar", "f1": 400, "f2": 1100, "f3": 2300, "pole_bandwidth": 100},
    "ȵ": {"type": "nasal", "place": "palatal", "f1": 350, "f2": 1500, "f3": 2800, "pole_bandwidth": 100},
    "l": {"type": "liquid", "place": "alveolar", "f1": 400, "f2": 1400, "f3": 2600},
    "r": {"type": "liquid", "place": "alveolar", "f1": 450, "f2": 1200, "f3": 1800},
    "j": {"type": "approximant", "place": "palatal", "f1": 300, "f2": 2200, "f3": 3000},
    "w": {"type": "approximant", "place": "labiovelar", "f1": 300, "f2": 1000, "f3": 2300},
    "ʷ": {"type": "labialization", "effect": "rounding"}, "ʰ": {"type": "aspiration", "effect": "burst"},
    "ʂ": {"type": "fricative", "voiced": False, "place": "retroflex", "center": 3500, "bandwidth": 1800},
    "ʐ": {"type": "fricative", "voiced": True, "place": "retroflex", "center": 3000, "bandwidth": 1800},
    "tʂ": {"type": "affricate", "stop": "t", "fricative": "ʂ"},
}

def saw_wave(t, pitch):
    phase = (t * pitch) % 1.0
    sig = np.where(phase < 0.5, 1 - phase / 0.5, - (phase - 0.5) / 0.5)
    return sig * 0.3 + 0.7 * np.sin(2 * np.pi * pitch * t)

def _resonator(signal, freq, bw, sr):
    if freq <= 0: return signal
    from scipy.signal import lfilter
    r = math.exp(-math.pi * bw / sr)
    theta = 2 * math.pi * freq / sr
    a1 = -2 * r * math.cos(theta); a2 = r * r; b0 = 1 - r
    return lfilter([b0], [1.0, a1, a2], signal)

def formant_filter(signal, f1, f2, f3, sr):
    output = signal.copy()
    for f, bw in [(f1, 80), (f2, 100), (f3, 150)]:
        output = _resonator(output, f, bw, sr)
    return output

def get_envelope(n, sr, attack=0.02, release=0.05):
    env = np.ones(n)
    a_len = min(int(sr * attack), n // 2)
    r_len = min(int(sr * release), n // 2)
    if a_len > 1: env[:a_len] = np.linspace(0, 1, a_len)
    if r_len > 1 and n > r_len: env[-r_len:] = np.linspace(1, 0, r_len)
    return env

def generate_noise(duration, center, bandwidth, sample_rate=SAMPLE_RATE):
    n = int(sample_rate * duration)
    noise = np.random.randn(n)
    from scipy.signal import butter, sosfilt
    try:
        low, high = max(100, center - bandwidth // 2), min(sample_rate // 2 - 1, center + bandwidth // 2)
        sos = butter(4, [low, high], btype='band', fs=sample_rate, output='sos')
        noise = sosfilt(sos, noise)
    except: pass
    return noise * 0.3

def generate_stop_burst(duration, noise_start, noise_end, sample_rate=SAMPLE_RATE):
    n = int(sample_rate * duration)
    noise = np.random.randn(n)
    from scipy.signal import butter, sosfilt
    try:
        center, bw = (noise_start + noise_end) / 2, noise_end - noise_start
        sos = butter(4, [max(100, center - bw//2), min(sample_rate//2-1, center + bw//2)], btype='band', fs=sample_rate, output='sos')
        noise = sosfilt(sos, noise)
    except: pass
    env = np.exp(-np.arange(n) / (n * 0.1))
    return noise * env * 0.5

def generate_vowel(f1, f2, f3, duration, pitch=130, sample_rate=SAMPLE_RATE):
    n = int(sample_rate * duration)
    t = np.arange(n) / sample_rate
    output = formant_filter(saw_wave(t, pitch), f1, f2, f3, sample_rate)
    return output * get_envelope(n, sample_rate) * 0.7

def generate_nasal(f1, f2, f3, duration, pitch=120, sample_rate=SAMPLE_RATE):
    n = int(sample_rate * duration)
    t = np.arange(n) / sample_rate
    output = formant_filter(saw_wave(t, pitch) * 0.5, f1, f2, f3, sample_rate)
    return output * get_envelope(n, sample_rate, 0.04, 0.06) * 0.5

def generate_liquid(f1, f2, f3, duration, pitch=125, sample_rate=SAMPLE_RATE):
    n = int(sample_rate * duration)
    t = np.arange(n) / sample_rate
    output = formant_filter(saw_wave(t, pitch), f1, f2, f3, sample_rate)
    return output * get_envelope(n, sample_rate, 0.02, 0.04) * 0.5

MULTI_CHAR_PHONEMES = ["tɕʰ", "tʂʰ", "tsʰ", "dʑ", "tɕ", "dʐ", "tʂ", "dʒ", "tʃ", "dz", "ts", "ʂ", "ʐ"]

def tokenize_ipa(ipa_str):
    ipa_str = ipa_str.strip()
    result, i = [], 0
    while i < len(ipa_str):
        matched = False
        for length in [3, 2, 1]:
            if i + length <= len(ipa_str):
                chunk = ipa_str[i:i+length]
                if chunk in MULTI_CHAR_PHONEMES:
                    result.append(chunk); i += length; matched = True; break
        if matched: continue
        result.append(ipa_str[i]); i += 1
    return result

def is_vowel(phoneme):
    return phoneme in "iyeɛæaɨəɐuoɔʌɑɒʉɯɤ" or (phoneme and phoneme[0] in "iyeɛæaɨəɐuoɔʌɑɒʉɯɤ")

def synth_with_formant(ipa_str, pitch=120):
    phonemes = tokenize_ipa(ipa_str)
    if not phonemes: return np.array([])
    audio_parts = []
    for i, ph in enumerate(phonemes):
        if ph in (' ', '　'):
            audio_parts.append(np.zeros(int(SAMPLE_RATE * 0.05))); continue
        is_final = True
        for next_ph in phonemes[i+1:]:
            if is_vowel(next_ph) or next_ph in ('j', 'w', 'ʷ', 'ʲ'):
                is_final = False; break
        if ph in CONSONANT_PARAMS:
            params = CONSONANT_PARAMS[ph]; ptype = params["type"]
            if is_final and ptype in ("stop", "fricative", "affricate", "nasal", "liquid", "approximant"):
                if ptype == "stop": audio_parts.append(np.zeros(int(SAMPLE_RATE * 0.03)))
                elif ptype == "nasal": audio_parts.append(generate_nasal(params["f1"], params["f2"], params["f3"], 0.06, pitch))
                elif ptype == "fricative": audio_parts.append(generate_noise(0.045, params["center"], params["bandwidth"]) * 0.5)
                elif ptype == "affricate": audio_parts.append(generate_noise(0.0375, 3500, 1800) * 0.3)
                elif ptype in ("liquid", "approximant"): audio_parts.append(generate_liquid(params["f1"], params["f2"], params["f3"], 0.045, pitch) * 0.5)
            else:
                if ptype == "stop": audio_parts.append(generate_stop_burst(0.0225, params["noise_start"], params["noise_end"]))
                elif ptype == "fricative": audio_parts.append(generate_noise(0.09, params["center"], params["bandwidth"]))
                elif ptype == "affricate":
                    if params["stop"] in CONSONANT_PARAMS:
                        sp = CONSONANT_PARAMS[params["stop"]]
                        audio_parts.append(generate_stop_burst(0.0225, sp["noise_start"], sp["noise_end"]))
                    if params["fricative"] in CONSONANT_PARAMS:
                        fp = CONSONANT_PARAMS[params["fricative"]]
                        audio_parts.append(generate_noise(0.06, fp["center"], fp["bandwidth"]))
                elif ptype == "nasal": audio_parts.append(generate_nasal(params["f1"], params["f2"], params["f3"], 0.09, pitch))
                elif ptype == "liquid": audio_parts.append(generate_liquid(params["f1"], params["f2"], params["f3"], 0.09, pitch))
                elif ptype == "approximant": audio_parts.append(generate_liquid(params["f1"], params["f2"], params["f3"], 0.075, pitch))
                elif ptype == "aspiration": audio_parts.append(generate_noise(0.0225, 3000, 2000) * 0.4)
                elif ptype == "labialization": audio_parts.append(generate_liquid(300, 1000, 2300, 0.015, pitch) * 0.3)
        elif is_vowel(ph):
            f1, f2, f3 = VOWEL_FORMANTS.get(ph, VOWEL_FORMANTS.get(ph[0], (500, 1500, 2500)))
            if i > 0 and phonemes[i-1] in CONSONANT_PARAMS:
                prev_params = CONSONANT_PARAMS[phonemes[i-1]]
                if prev_params.get("type") == "labialization" or ('ʷ' in str(phonemes[i-1])):
                    f2, f3 = int(f2 * 0.8), int(f3 * 0.9)
            audio_parts.append(generate_vowel(f1, f2, f3, 0.15, pitch))
    if not audio_parts: return np.array([])
    result = np.concatenate(audio_parts) if len(audio_parts) > 1 else audio_parts[0]
    if len(result) > 0 and np.max(np.abs(result)) > 0:
        result = result / np.max(np.abs(result)) * 0.8
    return result


# ============================================================
# 统一合成接口
# ============================================================

def synthesize_text(ipa_text, word_gap=0.08, pitch=130, tone_list=None):
    """统一合成接口：eSpeak-ng 优先，回退共振峰。返回 numpy 数组

    停顿处理策略：按标点分组为短语，每个短语整体交给 eSpeak-ng，
    短语之间在 numpy 层插入静音，不做音频切割。
    """
    if not ipa_text or not ipa_text.strip():
        return np.array([])

    ipa_parts = ipa_text.strip().split()

    # 按停顿标记分组为短语组
    phrases = []
    current = []
    for p in ipa_parts:
        if p == ".":
            if current:
                phrases.append(("phrase", current))
                current = []
            phrases.append(("pause", 0.4))
        elif p == ",":
            if current:
                phrases.append(("phrase", current))
                current = []
            phrases.append(("pause", 0.2))
        elif p not in ("?", ""):
            current.append(p)
    if current:
        phrases.append(("phrase", current))

    # 如果没有任何标点，当成一个整体
    if not phrases:
        if ipa_parts:
            phrases = [("phrase", [p for p in ipa_parts if p not in ("?", "")])]

    parts = []

    for typ, data in phrases:
        if typ == "pause":
            parts.append(np.zeros(int(SAMPLE_RATE * data)))
            continue

        # 合成一个短语
        espeak_audio = synth_with_espeak(data, pitch)
        if espeak_audio is not None and len(espeak_audio) > 0:
            parts.append(espeak_audio)
        else:
            # 回退到共振峰，scipy 异常已有保护
            try:
                phrase_audio = []
                for i, ipa in enumerate(data):
                    part = synth_with_formant(ipa, pitch)
                    if len(part) > 0:
                        phrase_audio.append(part)
                        if i < len(data) - 1:
                            phrase_audio.append(np.zeros(int(SAMPLE_RATE * word_gap)))
                if phrase_audio:
                    p = np.concatenate(phrase_audio)
                    if len(p) > 0 and np.max(np.abs(p)) > 0:
                        p = p / np.max(np.abs(p)) * 0.8
                    parts.append(p)
            except ImportError:
                pass

    if not parts:
        return np.array([])

    result = np.concatenate(parts) if len(parts) > 1 else parts[0]
    if len(result) > 0 and np.max(np.abs(result)) > 0:
        result = result / np.max(np.abs(result)) * 0.8
    return result


# ============================================================
# 工具函数
# ============================================================

def audio_to_wav_bytes(audio_array, sample_rate=SAMPLE_RATE):
    if len(audio_array) == 0: return b''
    audio_array = np.clip(audio_array, -1.0, 1.0)
    pcm = (audio_array * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def audio_to_base64(audio_array, sample_rate=SAMPLE_RATE):
    wav_bytes = audio_to_wav_bytes(audio_array, sample_rate)
    if not wav_bytes: return ""
    return base64.b64encode(wav_bytes).decode("ascii")


def audio_html_tag(base64_data, autoplay=False):
    autoplay_attr = " autoplay" if autoplay else ""
    return f'<audio controls{autoplay_attr} style="width:100%"><source src="data:audio/wav;base64,{base64_data}" type="audio/wav"></audio>'


if __name__ == "__main__":
    espeak_available = synth_with_espeak(["ten"]) is not None
    print(f"eSpeak-ng: {'OK' if espeak_available else 'not found'}")
    for test in ["ten", "Jit", "ten dis"]:
        audio = synthesize_text(test, pitch=130)
        if len(audio) > 0:
            print(f"  {test}: {len(audio)} samples ({len(audio)/22050:.2f}s)")


ESPEAK_AVAILABLE = False  # set to True on Windows after installing espeak-ng
