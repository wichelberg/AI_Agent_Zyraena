"""The control panel's Disk tab (control_panel.py): free / used space, the scanned items (type, size,
last use and where that date comes from, what it is, re-downloadable or not, dependencies), sortable
by any column and filtered by type and size, a timeline of the disk and of the selected item, and
what grew most this week. Delete works by the item's kind (disk_actions.plan) and always asks first,
listing what goes with the item and what breaks. There is no compress button, on purpose.

The data comes from a `service` (disk_watch in the app, a fake in the tests); everything here runs on
the panel's Tk thread.
"""
import threading
import time
import tkinter as tk
from tkinter import ttk

import disk_actions
import disk_tools
import i18n
from chat_box import CYAN, MUTED, NAVY, NAVY_LIGHT, PINK, TEXT, _Neon
from desktop_pet import _work_area
from disk_watch import size_text

RED = "#ff4d6d"
SELECT = "#24407a"
DISK_SIZE = (1080, 660)
CONFIRM_SIZE = (560, 380)
KEEP_ON_TOP_MS = 250
COLUMNS = (("kind", 75), ("name", 220), ("size", 72), ("used", 205), ("what", 240), ("redl", 112), ("deps", 150))
MIN_SIZES = ((0, "0"), (100 * 1024 ** 2, "100 MB"), (1024 ** 3, "1 GB"), (10 * 1024 ** 3, "10 GB"))


def disk_size(work_area):
    """The Disk tab's panel size, smaller on a small screen."""
    left, top, right, bottom = work_area
    return min(DISK_SIZE[0], right - left - 120), min(DISK_SIZE[1], bottom - top - 120)


def used_text(lang, item, now=None):
    """'2026-10-21 · 3 days · Steam' style text for the Last used column."""
    now = now or time.time()
    source = i18n.get(lang, f"disk_src_{item.used_source}") if item.used_source else ""
    if not item.last_used:
        return source or "—"
    days = int((now - item.last_used) // 86400)
    when = time.strftime("%Y-%m-%d", time.localtime(item.last_used))
    ago = i18n.get(lang, "disk_days_ago", days=days) if days > 0 else i18n.get(lang, "disk_today")
    return f"{when} · {ago} · {source}"


def what_text(lang, item):
    if not item.what:
        return "—"
    if item.what_source == "gemini":
        return f"{item.what}  [{i18n.get(lang, 'disk_what_src_gemini')}]"
    return item.what


def deps_text(lang, item, by_id, users, same):
    """The Dependencies column: what's missing first (shown red), then what it needs and who uses it."""
    if item.broken:
        return i18n.get(lang, "disk_deps_missing", path=item.broken[0])
    parts = []
    names = [by_id[d].name for d in item.dep_ids if d in by_id]
    if names:
        parts.append(i18n.get(lang, "disk_deps_needs", names=", ".join(names)))
    if users.get(item.id):
        parts.append(i18n.get(lang, "disk_deps_used_by", count=len(users[item.id])))
    if same.get(item.id):
        parts.append(i18n.get(lang, "disk_deps_same", names=", ".join(same[item.id])))
    return " · ".join(parts) or "—"


def sort_key(column, item):
    return {
        "kind": item.kind, "name": item.name.lower(), "size": item.size, "used": item.last_used or 0,
        "what": item.what.lower(), "redl": item.redownloadable, "deps": (bool(item.broken), len(item.dep_ids)),
    }[column]


class DiskTab:
    def __init__(self, root, win, lang, service, places=None, first_row=2):
        self.root, self.win, self.lang, self.service = root, win, lang, service
        self.places = places
        self.closed = False
        self.sort_column, self.sort_reverse = "size", True
        self.selected = None
        self.scan = None
        self.items_by_row = {}
        self.confirm = None
        t = self.t
        win.columnconfigure(0, weight=3)
        win.columnconfigure(1, weight=2)
        win.rowconfigure(first_row + 2, weight=1)

        top = tk.Frame(win, bg=NAVY)
        top.grid(row=first_row, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 6))
        top.columnconfigure(1, weight=1)
        self.free_label = tk.Label(top, text="", bg=NAVY, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w")
        self.free_label.grid(row=0, column=0, sticky="w")
        self.bar = tk.Canvas(top, height=10, bg=NAVY_LIGHT, highlightthickness=0)
        self.bar.grid(row=0, column=1, sticky="ew", padx=12)
        self.scan_button = self._button(top, t("disk_scan_button"), self._scan, CYAN)
        self.scan_button.grid(row=0, column=2, sticky="e")
        self.status = tk.Label(top, text="", bg=NAVY, fg=MUTED, font=("Segoe UI", 8, "italic"), anchor="w")
        self.status.grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

        filters = tk.Frame(win, bg=NAVY)
        filters.grid(row=first_row + 1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 4))
        self.kinds = [("", t("disk_filter_all"))] + [(k, t(f"disk_kind_{k}")) for k in disk_tools.KINDS]
        # The master matters: without one tkinter uses the process's first Tk root, the pet's, on another
        # thread, and that deadlocks while the pet reads window titles (2026-10-21: the panel opened blank).
        self.kind_var = tk.StringVar(win, value=self.kinds[0][1])
        self.min_var = tk.StringVar(win, value=MIN_SIZES[1][1])
        _style(ttk.Style(win), win)
        kind_box = ttk.Combobox(filters, textvariable=self.kind_var, values=[label for _, label in self.kinds],
                                state="readonly", width=16, style="Disk.TCombobox")
        kind_box.pack(side="left")
        tk.Label(filters, text=t("disk_filter_min"), bg=NAVY, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(12, 4))
        min_box = ttk.Combobox(filters, textvariable=self.min_var, values=[label for _, label in MIN_SIZES],
                               state="readonly", width=8, style="Disk.TCombobox")
        min_box.pack(side="left")
        for box in (kind_box, min_box):
            box.bind("<<ComboboxSelected>>", lambda e: self.fill())

        table = tk.Frame(win, bg=NAVY)
        table.grid(row=first_row + 2, column=0, columnspan=2, sticky="nsew", padx=16)
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=[c for c, _ in COLUMNS], show="headings", style="Disk.Treeview",
                                 selectmode="browse")
        for column, width in COLUMNS:
            self.tree.heading(column, text=t(f"disk_col_{column}"), command=lambda c=column: self._sort(c))
            self.tree.column(column, width=width, minwidth=50, stretch=column in ("name", "what", "deps"),
                             anchor="e" if column == "size" else "w")
        self.tree.tag_configure("broken", foreground=RED)
        self.tree.tag_configure("protected", foreground=MUTED)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview, style="Disk.Vertical.TScrollbar")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._select())

        details = tk.Frame(win, bg=NAVY)
        details.grid(row=first_row + 3, column=0, sticky="nsew", padx=(16, 8), pady=(8, 12))
        details.columnconfigure(0, weight=1)
        self.details = tk.Label(details, text=t("disk_select"), bg=NAVY, fg=TEXT, font=("Segoe UI", 9),
                                justify="left", anchor="nw", wraplength=560)
        self.details.grid(row=0, column=0, sticky="nw")
        self.delete_button = self._button(details, t("disk_delete"), self._ask_delete, PINK)
        self.delete_button.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.delete_button.configure(state="disabled")
        self.delete_note = tk.Label(details, text="", bg=NAVY, fg=MUTED, font=("Segoe UI", 8, "italic"), anchor="w",
                                    justify="left", wraplength=560)
        self.delete_note.grid(row=2, column=0, sticky="w")
        self.result_label = tk.Label(details, text="", bg=NAVY, fg=CYAN, font=("Segoe UI", 9, "bold"), anchor="w",
                                     justify="left", wraplength=560)
        self.result_label.grid(row=3, column=0, sticky="w", pady=(4, 0))  # the last delete's outcome

        side = tk.Frame(win, bg=NAVY)
        side.grid(row=first_row + 3, column=1, sticky="nsew", padx=(8, 16), pady=(8, 12))
        side.columnconfigure(0, weight=1)
        tk.Label(side, text=t("disk_timeline"), bg=NAVY, fg=PINK, font=("Segoe UI", 9, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w")
        self.timeline = tk.Canvas(side, height=110, bg=NAVY_LIGHT, highlightthickness=0)
        self.timeline.grid(row=1, column=0, sticky="ew")
        tk.Label(side, text=t("disk_growers"), bg=NAVY, fg=PINK, font=("Segoe UI", 9, "bold"), anchor="w").grid(
            row=2, column=0, sticky="w", pady=(6, 0))
        self.growers = tk.Label(side, text="", bg=NAVY, fg=TEXT, font=("Segoe UI", 9), justify="left", anchor="nw")
        self.growers.grid(row=3, column=0, sticky="nw")

        self.stop_listening = service.listen(lambda: self._later(self.refresh))
        self.refresh()

    def t(self, key, **kw):
        return i18n.get(self.lang, key, **kw)

    def _button(self, parent, text, command, color):
        return tk.Button(parent, text=text, command=command, bg=NAVY_LIGHT, fg=color, activebackground=NAVY,
                         activeforeground=color, relief="flat", font=("Segoe UI", 9, "bold"), padx=12, pady=3,
                         borderwidth=0, cursor="hand2", disabledforeground=MUTED)

    def _later(self, fn):
        if self.closed:
            return
        try:
            self.root.after(0, lambda: None if self.closed else fn())
        except RuntimeError:
            pass

    # --- data ---

    def refresh(self):
        self.scan = self.service.latest()
        running = self.service.running()
        self.scan_button.configure(state="disabled" if running else "normal")
        if running:
            self.status.configure(text=self.service.progress() or self.t("disk_scanning"))
        elif self.scan is None:
            self.status.configure(text=self.t("disk_never_scanned"))
        else:
            self.status.configure(text=self.t("disk_last_scan", when=time.strftime("%Y-%m-%d %H:%M",
                                                                                  time.localtime(self.scan.at)),
                                              seconds=self.scan.stats.get("seconds", 0), items=len(self.scan.items)))
        self._free()
        self.fill()
        self._growers()

    def _free(self):
        scan = self.scan
        self.bar.delete("all")
        if scan is None or not scan.total:
            self.free_label.configure(text="")
            return
        drive = (self.places.drive if self.places else "C:\\")
        self.free_label.configure(text=self.t("disk_free_line", drive=str(drive).rstrip("\\"), free=size_text(scan.free),
                                              total=size_text(scan.total), used=size_text(scan.used)))
        self.bar.update_idletasks()
        width = max(self.bar.winfo_width(), 200)
        share = scan.used / scan.total
        self.bar.create_rectangle(0, 0, int(width * share), 10, fill=PINK if share > 0.85 else CYAN, width=0)

    def rows(self):
        """The items the filters let through, sorted."""
        if self.scan is None:
            return []
        kind = next((k for k, label in self.kinds if label == self.kind_var.get()), "")
        min_size = next((s for s, label in MIN_SIZES if label == self.min_var.get()), 0)
        items = [it for it in self.scan.items if (not kind or it.kind == kind)
                 and (it.size >= min_size or (it.kind == "link" and kind == "link") or it.broken)]
        return sorted(items, key=lambda it: sort_key(self.sort_column, it), reverse=self.sort_reverse)

    def fill(self):
        self.tree.delete(*self.tree.get_children())
        self.items_by_row = {}
        if self.scan is None:
            return
        by_id = self.scan.by_id()
        users = {}
        for it in self.scan.items:
            for d in it.dep_ids:
                users.setdefault(d, []).append(it.id)
        same = {}
        for group in disk_tools.duplicate_venvs(self.scan.items):
            for it in group:
                same[it.id] = [o.name for o in group if o is not it]
        keep = None
        for it in self.rows():
            values = (self.t(f"disk_kind_{it.kind}"), it.name, size_text(it.size) + ("~" if it.size_source == "registry" else ""),
                      used_text(self.lang, it), what_text(self.lang, it),
                      self.t("disk_yes") if it.redownloadable else self.t("disk_no"), deps_text(self.lang, it, by_id, users, same))
            tags = ("broken",) if it.broken else ("protected",) if it.protected else ()
            row = self.tree.insert("", "end", values=values, tags=tags)
            self.items_by_row[row] = it
            if self.selected is not None and it.id == self.selected.id:
                keep = row
        self.users = users
        if keep is not None:
            self.tree.selection_set(keep)
            self.tree.see(keep)
        else:
            self.selected = None
            self._show(None)

    def _sort(self, column):
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column, self.sort_reverse = column, column in ("size", "used", "deps")
        self.fill()

    def _select(self):
        rows = self.tree.selection()
        self.selected = self.items_by_row.get(rows[0]) if rows else None
        self._show(self.selected)

    def _show(self, it):
        if it is None:
            self.details.configure(text=self.t("disk_select"))
            self.delete_button.configure(state="disabled")
            self.delete_note.configure(text="")
            self._timeline(None)
            return
        lines = [f"{it.name}  ·  {size_text(it.size)}"]
        if it.shared:
            lines[0] += "  " + self.t("disk_shared", size=size_text(it.shared))
        if it.path:
            lines.append(f"{self.t('disk_details_path')}: {it.path}" + (f"  (+{len(it.parts)})" if it.parts else ""))
        lines.append(f"{self.t('disk_col_used')}: {used_text(self.lang, it)}")
        if it.what:
            lines.append(f"{self.t('disk_col_what')}: {it.what} ({self.t('disk_what_src_' + it.what_source)})")
        if "redownloadable_guess" in it.info:
            lines.append(self.t("disk_guess_redl", value=self.t("disk_yes" if it.info["redownloadable_guess"] else "disk_no")))
        if it.broken:
            lines.append(self.t("disk_deps_missing", path=", ".join(it.broken)))
        self.details.configure(text="\n".join(lines))
        p = disk_actions.plan(it)
        if p is None:
            self.delete_button.configure(state="disabled")
            self.delete_note.configure(text=self.t("disk_protected", reason=it.protected) if it.protected
                                       else self.t("disk_no_action"))
        else:
            self.delete_button.configure(state="normal")
            self.delete_note.configure(text="")
        self._timeline(it)

    def _growers(self):
        try:
            rows = self.service.store().history.growers(days=7, limit=6)
        except Exception:
            rows = []
        self.growers.configure(text="\n".join(f"+{size_text(d)}  {name}" for _, name, _, d in rows)
                               or self.t("disk_growers_none"), fg=TEXT if rows else MUTED)

    def _timeline(self, item):
        """Two small charts: total used space and, below it, the selected item's size, scan by scan."""
        c = self.timeline
        c.delete("all")
        try:
            history = self.service.store().history
            totals = [(at, used) for at, used, _ in history.totals()]
            mine = history.item_sizes(item.id) if item is not None else []
        except Exception:
            totals, mine = [], []
        c.update_idletasks()
        width, height = max(c.winfo_width(), 260), 110
        half = height // 2
        self._series(c, totals, 0, half - 4, width, CYAN, self.t("disk_timeline_total"))
        if item is not None:
            self._series(c, mine, half + 4, height, width, PINK, item.name)

    def _series(self, c, points, y0, y1, width, color, label):
        c.create_text(6, y0 + 2, text=label, anchor="nw", fill=MUTED, font=("Segoe UI", 7))
        if not points:
            return
        times = [p[0] for p in points]
        values = [p[1] for p in points]
        lo, hi = min(values), max(values)
        t0, t1 = min(times), max(times)
        c.create_text(width - 6, y0 + 2, text=size_text(values[-1]), anchor="ne", fill=color, font=("Segoe UI", 7, "bold"))
        coords = []
        for at, value in points:
            x = 10 + (width - 20) * ((at - t0) / (t1 - t0) if t1 > t0 else 1)
            y = y1 - 6 - (y1 - y0 - 20) * ((value - lo) / (hi - lo) if hi > lo else 0.5)
            coords += [x, y]
        if len(coords) >= 4:
            c.create_line(*coords, fill=color, width=2)
        for i in range(0, len(coords), 2):
            c.create_oval(coords[i] - 2, coords[i + 1] - 2, coords[i] + 2, coords[i + 1] + 2, fill=color, width=0)

    # --- actions ---

    def _scan(self):
        if self.service.scan_now():
            self.scan_button.configure(state="disabled")
            self.status.configure(text=self.t("disk_scanning"))

    def _ask_delete(self):
        it = self.selected
        p = disk_actions.plan(it) if it is not None else None
        if p is None or self.scan is None or self.confirm is not None:
            return
        going, breaking = disk_tools.dependents(it, self.scan.items)
        self.confirm = ConfirmDelete(self.root, self.lang, it, p, going, breaking, self._delete)

    def _delete(self, it, p, ok):
        self.confirm = None
        if not ok:
            return
        self.delete_button.configure(state="disabled")
        self.result_label.configure(text=self.t("disk_deleting"), fg=MUTED)

        def work():
            places = self.places or disk_tools.Places.real()
            result = disk_actions.execute(p, places)
            if result.ok and not result.started:
                self.service.after_delete(self.scan, it)
            self._later(lambda: self._done(it, result))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, it, result):
        if result.error == "too_big_for_bin":
            text, color = self.t("disk_too_big_for_bin", size=size_text(it.size), free=size_text(result.bin_free)), PINK
        elif result.error == "not_in_bin":
            text, color = self.t("disk_not_in_bin", name=it.name), PINK
        elif not result.ok:
            text, color = self.t("disk_failed", error=result.error), PINK
        elif result.started:
            text, color = self.t("disk_started", name=it.name), CYAN
        else:
            text, color = self.t("disk_done", name=it.name, freed=size_text(result.freed)), CYAN
        self.refresh()
        self.result_label.configure(text=text, fg=color)

    def close(self):
        self.closed = True
        self.stop_listening()
        if self.confirm is not None:
            self.confirm.pick(False)


class ConfirmDelete:
    """"Delete X?" with how it goes, what goes with it and what breaks; answer(item, plan, bool) once."""

    def __init__(self, root, lang, item, p, going, breaking, answer):
        self.item, self.plan, self.answer, self.done = item, p, answer, False
        left, top, right, bottom = _work_area()
        self.neon = _Neon(root, CONFIRM_SIZE, (left + right - CONFIRM_SIZE[0]) // 2, (top + bottom - CONFIRM_SIZE[1]) // 2)
        win = self.neon.win
        t = lambda key, **kw: i18n.get(lang, key, **kw)  # noqa: E731
        tk.Label(win, text=t("disk_confirm_title", name=item.name), bg=NAVY, fg=PINK, font=("Segoe UI", 11, "bold"),
                 anchor="w", wraplength=CONFIRM_SIZE[0] - 28, justify="left").pack(fill="x", padx=14, pady=(12, 4))
        how = {"url": t("disk_how_url", appid=item.info.get("appid", "")),
               "uninstaller": t("disk_how_uninstaller", command=p.describe()),
               "command": t("disk_how_command", command=p.describe()),
               "delete": t("disk_how_delete", size=size_text(p.size)),
               "trash": t("disk_how_trash", size=size_text(p.size)),
               "contents": t("disk_how_contents")}[p.mode]
        lines = [how, ""]
        if going:
            lines.append(t("disk_confirm_inside"))
            lines += [f"  • {g.name} ({size_text(g.size)})" for g in going[:12]]
            if len(going) > 12:
                lines.append(f"  … +{len(going) - 12}")
        if breaking:
            lines.append(t("disk_confirm_breaks"))
            lines += [f"  • {b.name} — {t('disk_kind_' + b.kind)}" for b in breaking[:12]]
            if len(breaking) > 12:
                lines.append(f"  … +{len(breaking) - 12}")
        if not going and not breaking:
            lines.append(t("disk_confirm_nothing"))
        text = tk.Text(win, bg=NAVY, fg=TEXT, font=("Segoe UI", 9), wrap="word", relief="flat", borderwidth=0,
                       highlightthickness=0, height=12)
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        text.pack(fill="both", expand=True, padx=14)
        self.text = "\n".join(lines)
        buttons = tk.Frame(win, bg=NAVY)
        buttons.pack(fill="x", padx=14, pady=(4, 12))
        for label, value, color in ((t("disk_confirm_no"), False, CYAN), (t("disk_confirm_yes"), True, PINK)):
            tk.Button(buttons, text=label, command=lambda v=value: self.pick(v), bg=NAVY_LIGHT, fg=color,
                      activebackground=NAVY, activeforeground=color, relief="flat", font=("Segoe UI", 10, "bold"),
                      padx=14, pady=3, borderwidth=0, cursor="hand2").pack(side="right", padx=(8, 0))
        win.bind("<Escape>", lambda e: self.pick(False))
        self.root = root
        win.focus_force()
        self._keep_on_top()

    def _keep_on_top(self):
        """The panel is topmost too: a click on it would cover this window (2026-10-21: the Delete button
        ended up hidden behind it). So this window goes back on top as long as it's open."""
        if self.done:
            return
        self.neon.glow_win.lift()
        self.neon.win.lift()
        self.root.after(KEEP_ON_TOP_MS, self._keep_on_top)

    def pick(self, value):
        if self.done:
            return
        self.done = True
        self.neon.destroy()
        self.answer(self.item, self.plan, value)


def _style(style, win):
    style.theme_use("clam")
    for option, value in (("background", NAVY_LIGHT), ("foreground", TEXT), ("selectBackground", SELECT),
                          ("selectForeground", TEXT)):
        win.option_add(f"*TCombobox*Listbox.{option}", value)
    style.configure("Disk.Treeview", background=NAVY, fieldbackground=NAVY, foreground=TEXT, rowheight=22,
                    borderwidth=0, font=("Segoe UI", 9))
    style.map("Disk.Treeview", background=[("selected", SELECT)], foreground=[("selected", TEXT)])
    style.configure("Disk.Treeview.Heading", background=NAVY_LIGHT, foreground=CYAN, relief="flat",
                    font=("Segoe UI", 9, "bold"))
    style.map("Disk.Treeview.Heading", background=[("active", SELECT)])
    style.configure("Disk.TCombobox", fieldbackground=NAVY_LIGHT, background=NAVY_LIGHT, foreground=TEXT,
                    arrowcolor=CYAN, bordercolor=NAVY_LIGHT, lightcolor=NAVY_LIGHT, darkcolor=NAVY_LIGHT)
    style.map("Disk.TCombobox", fieldbackground=[("readonly", NAVY_LIGHT)], foreground=[("readonly", TEXT)],
              selectbackground=[("readonly", NAVY_LIGHT)], selectforeground=[("readonly", TEXT)])
    style.configure("Disk.Vertical.TScrollbar", background=NAVY_LIGHT, troughcolor=NAVY, arrowcolor=CYAN,
                    bordercolor=NAVY, lightcolor=NAVY_LIGHT, darkcolor=NAVY_LIGHT)
