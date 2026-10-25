"""User Care: Zyraena looks after the owner. A mood layer on top of her persona (not a second persona):
breaks, water, sleep at night, and her mood toward the owner, which goes into her system prompt (lady
mode) with every message, together with the last events and their reasons.

- Breaks: every `break.every_minutes` of active use a prompt (Take a break / Snooze). Snoozes in a row
  depend on the mood (happy 2, normal 1, angry 0); with none left the next break is forced: a warning
  `forced_warning_minutes` before, then a fullscreen window with a countdown and no close button (an
  emergency exit with a written reason). No input blocking. Breaks end with a Telegram message.
- Away: no keyboard/mouse input for `afk_minutes` stops the timers (unless a fullscreen video plays);
  `afk_break_minutes` away, or a sleeping PC (a jump in time between two checks), counts as a break.
- Night (start_hour..end_hour): a sleep warning every hour (points by hour: warning_points); at check_hour she opens the text box and asks
  why the owner is still up. The answer is sorted by the assistant model (work, exam, emergency, can't
  sleep, whim); a good reason (at most excuses_per_week) stops the warnings for the night, "can't sleep"
  never shuts down, anything else costs night_refused points and starts a step-by-step shutdown.
- Shutdown: a "save your work" warning, a countdown, the last `final_seconds` fullscreen, always
  cancellable (the window, Telegram /iptal, `shutdown /a`). The protection list (care_guard) is checked at
  the start and right before; while it holds, a forced break comes instead. dry_run (the default) only logs.
- Every first morning: yesterday's summary in the text box.
- Affection: how close she is to the owner, apart from the mood (relationship.py moves it after each
  conversation). Mood level x affection level picks one of nine relationship styles for her prompt.
- Drop-in: now and then, while the owner works, she says something on her own in the pet's bubble
  (about the window in front; a click on the bubble opens the text box with it).

Everything is in config.json ("user_care"; missing keys are filled in from DEFAULTS and written back).
The state (mood, events, timers, weekly excuses) is in %LOCALAPPDATA%\\Zyraena\\care.

Debug: `python user_care.py --debug --at 02:58 --active 178 --mood 25 --speed 30` runs User Care alone
on a fake clock (own state file, fresh each run unless --keep; never shuts down) with the panel's Care
tab open for its buttons.
"""
import argparse
import copy
import json
import math
import os
import random
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import care_guard
import config_loader
import i18n
import system_tools

DEFAULTS = {
    "enabled": True,
    "dry_run": True,  # the owner turns real shutdowns on when ready
    "afk_minutes": 5,
    "sleep_gap_seconds": 120,  # two checks this far apart: the PC slept
    "break": {"every_minutes": 60, "answer_minutes": 5, "normal_minutes": 10, "forced_minutes": 10,
              "forced_warning_minutes": 2, "afk_break_minutes": 10},
    "water": {"every_minutes": 20, "later_minutes": 15, "answer_minutes": 5},
    "night": {"start_hour": 0, "end_hour": 6, "check_hour": 3, "answer_minutes": 10, "excuses_per_week": 2,
              "bedtime_gap_hours": 4, "bedtime_from_hour": 22,
              # Sleep warning points by hour (owner, 2026-10-25); hours not listed use mood.points.sleep_warning.
              "warning_points": {"00": 0, "01": -5, "02": -15}},
    "shutdown": {"warning_minutes": 5, "angry_warning_minutes": 2, "final_seconds": 60},
    # Rough on purpose (owner, 2026-10-24): good habits barely lift her mood, slips cost a lot.
    "mood": {"start": 25, "happy_from": 70, "angry_to": 30, "drift_per_hour": 1,
             "snoozes": {"happy": 2, "normal": 1, "angry": 0},
             "points": {"break": 5, "snooze": -15, "unanswered": -20, "forced_done": 5, "emergency_exit": -30,
                        "water": 1, "water_later": -3, "sleep_warning": -15, "on_time_bed": 10, "peace": 5,
                        "shutdown_cancel": -30, "night_refused": -30}},
    "peace": {"min_hours": 2, "per_day": 2},
    # Affection (owner, 2026-10-25): how close she is to them, apart from the mood. No drift; only the
    # look at each finished conversation (relationship.py) moves it, within these limits.
    "affection": {"start": 50, "high_from": 70, "low_to": 30, "max_per_chat": 5, "up_per_day": 8,
                  "down_per_day": 15},
    # She comes by on her own: a free check every check_minutes, then one persona call that may say SKIP.
    # Only the window title is sent, never a screenshot. Off: Ctrl+F1 → Bakım.
    "drop_in": {"enabled": True, "check_minutes": 10, "chance": 0.3, "min_gap_minutes": 120,
                "active_minutes": 15, "after_chat_minutes": 30, "bubble_seconds": 40,
                "per_day": {"high": 4, "normal": 2, "low": 1},
                "skip_programs": ["keepass.exe", "keepassxc.exe", "bitwarden.exe", "1password.exe"]},
    "protect": {
        "programs": ["claude.exe", "blender.exe", "Unity.exe", "VideoEditorPlus.exe", "rsession.exe", "yt-dlp.exe"],
        "gpu": {"enabled": True, "percent": 80, "minutes": 3, "compute_percent": 20},
        "terminal_jobs": {"enabled": True, "cpu_percent": 25, "minutes": 3},
        "training": {"enabled": True, "patterns": ["Wichelberg_VoiceChanger\\data\\egitim", "RNNModel",
                                                    "Voice_Changer_Production", "train_stt.py"]},
        "zyraena_runs": {"enabled": True},
        "busy_cpu": {"enabled": True, "percent": 40, "minutes": 5},
        "downloads": {"enabled": True, "mb_per_second": 5, "minutes": 3, "folder": "~/Downloads"},
    },
    "debug": {"enabled": False, "at": "", "active_minutes": 0, "mood": None, "speed": 1, "telegram": False,
              "keep": False},
}

CATEGORIES = ("work", "exam", "emergency", "cant_sleep", "whim")
GOOD_REASONS = ("work", "exam", "emergency")
TONES = ("happy", "normal", "angry", "worried")
RECENT_KEPT = 30
PROMPT_EVENTS = 5
GRUDGE_HOURS = 24  # an emergency exit's reason stays in her prompt this long, even when older than 5 events
SAVE_SECONDS = 60
TICK_SECONDS = 5
GUARD_SECONDS = 60
OFFLINE_DRIFT_HOURS = 48
EXTERNAL_CANCEL_SECONDS = 90  # still running this long after a real shutdown was due: someone ran shutdown /a


def _log(text):
    """print, but a console that can't show Turkish letters (cp1252) gets them replaced instead of failing."""
    try:
        print(f"User care: {text}")
    except UnicodeEncodeError:
        print(f"User care: {text}".encode("ascii", "replace").decode("ascii"))


def care_dir():
    custom = os.environ.get("ZYRAENA_CARE_HOME", "").strip()
    return Path(custom) if custom else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Zyraena" / "care"


# --- config ---------------------------------------------------------------------------------------------

def merged(defaults, given):
    """defaults with `given`'s values wherever the keys match (dicts merged key by key)."""
    out = copy.deepcopy(defaults)
    for key, value in (given or {}).items():
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = merged(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path=None):
    """The user_care section of config.json, with defaults for what's missing. Writes the full section back
    when keys were missing, so the owner sees every setting there."""
    path = Path(path or config_loader.CONFIG_PATH)
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"events": []}
    except (OSError, ValueError) as e:
        _log(f"config.json unreadable ({e}), using the defaults")
        return copy.deepcopy(DEFAULTS)
    cfg = merged(DEFAULTS, raw.get("user_care"))
    if raw.get("user_care") != cfg:
        save_config(cfg, path)
    return cfg


def save_config(cfg, path=None):
    """Writes the user_care section into config.json, keeping everything else (the alarms) as it is."""
    import reminder_tools  # its lock: the alarm tools write the same file

    path = Path(path or config_loader.CONFIG_PATH)
    with reminder_tools._lock:
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"events": []}
        except (OSError, ValueError):
            return
        cfg = dict(cfg, debug=(raw.get("user_care") or {}).get("debug", cfg["debug"]))  # never a debug run's
        raw["user_care"] = cfg
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=4), encoding="utf-8")
        os.replace(tmp, path)


# --- clocks ---------------------------------------------------------------------------------------------

class Clock:
    """The real clock. time.monotonic() keeps counting while the PC sleeps (GetTickCount64)."""
    fake = False
    speed = 1.0

    def now(self):
        return datetime.now()

    def mono(self):
        return time.monotonic()

    def real_seconds(self, seconds):
        return seconds


class FakeClock(Clock):
    """Debug: starts at `at`, runs `speed` times faster; advance() jumps without it looking like sleep."""
    fake = True

    def __init__(self, at=None, speed=1.0):
        self.speed = max(0.01, float(speed))
        self._real = time.monotonic()
        self._start = at or datetime.now()
        self._offset = 0.0

    def mono(self):
        return (time.monotonic() - self._real) * self.speed + self._offset

    def now(self):
        return self._start + timedelta(seconds=self.mono())

    def advance(self, seconds):
        self._offset += seconds

    def real_seconds(self, seconds):
        return seconds / self.speed


# --- state ----------------------------------------------------------------------------------------------

def new_state(cfg):
    return {"mood": float(cfg["mood"]["start"]), "active": 0.0, "cycle": 0.0, "snoozes": 0, "water": 0.0,
            "water_due": cfg["water"]["every_minutes"] * 60.0, "last_seen": None, "last_input": None,
            "night": {}, "excuses": [], "peace": [], "summary_day": None, "slept_night": None,
            "forced_until": None, "recent": [], "affection": float(cfg["affection"]["start"]),
            "affection_day": {}, "drop_in": {}, "last_chat": None}


class Store:
    def __init__(self, folder, suffix=""):
        self.folder = Path(folder)
        self.state_path = self.folder / f"state{suffix}.json"
        self.events_path = self.folder / f"events{suffix}.jsonl"

    def load(self, cfg):
        state = new_state(cfg)
        try:
            state.update(json.loads(self.state_path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            _log(f"state unreadable ({e}), starting fresh")
        return state

    def save(self, state):
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def append(self, event):
        self.folder.mkdir(parents=True, exist_ok=True)
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def events(self):
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out


def _iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


def _dt(text):
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


# --- what's on the screen -------------------------------------------------------------------------------

def fullscreen_video():
    """True when the window in front covers its whole monitor and its program is playing sound (a video;
    a game would have input anyway). A maximized window with a title bar doesn't count."""
    import ctypes
    from ctypes import wintypes

    import desktop_pet

    user32 = desktop_pet.user32
    fg = user32.GetForegroundWindow()
    if not fg:
        return False
    name = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(fg, name, 64)
    if name.value in desktop_pet.DESKTOP_CLASSES:
        return False
    if user32.IsZoomed(fg) and user32.GetWindowLongW(fg, desktop_pet.GWL_STYLE) & desktop_pet.WS_CAPTION == \
            desktop_pet.WS_CAPTION:
        return False
    info = desktop_pet.MONITORINFO(cbSize=ctypes.sizeof(desktop_pet.MONITORINFO))
    user32.GetMonitorInfoW(user32.MonitorFromWindow(fg, desktop_pet.MONITOR_DEFAULTTONEAREST), ctypes.byref(info))
    rect = wintypes.RECT()
    user32.GetWindowRect(fg, ctypes.byref(rect))
    m = info.rcMonitor
    if not (rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom):
        return False
    _, exe = desktop_pet._process_name(fg)
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities

        comtypes.CoInitialize()
        # Browsers play sound from a helper process of the same exe, so the name is compared, not the PID.
        return any(s.State == 1 and s.Process and s.Process.name().lower() == exe
                   for s in AudioUtilities.GetAllSessions())
    except Exception:
        return False


# --- the engine -----------------------------------------------------------------------------------------

class Care:
    """All rules. tick() runs every few seconds on User Care's thread; the windows' answers come from the
    Tk thread; both take the lock. `ui` (care_windows) never waits, so holding the lock while calling it
    is safe. `persona(instruction, what)` -> Zyraena's text (slow: always on its own thread),
    `classify(prompt, what)` -> the assistant model's answer, `notify(text)` -> Telegram,
    `chat(text)` -> opens the text box with her line, `screen()` -> (exe, window title) of what the owner
    is using, or None when she can't drop in now, `drop_in(text)` -> shows her drop-in line."""

    def __init__(self, cfg, store, clock, ui, guard, persona=None, classify=None, notify=None, chat=None,
                 lang=lambda: "tr", idle=None, video=None, config_path=None, screen=None, drop_in=None):
        self.cfg, self.store, self.clock, self.ui, self.guard = cfg, store, clock, ui, guard
        self.persona, self.classify = persona, classify
        self.notify = notify or print
        self.chat = chat or (lambda text: None)
        self.screen = screen or (lambda: None)
        self.drop_in_say = drop_in or (lambda text: None)
        self._drop_check = None  # when the next drop-in check is due
        self.lang = lang
        self.idle = idle or system_tools.idle_seconds
        self.video = video or fullscreen_video
        self.config_path = config_path
        self.lock = threading.RLock()
        self.state = store.load(cfg)
        self.prompts = {}        # kind ("break"/"water") -> {"since": datetime, "input": bool}
        self.forced_at = None    # the forced break's start, once its warning was shown
        self.breaking = None     # {"kind": "normal"/"forced", "until": datetime}
        self.shutdown = None     # the step-by-step shutdown in progress
        self.away_counted = False
        self.protection = []     # the guard's last answer, for the panel
        self._last_mono = None
        self._last_save = 0.0
        self._dirty = False
        self._config_mtime = self._mtime()
        self._running = False

    # --- helpers --------------------------------------------------------------------------------------

    def t(self, key, **kw):
        return i18n.get(self.lang(), key, **kw)

    def level(self, mood=None):
        mood = self.state["mood"] if mood is None else mood
        m = self.cfg["mood"]
        return "happy" if mood >= m["happy_from"] else "angry" if mood <= m["angry_to"] else "normal"

    def affection_level(self, affection=None):
        affection = self.state["affection"] if affection is None else affection
        a = self.cfg["affection"]
        return "high" if affection >= a["high_from"] else "low" if affection <= a["low_to"] else "normal"

    def relation(self):
        """The relationship style's key: mood level x affection level, e.g. "normal_high"."""
        return f"{self.level()}_{self.affection_level()}"

    def night_hours(self):
        n = self.cfg["night"]
        return [(n["start_hour"] + i) % 24 for i in range((n["end_hour"] - n["start_hour"]) % 24 or 24)]

    def in_night(self, now):
        return now.hour in self.night_hours()

    def night_id(self, when):
        return (when - timedelta(hours=self.cfg["night"]["end_hour"])).date().isoformat()

    def day_key(self, when):
        return (when - timedelta(hours=self.cfg["night"]["end_hour"])).date().isoformat()

    def tone(self, now=None):
        """How she sounds: by mood, but worried instead of angry at night."""
        level = self.level()
        return "worried" if level == "angry" and self.in_night(now or self.clock.now()) else level

    def toned(self, key, now=None, **kw):
        """One of her lines for key in her tone (each line of the text is a variant); {user} is the owner."""
        text = self.t(f"{key}_{self.tone(now)}", user=i18n.user_name(), **kw)
        lines = [line for line in text.split("\n") if line.strip()]
        return random.choice(lines)

    def _snooze_rights(self):
        return self.cfg["mood"]["snoozes"][self.level()]

    def _next_is_forced(self):
        return self.state["snoozes"] >= self._snooze_rights()

    def _points(self, name):
        return self.cfg["mood"]["points"].get(name, 0)

    def dry_run(self):
        return self.cfg["dry_run"] or self.clock.fake

    def _mtime(self):
        try:
            return Path(self.config_path).stat().st_mtime if self.config_path else None
        except OSError:
            return None

    # --- events ---------------------------------------------------------------------------------------

    def event(self, kind, points=0, reason="", now=None, day=None, **data):
        now = now or self.clock.now()
        if points:
            self.state["mood"] = min(100.0, max(0.0, self.state["mood"] + points))
        entry = {"t": _iso(now), "day": day or self.day_key(now), "kind": kind, "points": points,
                 "mood": round(self.state["mood"]), "reason": reason, **data}
        self.state["recent"] = (self.state["recent"] + [entry])[-RECENT_KEPT:]
        try:
            self.store.append(entry)
        except OSError as e:
            _log(f"couldn't write the event log: {e}")
        _log(f"{kind} {points:+d} -> mood {entry['mood']}" + (f" ({reason})" if reason else ""))
        self._dirty = True
        return entry

    def describe(self, entry, lang=None):
        lang = lang or self.lang()
        data = {k: v for k, v in entry.items() if k not in ("t", "day", "kind", "points", "mood", "reason")}
        if "category" in data:
            data["category"] = i18n.get(lang, "care_cat_" + data["category"])
        if "verdict" in data:
            data["verdict"] = i18n.get(lang, "care_verdict_" + data["verdict"])
        try:
            text = i18n.get(lang, "care_ev_" + entry["kind"], **data)
        except (KeyError, IndexError):
            text = entry["kind"]
        if entry.get("reason"):
            text += i18n.get(lang, "care_ev_reason", reason=entry["reason"])
        if entry.get("points"):
            text += f" ({entry['points']:+d})"
        return text

    # --- the loop -------------------------------------------------------------------------------------

    def start(self):
        """Catches up with the time Zyraena was off, then runs the loop on its own thread."""
        with self.lock:
            now = self.clock.now()
            last = _dt(self.state["last_seen"])
            if last is not None and now > last:
                gap = (now - last).total_seconds()
                self._drift(min(gap, OFFLINE_DRIFT_HOURS * 3600))
                if gap >= self.cfg["break"]["afk_break_minutes"] * 60:
                    self._reset_cycle()
            forced = _dt(self.state.get("forced_until"))
            if forced is not None and forced > now:  # restarted during a forced break: it goes on
                self._start_forced(now, "restart", until=forced)
            self.state["last_seen"] = _iso(now)
            self._save(force=True)
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._guard_loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self.tick()
            except Exception as e:  # one bad tick must not end User Care
                _log(f"tick failed: {e!r}")
            time.sleep(TICK_SECONDS if not self.clock.fake else max(0.25, min(TICK_SECONDS, 30 / self.clock.speed)))

    def _guard_loop(self):
        while self._running:
            try:
                self.guard.sample(self.cfg["protect"])
                found = self.guard.reasons(self.cfg["protect"])
                with self.lock:
                    self.protection = found
            except Exception as e:
                _log(f"protection check failed: {e!r}")
            time.sleep(GUARD_SECONDS)

    def tick(self, idle=None, video=None):
        """One check. idle/video are for tests (else the real input idle time and fullscreen video)."""
        mono = self.clock.mono()
        idle = self.idle() if idle is None else idle
        with self.lock:
            self._reload_config()
            if not self.cfg["enabled"]:
                self._last_mono = mono
                return
            now = self.clock.now()
            dt = 0.0 if self._last_mono is None else max(0.0, mono - self._last_mono)
            self._last_mono = mono
            if dt >= self.cfg["sleep_gap_seconds"]:
                self._slept(now, dt)
                dt = 0.0
            self._drift(dt)
            away = idle >= self.cfg["afk_minutes"] * 60
            if away and video is None:
                video = self.video()
            if away and video:
                away, idle = False, 0
            self._input(now, idle)
            self._prompt_timeouts(now, idle)
            if away:
                if (idle >= self.cfg["break"]["afk_break_minutes"] * 60 and not self.away_counted
                        and self.breaking is None):
                    self.away_counted = True
                    self._reset_cycle(close_prompts=True)
                    self.event("afk_break", now=now, minutes=int(idle // 60))
            else:
                self.away_counted = False
                self._morning(now)
                if self.breaking is None and self.shutdown is None:
                    self.state["active"] += dt
                    self.state["cycle"] += dt if "break" not in self.prompts else 0
                    self.state["water"] += dt if "water" not in self.prompts else 0
                    self._breaks(now)
                    self._water(now)
                    self._drop_in(now, idle)
            self._night(now, away, dt)
            self._shutdown_step(now)
            self.state["last_seen"] = _iso(now)
            self._save()

    def _reload_config(self):
        mtime = self._mtime()
        if mtime is not None and mtime != self._config_mtime:
            self._config_mtime = mtime
            debug = self.cfg["debug"]
            self.cfg = load_config(self.config_path)
            self.cfg["debug"] = debug  # a debug run keeps its own settings

    def _save(self, force=False):
        if force or self._dirty or time.monotonic() - self._last_save >= SAVE_SECONDS:
            try:
                self.store.save(self.state)
            except OSError as e:
                _log(f"couldn't save the state: {e}")
            self._last_save = time.monotonic()
            self._dirty = False

    def _drift(self, seconds):
        """The mood goes back toward mood.start by drift_per_hour."""
        mood, base = self.state["mood"], self.cfg["mood"]["start"]
        step = self.cfg["mood"]["drift_per_hour"] * seconds / 3600
        self.state["mood"] = mood + math.copysign(min(step, abs(base - mood)), base - mood) if mood != base else mood

    def _reset_cycle(self, close_prompts=False):
        self.state.update(active=0.0, cycle=0.0, snoozes=0)
        self.forced_at = None
        if close_prompts and "break" in self.prompts:
            self.prompts.pop("break")
            self.ui.close("break")
            self.ui.close("notice")
        self._dirty = True

    def _slept(self, now, seconds):
        """The PC slept (or Zyraena was frozen) for `seconds`: a break, no points lost."""
        self.event("sleep", now=now, minutes=int(seconds // 60))
        self.away_counted = True
        for kind in list(self.prompts):
            self.prompts.pop(kind)
            self.ui.close(kind)
        self._reset_cycle()
        if self.shutdown is not None and not self.shutdown["final"]:  # the owner gets the full warning again
            self.shutdown["deadline"] = now + timedelta(seconds=self._warning_seconds())

    def _input(self, now, idle):
        """Notes the last input; a long gap in it starting late in the evening is when they went to bed."""
        at = now - timedelta(seconds=idle)
        last = _dt(self.state["last_input"])
        n = self.cfg["night"]
        if last is not None and (at - last).total_seconds() >= n["bedtime_gap_hours"] * 3600:
            self._went_to_bed(last, now)
        if last is None or at > last:
            self.state["last_input"] = _iso(at)
        for prompt in self.prompts.values():
            if at > prompt["since"]:
                prompt["input"] = True

    def _went_to_bed(self, at, now):
        n = self.cfg["night"]
        evening = [(n["bedtime_from_hour"] + i) % 24 for i in range((n["end_hour"] - n["bedtime_from_hour"]) % 24)]
        if at.hour not in evening:
            return
        self.state["slept_night"] = self.night_id(at)
        self.event("bedtime", now=now, day=self.day_key(at), time=f"{at:%H:%M}")
        if n["check_hour"] not in evening or evening.index(at.hour) < evening.index(n["check_hour"]):
            self.event("on_time_bed", self._points("on_time_bed"), now=now, day=self.day_key(at),
                       time=f"{at:%H:%M}")

    # --- breaks ---------------------------------------------------------------------------------------

    def _breaks(self, now):
        b = self.cfg["break"]
        every, warn = b["every_minutes"] * 60, b["forced_warning_minutes"] * 60
        cycle = self.state["cycle"]
        if self.forced_at is not None:
            if now >= self.forced_at:
                self._start_forced(now, "cycle")
            return
        if "break" in self.prompts:
            return
        if cycle >= every - warn and self._next_is_forced():
            self.forced_at = now + timedelta(seconds=max(warn if cycle >= every else every - cycle, 0))
            self.event("forced_warning", now=now, minutes=b["forced_warning_minutes"])
            self.ui.notice("forced", self.t("care_forced_warning_title"),
                           self.t("care_forced_warning", minutes=b["forced_warning_minutes"]),
                           self.clock.real_seconds(warn), sound=True)
        elif cycle >= every:
            self.prompts["break"] = {"since": now, "input": False}
            self.ui.prompt("break", self.t("care_break_title"),
                           self.toned("care_break_prompt", now, minutes=int(self.state["active"] // 60)),
                           [(self.t("care_take_break"), "break"), (self.t("care_snooze"), "snooze")],
                           self.answer_break, sound=True)

    def answer_break(self, value):
        """The break prompt's buttons (Tk thread)."""
        with self.lock:
            if self.prompts.pop("break", None) is None:
                return
            now = self.clock.now()
            if value == "break":
                self.event("break_taken", self._points("break"), now=now)
                self._reset_cycle()
                self._start_normal(now)
            else:
                self.state["snoozes"] += 1
                self.state["cycle"] = 0.0
                self.event("snooze", self._points("snooze"), now=now, count=self.state["snoozes"])
            self._save(force=True)

    def _prompt_timeouts(self, now, idle):
        b, w = self.cfg["break"], self.cfg["water"]
        prompt = self.prompts.get("break")
        # Unanswered only counts when they used the PC while it was open; if they're simply away, it
        # stays until they come back (or becomes an away break).
        if prompt and prompt["input"] and now - prompt["since"] >= timedelta(minutes=b["answer_minutes"]):
            self.prompts.pop("break")
            self.ui.close("break")
            self.state["snoozes"] += 1
            self.state["cycle"] = 0.0
            self.event("unanswered", self._points("unanswered"), now=now, count=self.state["snoozes"])
        prompt = self.prompts.get("water")
        if prompt and now - prompt["since"] >= timedelta(minutes=w["answer_minutes"]):
            self.prompts.pop("water")
            self.ui.close("water")
            self._water_later(now, quiet=True)

    def _start_normal(self, now):
        minutes = self.cfg["break"]["normal_minutes"]
        self.breaking = {"kind": "normal", "until": now + timedelta(minutes=minutes)}
        self.ui.break_window(self.clock.real_seconds(minutes * 60), self.t("care_break_window_title"),
                             self.t("care_break_window", minutes=minutes),
                             on_done=lambda: self._break_over("normal"), on_back=self._back_early)

    def _back_early(self):
        with self.lock:
            if self.breaking and self.breaking["kind"] == "normal":
                self.breaking = None
                self.event("break_back_early")

    def _start_forced(self, now, why, until=None):
        minutes = self.cfg["break"]["forced_minutes"]
        until = until or now + timedelta(minutes=minutes)
        self.forced_at = None
        for kind in list(self.prompts):
            self.prompts.pop(kind)
            self.ui.close(kind)
        self.ui.close("break_window")
        self.breaking = {"kind": "forced", "until": until}
        self.state["forced_until"] = _iso(until)
        self.event("forced_start", now=now, why=why)
        self.ui.forced(self.clock.real_seconds((until - now).total_seconds()), self.t("care_forced_title"),
                       self.toned("care_forced_text", now, minutes=minutes),
                       on_done=lambda: self._break_over("forced"), on_exit=self.emergency_exit)

    def emergency_exit(self, reason):
        """The forced break's emergency exit (Tk thread); `reason` is required by the window."""
        with self.lock:
            if not self.breaking or self.breaking["kind"] != "forced":
                return
            self.breaking = None
            self.state["forced_until"] = None
            self.state["cycle"] = 0.0  # snoozes stay: the next break is forced again
            self.event("emergency_exit", self._points("emergency_exit"), reason=reason.strip())
            self._save(force=True)

    def _break_over(self, kind):
        """A break's countdown reached zero (Tk thread)."""
        with self.lock:
            if not self.breaking or self.breaking["kind"] != kind:
                return
            self.breaking = None
            now = self.clock.now()
            if kind == "forced":
                self.state["forced_until"] = None
                self._reset_cycle()
                self.event("forced_done", self._points("forced_done"), now=now)
            else:
                self.event("break_done", now=now)
            minutes = self.cfg["break"]["forced_minutes" if kind == "forced" else "normal_minutes"]
            fallback = self.toned("care_break_over", now)
            self._save(force=True)
        self._say_later(f"The user's {'forced ' if kind == 'forced' else ''}break ({minutes} minutes) just ended. "
                        "Write a short Telegram message (one or two sentences) telling them the break is over "
                        "and they may come back to the PC.", fallback, "break over", self._telegram)

    # --- water ----------------------------------------------------------------------------------------

    def _water(self, now):
        if self.state["water"] < self.state["water_due"] or "water" in self.prompts or "break" in self.prompts:
            return
        self.prompts["water"] = {"since": now, "input": False}
        self.ui.prompt("water", self.t("care_water_title"), self.toned("care_water", now),
                       [(self.t("care_drank"), "drank"), (self.t("care_later"), "later")], self.answer_water)

    def answer_water(self, value):
        with self.lock:
            if self.prompts.pop("water", None) is None:
                return
            now = self.clock.now()
            if value == "drank":
                self.state.update(water=0.0, water_due=self.cfg["water"]["every_minutes"] * 60.0)
                self.event("water", self._points("water"), now=now)
            else:
                self._water_later(now)
            self._save(force=True)

    def _water_later(self, now, quiet=False):
        self.state.update(water=0.0, water_due=self.cfg["water"]["later_minutes"] * 60.0)
        if not quiet:
            self.event("water_later", self._points("water_later"), now=now)

    # --- night ----------------------------------------------------------------------------------------

    def _night(self, now, away, dt):
        if not self.in_night(now):
            return
        n = self.cfg["night"]
        nid = self.night_id(now)
        night = self.state["night"]
        if night.get("id") != nid:
            night = self.state["night"] = {"id": nid, "warned": [], "check": None, "verdict": None, "waited": 0.0}
        if away or self.state.get("slept_night") == nid or self.shutdown is not None or self.breaking is not None:
            return  # during a break the night waits: nothing pops up under the break window
        hours = self.night_hours()
        if night["check"] is None and night["verdict"] is None and n["check_hour"] in hours \
                and hours.index(now.hour) >= hours.index(n["check_hour"]):
            self._ask_why_up(now, night)
            return
        if night["check"] == "asked" and night["verdict"] is None:
            night["waited"] += dt
            if night["waited"] >= n["answer_minutes"] * 60:
                self._verdict(now, night, "whim", self.t("care_no_answer"))
            return
        if now.hour != n["check_hour"] and now.hour not in night["warned"] and night["verdict"] != "valid":
            night["warned"].append(now.hour)
            soft = night["verdict"] == "cant_sleep"
            points = n["warning_points"].get(f"{now:%H}", self._points("sleep_warning"))
            self.event("sleep_warning", 0 if soft else points, now=now, hour=f"{now:%H:%M}")
            hour = f"{now:%H:00}"
            text = self.t("care_sleep_soft", hour=hour) if soft else self.toned("care_sleep_warning", now, hour=hour)
            self.ui.notice("sleep", self.t("care_sleep_title"), text,
                           self.clock.real_seconds(10 * 60), sound=True)

    def _ask_why_up(self, now, night):
        night["check"] = "asked"
        night["asked_at"] = _iso(now)
        minutes = self.cfg["night"]["answer_minutes"]
        self.event("night_asked", now=now, time=f"{now:%H:%M}")
        self._say_later(f"It is {now:%H:%M} at night and the user is still at the PC. You open the chat yourself: "
                        "ask them, in character and in one to three sentences, why they haven't gone to bed. "
                        f"Tell them that if they don't answer within {minutes} minutes you'll take it as no good "
                        "reason.", self.toned("care_night_question", now, minutes=minutes), "03:00 check", self.chat)

    def box_message(self, text):
        """A message typed in the text box (before Zyraena answers it): the answer to the night question, if
        one is waiting. Blocks while the assistant model sorts it."""
        with self.lock:
            night = self.state["night"]
            waiting = night.get("check") == "asked" and night.get("verdict") is None
        if not waiting:
            return
        category = self._sort_reason(text)
        with self.lock:
            if night.get("verdict") is None:
                self._verdict(self.clock.now(), night, category, text.strip()[:200])

    def _sort_reason(self, text):
        prompt = self.t("care_classify_prompt", answer=text.strip()[:500])
        try:
            answer = self.classify(prompt, "03:00 answer") if self.classify else ""
            match = re.search(r"\{.*\}", answer or "", re.S)
            category = json.loads(match.group(0)).get("category") if match else None
            if category in CATEGORIES:
                return category
        except Exception as e:
            _log(f"sorting the night answer failed: {e!r}")
        return _guess_category(text)

    def _verdict(self, now, night, category, reason):
        n = self.cfg["night"]
        week = datetime.fromisoformat(night["id"]).isocalendar()[:2]
        used = sum(1 for d in self.state["excuses"] if datetime.fromisoformat(d).isocalendar()[:2] == week)
        if category in GOOD_REASONS and used < n["excuses_per_week"]:
            verdict = "valid"
            self.state["excuses"] = (self.state["excuses"] + [night["id"]])[-20:]
            used += 1
        elif category in GOOD_REASONS:
            verdict = "limit"
        elif category == "cant_sleep":
            verdict = "cant_sleep"
        else:
            verdict = "invalid"
        night["verdict"] = verdict
        night["category"] = category
        refused = verdict in ("invalid", "limit")
        self.event("night_reason", self._points("night_refused") if refused else 0, now=now, reason=reason,
                   category=category, verdict=verdict, used=used, limit=n["excuses_per_week"])
        if refused:
            self.start_shutdown(now, f"night:{category}")
        self._save(force=True)

    # --- shutdown -------------------------------------------------------------------------------------

    def _warning_seconds(self):
        s = self.cfg["shutdown"]
        return (s["angry_warning_minutes"] if self.level() == "angry" else s["warning_minutes"]) * 60

    def start_shutdown(self, now, why):
        """The step-by-step shutdown, or a forced break while the protection list holds."""
        if self.shutdown is not None:
            return
        found = self.guard.reasons(self.cfg["protect"])
        if found:
            self._protected(now, found)
            return
        seconds = self._warning_seconds()
        self.shutdown = {"deadline": now + timedelta(seconds=seconds), "final": False, "rechecked": False,
                         "issued": False, "why": why, "due": None}
        self.event("shutdown_warning", now=now, minutes=seconds // 60)
        text = self.toned("care_shutdown_warning", now, minutes=seconds // 60)
        self.ui.shutdown_warning(self.clock.real_seconds(seconds), self.t("care_shutdown_title"), text,
                                 on_cancel=lambda reason: self.cancel_shutdown("pc", reason))
        self._telegram(text + ("\n\n" + self.t("care_dry_run_note") if self.dry_run() else ""))

    def _protected(self, now, found):
        why = ", ".join(f"{self.t('care_rule_' + rule)}: {what}" for rule, what in found)
        self.event("shutdown_protected", now=now, why=why)
        self._start_forced(now, "protected")

    def _shutdown_step(self, now):
        s = self.shutdown
        if s is None:
            return
        left = (s["deadline"] - now).total_seconds()
        final = self.cfg["shutdown"]["final_seconds"]
        if not s["final"] and left <= final:
            found = self.guard.reasons(self.cfg["protect"])
            if found:
                self._end_shutdown_ui()
                self.shutdown = None
                self._protected(now, found)
                return
            s["final"] = True
            seconds = max(1, int(left))
            if self.dry_run():
                _log(f"[DRY_RUN] would run: shutdown /s /f /t {seconds}")
            else:
                result = subprocess.run(["shutdown", "/s", "/f", "/t", str(seconds), "/c", self.t("care_shutdown_comment")],
                                        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                s["issued"] = result.returncode == 0
                if not s["issued"]:
                    _log(f"shutdown.exe failed: {result.stderr or result.stdout!r}")
            self.ui.close("shutdown")
            self.ui.final_countdown(self.clock.real_seconds(left), self.t("care_final_title"),
                                    self.t("care_final_text"),
                                    on_cancel=lambda reason: self.cancel_shutdown("pc", reason))
        if s["final"] and not s["rechecked"] and left <= 5:
            s["rechecked"] = True
            found = self.guard.reasons(self.cfg["protect"])
            if found:
                self._abort_windows_shutdown()
                self._end_shutdown_ui()
                self.shutdown = None
                self._protected(now, found)
                return
        if left <= 0 and s["due"] is None:
            s["due"] = now
            if self.dry_run():
                self.event("shutdown_dry", now=now)
                self._end_shutdown_ui()
                self.shutdown = None
                self._telegram(self.t("care_dry_run_done"))
            else:
                self.event("shutdown", now=now)
                self._save(force=True)
        elif s["due"] is not None and (now - s["due"]).total_seconds() >= EXTERNAL_CANCEL_SECONDS:
            self.shutdown = None  # still here: it was cancelled outside Zyraena (shutdown /a)
            self._end_shutdown_ui()
            self.event("shutdown_cancel", self._points("shutdown_cancel"), now=now, source="shutdown /a")

    def _end_shutdown_ui(self):
        self.ui.close("shutdown")
        self.ui.close("final")

    def _abort_windows_shutdown(self):
        if self.shutdown and self.shutdown["issued"]:
            subprocess.run(["shutdown", "/a"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def cancel_shutdown(self, source, reason=""):
        """The window's Cancel, Telegram's /iptal (system_tools.cancel_shutdown). True if one was running."""
        with self.lock:
            if self.shutdown is None:
                return False
            self._abort_windows_shutdown()
            self.shutdown = None
            self._end_shutdown_ui()
            self.event("shutdown_cancel", self._points("shutdown_cancel"), reason=(reason or "").strip(),
                       source=source)
            self._save(force=True)
            return True

    # --- morning summary --------------------------------------------------------------------------------

    def _morning(self, now):
        today = self.day_key(now)
        last = self.state.get("summary_day")
        if last == today:
            return
        self.state["summary_day"] = today
        if last is None:
            return  # the first run: nothing to sum up
        yesterday = self.day_key(now - timedelta(days=1))
        facts = self.summary_facts(yesterday)
        if facts is None:
            return
        self.event("morning_summary", now=now, of=yesterday)
        self._say_later("The user just started their day. Greet them and sum up yesterday in character, briefly "
                        "(at most six short lines), from these facts; praise or scold according to your mood and "
                        f"mention the reasons of emergency exits, if any:\n{facts}",
                        self.t("care_summary_fallback", facts=facts), "morning summary", self.chat)

    def summary_facts(self, day):
        """Yesterday in a few lines (None if nothing was recorded)."""
        events = [e for e in self.store.events() if e.get("day") == day]
        if not events:
            return None
        count = lambda *kinds: sum(1 for e in events if e["kind"] in kinds)  # noqa: E731
        bed = next((e.get("time") for e in reversed(events) if e["kind"] == "bedtime"), None)
        exits = [e.get("reason") or "?" for e in events if e["kind"] == "emergency_exit"]
        night = next((e for e in reversed(events) if e["kind"] == "night_reason"), None)
        lines = [self.t("care_fact_bed", time=bed) if bed else self.t("care_fact_bed_unknown"),
                 self.t("care_fact_breaks", taken=count("break_taken"), forced=count("forced_done"),
                        away=count("afk_break", "sleep"), snoozed=count("snooze"), unanswered=count("unanswered")),
                 self.t("care_fact_water", count=count("water")),
                 self.t("care_fact_warnings", count=count("sleep_warning"))]
        if exits:
            lines.append(self.t("care_fact_exits", count=len(exits), reasons="; ".join(f'"{r}"' for r in exits)))
        if night:
            lines.append(self.t("care_fact_night", category=self.t("care_cat_" + night["category"]),
                                verdict=self.t("care_verdict_" + night["verdict"])))
        if count("shutdown_cancel"):
            lines.append(self.t("care_fact_cancels", count=count("shutdown_cancel")))
        return "\n".join("- " + line for line in lines)

    # --- speaking -----------------------------------------------------------------------------------------

    def _telegram(self, text):
        if self.clock.fake and not self.cfg["debug"].get("telegram"):
            _log(f"[debug, not sent] Telegram: {text}")
            return
        try:
            self.notify(text)
        except Exception as e:
            _log(f"Telegram failed: {e!r}")

    def _say_later(self, instruction, fallback, what, deliver):
        """Zyraena's own words for `instruction` on a worker thread (the template if the model fails)."""
        def work():
            text = None
            if self.persona is not None:
                try:
                    text = (self.persona(instruction, what) or "").strip() or None
                except Exception as e:
                    _log(f"persona text failed: {e!r}")
            deliver(text or fallback)

        threading.Thread(target=work, daemon=True).start()

    # --- her prompt ---------------------------------------------------------------------------------------

    def prompt_block(self):
        """What goes into the lady persona's system prompt with every message."""
        with self.lock:
            if not self.cfg["enabled"]:
                return ""
            lang = self.lang()
            now = self.clock.now()
            mood = round(self.state["mood"])
            recent = self.state["recent"][-PROMPT_EVENTS:]
            events = "; ".join(f"{e['t'][11:16]} {self.describe(e, lang)}" for e in reversed(recent)) or "-"
            line = (f"[mood: {mood}/100, {i18n.get(lang, 'care_level_' + self.level())}, "
                    f"{i18n.get(lang, 'care_recent')}: {events}]")
            grudge = next((e for e in reversed(self.state["recent"]) if e["kind"] == "emergency_exit"
                           and e not in recent and now - _dt(e["t"]) <= timedelta(hours=GRUDGE_HOURS)), None)
            if grudge:
                line += f"\n[{i18n.get(lang, 'care_last_exit')}: {grudge['t'][:16].replace('T', ' ')} \"{grudge['reason']}\"]"
            relation = self.relation()
            parts = [line, f"[affection: {round(self.state['affection'])}/100, "
                           f"{i18n.get(lang, 'care_aff_' + self.affection_level())} · "
                           f"{i18n.get(lang, 'care_rel_' + relation)}]",
                     "Your relationship style right now (mood x affection): " + i18n.RELATION_STYLES[relation],
                     PROMPT_RULES]
            if self.in_night(now):
                parts.append("It is late at night: a low mood shows as worry about them, not anger.")
            night = self.state["night"]
            if night.get("id") == self.night_id(now) and night.get("verdict"):
                parts.append(NIGHT_NOTES[night["verdict"]].format(
                    category=night.get("category", ""), limit=self.cfg["night"]["excuses_per_week"]))
            elif night.get("check") == "asked":
                parts.append("You asked them why they are still up; their next message is the answer.")
            return "User Care (your mood and affection toward the user, a layer on your own persona; never a "\
                   "different persona):\n" + "\n".join(parts)

    def make_peace(self, reason):
        """The care_make_peace tool: an apology or a promise brings the mood up, a few times a day at most."""
        with self.lock:
            now = self.clock.now()
            p = self.cfg["peace"]
            times = [t for t in (_dt(x) for x in self.state["peace"]) if t is not None]
            if times and now - max(times) < timedelta(hours=p["min_hours"]):
                return (f"Not counted: you already made peace at {max(times):%H:%M}; mood stays "
                        f"{round(self.state['mood'])}/100.")
            if sum(1 for t in times if self.day_key(t) == self.day_key(now)) >= p["per_day"]:
                return f"Not counted: already {p['per_day']} times today; mood stays {round(self.state['mood'])}/100."
            self.state["peace"] = [_iso(t) for t in times if now - t < timedelta(days=2)] + [_iso(now)]
            entry = self.event("peace", self._points("peace"), reason=(reason or "").strip()[:200], now=now)
            self._save(force=True)
            return f"Peace made: mood is now {entry['mood']}/100 ({self.level()})."

    # --- affection ----------------------------------------------------------------------------------------

    def add_affection(self, change, reason="", source=""):
        """The look at a finished conversation (relationship.py): at most max_per_chat either way, and
        no more than up_per_day / down_per_day in a day. Returns the change that counted."""
        with self.lock:
            a = self.cfg["affection"]
            now = self.clock.now()
            day = self.day_key(now)
            spent = self.state["affection_day"].get(day, {"up": 0, "down": 0})
            change = max(-a["max_per_chat"], min(a["max_per_chat"], int(round(change or 0))))
            if change > 0:
                change = min(change, max(0, a["up_per_day"] - spent["up"]))
            elif change < 0:
                change = -min(-change, max(0, a["down_per_day"] - spent["down"]))
            if change == 0:
                return 0
            old = self.state["affection"]
            self.state["affection"] = min(100.0, max(0.0, old + change))
            change = int(round(self.state["affection"] - old))
            spent = dict(spent, up=spent["up"] + max(change, 0), down=spent["down"] + max(-change, 0))
            self.state["affection_day"] = {day: spent}  # older days don't matter any more
            self.event("affection", reason=(reason or "").strip()[:200], now=now, change=change,
                       affection=round(self.state["affection"]), source=source)
            self._save(force=True)
            return change

    def note_chat(self):
        """A conversation just ended: no drop-in right after it."""
        with self.lock:
            self.state["last_chat"] = _iso(self.clock.now())
            self._dirty = True

    # --- drop-in ------------------------------------------------------------------------------------------

    def _drop_in(self, now, idle):
        """Every check_minutes, while they're at the PC and nothing else of hers is on screen, a chance
        that she comes by on her own. All of this is free; only the line itself costs a persona call."""
        d = self.cfg["drop_in"]
        if not d["enabled"] or self.persona is None:
            return
        if self._drop_check is not None and now < self._drop_check:
            return
        self._drop_check = now + timedelta(minutes=d["check_minutes"])
        state = self.state["drop_in"]
        last, chat = _dt(state.get("last")), _dt(self.state.get("last_chat"))
        today = self.day_key(now)
        count = state.get("count", 0) if state.get("day") == today else 0
        if (self.in_night(now) or self.prompts or self.forced_at is not None or idle >= 60
                or self.state["cycle"] < d["active_minutes"] * 60
                or count >= d["per_day"][self.affection_level()]
                or (last is not None and now - last < timedelta(minutes=d["min_gap_minutes"]))
                or (chat is not None and now - chat < timedelta(minutes=d["after_chat_minutes"]))
                or random.random() >= d["chance"]):
            return
        try:
            seen = self.screen()
        except Exception as e:
            _log(f"drop-in: reading the screen failed: {e!r}")
            seen = None
        if not seen:
            return  # the box is open, a game, the pet hidden...: no call
        exe, title = seen
        if exe.lower() in [p.lower() for p in d["skip_programs"]]:
            return
        # Counted before the call: a SKIP is her choice too, and she isn't asked again right away.
        self.state["drop_in"] = {"day": today, "count": count + 1, "last": _iso(now)}
        self._dirty = True
        minutes = int(self.state["cycle"] // 60)
        instruction = (f"You decide on your own to drop by and say something to the user, unprompted. Right now "
                       f"they are using {exe or 'an app'}, window title: \"{title[:150]}\"; they have been at the "
                       f"PC for {minutes} minutes since their last break. Say one or two short sentences in "
                       "character, in your current relationship style: a remark or tease about what they are "
                       "doing, a question, or checking on them; you may bring up a memory if it fits. Don't "
                       "remind them about water or breaks (that is handled elsewhere). If you have nothing "
                       "worth saying right now, answer exactly SKIP.")

        def work():
            try:
                text = (self.persona(instruction, "drop-in") or "").strip()
            except Exception as e:
                _log(f"drop-in text failed: {e!r}")
                return
            if not text or text.strip(" .*\"'").upper() == "SKIP":
                _log("drop-in: she had nothing to say")
                return
            with self.lock:
                self.event("drop_in", program=exe or "?")
            try:
                self.drop_in_say(text)
            except Exception as e:
                _log(f"drop-in failed: {e!r}")

        threading.Thread(target=work, daemon=True).start()

    # --- the panel's Care tab -----------------------------------------------------------------------------

    def status(self):
        with self.lock:
            b, w = self.cfg["break"], self.cfg["water"]
            night = self.state["night"]
            week = self.clock.now().isocalendar()[:2]
            return {
                "now": self.clock.now(), "fake": self.clock.fake, "dry_run": self.dry_run(),
                "mood": round(self.state["mood"]), "level": self.level(),
                "active": self.state["active"], "cycle": self.state["cycle"], "every": b["every_minutes"] * 60,
                "snoozes": self.state["snoozes"], "rights": self._snooze_rights(),
                "forced_next": self._next_is_forced(), "water": self.state["water"],
                "water_due": self.state["water_due"], "breaking": (self.breaking or {}).get("kind"),
                "shutdown": self.shutdown is not None, "protection": list(self.protection),
                "night": night.get("verdict") or night.get("check"),
                "excuses": sum(1 for d in self.state["excuses"] if datetime.fromisoformat(d).isocalendar()[:2] == week),
                "excuse_limit": self.cfg["night"]["excuses_per_week"],
                "affection": round(self.state["affection"]), "affection_level": self.affection_level(),
                "relation": self.relation(), "drop_in": bool(self.cfg["drop_in"]["enabled"]),
            }

    def recent(self, n=12):
        with self.lock:
            return [(e["t"], self.describe(e)) for e in reversed(self.state["recent"][-n:])]

    def set_options(self, changes):
        """Changes settings in config.json's user_care section: [(path, value)], a path like
        ("drop_in", "enabled"). Writes the file: not on a Tk thread."""
        with self.lock:
            for path, value in changes:
                target = self.cfg
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
            if self.config_path:
                save_config(self.cfg, self.config_path)
                self._config_mtime = self._mtime()

    def set_protect(self, changes):
        """Changes protection settings in config.json: [(path, value)], a path like ("gpu", "enabled") or
        ("programs",). Slow (looks at the processes again): not on a Tk thread."""
        self.set_options([(("protect",) + tuple(path), value) for path, value in changes])
        with self.lock:
            protect = copy.deepcopy(self.cfg["protect"])
        found = self.guard.reasons(protect)  # outside the lock: the panel reads the status every second
        with self.lock:
            self.protection = found

    # --- debug (fake clock only) --------------------------------------------------------------------------

    def debug_advance(self, minutes, active=True):
        """Moves the fake clock on; with active=True the time counts as active use (not as sleep)."""
        if not self.clock.fake:
            return
        with self.lock:
            self.clock.advance(minutes * 60)
            self._last_mono = self.clock.mono()
            if active and self.breaking is None:
                for key in ("active", "cycle", "water"):
                    self.state[key] += minutes * 60
        self.tick()

    def debug_set_clock(self, hhmm):
        if not self.clock.fake:
            return
        hour, minute = map(int, hhmm.split(":"))
        now = self.clock.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        self.debug_advance((target - now).total_seconds() / 60, active=False)

    def debug_set_active(self, minutes):
        """Sets the active time; every full break cycle in it counts as one snooze (the "3 hours" case)."""
        with self.lock:
            every = self.cfg["break"]["every_minutes"]
            self.state.update(active=minutes * 60.0, cycle=(minutes % every) * 60.0, snoozes=int(minutes // every))
            self.forced_at = None
            self._dirty = True

    def debug_away(self, minutes):
        with self.lock:
            self._last_mono = self.clock.mono()
        self.tick(idle=minutes * 60, video=False)

    def debug_sleep(self, minutes):
        if not self.clock.fake:
            return
        with self.lock:
            self.clock.advance(minutes * 60)
        self.tick()

    def debug_mood(self, points):
        with self.lock:
            self.state["mood"] = min(100.0, max(0.0, self.state["mood"] + points))
            self._dirty = True

    def debug_affection(self, points):
        with self.lock:
            self.state["affection"] = min(100.0, max(0.0, self.state["affection"] + points))
            self._dirty = True


PROMPT_RULES = (
    "React to it in character: speak in that relationship style and bring up "
    "these events and their reasons when it fits. If the user sincerely "
    "apologizes or promises to look after themselves, you may forgive them: call care_make_peace. However "
    "low your mood, still do whatever they ask, fully and correctly; you may grumble while doing it.")

NIGHT_NOTES = {
    "valid": "Tonight you asked why they are still up and accepted their reason ({category}); the sleep warnings "
             "stop for tonight, breaks go on. Tell them so, in character.",
    "limit": "Tonight they gave a reason ({category}) but already used their {limit} accepted reasons this week, "
             "so it doesn't count: the PC is being shut down step by step (they can save first). Tell them so.",
    "cant_sleep": "Tonight they told you they can't sleep. Be gentle and caring, offer a few calming ideas "
                  "(dim the screen, breathing, warm drink, no phone); the PC will not be shut down.",
    "invalid": "Tonight they had no good reason to be up ({category}): the PC is being shut down step by step "
               "(they can save first). Tell them so, in character.",
}


def _guess_category(text):
    """When the assistant model can't sort the answer: a few Turkish / English key words."""
    t = text.lower()
    for category, words in (("emergency", ("acil", "hastane", "emergency", "hospital")),
                            ("exam", ("sınav", "sinav", "vize", "final", "exam", "quiz")),
                            ("work", ("deadline", "teslim", "iş", "proje", "rapor", "work", "ödev", "odev")),
                            ("cant_sleep", ("uyuyamıyorum", "uyuyamiyorum", "uykum yok", "uyku tutmuyor",
                                            "can't sleep", "cant sleep", "insomnia"))):
        if any(w in t for w in words):
            return category
    return "whim"


# --- the app's single instance ------------------------------------------------------------------------------

_state = {"care": None}


def service():
    """The running Care (for the panel), or None."""
    return _state["care"]


def start(persona=None, classify=None, notify=None, chat=None, lang=lambda: "tr", debug=None, screen=None,
          drop_in=None):
    """Starts User Care (unless switched off in config.json). debug: overrides for the debug section."""
    if _state["care"] is not None:
        return _state["care"]
    cfg = load_config()
    dbg = merged(cfg["debug"], debug or {})
    if dbg["enabled"]:
        at = None
        if dbg.get("at"):
            hour, minute = map(int, dbg["at"].split(":"))
            at = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        clock, store = FakeClock(at, dbg.get("speed") or 1), Store(care_dir(), "_debug")
        cfg["debug"] = dbg
        if not dbg.get("keep"):  # each debug run plays its scenario from a clean state
            for path in (store.state_path, store.events_path):
                path.unlink(missing_ok=True)
    else:
        clock, store = Clock(), Store(care_dir())
    from care_windows import Windows

    care = Care(cfg, store, clock, Windows(lang), care_guard.Guard(runs=_running_scripts), persona=persona,
                classify=classify, notify=notify, chat=chat, lang=lang, config_path=config_loader.CONFIG_PATH,
                screen=screen, drop_in=drop_in)
    if dbg["enabled"]:
        if dbg.get("mood") is not None:
            care.state["mood"] = float(dbg["mood"])
        if dbg.get("active_minutes"):
            care.debug_set_active(float(dbg["active_minutes"]))
        care.state["last_seen"] = care.state["last_input"] = _iso(clock.now())
    _state["care"] = care
    system_tools.cancel_hooks.append(lambda: care.cancel_shutdown("telegram", "/iptal"))
    care.start()
    return care


def _running_scripts():
    return sum(1 for run in system_tools._runs.values() if run["ended"] is None)


def prompt_block():
    """Her mood for the lady persona's system prompt ("" if User Care isn't running). Never raises: a User
    Care problem must not stop her answering."""
    care = _state["care"]
    try:
        return care.prompt_block() if care else ""
    except Exception as e:
        _log(f"prompt block failed: {e!r}")
        return ""


def box_message(text):
    """A message typed in the text box, before she answers it (the 03:00 answer). Never raises."""
    care = _state["care"]
    try:
        if care:
            care.box_message(text)
    except Exception as e:
        _log(f"box message failed: {e!r}")


def add_affection(change, reason="", source=""):
    """relationship.py's verdict on a finished conversation. Returns the change that counted (0 if User
    Care isn't running). Never raises."""
    care = _state["care"]
    try:
        return care.add_affection(change, reason, source) if care else 0
    except Exception as e:
        _log(f"affection failed: {e!r}")
        return 0


def affection():
    """(affection 0-100, level) or None if User Care isn't running."""
    care = _state["care"]
    if care is None:
        return None
    with care.lock:
        return round(care.state["affection"]), care.affection_level()


def note_chat():
    care = _state["care"]
    if care:
        care.note_chat()


def log_event(kind, **data):
    """An event from outside User Care (a never-forget memory) for the Care tab and her prompt."""
    care = _state["care"]
    if care:
        with care.lock:
            care.event(kind, **data)


def care_make_peace(reason: str = "") -> str:
    care = _state["care"]
    return care.make_peace(reason) if care else "User Care isn't running."


TOOLS = [{
    "type": "function",
    "function": {
        "name": "care_make_peace",
        "description": "User Care: call this when the user sincerely apologizes to you or promises to look after "
                       "themselves (take breaks, sleep on time): your mood toward them goes up. Counts at most a "
                       "few times a day; don't call it for anything else.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string", "description": "What they said, in a few words."}}, "required": []},
    },
}]
TOOL_FUNCTIONS = {"care_make_peace": care_make_peace}


def main():
    parser = argparse.ArgumentParser(description="Runs User Care alone on a fake clock (never shuts down).")
    parser.add_argument("--debug", action="store_true", required=True)
    parser.add_argument("--at", default="", help="fake time to start at, HH:MM (e.g. 02:58)")
    parser.add_argument("--active", type=float, default=0, help="active minutes already used (178 = the 3rd hour)")
    parser.add_argument("--mood", type=float, default=None)
    parser.add_argument("--speed", type=float, default=1, help="fake minutes per real minute")
    parser.add_argument("--telegram", action="store_true", help="really send the Telegram messages")
    parser.add_argument("--keep", action="store_true", help="go on from the last debug run's state")
    args = parser.parse_args()

    import ai_assistant
    import pc_tools
    import telegram_listener

    if args.telegram:
        telegram_listener.start()
    ai_assistant.start_user_care(debug={"enabled": True, "at": args.at, "active_minutes": args.active,
                                        "mood": args.mood, "speed": args.speed, "telegram": args.telegram,
                                        "keep": args.keep},
                                 notify=lambda text: pc_tools.fallback_notify(text))
    ai_assistant.open_care_panel()
    print("User Care debug is running; Ctrl+C ends it. The Care tab in the panel has the debug buttons.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
