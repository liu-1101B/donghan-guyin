"""接入 Sinica CCR 中「隋唐／中古」各学者拟音的逐字数据。

数据来源：中央研究院「漢字構形資料庫」（xiaoxue.iis.sinica.edu.tw），
已随仓库打包在 data/historical/sinica_ccr_import/ 下，字段为每位学者对每个字的
聲母 / 韻母 转写。许可见该包的 manifest（PDM）。

边界说明（重要）：
- 上游**没有声调字段**。这里不推测、不补全，tone 恒为 None。
- 聲母里的 "0" 是上游用来表示**零声母**的符号，不是数字 0。
- ȶ / ȡ 等是王力方案使用的符号，不是通用 IPA；能否送进合成器属于
  「音素能力矩阵」的问题（v5 第三阶段），本模块不做替换。
- 因此这些记录是**可追溯的学者拟音**，不等于已验证可播的读音。
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BUNDLE_PATH = (Path(__file__).resolve().parents[2] / "data" / "historical"
               / "sinica_ccr_import" / "sinica_ccr_records.jsonl.gz")

DATASET_MIDDLE_CHINESE = "sinica_ccr_middle_chinese"
DATASET_OLD_CHINESE = "sinica_ccr_old_chinese"

# system_id -> Sinica 的 system 字段
SCHOLAR_SYSTEMS = {
    "wangli_mc": "王力系統",
}

# 同一个数据包里还躺着这些中古学者方案，接入时各加一行即可
AVAILABLE_BUT_UNREGISTERED = {
    "dongtonghe_mc": "董同龢系統",
    "zhoufagao_mc": "周法高系統",
    "lifanggui_mc": "李方桂系統",
    "chenxinxiong_mc": "陳新雄系統",
}


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

    @property
    def has_initial(self) -> bool:
        """上游用 "" 或 "0" 表示零声母。"""
        return self.initial not in ("", "0")


# 声母只可能是辅音（含 j/w 这类半元音）外加表示零声母的 "0"。
# 源表里有 13 行把韵母值填进了聲母列（如「反」的声母写成 ǐɐn），
# 拼出来的 IPA 会是假的，所以必须识别出来并置空。
_VOWEL_CHARS = set("aeiouɑɛɔɐəɯyæɒœʌɤɨʉɘɵɪʊ")


def _looks_like_final(value: str) -> bool:
    return any(ch in _VOWEL_CHARS for ch in value)


def _compose_ipa(initial: str, final: str) -> str:
    """聲母 + 韻母。上游的 "0" 表示零声母，按无辅音处理。"""
    head = "" if initial == "0" else initial
    return f"{head}{final}"


# 加载时被跳过的记录数（以及原因），用于在覆盖率报告里如实交代差额
_SKIPPED: dict[str, dict[str, int]] = {}


@lru_cache(maxsize=4)
def load_scholar_readings(system_id: str,
                          path: str | None = None) -> tuple[ScholarReading, ...]:
    """读取某位学者在中古数据集里的全部逐字记录。"""
    if system_id not in SCHOLAR_SYSTEMS:
        raise KeyError(f"unknown Sinica scholar system: {system_id}")
    system_name = SCHOLAR_SYSTEMS[system_id]
    bundle = Path(path) if path else BUNDLE_PATH
    if not bundle.is_file():
        raise FileNotFoundError(
            f"找不到 Sinica 数据包：{bundle}；"
            "请先运行 scripts/import_sinica_ccr.py 或从仓库恢复 data/historical/sinica_ccr_import/")

    readings: list[ScholarReading] = []
    skipped = {"matched": 0, "not_single_char": 0, "empty_final": 0, "suspect_initial": 0}
    with gzip.open(bundle, "rt", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("dataset_id") != DATASET_MIDDLE_CHINESE:
                continue
            if record.get("system") != system_name:
                continue
            skipped["matched"] += 1
            fields = record.get("fields") or {}
            character = (record.get("character") or fields.get("字") or "").strip()
            if len(character) != 1:
                skipped["not_single_char"] += 1
                continue
            initial = (fields.get("聲母") or "").strip()
            final = (fields.get("韻母") or "").strip()
            if not final:
                skipped["empty_final"] += 1
                continue
            # 源表有少量行把韵母值填进了聲母列，拼出来会是假 IPA
            suspect = bool(initial) and _looks_like_final(initial)
            if suspect:
                skipped["suspect_initial"] += 1
            readings.append(ScholarReading(
                character=character,
                system_id=system_id,
                system_name=system_name,
                initial=initial,
                final=final,
                ipa="" if suspect else _compose_ipa(initial, final),
                source_workbook=record.get("source_workbook", ""),
                source_sheet=record.get("source_sheet", ""),
                source_row=int(record.get("source_row") or 0),
                source_sha256=record.get("source_workbook_sha256", ""),
                license_mark=record.get("license_mark", ""),
                suspect=suspect,
                note=("源表聲母列疑似错位（填入的是韵母值），未生成 IPA。"
                      if suspect else ""),
            ))
    _SKIPPED[system_id] = skipped
    return tuple(readings)


@lru_cache(maxsize=1)
def _index(system_id: str) -> dict[str, tuple[ScholarReading, ...]]:
    grouped: dict[str, list[ScholarReading]] = {}
    for reading in load_scholar_readings(system_id):
        grouped.setdefault(reading.character, []).append(reading)
    return {ch: tuple(rows) for ch, rows in grouped.items()}


def lookup_scholar_reading(character: str, system_id: str) -> tuple[ScholarReading, ...]:
    """返回某字在该学者方案下的全部记录（多音字可能有多条）。"""
    if len(character) != 1:
        raise ValueError("lookup_scholar_reading expects exactly one character")
    return _index(system_id).get(character, ())


def scholar_record_count(system_id: str) -> int:
    return len(load_scholar_readings(system_id))


def scholar_character_count(system_id: str) -> int:
    return len(_index(system_id))


def scholar_coverage(system_id: str) -> dict:
    """覆盖率报告所需统计（不合成、不改写数据）。"""
    rows = load_scholar_readings(system_id)
    grouped = _index(system_id)
    skipped = _SKIPPED.get(system_id, {})
    initials = {r.initial for r in rows}
    finals = {r.final for r in rows}
    multi = sum(1 for ch, items in grouped.items() if len(items) > 1)
    no_initial = sum(1 for r in rows if r.initial == "")
    zero_initial = sum(1 for r in rows if r.initial == "0")
    return {
        "system_id": system_id,
        "system_name": SCHOLAR_SYSTEMS[system_id],
        "matched_records": skipped.get("matched", len(rows)),
        "records": len(rows),
        "skipped_not_single_char": skipped.get("not_single_char", 0),
        "skipped_empty_final": skipped.get("empty_final", 0),
        "skipped_suspect_initial": skipped.get("suspect_initial", 0),
        "suspect_characters": sorted(ch for ch, items in grouped.items()
                                     if any(r.suspect for r in items))[:20],
        "characters": len(grouped),
        "multi_reading_characters": multi,
        "distinct_initials": len(initials),
        "distinct_finals": len(finals),
        "blank_initial": no_initial,
        "zero_initial": zero_initial,
        "tone_available": False,
        "initials": sorted(initials),
        "finals_sample": sorted(finals)[:20],
    }
