# Zyraena

<img src="assets/Zyraena.png" alt="Zyraena" width="260" align="right">

A Windows desktop assistant that can act on your PC. Press **Ctrl+F1** to open her chat
window, or talk to her from your phone over **Telegram**. She can manage files, launch apps
and games, control Opera GX and YouTube, run Python scripts, set reminders, shut the PC
down on a schedule, look at the screen and talk back by voice. Every action that changes
something on your PC asks for your confirmation first.

Zyraena has two modes: **assistant** (a neutral assistant) and **lady** (the in-character
persona from `personality.md`). Both run on [OpenRouter](https://openrouter.ai), so any
model there can be used.

<br clear="right">

## Features

| Area | What she can do |
|---|---|
| Files | List, search, read, create, write, move and delete (to the Recycle Bin) files in the allowed folders, open them with their default app; tidy Downloads into Images / Documents / Code / ... subfolders with one confirmation (nothing deleted or overwritten) |
| Apps & games | Find and launch installed apps and Steam games; list open apps and close them (normally or forced); list running processes and end one by PID, like Task Manager |
| Browser | Open sites in Opera GX (new tab, or starts Opera), find a site by name via web search, search YouTube and open a result by number, fullscreen / mute / close tab, loop the current video and set its own volume in percent (needs the extension below) |
| Media | Play/pause/next via media keys (works for YouTube, Spotify, ...), set the system volume |
| Python & dev | Run a `.py` file in the background (uses the project's virtualenv if there is one) and report the output when it finishes, optionally in a visible window; open a terminal or a folder in VS Code |
| Power | Shut down / restart now, in N minutes or when a script finishes (always with a 60 s warning you can cancel); lock the PC; show CPU/RAM/disk status |
| Steam | List installed games by size or last played; uninstall one |
| Health | Watches GPU temperature, RAM, CPU load and free disk space; past a limit (see `.env.example`) she warns you with a popup and on Telegram, with buttons to end the program causing it or leave it. Telegram reminders every minute from minute 3; with no answer by minute 10 and the value still bad, she ends that program herself. A full disk is only reported |
| Reminders | "Remind me at 9 tomorrow…", repeating alarms, turn alarms on/off; alarms also go to Telegram when you're away from the PC |
| Screen | Take a screenshot to check the result of an action, or send it to you on Telegram |
| Sleep mode | "Finish this, I'm going to sleep": after one confirmation, Claude Code does the job alone in `Documents\Projects` / `Documents\Work` (if a first attempt fails it investigates and finds its own way). Every project folder is copied to `Documents\Failsafe` before its first change; at the end a detailed report (what changed, what was done and why) is sent on Telegram and saved in the changed folders, then the PC shuts down |
| WhatsApp | Send a file from the PC to a phone number from your own account through WhatsApp Desktop ("send the CV in Downloads to +44 7700 900123 on WhatsApp"); you see a screenshot of the ready chat and it's sent only after you confirm. No contact list is stored |
| Web & memory | Web search (Tavily), search past conversations |
| Voice | Talk with the 🎤 button and she answers out loud; send Telegram voice notes (she confirms what she understood before acting) |
| Claude Code | Hand a bigger job (e.g. code changes) to a headless [Claude Code](https://claude.com/claude-code) session with `/c` |
| Credits | See your remaining OpenRouter credit and roughly how many messages it covers |

## Requirements

- Windows 10/11
- Python 3.12+ (developed on 3.13)
- An [OpenRouter](https://openrouter.ai/settings/keys) API key and a [Tavily](https://app.tavily.com) API key
- Optional: Opera GX, Steam, VS Code, Claude Code, a Telegram bot (see below)
- Optional, for looping videos and setting their volume: load `extensions/video-loop` in Opera GX once
  (`opera://extensions` → Developer mode → Load unpacked). It only acts on the current tab
  when its shortcuts (Alt+Shift+L loop, Alt+Shift+V volume) are pressed.
- Optional, for sending files on WhatsApp: WhatsApp Desktop, logged in.

## Setup

```powershell
git clone https://github.com/<you>/Zyraena.git
cd Zyraena
python -m pip install -r requirements.txt

copy .env.example .env                       # then fill in OPENROUTER_API_KEY and TAVILY_API_KEY
copy personality.example.md personality.md   # optional: the persona for "lady" mode
copy config.example.json config.json         # optional: example alarms (reminders create it anyway)
```

Optionally put your own picture at `assets/user.jpg` to show it next to your messages.

## Run

```powershell
python main.py
```

Zyraena runs in the background. **Ctrl+F1** opens or closes the chat window.

### Build the exe

```powershell
python -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File build.ps1
```

This creates `dist\Zyraena.exe`. Put your `.env` (and optionally `personality.md`,
`config.json`) next to the exe; chat logs and script logs are written there too. To start
Zyraena with Windows, put a shortcut to the exe in `shell:startup`.

## Commands

Most things are asked in plain language, in Turkish or English, for example:

```
Opera GX'te YouTube'u aç
lofi hip hop ara        →  3'ü aç  →  tam ekran yap
Masaüstündeki rapor.pdf'i İndirilenler'e taşı
C:\Users\me\Documents\Projects\demo\train.py'yi çalıştır, bitince PC'yi kapat
2 saat sonra PC'yi kapat
Yarın 9'da annemi aramamı hatırlat
En çok yer kaplayan Steam oyunlarım?
Ekranda ne var, video durdu mu?
```

### Chat window (PC)

| Input | What it does |
|---|---|
| **Ctrl+F1** | Open / close the window (Esc also closes it) |
| 🎤 | Press to start listening, press ⏹ to stop; she answers out loud |
| TR / EN | Switch the window's language |
| `/mode` | Show the current mode and model |
| `/mode assistant`, `/mode lady` | Switch mode; the conversation continues |

### Telegram

| Command | What it does |
|---|---|
| any message | Goes to Zyraena when no Claude Code session is waiting for an answer |
| `/z <message>` | Always goes to Zyraena (`/h` also works) |
| reply to her message | Goes to Zyraena |
| voice note | Transcribed; she asks "is this what you meant?" with Yes/No buttons before acting |
| `/mode`, `/mode assistant`, `/mode lady` | Same as in the window |
| `/c <task>` | Hands the task to Claude Code and sends back its result |
| `/yeni` (`/new`) | Starts a fresh conversation (also resets the Claude Code session) |
| `/iptal` (`/cancel`) | Cancels a planned or counting-down shutdown immediately |
| `/ss` (`/ekran`) | Sends a screenshot |
| `/kredi` (`/credits`) | Remaining OpenRouter credit |
| `/status` | Shows waiting Claude Code sessions and whether Zyraena is listening |

Confirmations arrive as ✅ Yes / ❌ No buttons; no answer within 10 minutes counts as No.

## Telegram

Zyraena doesn't talk to Telegram directly: she shares a bot with **claude_comm**, a small
standard-library tool that lets Claude Code sessions ask you questions on Telegram. Only one
program may poll a bot at a time, so Zyraena polls through claude_comm's router: messages
that belong to a waiting Claude Code session go there, everything else goes to her. Set
`CLAUDE_COMM_PATH` in `.env` to your `claude_comm.py`; without it the Telegram features are
simply off.

## Configuration

All settings live in `.env`; see [.env.example](.env.example) for the full list with
comments. The most useful ones:

| Setting | Default | Meaning |
|---|---|---|
| `OPENROUTER_API_KEY`, `TAVILY_API_KEY` | – | Required keys |
| `ZYRAENA_USER_NAME` | `You` | Your name in the chat window |
| `ZYRAENA_DEFAULT_MODE` | `assistant` | Mode new chats start in |
| `OPENROUTER_ASSISTANT_MODEL`, `OPENROUTER_LADY_MODEL` | Gemini Flash, Claude Haiku | Model per mode |
| `ZYRAENA_ALLOWED_DIRS` | Desktop;Downloads;Documents | The only folders she may touch |
| `CLAUDE_COMM_PATH` | – | Enables Telegram |
| `ZYRAENA_TTS_MODEL`, `ZYRAENA_TTS_VOICE` | `openai/gpt-audio-mini`, `shimmer` | Spoken replies |

Older `HANNAH_*` setting names (the project's former name) are still accepted.

## Safety

- File tools only work inside `ZYRAENA_ALLOWED_DIRS`; deleted files go to the Recycle Bin
  (uninstalling a Steam game is permanent).
- Creating, changing, moving, deleting, running, closing, uninstalling and shutting down are
  always confirmed (a dialog on the PC, buttons on Telegram).
- Shutdowns are forced (unsaved work is lost) and always preceded by a 60-second warning that
  `/iptal` or "cancel the shutdown" stops.
- Screenshots are sent to the model only when she uses `look_at_screen`, and dropped from the
  conversation right after.
- `/c` runs Claude Code in `acceptEdits` mode: it can edit files but can't run shell commands
  that aren't already allowed in your Claude Code settings.
- `/c` works in `Documents\Projects` (`CLAUDE_CODE_CWD`) and may also use `Documents\Work`
  (`CLAUDE_CODE_EXTRA_DIRS`).
- Ending a process asks first and never touches Windows, security software, other users'
  processes or Zyraena herself.
- The one thing she does without asking: when a health alarm got no answer for 10 minutes
  and the value is still past its limit, she ends the process using most of it (same
  protections as above). Set `ZYRAENA_HEALTH=off` to turn this off.
- Sleep mode is the other exception to "she asks first": you confirm once when it starts. Claude
  Code then runs in `auto` permission mode (no questions, but a safety check still blocks
  destructive or out-of-scope actions; commands can't be strictly fenced into a folder on
  Windows). The `sleep_hook.ps1` hook copies each project folder to `Documents\Failsafe` before
  anything in it changes and blocks the change if the copy fails; `.venv`, `venv`,
  `node_modules` and `__pycache__` aren't copied (rebuild them from `requirements.txt`).
  Copies of folders that end up unchanged are deleted. The Telegram bridge folder and `.env`
  files are off-limits. To undo a night's work, copy the folder back from `Failsafe`. The health
  monitor always runs during sleep mode (even with `ZYRAENA_HEALTH=off`): an overheating job is
  ended like any other program. Claude is told not to message you on Telegram while you sleep.
- WhatsApp: files go only to a number you give with its country code (no guessing, no stored
  contacts), only from the allowed folders, never secrets (`.env`, keys, `.ssh`...), and only
  after you confirm the number and a screenshot of the ready chat. It drives the official WhatsApp Desktop app (no unofficial API that could get
  the number banned), so it needs an unlocked PC, and it uses the clipboard to attach the file.

## Project layout

| File | Purpose |
|---|---|
| `main.py` | Entry point: reminder loop, chat window, Telegram listener |
| `ai_assistant.py` | Chat window, modes, OpenRouter requests, tool loop |
| `pc_tools.py` | Files and app launching (+ confirmation channels) |
| `browser_tools.py` | Opera GX and YouTube |
| `system_tools.py` | Closing apps, Python runs, terminal, VS Code, shutdown, PC status |
| `health_monitor.py` | Background health checks, alarms and their escalation |
| `steam_tools.py` | Installed Steam games |
| `whatsapp_tools.py` | Sending files through WhatsApp Desktop |
| `sleep_mode.py`, `sleep_hook.ps1` | Sleep mode: backups, the unattended Claude Code job, report, shutdown |
| `screen_tools.py`, `media_tools.py` | Screenshots; media keys and volume |
| `reminder_tools.py`, `config_loader.py`, `check_event.py`, `alert.py` | Alarms and reminders |
| `telegram_listener.py` | Telegram via claude_comm |
| `claude_bridge.py` | `/c` → headless Claude Code |
| `voice.py`, `voice_worker.py` | Speech-to-text, text-to-speech, optional RVC voice conversion |
| `i18n.py` | UI texts (English / Turkish) |
| `paths.py` | App/resource folders and `.env` loading |
