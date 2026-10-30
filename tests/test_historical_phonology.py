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
                              scholar_coverage, SCHOLAR_SYSTEMS)


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


if __name__ == "__main__":
    unittest.main()
