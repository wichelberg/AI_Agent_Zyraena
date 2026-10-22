"""Zyraena's Tk roots live on separate threads; one must never wait for another (2026-10-21: the app
hung twice, once when a message was sent from the text box during a game). tkpost.Mailbox.post must
return at once even while the owner thread is busy, and the pet's screen check must not wait on a
window of this process whose thread is busy.

Needs a working Tcl/Tk (py -3); without one the tests are skipped.
Run from the project folder: python -m unittest discover -s tests
"""
import ctypes
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import tkinter as tk

    _probe = tk.Tk()
    _probe.destroy()
    import desktop_pet  # noqa: E402
    import tkpost  # noqa: E402
    TK_ERROR = None
except Exception as e:  # broken Tcl/Tk (the project's Python 3.11)
    TK_ERROR = e
    tkpost = None

BUSY_SECONDS = 3


class OtherRoot:
    """A Tk root on its own thread with a visible, titled window, like the text box."""

    def __init__(self):
        ready = threading.Event()

        def run():
            self.root = tk.Tk()
            self.root.title("zyraena test window")
            self.root.geometry("200x120+20+20")
            self.mailbox = tkpost.Mailbox(self.root)
            self.root.update()
            self.hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            ready.set()
            self.root.mainloop()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        ready.wait(5)

    def close(self):
        self.mailbox.post(self.root.destroy)
        self.thread.join(5)


@unittest.skipIf(tkpost is None, f"no Tcl/Tk: {TK_ERROR}")
class TkThreadsTest(unittest.TestCase):
    def setUp(self):
        self.other = OtherRoot()

    def tearDown(self):
        self.other.close()

    def test_post_never_waits_and_keeps_order(self):
        done, order = threading.Event(), []
        self.other.mailbox.post(lambda: time.sleep(1))  # the owner thread is busy for a second
        started = time.monotonic()
        for i in range(3):
            self.other.mailbox.post(lambda i=i: order.append(i))
        self.other.mailbox.post(done.set)
        self.assertLess(time.monotonic() - started, 0.1)
        self.assertTrue(done.wait(5))
        self.assertEqual(order, [0, 1, 2])

    def test_a_failing_call_does_not_stop_the_queue(self):
        done = threading.Event()
        self.other.mailbox.post(lambda: 1 / 0)
        self.other.mailbox.post(done.set)
        self.assertTrue(done.wait(5))

    def test_screen_check_skips_own_windows_without_waiting(self):
        busy = threading.Event()

        def block():  # the window's thread stops answering messages, as when it waits for the pet
            busy.set()
            time.sleep(BUSY_SECONDS)

        self.other.mailbox.post(block)
        self.assertTrue(busy.wait(5))
        started = time.monotonic()
        desktop_pet._screen_context(ctypes.windll.user32.GetDesktopWindow())
        self.assertLess(time.monotonic() - started, BUSY_SECONDS / 2)


if __name__ == "__main__":
    unittest.main()
