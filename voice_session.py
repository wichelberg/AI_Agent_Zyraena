"""A spoken conversation: "Zyraena açıl" (wake.py) starts it, the light goes up around the screen
(glow.py), she listens, answers aloud, and listens again, until "Zyraena kapat" or IDLE_SECONDS
with nothing said. The pet thinks while the answer comes and talks while she speaks.

Credits are only spent on what the owner said: "Zyraena kapat" is recognized here and ends it at
once, sending nothing; a turn with no speech in it (SilenceCut), or sound that never pauses for
LONGEST seconds (a video, not someone talking to her), is never sent; speech is transcribed only
by the local Whisper (no paid fallback here). If her voice can't say the answer, it goes to
Telegram as text. voice_guard ends the conversation on battery or when a game shows up.
"""
import threading
import time
from datetime import datetime

import voice

IDLE_SECONDS = 30      # with nothing said (the owner's choice), counted from the end of her last answer
LONGEST = 15.0         # one turn: longer without a pause is not someone talking to her
AFTER_SPEECH = 0.3     # before listening again: the speakers' tail


class Session:
    def __init__(self, answer, new_chat, transcribe, notify, activity, glow, log_dir, ended=None):
        self._answer, self._new_chat, self._transcribe = answer, new_chat, transcribe
        self._notify, self._activity, self._glow, self._log_dir = notify, activity, glow, log_dir
        self._ended = ended or (lambda chat: None)  # the finished conversation (relationship.chat_ended)
        self._chat = None
        self._lock = threading.Lock()
        self._on = False
        self._turn = 0
        self._recorder = None
        self.state = "off"
        self._floor = None
        self._last_speech = 0.0
        self._log_path = None

    def active(self):
        return self._on

    def _current(self, turn):
        return self._on and self._turn == turn

    def level(self):
        """For the light: her voice while she speaks, the microphone while listening."""
        if self.state == "speaking":
            return voice.level()
        recorder = self._recorder
        return recorder.level() if self.state == "listening" and recorder is not None else 0.0

    def start(self, floor=None):
        """floor: the room's level the wake listener learned (so a video in the background isn't speech)."""
        with self._lock:
            if self._on:
                return
            self._on = True
            self._turn += 1
            turn = self._turn
        self._chat = self._new_chat()
        self._floor = floor
        self._last_speech = time.monotonic()
        self._log_path = self._log_dir / f"{datetime.now():%Y-%m-%d_%H-%M-%S}_voice.txt"
        voice.warm_up()  # the voice pack loads (~3 s) while the owner says the first thing
        self._glow.show(self.level, "listen")
        self._listen(turn)

    def close(self, why=""):
        with self._lock:
            if not self._on:
                return
            self._on = False
            self._turn += 1
            recorder, self._recorder = self._recorder, None
        self.state = "off"
        if recorder is not None:
            try:
                recorder.stop()
            except Exception:
                pass
        voice.stop_playing()
        self._glow.hide()
        self._activity(None)
        self._log("—", f"(closed: {why})")
        try:
            self._ended(self._chat)
        except Exception as e:
            print(f"Voice: after the conversation: {e!r}")

    def _log(self, who, text):
        if self._log_path is None:
            return
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(f"{who}: {text}\n")
        except OSError:
            pass

    def _set(self, state, glow_mode, activity):
        self.state = state
        self._glow.set_mode(glow_mode)
        self._activity(activity)

    def _listen(self, turn):
        if not self._current(turn):
            return
        self._set("listening", "listen", "listen")
        try:
            recorder = voice.Recorder(on_silence=lambda: self._heard(turn), floor=self._floor, longest=LONGEST)
        except Exception as e:
            self._log("—", f"(microphone failed: {e})")
            self.close("microphone")
            return
        with self._lock:
            if self._current(turn):
                self._recorder = recorder
                return
        recorder.stop()

    def _idle_or_listen(self, turn):
        if time.monotonic() - self._last_speech >= IDLE_SECONDS:
            self.close("nothing said")
        else:
            self._listen(turn)

    def _heard(self, turn):
        with self._lock:
            recorder, self._recorder = self._recorder, None
        if recorder is None or not self._current(turn):
            return
        audio = recorder.stop()
        cut = recorder.cut
        self._floor = cut.floor()
        if not audio or not cut.spoke or cut.ran_out:
            return self._idle_or_listen(turn)  # nobody talked to her: nothing to send
        self._set("thinking", "think", "think")
        try:
            text = (self._transcribe(audio) or "").strip()
        except Exception as e:
            self._log("—", f"(couldn't hear: {e})")
            text = ""
        if not self._current(turn):
            return
        if not text:
            return self._idle_or_listen(turn)
        import wake  # (wake imports voice_guard; imported late to keep this module light)

        if wake.heard_close(text):
            self._log("🎤", text)
            return self.close("Zyraena kapat")
        self._last_speech = time.monotonic()
        self._log("🎤", text)
        answer = self._answer(self._chat, text + voice.SPOKEN_HINT)
        if not self._current(turn):
            return
        self._log("Zyraena", answer)
        self._set("speaking", "speak", "talk")
        voice.speak(answer, on_error=lambda e: self._not_said(answer, e), on_done=lambda: self._spoken(turn))

    def _spoken(self, turn):
        if not self._current(turn):
            return
        self._last_speech = time.monotonic()
        time.sleep(AFTER_SPEECH)
        self._listen(turn)

    def _not_said(self, answer, error):
        self._log("—", f"(not said aloud: {error}; sent to Telegram)")
        try:
            self._notify(answer)
        except Exception:
            pass


_session = {"it": None}


def _local_transcribe(wav_bytes):
    """Only the local Whisper: an empty answer rather than a paid one."""
    if not (voice.stt_on() and voice.local_stt.loaded()):
        return ""
    return voice.local_stt.transcribe(wav_bytes) or ""


def setup(answer, new_chat, notify, activity, log_dir, ended=None):
    """Creates the session (main.py); voice_guard ends it on battery or in a game."""
    import glow
    import voice_guard

    if _session["it"] is None:
        _session["it"] = Session(answer, new_chat, _local_transcribe, notify, activity, glow, log_dir, ended)
        voice_guard.listeners.append(
            lambda mode, suspect: _session["it"].close("battery, a game, or the GPU busy")
            if (mode != "ready" or suspect) and _session["it"].active() else None)
    return _session["it"]


def start():
    """Thread-safe (wake.py heard "Zyraena açıl")."""
    import wake

    if _session["it"] is not None:
        threading.Thread(target=_session["it"].start, args=(wake.room_level(),), daemon=True).start()


def active():
    return _session["it"] is not None and _session["it"].active()
