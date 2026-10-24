# Zyraena

<img src="assets/Zyraena.png" alt="Zyraena" width="260" align="right">

A Windows desktop assistant that can act on your PC. Say **"Zyraena açıl"** to talk to her, click
her on the desktop to write to her, or use **Telegram** from your phone. **Ctrl+F1** opens a small panel
(show/hide her, live OpenRouter and Tavily credit). She can manage files, launch apps
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
| Browser | Open sites in Opera GX (new tab, or starts Opera), find a site by name via web search, search YouTube and open a result by number |
| Web control | With the Zyraena Web Control extension: list, open, close and switch Opera GX tabs, read a page, click, type, download (with Opera's own logins) and upload a file from the PC. Every step, reading included, is asked first on the PC and on Telegram at once; the first answer counts. The video in a tab (loop on/off, its own volume in percent, mute) goes through it too, without asking, and the answer says the video's state; fullscreen is YouTube's own `f` key. If Opera can't run the extension (not loaded, its folder moved, an old copy, not connecting), she tells you on the PC and on Telegram |
| Media | Play/pause/next via media keys (works for YouTube, Spotify, ...), set the system volume |
| Python & dev | Run a `.py` file in the background (uses the project's virtualenv if there is one) and report the output when it finishes, optionally in a visible window; open a terminal or a folder in VS Code |
| Power | Shut down / restart now, in N minutes or when a script finishes (always with a 60 s warning you can cancel); lock the PC; show CPU/RAM/disk status |
| Steam | List installed games by size or last played; uninstall one |
| Health | Watches GPU temperature, RAM, CPU load and free disk space; past a limit (see `.env.example`) she warns you with a popup and on Telegram, with buttons to end the program causing it or leave it. Telegram reminders every minute from minute 3; with no answer by minute 10 and the value still bad, she ends that program herself. A full disk is only reported |
| Reminders | "Remind me at 9 tomorrow…", repeating alarms, turn alarms on/off; alarms also go to Telegram when you're away from the PC |
| Screen | Take a screenshot to check the result of an action, or send it to you on Telegram |
| Sleep mode | "Finish this, I'm going to sleep": after one confirmation, Claude Code does the job alone in `Documents\Projects` / `Documents\Work` (if a first attempt fails it investigates and finds its own way). Every project folder is copied to `Documents\Failsafe` before its first change; at the end a detailed report (what changed, what was done and why) is sent on Telegram and saved in the changed folders, then the PC shuts down |
| WhatsApp | Everything goes through the WhatsApp Desktop app (no browser, no WhatsApp Web): list your chats, read a chat's latest messages (who, when, links, which ones are photos/videos/documents), opening it by name first if needed; send a file to a phone number or to a chat by name ("send the CV in Downloads to +44 7700 900123 on WhatsApp", "Annem'e bu fotoğrafı at"). You see a screenshot of the ready chat and it's sent only after you confirm. Reading is asked first on the PC and on Telegram at once. No contact list is stored |
| Web & memory | Web search (Tavily), search past conversations |
| Voice | Say "Zyraena açıl" and talk; she answers out loud and keeps listening until "Zyraena kapat", with a light around the screen moving with her voice; send Telegram voice notes (she confirms what she understood before acting) |
| Claude Code | Hand a bigger job (e.g. code changes) to a headless [Claude Code](https://claude.com/claude-code) session with `/c` |
| Credits | See your remaining OpenRouter credit and roughly how many messages it covers; the Ctrl+F1 panel shows the OpenRouter and Tavily credit live, and its "API credit log" button opens the Credits tab: every paid request (text box, Telegram, voice chat, cloud speech-to-text, disk scan) with what it was for, model, tokens, tools called, the cost OpenRouter reported, the balance before and after and their difference (OpenRouter shows a new balance about a minute late), plus totals for today / 7 / 30 days and by source. Stored in `%LOCALAPPDATA%\Zyraena\credit_log.sqlite` |
| User Care | Breaks, water and sleep, with her mood toward you as a layer on her persona (see [User Care](#user-care)): a break prompt every hour of active use, snoozes allowed by her mood, then a fullscreen forced break; water every hour; sleep warnings after midnight; at 03:00 she asks why you're still up and shuts the PC down step by step without a good reason (dry run until you turn it on); a summary of yesterday every morning. The Ctrl+F1 panel's Care tab shows it all and switches the protection rules |
| Disk | The Ctrl+F1 panel's Disk tab shows what takes the space on C: as items (Steam games, programs, Pythons and venvs, caches, HuggingFace models, projects, your folders, unknown big folders) with size, last use and its source, what it is, whether it can be downloaded again and what depends on it; delete goes the way the kind is meant to (Steam, the uninstaller, `pip cache purge`, Recycle Bin…) after a confirm listing what breaks. Once a day an idle scan runs and the pet says "Disk: new findings" past the `ZYRAENA_DISK_*` limits. At start she deletes the `_MEI` folders force-closed exes left in Temp. Memory and history live in `%LOCALAPPDATA%\Zyraena\disk` (`knowledge.json` can be edited by hand) |
| Desktop | A realistic, full-body Zyraena lives above the taskbar: most of the time she sits cross-legged on her throne in the bottom-right corner, now and then she gets up, walks around, turns toward you and says something, then goes back. While a fullscreen game or video is in front she leans on the screen edge and watches it, and clicks go through her. She can be picked up and dropped; click her to open the chat, right-click for a menu |

## Requirements

- Windows 10/11
- Python 3.12+ (developed on 3.13)
- An [OpenRouter](https://openrouter.ai/settings/keys) API key and a [Tavily](https://app.tavily.com) API key
- Optional: Opera GX, Steam, VS Code, Claude Code, a Telegram bot (see below)
- Optional, for WhatsApp: [WhatsApp Desktop](https://www.whatsapp.com/download) from the Microsoft Store,
  logged in. Zyraena reads it through Windows UI Automation (`comtypes`); if a WhatsApp update
  breaks reading, `python whatsapp_tools.py --dump` writes what she sees of its window.
- Optional, for browser control and the video in a tab (loop, volume, mute): load the Zyraena Web
  Control extension (its own project, `Documents\Projects\Web_ControlExtention`) in Opera GX once
  (`opera://extensions` → Developer mode → Load unpacked). The extension connects to Zyraena on
  `127.0.0.1:47821`; she only accepts that extension, and asks you before every step (except the video
  controls). Opera loads an unpacked extension from its folder every time: if the folder moves, remove
  the extension in `opera://extensions` and load it from the new place (Zyraena notices and tells you).
  After updating its files, press the reload button on its card (she tells you if Opera runs an old copy).

## Setup

```powershell
git clone https://github.com/<you>/Zyraena.git
cd Zyraena
python -m pip install -r requirements.txt

copy .env.example .env                       # then fill in OPENROUTER_API_KEY and TAVILY_API_KEY
copy i18n.example.py i18n.py                 # required: UI text and her lines by mood (edit them there)
copy personality.example.md personality.md   # optional: the persona for "lady" mode
copy config.example.json config.json         # optional: example alarms (reminders create it anyway)
```

Optionally put your own picture at `assets/user.jpg` to show it next to your messages.

## Run

```powershell
python main.py
```

Zyraena runs in the background, on the desktop as the pet. A click on her opens or closes the
text box beside her; **Ctrl+F1** opens or closes the panel in the middle of the screen; "Zyraena
açıl" starts a spoken conversation.

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

### On the PC

| Input | What it does |
|---|---|
| "Zyraena açıl" | A spoken conversation: the light goes up around the screen, she listens, answers out loud and listens again. Only on mains power with no game running |
| "Zyraena kapat" | Ends it at once; nothing is sent to a model. 30 s with nothing said ends it too |
| Click on the pet | Opens / closes the text box beside her (Esc also closes it). Her answer shows in the box, silently, while she thinks and then talks |
| **Ctrl+F1** | Opens / closes the panel in the middle of the screen, in the same neon look: a button to hide or show the pet (the way back after "Hide" in her menu), and the live OpenRouter and Tavily credit, fetched when it opens ("yükleniyor…" until then, a short error if it fails). Esc also closes it |
| `/mode` | Show the current mode and model |
| `/mode assistant`, `/mode lady` | Switch mode; the conversation continues |

Before she changes something on the PC, a small yes/no box in the same neon look asks first
(beside the pet). Every conversation is written to `chat_logs\` (spoken ones as `*_voice.txt`).

### Telegram

| Command | What it does |
|---|---|
| any message | Goes to Zyraena when no Claude Code session is waiting for an answer |
| `/z <message>` | Always goes to Zyraena (`/h` also works) |
| reply to her message | Goes to Zyraena |
| voice note | Transcribed; she asks "is this what you meant?" with Yes/No buttons before acting (a Yes also keeps the clip for voice training) |
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

## Local speech-to-text

What you say (in a spoken conversation and in Telegram voice notes) is transcribed on this PC by
[faster-whisper](https://github.com/SYSTRAN/faster-whisper), free and in well under a second
on the GPU. It runs in its own small Python (`voice_env`) next to Zyraena, so the exe stays
small: voice_env only holds faster-whisper and ctranslate2 and borrows the rest (numpy,
onnxruntime, tokenizers, and the CUDA libraries that ship with torch) from an existing venv
that has torch, by default Wichelberg's training venv, which it never changes. Set it up once:

```powershell
python setup_voice_env.py            # creates voice_env, downloads the model (~1.6 GB), checks it loads
python setup_voice_env.py --test some_voice_note.ogg
```

Everything goes to `%LOCALAPPDATA%\Zyraena\voice` (`ZYRAENA_VOICE_HOME`). Without voice_env,
or if the local model fails or hears nothing, transcription falls back to OpenRouter as before.
Audio longer than 30 s (long voice notes) is first cut at pauses and the pieces are
transcribed separately, so no words get lost where Whisper's 30 s windows meet. The model is
loaded on first use (or ahead by voice_guard) and unloaded after 10 idle minutes.

The default model is [RsGoksel_ITU_Mainframe-ct2](https://huggingface.co/RsGoksel/RsGoksel_ITU_Mainframe-ct2),
Whisper large-v3-turbo fine-tuned for Turkish (MIT; it often writes lowercase without punctuation).
Measured on an RTX 5070 Laptop with 71 Common Voice Turkish test clips (sentences without
numbers, since Whisper writes numbers as digits):

| Model | Word error rate | Time for a ~4 s clip | VRAM |
|---|---|---|---|
| Turkish turbo (default) | 5.0% | 0.36 s | 1.2 GB |
| `large-v3-turbo` | 6.8% | 0.35 s | 1.2 GB |
| `large-v3` | 6.2% | 0.82 s | 2.1 GB |
| Gemini Flash on OpenRouter (before) | 3.8% | 4.5 s | – |

### Training data for your voice

To later fine-tune Whisper on your own voice, Zyraena keeps clips whose text you confirmed:
a Telegram voice note you answered **Yes** to. To collect more at once, read sentences aloud:

```powershell
python voice_recorder.py             # Space: record/stop · D: play back · Enter: keep, next · S: skip
```

It shows ~230 Turkish sentences (`voice_sentences_tr.txt`: commands, everyday talk,
numbers and dates, English tech words), skips the ones you already recorded and warns
when a take is too quiet or clips. Clips go to `%LOCALAPPDATA%\Zyraena\voice\data`
(`clips\*.flac` + `samples.jsonl`), never into the repo. `ZYRAENA_VOICE_DATA=off` keeps nothing.

### Fine-tuning on your voice

`train_stt.py` trains a LoRA on top of the Turkish model (its trainable
[Hugging Face weights](https://huggingface.co/RsGoksel/RsGoksel_ITU_Mainframe), downloaded
once, ~1.6 GB) with those clips. It runs in `train_env`, made the same way as voice_env
(it adds only peft, accelerate and ctranslate2's converter):

```powershell
python setup_voice_env.py --training
%LOCALAPPDATA%\Zyraena\voice\train_env\Scripts\python.exe train_stt.py --cv 200 --cv-test 60
```

Longer recordings work too: read the sections of `voice_reading_tr.txt` aloud (~2 minutes
each) with any recorder, on the PC and on the phone, and drop the files into `UserVoice\`
named `<section>_<device>.<ext>` (`1_pc.m4a`, `1_telefon.m4a`, ...; m4a and other formats are
decoded with ffmpeg). The last section is never trained on: it scores each device separately.

It holds back ~15% of your sentences as a test, scores the model on them before and after
training, then merges and converts the tuned model into `voice\models\<name>` and prints the
`ZYRAENA_STT_MODEL=<name>` line that switches Zyraena to it (nothing changes until you add it
to `.env`). Clips longer than Whisper's 30 s are cut at quiet moments and their text is shared
out over the pieces. `--cv N` mixes Common Voice clips in so it doesn't unlearn other voices,
`--cv-test N` checks that. On the RTX 5070 Laptop, 200 clips take ~1.5 minutes per epoch and
~2.7 GB of VRAM. Every number and test transcript lands in `voice\training\<name>\report.json`.

First run (2026-10-18, `--cv 200 --cv-test 60 --epochs 6 --accumulate 2`, 19.5 minutes of
reading on two devices, 11 minutes of training), scored through Zyraena's own runtime on
section 6, which it never trained on:

| | Base | Tuned |
|---|---|---|
| Your voice, PC recorder | 8.0% | 7.1% |
| Your voice, phone recorder | 15.8% | 12.8% |
| Other voices (Common Voice, short clips, numbers aside) | 4.8% | 6.0% |

## Spoken replies

Spoken replies are read by Chatterbox Multilingual (`tts_worker.py` in `voice\tts_env`) and turned
into Zyraena's voice by the RVC voice pack (`voice_worker.py` in Wichelberg's Python). Both run as
a pipeline: while one sentence goes through the voice pack, Chatterbox already reads the next.
The first piece is cut short (at its first comma, or after ~7 words) so the first sound comes
early, and no piece is more than 1.5x as long as the one before (cut at commas), so each is ready
before the one before has been played. Both workers make one warm-up run before they say they're
ready (the first sentence after loading was 1-5 s slower). The voice pack runs on the GPU through
DirectML, but only because its output was measured to be the same as the CPU's by Wichelberg's
parity rule (`voice\rvc_parity.json`: checked once per GPU, ONNX Runtime version and voice pack; a
GPU that fails is never used). During a game (`voice_guard`) nothing is said and nothing local
runs: the reply stays as text, as it does when the GPU is busy; speech is never sent to a paid
service. Audio longer than 8 s goes to the CPU, since DirectML's memory grows with the longest input (+1.8 GB at
6 s, +6.4 GB at 30 s). Chatterbox's token model (T3) runs in bfloat16: 1 GB less, same speed, Whisper heard it as well
(WER 5.4% vs 9.0% in fp32 on 20 sentences). With Whisper (1.2 GB), Chatterbox (2.7 GB) and the voice
pack (up to 2 GB) loaded the 8 GB card is ~81% full (93.7% before), so the voice pack loads only when a conversation starts, unloads after 3 idle minutes, and is the
first to move to the CPU (for 10 minutes) if the VRAM gets full. `voice\speech.log` gets one line
per spoken reply: how fast it started, the gaps, where the voice pack ran.

Measured on the RTX 5070 Laptop, GPU otherwise idle, models warm, 3 replies of 3-4 sentences × 2:

| | First sound (median) | Gaps between sentences (total, 12-16 joins) | Time / audio length |
|---|---|---|---|
| One sentence after another, voice pack on CPU | 6.65 s | 10.2 s | 1.58 |
| Overlapped | 6.49 s | 0.7 s | 1.47 |
| + short first piece | 4.93 s | 7.2 s | 1.39 |
| + voice pack on GPU | 2.9 s | 0.9-2.6 s | 1.2 |
| Installed app, one real 🎤 reply (before the 1.5x rule) | 4.35 s | 3.1 s (one long piece) | – |

What's left is Chatterbox itself: ~2.5 s for even 3-4 words (its token loop runs at ~19 ms per
token, and how long it makes a piece varies from run to run), so the piece after a short first one
is sometimes not ready in time (a pause of up to ~1.5 s after the first comma). With other GPU users
(e.g. Wallpaper Engine) the first sound was measured at 3.2-4.7 s.

## Wake phrase

Saying **"Zyraena açıl"** starts a spoken conversation (`voice_session.py`): the light around the
screen comes up (`glow.py`), she listens until you've finished (1.2 s of quiet), answers out loud,
and listens again until **"Zyraena kapat"** (recognized locally: nothing is sent) or 30 s with
nothing said. Turns with no speech in them, or sound that never pauses for 15 s (a video, not you),
are never sent to a model, and speech is transcribed only by the local Whisper here. The pet
thinks while the answer comes and talks while she speaks.

The light is one rounded frame round the whole screen (no seams at the corners), purple to cyan
plasma wisps that rise and fall with her voice and yours, drawn at full resolution and ~55-60 fps
(measured on the Ryzen AI 7 350: ~0.65-0.8 of one CPU core, only while a conversation is on; the
frame is worked out on an unrolled strip and mapped onto the four screen edges).

`wake.py` reads the
microphone on the CPU (~4.5% of one core with Windows' audio engine, measured), cuts out short bits
of speech by loudness (0.4-3.5 s, clearly louder than the room: a video playing in the background
becomes the room's level), and hands only those to the local Whisper that `voice_guard` keeps
loaded (~0.3 s on the GPU each). Nothing goes to OpenRouter. It runs only in `voice_guard`'s
"ready" mode: on battery or as soon as a game shows up the microphone is closed. It doesn't listen
while Zyraena speaks or a conversation is on. `voice\wake.log` shows when it listened and every bit it
heard (what was said only if it sounded like the phrase).

On battery, measured on the RTX 5070 Laptop: idle 26.0 W, with Whisper loaded 26.6 W, with Whisper
and the microphone listening 26.2 W (±1.5 W): no measurable difference, because other apps keep the
NVIDIA GPU awake anyway. If the GPU could sleep, a loaded Whisper would keep it awake (it idles at
~10-13 W in P2), which is why it is off on battery.

## Desktop pet frames

The frames in `assets/pet` are rendered from a 3D model that `pet/blender/zyraena_real.py`
builds entirely from code; her body, colors, armor and poses come from
`pet/blender/zyraena_real_params.json`. To change her look and render new frames you need
(all free):

- [Blender](https://www.blender.org) 5.2
- the [MPFB](https://extensions.blender.org/add-ons/mpfb/) extension (MakeHuman for Blender)
- the CC0 [makehuman system assets](https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html)
  pack, unzipped into MPFB's user data folder (`extensions\.user\user_default\mpfb\data` inside
  Blender's config folder)

```powershell
blender -b -P pet/blender/zyraena_real.py -- --params pet/blender/zyraena_real_params.json `
    --out pet/renders/real --views front,threequarter,side,face --sprites assets/pet
```

`--views` writes preview images (and the `.blend` file) to `--out`; `--sprites` renders every
pet animation: walk, turn, idle, talk, drag, sitdown, sit, leanin, lean, codein, code, watchin, watch,
liftin, lift, stretchin, stretch, daggerin, dagger and the throne (`--only lean,leanin` renders just those).

What she does follows what is open on her monitor: the throne only on the bare desktop, a
holographic screen and keyboard to code along with you when an editor (VS Code and the like)
is on top (with a stretch now and then), watching the screen, curling a dumbbell, spinning her
dagger or stretching with any other window, and leaning on
the screen edge while a fullscreen game or video runs.

## User Care

Zyraena looks after you. It isn't a second persona: her mood toward you (0-100, starts at 50) and the
last five events with their reasons go into the lady persona's system prompt with every message, e.g.
`[mood: 24/100, sinirli, son olaylar: 02:40 uyku uyarısı (-10); ...]`, and she reacts in character,
brings up the reasons and makes peace when you apologize (the `care_make_peace` tool, +5, at most every
2 hours and twice a day). However low her mood, she still does what you ask; late at night a low mood is
worry, not anger. The assistant mode stays neutral. Happy is 70 and up, angry 30 and down; she drifts
back toward 50 by 1 point an hour. The points are rough on purpose: good habits barely lift
her mood, slips cost a lot.

| What | Rule (all numbers in `config.json`, `user_care`) | Mood |
|---|---|---|
| Break prompt | Every 60 min of active use: "Mola ver" / "Ertele" | +2 / -15 |
| Unanswered | 5 min without an answer while you use the PC counts as a snooze (just being away doesn't) | -20 |
| Forced break | When the snoozes in a row run out (happy 2, normal 1, angry 0): "save" 2 min before, then a fullscreen 10 min countdown with no close button. Nothing blocks the keyboard or mouse; the emergency exit needs a written reason she remembers | +5 done / -30 exit |
| Break over | A Telegram message in her voice | |
| Water | Every 60 min of active use: "İçtim" / "Sonra" (back in 15 min) | +1 / -3 |
| Away | 5 min without input stops the timers (not while a fullscreen video plays); 10 min away, or the PC sleeping, counts as a break | 0 |
| Night | 00:00-06:00: a sleep warning every hour | -15 |
| 03:00 | She opens the text box and asks why you're up; Gemini Flash sorts the answer: work / exam / emergency (accepted twice a week: warnings stop tonight), can't sleep (gentle, never shuts down), no reason (or no answer in 10 min): step-by-step shutdown | |
| Shutdown | "Save" 5 min before (2 when angry), a countdown, the last 60 s fullscreen; cancel with a reason in the window, `/iptal` on Telegram or `shutdown /a` | -30 cancel |
| Bedtime | The last input before a 4 h gap starting after 22:00 is when you went to bed; before 03:00 gives a bonus the next day | +10 |
| Morning | The first activity after 06:00: yesterday in the text box (bedtime, breaks given / snoozed / forced, water, emergency exits with their reasons) | |

**Protection list.** While one of these holds, User Care never shuts the PC down; a forced break comes
instead (breaks and reminders go on either way). It only guards User Care's own shutdown: one you ask
for and sleep mode's are not affected. Every rule can be switched on the Care tab; "Protection
settings…" edits the lists and limits.

| Rule | Holds when |
|---|---|
| Programs | `claude.exe` (Claude Code), `blender.exe`, `Unity.exe`, `VideoEditorPlus.exe` (Movavi), `rsession.exe` (RStudio), `yt-dlp.exe` is running |
| GPU | The GPU is past 80% for 3 min and the load is on the compute/cuda engine (training), not 3d (a game); her own voice workers don't count |
| Terminal job | Something started from a terminal (PowerShell, cmd, VS Code's terminal) used CPU for 3 min; an idle terminal doesn't count |
| Training | A Python command line contains one of the training patterns (Wichelberg's `data\egitim`, `RNNModel`, `Voice_Changer_Production`, `train_stt.py`) |
| Zyraena's scripts | A script she runs with `run_python` hasn't finished |
| Busy CPU | A background process (not the one in front, not Windows) used over 40% of the CPU for 5 min |
| Downloads | A `.crdownload` / `.opdownload` / `.part` file in Downloads grew in the last 2 min, or over 5 MB/s came in for 3 min |

**Dry run.** `"dry_run": true` (the default) runs every step but never calls `shutdown.exe`; the log and
Telegram say what would have happened. Set it to `false` in `config.json` for real shutdowns.

**Debug.** `py -3 user_care.py --debug --at 02:58 --active 178 --mood 25 --speed 30` runs User Care
alone on a fake clock (30 times faster here), with its own state file (fresh each run; `--keep` goes on
from the last one), never shutting down and without Telegram (add `--telegram` to send). `--active 178` is the "third hour" case: two snoozes used, two
minutes to go. The Care tab opens with buttons to move the clock (+10 min, +1 h, 02:59, 23:59, 06:01),
fake being away or asleep, and change the mood.

State and history: `%LOCALAPPDATA%\Zyraena\care` (`state.json`, `events.jsonl`; the debug run uses
`state_debug.json`, `events_debug.jsonl`; `ZYRAENA_CARE_HOME` moves it).

## Configuration

All settings live in `.env`; see [.env.example](.env.example) for the full list with
comments. The most useful ones:

| Setting | Default | Meaning |
|---|---|---|
| `OPENROUTER_API_KEY`, `TAVILY_API_KEY` | – | Required keys |
| `ZYRAENA_LANGUAGE` | `tr` | Language of the text box, the yes/no box and the pet's lines (`tr` or `en`) |
| `ZYRAENA_USER_NAME` | `You` | Your name in the text box and the chat logs |
| `ZYRAENA_DEFAULT_MODE` | `assistant` | Mode new chats start in |
| `OPENROUTER_ASSISTANT_MODEL`, `OPENROUTER_LADY_MODEL` | Gemini Flash, Claude Haiku | Model per mode |
| `ZYRAENA_ALLOWED_DIRS` | Desktop;Downloads;Documents | The only folders she may touch |
| `CLAUDE_COMM_PATH` | – | Enables Telegram |
| `ZYRAENA_STT` | `local` | Speech-to-text: `local` (Whisper, falls back to OpenRouter) or `openrouter` |
| `ZYRAENA_STT_MODEL`, `ZYRAENA_STT_LANGUAGE` | Turkish turbo, `tr` | Local Whisper model and language (`auto` detects it); run `setup_voice_env.py` after changing the model |
| `ZYRAENA_STT_IDLE_MINUTES` | `10` | Unload the local model after this long unused (0 = keep it) |
| `ZYRAENA_VOICE_DATA` | `on` | Keep confirmed voice clips for training (`off` = keep nothing) |
| `ZYRAENA_TTS` | `local` | Spoken replies, only on this PC (Chatterbox in `voice\tts_env`, sentence by sentence); when it can't run (a game, a busy GPU) the reply stays as text, nothing is ever paid for. `off` = no spoken replies |
| `ZYRAENA_VOICE_PACK` | – | RVC voice pack that turns the spoken reply into Zyraena's voice (a folder, or a name in Wichelberg's library, e.g. `zyraena`) |
| `ZYRAENA_RVC_DEVICE` | – | `cpu` keeps the voice pack off the GPU (otherwise: GPU through DirectML, CPU during a game) |
| `ZYRAENA_WAKE` | `on` | "Zyraena açıl" starts a spoken conversation (only on mains power, no game); `off` = never |
| `ZYRAENA_RVC_IDLE_MINUTES` | `3` | Unload the voice pack after this long unused (it reloads in ~2 s when a conversation starts) |
| `ZYRAENA_PET`, `ZYRAENA_PET_HEIGHT` | `on`, `340` | The desktop pet and her height in pixels |

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
- User Care's shutdown is dry run until `dry_run` is set to `false`, is always cancellable (the window,
  `/iptal`, `shutdown /a`), and checks the protection list when it starts and again right before the
  end; while it holds, a forced break comes instead. The forced break never blocks input.
- WhatsApp: files go only to a number you give with its country code or a chat you name (no
  guessing, no stored contacts), only from the allowed folders, never secrets (`.env`, keys,
  `.ssh`...), and only after you confirm the chat WhatsApp opened and a screenshot of it. Reading
  messages is asked first (PC + Telegram), and message text is treated as untrusted. It drives the
  official WhatsApp Desktop app (no unofficial API that could get the number banned), so opening a
  chat and sending need an unlocked PC; keys are only pressed while WhatsApp is in front, and the
  file is attached through the clipboard.

## Project layout

| File | Purpose |
|---|---|
| `main.py` | Entry point: reminder loop, pet, text box hotkey, voice, Telegram listener |
| `ai_assistant.py` | Modes, OpenRouter requests, tool loop, the text box's conversation |
| `chat_box.py` | The neon text box beside the pet and the yes/no box |
| `voice_session.py`, `glow.py` | The spoken conversation and the light around the screen |
| `pc_tools.py` | Files and app launching (+ confirmation channels) |
| `browser_tools.py` | Opera GX and YouTube |
| `system_tools.py` | Closing apps, Python runs, terminal, VS Code, shutdown, PC status |
| `health_monitor.py` | Background health checks, alarms and their escalation |
| `user_care.py`, `care_guard.py`, `care_windows.py`, `care_panel.py` | User Care: the rules, mood and state; the protection list; its windows (prompts, breaks, fullscreen); the panel's Care tab |
| `steam_tools.py` | Installed Steam games |
| `whatsapp_tools.py` | WhatsApp Desktop: chat list, reading messages (UI Automation), sending files |
| `web_control.py` | Opera GX through the Zyraena Web Control extension |
| `sleep_mode.py`, `sleep_hook.ps1` | Sleep mode: backups, the unattended Claude Code job, report, shutdown. `python sleep_mode.py start/finish` runs the same mode inside an interactive Claude Code session (with the global hook `~/.claude/hooks/zyraena_sleep_gate.py`) |
| `screen_tools.py`, `media_tools.py` | Screenshots; media keys and volume |
| `reminder_tools.py`, `config_loader.py`, `check_event.py`, `alert.py` | Alarms and reminders |
| `telegram_listener.py` | Telegram via claude_comm |
| `claude_bridge.py` | `/c` → headless Claude Code |
| `wake.py` | The "Zyraena açıl" wake phrase |
| `voice.py`, `voice_worker.py` | Speech-to-text, text-to-speech, optional RVC voice conversion |
| `speech_worker.py`, `setup_voice_env.py` | Local speech-to-text (Whisper in voice_env) and its setup |
| `voice_data.py`, `voice_recorder.py`, `voice_sentences_tr.txt`, `voice_reading_tr.txt` | Your confirmed voice clips for training speech-to-text, the sentence recorder, and longer texts to read into `UserVoice\` |
| `tts_worker.py`, `tts_text.py` | Local text-to-speech (Chatterbox in tts_env) and its Turkish text prep (numbers, names, sentences) |
| `train_stt.py`, `stt_eval.py` | Fine-tuning speech-to-text on your voice (LoRA), and its scoring / long-clip cutting |
| `i18n.py` | UI texts (English / Turkish) |
| `desktop_pet.py` | The desktop pet: layered window, walking, turning, talking, drag and drop, modes by what's open on her screen |
| `pet/blender/zyraena_real.py` | Builds her 3D model and renders the pet's frames into `assets/pet` (see below) |
| `paths.py` | App/resource folders and `.env` loading |
