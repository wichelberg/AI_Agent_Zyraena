"""Keeps Zyraena's voice models ready without getting in a game's way. The PC's health comes first.

Every CHECK_SECONDS (BATTERY_CHECK_SECONDS on battery) it reads the NVIDIA GPU (nvidia-smi) and picks a mode:
- game: something else keeps the GPU busy (>= ZYRAENA_TTS_GPU_BUSY %, default 40, twice in a row),
  the GPU is at ZYRAENA_HEALTH_GPU_TEMP (default 87 °C) or hotter, or its memory is 95% full.
  While our own models work (loading, answering, 5 s after) the load counts as ours, unless the VRAM
  beyond our models (OTHERS_GAME_MB) shows a big program too. Models load off the guard's thread, so
  readings go on while they load. Whisper, Chatterbox and the voice pack stop at once, even half
  loaded, and nothing local runs (the owner types
  during games): replies stay as text, and a voice note that still comes in goes to OpenRouter.
- ready: the GPU has been calm for a while (30 s after Zyraena starts, 2 minutes after a game),
  is cool, has room for the models, and the PC is on mains power. Whisper and Chatterbox are
  loaded ahead and kept loaded, so a spoken reply starts fast; the voice pack (on the GPU) loads
  when 🎤 is pressed (RVC_GPU_MB). Only in this mode does wake.py listen for "Zyraena açıl" (it is
  told through `listeners`, and closes the microphone at the first busy reading).
- idle: on battery, or ZYRAENA_VOICE_PRELOAD=off. Nothing is loaded ahead; models load when
  needed and unload after their idle time (a loaded model keeps a laptop's NVIDIA GPU awake).

Measured on the RTX 5070 Laptop: loaded but idle models changed neither power (11.3 W vs 11.4 W),
temperature nor clocks; what they cost is ~5 GB of VRAM, which a game may need (it then stutters).
Mode changes are written to voice_home/voice_guard.log.
"""
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime

import psutil

import paths
import voice

CHECK_SECONDS = 5             # on mains power: a game is noticed in ~10 s
BATTERY_CHECK_SECONDS = 30    # nvidia-smi wakes a sleeping laptop GPU: rarely on battery
BUSY_HITS = 2                 # readings in a row
FIRST_CALM_SECONDS = 30       # after Zyraena starts
CALM_SECONDS = 2 * 60         # after a game
MEMORY_FULL = 0.95            # share of VRAM: step aside
MEMORY_ROOM = 0.90            # load only if the models fit under this share
COOL_MARGIN = 5               # °C below the temperature limit to load again
NEED_MB = {"stt": 1300, "tts": 2900}  # what each loaded model takes (measured: 1.22 GB, 2.73 GB with T3 in bf16)
# The voice pack on the GPU (measured: up to ~2 GB). Not loaded ahead, so only ~4 GB stay loaded while
# the owner isn't talking; with all three the 8 GB card is ~81% full (measured 6.58 GB; 93.7% before
# Chatterbox's T3 went to bf16). It loads when 🎤 is pressed (~3 s, while the owner talks) and unloads
# after ZYRAENA_RVC_IDLE_MINUTES (default 3). If the VRAM gets full while it is on the GPU, it moves to
# the CPU before anything else (_make_room).
RVC_GPU_MB = 2100
# VRAM used by others (all of it minus our models) that means a big program: the desktop, browser and
# overlays take 0.5-1.2 GB here (measured in voice_guard.log), a game 3 GB and more.
OTHERS_GAME_MB = 2500


@dataclass
class Reading:
    util: float      # %
    mem_used: float  # MiB
    mem_total: float
    temp: float      # °C


@dataclass
class State:
    mode: str = "idle"
    hits: int = 0
    calm_since: float = None
    calm_needed: float = FIRST_CALM_SECONDS


def _setting(name, default):
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def step(state, reading, now, plugged, ours_busy, ours_mb, preload=True):
    """The mode for this reading (pure: no GPU, no workers). ours_busy: a model is working right now,
    so the GPU load is partly ours; ours_mb: VRAM our loaded models take."""
    if reading is None:  # no nvidia-smi: nothing to judge by
        return state.mode
    busy_limit = _setting("ZYRAENA_TTS_GPU_BUSY", 40)
    temp_limit = _setting("ZYRAENA_HEALTH_GPU_TEMP", 87)
    # While a model of ours works the load is taken as ours, unless the VRAM beyond our models shows
    # another big program (a game starting while ours load): then it counts all the same.
    ours_only = ours_busy and reading.mem_used - ours_mb < OTHERS_GAME_MB
    others_busy = busy_limit > 0 and not ours_only and reading.util >= busy_limit
    state.hits = state.hits + 1 if others_busy else 0
    if state.hits >= BUSY_HITS or reading.temp >= temp_limit or reading.mem_used >= MEMORY_FULL * reading.mem_total:
        if state.mode != "game":
            state.calm_needed = CALM_SECONDS
        state.mode, state.calm_since = "game", None
        return state.mode

    room = MEMORY_ROOM * reading.mem_total - (reading.mem_used - ours_mb)
    calm = not others_busy and reading.temp < temp_limit - COOL_MARGIN and room >= sum(NEED_MB.values())
    if not calm:
        state.calm_since = None
    else:
        state.calm_since = state.calm_since if state.calm_since is not None else now
        if now - state.calm_since >= state.calm_needed:
            state.mode = "ready" if plugged and preload else "idle"
    if state.mode == "ready" and not (plugged and preload):
        state.mode = "idle"
    return state.mode


# --- the running guard ----------------------------------------------------------------------

_state = State()
_started = {"on": False}
# Called with (mode, suspect) after every reading; suspect: one busy reading already, a game may be
# starting (wake.py closes the microphone then, without waiting for the second one).
listeners = []


def _read_gpu():
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
        util, used, total, temp = (float(v) for v in out.splitlines()[0].split(","))
        return Reading(util, used, total, temp)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _plugged():
    battery = psutil.sensors_battery()
    return battery is None or bool(battery.power_plugged)


def _rvc_on_gpu():
    return voice.voice_pack.loaded() and voice.voice_pack.device == "gpu"


def _make_room(reading):
    """VRAM full while the voice pack is on the GPU: it goes to the CPU first (frees ~2 GB at once,
    and it is the cheapest to bring back). Returns the reading to judge by."""
    if reading is None or reading.mem_used < MEMORY_FULL * reading.mem_total or not _rvc_on_gpu():
        return reading
    voice.voice_pack.off_the_gpu()
    _log(f"VRAM full: voice pack moved to the CPU for {voice.VoicePack.CPU_MINUTES} min ({reading})")
    return _read_gpu() or reading


def _ours_mb():
    rvc_on_gpu = _rvc_on_gpu()
    return ((NEED_MB["stt"] if voice.local_stt.loaded() else 0) + (NEED_MB["tts"] if voice.local_tts.loaded() else 0)
            + (RVC_GPU_MB if rvc_on_gpu else 0))


def _log(text):
    try:
        with open(paths.voice_home() / "voice_guard.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")
    except OSError:
        pass


def apply(mode):
    """Puts the workers in line with `mode`."""
    voice.gaming["on"] = mode == "game"
    keep = mode == "ready"
    voice.local_stt.keep_loaded = voice.local_tts.keep_loaded = keep
    if mode == "game":  # at once, even one still loading: the game comes first
        voice.local_tts.stop(at_once=True)
        voice.local_stt.stop(at_once=True)
        voice.voice_pack.stop(at_once=True)
    elif voice.voice_pack.stale():  # on the CPU after a full VRAM: it restarts on the GPU when needed
        voice.voice_pack.stop()
    elif mode == "ready":
        for worker, on in ((voice.local_stt, voice.stt_on()), (voice.local_tts, voice.tts_on())):
            if on and not worker.loaded() and not worker.busy():
                _in_background(worker.start)


def _in_background(load):
    """Loads a model off the guard's thread: a cold load takes up to minutes (2026-10-20, a game
    starting meanwhile: 2 min 20 s), and the guard must keep reading the GPU every few seconds."""
    def run():
        try:
            load()
        except Exception as e:  # stopped for a game, or broken: the next "ready" reading tries again
            _log(f"loading failed: {type(e).__name__}: {e}")
    threading.Thread(target=run, daemon=True).start()


def _loop():
    preload = os.environ.get("ZYRAENA_VOICE_PRELOAD", "").strip().lower() != "off"
    while True:
        plugged = True
        try:
            before = _state.mode
            reading = _make_room(_read_gpu())
            plugged = _plugged()
            mode = step(_state, reading, time.monotonic(), plugged, voice.workers_busy(), _ours_mb(), preload)
            if mode != before:
                _log(f"{before} -> {mode} ({reading})")
            apply(mode)
            for listener in listeners:
                listener(mode, _state.hits > 0)
        except Exception as e:  # never let the guard die: the voice would stay as it is
            _log(f"error: {type(e).__name__}: {e}")
        time.sleep(CHECK_SECONDS if plugged else BATTERY_CHECK_SECONDS)


def start():
    """Starts guarding in the background (main.py). Does nothing twice."""
    if _started["on"]:
        return
    _started["on"] = True
    threading.Thread(target=_loop, daemon=True).start()
