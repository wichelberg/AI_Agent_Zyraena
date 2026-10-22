"""Local speech-to-text plumbing and voice training data, without Whisper or a microphone:
a fake speech worker stands in for speech_worker.py.

Run from the project folder: python -m unittest discover -s tests
"""
import io
import json
import os
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import voice  # noqa: E402
import voice_data  # noqa: E402
import voice_recorder  # noqa: E402

FAKE_WORKER = textwrap.dedent("""
    import json, os, sys
    print("a library printing to stdout", flush=True)
    print(json.dumps({"ready": True, "device": "fake", "seconds": 0.1}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        if request.get("prompt") == "die":
            sys.exit(1)
        print(json.dumps({"ok": True, "text": "duydum " + str(os.path.exists(request["wav"]))}), flush=True)
""")


def wav_bytes(seconds=1.0, amplitude=0.3, rate=16000):
    t = np.arange(int(seconds * rate)) / rate
    out = io.BytesIO()
    sf.write(out, (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32), rate, format="WAV", subtype="PCM_16")
    return out.getvalue()


class Home(unittest.TestCase):
    """Each test gets its own voice home and a clean set of speech settings."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        env = {key: "" for key in os.environ if key.startswith(("ZYRAENA_STT", "ZYRAENA_VOICE"))}
        env.update(ZYRAENA_VOICE_HOME=str(self.home), ZYRAENA_STT_PYTHON=sys.executable)
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        # its own audio folder too: a running Zyraena writes into the shared one while it listens
        audio = mock.patch.object(voice, "_audio_dir", self.home / "audio")
        audio.start()
        self.addCleanup(audio.stop)
        self.addCleanup(self.tmp.cleanup)


class LocalSttTest(Home):
    def setUp(self):
        super().setUp()
        script = self.home / "fake_worker.py"
        script.write_text(FAKE_WORKER, encoding="utf-8")
        self.model = self.home / "models" / voice.LocalStt.DEFAULT_MODEL.replace("/", "--")
        self.model.mkdir(parents=True)
        (self.model / "model.bin").write_bytes(b"")
        self.stt = voice.LocalStt(script=script)
        self.addCleanup(self.stt.stop)

    def test_transcribes_through_the_worker_and_cleans_up(self):
        self.assertEqual(self.stt.transcribe(wav_bytes()), "duydum True")  # the wav existed while heard
        self.assertEqual(self.stt.device, "fake")
        self.assertEqual(list(voice._audio_dir.glob("*_heard.wav")), [])

    def test_restarts_after_the_worker_dies(self):
        os.environ["ZYRAENA_STT_PROMPT"] = "die"
        with self.assertRaises(RuntimeError):
            self.stt.transcribe(wav_bytes())
        os.environ["ZYRAENA_STT_PROMPT"] = ""
        self.assertEqual(self.stt.transcribe(wav_bytes()), "duydum True")

    def test_stops_when_idle(self):
        self.stt.WATCH_SECONDS = 0.05
        os.environ["ZYRAENA_STT_IDLE_MINUTES"] = "0.001"  # 60 ms
        self.stt.start()
        proc = self.stt._proc
        deadline = time.monotonic() + 5
        while self.stt._proc is not None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIsNone(self.stt._proc)
        self.assertIsNotNone(proc.wait(5))

    def test_a_game_stops_a_worker_still_loading_at_once(self):
        slow = self.home / "slow_worker.py"
        slow.write_text("import time\ntime.sleep(60)\n" + FAKE_WORKER, encoding="utf-8")  # a long cold load
        stt = voice.LocalStt(script=slow)
        self.addCleanup(stt.stop)
        failed = []

        def load():
            try:
                stt.start()
            except RuntimeError as e:
                failed.append(e)

        loader = threading.Thread(target=load, daemon=True)
        loader.start()
        deadline = time.monotonic() + 5
        while stt._proc is None and time.monotonic() < deadline:
            time.sleep(0.02)
        proc = stt._proc
        self.assertTrue(stt.busy())
        started = time.monotonic()
        stt.stop(at_once=True)
        self.assertLess(time.monotonic() - started, 1.0)  # no waiting for the load
        self.assertIsNotNone(proc.wait(5))
        loader.join(5)
        self.assertEqual(len(failed), 1)  # its loader fails...
        self.assertIsNone(stt._proc)
        self.assertFalse(stt._lock.locked())  # ...and lets go, so the next start works

    def test_stop_at_once_on_an_idle_worker_stops_it_normally(self):
        self.stt.start()
        proc = self.stt._proc
        self.stt.stop(at_once=True)
        self.assertIsNone(self.stt._proc)
        self.assertIsNotNone(proc.wait(5))

    def test_unavailable_without_voice_env(self):
        os.environ["ZYRAENA_STT_PYTHON"] = str(self.home / "missing" / "python.exe")
        self.assertIsNone(self.stt.transcribe(wav_bytes()))

    def test_never_waits_on_a_download(self):
        os.environ["ZYRAENA_STT_MODEL"] = "org/not-downloaded-yet"
        self.assertEqual(self.stt.model_folder(), self.home / "models" / "org--not-downloaded-yet")
        self.assertIsNone(self.stt.transcribe(wav_bytes()))
        self.assertIsNone(self.stt._proc)

    def test_model_can_be_a_folder(self):
        os.environ["ZYRAENA_STT_MODEL"] = str(self.model)
        self.assertEqual(self.stt.transcribe(wav_bytes()), "duydum True")


class TranscribeChoiceTest(Home):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(voice.local_stt, "available", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_local_first(self):
        with mock.patch.object(voice.local_stt, "transcribe", return_value="yerel"), \
                mock.patch.object(voice, "transcribe_openrouter") as remote:
            self.assertEqual(voice.transcribe(b"x", "model"), "yerel")
            remote.assert_not_called()

    def test_falls_back_when_local_fails_or_hears_nothing(self):
        for local in (mock.Mock(side_effect=RuntimeError("boom")), mock.Mock(return_value="")):
            with mock.patch.object(voice.local_stt, "transcribe", local), \
                    mock.patch.object(voice, "transcribe_openrouter", return_value="bulut") as remote, \
                    mock.patch("builtins.print"):
                self.assertEqual(voice.transcribe(b"x", "model"), "bulut")
                remote.assert_called_once_with(b"x", "model")

    def test_openrouter_setting_missing_env_or_a_game_skip_local(self):
        cases = ({"env": {"ZYRAENA_STT": "openrouter"}}, {"available": False}, {"gaming": True})
        for case in cases:
            with mock.patch.dict(os.environ, case.get("env", {})), \
                    mock.patch.object(voice.local_stt, "available", return_value=case.get("available", True)), \
                    mock.patch.dict(voice.gaming, {"on": case.get("gaming", False)}), \
                    mock.patch.object(voice.local_stt, "transcribe") as local, \
                    mock.patch.object(voice, "transcribe_openrouter", return_value="bulut"):
                self.assertEqual(voice.transcribe(b"x", "model"), "bulut", case)
                local.assert_not_called()


class VoiceDataTest(Home):
    def test_saves_clip_and_line(self):
        clip_id = voice_data.save(wav_bytes(1.5), "  Merhaba Zyraena  ", "mic", heard="merhaba zirena")
        [sample] = voice_data.samples()
        self.assertEqual(sample["id"], clip_id)
        self.assertEqual((sample["text"], sample["heard"], sample["source"]), ("Merhaba Zyraena", "merhaba zirena", "mic"))
        self.assertAlmostEqual(sample["seconds"], 1.5, places=2)
        audio, rate = sf.read(voice_data.data_dir() / sample["audio"])
        self.assertEqual((len(audio), rate), (24000, 16000))

    def test_keeps_nothing_when_off_or_empty(self):
        self.assertIsNone(voice_data.save(wav_bytes(), "  ", "mic"))
        self.assertIsNone(voice_data.save(b"", "metin", "mic"))
        os.environ["ZYRAENA_VOICE_DATA"] = "off"
        self.assertIsNone(voice_data.save(wav_bytes(), "metin", "mic"))
        self.assertEqual(voice_data.samples(), [])

    def test_skips_broken_lines(self):
        voice_data.save(wav_bytes(), "bir", "reading")
        with open(voice_data.data_dir() / "samples.jsonl", "a", encoding="utf-8") as f:
            f.write("{yarım satır\n")
        voice_data.save(wav_bytes(), "iki", "reading")
        self.assertEqual([s["text"] for s in voice_data.samples()], ["bir", "iki"])


class TelegramSampleTest(Home):
    def test_confirmed_voice_note_is_kept(self):
        import telegram_listener as tl

        note = wav_bytes(1.0)
        with mock.patch.object(tl, "_download", return_value=note), \
                mock.patch.object(tl.voice, "transcribe", return_value="ekranı göster"):
            audio, heard = tl._hear(None, "file-id")
        tl._keep_sample(audio, heard)
        [sample] = voice_data.samples()
        self.assertEqual((sample["text"], sample["heard"], sample["source"]), ("ekranı göster", "ekranı göster", "telegram"))

    def test_saving_never_breaks_the_reply(self):
        import telegram_listener as tl

        with mock.patch.object(tl.voice_data, "save", side_effect=OSError("disk full")), \
                mock.patch("builtins.print"):
            tl._keep_sample(wav_bytes(), "metin")  # no exception


class RecorderToolTest(unittest.TestCase):
    def test_sentence_list(self):
        if not voice_recorder.SENTENCES.is_file():
            self.skipTest("voice_sentences_tr.txt is gitignored; not in this checkout")
        sentences = voice_recorder.load_sentences(voice_recorder.SENTENCES)
        self.assertGreaterEqual(len(sentences), 200)
        self.assertEqual(len(sentences), len(set(sentences)), "duplicate sentences")
        self.assertFalse([s for s in sentences if s.startswith("#")])

    def test_take_checks(self):
        self.assertIsNone(voice_recorder.check(wav_bytes(2.0, 0.3))[1])
        self.assertIn("kısa", voice_recorder.check(wav_bytes(0.3, 0.3))[1])
        self.assertIn("sessiz", voice_recorder.check(wav_bytes(2.0, 0.01))[1])
        self.assertIn("kırpılma", voice_recorder.check(wav_bytes(2.0, 1.0))[1])


if __name__ == "__main__":
    unittest.main()
