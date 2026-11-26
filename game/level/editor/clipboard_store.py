"""
clipboard_store.py
==================
The level editor's copy buffer, kept outside any one level so what you copy in one level can be pasted into another.

It is held in memory for as long as the game runs (opening another level's editor keeps it) and also written to
editor_clipboard.json next to the other save files, so it survives closing the game too. A read or write problem
never stops the editor: the clipboard simply stays in memory.
"""

import copy
import json

from ...scripts import paths

_FILE = "editor_clipboard.json"
_memory = None            # None = not read from disk yet


def _path():
    return paths.save_file(_FILE)


def load():
    """The saved clipboard (a list of world entries, possibly empty)."""
    global _memory
    if _memory is None:
        _memory = []
        try:
            with open(_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                _memory = [d for d in data if isinstance(d, dict) and "x" in d and "y" in d]
        except (OSError, ValueError):
            pass
    return copy.deepcopy(_memory)


def save(items):
    """Remember ``items`` (world entries) for the next level / session. An empty list is ignored so a stray
    Ctrl+C with nothing selected does not wipe what was copied before."""
    global _memory
    if not items:
        return False
    _memory = copy.deepcopy(items)
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(_memory, f)
    except (OSError, TypeError, ValueError) as exc:
        print(f"[editor clipboard] could not write {_FILE}: {exc}")
    return True
