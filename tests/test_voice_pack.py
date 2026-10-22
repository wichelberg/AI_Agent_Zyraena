"""voice.VoicePack: the voice pack's worker on the GPU, or on the CPU during a game, without Wichelberg:
a fake worker stands in for voice_worker.py.

Run from the project folder: python -m unittest discover -s tests
"""
import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import voice  # noqa: E402

# argv like voice_worker.py: <wichelberg> <pack> <cpu|gpu> <parity file>; "converts" by copying
FAKE_WORKER = textwrap.dedent("""
    import json, shutil, sys
    if sys.argv[2].endswith("broken"):
        sys.exit(1)
    print(json.dumps({"ready": True, "device": sys.argv[3], "seconds": 0.1, "note": "fake"}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        shutil.copy(request["in"], request["wav"])
        print(json.dumps({"ok": True, "seconds": 0.01, "device": sys.argv[3]}), flush=True)
""")


class VoicePackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        script = self.home / "fake_voice_worker.py"
        script.write_text(FAKE_WORKER, encoding="utf-8")
        self.pack = self.home / "zyraena"
        self.pack.mkdir()
        (self.pack / "voice.json").write_text("{}", encoding="utf-8")
        self.src = self.home / "in_tts.wav"
        self.src.write_bytes(b"RIFF")
        self.gaming = {"on": False}
        env = {"ZYRAENA_VOICE_HOME": str(self.home), "ZYRAENA_VOICE_PACK": str(self.pack), "ZYRAENA_RVC_DEVICE": ""}
        for p in (mock.patch.dict(os.environ, env), mock.patch.object(voice, "gaming", self.gaming),
                  mock.patch.object(voice, "_worker_python", return_value=Path(sys.executable)),
                  mock.patch("builtins.print")):
            p.start()
            self.addCleanup(p.stop)
        self.worker = voice.VoicePack(script=script)
        self.addCleanup(self.worker.stop)

    def convert(self):
        out = self.home / "out.wav"
        out.unlink(missing_ok=True)
        self.assertTrue(self.worker.convert(self.src, out, None))
        self.assertTrue(out.is_file())

    def test_gpu_when_no_game_runs(self):
        self.convert()
        self.assertEqual((self.worker.accel, self.worker.device), ("gpu", "gpu"))
        self.assertFalse(self.worker.stale())

    def test_a_game_moves_it_to_the_cpu_and_back(self):
        self.convert()
        first = self.worker._proc
        self.gaming["on"] = True
        self.assertTrue(self.worker.stale())
        self.convert()
        self.assertEqual(self.worker.device, "cpu")
        self.assertIsNotNone(first.wait(5))  # the GPU worker was stopped
        self.gaming["on"] = False
        self.assertTrue(self.worker.stale())
        self.worker.start()
        self.assertEqual(self.worker.device, "gpu")

    def test_full_vram_moves_it_to_the_cpu_for_a_while(self):
        self.convert()
        self.worker.off_the_gpu()
        self.assertFalse(self.worker.loaded())
        self.convert()
        self.assertEqual(self.worker.device, "cpu")
        self.worker.cpu_until = 0.0  # CPU_MINUTES later
        self.assertTrue(self.worker.stale())

    def test_cpu_only_setting(self):
        os.environ["ZYRAENA_RVC_DEVICE"] = "cpu"
        self.convert()
        self.assertEqual(self.worker.device, "cpu")

    def test_no_voice_pack_means_no_conversion(self):
        os.environ["ZYRAENA_VOICE_PACK"] = ""
        self.assertFalse(self.worker.convert(self.src, self.home / "out.wav", None))
        self.assertIsNone(self.worker._proc)

    def test_a_worker_that_does_not_start_leaves_the_speech_as_it_is(self):
        broken = self.home / "broken"
        shutil.copytree(self.pack, broken)
        os.environ["ZYRAENA_VOICE_PACK"] = str(broken)
        self.assertFalse(self.worker.convert(self.src, self.home / "out.wav", None))

    def test_arguments_name_the_device_and_the_parity_file(self):
        self.worker.accel = "gpu"
        args = self.worker.arguments()
        self.assertEqual(args[1:], [self.pack, "gpu", self.home / "rvc_parity.json"])


class WichelbergParityTest(unittest.TestCase):
    def test_a_gpu_wichelberg_found_different_is_never_used(self):
        import voice_worker

        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config"
            config.mkdir()
            (config / "config.json").write_text(json.dumps(
                {"ai": {"benchmark": {"gpus": [{"device_id": 1, "parity_ok": False}, {"device_id": 0, "parity_ok": True}]}}}),
                encoding="utf-8")
            self.assertTrue(voice_worker._wichelberg_says_different(Path(folder), 1))
            self.assertFalse(voice_worker._wichelberg_says_different(Path(folder), 0))
            self.assertFalse(voice_worker._wichelberg_says_different(Path(folder) / "missing", 0))


if __name__ == "__main__":
    unittest.main()
