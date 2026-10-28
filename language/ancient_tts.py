"""
language/ancient_tts.py
汉字 → 东汉 IPA → 古韵 WAV

从 guyun_app.py 抽离的 IPA 组装逻辑（不修改原文件），
并增加覆盖率统计：已收录字数 / 拼音近似字数。
"""
import re
import unicodedata
from dataclasses import dataclass, field

from phonology_db import lookup_char, EASTERN_HAN_DB
from sound_synth import synthesize_text, audio_to_wav_bytes, SAMPLE_RATE

try:
    from pypinyin import pinyin as _pypinyin, Style
    PYPINYIN_AVAILABLE = True
except ImportError:
    PYPINYIN_AVAILABLE = False


def get_pinyin_fallback(char):
    """现代拼音（去声调数字），未收录字的近似音入口"""
    if not PYPINYIN_AVAILABLE:
        return None
    try:
        return re.sub(r'[0-9]', '', _pypinyin(char, style=Style.TONE3)[0][0])
    except Exception:
        return None


_INIT_MAP = {'b': 'p', 'p': 'pʰ', 'm': 'm', 'f': 'f', 'd': 't', 't': 'tʰ',
             'n': 'n', 'l': 'l', 'g': 'k', 'k': 'kʰ', 'h': 'h', 'j': 'tɕ',
             'q': 'tɕʰ', 'x': 'ɕ', 'zh': 'tʂ', 'ch': 'tʂʰ', 'sh': 'ʂ',
             'r': 'ȵ', 'z': 'ts', 'c': 'tsʰ', 's': 's', 'y': 'j', 'w': 'ʔ'}
_FINAL_MAP = {'iang': 'iaŋ', 'uang': 'uaŋ', 'iong': 'yuŋ', 'uai': 'uai',
              'ang': 'ɑŋ', 'eng': 'əŋ', 'ing': 'iŋ', 'ong': 'uŋ',
              'ian': 'ian', 'uan': 'uan', 'iao': 'iau', 'iou': 'iou',
              'ai': 'ai', 'ei': 'ei', 'ui': 'uei', 'ao': 'au', 'ou': 'ou',
              'iu': 'iou', 'an': 'an', 'en': 'ən', 'in': 'in', 'un': 'uən',
              'vn': 'yn', 'ia': 'ia', 'ie': 'ie', 'ua': 'ua', 'uo': 'uo',
              've': 'ye', 'van': 'yan', 'ue': 'ye', 'a': 'a', 'o': 'o',
              'e': 'ə', 'i': 'i', 'u': 'u', 'v': 'y'}
_INIT_LIST = ['zh', 'ch', 'sh', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l',
              'g', 'k', 'h', 'j', 'q', 'x', 'r', 'z', 'c', 's', 'y', 'w']


def estimate_ipa_from_pinyin(py):
    """现代拼音 → 近似的东汉风格 IPA（仅作未收录字回退）"""
    if not py:
        return None
    init_ipa, rest = '', py
    for init in _INIT_LIST:
        if py.startswith(init):
            init_ipa = _INIT_MAP.get(init, '')
            rest = py[len(init):]
            break
    final_ipa = rest
    for f_len in range(5, 0, -1):
        if len(rest) >= f_len and rest[:f_len] in _FINAL_MAP:
            final_ipa = _FINAL_MAP[rest[:f_len]]
            break
    return f"{init_ipa}{final_ipa}" if (init_ipa or final_ipa) else None


def _is_cjk(ch):
    return '一' <= ch <= '鿿' or '㐀' <= ch <= '䶿'


@dataclass
class AncientResult:
    ipa_text: str
    coverage: int          # 已收录字数
    approx: int            # 拼音近似字数
    unknown: list = field(default_factory=list)

    @property
    def total(self):
        return self.coverage + self.approx

    @property
    def coverage_pct(self):
        return round(100 * self.coverage / self.total, 1) if self.total else 0.0


def text_to_ipa(classical: str) -> AncientResult:
    """文言文 → IPA 序列（标点转停顿），并统计覆盖率"""
    ipa_parts, unknown = [], []
    coverage = approx = 0
    for ch in classical:
        if ch in '。！？':
            ipa_parts.append('.')
        elif ch in '，、；：':
            ipa_parts.append(',')
        elif ch.strip() and not _is_cjk(ch):
            continue
        elif ch.strip():
            data = lookup_char(ch)
            if data:
                coverage += 1
            else:
                py = get_pinyin_fallback(ch)
                est = estimate_ipa_from_pinyin(py) if py else None
                if est:
                    approx += 1
                    data = {'ipa': est}
                else:
                    unknown.append(ch)
                    continue
            ipa_parts.append(data['ipa'])
        # 引号括号等直接跳过
    # 过滤含中文字符的非法片段
    clean = [p for p in ipa_parts
             if not any(_is_cjk(c) for c in p)]
    return AncientResult(
        ipa_text=' '.join(clean),
        coverage=coverage,
        approx=approx,
        unknown=unknown,
    )


def synthesize_ancient(classical: str, pitch: int = 130,
                       speed: float = 1.0) -> tuple:
    """文言文 → (WAV bytes, AncientResult)。空文本返回 (b'', result)

    pitch: 基频 Hz（音色高低）
    speed: 语速倍率，1.0 正常；<1 更慢（字间停顿加大），>1 更快
    """
    result = text_to_ipa(classical)
    if not result.ipa_text.strip():
        return b'', result
    # 语速 → 字间停顿：正常 0.08s，放慢到 0.20s，加快到 0.03s
    word_gap = max(0.03, min(0.20, 0.08 / max(0.4, speed)))
    audio = synthesize_text(result.ipa_text, word_gap=word_gap, pitch=pitch)
    if audio is None or len(audio) == 0:
        return b'', result
    return audio_to_wav_bytes(audio, SAMPLE_RATE), result


def db_coverage(classical: str) -> dict:
    """统计一段文字在音韵库中的覆盖情况（不合成）"""
    r = text_to_ipa(classical)
    return {
        'total': r.total,
        'covered': r.coverage,
        'approx': r.approx,
        'pct': r.coverage_pct,
        'unknown': r.unknown,
    }
