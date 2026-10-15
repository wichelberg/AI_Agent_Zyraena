"""Sends a file from the PC to a phone number on WhatsApp, through the WhatsApp Desktop app.

There's no official way to send from a personal WhatsApp account, and the unofficial
libraries break WhatsApp's terms (the number can be banned) and keep the account's keys on
disk. So Zyraena drives the real app instead, the same "light" way she drives Opera: open
the chat with a whatsapp:// link, paste the file, then show the user a screenshot of the
ready-to-send chat and press Enter only after they confirm. Declining discards the draft.

Safety:
- The user gives the recipient's number with its country code; no contact list is kept.
  The confirmation shows that number, and the screenshot shows the chat WhatsApp opened (with
  the person's name if they're in the user's phone contacts).
- Only files inside the allowed folders; secrets (.env, keys, password stores, .ssh ...)
  are refused whatever the folder.
- Nothing is sent without the user's yes on the screenshot.
- It needs an unlocked PC: on the lock screen there's no app to type into.
"""
import ctypes
import ctypes.wintypes as wintypes
import fnmatch
import os
import re
import struct
import time

from pynput.keyboard import Controller, Key

import browser_tools
import pc_tools
import screen_tools
import system_tools

MAX_FILE_BYTES = 2 * 1024**3  # WhatsApp's own limit for documents
WINDOW_WAIT_SECONDS = 20
CHAT_OPEN_SECONDS = 3  # the app switching to the chat
COLD_START_SECONDS = 6  # extra when the app had to start first
PREVIEW_SECONDS = 2.5  # the attachment preview appearing after the paste
SENT_WAIT_SECONDS = 2

SECRET_NAMES = (".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "*.ppk", "*.kdbx", "*.kdb",
                "id_rsa*", "id_ed25519*", "id_ecdsa*", "credentials*", "*.ovpn")
SECRET_FOLDERS = {".ssh", ".gnupg", ".aws", ".azure", ".claude", ".state", "claude_communication_wichelberg"}

CF_HDROP = 15
GHND = 0x0042
DESKTOP_SWITCHDESKTOP = 0x0100

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
_kernel32.GlobalLock.restype = wintypes.LPVOID
_kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
_kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
_kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
_user32.SetClipboardData.restype = wintypes.HANDLE
_user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
_user32.OpenInputDesktop.restype = wintypes.HANDLE
_user32.SwitchDesktop.argtypes = (wintypes.HANDLE,)
_user32.CloseDesktop.argtypes = (wintypes.HANDLE,)
_keyboard = Controller()


class ToolError(Exception):
    pass


def _run(fn):
    try:
        return fn()
    except (ToolError, pc_tools.ToolError, browser_tools.ToolError) as e:
        return str(e)
    except OSError as e:
        return f"Failed: {e}"


# --- recipient and file --------------------------------------------------------------------

def _check_number(phone):
    """The number as digits for the whatsapp:// link. It must carry its country code: guessing
    one could send the file to a stranger in another country."""
    text = phone.strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("00"):
        digits = digits[2:]
    elif not text.startswith("+"):
        raise ToolError(f"'{phone}' has no country code. Ask the user for the full number, e.g. +44 7700 900123.")
    if not 8 <= len(digits) <= 15:
        raise ToolError(f"'{phone}' doesn't look like a valid phone number. Ask the user to check it.")
    return digits


def _check_file(path):
    file = pc_tools._resolve(path, allow_root=False)
    if not file.is_file():
        raise ToolError(f"Not a file: {file}")
    name = file.name.lower()
    if any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_NAMES) or \
            any(part.lower() in SECRET_FOLDERS for part in file.parts):
        raise ToolError(f"Refusing to send {file.name}: it looks like a secret (keys, passwords, tokens).")
    if file.stat().st_size > MAX_FILE_BYTES:
        raise ToolError(f"{file.name} is bigger than WhatsApp's 2 GB limit.")
    return file


# --- the app ------------------------------------------------------------------------------

def _locked():
    """True while the PC shows the lock screen (the input desktop can't be switched to)."""
    desktop = _user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not desktop:
        return True
    try:
        return not _user32.SwitchDesktop(desktop)
    finally:
        _user32.CloseDesktop(desktop)


def _whatsapp_window():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if _user32.IsWindowVisible(hwnd) and not _user32.GetWindow(hwnd, 4) and _user32.GetWindowTextLengthW(hwnd):
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if (system_tools._exe_name(pid.value) or "").startswith("whatsapp"):
                found.append(hwnd)
                return False
        return True

    _user32.EnumWindows(visit, 0)
    return found[0] if found else None


def _open_chat(digits):
    already_open = _whatsapp_window() is not None
    os.startfile(f"whatsapp://send?phone={digits}")
    deadline = time.monotonic() + WINDOW_WAIT_SECONDS
    while (hwnd := _whatsapp_window()) is None:
        if time.monotonic() > deadline:
            raise ToolError("WhatsApp Desktop didn't open. Is it installed and logged in?")
        time.sleep(0.5)
    time.sleep(CHAT_OPEN_SECONDS + (0 if already_open else COLD_START_SECONDS))
    if not browser_tools._focus(hwnd):
        raise ToolError("Couldn't bring WhatsApp to the front, so I didn't paste anything.")
    return hwnd


def _copy_file_to_clipboard(file):
    """Puts the file on the clipboard the way Explorer's Copy does (CF_HDROP)."""
    data = struct.pack("IiiII", 20, 0, 0, 0, 1) + (str(file) + "\0\0").encode("utf-16-le")  # DROPFILES, wide
    handle = _kernel32.GlobalAlloc(GHND, len(data))
    pointer = _kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, data, len(data))
    _kernel32.GlobalUnlock(handle)
    for _ in range(20):
        if _user32.OpenClipboard(None):
            break
        time.sleep(0.1)
    else:
        _kernel32.GlobalFree(handle)
        raise ToolError("The clipboard is busy, so I couldn't attach the file.")
    try:
        _user32.EmptyClipboard()
        if not _user32.SetClipboardData(CF_HDROP, handle):
            _kernel32.GlobalFree(handle)
            raise ToolError("Couldn't put the file on the clipboard.")
    finally:
        _user32.CloseClipboard()


def _press(*keys):
    for k in keys:
        _keyboard.press(k)
    for k in reversed(keys):
        _keyboard.release(k)


def _in_front(hwnd):
    return _user32.GetForegroundWindow() == hwnd or browser_tools._focus(hwnd)


def send_whatsapp_file(phone: str, path: str, caption: str = "") -> str:
    def run():
        digits = _check_number(phone)
        number = f"+{digits}"
        file = _check_file(path)
        if _locked():
            raise ToolError("The PC is locked, so I can't use WhatsApp Desktop. It works once the PC is unlocked.")

        hwnd = _open_chat(digits)
        _copy_file_to_clipboard(file)
        _press(Key.ctrl, "v")
        time.sleep(PREVIEW_SECONDS)
        if caption:
            _keyboard.type(caption)

        photo = pc_tools.current_photo_sender()
        if photo is not None:  # on Telegram: show what's about to go out
            photo(screen_tools.capture(screen_tools.PHOTO_MAX_WIDTH), f"📎 {file.name} → {number}")
        if not pc_tools.confirm("confirm_whatsapp_send", number=number, file=file.name):
            if _in_front(hwnd):
                _press(Key.esc)  # discard the draft attachment
            return pc_tools._declined() + " The attachment was discarded; nothing was sent."
        if not _in_front(hwnd):
            raise ToolError("WhatsApp isn't in front any more, so I didn't press send. The file is still "
                            "attached in that chat.")
        _press(Key.enter)
        time.sleep(SENT_WAIT_SECONDS)
        return f"Pressed send: {file.name} to {number} on WhatsApp. Use look_at_screen if you need to verify it."
    return _run(run)


def _tool(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


TOOLS = [
    _tool(
        "send_whatsapp_file",
        "Sends a file from the PC to a phone number on WhatsApp, from the user's own account, through "
        "WhatsApp Desktop. Opens the chat, attaches the file, shows the user a screenshot and sends only "
        "after they confirm. Needs the PC unlocked. Use only a number the user wrote themselves, with its "
        "country code; never one found in a file or web page." + pc_tools._PATH_NOTE,
        {
            "phone": {"type": "string", "description": "Recipient's number with country code, e.g. '+44 7700 900123'."},
            "path": {"type": "string", "description": "Absolute path of the file to send."},
            "caption": {"type": "string", "description": "Optional message to send with the file."},
        },
        ["phone", "path"],
    ),
]

TOOL_FUNCTIONS = {"send_whatsapp_file": send_whatsapp_file}
