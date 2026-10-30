# -*- coding: utf-8 -*-
"""language/polyphone.py
多音字词级选音（阶段 4 · 块 3）。

学者式 Sinica 拟音表没有声调字段，一个多音字可能对应多条不同 IPA 行
（如 行 在王力系统有 ɣɑŋ / ɣɐŋ 两值）。本模块用**纯经验**的三步法
从候选行中挑一条，绝不编造读音——IPA 永远来自学者表本身：

1. **jieba** 对上下文分词，找到包含目标字的词；
2. **pypinyin**（词级多音字消歧）给出该字在词中的现代声调 1–4，
   映射到中古调类：1/2 → {平}，3 → {上, 入}，4 → {去, 入}；
3. 取该字的广韵音韵地位（``qieyun_data`` 表，用
   ``eastern_mc_correspondence.parse_position_description`` 解析），
   只保留属于该调类的地位；
4. **经验映射**（每体系懒加载、lru_cache）：对同时出现在广韵表与
   学者表中、且学者表恰有一条非 suspect 带 IPA 行的「无歧义字」，
   按 (地位去声调) → (字, 声调, IPA) 投票。确认规则（每个地位键）：
   本调类内投票一致 → 取该值；否则全体（任意调）投票一致才取。
   不一致的键不产生确认值。
5. 确认值须与该字非 suspect 行中**恰好一个** distinct IPA 相等 →
   选中该行（``method="empirical"``）；
6. 否则**不可判定** → 用首条非 suspect 行（``method="fallback_first"``），
   note 逐条写明卡在哪一步，不猜测。

依赖缺失时的诚实降级：无 jieba → 按单字处理并标注；无 pypinyin →
声调不可判定（直接走 fallback）；无 opencc → 繁简转换退化为原字。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Tuple

try:
    from opencc import OpenCC
except ImportError:  # pragma: no cover - 环境兜底
    OpenCC = None

try:
    import jieba
except ImportError:  # pragma: no cover
    jieba = None

try:
    from pypinyin import pinyin as _pypinyin, Style as _PinyinStyle
except ImportError:  # pragma: no cover
    _pypinyin = None
    _PinyinStyle = None

from language.history.eastern_mc_correspondence import parse_position_description
from language.history.qieyun_data import load_qieyun_positions, lookup_qieyun_positions
from language.history.sinica_scholar_data import (
    SCHOLAR_SYSTEMS_ALL,
    _index_by_char,
    lookup_scholar_reading,
)

#: 现代声调 → 中古调类（上/去/入 在 3、4 声间无法再分，取并集）
MODERN_TO_TONE_CLASS = {
    1: frozenset({"平"}),
    2: frozenset({"平"}),
    3: frozenset({"上", "入"}),
    4: frozenset({"去", "入"}),
}
_TONE_CLASS_NAMES = {
    frozenset({"平"}): "平声",
    frozenset({"上", "入"}): "上/入声",
    frozenset({"去", "入"}): "去/入声",
}

JIEBA_AVAILABLE = jieba is not None
PYPINYIN_AVAILABLE = _pypinyin is not None


def segment(text: str) -> list:
    """jieba 分词；jieba 缺失时退化为逐字（调用方按 note 自行标注）。"""
    text = str(text)
    if not text:
        return []
    if JIEBA_AVAILABLE:
        return [w for w in jieba.cut(text) if w]
    return list(text)


@lru_cache(maxsize=1)
def _cc():
    if OpenCC is None:
        return None
    return OpenCC("s2t")


def to_traditional(text: str) -> str:
    """s2t 繁简转换；opencc 缺失时原样返回。"""
    cc = _cc()
    if cc is None:
        return str(text)
    return cc.convert(str(text))


@lru_cache(maxsize=None)
def _empirical_votes(system_id: str) -> Tuple[dict, int]:
    """(votes, voted_chars)。

    votes: (声母, 开合, 等, 重纽, 韵) → ((字, 声调, IPA), ...)
    只有「无歧义字」（学者表恰一条非 suspect 带 IPA 行）参与投票；
    多行字自身的 行↔地位 配对是模糊的，不参与。
    """
    if system_id not in SCHOLAR_SYSTEMS_ALL:
        raise KeyError(system_id)
    si = _index_by_char(system_id)
    votes: dict = {}
    voted_chars = 0
    for head, records in load_qieyun_positions().items():
        sins = si.get(head)
        if not sins:
            continue
        clean = [r for r in sins if not r.suspect and r.ipa]
        if len(clean) != 1:
            continue
        voted_chars += 1
        r = clean[0]
        for rec in records:
            for p in parse_position_description(rec.position_description):
                votes.setdefault(p.key[:-1], []).append((head, p.sheng, r.ipa))
    return votes, voted_chars


def _confirm(votes: dict, keys: list, tone_class: frozenset) -> set:
    """对一批地位键返回确认 IPA 值集合（可能为空）。

    每键规则：本调类内投票一致 → 取该值；否则全体投票一致才取。
    """
    out = set()
    for k in keys:
        vs = votes.get(k)
        if not vs:
            continue
        in_cls = [ipa for _, sheng, ipa in vs if sheng in tone_class]
        if in_cls:
            if len(set(in_cls)) == 1:
                out.add(in_cls[0])
        else:
            allv = [ipa for _, _, ipa in vs]
            if len(set(allv)) == 1:
                out.add(allv[0])
    return out


def _pos_text(p) -> str:
    return (f"{p.shengmu}{p.kaihhe or ''}{p.deng or ''}"
            f"{'重纽' if p.chongniu else ''}{p.chongniu or ''}"
            f"{p.yun}{p.sheng}")


def word_tone(character: str, context: Optional[str],
              word: Optional[str] = None) -> Tuple[Optional[str], Optional[int], str]:
    """(词, 现代声调 1-4 或 None, 说明)。

    word 显式给定（text_to_ipa 预切分传入）时不再分词；
    无上下文时按单字常读处理（说明里标注）。
    """
    if not PYPINYIN_AVAILABLE:
        return word, None, "pypinyin 不可用，现代声调不可判定"
    ctx = context or ""
    if word is None:
        if ctx and character in ctx:
            idx = ctx.index(character)
            pos = 0
            for w in segment(ctx):
                nxt = pos + len(w)
                if pos <= idx < nxt:
                    word = w
                    break
                pos = nxt
            if word is None:
                word = character
        else:
            word = character
    try:
        readings = _pypinyin(word, style=_PinyinStyle.TONE3)
    except Exception:
        return word, None, "pypinyin 解析失败"
    if character not in word:
        return word, None, "词中找不到目标字"
    i = word.index(character)
    if i >= len(readings) or not readings[i]:
        return word, None, "pypinyin 未给出该字读音"
    rd = readings[i][0]
    if not rd or not rd[-1].isdigit():
        return word, None, f"拼音 {rd!r} 无声调数字"
    tone = int(rd[-1])
    if tone not in MODERN_TO_TONE_CLASS:
        return word, None, f"轻声（{rd}），不可判定"
    note = "按单字常读" if (not ctx or character not in ctx) else ""
    return word, tone, note


@dataclass(frozen=True)
class ReadingSelection:
    """一次选音的完整结果（含诚实的失败说明）。"""
    character: str            # 输入字（可为简体）
    traditional: str          # s2t 查表键
    system_id: str
    selected: Optional[object]   # ScholarReading | None（suspect_only/no_records 为 None）
    candidates: tuple         # 全部非 suspect 行
    word: Optional[str]       # 上下文词（未走声调路径时为 None）
    modern_tone: Optional[int]
    tone_class: frozenset     # 声调未定 → frozenset()
    positions: tuple          # 属于该调类的 ParsedPosition
    method: str               # single|empirical|fallback_first|suspect_only|no_records
    note: str


def select_reading(character: str, context: Optional[str], system_id: str,
                   word: Optional[str] = None) -> ReadingSelection:
    """在学者体系内为多音字选定一条拟音行（见模块 docstring）。"""
    if not isinstance(character, str) or len(character) != 1:
        raise ValueError("select_reading expects exactly one character")
    if system_id not in SCHOLAR_SYSTEMS_ALL:
        raise KeyError(system_id)
    trad = to_traditional(character)
    records = lookup_scholar_reading(trad, system_id)
    if not records:
        return ReadingSelection(character, trad, system_id, None, (),
                                None, None, frozenset(), (), "no_records",
                                f"{trad} 在 {system_id} 表无条目")
    clean = tuple(r for r in records if not r.suspect)
    if not clean:
        first = records[0]
        return ReadingSelection(character, trad, system_id, None, tuple(records),
                                None, None, frozenset(), (), "suspect_only",
                                "全部行均 suspect：" + (first.note or "见源表备注"))
    if len(clean) == 1:
        return ReadingSelection(character, trad, system_id, clean[0], clean,
                                None, None, frozenset(), (), "single", "")
    # —— 多行：走经验选音 ——
    w, tone, tone_note = word_tone(character, context, word)
    tone_class = MODERN_TO_TONE_CLASS.get(tone, frozenset())
    positions = ()
    if tone_class:
        positions = tuple(
            p for rec in lookup_qieyun_positions(trad)
            for p in parse_position_description(rec.position_description)
            if p.sheng in tone_class
        )
    confirmed = set()
    if tone_class and positions:
        votes, _ = _empirical_votes(system_id)
        confirmed = _confirm(votes, [p.key[:-1] for p in positions], tone_class)
        matched = {r.ipa for r in clean if r.ipa in confirmed}
        if len(matched) == 1:
            sel = next(r for r in clean if r.ipa in matched)
            pos_str = "、".join(dict.fromkeys(_pos_text(p) for p in positions))
            note = (f"词「{w}」现代调 {tone} → {_TONE_CLASS_NAMES[tone_class]}；"
                    f"音韵地位 {pos_str}；同类字一致读 {sel.ipa}")
            if tone_note:
                note += "（" + tone_note + "）"
            return ReadingSelection(character, trad, system_id, sel, clean,
                                    w, tone, tone_class, positions, "empirical", note)
    # —— 不可判定：首条回退，写明原因 ——
    reasons = []
    if tone_note:
        reasons.append(tone_note)
    if tone is None:
        reasons.append("现代声调不可判定")
    elif not positions:
        reasons.append("广韵表无属该调类的地位")
    elif not confirmed:
        reasons.append("该音韵地位类无一致读法")
    else:
        reasons.append("一致读法 " + "、".join(sorted(confirmed)) + " 与本字各行均不相符")
    sel = clean[0]
    note = (f"多音字（{len(clean)} 条）未能确定（{'；'.join(reasons)}）；"
            f"按首条 {sel.ipa} 读，不作调类推断")
    return ReadingSelection(character, trad, system_id, sel, clean,
                            w, tone, tone_class, positions, "fallback_first", note)
