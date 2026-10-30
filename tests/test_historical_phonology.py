"""Tests for historical timeline and reconstruction metadata."""
import unittest
import gzip
import json
import tempfile
from pathlib import Path
from language.history import (TIMELINE, get_period, get_system, lookup_reading,
                              lookup_qieyun_positions, period_at,
                              qieyun_record_count, systems_for_period,
                              lookup_phono_ml, phono_ml_record_count,
                              lookup_zhongyuan, zhongyuan_record_count,
                              dataset_available, lookup_sinica_ccr_records,
                              sinica_ccr_record_count, sinica_ccr_package_counts,
                              lookup_scholar_reading, scholar_character_count,
                              scholar_coverage, SCHOLAR_SYSTEMS,
                               SCHOLAR_SYSTEMS_OLD,
                               compare_character)
from phonology_db import EASTERN_HAN_DB
from language.history import eastern_mc_correspondence as emc
from language.history.qieyun_data import (
    load_qieyun_positions as load_qieyun_positions_all,
)
from language.ancient_tts import text_to_ipa
from language.polyphone import (
    MODERN_TO_TONE_CLASS,
    _empirical_votes,
    segment,
    select_reading,
)
from language.phoneme_capability import (
    ESPEAK_IPA_MAP, classify_symbol, assess_ipa, system_capability_report,
    _formant_status, OK, APPROX, SILENT, COMBINING, JUNK,
)
from sound_synth import preprocess_ipa




class SinicaScholarSystemsTests(unittest.TestCase):
    """六个中古学者方案共用的契约。"""

    def test_all_six_systems_are_registered_and_queryable(self):
        self.assertEqual(len(SCHOLAR_SYSTEMS), 6)
        for system_id in SCHOLAR_SYSTEMS:
            reading = lookup_reading("東", system_id)
            self.assertTrue(reading.available, system_id)
            self.assertEqual(reading.source_status, "scholar_reconstruction", system_id)

    def test_all_systems_appear_in_middle_chinese_filter(self):
        ids = {s.id for s in systems_for_period("middle_chinese",
                                                include_metadata_only=False)}
        for system_id in SCHOLAR_SYSTEMS:
            self.assertIn(system_id, ids)

    def test_systems_disagree_showing_they_are_separate_scholars(self):
        # 同一个「融」，六家拟音不该被折叠成同一个值
        values = {lookup_reading("融", sid).ipa for sid in SCHOLAR_SYSTEMS}
        self.assertGreater(len(values), 3)

    def test_no_system_invents_a_tone(self):
        for system_id in SCHOLAR_SYSTEMS:
            self.assertIsNone(lookup_reading("東", system_id).tone, system_id)

    def test_lifanggui_ji_initial_is_not_treated_as_defect(self):
        # 李方桂用 ji- 表示喻母，是合法声母；启发式曾误判它 974 行
        reading = lookup_reading("融", "lifanggui_mc")
        self.assertTrue(reading.available)
        self.assertEqual(reading.initial, "ji")
        self.assertFalse(reading.source_status == "source_record_defect")
        cov = scholar_coverage("lifanggui_mc")
        self.assertEqual(cov["skipped_suspect_initial"], 0)

    def test_vowel_initial_rows_are_still_caught(self):
        # 王力 13 行、周法高 5 行确属错位，规则收紧后仍要抓到
        self.assertEqual(scholar_coverage("wangli_mc")["skipped_suspect_initial"], 13)
        self.assertEqual(scholar_coverage("zhoufagao_mc")["skipped_suspect_initial"], 5)

    def test_karlgren_has_lower_coverage_than_others(self):
        # 高本漢表只有 7685 条，覆盖率明显更低，属已知事实
        self.assertLess(scholar_character_count("karlgren_mc"), 10000)
        self.assertGreater(scholar_character_count("wangli_mc"), 19000)


class WangLiMiddleChineseTests(unittest.TestCase):
    """王力中古拟音（Sinica 汉字构形资料库）接入的契约。"""

    def test_dataset_is_bundled_and_queryable(self):
        self.assertGreater(scholar_character_count("wangli_mc"), 19000)
        self.assertTrue(lookup_scholar_reading("東", "wangli_mc"))

    def test_reading_composes_initial_and_final(self):
        reading = lookup_reading("東", "wangli_mc")
        self.assertTrue(reading.available)
        self.assertEqual(reading.ipa, "tuŋ")
        self.assertEqual(reading.initial, "t")
        self.assertEqual(reading.final, "uŋ")
        self.assertEqual(reading.source_status, "scholar_reconstruction")

    def test_tone_is_never_invented(self):
        # 上游没有聲調字段，任何字都不该凭空出现声调
        for ch in ("東", "天", "人", "中", "國"):
            self.assertIsNone(lookup_reading(ch, "wangli_mc").tone)

    def test_defective_source_row_yields_no_ipa(self):
        # 源表这些行把韵母值填进了聲母列，拼出来会是假拟音
        reading = lookup_reading("弩", "wangli_mc")
        self.assertFalse(reading.available)
        self.assertIsNone(reading.ipa)
        self.assertEqual(reading.source_status, "source_record_defect")

    def test_multi_reading_character_keeps_all_rows(self):
        self.assertGreater(len(lookup_scholar_reading("哆", "wangli_mc")), 1)

    def test_integrated_in_middle_chinese_filter(self):
        ids = [s.id for s in systems_for_period("middle_chinese",
                                                include_metadata_only=False)]
        self.assertIn("wangli_mc", ids)

    def test_coverage_reports_declare_skips(self):
        cov = scholar_coverage("wangli_mc")
        self.assertIs(cov["tone_available"], False)
        self.assertEqual(cov["skipped_suspect_initial"], 13)
        self.assertEqual(cov["skipped_not_single_char"], 13)
        self.assertEqual(cov["matched_records"],
                         cov["records"] + cov["skipped_not_single_char"]
                         + cov["skipped_empty_final"])


class TimelineTests(unittest.TestCase):
    def test_eastern_han_period(self):
        p = get_period("eastern_han")
        self.assertEqual((p.start_year, p.end_year), (25, 220))
        self.assertTrue(p.contains(100))

    def test_overlapping_ranges_are_preserved(self):
        ids = {p.id for p in period_at(100)}
        self.assertIn("old_chinese", ids)
        self.assertIn("eastern_han", ids)

    def test_unknown_period_raises(self):
        with self.assertRaises(KeyError):
            get_period("not-a-period")

    def test_timeline_ids_unique(self):
        self.assertGreaterEqual(len(TIMELINE), 5)
        self.assertEqual(len({p.id for p in TIMELINE}), len(TIMELINE))


class SystemsTests(unittest.TestCase):
    def test_systems_and_periods_are_separate(self):
        old = get_system("baxter_sagart_oc")
        self.assertTrue(old.supports_period("old_chinese"))
        self.assertFalse(old.supports_period("middle_chinese"))

    def test_integrated_system_filter(self):
        got = systems_for_period("eastern_han", include_metadata_only=False)
        self.assertEqual([s.id for s in got], ["han_eastern_experimental"])


    def test_guangyun_dataset_is_bundled_and_queryable(self):
        self.assertGreater(qieyun_record_count(), 3000)
        records = lookup_qieyun_positions("東")
        self.assertTrue(records)
        self.assertEqual(records[0].xiaoyun_id, "1")
        self.assertEqual(records[0].position_description, "端一東平")

    def test_guangyun_source_record_is_not_mislabeled_as_ipa(self):
        reading = lookup_reading("東", "guangyun_qieyun_position")
        self.assertTrue(reading.has_record)
        self.assertFalse(reading.available)
        self.assertEqual(reading.source_status, "source_record")
        self.assertEqual(reading.phonological_position, "端一東平")
        self.assertEqual(reading.provenance.confidence, "unassessed")
        self.assertIn("93ca1b1551b30bba9c76fe21078f156b8299d9cc",
                      reading.provenance.source_version)

    def test_integrated_dataset_is_available_in_middle_chinese_filter(self):
        systems = systems_for_period("middle_chinese", include_metadata_only=False)
        self.assertIn("guangyun_qieyun_position", [s.id for s in systems])


    def test_phono_ml_dataset_is_bundled_and_queryable(self):
        self.assertGreater(phono_ml_record_count(), 20000)
        records = lookup_phono_ml("東")
        self.assertTrue(records)
        self.assertTrue(records[0].transcription)
        self.assertEqual(records[0].transcription_scheme,
                         "Baxter-Sagart Middle Chinese transcription")

    def test_phono_ml_reading_is_not_mislabeled_as_ipa(self):
        reading = lookup_reading("東", "phono_ml_baxter_sagart_mc")
        self.assertTrue(reading.has_record)
        self.assertFalse(reading.available)
        self.assertEqual(reading.source_status, "source_reconstruction")
        self.assertTrue(reading.transcription)
        self.assertIn("e371665481c70b56534a618f42f620567ae5a762",
                      reading.provenance.source_version)

    def test_zhongyuan_dataset_has_multiple_scholarly_systems(self):
        self.assertGreater(zhongyuan_record_count(), 5000)
        records = lookup_zhongyuan("東", "zhongyuan_yangnaisi")
        self.assertTrue(records)
        self.assertEqual(records[0].transcriptions[0][0], "zhongyuan_yangnaisi")
        self.assertTrue(dict(records[0].transcriptions)["zhongyuan_yangnaisi"])

    def test_zhongyuan_reading_is_scheme_specific_and_traceable(self):
        reading = lookup_reading("東", "zhongyuan_yangnaisi")
        self.assertTrue(reading.has_record)
        self.assertFalse(reading.available)
        self.assertEqual(reading.source_status, "source_reconstruction")
        self.assertTrue(reading.transcription)
        self.assertEqual(reading.transcription_scheme, "中原音韵拟音（杨耐思）")
        self.assertIn("74b2b30565a2ac4c47b309fe1ff804c6b438c4a9",
                      reading.provenance.source_version)

    def test_new_systems_appear_in_period_filters(self):
        mc = systems_for_period("middle_chinese", include_metadata_only=False)
        yuan = systems_for_period("early_mandarin", include_metadata_only=False)
        self.assertIn("phono_ml_baxter_sagart_mc", [s.id for s in mc])
        self.assertIn("zhongyuan_yangnaisi", [s.id for s in yuan])

    def test_unintegrated_system_does_not_invent_ipa(self):
        r = lookup_reading("天", "baxter_sagart_oc")
        self.assertFalse(r.available)
        self.assertEqual(r.source_status, "not_integrated")
        self.assertIsNone(r.ipa)

    def test_legacy_adapter_marks_experimental_data(self):
        r = lookup_reading("天", "han_eastern_experimental", legacy_db={
            "天": {"ipa": "tʰen", "init": "透母", "final": "真韵", "tone": "平声"}})
        self.assertTrue(r.available)
        self.assertTrue(r.approximation)
        self.assertEqual(r.source_status, "legacy_experimental")
        self.assertIn("实验性", r.note)

    def test_missing_character_is_not_guessed(self):
        r = lookup_reading("龘", "han_eastern_experimental", legacy_db={})
        self.assertFalse(r.available)
        self.assertEqual(r.source_status, "missing_character")

    def test_requires_one_character(self):
        with self.assertRaises(ValueError):
            lookup_reading("中国", "han_eastern_experimental")



class SinicaCCRDataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "records.jsonl.gz"
        self.fixture = [
            {
                "dataset_id": "sinica_ccr_old_chinese",
                "source_url": "https://xiaoxue.iis.sinica.edu.tw/ccrdata/file/ccr01_shangguyin_data_xlsx.zip",
                "license_mark": "PDM",
                "period": "东汉",
                "system": "韵部资料",
                "record_type": "historical_rhyme_group",
                "source_workbook": "007 兩漢_東漢.xlsx",
                "source_sheet": "_007_兩漢_東漢",
                "source_row": 2,
                "source_workbook_sha256": "a" * 64,
                "character": "東",
                "fields": {"字號": "1", "字": "東", "韻部": "東"},
            },
            {
                "dataset_id": "sinica_ccr_middle_chinese",
                "source_url": "https://xiaoxue.iis.sinica.edu.tw/ccrdata/file/ccr02_zhongguyin_data_xlsx.zip",
                "license_mark": "PDM",
                "period": "隋唐",
                "system": "王力系統",
                "record_type": "scholar_reconstruction",
                "source_workbook": "014 隋唐_擬音_王力系統.xlsx",
                "source_sheet": "_014_隋唐_擬音_王力系統",
                "source_row": 2,
                "source_workbook_sha256": "b" * 64,
                "character": "東",
                "fields": {"字號": "1", "字": "東", "聲母": "t", "韻母": "uŋ"},
            },
        ]
        with gzip.open(self.path, "wt", encoding="utf-8", newline="") as handle:
            for row in self.fixture:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dataset_path_and_multiple_readings(self):
        self.assertTrue(dataset_available(str(self.path)))
        rows = lookup_sinica_ccr_records("東", path=str(self.path))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].character, "東")
        self.assertEqual(rows[0].license_mark, "PDM")
        self.assertTrue(any("007 兩漢_東漢.xlsx" in row.source_location for row in rows))

    def test_filtering_and_source_fields_are_preserved(self):
        rows = lookup_sinica_ccr_records(
            "東", dataset_id="sinica_ccr_middle_chinese",
            period="隋唐", workbook_keyword="王力", path=str(self.path),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].fields["聲母"], "t")
        self.assertEqual(rows[0].fields["韻母"], "uŋ")
        self.assertEqual(rows[0].system, "王力系統")
        self.assertEqual(rows[0].source_row, 2)

    def test_record_counts_by_package(self):
        self.assertEqual(sinica_ccr_record_count(path=str(self.path)), 2)
        self.assertEqual(
            sinica_ccr_record_count(dataset_id="sinica_ccr_old_chinese", path=str(self.path)),
            1,
        )
        self.assertEqual(
            sinica_ccr_package_counts(path=str(self.path)),
            {"sinica_ccr_middle_chinese": 1, "sinica_ccr_old_chinese": 1},
        )


    def test_official_sinica_payload_is_bundled_and_queryable(self):
        self.assertTrue(dataset_available())
        self.assertEqual(sinica_ccr_record_count(), 378214)
        records = lookup_sinica_ccr_records(
            "東",
            dataset_id="sinica_ccr_old_chinese",
            period="东汉",
            limit=20,
        )
        self.assertTrue(records)
        self.assertTrue(any(record.fields.get("韻部") == "東" for record in records))
        self.assertTrue(all(record.license_mark == "PDM" for record in records))

    def test_missing_bundle_raises_actionable_error(self):
        missing = Path(self.temp_dir.name) / "missing.jsonl.gz"
        with self.assertRaisesRegex(FileNotFoundError, "Extract sinica_ccr_records"):
            lookup_sinica_ccr_records("東", path=str(missing))


class SinicaScholarOldChineseTests(unittest.TestCase):
    """五个上古（先秦）学者方案共用的契约。"""

    def test_all_five_old_systems_are_registered_and_queryable(self):
        self.assertEqual(len(SCHOLAR_SYSTEMS_OLD), 5)
        for system_id in SCHOLAR_SYSTEMS_OLD:
            reading = lookup_reading("東", system_id)
            self.assertTrue(reading.available, system_id)
            self.assertEqual(reading.source_status, "scholar_reconstruction", system_id)

    def test_old_systems_appear_in_old_chinese_filter_only(self):
        ids = {s.id for s in systems_for_period("old_chinese",
                                                include_metadata_only=False)}
        for system_id in SCHOLAR_SYSTEMS_OLD:
            self.assertIn(system_id, ids)

    def test_east_ipa_matches_upstream_sheets(self):
        # 001–005 先秦表的 東：t+uŋ / t+ɔŋ / t+ûŋ / t+ewŋ / t+ung
        # 上游「û」按分解形式存储（u + U+0302），断言用显式码点，不重编码
        self.assertEqual(lookup_reading("東", "karlgren_oc").ipa, "tu\u014b")
        self.assertEqual(lookup_reading("東", "wangli_oc").ipa, "t\u0254\u014b")
        self.assertEqual(lookup_reading("東", "dongtonghe_oc").ipa, "tu\u0302\u014b")
        self.assertEqual(lookup_reading("東", "zhoufagao_oc").ipa, "tewŋ")
        self.assertEqual(lookup_reading("東", "lifanggui_oc").ipa, "tung")

    def test_rhyme_group_carried_through(self):
        for system_id in ("wangli_oc", "dongtonghe_oc", "zhoufagao_oc", "lifanggui_oc"):
            self.assertEqual(lookup_reading("東", system_id).rhyme_group, "東")
        # 001 高本漢表没有「韻部」栏
        self.assertIsNone(lookup_reading("東", "karlgren_oc").rhyme_group)

    def test_no_old_system_invents_a_tone(self):
        for system_id in SCHOLAR_SYSTEMS_OLD:
            self.assertIsNone(lookup_reading("東", system_id).tone, system_id)

    def test_systems_disagree_on_rong(self):
        # 同一个「融」，各家拟音不该被折叠；高本漢先秦表无此字（报缺）
        values = {lookup_reading("融", sid).ipa for sid in SCHOLAR_SYSTEMS_OLD
                  if lookup_reading("融", sid).available}
        self.assertGreaterEqual(len(values), 4)
        self.assertEqual(
            lookup_reading("融", "karlgren_oc").source_status, "missing_character")
        for system_id in ("dongtonghe_oc", "zhoufagao_oc", "lifanggui_oc"):
            self.assertEqual(len(lookup_scholar_reading("融", system_id)), 2)

    def test_zero_initial_marks_compose_as_no_onset(self):
        # 王力表用 "0"，李方桂表用 U+0387（点）；都按无辅音处理
        wangli = lookup_reading("翁", "wangli_oc")
        self.assertEqual(wangli.initial, "0")
        self.assertEqual(wangli.ipa, "ɔŋ")
        self.assertFalse(lookup_scholar_reading("翁", "wangli_oc")[0].has_initial)
        lifanggui = lookup_reading("翁", "lifanggui_oc")
        self.assertEqual(lifanggui.initial, "\u0387")
        self.assertEqual(lifanggui.ipa, "ung")
        self.assertFalse(lifanggui.ipa.startswith("\u0387"))

    def test_zero_initial_with_glide_keeps_the_glide(self):
        # 委（李方桂）= ·w + jər → wjər，介音 w 不能丢
        reading = lookup_reading("委", "lifanggui_oc")
        self.assertTrue(reading.ipa.startswith("w"))
        self.assertIn(reading.ipa, {"wjər", "wjərx"})
        self.assertTrue(lookup_scholar_reading("委", "lifanggui_oc")[0].has_initial)

    def test_html_entity_initials_are_decoded(self):
        # '&#609' → ȡ（高本漢 異），'&#611' → ȣ（董同龢 囩）
        self.assertEqual(lookup_reading("異", "karlgren_oc").initial, "\u0261")
        self.assertEqual(lookup_reading("囩", "dongtonghe_oc").initial, "\u0263")

    def test_fullwidth_initial_is_normalized(self):
        # 王力表 屁 的聲母上游误写为全角 ｐ，机械还原为 p；
        # 韻母「ǐ」按分解形式存储（i + U+030C），不重编码
        reading = lookup_reading("屁", "wangli_oc")
        self.assertEqual(reading.initial, "p")
        self.assertEqual(reading.ipa, "pi\u030cei")

    def test_upstream_note_preserved_verbatim(self):
        records = lookup_scholar_reading("美", "lifanggui_oc")
        self.assertTrue(records)
        self.assertTrue(any("脂韻重紐" in r.upstream_note for r in records))

    def test_suspect_counts_per_old_system(self):
        # 高本漢 8 行只剩送氣符；王力 4 行聲母列填了韻部名 + 4 行填了韻母值；
        # 其余三家无错位
        self.assertEqual(scholar_coverage("karlgren_oc")["skipped_suspect_initial"], 8)
        self.assertEqual(scholar_coverage("wangli_oc")["skipped_suspect_initial"], 8)
        self.assertEqual(scholar_coverage("dongtonghe_oc")["skipped_suspect_initial"], 0)
        self.assertEqual(scholar_coverage("zhoufagao_oc")["skipped_suspect_initial"], 0)
        self.assertEqual(scholar_coverage("lifanggui_oc")["skipped_suspect_initial"], 0)

    def test_karlgren_empty_finals_are_counted_not_dropped(self):
        # 530 行韻母为空 + 5 行「?」= 535，全部计入并如实暴露
        cov = scholar_coverage("karlgren_oc")
        self.assertEqual(cov["skipped_empty_final"], 535)
        self.assertEqual(cov["matched_records"],
                         cov["records"] + cov["skipped_not_single_char"]
                         + cov["skipped_empty_final"])
        # 中 在高本漢先秦表两条记录韻母皆空 → 该体系报「缺」，不编造
        self.assertEqual(lookup_reading("中", "karlgren_oc").source_status,
                         "missing_character")
        self.assertTrue(lookup_reading("中", "wangli_oc").available)

    def test_defect_and_entity_rows_are_counted(self):
        self.assertEqual(scholar_coverage("karlgren_oc")["entity_decoded"], 2)
        self.assertEqual(scholar_coverage("dongtonghe_oc")["entity_decoded"], 2)
        self.assertEqual(scholar_coverage("wangli_oc")["zero_initial"], 374)
        self.assertEqual(scholar_coverage("lifanggui_oc")["zero_initial"], 465)
        self.assertEqual(scholar_coverage("lifanggui_oc")["glide_onset"], 153)
        self.assertEqual(scholar_coverage("lifanggui_oc")["upstream_note_rows"], 96)



class CompareCharacterTests(unittest.TestCase):
    """第二阶段②：同字跨体系对照（数据层契约）。"""

    def test_middle_chinese_rong_six_scholars_six_values(self):
        cmp = compare_character("融", "middle_chinese")
        by_id = {r.system_id: r for r in cmp.rows}
        self.assertTrue(set(SCHOLAR_SYSTEMS) <= set(by_id))
        # 广韵地位 + phono_ml 行也在，值类型不同
        self.assertEqual(by_id["guangyun_qieyun_position"].value_kind, "position")
        self.assertEqual(by_id["phono_ml_baxter_sagart_mc"].value_kind, "transcription")
        scholar_values = [by_id[sid].values for sid in SCHOLAR_SYSTEMS]
        for sid, values in zip(SCHOLAR_SYSTEMS, scholar_values):
            self.assertEqual(by_id[sid].value_kind, "ipa", sid)
            self.assertTrue(values, sid)
        # 六家六值，不允许被折叠
        self.assertEqual(len({v[0] for v in scholar_values}), 6)
        self.assertTrue(cmp.disagrees)

    def test_old_chinese_rong_reports_karlgren_gap_and_multi_reading(self):
        cmp = compare_character("融", "old_chinese")
        by_id = {r.system_id: r for r in cmp.rows}
        self.assertIn("han_eastern_experimental", by_id)
        # 高本漢先秦表无此字：如实报缺，不拿别家值补
        self.assertEqual(by_id["karlgren_oc"].source_status, "missing_character")
        self.assertFalse(by_id["karlgren_oc"].has_value)
        self.assertIsNone(by_id["karlgren_oc"].rhyme_group)
        for sid in ("wangli_oc", "dongtonghe_oc", "zhoufagao_oc", "lifanggui_oc"):
            self.assertTrue(by_id[sid].has_value, sid)
            self.assertEqual(by_id[sid].value_kind, "ipa", sid)
        # 多音字全部值并排：dong/zhou/lifanggui 各 2 条，wangli 1 条
        for sid in ("dongtonghe_oc", "zhoufagao_oc", "lifanggui_oc"):
            self.assertEqual(len(by_id[sid].values), 2, sid)
        self.assertEqual(len(by_id["wangli_oc"].values), 1)
        self.assertEqual(by_id["wangli_oc"].rhyme_group, "冬")
        self.assertTrue(cmp.disagrees)

    def test_old_chinese_zhong_includes_legacy_row(self):
        # legacy 表以简体为键（「东」），繁体「東」精确查不到——与其他接口行为一致
        cmp = compare_character("中", "old_chinese")
        by_id = {r.system_id: r for r in cmp.rows}
        self.assertEqual(len(by_id), 6)
        legacy = by_id["han_eastern_experimental"]
        self.assertEqual(legacy.value_kind, "ipa")
        self.assertTrue(legacy.has_value)
        self.assertEqual(legacy.values[0], str(EASTERN_HAN_DB["中"]["ipa"]))
        # 中 在高本漢先秦表韵母为空 → 该体系报缺，不编造
        self.assertEqual(by_id["karlgren_oc"].source_status, "missing_character")
        for sid in ("wangli_oc", "dongtonghe_oc", "zhoufagao_oc", "lifanggui_oc"):
            self.assertEqual(by_id[sid].value_kind, "ipa", sid)
    def test_early_mandarin_rows_are_transcriptions(self):
        cmp = compare_character("東", "early_mandarin")
        self.assertEqual(len(cmp.rows), 5)
        for r in cmp.rows:
            self.assertTrue(r.system_id.startswith("zhongyuan_"), r.system_id)
            if r.has_value:
                self.assertEqual(r.value_kind, "transcription")

    def test_unknown_character_is_reported_missing_everywhere(self):
        cmp = compare_character("龘", "old_chinese")
        self.assertEqual(cmp.system_ids_with_values, ())
        self.assertEqual(cmp.system_ids_without_values,
                         tuple(r.system_id for r in cmp.rows))
        self.assertFalse(cmp.disagrees)
        for r in cmp.rows:
            self.assertIn(r.source_status,
                          {"missing_character", "missing_reconstruction"},
                          r.system_id)

    def test_invalid_arguments_raise(self):
        with self.assertRaises(ValueError):
            compare_character("abcd", "middle_chinese")
        with self.assertRaises(KeyError):
            compare_character("東", "nonexistent_period")


class TtsSystemRoutingTests(unittest.TestCase):
    """Phase 3 (1): text_to_ipa(system_id=...) routes to the chosen system."""

    def test_default_path_unchanged(self):
        r = text_to_ipa("中")  # 中
        self.assertEqual(r.coverage, 1)
        self.assertEqual(r.approx, 0)
        self.assertIsNone(r.system_id)
        self.assertEqual(r.ipa_text, str(EASTERN_HAN_DB["中"]["ipa"]))

    def test_scholar_system_uses_scholar_ipa(self):
        # 東 wangli_mc == tuŋ (frozen by MiddleChineseScholarTests)
        r = text_to_ipa("東", system_id="wangli_mc")
        self.assertEqual(r.system_id, "wangli_mc")
        self.assertEqual(r.coverage, 1)
        self.assertEqual(r.approx, 0)
        self.assertEqual(r.ipa_text, "tu" + "ŋ")

    def test_scholar_system_missing_not_approximated(self):
        # 龘 is absent from every Sinica table; no pinyin back-fill allowed
        r = text_to_ipa("龘", system_id="wangli_mc")
        self.assertEqual(r.coverage, 0)
        self.assertEqual(r.approx, 0)
        self.assertEqual(r.unknown, ["龘"])
        self.assertEqual(r.ipa_text, "")

    def test_scholar_system_karlgren_gap_reports_unknown(self):
        # 融 is missing from Karlgren's pre-Qin workbook
        r = text_to_ipa("融", system_id="karlgren_oc")
        self.assertEqual(r.unknown, ["融"])
        self.assertEqual(r.approx, 0)

    def test_non_ipa_system_rejected(self):
        for sid in ("guangyun_qieyun_position", "zhongyuan_unt",
                    "phono_ml_baxter_sagart_mc", "zhengzhang_oc"):
            with self.assertRaises(ValueError, msg=sid):
                text_to_ipa("融", system_id=sid)

    def test_unknown_system_id_raises_keyerror(self):
        with self.assertRaises(KeyError):
            text_to_ipa("融", system_id="nonexistent_system")

    def test_han_eastern_experimental_maps_to_legacy(self):
        r = text_to_ipa("中", system_id="han_eastern_experimental")
        self.assertEqual(r.coverage, 1)
        self.assertIsNone(r.system_id)
        self.assertEqual(r.ipa_text, str(EASTERN_HAN_DB["中"]["ipa"]))

    def test_mixed_text_counts(self):
        # 東 has a value in karlgren_oc; 龘 is absent from every OC table
        # (frozen by test_unknown_character_is_reported_missing_everywhere)
        r = text_to_ipa("東龘", system_id="karlgren_oc")
        self.assertEqual(r.coverage, 1)
        self.assertEqual(r.unknown, ["龘"])
        self.assertIn("tu" + "ŋ", r.ipa_text)

    def test_result_tracks_characters_for_ui(self):
        # Phase 3 (3): 逐字 (字, IPA, 状态) 供 UI「重建状态 × 合成能力」双列
        r = text_to_ipa("東", system_id="wangli_mc")
        self.assertEqual(r.characters, [("東", "tu" + "ŋ", "covered")])
        self.assertEqual(r.system_id, "wangli_mc")

    def test_scholar_unknown_character_tracked(self):
        # 融 absent from karlgren_oc (frozen) → (字, None, "unknown")，不进 IPA 串
        r = text_to_ipa("東融", system_id="karlgren_oc")
        self.assertEqual(r.characters[1], ("融", None, "unknown"))
        self.assertEqual(r.unknown, ["融"])

    def test_legacy_pinyin_approx_tracked(self):
        # 旧路径的拼音近似字也要进逐字明细（状态 "approx"）
        r = text_to_ipa("龍")  # 旧表 simplified-keyed，繁体字走拼音近似
        self.assertEqual(r.characters[0][2], "approx")
        self.assertEqual(r.approx, 1)
        self.assertIsNone(r.system_id)


def _first_clean_ipa(char, system_id):
    """该字在学者表的首条非 suspect 行 IPA（fallback_first 的选中值）。

    直接取数据侧真值，避免在测试里手敲含组合符号的 IPA 字面量。
    """
    from language.polyphone import to_traditional
    recs = lookup_scholar_reading(to_traditional(char), system_id)
    return next(r.ipa for r in recs if not r.suspect)


class PolyphoneSelectionTests(unittest.TestCase):
    """Phase 4 (3): 多音字词级选音（jieba 分词 + pypinyin 声调 + 经验地位映射）。

    原则：IPA 永远来自学者表本身；选不出就 fallback_first 并写明卡因，不猜测。
    """

    # ---- 基础行为 ----

    def test_tone_class_mapping(self):
        self.assertEqual(MODERN_TO_TONE_CLASS[1], frozenset({"平"}))
        self.assertEqual(MODERN_TO_TONE_CLASS[2], frozenset({"平"}))
        self.assertEqual(MODERN_TO_TONE_CLASS[3], frozenset({"上", "入"}))
        self.assertEqual(MODERN_TO_TONE_CLASS[4], frozenset({"去", "入"}))

    def test_segment_uses_jieba(self):
        words = segment("银行的行")
        self.assertIn("银行", words)
        self.assertIn("行走", segment("行走的行"))
        self.assertIn("解说", segment("解说文"))

    def test_single_record_char_is_single(self):
        s = select_reading("東", "東", "wangli_mc")
        self.assertEqual(s.method, "single")
        self.assertEqual(s.selected.ipa, "tuŋ")
        self.assertEqual(len(s.candidates), 1)
        self.assertIsNone(s.modern_tone)

    def test_no_records(self):
        s = select_reading("龘", "龘", "wangli_mc")
        self.assertEqual(s.method, "no_records")
        self.assertIsNone(s.selected)
        self.assertIn("无条目", s.note)

    def test_simplified_input_looks_up_traditional(self):
        # 东 → 東（s2t）；display 保留原字
        s = select_reading("东", "东", "wangli_mc")
        self.assertEqual(s.traditional, "東")
        self.assertEqual(s.character, "东")
        self.assertEqual(s.method, "single")
        self.assertEqual(s.selected.ipa, "tuŋ")

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            select_reading("行行", "行行", "wangli_mc")
        with self.assertRaises(KeyError):
            select_reading("行", "行", "nonexistent_system")

    # ---- 经验选音（method="empirical"） ----

    def test_empirical_jie_wangli(self):
        # 解：解说 (jie3, 上/入) → 見開佳上；同类字（佳/懈）一致读 kai
        s = select_reading("解", "解说文", "wangli_mc")
        self.assertEqual(s.method, "empirical")
        self.assertEqual(s.word, "解说")
        self.assertEqual(s.modern_tone, 3)
        self.assertEqual(s.tone_class, frozenset({"上", "入"}))
        self.assertEqual(s.selected.ipa, "kai")
        self.assertIn("見開佳上", s.note)

    def test_empirical_tu_wangli(self):
        # 土：率土之滨 (tu3, 上/入) → 透模上 → tʰu
        s = select_reading("土", "率土之滨", "wangli_mc")
        self.assertEqual(s.method, "empirical")
        self.assertEqual(s.selected.ipa, "tʰu")

    def test_empirical_hao_wangli(self):
        # 好：好人 (hao3, 上/入) → 曉豪上；蒿 平声一致读 hɑu
        s = select_reading("好", "好人好事", "wangli_mc")
        self.assertEqual(s.method, "empirical")
        self.assertEqual(s.selected.ipa, "hɑu")

    def test_empirical_xing_karlgren(self):
        # 行：行走 (xing2, 平) → 匣開二庚平；杏 一致读 ɣɐŋ
        s = select_reading("行", "行走的行", "karlgren_mc")
        self.assertEqual(s.method, "empirical")
        self.assertEqual(s.selected.ipa, "ɣɐŋ")
        self.assertEqual(s.word, "行走")
        self.assertEqual(s.modern_tone, 2)

    # ---- 不可判定 → fallback_first（诚实说明卡因） ----

    def test_fallback_xing_wangli_conflicting_votes(self):
        # 行：王力表 匣開二庚 类投票不一致（杏 ɣɐŋ / 垎 ɣɐk）→ 不确认
        s = select_reading("行", "银行的行", "wangli_mc")
        self.assertEqual(s.method, "fallback_first")
        self.assertEqual(s.selected.ipa, "ɣɑŋ")  # 首条
        self.assertEqual(len(s.candidates), 4)
        self.assertIn("无一致读法", s.note)
        self.assertEqual(s.word, "银行")
        self.assertEqual(s.modern_tone, 2)
        self.assertEqual(len(s.positions), 1)  # 匣開二庚平

    def test_fallback_zhong_wangli_value_mismatch(self):
        # 中：一致读法 ȶǐuk（竹 入声）与本字各行 ȶǐuŋ 不符 → 首条
        s = select_reading("中", "中国的字", "wangli_mc")
        self.assertEqual(s.method, "fallback_first")
        self.assertEqual(s.selected.ipa, _first_clean_ipa("中", "wangli_mc"))
        self.assertIn("不相符", s.note)
        self.assertEqual(s.modern_tone, 1)

    def test_fallback_zhong_qu_tone(self):
        # 打中 (zhong4, 去/入) → 東去地位，同样不可判定
        s = select_reading("中", "打中的字", "wangli_mc")
        self.assertEqual(s.method, "fallback_first")
        self.assertEqual(s.selected.ipa, _first_clean_ipa("中", "wangli_mc"))
        self.assertEqual(s.modern_tone, 4)
        self.assertEqual(s.tone_class, frozenset({"去", "入"}))

    def test_fallback_shuai_wangli_no_votes(self):
        # 率：生合眞入 类无任何无歧义投票字 → 首条 ʃwi
        s = select_reading("率", "率领大军", "wangli_mc")
        self.assertEqual(s.method, "fallback_first")
        self.assertEqual(s.selected.ipa, "ʃwi")
        self.assertIn("无一致读法", s.note)

    def test_fallback_hao_preference_no_position(self):
        # 好 (hao4, 去/入)：粗表只有 豪上 地位，无属去/入类地位
        s = select_reading("好", "喜好文雅", "wangli_mc")
        self.assertEqual(s.method, "fallback_first")
        self.assertEqual(s.selected.ipa, "hɑu")
        self.assertEqual(s.positions, ())
        self.assertIn("无属该调类的地位", s.note)

    # ---- text_to_ipa 接线 ----

    def test_empirical_votes_are_nontrivial(self):
        votes, voted_chars = _empirical_votes("wangli_mc")
        self.assertGreater(voted_chars, 1500)
        self.assertGreater(len(votes), 500)
        for vs in votes.values():
            for head, sheng, ipa in vs:
                self.assertTrue(ipa)
                self.assertIn(sheng, "平上去入")

    def test_text_to_ipa_selections_empirical(self):
        r = text_to_ipa("解说文", system_id="wangli_mc")
        self.assertEqual(r.coverage, 3)
        by_char = {ch: (ipa, method, note) for ch, ipa, method, note in r.selections}
        self.assertIn("解", by_char)
        self.assertEqual(by_char["解"][:2], ("kai", "empirical"))

    def test_text_to_ipa_selections_fallback(self):
        r = text_to_ipa("银行的行", system_id="wangli_mc")
        self.assertEqual(r.coverage, 4)
        xings = [(ipa, method) for ch, ipa, method, note in r.selections
                 if ch == "行"]
        self.assertEqual(xings, [("ɣɑŋ", "fallback_first")] * 2)
        self.assertIn("ɣɑŋ", r.ipa_text)
        self.assertIn(_first_clean_ipa("银", "wangli_mc"), r.ipa_text)  # 银

    def test_text_to_ipa_scholar_simplified_char(self):
        # 简繁：东 → 東，逐字明细显示原字
        r = text_to_ipa("东", system_id="wangli_mc")
        self.assertEqual(r.characters, [("东", "tuŋ", "covered")])
        self.assertEqual(r.selections, ())

    def test_text_to_ipa_legacy_selections_empty(self):
        r = text_to_ipa("中")
        self.assertEqual(r.selections, ())
        self.assertIsNone(r.system_id)

    def test_text_to_ipa_context_param(self):
        # context 显式覆盖：单字输入 + 外部上下文
        r = text_to_ipa("行", system_id="karlgren_mc", context="行走")
        xing = [s for s in r.selections if s[0] == "行"]
        self.assertEqual(len(xing), 1)
        self.assertEqual(xing[0][1], "ɣɐŋ")
        self.assertEqual(xing[0][2], "empirical")

    def test_text_to_ipa_xingzou_karlgren(self):
        r = text_to_ipa("行走", system_id="karlgren_mc")
        self.assertEqual(r.characters[0], ("行", "ɣɐŋ", "covered"))


class EraComparisonTests(unittest.TestCase):
    """Phase 4 (1): 一句话三时期音频对照（东汉 / 中古 / 现代）。"""

    def test_three_eras_produce_independent_audio(self):
        from language.era_audio import (make_era_comparison, ERA_EASTERN,
                                        ERA_MIDDLE, ERA_MODERN)
        eastern, middle, modern = make_era_comparison("天子")
        self.assertEqual((eastern.key, middle.key, modern.key),
                         (ERA_EASTERN, ERA_MIDDLE, ERA_MODERN))
        # 东汉：tʰen（洛阳官音重建，703 字旧表）
        self.assertTrue(eastern.has_audio)
        self.assertEqual(eastern.kind, "wav")
        self.assertIn("tʰen", eastern.ipa)
        # 中古王力：tʰien（与东汉同句不同音，正是对照的意义）
        self.assertTrue(middle.has_audio)
        self.assertIn("tʰien", middle.ipa)
        self.assertNotEqual(eastern.ipa, middle.ipa)
        self.assertEqual(middle.coverage_pct, 100.0)
        # 现代：有网 → 真 MP3；断网 → 诚实的 tts_unavailable，绝不伪造
        if modern.has_audio:
            self.assertEqual(modern.kind, "mp3")
            self.assertEqual(modern.status, "ok")
        else:
            self.assertEqual(modern.status, "tts_unavailable")
            self.assertIn("网络不可用", modern.note)

    def test_empty_text_reports_text_empty_for_all_eras(self):
        from language.era_audio import make_era_comparison
        for era in make_era_comparison(""):
            self.assertEqual(era.status, "text_empty")
            self.assertFalse(era.has_audio)
            self.assertTrue(era.note)

    def test_middle_system_label_and_unknown_id(self):
        from language.era_audio import make_era_comparison, \
            middle_system_label
        self.assertEqual(middle_system_label("wangli_mc"), "王力系統")
        self.assertEqual(middle_system_label("nope"), "nope")
        with self.assertRaises(KeyError):
            make_era_comparison("天子", middle_system="nonexistent")


class PhonemeCapabilityTests(unittest.TestCase):
    """Phase 3 (2): IPA → 合成器能力矩阵（eSpeak 主路径 + 共振峰回退）。"""

    # -- 静态分类 ----------------------------------------------------------

    def test_espeak_map_is_single_source_of_truth_for_preprocess(self):
        # 23 个映射、顺序敏感：整串过 preprocess_ipa 应得确定结果
        src = "\u02b0\u02b7\u02b2\u0268\u0259\u025b\u0254\u0251\u0250\u0252\u00e6\u014b\u0235\u0291\u0255\u0282\u0290\u0294\u0266\u028c\u0264\u026f\u0289"
        self.assertEqual(preprocess_ipa(src), "hwj1@EOAVQ{NJZSs`z`?hV7uu")
        # 映射表每个键都确实被替换
        for ch, alias in ESPEAK_IPA_MAP.items():
            self.assertNotIn(ch, preprocess_ipa(ch), ch)
            self.assertIn(alias, preprocess_ipa(ch), ch)

    def test_frozen_silent_symbols(self):
        # 实测（eSpeak-ng 1.52 -v zh）：这些符号整段被静默丢弃
        for ch in "\u00e4\u00e5\u00e7\u015b\u017a\u0221\u0236\u0256\u025f\u0261\u0263\u026a\u0271\u0272\u0273\u027d\u0283\u0285\u0288\u028e\u0292\u1e0d\u1e47\u1e63\u1e6d\u1e93\u1ead":
            self.assertEqual(classify_symbol(ch), SILENT, repr(ch))

    def test_mapped_and_ascii_symbols_are_ok(self):
        for ch in "\u014b\u0255\u02b0tskhng":
            self.assertEqual(classify_symbol(ch), OK, repr(ch))
        self.assertEqual(classify_symbol("&"), JUNK)

    def test_precomposed_accented_vowels_are_approx(self):
        for ch in "\u00e2\u0103\u00ef\u00fb\u00fc\u0115":
            self.assertEqual(classify_symbol(ch), APPROX, repr(ch))

    def test_combining_marks_depend_on_base_letter(self):
        self.assertEqual(classify_symbol("\u030c"), COMBINING)
        a = assess_ipa("ti\u030c")  # i + caron（分解型，王力/李方桂带调元音）
        self.assertEqual(a.espeak_level, "approx")
        self.assertEqual(a.dropped_tokens, ())

    # -- assess_ipa ------------------------------------------------------------

    def test_assess_full(self):
        a = assess_ipa("jung")
        self.assertEqual(a.espeak_level, "full")
        self.assertEqual(a.formant_level, "full")
        self.assertTrue(a.fully_synth)

    def test_assess_partial_drops_segment(self):
        # eSpeak 逐字符丢弃：t/a 保留，ɣ 缺段（实测 [[tɣa]] 与 [[ta]] 同采样数）
        a = assess_ipa("t\u0263a")
        self.assertEqual(a.espeak_level, "partial")
        self.assertEqual(a.dropped_tokens, ("\u0263",))
        self.assertTrue(a.any_segment_dropped)

    def test_assess_approx_keeps_all_segments(self):
        a = assess_ipa("m\u0325a")  # m̥ a：点符丢失，段完整
        self.assertEqual(a.espeak_level, "approx")
        self.assertEqual(a.dropped_tokens, ())

    def test_assess_empty_raises(self):
        with self.assertRaises(ValueError):
            assess_ipa("")

    def test_formant_status_uses_real_engine_sets(self):
        # 共振峰表能真发的（直接读 sound_synth 的表，防漂移）
        for ch in "\u0283\u0292\u0255\u0291xh\u0263":
            self.assertEqual(_formant_status(ch), OK, repr(ch))
        # ASCII g 能发，小写 G 变体 ɡ 不能
        self.assertEqual(_formant_status("g"), OK)
        self.assertEqual(_formant_status("\u0261"), SILENT)
        self.assertEqual(_formant_status("\u0236"), SILENT)
        self.assertEqual(_formant_status("i"), OK)
        self.assertEqual(_formant_status("\u026a"), SILENT)  # ɪ

    # -- 体系级报告（冻结 .probe_reports.json 的数字）-------------------------

    def test_lifanggui_oc_is_fully_synth(self):
        # 李方桂先秦表 100% 可合成：全部读法无缺段、无近似
        r = system_capability_report("lifanggui_oc")
        self.assertEqual(r["readings"], 11160)
        self.assertEqual(r["espeak_full"], 11160)
        self.assertEqual(r["espeak_partial"], 0)
        self.assertEqual(r["formant_full"], 11160)
        self.assertEqual(r["characters_with_gaps"], 0)
        self.assertEqual(r["characters_clean"], 9001)

    def test_wangli_mc_frozen_aggregates(self):
        r = system_capability_report("wangli_mc")
        self.assertEqual((r["espeak_full"], r["espeak_approx"], r["espeak_partial"]),
                         (11317, 9745, 4433))
        self.assertEqual(r["no_ipa_records"], 13)
        d = r["dropped_symbols"]
        self.assertEqual(d["\u0263"], 1658)
        self.assertEqual(d["\u0283"], 923)
        self.assertEqual(d["\u0236"], 720)
        self.assertEqual(d["\u0221"], 486)
        self.assertEqual(d["\u027d"], 406)
        self.assertEqual(d["\u0292"], 240)

    def test_lifanggui_mc_dropped_symbols(self):
        r = system_capability_report("lifanggui_mc")
        self.assertEqual((r["espeak_full"], r["espeak_approx"], r["espeak_partial"]),
                         (9933, 8492, 7082))
        d = r["dropped_symbols"]
        self.assertEqual(d["\u0263"], 1325)
        self.assertEqual(d["\u015b"], 1159)
        self.assertEqual(d["\u1ead"], 1152)

    def test_karlgren_mc_reports_data_quality_junk(self):
        # 高本漢中古 IPA 值含上游残留标点：如实暴露，不静默吞掉
        r = system_capability_report("karlgren_mc")
        self.assertEqual(r["no_ipa_records"], 1)
        self.assertEqual(r["espeak_full"], 2889)
        self.assertEqual(r["anomalous_chars"],
                         {"=": 2, "_": 2, "&": 1, "#": 1, ";": 1,
                          "*": 1, "\n": 1, '"': 1})

    def test_dongtonghe_mc_reports_data_quality_junk(self):
        r = system_capability_report("dongtonghe_mc")
        self.assertEqual(r["anomalous_chars"],
                         {"&": 280, ";": 280, "(": 47, ")": 47})

    def test_zhoufagao_mc_has_no_approx_symbols(self):
        # 周法高体系不用任何附加符：近似档应为空
        r = system_capability_report("zhoufagao_mc")
        self.assertEqual(r["espeak_approx"], 0)
        self.assertEqual(r["approx_symbols"], {})
        self.assertEqual(r["dropped_symbols"]["\u026a"], 2544)

    def test_dongtonghe_oc_dominant_dropped_is_small_cap_g(self):
        r = system_capability_report("dongtonghe_oc")
        self.assertEqual(r["dropped_symbols"]["\u0261"], 3697)

    def test_unknown_system_raises(self):
        with self.assertRaises(KeyError):
            system_capability_report("nonexistent_system")



class EasternMcCorrespondenceTests(unittest.TestCase):
    """东汉 → 中古音类对应表（观测对应，非音变规律）的契约。"""

    # ---- 音韵地位描述解析 ----

    def test_parse_plain_grade_rhyme_tone(self):
        (p,) = emc.parse_position_description("端一東平")
        self.assertEqual((p.shengmu, p.kaihhe, p.deng, p.chongniu, p.yun, p.sheng),
                         ("端", None, "一", None, "東", "平"))

    def test_parse_open_close_and_grade(self):
        (p,) = emc.parse_position_description("端開一登入")
        self.assertEqual((p.shengmu, p.kaihhe, p.deng, p.chongniu, p.yun, p.sheng),
                         ("端", "開", "一", None, "登", "入"))
        # 等可省略（表内确有此类描述）
        (p,) = emc.parse_position_description("端開登入")
        self.assertEqual((p.shengmu, p.kaihhe, p.deng, p.chongniu, p.yun, p.sheng),
                         ("端", "開", None, None, "登", "入"))

    def test_parse_chongniu_with_and_without_open_close(self):
        (p,) = emc.parse_position_description("見開B支平")
        self.assertEqual((p.shengmu, p.kaihhe, p.deng, p.chongniu, p.yun, p.sheng),
                         ("見", "開", None, "B", "支", "平"))
        (p,) = emc.parse_position_description("明B支平")
        self.assertEqual((p.shengmu, p.kaihhe, p.deng, p.chongniu, p.yun, p.sheng),
                         ("明", None, None, "B", "支", "平"))

    def test_parse_three_char_description(self):
        (p,) = emc.parse_position_description("端冬平")
        self.assertEqual((p.shengmu, p.kaihhe, p.deng, p.chongniu, p.yun, p.sheng),
                         ("端", None, None, None, "冬", "平"))

    def test_parse_rejects_garbage(self):
        self.assertEqual(emc.parse_position_description(""), ())
        self.assertEqual(emc.parse_position_description(None), ())
        self.assertEqual(emc.parse_position_description("東平"), ())
        self.assertEqual(emc.parse_position_description("端東"), ())

    def test_parse_multiple_alternatives(self):
        ps = emc.parse_position_description("端一東平/端開一東平")
        self.assertEqual(len(ps), 2)
        self.assertIsNone(ps[0].kaihhe)
        self.assertEqual(ps[1].kaihhe, "開")

    # ---- 表完整性与锚点覆盖 ----

    def test_bundled_table_parses_completely(self):
        # 3872 条记录全部可解析（上游表与解析器零漏网）
        total = 0
        for _head, records in load_qieyun_positions_all().items():
            for record in records:
                self.assertTrue(emc.parse_position_description(record.position_description),
                                record.position_description)
                total += 1
        self.assertEqual(total, 3872)

    def test_anchor_counts_are_pinned(self):
        cov = emc.anchor_coverage()
        self.assertEqual(cov["han_total"], 703)
        self.assertEqual(cov["anchored"], 493)
        self.assertEqual(cov["unanchored"], 210)
        self.assertEqual(cov["pair_total"], 526)
        self.assertEqual(cov["table_rows"], 3872)
        self.assertEqual(cov["table_distinct_heads"], 3707)
        self.assertEqual(cov["mc_initials"], 38)
        self.assertEqual(cov["mc_rhymes"], 58)

    def test_unanchored_common_chars_are_exposed_not_backfilled(self):
        # 人/今/他 在上游表中只作反切字出现；使 完全不出现——如实暴露
        missing = set(emc.unanchored_characters())
        for ch in ("人", "今", "他", "使"):
            self.assertIn(ch, missing)
        self.assertNotIn("东", missing)

    # ---- 声母对应表 ----

    def test_initial_table_shape(self):
        table = emc.initial_correspondence()
        # 31 个东汉母中初母（仅 1 字）无锚定字，表内 30 母
        self.assertEqual(len(table), 30)
        self.assertNotIn("初母", table)
        self.assertEqual(sum(p.n for pairs in table.values()
                             for p in pairs.values()), 526)

    def test_initial_table_pins_classic_splits(self):
        t = emc.initial_correspondence()
        self.assertEqual(t["见母"]["見"].n, 51)
        self.assertEqual(t["匣母"]["匣"].n, 24)
        self.assertEqual(t["匣母"]["云"].n, 13)
        self.assertEqual(t["定母"]["定"].n, 17)
        self.assertEqual(t["定母"]["澄"].n, 6)
        self.assertEqual(t["端母"]["端"].n, 15)
        self.assertEqual(t["端母"]["知"].n, 7)
        self.assertEqual(t["透母"]["昌"].n, 5)
        self.assertEqual(t["透母"]["透"].n, 4)
        self.assertEqual(t["帮母"]["幫"].n, 20)
        self.assertEqual(t["帮母"]["滂"].n, 1)

    def test_each_initial_is_concentrated(self):
        # 每个东汉母的主导中古母占该类样本半数以上（观测集中性，非规律）
        for dh, pairs in emc.initial_correspondence().items():
            total = sum(p.n for p in pairs.values())
            dominant = max(p.n for p in pairs.values())
            self.assertGreaterEqual(dominant, total / 2, dh)

    # ---- 韵母对应表 ----

    def test_final_table_shape(self):
        t = emc.final_correspondence()
        self.assertEqual(sum(p.n for pairs in t.values()
                             for p in pairs.values()), 526)
        self.assertIn("阳韵", t)

    def test_final_table_pins_classic_splits(self):
        t = emc.final_correspondence()
        self.assertEqual(t["阳韵"]["陽"].n, 17)
        self.assertEqual(t["阳韵"]["唐"].n, 13)
        self.assertEqual(t["阳韵"]["庚"].n, 8)
        self.assertEqual(t["东韵"]["東"].n, 19)
        self.assertEqual(t["东韵"]["江"].n, 1)
        self.assertEqual(t["鱼韵(上)"]["魚"].n, 11)
        self.assertEqual(t["鱼韵(上)"]["麻"].n, 6)
        self.assertEqual(t["鱼韵(上)"]["模"].n, 5)
        self.assertEqual(t["鱼韵(上)"]["虞"].n, 2)
        # 钟韵 → 鍾 1:1 无散点
        self.assertEqual(len(t["钟韵"]), 1)
        self.assertEqual(t["钟韵"]["鍾"].n, 12)
        self.assertEqual(t["德韵"]["登"].n, 6)
        self.assertEqual(t["祭韵(去)"]["泰"].n, 7)

    def test_pair_chars_are_the_textual_basis(self):
        # 每对（东汉类 → 中古类）都附字表作为文字依据
        pair = emc.initial_correspondence()["见母"]["匣"]
        self.assertEqual(pair.n, 1)
        self.assertEqual(len(pair.chars), 1)
        ch = pair.chars[0]
        self.assertEqual(EASTERN_HAN_DB[ch]["init"], "见母")
        row = emc.anchor_for(ch)
        self.assertTrue(row.anchored)
        self.assertTrue(any(p.shengmu == "匣" for p in row.positions))

    def test_small_pairs_are_flagged_as_exceptions(self):
        self.assertTrue(emc.initial_correspondence()["见母"]["匣"].is_exception)
        self.assertFalse(emc.initial_correspondence()["心母"]["心"].is_exception)

    # ---- 单字锚点查询 ----

    def test_anchor_for_single_char(self):
        row = emc.anchor_for("东")
        self.assertIsNotNone(row)
        self.assertEqual(row.traditional, "東")
        self.assertEqual(row.han_init, EASTERN_HAN_DB["东"]["init"])
        self.assertTrue(row.anchored)
        self.assertTrue(any(p.shengmu == "端" and p.yun == "東"
                            for p in row.positions))

    def test_anchor_for_unanchored_and_unknown(self):
        self.assertFalse(emc.anchor_for("使").anchored)
        self.assertIsNone(emc.anchor_for("龘"))

    # ---- 来源与报告 ----

    def test_provenance_exposes_sources_and_limitations(self):
        prov = emc.provenance()
        self.assertEqual(prov["mc_anchor_source"]["license"], "CC0")
        self.assertEqual(prov["mc_anchor_source"]["source_blob_sha"],
                         "93ca1b1551b30bba9c76fe21078f156b8299d9cc")
        self.assertEqual(prov["han_source"]["source_status"], "legacy_experimental")
        self.assertEqual(len(prov["limitations"]), 3)
        self.assertIn("observed co-occurrence", prov["method"])

    def test_report_contains_headline_facts(self):
        report = emc.build_report()
        self.assertIn("493/703", report)
        self.assertIn("526", report)
        self.assertIn("非音变规律", report)
        self.assertIn("38 声母 / 58 韵", report)
        self.assertIn("210", report)

    # ---- 与 Qieyun 规范位置集对账 ----

    def test_parser_matches_qieyun_canonical_fields(self):
        try:
            import Qieyun
        except ImportError:
            self.skipTest("Qieyun not installed")
        fn = [a for a in dir(Qieyun) if a.startswith("iter")][0]
        obj0 = list(getattr(Qieyun, fn)())[0]
        from_desc = obj0.from描述
        checked = 0
        for _head, records in load_qieyun_positions_all().items():
            for record in records:
                desc = record.position_description
                obj = from_desc(desc)
                self.assertIsNotNone(obj, desc)
                (p,) = emc.parse_position_description(desc)
                self.assertEqual(p.shengmu, obj.母, desc)
                self.assertEqual(p.yun, obj.韻, desc)
                self.assertEqual(p.sheng, obj.聲, desc)
                if p.kaihhe:
                    self.assertEqual(p.kaihhe, obj.呼, desc)
                if p.deng:
                    self.assertEqual(p.deng, obj.等, desc)
                if p.chongniu:
                    self.assertEqual(p.chongniu, obj.重紐, desc)
                checked += 1
        self.assertEqual(checked, 3872)


if __name__ == "__main__":
    unittest.main()