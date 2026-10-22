"""disk_tools: recognising items on a fake drive (tests/disk_fixture.py), sizes with hard links counted
once, the dependency graph and the protection rules. Read-only: only the temporary fake drive is walked.
Run from the project folder: python -m unittest discover -s tests
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_actions  # noqa: E402
import disk_tools  # noqa: E402
from disk_fixture import KB, Tree, by_path  # noqa: E402


class VdfTest(unittest.TestCase):
    def test_nested_and_case_insensitive(self):
        data = disk_tools.parse_vdf('"AppState"\n{\n "appid" "730"\n "UserConfig"\n {\n  "language" "turkish"\n }\n'
                                    ' "path" "C:\\\\Games"\n}\n')
        self.assertEqual(disk_tools.vget(data, "appstate", "APPID"), "730")
        self.assertEqual(disk_tools.vget(data, "AppState", "userconfig", "language"), "turkish")
        self.assertEqual(disk_tools.vget(data, "AppState", "path"), "C:\\Games")
        self.assertIsNone(disk_tools.vget(data, "AppState", "missing", "x"))

    def test_command_exe(self):
        self.assertEqual(disk_tools._command_exe('"C:\\Program Files\\A\\a.exe" --tray'), "C:\\Program Files\\A\\a.exe")
        self.assertEqual(disk_tools._command_exe("C:\\Tools\\b.exe -x"), "C:\\Tools\\b.exe")


class ScanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = Tree()
        cls.tree.sources.git[disk_tools.norm(cls.tree.proj)] = 1_700_000_500
        cls.scan = cls.tree.scan()
        cls.items = {it.id: it for it in cls.scan.items}

    @classmethod
    def tearDownClass(cls):
        cls.tree.cleanup()

    def item(self, path):
        it = by_path(self.scan, path)
        self.assertIsNotNone(it, f"no item for {path}")
        return it

    def test_steam_game_with_last_played(self):
        game = self.items["steam:123"]
        self.assertEqual((game.kind, game.name, game.info["appid"]), ("game", "Fake Game", "123"))
        self.assertEqual((game.last_used, game.used_source), (1_700_000_000, "steam"))
        self.assertTrue(game.redownloadable)
        self.assertEqual(len(game.parts), 1)  # its shader cache is charged to it
        self.assertGreaterEqual(game.size, 136 * KB)

    def test_steam_folder_without_a_manifest_is_a_leftover(self):
        old = self.item(self.tree.steam / "steamapps" / "common" / "OldGame")
        self.assertEqual(old.info.get("steam_leftover"), "common")
        self.assertFalse(old.redownloadable)  # may hold mods and saves: Recycle Bin

    def test_programs_from_the_registry(self):
        foo = self.items["program:hklm64\\foo"]
        self.assertEqual((foo.kind, disk_tools.norm(foo.path)), ("program", disk_tools.norm(self.tree.foo)))
        self.assertEqual(foo.key, "program:foo|foo inc")
        self.assertIn("unins000.exe", foo.info["uninstall"])
        ghost = self.items["program:hklm64\\ghost"]
        self.assertEqual((ghost.path, ghost.size, ghost.size_source), ("", 2048 * 1024, "registry"))
        self.assertTrue(self.items["program:hklm64\\vc"].protected)  # a runtime: Settings > Apps
        names = {it.name for it in self.scan.items}
        self.assertNotIn("Hidden part", names)
        self.assertNotIn("program:hklm64\\steam app 123", self.items)  # the game comes from Steam

    def test_python_install_gets_its_uninstaller(self):
        py = self.item(self.tree.python)
        self.assertEqual(py.kind, "python")
        self.assertIn("/uninstall", py.info["uninstall"])
        self.assertNotIn("Python 3.11.9 (64-bit)", {it.name for it in self.scan.items})

    def test_venv_details(self):
        venv = self.item(self.tree.proj_venv)
        self.assertEqual(venv.kind, "venv")
        self.assertEqual(venv.info["python"], "3.11.9")
        self.assertEqual(set(venv.info["packages"]), {"torch", "numpy"})
        self.assertEqual(venv.used_source, "newest_file")
        self.assertIn("torch", venv.what)

    def test_venvs_inside_failsafe_are_not_items(self):
        self.assertIsNone(by_path(self.scan, self.tree.failsafe / "backup" / ".venv"))

    def test_caches_models_mei_projects_own(self):
        self.assertEqual(self.item(self.tree.pip).info["cache"], "pip")
        model = self.item(self.tree.model)
        self.assertEqual((model.kind, model.name), ("model", "org/model"))
        mei = self.items["mei:leftovers"]
        self.assertEqual([disk_tools.norm(p) for p in [mei.path, *mei.parts]], [disk_tools.norm(self.tree.mei_old)])
        self.assertEqual(self.items["mei:own"].kind, "mei")
        proj = self.item(self.tree.proj)
        self.assertEqual((proj.kind, proj.redownloadable), ("project", False))
        self.assertEqual((proj.last_used, proj.used_source), (1_700_000_500, "git"))
        self.assertEqual(proj.info["models"], ["org/model"])  # "not/cached" isn't in the HF cache
        own = self.item(self.tree.downloads)
        self.assertEqual((own.kind, own.redownloadable), ("own", False))

    def test_unknown_folder_uses_its_exe_info(self):
        mystery = self.item(self.tree.root / "Program Files" / "Mystery")
        self.assertEqual((mystery.kind, mystery.what_source), ("folder", "exe"))
        self.assertEqual(mystery.key, "product:mystery tool|fake co")
        self.assertTrue(mystery.redownloadable)  # an installed product under Program Files
        self.assertEqual(disk_actions.plan(mystery).mode, "trash")  # but unknown: never deleted for good

    def test_every_item_is_marked(self):
        for it in self.scan.items:
            self.assertIsInstance(it.redownloadable, bool, it.name)
            self.assertIn(it.kind, disk_tools.KINDS)

    def test_hard_link_counted_once(self):
        pip, venv = self.item(self.tree.pip), self.item(self.tree.proj_venv)
        wheel = os.path.getsize(self.tree.pip / "wheel.whl")
        self.assertEqual(pip.shared + venv.shared, wheel)
        self.assertGreaterEqual(self.scan.stats["hardlinked_bytes"], wheel)
        total = sum(it.size + it.shared for it in (pip, venv))
        self.assertEqual(sum(it.size for it in (pip, venv)), total - wheel)

    def test_sizes_leave_nested_items_out(self):
        proj = self.item(self.tree.proj)
        self.assertLess(proj.size, 32 * KB)  # main.py only; the venv is its own item

    # --- graph ---

    def test_dependencies(self):
        py = self.item(self.tree.python)
        venv = self.item(self.tree.proj_venv)
        self.assertIn(py.id, venv.dep_ids)  # home=
        voice_env = self.item(self.tree.voice_env)
        egitim = self.item(self.tree.egitim)
        self.assertIn(egitim.id, voice_env.dep_ids)  # .pth
        proj = self.item(self.tree.proj)
        self.assertIn(self.item(self.tree.model).id, proj.dep_ids)  # model id in the code
        link = next(it for it in self.scan.items if it.kind == "link" and it.name == "Foo")
        self.assertEqual(link.dep_ids, ["program:hklm64\\foo"])
        dead = next(it for it in self.scan.items if it.kind == "link" and it.name == "\\Hannah")
        self.assertEqual(len(dead.broken), 1)  # its exe is gone: red in the panel

    def test_dependents_of_a_python(self):
        py = self.item(self.tree.python)
        going, breaking = disk_tools.dependents(py, self.scan.items)
        self.assertEqual(going, [])
        self.assertTrue({self.item(self.tree.proj_venv).id, self.item(self.tree.egitim).id}
                        <= {b.id for b in breaking})

    def test_project_takes_its_venv_with_it(self):
        proj = self.item(self.tree.proj)
        going, _ = disk_tools.dependents(proj, self.scan.items)
        self.assertIn(self.item(self.tree.proj_venv).id, {g.id for g in going})

    def test_duplicate_venvs(self):
        groups = disk_tools.duplicate_venvs(self.scan.items)
        names = [sorted(disk_tools.norm(it.path) for it in g) for g in groups]
        self.assertIn(sorted(disk_tools.norm(p) for p in (self.tree.proj_venv, self.tree.twin_venv, self.tree.egitim)),
                      names)

    # --- protection ---

    def test_protected(self):
        self.assertTrue(self.items["system:windows"].protected)
        self.assertTrue(self.item(self.tree.voice_env).protected)       # under Zyraena\voice
        self.assertTrue(self.item(self.tree.egitim).protected)          # Wichelberg's egitim venv
        self.assertTrue(self.item(self.tree.failsafe).protected)
        self.assertTrue(self.items["mei:own"].protected)                # the running Zyraena's _MEI
        self.assertTrue(self.items["app:zyraena"].protected)
        common = self.item(self.tree.root / "Program Files" / "Common Files")
        self.assertEqual(common.kind, "system")
        self.assertTrue(common.protected)
        base = self.item(self.tree.base_venv)  # proj4's venv reaches it through a .pth
        self.assertIn("proj4", base.protected)
        for it in self.scan.items:
            if it.protected:
                self.assertIsNone(disk_actions.plan(it), it.name)

    def test_ordinary_items_are_not_protected(self):
        for path in (self.tree.proj_venv, self.tree.pip, self.tree.model, self.tree.proj, self.tree.downloads):
            self.assertEqual(self.item(path).protected, "", path)
        self.assertEqual(self.items["steam:123"].protected, "")
        self.assertEqual(self.items["mei:leftovers"].protected, "")

    def test_graph_after_a_delete(self):
        tree = Tree()
        try:
            scan = tree.scan()
            py = by_path(scan, tree.python)
            shutil.rmtree(tree.python)
            import disk_watch

            store = _MemoryStore()
            disk_watch.configure(store=store)
            disk_watch.after_delete(scan, py)
            self.assertIsNone(by_path(scan, tree.python))  # gone from the list
            venv = by_path(scan, tree.proj_venv)
            self.assertEqual([disk_tools.norm(b) for b in venv.broken], [disk_tools.norm(tree.python)])
            self.assertIs(store.saved, scan)
        finally:
            disk_watch.configure(store=None)
            disk_watch._state["store"] = None
            tree.cleanup()


class _MemoryStore:
    saved = None

    def save_scan(self, scan):
        self.saved = scan


if __name__ == "__main__":
    unittest.main()
