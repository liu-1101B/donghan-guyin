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


if __name__ == "__main__":
    unittest.main()
