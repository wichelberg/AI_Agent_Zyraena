"""disk_memory and disk_watch: the knowledge is asked before Gemini (and Gemini gets no paths or file
contents), the scan history, and the findings the daily scan tells. Gemini is a fake; files go to a
temporary folder.
Run from the project folder: python -m unittest discover -s tests
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_memory  # noqa: E402
import disk_watch  # noqa: E402
from disk_tools import Item, Scan  # noqa: E402

GB = 1024 ** 3


class FakeGemini:
    def __init__(self, answers):
        self.answers, self.prompts = answers, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return "```json\n" + json.dumps(self.answers) + "\n```"


class KnowledgeTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="zyraena_knowledge_test_"))
        self.app = self.folder / "Users" / "me" / "AppData" / "Local" / "Acme"
        (self.app / "data").mkdir(parents=True)
        (self.app / "acme.exe").write_bytes(b"x")
        (self.app / "secret_notes.txt").write_text("PRIVATE CONTENT", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def items(self):
        return [
            Item("program:a", "program", "Known App", key="program:known app|a co", info={"publisher": "A Co"}),
            Item("program:b", "program", "Owner App", key="program:owner app|b co", info={"publisher": "B Co"}),
            Item("path:acme", "folder", "~\\AppData\\Local\\Acme", str(self.app), key="folder:~\\appdata\\local\\acme"),
            Item("program:c", "program", "New App", key="program:new app|c co", info={"publisher": "C Co"}),
            Item("venv:x", "venv", "p\\.venv", key="venv:p\\.venv", what="Python 3.11 ortamı", what_source="rule"),
            Item("path:own", "own", "Downloads", key="own:downloads"),
        ]

    def test_memory_first_then_gemini_once(self):
        knowledge = disk_memory.Knowledge(self.folder / "knowledge.json")
        knowledge.put("program:known app|a co", "Bilinen uygulama", "gemini", "Known App", True)
        knowledge.put("program:owner app|b co", "Benim notum", "owner", "Owner App", False)
        gemini = FakeGemini([{"id": 0, "what": "Acme verileri", "redownloadable": False},
                             {"id": 1, "what": "Yeni bir uygulama", "redownloadable": True}])
        items = self.items()
        calls = disk_memory.describe(items, knowledge, gemini)
        self.assertEqual(calls, 1)
        known, owner, acme, new, venv, own = items
        self.assertEqual((known.what, known.what_source), ("Bilinen uygulama", "gemini"))
        self.assertEqual((owner.what, owner.what_source, owner.redownloadable), ("Benim notum", "owner", False))
        self.assertEqual((acme.what, acme.what_source), ("Acme verileri", "gemini"))
        self.assertEqual((new.what, new.info["redownloadable_guess"]), ("Yeni bir uygulama", True))
        self.assertTrue(new.redownloadable)  # a guess never decides how something is deleted
        self.assertEqual(venv.what_source, "rule")
        # only what the knowledge didn't know went out, and only names
        sent = gemini.prompts[0]
        self.assertIn("New App", sent)
        self.assertIn('"folder": "Acme"', sent)
        self.assertIn("acme.exe", sent)
        for private in ("Known App", "Owner App", "Downloads", "PRIVATE CONTENT", str(self.folder), "Users",
                        "\\\\me\\\\", "p\\\\.venv"):
            self.assertNotIn(private, sent)
        # saved: the next scan asks nobody
        knowledge.save()
        again = disk_memory.Knowledge(self.folder / "knowledge.json")
        gemini2 = FakeGemini([])
        items2 = self.items()
        self.assertEqual(disk_memory.describe(items2, again, gemini2), 0)
        self.assertEqual(gemini2.prompts, [])
        self.assertEqual(items2[3].what, "Yeni bir uygulama")
        saved = json.loads((self.folder / "knowledge.json").read_text(encoding="utf-8"))["items"]
        self.assertEqual(saved["program:new app|c co"]["source"], "gemini")

    def test_owner_text_beats_the_rule(self):
        knowledge = disk_memory.Knowledge(self.folder / "knowledge.json")
        knowledge.put("venv:p\\.venv", "Tez deneyleri", "owner")
        items = self.items()
        disk_memory.describe(items, knowledge, None)
        self.assertEqual((items[4].what, items[4].what_source), ("Tez deneyleri", "owner"))

    def test_exe_info_is_remembered(self):
        knowledge = disk_memory.Knowledge(self.folder / "knowledge.json")
        item = Item("path:m", "folder", "C:\\Mystery", key="product:mystery|fake co", what="Mystery · Fake Co",
                    what_source="exe")
        disk_memory.describe([item], knowledge, FakeGemini([]))
        self.assertEqual(knowledge.get("product:mystery|fake co")["source"], "exe")

    def test_broken_answer_and_failing_gemini(self):
        knowledge = disk_memory.Knowledge(self.folder / "knowledge.json")
        items = self.items()
        self.assertEqual(disk_memory.describe(items, knowledge, lambda prompt: "sorry, no JSON"), 1)
        self.assertEqual(items[3].what, "")

        def down(prompt):
            raise ConnectionError("offline")
        self.assertEqual(disk_memory.describe(self.items(), knowledge, down), 1)

    def test_hand_edit_that_breaks_the_json(self):
        path = self.folder / "knowledge.json"
        path.write_text("{ not json", encoding="utf-8")
        self.assertEqual(disk_memory.Knowledge(path).entries, {})


def scan_at(at, used, sizes, free=200 * GB, last_used=None):
    items = [Item(i, "cache", i.split(":")[-1], f"C:\\x\\{i}", size=s, last_used=(last_used or {}).get(i, at))
             for i, s in sizes.items()]
    return Scan(at, items, 1000 * GB, used, free, {"seconds": 1})


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="zyraena_history_test_"))
        self.history = disk_memory.History(self.folder / "history.sqlite")

    def tearDown(self):
        self.history.close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_timeline_and_growers(self):
        day = 86400
        now = 100 * day
        self.history.add(scan_at(now - 10 * day, 500, {"a": 1 * GB, "b": 5 * GB}))
        self.history.add(scan_at(now - 8 * day, 510, {"a": 2 * GB, "b": 5 * GB}))
        self.history.add(scan_at(now - 1 * day, 520, {"a": 2 * GB, "b": 9 * GB, "c": 1 * GB}))
        self.assertEqual([u for _, u, _ in self.history.totals()], [500, 510, 520])
        self.assertEqual([s for _, s in self.history.item_sizes("a")], [GB, 2 * GB, 2 * GB])
        growers = self.history.growers(days=7, now=now)
        self.assertEqual([(g[0], g[3]) for g in growers], [("b", 4 * GB), ("c", GB)])
        self.assertEqual(self.history.sizes_before(now - 1 * day), {"a": 2 * GB, "b": 5 * GB})
        self.assertEqual(self.history.last_at(), now - day)

    def test_told_once(self):
        self.assertFalse(self.history.told("x"))
        self.history.tell(["x"])
        self.assertTrue(self.history.told("x"))


class FindingsTest(unittest.TestCase):
    def test_limits(self):
        now = 1_000 * 86400
        scan = scan_at(now, 900, {"grew": 10 * GB, "same": 3 * GB, "old": 20 * GB, "oldsmall": 1 * GB},
                       free=120 * GB, last_used={"old": now - 90 * 86400, "oldsmall": now - 90 * 86400})
        scan.items.append(Item("mei:leftovers", "mei", "_MEI", "C:\\t", size=GB, last_used=now, info={"count": 5}))
        found = disk_watch.findings(scan, {"grew": 7 * GB, "same": 3 * GB}, disk_watch.Limits(), "tr", now)
        keys = sorted(f.key.split(":")[0] + ":" + (f.item_id or "") for f in found)
        self.assertEqual(keys, ["free:", "grew:grew", "mei:mei:leftovers", "stale:old"])
        self.assertTrue(any("3.0 GB" in f.text for f in found))

    def test_quiet_when_nothing_crosses_a_limit(self):
        now = 1_000 * 86400
        scan = scan_at(now, 500, {"a": 50 * GB}, free=400 * GB)
        self.assertEqual(disk_watch.findings(scan, {"a": 49 * GB}, disk_watch.Limits(), "tr", now), [])

    def test_protected_and_links_are_never_stale(self):
        now = 1_000 * 86400
        scan = scan_at(now, 500, {"a": 50 * GB}, free=400 * GB, last_used={"a": 1})
        scan.items[0].protected = "Windows"
        self.assertEqual(disk_watch.findings(scan, {}, disk_watch.Limits(), "tr", now), [])


class DailyScanTest(unittest.TestCase):
    """disk_watch's scan end to end on the fake drive: history, knowledge, one bubble for new findings."""

    def test_scan_tells_new_findings_once(self):
        from disk_fixture import Tree

        tree = Tree()
        folder = Path(tempfile.mkdtemp(prefix="zyraena_watch_test_"))
        told = []
        gemini = FakeGemini([])
        store = disk_memory.Store(folder)
        disk_watch.configure(ask=gemini, notify=told.append, lang=lambda: "tr", store=store)
        old_min, old_free = disk_watch.disk_tools.MIN_FOLDER_BYTES, disk_watch._setting
        try:
            disk_watch.disk_tools.MIN_FOLDER_BYTES = 0
            self.assertTrue(disk_watch.scan_now(tree.places, tree.sources, wait=True))
            self.assertEqual(len(told), 1)  # free space 100 GB < 150 GB
            self.assertTrue(any(f.key.startswith("free:") for f in told[0]))
            self.assertEqual(len(store.history.totals()), 1)
            self.assertIsNotNone(store.last_scan())
            self.assertEqual(disk_watch.latest().stats["gemini_calls"], 1)  # Ghost App + Mystery's neighbours
            self.assertTrue(disk_watch.scan_now(tree.places, tree.sources, wait=True))
            self.assertEqual(len(told), 1)  # the same finding isn't told twice
            self.assertEqual(len(gemini.prompts), 2)  # the fake answered nothing, so it's asked again
            self.assertFalse(disk_watch.due())
        finally:
            disk_watch.disk_tools.MIN_FOLDER_BYTES = old_min
            disk_watch._setting = old_free
            disk_watch._state.update(store=None, scan=None, ask=None, notify=None)
            store.history.close()
            tree.cleanup()
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
