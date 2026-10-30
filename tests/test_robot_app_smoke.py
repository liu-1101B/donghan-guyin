"""Smoke test: render the robot Streamlit app without microphone or network access."""
import unittest
from pathlib import Path


class RobotAppSmokeTests(unittest.TestCase):
    def test_app_renders_without_hardware_or_vosk_model(self):
        from streamlit.testing.v1 import AppTest

        root = Path(__file__).resolve().parents[1]
        app = root / "robot" / "app.py"
        test_app = AppTest.from_file(str(app), default_timeout=45).run()
        self.assertFalse(
            test_app.exception,
            "Streamlit app raised during initial render: "
            + "; ".join(str(item) for item in test_app.exception),
        )


class WorkerFourAudioTests(unittest.TestCase):
    """Phase 4 (1): _gen_worker 四段音频 payload（新增中古 reply_mc）。

    LLM / TTS / 声卡全部打桩：只验证调度与 payload 形状，不触网不触硬件。
    """

    def _run_worker(self, generate_turn):
        import robot.app as ra
        from robot.session import Session
        import services.llm_client as llm_client
        import services.tts_client as tts_client

        orig = (llm_client.generate_turn, tts_client.speak_natural,
                ra.get_audio_io)
        try:
            llm_client.generate_turn = generate_turn
            tts_client.speak_natural = lambda *a, **k: b"MP3FAKE"

            def _no_audio_io():
                raise RuntimeError("headless test: no audio device")

            ra.get_audio_io = _no_audio_io
            job = {}
            cfg = {"text": "你好", "mode": "ancient", "mode_label": "古韵",
                   "llm_mode": "dictionary", "voice": "zh-CN-YunxiNeural",
                   "rate": "-10%", "speed": 1.0, "pitch": 130}
            ra._gen_worker(job, Session(), cfg)
            return job
        finally:
            (llm_client.generate_turn, tts_client.speak_natural,
             ra.get_audio_io) = orig

    def test_reply_path_has_four_audio_slots(self):
        def gen(text, history=None, mode="dictionary"):
            return {"translation": "天子", "reply": "善哉",
                    "reply_modern": "好啊", "source": "local-dictionary"}

        job = self._run_worker(gen)
        kind, res = job["result"]
        self.assertEqual(kind, "ok")
        audios = res["audios"]
        self.assertEqual(set(audios), {"user", "reply_anc", "reply_mc",
                                       "reply_mod"})
        self.assertTrue(audios["user"]["data"])
        self.assertTrue(audios["reply_anc"]["data"])
        mc = audios["reply_mc"]
        self.assertTrue(mc["data"], "中古音频未产出")
        self.assertEqual(mc["system"], "wangli_mc")
        self.assertEqual(mc["system_label"], "王力系統")
        self.assertTrue(mc["ipa"])
        self.assertEqual(mc["coverage"], 100.0)
        self.assertEqual(audios["reply_mod"]["data"], b"MP3FAKE")
        self.assertTrue(job.get("play_done") is True)

    def test_no_reply_path_keeps_reply_mc_honest_empty(self):
        def gen(text, history=None, mode="dictionary"):
            return {"translation": "量子计算", "reply": "",
                    "reply_modern": "", "source": "local-dictionary-miss"}

        job = self._run_worker(gen)
        kind, res = job["result"]
        self.assertEqual(kind, "ok")
        mc = res["audios"]["reply_mc"]
        self.assertEqual(mc["data"], b"")
        self.assertEqual(mc["ipa"], "")
        self.assertEqual(mc["unknown"], [])


if __name__ == "__main__":
    unittest.main()
