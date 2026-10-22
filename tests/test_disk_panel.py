"""The control panel's Disk tab (disk_panel.py) on the fake drive's scan: tabs, the list, filters and
sorting, no delete button for protected items, and the confirm window listing what goes and what
breaks. Deleting is faked (disk_actions.execute is replaced): nothing on the PC changes.

The window tests need a working Tcl/Tk (py -3); without one they are skipped.
Run from the project folder: python -m unittest discover -s tests
"""
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import tkinter as tk

    _probe = tk.Tk()
    _probe.destroy()
    import chat_box  # noqa: E402
    import control_panel  # noqa: E402
    import disk_actions  # noqa: E402
    import disk_memory  # noqa: E402
    import disk_panel  # noqa: E402
    TK_ERROR = None
except Exception as e:  # broken Tcl/Tk (the project's Python 3.11)
    TK_ERROR = e
    control_panel = None

from disk_fixture import Tree, by_path  # noqa: E402


def on_ui(fn, timeout=5.0):
    box, done = {}, threading.Event()

    def run():
        try:
            box["value"] = fn()
        except Exception as e:
            box["error"] = e
        done.set()

    chat_box._state["root"].after(0, run)
    if not done.wait(timeout):
        raise TimeoutError("the Tk thread didn't answer")
    if "error" in box:
        raise box["error"]
    return box["value"]


def wait_for(check, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if on_ui(check):
            return True
        time.sleep(0.05)
    return False


class FakeService:
    """disk_watch's face to the tab."""

    def __init__(self, scan, folder):
        self.scan = scan
        self.st = disk_memory.Store(folder)
        self.st.history.add(scan)
        self.listeners, self.deleted, self.scans = [], [], 0

    def latest(self):
        return self.scan

    def running(self):
        return False

    def progress(self):
        return ""

    def listen(self, fn):
        self.listeners.append(fn)
        return lambda: self.listeners.remove(fn)

    def scan_now(self):
        self.scans += 1
        return True

    def store(self):
        return self.st

    def after_delete(self, scan, item):
        self.deleted.append(item.id)
        scan.items = [it for it in scan.items if it is not item]


class DiskTabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if control_panel is None:
            raise unittest.SkipTest(f"no Tcl/Tk: {TK_ERROR}")
        cls.tree = Tree()
        cls.folder = tempfile.mkdtemp(prefix="zyraena_panel_test_")

    @classmethod
    def tearDownClass(cls):
        cls.tree.cleanup()

    def setUp(self):
        self.scan = self.tree.scan()
        self.service = FakeService(self.scan, self.folder)
        self.executed = []
        self.real_execute = disk_actions.execute
        disk_actions.execute = lambda p, pl, *a, **k: self.executed.append(p) or disk_actions.Result(True, freed=4096)

    def tearDown(self):
        disk_actions.execute = self.real_execute
        if control_panel.is_open():
            on_ui(lambda: control_panel._state["panel"].close())
        self.service.st.history.close()

    def open(self, tab="disk"):
        control_panel.show(tab, "tr", lambda: True, lambda: True, lambda: 1.0, lambda: ("unknown", None), self.service)
        self.assertTrue(wait_for(control_panel.is_open))
        return control_panel._state["panel"]

    def select(self, tab, item_id):
        def run():
            for row, it in tab.items_by_row.items():
                if it.id == item_id:
                    tab.tree.selection_set(row)
                    return True
            return False
        self.assertTrue(on_ui(run), item_id)
        self.assertTrue(wait_for(lambda: tab.selected is not None and tab.selected.id == item_id))

    def test_tabs(self):
        panel = self.open("general")
        self.assertEqual(panel.tab, "general")
        self.assertTrue(wait_for(lambda: panel.values["openrouter"].cget("text") == "$1.00"))
        on_ui(lambda: panel.tab_buttons["disk"].invoke())
        self.assertTrue(wait_for(lambda: panel.tab == "disk" and panel.disk_tab is not None))
        w = on_ui(lambda: panel.neon.win.winfo_width())
        self.assertGreater(w, control_panel.PANEL_SIZE[0])
        on_ui(lambda: panel.tab_buttons["general"].invoke())
        self.assertTrue(wait_for(lambda: panel.tab == "general"))
        self.assertEqual(on_ui(lambda: panel.values["openrouter"].cget("text")), "$1.00")  # kept, not fetched again

    def test_list_filter_and_sort(self):
        tab = self.open().disk_tab
        on_ui(lambda: (tab.min_var.set("0"), tab.fill()))  # the fake drive's items are tiny
        rows = on_ui(lambda: [it.size for it in tab.items_by_row.values()])
        self.assertGreater(len(rows), 10)
        self.assertEqual(rows, sorted(rows, reverse=True))  # biggest first
        on_ui(lambda: (tab.min_var.set("0"), tab.kind_var.set("Venv"), tab.fill()))
        kinds = on_ui(lambda: {it.kind for it in tab.items_by_row.values()})
        self.assertEqual(kinds, {"venv"})
        on_ui(lambda: tab._sort("name"))
        names = on_ui(lambda: [it.name.lower() for it in tab.items_by_row.values()])
        self.assertEqual(names, sorted(names))
        headings = on_ui(lambda: [tab.tree.heading(c)["text"] for c, _ in disk_panel.COLUMNS])
        self.assertEqual(headings, ["Tür", "Ad", "Boyut", "Son kullanım", "Ne olduğu", "Yeniden indirilir",
                                    "Bağımlılıklar"])

    def test_broken_dependency_is_red(self):
        tab = self.open().disk_tab
        on_ui(lambda: (tab.min_var.set("0"), tab.fill()))
        rows = on_ui(lambda: {it.name: tab.tree.item(row, "tags") for row, it in tab.items_by_row.items()})
        self.assertIn("broken", rows["\\Hannah"])
        values = on_ui(lambda: next(tab.tree.item(row, "values") for row, it in tab.items_by_row.items()
                                    if it.name == "\\Hannah"))
        self.assertTrue(values[-1].startswith("bağımlılık yok"))

    def test_protected_has_no_delete(self):
        tab = self.open().disk_tab
        on_ui(lambda: (tab.min_var.set("0"), tab.fill()))
        self.select(tab, "system:windows")
        self.assertEqual(on_ui(lambda: tab.delete_button.cget("state")), "disabled")
        self.assertIn("Korunuyor", on_ui(lambda: tab.delete_note.cget("text")))

    def test_confirm_lists_what_breaks_and_cancel_does_nothing(self):
        tab = self.open().disk_tab
        on_ui(lambda: (tab.min_var.set("0"), tab.fill()))
        python = by_path(self.scan, self.tree.python)
        self.select(tab, python.id)
        on_ui(tab._ask_delete)
        self.assertTrue(wait_for(lambda: tab.confirm is not None))
        text = on_ui(lambda: tab.confirm.text)
        self.assertIn("kaldırıcısı", text)  # python.org's own uninstaller
        self.assertIn("Bunlar bozulur", text)
        self.assertIn("proj1\\.venv", text)
        on_ui(lambda: tab.confirm.pick(False))
        time.sleep(0.2)
        self.assertEqual(self.executed, [])

    def test_delete_after_yes(self):
        tab = self.open().disk_tab
        on_ui(lambda: (tab.min_var.set("0"), tab.fill()))
        venv = by_path(self.scan, self.tree.proj_venv)
        self.select(tab, venv.id)
        on_ui(tab._ask_delete)
        self.assertTrue(wait_for(lambda: tab.confirm is not None))
        self.assertIn("Kalıcı olarak silinir", on_ui(lambda: tab.confirm.text))
        on_ui(lambda: tab.confirm.pick(True))
        done = wait_for(lambda: tab.result_label.cget("text").startswith("Tamam"))
        self.assertTrue(done, on_ui(lambda: tab.result_label.cget("text")))
        self.assertEqual([p.mode for p in self.executed], ["delete"])
        self.assertEqual(self.service.deleted, [venv.id])
        self.assertNotIn(venv.id, on_ui(lambda: [it.id for it in tab.items_by_row.values()]))

    def test_variables_belong_to_the_panel(self):
        """2026-10-21: without a master they went to the pet's Tk root on another thread and deadlocked."""
        tab = self.open().disk_tab
        self.assertTrue(on_ui(lambda: tab.kind_var._tk is tab.win.tk and tab.min_var._tk is tab.win.tk))

    def test_confirm_stays_above_the_panel(self):
        """2026-10-21: a click on the panel covered the confirm window and its Delete button."""
        import ctypes

        user32 = ctypes.windll.user32
        user32.GetWindow.restype = ctypes.c_void_p
        user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetTopWindow.restype = ctypes.c_void_p
        user32.GetParent.restype = ctypes.c_void_p
        user32.GetParent.argtypes = [ctypes.c_void_p]

        def above(a, b):
            h = user32.GetTopWindow(None)
            while h:
                if h == a:
                    return True
                if h == b:
                    return False
                h = user32.GetWindow(h, 2)  # GW_HWNDNEXT
            return False

        panel = self.open()
        tab = panel.disk_tab
        on_ui(lambda: (tab.min_var.set("0"), tab.fill()))
        self.select(tab, by_path(self.scan, self.tree.proj_venv).id)
        on_ui(tab._ask_delete)
        self.assertTrue(wait_for(lambda: tab.confirm is not None))
        confirm = on_ui(lambda: user32.GetParent(tab.confirm.neon.win.winfo_id()))
        main = on_ui(lambda: user32.GetParent(panel.neon.win.winfo_id()))
        on_ui(lambda: panel.neon.win.lift())  # like a click on the panel
        time.sleep(disk_panel.KEEP_ON_TOP_MS / 1000 * 3)
        self.assertTrue(above(confirm, main))
        on_ui(lambda: tab.confirm.pick(False))

    def test_scan_button(self):
        tab = self.open().disk_tab
        on_ui(lambda: tab.scan_button.invoke())
        self.assertEqual(self.service.scans, 1)


if __name__ == "__main__":
    unittest.main()
