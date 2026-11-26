"""
progress.py
===========
The campaign save: how far the player has got, and how many times they have
crawled the whole descent again (New Game+).

    progress.json  ->  {"highest_cleared": 4, "ng_plus": 0}

Only the *story* folder counts. Co-op levels, the player's own worlds and the
test maps never touch this file.

It is written when a story level is won (one small write, never per frame) and
lives in paths.save_dir(). Any file error is
swallowed: a broken save must never crash a run, it just forgets progress.
"""

import json
import os

from ..scripts import paths

SAVE_NAME = "progress.json"

# New Game+: every loop adds this much to enemy health and damage, on top of the
# normal per-floor scaling in data/difficulty.py.  1 loop = x1.5, 2 loops = x2.0 ...
NG_PLUS_STEP = 0.5


class Progress:
    def __init__(self, path=None):
        self.path = path or paths.save_file(SAVE_NAME)
        self.highest_cleared = 0
        self.ng_plus = 0
        self.load()

    # ---------------- persistence ---------------- #
    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.highest_cleared = max(0, int(data.get("highest_cleared", 0)))
            self.ng_plus = max(0, int(data.get("ng_plus", 0)))
        except (OSError, ValueError, TypeError, AttributeError):
            self.highest_cleared = 0
            self.ng_plus = 0

    def save(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"highest_cleared": self.highest_cleared, "ng_plus": self.ng_plus}, fh, indent=2)
            os.replace(tmp, self.path)       # atomic: a crash mid-write cannot corrupt the save
            return True
        except OSError:
            return False

    # ---------------- story progress ---------------- #
    def record_clear(self, level):
        """A story level was won. Returns True if this moved the save forward."""
        try:
            level = int(level)
        except (TypeError, ValueError):
            return False
        if level <= self.highest_cleared:
            return False
        self.highest_cleared = level
        self.save()
        return True

    def is_unlocked(self, level):
        """A story level is open if it is beaten, it is the next one, or the game has been finished."""
        try:
            level = int(level)
        except (TypeError, ValueError):
            return False
        return self.ng_plus > 0 or level <= self.highest_cleared + 1

    # ---------------- New Game+ ---------------- #
    def start_new_game_plus(self):
        self.ng_plus += 1
        self.save()
        return self.ng_plus

    def enemy_multiplier(self):
        """Health and damage multiplier for story enemies at the current loop."""
        return 1.0 + NG_PLUS_STEP * self.ng_plus


_progress = None


def get():
    """The one shared Progress (created on first use)."""
    global _progress
    if _progress is None:
        _progress = Progress()
    return _progress


def reload():
    """Drop the cached copy and read the file again (tests, and after a manual edit)."""
    global _progress
    _progress = None
    return get()
