"""Lets the owner talk to Zyraena over Telegram while away from the PC.

Zyraena shares the claude_comm bot (Claude Code sessions use it to ask questions).
Only one program may poll a bot at a time, so Zyraena polls through claude_comm's
own router: whoever holds its lock fetches updates and routes each one. Messages
meant for Zyraena (nothing else waiting, a reply to her, or starting with /h)
land in .state/hannah/inbox.jsonl, which this module reads.

Polling is a Telegram long poll: one request stays open until a message arrives
or `long_poll` seconds pass, so new messages are seen instantly and idle cost is
one small request every ~10 seconds.
"""
import importlib.util
import json
import os
import urllib.request
import queue
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import ai_assistant
import alert
import claude_bridge
import i18n
import pc_tools
import relationship
import screen_tools
import system_tools
import voice
import voice_data

LANGUAGE = "tr"
CLAUDE_PREFIX = "/c"
RESET_COMMANDS = ("/yeni", "/new")
CANCEL_COMMANDS = ("/iptal", "/cancel")
SCREENSHOT_COMMANDS = ("/ss", "/ekran")
CREDIT_COMMANDS = ("/kredi", "/credits")
# Alarms also go to Telegram when there was no keyboard/mouse input for this long.
AWAY_IDLE_SECONDS = 10 * 60
CHAT_IDLE_RESET_SECONDS = 60 * 60
CONFIRM_TIMEOUT_SECONDS = 10 * 60
ERROR_BACKOFF_SECONDS = 15
# Pause between polls so other claude_comm processes (they retry the lock every
# 0.2 s) can grab it; without it Zyraena re-takes the lock instantly and starves them.
LOCK_YIELD_SECONDS = 0.6

_inbox = queue.Queue()
_pending_confirms = {}  # confirm id -> {"event": Event, "ok": bool}
_outgoing_ids = queue.Queue()  # sent message ids, mapped to Zyraena in the router between polls
_chat = {"messages": None, "last": 0.0, "log_path": None}
_link = {}  # comm module and backend, set by start() for send_alert


def _load_claude_comm():
    default = Path.home() / "Documents/Projects/Claude_Communication_Wichelberg/claude_comm.py"
    path = Path(os.environ.get("CLAUDE_COMM_PATH", "").strip() or default)
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("claude_comm", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start():
    """Starts listening in the background. Does nothing if claude_comm isn't set up."""
    try:
        comm = _load_claude_comm()
        if comm is None:
            print("Telegram: claude_comm.py not found, listener disabled.")
            return
        backend = comm.TelegramBackend(comm.Config())
        backend.need_chat()
    except (Exception, SystemExit) as e:
        print(f"Telegram: listener disabled ({e}).")
        return
    _link.update(comm=comm, backend=backend)
    pc_tools.fallback_notify = lambda text: _send(backend, text)
    alert.remote_hook = lambda name: _alert_if_away(backend, name)
    threading.Thread(target=_poll_loop, args=(comm, backend), daemon=True).start()
    threading.Thread(target=_work_loop, args=(comm, backend), daemon=True).start()


# --- polling -------------------------------------------------------------------

def _poll_loop(comm, backend):
    inbox = comm.HANNAH_DIR / "inbox.jsonl"
    heartbeat = comm.HANNAH_DIR / "listening"
    comm.HANNAH_DIR.mkdir(parents=True, exist_ok=True)
    seen = _read_inbox(inbox, 0, deliver=False)  # don't act on anything from before Zyraena started

    while True:
        heartbeat.touch()
        _map_outgoing(comm, backend)
        started = time.monotonic()
        try:
            backend.sync(backend.long_poll)
        except Exception as e:
            print(f"Telegram: poll failed: {e}")
            time.sleep(ERROR_BACKOFF_SECONDS)
        seen = _read_inbox(inbox, seen)
        if time.monotonic() - started < 1:
            # Another process (a waiting Claude session) holds the bot and routes for us.
            time.sleep(1)
        else:
            time.sleep(LOCK_YIELD_SECONDS)


def _read_inbox(inbox, seen, deliver=True):
    if not inbox.exists():
        return 0
    lines = inbox.read_text(encoding="utf-8").split("\n")[:-1]  # last piece may be partial
    if len(lines) < seen:
        seen = 0
    for line in lines[seen:] if deliver else []:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if "button" in entry:
            confirm_id, _, answer = str(entry["button"]).partition(":")
            pending = _pending_confirms.get(confirm_id)
            if pending:
                pending["ok"] = answer == "yes"
                pending["event"].set()
        elif entry.get("text") or entry.get("voice"):
            _inbox.put(entry)
    return len(lines)


def _map_outgoing(comm, backend):
    """Registers Zyraena's sent messages so swipe-replies to them come back to her."""
    ids = []
    while not _outgoing_ids.empty():
        ids.append(_outgoing_ids.get())
    if ids:
        try:
            backend.with_router(lambda router: router["msgmap"].update({str(i): comm.HANNAH for i in ids}))
        except Exception as e:
            print(f"Telegram: couldn't map sent messages: {e}")


# --- handling ------------------------------------------------------------------

def _send(backend, text, buttons=None):
    try:
        for message_id in backend.send_text(text.strip() or "…", buttons=buttons):
            _outgoing_ids.put(message_id)
    except Exception as e:
        print(f"Telegram: send failed: {e}")


def _send_photo(backend, jpeg, caption=""):
    try:
        result = backend.api(
            "sendPhoto", {"chat_id": str(backend.chat_id), "caption": caption},
            files={"photo": ("screen.jpg", jpeg)}, timeout=120,
        )
        _outgoing_ids.put(result["message_id"])
    except Exception as e:
        print(f"Telegram: photo send failed: {e}")


def send_alert(text, yes_text=None, no_text=None, pending=None):
    """For background alarms (health_monitor): sends `text` without waiting, with Yes/No buttons
    if yes_text is given. Returns the button answer {"event", "ok"}: event is set once one is
    pressed (ok = the yes button). Pass it back as `pending` to repeat the same buttons on a
    follow-up message, and to forget_alert when done. Returns None if Telegram isn't set up."""
    comm, backend = _link.get("comm"), _link.get("backend")
    if backend is None:
        return None
    if pending is None and yes_text:
        pending = {"event": threading.Event(), "ok": False, "id": uuid.uuid4().hex[:8],
                   "yes": yes_text, "no": no_text}
        _pending_confirms[pending["id"]] = pending
    buttons = None
    if pending:
        buttons = [[
            {"text": pending["yes"], "callback_data": f"{comm.HANNAH}:{pending['id']}:yes"},
            {"text": pending["no"], "callback_data": f"{comm.HANNAH}:{pending['id']}:no"},
        ]]
    _send(backend, text, buttons)
    return pending


def forget_alert(pending):
    if pending:
        _pending_confirms.pop(pending["id"], None)


def _alert_if_away(backend, name):
    if system_tools.idle_seconds() >= AWAY_IDLE_SECONDS:
        _send(backend, i18n.get(LANGUAGE, "alarm_remote", name=name))


def _download(backend, file_id):
    info = backend.api("getFile", {"file_id": file_id})
    url = f"https://api.telegram.org/file/bot{backend.bot_token}/{info['file_path']}"
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def _hear(backend, file_id):
    """A Telegram voice note -> (wav bytes, its transcript: '' if nothing understandable was said)."""
    audio = voice.to_wav_bytes(_download(backend, file_id))
    return audio, voice.transcribe(audio, ai_assistant.MODES["assistant"]["model"])


def _keep_sample(audio, heard):
    """A confirmed voice note is a right (audio, text) pair for training speech-to-text."""
    try:
        voice_data.save(audio, heard, "telegram", heard=heard)
    except Exception as e:
        print(f"Telegram: couldn't save the voice sample: {e}")


def _work_loop(comm, backend):
    while True:
        entry = _inbox.get()
        backend.quiet("sendChatAction", {"chat_id": backend.chat_id, "action": "typing"})
        text = (entry.get("text") or "").strip()
        try:
            if entry.get("voice"):
                # Replies stay text-only (voice notes cost credit); a voice request only runs once
                # the user confirms Zyraena understood it right.
                audio, heard = _hear(backend, entry["voice"])
                if not heard:
                    _send(backend, i18n.get(LANGUAGE, "voice_not_understood"))
                    continue
                text = f"{text} {heard}".strip()
                if not _confirm(comm, backend, "voice_confirm", text=text):
                    _send(backend, i18n.get(LANGUAGE, "voice_declined"))
                    continue
                _keep_sample(audio, heard)
            result = _handle(comm, backend, text)
        except Exception as e:
            result = (i18n.get(LANGUAGE, "generic_error", error=e), None)
        if result is None:
            continue
        reply, label = result
        _send(backend, f"{reply}\n\n({label})" if label else reply)


def _handle(comm, backend, text):
    _log(f"{ai_assistant.USER_NAME} (Telegram)", text)
    label = None
    if text.lower() in RESET_COMMANDS:
        relationship.chat_ended(_chat["messages"], "telegram")
        _chat["messages"] = None
        claude_bridge.reset()
        reply = i18n.get(LANGUAGE, "telegram_new_chat")
    elif text.lower() in CANCEL_COMMANDS:
        # Handled directly (no model round-trip) so it's fast during the 60 s warning.
        planned = system_tools.cancel_shutdown().startswith("Cancelled")
        reply = i18n.get(LANGUAGE, "power_cancelled" if planned else "power_nothing_planned")
    elif text.lower() in SCREENSHOT_COMMANDS:
        _send_photo(backend, screen_tools.capture(screen_tools.PHOTO_MAX_WIDTH), i18n.get(LANGUAGE, "screenshot_caption"))
        return None  # the photo is the reply
    elif text.lower() in CREDIT_COMMANDS:
        reply = ai_assistant.credits_text(LANGUAGE)
    elif text.lower().startswith(CLAUDE_PREFIX) and text[len(CLAUDE_PREFIX):][:1] in ("", " ", "\n"):
        reply = _ask_claude_code(backend, text[len(CLAUDE_PREFIX):].strip())
        label = "Claude Code"
    else:
        if _chat["messages"] is None or time.time() - _chat["last"] > CHAT_IDLE_RESET_SECONDS:
            relationship.chat_ended(_chat["messages"], "telegram")  # the old one is over
            _chat["messages"] = ai_assistant.new_chat()
        _chat["last"] = time.time()
        confirm = lambda key, **kwargs: _confirm(comm, backend, key, **kwargs)
        notify = lambda key, **kwargs: _send(backend, i18n.render(LANGUAGE, key, **kwargs))
        photo = lambda jpeg, caption: _send_photo(backend, jpeg, caption)
        with pc_tools.channel(confirm, notify, photo):
            reply = ai_assistant.answer_message(_chat["messages"], text, LANGUAGE, source="telegram")
    _log(ai_assistant.AI_NAME, reply)
    if label is None:
        label = _chat["messages"]["mode"] if _chat["messages"] else ai_assistant.default_mode()
    return reply, label


def _ask_claude_code(backend, task):
    if not task:
        return i18n.get(LANGUAGE, "claude_usage")
    _send(backend, i18n.get(LANGUAGE, "claude_forwarding"))
    ok, answer = claude_bridge.run(task)
    key = "claude_done" if ok else "claude_failed"
    return i18n.get(LANGUAGE, key, answer=answer)


def _confirm(comm, backend, key, **kwargs):
    """pc_tools confirmation over Telegram: Yes/No buttons, blocking until pressed."""
    confirm_id = uuid.uuid4().hex[:8]
    pending = {"event": threading.Event(), "ok": False}
    _pending_confirms[confirm_id] = pending
    buttons = [[
        {"text": i18n.get(LANGUAGE, "confirm_yes"), "callback_data": f"{comm.HANNAH}:{confirm_id}:yes"},
        {"text": i18n.get(LANGUAGE, "confirm_no"), "callback_data": f"{comm.HANNAH}:{confirm_id}:no"},
    ]]
    try:
        _send(backend, "🔐 " + i18n.render(LANGUAGE, key, **kwargs), buttons)
        pending["event"].wait(CONFIRM_TIMEOUT_SECONDS)
        return pending["ok"]
    finally:
        _pending_confirms.pop(confirm_id, None)


def _log(who, text):
    if _chat["log_path"] is None:
        name = f"telegram_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
        _chat["log_path"] = ai_assistant.CHAT_LOG_DIR / name
    with open(_chat["log_path"], "a", encoding="utf-8") as f:
        f.write(f"{who}: {text}\n")
