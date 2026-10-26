"""Evidence and provenance fields for historical reading records."""
from dataclasses import dataclass
from typing import Optional

CONFIDENCE_LEVELS = frozenset({"high", "medium", "low", "unassessed"})


@dataclass(frozen=True, slots=True)
class Provenance:
    """Editorial confidence is not a statistical probability."""
    source_title: str = ""
    source_author: str = ""
    source_url: Optional[str] = None
    source_version: Optional[str] = None
    page_or_entry: Optional[str] = None
    derivation_rule: Optional[str] = None
    confidence: str = "unassessed"
    evidence_note: str = ""

    def __post_init__(self):
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"confidence must be one of {sorted(CONFIDENCE_LEVELS)}")

    @property
    def is_traceable(self) -> bool:
        return bool(self.source_title or self.source_url or self.page_or_entry)
