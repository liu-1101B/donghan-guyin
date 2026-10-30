"""Eastern Han → Middle Chinese phonological-class correspondence.

Anchors the legacy Eastern Han reading table (``phonology_db.EASTERN_HAN_DB``,
source_status ``legacy_experimental``, unassessed) to Middle Chinese
phonological positions from the bundled CC0 Guangyun fanqie table
(``data/historical/guangyun_positions.csv``, see
:mod:`language.history.qieyun_data` for provenance).

Method: every Eastern Han character (simplified key) is converted to
traditional via OpenCC ``s2t`` and looked up among the table's 小韻首字.
For each anchored character the Eastern Han initial/final class and every
Middle Chinese position record are paired, and the two correspondence tables
(initial table, final table) are the *observed co-occurrences* on that
intersection. They are NOT sound-change laws: each pair is backed by the
listed characters, 1:many scatter is reported as exceptions, and the 210
unanchored characters are exposed, never backfilled.

The anchor space uses 38 initials / 58 rhymes / 4 tones. That granularity is
shared exactly by both bundled sources (the CC0 table and the Qieyun
canonical position set); it is not the traditional 106-rhyme numbering of
the Guangyun and is documented as an upstream data characteristic.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from opencc import OpenCC

from phonology_db import EASTERN_HAN_DB
from .qieyun_data import (
    QieyunPositionRecord,
    load_qieyun_positions,
    qieyun_record_count,
    SOURCE_BLOB_SHA,
    SOURCE_URL,
)

_TONE = "平上去入"
_GRADE = "一二三四"
_OPEN_CLOSE = "開合"
_CHONGNIU = "AB"


@dataclass(frozen=True, slots=True)
class ParsedPosition:
    """One parsed 音韻地位 description, e.g. ``見開B支平`` or ``端冬平``."""

    shengmu: str
    yun: str
    sheng: str
    kaihhe: Optional[str] = None
    deng: Optional[str] = None
    chongniu: Optional[str] = None

    @property
    def key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.shengmu, self.kaihhe or "", self.deng or "",
            self.chongniu or "", self.yun, self.sheng,
        )


@dataclass(frozen=True, slots=True)
class AnchorRow:
    """One Eastern Han character with its Middle Chinese anchors."""

    char: str
    traditional: str
    han_init: str
    han_final: str
    han_tone: str
    han_ipa: str
    positions: tuple[ParsedPosition, ...]

    @property
    def anchored(self) -> bool:
        return bool(self.positions)


@dataclass(frozen=True, slots=True)
class CorrespondencePair:
    """An observed (Eastern Han class → Middle Chinese class) pair."""

    n: int
    chars: tuple[str, ...]

    @property
    def is_exception(self) -> bool:
        return self.n < 3


def parse_position_description(s: str) -> tuple[ParsedPosition, ...]:
    """Parse a 音韻地位 description into its fields.

    Format observed in the bundled table:
    ``[声母][开合][等|重纽AB]韵调`` — the trailing 调 is one of 平上去入,
    the 韵 is the character before it, and the remaining tail carries at
    most one 开合 (開/合), one 等 (一二三四) and one 重纽 (A/B) token,
    each at most once. Returns all alternatives when the description
    contains ``/``; returns ``()`` when nothing parses.
    """
    if not s:
        return ()
    out: list[ParsedPosition] = []
    for part in s.split("/"):
        part = part.strip()
        if len(part) < 3 or part[-1] not in _TONE:
            continue
        yun, sheng = part[-2], part[-1]
        prefix = part[:-2]
        deng = khh = ab = None
        i = len(prefix)
        while i > 0:
            ch = prefix[i - 1]
            if ch in _GRADE and deng is None:
                deng = ch
                i -= 1
            elif ch in _OPEN_CLOSE and khh is None:
                khh = ch
                i -= 1
            elif ch in _CHONGNIU and ab is None:
                ab = ch
                i -= 1
            else:
                break
        shengmu = prefix[:i]
        if not shengmu:
            continue
        out.append(ParsedPosition(
            shengmu=shengmu, yun=yun, sheng=sheng,
            kaihhe=khh, deng=deng, chongniu=ab,
        ))
    return tuple(out)


@lru_cache(maxsize=1)
def _s2t() -> OpenCC:
    return OpenCC("s2t")


@lru_cache(maxsize=1)
def _parsed_table() -> dict[str, tuple[ParsedPosition, ...]]:
    """小韻首字 → parsed positions, multiple records kept in source order."""
    grouped: dict[str, list[ParsedPosition]] = {}
    for head, records in load_qieyun_positions().items():
        parsed: list[ParsedPosition] = []
        for record in records:
            parsed.extend(parse_position_description(record.position_description))
        if parsed:
            grouped[head] = tuple(parsed)
    return grouped


@lru_cache(maxsize=1)
def eastern_mc_anchors() -> tuple[AnchorRow, ...]:
    """All 703 Eastern Han characters with their Middle Chinese anchors."""
    cc = _s2t()
    rows: list[AnchorRow] = []
    table = _parsed_table()
    for char, entry in EASTERN_HAN_DB.items():
        traditional = cc.convert(char)
        rows.append(AnchorRow(
            char=char,
            traditional=traditional,
            han_init=entry["init"],
            han_final=entry["final"],
            han_tone=entry["tone"],
            han_ipa=entry["ipa"],
            positions=table.get(traditional, ()),
        ))
    return tuple(rows)


def anchor_for(char: str) -> Optional[AnchorRow]:
    """Anchor row for one Eastern Han DB key (simplified)."""
    for row in eastern_mc_anchors():
        if row.char == char or row.traditional == char:
            return row
    return None


@lru_cache(maxsize=1)
def anchor_coverage() -> dict:
    """Coverage counts: what is anchored, what is exposed as missing."""
    rows = eastern_mc_anchors()
    anchored = [r for r in rows if r.anchored]
    unanchored = [r for r in rows if not r.anchored]
    table = _parsed_table()
    mc = [p for positions in table.values() for p in positions]
    return {
        "han_total": len(rows),
        "han_distinct_traditional": len({r.traditional for r in rows}),
        "anchored": len(anchored),
        "unanchored": len(unanchored),
        "pair_total": sum(len(r.positions) for r in anchored),
        "table_rows": qieyun_record_count(),
        "table_distinct_heads": len(table),
        "mc_initials": len({p.shengmu for p in mc}),
        "mc_rhymes": len({p.yun for p in mc}),
    }


def unanchored_characters() -> tuple[str, ...]:
    """Eastern Han DB keys with no 小韻首字 anchor (exposed, never filled)."""
    return tuple(r.char for r in eastern_mc_anchors() if not r.anchored)


def _collect(
    rows: tuple[AnchorRow, ...],
    side_key: str,
    mc_key: str,
) -> dict[str, dict[str, CorrespondencePair]]:
    init: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if not row.anchored:
            continue
        for pos in row.positions:
            init[row.__getattribute__(side_key)][
                getattr(pos, mc_key)
            ].append(row.char)
    out: dict[str, dict[str, CorrespondencePair]] = {}
    for k, pairs in init.items():
        out[k] = {
            mk: CorrespondencePair(n=len(v), chars=tuple(sorted(v)))
            for mk, v in sorted(pairs.items(), key=lambda x: (-len(x[1]), x[0]))
        }
    return dict(sorted(out.items(), key=lambda x: -sum(p.n for p in x[1].values())))


@lru_cache(maxsize=1)
def initial_correspondence() -> dict[str, dict[str, CorrespondencePair]]:
    """东汉声母类 → 中古声母, observed on anchored characters only."""
    return _collect(eastern_mc_anchors(), "han_init", "shengmu")


@lru_cache(maxsize=1)
def final_correspondence() -> dict[str, dict[str, CorrespondencePair]]:
    """东汉韵部 → 中古韵名, observed on anchored characters only."""
    return _collect(eastern_mc_anchors(), "han_final", "yun")


def provenance() -> dict:
    """Sources and limitations, in the exact wording used by the report."""
    coverage = anchor_coverage()
    return {
        "han_source": {
            "module": "phonology_db.EASTERN_HAN_DB",
            "characters": coverage["han_total"],
            "source_status": "legacy_experimental",
            "confidence": "unassessed",
        },
        "mc_anchor_source": {
            "path": "data/historical/guangyun_positions.csv",
            "rows": coverage["table_rows"],
            "distinct_heads": coverage["table_distinct_heads"],
            "license": "CC0",
            "source_url": SOURCE_URL,
            "source_blob_sha": SOURCE_BLOB_SHA,
        },
        "key_alignment": "OpenCC s2t on Eastern Han keys",
        "method": (
            "observed co-occurrence on the anchored intersection; "
            "not a sound-change law"
        ),
        "anchor_space": {
            "initials": coverage["mc_initials"],
            "rhymes": coverage["mc_rhymes"],
            "tones": "平上去入",
            "note": (
                "granularity shared exactly by the bundled CC0 table and the "
                "Qieyun canonical position set; not the traditional 106-rhyme "
                "numbering of the Guangyun"
            ),
        },
        "limitations": [
            f"{coverage['unanchored']} of {coverage['han_total']} characters "
            "have no 小韻首字 anchor (e.g. 人/今/他 occur in the table only as "
            "fanqie characters, 使 does not occur at all); they are reported, "
            "never backfilled",
            "Eastern Han side is legacy experimental (unassessed)",
            "correspondence pairs are observations on anchored characters, "
            "not causal sound-change rules",
        ],
    }


def _fmt_pairs(pairs: dict[str, CorrespondencePair]) -> str:
    return " | ".join(f"{mc} {p.n}" for mc, p in pairs.items())


def build_report(top_finals: int = 30) -> str:
    """Full Chinese-language correspondence report (CLI + tests)."""
    cov = anchor_coverage()
    lines: list[str] = []
    add = lines.append
    add("东汉 → 中古 音类对应报告（观测对应，非音变规律）")
    add("=" * 56)
    add("[数据]")
    add(f"- 东汉端：phonology_db.EASTERN_HAN_DB，{cov['han_total']} 字"
        "（legacy_experimental / unassessed）")
    add(f"- 中古锚点：data/historical/guangyun_positions.csv，"
        f"{cov['table_rows']} 条反切音韵地位记录 / "
        f"{cov['table_distinct_heads']} 首字（CC0，blob {SOURCE_BLOB_SHA[:12]}…）")
    add(f"- 字表对齐：简→繁（OpenCC s2t）；{cov['anchored']}/{cov['han_total']} 字有锚点，"
        f"{cov['unanchored']} 字无锚点（{(cov['unanchored'] / cov['han_total']) * 100:.1f}%）")
    add(f"- 锚点空间粒度：{cov['mc_initials']} 声母 / {cov['mc_rhymes']} 韵 / 4 调"
        "（与 Qieyun 规范位置集完全一致；不同于传统 106 韵编号，属上游数据粒度特征）")
    add(f"- 对应样本：{cov['pair_total']} 条（字, 中古位置）对"
        "（部分锚定字有多条反切记录）")
    add("")
    add(f"[声母对应]（东汉 {len(initial_correspondence())} 母 → 中古声母）")
    for dh, pairs in initial_correspondence().items():
        add(f"  {dh}（{sum(p.n for p in pairs.values())}）→ {_fmt_pairs(pairs)}")
    add("")
    add(f"[韵母对应]（按锚定样本数前 {top_finals} 的东汉韵部）")
    finals = list(final_correspondence().items())[:top_finals]
    for dh, pairs in finals:
        add(f"  {dh}（{sum(p.n for p in pairs.values())}）→ {_fmt_pairs(pairs)}")
    if len(finals) < len(final_correspondence()):
        add(f"  …（其余 {len(final_correspondence()) - len(finals)} 个东汉韵部略，"
            "见 final_correspondence()）")
    add("")
    missing = unanchored_characters()
    add(f"[无锚点字]（{len(missing)} 字，仅列前 40）")
    add("  " + " ".join(missing[:40]) + (" …" if len(missing) > 40 else ""))
    add("")
    add("[局限]")
    for i, note in enumerate(provenance()["limitations"], 1):
        add(f"  {i}. {note}")
    return "\n".join(lines)
