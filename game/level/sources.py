"""
sources.py
==========
Where the level selector gets its levels from. Each tab of the selector is one
*source* with the same small surface:

    source.list()      -> [entry, ...]   cards to show (cheap enough to call on refresh)
    source.load(id)    -> world list     the raw level JSON

so a network source (community server, uploads) can slot in later without the
selector changing. An entry is a plain dict:

    id, folder, meta, objects, stats      what the card and details panel draw
    locked, lock_text                     story progression
    players                               (min, max) for co-op levels

Sources never touch the game. The selector asks, the game loads the chosen
(folder, id) through Level_Loader like it always did.
"""

import json
import os
from collections import namedtuple

from ..scripts import paths
from . import preview
from . import progress


# How the game is being played right now. The selector uses it to lock whole tabs:
#   SOLO   story mode            -> STORY open, every other tab locked
#   SPLIT  split screen (local)  -> story locked, the rest open
#   ONLINE host / join           -> story locked, the rest open
SOLO, SPLIT, ONLINE = "solo", "split", "online"
ONLY_IN_MULTI = "Only open in split screen and online modes"
ONLY_IN_SOLO = "Story levels only open in solo mode"


def play_mode(game):
    """SOLO, SPLIT or ONLINE for ``game`` (the Mode window's three states)."""
    if getattr(game, "MULTIPLAYER", False) and not getattr(game, "_multiplayer_from_selector", False):
        return ONLINE
    if getattr(game, "SPLIT_SCREEN", False):
        return SPLIT
    return SOLO


# What the selector hands back when the player picks a level.
# players is (min, max) for co-op levels and None for everything else.
LevelChoice = namedtuple("LevelChoice", ["folder", "id", "players"], defaults=[None])


# ---------------------------------------------------------------------- #
# shared helpers
# ---------------------------------------------------------------------- #

def level_stats(objects):
    counts = {"objects": len(objects), "blocks": 0, "enemies": 0, "water": 0,
              "platforms": 0, "treasures": 0, "trees": 0, "traps": 0, "weapons": 0}
    for o in objects:
        typ = str(o.get("type", "other"))
        if typ == "block": counts["blocks"] += 1
        elif typ in ("enemy", "spawn_point"): counts["enemies"] += 1
        elif typ == "water": counts["water"] += 1
        elif typ == "moving_platform": counts["platforms"] += 1
        elif typ == "treasure": counts["treasures"] += 1
        elif typ == "tree": counts["trees"] += 1
        elif "trap" in typ: counts["traps"] += 1
        elif "weapon" in typ: counts["weapons"] += 1
    return counts


def difficulty_by_number(n):
    if n <= 2: return "EASY"
    if n <= 5: return "STANDARD"
    if n <= 8: return "HARD"
    return "EXTREME"


_NUMERIC_DIFFICULTY = {1: "EASY", 2: "STANDARD", 3: "STANDARD", 4: "HARD", 5: "EXTREME"}


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def numeric_ids(folder):
    """Every N.json in a level folder, sorted. Anything not named by a number is ignored."""
    directory = paths.folder_dir(folder)
    ids = []
    try:
        names = os.listdir(directory)
    except OSError:
        return ids
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            ids.append(int(name[:-5]))
        except ValueError:
            continue
    return sorted(ids)


def next_id(folder):
    ids = numeric_ids(folder)
    return (max(ids) + 1) if ids else 1


# ---------------------------------------------------------------------- #
# base + folder sources
# ---------------------------------------------------------------------- #

class LevelSource:
    key = "source"
    label = "SOURCE"
    folder = None
    editable = False            # shows the pencil
    can_create = False          # shows NEW +
    can_upload = False          # shows the (coming soon) UPLOAD button
    placeholder = None          # (headline, body) -> a "coming soon" tab with no levels
    archive_label = "ARCHIVE"
    default_subtitle = "OFFICIAL // CORE CAMPAIGN"
    default_mode = "Solo + Local Co-op"
    empty_text = "NOTHING CRAWLED BACK."

    def mode_lock(self, mode):
        """The text to show when this tab is closed in play ``mode`` (SOLO / SPLIT / ONLINE), else None."""
        return None

    def list(self):
        return []

    def load(self, level_id):
        raise NotImplementedError(f"{self.key} cannot load levels yet")


class FolderSource(LevelSource):
    """A folder of N.json files, with an optional metadata.json beside them."""

    official = False

    def __init__(self, unlock_all=False):
        self.unlock_all = unlock_all

    # -- reading -- #
    def load(self, level_id):
        world = read_json(paths.level_file(level_id, self.folder))
        if world is None:
            raise FileNotFoundError(paths.level_file(level_id, self.folder))
        return world

    def _folder_metadata(self):
        return read_json(paths.metadata_file(self.folder), {}) or {}

    def _make_entry(self, level_id, index):
        world = read_json(paths.level_file(level_id, self.folder))
        if not isinstance(world, list):
            return None
        meta = {}
        if world and isinstance(world[0], dict):
            meta = dict(world[0].get("_level_meta", {}))
        # metadata.json only fills what the level's own _level_meta leaves out
        for k, v in (index.get(str(level_id)) or {}).items():
            if k == "difficulty" and "difficulty" not in meta:
                meta["difficulty"] = _NUMERIC_DIFFICULTY.get(v, v) if isinstance(v, int) else v
            else:
                meta.setdefault(k, v)

        objects = [o for o in world if isinstance(o, dict) and o.get("type") not in ("entity settings", preview.TYPE)]
        meta.setdefault("title", f"Level {level_id}")
        meta.setdefault("subtitle", self.default_subtitle)
        meta.setdefault("author", "Unknown")
        meta.setdefault("created", "Not recorded")
        meta.setdefault("updated", "Not recorded")
        meta.setdefault("description", "A PIXEL ABYSS challenge.")
        meta.setdefault("difficulty", difficulty_by_number(level_id))
        meta.setdefault("theme", "Abyss")
        meta.setdefault("tags", [])
        meta.setdefault("estimated_time", "5–10 min")
        meta.setdefault("mode", self.default_mode)
        meta.setdefault("objective", "Descend, survive, and reach the exit.")
        meta.setdefault("official", self.official)
        return {"id": level_id, "folder": self.folder, "meta": meta, "objects": objects,
                "stats": level_stats(objects), "locked": False, "lock_text": "", "players": None,
                "preview": preview.point(world)}

    def list(self):
        index = self._folder_metadata()
        entries = []
        for level_id in numeric_ids(self.folder):
            entry = self._make_entry(level_id, index)
            if entry:
                entries.append(entry)
        self._decorate(entries)
        return entries

    def _decorate(self, entries):
        """Hook for subclasses: lock state, player counts."""


# ---------------------------------------------------------------------- #
# the four tabs (+ the debug one)
# ---------------------------------------------------------------------- #

class StorySource(FolderSource):
    key = "story"
    label = "STORY"
    folder = paths.STORY
    official = True
    archive_label = "THE DESCENT"

    def mode_lock(self, mode):
        return ONLY_IN_SOLO if mode != SOLO else None

    def _decorate(self, entries):
        prog = progress.get()
        previous = None
        for entry in entries:
            open_ = self.unlock_all or prog.is_unlocked(entry["id"])
            entry["locked"] = not open_
            if entry["locked"] and previous is not None:
                entry["lock_text"] = f"Beat {previous['meta']['title']} to unlock"
            elif entry["locked"]:
                entry["lock_text"] = "Locked"
            previous = entry

    def last_level(self):
        ids = numeric_ids(self.folder)
        return ids[-1] if ids else 1


class MultiplayerSource(FolderSource):
    key = "coop"
    label = "CO-OP"
    folder = paths.MULTIPLAYER
    official = True
    archive_label = "CO-OP LEVELS"
    default_subtitle = "OFFICIAL // CO-OP"
    default_mode = "Co-op"
    empty_text = "NO CO-OP LEVELS YET."

    def mode_lock(self, mode):
        return ONLY_IN_MULTI if mode == SOLO else None

    def _decorate(self, entries):
        for entry in entries:
            low, high = self._player_range(entry["meta"])
            entry["players"] = (low, high)
            entry["meta"]["mode"] = f"Co-op, {low}–{high} players" if low != high else f"Co-op, {low} players"

    @staticmethod
    def _player_range(meta):
        """Player count from metadata: {"players": 3}, {"players": [2, 4]} or "2-4"."""
        raw = meta.get("players", meta.get("recommended_players", [2, 4]))
        try:
            if isinstance(raw, (list, tuple)) and raw:
                low, high = int(raw[0]), int(raw[-1])
            elif isinstance(raw, str) and "-" in raw:
                low, high = (int(p) for p in raw.replace("–", "-").split("-", 1))
            else:
                low = high = int(raw)
        except (TypeError, ValueError):
            low, high = 2, 4
        low = max(2, min(4, low))
        high = max(low, min(4, high))
        return low, high


class MyWorldsSource(FolderSource):
    key = "worlds"
    label = "MY WORLDS"
    folder = paths.USER_WORLDS
    editable = True
    can_create = True
    can_upload = True
    archive_label = "YOUR WORLDS"
    default_subtitle = "CUSTOM // USER CREATED"
    empty_text = "NO WORLDS YET. PRESS NEW +"

    def mode_lock(self, mode):
        return ONLY_IN_MULTI if mode == SOLO else None

    def list(self):
        paths.ensure_folder(self.folder)
        return super().list()


class CommunitySource(LevelSource):
    key = "community"
    label = "COMMUNITY"
    archive_label = "COMMUNITY"
    placeholder = ("COMING SOON",
                   "Worlds made by other players will land here. "
                   "Build yours in MY WORLDS while you wait.")

    def mode_lock(self, mode):
        return ONLY_IN_MULTI if mode == SOLO else None


class TestWorldsSource(FolderSource):
    key = "test"
    label = "TEST"
    folder = paths.TEST_WORLDS
    archive_label = "DEV MAPS"
    default_subtitle = "DEV // TEST WORLD"


def build_sources(debug=False, dev=False):
    """The tabs, in order. Test worlds appear only when debugging (or in the dev editor).

    ``dev`` also opens every story level and lets the pencil edit every folder,
    which is what the standalone level editor wants.
    """
    unlock_all = bool(debug or dev)
    sources = [StorySource(unlock_all), MultiplayerSource(), MyWorldsSource(), CommunitySource()]
    if debug or dev:
        sources.append(TestWorldsSource())
    return sources
