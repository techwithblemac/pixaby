"""
editor_palette.py
=================
Single source of truth for the level editor's placement categories.

Before this module the ``edit_grid_settings`` table existed twice -- once in
``Level_Loader.initialise_grid()`` and again, hand-copied, inside
``Level_Editor_Tools.grid_settings_manager()`` -- along with two identical
copies of the block-name derivation loop. Adding a category meant editing
both copies and hoping they stayed in step.

Everything about "what can the editor place, and what does each category
cycle through" now lives here. The editor, the loader and the tools module
all read from this one table, so a new category is a single edit.

Category indices are exported as constants rather than bare ints so call
sites read as ``EDIT_GRID == SPAWNERS`` instead of ``EDIT_GRID == 6``.
"""

from ...assets import Assets
from ...data.palletes.blocks import block_pallete
from ...data.palletes.entities import entity_pallete
from ...data.palletes.doors import DOOR_KINDS, DOOR_BIOMES
from ...data.biomes import BIOMES
from ...data.traps import TRAP_NAMES

# ---------------------------------------------------------------------- #
# Category indices (the value of game.EDIT_GRID)
# ---------------------------------------------------------------------- #
BLOCKS = 0
ENTITIES = 1
TREASURE = 2
DECO = 3
WATER = 4
PLATFORMS = 5
DOORS = 6
SPAWNERS = 7
START = 8
TRAPS = 9

CATEGORY_ORDER = (BLOCKS, ENTITIES, TREASURE, DECO, WATER, PLATFORMS, DOORS,
                  SPAWNERS, START, TRAPS)

CATEGORY_NAMES = {
    BLOCKS: "BLOCKS",
    ENTITIES: "ENEMIES",
    TREASURE: "TREASURE",
    DECO: "DECO",
    WATER: "WATER ZONES",
    PLATFORMS: "PLATFORMS",
    DOORS: "DOORS",
    SPAWNERS: "SPAWNERS",
    START: "START POINTS",
    TRAPS: "TRAPS",
}

# Categories that have no size/colour variants -- the "Size" button is
# hidden for these.
NO_SIZE_CATEGORIES = (TREASURE, WATER, PLATFORMS, START, TRAPS)

# Categories where the "Size" button is really a colour picker.
COLOUR_CATEGORIES = (ENTITIES, SPAWNERS)

# Categories where the "Size" button is really a biome picker (doors: the
# Type button walks the kinds, this one walks the 8 biome variants).
BIOME_CATEGORIES = (DOORS,)

# ---------------------------------------------------------------------- #
# Entity vocabulary (shared by the enemy and spawner categories)
# ---------------------------------------------------------------------- #
ENTITY_NAMES = ["TNT", "Pawn", "Warrior", "Torch", "Archer"]


def entity_colors():
    """Legal enemy colour strings, straight from the palette module.

    The engine raises a KeyError on any colour outside this set, so every
    editor path that writes a colour validates against this list rather
    than trusting typed input.
    """
    return list(entity_pallete.keys())


# ---------------------------------------------------------------------- #
# Category -> collision rules
# ---------------------------------------------------------------------- #

# EDIT_GRID -> the key used against game.world_rules. BLOCKS is resolved at
# runtime because it depends on the fore/back perspective toggle.
CATEGORY_MODES = {
    ENTITIES: "entities",
    TREASURE: "treasure",
    DECO: "deco",
    WATER: "water",
    PLATFORMS: "platforms",
    DOORS: "door",
    SPAWNERS: "spawn_point",
    START: "start",
    TRAPS: "trap",
}

# A placement mode can occupy a grid cell under a *different* tag than its
# own name. Spawn points share the "entities" tag so that the loader
# (which tags them that way in prep()) and the editor agree on occupancy --
# otherwise an enemy could be dropped into a cell that already holds a
# spawner, and load_world() would silently discard one of them.
GRID_TAGS = {"spawn_point": "entities"}


def mode_for(edit_grid, perspective="fore"):
    """The world_rules key for a category (blocks depend on perspective)."""
    if edit_grid == BLOCKS:
        return f"block_{perspective}"
    return CATEGORY_MODES.get(edit_grid, "platforms")


def grid_tag_for(mode):
    """The tag actually written into ``grid_info[2]`` for a placement mode."""
    return GRID_TAGS.get(mode, mode)


def change_tag_for(edit_grid, perspective="fore"):
    """The ``self.changes`` tag used for dirty-tracking on insert/delete."""
    if edit_grid == BLOCKS:
        return f"block_{perspective}"
    if edit_grid == WATER:
        return "zones"
    if edit_grid == SPAWNERS:
        return "entities"
    if edit_grid == START:
        return "start"
    return CATEGORY_MODES.get(edit_grid, "platforms")


# ---------------------------------------------------------------------- #
# The placement table
# ---------------------------------------------------------------------- #

def build_block_list():
    """Every placeable block name, including palette-swapped variants.

    ``stone``/``grass``/``brick`` blocks carry a ``_2``.. ``_8`` palette
    suffix; everything else has a single variant.
    """
    blocks = list(Assets.blocks.keys())
    all_blocks = []
    for type_ in block_pallete.keys():
        for variant in block_pallete[type_].keys():
            for name in blocks:
                if ("stone" in name or "grass" in name or "brick" in name):
                    var = name if variant == "1" else f"{name}_{variant}"
                else:
                    var = name

                if var not in all_blocks:
                    all_blocks.append(var)

    return all_blocks


# ---------------------------------------------------------------------- #
# Block biomes (the Biome button / B key on the BLOCKS category)
#
# stone / grass / brick blocks carry a ``_2`` .. ``_8`` biome suffix on their
# name ("stone_6"); biome "1" is the unsuffixed original. These helpers let
# the editor swap just the biome while keeping the block kind selected.
# ---------------------------------------------------------------------- #
_BIOME_FAMILIES = ("stone", "grass", "brick")


def block_biome_split(name):
    """``"stone_6"`` -> ``("stone", "6")``; ``"stone"`` -> ``("stone", "1")``."""
    base, _, tail = name.rpartition("_")
    if base and tail in BIOMES and tail != "1" and any(f in base for f in _BIOME_FAMILIES):
        return base, tail
    return name, "1"


def block_has_biomes(name):
    return any(f in block_biome_split(name)[0] for f in _BIOME_FAMILIES)


def block_biome_name(base, biome):
    return base if biome == "1" else f"{base}_{biome}"


def build_edit_grid_settings():
    """The full category table the editor cycles through.

    ``block_types`` is a list of lists: the "Type" button walks the outer
    list and the inner list, so a category that wants one entry per press
    uses single-item inner lists.
    """
    all_blocks = build_block_list()
    colors = entity_colors()

    return {
        BLOCKS: {
            'button_text': 'CHANGE TO ENTITIES',
            'change_size_text': 'CHANGE SIZE',
            'block_types': [all_blocks],
            'block_sizes': ['big', 'small'],
        },
        ENTITIES: {
            'button_text': 'CHANGE TO TREASURE',
            'change_size_text': 'CHANGE COLOUR',
            'block_types': [[name] for name in ENTITY_NAMES],
            'block_sizes': colors,
        },
        TREASURE: {
            'button_text': 'CHANGE TO DECO',
            'change_size_text': '',
            'block_types': [['red', 'pink', 'green', 'yellow', 'charm']],   # 'charm' = the co-op Charm Crystal (rare, placed by hand)
            'block_sizes': [],
        },
        DECO: {
            'button_text': 'CHANGE TO WATERZONES',
            'change_size_text': 'CHANGE PALETTE',
            'block_types': [['tree'], ['grass1'], ['grass2'], ['shrub1'], ['shrub2'], ['shrub3'],
                            ['shroom1'], ['shroom2'], ['shroom3'], ['exit'], ['bone'], ['arrow'],
                            ['scare_crow'], ['pumpkin1'], ['pumpkin2']],
            # Decorations stay neutral until the author explicitly chooses a
            # palette in the editor.
            'block_sizes': list(BIOMES),
        },
        WATER: {
            'button_text': 'CHANGE TO PLATFORMS',
            'change_size_text': '',
            'block_types': [['normal'], ['current'], ['healing'], ['toxic'], ['lava']],
            'block_sizes': [],
        },
        PLATFORMS: {
            'button_text': 'CHANGE TO DOORS',
            'change_size_text': '',
            'block_types': [['normal'], ['current']],
            'block_sizes': [],
        },
        DOORS: {
            'button_text': 'CHANGE TO SPAWNERS',
            'change_size_text': 'CHANGE BIOME',
            'block_types': [[kind] for kind in DOOR_KINDS],
            'block_sizes': list(DOOR_BIOMES),
        },
        SPAWNERS: {
            'button_text': 'CHANGE TO START POINTS',
            'change_size_text': 'CHANGE COLOUR',
            'block_types': [[name] for name in ENTITY_NAMES],
            'block_sizes': colors,
        },
        START: {
            'button_text': 'CHANGE TO TRAPS',
            'change_size_text': '',
            'block_types': [['player start']],
            'block_sizes': [],
        },
        TRAPS: {
            'button_text': 'CHANGE TO BLOCKS',
            'change_size_text': '',
            'block_types': [[name] for name in TRAP_NAMES],
            'block_sizes': [],
        },
    }
