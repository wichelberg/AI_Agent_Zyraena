import threading
import tkinter as tk
from datetime import datetime

import ai_assistant
import alert
import check_event
import config_loader
import desktop_pet
import disk_actions
import disk_watch
import health_monitor
import i18n
import pc_tools
import relationship
import telegram_listener
import voice_guard
import voice_session
import wake
import web_control

RELOAD_INTERVAL_SECONDS = 1 * 60


def sync_events(running, raw_events):
    now = datetime.now()
    seen_names = set()

    for raw_event in raw_events:
        name = raw_event["name"]
        seen_names.add(name)
        existing = running.get(name)

        if existing is not None and existing["raw"] == raw_event:
            continue

        if existing is not None:
            print(f"Config changed for '{name}', restarting.")
            existing["stop_event"].set()

        config = config_loader.parse_event(raw_event, now)
        stop_event = threading.Event()
        thread = threading.Thread(target=check_event.is_event, args=(config, stop_event), daemon=True)
        running[name] = {"raw": raw_event, "stop_event": stop_event, "thread": thread}
        thread.start()

    for name in list(running.keys()):
        if name not in seen_names:
            print(f"Event '{name}' removed from config, stopping.")
            running.pop(name)["stop_event"].set()


def supervisor_loop():
    running = {}

    while True:
        try:
            raw_events = config_loader.load_raw_events()
        except Exception as e:
            print(f"Failed to load config: {e}")
        else:
            sync_events(running, raw_events)

        config_loader.wait_for_reload(RELOAD_INTERVAL_SECONDS)


def _extension_problem(text):
    """The Web Control extension can't work (web_control.watch): said by the pet and sent on Telegram."""
    print(f"Web control: {text}")
    desktop_pet.say("🧩 " + text, seconds=20)
    pc_tools.fallback_notify("🧩 " + text)


def _clean_mei():
    """Deletes the Temp\\_MEI folders force-closed Zyraena exes left behind (disk_actions.clean_mei)."""
    try:
        removed, kept = disk_actions.clean_mei()
    except Exception as e:
        print(f"_MEI clean-up failed: {e}")
        return
    if removed or kept:
        print(f"_MEI clean-up: {len(removed)} deleted, {len(kept)} still in use")


def _disk_findings(found):
    """The daily disk scan found something new: one bubble, a click opens the Disk tab."""
    print("Disk: " + "; ".join(f.text for f in found))
    desktop_pet.say(i18n.get(ai_assistant.current_language(), "disk_findings"), seconds=30,
                    on_click=ai_assistant.open_disk_panel)


def main():
    threading.Thread(target=_clean_mei, daemon=True).start()
    threading.Thread(target=supervisor_loop, daemon=True).start()
    ai_assistant.start_ai_assistant()
    desktop_pet.start(on_click=ai_assistant.toggle_chat_box, language=ai_assistant.current_language)
    telegram_listener.start()
    health_monitor.start()
    voice_guard.start()
    voice_session.setup(answer=lambda chat, text: ai_assistant.answer_message(chat, text, source="voice"),
                        new_chat=ai_assistant.new_chat,
                        notify=lambda text: pc_tools.fallback_notify(text),  # Telegram, once it's connected
                        activity=desktop_pet.activity, log_dir=ai_assistant.CHAT_LOG_DIR,
                        ended=lambda chat: relationship.chat_ended(chat, "voice"))
    wake.start(on_wake=voice_session.start, paused=voice_session.active)
    web_control.start()
    web_control.watch(notify=_extension_problem, lang=ai_assistant.current_language)
    disk_watch.configure(ask=ai_assistant.ask_flash, notify=_disk_findings, lang=ai_assistant.current_language)
    disk_watch.start()
    try:
        ai_assistant.start_user_care(notify=lambda text: pc_tools.fallback_notify(text))  # after Telegram
    except Exception as e:  # breaks and reminders must not take the app down
        print(f"User care couldn't start: {e!r}")

    root = tk.Tk()
    root.withdraw()
    alert.init(root)
    root.mainloop()


if __name__ == "__main__":
    main()
