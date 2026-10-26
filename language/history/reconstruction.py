"""Safe reading lookup with a compatibility adapter for the legacy Han database."""
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from .provenance import Provenance
from .systems import get_system


@dataclass(frozen=True, slots=True)
class Reading:
    character: str
    system_id: str
    period_id: str
    ipa: Optional[str]
    initial: Optional[str] = None
    final: Optional[str] = None
    tone: Optional[str] = None
    source_status: str = "unavailable"
    approximation: bool = False
    provenance: Provenance = Provenance()
    note: str = ""

    @property
    def available(self) -> bool:
        return bool(self.ipa)


def lookup_reading(character: str, system_id: str, *, period_id: Optional[str] = None,
                   legacy_db: Optional[Mapping[str, Mapping[str, Any]]] = None) -> Reading:
    """Never fabricate IPA for a registered system whose dataset is not integrated."""
    if len(character) != 1:
        raise ValueError("lookup_reading expects exactly one character")
    system = get_system(system_id)
    selected_period = period_id or system.period_ids[0]
    if not system.supports_period(selected_period):
        raise ValueError(f"system {system_id!r} does not support period {selected_period!r}")

    if system_id != "han_eastern_experimental":
        return Reading(character, system_id, selected_period, None,
            source_status="not_integrated",
            note="该体系已登记，但尚无可核验的逐字数据；不生成猜测读音。")

    if legacy_db is None:
        try:
            from phonology_db import EASTERN_HAN_DB
            legacy_db = EASTERN_HAN_DB
        except (ImportError, AttributeError):
            legacy_db = {}
    item = legacy_db.get(character)
    if not item:
        return Reading(character, system_id, selected_period, None,
            source_status="missing_character", note="现有东汉实验字表中无此字条。")

    return Reading(character, system_id, selected_period,
        str(item.get("ipa") or "") or None,
        initial=item.get("init"), final=item.get("final"), tone=item.get("tone"),
        source_status="legacy_experimental", approximation=True,
        provenance=Provenance(source_title="项目现有 EASTERN_HAN_DB",
            confidence="unassessed",
            evidence_note="沿用旧字表记录；来源、推导过程和置信度尚未逐字审计。"),
        note="项目实验性拟音，不应视为已确立的唯一历史读音。")
