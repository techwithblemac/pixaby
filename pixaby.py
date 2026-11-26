"""
pixaby.py - launch the game.

    python3 pixaby.py          Windows / Linux

The name and version printed here come from the VERSION file (game/version.py).
"""

import game.main as game
from game.version import NAME, VERSION_TAG

print(f"{NAME} {VERSION_TAG}")

LEVEL = 1


def main():
    """Start the game (it opens its own window)."""
    game.Game(LEVEL).start()


if __name__ == "__main__":
    main()
