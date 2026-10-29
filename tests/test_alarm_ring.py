"""A ringing alarm reaches Telegram and can be stopped there (2026-10-25: one rang for hours while the
owner was away). The popup and Telegram are fakes and the timings are shrunk.

Run from the project folder: python -m unittest discover -s tests
"""
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import alarm_ring  # noqa: E402
import alert  # noqa: E402

WAIT = 3  # s: the longest any scenario may take


class FakeTelegram:
    def __init__(self, set_up=True):
        self.set_up = set_up
        self.alerts, self.sent, self.retired, self.forgotten = [], [], [], []

    def send_alert(self, text, yes_text=None, no_text=None, pending=None):
        if not self.set_up:
            return None
        pending = {"event": threading.Event(), "ok": False, "yes": yes_text, "no": no_text}
        self.alerts.append((text, pending))
        return pending

    def press(self, yes):
        pending = self.alerts[-1][1]
        pending["ok"] = yes
        pending["event"].set()

    def send(self, text):
        self.sent.append(text)
        return self.set_up

    def retire_alert(self, pending, note):
        self.retired.append((pending, note))

    def forget_alert(self, pending):
        self.forgotten.append(pending)


class FakePopup:
    """Stands in for alert's popup: records calls, and close_on_pc() is the owner clicking OK."""

    def __init__(self):
        self.calls = []
        self.on_choice = None

    def show_choice(self, token, text, sound_path, choices, on_choice, **kwargs):
        self.calls.append(("show", text, sound_path))
        self.on_choice = on_choice

    def silence(self, token):
        self.calls.append(("silence",))

    def close(self, token):
        self.calls.append(("close",))

    def close_on_pc(self):
        self.on_choice(0)

    def kinds(self):
        return [c[0] for c in self.calls]


def wait_for(condition):
    end = time.monotonic() + WAIT
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


class AlarmRingTest(unittest.TestCase):
    def setUp(self):
        self.popup = FakePopup()
        self.telegram = FakeTelegram()
        self.idle = 0
        patches = [
            mock.patch.object(alarm_ring.alert, "show_choice", self.popup.show_choice),
            mock.patch.object(alarm_ring.alert, "silence", self.popup.silence),
            mock.patch.object(alarm_ring.alert, "close", self.popup.close),
            mock.patch.object(alarm_ring, "_telegram", lambda: self.telegram),
            mock.patch.object(alarm_ring, "_idle_seconds", lambda: self.idle),
            mock.patch.object(alarm_ring, "POLL_SECONDS", 0.01),
            mock.patch.object(alarm_ring, "REMOTE_AFTER_SECONDS", 0.3),
            mock.patch.object(alarm_ring, "SILENCE_AFTER_SECONDS", 0.6),
            mock.patch.object(alarm_ring, "AWAY_IDLE_SECONDS", 100),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def start(self):
        thread = threading.Thread(target=alarm_ring._run, args=("Toplantı", "sounds/alert.mp3"), daemon=True)
        thread.start()
        self.assertTrue(wait_for(lambda: self.popup.on_choice is not None))
        return thread

    def finish(self, thread):
        thread.join(WAIT)
        self.assertFalse(thread.is_alive(), "the alarm didn't end")

    def test_closed_on_pc_quickly_sends_nothing(self):
        thread = self.start()
        self.popup.close_on_pc()
        self.finish(thread)
        self.assertEqual(self.telegram.alerts, [])
        self.assertEqual(self.telegram.retired, [(None, mock.ANY)])
        self.assertNotIn("close", self.popup.kinds())  # the popup closed itself

    def test_away_goes_to_telegram_at_once_and_closes_from_there(self):
        self.idle = 1000
        thread = self.start()
        self.assertTrue(wait_for(lambda: self.telegram.alerts))
        text, pending = self.telegram.alerts[0]
        self.assertIn("Toplantı", text)
        self.assertEqual(pending["yes"], alarm_ring.i18n.get("tr", "alarm_button_close"))
        self.telegram.press(yes=True)
        self.finish(thread)
        self.assertIn("close", self.popup.kinds())
        self.assertNotIn("silence", self.popup.kinds())
        self.assertEqual(self.telegram.forgotten, [pending])
        self.assertEqual(len(self.telegram.sent), 1)
        self.assertIn("kapatıldı", self.telegram.sent[0])

    def test_at_the_pc_telegram_only_after_it_rang_unanswered(self):
        thread = self.start()
        time.sleep(0.15)
        self.assertEqual(self.telegram.alerts, [])
        self.assertTrue(wait_for(lambda: self.telegram.alerts))
        self.popup.close_on_pc()
        self.finish(thread)
        pending = self.telegram.alerts[0][1]
        self.assertEqual(self.telegram.retired[0][0], pending)  # its buttons are taken off
        self.assertIn("PC'den", self.telegram.retired[0][1])

    def test_snooze_closes_and_rings_again(self):
        self.idle = 1000
        again = []
        with mock.patch.object(alarm_ring, "SNOOZE_MINUTES", 0.005), \
                mock.patch.object(alarm_ring, "ring", lambda name, sound: again.append((name, sound))):
            thread = self.start()
            self.assertTrue(wait_for(lambda: self.telegram.alerts))
            self.telegram.press(yes=False)
            self.finish(thread)
            self.assertIn("close", self.popup.kinds())
            self.assertIn("ertelendi", self.telegram.sent[0])
            self.assertTrue(wait_for(lambda: again))
        self.assertEqual(again, [("Toplantı", "sounds/alert.mp3")])

    def test_unanswered_alarm_goes_quiet_and_can_still_be_closed(self):
        self.idle = 1000
        thread = self.start()
        self.assertTrue(wait_for(lambda: "silence" in self.popup.kinds()))
        self.assertTrue(wait_for(lambda: self.telegram.sent))
        self.assertIn("sesini kapattım", self.telegram.sent[0])
        self.assertTrue(thread.is_alive())  # popup and buttons stay
        time.sleep(0.2)
        self.assertEqual(self.popup.kinds().count("silence"), 1)
        self.telegram.press(yes=True)
        self.finish(thread)
        self.assertIn("close", self.popup.kinds())

    def test_without_telegram_it_still_goes_quiet(self):
        self.telegram = FakeTelegram(set_up=False)
        self.idle = 1000
        thread = self.start()
        self.assertTrue(wait_for(lambda: "silence" in self.popup.kinds()))
        self.assertEqual(self.telegram.sent, [])
        self.popup.close_on_pc()
        self.finish(thread)


try:
    import tkinter as tk

    _probe = tk.Tk()
    _probe.destroy()
    TK_ERROR = None
except Exception as e:  # broken Tcl/Tk (the project's Python 3.11)
    TK_ERROR = e


@unittest.skipIf(TK_ERROR is not None, f"no working Tcl/Tk: {TK_ERROR}")
class PopupSilenceTest(unittest.TestCase):
    """alert.silence stops the sound once and keeps the window; closing then doesn't stop it again."""

    def test_silence_keeps_the_popup(self):
        mci = []
        root = tk.Tk()
        root.withdraw()
        try:
            with mock.patch.object(alert, "_mci", mci.append):
                alert.show_choice("t1", "Toplantı", "x.mp3", ["OK"], lambda i: None, close_choice=0)
                alert._poll_queue(root)
                self.assertIn("t1", alert._popups)
                alert.silence("t1")
                alert._poll_queue(root)
                self.assertEqual([c.split()[0] for c in mci], ["open", "play", "stop", "close"])
                self.assertIn("t1", alert._popups)
                alert.close("t1")
                alert._poll_queue(root)
                self.assertEqual(len(mci), 4)
                self.assertNotIn("t1", alert._popups)
                self.assertNotIn("t1", alert._silencers)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
