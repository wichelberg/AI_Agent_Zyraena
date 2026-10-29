"""Plans go to the phone's calendar as one .ics on Telegram, plus a PC reminder each (plan item 6).
Telegram and the alarm tools are fakes; files go to a temporary folder.

Run from the project folder: python -m unittest discover -s tests
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calendar_tools  # noqa: E402

PLAN = """INTRO
Durumlar: BEKLİYOR

----------------------------------------------------------------------------
1) Birinci iş
   Eklendi: 2026-10-20 · Durum: BEKLİYOR
----------------------------------------------------------------------------
Birinci gövde.

----------------------------------------------------------------------------
6) Plan + alarm isteği · Durum: BEKLİYOR
----------------------------------------------------------------------------
- Salı 2026-10-27 10:00 hoca toplantısı
"""


class FakeTelegram:
    def __init__(self, set_up=True):
        self.set_up, self.documents = set_up, []

    def send_document(self, data, filename, caption=""):
        self.documents.append((data, filename, caption))
        return self.set_up


class CalendarTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.telegram = FakeTelegram()
        self.reminders = []
        self.future = (datetime.now() + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        patches = [
            mock.patch.object(calendar_tools, "calendar_dir", lambda: self.dir),
            mock.patch.object(calendar_tools, "_telegram", lambda: self.telegram),
            mock.patch.object(calendar_tools.reminder_tools, "add_reminder",
                              lambda text, at=None, in_minutes=None, repeat="none":
                              self.reminders.append((text, at, repeat)) or f"set {at}"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def ics(self):
        return self.telegram.documents[-1][0].decode("utf-8")

    def test_meeting_goes_to_phone_and_pc(self):
        start = f"{self.future:%Y-%m-%d %H:%M}"
        result = calendar_tools.add_to_calendar([
            {"title": "Hoca toplantısı", "start": start, "minutes": 60, "alert_minutes_before": 30,
             "notes": "Sorular, materyal; son kontrol"},
        ])
        self.assertIn("Sent to Telegram", result)
        ics = self.ics()
        self.assertIn("SUMMARY:Hoca toplantısı", ics)
        self.assertIn("DESCRIPTION:Sorular\\, materyal\\; son kontrol", ics)
        self.assertIn("TRIGGER:-PT30M", ics)
        utc = self.future.astimezone(calendar_tools.timezone.utc)
        self.assertIn(f"DTSTART:{utc:%Y%m%dT%H%M%S}Z", ics)
        self.assertIn(f"DTEND:{utc + timedelta(minutes=60):%Y%m%dT%H%M%S}Z", ics)
        self.assertTrue(all(len(line.encode()) <= 75 for line in ics.split("\r\n")))
        self.assertEqual(self.reminders, [("Hoca toplantısı", f"{self.future - timedelta(minutes=30):%Y-%m-%d %H:%M}", "none")])
        self.assertEqual(len(list(self.dir.glob("*.ics"))), 1)

    def test_same_event_keeps_its_uid(self):
        start = f"{self.future:%Y-%m-%d %H:%M}"
        calendar_tools.add_to_calendar([{"title": "Kalk", "start": start}])
        first = [l for l in self.ics().split("\r\n") if l.startswith("UID:")]
        calendar_tools.add_to_calendar([{"title": "kalk ", "start": start}])
        second = [l for l in self.ics().split("\r\n") if l.startswith("UID:")]
        self.assertEqual(first, second)

    def test_no_guessing_times(self):
        for start in ("10:00", "salı 10:00", "", None):
            result = calendar_tools.add_to_calendar([{"title": "QDA ödevi", "start": start}])
            self.assertTrue(result.startswith("Couldn't add"), start)
        self.assertEqual(self.telegram.documents, [])
        self.assertEqual(self.reminders, [])

    def test_past_ones_are_skipped(self):
        past = datetime.now() - timedelta(hours=1)
        result = calendar_tools.add_to_calendar([
            {"title": "Eski", "start": f"{past:%Y-%m-%d %H:%M}"},
            {"title": "Yeni", "start": f"{self.future:%Y-%m-%d %H:%M}"},
        ])
        self.assertIn("Skipped (already past): Eski", result)
        self.assertNotIn("SUMMARY:Eski", self.ics())
        self.assertEqual([r[0] for r in self.reminders], ["Yeni"])

    def test_weekly_block_with_an_end(self):
        result = calendar_tools.add_to_calendar([
            {"title": "QDA blok", "start": f"{self.future:%Y-%m-%d %H:%M}", "minutes": 90, "repeat": "weekly",
             "repeat_until": f"{self.future + timedelta(days=14):%Y-%m-%d}"},
        ])
        self.assertIn("RRULE:FREQ=WEEKLY;UNTIL=", self.ics())
        self.assertIn("weekly until", result)
        self.assertEqual(self.reminders[0][2], "none")  # add_reminder can't stop, so the PC rings the first one

    def test_without_telegram_the_file_is_still_made(self):
        self.telegram = FakeTelegram(set_up=False)
        result = calendar_tools.add_to_calendar([{"title": "Kalk", "start": f"{self.future:%Y-%m-%d %H:%M}"}])
        self.assertIn("Telegram isn't connected", result)
        self.assertEqual(len(list(self.dir.glob("*.ics"))), 1)

    def test_long_text_is_folded(self):
        calendar_tools.add_to_calendar([{"title": "Hazırlık", "start": f"{self.future:%Y-%m-%d %H:%M}",
                                         "notes": "ğüşiöç " * 40}])
        lines = self.ics().split("\r\n")
        self.assertTrue(all(len(line.encode()) <= 75 for line in lines))
        description = next(i for i, l in enumerate(lines) if l.startswith("DESCRIPTION:"))
        self.assertTrue(lines[description + 1].startswith(" "))

    def test_read_plan_item(self):
        path = self.dir / "plan.txt"
        path.write_text(PLAN, encoding="utf-8")
        with mock.patch.object(calendar_tools, "DEV_PLAN_PATH", path):
            item = calendar_tools.read_plan_item(6)
            self.assertTrue(item.startswith("6) Plan + alarm isteği"))
            self.assertIn("hoca toplantısı", item)
            self.assertNotIn("Birinci", item)
            self.assertIn("Birinci gövde", calendar_tools.read_plan_item(1))
            self.assertIn("no item 3", calendar_tools.read_plan_item(3))

    def test_read_plan_item_from_finished(self):
        path = self.dir / "plan.txt"
        path.write_text(PLAN, encoding="utf-8")
        (self.dir / calendar_tools.DONE_PLAN_NAME).write_text(
            PLAN.replace("1) Birinci", "3) Üçüncü").replace("Birinci gövde", "Üçüncü gövde"), encoding="utf-8")
        with mock.patch.object(calendar_tools, "DEV_PLAN_PATH", path):
            self.assertIn("Üçüncü gövde", calendar_tools.read_plan_item(3))
            self.assertIn("Birinci gövde", calendar_tools.read_plan_item(1))
            self.assertIn("no item 4", calendar_tools.read_plan_item(4))

    def test_real_plan_has_item_6(self):
        if not calendar_tools.DEV_PLAN_PATH.exists():
            self.skipTest("no development plan on this PC")
        self.assertIn("Outlook", calendar_tools.read_plan_item(6))


if __name__ == "__main__":
    unittest.main()
