"""Zyraena on the desktop: a full-body sprite living along the bottom of the screen.

What she does depends on what is open on her monitor (checked twice a second):

- Nothing (the bare desktop): her throne stands in the bottom-right corner. Most of the time
  (SIT_CHANCE) she sits on it with her legs crossed, like the owner of this PC; now and then
  she gets up, walks around, stops to look at you and says something, then goes back to it.
- A code editor (VS Code and the like) on top: the throne goes away and she works with you.
  She takes her place in the bottom-right corner (clear of the file explorer), facing the
  screen, summons a holographic screen of code and a keyboard of light, and types along, now
  and then commenting or stopping for a stretch before getting back to it.
- Any other window (a browser, an app): no throne. She wanders, crosses her arms to watch
  the screen (more often in a browser), curls a dumbbell to show off, spins her dagger or
  stretches (PASTIMES). Off the throne on the bare desktop she does the same, minus watching.
- A fullscreen window in front (game mode): she walks to the nearer screen edge and leans
  her back on it to watch, and mouse clicks go through her to the game. She says nothing
  meanwhile. When it ends she straightens up and carries on.

She can be picked up with the mouse and dropped (she falls back to the floor); a click opens
the text box beside her (chat_box.py), a right click shows a small menu. In a conversation (the
text box, or a spoken one: voice_session.py) she stops what she's doing and faces you, thinks
while the answer comes and talks while it's given (set_activity).

Frames come from assets/pet/<animation>/NNN.png, rendered by pet/blender/zyraena_real.py:
walk (to the right; mirrored for left), turn/turn1/turn2/turn3 (from walking right to facing you,
starting at each quarter of the walk cycle: she stops at the nearest one), idle,
talk, drag, sitdown (standing to seated), sit, leanin (turning her back to a wall and
leaning on it), lean, codein (from idle to typing, the hologram appearing), code, watchin
(crossing her arms), watch, liftin (the dumbbell appearing in her hand), lift, stretchin,
stretch, daggerin (the dagger appearing in her fist), dagger, thinkin (her hand going to her chin,
her elbow on her other arm), think, and throne
(the empty throne, drawn in its own window behind her). codein/code and watchin/watch face
the left, toward the screen from its right corner; mirrored they face the right. The window
is a Win32 layered window updated with per-pixel alpha (UpdateLayeredWindow), so soft edges
and hair stay clean on any background, and clicks on transparent pixels go to whatever is
behind her.

assets/pet/meta.json (written by the renderer): the walk speed; "tracks", how far the window moves
with each frame of a transition so the boot she stands on stays still on the floor; "pingpong", the
loops rendered as half a cycle and played forward and back. Animation frames are kept zlib-compressed
and unpacked into one shared bitmap as they are drawn (as bitmaps, both facings of ~850 frames would
take several hundred MB).

ZYRAENA_PET=off turns her off; ZYRAENA_PET_HEIGHT sets her height in pixels (default 351).
Hidden from her menu, she comes back from the Ctrl+F1 panel (control_panel.py); that choice is kept
in pet.json.

Every couple of seconds she checks her own window (shown, on top, on a screen) and puts it
right if something outside knocked it off. That, errors, and the user hiding her (usually
because she went missing) are written to pet_log.txt next to the app, with her recent states.
"""
import ctypes
import json
import math
import os
import random
import threading
import time
import tkinter as tk
import traceback
import zlib
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from datetime import datetime

import numpy as np
from PIL import Image, ImageOps

import i18n
import paths
import tkpost

FRAME_MS = 20  # 50 fps
# Ticks each frame stays on screen: the walk and the turns play every frame (50 fps; a walk cycle is
# 60 frames = 1.2 s), everything else every other one (25 fps).
TURNS = ("turn", "turn1", "turn2", "turn3")  # stopping from walk frame 0, n/4, n/2 and 3n/4
HOLD = {"walk": 1, **{turn: 1 for turn in TURNS}}
DEFAULT_HOLD = 2
# Walking to a place (the throne, her corner, a screen edge): within this many walk cycles of it she
# plans her last steps so the walk ends at a quarter of its cycle right where the turn and what follows
# leave her at the place; the strides are stretched or shortened for it, within STRIDE_LIMITS.
ARRIVE_CYCLES = 2
STRIDE_LIMITS = (0.8, 1.25)
# Poses she holds for a while, each entered by playing "<pose>in" and left by playing it backwards.
POSES = ("code", "watch", "lift", "stretch", "dagger", "impatient")
DEFAULT_HEIGHT = 351  # 340 before the high platform boots: her body keeps its size, the boots add to it
# Used only without meta.json: one 60-frame walk cycle covers ~1.44 m, seen at 55 degrees.
WALK_SPEED_PER_HEIGHT = 1.44 * 0.82 / 2.5 / 60
GRAVITY = 0.09  # px per tick^2 while falling
DRAG_THRESHOLD = 5  # px of mouse movement that turns a click into a drag
WALK_SECONDS = (5, 12)
IDLE_SECONDS = (6, 14)
SIT_SECONDS = (18, 40)  # one sitting spell; she often stays for several (SIT_CHANCE), ~75% of her time overall
SIT_CHANCE = 0.75  # each time she picks what to do next: back to (or stay on) the throne
TALK_CHANCE = 0.5
BUBBLE_SECONDS = 6
THRONE_MARGIN = 24  # px between the throne and the right edge of the screen
GAME_CHECK_TICKS = 25  # how often (in ticks, 0.5 s) to look at what is open on her monitor
CONTEXT_CHECKS = 2  # a new reading must hold this many checks in a row (a start menu flashing by doesn't count)
WINDOW_CHECK_TICKS = 100  # how often (2 s) she makes sure her window is still shown and on top
HISTORY_SIZE = 30  # recent states kept for pet_log.txt
LOG_MAX_BYTES = 200_000
LOG_REPEAT_SECONDS = 60  # the same problem is logged at most once a minute
POSE_SECONDS = {"code": (40, 90),  # while coding: how often she thinks about saying something or a break
                "watch": (10, 25), "lift": (6, 12), "stretch": (4, 7), "dagger": (5, 9),
                "impatient": (20, 35)}  # after a snoozed or unanswered break (User Care)
# What she picks to do next, by what's open on her monitor (whatever is left over: walk on).
# On the bare desktop these only come up when she doesn't go back to the throne (SIT_CHANCE).
PASTIMES = {"browse": {"watch": 0.45, "lift": 0.15, "dagger": 0.15, "stretch": 0.1},
            "app": {"watch": 0.25, "lift": 0.2, "dagger": 0.2, "stretch": 0.1},
            "desktop": {"dagger": 0.3, "stretch": 0.2, "lift": 0.15}}
# Her mood from User Care (user_care.py: tone() is happy/normal/angry, or worried instead of angry at
# night). Happy is how she always was; the others stand, talk and sit their own way. A mood without frames
# for something falls back along MOOD_FALLBACK, then to the plain animation.
MOOD_ANIMS = {"angry": {"idle": "angry_idle", "talk": "angry_talk", "sit": "angry_sit"},
              "normal": {"idle": "normal_idle", "talk": "normal_talk", "sit": "normal_sit"},
              "worried": {"idle": "worried", "talk": "worried"}}
MOOD_FALLBACK = {"worried": "normal"}
MOOD_CHECK_TICKS = 250  # how often (5 s) she looks at her mood
# Pastime odds by mood, times PASTIMES (angry: more dagger and dumbbell, hardly any stretching).
MOOD_PASTIMES = {"angry": {"dagger": 2.0, "lift": 2.0, "stretch": 0.3, "watch": 0.8},
                 "normal": {"stretch": 0.7},
                 "worried": {"lift": 0.5, "dagger": 0.5}}
IMPATIENT_WINDOW = 120  # s: a snoozed or unanswered break older than this doesn't make her impatient
# What her body is doing, as a tree: each pose is entered from its parent by playing its entry animation
# (backwards to leave it). Moving between any two poses plays the way through the tree (see _bridge), so
# a mood's stance is left before she sits down, walks off or takes another pose. Loops not named here
# are their own pose; "walk" is entered by the turns.
ENTRIES = {"angry": ("angry_in", "stand"), "angry_talk": ("angry_talkin", "angry"),
           "normal": ("normal_in", "stand"), "worried": ("worried_in", "stand"),
           "sit": ("sitdown", "stand"), "angry_sit": ("angry_sitdown", "stand"),
           "normal_sit": ("normal_sitdown", "stand"), "lean": ("leanin", "stand"), "think": ("thinkin", "stand")}
POSE_OF = {"idle": "stand", "talk": "stand", "angry_idle": "angry", "normal_idle": "normal",
           "normal_talk": "normal", "drag": None}
FINISH_LOOPS = ("angry_talk",)  # left only at the end of a loop (the arm back where the entry has it)
CODE_BREAK_CHANCE = 0.25  # now and then she stops typing to stretch, then gets back to work
SHORT_WALK_SECONDS = (1.5, 3)  # a few steps to face the middle of the screen before watching it
MIN_COVER = 0.15  # a window counts as open on her monitor when it covers this much of it
CODE_APPS = {"code.exe", "code - insiders.exe", "cursor.exe", "windsurf.exe", "devenv.exe", "pycharm64.exe",
             "idea64.exe", "rider64.exe", "webstorm64.exe", "sublime_text.exe", "zed.exe"}
BROWSERS = {"opera.exe", "opera_gx.exe", "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "vivaldi.exe",
            "arc.exe", "zen.exe"}
SHELL_PROCESSES = {"shellexperiencehost.exe", "startmenuexperiencehost.exe", "searchhost.exe", "searchapp.exe",
                   "textinputhost.exe", "lockapp.exe"}
SHELL_CLASSES = {"Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow"}

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION = 0x00C00000
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TRANSPARENT = 0x00000020  # mouse clicks pass through the window
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOPMOST = 0x00000008
MONITOR_DEFAULTTONULL = 0
MONITOR_DEFAULTTONEAREST = 2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
HWND_TOPMOST = -1
SW_SHOWNOACTIVATE = 4
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
DESKTOP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
ULW_ALPHA = 0x2
AC_SRC_ALPHA = 0x1
DIB_RGB_COLORS = 0
SPI_GETWORKAREA = 0x0030


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromRect.restype = wintypes.HANDLE
user32.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
    wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION),
    wintypes.DWORD]
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wintypes.UINT]
kernel32 = ctypes.windll.kernel32
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
dwmapi = ctypes.windll.dwmapi
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]  # a 64-bit handle overflows the default int

_state = {"pet": None, "callbacks": None}
PREF_FILE = paths.app_dir() / "pet.json"
LOG_FILE = paths.app_dir() / "pet_log.txt"


def _log(text):
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            LOG_FILE.replace(LOG_FILE.with_name("pet_log.old.txt"))
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")
    except OSError:
        pass


def enabled():
    """Off with ZYRAENA_PET=off, or when the user hid her with the chat window's button."""
    if os.environ.get("ZYRAENA_PET", "").strip().lower() in ("off", "0", "false", "no"):
        return False
    try:
        return bool(json.loads(PREF_FILE.read_text(encoding="utf-8")).get("visible", True))
    except (OSError, ValueError):
        return True


def _remember(visible):
    try:
        PREF_FILE.write_text(json.dumps({"visible": visible}), encoding="utf-8")
    except OSError:
        pass


def _height():
    try:
        return max(80, int(os.environ.get("ZYRAENA_PET_HEIGHT", "").strip()))
    except ValueError:
        return DEFAULT_HEIGHT


def _work_area():
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right, rect.bottom


def _fullscreen_monitor(pet_hwnd, own):
    """The rect of the pet's monitor when the foreground window covers all of it (a game or a
    fullscreen video), else None. The desktop, the taskbar and the pet's own windows don't count,
    and neither does a maximized window with a title bar: with the taskbar on auto-hide the work
    area is the whole monitor, so every maximized app covers it too (2026-10-21)."""
    fg = user32.GetForegroundWindow()
    if not fg or fg in own:
        return None
    name = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(fg, name, 64)
    if name.value in DESKTOP_CLASSES:
        return None
    if user32.IsZoomed(fg) and user32.GetWindowLongW(fg, GWL_STYLE) & WS_CAPTION == WS_CAPTION:
        return None
    monitor = user32.MonitorFromWindow(fg, MONITOR_DEFAULTTONEAREST)
    if monitor != user32.MonitorFromWindow(pet_hwnd, MONITOR_DEFAULTTONEAREST):
        return None
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    rect = wintypes.RECT()
    user32.GetWindowRect(fg, ctypes.byref(rect))
    m = info.rcMonitor
    if rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom:
        return m.left, m.top, m.right, m.bottom
    return None


def _process_name(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return pid.value, ""
    try:
        path = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size))
        return pid.value, os.path.basename(path.value).lower()
    finally:
        kernel32.CloseHandle(handle)


def _screen_context(pet_hwnd):
    """What is open on the pet's monitor, judged by the topmost app window that covers a fair
    part of it (MIN_COVER): "code" for an editor, "browse" for a browser, "app" for anything
    else, "desktop" when there's none. Minimized, cloaked (other virtual desktops, suspended
    store apps) and tool windows don't count, and neither do this app's own windows."""
    monitor = user32.MonitorFromWindow(pet_hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    m = info.rcMonitor
    area = (m.right - m.left) * (m.bottom - m.top)
    own_pid = os.getpid()
    found = []

    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == own_pid:
            # Before anything else: GetWindowTextLength sends a message to a window of this process and
            # waits for its thread; if that thread waits for the pet's, both hang (2026-10-21).
            return True
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd) or not user32.GetWindowTextLengthW(hwnd):
            return True
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if style & WS_EX_TOOLWINDOW and not style & WS_EX_APPWINDOW:
            return True
        cloaked = wintypes.DWORD()
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:
            return True
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, name, 64)
        if name.value in DESKTOP_CLASSES or name.value in SHELL_CLASSES:
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = min(rect.right, m.right) - max(rect.left, m.left)
        h = min(rect.bottom, m.bottom) - max(rect.top, m.top)
        if w <= 0 or h <= 0 or w * h < MIN_COVER * area:
            return True
        pid, exe = _process_name(hwnd)
        if pid == own_pid or exe in SHELL_PROCESSES:
            return True
        found.append(exe)
        return False  # the topmost one decides

    user32.EnumWindows(WNDENUMPROC(visit), 0)
    if not found:
        return "desktop"
    return "code" if found[0] in CODE_APPS else "browse" if found[0] in BROWSERS else "app"


def _premultiplied(image):
    """An RGBA image as the premultiplied BGRA bytes UpdateLayeredWindow wants."""
    rgba = np.asarray(image, dtype=np.uint16)
    alpha = rgba[..., 3:4]
    return np.concatenate([rgba[..., 2::-1] * alpha // 255, alpha], axis=2).astype(np.uint8).tobytes()


def _dib(dc, width, height):
    """A top-down 32-bit DIB section: (handle, pointer to its pixels)."""
    header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=width,
                              biHeight=-height, biPlanes=1, biBitCount=32, biCompression=0)
    bits = ctypes.c_void_p()
    handle = gdi32.CreateDIBSection(dc, ctypes.byref(header), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
    return handle, bits


class Frame:
    """One sprite as a premultiplied 32-bit bitmap ready for UpdateLayeredWindow."""

    def __init__(self, image, dc):
        self.width, self.height = image.size
        self.bitmap, bits = _dib(dc, self.width, self.height)
        data = _premultiplied(image)
        ctypes.memmove(bits, data, len(data))

    def free(self):
        gdi32.DeleteObject(self.bitmap)


class Sprite:
    """An animation frame kept zlib-compressed; .bitmap unpacks it into a bitmap shared by every
    sprite of its size (drawn one at a time on the pet's thread, and UpdateLayeredWindow copies it)."""

    _canvases = {}  # (dc, width, height) -> (handle, pixels)

    def __init__(self, image, dc):
        self.width, self.height = image.size
        self.dc = dc
        self.data = zlib.compress(_premultiplied(image), 1)

    @property
    def bitmap(self):
        key = (self.dc, self.width, self.height)
        if key not in Sprite._canvases:
            Sprite._canvases[key] = _dib(self.dc, self.width, self.height)
        handle, bits = Sprite._canvases[key]
        data = zlib.decompress(self.data)
        ctypes.memmove(bits, data, len(data))
        return handle


def _alpha_box(path, cutoff):
    with Image.open(path) as image:
        return image.convert("RGBA").getchannel("A").point(lambda a: 255 if a > cutoff else 0).getbbox()


def _load_animations(dc, height):
    """{name: {1: frames facing right/you, -1: mirrored}}, cropped to their shared bounds, and what
    meta.json says about them, in window pixels. One image at a time per thread (all ~850 at once
    would take ~800 MB); PIL and zlib release the GIL, so the threads share the work."""
    root = paths.resource_dir() / "assets" / "pet"
    files = {folder.name: sorted(folder.glob("*.png")) for folder in sorted(p for p in root.iterdir() if p.is_dir())}
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        boxes = [box for box in pool.map(lambda path: _alpha_box(path, 8), [p for ps in files.values() for p in ps])
                 if box]
        bounds = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                  max(b[3] for b in boxes))
        scale = height / (bounds[3] - bounds[1])
        size = (round((bounds[2] - bounds[0]) * scale), height)

        def load(name, path):
            with Image.open(path) as image:
                right = image.convert("RGBA").crop(bounds).resize(size, Image.LANCZOS)
            box = right.getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
            if name == "throne":
                return Frame(right, dc), None, box
            return Sprite(right, dc), Sprite(ImageOps.mirror(right), dc), box

        loaded = {name: list(pool.map(lambda path, name=name: load(name, path), paths_))
                  for name, paths_ in files.items()}
    try:  # measured in Blender, in render pixels
        meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    walk_speed = meta["walk_px_per_frame"] * scale if "walk_px_per_frame" in meta else None
    tracks = {name: [v * scale for v in track] for name, track in meta.get("tracks", {}).items()}
    animations, extents = {}, {}
    for name, frames in loaded.items():
        animations[name] = {1: [f[0] for f in frames]}
        if name != "throne":
            animations[name][-1] = [f[1] for f in frames]
        boxes = [f[2] for f in frames if f[2]]
        if boxes:  # horizontal extent of the visible figure (facing right), in window pixels
            extents[name] = (min(b[0] for b in boxes), max(b[2] for b in boxes))
    return animations, size, walk_speed, extents, tracks, set(meta.get("pingpong", ()))


class Pet:
    def __init__(self, root, on_click, language):
        self.root, self.on_click, self.language = root, on_click, language
        self.history = deque(maxlen=HISTORY_SIZE)  # recent states, for pet_log.txt
        self.logged = {}  # problem text -> when it was last logged
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.screen_dc = user32.GetDC(None)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)
        self.anims, (self.w, self.h), walk_speed, self.extents, self.tracks, self.pingpong = _load_animations(
            self.screen_dc, _height())
        self.game = None  # the fullscreen monitor's rect while in game mode
        self.edge = 1  # which screen edge she leans on: 1 right, -1 left
        self.blend = BLENDFUNCTION(0, 0, 255, AC_SRC_ALPHA)
        self.blank = Frame(Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0)), self.screen_dc)  # the throne, away
        self.throne_win = None
        if "throne" in self.anims:  # created before her window, so she's drawn above it
            self.throne_win = tk.Toplevel(root)
            self.throne_win.overrideredirect(True)
            self.throne_win.attributes("-topmost", True)
            self.throne_hwnd = self._layered(self.throne_win)
            self.throne_win.bind("<ButtonPress-1>", self._throne_click)
        self.win.lift()
        self.hwnd = self._layered(self.win)
        self.throne_shown = self.throne_win is not None

        left, _, right, bottom = _work_area()
        self.y = bottom - self.h
        self.dir = -1
        self.speed = walk_speed or self.h * WALK_SPEED_PER_HEIGHT
        self.held = 0  # ticks the current frame has been shown
        self.vy = 0.0
        self.tick = 0
        # [animation, facing, frame indexes, the frame taken as shown before the first] to play before
        # the state continues; walk and tracked frames move the window as they're shown (_shift)
        self.queue = []
        self.track_at = None  # the queued frame shown last, for _shift
        self.walk_step = self.speed  # window px per queued walk frame (_stop)
        self.snap_x = None  # where she must stand once the queue is done (_arrive)
        self.then = None  # a pose to take at the end of the current walk (see _walk_on)
        self.context = _screen_context(self.hwnd)  # what's open on her monitor (see _screen_context)
        self.pending, self.pending_hits = self.context, 0
        self.pose = None  # she appears in her first pose (no way into it)
        self.mood, self.last_nag = self._read_mood()
        if self.throne_win is not None and self.context == "desktop":  # she starts on her throne
            self.x = self._throne_x()
            self._set_state("sit", SIT_SECONDS, "sit", 1)
        else:  # a window is already open: she appears standing and picks what to do (_decide)
            self.x = random.randint(left, max(left, right - self.w))
            self._set_state("idle", (1, 2), "idle", 1)
        self.drag_from = None
        self.bubble = None
        self.hidden = False

        self.win.bind("<ButtonPress-1>", self._press)
        self.win.bind("<B1-Motion>", self._motion)
        self.win.bind("<ButtonRelease-1>", self._release)
        self.win.bind("<ButtonPress-3>", self._menu)
        self._loop()

    def _layered(self, win):
        win.geometry(f"{self.w}x{self.h}+0+0")
        win.update_idletasks()
        hwnd = user32.GetParent(win.winfo_id())
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TOOLWINDOW)
        return hwnd

    def _area(self):
        """Where she lives: the whole monitor in game mode (no taskbar), else the work area."""
        return self.game if self.game else _work_area()

    def _click_through(self, on):
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        style = style | WS_EX_TRANSPARENT if on else style & ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style)

    def _edge_x(self):
        """Window x that puts her back (the lean frames' far edge) right on the screen edge."""
        left, _, right, _ = self.game
        ext_left, ext_right = self.extents["lean"]
        return right - ext_right if self.edge > 0 else left - (self.w - ext_right)

    def _check_screen(self):
        if self.state in ("drag", "fall"):
            return
        if "lean" in self.anims:
            own = {self.hwnd, getattr(self, "throne_hwnd", None)}
            monitor = _fullscreen_monitor(self.hwnd, own)
            if monitor and not self.game:
                self._enter_game(monitor)
            elif self.game and not monitor:
                self.context = self.pending = _screen_context(self.hwnd)
                self._exit_game()
            if self.game:
                return
        context = _screen_context(self.hwnd)
        if context != self.pending:
            self.pending, self.pending_hits = context, 0
        self.pending_hits += 1
        if context != self.context and self.pending_hits >= CONTEXT_CHECKS:
            self._change_context(context)

    def _change_context(self, context):
        """Something was opened, closed or brought to the front on her monitor."""
        self.context = context
        if self.state == "busy":
            return  # talking with the owner: what's open can wait
        if self.state in POSES:
            if self.state == "code" and context == "code":
                return
            if self.state != "code" and context not in ("desktop", "code"):
                return  # watching or lifting suits any open window
            self._leave_pose()
            self._decide()
        elif self.state == "sit":
            if context != "desktop":
                self._hide_bubble()
                self._get_up()
                self.facing = 1
                self._decide()
        elif self.state == "to_throne" and context != "desktop":
            self._decide()
        elif self.state == "to_work" and context != "code":
            self._decide()
        elif self.state == "idle" and context != "desktop":  # a window just came up: react to it
            self._decide()
        elif context == "code" and self.state in ("walk", "idle", "talk"):
            if self.state == "walk":
                self._stop_and_face()
            self._decide()

    def _sync_throne(self):
        """The throne stands only on the bare desktop (or while she's still on it, getting up),
        always just behind her: a click on it would otherwise bring it in front of her.
        Away it is drawn fully transparent (invisible, clicks go through) rather than withdrawn:
        a Tk window withdrawn while it was still being mapped came back as a blank white box."""
        if self.throne_win is None:
            return
        wanted = not self.game and (self.context == "desktop" or self.state == "sit"
                                    or any(entry[0].endswith("sitdown") for entry in self.queue))
        changed = wanted != self.throne_shown
        self.throne_shown = wanted
        if changed and not wanted:
            _, _, _, bottom = _work_area()
            self._draw(self.blank, self.throne_hwnd, self._throne_x(), bottom - self.h)
        if wanted and (changed or self.tick % GAME_CHECK_TICKS == 0):
            self._throne_behind()

    def _throne_behind(self):
        user32.SetWindowPos(self.throne_hwnd, self.hwnd, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _throne_click(self, event):
        self._throne_behind()
        self.on_click()

    def _enter_game(self, monitor):
        self._hide_bubble()
        self.game = monitor
        self._click_through(True)
        self._clear_queue()
        if self.state == "sit":
            self._get_up()
        elif self.state in POSES:
            self._leave_pose()
        left, _, right, bottom = monitor
        self.y = bottom - self.h
        self.edge = 1 if self.x + self.w / 2 >= (left + right) / 2 else -1
        target = self._edge_x()
        self.dir = (1 if target > self.x else -1) if abs(target - self.x) > self.speed else self.edge
        if self._close_to(target - self._track_total("leanin") * self.edge) and self.anim != "walk":
            self.x = target - self._track_total("leanin") * self.edge  # no room for steps: lean right away
            self._play("leanin", self.edge, range(1, len(self.anims["leanin"][1])), shown=0)
            self._set_state("lean", (600, 600), "lean", self.edge)
        elif self.state in ("walk", "to_throne", "to_work") and self.anim == "walk":
            self.state = "to_edge"  # walking already: on in her stride
        else:
            self._start_walk("to_edge", (600, 600))

    def _exit_game(self):
        was_leaning = self.state == "lean"
        self.game = None
        self._click_through(False)
        self._clear_queue()
        _, _, right, bottom = _work_area()
        self.y = bottom - self.h
        self.x = min(self.x, right - self.w)  # back inside the work area
        if was_leaning:
            last = len(self.anims["leanin"][1]) - 1
            self._play("leanin", self.edge, range(last - 1, -1, -1), shown=last)
            self.dir = self.edge
        self._decide()

    def _throne_x(self):
        _, _, right, _ = _work_area()
        return right - self.w - THRONE_MARGIN

    @staticmethod
    def _ticks(seconds_range):
        return int(random.uniform(*seconds_range) * 1000 / FRAME_MS)

    # --- Drawing ----------------------------------------------------------------------

    def _draw(self, frame, hwnd=None, x=None, y=None):
        hwnd = self.hwnd if hwnd is None else hwnd
        x, y = (self.x, self.y) if x is None else (x, y)
        old = gdi32.SelectObject(self.mem_dc, frame.bitmap)
        user32.UpdateLayeredWindow(hwnd, self.screen_dc, ctypes.byref(wintypes.POINT(int(x), int(y))),
                                   ctypes.byref(wintypes.SIZE(frame.width, frame.height)), self.mem_dc,
                                   ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(self.blend), ULW_ALPHA)
        gdi32.SelectObject(self.mem_dc, old)

    def _play(self, anim, facing, indexes, shown=None):
        """Queues frames of anim; shown is the frame of it already on screen (where the first one's
        move is counted from, see _shift). If her body isn't in the pose they start from, the way there
        is queued first (_bridge)."""
        indexes = list(indexes)
        if indexes:
            start, end = self._ends(anim, indexes)
            self._bridge(start, facing)
            self.queue.append([anim, facing, indexes, shown])
            self.pose, self.pose_facing = end, facing

    # --- Poses and moods ----------------------------------------------------------------

    # Defaults for a Pet made without __init__ (the tests).
    mood = None  # User Care's tone (see MOOD_ANIMS); None: happy, or no User Care
    pose, pose_facing = "stand", 1  # where the queued frames leave her body (see ENTRIES); None: anywhere
    last_nag, nag_until = None, None

    @staticmethod
    def _pose_of(anim):
        return POSE_OF.get(anim, anim)

    @staticmethod
    def _entry(pose):
        """(entry animation, parent pose) of a pose, or None for "stand", "walk" and loose loops."""
        return ENTRIES.get(pose) or ((pose + "in", "stand") if pose in POSES else None)

    def _ends(self, anim, indexes):
        """The poses frames of anim start and end in (an entry played backwards leaves its pose)."""
        if anim in TURNS:
            ends = ("walk", "stand")
        else:
            pose = anim[:-2] if anim.endswith("in") and anim[:-2] in POSES else next(
                (name for name, (entry, _) in ENTRIES.items() if entry == anim), None)
            if pose is None:
                pose = self._pose_of(anim)
                return pose, pose
            ends = (self._entry(pose)[1], pose)
        return ends if indexes[-1] >= indexes[0] else ends[::-1]

    def _path(self, pose):
        """The poses from "stand" down to pose, or None if there's no way (walk, missing frames)."""
        path = [pose]
        while path[-1] != "stand":
            entry = self._entry(path[-1])
            if entry is None or entry[0] not in self.anims:
                return None
            path.append(entry[1])
        return path[::-1]

    def _bridge(self, target, facing):
        """Queues the way from the pose her body is in to target: back up the tree (entries played
        backwards), then down to target. Nothing if either is loose (None) or has no way."""
        here = self.pose
        if here is None or target is None or here == target:
            return
        up, down = self._path(here), self._path(target)
        if up is None or down is None:
            return
        k = 0
        while k < min(len(up), len(down)) and up[k] == down[k]:
            k += 1
        if up[k:] and self.anim in FINISH_LOOPS and self._pose_of(self.anim) == here and not self.queue:
            n = len(self.anims[self.anim][1])  # the arm comes back down before the way out
            self.queue.append([self.anim, self.pose_facing, list(range(self.index % n + 1, n)), self.index % n])
        for pose in reversed(up[k:]):
            anim = self._entry(pose)[0]
            n = len(self.anims[anim][1])
            self.queue.append([anim, self.pose_facing, list(range(n - 2, -1, -1)), n - 1])
        for pose in down[k:]:
            anim = self._entry(pose)[0]
            self.queue.append([anim, facing, list(range(1, len(self.anims[anim][1]))), 0])
        self.queue = [entry for entry in self.queue if entry[2]]
        self.pose, self.pose_facing = target, facing

    def _get_up(self):
        """Off the throne (whichever way she sits), standing facing you."""
        self._bridge("stand", 1)

    def _clear_queue(self):
        """Drops the queued frames: her body is taken as in the current state's pose (she jumps there)."""
        self.queue.clear()
        self.pose, self.pose_facing = self._pose_of(self.anim), self.facing

    def _moody(self, anim):
        """The animation she plays for anim (idle, talk, sit) in her mood."""
        mood = self.mood
        while mood:
            name = MOOD_ANIMS.get(mood, {}).get(anim)
            if name in self.anims and self._path(self._pose_of(name)) is not None:
                return name
            mood = MOOD_FALLBACK.get(mood)
        return anim

    def _read_mood(self):
        """(tone, time of the latest snoozed or unanswered break) from User Care; (None, None) without it.
        Imported here: the pet runs without User Care too."""
        try:
            import user_care
            care = user_care.service()
            if care is None:
                return None, None
            tone = care.tone()
            nag = next((e.get("t") for e in reversed(list(care.state.get("recent") or ()))
                        if e.get("kind") in ("snooze", "unanswered")), None)
        except Exception as e:  # User Care is optional: she just stays as she is
            self._report(f"mood: {e!r}")
            return None, None
        return (None if tone == "happy" else tone), nag

    def _check_mood(self):
        mood, nag = self._read_mood()
        self.mood = mood
        if nag and nag != self.last_nag:
            self.last_nag = nag
            try:
                fresh = abs((datetime.now() - datetime.fromisoformat(nag)).total_seconds()) < IMPATIENT_WINDOW
            except (TypeError, ValueError):
                fresh = False
            if fresh:
                self.nag_until = time.monotonic() + IMPATIENT_WINDOW
        if self.nag_until is not None:
            if time.monotonic() > self.nag_until or self._impatient():
                self.nag_until = None
        self._settle_mood()

    def _impatient(self):
        """Arms crossed, tapping her foot, after a snoozed or unanswered break. Returns False to try again
        later (walking, busy), True once done (or impossible)."""
        if "impatient" not in self.anims or "impatientin" not in self.anims or self.state == "impatient":
            return True
        if self.game or self.hidden or self.queue or self.state not in ("idle", "talk", "sit") + POSES \
                or self.state == "code":
            return False
        facing = 1 if self.state == "sit" else self.facing
        if self.state in POSES:
            self._leave_pose()
        self._hide_bubble()
        self._take_pose("impatient", facing)
        self.say(random.choice(self._lines("impatient")))
        return True

    def _settle_mood(self):
        """Shows a change of mood in a quiet moment, standing around or on the throne (otherwise the next
        state picks it up)."""
        if self.queue or self.bubble is not None or self.state not in ("idle", "sit") or \
                self.state_ticks < MOOD_CHECK_TICKS:
            return
        plain = "idle" if self.state == "idle" else "sit"
        if self.anim != self._moody(plain):
            ticks = self.state_ticks
            self._set_state(self.state, (1, 1), plain, self.facing)
            self.state_ticks = ticks

    def _shift(self, anim, facing, index, before):
        """Moves her window as a queued frame comes up: a walk frame by one stride, a tracked transition
        by its planted boot (meta.json tracks), so her feet stay put on the floor."""
        if anim == "walk":
            self.x += facing * self.walk_step
            return
        track = self.tracks.get(anim)
        if track and before is not None and max(index, before) < len(track):
            self.x += (track[index] - track[before]) * facing

    def _next_frame(self):
        """The frame to show now: queued one-shot frames first, else the state's loop (ping-pong loops
        forward and back). Each frame stays up for its animation's HOLD ticks."""
        if self.queue:
            entry = self.queue[0]
            anim, facing, indexes, shown = entry
            if self.held == 0:
                self._shift(anim, facing, indexes[0], shown)
            frame = self.anims[anim][facing][indexes[0]]
            self.held += 1
            if self.held >= HOLD.get(anim, DEFAULT_HOLD):
                self.held = 0
                entry[3] = indexes.pop(0)
                if not indexes:
                    self.queue.pop(0)
                    if not self.queue and self.snap_x is not None:
                        self.x, self.snap_x = self.snap_x, None
            return frame
        loop = self.anims[self.anim][self.facing]
        n = len(loop)
        self.held += 1
        if self.held >= HOLD.get(self.anim, DEFAULT_HOLD):
            self.held = 0
            period = 2 * n - 2 if self.anim in self.pingpong and n > 2 else n
            self.index = (self.index + 1) % period
        i = self.index % (2 * n)
        return loop[i if i < n else 2 * n - 2 - i]

    # --- Behavior ---------------------------------------------------------------------

    def _loop(self):
        if self.hidden:
            return
        try:
            self.tick += 1
            if self.tick % WINDOW_CHECK_TICKS == 0:
                self._check_window()
            if self.tick % GAME_CHECK_TICKS == 0:
                self._check_screen()
            if self.tick % MOOD_CHECK_TICKS == 0:
                self._check_mood()
            self._step()
            self._sync_throne()
            if self.throne_shown:
                _, _, _, bottom = _work_area()
                self._draw(self.anims["throne"][1][0], self.throne_hwnd, self._throne_x(), bottom - self.h)
            self._draw(self._next_frame())
            self._place_bubble()
        except Exception as e:  # keep going (the next tick may work), but leave a trace
            self._report(f"error: {e!r}", traceback.format_exc())
        finally:
            self.root.after(FRAME_MS, self._loop)

    def _report(self, text, details=""):
        now = time.monotonic()
        if now - self.logged.get(text, -LOG_REPEAT_SECONDS) < LOG_REPEAT_SECONDS:
            return
        self.logged[text] = now
        _log(f"{text}\n{self._snapshot()}" + (f"\n{details}" if details else ""))

    def _snapshot(self):
        """Her window and recent states, for pet_log.txt."""
        rect = wintypes.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        cloaked = wintypes.DWORD()
        dwmapi.DwmGetWindowAttribute(self.hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        return (f"  window: shown={bool(user32.IsWindowVisible(self.hwnd))} minimized={bool(user32.IsIconic(self.hwnd))} "
                f"on_top={bool(style & WS_EX_TOPMOST)} cloaked={cloaked.value} "
                f"rect=({rect.left},{rect.top},{rect.right},{rect.bottom}) x={self.x} y={self.y} "
                f"state={self.state} context={self.context} game={self.game} work_area={_work_area()}\n"
                "  recent: " + " | ".join(self.history))

    def _check_window(self):
        """Puts her window right if something outside hid it, pushed it under other windows or
        left it on no screen."""
        problems = []
        if not user32.IsWindowVisible(self.hwnd):
            problems.append("not shown")
        if user32.IsIconic(self.hwnd):
            problems.append("minimized")
        if not user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST:
            problems.append("not on top")
        rect = None
        if math.isfinite(self.x) and math.isfinite(self.y):
            rect = wintypes.RECT(int(self.x), int(self.y), int(self.x) + self.w, int(self.y) + self.h)
        lost = self.state != "drag" and (rect is None or not user32.MonitorFromRect(ctypes.byref(rect),
                                                                                    MONITOR_DEFAULTTONULL))
        if lost:
            problems.append("off screen")
        if not problems:
            return
        self._report("window fixed: " + ", ".join(problems))
        if lost:
            left, _, right, bottom = self._area()
            self.x = (left + right - self.w) / 2 if rect is None else max(left, min(self.x, right - self.w))
            self.y = bottom - self.h
            self._clear_queue()
            self._set_state("idle", (1, 2), "idle", self.facing, mood=False)
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        user32.SetWindowPos(self.hwnd, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _step(self):
        left, _, right, bottom = self._area()
        floor = bottom - self.h
        if self.state == "drag":
            return
        if self.state == "fall":
            self.vy += GRAVITY
            self.y = min(floor, self.y + self.vy)
            if self.y >= floor:
                self._set_state("idle", IDLE_SECONDS, "idle", self.facing)
            return
        self.y = floor
        if self.queue:
            return  # a one-shot animation is playing; don't move meanwhile
        if self.state == "busy":
            return  # in a conversation with the owner (see set_activity) until it ends
        self.state_ticks -= 1
        if self.state == "to_edge":
            target = self._edge_x()
            if (target - self.x) * self.dir < 0:
                self.dir = self.facing = 1 if target > self.x else -1
            if self._arrive(target, [("leanin", self.edge)]):
                self._play("leanin", self.edge, range(1, len(self.anims["leanin"][1])), shown=0)
                self._set_state("lean", (600, 600), "lean", self.edge)
            else:
                self.x += self.dir * self.speed
            return
        if self.state == "lean":
            return  # watching the game until it ends (see _check_screen)
        if self.state == "code":  # working with you until the editor goes (see _change_context)
            if self.state_ticks <= 0:
                self.state_ticks = self._ticks(POSE_SECONDS["code"])
                roll = random.random()
                if roll < CODE_BREAK_CHANCE and "stretch" in self.anims:
                    self._hide_bubble()
                    self._leave_pose()  # back to work afterwards: _decide sends her there
                    self._take_pose("stretch", self.facing)
                elif self.bubble is None and roll < CODE_BREAK_CHANCE + TALK_CHANCE:
                    self.say(random.choice(self._lines("code")))
            return
        if self.state in POSES:
            if self.state_ticks <= 0:
                if self.bubble is None and random.random() < TALK_CHANCE:
                    self.say(random.choice(self._lines(self.state)))
                    self.state_ticks = self._ticks((BUBBLE_SECONDS, BUBBLE_SECONDS + 2))
                else:
                    self._leave_pose()
            return
        if self.state in ("to_work", "to_throne"):
            # The target is looked up on every step and she always heads for it: it moves when
            # the work area changes (taskbar, screen settings), and a walk still going the old
            # way would never arrive and would carry her off the screen.
            target = self._work_x() if self.state == "to_work" else self._throne_x()
            if (target - self.x) * self.dir < 0:
                self.dir = self.facing = 1 if target > self.x else -1
            after = [("codein", self.dir)] if self.state == "to_work" else []
            if self._arrive(target, after):
                if self.state == "to_work":
                    self._take_pose("code", self.dir)
                else:
                    self._set_state("sit", SIT_SECONDS, "sit", 1)  # sits down (see _bridge)
            else:
                self.x += self.dir * self.speed
        elif self.state == "walk":
            self.x += self.dir * self.speed
            if self.x <= left or self.x + self.w >= right:
                self.x = max(left, min(self.x, right - self.w))
                self.dir = -self.dir
                self.facing = self.dir
            if self.state_ticks <= 0:
                self._stop_and_face()
        elif self.state == "sit" and self.state_ticks <= 0:
            if random.random() < SIT_CHANCE:  # stays where she belongs
                self._set_state("sit", SIT_SECONDS, "sit", 1)
                if self.bubble is None and random.random() < TALK_CHANCE:
                    self.say(random.choice(self._lines()))
            else:
                self._get_up()
                self._pastime()
        elif self.state in ("idle", "talk") and self.state_ticks <= 0:
            if self.state == "idle" and self.bubble is None and random.random() < TALK_CHANCE:
                self.say(random.choice(self._lines()))
            else:
                self._decide()

    def _set_state(self, state, seconds, anim, facing, mood=True):
        """mood: idle, talk and sit go by her mood (False for a moment's idle between two things: no
        stance for a second or two)."""
        if mood:
            anim = self._moody(anim)
        pose = self._pose_of(anim)
        if self.pose is not None:  # the way into this loop's pose, if her body isn't there yet
            self._bridge(pose, facing)
        self.pose, self.pose_facing = pose, facing
        self.state, self.state_ticks = state, self._ticks(seconds)
        self.anim, self.facing, self.index = anim, facing, 0
        self.history.append(f"{datetime.now():%H:%M:%S} {state} x={getattr(self, 'x', '?')} "
                            f"{getattr(self, 'context', '?')}{' game' if self.game else ''}")

    def _turns(self):
        """The turns there are frames for, by the walk frame each starts from."""
        quarter = len(self.anims["walk"][1]) // len(TURNS)
        return {q * quarter: turn for q, turn in enumerate(TURNS) if turn in self.anims}

    def _landings(self, count=1):
        """The next walk frames she can stop at (where a turn starts), as (walk frames still to show,
        that turn): the frame on screen now if it is one, then the following ones."""
        n = len(self.anims["walk"][1])
        turns = self._turns()
        now = self.index % n if self.anim == "walk" else 0
        found = []
        for k in range(2 * n * ARRIVE_CYCLES + n):
            turn = turns.get((now + k) % n)
            if turn:
                found.append((k, turn))
                if len(found) == count:
                    break
        return found

    def _stop(self, landing, step=None):
        """Queues the walk on to a landing (see _landings), one stride of `step` px per frame, then the
        turn that starts from that walk frame: she ends up standing, facing you."""
        k, turn = landing
        n = len(self.anims["walk"][1])
        now = self.index % n if self.anim == "walk" else 0
        self.walk_step = self.speed if step is None else step
        self._play("walk", self.dir, [(now + j) % n for j in range(1, k + 1)])
        self._play(turn, self.dir, range(1, len(self.anims[turn][1])), shown=0)

    def _start_walk(self, state, seconds):
        """Steps off from standing into the walk (a turn played backwards, from one of its starting
        quarters), then walks on in `state`."""
        turns = self._turns()
        start = random.choice(list(turns))
        turn = turns[start]
        self._play(turn, self.dir, range(len(self.anims[turn][1]) - 1, 0, -1))
        self._set_state(state, seconds, "walk", self.dir)
        self.index = start - 1  # the walk goes on from the turn's first frame

    def _arrive(self, target, after=()):
        """Walking to window x target: once it's near (ARRIVE_CYCLES), queues the last strides, the turn
        and `after` [(tracked animation, facing)] so that she stands exactly at target when they're done.
        The strides are stretched within STRIDE_LIMITS (no foot slides: they are whole walk frames);
        if no landing fits she is put on target at the end. Returns whether it's planned."""
        distance = (target - self.x) * self.dir
        if distance > self.speed * len(self.anims["walk"][1]) * ARRIVE_CYCLES:
            return False
        later = sum(self._track_total(anim) * facing for anim, facing in after)
        best = None
        for k, turn in self._landings(count=4 * ARRIVE_CYCLES + 4):
            rest = (target - self.x - self._track_total(turn) * self.dir - later) * self.dir
            if k == 0:
                stretch = 1.0 if abs(rest) < 1 else math.inf
            else:
                stretch = rest / (self.speed * k)
            off = 0 if STRIDE_LIMITS[0] <= stretch <= STRIDE_LIMITS[1] else 1
            score = (off, abs(math.log(stretch)) if stretch > 0 else math.inf)
            if best is None or score < best[0]:
                best = (score, k, turn, stretch)
        _, k, turn, stretch = best
        if not math.isfinite(stretch) or stretch <= 0 or best[0][0]:
            stretch = min(max(stretch, STRIDE_LIMITS[0]), STRIDE_LIMITS[1]) if math.isfinite(stretch) and stretch > 0 \
                else 1.0
            self.snap_x = target
        self._stop((k, turn), self.speed * stretch)
        return True

    def _close_to(self, x):
        """Nearer than a quarter of a walk cycle: too close to walk there."""
        return abs(x - self.x) < self.speed * len(self.anims["walk"][1]) / len(TURNS)

    def _track_total(self, anim):
        track = self.tracks.get(anim)
        return track[-1] - track[0] if track else 0.0

    def _stop_and_face(self):
        self._stop(self._landings()[0])
        then, self.then = self.then, None
        if then and self.context != "code":  # straight into the pose (no mood stance on the way)
            self.facing = self.dir
            self._take_pose(then, self._inward() if then == "watch" else self.dir)
        else:  # coming from the left, the mirrored frames keep the hand on the same hip as the turn
            self._set_state("idle", IDLE_SECONDS, "idle", self.dir)

    def _decide(self):
        """What next after standing around, by what is open on her monitor: with an editor
        she goes to work; on the bare desktop she usually goes back to the throne; otherwise
        one of her pastimes (see PASTIMES)."""
        if self.context == "code" and "code" in self.anims:
            self._go_to_work()
        elif self.context == "desktop":
            if self.throne_win is not None and random.random() < SIT_CHANCE:
                self._hide_bubble()
                self.dir = 1 if self._throne_x() > self.x else -1
                if self._close_to(self._throne_x()):  # standing in front of it already: sits right down
                    self.x = self._throne_x()
                    self._set_state("sit", SIT_SECONDS, "sit", 1)  # sits down (see _bridge)
                else:
                    self._start_walk("to_throne", (600, 600))
            else:
                self._pastime()
        else:
            self._pastime()

    def _pastime(self):
        """Something to do, picked by PASTIMES for what's open: watch the screen (arms crossed,
        turned toward its middle), curl a dumbbell, spin her dagger, stretch, or walk on.
        Watching needs her facing the middle (the "watchin" frames start from that idle pose),
        so otherwise she first takes a few steps toward the nearer edge, which ends facing it."""
        roll = random.random()
        for pose, chance in self._pastimes().items():
            if roll >= chance:
                roll -= chance
                continue
            if pose not in self.anims:
                break
            if pose == "watch":
                inward = self._inward()
                left, _, right, _ = self._area()
                room = right - (self.x + self.w) if inward > 0 else self.x - left
                if self.facing != inward and room > self.w / 2:
                    self._walk_on(inward, SHORT_WALK_SECONDS, then="watch")
                    return
                self._take_pose("watch", inward)
            else:
                self._take_pose(pose, self.facing)
            return
        self._walk_on()

    def _pastimes(self):
        """PASTIMES for what's open, weighted by her mood (MOOD_PASTIMES); some chance of walking on is
        always left."""
        chances = {pose: chance * MOOD_PASTIMES.get(self.mood, {}).get(pose, 1.0)
                   for pose, chance in PASTIMES.get(self.context, {}).items()}
        total = sum(chances.values())
        if total > 0.9:
            chances = {pose: chance * 0.9 / total for pose, chance in chances.items()}
        return chances

    def _inward(self):
        """Facing that turns the code and watch poses toward the middle of the screen: they are
        rendered facing left (1), which suits the right half."""
        left, _, right, _ = self._area()
        return 1 if self.x + self.w / 2 >= (left + right) / 2 else -1

    def _work_x(self):
        """Her place while coding: the bottom-right corner (the throne's place), always: editors
        keep their file explorer on the left, where she'd be in the way."""
        return self._throne_x()

    def _go_to_work(self):
        self._hide_bubble()
        target = self._work_x()
        if target - self.x <= self.speed:  # already there, or between it and the edge
            if self.state == "walk":
                self._stop(self._landings()[0])
            self._take_pose("code", 1)
            return
        self.dir = 1  # walking right into the corner leaves her facing the screen once there
        if self.state == "walk":
            self.state = "to_work"  # walking already: on in her stride
        else:
            self._start_walk("to_work", (600, 600))

    def _take_pose(self, pose, facing):
        self._play(pose + "in", facing, range(1, len(self.anims[pose + "in"][1])), shown=0)
        self._set_state(pose, POSE_SECONDS[pose], pose, facing)

    def _leave_pose(self):
        """Back to standing from one of the POSES (the hologram, dumbbell or dagger going away)."""
        pose = self.state
        last = len(self.anims[pose + "in"][1]) - 1
        self._play(pose + "in", self.facing, range(last - 1, -1, -1), shown=last)
        self._set_state("idle", (1, 2), "idle", self.facing, mood=False)

    def _walk_on(self, direction=None, seconds=WALK_SECONDS, then=None):
        """Walks off (direction if there's room that way, else wherever there's room); then is
        a pose to take where she stops."""
        self._hide_bubble()
        self.then = then
        left, _, right, _ = self._area()
        room_right = right - (self.x + self.w)
        if direction is not None and (room_right if direction > 0 else self.x - left) > self.w / 2:
            self.dir = direction
        else:
            self.dir = random.choice((-1, 1)) if min(room_right, self.x - left) > self.w else (
                1 if room_right > self.x - left else -1)
        self._start_walk("walk", seconds)

    def _lines(self, kind=None):
        """Her lines for kind (a pose, or None) in her mood: pet_lines[_<kind>]_<mood>, a mood without its own
        falling back along MOOD_FALLBACK, then to happy; {user} is the owner's name."""
        lang = self.language()
        base = f"pet_lines_{kind}" if kind else "pet_lines"
        tables = (i18n.STRINGS.get(lang, {}), i18n.STRINGS[i18n.DEFAULT_LANGUAGE])
        mood, key = self.mood or "happy", None
        while mood and key is None:
            if any(f"{base}_{mood}" in table for table in tables):
                key = f"{base}_{mood}"
            mood = MOOD_FALLBACK.get(mood) or ("happy" if mood != "happy" else None)
        text = i18n.get(lang, key or base, user=i18n.user_name())
        return [line for line in text.split("\n") if line.strip()]

    # --- Speech -------------------------------------------------------------------------

    def say(self, text, seconds=BUBBLE_SECONDS, on_click=None):
        if self.game:
            return  # no bubbles over a game
        if self.state == "walk":
            self._stop_and_face()
        self._hide_bubble()
        bubble = tk.Toplevel(self.root)
        bubble.overrideredirect(True)
        bubble.attributes("-topmost", True)
        bubble.attributes("-alpha", 0.95)
        border = tk.Frame(bubble, bg="#3a7bff", padx=2, pady=2)
        border.pack()
        label = tk.Label(border, text=text, bg="#14182b", fg="#e4e9ff", font=("Segoe UI", 10), wraplength=260,
                         justify="left", padx=10, pady=7)
        label.pack()
        if on_click is not None:  # e.g. "Disk: new findings" opens the Disk tab
            def clicked(event, b=bubble):
                self._hide_bubble(b)
                on_click()
            for widget in (bubble, border, label):
                widget.bind("<Button-1>", clicked)
            label.configure(cursor="hand2")
        self.bubble = bubble
        if self.state not in ("sit", "to_throne", "to_work") + POSES:  # busy: she keeps going
            self._set_state("talk", (seconds, seconds), "talk", self.facing)
        self._place_bubble()
        self.root.after(int(seconds * 1000), lambda b=bubble: self._hide_bubble(b))

    def _place_bubble(self):
        if self.bubble is None:
            return
        self.bubble.update_idletasks()
        bw, bh = self.bubble.winfo_reqwidth(), self.bubble.winfo_reqheight()
        left, top, right, _ = self._area()
        x = int(min(max(left, self.x + self.w / 2 - bw / 2), right - bw))
        y = int(max(top, self.y - bh + self.h * 0.02))
        self.bubble.geometry(f"+{x}+{y}")

    def _hide_bubble(self, only=None):
        if self.bubble is not None and (only is None or only is self.bubble):
            self.bubble.destroy()
            self.bubble = None
            if self.state == "talk":
                self._set_state("idle", IDLE_SECONDS, "idle", self.facing)

    # --- Conversation ---------------------------------------------------------------------

    ACTIVITY_ANIMS = {"listen": "idle", "think": "think", "talk": "talk"}

    def set_activity(self, kind):
        """A conversation with the owner (voice_session.py, the text box): "listen" (she stands facing
        you), "think" (while the answer comes), "talk" (while it's said or shown); None: back to her
        own life. She first leaves what she was doing: gets up from the throne, ends a pose, stops."""
        if self.game or self.hidden:
            return  # no conversation poses over a game
        if kind is None:
            if self.state == "busy":
                if self.anim == "think" and "thinkin" in self.anims:
                    self._play("thinkin", self.facing, reversed(range(len(self.anims["thinkin"][1]))))
                self._set_state("idle", IDLE_SECONDS, "idle", self.facing)
            return
        facing = self.facing
        if self.state != "busy":
            self._hide_bubble()
            if self.state == "sit":
                self._get_up()
                facing = 1
            elif self.state in POSES:
                self._leave_pose()
            elif self.state in ("walk", "to_throne", "to_work", "to_edge"):
                self._stop(self._landings()[0])
                facing = self.dir
        anim = self.ACTIVITY_ANIMS.get(kind, "idle")
        if anim not in self.anims:  # "think" until its frames are rendered
            anim = "idle"
        if self.state == "busy" and self.anim == self._moody(anim):
            return
        if "thinkin" in self.anims:  # the hand goes to her chin, and back down after
            frames = range(len(self.anims["thinkin"][1]))
            if anim == "think":
                self._play("thinkin", facing, frames)
            elif self.state == "busy" and self.anim == "think":
                self._play("thinkin", facing, reversed(frames))
        self._set_state("busy", (3600, 3600), anim, facing)

    def anchor(self):
        """Her window on the screen (x, y, w, h), for the text box next to her."""
        return int(self.x), int(self.y), self.w, self.h

    # --- Mouse --------------------------------------------------------------------------

    def _press(self, event):
        self.drag_from = (event.x_root, event.y_root, self.x, self.y, False)

    def _motion(self, event):
        if self.drag_from is None:
            return
        x0, y0, px, py, dragging = self.drag_from
        if not dragging and abs(event.x_root - x0) + abs(event.y_root - y0) < DRAG_THRESHOLD:
            return
        if not dragging:
            self._hide_bubble()
            self._clear_queue()
            self._set_state("drag", (1, 1), "drag", 1)
        self.drag_from = (x0, y0, px, py, True)
        self.x, self.y = px + event.x_root - x0, py + event.y_root - y0

    def _release(self, event):
        if self.drag_from is None:
            return
        dragging = self.drag_from[4]
        self.drag_from = None
        if dragging:
            self.vy = 0.0
            self._set_state("fall", (1, 1), "drag", 1)
        else:
            self.on_click()

    def _menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        lang = self.language()
        menu.add_command(label=i18n.get(lang, "pet_menu_chat"), command=self.on_click)
        menu.add_command(label=i18n.get(lang, "pet_menu_talk"), command=lambda: self.say(random.choice(
            self._lines(self.state if self.state in POSES else None))))
        menu.add_command(label=i18n.get(lang, "pet_menu_hide"), command=self.hide)
        menu.tk_popup(event.x_root, event.y_root)

    def hide(self):
        _log(f"hidden by the user\n{self._snapshot()}")  # often because she went missing
        self.hidden = True
        self._hide_bubble()
        self.win.withdraw()
        if self.throne_win is not None:
            self.throne_win.withdraw()
        _remember(False)

    def show(self):
        if not self.hidden:
            return
        self.hidden = False
        if self.throne_win is not None:
            self.throne_win.deiconify()
        self.win.deiconify()
        self.win.lift()
        _remember(True)
        self._loop()


def start(on_click, language, force=False):
    """Starts the pet on its own Tk thread. on_click() runs when she's clicked; language()
    returns the current UI language ("en"/"tr") for her lines. force starts her even when
    she's switched off (the chat window's button)."""
    _state["callbacks"] = (on_click, language)
    if (not force and not enabled()) or _state["pet"] is not None:
        return
    ready = threading.Event()

    def ui_thread():
        root = tk.Tk()
        root.withdraw()
        try:
            pet = Pet(root, on_click, language)
            pet.mailbox = tkpost.Mailbox(root)  # how other threads reach her: never waits (tkpost.py)
            _state["pet"] = pet
        except Exception as e:  # missing frames or a Win32 failure must not take the app down
            print(f"Desktop pet couldn't start: {e}")
            ready.set()
            return
        ready.set()
        root.mainloop()

    threading.Thread(target=ui_thread, daemon=True).start()
    ready.wait()


def visible():
    pet = _state["pet"]
    return pet is not None and not pet.hidden


def can_talk():
    """Whether a bubble would show now: she's shown and not in game mode."""
    pet = _state["pet"]
    return pet is not None and not pet.hidden and pet.game is None


def toggle():
    """Thread-safe: shows her if she's hidden (starting her if needed), else hides her.
    Returns whether she is visible afterwards."""
    pet = _state["pet"]
    if pet is None:
        if _state["callbacks"] is None:
            return False
        start(*_state["callbacks"], force=True)
        _remember(True)
        return _state["pet"] is not None
    if pet.hidden:
        pet.mailbox.post(pet.show)
        return True
    pet.mailbox.post(pet.hide)
    return False


def activity(kind):
    """Thread-safe: see Pet.set_activity ("listen", "think", "talk" or None)."""
    pet = _state["pet"]
    if pet is not None and not pet.hidden:
        pet.mailbox.post(lambda: pet.set_activity(kind))


def anchor():
    """Thread-safe: her window (x, y, w, h) while she's shown, else None."""
    pet = _state["pet"]
    if pet is None or pet.hidden:
        return None
    return pet.anchor()


def say(text, seconds=BUBBLE_SECONDS, on_click=None):
    """Thread-safe: shows text in her speech bubble; on_click() runs if the bubble is clicked."""
    pet = _state["pet"]
    if pet is not None and not pet.hidden:
        pet.mailbox.post(lambda: pet.say(text, seconds, on_click))
