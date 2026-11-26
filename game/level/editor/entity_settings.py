"""
entity_settings.py
==================
Editing for the level's ``"entity settings"`` entry -- the per-level stat
block that tunes every enemy type:

    {"type": "entity settings",
     "Pawn": {"health": 70, "attack_power": 5, "attack_range": 40, ...},
     "Archer": {...},
     "_level_meta": {...}}

``Level_Loader.personalise()`` copies these onto every entity as it is
created, so they are how a level says "archers hit harder here". Until
now the only way to set them was to hand-edit the JSON.

Two popups rather than one: the field popup renders a fixed row per
field, and five entity types times eight stats is forty rows on a panel
that expects five or six. So the first popup picks the type and the
second edits that type's stats.

``_level_meta`` shares this dict and is owned by the level selector, so
this module only ever touches the per-entity sub-dicts and leaves every
other key alone.
"""

from .editor_palette import ENTITY_NAMES


# Stat -> (label, minimum, maximum). Ordered as they appear in the popup.
STATS = [
    ("health",        "Health",        1, 100000),
    ("attack_power",  "Attack Power",  0, 10000),
    ("attack_range",  "Attack Range",  0, 10000),
    ("attack_up",     "Attack Up",     0, 10000),
    ("attack_down",   "Attack Down",   0, 10000),
    ("acquire_range", "Acquire Range", 0, 10000),
    ("acquire_up",    "Acquire Up",    0, 10000),
    ("acquire_down",  "Acquire Down",  0, 10000),
]

# Used when a level's stat block has no entry for a type yet. Matches the
# engine defaults in entity_utils so opening the dialog on an untouched
# level shows what the entity is actually running with.
DEFAULTS = {
    "health": 100,
    "attack_power": 5,
    "attack_range": 50,
    "attack_up": 50,
    "attack_down": 50,
    "acquire_range": 1000,
    "acquire_up": 500,
    "acquire_down": 500,
}


def settings_data(game, create=True):
    """The level's single ``entity settings`` entry, created on demand."""
    for data in game.world:
        if isinstance(data, dict) and data.get("type") == "entity settings":
            return data

    if not create:
        return None

    data = {"type": "entity settings"}
    # The loader expects this block first -- that's where prep() looks.
    game.world.insert(0, data)
    return data


def stats_for(game, name):
    """Current stats for one entity type, filled out with defaults."""
    data = settings_data(game, create=False) or {}
    stored = data.get(name) or {}
    merged = dict(DEFAULTS)
    for key, value in stored.items():
        if key in DEFAULTS:
            merged[key] = value
    return merged


def edit(game):
    """Run the two-step stat editor. Returns the edited name, or None."""
    chosen = game.open_field_popup("Entity Stats", [
        {"key": "name", "label": "Entity", "type": "choice",
         "options": list(ENTITY_NAMES), "default": ENTITY_NAMES[0]},
    ])
    name = chosen.get("name", ENTITY_NAMES[0])
    if name not in ENTITY_NAMES:
        return None

    current = stats_for(game, name)
    fields = [
        {"key": key, "label": label, "type": "int",
         "default": int(current[key]), "min": low, "max": high}
        for key, label, low, high in STATS
    ]
    values = game.open_field_popup(f"{name} Stats", fields)

    data = settings_data(game)
    stats = dict(data.get(name) or {})
    for key, _, _, _ in STATS:
        if key in values:
            stats[key] = values[key]
    data[name] = stats

    # Keep the live world in step so the change is visible without a reload.
    if not isinstance(getattr(game, "settings", None), dict):
        game.settings = {}
    game.settings.setdefault("entity", {})
    game.settings["entity"][name] = dict(stats)

    for entity in list(getattr(game, "enemy_list", None) or []):
        if getattr(entity, "name", None) == name:
            for key, value in stats.items():
                setattr(entity, key, value)

    game.changes.add("entities")
    return name
