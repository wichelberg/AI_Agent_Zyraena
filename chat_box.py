"""The text box next to the pet (a click on her): a dark navy panel inside a double neon
frame, magenta to cyan, glowing outward. Typed messages go to Zyraena; her answer shows here
(silently) while the pet thinks and then talks. The same look asks yes/no before she changes
something on the PC (confirm).

The glow is a click-through layered window (per-pixel alpha); the panel itself is a plain Tk window
inside it. Everything runs on this module's own Tk thread; the functions at the bottom are
thread-safe.
"""
import ctypes
import threading
import tkinter as tk
from ctypes import wintypes

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import tkpost
from desktop_pet import (AC_SRC_ALPHA, BLENDFUNCTION, GWL_EXSTYLE, ULW_ALPHA, WS_EX_LAYERED, WS_EX_TOOLWINDOW,
                         WS_EX_TRANSPARENT, Frame, _work_area, gdi32, user32)

gdi32.DeleteDC.argtypes = [wintypes.HDC]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

NAVY = "#0b1431"
NAVY_LIGHT = "#12214a"
TEXT = "#dfe8ff"
PINK = "#ff5ad8"
CYAN = "#3fe4ff"
MUTED = "#7f8bb3"
MAGENTA_RGB = np.array([255, 40, 220], np.float32)
CYAN_RGB = np.array([30, 230, 255], np.float32)
MARGIN = 26         # room around the panel for the glow
INSET = 9           # from the inner neon line to the panel
BOX_SIZE = (430, 310)
CONFIRM_SIZE = (380, 170)
CONFIRM_TIMEOUT_SECONDS = 300


def neon_frame(width, height):
    """The frame as a PIL RGBA image (width x height, the panel MARGIN inside): two neon lines with
    a magenta-to-cyan sweep, a soft glow and a few flares, over a translucent navy fill."""
    w, h = width, height
    lines = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(lines)
    m = MARGIN - 4
    draw.rounded_rectangle((m, m, w - m, h - m), radius=6, outline=255, width=2)
    draw.rounded_rectangle((m + 5, m + 5, w - m - 5, h - m - 5), radius=4, outline=200, width=2)
    flares = Image.new("L", (w, h), 0)
    fd = ImageDraw.Draw(flares)
    for fx, fy, rx in ((0.35, 0, 40), (0.8, 0, 22), (0, 0.4, 16), (1, 0.7, 18), (0.6, 1, 34), (0.15, 1, 20)):
        cx, cy = m + fx * (w - 2 * m), m + fy * (h - 2 * m)
        horizontal = fy in (0, 1)
        fd.ellipse((cx - (rx if horizontal else 3), cy - (3 if horizontal else rx),
                    cx + (rx if horizontal else 3), cy + (3 if horizontal else rx)), fill=255)
    sharp = np.asarray(lines, np.float32) / 255
    glow = (np.asarray(lines.filter(ImageFilter.GaussianBlur(9)), np.float32) / 255 * 2.2
            + np.asarray(lines.filter(ImageFilter.GaussianBlur(3)), np.float32) / 255 * 1.2)
    flare = np.asarray(flares.filter(ImageFilter.GaussianBlur(5)), np.float32) / 255
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = np.clip((xx / w * 0.65 + yy / h * 0.35 - 0.15) / 0.7, 0, 1)[..., None]   # magenta top-left, cyan bottom-right
    color = MAGENTA_RGB * (1 - t) + CYAN_RGB * t
    inside = np.zeros((h, w), np.float32)
    inside[m + 2:h - m - 2, m + 2:w - m - 2] = 0.9
    light = np.clip(sharp + glow + flare, 0, 1)
    alpha = np.clip(np.maximum(inside, light), 0, 1)
    navy = np.array([11, 20, 49], np.float32)
    rgb = navy * (inside * (1 - light))[..., None] + color * light[..., None] + 255 * (sharp * 0.35 + flare * 0.6)[..., None]
    rgb = np.clip(rgb, 0, 255)
    return Image.fromarray(np.dstack([rgb, alpha * 255]).astype(np.uint8), "RGBA")


class _Neon:
    """A panel of `size` with the neon frame around it, at (x, y) (the panel's top left)."""

    def __init__(self, root, size, x, y):
        self.root = root
        pw, ph = size
        fw, fh = pw + 2 * (MARGIN + INSET), ph + 2 * (MARGIN + INSET)
        self.glow_win = tk.Toplevel(root)
        self.glow_win.overrideredirect(True)
        self.glow_win.attributes("-topmost", True)
        self.glow_win.geometry(f"{fw}x{fh}+{x - MARGIN - INSET}+{y - MARGIN - INSET}")
        self.glow_win.update_idletasks()
        hwnd = user32.GetParent(self.glow_win.winfo_id())
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT)
        screen_dc = user32.GetDC(None)
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        self.frame = Frame(neon_frame(fw, fh), screen_dc)
        old = gdi32.SelectObject(mem_dc, self.frame.bitmap)
        user32.UpdateLayeredWindow(hwnd, screen_dc, ctypes.byref(wintypes.POINT(x - MARGIN - INSET, y - MARGIN - INSET)),
                                   ctypes.byref(wintypes.SIZE(fw, fh)), mem_dc, ctypes.byref(wintypes.POINT(0, 0)), 0,
                                   ctypes.byref(BLENDFUNCTION(0, 0, 255, AC_SRC_ALPHA)), ULW_ALPHA)
        gdi32.SelectObject(mem_dc, old)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)
        self.win = tk.Toplevel(root)  # after the glow, so it's drawn above it
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=NAVY)
        self.win.geometry(f"{pw}x{ph}+{x}+{y}")

    def destroy(self):
        self.win.destroy()
        self.glow_win.destroy()
        self.frame.free()


def _place(size):
    """Where a panel of `size` goes: beside the pet (the side with more room), level with her chest;
    without her, the bottom-right corner."""
    import desktop_pet

    left, top, right, bottom = _work_area()
    pw, ph = size
    pad = MARGIN + INSET
    at = desktop_pet.anchor()
    if at is None:
        return right - pw - pad - 20, bottom - ph - pad - 20
    x, y, w, h = at
    if x + w / 2 > (left + right) / 2:
        px = x + w * 0.2 - pw - pad  # to her left
    else:
        px = x + w * 0.8 + pad
    py = y + h * 0.25
    px = int(min(max(left + pad, px), right - pw - pad))
    py = int(min(max(top + pad, py), bottom - ph - pad))
    return px, py


class ChatBox:
    def __init__(self, root, on_send, on_close, hint, thinking_text):
        self.root, self.on_send, self.on_close = root, on_send, on_close
        self.thinking_text = thinking_text
        self.neon = _Neon(root, BOX_SIZE, *_place(BOX_SIZE))
        win = self.neon.win
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)
        self.history = tk.Text(win, bg=NAVY, fg=TEXT, font=("Segoe UI", 10), wrap="word", relief="flat",
                               borderwidth=0, highlightthickness=0, padx=10, pady=8, cursor="arrow",
                               insertbackground=NAVY)
        self.history.grid(row=0, column=0, sticky="nsew")
        self.history.tag_configure("you", foreground=PINK, font=("Segoe UI", 10, "bold"))
        self.history.tag_configure("her", foreground=CYAN, font=("Segoe UI", 10, "bold"))
        self.history.tag_configure("note", foreground=MUTED, font=("Segoe UI", 9, "italic"))
        self.history.configure(state="disabled")
        self.status = tk.Label(win, text="", bg=NAVY, fg=MUTED, font=("Segoe UI", 9, "italic"), anchor="w", padx=10)
        self.status.grid(row=1, column=0, sticky="ew")
        line = tk.Frame(win, bg=PINK, height=1)
        line.grid(row=2, column=0, sticky="ew", padx=10)
        self.entry = tk.Entry(win, bg=NAVY_LIGHT, fg=TEXT, insertbackground=CYAN, relief="flat",
                              disabledbackground=NAVY_LIGHT, disabledforeground=MUTED,
                              font=("Segoe UI", 11), highlightthickness=0)
        self.entry.grid(row=3, column=0, sticky="ew", padx=10, pady=(6, 10), ipady=5)
        self.hint = hint
        self.status.configure(text=hint)  # the entry has the focus at once: the hint stays above it
        self.entry.bind("<Return>", self._send)
        for w in (win, self.entry, self.history):
            w.bind("<Escape>", lambda e: self.close())
        self._dots = 0
        self._thinking = False
        win.update_idletasks()
        win.lift()
        win.focus_force()
        self.entry.focus_set()

    def _send(self, event=None):
        text = self.entry.get().strip()
        if not text or self._thinking:
            return
        self.entry.delete(0, "end")
        self.on_send(text)

    def add(self, who, text, tag):
        self.history.configure(state="normal")
        if self.history.index("end-1c") != "1.0":
            self.history.insert("end", "\n\n")
        if who:
            self.history.insert("end", f"{who}: ", tag)
            self.history.insert("end", text)
        else:
            self.history.insert("end", text, tag)
        self.history.see("end")
        self.history.configure(state="disabled")

    def thinking(self, on):
        self._thinking = on
        self.entry.configure(state="disabled" if on else "normal")
        if on:
            self._tick()
        else:
            self.status.configure(text=self.hint)
            self.entry.focus_set()

    def _tick(self):
        if not self._thinking:
            return
        self._dots = self._dots % 3 + 1
        self.status.configure(text=self.thinking_text + "." * self._dots)
        self.root.after(400, self._tick)

    def close(self):
        self._thinking = False
        self.neon.destroy()
        self.on_close()


class Confirm:
    """Yes/no in the same look, beside the pet; answer(bool) is called once."""

    def __init__(self, root, title, question, yes, no, answer):
        self.answer, self.done = answer, False
        self.neon = _Neon(root, CONFIRM_SIZE, *_place(CONFIRM_SIZE))
        win = self.neon.win
        tk.Label(win, text=title, bg=NAVY, fg=PINK, font=("Segoe UI", 10, "bold"), anchor="w").pack(
            fill="x", padx=12, pady=(10, 2))
        tk.Label(win, text=question, bg=NAVY, fg=TEXT, font=("Segoe UI", 10), wraplength=CONFIRM_SIZE[0] - 24,
                 justify="left", anchor="w").pack(fill="both", expand=True, padx=12)
        buttons = tk.Frame(win, bg=NAVY)
        buttons.pack(fill="x", padx=12, pady=(4, 12))
        for text, value, color in ((no, False, PINK), (yes, True, CYAN)):
            tk.Button(buttons, text=text, command=lambda v=value: self._pick(v), bg=NAVY_LIGHT, fg=color,
                      activebackground=NAVY, activeforeground=color, relief="flat", font=("Segoe UI", 10, "bold"),
                      padx=14, pady=3, borderwidth=0, cursor="hand2").pack(side="right", padx=(8, 0))
        win.bind("<Escape>", lambda e: self._pick(False))
        win.bind("<Return>", lambda e: self._pick(True))
        win.lift()
        win.focus_force()

    def _pick(self, value):
        if self.done:
            return
        self.done = True
        self.neon.destroy()
        self.answer(value)


_state = {"root": None, "box": None, "mailbox": None}
_lock = threading.Lock()


def _ensure():
    with _lock:
        if _state["root"] is not None:
            return
        ready = threading.Event()

        def ui_thread():
            root = tk.Tk()
            root.withdraw()
            _state["mailbox"] = tkpost.Mailbox(root)  # how other threads reach this one: never waits
            _state["root"] = root
            ready.set()
            root.mainloop()

        threading.Thread(target=ui_thread, daemon=True).start()
        ready.wait()


def toggle(on_open, on_send, on_close, hint, thinking_text):
    """Thread-safe: opens the box (on_open() first) or closes it (on_close() after)."""
    _ensure()

    def run():
        if _state["box"] is not None:
            _state["box"].close()
            return
        on_open()

        def closed():
            _state["box"] = None
            on_close()

        _state["box"] = ChatBox(_state["root"], on_send, closed, hint, thinking_text)

    post(run)


def post(fn):
    """Thread-safe, never waits: fn() runs on this module's Tk thread (tkpost.Mailbox)."""
    _ensure()
    _state["mailbox"].post(fn)


def is_open():
    return _state["box"] is not None


def add(who, text, tag="her"):
    """Thread-safe: a line in the box ("you", "her" or "note"), if it's open."""
    if _state["root"] is not None:
        post(lambda: _state["box"] and _state["box"].add(who, text, tag))


def thinking(on):
    if _state["root"] is not None:
        post(lambda: _state["box"] and _state["box"].thinking(on))


def confirm(title, question, yes, no, timeout=CONFIRM_TIMEOUT_SECONDS):
    """Blocks the calling (worker) thread until yes/no is clicked; no after `timeout` seconds."""
    _ensure()
    result, done = {"ok": False}, threading.Event()

    def answer(value):
        result["ok"] = value
        done.set()

    box = {}
    post(lambda: box.setdefault("it", Confirm(_state["root"], title, question, yes, no, answer)))
    if not done.wait(timeout):
        post(lambda: box.get("it") and box["it"]._pick(False))
    return result["ok"]
