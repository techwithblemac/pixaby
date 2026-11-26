"""
controls.py
===========
THE key table. The Game Info "Controls" page is generated from it, so the page can never go
stale: change a binding in entities/controls.py or settings.py, change it here, done.
(Charm keys come straight from ``Settings.CHARM_KEYS`` / ``Settings.CHARM_JOY_BUTTON``.)

Every row: action, a one-line note, then the label lists per scheme
    p1     keyboard player 1 (arrow keys)         p2   keyboard player 2 (WASD)
    pad    gamepad (button numbers are the raw pygame indices)
    touch  the on-screen control on touchscreens
"""

import pygame

from ..settings import Settings

_NICE = {"return": "ENTER", "escape": "ESC", "right ctrl": "R-CTRL", "left ctrl": "L-CTRL",
         "right shift": "R-SHIFT", "left shift": "L-SHIFT", "space": "SPACE",
         "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT"}


def key_label(key):
    """pygame key constant -> a short keycap label."""
    name = pygame.key.name(key)
    return _NICE.get(name, name.upper())


def _k(*keys):
    return [key_label(k) for k in keys]


def control_rows():
    charm1 = Settings.CHARM_KEYS.get(0)
    charm2 = Settings.CHARM_KEYS.get(1)
    pad_charm = f"BTN {Settings.CHARM_JOY_BUTTON}"
    return [
        {"action": "Move", "note": "Walk and run.",
         "p1": _k(pygame.K_LEFT, pygame.K_RIGHT), "p2": _k(pygame.K_a, pygame.K_d),
         "pad": ["STICK L/R"], "touch": "Left stick"},
        {"action": "Jump / swim up", "note": "A second press in the air jumps again.",
         "p1": _k(pygame.K_UP), "p2": _k(pygame.K_w), "pad": ["STICK UP"], "touch": "Left stick up"},
        {"action": "Swim down", "note": "In water.",
         "p1": _k(pygame.K_DOWN), "p2": _k(pygame.K_s), "pad": ["STICK DOWN"], "touch": "Left stick down"},
        {"action": "Attack", "note": "Hold to keep attacking.",
         "p1": _k(pygame.K_RSHIFT), "p2": _k(pygame.K_LSHIFT), "pad": ["BTN 6"], "touch": "ATTACK button"},
        {"action": "Dash", "note": "Hold it: the dash lasts while the bar does. The bar refills by time.",
         "p1": _k(pygame.K_RCTRL), "p2": _k(pygame.K_LCTRL), "pad": ["BTN 5"], "touch": "DASH button"},
        {"action": "Fire arrows", "note": "Archer and TNT volley at the current target.",
         "p1": [], "p2": [], "pad": ["BTN 7"], "touch": "ATTACK button"},
        {"action": "Befriend charm", "note": "Opens charm mode (story campaign).",
         "p1": _k(charm1) if charm1 else [], "p2": _k(charm2) if charm2 else [],
         "pad": [pad_charm], "touch": "Heart button"},
        {"action": "In charm mode: choose", "note": "Jumps to the next enemy in that direction.",
         "p1": _k(pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN),
         "p2": _k(pygame.K_a, pygame.K_d, pygame.K_w, pygame.K_s), "pad": ["D-PAD", "STICK"], "touch": "Tap an enemy"},
        {"action": "In charm mode: confirm", "note": "Spends the charm on the chosen enemy.",
         "p1": _k(pygame.K_RETURN, pygame.K_SPACE), "p2": _k(pygame.K_RETURN, pygame.K_SPACE),
         "pad": ["BTN 0"], "touch": "Tap it again / OK"},
        {"action": "In charm mode: cancel", "note": "Free if you cancel within the first second.",
         "p1": _k(pygame.K_ESCAPE), "p2": _k(pygame.K_ESCAPE), "pad": ["BTN 1"], "touch": "X button"},
        {"action": "Zoom in / out", "note": "The camera also widens a little at speed.",
         "p1": _k(pygame.K_n, pygame.K_m), "p2": _k(pygame.K_z, pygame.K_x), "pad": ["BTN 8", "BTN 9"], "touch": "-"},
        {"action": "Slow motion", "note": "Hold while the world is moving.",
         "p1": _k(pygame.K_SPACE), "p2": _k(pygame.K_SPACE), "pad": ["-"], "touch": "-"},
        {"action": "Menus", "note": "Every menu works with all three.",
         "p1": _k(pygame.K_UP, pygame.K_DOWN, pygame.K_RETURN, pygame.K_ESCAPE), "p2": [],
         "pad": ["D-PAD", "BTN 0", "BTN 1"], "touch": "Tap"},
    ]
