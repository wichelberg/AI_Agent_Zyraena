"""credit_log and the panel's Credits tab: one entry per thing asked, the cost OpenRouter reports per
request, the balance before / after and their difference, overlapping entries, Tavily, the tab's list
and details. The balances are fakes and the log is a temporary database: no network, no real log.

The window tests need a working Tcl/Tk (py -3); without one they are skipped.
Run from the project folder: python -m unittest discover -s tests
"""
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import credit_log  # noqa: E402


class Balances:
    """A fake balance that goes down as the requests are 'billed'."""

    def __init__(self, start):
        self.value, self.reads = start, 0

    def __call__(self):
        self.reads += 1
        return self.value


class LogTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="zyraena_credit_test_"))
        self.ledger = credit_log.Ledger(self.folder / "log.sqlite")
        self.balance = Balances(10.0)
        self.tavily = Balances(900)
        self.old = dict(credit_log._state), credit_log.AFTER_DELAYS
        credit_log._state.update(ledger=self.ledger, balance=self.balance, tavily=self.tavily, open=set(), listeners=[])
        credit_log.AFTER_DELAYS = (0, 0)

    def tearDown(self):
        credit_log._state.clear()
        credit_log._state.update(self.old[0])
        credit_log.AFTER_DELAYS = self.old[1]
        self.ledger.close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def settled(self, count=1, timeout=5):
        end = time.time() + timeout
        while time.time() < end:
            rows = self.ledger.entries()
            if len(rows) >= count and all(r.after is not None for r in rows) and not credit_log._state["open"]:
                return rows
            time.sleep(0.02)
        self.fail(f"not settled: {self.ledger.entries()}")

    def bill(self, cost, model="google/gemini-3.7-flash", tools=()):
        self.balance.value -= cost
        credit_log.record(model, {"cost": cost, "prompt_tokens": 1200, "completion_tokens": 80})
        for tool in tools:
            credit_log.note_tool(tool)

    def test_one_message_with_two_rounds(self):
        with credit_log.activity("box", "  hava   nasıl\n yarın? "):
            self.bill(0.004, tools=["web_search"])
            self.bill(0.006)
        (e,) = self.settled()
        self.assertEqual((e.source, e.what, e.requests), ("box", "hava nasıl yarın?", 2))
        self.assertAlmostEqual(e.cost, 0.01)
        self.assertEqual(e.before, 10.0)
        self.assertAlmostEqual(e.after, 9.99)
        self.assertAlmostEqual(e.difference, 0.01)
        self.assertEqual([r["tools"] for r in e.rounds], [["web_search"], []])
        self.assertEqual(e.rounds[0]["prompt_tokens"], 1200)
        self.assertFalse(e.overlap)

    def test_nested_activity_joins_the_outer_one(self):
        with credit_log.activity("voice", "turn"):
            with credit_log.activity("other", "inner"):
                self.bill(0.002)
            self.bill(0.003)
        (e,) = self.settled()
        self.assertEqual((e.source, e.requests), ("voice", 2))

    def test_nothing_paid_no_entry(self):
        with credit_log.activity("box", "/mode"):
            pass
        time.sleep(0.1)
        self.assertEqual(self.ledger.entries(), [])
        self.assertEqual(credit_log._state["open"], set())

    def test_request_outside_an_activity(self):
        self.bill(0.001, model="x/model")
        (e,) = self.settled()
        self.assertEqual((e.source, e.what, e.before), ("other", "x/model", None))
        self.assertIsNone(e.difference)

    def test_late_balance_is_read_again(self):
        reads = iter([10.0, 10.0, 9.995])  # before, after (OpenRouter hasn't caught up), after again
        credit_log._state["balance"] = lambda: next(reads)
        with credit_log.activity("telegram", "x"):
            credit_log.record("m", {"cost": 0.005})
        (e,) = self.settled()
        self.assertAlmostEqual(e.difference, 0.005)
        self.assertIsNone(next(reads, None))  # all three were read

    def test_overlapping_entries_are_marked(self):
        started, release = threading.Event(), threading.Event()

        def other():
            with credit_log.activity("telegram", "other"):
                started.set()
                release.wait(5)
                self.bill(0.002)

        t = threading.Thread(target=other)
        t.start()
        started.wait(5)
        with credit_log.activity("box", "mine"):
            self.bill(0.003)
        release.set()
        t.join()
        rows = self.settled(2)
        self.assertEqual({r.what: r.overlap for r in rows}, {"other": True, "mine": True})

    def test_tavily_before_and_after(self):
        with credit_log.activity("box", "search"):
            credit_log.before_search()
            self.tavily.value -= 1
            credit_log.before_search()
            self.tavily.value -= 1
            self.bill(0.001, tools=["web_search", "web_search"])
        (e,) = self.settled()
        self.assertEqual((e.searches, e.tavily_before, e.tavily_after), (2, 900, 898))

    def test_totals_and_filters(self):
        for source, cost in (("box", 0.01), ("telegram", 0.02), ("box", 0.03)):
            with credit_log.activity(source, source):
                self.bill(cost)
        self.settled(3)
        totals = self.ledger.totals()
        self.assertEqual(totals["box"][0], 2)
        self.assertAlmostEqual(totals["box"][1], 0.04)
        self.assertEqual([e.source for e in self.ledger.entries(source="telegram")], ["telegram"])
        self.assertEqual(self.ledger.entries(since=time.time() + 60), [])
        self.assertEqual([e.what for e in self.ledger.entries()], ["box", "telegram", "box"][::-1])  # newest first

    def test_unknown_source_is_other(self):
        with credit_log.activity("nonsense", "x"):
            self.bill(0.001)
        self.assertEqual(self.settled()[0].source, "other")


try:
    import tkinter as tk

    _probe = tk.Tk()
    _probe.destroy()
    import chat_box  # noqa: E402
    import control_panel  # noqa: E402
    import credit_panel  # noqa: E402
    TK_ERROR = None
except Exception as e:  # broken Tcl/Tk (the project's Python 3.11)
    TK_ERROR = e
    control_panel = None


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


class FakeLog:
    """credit_log's face to the tab, over a temporary ledger."""

    def __init__(self, ledger):
        self.led, self.listeners = ledger, []

    def ledger(self):
        return self.led

    def listen(self, fn):
        self.listeners.append(fn)
        return lambda: self.listeners.remove(fn)


class CreditTabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if control_panel is None:
            raise unittest.SkipTest(f"no Tcl/Tk: {TK_ERROR}")

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="zyraena_credit_tab_test_"))
        self.ledger = credit_log.Ledger(self.folder / "log.sqlite")
        now = time.time()
        rows = [
            credit_log.Entry(now - 60, "box", "hava nasıl", cost=0.0123, requests=2, before=10.0, after=9.9877,
                             rounds=[{"model": "google/gemini-3.7-flash", "cost": 0.01, "prompt_tokens": 1500,
                                      "completion_tokens": 90, "tools": ["web_search"]},
                                     {"model": "google/gemini-3.7-flash", "cost": 0.0023, "prompt_tokens": 2100,
                                      "completion_tokens": 200, "tools": []}],
                             searches=1, tavily_before=900, tavily_after=899),
            credit_log.Entry(now - 30, "telegram", "ekran", cost=0.004, requests=1, before=9.9877, after=None,
                             rounds=[{"model": "anthropic/claude-haiku-5.5", "cost": 0.004, "prompt_tokens": 800,
                                      "completion_tokens": 50, "tools": ["look_at_screen"]}]),
            credit_log.Entry(now - 3 * 86400, "disk", "", cost=0.001, requests=1, before=11.0, after=10.9, overlap=True,
                             rounds=[{"model": "google/gemini-3.7-flash", "cost": 0.001, "prompt_tokens": 400,
                                      "completion_tokens": 300, "tools": []}]),
        ]
        for e in rows:
            e.finished = e.started + 2
            e.id = self.ledger.insert(e)
        self.log = FakeLog(self.ledger)

    def tearDown(self):
        if control_panel.is_open():
            on_ui(lambda: control_panel._state["panel"].close())
        self.ledger.close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def open(self, tab="credits"):
        control_panel.show(tab, "tr", lambda: True, lambda: True, lambda: 1.0, lambda: ("unknown", None), None,
                           self.log)
        self.assertTrue(wait_for(control_panel.is_open))
        return control_panel._state["panel"]

    def test_button_on_the_general_tab_opens_it(self):
        panel = self.open("general")
        self.assertEqual(on_ui(lambda: panel.credits_button.cget("text")), "API kredi kaydı")
        on_ui(panel.credits_button.invoke)
        self.assertTrue(wait_for(lambda: panel.tab == "credits" and panel.credit_tab is not None))
        self.assertNotIn("disk", panel.tab_buttons)  # no disk service: no Disk tab

    def test_rows_and_summary(self):
        tab = self.open().credit_tab
        rows = on_ui(lambda: [tab.tree.item(r, "values") for r in tab.tree.get_children()])
        self.assertEqual([r[1] for r in rows], ["Telegram", "Yazı kutusu", "Disk taraması"])  # newest first
        box = rows[1]
        self.assertEqual((box[2], box[4], box[5], box[6], box[7], box[8]),
                         ("hava nasıl", "2", "$0.0123", "$10.0000", "$9.9877", "$0.0123"))
        self.assertEqual(rows[0][8], "bekleniyor…")
        self.assertEqual(rows[2][2], "—")
        self.assertTrue(rows[2][8].endswith("*"))  # overlapping
        summary = on_ui(lambda: tab.summary.cget("text"))
        self.assertIn("Bugün: $0.0163 (2)", summary)
        self.assertIn("Son 7 gün: $0.0173 (3)", summary)

    def test_details_of_a_row(self):
        tab = self.open().credit_tab

        def pick():
            row = next(r for r, e in tab.entries_by_row.items() if e.source == "box")
            tab.tree.selection_set(row)
        on_ui(pick)
        self.assertTrue(wait_for(lambda: "giriş" in tab.detail.cget("text")))
        text = on_ui(lambda: tab.detail.cget("text"))
        self.assertIn("1. google/gemini-3.7-flash · 1500 giriş + 90 çıkış token · $0.0100 · araçlar: web_search", text)
        self.assertIn("Bildirilen maliyet $0.0123 · bakiye $10.0000 → $9.9877 (fark $0.0123)", text)
        self.assertIn("Tavily: 1 arama · kredi 900 → 899 (1 harcandı)", text)

    def test_filters(self):
        tab = self.open().credit_tab
        on_ui(lambda: (tab.source_var.set("Telegram"), tab.refresh()))
        self.assertEqual(on_ui(lambda: [e.source for e in tab.entries_by_row.values()]), ["telegram"])
        on_ui(lambda: (tab.source_var.set("Tüm kaynaklar"), tab.period_var.set("Bugün"), tab.refresh()))
        self.assertEqual(on_ui(lambda: len(tab.entries_by_row)), 2)

    def test_new_entry_shows_up(self):
        tab = self.open().credit_tab
        e = credit_log.Entry(time.time(), "voice", "selam", cost=0.002, requests=1, before=9.0, after=8.998)
        e.id = self.ledger.insert(e)
        for fn in list(self.log.listeners):
            fn()
        self.assertTrue(wait_for(lambda: len(tab.entries_by_row) == 4))

    def test_variables_belong_to_the_panel(self):
        tab = self.open().credit_tab
        self.assertTrue(on_ui(lambda: tab.period_var._tk is tab.win.tk and tab.source_var._tk is tab.win.tk))


if __name__ == "__main__":
    unittest.main()
