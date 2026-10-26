"""Offline lookup for CC0 Guangyun phonological-position records.

The bundled source records 小韻首字 and its 切韻系音韻地位 description.
They are source-derived phonological classifications, NOT IPA and NOT a
scholar-specific pronunciation reconstruction.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

DATA_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "historical" / "guangyun_positions.csv"
)
SOURCE_URL = (
    "https://github.com/nk2028/tshet-uinh-data/blob/"
    "main/反切音韻地位/廣韻反切音韻地位表.csv"
)
SOURCE_BLOB_SHA = "93ca1b1551b30bba9c76fe21078f156b8299d9cc"


@dataclass(frozen=True, slots=True)
class QieyunPositionRecord:
    xiaoyun_id: str
    head_character: str
    fanqie_upper: str
    fanqie_lower: str
    position_description: str
    source_status: str = "source_record"

    @property
    def has_multiple_descriptions(self) -> bool:
        return "/" in self.position_description


@lru_cache(maxsize=1)
def load_qieyun_positions(
    path: Optional[str] = None,
) -> dict[str, tuple[QieyunPositionRecord, ...]]:
    """Load the bundled table, grouped by 小韻首字.

    Pass a path to load a fixture or alternate, schema-compatible CSV.
    Multiple 小韻s for one character are preserved in source order.
    """
    csv_path = Path(path) if path else DATA_PATH
    grouped: dict[str, list[QieyunPositionRecord]] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "小韻號", "小韻首字", "上字", "下字", "被切字音韻描述們"
        }
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Guangyun CSV missing columns: {sorted(missing)}")
        for row in reader:
            character = (row.get("小韻首字") or "").strip()
            if not character:
                continue
            record = QieyunPositionRecord(
                xiaoyun_id=(row.get("小韻號") or "").strip(),
                head_character=character,
                fanqie_upper=(row.get("上字") or "").strip(),
                fanqie_lower=(row.get("下字") or "").strip(),
                position_description=(
                    row.get("被切字音韻描述們") or ""
                ).strip(),
            )
            grouped.setdefault(character, []).append(record)
    return {key: tuple(value) for key, value in grouped.items()}


def lookup_qieyun_positions(character: str) -> tuple[QieyunPositionRecord, ...]:
    """Return all source records whose 小韻首字 matches one character."""
    if len(character) != 1:
        raise ValueError("lookup_qieyun_positions expects exactly one character")
    return load_qieyun_positions().get(character, ())


def qieyun_record_count() -> int:
    """Count rows in the source table, including multiple records per character."""
    return sum(len(records) for records in load_qieyun_positions().values())
