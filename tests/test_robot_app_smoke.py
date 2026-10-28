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


if __name__ == "__main__":
    unittest.main()
