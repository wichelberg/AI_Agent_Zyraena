"""voice_session: the spoken conversation loop, its closing phrase, timeouts and the credit guards.
No microphone, Whisper, model or speakers: fakes.

Run from the project folder: python -m unittest discover -s tests
"""
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import voice  # noqa: E402
import voice_session  # noqa: E402


class FakeCut:
    def __init__(self, spoke=True, ran_out=False):
        self.spoke, self.ran_out, self.level = spoke, ran_out, 0.2

    def floor(self):
        return 0.001


class Script:
    """What each recording "hears", in order; after the last one nothing more is heard."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.made = 0
        self.lock = threading.Lock()

    def recorder(self, on_silence, floor=None, longest=None):
        with self.lock:
            self.made += 1
            turn = self.turns.pop(0) if self.turns else None
        return FakeRecorder(on_silence, turn)


class FakeRecorder:
    def __init__(self, on_silence, turn):
        self.turn = turn
        self.cut = FakeCut(**(turn or {}).get("cut", {}))
        if turn is not None:
            threading.Timer(0.01, on_silence).start()

    def stop(self):
        return (self.turn or {}).get("audio", b"wav")

    def level(self):
        return self.cut.level


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.answers, self.notified, self.activity, self.spoken = [], [], [], []
        self.heard = {}  # audio -> text
        self.speak_error = None
        self.glow = mock.Mock()

        def answer(chat, text):
            self.answers.append(text)
            return "Tamam, hallettim."

        def speak(text, on_error=None, on_done=None):
            self.spoken.append(text)
            if self.speak_error and on_error:
                on_error(self.speak_error)
            if on_done:
                threading.Thread(target=on_done, daemon=True).start()

        self.session = voice_session.Session(answer, lambda: {"mode": "assistant", "messages": []},
                                             lambda audio: self.heard.get(audio, ""), self.notified.append,
                                             self.activity.append, self.glow, Path(self.tmp.name))
        for p in (mock.patch.object(voice, "speak", speak), mock.patch.object(voice, "stop_playing"),
                  mock.patch.object(voice, "warm_up"),
                  mock.patch.object(voice_session, "AFTER_SPEECH", 0)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lambda: self.session.close("test over"))

    def run_script(self, turns, wait_for):
        script = Script(turns)
        with mock.patch.object(voice, "Recorder", script.recorder):
            self.session.start(floor=0.001)
            deadline = time.monotonic() + 5
            while not wait_for(script) and time.monotonic() < deadline:
                time.sleep(0.01)
        return script

    def test_a_turn_then_she_listens_again(self):
        self.heard[b"q"] = "bugün hava nasıl"
        script = self.run_script([{"audio": b"q"}], lambda s: s.made >= 2)
        self.assertEqual(self.answers, ["bugün hava nasıl" + voice.SPOKEN_HINT])
        self.assertEqual(self.spoken, ["Tamam, hallettim."])
        self.assertEqual(script.made, 2)  # the microphone opened again after her answer
        self.assertIn("think", self.activity)
        self.assertIn("talk", self.activity)
        self.glow.show.assert_called_once()

    def test_closing_phrase_sends_nothing(self):
        self.heard[b"bye"] = "Zyraena kapat."
        self.run_script([{"audio": b"bye"}], lambda s: not self.session.active())
        self.assertFalse(self.session.active())
        self.assertEqual(self.answers, [])
        self.glow.hide.assert_called_once()
        self.assertEqual(self.activity[-1], None)

    def test_no_speech_and_endless_sound_are_never_sent(self):
        self.heard[b"video"] = "sayın başkanım değerli milletvekilleri"
        turns = [{"cut": {"spoke": False}}, {"audio": b"video", "cut": {"ran_out": True}}, {"audio": None}]
        self.run_script(turns, lambda s: s.made >= 4)
        self.assertEqual(self.answers, [])
        self.assertTrue(self.session.active())

    def test_nothing_said_for_a_while_ends_it(self):
        with mock.patch.object(voice_session, "IDLE_SECONDS", 0):
            self.run_script([{"cut": {"spoke": False}}], lambda s: not self.session.active())
        self.assertFalse(self.session.active())
        self.assertEqual(self.answers, [])

    def test_an_answer_she_cant_say_goes_to_telegram(self):
        self.heard[b"q"] = "ne yapsam"
        self.speak_error = voice.NoLocalVoice("busy")
        self.run_script([{"audio": b"q"}], lambda s: s.made >= 2)
        self.assertEqual(self.notified, ["Tamam, hallettim."])

    def test_nothing_heard_by_whisper_is_not_sent(self):
        self.run_script([{"audio": b"mumble"}], lambda s: s.made >= 2)
        self.assertEqual(self.answers, [])

    def test_close_stops_everything_once(self):
        self.run_script([], lambda s: s.made >= 1)
        self.session.close("guard")
        self.session.close("again")
        self.assertFalse(self.session.active())
        self.glow.hide.assert_called_once()
        log = next(Path(self.tmp.name).glob("*_voice.txt")).read_text(encoding="utf-8")
        self.assertIn("closed: guard", log)


class GuardHookTest(unittest.TestCase):
    def test_battery_or_a_game_ends_it(self):
        import voice_guard

        fake = mock.Mock()
        fake.active.return_value = True
        with mock.patch.object(voice_session, "Session", return_value=fake), \
                mock.patch.dict(voice_session._session, {"it": None}), mock.patch.object(voice_guard, "listeners", []):
            voice_session.setup(None, None, None, None, Path("."))
            hook, = voice_guard.listeners
            hook("ready", False)
            fake.close.assert_not_called()
            hook("ready", True)
            hook("idle", False)
            self.assertEqual(fake.close.call_count, 2)


class LocalOnlyTest(unittest.TestCase):
    def test_never_a_paid_transcription(self):
        with mock.patch.object(voice, "stt_on", return_value=True), \
                mock.patch.object(voice.local_stt, "loaded", return_value=False), \
                mock.patch.object(voice, "transcribe_openrouter", side_effect=AssertionError("paid")):
            self.assertEqual(voice_session._local_transcribe(b"wav"), "")


if __name__ == "__main__":
    unittest.main()
