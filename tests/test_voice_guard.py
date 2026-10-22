"""voice_guard: when the voice models get out of a game's way and when they load ahead.
No GPU: readings are made up, the workers are fakes.

Run from the project folder: python -m unittest discover -s tests
"""
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import voice_guard as g  # noqa: E402

TOTAL = 8151
CALM = g.Reading(util=3, mem_used=900, mem_total=TOTAL, temp=48)
GAME = g.Reading(util=85, mem_used=5200, mem_total=TOTAL, temp=72)


class StepTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"ZYRAENA_TTS_GPU_BUSY": "", "ZYRAENA_HEALTH_GPU_TEMP": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state = g.State()
        self.now = 1000.0

    def step(self, reading, seconds=g.CHECK_SECONDS, plugged=True, ours_busy=False, ours_mb=0, preload=True):
        self.now += seconds
        return g.step(self.state, reading, self.now, plugged, ours_busy, ours_mb, preload)

    def test_loads_ahead_after_starting_calm(self):
        self.assertEqual(self.step(CALM), "idle")  # calm starts counting
        self.assertEqual(self.step(CALM, seconds=g.FIRST_CALM_SECONDS), "ready")

    def test_not_on_battery_or_when_turned_off(self):
        self.step(CALM)
        self.assertEqual(self.step(CALM, seconds=60, plugged=False), "idle")
        state = g.State()
        g.step(state, CALM, 0, True, False, 0, preload=False)
        self.assertEqual(g.step(state, CALM, 60, True, False, 0, preload=False), "idle")

    def test_game_needs_two_busy_readings(self):
        self.step(CALM)
        self.step(CALM, seconds=60)
        self.assertEqual(self.step(GAME), "ready")  # one spike isn't a game
        self.assertEqual(self.step(GAME), "game")

    def test_our_own_work_is_not_a_game(self):
        self.step(CALM)
        self.step(CALM, seconds=60)
        for _ in range(4):
            self.assertEqual(self.step(g.Reading(85, 6000, TOTAL, 60), ours_busy=True, ours_mb=5300), "ready")

    def test_a_game_starting_while_ours_load_is_still_noticed(self):
        # 2026-10-20: Helldivers 2 started while Whisper and Chatterbox loaded (util 93 %, 7.4 GB used)
        self.step(CALM)
        self.step(CALM, seconds=60)
        loading_and_game = g.Reading(93, 7423, TOTAL, 72)
        self.assertEqual(self.step(loading_and_game, ours_busy=True, ours_mb=4200), "ready")
        self.assertEqual(self.step(loading_and_game, ours_busy=True, ours_mb=4200), "game")

    def test_ours_with_the_usual_desktop_vram_is_still_ours(self):
        self.step(CALM)
        self.step(CALM, seconds=60)
        desktop = g.Reading(90, 4200 + g.OTHERS_GAME_MB - 100, TOTAL, 60)
        for _ in range(4):
            self.assertEqual(self.step(desktop, ours_busy=True, ours_mb=4200), "ready")

    def test_heat_and_full_memory_act_at_once(self):
        self.step(CALM)
        self.step(CALM, seconds=60)
        self.assertEqual(self.step(g.Reading(10, 2000, TOTAL, 88)), "game")
        state = g.State(mode="ready")
        self.assertEqual(g.step(state, g.Reading(10, 7900, TOTAL, 60), 0, True, False, 5300), "game")

    def test_back_after_two_calm_minutes_with_room(self):
        self.step(GAME)
        self.assertEqual(self.step(GAME), "game")
        self.assertEqual(self.step(CALM), "game")
        self.assertEqual(self.step(CALM, seconds=60), "game")  # not 2 minutes yet
        self.assertEqual(self.step(CALM, seconds=61), "ready")

    def test_no_loading_without_room_or_while_warm(self):
        self.step(GAME)
        self.step(GAME)
        crowded = g.Reading(10, 3500, TOTAL, 50)  # a game left open in the background
        for _ in range(12):
            self.assertEqual(self.step(crowded, seconds=30), "game")
        warm = g.Reading(10, 900, TOTAL, 84)  # under the limit, but not 5 °C under
        for _ in range(12):
            self.assertEqual(self.step(warm, seconds=30), "game")

    def test_battery_while_ready(self):
        self.step(CALM)
        self.step(CALM, seconds=60)
        self.assertEqual(self.step(CALM, plugged=False), "idle")

    def test_no_reading_keeps_the_mode(self):
        self.state.mode = "ready"
        self.assertEqual(self.step(None), "ready")


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.stt, self.tts, self.rvc = mock.Mock(), mock.Mock(), mock.Mock()
        for worker in (self.stt, self.tts, self.rvc):
            worker.stale.return_value = False
            worker.busy.return_value = False
        self.rvc.available.return_value = True
        self.gaming = {"on": False}
        self.loads = []  # what apply() started loading in the background
        for p in (mock.patch.object(g.voice, "local_stt", self.stt), mock.patch.object(g.voice, "local_tts", self.tts),
                  mock.patch.object(g.voice, "voice_pack", self.rvc), mock.patch.object(g.voice, "gaming", self.gaming),
                  mock.patch.object(g.voice, "stt_on", return_value=True),
                  mock.patch.object(g.voice, "tts_on", return_value=True),
                  mock.patch.object(g, "_in_background", side_effect=lambda load: (self.loads.append(load), load()))):
            p.start()
            self.addCleanup(p.stop)

    def test_game_stops_everything_local_at_once(self):
        self.rvc.stale.return_value = True  # running on the GPU
        g.apply("game")
        for worker in (self.tts, self.stt, self.rvc):
            worker.stop.assert_called_once_with(at_once=True)  # even half loaded: no waiting for it
        self.assertTrue(self.gaming["on"])
        self.assertFalse(self.tts.keep_loaded or self.stt.keep_loaded)

    def test_ready_loads_off_the_guards_thread(self):
        self.stt.loaded.return_value = self.tts.loaded.return_value = False
        g.apply("ready")
        self.assertEqual(self.loads, [self.stt.start, self.tts.start])

    def test_ready_leaves_a_model_still_loading_alone(self):
        self.stt.loaded.return_value = self.tts.loaded.return_value = False
        self.stt.busy.return_value = True
        g.apply("ready")
        self.stt.start.assert_not_called()
        self.tts.start.assert_called_once()


    def test_game_stops_the_voice_pack_wherever_it_runs(self):
        g.apply("game")  # stale() is False: on the CPU
        self.rvc.stop.assert_called_once()

    def test_ready_loads_both_and_keeps_them(self):
        self.stt.loaded.return_value = self.tts.loaded.return_value = self.rvc.loaded.return_value = False
        g.apply("ready")
        self.stt.start.assert_called_once()
        self.tts.start.assert_called_once()
        self.assertTrue(self.stt.keep_loaded and self.tts.keep_loaded)
        self.assertFalse(self.gaming["on"])

    def test_the_voice_pack_is_never_loaded_ahead_nor_kept(self):
        self.rvc.loaded.return_value = False
        self.rvc.keep_loaded = False
        g.apply("ready")
        self.rvc.start.assert_not_called()
        self.assertFalse(self.rvc.keep_loaded)

    def test_ready_leaves_loaded_models_alone(self):
        self.stt.loaded.return_value = self.tts.loaded.return_value = self.rvc.loaded.return_value = True
        g.apply("ready")
        self.stt.start.assert_not_called()
        self.tts.start.assert_not_called()
        self.rvc.stop.assert_not_called()

    def test_ready_stops_the_voice_pack_left_on_the_cpu(self):
        self.stt.loaded.return_value = self.tts.loaded.return_value = True
        self.rvc.stale.return_value = True  # still on the CPU from the game: next use starts it on the GPU
        g.apply("ready")
        self.rvc.stop.assert_called_once()

    def test_idle_lets_them_unload(self):
        g.apply("idle")
        self.stt.start.assert_not_called()
        self.tts.start.assert_not_called()
        self.assertFalse(self.stt.keep_loaded or self.tts.keep_loaded)

    def test_full_vram_moves_the_voice_pack_off_the_gpu_first(self):
        self.rvc.loaded.return_value, self.rvc.device = True, "gpu"
        after = g.Reading(5, 5800, TOTAL, 50)
        with mock.patch.object(g, "_read_gpu", return_value=after), mock.patch.object(g, "_log"):
            self.assertIs(g._make_room(g.Reading(5, 7760, TOTAL, 50)), after)
        self.rvc.off_the_gpu.assert_called_once()

    def test_room_is_left_alone_when_not_full_or_on_the_cpu(self):
        self.rvc.loaded.return_value, self.rvc.device = True, "gpu"
        calm = g.Reading(5, 7000, TOTAL, 50)
        self.assertIs(g._make_room(calm), calm)
        self.rvc.device = "cpu"
        full = g.Reading(5, 7900, TOTAL, 50)
        self.assertIs(g._make_room(full), full)
        self.rvc.off_the_gpu.assert_not_called()

    def test_our_vram_counts_the_voice_pack_only_on_the_gpu(self):
        self.stt.loaded.return_value = self.tts.loaded.return_value = False
        self.rvc.loaded.return_value, self.rvc.device = True, "gpu"
        self.assertEqual(g._ours_mb(), g.RVC_GPU_MB)
        self.rvc.device = "cpu"
        self.assertEqual(g._ours_mb(), 0)


class InBackgroundTest(unittest.TestCase):
    def test_returns_at_once_and_logs_a_failed_load(self):
        release, failed = threading.Event(), threading.Event()

        def slow_broken_load():
            release.wait(5)
            raise RuntimeError("tts_worker stopped")

        with mock.patch.object(g, "_log", side_effect=lambda text: failed.set()) as log:
            started = time.monotonic()
            g._in_background(slow_broken_load)
            self.assertLess(time.monotonic() - started, 0.5)  # the guard's loop goes on reading the GPU
            release.set()
            self.assertTrue(failed.wait(5))
        self.assertIn("loading failed: RuntimeError", log.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
