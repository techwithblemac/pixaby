"""
version.py
==========
The ONE place the game's name and version come from.

    VERSION   the text of the VERSION file at the project root ("39.0.0"); edit that file (or run
              extras/bump_version.py) and the whole game follows: the window title, Game Info,
              Author Info, the editor, crash logs and game.json.
    NAME      the app / package name ("Pixaby")
    TITLE     the title shown in the game ("PIXEL ABYSS")

Never type the version anywhere else; import it from here.
"""

import re

from .scripts import paths

NAME = "Pixaby"
TITLE = "PIXEL ABYSS"
FALLBACK = "0.0.0"
VERSION_FILE = paths.BASE_DIR / "VERSION"


def read_version(path=VERSION_FILE):
    """The version in ``path`` (major.minor.patch); FALLBACK if the file is missing or malformed."""
    try:
        text = path.read_text(encoding="utf-8").strip().lstrip("vV")
    except OSError:
        return FALLBACK
    return text if re.fullmatch(r"\d+\.\d+\.\d+", text) else FALLBACK


VERSION = read_version()
VERSION_TAG = "v" + VERSION
VERSION_TUPLE = tuple(int(n) for n in VERSION.split("."))
WINDOW_TITLE = f"{TITLE} {VERSION_TAG}"
