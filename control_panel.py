"""The panel Ctrl+F1 opens in the middle of the screen, in the text box's neon look, with four tabs.
General: a button that hides or shows the pet (the way back when she's hidden), the live OpenRouter
and Tavily credits, fetched in the background once each time it opens ("loading…" until they
arrive), and a button to the API credit log. Credits: what each paid request cost and what it was
for (credit_panel.py). Disk: what takes the space and deleting it (disk_panel.py); the pet's "Disk: new
findings" bubble opens the panel on this tab. Care: User Care's mood, timers, protection list and
events (care_panel.py). Esc or Ctrl+F1 again closes it. It shares the text
box's Tk thread (chat_box); toggle() and show() are thread-safe.
"""
import threading
import tkinter as tk

import chat_box
import care_panel
import credit_panel
import disk_panel
import i18n
from chat_box import CYAN, MUTED, NAVY, NAVY_LIGHT, PINK, TEXT, _Neon
from desktop_pet import _work_area

PANEL_SIZE = (360, 214)
TABS = ("general", "credits", "disk", "care")
CREDITS_BUTTON_HEIGHT = 38

_state = {"panel": None}


def openrouter_text(lang, balance):
    """What the OpenRouter row shows for openrouter_balance()'s result (USD or None)."""
    if balance is None:
        return i18n.get(lang, "panel_failed")
    return f"${balance:.2f}"


def tavily_text(lang, result):
    """What the Tavily row shows for _get_tavily_credits()'s (kind, data)."""
    kind, data = result
    if kind == "ok":
        def number(x):
            return str(int(x)) if float(x).is_integer() else f"{x:.1f}"
        return i18n.get(lang, "panel_tavily_value", remaining=number(data["remaining"]), limit=number(data["limit"]))
    return i18n.get(lang, "panel_unknown" if kind == "unknown" else "panel_failed")


def _center(size):
    left, top, right, bottom = _work_area()
    pw, ph = size
    return (left + right - pw) // 2, (top + bottom - ph) // 2


class Panel:
    def __init__(self, root, lang, pet_visible, toggle_pet, fetch_openrouter, fetch_tavily, on_close, disk=None,
                 tab="general", credits=None, care=None):
        self.root, self.lang, self.pet_visible, self.toggle_pet = root, lang, pet_visible, toggle_pet
        self.on_close, self.disk, self.credits, self.care = on_close, disk, credits, care
        self.closed = False
        self.neon = self.tab = self.disk_tab = self.credit_tab = self.care_tab = None
        self.values, self.results = {}, {}
        self.show_tab(tab)
        self._fetch("openrouter", fetch_openrouter, lambda v: openrouter_text(lang, v), lambda v: v is not None)
        self._fetch("tavily", fetch_tavily, lambda v: tavily_text(lang, v), lambda v: v[0] == "ok")

    def show_tab(self, tab):
        """Builds the panel for a tab (the Disk tab is bigger, so the window is made again)."""
        if tab not in TABS or self._service(tab) is None:
            tab = "general"
        if tab == self.tab or self.closed:
            return
        self._close_tab()
        if self.neon is not None:
            self.neon.destroy()
        self.tab = tab
        size = (self._general_size() if tab == "general" else care_panel.care_size(_work_area()) if tab == "care"
                else disk_panel.disk_size(_work_area()))
        self.neon = _Neon(self.root, size, *_center(size))
        win = self.neon.win
        self._header(win)
        if tab == "general":
            self._general(win)
        elif tab == "disk":
            self.disk_tab = disk_panel.DiskTab(self.root, win, self.lang, self.disk, first_row=2)
            self.disk_tab.tree.bind("<Escape>", lambda e: self.close())
        elif tab == "care":
            self.care_tab = care_panel.CareTab(self.root, win, self.lang, self.care, first_row=2)
        else:
            self.credit_tab = credit_panel.CreditTab(self.root, win, self.lang, self.credits, first_row=2)
            self.credit_tab.tree.bind("<Escape>", lambda e: self.close())
        win.bind("<Escape>", lambda e: self.close())
        win.update_idletasks()
        win.lift()
        win.focus_force()

    def _service(self, tab):
        return {"general": True, "disk": self.disk, "credits": self.credits, "care": self.care}.get(tab)

    def _general_size(self):
        return PANEL_SIZE[0], PANEL_SIZE[1] + (CREDITS_BUTTON_HEIGHT if self.credits is not None else 0)

    def _close_tab(self):
        for name in ("disk_tab", "credit_tab", "care_tab"):
            view = getattr(self, name)
            if view is not None:
                view.close()
                setattr(self, name, None)

    def _header(self, win):
        win.columnconfigure(1, weight=1)
        tk.Label(win, text=i18n.get(self.lang, "panel_title"), bg=NAVY, fg=PINK, font=("Segoe UI", 13, "bold"),
                 anchor="w").grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        tabs = tk.Frame(win, bg=NAVY)
        tabs.grid(row=0, column=1, sticky="e", padx=16, pady=(12, 4))
        self.tab_buttons = {}
        for name in TABS:
            if self._service(name) is None:
                continue
            active = name == self.tab
            button = tk.Button(tabs, text=i18n.get(self.lang, f"panel_tab_{name}"), command=lambda n=name: self.show_tab(n),
                               bg=NAVY_LIGHT if active else NAVY, fg=PINK if active else MUTED, activebackground=NAVY,
                               activeforeground=CYAN, relief="flat", font=("Segoe UI", 9, "bold"), padx=10, pady=1,
                               borderwidth=0, cursor="hand2")
            button.pack(side="left", padx=(6, 0))
            self.tab_buttons[name] = button
        tk.Frame(win, bg=PINK, height=1).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 8))

    def _general(self, win):
        self.values = {}
        for row, (key, label) in enumerate((("openrouter", "panel_openrouter"), ("tavily", "panel_tavily")), 2):
            tk.Label(win, text=i18n.get(self.lang, label), bg=NAVY, fg=TEXT, font=("Segoe UI", 10),
                     anchor="w").grid(row=row, column=0, sticky="w", padx=(16, 8), pady=3)
            shown, color = self.results.get(key, (i18n.get(self.lang, "panel_loading"), MUTED))
            value = tk.Label(win, text=shown, bg=NAVY, fg=color, font=("Segoe UI", 10, "bold"), anchor="e")
            value.grid(row=row, column=1, sticky="e", padx=(8, 16), pady=3)
            self.values[key] = value
        self.pet_button = tk.Button(win, command=self._toggle_pet, bg=NAVY_LIGHT, fg=CYAN, activebackground=NAVY,
                                    activeforeground=CYAN, relief="flat", font=("Segoe UI", 10, "bold"),
                                    padx=14, pady=4, borderwidth=0, cursor="hand2")
        self.pet_button.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 4))
        self._show_pet_state(self.pet_visible())
        row = 5
        if self.credits is not None:
            self.credits_button = tk.Button(win, text=i18n.get(self.lang, "panel_credit_log"),
                                            command=lambda: self.show_tab("credits"), bg=NAVY_LIGHT, fg=PINK,
                                            activebackground=NAVY, activeforeground=PINK, relief="flat",
                                            font=("Segoe UI", 10, "bold"), padx=14, pady=4, borderwidth=0,
                                            cursor="hand2")
            self.credits_button.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 4))
            row += 1
        tk.Label(win, text=i18n.get(self.lang, "panel_hint"), bg=NAVY, fg=MUTED, font=("Segoe UI", 8, "italic"),
                 anchor="center").grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 8))

    def _fetch(self, key, fetch, text, ok):
        """fetch() on a worker thread; its result shows as text(result), cyan if ok(result), else pink."""
        def work():
            try:
                result = fetch()
                shown, good = text(result), ok(result)
            except Exception:
                shown, good = i18n.get(self.lang, "panel_failed"), False
            self._later(lambda: self._set(key, shown, CYAN if good else PINK))

        threading.Thread(target=work, daemon=True).start()

    def _later(self, fn):
        try:
            self.root.after(0, fn)
        except RuntimeError:  # the Tk thread is gone (shutting down)
            pass

    def _set(self, key, text, color):
        self.results[key] = (text, color)
        if not self.closed and self.tab == "general":
            self.values[key].configure(text=text, fg=color)

    def _show_pet_state(self, visible):
        self.pet_button.configure(text=i18n.get(self.lang, "panel_pet_hide" if visible else "panel_pet_show"))

    def _toggle_pet(self):
        """desktop_pet.toggle may start her (and wait for her Tk thread), so it runs off this thread."""
        self.pet_button.configure(state="disabled")

        def work():
            try:
                visible = self.toggle_pet()
            except Exception:
                visible = None

            def done():
                if self.closed or self.tab != "general":
                    return
                self.pet_button.configure(state="normal")
                if visible is not None:
                    self._show_pet_state(visible)
            self._later(done)

        threading.Thread(target=work, daemon=True).start()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._close_tab()
        self.neon.destroy()
        self.on_close()


def toggle(lang, pet_visible, toggle_pet, fetch_openrouter, fetch_tavily, disk=None, credits=None, care=None):
    """Thread-safe: opens the panel or closes it. pet_visible() -> bool, toggle_pet() -> visible after,
    fetch_openrouter() -> USD or None, fetch_tavily() -> (kind, data); the fetches run on worker threads.
    disk: the Disk tab's service (disk_watch), credits: the credit log (credit_log), care: User Care
    (user_care.Care); without them those tabs aren't there."""
    _run(lambda root: _state["panel"].close() if _state["panel"] is not None
         else _open(root, lang, pet_visible, toggle_pet, fetch_openrouter, fetch_tavily, disk, "general", credits,
                    care))


def show(tab, lang, pet_visible, toggle_pet, fetch_openrouter, fetch_tavily, disk=None, credits=None, care=None):
    """Thread-safe: opens the panel on `tab`, or switches the open panel to it."""
    def run(root):
        if _state["panel"] is not None:
            _state["panel"].show_tab(tab)
        else:
            _open(root, lang, pet_visible, toggle_pet, fetch_openrouter, fetch_tavily, disk, tab, credits, care)
    _run(run)


def _run(fn):
    chat_box._ensure()
    root = chat_box._state["root"]
    chat_box.post(lambda: fn(root))  # never waits: the caller may be the pet's Tk thread


def _open(root, lang, pet_visible, toggle_pet, fetch_openrouter, fetch_tavily, disk, tab, credits=None, care=None):
    def closed():
        _state["panel"] = None

    _state["panel"] = Panel(root, lang, pet_visible, toggle_pet, fetch_openrouter, fetch_tavily, closed, disk, tab,
                            credits, care)


def is_open():
    return _state["panel"] is not None
