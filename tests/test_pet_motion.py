"""The pet's motion logic without windows: stopping on a quarter of the walk, arriving exactly where she
must stand, tracked transitions and ping-pong loops.

Run from the project folder: py -3 -m unittest tests.test_pet_motion
"""
import os
import sys
import unittest
from collections import deque
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import desktop_pet  # noqa: E402

N = 60          # walk frames
SPEED = 4.0     # window px per walk frame
TURN_SHIFT = {"turn": 6.0, "turn1": -3.0, "turn2": 9.0, "turn3": 2.0}
LEAN_SHIFT = -14.0
CODE_SHIFT = 5.0


def _track(total, frames):
    return [total * i / (frames - 1) for i in range(frames)]


def make_pet(x=100.0, direction=1):
    pet = desktop_pet.Pet.__new__(desktop_pet.Pet)
    counts = {"walk": N, "idle": 50, "sit": 50, "sitdown": 20, "lean": 50, "leanin": 30, "code": 60,
              "codein": 20, **{turn: 40 for turn in desktop_pet.TURNS}}
    pet.anims = {name: {1: [(name, i) for i in range(n)], -1: [(name, -i) for i in range(n)]}
                 for name, n in counts.items()}
    pet.tracks = {**{turn: _track(total, 40) for turn, total in TURN_SHIFT.items()},
                  "leanin": _track(LEAN_SHIFT, 30), "codein": _track(CODE_SHIFT, 20)}
    pet.pingpong = {"idle", "sit", "lean"}
    pet.speed = SPEED
    pet.walk_step = SPEED
    pet.x, pet.y, pet.dir, pet.facing = x, 0.0, direction, direction
    pet.queue, pet.held, pet.snap_x, pet.index = [], 0, None, 0
    pet.history, pet.context, pet.game, pet.edge = deque(maxlen=5), "desktop", None, 1
    pet.state, pet.anim, pet.state_ticks = "idle", "idle", 100
    pet.bubble, pet.then = None, None
    pet.w, pet.h = 100, 300
    return pet


def tick(pet):
    pet._step()
    return pet._next_frame()


class PetMotionTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(desktop_pet, "_work_area", lambda: (0, 0, 3000, 1000))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_walks_to_the_throne_and_sits_exactly_there(self):
        for start, target in ((100.0, 1500.0), (100.0, 900.0), (500.0, 830.0), (1400.0, 200.0)):
            with self.subTest(start=start, target=target):
                pet = make_pet(start, 1 if target > start else -1)
                pet._throne_x = lambda target=target: target
                pet._start_walk("to_throne", (600, 600))
                steps = []
                for _ in range(5000):
                    before, shown = pet.x, pet.queue[0][0] if pet.queue else pet.anim
                    tick(pet)
                    if shown == "walk" and pet.x != before:
                        steps.append(abs(pet.x - before))
                    if pet.state == "sit" and not pet.queue:
                        break
                self.assertAlmostEqual(pet.x, target, delta=0.01)
                self.assertGreaterEqual(min(steps), SPEED * desktop_pet.STRIDE_LIMITS[0] - 1e-6)
                self.assertLessEqual(max(steps), SPEED * desktop_pet.STRIDE_LIMITS[1] + 1e-6)

    def test_walks_to_the_edge_and_leans_exactly_there(self):
        pet = make_pet(300.0, 1)
        pet.game = (0, 0, 3000, 1000)
        pet.extents = {"lean": (10, 90)}
        pet.w = 100
        target = pet._edge_x()
        pet._start_walk("to_edge", (600, 600))
        for _ in range(5000):
            tick(pet)
            if pet.state == "lean" and not pet.queue:
                break
        self.assertEqual(pet.state, "lean")
        self.assertAlmostEqual(pet.x, target, delta=0.01)

    def test_stopping_goes_on_to_a_quarter_and_plays_its_turn_without_a_jump(self):
        for now in range(N):
            with self.subTest(now=now):
                pet = make_pet()
                pet.state, pet.anim, pet.index = "walk", "walk", now
                pet._stop_and_face()
                walk = pet.queue[0][2] if pet.queue[0][0] == "walk" else []
                turn_entry = pet.queue[-1]
                landing = walk[-1] if walk else now
                self.assertEqual(landing % (N // 4), 0)  # the turn starts from the walk frame it was rendered from
                self.assertEqual(turn_entry[0], desktop_pet.TURNS[landing // (N // 4)])
                self.assertEqual((turn_entry[2][0], turn_entry[3]), (1, 0))
                self.assertEqual(walk, [(now + j) % N for j in range(1, len(walk) + 1)])
                self.assertLess(len(walk), N // 4)

    def test_starting_to_walk_continues_from_the_turns_first_frame(self):
        pet = make_pet()
        pet._start_walk("walk", (5, 5))
        start = desktop_pet.TURNS.index(pet.queue[0][0]) * (N // 4)
        while pet.queue:
            tick(pet)
        self.assertEqual(tick(pet), ("walk", start))

    def test_tracked_transition_moves_the_window_by_its_track_and_back(self):
        pet = make_pet(500.0)
        pet._take_pose("code", 1)
        while pet.queue:
            pet._next_frame()
        self.assertAlmostEqual(pet.x, 500.0 + CODE_SHIFT)
        pet.state = "code"
        pet._leave_pose()
        while pet.queue:
            pet._next_frame()
        self.assertAlmostEqual(pet.x, 500.0)

    def test_mirrored_transitions_move_the_other_way(self):
        pet = make_pet(500.0, -1)
        pet._take_pose("code", -1)
        while pet.queue:
            pet._next_frame()
        self.assertAlmostEqual(pet.x, 500.0 - CODE_SHIFT)

    def test_pingpong_loops_go_forward_and_back(self):
        pet = make_pet()
        pet.anim, pet.facing, pet.index = "idle", 1, 0
        shown = [pet._next_frame()[1] for _ in range(2 * 2 * 49)]  # two ticks a frame, one whole cycle
        frames = shown[1::2]
        self.assertEqual(frames[:49], list(range(1, 50)))
        self.assertEqual(frames[49:97], list(range(48, 0, -1)))
        self.assertEqual(frames[97], 0)


if __name__ == "__main__":
    unittest.main()
