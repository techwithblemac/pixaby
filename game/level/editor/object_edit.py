"""
object_edit.py
==============
The editor's third tool: MODIFY. Left-click a cell that already holds
something and its settings popup reopens, prefilled with what's actually
there, instead of having to delete the object and place a fresh one just
to change a patrol range.

Two halves:

* ``fields_for(data)`` -- rebuilds the same popup field list the matching
  ``add_*`` used when the object was first placed, but with the object's
  current values as defaults.
* ``apply(game, data, values)`` -- writes the values into the world JSON
  and then re-instantiates the live object from that JSON.

Two objects skip the generic popup and get their own window (ui/entity_editor.py):

* an ENEMY opens the ENTITY EDITOR (categories: placement, health, combat, arrows, movement & dash, homing
  traps, boss, and the shop items it can be granted). ``apply_entity`` writes its result: placement keys at the
  top of the entry and everything else under ``"mods"`` (read back by entities/mods.py).
* a HOMING ARROW TRAP opens a small window for its hand-set effects (it has no owner to take them from).

The re-instantiation deliberately mirrors the constructor calls in
``editor_tools.add_*`` rather than reaching into the live object and
setting attributes piecemeal. Width/height changes need a fresh sprite,
and a half-updated object that only looks right after a reload is worse
than no feature at all. The JSON stays the single source of truth.
"""

import pygame

from ...entities.entities import Enemy, Spawn_Point
from ...objects.objects import Tree, Block, Deco, WaterZone, Platform, Treasure, Door, Trap, make_treasure
from ...objects import arrow_trap
from ...entities import mods as mods_rt
from . import editor_palette
from . import spawner_tools
from . import door_tools
from . import layer_tools


# JSON type -> the live list that holds it.
def _live_list(game, data):
    kind = data.get("type")
    if kind == "block":
        return game.bg_objects if data.get("perspective", "fore") == "back" else game.objects
    return {
        "enemy": getattr(game, "enemy_list", None),
        "spawn_point": getattr(game, "spawn_points", None),
        "water": getattr(game, "zones", None),
        "moving_platform": getattr(game, "platforms", None),
        "treasure": getattr(game, "treasure_list", None),
        "deco": getattr(game, "damageable_objects", None),
        "tree": getattr(game, "damageable_objects", None),
        "door": getattr(game, "doors", None),
        "trap": getattr(game, "traps", None),
    }.get(kind)


CHANGE_TAGS = {
    "enemy": "entities",
    "spawn_point": "entities",
    "water": "zones",
    "moving_platform": "platforms",
    "treasure": "treasure",
    "deco": "deco",
    "tree": "deco",
    "door": "door",
    "trap": "trap",
}


def change_tag_for(data):
    if data.get("type") == "block":
        return "block_back" if data.get("perspective", "fore") == "back" else "block_fore"
    return CHANGE_TAGS.get(data.get("type"), "entities")


# Types this tool knows how to edit. Anything else is skipped when
# picking what the click landed on.
EDITABLE = ("block", "enemy", "spawn_point", "water",
            "moving_platform", "treasure", "deco", "tree", "door", "trap")

# Which JSON types each editor category considers "its own", so a click
# on a cell holding several things edits the one you're working with.
CATEGORY_TYPES = {
    editor_palette.BLOCKS: ("block",),
    editor_palette.ENTITIES: ("enemy",),
    editor_palette.TREASURE: ("treasure",),
    editor_palette.DECO: ("deco", "tree"),
    editor_palette.WATER: ("water",),
    editor_palette.PLATFORMS: ("moving_platform",),
    editor_palette.SPAWNERS: ("spawn_point",),
    editor_palette.DOORS: ("door",),
    editor_palette.TRAPS: ("trap",),
}


def pick(game, grid_info):
    """The world entry a click on this cell should edit.

    A cell can legitimately hold more than one thing (a background block
    under an enemy). Preference goes to whatever matches the active
    category, so the tool edits what you're looking at.
    """
    hits = [
        data for data in game.world
        if isinstance(data, dict)
        and data.get("type") in EDITABLE
        and layer_tools.type_visible(game, data.get("type"))
        and grid_info[0].collidepoint(data.get("x", 1), data.get("y", 1))
    ]
    if not hits:
        return None

    preferred = CATEGORY_TYPES.get(getattr(game, "EDIT_GRID", None), ())
    for data in hits:
        if data.get("type") in preferred:
            return data
    return hits[0]


def title_for(data):
    return {
        "block": "Edit Block",
        "enemy": "Edit Enemy",
        "spawn_point": "Edit Spawner",
        "water": "Edit Water Zone",
        "moving_platform": "Edit Platform",
        "treasure": "Edit Treasure",
        "deco": "Edit Decoration",
        "tree": "Edit Tree",
        "door": "Edit Door",
        "trap": "Edit Trap",
    }.get(data.get("type"), "Edit Object")


def fields_for(data):
    """Popup fields for an existing object, defaulted to its own values."""
    kind = data.get("type")
    x = int(data.get("x", 0))
    y = int(data.get("y", 0))

    size = [
        {"key": "width", "label": "Width", "type": "int",
         "default": int(data.get("width", 64)), "min": 1, "max": 4000},
        {"key": "height", "label": "Height", "type": "int",
         "default": int(data.get("height", 64)), "min": 1, "max": 4000},
    ]

    if kind == "block":
        return size

    if kind == "enemy":
        # The cell is 64px; keep the nudge range anchored to the cell the
        # enemy already sits in rather than to its current offset.
        cell_x, cell_y = (x // 64) * 64, (y // 64) * 64
        return [
            {"key": "x", "label": "X", "type": "int", "default": x,
             "min": cell_x, "max": cell_x + 63},
            {"key": "y", "label": "Y", "type": "int", "default": y,
             "min": cell_y, "max": cell_y + 63},
            {"key": "posted", "label": "Posted", "type": "bool",
             "default": bool(data.get("posted", False))},
            {"key": "patroller", "label": "Patroller", "type": "bool",
             "default": bool(data.get("patroller", False))},
            {"key": "patrol_range_x", "label": "Patrol Range X", "type": "int",
             "default": int(data.get("patrol_range_x", 1000)), "min": 64, "max": 2000},
            {"key": "patrol_range_y", "label": "Patrol Range Y", "type": "int",
             "default": int(data.get("patrol_range_y", 1000)), "min": 64, "max": 2000},
        ]

    if kind == "trap":
        fields = []
        if str(data.get("name", "")).lower() == arrow_trap.NAME:
            return fields          # the Homing Trap has its own window (ui/entity_editor.edit_trap)
        if str(data.get("name", "")).lower() == "fire":
            fields += [
                {"key": "off_time", "label": "Rest time (sec)", "type": "float",
                 "default": float(data.get("off_time", 2.0)), "min": 0.1, "max": 60.0},
                {"key": "on_time", "label": "Flame time (sec)", "type": "float",
                 "default": float(data.get("on_time", 1.5)), "min": 0.1, "max": 60.0},
                {"key": "delay", "label": "Start delay (sec)", "type": "float",
                 "default": float(data.get("delay", 0.0)), "min": 0.0, "max": 60.0},
            ]
        fields.append({"key": "hurt_enemies", "label": "Hurts enemies", "type": "bool",
                       "default": bool(data.get("hurt_enemies", True))})
        return fields

    if kind == "door":
        cell_x, cell_y = (x // 64) * 64, (y // 64) * 64
        fields = [
            {"key": "x", "label": "X", "type": "int", "default": x,
             "min": cell_x, "max": cell_x + 63},
            {"key": "y", "label": "Y", "type": "int", "default": y,
             "min": cell_y, "max": cell_y + 63},
        ]
        if str(data.get("name", "")).startswith("warp"):
            fields.append({
                "key": "targets", "label": "Targets (x,y; x,y)", "type": "text",
                "default": door_tools.format_targets(data.get("targets") or []),
            })
        return fields

    if kind == "spawn_point":
        roster = data.get("entities") or [["Pawn", "Red"]]
        return [
            {"key": "interval", "label": "Interval (sec)", "type": "int",
             "default": int(data.get("interval", 5)), "min": 1, "max": 600},
            {"key": "limit", "label": "Spawn Limit", "type": "int",
             "default": int(data.get("limit", 5)), "min": 1, "max": 999},
            {"key": "roster", "label": "Roster (Name:Colour)", "type": "text",
             "default": spawner_tools.format_roster(roster)},
        ]

    if kind == "water":
        return size + [
            {"key": "flow", "label": "Flow", "type": "int",
             "default": int(data.get("flow", 1)), "min": -100, "max": 100},
            {"key": "rise", "label": "Rise", "type": "bool",
             "default": bool(data.get("rise", False))},
        ]

    if kind == "moving_platform":
        direction = data.get("direction") or [-1, -1]
        return size + [
            {"key": "dir_x", "label": "Direction X", "type": "choice",
             "options": [-1, 1], "default": direction[0]},
            {"key": "dir_y", "label": "Direction Y", "type": "choice",
             "options": [-1, 1], "default": direction[1]},
            {"key": "moving", "label": "Moving", "type": "bool",
             "default": bool(data.get("moving", True))},
            {"key": "speed", "label": "Speed", "type": "int",
             "default": int(data.get("speed", 100)), "min": 1, "max": 2000},
        ]

    # treasure / deco / tree carry nothing but geometry.
    return size


def _write(data, values):
    """Merge popup values into the world entry."""
    kind = data.get("type")

    for key in ("width", "height", "x", "y", "flow", "rise",
                "posted", "patroller", "patrol_range_x", "patrol_range_y", "facing",
                "interval", "limit", "moving", "speed",
                "off_time", "on_time", "delay", "hurt_enemies"):
        if key in values:
            data[key] = values[key]

    for key in arrow_trap.PROP_DEFAULTS:
        if kind == "trap" and key in values:
            data[key] = values[key]

    if kind == "door" and "targets" in values:
        data["targets"] = door_tools.parse_targets(values["targets"])

    if kind == "spawn_point" and "roster" in values:
        data["entities"] = spawner_tools.parse_roster(values["roster"])

    if kind == "moving_platform" and "dir_x" in values:
        data["direction"] = [values["dir_x"], values["dir_y"]]


def _construct(game, data):
    """Build a live object from a world entry.

    Mirrors the constructor calls in ``editor_tools.add_*`` -- if one of
    those changes shape, this is the other half that has to follow.
    """
    kind = data.get("type")
    x, y = data.get("x", 0), data.get("y", 0)
    width = data.get("width", 64)
    height = data.get("height", 64)

    if kind == "block":
        return Block(x, y, width, height, data.get("name"), data.get("size"),
                     game=game, perspective=data.get("perspective", "fore"))

    if kind == "enemy":
        enemy = Enemy(x, y, width, height, data.get("name"), data.get("color"), game)
        enemy.update_sprite()
        enemy.posted = data.get("posted", False)
        enemy.patroller = data.get("patroller", False)
        enemy.patrol_range_x = data.get("patrol_range_x", 1000)
        enemy.patrol_range_y = data.get("patrol_range_y", 1000)
        mods_rt.apply(enemy, data)
        return enemy

    if kind == "spawn_point":
        return Spawn_Point(x, y, width, height,
                           data.get("interval", 5), data.get("limit", 5),
                           data.get("entities") or [["Pawn", "Red"]], game)

    if kind == "water":
        color = tuple(data.get("color") or (50, 200, 50))
        return WaterZone(x, y, width, height, data.get("water_type", "normal"),
                         game, color, data.get("flow", 1), data.get("rise", False))

    if kind == "moving_platform":
        dest_x = data.get("dest_x") or [data.get("min_x", x), data.get("max_x", x + width)]
        dest_y = data.get("dest_y") or [y, y + height]
        return Platform(x, y, width, height, data.get("moving", True),
                        data.get("direction") or [-1, -1], data.get("speed", 100),
                        (dest_x[0], dest_x[1]), (dest_y[0], dest_y[1]), game)

    if kind == "trap" and str(data.get("name", "")).lower() == arrow_trap.NAME:
        return arrow_trap.ArrowTrap(x, y, game, props=data)

    if kind == "trap":
        return Trap(x, y, data.get("name", "spikes"), game, data.get("off_time"),
                    data.get("on_time"), data.get("delay"), data.get("hurt_enemies", True))

    if kind == "door":
        return Door(x, y, data.get("name"), game, data.get("targets"))

    if kind == "treasure":
        treasure = make_treasure(x, y, data.get("name"), game)
        treasure.update_sprite()
        return treasure

    if kind == "tree":
        name = str(data.get("name", "tree"))
        palette = name.rsplit("_", 1)[-1] if name.rsplit("_", 1)[-1] in ("1","2","3","4","5","6","7","8") else "1"
        tree = Tree(x, y, game, palette)
        tree.update_sprite()
        return tree

    if kind == "deco":
        deco = Deco(x, y, data.get("name"), game)
        deco.update_sprite()
        return deco

    return None


def _match(obj, grid_info, kind):
    """Does this live object correspond to the clicked cell?"""
    if kind == "block":
        rect = getattr(obj, "rect", None)
        return rect is not None and rect.colliderect(grid_info[0])
    rect = getattr(obj, "origin_rect", None) or getattr(obj, "rect", None)
    return rect is not None and grid_info[0].collidepoint(rect.x, rect.y)


def apply_entity(game, data, result, grid_info):
    """Write an Entity Editor result ({"data": placement keys, "mods": sparse tweaks}) into the entry and rebuild it."""
    values = dict(result["data"])
    mods = result["mods"]
    if mods:
        data["mods"] = mods
    else:
        data.pop("mods", None)
    return apply(game, data, values, grid_info)


def apply(game, data, values, grid_info):
    """Write ``values`` into ``data`` and rebuild the live object."""
    _write(data, values)

    kind = data.get("type")
    live = _live_list(game, data)
    if live is None:
        return False

    for obj in live[:]:
        if _match(obj, grid_info, kind):
            live.remove(obj)
            break

    replacement = _construct(game, data)
    if replacement is not None:
        live.append(replacement)

    game.changes.add(change_tag_for(data))
    if kind in ("enemy", "spawn_point"):
        game._entities_dirty = True
    game._draw_list_dirty = True
    return True
