"""Offline access to the Academia Sinica / NTU historical phonology tables.

The source workbooks are converted to a provenance-preserving gzip JSONL file
by scripts/import_sinica_ccr.py. This adapter creates a SQLite cache outside
the repository on first query, so the UI does not need to load every row into
Python objects at once.

The source landing page distinguishes independent downloadable data files
marked with PDM from the online database/compilation as a whole. Preserve
source file URLs, archive/workbook hashes, workbook/sheet/row, and original
field names. See data/historical/README.md.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Optional

DATA_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "historical" / "sinica_ccr_import" / "sinica_ccr_records.jsonl.gz"
)
SOURCE_LANDING_PAGE = "https://xiaoxue.iis.sinica.edu.tw/ccrdata/"
SOURCE_URLS = {
    "sinica_ccr_old_chinese": (
        "https://xiaoxue.iis.sinica.edu.tw/ccrdata/file/ccr01_shangguyin_data_xlsx.zip"
    ),
    "sinica_ccr_middle_chinese": (
        "https://xiaoxue.iis.sinica.edu.tw/ccrdata/file/ccr02_zhongguyin_data_xlsx.zip"
    ),
    "sinica_ccr_rhyme_books": (
        "https://xiaoxue.iis.sinica.edu.tw/ccrdata/file/ccr03_yunshu_data_xlsx.zip"
    ),
}
LICENSE_MARK = "PDM"
INDEX_SCHEMA_VERSION = "1"


@dataclass(frozen=True, slots=True)
class SinicaCCRRecord:
    dataset_id: str
    period: str
    system: str
    record_type: str
    character: str
    source_workbook: str
    source_sheet: str
    source_row: int
    source_url: str
    license_mark: str
    source_workbook_sha256: str
    fields: Mapping[str, str]

    @property
    def source_location(self) -> str:
        return f"{self.source_workbook} / {self.source_sheet} / row {self.source_row}"

    @property
    def transcription_components(self) -> tuple[str, ...]:
        """Return separated source transcription components without IPA claims."""
        values = []
        for key in ("聲母", "韻母", "擬音", "聲調", "韻部", "韻目", "字母", "開合", "等第"):
            value = (self.fields.get(key) or "").strip()
            if value:
                values.append(f"{key}={value}")
        return tuple(values)


def dataset_available(path: Optional[str] = None) -> bool:
    """Whether the normalized local data bundle is present."""
    return Path(path).is_file() if path else DATA_PATH.is_file()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _cache_is_valid(db_path: Path, source_sha256: str) -> bool:
    if not db_path.is_file():
        return False
    try:
        with sqlite3.connect(str(db_path)) as conn:
            rows = dict(conn.execute("SELECT key, value FROM metadata"))
            return (
                rows.get("source_sha256") == source_sha256
                and rows.get("schema_version") == INDEX_SCHEMA_VERSION
            )
    except (sqlite3.Error, ValueError):
        return False


def _build_index(source_path: Path, source_sha256: str) -> Path:
    cache_path = Path(tempfile.gettempdir()) / f"donghan_sinica_ccr_{source_sha256[:24]}.sqlite3"
    if _cache_is_valid(cache_path, source_sha256):
        return cache_path

    tmp_path = cache_path.with_name(cache_path.name + f".{os.getpid()}.tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    conn = sqlite3.connect(str(tmp_path))
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            """CREATE TABLE records (
                id INTEGER PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                period TEXT NOT NULL,
                system TEXT NOT NULL,
                record_type TEXT NOT NULL,
                character TEXT NOT NULL,
                source_workbook TEXT NOT NULL,
                source_sheet TEXT NOT NULL,
                source_row INTEGER NOT NULL,
                source_url TEXT NOT NULL,
                license_mark TEXT NOT NULL,
                source_workbook_sha256 TEXT NOT NULL,
                fields_json TEXT NOT NULL
            )"""
        )
        insert_sql = """INSERT INTO records (
            dataset_id, period, system, record_type, character, source_workbook,
            source_sheet, source_row, source_url, license_mark,
            source_workbook_sha256, fields_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        batch = []
        with gzip.open(source_path, "rt", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL on line {line_no}: {exc}") from exc
                batch.append((
                    str(row.get("dataset_id") or ""),
                    str(row.get("period") or ""),
                    str(row.get("system") or ""),
                    str(row.get("record_type") or ""),
                    str(row.get("character") or ""),
                    str(row.get("source_workbook") or ""),
                    str(row.get("source_sheet") or ""),
                    int(row.get("source_row") or 0),
                    str(row.get("source_url") or ""),
                    str(row.get("license_mark") or "PDM"),
                    str(row.get("source_workbook_sha256") or ""),
                    json.dumps(row.get("fields") or {}, ensure_ascii=False, separators=(",", ":")),
                ))
                if len(batch) >= 2000:
                    conn.executemany(insert_sql, batch)
                    batch.clear()
        if batch:
            conn.executemany(insert_sql, batch)
        conn.execute("CREATE INDEX records_character_idx ON records(character)")
        conn.execute("CREATE INDEX records_character_dataset_idx ON records(character, dataset_id)")
        conn.execute("CREATE INDEX records_period_idx ON records(period)")
        conn.execute("CREATE INDEX records_system_idx ON records(system)")
        conn.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [("source_sha256", source_sha256), ("schema_version", INDEX_SCHEMA_VERSION)],
        )
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp_path, cache_path)
    return cache_path


@lru_cache(maxsize=4)
def _indexed_db_path(path_string: str, mtime_ns: int, size_bytes: int) -> str:
    source_path = Path(path_string)
    source_sha256 = _file_sha256(source_path)
    return str(_build_index(source_path, source_sha256))


def _get_db_path(path: Optional[str] = None) -> Path:
    source_path = Path(path) if path else DATA_PATH
    if not source_path.is_file():
        raise FileNotFoundError(
            "Central Research Institute data bundle is not installed. "
            "Extract sinica_ccr_records.jsonl.gz to "
            "data/historical/sinica_ccr_import/; see data/historical/README.md."
        )
    stat = source_path.stat()
    return Path(_indexed_db_path(str(source_path.resolve()), stat.st_mtime_ns, stat.st_size))


def lookup_sinica_ccr_records(
    character: str,
    *,
    dataset_id: Optional[str] = None,
    period: Optional[str] = None,
    system: Optional[str] = None,
    record_type: Optional[str] = None,
    path: Optional[str] = None,
    limit: int = 100,
) -> tuple[SinicaCCRRecord, ...]:
    """Look up all matching source records; multiple readings are preserved."""
    if len(character) != 1:
        raise ValueError("lookup_sinica_ccr_records expects exactly one character")
    if limit < 1 or limit > 2000:
        raise ValueError("limit must be between 1 and 2000")
    db_path = _get_db_path(path)
    clauses = ["character = ?"]
    params: list[object] = [character]
    for column, value in (
        ("dataset_id", dataset_id), ("period", period),
        ("system", system), ("record_type", record_type),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    params.append(limit)
    sql = (
        "SELECT dataset_id, period, system, record_type, character, "
        "source_workbook, source_sheet, source_row, source_url, license_mark, "
        "source_workbook_sha256, fields_json FROM records WHERE "
        + " AND ".join(clauses)
        + " ORDER BY dataset_id, source_workbook, source_sheet, source_row LIMIT ?"
    )
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(sql, params).fetchall()
    return tuple(
        SinicaCCRRecord(
            dataset_id=row[0], period=row[1], system=row[2], record_type=row[3],
            character=row[4], source_workbook=row[5], source_sheet=row[6],
            source_row=int(row[7]), source_url=row[8], license_mark=row[9],
            source_workbook_sha256=row[10], fields=json.loads(row[11]),
        )
        for row in rows
    )


def sinica_ccr_record_count(*, dataset_id: Optional[str] = None, path: Optional[str] = None) -> int:
    """Return the number of normalized source rows, optionally for one package."""
    db_path = _get_db_path(path)
    sql = "SELECT COUNT(*) FROM records"
    params: tuple[object, ...] = ()
    if dataset_id is not None:
        sql += " WHERE dataset_id = ?"
        params = (dataset_id,)
    with sqlite3.connect(str(db_path)) as conn:
        return int(conn.execute(sql, params).fetchone()[0])


def sinica_ccr_package_counts(*, path: Optional[str] = None) -> dict[str, int]:
    """Return counts per official download package."""
    db_path = _get_db_path(path)
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT dataset_id, COUNT(*) FROM records GROUP BY dataset_id ORDER BY dataset_id"
        ).fetchall()
    return {str(package_id): int(count) for package_id, count in rows}
