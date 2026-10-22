"""The wake phrase: saying "Zyraena açıl" opens the chat window and starts listening.

The microphone is read on the CPU (~4.5% of one core with Windows' audio engine, measured on the
Ryzen AI 7 350). A plain loudness detector cuts out short bits of speech (MIN_SPEECH to MAX_SPEECH
seconds; the phrase takes ~1-1.5 s), and only those go to the local Whisper that voice_guard keeps
loaded, ~0.3 s on the GPU each. Nothing is ever sent to OpenRouter from here.

On only while voice_guard is in "ready" (mains power, no game, the GPU calm): on battery or when
a game shows up the microphone is closed at once. Paused while Zyraena speaks or 🎤 records, so
she doesn't wake herself. ZYRAENA_WAKE=off turns it off.
"""
import collections
import difflib
import io
import os
import queue
import re
import threading
import time
from datetime import datetime

import numpy as np
import soundfile as sf

import paths
import voice

RATE = 16000
BLOCK = 1024                 # 64 ms
MIN_SPEECH = 0.4             # seconds of sound in a bit worth hearing
MAX_SPEECH = 3.5             # longer: someone is talking, not calling her
END_SILENCE = 0.5            # quiet this long ends a bit
PRE_ROLL = 0.25              # kept from before the sound started (the first syllable is quiet)
# How Whisper has written her name in the owner's 🎤 messages so far, too ("Alena, bugün ne..."):
NAMES = ("zyraena", "zirayena", "ziraena", "zirena", "zayrena", "zyrena", "zarine", "zerrin", "alena")
NAME_SIMILARITY = 0.75
COOLDOWN_SECONDS = 3         # after waking, or after she spoke
# No blocks from the microphone this long: the stream died without telling (2026-10-20: Windows showed
# the session inactive, nothing logged, never reopened). voice_guard's next check reopens it.
STALE_SECONDS = 10


def _setting_on():
    return os.environ.get("ZYRAENA_WAKE", "").strip().lower() != "off"


def _words(text):
    text = text.replace("I", "ı").replace("İ", "i").lower()
    return re.sub(r"[^\w\s]", " ", text).split()


def _log(text):
    """voice_home/wake.log: on/off, and each bit heard (its text only if it looks like the phrase:
    what is said in the room otherwise isn't kept)."""
    try:
        with open(paths.voice_home() / "wake.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")
    except OSError:
        pass


def _looks_like_it(text):
    words = _words(text)
    return any(w.startswith(("aç", "ac")) or max(difflib.SequenceMatcher(None, w, n).ratio() for n in NAMES) >= 0.6
               for w in words)


def _name_then(text, starts):
    """Her name (as Whisper may spell it) followed within two words by a word starting with `starts`."""
    words = _words(text)
    for i, word in enumerate(words):
        if max(difflib.SequenceMatcher(None, word, name).ratio() for name in NAMES) >= NAME_SIMILARITY:
            if any(w.startswith(starts) for w in words[i + 1:i + 3]):
                return True
    return False


def heard_wake(text):
    """Whisper's text holds the wake phrase: her name and right after it a word starting with "aç"
    ("açıl", "aç", also "acil": Whisper drops the cedilla at times)."""
    return _name_then(text, ("aç", "ac"))


def heard_close(text):
    """ "Zyraena kapat" (or "kapan"): voice_session.py ends the conversation on it, sending nothing."""
    return _name_then(text, ("kapa",))


class Segmenter:
    """Cuts short bits of speech out of the microphone's blocks by loudness. Pure: no audio device."""

    BACKGROUND_SECONDS = 5.0
    LOUDER = 2.5     # than the background: a voice close to the microphone
    FLOOR = 0.0015   # this microphone is quiet: a quiet room 0.0005, speech from the speakers 0.001-0.008

    def __init__(self, rate=RATE, block=BLOCK):
        self.block_seconds = block / rate
        # The room's level: the 30th percentile of the last few seconds, so a video playing in the
        # background raises it and only speech clearly louder than that (the owner, close by) counts.
        self._levels = collections.deque(maxlen=round(self.BACKGROUND_SECONDS / self.block_seconds))
        self.noise = 1e-3
        self._pre = []          # the last PRE_ROLL seconds of quiet blocks
        self._bit = None        # blocks of the bit being heard
        self._too_long = False
        self._quiet = 0
        self._loud = 0

    def threshold(self):
        return max(self.LOUDER * self.noise, self.FLOOR)

    def feed(self, block):
        """Returns a finished bit (float32 array) worth hearing, or None."""
        rms = float(np.sqrt(np.mean(block ** 2))) + 1e-9
        loud = rms > self.threshold()
        # The level is frozen while a bit is heard (else a long sound turns into "background" and ends
        # the bit with a pause that isn't there), but follows again once it is too long to be the phrase.
        if self._bit is None or self._too_long:
            self._levels.append(rms)
            if len(self._levels) >= self._levels.maxlen // 2:
                self.noise = float(np.percentile(self._levels, 30))
        if len(self._levels) < self._levels.maxlen // 2:
            return None  # just started listening: learning the room first
        if self._bit is None:
            self._pre = (self._pre + [block])[-max(1, round(PRE_ROLL / self.block_seconds)):]
            self._loud = self._loud + 1 if loud else 0
            if self._loud >= 2:  # 128 ms: not a click
                self._bit, self._quiet = list(self._pre), 0
            return None
        self._quiet = 0 if loud else self._quiet + 1
        if not self._too_long:
            self._bit.append(block)
            if len(self._bit) * self.block_seconds > MAX_SPEECH + END_SILENCE + PRE_ROLL:
                self._bit, self._too_long = [], True  # someone talking: drop it all until a pause
        if self._quiet * self.block_seconds < END_SILENCE:
            return None
        bit, too_long = self._bit, self._too_long
        self._bit, self._too_long, self._loud, self._pre = None, False, 0, []
        seconds = (len(bit) - self._quiet) * self.block_seconds - PRE_ROLL
        return np.concatenate(bit) if not too_long and MIN_SPEECH <= seconds <= MAX_SPEECH else None


def _wav_bytes(audio):
    out = io.BytesIO()
    sf.write(out, audio, RATE, format="WAV", subtype="PCM_16")
    return out.getvalue()


class WakeListener:
    """Listens for the wake phrase while enabled; on_wake() is called (from a background thread)."""

    def __init__(self, on_wake, paused=lambda: False, transcribe=None):
        self.on_wake = on_wake
        self.paused = paused          # e.g. 🎤 is recording
        self._transcribe = transcribe or voice.local_stt.transcribe
        self._stream = None
        self._lock = threading.Lock()
        self._bits = queue.Queue(maxsize=2)  # more than that: drop, Whisper is still busy
        self._segmenter = Segmenter()
        self._quiet_until = 0.0
        self._last_audio = 0.0
        self._callback_failed = False
        threading.Thread(target=self._hear, daemon=True).start()

    def enabled(self):
        return self._stream is not None

    def _dead(self):
        """The open stream stopped giving audio (a device hiccup, or PortAudio ended it)."""
        stream = self._stream
        return stream is not None and (not getattr(stream, "active", True)
                                       or time.monotonic() - self._last_audio > STALE_SECONDS)

    def set_enabled(self, on):
        """Opens or closes the microphone (safe to call every few seconds); reopens it if it died."""
        on = on and _setting_on()
        with self._lock:
            if on and self._dead():
                _log("the microphone stopped giving audio: reopening it")
                self._close()
            if on and self._stream is None:
                import sounddevice

                self._segmenter = Segmenter()
                self._last_audio = time.monotonic()
                stream = sounddevice.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK,
                                                 callback=self._on_audio)
                stream.start()
                self._stream = stream
                _log("listening")
            elif not on and self._stream is not None:
                self._close()
                _log("off (battery, a game, or not ready)")

    def _close(self):
        stream, self._stream = self._stream, None
        try:
            stream.abort()
            stream.close()
        except Exception as e:  # a dead device may refuse; the stream is dropped anyway
            _log(f"closing the microphone: {type(e).__name__}: {e}")

    def _busy(self):
        if voice.speaking() or self.paused():
            self._quiet_until = time.monotonic() + COOLDOWN_SECONDS
            return True
        return time.monotonic() < self._quiet_until

    def _on_audio(self, data, frames, when, status):
        self._last_audio = time.monotonic()
        try:  # an exception here would make PortAudio end the stream without a word
            bit = self._segmenter.feed(data[:, 0].copy())
            if bit is not None and not self._busy():
                self._bits.put_nowait(bit)
        except queue.Full:
            pass
        except Exception as e:
            if not self._callback_failed:
                self._callback_failed = True
                _log(f"microphone block failed: {type(e).__name__}: {e}")

    def _hear(self):
        while True:
            bit = self._bits.get()
            # only the model voice_guard keeps loaded: never load it (or anything paid) for this
            if not self.enabled() or self._busy():
                continue
            if not (voice.stt_on() and voice.local_stt.loaded()):
                _log(f"{len(bit) / RATE:.1f} s bit skipped: the local Whisper isn't loaded")
                continue
            started = time.monotonic()
            try:
                text = self._transcribe(_wav_bytes(bit)) or ""
            except Exception as e:
                _log(f"couldn't hear: {e}")
                continue
            woke = heard_wake(text) and self.enabled() and not self._busy()
            _log(f"{len(bit) / RATE:.1f} s bit, heard in {time.monotonic() - started:.2f} s"
                 + (f": {text!r}" if _looks_like_it(text) else "") + (" -> WAKE" if woke else ""))
            if woke:
                self._quiet_until = time.monotonic() + COOLDOWN_SECONDS
                try:
                    self.on_wake()
                except Exception as e:
                    print(f"Wake: couldn't open: {e}")


_listener = {"it": None}


def room_level():
    """The room's loudness the listener has learned (voice_session.py starts from it), or None."""
    it = _listener["it"]
    if it is None or not it.enabled() or len(it._segmenter._levels) < it._segmenter._levels.maxlen // 2:
        return None
    return it._segmenter.noise


def start(on_wake, paused=lambda: False):
    """Creates the listener and hands it to voice_guard, which turns it on and off (main.py)."""
    import voice_guard

    if _listener["it"] is None:
        _listener["it"] = WakeListener(on_wake, paused)
        voice_guard.listeners.append(lambda mode, suspect: _listener["it"].set_enabled(mode == "ready" and not suspect))
