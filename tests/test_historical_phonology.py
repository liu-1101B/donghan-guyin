"""Tests for historical timeline and reconstruction metadata."""
import unittest
from language.history import (TIMELINE, get_period, get_system, lookup_reading,
                              lookup_qieyun_positions, period_at,
                              qieyun_record_count, systems_for_period)


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


if __name__ == "__main__":
    unittest.main()
