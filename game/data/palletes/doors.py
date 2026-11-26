"""
doors.py
========
The door vocabulary and its biome palettes.

A door's ``name`` in the level JSON is ``<kind>`` or ``<kind>_<biome>``,
exactly like blocks use ``stone`` / ``stone_2``:

    teleport     random start point (the pool the player spawns from)
    warp         random pick from the door's own ``targets`` list
    exit         ends the level

    <kind>_2 .. <kind>_8   the same door re-coloured for a biome
                           (2 dark, 3 sandy, 4 mossy, 5 snow, 6 nether,
                           7 void, 8 autumn -- the same numbering as blocks)

Biome colours are NOT duplicated here. The frame of ``door_open.png`` is
drawn in the stone block's colours, so the frame swaps are read straight
from ``block_pallete["stone"]`` (plus the outline colour from the brick
palette). Add or tweak a biome in blocks.py and the doors follow.

The portal in the middle is tinted per *kind* rather than per biome, so
you can tell a teleport from a warp from an exit at a glance in any biome.
"""

from .blocks import block_pallete

DOOR_KINDS = ("teleport", "warp", "exit")
DOOR_BIOMES = tuple(block_pallete["stone"].keys())      # "1" .. "8"

# --- colours that exist in assets/doors/door_open.png ------------------- #
_FRAME_OUTLINE = (33, 31, 48)
# The portal interior is the same two greys as the stone frame, but drawn
# semi-transparent, so the two are told apart by alpha when recolouring.
_PORTAL_LIGHT = (133, 141, 153)
_PORTAL_DARK = (98, 103, 122)

# (light, dark) tint of the portal for each kind
PORTAL_COLORS = {
    "teleport": ((176, 120, 255), (112, 64, 200)),    # violet
    "warp":     ((90, 220, 240),  (40, 140, 200)),    # cyan
    "exit":     ((120, 240, 140), (50, 170, 90)),     # green
}


def door_name(kind, biome="1"):
    """``("teleport", "3")`` -> ``"teleport_3"``; biome 1 has no suffix."""
    biome = str(biome)
    return kind if biome == "1" or biome not in DOOR_BIOMES else f"{kind}_{biome}"


def parse_door_name(name):
    """``"warp_4"`` -> ``("warp", "4")``.

    Anything unrecognised (e.g. an old hand-edited level) is treated as a
    plain ``teleport`` so a typo can never crash the loader.
    """
    name = str(name or "")
    if name in DOOR_KINDS:
        return name, "1"
    kind, _, biome = name.rpartition("_")
    if kind in DOOR_KINDS and biome in DOOR_BIOMES:
        return kind, biome
    return "teleport", "1"


def build_door_names():
    """Every placeable door name, kind by kind."""
    return [door_name(kind, biome) for kind in DOOR_KINDS for biome in DOOR_BIOMES]


def frame_swaps(biome):
    """``{old_rgb: new_rgb}`` for the stone frame in the given biome."""
    swaps = {tuple(old): tuple(new) for old, new in block_pallete["stone"].get(biome, [])}
    for old, new in block_pallete["brick"].get(biome, []):
        if tuple(old) == _FRAME_OUTLINE:
            swaps[_FRAME_OUTLINE] = tuple(new)
    return swaps


def portal_swaps(kind):
    """``{old_rgb: new_rgb}`` for the translucent portal of a door kind."""
    light, dark = PORTAL_COLORS[kind]
    return {_PORTAL_LIGHT: light, _PORTAL_DARK: dark}
