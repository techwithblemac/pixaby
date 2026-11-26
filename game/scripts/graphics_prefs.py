"""
graphics_prefs.py
=================
The atmosphere switches (Game Settings -> GRAPHICS): lighting, shadows, fireflies.

They are remembered in graphics.json next to the game, like the screen mode (display.json).
settings.py reads them once at start (``saved``); the Graphics window calls ``save`` after a change.
Must not import ``settings`` at import time (settings imports this module).
"""

import json

from . import paths

KEYS = ("LIGHTING", "SHADOWS", "FIREFLIES")
_FILE = "graphics.json"


def _read():
    try:
        with open(paths.save_file(_FILE), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def saved(key, default):
    """The remembered value of one switch, or ``default`` when there is no (valid) file."""
    value = _read().get(key)
    return value if isinstance(value, bool) else default


def save():
    """Write the current Settings values. A failed write never crashes the game."""
    from ..settings import Settings
    try:
        with open(paths.save_file(_FILE), "w", encoding="utf-8") as f:
            json.dump({k: bool(getattr(Settings, k, False)) for k in KEYS}, f)
    except OSError:
        pass
