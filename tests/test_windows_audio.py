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


if __name__ == "__main__":
    unittest.main()
