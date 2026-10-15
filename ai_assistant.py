import json
import os
import re
import threading
import time
import tkinter as tk
import uuid
from collections import deque
from datetime import datetime
from tkinter import messagebox
from pathlib import Path

import requests
from PIL import Image, ImageTk
from pynput import keyboard
from tavily import TavilyClient

import i18n
import paths
import browser_tools
import media_tools
import pc_tools
import reminder_tools
import screen_tools
import sleep_mode
import steam_tools
import system_tools
import voice
import whatsapp_tools

AI_NAME = "Zyraena"
AI_AVATAR = "Zyraena.png"
USER_NAME = os.environ.get("ZYRAENA_USER_NAME", "").strip() or "You"
USER_AVATAR = "user.jpg"  # optional: put your own picture in assets/

CHAT_LOG_DIR = paths.app_dir() / "chat_logs"
CHAT_LOG_DIR.mkdir(exist_ok=True)

AVATAR_DIR = paths.resource_dir() / "assets"
AVATAR_SIZE = 25
HEADER_AVATAR_SIZE = 140

# Theme: white / gold / purple, futuristic accents
BG_COLOR = "#241333"     # near-black purple (window background / frames)
PURPLE = "#7A3FC4"       # user label color / glow accent
GOLD = "#D4AF37"         # buttons, borders
GOLD_TEXT = "#9C7A00"    # Zyraena label color (readable on white)
GOLD_LIGHT = "#F1D97A"   # button hover/active
WHITE = "#FDFBFF"        # history/entry background
MUTED = "#8A7F99"        # mode label under Zyraena's messages
MONO_FONT = "Consolas"

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
    "and reply in the language the user writes in."
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

_state = {"root": None, "listener": None, "window": None, "chat": None, "log_path": None}
_lock = threading.Lock()
_avatar_cache = {}
_language = i18n.DEFAULT_LANGUAGE


def _load_avatar(filename, size=AVATAR_SIZE):
    """Loads+resizes an avatar image once per (filename, size) and keeps it
    cached (and referenced, so Tk doesn't garbage-collect it)."""
    cache_key = (filename, size)
    if cache_key in _avatar_cache:
        return _avatar_cache[cache_key]

    path = AVATAR_DIR / filename
    photo = None
    if path.exists():
        try:
            img = Image.open(path).convert("RGB").resize((size, size), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
        except Exception as e:
            print(i18n.get(_language, "avatar_load_failed", filename=filename, error=e))
    _avatar_cache[cache_key] = photo
    return photo


def _draw_gradient(canvas, color_start, color_end):
    canvas.delete("all")
    width = canvas.winfo_width()
    height = canvas.winfo_height()
    if width <= 1:
        return
    r1, g1, b1 = canvas.winfo_rgb(color_start)
    r2, g2, b2 = canvas.winfo_rgb(color_end)
    steps = max(width // 4, 1)
    for i in range(steps):
        t = i / steps
        r = int(r1 + (r2 - r1) * t) >> 8
        g = int(g1 + (g2 - g1) * t) >> 8
        b = int(b1 + (b2 - b1) * t) >> 8
        color = f"#{r:02x}{g:02x}{b:02x}"
        x0 = i * (width / steps)
        x1 = (i + 1) * (width / steps)
        canvas.create_rectangle(x0, 0, x1, height, outline="", fill=color)


def web_search(query: str) -> str:
    """Searches the web for current, up-to-date, or real-world information.

    Use this whenever the answer depends on recent, specific, or verifiable
    facts (news, prices, specs, dates, current events) rather than general
    knowledge you're already confident about.

    Args:
        query: The search query to look up on the web.
    """
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
     + sleep_mode.TOOLS)

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
    **sleep_mode.TOOL_FUNCTIONS,
}


def _ask_confirmation(key, **kwargs):
    """Called from the worker thread by pc_tools before any change on the PC.
    Shows a yes/no dialog on the Tk thread and blocks until it's answered."""
    win = _state["window"]
    if win is None:
        return False

    result = {"ok": False}
    done = threading.Event()

    def ask():
        try:
            result["ok"] = messagebox.askyesno(
                i18n.get(_language, "confirm_title"), i18n.render(_language, key, **kwargs), parent=win,
            )
        finally:
            done.set()

    win.after(0, ask)
    # If the window is closed before the dialog shows, the callback never runs; deny after a while.
    done.wait(CONFIRM_TIMEOUT_SECONDS)
    return result["ok"]


pc_tools.confirm_handler = _ask_confirmation


def _notify(key, **kwargs):
    """Reports a finished background job started from the PC: in Zyraena's window if
    it's open, otherwise wherever pc_tools.fallback_notify sends it (Telegram)."""
    text = i18n.render(_language, key, **kwargs)
    win, append = _state["window"], _state.get("append")
    if win is not None and append is not None:
        win.after(0, append, AI_NAME, text, "ai_name", AI_AVATAR)
    else:
        pc_tools.fallback_notify(text)


pc_tools.notify_handler = _notify


def answer_message(chat, text, language=None):
    """Like _send_message, but turns any failure into a user-facing message instead of raising.
    Also handles the /mode command, which switches the model this chat continues on.
    `language` overrides the window's UI language for these messages (Telegram is always Turkish)."""
    lang = language or _language
    if _is_mode_command(text):
        return _handle_mode_command(chat, text.strip()[len(MODE_COMMAND):].strip().lower(), lang)

    mode = MODES[chat["mode"]]
    if not os.environ.get(mode["key_env"], "").strip():
        return i18n.get(lang, "invalid_api_key", provider=mode["provider"], env=mode["key_env"])
    try:
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
    return f"{mode['system']}\n\n{clock}" if mode["system"] else clock


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
            "tools": TOOLS,
            "usage": {"include": True},  # OpenRouter reports the request's cost
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
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


def openrouter_balance():
    """Remaining OpenRouter credit in USD, or None if it can't be read."""
    try:
        resp = requests.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {os.environ.get(OPENROUTER_KEY_ENV, '').strip()}"},
            timeout=10,
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


def _render_credits(kind, data):
    if kind == "ok":
        return i18n.get(_language, "credits_format", remaining=data["remaining"], limit=data["limit"])
    if kind == "unknown":
        return i18n.get(_language, "credits_unknown")
    if kind == "error":
        return i18n.get(_language, "credits_failed")
    return i18n.get(_language, "credits_loading")


def _new_log_path():
    return CHAT_LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"


def _log_line(who, text):
    path = _state.get("log_path")
    if path is None:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{who}: {text}\n")


def _close_popup():
    with _lock:
        win = _state["window"]
        _state["window"] = None
        _state["chat"] = None
        _state["log_path"] = None
        recorder = _state.pop("recorder", None)
    if recorder is not None:
        recorder.stop()
    if win is not None:
        win.destroy()


def _open_popup():
    with _lock:
        if _state["window"] is not None:
            already_open = True
        else:
            already_open = False
            win = tk.Toplevel(_state["root"])
            _state["window"] = win
            _state["chat"] = new_chat()
            _state["log_path"] = _new_log_path()

    if already_open:
        _close_popup()
        return

    win.title(i18n.get(_language, "window_title"))
    win.geometry("640x760")
    win.minsize(480, 460)
    win.attributes("-topmost", True)
    win.configure(bg=BG_COLOR)

    win.rowconfigure(2, weight=1)
    win.rowconfigure(3, weight=0)
    win.columnconfigure(0, weight=1)

    header = tk.Frame(win, bg=BG_COLOR)
    header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))
    header.columnconfigure(0, weight=1)
    header.columnconfigure(1, weight=0)
    header.columnconfigure(2, weight=1)

    ai_side = tk.Frame(header, bg=BG_COLOR)
    ai_side.grid(row=0, column=0, sticky="w")
    ai_header_avatar = _load_avatar(AI_AVATAR, HEADER_AVATAR_SIZE)
    if ai_header_avatar is not None:
        tk.Label(ai_side, image=ai_header_avatar, bg=BG_COLOR).pack()
    tk.Label(ai_side, text=AI_NAME, bg=BG_COLOR, fg=GOLD, font=("Segoe UI", 12, "bold")).pack()

    center = tk.Frame(header, bg=BG_COLOR)
    center.grid(row=0, column=1, padx=12)

    buttons_row = tk.Frame(center, bg=BG_COLOR)
    buttons_row.pack()
    mic_btn = tk.Button(
        buttons_row, text="🎤", command=lambda: toggle_mic(), bg=BG_COLOR, fg=GOLD,
        activebackground=BG_COLOR, activeforeground=GOLD_LIGHT, relief="flat",
        font=("Segoe UI", 16), borderwidth=0, highlightthickness=1,
        highlightbackground=GOLD,
    )
    mic_btn.pack(side="left")
    lang_btn = tk.Button(
        buttons_row, text=i18n.get(_language, "lang_toggle"), command=lambda: toggle_language(),
        bg=BG_COLOR, fg=GOLD, activebackground=BG_COLOR, activeforeground=GOLD_LIGHT,
        relief="flat", font=("Segoe UI", 10, "bold"), borderwidth=0, highlightthickness=1,
        highlightbackground=GOLD, padx=6,
    )
    lang_btn.pack(side="left", padx=(6, 0))

    credits_var = tk.StringVar(value=i18n.get(_language, "credits_loading"))
    tk.Label(center, textvariable=credits_var, bg=BG_COLOR, fg=GOLD_LIGHT, font=(MONO_FONT, 7)).pack(pady=(4, 0))
    openrouter_var = tk.StringVar(value="OpenRouter: …")
    tk.Label(center, textvariable=openrouter_var, bg=BG_COLOR, fg=GOLD_LIGHT, font=(MONO_FONT, 7)).pack()

    user_side = tk.Frame(header, bg=BG_COLOR)
    user_side.grid(row=0, column=2, sticky="e")
    user_header_avatar = _load_avatar(USER_AVATAR, HEADER_AVATAR_SIZE)
    if user_header_avatar is not None:
        tk.Label(user_side, image=user_header_avatar, bg=BG_COLOR).pack()
    tk.Label(user_side, text=USER_NAME, bg=BG_COLOR, fg=PURPLE, font=("Segoe UI", 12, "bold")).pack()

    def load_credits():
        kind, data = _get_tavily_credits()
        _state["credits"] = (kind, data)
        win.after(0, credits_var.set, _render_credits(kind, data))
        balance = openrouter_balance()
        win.after(0, openrouter_var.set, f"OpenRouter: ${balance:.2f}" if balance is not None else "OpenRouter: ?")

    threading.Thread(target=load_credits, daemon=True).start()

    gradient = tk.Canvas(win, height=3, highlightthickness=0, bg=BG_COLOR)
    gradient.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
    gradient.bind("<Configure>", lambda e: _draw_gradient(gradient, GOLD, PURPLE))

    history = tk.Text(
        win, state="disabled", wrap="word", bg=WHITE, fg=PURPLE,
        insertbackground=PURPLE, relief="flat", padx=10, pady=10,
        font=(MONO_FONT, 10), borderwidth=0, highlightthickness=2,
        highlightbackground=GOLD, highlightcolor=GOLD,
    )
    history.tag_config("user_name", foreground=PURPLE, font=("Segoe UI", 10, "bold"))
    history.tag_config("ai_name", foreground=GOLD_TEXT, font=("Segoe UI", 10, "bold"))
    history.tag_config("mode_label", foreground=MUTED, font=("Segoe UI", 8, "italic"))
    history.grid(row=2, column=0, sticky="nsew", padx=10, pady=4)

    input_frame = tk.Frame(win, bg=BG_COLOR)
    input_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(4, 10))
    input_frame.columnconfigure(0, weight=1)

    entry = tk.Entry(
        input_frame, bg=WHITE, fg=PURPLE, insertbackground=PURPLE,
        relief="flat", font=(MONO_FONT, 10), highlightthickness=2,
        highlightbackground=GOLD, highlightcolor=GOLD,
    )
    entry.grid(row=0, column=0, sticky="ew", ipady=4)

    def append_history(who, text, tag, avatar_file, mode=None):
        history.config(state="normal")
        avatar = _load_avatar(avatar_file)
        if avatar is not None:
            history.image_create("end", image=avatar)
            history.insert("end", " ")
        history.insert("end", f"{who}: ", tag)
        history.insert("end", f"{text}\n")
        if mode:
            history.insert("end", f"({mode})\n", "mode_label")
        history.insert("end", "\n")
        history.config(state="disabled")
        history.see("end")
        _log_line(who, text)

    _state["append"] = append_history
    append_history(AI_NAME, i18n.get(_language, "greeting", user=USER_NAME), "ai_name", AI_AVATAR, _state["chat"]["mode"])

    def on_send(event=None):
        message = entry.get().strip()
        if not message:
            return
        entry.delete(0, "end")
        append_history(USER_NAME, message, "user_name", USER_AVATAR)

        chat = _state["chat"]
        threading.Thread(target=respond, args=(chat, message, False), daemon=True).start()

    def respond(chat, message, speak):
        """Worker thread: answers, shows the answer, and reads it aloud if the user spoke (🎤)."""
        answer = answer_message(chat, message + voice.SPOKEN_HINT if speak else message)
        win.after(0, append_history, AI_NAME, answer, "ai_name", AI_AVATAR, chat["mode"])
        if speak:
            try:
                spoken = voice.synthesize(answer)
                if spoken is not None:
                    voice.play(spoken[0])
            except Exception as e:
                win.after(0, append_history, AI_NAME, i18n.get(_language, "voice_reply_failed", error=e),
                          "ai_name", AI_AVATAR)

    def toggle_mic():
        """First press starts recording, second press stops it and sends what was said."""
        recorder = _state.pop("recorder", None)
        if recorder is None:
            voice.stop_playing()
            try:
                _state["recorder"] = voice.Recorder()
            except Exception as e:
                append_history(AI_NAME, i18n.get(_language, "mic_failed", error=e), "ai_name", AI_AVATAR)
                return
            voice.warm_up()
            mic_btn.config(text="⏹", fg=PURPLE)
            return
        mic_btn.config(text="🎤", fg=GOLD)
        audio = recorder.stop()
        chat = _state["chat"]

        def hear():
            try:
                text = voice.transcribe(audio, MODES["assistant"]["model"]) if audio else ""
            except Exception as e:
                text, error = "", e
            else:
                error = None
            if not text:
                message = i18n.get(_language, "mic_failed", error=error) if error else i18n.get(_language, "voice_not_understood")
                win.after(0, append_history, AI_NAME, message, "ai_name", AI_AVATAR)
                return
            win.after(0, append_history, USER_NAME, f"🎤 {text}", "user_name", USER_AVATAR)
            respond(chat, text, True)

        threading.Thread(target=hear, daemon=True).start()

    send_btn = tk.Button(
        input_frame, text=i18n.get(_language, "send_button"), command=on_send, bg=GOLD, fg=BG_COLOR,
        activebackground=GOLD_LIGHT, relief="flat", font=("Segoe UI", 9, "bold"),
        borderwidth=0, padx=10,
    )
    send_btn.grid(row=0, column=1, padx=(6, 0))
    entry.bind("<Return>", on_send)

    def toggle_language():
        global _language
        _language = "tr" if _language == "en" else "en"
        win.title(i18n.get(_language, "window_title"))
        send_btn.config(text=i18n.get(_language, "send_button"))
        lang_btn.config(text=i18n.get(_language, "lang_toggle"))
        credits_var.set(_render_credits(*_state.get("credits", ("loading", None))))

    win.bind("<Escape>", lambda event: _close_popup())
    win.protocol("WM_DELETE_WINDOW", _close_popup)

    # A Toplevel created from a background-thread mainloop (triggered by a
    # global hook) can render blank on Windows until it's forced to repaint
    # and take focus.
    win.update_idletasks()
    win.deiconify()
    win.lift()
    win.attributes("-topmost", True)
    win.focus_force()
    entry.focus_set()


HOTKEY = "<ctrl>+<f1>"


def _on_hotkey():
    if _state["root"] is not None:
        _state["root"].after(0, _open_popup)


def start_ai_assistant():
    """Starts the global Ctrl+F1 hotkey listener and this module's own Tk UI thread."""
    if _state["listener"] is not None:
        return  # already running

    ready = threading.Event()

    def ui_thread():
        root = tk.Tk()
        root.withdraw()
        _state["root"] = root
        ready.set()
        root.mainloop()

    threading.Thread(target=ui_thread, daemon=True).start()
    ready.wait()

    listener = keyboard.GlobalHotKeys({HOTKEY: _on_hotkey})
    listener.daemon = True
    listener.start()
    _state["listener"] = listener


def stop_ai_assistant():
    listener = _state["listener"]
    if listener is not None:
        listener.stop()
        _state["listener"] = None

    root = _state["root"]
    if root is not None:
        root.after(0, root.quit)
        _state["root"] = None
