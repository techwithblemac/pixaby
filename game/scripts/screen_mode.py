"""
screen_mode.py
==============
The three screen modes (Game Settings -> bottom row) and everything needed to switch between them.

    fullscreen   the desktop resolution, full screen
    800x600      a centred window
    1280x960     a centred window  (only offered when the desktop is big enough to hold it)

The choice is remembered in display.json next to the game (paths.save_file), so the game opens the
way you left it. The first time there is no file, it opens full screen.

``Settings.WIDTH / HEIGHT / window / window_rect`` always describe the CURRENT mode; switching
rewrites them and then re-lays-out whatever caches a size (viewports, touch sticks, menu backdrop).
Menus fix their own button rectangles when the surface size changes (scripts/menu.py).

This module must not import ``settings`` at import time (settings imports it); ``apply()`` imports it late.
"""

import json
import os

import pygame

from . import paths

FULLSCREEN = "fullscreen"
MODES = (FULLSCREEN, "800x600", "1280x960")
SIZES = {"800x600": (800, 600), "1280x960": (1280, 960)}
LABELS = {FULLSCREEN: "FULLSCREEN", "800x600": "800 x 600", "1280x960": "1280 x 960"}
DEFAULT_MODE = FULLSCREEN

_WINDOW_MARGIN = 80          # room kept for the title bar and the taskbar when a window must fit
_FILE = "display.json"

_desktop = None              # measured once, before the first set_mode()
_current = DEFAULT_MODE


def desktop_size():
    """(width, height) of the desktop, landscape. Measured once: after set_mode() Info() reports the window."""
    global _desktop
    if _desktop is None:
        try:
            w, h = pygame.display.get_desktop_sizes()[0]
        except (AttributeError, IndexError, pygame.error):
            info = pygame.display.Info()
            w, h = info.current_w, info.current_h
        _desktop = (max(w, h), min(w, h))
    return _desktop


def available(mode):
    """Full screen always; a window only if it fits on this desktop."""
    if mode == FULLSCREEN:
        return True
    if mode not in SIZES:
        return False
    w, h = SIZES[mode]
    dw, dh = desktop_size()
    return w <= dw and h <= dh - _WINDOW_MARGIN


def current():
    return _current


def saved_mode():
    """The remembered mode, or the default when there is no (valid) file or it no longer fits."""
    try:
        with open(paths.save_file(_FILE), "r", encoding="utf-8") as f:
            mode = json.load(f).get("mode")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_MODE
    return mode if mode in MODES and available(mode) else DEFAULT_MODE


def _remember(mode):
    # A failed write must never crash the game; the mode just is not remembered.
    try:
        with open(paths.save_file(_FILE), "w", encoding="utf-8") as f:
            json.dump({"mode": mode}, f)
    except OSError:
        pass


def open_window(mode):
    """Create the display for ``mode`` and return its surface."""
    global _current
    if mode not in MODES or not available(mode):
        mode = DEFAULT_MODE
    if mode == FULLSCREEN:
        surface = pygame.display.set_mode(desktop_size(), pygame.FULLSCREEN, 32)
    else:
        os.environ["SDL_VIDEO_CENTERED"] = "1"        # read by SDL when the window is (re)created
        surface = pygame.display.set_mode(SIZES[mode], 0, 32)
    _current = mode
    return surface


def initial_window():
    """Used once by settings.py: the remembered mode's window."""
    return open_window(saved_mode())


def apply(game, mode):
    """Switch to ``mode`` now. Returns False (and changes nothing) when it is unknown or does not fit."""
    if mode not in MODES or not available(mode):
        return False
    if mode == _current:
        return True
    from ..settings import Settings

    surface = open_window(mode)
    Settings.window = surface
    Settings.WIDTH, Settings.HEIGHT = surface.get_size()
    Settings.window_rect = surface.get_rect()
    _remember(mode)
    if game is not None:
        relayout(game)
    return True


def relayout(game):
    """Re-do everything the game computed from the old window size."""
    from ..settings import Settings
    from .functions import calculate_viewports

    game.window_rect = Settings.window_rect

    if hasattr(game, "layout_touch_sticks"):
        game.layout_touch_sticks()
    if hasattr(game, "initialise_constants"):
        game.initialise_constants()                     # the scaled menu backdrop
    if hasattr(game, "game_name") and hasattr(game, "update_start_btns_pos"):
        game.update_start_btns_pos()                    # the title on the start screen

    local = getattr(game, "local_players", None)
    if local:
        for player, view in zip(local, calculate_viewports(game, len(local))):
            player.viewport = pygame.Rect(*view)
            player.camera_update()

    if getattr(game, "players", None) and hasattr(game, "players_config") and hasattr(game, "update_player_edit"):
        game.update_player_edit()                       # its menus are sub-surfaces of the old display
