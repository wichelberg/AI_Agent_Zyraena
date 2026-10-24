"""User Care's windows, in the text box's neon look, on the text box's Tk thread (chat_box): every method
of Windows is thread-safe and never waits (chat_box.post).

- prompt / notice: a small panel in the top-right corner (the text box is at the bottom, beside the pet)
  that doesn't take the keyboard focus (a game or a sentence being typed goes on), with buttons.
- break_window: the voluntary break's countdown, with "I'm back".
- forced / final_countdown: one window per monitor covering it, always on top, no close button, raised
  again every second. Nothing blocks the keyboard or mouse; the way out is the emergency exit (forced
  break) or Cancel (shutdown), both needing a written reason.
- shutdown_warning: the "save your work" panel with the countdown and Cancel.
"""
import ctypes
import itertools
import time
import tkinter as tk
from ctypes import wintypes

import chat_box
import i18n
import paths
from chat_box import CYAN, MUTED, NAVY, NAVY_LIGHT, PINK, TEXT, _Neon
from desktop_pet import GWL_EXSTYLE, MONITORINFO, _work_area, user32

PROMPT_SIZE = (360, 170)
BREAK_SIZE = (330, 150)
WARNING_SIZE = (380, 200)
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
RAISE_MS = 1000
MIN_REASON_CHARS = 3
SOUND = "sounds/alert.mp3"
SOUND_SECONDS = 8
IMAGE = "assets/Zyraena.png"

MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                     wintypes.LPARAM)
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), MONITORENUMPROC, wintypes.LPARAM]
_sound_ids = itertools.count(1)


def monitors():
    """(left, top, right, bottom, primary) of every monitor, the primary first."""
    found = []

    def visit(handle, _dc, _rect, _data):
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(handle, ctypes.byref(info))
        r = info.rcMonitor
        found.append((r.left, r.top, r.right, r.bottom, bool(info.dwFlags & 1)))
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(visit), 0)
    return sorted(found, key=lambda m: not m[4]) or [(0, 0, 1920, 1080, True)]


def _hwnd(win):
    win.update_idletasks()
    return user32.GetParent(win.winfo_id())


def _no_focus(win):
    """Clicks still work, but the window never takes the keyboard from the app in front."""
    hwnd = _hwnd(win)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_NOACTIVATE)


def _corner(size):
    left, top, right, bottom = _work_area()
    pad = chat_box.MARGIN + chat_box.INSET
    return right - size[0] - pad - 12, top + pad + 12


def _clock(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02}:{seconds % 60:02}"


def _beep(root):
    """The alert sound once (alert.py loops it; here it's only a nudge)."""
    import alert

    alias = f"care_sound_{next(_sound_ids)}"
    alert._mci(f'open "{paths.resource_dir() / SOUND}" alias {alias}')
    alert._mci(f"play {alias}")
    root.after(SOUND_SECONDS * 1000, lambda: alert._mci(f"close {alias}"))


def _button(parent, text, command, color=CYAN, size=10):
    return tk.Button(parent, text=text, command=command, bg=NAVY_LIGHT, fg=color, activebackground=NAVY,
                     activeforeground=color, relief="flat", font=("Segoe UI", size, "bold"), padx=14, pady=3,
                     borderwidth=0, cursor="hand2")


class _Panel:
    """A small neon panel: title, text, an optional countdown line and buttons."""

    def __init__(self, root, size, title, text, at=None, focus=False):
        self.root, self.closed = root, False
        self.neon = _Neon(root, size, *(at or _corner(size)))
        win = self.win = self.neon.win
        tk.Label(win, text=title, bg=NAVY, fg=PINK, font=("Segoe UI", 10, "bold"), anchor="w").pack(
            fill="x", padx=12, pady=(10, 2))
        tk.Label(win, text=text, bg=NAVY, fg=TEXT, font=("Segoe UI", 10), wraplength=size[0] - 24, justify="left",
                 anchor="nw").pack(fill="both", expand=True, padx=12)
        self.countdown = tk.Label(win, text="", bg=NAVY, fg=CYAN, font=("Segoe UI", 11, "bold"), anchor="w")
        self.buttons = tk.Frame(win, bg=NAVY)
        self.buttons.pack(side="bottom", fill="x", padx=12, pady=(4, 12))
        if not focus:
            _no_focus(win)
        win.lift()

    def count(self, seconds, on_zero):
        """Shows a countdown from `seconds` (real time); on_zero() when it reaches 0."""
        self.countdown.pack(side="bottom", fill="x", padx=12, before=self.buttons)
        end = time.monotonic() + seconds

        def step():
            if self.closed:
                return
            left = end - time.monotonic()
            self.countdown.configure(text=_clock(left))
            if left <= 0:
                on_zero()
            else:
                self.root.after(250, step)
        step()

    def close(self):
        if not self.closed:
            self.closed = True
            self.neon.destroy()


class _Reason(tk.Frame):
    """A line for the reason and a button that only works once one is written."""

    def __init__(self, parent, lang, button, on_reason, bg=NAVY):
        super().__init__(parent, bg=bg)
        self.on_reason = on_reason
        tk.Label(self, text=i18n.get(lang, "care_reason_hint"), bg=bg, fg=MUTED,
                 font=("Segoe UI", 9, "italic")).pack(anchor="w")
        row = tk.Frame(self, bg=bg)
        row.pack(fill="x", pady=(2, 0))
        self.entry = tk.Entry(row, bg=NAVY_LIGHT, fg=TEXT, insertbackground=CYAN, relief="flat",
                              font=("Segoe UI", 11), highlightthickness=0, width=36)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        _button(row, button, self._go, PINK).pack(side="left", padx=(8, 0))
        self.entry.bind("<Return>", lambda e: self._go())

    def _go(self):
        reason = self.entry.get().strip()
        if len(reason) >= MIN_REASON_CHARS:
            self.on_reason(reason)
        else:
            self.entry.configure(bg="#3a1235")
            self.after(400, lambda: self.entry.winfo_exists() and self.entry.configure(bg=NAVY_LIGHT))


class _Fullscreen:
    """Covers every monitor; the primary one has the text, the countdown and the way out."""

    def __init__(self, root, lang, seconds, title, text, out_label, on_out, on_zero, prominent=False):
        self.root, self.closed = root, False
        self.wins = []
        for left, top, right, bottom, primary in monitors():
            win = tk.Toplevel(root)
            win.overrideredirect(True)
            win.configure(bg=NAVY)
            win.attributes("-topmost", True)
            win.geometry(f"{right - left}x{bottom - top}+{left}+{top}")
            win.protocol("WM_DELETE_WINDOW", lambda: None)  # Alt+F4 does nothing
            self.wins.append(win)
            if len(self.wins) == 1:  # monitors() lists the primary one first
                self._content(win, lang, right - left, bottom - top, title, text, out_label, on_out, prominent)
        self.countdowns = [tk.Label(w, text="", bg=NAVY, fg=CYAN, font=("Segoe UI", 64, "bold")) for w in self.wins[1:]]
        for label in self.countdowns:
            label.place(relx=0.5, rely=0.5, anchor="center")
        self.countdowns.insert(0, self.big)
        self.end = time.monotonic() + seconds
        self.on_zero = on_zero
        self._step()
        self._raise()

    def _content(self, win, lang, width, height, title, text, out_label, on_out, prominent):
        frame = tk.Frame(win, bg=NAVY)
        frame.place(relx=0.5, rely=0.5, anchor="center")
        self.image = self._image(height)
        if self.image is not None:
            tk.Label(frame, image=self.image, bg=NAVY).pack(side="left", padx=(0, 40))
        column = tk.Frame(frame, bg=NAVY)
        column.pack(side="left")
        tk.Label(column, text=title, bg=NAVY, fg=PINK, font=("Segoe UI", 28, "bold")).pack(anchor="w")
        tk.Label(column, text=text, bg=NAVY, fg=TEXT, font=("Segoe UI", 14), wraplength=min(720, width // 2),
                 justify="left").pack(anchor="w", pady=(12, 18))
        self.big = tk.Label(column, text="", bg=NAVY, fg=CYAN, font=("Segoe UI", 64, "bold"))
        self.big.pack(anchor="w")
        self.out = tk.Frame(column, bg=NAVY)
        self.out.pack(anchor="w", fill="x", pady=(24, 0))

        def show_reason():
            opener.destroy()
            reason = _Reason(self.out, lang, out_label, on_out)
            reason.pack(fill="x")
            reason.entry.focus_force()

        if prominent:  # cancelling a shutdown must be easy to find
            opener = _button(self.out, out_label, show_reason, PINK, 13)
        else:
            opener = tk.Button(self.out, text=out_label, command=show_reason, bg=NAVY, fg=MUTED, activebackground=NAVY,
                               activeforeground=PINK, relief="flat", font=("Segoe UI", 11), borderwidth=0,
                               cursor="hand2")
        opener.pack(anchor="w")

    def _image(self, height):
        try:
            from PIL import Image, ImageTk

            image = Image.open(paths.resource_dir() / IMAGE)
            h = int(height * 0.55)
            return ImageTk.PhotoImage(image.resize((max(1, int(image.width * h / image.height)), h)), master=self.root)
        except Exception:
            return None

    def _step(self):
        if self.closed:
            return
        left = self.end - time.monotonic()
        for label in self.countdowns:
            label.configure(text=_clock(left))
        if left <= 0:
            self.on_zero()
        else:
            self.root.after(250, self._step)

    def _raise(self):
        """Back on top every second (another window may have been put above it), without stealing focus."""
        if self.closed:
            return
        for win in self.wins:
            try:
                user32.SetWindowPos(_hwnd(win), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            except tk.TclError:
                return
        self.root.after(RAISE_MS, self._raise)

    def close(self):
        if not self.closed:
            self.closed = True
            for win in self.wins:
                win.destroy()


class Windows:
    """What user_care.Care calls. lang() -> the UI language. Seconds are real seconds."""

    def __init__(self, lang):
        self.lang = lang
        self.open = {}  # kind -> window (Tk thread only)

    def _post(self, fn):
        chat_box.post(lambda: fn(chat_box._state["root"]))

    def _replace(self, kind, window):
        old = self.open.pop(kind, None)
        if old is not None:
            old.close()
        if window is not None:
            self.open[kind] = window

    def _done(self, kind, window, fn, *args):
        """Closes `window` (if it's still the open one of its kind) and runs fn(*args)."""
        if self.open.get(kind) is window:
            self.open.pop(kind)
        window.close()
        if fn is not None:
            fn(*args)

    def close(self, kind):
        """kind: break, water, notice, break_window, forced, shutdown, final (notice closes all notices)."""
        def run(root):
            for key in [k for k in self.open if k == kind or (kind == "notice" and k.startswith("notice:"))]:
                self._replace(key, None)
        self._post(run)

    def prompt(self, kind, title, text, buttons, on_answer, sound=False):
        def run(root):
            panel = _Panel(root, PROMPT_SIZE, title, text)
            for label, value in reversed(buttons):
                _button(panel.buttons, label, lambda v=value: self._done(kind, panel, on_answer, v)).pack(
                    side="right", padx=(8, 0))
            self._replace(kind, panel)
            if sound:
                _beep(root)
        self._post(run)

    def notice(self, name, title, text, seconds=None, sound=False):
        kind = "notice:" + name

        def run(root):
            panel = _Panel(root, PROMPT_SIZE, title, text)
            _button(panel.buttons, i18n.get(self.lang(), "care_ok"), lambda: self._done(kind, panel, None)).pack(
                side="right")
            if seconds:
                root.after(int(seconds * 1000), lambda: self._done(kind, panel, None) if not panel.closed else None)
            self._replace(kind, panel)
            if sound:
                _beep(root)
        self._post(run)

    def break_window(self, seconds, title, text, on_done, on_back):
        def run(root):
            panel = _Panel(root, BREAK_SIZE, title, text)
            _button(panel.buttons, i18n.get(self.lang(), "care_back"),
                    lambda: self._done("break_window", panel, on_back)).pack(side="right")
            panel.count(seconds, lambda: self._done("break_window", panel, on_done))
            self._replace("break_window", panel)
        self._post(run)

    def forced(self, seconds, title, text, on_done, on_exit):
        def run(root):
            box = {}
            screen = _Fullscreen(root, self.lang(), seconds, title, text, i18n.get(self.lang(), "care_emergency_exit"),
                                 lambda reason: self._done("forced", box["it"], on_exit, reason),
                                 lambda: self._done("forced", box["it"], on_done))
            box["it"] = screen
            self._replace("forced", screen)
        self._post(run)

    def shutdown_warning(self, seconds, title, text, on_cancel):
        def run(root):
            panel = _Panel(root, WARNING_SIZE, title, text, focus=True)

            def ask_reason():
                opener.destroy()
                reason = _Reason(panel.buttons, self.lang(), i18n.get(self.lang(), "care_cancel"),
                                 lambda r: self._done("shutdown", panel, on_cancel, r))
                reason.pack(fill="x")
                reason.entry.focus_force()

            opener = _button(panel.buttons, i18n.get(self.lang(), "care_cancel_shutdown"), ask_reason, PINK)
            opener.pack(side="right")
            panel.count(seconds, lambda: None)  # Care moves on to the final countdown by itself
            self._replace("shutdown", panel)
            _beep(root)
        self._post(run)

    def final_countdown(self, seconds, title, text, on_cancel):
        def run(root):
            box = {}
            screen = _Fullscreen(root, self.lang(), seconds, title, text, i18n.get(self.lang(), "care_cancel_shutdown"),
                                 lambda reason: self._done("final", box["it"], on_cancel, reason), lambda: None,
                                 prominent=True)
            box["it"] = screen
            self._replace("final", screen)
        self._post(run)
