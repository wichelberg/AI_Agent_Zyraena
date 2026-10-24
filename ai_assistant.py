import json
import os
import re
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

import requests
from pynput import keyboard
from tavily import TavilyClient

import desktop_pet
import i18n
import paths
import browser_tools
import chat_box
import control_panel
import credit_log
import disk_watch
import media_tools
import pc_tools
import reminder_tools
import screen_tools
import sleep_mode
import steam_tools
import system_tools
import user_care
import web_control
import whatsapp_tools

AI_NAME = "Zyraena"
USER_NAME = os.environ.get("ZYRAENA_USER_NAME", "").strip() or "You"

CHAT_LOG_DIR = paths.app_dir() / "chat_logs"
CHAT_LOG_DIR.mkdir(exist_ok=True)

MAX_TOOL_ROUNDS = 20
CONFIRM_TIMEOUT_SECONDS = 300


def _call_with_retry(fn, retries=2, delay=2.0):
    """Retries on transient connection/server errors before giving up.
    Raises immediately on 4xx errors (bad key, rate limit, etc.) since retrying won't help."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except requests.exceptions.ConnectionError as e:
            last_error = e
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code < 500:
                raise
            last_error = e
        if attempt < retries:
            time.sleep(delay)
    raise last_error


_tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))  # .env is loaded by paths


def _load_personality():
    """The persona for "lady" mode: personality.md next to the exe (multi-line Markdown),
    else the single-line ZYRAENA_PERSONALITY from .env."""
    path = paths.app_dir() / "personality.md"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return os.environ.get("ZYRAENA_PERSONALITY", "").strip()


_personality = _load_personality()

MODE_COMMAND = "/mode"
DEFAULT_ASSISTANT_PROMPT = (
    "You are a helpful, concise assistant. Answer clearly and accurately, "
    "and reply in the language the user writes in. For WhatsApp use whatsapp_chats, whatsapp_messages "
    "and send_whatsapp_file, which work through the WhatsApp Desktop app; never WhatsApp Web in the browser."
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"

# Each mode is a model + system prompt, all served through OpenRouter's
# OpenAI-compatible endpoint. Chat history is stored in OpenAI chat format, so
# a session can switch modes mid-conversation and keep its history.
MODES = {
    "assistant": {
        "provider": "OpenRouter",
        "url": OPENROUTER_URL,
        "key_env": OPENROUTER_KEY_ENV,
        "model": os.environ.get("OPENROUTER_ASSISTANT_MODEL", "").strip() or "google/gemini-3.7-flash",
        "system": os.environ.get("ASSISTANT_PERSONALITY", "").strip() or DEFAULT_ASSISTANT_PROMPT,
    },
    "lady": {
        "provider": "OpenRouter",
        "url": OPENROUTER_URL,
        "key_env": OPENROUTER_KEY_ENV,
        "model": os.environ.get("OPENROUTER_LADY_MODEL", "").strip() or "anthropic/claude-haiku-5.5",
        "system": _personality,
    },
}

_default_mode = os.environ.get("ZYRAENA_DEFAULT_MODE", "").strip().lower()
if _default_mode not in MODES:
    _default_mode = "assistant"

_state = {"listener": None, "chat": None, "log_path": None}  # chat/log_path: the open text box
_lock = threading.Lock()
# The text box, yes/no box and the pet's lines (no window toggle any more): ZYRAENA_LANGUAGE, Turkish by default.
_language = os.environ.get("ZYRAENA_LANGUAGE", "").strip().lower() or "tr"
if _language not in i18n.STRINGS:
    _language = i18n.DEFAULT_LANGUAGE


def web_search(query: str) -> str:
    """Searches the web for current, up-to-date, or real-world information.

    Use this whenever the answer depends on recent, specific, or verifiable
    facts (news, prices, specs, dates, current events) rather than general
    knowledge you're already confident about.

    Args:
        query: The search query to look up on the web.
    """
    credit_log.before_search()
    try:
        response = _tavily_client.search(query, max_results=5)
    except Exception as e:
        return i18n.get(_language, "web_search_failed", error=e)

    results = response.get("results", [])
    if not results:
        return i18n.get(_language, "web_search_no_results")

    return "\n".join(
        f"- {r.get('title', '')} ({r.get('url', '')})\n  {r.get('content', '')}"
        for r in results
    )


def search_memory(query: str) -> str:
    """Searches past saved conversations for something the user refers to.

    Use this when the user asks whether you remember something from an
    earlier conversation, or references something discussed before.

    Args:
        query: Keywords describing what to look for in past conversations.
    """
    keywords = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]
    if not keywords:
        return i18n.get(_language, "memory_no_keywords")

    current_log = _state.get("log_path")
    matches = []
    for log_file in sorted(CHAT_LOG_DIR.glob("*.txt")):
        if log_file == current_log:
            continue  # skip the still-open current session
        try:
            lines = log_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        seen_contexts = set()
        for i, line in enumerate(lines):
            if any(kw in line.lower() for kw in keywords):
                context = "\n".join(lines[max(0, i - 1): i + 2])
                if context in seen_contexts:
                    continue
                seen_contexts.add(context)
                matches.append(f"[{log_file.stem}]\n{context}")

    if not matches:
        return i18n.get(_language, "memory_no_matches")
    return "\n\n".join(matches[:10])


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Searches the web for current, up-to-date, or real-world information. "
                "Use this whenever the answer depends on recent, specific, or verifiable "
                "facts (news, prices, specs, dates, current events) rather than general "
                "knowledge you're already confident about."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query to look up on the web."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": (
                "Searches past saved conversations for something the user refers to. "
                "Use this when the user asks whether you remember something from an "
                "earlier conversation, or references something discussed before."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords describing what to look for in past conversations."},
                },
                "required": ["query"],
            },
        },
    },
] + (pc_tools.TOOLS + browser_tools.TOOLS + system_tools.TOOLS + steam_tools.TOOLS
     + screen_tools.TOOLS + media_tools.TOOLS + reminder_tools.TOOLS + whatsapp_tools.TOOLS
     + web_control.TOOLS + sleep_mode.TOOLS)

TOOL_FUNCTIONS = {
    "web_search": web_search,
    "search_memory": search_memory,
    **pc_tools.TOOL_FUNCTIONS,
    **browser_tools.TOOL_FUNCTIONS,
    **system_tools.TOOL_FUNCTIONS,
    **steam_tools.TOOL_FUNCTIONS,
    **screen_tools.TOOL_FUNCTIONS,
    **media_tools.TOOL_FUNCTIONS,
    **reminder_tools.TOOL_FUNCTIONS,
    **whatsapp_tools.TOOL_FUNCTIONS,
    **web_control.TOOL_FUNCTIONS,
    **sleep_mode.TOOL_FUNCTIONS,
    **user_care.TOOL_FUNCTIONS,
}


def _ask_confirmation(key, **kwargs):
    """Called from the worker thread by pc_tools before any change on the PC: a yes/no box in the
    text box's neon look beside the pet; blocks until it's answered (no after CONFIRM_TIMEOUT_SECONDS)."""
    return chat_box.confirm(i18n.get(_language, "confirm_title"), i18n.render(_language, key, **kwargs),
                            i18n.get(_language, "confirm_yes"), i18n.get(_language, "confirm_no"),
                            CONFIRM_TIMEOUT_SECONDS)


pc_tools.confirm_handler = _ask_confirmation


def _notify(key, **kwargs):
    """Reports a finished background job started from the PC: in the text box if it's open,
    otherwise wherever pc_tools.fallback_notify sends it (Telegram)."""
    text = i18n.render(_language, key, **kwargs)
    if chat_box.is_open():
        chat_box.add(AI_NAME, text, "her")
    else:
        pc_tools.fallback_notify(text)


pc_tools.notify_handler = _notify


def answer_message(chat, text, language=None, source="other"):
    """Like _send_message, but turns any failure into a user-facing message instead of raising.
    Also handles the /mode command, which switches the model this chat continues on.
    `language` overrides the window's UI language for these messages (Telegram is always Turkish).
    `source` (box, telegram, voice) is where the request came from, for the credit log."""
    lang = language or _language
    if _is_mode_command(text):
        return _handle_mode_command(chat, text.strip()[len(MODE_COMMAND):].strip().lower(), lang)

    mode = MODES[chat["mode"]]
    if not os.environ.get(mode["key_env"], "").strip():
        return i18n.get(lang, "invalid_api_key", provider=mode["provider"], env=mode["key_env"])
    try:
        with credit_log.activity(source, text):
            return _send_message(chat, text)
    except requests.exceptions.ConnectionError:
        return i18n.get(lang, "connection_error", provider=mode["provider"])
    except requests.exceptions.HTTPError as e:
        if e.response is None:
            return i18n.get(lang, "generic_error", error=e)
        status, body = e.response.status_code, e.response.text
    except Exception as e:
        return i18n.get(lang, "generic_error", error=e)

    if status in (401, 403):
        return i18n.get(lang, "invalid_api_key", provider=mode["provider"], env=mode["key_env"])
    if status == 404:
        return i18n.get(lang, "model_not_found", provider=mode["provider"], model=mode["model"])
    if status == 429:
        return i18n.get(lang, "rate_limited")
    if status >= 500:
        return i18n.get(lang, "server_overloaded", provider=mode["provider"])
    return i18n.get(lang, "generic_error", error=body)


def default_mode():
    return _default_mode


def new_chat(mode=None):
    """A chat session: its mode plus the history in OpenAI chat format (system
    prompt excluded; it's added per request from the current mode)."""
    return {"mode": mode or _default_mode, "messages": []}


def _is_mode_command(text):
    text = text.strip().lower()
    return text.startswith(MODE_COMMAND) and text[len(MODE_COMMAND):][:1] in ("", " ")


def _handle_mode_command(chat, name, lang):
    global _default_mode
    if not name:
        mode = MODES[chat["mode"]]
        return i18n.get(lang, "mode_current", mode=chat["mode"], model=mode["model"], modes=", ".join(MODES))
    if name not in MODES:
        return i18n.get(lang, "mode_unknown", mode=name, modes=", ".join(MODES))
    chat["mode"] = name
    _default_mode = name  # new chats start in the last chosen mode
    return i18n.get(lang, "mode_switched", mode=name, model=MODES[name]["model"])


def _system_prompt(mode):
    now = datetime.now()
    clock = f"Current local date and time: {now:%Y-%m-%d %H:%M} ({now:%A})."
    text = f"{mode['system']}\n\n{clock}" if mode["system"] else clock
    care = user_care.prompt_block() if mode is MODES["lady"] else ""  # the mood is the persona's, not the assistant's
    return f"{text}\n\n{care}" if care else text


def _tools(mode):
    return TOOLS + user_care.TOOLS if mode is MODES["lady"] else TOOLS


def _openai_compat_request(mode, messages):
    """Returns (content, tool_calls, cost_in_usd) for the next assistant turn."""
    response = requests.post(
        mode["url"],
        headers={
            "Authorization": f"Bearer {os.environ.get(mode['key_env'], '').strip()}",
            "Content-Type": "application/json",
            "X-Title": "Zyraena",
        },
        json={
            "model": mode["model"],
            "messages": [{"role": "system", "content": _system_prompt(mode)}] + messages,
            "tools": _tools(mode),
            "usage": {"include": True},  # OpenRouter reports the request's cost
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    credit_log.record(mode["model"], data.get("usage"))
    message = data["choices"][0]["message"]
    tool_calls = message.get("tool_calls") or []
    for tc in tool_calls:
        tc["id"] = tc.get("id") or f"call_{uuid.uuid4().hex[:12]}"  # some models leave ids empty
    return message.get("content") or "", tool_calls, float((data.get("usage") or {}).get("cost") or 0)


def _drop_images(messages):
    """Replaces screenshots already answered from with a placeholder, so they aren't
    re-sent (and paid for) with every later message."""
    for m in messages:
        if isinstance(m.get("content"), list):
            m["content"] = "[screenshot from look_at_screen, no longer attached]"


def _send_message(chat, user_text):
    """Sends a message, resolving any tool calls, and returns the final answer text.
    chat["messages"] is mutated in place so the conversation history keeps growing.
    A tool may return {"text": ..., "image": data_uri}; the image is shown to the
    model in a message right after the tool results."""
    messages = chat["messages"]
    messages.append({"role": "user", "content": user_text})
    cost = 0.0
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            mode = MODES[chat["mode"]]
            content, tool_calls, round_cost = _call_with_retry(lambda: _openai_compat_request(mode, messages))
            cost += round_cost

            if not tool_calls:
                messages.append({"role": "assistant", "content": content})
                return content

            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
            images = []
            for tc in tool_calls:
                fn_info = tc["function"]
                credit_log.note_tool(fn_info["name"])
                func = TOOL_FUNCTIONS.get(fn_info["name"])
                try:
                    args = json.loads(fn_info.get("arguments") or "{}")
                    result = func(**args) if func else i18n.get(_language, "unknown_tool", name=fn_info["name"])
                except Exception as e:
                    result = i18n.get(_language, "tool_error", error=e)
                if isinstance(result, dict) and "image" in result:
                    images.append(result["image"])
                    result = result["text"]
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(result)})
            if images:
                messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": "[Screenshot taken by look_at_screen]"}]
                    + [{"type": "image_url", "image_url": {"url": url}} for url in images],
                })

        return i18n.get(_language, "too_many_tool_calls")
    finally:
        _drop_images(messages)
        if cost:
            _message_costs.append(cost)


# --- OpenRouter credits ---------------------------------------------------------------

_message_costs = deque(maxlen=50)  # cost of each recent user message, all tool rounds included


def openrouter_balance(timeout=10):
    """Remaining OpenRouter credit in USD, or None if it can't be read."""
    try:
        resp = requests.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {os.environ.get(OPENROUTER_KEY_ENV, '').strip()}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return float(data["total_credits"]) - float(data["total_usage"])
    except Exception:
        return None


def credits_text(lang):
    remaining = openrouter_balance()
    if remaining is None:
        return i18n.get(lang, "openrouter_credits_failed")
    text = i18n.get(lang, "openrouter_credits", remaining=remaining)
    if _message_costs:
        average = sum(_message_costs) / len(_message_costs)
        if average > 0:
            text += "\n" + i18n.get(lang, "openrouter_estimate", messages=int(remaining / average),
                                    average=average, count=len(_message_costs))
    return text


def get_openrouter_credits() -> str:
    return credits_text("en")


TOOLS.append({
    "type": "function",
    "function": {
        "name": "get_openrouter_credits",
        "description": "Shows the user's remaining OpenRouter credit (what Zyraena's replies cost) and roughly "
                       "how many more messages it covers at the recent average cost.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
})
TOOL_FUNCTIONS["get_openrouter_credits"] = get_openrouter_credits


def _get_tavily_credits():
    """Returns (kind, data) where kind is 'ok' | 'unknown' | 'error', for re-rendering on language toggle."""
    try:
        resp = requests.get(
            "https://api.tavily.com/usage",
            headers={"Authorization": f"Bearer {os.environ.get('TAVILY_API_KEY')}"},
            timeout=5,
        )
        resp.raise_for_status()
        account = resp.json().get("account", {})
        usage, limit = account.get("plan_usage"), account.get("plan_limit")
        if usage is None or limit is None:
            return ("unknown", None)
        return ("ok", {"remaining": limit - usage, "limit": limit})
    except Exception:
        return ("error", None)


def _tavily_remaining():
    kind, data = _get_tavily_credits()
    return data["remaining"] if kind == "ok" else None


# Before / after balances for the credit log; "before" holds the request up, so it gets a short timeout.
credit_log.configure(balance=lambda: openrouter_balance(timeout=4), tavily=_tavily_remaining)


def _new_log_path():
    return CHAT_LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"


def _log_line(who, text):
    path = _state.get("log_path")
    if path is None:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{who}: {text}\n")


def _box_open():
    with _lock:
        _state["chat"] = new_chat()
        _state["log_path"] = _new_log_path()
    desktop_pet.activity("listen")


def _box_close():
    with _lock:
        _state["chat"] = None
        _state["log_path"] = None
    import voice_session

    if not voice_session.active():  # a spoken conversation keeps her busy
        desktop_pet.activity(None)


def _box_send(text):
    """Enter in the text box: Zyraena thinks (the pet too), then her answer shows in the box while the
    pet talks for about as long as it takes to read. Silent: the owner chose text for the box."""
    chat = _state["chat"]
    if chat is None:
        return
    chat_box.add(USER_NAME, text, "you")
    _log_line(USER_NAME, text)
    chat_box.thinking(True)
    desktop_pet.activity("think")

    def work():
        user_care.box_message(text)  # the answer to her 03:00 question, if she asked one
        answer = answer_message(chat, text, source="box")
        _log_line(AI_NAME, answer)
        chat_box.thinking(False)
        chat_box.add(AI_NAME, answer, "her")
        desktop_pet.activity("talk")
        time.sleep(min(10.0, max(2.0, len(answer) / 18)))
        if chat_box.is_open() and _state["chat"] is chat:
            desktop_pet.activity("listen")

    threading.Thread(target=work, daemon=True).start()


def toggle_chat_box():
    """Thread-safe: opens the text box beside the pet, or closes it (a click on her). A hidden pet
    comes back first."""
    if not desktop_pet.visible():
        desktop_pet.toggle()
    chat_box.toggle(_box_open, _box_send, _box_close, i18n.get(_language, "box_hint"),
                    i18n.get(_language, "box_thinking"))


def say_in_box(text):
    """Thread-safe: Zyraena starts the conversation herself (User Care: the 03:00 question, the morning
    summary): the text box opens (unless it's open) with her line, and the chat goes on from it."""
    if not chat_box.is_open():
        toggle_chat_box()

    def add():
        chat = _state["chat"]
        if chat is not None:
            # A user turn first: some providers don't take a conversation that starts with the assistant.
            chat["messages"] += [{"role": "user", "content": "[Zyraena opened the chat herself.]"},
                                 {"role": "assistant", "content": text}]
            _log_line(AI_NAME, text)
        chat_box.add(AI_NAME, text, "her")
        desktop_pet.activity("talk")

    chat_box.post(add)


def toggle_panel():
    """Thread-safe: opens the panel in the middle of the screen (Ctrl+F1), or closes it: show/hide the
    pet, the live OpenRouter and Tavily credits, the API credit log, the Disk tab and the Care tab."""
    control_panel.toggle(_language, desktop_pet.visible, desktop_pet.toggle, openrouter_balance,
                         _get_tavily_credits, disk_watch, credit_log, user_care.service())


def open_disk_panel():
    """Thread-safe: the panel on its Disk tab (a click on the pet's "Disk: new findings" bubble)."""
    control_panel.show("disk", _language, desktop_pet.visible, desktop_pet.toggle, openrouter_balance,
                       _get_tavily_credits, disk_watch, credit_log, user_care.service())


def open_care_panel():
    """Thread-safe: the panel on its Care tab (User Care's debug run opens it at start)."""
    control_panel.show("care", _language, desktop_pet.visible, desktop_pet.toggle, openrouter_balance,
                       _get_tavily_credits, disk_watch, credit_log, user_care.service())


def ask_flash(prompt, what="", source="disk"):
    """One question to the assistant mode's model (Gemini Flash) with no tools and no history; returns
    the answer's text. The disk scanner uses it for folders no rule knows (disk_memory.describe), User
    Care to sort the owner's answer at 03:00."""
    mode = MODES["assistant"]
    key = os.environ.get(mode["key_env"], "").strip()
    if not key:
        raise RuntimeError(f"{mode['key_env']} is not set")

    def request():
        response = requests.post(mode["url"], headers={"Authorization": f"Bearer {key}", "X-Title": "Zyraena"},
                                 json={"model": mode["model"], "messages": [{"role": "user", "content": prompt}],
                                       "usage": {"include": True}}, timeout=90)
        response.raise_for_status()
        return response.json()

    with credit_log.activity(source, what):
        data = _call_with_retry(request)
        credit_log.record(mode["model"], data.get("usage"))
    return data["choices"][0]["message"].get("content") or ""


def ask_persona(instruction, what=""):
    """One message in Zyraena's own voice (lady mode: her persona and User Care's mood) with no tools and no
    history, for what User Care says by itself (break over on Telegram, the 03:00 question, the morning
    summary). Returns the text."""
    mode = MODES["lady"]
    key = os.environ.get(mode["key_env"], "").strip()
    if not key:
        raise RuntimeError(f"{mode['key_env']} is not set")
    language = "Turkish" if _language == "tr" else "English"

    def request():
        response = requests.post(mode["url"], headers={"Authorization": f"Bearer {key}", "X-Title": "Zyraena"},
                                 json={"model": mode["model"],
                                       "messages": [{"role": "system", "content": _system_prompt(mode)},
                                                    {"role": "user", "content": f"[User Care, not from the user] "
                                                                                f"{instruction} Write in {language}; "
                                                                                "only the message itself."}],
                                       "usage": {"include": True}}, timeout=60)
        response.raise_for_status()
        return response.json()

    with credit_log.activity("care", what):
        data = _call_with_retry(request)
        credit_log.record(mode["model"], data.get("usage"))
    return data["choices"][0]["message"].get("content") or ""


def start_user_care(notify, debug=None):
    """Starts User Care (user_care.py) with Zyraena's voice, the text box and `notify` (Telegram)."""
    return user_care.start(persona=ask_persona, classify=lambda prompt, what: ask_flash(prompt, what, "care"),
                           notify=notify, chat=say_in_box, lang=current_language, debug=debug)


HOTKEY = "<ctrl>+<f1>"


def current_language():
    return _language


def start_ai_assistant():
    """Starts the global Ctrl+F1 hotkey (the panel)."""
    if _state["listener"] is not None:
        return  # already running
    listener = keyboard.GlobalHotKeys({HOTKEY: toggle_panel})
    listener.daemon = True
    listener.start()
    _state["listener"] = listener


def stop_ai_assistant():
    listener = _state["listener"]
    if listener is not None:
        listener.stop()
        _state["listener"] = None
