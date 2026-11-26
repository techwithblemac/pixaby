"""
bump_version.py - change the game's version in ONE step.

    python3 extras/bump_version.py            bump the patch   39.0.0 -> 39.0.1
    python3 extras/bump_version.py minor      39.0.1 -> 39.1.0
    python3 extras/bump_version.py major      39.1.0 -> 40.0.0
    python3 extras/bump_version.py 41.2.0     set it exactly

The VERSION file at the project root is the single source of truth. This script writes it and
keeps game.json in step; everything else (window title, Game Info, Author Info, editor, crash
logs) reads the file itself, so there is nothing more to edit.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
GAME_JSON = ROOT / "game.json"


def current():
    try:
        text = VERSION_FILE.read_text(encoding="utf-8").strip().lstrip("vV")
    except OSError:
        return "0.0.0"
    return text if re.fullmatch(r"\d+\.\d+\.\d+", text) else "0.0.0"


def bumped(version, mode="patch"):
    if re.fullmatch(r"v?\d+\.\d+\.\d+", mode):
        return mode.lstrip("v")
    major, minor, patch = (int(p) for p in version.split("."))
    if mode == "major":
        return f"{major + 1}.0.0"
    if mode == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def write(version):
    VERSION_FILE.write_text(version + "\n", encoding="utf-8")
    if GAME_JSON.exists():
        data = json.loads(GAME_JSON.read_text(encoding="utf-8"))
        data["version"] = "v" + version
        GAME_JSON.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")


if __name__ == "__main__":
    new = bumped(current(), sys.argv[1].lower() if len(sys.argv) > 1 else "patch")
    write(new)
    print(new)
