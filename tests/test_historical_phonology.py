"""Tests for historical timeline and reconstruction metadata."""
import unittest
from language.history import (TIMELINE, get_period, get_system, lookup_reading,
                              period_at, systems_for_period)


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
