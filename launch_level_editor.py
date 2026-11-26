"""
launch_level_editor.py - launch the level editor.

    python3 launch_level_editor.py
"""

import pygame

import game.level.level_editor as level_editor
from game import settings as _settings
from game.scripts import paths
from game.version import NAME, VERSION_TAG

pygame.display.set_caption(f"{NAME.upper()} LEVEL EDITOR")
_settings.icon = pygame.image.load(paths.asset("icons", "icon_2.png"))
pygame.display.set_icon(_settings.icon)

print(f"{NAME} Level Editor {VERSION_TAG}")


def main():
    level_editor.Level_Editor().start()


if __name__ == "__main__":
    main()
