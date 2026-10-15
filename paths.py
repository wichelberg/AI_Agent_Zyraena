import os
import sys
from pathlib import Path

LEGACY_ENV_PREFIX = "HANNAH_"  # the app's former name; old .env files keep working
ENV_PREFIX = "ZYRAENA_"


def app_dir() -> Path:
    """Directory the exe lives in when frozen, else this project's directory.

    Used for user-editable/persistent files (config.json, .env, chat_logs)
    so they survive next to the exe instead of PyInstaller's temp extraction dir.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    """Directory holding bundled read-only assets (images, sounds).

    PyInstaller (onefile) extracts --add-data assets into sys._MEIPASS at
    runtime, not next to the exe, so bundled assets must be read from there.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return Path(__file__).resolve().parent


# Keys that came from Zyraena's .env (not from the real environment). They're Zyraena's settings,
# so programs she starts (Claude Code) don't get them: e.g. an ANTHROPIC_API_KEY there would make
# Claude Code bill that key instead of the user's own login.
ENV_FILE_KEYS = set()


def load_env(path=None):
    """Loads KEY=VALUE lines from .env next to the app into os.environ (real
    environment variables win). Runs when this module is first imported, so
    every module that reads settings at import time already sees them."""
    path = Path(path or app_dir() / ".env")
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key not in os.environ:
                os.environ[key] = value.strip()
                ENV_FILE_KEYS.add(key)
    for key, value in list(os.environ.items()):
        if key.startswith(LEGACY_ENV_PREFIX):
            os.environ.setdefault(ENV_PREFIX + key[len(LEGACY_ENV_PREFIX):], value)


load_env()
