"""The control panel's Credits tab (control_panel.py): the API credit log (credit_log.py). Totals for
today / 7 / 30 days and by source, then every entry: when, from where (text box, Telegram, voice,
cloud transcription, disk scan), what it was for, the model, the cost OpenRouter reported, the
balance before and after and their difference. Selecting an entry shows each request in it (model,
tokens, cost, the tools it called) and Tavily's credit before / after.

The data comes from a `service` (the credit_log module in the app, a fake in the tests); everything here
runs on the panel's Tk thread.
"""
import time
import tkinter as tk
from tkinter import ttk

import credit_log
import i18n
from chat_box import CYAN, MUTED, NAVY, NAVY_LIGHT, PINK, TEXT
from disk_panel import _style

COLUMNS = (("time", 108), ("source", 112), ("what", 250), ("model", 150), ("requests", 42), ("cost", 78),
           ("before", 72), ("after", 72), ("difference", 92))
PERIODS = (("today", None), ("week", 7), ("month", 30), ("all", 0))
MISMATCH = 0.2   # the balance difference and the reported cost disagree by more than this share


def money(x, digits=4):
    if x is None:
        return "—"
    if 0 < abs(x) < 0.001:
        return f"${x:.6f}"
    return f"${x:.{digits}f}"


def since(period, now=None):
    """Start of a period: today (midnight), the last 7 / 30 days, or everything (0)."""
    now = now or time.time()
    days = dict(PERIODS)[period]
    if days is None:
        t = time.localtime(now)
        return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
    return now - days * 86400 if days else 0


def models(entry):
    return ", ".join(dict.fromkeys(r.get("model", "") for r in entry.rounds)) or "—"


def difference_text(lang, entry):
    if entry.before is None:
        return "—"
    if entry.after is None:
        return i18n.get(lang, "credits_pending")
    return money(entry.difference) + (" *" if entry.overlap else "")


def details(lang, entry):
    """The selected entry, request by request."""
    t = lambda key, **kw: i18n.get(lang, key, **kw)  # noqa: E731
    lines = [f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry.started))} · "
             f"{t('credits_source_' + entry.source)} · {entry.what or '—'}"]
    for n, r in enumerate(entry.rounds, 1):
        tools = f" · {t('credits_tools')}: {', '.join(r['tools'])}" if r.get("tools") else ""
        lines.append(t("credits_round", n=n, model=r.get("model", "?"), prompt=r.get("prompt_tokens", 0),
                       completion=r.get("completion_tokens", 0), cost=money(r.get("cost", 0))) + tools)
    lines.append(t("credits_total", cost=money(entry.cost), before=money(entry.before), after=money(entry.after),
                   difference=money(entry.difference)))
    if entry.searches:
        used = (entry.tavily_before - entry.tavily_after
                if entry.tavily_before is not None and entry.tavily_after is not None else None)
        lines.append(t("credits_tavily", searches=entry.searches,
                       before=_number(entry.tavily_before), after=_number(entry.tavily_after),
                       used=_number(used)))
    if entry.overlap:
        lines.append(t("credits_overlap_note"))
    elif entry.difference is not None and abs(entry.difference - entry.cost) > max(0.0005, entry.cost * MISMATCH):
        lines.append(t("credits_mismatch_note"))
    if entry.before is None:
        lines.append(t("credits_no_before_note"))
    return "\n".join(lines)


def _number(x):
    if x is None:
        return "—"
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}"


class CreditTab:
    def __init__(self, root, win, lang, service, first_row=2):
        self.root, self.win, self.lang, self.service = root, win, lang, service
        self.closed = False
        self.entries_by_row = {}
        t = self.t
        win.columnconfigure(0, weight=1)
        win.columnconfigure(1, weight=0)
        win.rowconfigure(first_row + 3, weight=1)

        self.summary = tk.Label(win, text="", bg=NAVY, fg=TEXT, font=("Segoe UI", 10, "bold"), anchor="w",
                                justify="left")
        self.summary.grid(row=first_row, column=0, columnspan=2, sticky="ew", padx=16)
        self.by_source = tk.Label(win, text="", bg=NAVY, fg=MUTED, font=("Segoe UI", 9), anchor="w", justify="left")
        self.by_source.grid(row=first_row + 1, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 6))

        filters = tk.Frame(win, bg=NAVY)
        filters.grid(row=first_row + 2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 4))
        _style(ttk.Style(win), win)
        self.periods = [(p, t(f"credits_period_{p}")) for p, _ in PERIODS]
        self.sources = [("", t("credits_all_sources"))] + [(s, t(f"credits_source_{s}")) for s in credit_log.SOURCES]
        self.period_var = tk.StringVar(win, value=self.periods[1][1])   # master: see disk_panel
        self.source_var = tk.StringVar(win, value=self.sources[0][1])
        for var, values, width in ((self.period_var, self.periods, 14), (self.source_var, self.sources, 16)):
            box = ttk.Combobox(filters, textvariable=var, values=[label for _, label in values], state="readonly",
                               width=width, style="Disk.TCombobox")
            box.pack(side="left", padx=(0, 8))
            box.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        tk.Label(filters, text=t("credits_hint"), bg=NAVY, fg=MUTED, font=("Segoe UI", 8, "italic")).pack(side="left")

        table = tk.Frame(win, bg=NAVY)
        table.grid(row=first_row + 3, column=0, columnspan=2, sticky="nsew", padx=16)
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=[c for c, _ in COLUMNS], show="headings", style="Disk.Treeview",
                                 selectmode="browse")
        for column, width in COLUMNS:
            self.tree.heading(column, text=t(f"credits_col_{column}"))
            self.tree.column(column, width=width, minwidth=40, stretch=column == "what",
                             anchor="e" if column in ("requests", "cost", "before", "after", "difference") else "w")
        self.tree.tag_configure("overlap", foreground=MUTED)
        self.tree.tag_configure("pending", foreground=CYAN)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview, style="Disk.Vertical.TScrollbar")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._select())

        self.detail = tk.Label(win, text=t("credits_select"), bg=NAVY, fg=TEXT, font=("Segoe UI", 9), anchor="nw",
                               justify="left", wraplength=1000)
        self.detail.grid(row=first_row + 4, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 12))

        self.stop_listening = service.listen(lambda: self._later(self.refresh))
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

    def _choice(self, var, values):
        return next((k for k, label in values if label == var.get()), values[0][0])

    def refresh(self):
        led = self.service.ledger()
        now = time.time()
        sums = {p: led.totals(since(p, now)) for p in ("today", "week", "month")}

        def total(by):
            return sum(c for _, c in by.values()), sum(n for n, _ in by.values())

        parts = []
        for p in ("today", "week", "month"):
            cost, count = total(sums[p])
            parts.append(self.t("credits_summary_part", period=self.t(f"credits_period_{p}"), cost=money(cost),
                                count=count))
        self.summary.configure(text="  ·  ".join(parts))
        period = self._choice(self.period_var, self.periods)
        by = led.totals(since(period, now))
        self.by_source.configure(text="  ·  ".join(
            f"{self.t('credits_source_' + s)} {money(c)} ({n})"
            for s, (n, c) in sorted(by.items(), key=lambda x: -x[1][1])) or self.t("credits_empty"))
        selected = self._selected_id()
        self.tree.delete(*self.tree.get_children())
        self.entries_by_row = {}
        keep = None
        for e in led.entries(since(period, now), self._choice(self.source_var, self.sources) or None):
            values = (time.strftime("%m-%d %H:%M:%S", time.localtime(e.started)), self.t(f"credits_source_{e.source}"),
                      e.what or "—", models(e), e.requests, money(e.cost), money(e.before), money(e.after),
                      difference_text(self.lang, e))
            tags = ("pending",) if e.before is not None and e.after is None else ("overlap",) if e.overlap else ()
            row = self.tree.insert("", "end", values=values, tags=tags)
            self.entries_by_row[row] = e
            if e.id == selected:
                keep = row
        if keep is not None:
            self.tree.selection_set(keep)
        else:
            self.detail.configure(text=self.t("credits_select"))

    def _selected_id(self):
        rows = self.tree.selection()
        e = self.entries_by_row.get(rows[0]) if rows else None
        return e.id if e else None

    def _select(self):
        rows = self.tree.selection()
        e = self.entries_by_row.get(rows[0]) if rows else None
        self.detail.configure(text=details(self.lang, e) if e else self.t("credits_select"))

    def close(self):
        self.closed = True
        self.stop_listening()
