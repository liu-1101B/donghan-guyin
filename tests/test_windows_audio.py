"""Unit tests for the Windows audio adapter (no physical audio device required)."""
import io
import unittest
import wave
from tempfile import TemporaryDirectory
from unittest.mock import patch

from robot.windows_audio import (
    WindowsAudioIO, list_output_devices, resolve_device, _wav_to_int16,
)


class _FakeDefault:
    device = (0, 1)


class _FakeOutputStream:
    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def write(self, samples):
        self.owner.written_frames += len(samples)

    def abort(self):
        return None


class _FakeSoundDevice:
    default = _FakeDefault()

    def __init__(self):
        self.written_frames = 0
        self.devices = [
            {"name": "USB Microphone", "max_input_channels": 1,
             "max_output_channels": 0, "default_samplerate": 48000},
            {"name": "Speakers (USB Audio)", "max_input_channels": 0,
             "max_output_channels": 2, "default_samplerate": 48000},
            {"name": "Webcam Microphone", "max_input_channels": 1,
             "max_output_channels": 0, "default_samplerate": 44100},
        ]

    def query_devices(self, device=None, kind=None):
        if device is not None:
            return self.devices[int(device)]
        if kind == "input":
            return self.devices[self.default.device[0]]
        if kind == "output":
            return self.devices[self.default.device[1]]
        return self.devices

    def rec(self, frames, samplerate, channels, dtype, device, blocking):
        import numpy as np
        return np.zeros((frames, channels), dtype=np.int16)

    def OutputStream(self, **kwargs):
        return _FakeOutputStream(self)


class WindowsAudioDeviceTests(unittest.TestCase):
    def setUp(self):
        self.sd = _FakeSoundDevice()

    def test_lists_only_output_devices_and_marks_default(self):
        self.assertEqual(
            list_output_devices(self.sd),
            [(1, "Speakers (USB Audio)", True, None)],
        )

    def test_resolves_input_device_by_name(self):
        self.assertEqual(resolve_device("USB Microphone", "input", self.sd), 0)
        self.assertEqual(resolve_device("Webcam", "input", self.sd), 2)

    def test_resolves_output_device_by_name(self):
        self.assertEqual(
            resolve_device("Speakers (USB Audio)", "output", self.sd), 1
        )

    def test_linux_alsa_name_falls_back_to_windows_default(self):
        self.assertEqual(resolve_device("plughw:2,0", "output", self.sd), 1)

    def test_missing_name_falls_back_to_default_device(self):
        self.assertEqual(resolve_device("not connected", "input", self.sd), 0)

    def test_wav_decoder_reads_16_bit_pcm_without_sound_hardware(self):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x01\x00\x02\x00\x03\x00")
        samples, sample_rate, channels = _wav_to_int16(buf.getvalue())
        self.assertEqual((sample_rate, channels), (16000, 1))
        self.assertEqual(samples.shape, (3, 1))
        self.assertEqual(samples.dtype.name, "int16")

    def test_windows_record_writes_a_valid_wav(self):
        with patch.dict("sys.modules", {"sounddevice": self.sd}):
            audio = WindowsAudioIO(
                capture_device="USB Microphone", playback_device="Speakers",
                sample_rate=16000,
            )
            with TemporaryDirectory() as folder:
                path = folder + "/captured.wav"
                self.assertTrue(audio.record(0.05, path))
                with wave.open(path, "rb") as wf:
                    self.assertEqual(wf.getnchannels(), 1)
                    self.assertEqual(wf.getsampwidth(), 2)
                    self.assertEqual(wf.getframerate(), 16000)
                    self.assertGreater(wf.getnframes(), 0)

    def test_windows_playback_stream_receives_pcm_frames(self):
        with patch.dict("sys.modules", {"sounddevice": self.sd}):
            audio = WindowsAudioIO(playback_device="Speakers (USB Audio)")
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x01\x00" * 5000)
            self.assertTrue(audio.play_wav(buf.getvalue()))
            self.assertEqual(self.sd.written_frames, 5000)


class _MultiApiSoundDevice:
    """真实 Windows 的样子：同一只音箱经 MME/DS/WASAPI/WDM-KS 各列一次。"""

    NAME = "扬声器 (K02BS)"
    BTHF = ("耳机 (@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0\r\n;"
            "(Relink脑机接口))")

    def __init__(self):
        self.default = _FakeDefault()
        self.default.device = (0, 2)          # 默认输出 = WASAPI 的那条
        self._apis = [
            {"name": "MME"}, {"name": "Windows DirectSound"},
            {"name": "Windows WASAPI"}, {"name": "Windows WDM-KS"},
        ]
        self._devices = [
            {"name": self.NAME, "hostapi": 0, "max_input_channels": 0,
             "max_output_channels": 2, "default_samplerate": 48000},
            {"name": self.NAME, "hostapi": 1, "max_input_channels": 0,
             "max_output_channels": 2, "default_samplerate": 48000},
            {"name": self.NAME, "hostapi": 2, "max_input_channels": 0,
             "max_output_channels": 2, "default_samplerate": 48000},
            {"name": self.NAME, "hostapi": 3, "max_input_channels": 0,
             "max_output_channels": 2, "default_samplerate": 48000},
            {"name": "耳机 ()", "hostapi": 3, "max_input_channels": 0,
             "max_output_channels": 2, "default_samplerate": 48000},
            {"name": "耳机 ()", "hostapi": 3, "max_input_channels": 0,
             "max_output_channels": 2, "default_samplerate": 48000},
            {"name": self.BTHF, "hostapi": 3, "max_input_channels": 0,
             "max_output_channels": 2, "default_samplerate": 48000},
        ]

    def query_hostapis(self):
        return self._apis

    def query_devices(self, device=None, kind=None):
        if device is not None:
            return self._devices[int(device)]
        return self._devices


class WindowsDeviceListTests(unittest.TestCase):
    """下拉框必须在 Windows 上可读、可区分、不重复。"""

    def setUp(self):
        self.sd = _MultiApiSoundDevice()

    def test_same_endpoint_across_host_apis_collapses_to_one(self):
        listed = list_output_devices(self.sd)
        k02 = [row for row in listed if row[1].startswith("扬声器 (K02BS)")]
        self.assertEqual(len(k02), 1, f"同一端点重复出现: {k02}")
        # 保留下来的应是首选 host API（WASAPI）那条，并标为默认
        self.assertEqual(k02[0][0], 2)
        self.assertTrue(k02[0][2])

    def test_bluetooth_handsfree_name_becomes_readable(self):
        labels = [row[1] for row in list_output_devices(self.sd)]
        self.assertIn("Relink脑机接口（蓝牙·免提）", labels)
        self.assertFalse(any("\r" in label or "\n" in label for label in labels))

    def test_identical_names_stay_distinguishable_and_resolvable(self):
        listed = list_output_devices(self.sd)
        unnamed = [row for row in listed if row[1].startswith("耳机（未命名）")]
        self.assertEqual(len(unnamed), 2)
        self.assertEqual(len({row[1] for row in unnamed}), 2)
        for index, label, _default, _vol in unnamed:
            self.assertEqual(resolve_device(label, "output", self.sd), index)

    def test_resolves_cleaned_bluetooth_label_back_to_its_endpoint(self):
        self.assertEqual(
            resolve_device("Relink脑机接口（蓝牙·免提）", "output", self.sd), 6
        )


if __name__ == "__main__":
    unittest.main()
