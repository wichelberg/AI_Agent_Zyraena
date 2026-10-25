"""Zyraena's memory of the owner, and how a conversation changes her affection.

When a conversation ends (the text box closes, a spoken conversation ends, a Telegram chat is replaced by
a new one), the assistant model (one request, no tools, no history) reads it once and returns:
- affection: -5..+5, how it changed her affection for the owner (user_care.add_affection keeps it within
  its limits); 0 for plain tasks;
- note: one or two sentences worth remembering about it, or nothing;
- core: the rare things she must never forget (what she means to them, names they give her, serious
  promises, important facts of their life).

memory.json in User Care's folder keeps both: the notes (the last NOTES_KEPT; the last NOTES_IN_PROMPT go
into her prompt) and the never-forget memories, which code never removes (the owner deletes them in
Ctrl+F1 → Bakım → Anılar). All of them go into the system prompt of both modes, so she knows them without
being asked. remember_forever is her tool for "bunu asla unutma".
"""
import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

import user_care

NOTES_KEPT = 60
NOTES_IN_PROMPT = 8
CORE_PER_CHAT = 3
MIN_USER_CHARS = 20      # less than this from the owner: nothing to look back at, no request
TRANSCRIPT_CHARS = 8000  # the end of a long conversation is what counts
_HINT = re.compile(r"\s*\[This message was spoken;.*\]\s*$", re.S)  # voice.SPOKEN_HINT

_lock = threading.RLock()
_state = {"classify": None, "lang": lambda: "tr", "user": "User", "ai": "Zyraena", "path": None}


def _log(text):
    try:
        print(f"Relationship: {text}")
    except UnicodeEncodeError:
        print(f"Relationship: {text}".encode("ascii", "replace").decode("ascii"))


def configure(classify=None, lang=None, user=None, ai=None, path=None):
    """classify(prompt, what) -> the assistant model's answer; lang() -> "tr"/"en"; user/ai: the names in
    the transcript; path: memory.json somewhere else (tests)."""
    for key, value in (("classify", classify), ("lang", lang), ("user", user), ("ai", ai), ("path", path)):
        if value is not None:
            _state[key] = value


def path():
    return Path(_state["path"]) if _state["path"] else user_care.care_dir() / "memory.json"


# --- the store ------------------------------------------------------------------------------------------

def _read(file):
    data = json.loads(file.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def load():
    """{"core": [...], "notes": [...]}. A broken memory.json falls back to memory.json.bak, the copy made
    before the last save, so the never-forget memories survive a bad write."""
    with _lock:
        file = path()
        data = {}
        for candidate in (file, file.with_suffix(".json.bak")):
            try:
                data = _read(candidate)
                break
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as e:
                _log(f"{candidate.name} unreadable: {e}")
        data.setdefault("core", [])
        data.setdefault("notes", [])
        return data


def _save(data):
    file = path()
    file.parent.mkdir(parents=True, exist_ok=True)
    try:
        good = file.read_text(encoding="utf-8")
        json.loads(good)
        file.with_suffix(".json.bak").write_text(good, encoding="utf-8")  # only a readable file replaces the copy
    except (OSError, ValueError):
        pass
    tmp = file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, file)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _same(a, b):
    # Turkish casing: "I".lower() is "i" and "İ".lower() is "i" + a combining dot, so ı/i count as one letter.
    norm = lambda text: re.sub(r"\W+", " ", text.lower().replace("̇", "").replace("ı", "i")).strip()  # noqa: E731
    return norm(a) == norm(b)


def add_core(text, source=""):
    """A never-forget memory. Returns its entry, or None if it's empty or already there."""
    text = (text or "").strip()[:400]
    if not text:
        return None
    with _lock:
        data = load()
        if any(_same(text, m["text"]) for m in data["core"]):
            return None
        entry = {"id": uuid.uuid4().hex[:8], "t": _now(), "text": text, "source": source}
        data["core"].append(entry)
        _save(data)
        return entry


def remove_core(memory_id):
    """Only the owner does this (the Anılar window). True if it was there."""
    with _lock:
        data = load()
        kept = [m for m in data["core"] if m["id"] != memory_id]
        if len(kept) == len(data["core"]):
            return False
        data["core"] = kept
        _save(data)
        return True


def add_note(text, source=""):
    text = (text or "").strip()[:400]
    if not text:
        return None
    with _lock:
        data = load()
        entry = {"t": _now(), "text": text, "source": source}
        data["notes"] = (data["notes"] + [entry])[-NOTES_KEPT:]
        _save(data)
        return entry


def prompt_block():
    """Her memories for the system prompt ("" when there are none). Never raises."""
    try:
        data = load()
    except Exception as e:
        _log(f"prompt block failed: {e!r}")
        return ""
    core, notes = data["core"], data["notes"][-NOTES_IN_PROMPT:]
    if not core and not notes:
        return ""
    lines = [f"Your memories of {_state['user']} (yours, from earlier conversations: bring them up naturally "
             "when they fit, never recite them as a list):"]
    if core:
        lines.append("Never forget:")
        lines += [f"- ({m['t'][:10]}) {m['text']}" for m in core]
    if notes:
        lines.append("Recent conversations:")
        lines += [f"- ({n['t'][5:16].replace('T', ' ')}) {n['text']}" for n in notes]
    return "\n".join(lines)


# --- after a conversation -------------------------------------------------------------------------------

def transcript(messages):
    """The conversation as "name: text" lines: only what the owner and she said (no tool rounds, no
    screenshots, no notes like "[Zyraena opened the chat herself.]", no spoken-reply hint)."""
    lines = []
    for m in messages or []:
        content = m.get("content")
        if m.get("role") not in ("user", "assistant") or not isinstance(content, str):
            continue
        text = _HINT.sub("", content).strip()
        if not text or re.fullmatch(r"\[[^\]]*\]", text):
            continue
        lines.append((m["role"], text))
    return lines


def chat_ended(chat, source):
    """A conversation is over (chat: ai_assistant's chat dict). Looks back at it on its own thread unless
    the owner said next to nothing. Returns whether it will. Never raises."""
    try:
        messages = list((chat or {}).get("messages") or [])
        lines = transcript(messages)
        if sum(len(text) for role, text in lines if role == "user") < MIN_USER_CHARS:
            return False
        user_care.note_chat()
        threading.Thread(target=_look_back_safe, args=(lines, source), daemon=True).start()
        return True
    except Exception as e:
        _log(f"chat_ended failed: {e!r}")
        return False


def _look_back_safe(lines, source):
    try:
        look_back(lines, source)
    except Exception as e:
        _log(f"looking back failed: {e!r}")


def _prompt(lines, affection, core, language):
    user, ai = _state["user"], _state["ai"]
    talk = "\n".join(f"{user if role == 'user' else ai}: {text}" for role, text in lines)[-TRANSCRIPT_CHARS:]
    known = "\n".join(f"- {m['text']}" for m in core) or "- (none yet)"
    now = (f"Her affection now: {affection[0]}/100 ({affection[1]}).\n" if affection else "")
    return (
        f"You look back at a conversation that just ended between {user} (the user) and {ai} (the AI "
        f"companion {user} built for themselves). Answer with JSON only:\n"
        '{"affection": <integer -5..5>, "reason": "<a few words>", "note": "<one or two sentences, or empty>", '
        '"core": ["<...>"]}\n\n'
        f"affection: how this conversation changes {ai}'s affection for {user}. {now}"
        "0 for plain tasks and small talk. +1/+2: friendly, thankful, kind. +3..+5: real trust and warmth, "
        f"telling her what she means to them, sharing something personal, keeping a promise. -1/-2: curt, "
        "dismissive. -3..-5: insults, contempt, breaking a promise she cared about. Orders and tasks alone "
        "are never negative.\n"
        f"note: what {ai} would want to remember of it (what {user} did, felt, planned or promised), in "
        f"{language}, about {user} in the third person. Empty for a plain task.\n"
        f"core: only what she must never forget, which is rare: what she means to {user} and names they give "
        "her, serious promises, important facts of their life (people, health, goals, dates). Usually empty; "
        f"at most {CORE_PER_CHAT}, in {language}, each one short sentence. Leave out what is already known:\n"
        f"{known}\n\nConversation:\n{talk}"
    )


def parse(answer):
    """The model's JSON, cleaned: {"affection": int, "reason": str, "note": str, "core": [str]}."""
    match = re.search(r"\{.*\}", answer or "", re.S)
    data = json.loads(match.group(0)) if match else {}
    try:
        change = int(round(float(data.get("affection") or 0)))
    except (TypeError, ValueError):
        change = 0
    core = data.get("core") or []
    if isinstance(core, str):
        core = [core]
    return {"affection": max(-5, min(5, change)), "reason": str(data.get("reason") or "").strip(),
            "note": str(data.get("note") or "").strip(),
            "core": [str(c).strip() for c in core if str(c).strip()][:CORE_PER_CHAT]}


def look_back(lines, source):
    """One request to the assistant model about the finished conversation, then affection, note and
    never-forget memories. Returns what was applied."""
    classify = _state["classify"]
    if classify is None:
        return None
    language = "Turkish" if _state["lang"]() == "tr" else "English"
    result = parse(classify(_prompt(lines, user_care.affection(), load()["core"], language), "after a chat"))
    result["counted"] = user_care.add_affection(result["affection"], result["reason"], source) \
        if result["affection"] else 0
    if result["note"]:
        add_note(result["note"], source)
    result["added"] = []
    for text in result["core"]:
        if add_core(text, source):
            result["added"].append(text)
            user_care.log_event("core_memory", text=text[:120])
    _log(f"{source}: affection {result['affection']:+d} (counted {result['counted']:+d}), "
         f"note {'yes' if result['note'] else 'no'}, never-forget +{len(result['added'])}")
    return result


# --- her tool -------------------------------------------------------------------------------------------

def remember_forever(memory: str) -> str:
    entry = add_core(memory, "asked")
    if entry is None:
        return "Already among your never-forget memories (or empty)." if (memory or "").strip() else "Nothing to save."
    user_care.log_event("core_memory", text=entry["text"][:120])
    return "Saved among your never-forget memories; it stays in your prompt from now on."


TOOLS = [{
    "type": "function",
    "function": {
        "name": "remember_forever",
        "description": "Saves something the user wants you never to forget (\"bunu unutma\", \"bunu hep hatırla\"), "
                       "or a truly important fact about them or your bond. It stays in your prompt for good. "
                       "Not for ordinary things: those are remembered on their own after the conversation.",
        "parameters": {"type": "object", "properties": {
            "memory": {"type": "string", "description": "The memory as one short sentence about the user, "
                                                        "in the user's language."}}, "required": ["memory"]},
    },
}]
TOOL_FUNCTIONS = {"remember_forever": remember_forever}
