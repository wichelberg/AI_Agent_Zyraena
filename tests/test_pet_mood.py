"""The pet's moods (User Care) without windows: the mood's stance, talk and throne loops, the way between
poses (_bridge) so nothing jumps, falling back when frames are missing, impatience after a snoozed break,
pastime odds by mood.

Run from the project folder: py -3 -m unittest tests.test_pet_mood
"""
import os
import sys
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import test_pet_motion as motion  # noqa: E402
from test_pet_motion import desktop_pet  # noqa: E402

MOOD_COUNTS = {"angry_in": 20, "angry_idle": 50, "angry_talkin": 10, "angry_talk": 30, "angry_sitdown": 20,
               "angry_sit": 50, "normal_in": 20, "normal_idle": 50, "normal_talk": 30, "normal_sitdown": 20,
               "normal_sit": 50, "worried_in": 14, "worried": 40, "impatientin": 14, "impatient": 40,
               "watchin": 14, "watch": 50, "talk": 30}
ANGRY_SHIFT = 12.0


def make_pet(x=100.0, direction=1, without=()):
    pet = motion.make_pet(x, direction)
    for name, n in MOOD_COUNTS.items():
        if name not in without:
            pet.anims[name] = {1: [(name, i) for i in range(n)], -1: [(name, -i) for i in range(n)]}
    pet.tracks["angry_in"] = motion._track(ANGRY_SHIFT, 20)
    pet.pingpong |= {"angry_idle", "angry_sit", "normal_idle", "normal_sit", "worried"}
    pet.logged, pet.hidden, pet.language = {}, False, lambda: "tr"
    pet.say = mock.Mock()
    return pet


def queued(pet):
    """The queue as [(animation, first frame, last frame)]."""
    return [(anim, indexes[0], indexes[-1]) for anim, _, indexes, _ in pet.queue]


def run_queue(pet):
    shown = []
    while pet.queue:
        shown.append(pet._next_frame())
    return shown


class PetMoodTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(desktop_pet, "_work_area", lambda: (0, 0, 3000, 1000))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_happy_or_no_user_care_keeps_the_plain_animations(self):
        pet = make_pet()
        pet._set_state("idle", (10, 10), "idle", 1)
        pet._set_state("sit", (10, 10), "sit", 1)
        self.assertEqual(pet.anim, "sit")
        self.assertEqual(queued(pet), [("sitdown", 1, 19)])
        with mock.patch.dict(sys.modules, {"user_care": mock.Mock(service=lambda: None)}):
            self.assertEqual(pet._read_mood(), (None, None))

    def test_a_mood_change_while_standing_plays_into_the_stance_and_back(self):
        pet = make_pet()
        pet._set_state("idle", (30, 30), "idle", 1)
        pet.mood = "angry"
        pet._settle_mood()
        self.assertEqual((pet.state, pet.anim), ("idle", "angry_idle"))
        self.assertEqual(queued(pet), [("angry_in", 1, 19)])
        x0 = pet.x
        run_queue(pet)
        self.assertAlmostEqual(pet.x - x0, ANGRY_SHIFT)  # tracked: the planted boot stays put
        pet.mood = None
        pet._settle_mood()
        self.assertEqual(pet.anim, "idle")
        self.assertEqual(queued(pet), [("angry_in", 18, 0)])
        run_queue(pet)
        self.assertAlmostEqual(pet.x, x0)

    def test_a_mood_change_on_the_throne_gets_up_and_sits_down_the_new_way(self):
        pet = make_pet()
        pet._set_state("sit", (30, 30), "sit", 1)
        pet.queue.clear()
        pet.mood = "angry"
        pet._settle_mood()
        self.assertEqual((pet.state, pet.anim), ("sit", "angry_sit"))
        self.assertEqual(queued(pet), [("sitdown", 18, 0), ("angry_sitdown", 1, 19)])

    def test_no_change_in_the_middle_of_something(self):
        pet = make_pet()
        pet._set_state("idle", (30, 30), "idle", 1)
        pet._play("watchin", 1, range(1, 14), shown=0)
        pet.mood = "angry"
        pet._settle_mood()  # frames still queued: later
        self.assertEqual(pet.anim, "idle")
        pet.queue.clear()
        pet.state_ticks = 10  # about to move on anyway
        pet._settle_mood()
        self.assertEqual(pet.anim, "idle")

    def test_leaving_the_stance_comes_first(self):
        pet = make_pet()
        pet.mood = "angry"
        pet._set_state("idle", (30, 30), "idle", 1)
        pet.queue.clear()
        pet._start_walk("walk", (5, 5))
        names = [anim for anim, *_ in queued(pet)]
        self.assertEqual(names[0], "angry_in")
        self.assertIn(names[1], desktop_pet.TURNS)
        self.assertEqual(queued(pet)[0][1:], (18, 0))
        pet.queue.clear()
        pet.pose = "angry"
        pet._take_pose("watch", 1)
        self.assertEqual(queued(pet), [("angry_in", 18, 0), ("watchin", 1, 13)])

    def test_sitting_down_from_the_stance_goes_through_standing(self):
        pet = make_pet()
        pet.mood = "angry"
        pet._set_state("idle", (30, 30), "idle", 1)
        pet.queue.clear()
        pet._set_state("sit", (30, 30), "sit", 1)
        self.assertEqual(queued(pet), [("angry_in", 18, 0), ("angry_sitdown", 1, 19)])
        pet.queue.clear()
        pet._get_up()
        self.assertEqual(queued(pet), [("angry_sitdown", 18, 0)])
        self.assertEqual(pet.pose, "stand")

    def test_angry_talk_raises_the_hand_and_finishes_its_loop_before_lowering_it(self):
        pet = make_pet()
        pet.mood = "angry"
        pet._set_state("idle", (30, 30), "idle", 1)
        pet.queue.clear()
        pet._set_state("talk", (6, 6), "talk", 1)
        self.assertEqual(pet.anim, "angry_talk")
        self.assertEqual(queued(pet), [("angry_talkin", 1, 9)])
        pet.queue.clear()
        for _ in range(25):  # into the loop
            pet._next_frame()
        at = pet.index % 30
        pet._set_state("idle", (30, 30), "idle", 1)
        self.assertEqual(queued(pet), [("angry_talk", at + 1, 29), ("angry_talkin", 8, 0)])
        self.assertEqual(pet.anim, "angry_idle")

    def test_missing_frames_fall_back(self):
        pet = make_pet(without=("worried_in", "worried"))
        pet.mood = "worried"
        self.assertEqual(pet._moody("idle"), "normal_idle")
        self.assertEqual(pet._moody("sit"), "normal_sit")
        pet = make_pet(without=("worried_in", "normal_in", "angry_sitdown"))
        pet.mood = "worried"
        self.assertEqual(pet._moody("idle"), "idle")  # normal_idle has no way in without normal_in
        pet.mood = "angry"
        self.assertEqual(pet._moody("sit"), "sit")
        self.assertEqual(pet._moody("idle"), "angry_idle")
        pet.mood = "worried"
        pet2 = make_pet()
        pet2.mood = "worried"
        self.assertEqual((pet2._moody("idle"), pet2._moody("talk"), pet2._moody("sit")),
                         ("worried", "worried", "normal_sit"))

    def test_a_snoozed_break_makes_her_impatient_once(self):
        pet = make_pet()
        pet._set_state("sit", (30, 30), "sit", 1)
        pet.queue.clear()
        now = datetime.now().isoformat(timespec="seconds")
        with mock.patch.object(pet, "_read_mood", return_value=("normal", now)):
            pet._check_mood()
        self.assertEqual(pet.state, "impatient")
        self.assertEqual(queued(pet), [("sitdown", 18, 0), ("impatientin", 1, 13)])
        pet.say.assert_called_once()
        pet.queue.clear()
        pet._set_state("idle", (30, 30), "idle", 1)
        with mock.patch.object(pet, "_read_mood", return_value=("normal", now)):
            pet._check_mood()  # the same break again: nothing
        self.assertNotEqual(pet.state, "impatient")

    def test_an_old_snooze_or_a_walk_waits(self):
        pet = make_pet()
        pet._set_state("idle", (30, 30), "idle", 1)
        with mock.patch.object(pet, "_read_mood", return_value=(None, "2020-01-01T10:00:00")):
            pet._check_mood()
        self.assertEqual(pet.state, "idle")
        now = datetime.now().isoformat(timespec="seconds")
        pet._set_state("walk", (5, 5), "walk", 1)
        with mock.patch.object(pet, "_read_mood", return_value=(None, now)):
            pet._check_mood()
            self.assertEqual(pet.state, "walk")
            pet._set_state("idle", (30, 30), "idle", 1)
            pet._check_mood()
        self.assertEqual(pet.state, "impatient")

    def test_pastime_odds_follow_the_mood(self):
        pet = make_pet()
        pet.context = "desktop"
        happy = pet._pastimes()
        pet.mood = "angry"
        angry = pet._pastimes()
        self.assertGreater(angry["dagger"], happy["dagger"])
        self.assertGreater(angry["lift"], happy["lift"])
        self.assertLess(angry["stretch"], happy["stretch"])
        self.assertLessEqual(sum(angry.values()), 0.9 + 1e-9)

    def test_her_lines_follow_the_mood_and_never_say_little_one(self):
        pet = make_pet()
        seen = {}
        for mood in (None, "normal", "angry", "worried"):
            pet.mood = mood
            for kind in (None, "code", "watch", "lift", "dagger", "stretch", "impatient"):
                lines = pet._lines(kind)
                self.assertGreaterEqual(len(lines), 6, (mood, kind))
                self.assertFalse([line for line in lines if "{" in line or "küçük olan" in line], (mood, kind))
                seen[mood, kind] = lines
        self.assertNotEqual(seen[None, None], seen["angry", None])
        self.assertEqual(seen["worried", "code"], seen["normal", "code"])  # no worried code lines: normal's
        self.assertTrue(all(desktop_pet.i18n.user_name() in line for line in seen["normal", "code"]))

    def test_dragged_and_dropped_she_lands_in_her_mood_without_a_way_in(self):
        pet = make_pet()
        pet.mood = "angry"
        pet._set_state("idle", (30, 30), "idle", 1)
        pet.queue.clear()
        pet._clear_queue()
        pet._set_state("drag", (1, 1), "drag", 1)
        pet._set_state("fall", (1, 1), "drag", 1)
        pet._set_state("idle", (30, 30), "idle", 1)
        self.assertEqual((pet.anim, pet.queue), ("angry_idle", []))


if __name__ == "__main__":
    unittest.main()
