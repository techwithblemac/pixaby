"""
touch.py
========
Is there a touchscreen to play with?  Touch support stays in the game for touchscreen PCs, laptops
and tablets; this is the one place that decides whether the on-screen sticks / buttons are used.

    Settings.TOUCH_CONTROLS = "auto"   use touch when SDL reports a touch device (the default)
                              "on"     always join player 1 with touch (handy for testing)
                              "off"    never auto-join with touch
    environment variable PIXABY_TOUCH=on|off|auto overrides the setting without editing any file.
"""

import os

import pygame


def touch_screen_present():
    """True when SDL reports at least one touch device. Never raises."""
    try:
        from pygame._sdl2 import touch
        return touch.get_num_devices() > 0
    except Exception:
        return False


def touch_enabled(setting="auto"):
    """Resolve the touch mode ("auto" / "on" / "off", env var wins) to a plain bool."""
    mode = str(os.environ.get("PIXABY_TOUCH", setting)).strip().lower()
    if mode in ("on", "1", "true", "yes"):
        return True
    if mode in ("off", "0", "false", "no"):
        return False
    return touch_screen_present()
