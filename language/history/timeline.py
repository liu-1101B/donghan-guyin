"""Discrete navigation periods for historical Chinese exploration."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HistoricalPeriod:
    """Broad research range, not a claim of uniform pronunciation.

    Astronomical numbering is used: year 0 is 1 BCE, year -1 is 2 BCE.
    Bounds are inclusive. Ranges may overlap because language change is gradual.
    """
    id: str
    label: str
    start_year: int
    end_year: int
    description: str
    evidence_note: str = ""

    def __post_init__(self):
        if not self.id.strip():
            raise ValueError("period id must not be empty")
        if self.start_year > self.end_year:
            raise ValueError("start_year must be <= end_year")

    def contains(self, year: int) -> bool:
        return self.start_year <= year <= self.end_year


TIMELINE = (
    HistoricalPeriod("old_chinese", "上古汉语", -1200, 220,
        "以先秦至两汉材料为核心；研究分期与音系边界存在差异。",
        "构拟依赖韵文、谐声、通假及后世音系等间接证据。"),
    HistoricalPeriod("eastern_han", "东汉", 25, 220,
        "原项目东汉音韵实验区间，作为独立研究视图保留。",
        "现有字表是实验性拟音，不代表已确立的洛阳官音标准。"),
    HistoricalPeriod("middle_chinese", "中古汉语", 581, 907,
        "以切韵系韵书为重要参照；不等同于某一地点的单一口语。",
        "需区分韵书分类、学者拟音与具体时代口语。"),
    HistoricalPeriod("late_middle_chinese", "晚唐至宋", 800, 1279,
        "呈现中古音系演变及不同资料体系之间的过渡。",
        "具体读音应由对应材料与研究方案决定。"),
    HistoricalPeriod("early_mandarin", "近代汉语", 1200, 1911,
        "涵盖元明清等多类材料，不是单一统一音系。",
        "中原音韵、韵图及域外资料各有适用范围。"),
    HistoricalPeriod("modern_chinese", "现代汉语", 1912, 2100,
        "现代标准语与地方方言应进一步区分。",
        "普通话只是现代汉语变体之一。"),
)


def get_period(period_id: str) -> HistoricalPeriod:
    for period in TIMELINE:
        if period.id == period_id:
            return period
    raise KeyError(f"unknown historical period: {period_id}")


def period_at(year: int) -> tuple[HistoricalPeriod, ...]:
    """Return every matching period; overlaps are intentional."""
    return tuple(p for p in TIMELINE if p.contains(year))


def timeline_bounds() -> tuple[int, int]:
    return min(p.start_year for p in TIMELINE), max(p.end_year for p in TIMELINE)
