"""Offline access to CC0 Zhongyuan Yinyun reconstruction tables.

Each scholarly reconstruction is stored under its own scheme identifier.
The strings are source transcriptions/reconstructions, not a guarantee of
direct TTS compatibility. See data/historical/README.md for provenance.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "historical" / "zhongyuan_yinyun.tsv"
SOURCE_URL = "https://github.com/nk2028/zhongyuan-data/blob/main/%E4%B8%AD%E5%8E%9F%E9%9F%B3%E9%9F%BB.tsv"
SOURCE_BLOB_SHA = "74b2b30565a2ac4c47b309fe1ff804c6b438c4a9"

SCHEME_COLUMNS = {
    "zhongyuan_yangnaisi": ("楊耐思", "杨耐思"),
    "zhongyuan_ningjifu": ("寧繼福", "宁继福"),
    "zhongyuan_xuefengsheng": ("薛鳳生(音位)", "薛凤生（音位）"),
    "zhongyuan_unt_phonemic": ("unt(音位)", "unt（音位）"),
    "zhongyuan_unt": ("unt", "unt"),
}


@dataclass(frozen=True, slots=True)
class ZhongyuanRecord:
    xiaoyun: str
    character: str
    initial: str
    final: str
    tone: str
    transcriptions: tuple[tuple[str, str], ...]
    gloss: str = ""
    notes: str = ""
    source_status: str = "source_record"


@lru_cache(maxsize=1)
def load_zhongyuan(path: str | None = None) -> tuple[ZhongyuanRecord, ...]:
    tsv_path = Path(path) if path else DATA_PATH
    records: list[ZhongyuanRecord] = []
    with tsv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"小韻", "字", "聲母", "韻母", "聲調", "unt", "釋義", "校註"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Zhongyuan TSV missing columns: {sorted(missing)}")
        headers = set(reader.fieldnames or ())
        for row in reader:
            character = (row.get("字") or "").strip()
            if not character:
                continue
            variants: list[tuple[str, str]] = []
            for system_id, (column, _) in SCHEME_COLUMNS.items():
                if column in headers and (row.get(column) or "").strip():
                    variants.append((system_id, row[column].strip()))
            records.append(ZhongyuanRecord(
                xiaoyun=(row.get("小韻") or "").strip(),
                character=character,
                initial=(row.get("聲母") or "").strip(),
                final=(row.get("韻母") or "").strip(),
                tone=(row.get("聲調") or "").strip(),
                transcriptions=tuple(variants),
                gloss=(row.get("釋義") or "").strip(),
                notes=(row.get("校註") or "").strip(),
            ))
    return tuple(records)


def lookup_zhongyuan(character: str, system_id: str | None = None) -> tuple[ZhongyuanRecord, ...]:
    """Return all Zhongyuan Yinyun rows for a character, optionally scheme-filtered."""
    if len(character) != 1:
        raise ValueError("lookup_zhongyuan expects exactly one character")
    records = tuple(r for r in load_zhongyuan() if r.character == character)
    if system_id is None:
        return records
    if system_id not in SCHEME_COLUMNS:
        raise KeyError(f"unknown Zhongyuan reconstruction system: {system_id}")
    return tuple(r for r in records if any(sid == system_id for sid, _ in r.transcriptions))


def zhongyuan_record_count() -> int:
    return len(load_zhongyuan())
