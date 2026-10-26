"""Offline access to PHONO-ML Middle Chinese transcriptions.

The values are Baxter-Sagart style transcriptions, not IPA and not direct
recordings. Parallel semicolon-separated fields are kept aligned by index.
Dataset license: CC BY 4.0; see data/historical/PHONO-ML_ATTRIBUTION.md.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "historical" / "phono_ml_characters.csv"
SOURCE_URL = "https://github.com/alxdrdelaporte/PHONO-ML_database/blob/main/phonoML_characters.csv"
SOURCE_BLOB_SHA = "e371665481c70b56534a618f42f620567ae5a762"


@dataclass(frozen=True, slots=True)
class PhonoMLRecord:
    character: str
    transcription: str
    fanqie: str = ""
    phonological_position: str = ""
    identifiers: str = ""
    source_status: str = "source_record"
    transcription_scheme: str = "Baxter-Sagart Middle Chinese transcription"


def _split_parallel(value: str) -> list[str]:
    return value.split(";") if value else []


@lru_cache(maxsize=1)
def load_phono_ml(path: str | None = None) -> dict[str, tuple[PhonoMLRecord, ...]]:
    csv_path = Path(path) if path else DATA_PATH
    grouped: dict[str, list[PhonoMLRecord]] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Character", "Transcriptions", "Fanqie", "Sixtuples", "Identifiers"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"PHONO-ML CSV missing columns: {sorted(missing)}")
        for row in reader:
            char = (row.get("Character") or "").strip()
            if not char:
                continue
            transcriptions = _split_parallel((row.get("Transcriptions") or "").strip())
            fanqie = _split_parallel((row.get("Fanqie") or "").strip())
            positions = _split_parallel((row.get("Sixtuples") or "").strip())
            identifiers = _split_parallel((row.get("Identifiers") or "").strip())
            width = max(len(transcriptions), len(fanqie), len(positions), len(identifiers))
            for i in range(width):
                record = PhonoMLRecord(
                    character=char,
                    transcription=transcriptions[i] if i < len(transcriptions) else "",
                    fanqie=fanqie[i] if i < len(fanqie) else "",
                    phonological_position=positions[i] if i < len(positions) else "",
                    identifiers=identifiers[i] if i < len(identifiers) else "",
                )
                if record.transcription or record.phonological_position:
                    grouped.setdefault(char, []).append(record)
    return {key: tuple(value) for key, value in grouped.items()}


def lookup_phono_ml(character: str) -> tuple[PhonoMLRecord, ...]:
    """Return all source-aligned readings for exactly one Han character."""
    if len(character) != 1:
        raise ValueError("lookup_phono_ml expects exactly one character")
    return load_phono_ml().get(character, ())


def phono_ml_record_count() -> int:
    """Count character/transcription records, not distinct characters."""
    return sum(len(records) for records in load_phono_ml().values())
