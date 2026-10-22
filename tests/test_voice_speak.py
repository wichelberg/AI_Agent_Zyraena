"""voice.speak: local voice sentence by sentence (Chatterbox and the voice pack overlapped), text only
when it can't run, stopping, and never a paid service. No models, no sound: the local voice and the
speaker are fakes.

Run from the project folder: python -m unittest discover -s tests
"""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import voice  # noqa: E402

TEXT = "Spotify'ı açtım, sesi biraz kıstım. Toplantın on yedi otuzda başlıyor. Başka bir şey ister misin?"


class SpeakTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        before = set(threading.enumerate())
        # runs first: speech threads still cleaning up after a stop must not race the folder's removal
        self.addCleanup(lambda: [t.join(5) for t in set(threading.enumerate()) - before])
        self.played, self.made, self.voiced = [], [], []
        self.slow_after = None     # the sentence index that is "slow" to make
        self.fail_at = None        # Chatterbox fails on this sentence
        self.voice_fail_at = None  # the voice pack fails on this one
        self.done = threading.Event()

        def make_locally(piece):
            index = len(self.made)
            if self.fail_at == index:
                raise RuntimeError("tts broke")
            self.made.append(piece)
            return self.wav(f"local{index}"), index == self.slow_after

        def in_voice(raw):
            if self.voice_fail_at == len(self.voiced):
                raise RuntimeError("voice pack broke")
            self.voiced.append(raw.stem)
            return raw

        def play_sound(sound, flags):
            if sound:
                self.played.append(Path(sound).stem)

        def finished(ready, turn):
            try:
                real_play(ready, turn)
            finally:
                self.done.set()

        real_play = voice._play_in_order
        patches = [mock.patch.dict(os.environ, {"ZYRAENA_VOICE_HOME": self.tmp.name}),
                   mock.patch.object(voice, "_make_locally", make_locally),
                   mock.patch.object(voice, "_in_voice", in_voice),
                   mock.patch.object(voice.requests, "post", side_effect=AssertionError("a paid service was called")),
                   mock.patch.object(voice, "_play_in_order", finished),
                   mock.patch.object(voice, "_local_tts_on", lambda: True), mock.patch.object(voice, "_gpu_busy", lambda: False),
                   mock.patch.object(voice.winsound, "PlaySound", play_sound), mock.patch("builtins.print")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def wav(self, name):
        path = Path(self.tmp.name) / f"{name}.wav"
        sf.write(path, np.zeros(160, np.float32), 16000)  # 10 ms
        return path

    def speak(self, **kwargs):
        voice.speak(TEXT, **kwargs)
        self.assertTrue(self.done.wait(10))

    def test_sentence_by_sentence(self):
        self.speak()
        self.assertEqual(len(self.made), 3)
        self.assertEqual(self.played, ["local0", "local1", "local2"])
        self.assertIn("Spotifayı", self.made[0])

    def test_each_reply_is_timed_in_speech_log(self):
        self.speak()
        line = (Path(self.tmp.name) / "speech.log").read_text(encoding="utf-8")
        self.assertRegex(line, r"first sound \d+\.\d\d s, 3 pieces, 0\.0 s audio, gaps \d+\.\d\d s")

    def test_next_sentence_is_made_while_one_is_voiced(self):
        second_made = threading.Event()
        make, in_voice = voice._make_locally, voice._in_voice
        overlapped = []

        def make_locally(piece):
            result = make(piece)
            if len(self.made) == 2:
                second_made.set()
            return result

        def slow_voice(raw):
            if raw.stem == "local0":  # Chatterbox must not wait for this one
                overlapped.append(second_made.wait(5))
            return in_voice(raw)

        with mock.patch.object(voice, "_make_locally", make_locally), mock.patch.object(voice, "_in_voice", slow_voice):
            self.speak()
        self.assertEqual(overlapped, [True])
        self.assertEqual(self.played, ["local0", "local1", "local2"])

    def test_order_is_kept_when_the_voice_pack_is_slower(self):
        in_voice = voice._in_voice

        def slow_voice(raw):
            time.sleep(0.05 if raw.stem == "local0" else 0)
            return in_voice(raw)

        with mock.patch.object(voice, "_in_voice", slow_voice):
            self.speak()
        self.assertEqual(self.played, ["local0", "local1", "local2"])

    def speak_and_fail(self):
        errors = []
        self.speak(on_error=errors.append)
        self.assertEqual(len(errors), 1)
        return errors[0]

    def test_busy_gpu_keeps_it_text(self):
        with mock.patch.object(voice, "_gpu_busy", lambda: True):
            error = self.speak_and_fail()
        self.assertEqual((self.made, self.played), ([], []))
        self.assertEqual(error.reason, "busy")

    def test_a_game_keeps_it_text(self):
        with mock.patch.object(voice, "_local_tts_on", lambda: False), mock.patch.dict(voice.gaming, {"on": True}):
            error = self.speak_and_fail()
        self.assertEqual((self.made, self.played), ([], []))
        self.assertEqual(error.reason, "game")

    def test_slow_sentence_keeps_the_rest_as_text(self):
        self.slow_after = 0
        error = self.speak_and_fail()
        self.assertEqual(self.played, ["local0"])
        self.assertEqual(len(self.made), 1)
        self.assertEqual(error.reason, "slow")

    def test_failing_first_sentence_is_reported(self):
        self.fail_at = 0
        self.assertEqual(str(self.speak_and_fail()), "tts broke")
        self.assertEqual(self.played, [])

    def test_failing_voice_pack_on_first_sentence_is_reported(self):
        self.voice_fail_at = 0
        self.assertEqual(str(self.speak_and_fail()), "voice pack broke")
        self.assertEqual(self.played, [])

    def test_failing_later_sentence_is_reported(self):
        self.fail_at = 1
        self.assertEqual(str(self.speak_and_fail()), "tts broke")
        self.assertEqual(self.played, ["local0"])

    def test_failing_voice_pack_later_is_reported(self):
        self.voice_fail_at = 1
        self.assertEqual(str(self.speak_and_fail()), "voice pack broke")
        self.assertEqual(self.played, ["local0"])

    def test_there_is_no_paid_voice_at_all(self):
        for name in ("synthesize", "_tts_pcm", "_tts_once", "TTS_INSTRUCTIONS"):
            self.assertFalse(hasattr(voice, name), name)

    def test_stop_cancels_what_is_not_made_yet(self):
        gate = threading.Event()
        original = voice._make_locally

        def slow_maker(piece):
            gate.wait(5)
            return original(piece)

        with mock.patch.object(voice, "_make_locally", slow_maker):
            voice.speak(TEXT)
            time.sleep(0.05)
            voice.stop_playing()
            gate.set()
            self.assertTrue(self.done.wait(10))
        self.assertEqual(self.played, [])
        self.assertLessEqual(len(self.made), 1)

    def test_stop_cancels_what_is_being_voiced(self):
        gate = threading.Event()
        in_voice = voice._in_voice

        def slow_voice(raw):
            gate.wait(5)
            return in_voice(raw)

        with mock.patch.object(voice, "_in_voice", slow_voice):
            voice.speak(TEXT)
            time.sleep(0.05)
            voice.stop_playing()
            gate.set()
            self.assertTrue(self.done.wait(10))
        self.assertEqual(self.played, [])
        self.assertLessEqual(len(self.voiced), 1)


class PauseTest(unittest.TestCase):
    def test_slow_sentence_pauses_the_local_voice(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(voice, "_audio_dir", Path(folder)), \
                mock.patch.object(voice.local_tts, "say", return_value={"ok": True, "seconds": 9.0, "audio_seconds": 3.0}), \
                mock.patch.object(voice.local_tts, "available", return_value=True), \
                mock.patch.dict(voice._local_paused, {"until": 0.0}):
            _, slow = voice._make_locally("bir cümle")
            self.assertTrue(slow)
            self.assertFalse(voice._local_tts_on())


class GpuBusyTest(unittest.TestCase):
    def check(self, ours_busy):
        result = mock.Mock(stdout="97\n")
        with mock.patch.object(voice.shutil, "which", return_value="nvidia-smi"), \
                mock.patch.object(voice.subprocess, "run", return_value=result), \
                mock.patch.object(voice, "workers_busy", return_value=ours_busy), \
                mock.patch.dict(os.environ, {"ZYRAENA_TTS_GPU_BUSY": ""}):
            return voice._gpu_busy()

    def test_someone_else_keeps_it_busy(self):
        self.assertTrue(self.check(ours_busy=False))

    def test_our_own_load_is_not_someone_else(self):
        self.assertFalse(self.check(ours_busy=True))


class InVoiceTest(unittest.TestCase):
    def test_without_a_voice_pack_the_reader_is_played(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / "abc_tts.wav"
            raw.write_bytes(b"")
            with mock.patch.object(voice, "_convert", return_value=False):
                self.assertEqual(voice._in_voice(raw), raw)

    def test_with_a_voice_pack_the_converted_wav_is_played(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / "abc_tts.wav"
            raw.write_bytes(b"")
            with mock.patch.object(voice, "_convert", return_value=True) as convert:
                self.assertEqual(voice._in_voice(raw), Path(folder) / "abc.wav")
            convert.assert_called_once_with(raw, Path(folder) / "abc.wav", None)
            self.assertFalse(raw.exists())


if __name__ == "__main__":
    unittest.main()
