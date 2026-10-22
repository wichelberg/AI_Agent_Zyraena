"""disk_actions: how each kind of item is deleted, the safety net under it, and the _MEI clean-up.
Steam, uninstallers and pip / uv are never run: a fake Runner records what would have been run. Real
deletes happen only to fake folders in a temporary folder; the Recycle Bin is faked too.
Run from the project folder: python -m unittest discover -s tests
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import disk_actions  # noqa: E402
import disk_tools  # noqa: E402
from disk_fixture import Tree, by_path, write  # noqa: E402


class FakeRunner(disk_actions.Runner):
    def __init__(self):
        self.calls = []

    def open_url(self, url):
        self.calls.append(("url", url))

    def start(self, command):
        self.calls.append(("start", command))

    def run(self, argv):
        self.calls.append(("run", argv))

    def trash(self, path):
        self.calls.append(("trash", path))

    def free(self, drive):
        return 0


class PlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = Tree()
        cls.scan = cls.tree.scan()
        cls.items = {it.id: it for it in cls.scan.items}

    @classmethod
    def tearDownClass(cls):
        cls.tree.cleanup()

    def plan(self, item):
        return disk_actions.plan(item, python=["py", "-3"], uv="uv.exe")

    def test_game_goes_through_steam(self):
        p = self.plan(self.items["steam:123"])
        self.assertEqual((p.mode, p.command), ("url", "steam://uninstall/123"))

    def test_program_runs_its_own_uninstaller(self):
        p = self.plan(self.items["program:hklm64\\foo"])
        self.assertEqual(p.mode, "uninstaller")
        self.assertEqual(p.command, f'"{self.tree.foo}\\unins000.exe"')
        self.assertEqual(self.plan(self.items["program:hklm64\\ghost"]).command, "MsiExec.exe /X{GHOST}")

    def test_pip_and_uv_use_their_own_clean_up(self):
        pip = self.plan(by_path(self.scan, self.tree.pip))
        self.assertEqual((pip.mode, pip.command), ("command", ["py", "-3", "-m", "pip", "cache", "purge"]))
        uv = disk_tools.Item("path:uv", "cache", "uv", "C:\\x\\uv\\cache", info={"cache": "uv"})
        self.assertEqual(self.plan(uv).command, ["uv.exe", "cache", "clean"])
        no_uv = disk_actions.plan(uv, python=["py"], uv="")  # uv isn't installed: the folder is just deleted
        self.assertEqual(no_uv.mode, "delete")

    def test_folders_by_kind(self):
        self.assertEqual(self.plan(by_path(self.scan, self.tree.proj_venv)).mode, "delete")
        self.assertEqual(self.plan(by_path(self.scan, self.tree.model)).mode, "delete")
        self.assertEqual(self.plan(self.items["mei:leftovers"]).mode, "delete")
        self.assertEqual(self.plan(by_path(self.scan, self.tree.proj)).mode, "trash")       # irreplaceable
        self.assertEqual(self.plan(by_path(self.scan, self.tree.downloads)).mode, "trash")
        self.assertEqual(self.plan(by_path(self.scan, self.tree.temp)).mode, "contents")

    def test_no_delete_button(self):
        for it in self.scan.items:
            if it.kind in ("link", "system", "app") or it.container or it.protected:
                self.assertIsNone(self.plan(it), it.name)

    def test_execute_hands_off_to_steam_and_uninstallers(self):
        runner = FakeRunner()
        result = disk_actions.execute(self.plan(self.items["steam:123"]), self.tree.places, runner)
        self.assertTrue(result.ok and result.started)
        result = disk_actions.execute(self.plan(self.items["program:hklm64\\foo"]), self.tree.places, runner)
        self.assertTrue(result.started)
        result = disk_actions.execute(self.plan(by_path(self.scan, self.tree.pip)), self.tree.places, runner)
        self.assertTrue(result.ok and not result.started)
        self.assertEqual(runner.calls, [("url", "steam://uninstall/123"), ("start", f'"{self.tree.foo}\\unins000.exe"'),
                                        ("run", ["py", "-3", "-m", "pip", "cache", "purge"])])
        self.assertTrue(self.tree.foo.exists() and self.tree.pip.exists())  # nothing deleted by hand

    def test_too_big_for_the_recycle_bin(self):
        p = self.plan(by_path(self.scan, self.tree.downloads))
        runner = FakeRunner()
        result = disk_actions.execute(p, self.tree.places, runner, bin_limit=p.size - 1, bin_used=0)
        self.assertEqual((result.ok, result.error), (False, "too_big_for_bin"))
        self.assertEqual(runner.calls, [])
        result = disk_actions.execute(p, self.tree.places, runner, bin_limit=p.size + 1, bin_used=0)
        self.assertTrue(result.ok)
        self.assertEqual(runner.calls, [("trash", str(self.tree.downloads))])

    def test_what_is_already_in_the_bin_counts(self):
        """2026-10-21: the bin's size was checked, not its free room; Windows deleted the rest for good."""
        p = self.plan(by_path(self.scan, self.tree.downloads))
        runner = FakeRunner()
        result = disk_actions.execute(p, self.tree.places, runner, bin_limit=10 * p.size, bin_used=10 * p.size - 5)
        self.assertEqual((result.ok, result.error, result.bin_free), (False, "too_big_for_bin", 5))
        self.assertEqual(runner.calls, [])

    def test_gone_but_not_in_the_bin_is_reported(self):
        tree = Tree()
        try:
            folder = tree.downloads

            class Vanishing(FakeRunner):
                def trash(self, path):
                    import shutil

                    shutil.rmtree(path)  # what Windows did: deleted for good

                def in_bin(self, path, since):
                    return False

            p = disk_actions.plan(by_path(tree.scan(), folder))
            result = disk_actions.execute(p, tree.places, Vanishing(), bin_limit=10 ** 9, bin_used=0)
            self.assertEqual((result.ok, result.error), (False, "not_in_bin"))
        finally:
            tree.cleanup()

    def test_reads_the_original_path_of_a_bin_entry(self):
        name = "C:\\Users\\me\\Documents\\Paradox Interactive"
        data = (2).to_bytes(8, "little") + (123).to_bytes(8, "little") + (0).to_bytes(8, "little") \
            + (len(name) + 1).to_bytes(4, "little") + (name + "\0").encode("utf-16-le")
        self.assertEqual(disk_actions._bin_entry_path(data), name)
        self.assertEqual(disk_actions._bin_entry_path(b"\x01" + b"\0" * 40), "")


class DeleteTest(unittest.TestCase):
    def setUp(self):
        self.tree = Tree()
        self.scan = self.tree.scan()

    def tearDown(self):
        self.tree.cleanup()

    def test_venv_deleted_for_good(self):
        venv = by_path(self.scan, self.tree.proj_venv)
        os.chmod(self.tree.proj_venv / "pyvenv.cfg", 0o444)  # read-only files go too
        result = disk_actions.execute(disk_actions.plan(venv), self.tree.places, FakeRunner())
        self.assertTrue(result.ok, result.error)
        self.assertFalse(self.tree.proj_venv.exists())
        self.assertTrue((self.tree.proj / "main.py").exists())

    def test_mei_leftovers_deleted(self):
        result = disk_actions.execute(disk_actions.plan(next(i for i in self.scan.items if i.id == "mei:leftovers")),
                                      self.tree.places, FakeRunner())
        self.assertTrue(result.ok)
        self.assertFalse(self.tree.mei_old.exists())
        self.assertTrue(self.tree.mei_own.exists())

    def test_temp_keeps_new_files(self):
        new = write(self.tree.temp / "new.tmp")
        self.tree.age(new, -3600)  # "changed" after now (a file's creation time can't be moved back)
        old_limit, disk_actions.TEMP_MIN_AGE_SECONDS = disk_actions.TEMP_MIN_AGE_SECONDS, 0
        try:
            result = disk_actions.execute(disk_actions.plan(by_path(self.scan, self.tree.temp)), self.tree.places,
                                          FakeRunner())
        finally:
            disk_actions.TEMP_MIN_AGE_SECONDS = old_limit
        self.assertTrue(result.ok)
        self.assertFalse((self.tree.temp / "old.tmp").exists())
        self.assertTrue((self.tree.temp / "new.tmp").exists())
        self.assertTrue(self.tree.mei_old.exists())  # the _MEI folders are a separate item

    def test_safety_net(self):
        pl = self.tree.places
        for path in (pl.drive, pl.home, pl.documents, pl.windows, pl.voice_home, pl.voice_home / "env",
                     pl.egitim_venv, pl.failsafe, pl.voice_home.parent, pl.program_files[0], pl.temp, "relative\\x"):
            with self.assertRaises(disk_actions.Refused, msg=str(path)):
                disk_actions.check_path(str(path), pl)
        disk_actions.check_path(str(self.tree.proj_venv), pl)  # an ordinary folder is fine
        evil = disk_actions.Plan("delete", "x", "x", paths=[str(pl.voice_home.parent)])
        result = disk_actions.execute(evil, pl, FakeRunner())
        self.assertFalse(result.ok)
        self.assertTrue(pl.voice_home.exists())


class MeiTest(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="zyraena_mei_test_"))
        self.now = time.time() + 2 * 3600  # every folder made now looks two hours old

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp, ignore_errors=True)

    def mei(self, name, pyinstaller=True):
        folder = self.temp / name
        write(folder / ("base_library.zip" if pyinstaller else "readme.txt"))
        write(folder / "python311.dll")
        return folder

    def test_cleans_only_old_pyinstaller_leftovers(self):
        old = self.mei("_MEI100")
        own = self.mei("_MEI200")
        young = self.mei("_MEI300")
        future = time.time() + 2 * 3600
        os.utime(young, (future, future))  # changed within the hour
        foreign = self.mei("_MEI400", pyinstaller=False)
        other = self.mei("NotMEI")
        removed, kept = disk_actions.clean_mei(self.temp, own=str(own), now=self.now)
        self.assertEqual(removed, [str(old)])
        self.assertEqual(kept, [])
        self.assertFalse(old.exists())
        for folder in (own, young, foreign, other):
            self.assertTrue(folder.exists(), folder)

    def test_in_use_is_kept(self):
        busy = self.mei("_MEI500")
        handle = open(busy / "python311.dll", "rb")  # like a running exe's loaded files
        try:
            removed, kept = disk_actions.clean_mei(self.temp, own="", now=self.now)
            self.assertEqual((removed, kept), ([], [str(busy)]))
            self.assertTrue((busy / "base_library.zip").exists())
        finally:
            handle.close()
        removed, _ = disk_actions.clean_mei(self.temp, own="", now=self.now)
        self.assertEqual(removed, [str(busy)])

    def test_loaded_dll_is_kept(self):
        """A real process with a DLL from the folder loaded, as the onefile exe has."""
        busy = self.temp / "_MEI600"
        write(busy / "base_library.zip")
        dll = busy / "zyr_test.dll"
        dll.write_bytes(Path(sys.base_prefix, "DLLs", "_ctypes.pyd").read_bytes()
                        if Path(sys.base_prefix, "DLLs", "_ctypes.pyd").exists()
                        else Path(sys.base_prefix, "python3.dll").read_bytes())
        proc = subprocess.Popen([sys.executable, "-c", f"import ctypes,sys,time; ctypes.WinDLL(r'{dll}'); "
                                 "print('ready', flush=True); time.sleep(30)"], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(), "ready")
            removed, kept = disk_actions.clean_mei(self.temp, own="", now=self.now)
            self.assertEqual((removed, kept), ([], [str(busy)]))
            self.assertTrue(dll.exists())
        finally:
            proc.kill()
            proc.wait()
            proc.stdout.close()

    def test_half_deleted_tombstone_is_finished(self):
        tomb = self.temp / ("_MEI700" + disk_actions.TOMB)
        write(tomb / "leftover.pyd")  # base_library.zip went already
        removed, _ = disk_actions.clean_mei(self.temp, own="", now=self.now)
        self.assertEqual(removed, [str(tomb)])
        self.assertFalse(tomb.exists())


if __name__ == "__main__":
    unittest.main()
