"""
traps.py
========
Everything the game and the level editor need to know about the traps in
``assets/traps``. One table, read by the loader, the Trap object, the
editor palette and the editor's modify popup.

Sprite sheets are cut into frames ``FRAME_W`` pixels wide (the art is 16px)
and scaled up by the trap's ``scale`` (default ``SCALE``). Spikes are 4x, so
one frame fills the 64px grid cell. The fire burner is 2x: a 32x32 body with
the flame above it (32x64 in all), centred and resting on the bottom of one
64x64 cell. Nothing may stick out of the cell.

A third trap, "homing" (the Homing Arrow Trap), has no sprite sheet: it is drawn in code and simulated by
objects/arrow_trap.py. It is listed in TRAP_NAMES so the editor palette offers it; the loader builds an
``ArrowTrap`` for it instead of a ``Trap``.

Hitboxes are ``(x, y, w, h)`` in pixels relative to the top-left of the
trap's grid cell.
"""

FRAME_W = 16
SCALE = 4
CELL = 64

# order = the order the editor's Type button walks through
TRAP_NAMES = ["spikes", "fire", "homing"]   # "homing" is the Homing Arrow Trap (objects/arrow_trap.py): no sprite sheet, drawn in code

TRAP_KINDS = {
    "spikes": {
        "label": "Spikes",
        "scale": 4,
        "always_on": True,          # never switches off
        "hitbox": (6, 40, 52, 24),  # the pointy bit only
        "damage": 15.0,             # health lost per hit
        "cooldown": 0.8,            # seconds before the same victim can be hit again
        "hit_type": "spikes",
    },
    "fire": {
        "label": "Fire Burner",
        "scale": 2,                    # 32x32 body, flame above it, all inside the cell
        "always_on": False,
        "hitbox": (22, 4, 20, 28),     # the flame, inside the cell
        "damage_per_sec": 14.0,        # burning damage while the flame is up
        "hit_type": "fire",
        "windup_frame_time": 0.14,     # seconds per frame of the "hit" (warm-up) sheet
        "on_frame_time": 0.12,         # seconds per frame of the flame loop
        # defaults for the settings the editor lets you change per trap
        "off_time": 2.0,               # seconds the burner rests
        "on_time": 1.5,                # seconds the flame burns
        "delay": 0.0,                  # start offset, to stagger a row of burners
    },
}

# Defaults every trap shares (also editable per trap in the editor)
DEFAULT_HURT_ENEMIES = True


def kind_for(name):
    """Definition for ``name`` (falls back to spikes for unknown names)."""
    return TRAP_KINDS.get(str(name).lower(), TRAP_KINDS["spikes"])
