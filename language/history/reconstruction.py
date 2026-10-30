"""Safe reading lookup with a compatibility adapter for the legacy Han database."""
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from .provenance import Provenance
from .sinica_scholar_data import SCHOLAR_SYSTEMS_ALL as SINICA_SCHOLAR_SYSTEMS
from .systems import ReconstructionSystem, get_system, systems_for_period
from .timeline import get_period


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
    phonological_position: Optional[str] = None
    xiaoyun_id: Optional[str] = None
    fanqie_upper: Optional[str] = None
    fanqie_lower: Optional[str] = None
    transcription: Optional[str] = None
    transcription_scheme: Optional[str] = None
    rhyme_group: Optional[str] = None

    @property
    def available(self) -> bool:
        """Whether an IPA value exists and could be sent to a phoneme backend."""
        return bool(self.ipa)

    @property
    def has_record(self) -> bool:
        """Whether this result contains a source record, even without IPA."""
        return bool(self.ipa or self.phonological_position or self.transcription)


def lookup_reading(character: str, system_id: str, *, period_id: Optional[str] = None,
                   legacy_db: Optional[Mapping[str, Mapping[str, Any]]] = None) -> Reading:
    """Never fabricate IPA for a registered system whose dataset is not integrated."""
    if len(character) != 1:
        raise ValueError("lookup_reading expects exactly one character")
    system = get_system(system_id)
    selected_period = period_id or system.period_ids[0]
    if not system.supports_period(selected_period):
        raise ValueError(f"system {system_id!r} does not support period {selected_period!r}")

    if system_id == "phono_ml_baxter_sagart_mc":
        from .phono_ml_data import lookup_phono_ml, SOURCE_URL, SOURCE_BLOB_SHA
        records = lookup_phono_ml(character)
        if not records:
            return Reading(character, system_id, selected_period, None,
                source_status="missing_character",
                note="PHONO-ML 数据集中无此字条。")
        first = records[0]
        note = "PHONO-ML 的 Baxter–Sagart 风格中古音转写；不是 IPA 录音，也不保证可直接送入 TTS。"
        if len(records) > 1:
            note += f" 此字有 {len(records)} 条转写记录；请用 lookup_phono_ml() 查看全部。"
        return Reading(
            character, system_id, selected_period, None,
            source_status="source_reconstruction",
            provenance=Provenance(
                source_title="PHONO-ML Database",
                source_author="Guillaume Jacques / Alexander Delaporte",
                source_url=SOURCE_URL,
                source_version=f"Git blob {SOURCE_BLOB_SHA}",
                page_or_entry=first.identifiers or None,
                derivation_rule="Baxter (1992) principles and Jacques (2021); automated derivation",
                confidence="medium",
                evidence_note="上游说明其对相当一部分字条进行了抽样核验，并提示自动生成数据仍可能有误。",
            ),
            note=note,
            phonological_position=first.phonological_position or None,
            fanqie_upper=(first.fanqie[0] if first.fanqie else None),
            fanqie_lower=(first.fanqie[1] if len(first.fanqie) > 1 else None),
            transcription=first.transcription or None,
            transcription_scheme=first.transcription_scheme,
        )

    if system_id.startswith("zhongyuan_"):
        from .zhongyuan_data import lookup_zhongyuan, SOURCE_URL, SOURCE_BLOB_SHA
        records = lookup_zhongyuan(character, system_id)
        if not records:
            return Reading(character, system_id, selected_period, None,
                source_status="missing_character",
                note="《中原音韵》数据集中无此字的对应方案记录。")
        first = records[0]
        value = next((value for sid, value in first.transcriptions if sid == system_id), None)
        if not value:
            return Reading(character, system_id, selected_period, None,
                source_status="missing_reconstruction",
                note="该字有《中原音韵》条目，但没有此学者方案的转写。")
        system = get_system(system_id)
        return Reading(
            character, system_id, selected_period, None,
            source_status="source_reconstruction",
            provenance=Provenance(
                source_title="中原音韵数据集",
                source_author="nk2028/zhongyuan-data contributors; scholarly reconstructions as attributed in upstream README",
                source_url=SOURCE_URL,
                source_version=f"Git blob {SOURCE_BLOB_SHA}",
                page_or_entry=f"小韵 {first.xiaoyun}; {system.scholar} column",
                derivation_rule=system.name,
                confidence="medium",
                evidence_note="保留上游学者方案的原始转写；此字段不表示项目已验证其可直接语音合成。",
            ),
            note=f"《中原音韵》{system.name}。原始转写已接入；尚未声明为可直接 TTS 合成。",
            initial=first.initial or None,
            final=first.final or None,
            tone=first.tone or None,
            transcription=value,
            transcription_scheme=system.name,
        )

    if system_id == "guangyun_qieyun_position":
        from .qieyun_data import lookup_qieyun_positions, SOURCE_URL, SOURCE_BLOB_SHA
        records = lookup_qieyun_positions(character)
        if not records:
            return Reading(character, system_id, selected_period, None,
                source_status="missing_character",
                note="《廣韻》反切音韻地位表中无此小韻首字记录。")
        first = records[0]
        note = "原始音韻地位資料，不是 IPA 或可直接合成的讀音。"
        if len(records) > 1:
            note += f" 此字有 {len(records)} 条小韻记录；请用 lookup_qieyun_positions() 查看全部。"
        if first.has_multiple_descriptions:
            note += " 原始字段含多个音韻描述，均予保留。"
        return Reading(
            character, system_id, selected_period, None,
            source_status="source_record",
            provenance=Provenance(
                source_title="《廣韻》反切音韻地位表",
                source_author="nk2028/tshet-uinh-data contributors",
                source_url=SOURCE_URL,
                source_version=f"Git blob {SOURCE_BLOB_SHA}",
                page_or_entry=f"小韻号 {first.xiaoyun_id}",
                confidence="unassessed",
                evidence_note="资料行的音韻地位描述照原样保存；本项目尚未将其转写为学者拟音。",
            ),
            note=note,
            phonological_position=first.position_description or None,
            xiaoyun_id=first.xiaoyun_id or None,
            fanqie_upper=first.fanqie_upper or None,
            fanqie_lower=first.fanqie_lower or None,
        )

    if system_id in SINICA_SCHOLAR_SYSTEMS:
        from .sinica_scholar_data import lookup_scholar_reading
        records = lookup_scholar_reading(character, system_id)
        system = get_system(system_id)
        system_name = system.name
        if not records:
            return Reading(character, system_id, selected_period, None,
                source_status="missing_character",
                note=f"Sinica 汉字构形资料库中「{system_name}」无此字条。")
        # 多音字里可能只有个别行错位，优先取非错位的记录
        clean = [r for r in records if not r.suspect]
        first = clean[0] if clean else records[0]
        if not clean:
            # 源表该行聲母列存在错位或缺损，拼 IPA 会得到假读音，故不给 ipa
            return Reading(
                character, system_id, selected_period, None,
                initial=first.initial or None,
                final=first.final or None,
                rhyme_group=first.rhyme_group or None,
                source_status="source_record_defect",
                provenance=Provenance(
                    source_title=f"漢字構形資料庫 {first.source_workbook or system_name}",
                    source_author="中央研究院 資訊科學研究所（xiaoxue.iis.sinica.edu.tw）",
                    source_url="https://xiaoxue.iis.sinica.edu.tw/ccrdata/",
                    page_or_entry=f"{first.source_sheet} 第 {first.source_row} 行",
                    confidence="unassessed",
                    evidence_note="源表聲母列存在错位或缺损（填入韻母值/韻部名、只剩送氣符等），不作拟音使用。",
                ),
                note=first.note or "源表该字條的聲母列存在缺陷，本接口不生成 IPA，需回查原表。",
                transcription=first.final or None,
                transcription_scheme=system_name,
            )
        note = (f"{system_name} 逐字拟音，聲母+韻母已按原样拼接。"
                "上游无聲調字段，故不含声调，不能据此判断调类。")
        if first.rhyme_group:
            note += f" 韻部：{first.rhyme_group}。"
        if first.upstream_note:
            note += f" 上游備註：{first.upstream_note}"
        if len(records) > 1:
            note += f" 此字有 {len(records)} 条记录（多音）；请用 lookup_scholar_reading() 查看全部。"
        return Reading(
            character, system_id, selected_period, first.ipa,
            initial=first.initial or None,
            final=first.final or None,
            tone=None,      # 上游确实没有声调，不编造
            rhyme_group=first.rhyme_group or None,
            source_status="scholar_reconstruction",
            provenance=Provenance(
                source_title=f"漢字構形資料庫 {first.source_workbook or system_name}",
                source_author="中央研究院 資訊科學研究所（xiaoxue.iis.sinica.edu.tw）",
                source_url="https://xiaoxue.iis.sinica.edu.tw/ccrdata/",
                source_version=f"sha256 {first.source_sha256}" if first.source_sha256 else "",
                page_or_entry=f"{first.source_sheet} 第 {first.source_row} 行",
                derivation_rule=("原表 聲母 + 韻母 直接拼接"
                                 "（零聲母 0／· → 无辅音；·w → 介音 w + 韻母）"),
                confidence="medium",
                evidence_note=("逐字拟音表原样接入，未做音值推演；声调缺失；"
                               "ȶ/ȡ/ȣ/ɽ 等是各方案惯用写法，能否送入合成器见"
                               "v5 第三阶段音素能力矩阵。"),
            ),
            note=note,
            transcription=first.ipa,
            transcription_scheme=system_name,
        )

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


# ===== 同字跨体系对照（第二阶段②「争议项」视图的数据层）=====

@dataclass(frozen=True, slots=True)
class SystemComparisonRow:
    """一个体系下某个字的全部值（values 可有多条：多音字／多个小韵）。"""
    system_id: str
    system_name: str
    value_kind: str            # "ipa" | "transcription" | "position" | "none"
    values: tuple
    rhyme_group: Optional[str] = None
    source_status: str = "none"
    suspect: bool = False
    upstream_note: str = ""
    note: str = ""

    @property
    def has_value(self) -> bool:
        return bool(self.values)


@dataclass(frozen=True, slots=True)
class CharacterComparison:
    """一个时期内所有已接入体系对同一字的结果。缺就是缺，绝不跨体系补。"""
    character: str
    period_id: str
    rows: tuple

    @property
    def distinct_values(self) -> tuple:
        seen = []
        for row in self.rows:
            for value in row.values:
                if value and value not in seen:
                    seen.append(value)
        return tuple(seen)

    @property
    def disagrees(self) -> bool:
        return len(self.distinct_values) > 1

    @property
    def system_ids_with_values(self) -> tuple:
        return tuple(r.system_id for r in self.rows if r.has_value)

    @property
    def system_ids_without_values(self) -> tuple:
        return tuple(r.system_id for r in self.rows if not r.has_value)


def _compare_scholar_row(character: str, system: ReconstructionSystem) -> SystemComparisonRow:
    from .sinica_scholar_data import lookup_scholar_reading
    records = lookup_scholar_reading(character, system.id)
    if not records:
        return SystemComparisonRow(system.id, system.name, "none", (),
            source_status="missing_character",
            note=f"Sinica 汉字构形资料库「{system.name}」无此字条。")
    clean = [r for r in records if not r.suspect]
    first = clean[0] if clean else records[0]
    values = tuple(r.ipa for r in clean)
    if not clean:
        note = "源表此字条声母列存在缺陷（错位/缺损），不生成 IPA，需回查原表。"
    elif len(records) > 1:
        note = f"此字有 {len(records)} 条记录（多音），上列全部值。"
    else:
        note = ""
    return SystemComparisonRow(
        system.id, system.name,
        "ipa" if clean else "none",
        values,
        rhyme_group=first.rhyme_group,
        source_status="scholar_reconstruction" if clean else "source_record_defect",
        suspect=not clean,
        upstream_note=first.upstream_note or "",
        note=note,
    )


def _compare_legacy_row(character: str, system: ReconstructionSystem) -> SystemComparisonRow:
    try:
        from phonology_db import EASTERN_HAN_DB
    except (ImportError, AttributeError):
        EASTERN_HAN_DB = {}
    item = EASTERN_HAN_DB.get(character)
    if not item or not item.get("ipa"):
        return SystemComparisonRow(system.id, system.name, "none", (),
            source_status="missing_character",
            note="现有东汉实验字表中无此字条。")
    return SystemComparisonRow(system.id, system.name, "ipa", (str(item["ipa"]),),
        source_status="legacy_experimental",
        note="项目实验拟音，非已确立的历史读音。")


def _compare_qieyun_row(character: str, system: ReconstructionSystem) -> SystemComparisonRow:
    from .qieyun_data import lookup_qieyun_positions
    records = lookup_qieyun_positions(character)
    values = tuple(r.position_description for r in records if r.position_description)
    if not values:
        return SystemComparisonRow(system.id, system.name, "none", (),
            source_status="missing_character",
            note="《廣韻》反切音韻地位表中无此小韻首字记录。")
    note = "原始音韻地位資料，不是 IPA。"
    if len(records) > 1:
        note += f" 此字有 {len(records)} 条小韻记录。"
    return SystemComparisonRow(system.id, system.name, "position", values,
        source_status="source_record", note=note)


def _compare_transcription_row(character: str, system: ReconstructionSystem,
                               lookup, missing_note: str) -> SystemComparisonRow:
    records = lookup(character, system.id)
    values = tuple(
        value for record in records
        for scheme_id, value in record.transcriptions
        if scheme_id == system.id and value
    )
    if not records:
        return SystemComparisonRow(system.id, system.name, "none", (),
            source_status="missing_character", note=missing_note)
    if not values:
        return SystemComparisonRow(system.id, system.name, "none", (),
            source_status="missing_reconstruction",
            note="该字有数据条目，但没有此学者方案的转写。")
    return SystemComparisonRow(system.id, system.name, "transcription", values,
        source_status="source_reconstruction",
        note="原始转写逐字保留；不是 IPA，不保证可直接合成。")


def compare_character(character: str, period_id: str) -> CharacterComparison:
    """同一字在某个时期全部已接入体系下的对照结果。

    缺记录、缺方案、源表缺陷都如实标记；不同体系的值只并排陈列，
    不合并、不互推——这正是「各体系不可混用」证据的呈现方式。
    """
    if len(character) != 1:
        raise ValueError("compare_character expects exactly one character")
    get_period(period_id)
    rows = []
    for system in systems_for_period(period_id, include_metadata_only=False):
        if system.id in SINICA_SCHOLAR_SYSTEMS:
            rows.append(_compare_scholar_row(character, system))
        elif system.id == "han_eastern_experimental":
            rows.append(_compare_legacy_row(character, system))
        elif system.id == "guangyun_qieyun_position":
            rows.append(_compare_qieyun_row(character, system))
        elif system.id == "phono_ml_baxter_sagart_mc":
            from .phono_ml_data import lookup_phono_ml
            records = lookup_phono_ml(character)
            values = tuple(r.transcription for r in records if r.transcription)
            if not values:
                rows.append(SystemComparisonRow(system.id, system.name, "none", (),
                    source_status="missing_character",
                    note="PHONO-ML 数据集中无此字条。"))
            else:
                rows.append(SystemComparisonRow(system.id, system.name, "transcription",
                    values, source_status="source_reconstruction",
                    note="Baxter–Sagart 风格中古音转写，不是 IPA。"))
        elif system.id.startswith("zhongyuan_"):
            from .zhongyuan_data import lookup_zhongyuan
            rows.append(_compare_transcription_row(
                character, system, lookup_zhongyuan,
                "《中原音韵》数据集中无此字的对应方案记录。"))
        else:
            rows.append(SystemComparisonRow(system.id, system.name, "none", (),
                source_status="not_integrated",
                note="该体系已登记，但尚无可核验的逐字数据。"))
    return CharacterComparison(character, period_id, tuple(rows))
