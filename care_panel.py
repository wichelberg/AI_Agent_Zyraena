"""The control panel's Care tab (control_panel.py): User Care's mood and affection (with the relationship
style they make), active time, the next break and water reminder, tonight's state, the drop-in switch,
the protection list (on/off per rule, live) and the last events. The "Protection settings…" window edits
the program list, the training patterns and every rule's limits; "Memories…" shows her never-forget
memories (add, delete) and the last conversation notes (relationship.py). On User Care's fake clock
(debug) a row of buttons moves time, fakes being away or asleep, and changes the mood and affection.

Everything here runs on the panel's Tk thread; changes that write config.json or look at the processes
run on a worker thread.
"""
import threading
import tkinter as tk

import i18n
import relationship
from chat_box import CYAN, MUTED, NAVY, NAVY_LIGHT, PINK, TEXT, _Neon
from desktop_pet import _work_area

CARE_SIZE = (780, 700)
PROTECT_SIZE = (620, 560)
MEMORY_SIZE = (640, 560)
RULES = ("gpu", "terminal_jobs", "training", "zyraena_runs", "busy_cpu", "downloads")
LIMITS = (("gpu", "percent"), ("gpu", "minutes"), ("gpu", "compute_percent"), ("terminal_jobs", "cpu_percent"),
          ("terminal_jobs", "minutes"), ("busy_cpu", "percent"), ("busy_cpu", "minutes"),
          ("downloads", "mb_per_second"), ("downloads", "minutes"))
DEBUG_BUTTONS = (("plus10", "advance", 10), ("plus60", "advance", 60), ("at0259", "clock", "02:59"),
                 ("at2359", "clock", "23:59"), ("at0601", "clock", "06:01"), ("away", "away", 11),
                 ("sleep", "sleep", 30), ("active178", "active", 178), ("mood_down", "mood", -20),
                 ("mood_up", "mood", 20), ("aff_down", "affection", -20), ("aff_up", "affection", 20))
DEBUG_PER_ROW = 6
LEVEL_COLORS = {"happy": CYAN, "normal": TEXT, "angry": PINK}
AFFECTION_COLORS = {"high": PINK, "normal": TEXT, "low": MUTED}
REFRESH_MS = 1000
EVENTS_SHOWN = 12


def care_size(work_area):
    left, top, right, bottom = work_area
    return min(CARE_SIZE[0], right - left - 120), min(CARE_SIZE[1], bottom - top - 120)


def duration(lang, seconds):
    minutes = max(0, int(seconds // 60))
    if minutes >= 60:
        return i18n.get(lang, "care_hm", h=minutes // 60, m=minutes % 60)
    return i18n.get(lang, "care_m", m=minutes)


def status_lines(lang, s):
    """The tab's text for Care.status()."""
    t = lambda key, **kw: i18n.get(lang, key, **kw)  # noqa: E731
    left = max(0, s["every"] - s["cycle"])
    lines = [t("care_status_active", active=duration(lang, s["active"]), next=duration(lang, left),
               kind=t("care_status_forced" if s["forced_next"] else "care_status_normal"),
               snoozes=s["snoozes"], rights=s["rights"]),
             t("care_status_water", next=duration(lang, max(0, s["water_due"] - s["water"])))]
    night = t("care_status_night_" + s["night"]) if s["night"] else t("care_status_night_none")
    lines.append(t("care_status_night", night=night, used=s["excuses"], limit=s["excuse_limit"]))
    if s["breaking"]:
        lines.append(t("care_status_breaking_" + s["breaking"]))
    if s["shutdown"]:
        lines.append(t("care_status_shutdown"))
    flags = [t("care_status_dry_run")] if s["dry_run"] else [t("care_status_live")]
    if s["fake"]:
        flags.append(t("care_status_fake", time=f"{s['now']:%H:%M}"))
    lines.append(" · ".join(flags))
    return lines


def protection_text(lang, found):
    if not found:
        return i18n.get(lang, "care_protect_none")
    return i18n.get(lang, "care_protect_on", why="; ".join(
        f"{i18n.get(lang, 'care_rule_' + rule)}: {what}" for rule, what in found))


def _check(parent, text, var, command):
    return tk.Checkbutton(parent, text=text, variable=var, command=command, bg=NAVY, fg=TEXT, selectcolor=NAVY_LIGHT,
                          activebackground=NAVY, activeforeground=CYAN, font=("Segoe UI", 9), anchor="w",
                          highlightthickness=0, borderwidth=0)


def _button(parent, text, command, color=CYAN):
    return tk.Button(parent, text=text, command=command, bg=NAVY_LIGHT, fg=color, activebackground=NAVY,
                     activeforeground=color, relief="flat", font=("Segoe UI", 9, "bold"), padx=10, pady=2,
                     borderwidth=0, cursor="hand2")


def _in_background(fn, then=None):
    def work():
        try:
            fn()
        except Exception as e:
            print(f"Care tab: {e!r}")
        if then is not None:
            then()
    threading.Thread(target=work, daemon=True).start()


class CareTab:
    def __init__(self, root, win, lang, care, first_row=2):
        self.root, self.win, self.lang, self.care = root, win, lang, care
        self.closed = False
        self.protect_window = None
        self.memory_window = None
        t = self.t
        win.columnconfigure(0, weight=1)
        row = first_row

        self.mood = tk.Label(win, text="", bg=NAVY, fg=TEXT, font=("Segoe UI", 12, "bold"), anchor="w")
        self.mood.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16)
        self.bar = tk.Canvas(win, height=8, bg=NAVY_LIGHT, highlightthickness=0)
        self.bar.grid(row=row + 1, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 6))
        self.affection = tk.Label(win, text="", bg=NAVY, fg=TEXT, font=("Segoe UI", 11, "bold"), anchor="w")
        self.affection.grid(row=row + 2, column=0, columnspan=2, sticky="ew", padx=16)
        self.affection_bar = tk.Canvas(win, height=8, bg=NAVY_LIGHT, highlightthickness=0)
        self.affection_bar.grid(row=row + 3, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 8))
        self.status = tk.Label(win, text="", bg=NAVY, fg=TEXT, font=("Segoe UI", 9), anchor="w", justify="left")
        self.status.grid(row=row + 4, column=0, columnspan=2, sticky="ew", padx=16)

        self.drop_in = tk.IntVar(win, value=1 if care.cfg["drop_in"]["enabled"] else 0)
        _check(win, t("care_drop_in"), self.drop_in, self._set_drop_in).grid(row=row + 5, column=0, sticky="w",
                                                                              padx=12, pady=(6, 0))
        _button(win, t("care_memories"), self.open_memories).grid(row=row + 5, column=1, sticky="e", padx=16,
                                                                  pady=(6, 0))

        tk.Label(win, text=t("care_protect_title"), bg=NAVY, fg=PINK, font=("Segoe UI", 10, "bold"),
                 anchor="w").grid(row=row + 6, column=0, sticky="w", padx=16, pady=(10, 0))
        _button(win, t("care_protect_settings"), self.open_protect, PINK).grid(row=row + 6, column=1, sticky="e",
                                                                                 padx=16, pady=(10, 0))
        self.protect = tk.Label(win, text="", bg=NAVY, fg=MUTED, font=("Segoe UI", 9), anchor="w", justify="left",
                                wraplength=CARE_SIZE[0] - 40)
        self.protect.grid(row=row + 7, column=0, columnspan=2, sticky="ew", padx=16)
        rules = tk.Frame(win, bg=NAVY)
        rules.grid(row=row + 8, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 0))
        cfg = care.cfg["protect"]
        self.rule_vars = {}
        for i, rule in enumerate(RULES):
            var = tk.IntVar(win, value=1 if cfg[rule]["enabled"] else 0)   # master: see disk_panel
            self.rule_vars[rule] = var
            _check(rules, t("care_rule_" + rule), var, lambda r=rule: self._set_rule(r)).grid(
                row=i // 3, column=i % 3, sticky="w", padx=4)
        for c in range(3):
            rules.columnconfigure(c, weight=1)

        tk.Label(win, text=t("care_events_title"), bg=NAVY, fg=PINK, font=("Segoe UI", 10, "bold"),
                 anchor="w").grid(row=row + 9, column=0, columnspan=2, sticky="w", padx=16, pady=(10, 2))
        self.events = tk.Text(win, bg=NAVY_LIGHT, fg=TEXT, font=("Segoe UI", 9), relief="flat", height=10,
                              wrap="word", highlightthickness=0, padx=8, pady=6, cursor="arrow")
        self.events.grid(row=row + 10, column=0, columnspan=2, sticky="nsew", padx=16)
        win.rowconfigure(row + 10, weight=1)
        self.events.tag_configure("time", foreground=MUTED)
        self.events.configure(state="disabled")

        if care.clock.fake:
            debug = tk.Frame(win, bg=NAVY)
            debug.grid(row=row + 11, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 0))
            tk.Label(debug, text=t("care_debug"), bg=NAVY, fg=MUTED, font=("Segoe UI", 8, "italic")).grid(
                row=0, column=0, sticky="w")
            for i, (name, action, value) in enumerate(DEBUG_BUTTONS):
                _button(debug, t("care_debug_" + name), lambda a=action, v=value: self._debug(a, v)).grid(
                    row=i // DEBUG_PER_ROW, column=1 + i % DEBUG_PER_ROW, sticky="ew", padx=(4, 0), pady=(0, 2))
        tk.Label(win, text=t("care_hint"), bg=NAVY, fg=MUTED, font=("Segoe UI", 8, "italic"),
                 anchor="center").grid(row=row + 12, column=0, columnspan=2, sticky="ew", padx=16, pady=(6, 10))
        self.refresh()

    def t(self, key, **kw):
        return i18n.get(self.lang, key, **kw)

    def _later(self, fn):
        if self.closed:
            return
        try:
            self.root.after(0, lambda: None if self.closed else fn())
        except RuntimeError:
            pass

    def refresh(self):
        if self.closed:
            return
        s = self.care.status()
        self.mood.configure(text=self.t("care_status_mood", mood=s["mood"], level=self.t("care_level_" + s["level"])),
                            fg=LEVEL_COLORS[s["level"]])
        self.bar.delete("all")
        width = max(1, self.bar.winfo_width())
        self.bar.create_rectangle(0, 0, width * s["mood"] / 100, 8, fill=LEVEL_COLORS[s["level"]], width=0)
        color = AFFECTION_COLORS[s["affection_level"]]
        self.affection.configure(text=self.t("care_status_affection", affection=s["affection"],
                                             level=self.t("care_aff_" + s["affection_level"]),
                                             relation=self.t("care_rel_" + s["relation"])), fg=color)
        self.affection_bar.delete("all")
        width = max(1, self.affection_bar.winfo_width())
        self.affection_bar.create_rectangle(0, 0, width * s["affection"] / 100, 8, fill=color, width=0)
        if bool(self.drop_in.get()) != s["drop_in"]:  # config.json may have changed it
            self.drop_in.set(1 if s["drop_in"] else 0)
        self.status.configure(text="\n".join(status_lines(self.lang, s)))
        self.protect.configure(text=protection_text(self.lang, s["protection"]),
                               fg=CYAN if s["protection"] else MUTED)
        for rule, var in self.rule_vars.items():  # the settings window may have changed them
            if bool(var.get()) != self.care.cfg["protect"][rule]["enabled"]:
                var.set(1 if self.care.cfg["protect"][rule]["enabled"] else 0)
        self.events.configure(state="normal")
        self.events.delete("1.0", "end")
        for when, text in self.care.recent(EVENTS_SHOWN):
            self.events.insert("end", f"{when[5:16].replace('T', ' ')}  ", "time")
            self.events.insert("end", text + "\n")
        self.events.configure(state="disabled")
        self.root.after(REFRESH_MS, self.refresh)

    def _set_rule(self, rule):
        value = bool(self.rule_vars[rule].get())
        _in_background(lambda: self.care.set_protect([((rule, "enabled"), value)]))

    def _set_drop_in(self):
        value = bool(self.drop_in.get())
        _in_background(lambda: self.care.set_options([(("drop_in", "enabled"), value)]))

    def _debug(self, action, value):
        care = self.care
        run = {"advance": lambda: care.debug_advance(value), "clock": lambda: care.debug_set_clock(value),
               "away": lambda: care.debug_away(value), "sleep": lambda: care.debug_sleep(value),
               "active": lambda: care.debug_set_active(value), "mood": lambda: care.debug_mood(value),
               "affection": lambda: care.debug_affection(value)}[action]
        _in_background(run)

    def open_protect(self):
        if self.protect_window is None or self.protect_window.closed:
            self.protect_window = ProtectWindow(self.root, self.lang, self.care)

    def open_memories(self):
        if self.memory_window is None or self.memory_window.closed:
            self.memory_window = MemoryWindow(self.root, self.lang)

    def close(self):
        self.closed = True
        for window in (self.protect_window, self.memory_window):
            if window is not None:
                window.close()


class MemoryWindow:
    """Her never-forget memories (the owner adds and deletes them; code never removes one) and the last
    conversation notes, read-only (relationship.py)."""

    def __init__(self, root, lang):
        self.root, self.lang, self.closed = root, lang, False
        left, top, right, bottom = _work_area()
        size = (min(MEMORY_SIZE[0], right - left - 80), min(MEMORY_SIZE[1], bottom - top - 80))
        self.neon = _Neon(root, size, (left + right - size[0]) // 2 + 40, (top + bottom - size[1]) // 2 + 30)
        win = self.win = self.neon.win
        t = self.t
        win.columnconfigure(0, weight=1)
        tk.Label(win, text=t("care_mem_window"), bg=NAVY, fg=PINK, font=("Segoe UI", 12, "bold"),
                 anchor="w").grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 2))
        tk.Label(win, text=t("care_mem_explain"), bg=NAVY, fg=MUTED, font=("Segoe UI", 8, "italic"), anchor="w",
                 justify="left", wraplength=size[0] - 32).grid(row=1, column=0, sticky="ew", padx=16)

        tk.Label(win, text=t("care_mem_core"), bg=NAVY, fg=TEXT, font=("Segoe UI", 9, "bold"), anchor="w").grid(
            row=2, column=0, sticky="ew", padx=16, pady=(8, 0))
        self.core = tk.Listbox(win, bg=NAVY_LIGHT, fg=TEXT, selectbackground=PINK, relief="flat", highlightthickness=0,
                               font=("Segoe UI", 9), height=8, activestyle="none")
        self.core.grid(row=3, column=0, sticky="nsew", padx=16, pady=(2, 4))
        win.rowconfigure(3, weight=1)
        row = tk.Frame(win, bg=NAVY)
        row.grid(row=4, column=0, sticky="ew", padx=16)
        self.entry = tk.Entry(row, bg=NAVY_LIGHT, fg=TEXT, insertbackground=CYAN, relief="flat", highlightthickness=0,
                              font=("Segoe UI", 9))
        self.entry.pack(side="left", fill="x", expand=True, ipady=2)
        self.entry.bind("<Return>", lambda e: self.add())
        _button(row, t("care_add"), self.add).pack(side="left", padx=(6, 0))
        _button(row, t("care_remove"), self.remove, PINK).pack(side="left", padx=(6, 0))

        tk.Label(win, text=t("care_mem_notes"), bg=NAVY, fg=TEXT, font=("Segoe UI", 9, "bold"), anchor="w").grid(
            row=5, column=0, sticky="ew", padx=16, pady=(10, 0))
        self.notes = tk.Text(win, bg=NAVY_LIGHT, fg=TEXT, font=("Segoe UI", 9), relief="flat", height=8, wrap="word",
                             highlightthickness=0, padx=8, pady=6, cursor="arrow")
        self.notes.grid(row=6, column=0, sticky="nsew", padx=16, pady=(2, 0))
        win.rowconfigure(6, weight=1)
        self.notes.tag_configure("time", foreground=MUTED)
        _button(win, t("care_close"), self.close, PINK).grid(row=7, column=0, sticky="e", padx=16, pady=(8, 12))
        win.bind("<Escape>", lambda e: self.close())
        self.ids = []
        self.fill()
        win.lift()
        win.focus_force()

    def t(self, key, **kw):
        return i18n.get(self.lang, key, **kw)

    def fill(self):
        data = relationship.load()
        self.core.delete(0, "end")
        self.ids = [m["id"] for m in data["core"]]
        for m in data["core"]:
            self.core.insert("end", f"{m['t'][:10]}  {m['text']}")
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        for n in reversed(data["notes"]):
            self.notes.insert("end", f"{n['t'][5:16].replace('T', ' ')}  ", "time")
            self.notes.insert("end", n["text"] + "\n")
        if not data["notes"]:
            self.notes.insert("end", self.t("care_mem_none"), "time")
        self.notes.configure(state="disabled")

    def add(self):
        text = self.entry.get().strip()
        if text:
            relationship.add_core(text, "owner")
            self.entry.delete(0, "end")
            self.fill()

    def remove(self):
        for index in self.core.curselection():
            relationship.remove_core(self.ids[index])
        self.fill()

    def close(self):
        if not self.closed:
            self.closed = True
            self.neon.destroy()


class ProtectWindow:
    """The protection list's settings: programs, training patterns, each rule's switch and limits."""

    def __init__(self, root, lang, care):
        self.root, self.lang, self.care, self.closed = root, lang, care, False
        left, top, right, bottom = _work_area()
        size = (min(PROTECT_SIZE[0], right - left - 80), min(PROTECT_SIZE[1], bottom - top - 80))
        self.neon = _Neon(root, size, (left + right - size[0]) // 2 + 40, (top + bottom - size[1]) // 2 + 30)
        win = self.win = self.neon.win
        t = lambda key, **kw: i18n.get(lang, key, **kw)  # noqa: E731
        cfg = care.cfg["protect"]
        win.columnconfigure(0, weight=1)
        win.columnconfigure(1, weight=1)
        tk.Label(win, text=t("care_protect_window"), bg=NAVY, fg=PINK, font=("Segoe UI", 12, "bold"),
                 anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 2))
        tk.Label(win, text=t("care_protect_explain"), bg=NAVY, fg=MUTED, font=("Segoe UI", 8, "italic"), anchor="w",
                 justify="left", wraplength=size[0] - 32).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16)
        self.lists = {}
        for column, (key, values) in enumerate((("programs", cfg["programs"]),
                                                ("patterns", cfg["training"]["patterns"]))):
            self.lists[key] = self._list(win, column, t("care_protect_" + key), values)

        limits = tk.Frame(win, bg=NAVY)
        limits.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(10, 0))
        self.switches, self.limits = {}, {}
        for i, rule in enumerate(RULES):
            var = tk.IntVar(win, value=1 if cfg[rule]["enabled"] else 0)
            self.switches[rule] = var
            _check(limits, t("care_rule_" + rule), var, lambda: None).grid(row=i // 3, column=i % 3, sticky="w")
        for i, (rule, key) in enumerate(LIMITS):
            cell = tk.Frame(limits, bg=NAVY)
            cell.grid(row=2 + i // 3, column=i % 3, sticky="w", pady=(4, 0))
            tk.Label(cell, text=t(f"care_limit_{rule}_{key}"), bg=NAVY, fg=TEXT, font=("Segoe UI", 9)).pack(side="left")
            var = tk.StringVar(win, value=str(cfg[rule][key]))
            tk.Entry(cell, textvariable=var, width=5, bg=NAVY_LIGHT, fg=TEXT, insertbackground=CYAN, relief="flat",
                     highlightthickness=0, font=("Segoe UI", 9)).pack(side="left", padx=(4, 0))
            self.limits[(rule, key)] = var
        for c in range(3):
            limits.columnconfigure(c, weight=1)

        self.message = tk.Label(win, text="", bg=NAVY, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.message.grid(row=5, column=0, sticky="ew", padx=16, pady=(10, 12))
        buttons = tk.Frame(win, bg=NAVY)
        buttons.grid(row=5, column=1, sticky="e", padx=16, pady=(10, 12))
        _button(buttons, t("care_close"), self.close, PINK).pack(side="right", padx=(8, 0))
        _button(buttons, t("care_save"), self.save).pack(side="right")
        win.bind("<Escape>", lambda e: self.close())
        win.lift()
        win.focus_force()

    def _list(self, win, column, title, values):
        frame = tk.Frame(win, bg=NAVY)
        frame.grid(row=2, column=column, sticky="nsew", padx=(16 if column == 0 else 8, 16 if column else 8),
                   pady=(8, 0))
        win.rowconfigure(2, weight=1)
        tk.Label(frame, text=title, bg=NAVY, fg=TEXT, font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        box = tk.Listbox(frame, bg=NAVY_LIGHT, fg=TEXT, selectbackground=PINK, relief="flat", highlightthickness=0,
                         font=("Segoe UI", 9), height=8, activestyle="none")
        box.pack(fill="both", expand=True, pady=(2, 4))
        for value in values:
            box.insert("end", value)
        row = tk.Frame(frame, bg=NAVY)
        row.pack(fill="x")
        entry = tk.Entry(row, bg=NAVY_LIGHT, fg=TEXT, insertbackground=CYAN, relief="flat", highlightthickness=0,
                         font=("Segoe UI", 9))
        entry.pack(side="left", fill="x", expand=True, ipady=2)

        def add():
            value = entry.get().strip()
            if value and value not in box.get(0, "end"):
                box.insert("end", value)
            entry.delete(0, "end")

        def remove():
            for index in reversed(box.curselection()):
                box.delete(index)

        entry.bind("<Return>", lambda e: add())
        _button(row, i18n.get(self.lang, "care_add"), add).pack(side="left", padx=(6, 0))
        _button(row, i18n.get(self.lang, "care_remove"), remove, PINK).pack(side="left", padx=(6, 0))
        return box

    def save(self):
        changes = [(("programs",), list(self.lists["programs"].get(0, "end"))),
                   (("training", "patterns"), list(self.lists["patterns"].get(0, "end")))]
        changes += [((rule, "enabled"), bool(var.get())) for rule, var in self.switches.items()]
        for (rule, key), var in self.limits.items():
            try:
                value = float(var.get().replace(",", "."))
            except ValueError:
                self.message.configure(text=i18n.get(self.lang, "care_bad_number"), fg=PINK)
                return
            changes.append(((rule, key), int(value) if value.is_integer() else value))

        self.message.configure(text=i18n.get(self.lang, "care_saving"), fg=MUTED)
        _in_background(lambda: self.care.set_protect(changes), lambda: self._later(lambda: self.message.configure(
            text=i18n.get(self.lang, "care_saved"), fg=CYAN)))

    def _later(self, fn):
        if not self.closed:
            try:
                self.root.after(0, lambda: None if self.closed else fn())
            except RuntimeError:
                pass

    def close(self):
        if not self.closed:
            self.closed = True
            self.neon.destroy()
