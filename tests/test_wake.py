"""wake.py: the "Zyraena açıl" phrase, cutting speech out of the microphone, when it listens at all, and
voice.SilenceCut (the recording that stops by itself). No microphone, no Whisper: fakes.

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import voice  # noqa: E402
import voice_guard  # noqa: E402
import wake  # noqa: E402

RNG = np.random.default_rng(0)


def blocks(seconds, amplitude, block=wake.BLOCK, rate=wake.RATE):
    """`seconds` of noise (amplitude ~0.001) or speech-like tone (larger amplitude), in blocks."""
    out = []
    for _ in range(round(seconds * rate / block)):
        if amplitude <= 0.002:
            out.append((RNG.standard_normal(block) * amplitude).astype(np.float32))
        else:
            t = np.arange(block) / rate
            out.append((amplitude * np.sin(2 * np.pi * 220 * t) + RNG.standard_normal(block) * 0.001).astype(np.float32))
    return out


def bits(*parts):
    """Feeds (seconds, amplitude) parts to a Segmenter; returns the bits it gave back."""
    segmenter, found = wake.Segmenter(), []
    for seconds, amplitude in parts:
        for b in blocks(seconds, amplitude):
            bit = segmenter.feed(b)
            if bit is not None:
                found.append(len(bit) / wake.RATE)
    return found


class PhraseTest(unittest.TestCase):
    def test_the_phrase_as_whisper_may_write_it(self):
        for text in ("Zyraena açıl", "zirayena açıl.", "Zyraena, açıl!", "Zyraena aç", "ziraena acil", "Hey Zyraena açıl lütfen"):
            self.assertTrue(wake.heard_wake(text), text)

    def test_other_speech(self):
        for text in ("Zyraena nasılsın", "açıl susam açıl", "Bugün hava güzel", "Zyraena'yı kapat", "Wichelberg açıl", ""):
            self.assertFalse(wake.heard_wake(text), text)


class SegmenterTest(unittest.TestCase):
    def test_a_short_call_is_cut_out(self):
        found = bits((3.0, 0.001), (1.2, 0.1), (1.0, 0.001))
        self.assertEqual(len(found), 1)
        self.assertGreater(found[0], 1.2)

    def test_clicks_and_long_talk_are_not(self):
        self.assertEqual(bits((3.0, 0.001), (0.1, 0.2), (1.0, 0.001)), [])            # a click
        self.assertEqual(bits((3.0, 0.001), (0.2, 0.1), (1.0, 0.001)), [])            # too short
        self.assertEqual(bits((3.0, 0.001), (6.0, 0.1), (0.3, 0.001), (1.0, 0.1), (1.0, 0.001)), [])  # talk, its tail too

    def test_one_after_another(self):
        self.assertEqual(len(bits((3.0, 0.001), (1.0, 0.1), (1.0, 0.001), (1.5, 0.1), (1.0, 0.001))), 2)

    def test_it_follows_a_noisier_room(self):
        found = bits((3.0, 0.002), (1.0, 0.05), (1.0, 0.002))
        self.assertEqual(len(found), 1)

    def test_a_close_voice_over_a_video_in_the_background(self):
        segmenter, found = wake.Segmenter(), []
        video = blocks(10.0, 0.006)  # speech from the speakers, never pausing
        for i, b in enumerate(video):
            if 100 <= i < 119:  # ~1.2 s of the owner, 4x louder, on top of it
                b = b + blocks(0.064, 0.03)[0]
            bit = segmenter.feed(b)
            if bit is not None:
                found.append(len(bit) / wake.RATE)
        self.assertEqual(len(found), 1)
        self.assertLess(found[0], wake.MAX_SPEECH + wake.END_SILENCE + wake.PRE_ROLL + 0.1)

    def test_listening_starts_by_learning_the_room(self):
        self.assertEqual(bits((1.2, 0.1), (1.0, 0.001)), [])  # sound right away: not judged yet

    def test_the_video_alone_never_counts(self):
        self.assertEqual(bits((10.0, 0.006)), [])


class ListenerTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.woke = threading.Event()
        self.heard = []
        self.text = "Zyraena açıl"
        self.paused = False

        def transcribe(wav):
            self.heard.append(len(wav))
            return self.text

        for p in (mock.patch.object(voice, "stt_on", return_value=True),
                  mock.patch.object(voice.local_stt, "loaded", return_value=True),
                  mock.patch.object(voice, "speaking", return_value=False),
                  mock.patch.dict(os.environ, {"ZYRAENA_WAKE": "", "ZYRAENA_VOICE_HOME": self.home.name}),
                  mock.patch("builtins.print")):
            p.start()
            self.addCleanup(p.stop)
        self.listener = wake.WakeListener(self.woke.set, paused=lambda: self.paused, transcribe=transcribe)
        self.listener._stream = object()  # "enabled" without a microphone

    def say(self):
        for seconds, amplitude in ((3.0, 0.001), (1.2, 0.1), (1.0, 0.001)):
            for b in blocks(seconds, amplitude):
                self.listener._on_audio(b[:, None], len(b), None, None)

    def test_the_phrase_wakes_her(self):
        self.say()
        self.assertTrue(self.woke.wait(5))
        self.assertEqual(len(self.heard), 1)

    def test_other_speech_does_not(self):
        self.text = "bugün hava çok güzel"
        self.say()
        deadline = time.monotonic() + 5  # wait for the hearing thread, however busy the PC is
        while not self.heard and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(self.woke.wait(0.3))
        self.assertEqual(len(self.heard), 1)

    def test_not_while_recording_or_speaking(self):
        self.paused = True
        self.say()
        with mock.patch.object(voice, "speaking", return_value=True):
            self.paused = False
            self.say()
        self.assertFalse(self.woke.wait(0.5))
        self.assertEqual(self.heard, [])

    def test_never_without_the_loaded_local_whisper(self):
        with mock.patch.object(voice.local_stt, "loaded", return_value=False):
            self.say()
            time.sleep(0.3)
        self.assertEqual(self.heard, [])
        self.assertFalse(self.woke.is_set())

    def test_turned_off_in_env(self):
        listener = wake.WakeListener(lambda: None)
        os.environ["ZYRAENA_WAKE"] = "off"
        listener.set_enabled(True)  # would open the microphone otherwise
        self.assertFalse(listener.enabled())

    def reopen_check(self, old):
        """set_enabled(True) with `old` as the open stream: returns the stream it leaves open."""
        fake_sd = mock.Mock()
        fake_sd.InputStream.return_value = mock.Mock(active=True)
        self.listener._stream = old
        with mock.patch.dict(sys.modules, {"sounddevice": fake_sd}):
            self.listener.set_enabled(True)
        return self.listener._stream

    def test_a_stream_that_died_is_reopened(self):
        old = mock.Mock(active=False)
        self.listener._last_audio = time.monotonic()
        new = self.reopen_check(old)
        old.abort.assert_called_once()
        self.assertIsNot(new, old)
        new.start.assert_called_once()

    def test_a_stream_that_went_quiet_is_reopened(self):
        old = mock.Mock(active=True)
        self.listener._last_audio = time.monotonic() - wake.STALE_SECONDS - 1
        self.assertIsNot(self.reopen_check(old), old)

    def test_a_healthy_stream_is_kept(self):
        old = mock.Mock(active=True)
        self.listener._last_audio = time.monotonic()
        self.assertIs(self.reopen_check(old), old)
        old.abort.assert_not_called()

    def test_a_failing_block_does_not_end_the_stream(self):
        with mock.patch.object(self.listener._segmenter, "feed", side_effect=ValueError("bad block")):
            for b in blocks(0.2, 0.1):
                self.listener._on_audio(b[:, None], len(b), None, None)  # must not raise
        self.say()
        self.assertTrue(self.woke.wait(5))


class GuardTest(unittest.TestCase):
    def test_only_in_ready_without_a_suspect_reading(self):
        fake = mock.Mock()
        with mock.patch.object(wake, "WakeListener", return_value=fake), mock.patch.object(voice_guard, "listeners", []), \
                mock.patch.dict(wake._listener, {"it": None}):
            wake.start(lambda: None)
            hook, = voice_guard.listeners
            for mode, suspect, on in (("ready", False, True), ("ready", True, False), ("idle", False, False),
                                      ("game", False, False), ("game", True, False)):
                hook(mode, suspect)
                self.assertEqual(fake.set_enabled.call_args[0][0], on, (mode, suspect))


class SilenceCutTest(unittest.TestCase):
    def run_cut(self, *parts, floor=None, longest=voice.SilenceCut.LONGEST):
        self.cut, t = voice.SilenceCut(wake.RATE, floor, longest), 0.0
        for seconds, amplitude in parts:
            for b in blocks(seconds, amplitude):
                t += len(b) / wake.RATE
                if self.cut.feed(b):
                    return round(t, 1)
        return None

    def test_stops_after_the_speaker_finished(self):
        stopped = self.run_cut((0.5, 0.001), (3.0, 0.1), (0.4, 0.001), (2.0, 0.1), (3.0, 0.001))
        self.assertAlmostEqual(stopped, 0.5 + 3.0 + 0.4 + 2.0 + voice.SilenceCut.SILENCE, delta=0.2)
        self.assertTrue(self.cut.spoke)

    def test_speech_right_away_with_the_room_level_handed_over(self):
        stopped = self.run_cut((2.0, 0.1), (0.3, 0.001), (1.0, 0.1), (3.0, 0.001), floor=0.001)
        self.assertAlmostEqual(stopped, 3.3 + voice.SilenceCut.SILENCE, delta=0.2)

    def test_nothing_said(self):
        self.assertAlmostEqual(self.run_cut((10.0, 0.001)), voice.SilenceCut.NO_SPEECH, delta=0.1)
        self.assertFalse(self.cut.spoke)

    def test_a_video_already_playing_is_the_room(self):
        self.run_cut((10.0, 0.006), floor=0.004)  # background talk, its level handed over
        self.assertFalse(self.cut.spoke)

    def test_a_video_that_never_pauses_runs_out_and_becomes_the_room(self):
        self.run_cut((0.5, 0.001), (20.0, 0.02), longest=15.0)
        self.assertTrue(self.cut.ran_out)
        self.assertGreater(self.cut.floor(), 0.005)  # the next turn won't take it for speech


if __name__ == "__main__":
    unittest.main()
