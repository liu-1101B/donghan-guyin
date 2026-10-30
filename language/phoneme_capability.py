# -*- coding: utf-8 -*-
"""language/phoneme_capability.py — IPA → 合成器能力矩阵 (v5 第三阶段)

拟音"查得到"不等于"播得出"。本模块回答：**一条读法交给合成器，
哪些音素会发声、哪些会被丢掉、哪些只是近似**，让 UI 能显式报告
每一档降级，而不是静默吞音。

两级合成引擎（见 sound_synth.py）：

- eSpeak-ng：``preprocess_ipa()`` 把一小撮 IPA 符号显式映射成音素别名
  （:data:`ESPEAK_IPA_MAP`，与 sound_synth 共享同一份表）；**未处理的
  符号原样透传**，而 eSpeak-ng 的 zh 声音实测会丢掉其中大部分。
- 共振峰回退：``synth_with_formant()`` 只能发音
  ``VOWEL_FORMANTS`` / ``CONSONANT_PARAMS`` 里的符号，其余静默丢弃。
  （eSpeak 整体失败时才启用，所以它是"备用引擎"指标，不是主路径。）

分类依据两类证据，不做猜测：

1. **静态**：是否在 ``ESPEAK_IPA_MAP``（ok）、是否 ASCII（ok，字母按
   音素/字母读取；非字母 ASCII 记为 junk，属数据质量问题）。
2. **实测**（捆绑版 eSpeak-ng 1.52，``-v zh``，2026-10-30 逐符号合成
   并测量非零采样数；探针脚本 .probe_espeak.py / .probe_espeak2.py，
   结果已冻结进下面的集合）：
   - 非 IPA 拉丁字母（ç ȶ ȡ ɖ ʈ ɳ ɣ ɱ ɲ ɟ ʃ ʅ ʎ ʒ ɡ ɪ ɽ 及
     ä å ś ź ḍ ṇ ṣ ṭ ẓ ậ）**全部静默丢弃** → :data:`SILENT_FROZEN`。
     注意 ``ɡ``（小写 G 变体）与 ASCII ``g`` 不同，前者被丢。
   - 带重音的常见拉丁元音（â ă ï û ü 等）**发声但按基字母读**，
     重音/音色丢失 → :data:`APPROX_FROZEN`。
   - 分解型组合附加符（如 i+U+030C、u+U+0302，李方桂/王力方案的
     带调元音）：基字母发声、附加符丢失 → 按基字母计 :data:`approx`。
   - "发声"≠语音正确：矩阵只保证该段有声音，不保证听感正确，
     所以统一标 ``approx`` 而不是 ``ok``。

本模块**不修改、不规范化任何拟音数据**：NFC 只用于查表键，
输入字符串原样返回。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Optional, Tuple

# ------------------------------------------------------------
# eSpeak 映射表（sound_synth.preprocess_ipa 的单一数据源）
# ------------------------------------------------------------
# 顺序即应用顺序，必须与历史行为一致（sound_synth 里逐个 replace 的顺序）。
ESPEAK_IPA_MAP = {
    "ʰ": "h",
    "ʷ": "w",
    "ʲ": "j",
    "ɨ": "1",
    "ə": "@",
    "ɛ": "E",
    "ɔ": "O",
    "ɑ": "A",
    "ɐ": "V",
    "ɒ": "Q",
    "æ": "{",
    "ŋ": "N",
    "ȵ": "J",
    "ʑ": "Z",
    "ɕ": "S",
    "ʂ": "s`",
    "ʐ": "z`",
    "ʔ": "?",
    "ɦ": "h",
    "ʌ": "V",
    "ɤ": "7",
    "ɯ": "u",
    "ʉ": "u",
}

# ------------------------------------------------------------
# 实测冻结集合（eSpeak-ng 1.52 -v zh，2026-10-30）
# ------------------------------------------------------------
# 实测合成 [[X]] 非零采样数为 0 的符号（NFC 单字符键）。
SILENT_FROZEN = frozenset(
    "ȶȡɖʈɳɣɱɲɟʃʅʎʒɡɪɽ"   # IPA 辅音/元音：全部静默丢弃
    "çäåśźḍṇṣṭẓậ"            # 带符拉丁字母：全部静默丢弃
)

# 实测发声、但按基字母读（重音/音色丢失）的预组合符号（NFC 单字符键）。
# 分解型写法（基字母 + 组合附加符）在 classify_symbol 里按
# "ascii 基字母 + combining 附加符"自然归入 approx，不依赖此表。
APPROX_FROZEN = frozenset("âăïûüíǐǎĕ")

# 组合附加符 Unicode 区间（Mn/Me/Mc 类）
_COMBINING_LO, _COMBINING_HI = 0x0300, 0x036F

# 状态常量
OK = "ok"            # 引擎会按预期发音（映射表内 / ASCII）
APPROX = "approx"    # 有声音，但重音/音色丢失（近似）
SILENT = "silent"    # 实测被引擎静默丢弃（音节缺段）
UNTESTED = "untested"  # 未冻结、未实测（数据里不应再出现）
JUNK = "junk"        # ASCII 非字母数字（标点/换行），非语音内容
COMBINING = "combining"  # 单独的附加符，依附前一字符


def _nfc(ch: str) -> str:
    return unicodedata.normalize("NFC", ch)


def classify_symbol(ch: str) -> str:
    """对单个字符做 eSpeak 层能力分类（只查表，不改字符串）。"""
    if ch in ESPEAK_IPA_MAP:
        return OK
    if ch.isascii():
        return OK if ch.isalnum() else JUNK
    cp = ord(ch)
    if _COMBINING_LO <= cp <= _COMBINING_HI or \
            unicodedata.category(ch).startswith("M"):
        return COMBINING
    key = _nfc(ch)
    if key in SILENT_FROZEN:
        return SILENT
    if key in APPROX_FROZEN:
        return APPROX
    return UNTESTED


# 状态严重度：数值越大越差（用于取 token 内最差的字符状态）
_SEVERITY = {OK: 0, COMBINING: 1, APPROX: 1, UNTESTED: 2, SILENT: 3, JUNK: 4}


def _classify_token(tok: str) -> str:
    """token 级 eSpeak 状态 = 其中字符的最差状态。

    - 含 silent 字符 → 整个 token 缺段（如 "tɣ" 里的 ɣ）
    - 含 untested → 无法保证
    - 含 combining/approx → 近似（附加符/重音丢失，基音保留）
    - 纯 junk → junk（无语音内容，不参与级别计算）
    """
    statuses = [classify_symbol(c) for c in tok]
    worst = max(statuses, key=lambda s: _SEVERITY[s])
    if worst == JUNK:
        return JUNK
    if worst in (SILENT, UNTESTED, APPROX):
        return worst
    if COMBINING in statuses:
        return APPROX
    return OK


def _formant_status(tok: str) -> str:
    """token 级共振峰引擎状态（直接读 sound_synth 的真实表，防漂移）。"""
    from sound_synth import CONSONANT_PARAMS, is_vowel  # 惰性导入防循环
    if tok in CONSONANT_PARAMS or is_vowel(tok):
        return OK
    return SILENT


@dataclass(frozen=True)
class TokenCapability:
    token: str
    espeak: str   # ok / approx / silent / untested / junk
    formant: str  # ok / silent


@dataclass(frozen=True)
class IpAssessment:
    """一条 IPA 读法在两级引擎下的能力评估。"""
    ipa: str
    tokens: Tuple[TokenCapability, ...]
    espeak_level: str    # full / approx / partial / untested / silent
    formant_level: str   # full / partial / silent
    dropped_tokens: Tuple[str, ...] = field(default=())     # eSpeak 缺段的 token
    approx_tokens: Tuple[str, ...] = field(default=())      # 近似（音色丢失）的 token
    junk_chars: Tuple[str, ...] = field(default=())         # 数据质量：非语音 ASCII

    @property
    def fully_synth(self) -> bool:
        """eSpeak 主路径能否无降级发出所有段。"""
        return self.espeak_level == "full"

    @property
    def any_segment_dropped(self) -> bool:
        return bool(self.dropped_tokens)


def assess_ipa(ipa: str) -> IpAssessment:
    """评估一条读法。空字符串抛 ValueError（缺陷行应先行过滤）。

    eSpeak 主路径级别：
    - 有 token 缺段 → partial（音节缺音，最坏）
    - 有未实测 token → untested
    - 有近似 token → approx（音色/重音丢失，段完整）
    - 全部 ok → full
    （junk token 无语音内容，不参与级别，但记录在 junk_chars。）

    共振峰回退级别：全部 token 可发音 → full；一个都不能 → silent；
    其余 → partial。
    """
    from sound_synth import tokenize_ipa  # 惰性导入防循环
    if not ipa or not ipa.strip():
        raise ValueError("empty ipa")

    tokens = []
    dropped, approx, junk = [], [], []
    formant_ok_count = 0
    phonetic_count = 0
    espeak_levels = []

    for tok in tokenize_ipa(ipa):
        if tok in (" ", "\u3000"):
            continue
        e_status = _classify_token(tok)
        f_status = _formant_status(tok)
        tokens.append(TokenCapability(tok, e_status, f_status))
        if e_status == JUNK:
            junk.extend(tok)
            continue
        phonetic_count += 1
        espeak_levels.append(e_status)
        if f_status == OK:
            formant_ok_count += 1
        if e_status == SILENT:
            dropped.append(tok)
        elif e_status == APPROX:
            approx.append(tok)

    if phonetic_count == 0:
        espeak_level = "silent"
    elif any(l == SILENT for l in espeak_levels):
        espeak_level = "partial"
    elif any(l == UNTESTED for l in espeak_levels):
        espeak_level = "untested"
    elif any(l == APPROX for l in espeak_levels):
        espeak_level = "approx"
    else:
        espeak_level = "full"

    if phonetic_count == 0:
        formant_level = "silent"
    elif formant_ok_count == phonetic_count:
        formant_level = "full"
    elif formant_ok_count == 0:
        formant_level = "silent"
    else:
        formant_level = "partial"

    return IpAssessment(
        ipa=ipa,
        tokens=tuple(tokens),
        espeak_level=espeak_level,
        formant_level=formant_level,
        dropped_tokens=tuple(dropped),
        approx_tokens=tuple(approx),
        junk_chars=tuple(junk),
    )


# ------------------------------------------------------------
# 体系级覆盖报告
# ------------------------------------------------------------

def system_capability_report(system_id: str,
                             example_limit: int = 12) -> dict:
    """某学者体系全部读法在两级引擎下的能力统计。

    返回 dict（字段全部可 JSON 序列化，供 UI 直接展示）：

    - characters / readings / no_ipa_records
    - espeak_full / espeak_approx / espeak_partial / espeak_untested
      / espeak_silent：按读法（记录）计数的 eSpeak 主路径级别
    - formant_full / formant_partial / formant_silent：回退引擎级别
    - dropped_symbols {符号: 记录数}：含被 eSpeak 静默丢弃音素的读法数
    - approx_symbols {符号: 记录数}：含近似音素（重音/附加符丢失）的读法数
    - anomalous_chars {字符: 计数}：IPA 值里的非语音 ASCII（数据质量）
    - characters_clean：eSpeak 全读法 full 的字数
    - characters_with_gaps / gap_examples：有缺段读法的字数与例字
    """
    from language.history.sinica_scholar_data import (
        SCHOLAR_SYSTEMS_ALL, _index_by_char)
    if system_id not in SCHOLAR_SYSTEMS_ALL:
        raise KeyError(f"unknown system_id: {system_id!r}")
    system_name = SCHOLAR_SYSTEMS_ALL[system_id]

    idx = _index_by_char(system_id)
    level_counts = {"full": 0, "approx": 0, "partial": 0,
                    "untested": 0, "silent": 0}
    formant_counts = {"full": 0, "partial": 0, "silent": 0}
    dropped_symbols: dict = {}
    approx_symbols: dict = {}
    anomalous: dict = {}
    readings = 0
    no_ipa = 0
    chars_with_gap = set()

    for ch, recs in idx.items():
        char_has_gap = False
        for rec in recs:
            if not rec.ipa:
                no_ipa += 1
                continue
            readings += 1
            a = assess_ipa(rec.ipa)
            level_counts[a.espeak_level] += 1
            formant_counts[a.formant_level] += 1
            if a.dropped_tokens:
                char_has_gap = True
            for tok in a.dropped_tokens:
                for c in tok:
                    k = _nfc(c)
                    if classify_symbol(c) == SILENT:
                        dropped_symbols[k] = dropped_symbols.get(k, 0) + 1
            for tok in a.approx_tokens:
                for c in tok:
                    k = _nfc(c)
                    if classify_symbol(c) in (APPROX, COMBINING):
                        approx_symbols[k] = approx_symbols.get(k, 0) + 1
            for c in a.junk_chars:
                anomalous[c] = anomalous.get(c, 0) + 1
        if char_has_gap:
            chars_with_gap.add(ch)

    examples = sorted(chars_with_gap)[:example_limit]
    return {
        "system_id": system_id,
        "system_name": system_name,
        "characters": len(idx),
        "readings": readings,
        "no_ipa_records": no_ipa,
        "espeak_full": level_counts["full"],
        "espeak_approx": level_counts["approx"],
        "espeak_partial": level_counts["partial"],
        "espeak_untested": level_counts["untested"],
        "espeak_silent": level_counts["silent"],
        "formant_full": formant_counts["full"],
        "formant_partial": formant_counts["partial"],
        "formant_silent": formant_counts["silent"],
        "dropped_symbols": dict(sorted(dropped_symbols.items(),
                                       key=lambda kv: -kv[1])),
        "approx_symbols": dict(sorted(approx_symbols.items(),
                                      key=lambda kv: -kv[1])),
        "anomalous_chars": dict(sorted(anomalous.items(),
                                       key=lambda kv: -kv[1])),
        "characters_clean": len(idx) - len(chars_with_gap),
        "characters_with_gaps": len(chars_with_gap),
        "gap_examples": examples,
    }


# 供 UI 展示用的级别中文说明（不含具体数字，数字由报告提供）
ESPEAK_LEVEL_ZH = {
    "full": "全部音素可合成",
    "approx": "可合成，个别音素为近似（重音/音色丢失）",
    "partial": "可合成，但含被引擎静默丢弃的音素（音节缺段）",
    "untested": "含未实测音素，合成结果不保证",
    "silent": "整条读法无可合成音素",
}
