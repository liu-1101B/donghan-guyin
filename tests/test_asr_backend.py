"""后端选择：默认用最好的可用模型，缺模型时逐级降级，不能静默失败。"""
import os
import unittest
from unittest.mock import patch

import services.asr_client as asr


class BackendSelectionTests(unittest.TestCase):
    def test_prefers_sensevoice_when_model_present(self):
        with patch.multiple(
            asr.os.path, isfile=lambda p: "sense-voice" in str(p),
            exists=lambda p: "sense-voice" in str(p),
        ):
            self.assertEqual(asr.available_backends(), ["sensevoice"])
            self.assertEqual(asr.pick_backend("auto"), "sensevoice")

    def test_falls_back_to_vosk(self):
        with patch.multiple(
            asr.os.path, isfile=lambda p: "vosk-small-cn" in str(p),
            exists=lambda p: "vosk-small-cn" in str(p),
        ):
            self.assertEqual(asr.available_backends(), ["vosk"])
            self.assertEqual(asr.pick_backend("auto"), "vosk")

    def test_no_model_reports_none_instead_of_lying(self):
        with patch.multiple(
            asr.os.path, isfile=lambda p: False, exists=lambda p: False,
        ):
            self.assertEqual(asr.available_backends(), [])
            self.assertIsNone(asr.pick_backend("auto"))

    def test_explicit_backend_missing_returns_none(self):
        with patch.multiple(
            asr.os.path, isfile=lambda p: False, exists=lambda p: False,
        ):
            self.assertIsNone(asr.pick_backend("sensevoice"))

    def test_unknown_backend_name_means_auto(self):
        with patch.multiple(
            asr.os.path, isfile=lambda p: "sense-voice" in str(p),
            exists=lambda p: "sense-voice" in str(p),
        ):
            self.assertEqual(asr.pick_backend("local"), "sensevoice")


if __name__ == "__main__":
    unittest.main()
