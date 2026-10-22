"""control_panel: the Ctrl+F1 panel in the middle of the screen (pet show/hide, OpenRouter and Tavily
credits). The panel is opened by calling control_panel.toggle directly: keys sent with pynput's
Controller don't reach pynput's GlobalHotKeys. Nothing here touches the real pet, the network or any
file: the pet and the credit calls are fakes.

The window tests need a working Tcl/Tk (py -3); without one they are skipped.
Run from the project folder: python -m unittest discover -s tests
"""
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import i18n  # noqa: E402

try:
    import tkinter as tk

    _probe = tk.Tk()
    _probe.destroy()
    import chat_box  # noqa: E402
    import control_panel  # noqa: E402
    TK_ERROR = None
except Exception as e:  # broken Tcl/Tk (the project's Python 3.11)
    TK_ERROR = e
    control_panel = None


def on_ui(fn, timeout=5.0):
    """Runs fn on the panel's Tk thread and returns its result."""
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


class TextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if control_panel is None:
            raise unittest.SkipTest(f"no Tcl/Tk: {TK_ERROR}")

    def test_openrouter(self):
        self.assertEqual(control_panel.openrouter_text("tr", 12.3456), "$12.35")
        self.assertEqual(control_panel.openrouter_text("tr", None), "alınamadı")

    def test_tavily(self):
        self.assertEqual(control_panel.tavily_text("tr", ("ok", {"remaining": 812, "limit": 1000})), "812 / 1000")
        self.assertEqual(control_panel.tavily_text("tr", ("ok", {"remaining": 812.5, "limit": 1000.0})),
                         "812.5 / 1000")
        self.assertEqual(control_panel.tavily_text("tr", ("unknown", None)), "bilinmiyor")
        self.assertEqual(control_panel.tavily_text("tr", ("error", None)), "alınamadı")

    def test_turkish_and_english_have_the_same_keys(self):
        keys = [k for k in i18n.STRINGS["en"] if k.startswith("panel_")]
        self.assertGreaterEqual(len(keys), 9)
        for k in keys:
            self.assertIn(k, i18n.STRINGS["tr"])


class PanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if control_panel is None:
            raise unittest.SkipTest(f"no Tcl/Tk: {TK_ERROR}")

    def setUp(self):
        self.pet = {"visible": True, "toggles": 0}
        self.release = threading.Event()  # the fetches wait for it, so "loading…" can be seen first

    def tearDown(self):
        self.release.set()
        if control_panel.is_open():
            on_ui(lambda: control_panel._state["panel"].close())

    def open(self, openrouter=12.5, tavily=("ok", {"remaining": 900, "limit": 1000})):
        def fetch(value):
            def run():
                self.release.wait(5)
                if isinstance(value, Exception):
                    raise value
                return value
            return run

        def toggle_pet():
            self.pet["toggles"] += 1
            self.pet["visible"] = not self.pet["visible"]
            return self.pet["visible"]

        control_panel.toggle("tr", lambda: self.pet["visible"], toggle_pet, fetch(openrouter), fetch(tavily))
        self.assertTrue(wait_for(control_panel.is_open))
        return control_panel._state["panel"]

    def values(self, panel):
        return on_ui(lambda: {k: label.cget("text") for k, label in panel.values.items()})

    def test_loading_first_then_the_credits(self):
        panel = self.open()
        self.assertEqual(self.values(panel), {"openrouter": "yükleniyor…", "tavily": "yükleniyor…"})
        self.release.set()
        self.assertTrue(wait_for(lambda: panel.values["tavily"].cget("text") == "900 / 1000"
                                 and panel.values["openrouter"].cget("text") == "$12.50"))

    def test_errors_show_a_short_text(self):
        panel = self.open(openrouter=None, tavily=RuntimeError("network down"))
        self.release.set()
        self.assertTrue(wait_for(lambda: self.values_now(panel) == {"openrouter": "alınamadı", "tavily": "alınamadı"}))

    def values_now(self, panel):
        return {k: label.cget("text") for k, label in panel.values.items()}

    def test_centered_on_the_screen(self):
        panel = self.open()
        x, y, w, h = on_ui(lambda: (panel.neon.win.winfo_x(), panel.neon.win.winfo_y(),
                                    panel.neon.win.winfo_width(), panel.neon.win.winfo_height()))
        left, top, right, bottom = control_panel._work_area()
        self.assertLessEqual(abs(x + w / 2 - (left + right) / 2), 2)
        self.assertLessEqual(abs(y + h / 2 - (top + bottom) / 2), 2)

    def test_pet_button_hides_and_shows_her(self):
        panel = self.open()
        self.assertEqual(on_ui(lambda: panel.pet_button.cget("text")), "Pet'i gizle")
        on_ui(panel.pet_button.invoke)
        self.assertTrue(wait_for(lambda: panel.pet_button.cget("text") == "Pet'i göster"))
        self.assertEqual(self.pet, {"visible": False, "toggles": 1})
        on_ui(panel.pet_button.invoke)
        self.assertTrue(wait_for(lambda: panel.pet_button.cget("text") == "Pet'i gizle"))
        self.assertTrue(self.pet["visible"])

    def test_escape_closes(self):
        panel = self.open()
        on_ui(lambda: panel.neon.win.event_generate("<Escape>"))
        self.assertTrue(wait_for(lambda: not control_panel.is_open()))

    def test_toggle_again_closes_and_late_results_are_ignored(self):
        panel = self.open()
        control_panel.toggle("tr", lambda: True, lambda: True, lambda: 1.0, lambda: ("error", None))
        self.assertTrue(wait_for(lambda: not control_panel.is_open()))
        self.release.set()  # the first panel's fetches finish after it closed: no error
        time.sleep(0.2)
        self.assertTrue(panel.closed)


if __name__ == "__main__":
    unittest.main()
