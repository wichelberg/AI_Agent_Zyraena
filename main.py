import threading
import tkinter as tk
from datetime import datetime

import ai_assistant
import alert
import check_event
import config_loader
import health_monitor
import telegram_listener

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


def main():
    threading.Thread(target=supervisor_loop, daemon=True).start()
    ai_assistant.start_ai_assistant()
    telegram_listener.start()
    health_monitor.start()

    root = tk.Tk()
    root.withdraw()
    alert.init(root)
    root.mainloop()


if __name__ == "__main__":
    main()
