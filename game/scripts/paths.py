"""
paths.py
========
Where things live on disk, in one place.

Two kinds of files:

* READ-ONLY game data that ships with the build (levels/story, levels/multiplayer,
  levels/test_worlds, levels/selector_world).
* WRITABLE player data (progress.json, achievements.json, the player's own worlds).

Everything is resolved from ONE anchor, BASE_DIR (the project folder: the one that holds
assets/, levels/, VERSION and game/). Nothing else in the game computes its own base
directory or calls os.chdir; use ``asset()``, ``LEVELS_ROOT`` and ``BASE_DIR``.
``enter_base_dir()`` is called exactly once (settings.py) so that the few remaining
relative strings keep working wherever the game is launched from.

Writable files sit in BASE_DIR next to the game, so an existing achievements.json is still found.

Level ids are small ints (1.json, 2.json ...) inside a *folder*:

    story        levels/story/       the 10-level campaign        (read-only)
    multiplayer  levels/multiplayer/ co-op levels                 (read-only)
    test_worlds  levels/test_worlds/ dev maps, debug mode only    (read-only)
    user_worlds  levels/user_worlds/ the player's own worlds      (writable)

A level id that is a string containing "/" (for example the level-select
backdrop, "selector_world/level_select_map_standard") is taken relative to
levels/ and ignores the folder.
"""

import os
from pathlib import Path

# game/scripts/paths.py  ->  parents[2] is the project folder
BASE_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = BASE_DIR / "assets"
DOCS_DIR = BASE_DIR / "docs"
LEVELS_ROOT = str(BASE_DIR / "levels")

STORY = "story"
MULTIPLAYER = "multiplayer"
USER_WORLDS = "user_worlds"
TEST_WORLDS = "test_worlds"

FOLDERS = (STORY, MULTIPLAYER, USER_WORLDS, TEST_WORLDS)


def enter_base_dir():
    """Make BASE_DIR the working directory. The single place this happens (called from settings.py)."""
    if Path.cwd().resolve() != BASE_DIR:
        os.chdir(BASE_DIR)
    return BASE_DIR


def asset(*parts):
    """Absolute path of something under assets/.

    Folders in assets/ are lower case (Linux is case sensitive), so every FOLDER part is lower-cased
    here and callers cannot get it wrong; the last part is left alone when it is a file name
    (anything with a dot), because file names keep their real case (Tree.png, Terrain2.png).

        asset("terrain", "Terrain2.png")        asset("enemies", "warrior", "Warrior.png")
        asset("weapons/arrow/Arrow.png")        asset("sounds")
    """
    pieces = [c for p in parts for c in str(p).replace("\\", "/").split("/") if c]
    if pieces and "." not in pieces[-1]:
        fixed = [c.lower() for c in pieces]
    else:
        fixed = [c.lower() for c in pieces[:-1]] + pieces[-1:]
    return str(ASSETS_DIR.joinpath(*fixed))


def save_dir():
    """Folder player data (progress.json, achievements.json) is written to: BASE_DIR."""
    return str(BASE_DIR)


def save_file(name):
    return os.path.join(save_dir(), name)


def folder_dir(folder):
    """Directory holding a level folder."""
    folder = folder or STORY
    return os.path.join(LEVELS_ROOT, folder)


def ensure_folder(folder):
    path = folder_dir(folder)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def level_file(level, folder=STORY):
    """Path of one level's JSON file."""
    if isinstance(level, str) and "/" in level:
        return os.path.join(LEVELS_ROOT, level + ".json")
    return os.path.join(folder_dir(folder), f"{level}.json")


def metadata_file(folder):
    return os.path.join(folder_dir(folder), "metadata.json")
