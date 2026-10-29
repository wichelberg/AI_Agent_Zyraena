"""user_care: breaks, snoozes by mood, forced breaks, water, being away, sleep, the night rules, the
step-by-step shutdown (dry run), the protection list, the mood and its prompt block, the morning summary
and the saved state. Everything runs on a fake clock with fake windows, a fake protection check and a
temporary state folder: no window opens, no shutdown, no network, config.json is not touched.

care_guard is tested against real processes this test starts itself. The Windows test needs a working
Tcl/Tk (py -3); without one it is skipped.
Run from the project folder: python -m unittest discover -s tests
"""
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import care_guard  # noqa: E402
import i18n  # noqa: E402
import user_care  # noqa: E402

STEP = 60  # seconds per tick: below sleep_gap_seconds, so moving on never looks like sleep


class FakeUi:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return record

    def kinds(self, name):
        return [c for c in self.calls if c[0] == name]

    def last(self, name):
        found = self.kinds(name)
        return found[-1] if found else None


class FakeGuard:
    def __init__(self):
        self.found = []

    def sample(self, cfg):
        pass

    def reasons(self, cfg):
        return list(self.found)


class StillClock(user_care.FakeClock):
    """A fake clock that only moves with advance()."""

    def __init__(self, at):
        super().__init__(at, speed=1)

    def mono(self):
        return self._offset


# The rule tests below were written with these numbers; the shipped defaults (rougher, owner 2026-10-24)
# are pinned in StateAndConfigTest.test_rough_default_points.
TEST_MOOD = {"start": 50, "drift_per_hour": 2,
             "points": {"break": 5, "snooze": -5, "unanswered": -10, "forced_done": 10, "emergency_exit": -20,
                        "water": 5, "water_later": 0, "sleep_warning": -10, "on_time_bed": 20, "peace": 10,
                        "shutdown_cancel": -20}}


class Sim:
    """A Care on a fake clock; run() moves time on in STEP-second ticks."""

    def __init__(self, at="10:00", mood=50, classify=None, folder=None, cfg=None):
        self.folder = folder or tempfile.mkdtemp(prefix="care_test_")
        hour, minute = map(int, at.split(":"))
        self.clock = StillClock(datetime(2026, 10, 21, hour, minute))  # 2026-10-21 is a Wednesday
        self.ui, self.guard = FakeUi(), FakeGuard()
        self.sent, self.chats = [], []
        self.gaming = False  # what the game check says
        self.cfg = user_care.merged(user_care.merged(user_care.DEFAULTS, {"debug": {"telegram": True},
                                                                         "mood": TEST_MOOD}), cfg or {})
        self.care = user_care.Care(self.cfg, user_care.Store(self.folder), self.clock, self.ui, self.guard,
                                   classify=classify, notify=self.sent.append, chat=self.chats.append,
                                   lang=lambda: "tr", idle=lambda: 0, video=lambda: False,
                                   game=lambda: self.gaming)
        self.care.state["mood"] = float(mood)
        self.idle = 0.0
        self.care.tick(idle=0, video=False)

    def run(self, minutes, idle=None):
        """`minutes` of use; idle: seconds since the last input (None: the user is active)."""
        for _ in range(int(minutes * 60 // STEP)):
            self.clock.advance(STEP)
            if idle is not None:
                self.idle += STEP
            self.care.tick(idle=self.idle if idle is not None else 0, video=False)
        if idle is None:
            self.idle = 0.0

    def kinds(self):
        return [e["kind"] for e in self.care.state["recent"]]

    def prompts(self, kind="break"):
        return [c for c in self.ui.kinds("prompt") if c[1][0] == kind]

    def mood(self):
        return round(self.care.state["mood"])

    def answer(self, value):
        self.care.answer_break(value)


def wait_for(check, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return False


class MoodTest(unittest.TestCase):
    def test_levels_and_their_edges(self):
        care = Sim().care
        self.assertEqual([care.level(m) for m in (0, 30, 31, 69, 70, 100)],
                         ["angry", "angry", "normal", "normal", "happy", "happy"])

    def test_drifts_back_to_50_by_two_points_an_hour(self):
        sim = Sim(mood=20, cfg={"break": {"every_minutes": 600}, "water": {"every_minutes": 600}})
        sim.run(120)
        self.assertEqual(sim.mood(), 24)
        sim = Sim(mood=51, cfg={"break": {"every_minutes": 600}, "water": {"every_minutes": 600}})
        sim.run(120)
        self.assertEqual(sim.care.state["mood"], 50)  # stops at 50, doesn't overshoot


class BreakTest(unittest.TestCase):
    def test_prompt_after_an_hour_of_use(self):
        sim = Sim(cfg={"water": {"every_minutes": 600}})
        sim.run(59)
        self.assertIsNone(sim.ui.last("prompt"))
        sim.run(1)
        name, args, _ = sim.ui.last("prompt")
        self.assertEqual(args[0], "break")
        self.assertEqual([label for label, _ in args[3]], ["Mola ver", "Ertele"])

    def test_snooze_costs_5(self):
        sim = Sim()
        sim.run(60)
        sim.answer("snooze")
        self.assertEqual(sim.mood(), 45)
        self.assertEqual(sim.care.state["snoozes"], 1)

    def test_after_a_snooze_the_prompt_comes_back_an_hour_later(self):
        sim = Sim(mood=85)  # happy: a second snooze is allowed, so the next one is a prompt again
        sim.run(60)
        sim.answer("snooze")
        prompts = len(sim.prompts())
        sim.run(59)
        self.assertEqual(len(sim.prompts()), prompts)
        sim.run(1)
        self.assertEqual(len(sim.prompts()), prompts + 1)

    def test_take_break_gives_5_resets_and_ends_with_telegram(self):
        sim = Sim()
        sim.run(60)
        sim.answer("break")
        self.assertEqual(sim.mood(), 55)
        self.assertEqual((sim.care.state["cycle"], sim.care.state["snoozes"], sim.care.state["active"]), (0, 0, 0))
        name, args, kwargs = sim.ui.last("break_window")
        self.assertEqual(args[0], 300)  # 5 minutes (owner, 2026-10-26; was 10)
        kwargs["on_done"]()
        self.assertTrue(wait_for(lambda: sim.sent))
        self.assertIn("Mola bitti", sim.sent[0])

    def snooze_until_forced(self, mood):
        sim = Sim(mood=mood)
        hours = 0
        while not sim.ui.kinds("forced") and hours < 5:
            sim.run(58)
            if sim.care.forced_at is None:
                sim.run(2)
                if sim.care.prompts.get("break"):
                    sim.answer("snooze")
                    sim.care.state["mood"] = float(mood)  # keep the mood level for this check
            else:
                self.assertIn("forced_warning", sim.kinds())
                sim.run(2)
            hours += 1
        return hours

    def test_snoozes_allowed_by_mood(self):
        self.assertEqual(self.snooze_until_forced(80), 3)  # happy: 2 snoozes, forced in the 3rd hour
        self.assertEqual(self.snooze_until_forced(50), 2)  # normal: 1
        self.assertEqual(self.snooze_until_forced(20), 1)  # angry: 0, forced in the 1st hour

    def test_forced_break_warns_2_minutes_before(self):
        sim = Sim(mood=20)
        sim.run(57)
        self.assertIsNone(sim.ui.last("notice"))
        sim.run(1)
        name, args, _ = sim.ui.last("notice")
        self.assertEqual(args[0], "forced")
        self.assertIn("kaydet", args[2])
        sim.run(1)
        self.assertFalse(sim.ui.kinds("forced"))
        sim.run(1)
        name, args, kwargs = sim.ui.last("forced")
        self.assertEqual(args[0], 300)  # 5 minutes

    def test_forced_break_done_gives_10_and_resets(self):
        sim = Sim(mood=20)
        sim.run(60)
        _, _, kwargs = sim.ui.last("forced")
        kwargs["on_done"]()
        self.assertEqual(sim.mood(), 32)  # 20, +2 drifting back toward 50 in that hour, +10
        self.assertEqual((sim.care.state["active"], sim.care.state["snoozes"]), (0, 0))
        self.assertTrue(wait_for(lambda: sim.sent))

    def test_emergency_exit_costs_20_and_she_remembers_why(self):
        sim = Sim(mood=20)
        sim.run(60)
        _, _, kwargs = sim.ui.last("forced")
        kwargs["on_exit"]("rapor teslimi")
        self.assertEqual(sim.mood(), 2)  # 20 +2 drift -20
        exit_event = sim.care.state["recent"][-1]
        self.assertEqual((exit_event["kind"], exit_event["reason"]), ("emergency_exit", "rapor teslimi"))
        self.assertIn('"rapor teslimi"', sim.care.prompt_block())
        on_disk = [json.loads(line) for line in sim.care.store.events_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(on_disk[-1]["reason"], "rapor teslimi")

    def test_unanswered_while_using_the_pc_costs_10_and_counts_as_a_snooze(self):
        sim = Sim()
        sim.run(65)
        self.assertEqual(sim.mood(), 40)
        self.assertEqual(sim.care.state["snoozes"], 1)
        self.assertIn("unanswered", sim.kinds())

    def test_unanswered_while_away_is_no_snooze_and_becomes_a_break(self):
        sim = Sim()
        sim.run(60)
        sim.run(12, idle=True)
        self.assertNotIn("unanswered", sim.kinds())
        self.assertIn("afk_break", sim.kinds())
        self.assertEqual(sim.mood(), 50)
        self.assertEqual(sim.care.state["cycle"], 0)


class AwayTest(unittest.TestCase):
    def test_timers_stop_while_away(self):
        sim = Sim(cfg={"break": {"afk_break_minutes": 10}})  # by default 5 min away is already a break
        sim.run(30)
        sim.run(8, idle=True)
        cycle = sim.care.state["cycle"]
        self.assertLess(cycle, 36 * 60)  # 30 active + at most the 5 minutes before counting as away
        self.assertNotIn("afk_break", sim.kinds())

    def test_five_minutes_away_is_a_break(self):
        sim = Sim()
        sim.run(50)
        sim.run(4, idle=True)
        self.assertNotIn("afk_break", sim.kinds())
        sim.run(2, idle=True)
        self.assertEqual(sim.kinds().count("afk_break"), 1)
        self.assertEqual(sim.care.state["active"], 0)

    def test_ten_minutes_away_is_a_break(self):
        sim = Sim()
        sim.run(50)
        sim.run(11, idle=True)
        self.assertEqual(sim.kinds().count("afk_break"), 1)
        self.assertEqual(sim.care.state["active"], 0)

    def test_fullscreen_video_is_not_away(self):
        sim = Sim()
        sim.run(30)
        for _ in range(20):
            sim.clock.advance(STEP)
            sim.care.tick(idle=20 * 60, video=True)
        self.assertNotIn("afk_break", sim.kinds())
        self.assertGreaterEqual(sim.care.state["cycle"], 49 * 60)

    def test_sleep_counts_as_a_break_without_points(self):
        sim = Sim()
        sim.run(55)
        sim.clock.advance(45 * 60)
        sim.care.tick(idle=0, video=False)
        self.assertIn("sleep", sim.kinds())
        self.assertEqual(sim.mood(), 50)
        self.assertEqual(sim.care.state["cycle"], 0)

    def test_sleep_closes_an_open_prompt_without_penalty(self):
        sim = Sim()
        sim.run(60)
        self.assertIn("break", sim.care.prompts)
        sim.clock.advance(30 * 60)
        sim.care.tick(idle=0, video=False)
        self.assertNotIn("break", sim.care.prompts)
        self.assertNotIn("unanswered", sim.kinds())


class GameTest(unittest.TestCase):
    """In a game (owner, 2026-10-26): never a break prompt or a forced break; an hourly notice, the first
    free, then -5 each; a 5-minute break after a notice gives +5 and the count starts again."""

    NO_WATER = {"water": {"every_minutes": 600}, "mood": {"drift_per_hour": 0}}  # only the game points move it

    def gaming_sim(self, mood=50):
        sim = Sim(mood=mood, cfg=self.NO_WATER)
        sim.gaming = True
        return sim

    def notices(self, sim):
        return [c for c in sim.ui.kinds("notice") if c[1][0] == "game"]

    def test_first_hour_is_a_free_notice_then_minus_5_an_hour(self):
        sim = self.gaming_sim()
        sim.run(60)
        self.assertEqual(sim.prompts(), [])
        self.assertEqual(len(self.notices(sim)), 1)
        self.assertIn("1 saat", self.notices(sim)[0][1][2])
        self.assertEqual((sim.mood(), sim.care.state["snoozes"]), (50, 0))
        sim.run(60)
        sim.run(60)
        self.assertEqual(len(self.notices(sim)), 3)
        self.assertIn("3 saat", self.notices(sim)[-1][1][2])
        self.assertEqual(sim.mood(), 40)
        self.assertEqual(sim.care.state["snoozes"], 0)
        self.assertFalse(sim.ui.kinds("forced"))

    def test_break_after_a_notice_gives_5_and_starts_again(self):
        sim = self.gaming_sim()
        sim.run(120)  # free notice, then -5
        sim.run(6, idle=True)
        self.assertEqual(sim.kinds()[-2:], ["afk_break", "game_break"])
        self.assertEqual(sim.mood(), 50)
        self.assertEqual((sim.care.state["cycle"], sim.care.state["active"], sim.care.state["game_warns"]), (0, 0, 0))
        sim.run(59)
        self.assertEqual(len(self.notices(sim)), 2)
        sim.run(1)
        self.assertEqual(len(self.notices(sim)), 3)
        self.assertEqual(sim.mood(), 50)  # the first notice after a break is free again

    def test_a_break_without_a_notice_gives_nothing(self):
        sim = self.gaming_sim()
        sim.run(40)
        sim.run(6, idle=True)
        self.assertIn("afk_break", sim.kinds())
        self.assertNotIn("game_break", sim.kinds())
        self.assertEqual(sim.mood(), 50)

    def test_no_forced_break_in_a_game_even_without_snoozes(self):
        sim = self.gaming_sim(mood=20)  # angry: 0 snoozes, normally forced at the first hour
        sim.run(180)
        self.assertFalse(sim.ui.kinds("forced"))
        self.assertFalse([c for c in sim.ui.kinds("notice") if c[1][0] == "forced"])
        self.assertEqual(len(self.notices(sim)), 3)

    def test_game_started_after_the_forced_warning(self):
        sim = Sim(mood=20, cfg=self.NO_WATER)
        sim.run(59)
        self.assertTrue([c for c in sim.ui.kinds("notice") if c[1][0] == "forced"])
        sim.gaming = True
        sim.run(2)
        self.assertFalse(sim.ui.kinds("forced"))
        self.assertEqual(len(self.notices(sim)), 1)

    def test_prompt_left_open_going_into_a_game_is_no_snooze(self):
        sim = Sim(cfg=self.NO_WATER)
        sim.run(60)
        self.assertEqual(len(sim.prompts()), 1)
        sim.gaming = True
        sim.run(6)
        self.assertNotIn("unanswered", sim.kinds())
        self.assertEqual((sim.mood(), sim.care.state["snoozes"]), (50, 0))
        self.assertEqual(len(self.notices(sim)), 1)

    def test_out_of_the_game_the_normal_prompt_comes_back(self):
        sim = self.gaming_sim()
        sim.run(60)
        sim.gaming = False
        sim.run(60)
        self.assertEqual(len(sim.prompts()), 1)


class GameDetectionTest(unittest.TestCase):
    class Proc:
        def __init__(self, exe):
            self.info = {"exe": exe}

    def detect(self, exes, front=None, fullscreen=False):
        cfg = dict(user_care.DEFAULTS["game"], fullscreen=fullscreen)
        procs = [self.Proc(e) for e in exes]
        with mock.patch("psutil.process_iter", lambda attrs=None: procs), \
                mock.patch.object(user_care, "_fullscreen_front", lambda: front):
            return user_care.playing_game(cfg)

    def test_game_folders_and_their_launchers(self):
        always_on = [r"C:\Program Files (x86)\Steam\steam.exe",
                     r"C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\wallpaper64.exe",
                     r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
                     r"C:\Program Files (x86)\Ubisoft\Ubisoft Game Launcher\upc.exe",
                     r"C:\Riot Games\Riot Client\RiotClientServices.exe", None]
        self.assertFalse(self.detect(always_on))
        self.assertTrue(self.detect(always_on + [r"E:\SteamLibrary\steamapps\common\Once Human\ONE_HUMAN.exe"]))
        self.assertTrue(self.detect([r"C:\Program Files (x86)\Ubisoft\Ubisoft Game Launcher\games\Far Cry 6\bin\FarCry6.exe"]))
        self.assertTrue(self.detect([r"C:\Riot Games\VALORANT\live\VALORANT.exe"]))

    def test_fullscreen_only_when_turned_on(self):
        self.assertFalse(user_care.DEFAULTS["game"]["fullscreen"])  # owner: game folders only
        self.assertFalse(self.detect([], front="someubisoftgame.exe"))
        self.assertTrue(self.detect([], front="someubisoftgame.exe", fullscreen=True))
        self.assertFalse(self.detect([], front="opera.exe", fullscreen=True))
        self.assertFalse(self.detect([], front="vlc.exe", fullscreen=True))
        self.assertFalse(self.detect([], front=None, fullscreen=True))


class WaterTest(unittest.TestCase):
    def test_water_every_20_minutes_and_drinking_gives_5(self):
        sim = Sim(cfg={"break": {"every_minutes": 600}})
        sim.run(19)
        self.assertFalse(sim.prompts("water"))
        sim.run(1)
        name, args, _ = sim.ui.last("prompt")
        self.assertEqual(args[0], "water")
        sim.care.answer_water("drank")
        self.assertEqual(sim.mood(), 55)

    def test_later_comes_back_in_15_minutes(self):
        sim = Sim(cfg={"break": {"every_minutes": 600}})
        sim.run(20)
        sim.care.answer_water("later")
        sim.run(14)
        self.assertEqual(len(sim.ui.kinds("prompt")), 1)
        sim.run(1)
        self.assertEqual(len(sim.ui.kinds("prompt")), 2)


class NightTest(unittest.TestCase):
    def night(self, mood=50, classify='{"category": "exam"}', **kw):
        cfg = {"break": {"every_minutes": 600}, "water": {"every_minutes": 600}}
        return Sim(at="23:59", mood=mood, classify=lambda prompt, what: classify, cfg=cfg, **kw)

    def test_sleep_warning_every_hour_after_midnight(self):
        sim = self.night()
        sim.run(3 * 60 - 2)  # until 02:57
        self.assertEqual(sim.kinds().count("sleep_warning"), 3)  # 00, 01, 02
        points = [e["points"] for e in sim.care.state["recent"] if e["kind"] == "sleep_warning"]
        self.assertEqual(points, [0, -5, -15])  # night.warning_points
        self.assertAlmostEqual(sim.care.state["mood"], 50 - 20 + 2 + 1.9, delta=0.1)  # +2/h back toward 50

    def test_no_warning_or_prompt_while_away_at_night(self):
        sim = Sim(at="23:50", cfg={"break": {"every_minutes": 60}, "water": {"every_minutes": 20}})
        sim.run(99, idle=True)  # away from 23:50 (AFK after afk_minutes) to 01:29
        self.assertNotIn("sleep_warning", sim.kinds())
        self.assertEqual(sim.ui.kinds("prompt"), [])  # no water or break prompt either
        sim.run(1)
        self.assertEqual(sim.kinds().count("sleep_warning"), 1)  # only this hour's (01), once they're back

    def test_nothing_pops_up_during_a_forced_break(self):
        sim = self.night()
        sim.care._start_forced(sim.clock.now(), "test")
        sim.run(5)  # 00:04, still in the break
        self.assertNotIn("sleep_warning", sim.kinds())
        sim.ui.last("forced")[2]["on_done"]()
        sim.run(1)
        self.assertIn("sleep_warning", sim.kinds())

    def test_at_three_she_opens_the_chat_and_asks(self):
        sim = self.night()
        sim.run(3 * 60 + 2)
        self.assertIn("night_asked", sim.kinds())
        self.assertTrue(wait_for(lambda: sim.chats))
        self.assertIn("03:00", sim.chats[0])
        self.assertIn("Neden", sim.chats[0])

    def test_good_reason_stops_the_warnings_tonight(self):
        sim = self.night()
        sim.run(3 * 60 + 2)
        sim.care.box_message("yarın sınavım var")
        self.assertEqual(sim.care.state["night"]["verdict"], "valid")
        warnings = sim.kinds().count("sleep_warning")
        sim.run(120)
        self.assertEqual(sim.kinds().count("sleep_warning"), warnings)
        self.assertIsNone(sim.care.shutdown)
        self.assertIn("accepted their reason", sim.care.prompt_block())

    def test_only_two_good_reasons_a_week(self):
        folder = tempfile.mkdtemp(prefix="care_test_")
        for night in range(3):
            sim = self.night(folder=folder)
            sim.clock.advance(night * 24 * 3600)
            sim.care._last_mono = sim.clock.mono()
            sim.run(3 * 60 + 2)
            sim.care.box_message("deadline var")
            sim.care._save(force=True)
            verdict = sim.care.state["night"]["verdict"]
        self.assertEqual(verdict, "limit")  # Wed, Thu accepted; Fri is the third this week
        self.assertIsNotNone(sim.care.shutdown)

    def test_cant_sleep_never_shuts_down_and_is_gentle(self):
        sim = self.night(classify='{"category": "cant_sleep"}')
        sim.run(3 * 60 + 2)
        sim.care.box_message("uyuyamıyorum")
        mood = sim.mood()
        sim.run(120)
        self.assertIsNone(sim.care.shutdown)
        self.assertGreaterEqual(sim.mood(), mood)  # the hourly warnings go on, without points lost
        self.assertIn("calming", sim.care.prompt_block())

    def test_no_good_reason_starts_the_shutdown(self):
        sim = self.night(mood=90, classify='{"category": "whim"}')  # still "normal" after three warnings
        sim.run(3 * 60 + 2)
        mood = sim.mood()
        sim.care.box_message("canım istedi")
        self.assertIsNotNone(sim.care.shutdown)
        self.assertAlmostEqual(sim.mood(), mood - 30, delta=0.1)  # night_refused
        name, args, _ = sim.ui.last("shutdown_warning")
        self.assertEqual(args[0], 300)

    def test_angry_gets_two_minutes(self):
        sim = self.night(mood=10, classify='{"category": "whim"}')
        sim.run(3 * 60 + 2)
        sim.care.state["mood"] = 10.0
        sim.care.box_message("oyun")
        self.assertEqual(sim.ui.last("shutdown_warning")[1][0], 120)

    def test_no_answer_in_ten_minutes_is_no_good_reason(self):
        sim = self.night()
        sim.run(3 * 60 + 12)
        self.assertEqual(sim.care.state["night"]["verdict"], "invalid")
        self.assertIsNotNone(sim.care.shutdown)

    def test_model_failure_falls_back_to_key_words(self):
        def broken(prompt, what):
            raise RuntimeError("network down")
        sim = Sim(at="23:59", classify=broken, cfg={"break": {"every_minutes": 600}, "water": {"every_minutes": 600}})
        sim.run(3 * 60 + 2)
        sim.care.box_message("yarın vize var")
        self.assertEqual(sim.care.state["night"]["category"], "exam")


class ShutdownTest(unittest.TestCase):
    def start(self, found=()):
        sim = Sim(at="03:10", cfg={"break": {"every_minutes": 600}, "water": {"every_minutes": 600}})
        sim.guard.found = list(found)
        sim.care.start_shutdown(sim.clock.now(), "test")
        return sim

    def test_dry_run_goes_through_every_step_but_never_shuts_down(self):
        sim = self.start()
        real_run = subprocess.run
        ran = []
        subprocess.run = lambda *a, **k: ran.append(a)
        try:
            sim.run(3)
            self.assertFalse(sim.ui.kinds("final_countdown"))
            sim.run(1)
            self.assertTrue(sim.ui.kinds("final_countdown"))
            sim.run(1)
        finally:
            subprocess.run = real_run
        self.assertEqual(ran, [])
        self.assertIn("shutdown_dry", sim.kinds())
        self.assertIsNone(sim.care.shutdown)

    def test_protection_turns_it_into_a_forced_break(self):
        sim = self.start(found=[("program", "claude.exe")])
        self.assertIsNone(sim.care.shutdown)
        self.assertTrue(sim.ui.kinds("forced"))
        self.assertIn("shutdown_protected", sim.kinds())

    def test_protection_checked_again_before_the_end(self):
        sim = self.start()
        sim.run(3)
        sim.guard.found = [("gpu", "GPU 95%, compute: python.exe (PID 1)")]
        sim.run(2)
        self.assertIsNone(sim.care.shutdown)
        self.assertTrue(sim.ui.kinds("forced"))

    def test_cancel_costs_20_and_keeps_the_reason(self):
        sim = self.start()
        self.assertTrue(sim.care.cancel_shutdown("pc", "render bitmedi"))
        self.assertEqual(sim.mood(), 30)
        self.assertEqual(sim.care.state["recent"][-1]["reason"], "render bitmedi")
        self.assertFalse(sim.care.cancel_shutdown("telegram"))

    def test_telegram_cancel_reaches_user_care(self):
        import system_tools

        sim = self.start()
        system_tools.cancel_hooks.append(lambda: sim.care.cancel_shutdown("telegram", "/iptal"))
        real_run = subprocess.run
        subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, 1)
        try:
            self.assertIn("Cancelled", system_tools.cancel_shutdown())
        finally:
            subprocess.run = real_run
            system_tools.cancel_hooks.clear()
        self.assertIsNone(sim.care.shutdown)


class BedtimeAndMorningTest(unittest.TestCase):
    def night_off(self, at, off_hours):
        """Used until `at`+10 min, then the PC was off for off_hours; Zyraena starts again."""
        cfg = {"break": {"every_minutes": 600}, "water": {"every_minutes": 600}}
        sim = Sim(at=at, cfg=cfg)
        sim.run(10)
        sim.care._save(force=True)
        clock = StillClock(sim.clock.now() + timedelta(hours=off_hours))
        again = user_care.Care(sim.cfg, user_care.Store(sim.folder), clock, FakeUi(), FakeGuard(),
                               notify=[].append, chat=sim.chats.append, lang=lambda: "tr")
        again.tick(idle=0, video=False)
        return sim, again

    def test_bed_before_three_gives_20_the_next_day(self):
        sim, again = self.night_off("01:20", 7)
        kinds = [e["kind"] for e in again.state["recent"]]
        self.assertIn("bedtime", kinds)
        self.assertIn("on_time_bed", kinds)
        self.assertEqual(again.state["recent"][kinds.index("on_time_bed")]["points"], 20)

    def test_bed_after_three_gives_nothing(self):
        sim, again = self.night_off("03:40", 6)
        kinds = [e["kind"] for e in again.state["recent"]]
        self.assertIn("bedtime", kinds)
        self.assertNotIn("on_time_bed", kinds)

    def test_morning_summary_of_yesterday(self):
        sim = Sim(at="20:00", cfg={"break": {"every_minutes": 60}, "water": {"every_minutes": 600}})
        sim.run(60)
        sim.answer("snooze")
        sim.run(60)
        _, _, kwargs = sim.ui.last("forced")
        kwargs["on_exit"]("maç vardı")
        sim.run(10)
        sim.care._save(force=True)
        clock = StillClock(sim.clock.now() + timedelta(hours=10))
        chats = []
        again = user_care.Care(sim.cfg, user_care.Store(sim.folder), clock, FakeUi(), FakeGuard(),
                               notify=[].append, chat=chats.append, lang=lambda: "tr")
        again.tick(idle=0, video=False)
        self.assertTrue(wait_for(lambda: chats))
        text = chats[0]
        self.assertIn("Günaydın", text)
        self.assertIn("22:10'da yattın", text)
        self.assertIn("1 ertelendi", text)
        self.assertIn('"maç vardı"', text)


class PromptAndPeaceTest(unittest.TestCase):
    def test_prompt_block_has_mood_and_last_five_events(self):
        sim = Sim(mood=24)
        sim.care.event("snooze", -5, count=1)
        sim.care.event("emergency_exit", 0, reason="rapor teslimi")
        block = sim.care.prompt_block()
        self.assertEqual(block.splitlines()[1], '[mood: 19/100, sinirli, son olaylar: 10:00 zorunlu moladan acil '
                                                'çıkışla çıktı, sebep: "rapor teslimi"; 10:00 molayı erteledi (art '
                                                'arda 1) (-5)]')
        for i in range(8):
            sim.care.event("water")
        line = sim.care.prompt_block().splitlines()[1]
        self.assertEqual(line.count("su içti"), 5)

    def test_late_night_is_worry(self):
        sim = Sim(at="01:30", mood=20)
        self.assertEqual(sim.care.tone(), "worried")
        self.assertIn("worry", sim.care.prompt_block())
        sim = Sim(at="15:00", mood=20)
        self.assertEqual(sim.care.tone(), "angry")

    def test_peace_gives_10_but_not_too_often(self):
        sim = Sim(mood=20)
        self.assertIn("Peace made", sim.care.make_peace("özür dilerim"))
        self.assertEqual(sim.mood(), 30)
        self.assertIn("Not counted", sim.care.make_peace("tekrar özür"))
        sim.run(130)
        self.assertIn("Peace made", sim.care.make_peace("söz"))
        sim.run(130)
        self.assertIn("Not counted", sim.care.make_peace("bir daha"))  # 2 a day


class StateAndConfigTest(unittest.TestCase):
    def test_five_minute_breaks_and_game_points(self):
        b, points = user_care.DEFAULTS["break"], user_care.DEFAULTS["mood"]["points"]
        self.assertEqual((b["normal_minutes"], b["forced_minutes"], b["afk_break_minutes"]), (5, 5, 5))
        self.assertEqual((points["game_hour"], points["game_break"]), (-5, 5))

    def test_rough_default_points(self):
        mood = user_care.DEFAULTS["mood"]
        self.assertEqual(mood["snoozes"], {"happy": 2, "normal": 1, "angry": 0})
        self.assertEqual((mood["points"]["snooze"], mood["points"]["water"], mood["drift_per_hour"]), (-15, 1, 1))
        self.assertEqual((mood["points"]["break"], mood["points"]["night_refused"]), (5, -30))
        self.assertEqual((mood["start"], user_care.DEFAULTS["water"]["every_minutes"]), (25, 20))
        sim = Sim(mood=50, cfg={"mood": user_care.DEFAULTS["mood"], "water": {"every_minutes": 600}})
        sim.run(60)
        sim.answer("snooze")
        self.assertEqual(round(sim.mood()), 34)  # 50, -1 drifting toward 25 in that hour, -15
        sim.care._water_later(sim.clock.now())
        self.assertEqual(round(sim.mood()), 31)

    def test_mood_drifts_back_to_its_start(self):
        sim = Sim(mood=41, cfg={"mood": {"start": 25}, "break": {"every_minutes": 600},
                                "water": {"every_minutes": 600}})
        sim.run(120)
        self.assertEqual(sim.mood(), 37)  # -2 an hour toward 25

    def test_toned_lines_are_one_variant_with_the_name(self):
        sim = Sim(mood=50)
        texts = {sim.care.toned("care_water") for _ in range(40)}
        self.assertEqual(len(texts), 2)  # two variants, one at a time
        self.assertTrue(all("\n" not in t and user_care.i18n.user_name() in t for t in texts))
        sim.care.state["mood"] = 20.0
        self.assertNotIn("{", sim.care.toned("care_break_prompt", minutes=60))

    def test_state_survives_a_restart(self):
        sim = Sim(mood=50)
        sim.run(60)
        sim.answer("snooze")
        sim.run(20)
        sim.care._save(force=True)
        again = user_care.Care(sim.cfg, user_care.Store(sim.folder), sim.clock, FakeUi(), FakeGuard(),
                               lang=lambda: "tr")
        self.assertEqual(again.state["snoozes"], 1)
        self.assertAlmostEqual(again.state["mood"], 45 + 2 * 20 / 60, delta=0.05)
        self.assertAlmostEqual(again.state["cycle"], 20 * 60, delta=STEP)

    def test_config_gets_every_key_and_keeps_the_alarms(self):
        folder = Path(tempfile.mkdtemp(prefix="care_cfg_"))
        path = folder / "config.json"
        path.write_text(json.dumps({"events": [{"name": "x"}], "user_care": {"break": {"every_minutes": 45}}}),
                        encoding="utf-8")
        import reminder_tools  # noqa: F401  (save_config takes its lock)

        cfg = user_care.load_config(path)
        self.assertEqual(cfg["break"]["every_minutes"], 45)
        self.assertEqual(cfg["break"]["answer_minutes"], 5)
        self.assertTrue(cfg["dry_run"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["events"], [{"name": "x"}])
        self.assertEqual(saved["user_care"]["protect"]["programs"][0], "claude.exe")

    def test_a_debug_run_never_writes_debug_on(self):
        folder = Path(tempfile.mkdtemp(prefix="care_cfg_"))
        path = folder / "config.json"
        path.write_text(json.dumps({"events": []}), encoding="utf-8")
        cfg = user_care.load_config(path)
        cfg["debug"] = dict(cfg["debug"], enabled=True)
        user_care.save_config(cfg, path)
        self.assertFalse(json.loads(path.read_text(encoding="utf-8"))["user_care"]["debug"]["enabled"])


class TextTest(unittest.TestCase):
    def test_turkish_and_english_have_the_same_care_keys(self):
        en = {k for k in i18n.STRINGS["en"] if k.startswith("care_")}
        tr = {k for k in i18n.STRINGS["tr"] if k.startswith("care_")}
        self.assertEqual(en, tr)

    def test_every_mood_has_its_texts(self):
        for key in ("care_break_prompt", "care_forced_text", "care_break_over", "care_water", "care_sleep_warning",
                    "care_night_question", "care_shutdown_warning"):
            for tone in user_care.TONES:
                self.assertIn(f"{key}_{tone}", i18n.STRINGS["tr"])

    def test_every_event_has_a_description(self):
        sim = Sim()
        for kind in ("break_taken", "break_done", "break_back_early", "snooze", "unanswered", "forced_warning",
                     "forced_start", "forced_done", "emergency_exit", "afk_break", "sleep", "water", "water_later",
                     "sleep_warning", "night_asked", "night_reason", "shutdown_warning", "shutdown_protected",
                     "shutdown_dry", "shutdown", "shutdown_cancel", "bedtime", "on_time_bed", "peace",
                     "morning_summary"):
            entry = sim.care.event(kind, minutes=3, count=1, hour="01:00", time="01:00", category="exam",
                                   verdict="valid", why="x", source="pc", of="2026-10-20")
            self.assertNotEqual(sim.care.describe(entry), kind)
            self.assertNotIn("{", sim.care.describe(entry))


class GuardTest(unittest.TestCase):
    def cfg(self, **changes):
        cfg = user_care.merged(user_care.DEFAULTS["protect"], changes)
        for rule in ("gpu", "terminal_jobs", "busy_cpu", "downloads"):
            cfg[rule]["enabled"] = False
        return cfg

    def test_a_listed_program_protects(self):
        import psutil

        me = psutil.Process().name()
        off = {"enabled": False}
        found = care_guard.Guard().reasons(self.cfg(programs=[me.upper()], training=off))
        self.assertIn(("program", me), found)
        self.assertEqual(care_guard.Guard().reasons(self.cfg(programs=["nothing_like_this.exe"], training=off)), [])

    def test_a_training_script_protects_but_her_own_workers_dont(self):
        marker = "zyraena_care_test_training"
        code = "import time; time.sleep(8)"
        training = subprocess.Popen([sys.executable, "-c", code, marker])
        worker = subprocess.Popen([sys.executable, "-c", code, "tts_worker", "zyraena_care_test_worker"])
        try:
            time.sleep(0.5)
            cfg = self.cfg(programs=[], training={"enabled": True,
                                                  "patterns": [marker, "zyraena_care_test_worker"]})
            found = care_guard.Guard(own_pid=1).reasons(cfg)
            self.assertEqual([what.split(" ")[0] for rule, what in found if rule == "training"], [marker])
        finally:
            for proc in (training, worker):
                proc.kill()
                proc.wait()

    def test_zyraena_runs(self):
        found = care_guard.Guard(runs=lambda: 1).reasons(self.cfg(programs=[], training={"enabled": False}))
        self.assertIn(("zyraena_runs", "1"), found)

    def test_growing_download(self):
        folder = Path(tempfile.mkdtemp(prefix="care_dl_"))
        cfg = self.cfg(programs=[], training={"enabled": False})
        cfg["downloads"].update(enabled=True, folder=str(folder), mb_per_second=10 ** 6)
        self.assertEqual(care_guard.Guard().reasons(cfg), [])
        (folder / "film.mkv.opdownload").write_bytes(b"x")
        self.assertIn(("downloads", "film.mkv.opdownload"), care_guard.Guard().reasons(cfg))

    def test_terminal_job_needs_minutes_of_cpu(self):
        guard = care_guard.Guard(own_pid=1)
        cfg = self.cfg(programs=[])
        cfg["terminal_jobs"].update(enabled=True, minutes=0)
        busy = subprocess.Popen(["cmd", "/c", sys.executable, "-c", "while True: pass"],
                                creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            import psutil

            end = time.time() + 10
            while time.time() < end and not any(c.name().lower().startswith("python")
                                                for c in psutil.Process(busy.pid).children()):
                time.sleep(0.1)  # cmd starts conhost first, its Python child a moment later
            guard.sample(cfg)
            time.sleep(1.5)
            guard.sample(cfg)
            found = guard.reasons(cfg)
            self.assertTrue(any(rule == "terminal_jobs" for rule, _ in found), found)
            cfg["terminal_jobs"]["minutes"] = 3
            self.assertFalse(any(rule == "terminal_jobs" for rule, _ in guard.reasons(cfg)))
        finally:
            import psutil
            for child in psutil.Process(busy.pid).children(recursive=True):
                child.kill()
            busy.kill()
            busy.wait()


try:
    import tkinter as tk

    _probe = tk.Tk()
    _probe.destroy()
    import care_windows  # noqa: E402
    import chat_box  # noqa: E402
    TK_ERROR = None
except Exception as e:  # broken Tcl/Tk (the project's Python 3.11)
    TK_ERROR = e
    care_windows = None


class WindowsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if care_windows is None:
            raise unittest.SkipTest(f"no Tcl/Tk: {TK_ERROR}")

    def on_ui(self, fn):
        box, done = {}, threading.Event()
        chat_box.post(lambda: (box.setdefault("v", fn()), done.set()))
        self.assertTrue(done.wait(5))
        return box["v"]

    def test_prompt_answers_and_forced_break_covers_every_monitor(self):
        ui = care_windows.Windows(lambda: "tr")
        answers = []
        ui.prompt("break", "Mola", "metin", [("Mola ver", "break"), ("Ertele", "snooze")], answers.append)
        self.assertTrue(self.on_ui(lambda: "break" in ui.open))
        panel = ui.open["break"]
        buttons = self.on_ui(lambda: [w for w in panel.buttons.winfo_children() if isinstance(w, tk.Button)])
        self.on_ui(lambda: next(b for b in buttons if b.cget("text") == "Ertele").invoke())
        self.assertEqual(answers, ["snooze"])
        self.assertNotIn("break", ui.open)

        exits = []
        ui.forced(30, "Zorunlu mola", "metin", lambda: None, exits.append)
        self.assertTrue(self.on_ui(lambda: "forced" in ui.open))
        screen = ui.open["forced"]
        self.assertEqual(len(screen.wins), len(care_windows.monitors()))
        ui.close("forced")
        self.assertTrue(self.on_ui(lambda: "forced" not in ui.open and screen.closed))


if __name__ == "__main__":
    unittest.main()
