"""接入 Sinica CCR 里中古与上古各学者拟音的逐字数据。

数据来源：中央研究院「漢字構形資料庫」（xiaoxue.iis.sinica.edu.tw），
已随仓库打包在 data/historical/sinica_ccr_import/ 下。许可见该包的 manifest（PDM）。

- 中古（dataset_id=sinica_ccr_middle_chinese）：6 家学者表，
  字段 字號/字/聲母/韻母/備註。
- 上古（dataset_id=sinica_ccr_old_chinese）：5 家先秦表，
  字段 字號/字/韻部/聲母/韻母/備註（001 高本漢表无「韻部」栏）。
  同包里的 006/007 兩漢表是韵部资料（historical_rhyme_group），
  不是逐字拟音，按 system 名过滤后天然不接入。

边界说明（重要）：
- 上游**没有声调字段**。这里不推测、不补全，tone 恒为 None。
- 零声母记号：王力表用 "0"；李方桂表用 U+0387（希臘 anoteleia 点，下称「点」），
  点后还可带介音（如「·w」）。「0」和「·」按无辅音处理，「·w」的 w 并入 IPA。
- 王力/董同龢上古表的韵母可能带「ǐ」前缀（表上声），属上游记音，本模块不改写。
- ȶ / ȡ / ȣ / ɽ 等是各方案惯用符号，不是通用 IPA；能否送进合成器属于
  「音素能力矩阵」的问题（v5 第三阶段），本模块不做替换。
- 因此这些记录是**可追溯的学者拟音**，不等于已验证可播的读音。

上游缺陷的处理（不静默丢弃，全部计数并暴露）：
- 聲母列以元音开头 → 上游把韵母值填进了聲母列（错位）。
- 聲母列含汉字 → 上游把韵部名填进了聲母列（错位，上古王力表 4 行）。
- 聲母列只剩送氣符（如单独的 ʰ）→ 基音丢失（上古高本漢表 8 行）。
- 聲母/韻母是 HTML 实体文本（如 "&#611"）→ 机械解码为对应 Unicode 字符
  （&#611 → U+0263 ȣ、&#609 → U+0261 ȡ），并在记录备注里说明原值。
- 声母为全角字母（如「ｐ」）→ 机械还原为半角。
- 聲母/韻母为 "?" → 上游表示未知，按空缺处理（韵母空缺则该行跳过并计数）。
- 韵母为空 → 跳过并计数（上古高本漢表 530 行 + 5 行「?」）。
错位/缺陷的行**保留在数据里**（ipa 置空、suspect=True），绝不静默删除。
"""
from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BUNDLE_PATH = (Path(__file__).resolve().parents[2] / "data" / "historical"
                / "sinica_ccr_import" / "sinica_ccr_records.jsonl.gz")

DATASET_MIDDLE_CHINESE = "sinica_ccr_middle_chinese"
DATASET_OLD_CHINESE = "sinica_ccr_old_chinese"

# system_id -> Sinica 的 system 字段（中古 6 家）
SCHOLAR_SYSTEMS = {
    "wangli_mc": "王力系統",
    "dongtonghe_mc": "董同龢系統",
    "zhoufagao_mc": "周法高系統",
    "lifanggui_mc": "李方桂系統",
    "chenxinxiong_mc": "陳新雄系統",
    "karlgren_mc": "高本漢系統",
}

# 先秦（上古）5 家。Sinica 的 system 字段名与中古相同（如「王力系統」），
# 所以定位必须按 (dataset_id, system 名)，不能只按名字。
SCHOLAR_SYSTEMS_OLD = {
    "karlgren_oc": "高本漢系統",
    "wangli_oc": "王力系統",
    "dongtonghe_oc": "董同龢系統",
    "zhoufagao_oc": "周法高系統",
    "lifanggui_oc": "李方桂系統",
}

SCHOLAR_SYSTEMS_ALL = {**SCHOLAR_SYSTEMS, **SCHOLAR_SYSTEMS_OLD}

# 同一数据包里另有「时代韵部资料」（按时代分韵部，不是逐字拟音，，
# 韻母为空），接入时不要把它当拟音处理。
NOT_A_RECONSTRUCTION = {"时代韵部资料"}


def system_dataset(system_id: str) -> str:
    """system_id 对应的数据集（_oc 后缀 → 上古）。"""
    if system_id in SCHOLAR_SYSTEMS_OLD:
        return DATASET_OLD_CHINESE
    if system_id in SCHOLAR_SYSTEMS:
        return DATASET_MIDDLE_CHINESE
    raise KeyError(f"unknown Sinica scholar system: {system_id}")


@dataclass(frozen=True, slots=True)
class ScholarReading:
    """某位学者对单个字的拟音片段。"""

    character: str
    system_id: str
    system_name: str
    initial: str
    final: str
    ipa: str
    source_workbook: str = ""
    source_sheet: str = ""
    source_row: int = 0
    source_sha256: str = ""
    license_mark: str = ""
    note: str = ""
    suspect: bool = False
    rhyme_group: str = ""
    upstream_note: str = ""

    @property
    def has_initial(self) -> bool:
        """上游用 ""、"0"（王力）或「·」（李方桂，U+0387）表示零声母。"""
        return bool(self.initial) and not _is_zero_initial(self.initial)


# 声母只可能是辅音（含 j/w 这类半元音）外加零声母记号。
# 源表里有若干行把韵母值填进了聲母列（中古王力 13 行、周法高 5 行；
# 上古王力 4 行），拼出来的 IPA 会是假的，所以必须识别出来并置空。
#
# 判据用「**以元音开头**」，不能用「含元音」：
# 李方桂方案用 ji- 表示喻母（如「融」= ji + ung），含元音却是合法声母，
# 用「含元音」会误判它 974 行。
# ǐ（U+01D0）/û/ʅ 是上古表韵母里出现的带调元音，加进来防漏判。
_VOWEL_CHARS = set("aeiouɑɛɔɐəɯyæɒœʌɤɨʉɘɵɪʊǐûʅ")

# 零声母记号：王力 "0"；李方桂 U+0387（點），点后还可带介音（"·w"）。
_ZERO_INITIAL_MARKS = ("0", "\u0387")

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# 只剩送氣符/组合附加符、没有基音（上古高本漢表 8 行：'ʰ'）。
_ASPIRATION_ONLY_RE = re.compile(r"^[\u02b0\u0300-\u036f]+$")
# 上游把符号存成了 HTML 实体文本（如 '&#611'，不带分号）。
_ENTITY_RE = re.compile(r"^&#(\d{1,5});?$")


def _is_zero_initial(initial: str) -> bool:
    return initial in _ZERO_INITIAL_MARKS


def _strip_zero_initial(initial: str) -> str:
    """零声母记号 → 空；点后保留介音（"·w" → "w"）。"""
    if initial in _ZERO_INITIAL_MARKS:
        return ""
    if initial.startswith("\u0387"):
        return initial[1:]
    return initial


def _initial_looks_like_final(value: str) -> bool:
    return bool(value) and value[0] in _VOWEL_CHARS


def _normalize_phoneme_text(value: str) -> str:
    """全角 ASCII 还原为半角（上游有个别「ｐ」这类笔误，如上古王力「屁」）。"""
    return "".join(chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c
                   for c in value)


def _decode_html_entity(value: str) -> str:
    """把 '&#611' 这类实体文本机械解码为对应 Unicode 字符；不是实体则原样返回。"""
    m = _ENTITY_RE.match(value)
    if m:
        code = int(m.group(1))
        if 0 < code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF:
            return chr(code)
    return value


def _suspect_initial_reason(initial: str) -> str:
    """返回错位/缺陷原因；正常声母返回空串。"""
    if not initial:
        return ""
    if _CJK_RE.search(initial):
        return "源表聲母列含漢字（上游把韻部名填入了聲母列），未生成 IPA。"
    if _initial_looks_like_final(initial):
        return "源表聲母列以元音開頭（上游把韻母值填入了聲母列），未生成 IPA。"
    if _ASPIRATION_ONLY_RE.match(initial):
        return "源表聲母列只剩送氣符、缺基音，未生成 IPA。"
    return ""


def _compose_ipa(initial: str, final: str) -> str:
    """聲母 + 韻母。零声母记号（0 / ·）按无辅音处理，「·w」的介音 w 保留。"""
    return f"{_strip_zero_initial(initial)}{final}"


# 加载时被跳过的记录数（以及原因），用于在覆盖率报告里如实交代差额
_SKIPPED: dict[str, dict[str, int]] = {}


@lru_cache(maxsize=4)
def _bundle_rows(path: str | None, dataset_id: str) -> dict[str, tuple[dict, ...]]:
    """把整包按 (数据集, Sinica system) 分组，每个 (路径, 数据集) 只解析一次。

    11 个体系各扫一遍 6.6 MB 的包要 40 秒以上，分组后总耗时等于一次解析。
    """
    bundle = Path(path) if path else BUNDLE_PATH
    if not bundle.is_file():
        raise FileNotFoundError(
            f"找不到 Sinica 数据包：{bundle}；"
            "请先运行 scripts/import_sinica_ccr.py 或从仓库恢复 data/historical/sinica_ccr_import/")
    old_names = set(SCHOLAR_SYSTEMS_OLD.values())
    grouped: dict[str, list[dict]] = {}
    with gzip.open(bundle, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("dataset_id") != dataset_id:
                continue
            system = record.get("system")
            if dataset_id == DATASET_OLD_CHINESE:
                # 上古包里的「兩漢」表是韵部资料，不是学者拟音
                if system not in old_names:
                    continue
            elif system in NOT_A_RECONSTRUCTION:
                continue
            grouped.setdefault(system, []).append(record)
    return {name: tuple(rows) for name, rows in grouped.items()}


@lru_cache(maxsize=16)
def load_scholar_readings(system_id: str,
                          path: str | None = None) -> tuple[ScholarReading, ...]:
    """读取某位学者在中古/上古数据集里的全部逐字记录。"""
    if system_id not in SCHOLAR_SYSTEMS_ALL:
        raise KeyError(f"unknown Sinica scholar system: {system_id}")
    dataset_id = system_dataset(system_id)
    system_name = SCHOLAR_SYSTEMS_ALL[system_id]
    bundle = Path(path) if path else BUNDLE_PATH
    if not bundle.is_file():
        raise FileNotFoundError(
            f"找不到 Sinica 数据包：{bundle}；"
            "请先运行 scripts/import_sinica_ccr.py 或从仓库恢复 data/historical/sinica_ccr_import/")

    readings = []
    skipped = {"matched": 0, "not_single_char": 0, "empty_final": 0,
               "suspect_initial": 0, "entity_decoded": 0}
    for record in _bundle_rows(path, dataset_id).get(system_name, ()):
        skipped["matched"] += 1
        fields = record.get("fields") or {}
        character = (record.get("character") or fields.get("字") or "").strip()
        if len(character) != 1:
            skipped["not_single_char"] += 1
            continue
        initial = _normalize_phoneme_text((fields.get("聲母") or "").strip())
        final = _normalize_phoneme_text((fields.get("韻母") or "").strip())
        note_bits = []
        if initial == "?":
            initial = ""  # 上游「?」= 未知声母
        if final in ("", "?"):
            # 上游「?」= 未知韵母，按空缺处理（上古高本漢表 5 行）
            skipped["empty_final"] += 1
            continue
        initial_raw = _normalize_phoneme_text((fields.get("聲母") or "").strip())
        decoded_initial = _decode_html_entity(initial_raw)
        if decoded_initial != initial_raw:
            skipped["entity_decoded"] += 1
            note_bits.append(
                f"源表聲母列原为 HTML 实体 {initial_raw!r}，已機械解碼為 {decoded_initial!r}。")
            initial = decoded_initial
        final_raw = _normalize_phoneme_text((fields.get("韻母") or "").strip())
        final = _decode_html_entity(final_raw)
        if final != final_raw:
            skipped["entity_decoded"] += 1
            note_bits.append(
                f"源表韻母列原为 HTML 实体 {final_raw!r}，已機械解碼為 {final!r}。")
        reason = _suspect_initial_reason(initial)
        if reason:
            skipped["suspect_initial"] += 1
            note_bits.append(reason)
        readings.append(ScholarReading(
            character=character,
            system_id=system_id,
            system_name=system_name,
            initial=initial,
            final=final,
            ipa="" if reason else _compose_ipa(initial, final),
            source_workbook=record.get("source_workbook", ""),
            source_sheet=record.get("source_sheet", ""),
            source_row=int(record.get("source_row") or 0),
            source_sha256=record.get("source_sha256", ""),
            license_mark=record.get("license_mark", ""),
            note="".join(note_bits),
            suspect=bool(reason),
            rhyme_group=(fields.get("韻部") or "").strip(),
            upstream_note=(fields.get("備註") or "").strip(),
        ))
    _SKIPPED[system_id] = skipped
    return tuple(readings)


@lru_cache(maxsize=16)
def _index_by_char(system_id: str) -> dict[str, tuple[ScholarReading, ...]]:
    grouped: dict[str, list[ScholarReading]] = {}
    for reading in load_scholar_readings(system_id):
        grouped.setdefault(reading.character, []).append(reading)
    return {ch: tuple(items) for ch, items in grouped.items()}


def lookup_scholar_reading(character: str, system_id: str) -> tuple[ScholarReading, ...]:
    """某字在某个学者体系下的全部记录（多音字可能多条）；空元组表示无此字。"""
    return _index_by_char(system_id).get(character, ())


def scholar_record_count(system_id: str) -> int:
    return len(load_scholar_readings(system_id))


def scholar_character_count(system_id: str) -> int:
    return len(_index_by_char(system_id))


def scholar_coverage(system_id: str) -> dict:
    """覆盖率统计：匹配了多少、跳过多少、为什么，供报告与 UI 如实交代。"""
    if system_id not in SCHOLAR_SYSTEMS_ALL:
        raise KeyError(f"unknown Sinica scholar system: {system_id}")
    rows = load_scholar_readings(system_id)
    grouped = _index_by_char(system_id)
    skipped = _SKIPPED.get(system_id, {})
    initials = {r.initial for r in rows}
    finals = {r.final for r in rows}
    multi = sum(1 for items in grouped.values() if len(items) > 1)
    no_initial = sum(1 for r in rows if r.initial == "")
    zero_initial = sum(1 for r in rows if _is_zero_initial(r.initial))
    glide_onset = sum(1 for r in rows
                      if r.initial.startswith("\u0387") and len(r.initial) > 1)
    rhyme_groups = {r.rhyme_group for r in rows if r.rhyme_group}
    note_rows = sum(1 for r in rows if r.upstream_note)
    return {
        "system_id": system_id,
        "system_name": SCHOLAR_SYSTEMS_ALL[system_id],
        "dataset": system_dataset(system_id),
        "matched_records": skipped.get("matched", len(rows)),
        "records": len(rows),
        "skipped_not_single_char": skipped.get("not_single_char", 0),
        "skipped_empty_final": skipped.get("empty_final", 0),
        "skipped_suspect_initial": skipped.get("suspect_initial", 0),
        "entity_decoded": skipped.get("entity_decoded", 0),
        "suspect_characters": sorted(ch for ch, items in grouped.items()
                                      if any(r.suspect for r in items))[:20],
        "characters": len(grouped),
        "multi_reading_characters": multi,
        "distinct_initials": len(initials),
        "distinct_finals": len(finals),
        "blank_initial": no_initial,
        "zero_initial": zero_initial,
        "glide_onset": glide_onset,
        "rhyme_group_count": len(rhyme_groups),
        "rhyme_groups_sample": sorted(rhyme_groups)[:20],
        "upstream_note_rows": note_rows,
        "tone_available": False,
        "initials": sorted(initials),
        "finals_sample": sorted(finals)[:20],
    }
