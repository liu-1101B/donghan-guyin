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
    phonological_position: Optional[str] = None
    xiaoyun_id: Optional[str] = None
    fanqie_upper: Optional[str] = None
    fanqie_lower: Optional[str] = None
    transcription: Optional[str] = None
    transcription_scheme: Optional[str] = None

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
