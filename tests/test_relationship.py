"""relationship + User Care's affection and drop-in: the affection limits, the nine relationship styles in
her prompt, when she comes by on her own, the memory store (never-forget memories, notes, the backup copy)
and the look back at a finished conversation. Fake clock, fake models, temporary folders: no network, no
window, config.json is not touched.
Run from the project folder: python -m unittest tests.test_relationship
"""
import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import i18n  # noqa: E402
import relationship  # noqa: E402
import user_care  # noqa: E402
from test_user_care import Sim, wait_for  # noqa: E402

QUIET = {"break": {"every_minutes": 600}, "water": {"every_minutes": 600}}


class AffectionTest(unittest.TestCase):
    def test_limits_per_chat_and_per_day(self):
        sim = Sim(cfg=QUIET)
        self.assertEqual(sim.care.state["affection"], 50)
        self.assertEqual(sim.care.add_affection(9, "çok tatlıydı"), 5)  # max_per_chat
        self.assertEqual(sim.care.add_affection(5), 3)                  # up_per_day 8
        self.assertEqual(sim.care.add_affection(2), 0)
        self.assertEqual(sim.care.add_affection(-20, "hakaret"), -5)
        self.assertEqual(round(sim.care.state["affection"]), 53)
        sim.run(24 * 60)
        self.assertEqual(sim.care.add_affection(4), 4)                  # a new day
        self.assertEqual(round(sim.care.state["affection"]), 57)        # and no drift in between
        self.assertIn("affection", sim.kinds())

    def test_levels_pick_the_relationship_style(self):
        sim = Sim(mood=80, cfg=QUIET)
        sim.care.state["affection"] = 75.0
        self.assertEqual(sim.care.relation(), "happy_high")
        block = sim.care.prompt_block()
        self.assertIn("[affection: 75/100, seviyor · anaç, sevgi dolu, sahiplenici]", block)
        self.assertIn(i18n.RELATION_STYLES["happy_high"], block)
        sim.care.state.update(mood=20.0, affection=30.0)  # 30 and below is low, like the mood
        self.assertEqual(sim.care.relation(), "angry_low")
        sim.care.state.update(mood=50.0, affection=69.0)
        self.assertEqual(sim.care.relation(), "normal_normal")
        for key in i18n.RELATION_STYLES:
            self.assertNotEqual(i18n.get("tr", "care_rel_" + key), "care_rel_" + key)

    def test_mood_line_stays_second(self):
        sim = Sim(mood=24, cfg=QUIET)
        self.assertTrue(sim.care.prompt_block().splitlines()[1].startswith("[mood: 24/100"))


class DropInTest(unittest.TestCase):
    def sim(self, answer="*başını eğer* Yine mi kod?", seen=("code.exe", "user_care.py - VS Code"), **drop):
        sim = Sim(cfg=dict(QUIET, drop_in=dict({"chance": 1.0}, **drop)))
        sim.asked, sim.said = [], []
        sim.care.persona = lambda instruction, what: sim.asked.append(instruction) or answer
        sim.care.screen = lambda: seen
        sim.care.drop_in_say = sim.said.append
        return sim

    def test_comes_by_once_then_waits(self):
        sim = self.sim()  # checks at 10:01, 10:11, 10:21... (the first tick had no persona yet)
        sim.run(11)
        self.assertEqual(sim.asked, [])  # not before active_minutes
        sim.run(10)
        self.assertTrue(wait_for(lambda: sim.said))
        self.assertIn("user_care.py - VS Code", sim.asked[0])
        self.assertIn("drop_in", sim.kinds())
        sim.run(100)
        self.assertEqual(len(sim.asked), 1)  # min_gap_minutes 120
        sim.run(30)
        self.assertTrue(wait_for(lambda: len(sim.said) == 2))

    def test_daily_limit_follows_affection(self):
        sim = self.sim(min_gap_minutes=0)
        sim.care.state["affection"] = 10.0  # low: once a day
        sim.run(120)
        self.assertTrue(wait_for(lambda: sim.said))
        sim.run(120)
        self.assertEqual(len(sim.asked), 1)

    def test_skip_is_counted_but_not_shown(self):
        sim = self.sim(answer="SKIP")
        sim.run(21)
        self.assertTrue(wait_for(lambda: sim.asked))
        sim.run(1)
        self.assertEqual(sim.said, [])
        self.assertEqual(sim.care.state["drop_in"]["count"], 1)

    def test_no_call_when_she_cannot_come(self):
        for sim in (self.sim(seen=None), self.sim(enabled=False), self.sim(seen=("KeePass.exe", "Kasa"))):
            sim.run(60)
            self.assertEqual(sim.asked, [])
            self.assertEqual(sim.care.state["drop_in"], {})
        sim = self.sim()
        sim.care.note_chat()  # they just talked
        sim.run(25)
        self.assertEqual(sim.asked, [])
        night = Sim(at="00:30", cfg=dict(QUIET, drop_in={"chance": 1.0}))
        night.care.persona, night.care.screen = (lambda *a: "x"), (lambda: ("code.exe", "x"))
        night.run(60)
        self.assertNotIn("drop_in", night.kinds())


class MemoryStoreTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="memory_test_"))
        relationship.configure(path=self.folder / "memory.json", user="Wichelberg")

    def tearDown(self):
        relationship._state["path"] = None

    def test_core_memories_dedupe_and_delete(self):
        self.assertEqual(relationship.prompt_block(), "")
        first = relationship.add_core("Wichelberg ona yol arkadaşım dedi.", "box")
        self.assertIsNotNone(first)
        self.assertIsNone(relationship.add_core("wichelberg ona YOL ARKADAŞIM dedi"))
        relationship.add_core("Annesinin adı Ayşe.")
        block = relationship.prompt_block()
        self.assertIn("Never forget:", block)
        self.assertIn("yol arkadaşım dedi.", block)
        self.assertTrue(relationship.remove_core(first["id"]))
        self.assertFalse(relationship.remove_core(first["id"]))
        self.assertEqual([m["text"] for m in relationship.load()["core"]], ["Annesinin adı Ayşe."])

    def test_notes_are_capped_but_core_never(self):
        for i in range(relationship.NOTES_KEPT + 5):
            relationship.add_note(f"not {i}")
            relationship.add_core(f"anı {i}")
        data = relationship.load()
        self.assertEqual(len(data["notes"]), relationship.NOTES_KEPT)
        self.assertEqual(len(data["core"]), relationship.NOTES_KEPT + 5)
        self.assertEqual(relationship.prompt_block().count("- ("),
                         relationship.NOTES_KEPT + 5 + relationship.NOTES_IN_PROMPT)

    def test_a_broken_file_falls_back_to_the_copy(self):
        relationship.add_core("ilk")
        relationship.add_core("ikinci")  # the copy now has "ilk"
        (self.folder / "memory.json").write_text("{bozuk", encoding="utf-8")
        self.assertEqual([m["text"] for m in relationship.load()["core"]], ["ilk"])
        relationship.add_note("yeni")  # saving over the broken file keeps the good copy
        self.assertEqual(json.loads((self.folder / "memory.json.bak").read_text(encoding="utf-8"))["core"][0]["text"],
                         "ilk")


class LookBackTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="memory_test_"))
        self.sim = Sim(cfg=QUIET)
        user_care._state["care"] = self.sim.care
        self.prompts = []
        self.answer = json.dumps({"affection": 4, "reason": "ona yol arkadaşı dedi",
                                  "note": "Wichelberg Week 2 notlarına çalıştı.",
                                  "core": ["Wichelberg Zyraena'ya 'yol arkadaşım' dedi."]})
        relationship.configure(path=self.folder / "memory.json", user="Wichelberg", lang=lambda: "tr",
                               classify=lambda prompt, what: self.prompts.append(prompt) or self.answer)

    def tearDown(self):
        user_care._state["care"] = None
        relationship._state.update(path=None, classify=None)

    def test_transcript_keeps_only_what_was_said(self):
        lines = relationship.transcript([
            {"role": "user", "content": "[Zyraena opened the chat herself.]"},
            {"role": "assistant", "content": "Günaydın."},
            {"role": "user", "content": "Selam" + "\n\n[This message was spoken; your reply will be read aloud. "
                                                  "Keep it short.]"},
            {"role": "assistant", "content": "", "tool_calls": [{}]},
            {"role": "tool", "content": "ok"},
            {"role": "user", "content": [{"type": "text", "text": "[Screenshot]"}]},
        ])
        self.assertEqual(lines, [("assistant", "Günaydın."), ("user", "Selam")])

    def test_short_chats_cost_nothing(self):
        self.assertFalse(relationship.chat_ended({"messages": [{"role": "user", "content": "saat kaç"}]}, "box"))
        self.assertFalse(relationship.chat_ended(None, "box"))
        self.assertEqual(self.prompts, [])

    def test_look_back_applies_everything_once(self):
        lines = [("user", "Sen benim yol arkadaşımsın, sana güvenim tam."), ("assistant", "Senin yanındayım.")]
        result = relationship.look_back(lines, "box")
        self.assertEqual(result["counted"], 4)
        self.assertEqual(round(self.sim.care.state["affection"]), 54)
        self.assertIn("Her affection now: 50/100 (normal)", self.prompts[0])
        self.assertIn("Wichelberg: Sen benim yol arkadaşımsın", self.prompts[0])
        data = relationship.load()
        self.assertEqual(data["notes"][0]["text"], "Wichelberg Week 2 notlarına çalıştı.")
        self.assertEqual(len(data["core"]), 1)
        self.assertIn("core_memory", self.sim.kinds())
        relationship.look_back(lines, "box")  # the same memory again is not added twice
        self.assertEqual(len(relationship.load()["core"]), 1)
        self.assertIn("'yol arkadaşım' dedi.", self.prompts[1])  # it's shown as already known

    def test_chat_ended_runs_on_its_own_thread(self):
        chat = {"messages": [{"role": "user", "content": "Bugün sınavım iyi geçti, sayende çalıştım."},
                             {"role": "assistant", "content": "Aferin."}]}
        self.assertTrue(relationship.chat_ended(chat, "telegram"))
        self.assertTrue(wait_for(lambda: relationship.load()["notes"]))
        self.assertIsNotNone(self.sim.care.state["last_chat"])

    def test_parse_cleans_the_answer(self):
        self.assertEqual(relationship.parse("bilmem"), {"affection": 0, "reason": "", "note": "", "core": []})
        got = relationship.parse('```json\n{"affection": 9, "core": "tek anı", "note": null}\n```')
        self.assertEqual((got["affection"], got["core"], got["note"]), (5, ["tek anı"], ""))

    def test_remember_forever_tool(self):
        self.assertIn("Saved", relationship.remember_forever("Doğum günü 3 Mart."))
        self.assertIn("Already", relationship.remember_forever("doğum günü 3 mart"))
        self.assertIn("Nothing", relationship.remember_forever("  "))


if __name__ == "__main__":
    unittest.main()
