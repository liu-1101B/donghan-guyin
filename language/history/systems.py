"""Metadata registry for scholarly reconstruction and reading systems."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class ReconstructionSystem:
    id: str
    name: str
    scholar: str
    period_ids: tuple[str, ...]
    description: str
    status: str = "metadata_only"
    source_url: Optional[str] = None
    notes: str = ""

    def supports_period(self, period_id: str) -> bool:
        return period_id in self.period_ids


# Registry metadata is not a claim that the corresponding datasets are installed.
SYSTEMS = (
    ReconstructionSystem("han_eastern_experimental", "东汉拟音（项目实验方案）",
        "项目内部方案", ("old_chinese", "eastern_han"),
        "适配现有 phonology_db.EASTERN_HAN_DB 的兼容入口。",
        status="implemented_legacy_adapter",
        notes="实验性字条，来源和推导过程仍需逐字补齐。"),
    ReconstructionSystem("zhengzhang_oc", "上古音构拟（郑张尚芳）", "郑张尚芳",
        ("old_chinese",), "上古汉语参考体系；当前仅登记元数据。",
        source_url="https://zh.wikipedia.org/wiki/郑张尚芳上古音系统",
        notes="未接入完整字表，不能据此输出拟音。"),
    ReconstructionSystem("baxter_sagart_oc", "上古音构拟（白一平—沙加尔）",
        "William H. Baxter / Laurent Sagart", ("old_chinese",),
        "上古汉语参考体系；当前仅登记元数据。",
        source_url="https://github.com/BaxterSagart",
        notes="需核对数据版本和许可，不能与其他方案混合推导。"),
    ReconstructionSystem("karlgren_mc", "中古音构拟（高本汉）", "Bernhard Karlgren",
        ("middle_chinese", "late_middle_chinese"),
        "中古音参考体系；当前仅登记元数据。",
        notes="接入时需明确采用的著作与版本。"),
    ReconstructionSystem("wangli_mc", "中古音构拟（王力）", "王力",
        ("middle_chinese", "late_middle_chinese"),
        "中古音参考体系；当前仅登记元数据。",
        notes="接入时需记录著作、版本和符号规范。"),
    ReconstructionSystem("zhengzhang_mc", "中古音构拟（郑张尚芳）", "郑张尚芳",
        ("middle_chinese", "late_middle_chinese"),
        "中古音参考体系；当前仅登记元数据。",
        notes="接入时需记录资料版本与推导规则。"),
    ReconstructionSystem("mandarin_modern", "现代普通话", "现代标准音参考",
        ("modern_chinese",), "现代参考读音；后续应接词典和多音字消歧。",
        status="planned"),
)


def get_system(system_id: str) -> ReconstructionSystem:
    for system in SYSTEMS:
        if system.id == system_id:
            return system
    raise KeyError(f"unknown reconstruction system: {system_id}")


def systems_for_period(period_id: str, *, include_metadata_only: bool = True):
    matches = tuple(s for s in SYSTEMS if s.supports_period(period_id))
    if include_metadata_only:
        return matches
    return tuple(s for s in matches if s.status == "implemented_legacy_adapter")
