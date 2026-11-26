"""
entity_mods.py
==============
Everything the ENTITY EDITOR (ui/entity_editor.py) offers, as data. Pure tables: add a field here and it appears
in the window, is saved into the level, and is read by entities/mods.py - no window code to touch.

An enemy's world entry looks like this (everything under "mods" is optional; only what differs from the default
is ever written):

    {"type": "enemy", "name": "Archer", "color": "Red", "x": .., "y": .., "posted": false, ...,
     "mods": {
         "health": 600, "regen": 4, "boss": true, "boss_title": "The Hollow Warden",
         "dash": true, "trap": true,
         "fx":    {"homing": 1, "arrow_bonus": 2, "speed_mult": 0.15},      # raw SHOP EFFECTS (data/shop_items.py)
         "items": {"quiver": 3, "piercing_tips": 2}                          # SHOP ITEMS by id -> level
     }}

A field is:  key, label, type (int | float | bool | choice | text), default, min, max, step, unit, scale, hint, store
    store  "data"  top level of the entry (placement)
           "mods"  inside "mods"
           "fx"    inside "mods"."fx" - a raw shop effect, added on top of whatever the entity's items give
    scale  what the stored number is multiplied by for display (0.15 stored shows as 15 with scale 100, unit "%")
"""

from .shop_items import SHOP_ITEMS, TABS, tab_of

# ---------------------------------------------------------------------- #
# categories (the left column of the window) in display order
# ---------------------------------------------------------------------- #
# (id, label, accent colour, one-line blurb)
CATEGORIES = [
    ("place",    "PLACEMENT",       (122, 200, 255), "Where it stands and how it moves around the level."),
    ("health",   "HEALTH",          (110, 220, 130), "Hit points, healing, shields and the will to keep going."),
    ("combat",   "COMBAT",          (255, 112, 92),  "How hard it hits, how far it reaches, how it fights."),
    ("arrows",   "ARROWS & AMMO",   (255, 202, 80),  "Arrow properties. Its volleys AND the traps it drops use these."),
    ("move",     "MOVEMENT & DASH", (150, 220, 255), "Speed, jumps and the dash."),
    ("trap",     "HOMING TRAPS",    (240, 150, 40),  "Lets it drop homing-arrow traps that circle a spot and shoot whatever passes."),
    ("boss",     "BOSS",            (255, 210, 70),  "A title, a boss bar and a bigger fight."),
]

ITEM_CATEGORIES = [
    ("i_upgrades",    "UPGRADES",  (255, 120, 110), "Permanent shop upgrades (ruby)."),
    ("i_perks",       "PERKS",     (110, 220, 140), "Run perks (emerald)."),
    ("i_rare",        "RARE",      (240, 150, 200), "One-of-a-kind items (pearl)."),
    ("i_arsenal",     "ARSENAL",   (255, 202, 80),  "Arrows, fire, bombs and traps."),
    ("i_boosts",      "BOOSTS",    (255, 214, 120), "One-level boosts (gold)."),
]

TAB_TO_ITEM_CATEGORY = {"upgrades": "i_upgrades", "perks": "i_perks", "rare": "i_rare",
                        "arsenal": "i_arsenal", "consumables": "i_boosts"}

# ---------------------------------------------------------------------- #
# the fields
# ---------------------------------------------------------------------- #
def _f(key, label, type_, default, store="mods", **kw):
    field = {"key": key, "label": label, "type": type_, "default": default, "store": store}
    field.update(kw)
    return field


FIELDS = {
    "place": [
        _f("x", "X", "int", 0, "data", hint="Nudge inside its 64 px cell."),
        _f("y", "Y", "int", 0, "data"),
        _f("facing", "Faces", "choice", "left", "data", options=["left", "right"], hint="The way it looks until it spots someone."),
        _f("posted", "Posted", "bool", False, "data", hint="Never leaves this spot, whatever happens."),
        _f("patroller", "Patroller", "bool", False, "data", hint="Walks back and forth around where it spawned."),
        _f("patrol_range_x", "Patrol range X", "int", 1000, "data", min=64, max=2000, step=64, unit="px"),
        _f("patrol_range_y", "Patrol range Y", "int", 1000, "data", min=64, max=2000, step=64, unit="px"),
        _f("acquire_range_mult", "Sight range", "float", 1.0, min=0.2, max=4.0, step=0.1, unit="x",
           hint="Multiplies how far it notices targets."),
    ],
    "health": [
        _f("health", "Health", "int", 0, min=0, max=100000, step=10, hint="0 = the type's normal health."),
        _f("health_mult", "Health multiplier", "float", 1.0, min=0.1, max=50.0, step=0.25, unit="x"),
        _f("max_health", "Bonus max HP", "int", 0, "fx", min=0, max=100000, step=10, hint="Shop effect: Vitality / Abyssal Heart."),
        _f("regen", "Regeneration", "float", 0.0, min=0.0, max=500.0, step=0.5, unit="hp/s"),
        _f("regen_delay", "Regen starts after", "float", 3.0, min=0.0, max=30.0, step=0.5, unit="s",
           hint="Seconds without being hit before it heals."),
        _f("damage_cut", "Damage reduction", "float", 0.0, "fx", min=0.0, max=0.6, step=0.05, scale=100, unit="%",
           hint="Shop effect: Iron Skin. Capped at 60%."),
        _f("shield_hits", "Shield bubble", "int", 0, "fx", min=0, max=50, step=1, unit="hits",
           hint="Hits it swallows whole before taking damage."),
        _f("second_wind", "Second wind", "int", 0, "fx", min=0, max=5, step=1, unit="lives",
           hint="Stands back up at half health this many times."),
        _f("lifesteal", "Lifesteal", "float", 0.0, "fx", min=0.0, max=1.0, step=0.05, scale=100, unit="%",
           hint="Share of max HP healed per kill."),
        _f("rage_below", "Rage below", "float", 0.0, min=0.0, max=0.9, step=0.05, scale=100, unit="% hp",
           hint="Once its health drops under this, it enrages. 0 = never."),
        _f("rage_mult", "Rage strength", "float", 1.5, min=1.0, max=5.0, step=0.1, unit="x",
           hint="Damage and speed multiplier while enraged."),
    ],
    "combat": [
        _f("attack_power", "Attack power", "float", 0.0, min=0.0, max=10000.0, step=1.0, hint="0 = the type's normal damage."),
        _f("attack_mult", "Damage bonus", "float", 0.0, "fx", min=0.0, max=20.0, step=0.1, scale=100, unit="%",
           hint="Shop effect: Might / War Drum."),
        _f("attack_range_mult", "Reach", "float", 1.0, min=0.2, max=4.0, step=0.1, unit="x",
           hint="Multiplies how close/far it can strike from."),
        _f("reload_cut", "Attack speed", "float", 0.0, "fx", min=0.0, max=0.6, step=0.05, scale=100, unit="% faster",
           hint="Shop effect: Quick Hands. Shortens the delay between attacks."),
        _f("knockback_power", "Knockback", "int", 0, min=0, max=5000, step=25, hint="0 = the normal shove."),
        _f("crit_chance", "Crit chance", "float", 0.0, min=0.0, max=1.0, step=0.05, scale=100, unit="%"),
        _f("crit_bonus", "Crit damage", "float", 0.75, min=0.0, max=5.0, step=0.25, scale=100, unit="% extra"),
        _f("thorns", "Thorns", "float", 0.0, "fx", min=0.0, max=0.9, step=0.05, scale=100, unit="%",
           hint="Share of melee damage reflected at its attacker."),
    ],
    "arrows": [
        _f("arrow_bonus", "Extra arrows / volley", "int", 0, "fx", min=0, max=30, step=1, hint="Shop effect: Bigger Quiver."),
        _f("pierce", "Pierce", "int", 0, "fx", min=0, max=20, step=1, unit="enemies", hint="Shop effect: Piercing Tips."),
        _f("homing", "Homing arrows", "bool", False, "fx", hint="Shop effect: Homing Arrows. Arrows curve to a target."),
        _f("arrow_damage_mult", "Arrow damage", "float", 1.0, min=0.1, max=20.0, step=0.1, unit="x"),
        _f("arrow_speed_mult", "Arrow speed", "float", 1.0, min=0.3, max=4.0, step=0.1, unit="x"),
        _f("arrow_knockback_mult", "Arrow knockback", "float", 1.0, min=0.0, max=10.0, step=0.25, unit="x"),
        _f("arrow_burn", "Arrow burn", "float", 0.0, min=0.0, max=30.0, step=0.5, unit="s",
           hint="Seconds a victim keeps burning. Applies to traps too."),
        _f("fire_bonus", "Extra fires / cast", "int", 0, "fx", min=0, max=30, step=1, hint="Shop effect: Ember Stock (Torch)."),
        _f("hot_coals", "Hot coals", "int", 0, "fx", min=0, max=10, step=1, hint="Fire burns longer and hotter."),
        _f("bomb_bonus", "Extra bombs / throw", "int", 0, "fx", min=0, max=30, step=1, hint="Shop effect: Bomb Bag (TNT)."),
        _f("bomb_cap", "Bombs alive at once", "int", 0, "fx", min=0, max=40, step=1, unit="extra"),
        _f("blast_radius", "Blast radius", "int", 0, "fx", min=0, max=300, step=10, unit="px"),
    ],
    "move": [
        _f("speed_mult", "Run speed", "float", 0.0, "fx", min=-0.5, max=3.0, step=0.05, scale=100, unit="%",
           hint="Shop effect: Swiftness."),
        _f("jump_mult", "Jump height", "float", 0.0, "fx", min=-0.5, max=2.0, step=0.05, scale=100, unit="%",
           hint="Shop effect: Spring Boots."),
        _f("extra_jumps", "Air jumps", "int", 0, "fx", min=0, max=5, step=1, hint="Shop effect: Cloud Step."),
        _f("dash", "Can dash", "bool", False, hint="Lets it dash toward or away from its target."),
        _f("dash_mode", "Dash style", "choice", "both", options=["chase", "evade", "both"],
           hint="chase = closes gaps, evade = leaps out of danger."),
        _f("dash_len", "Dash length", "float", 0.35, min=0.1, max=2.0, step=0.05, unit="s"),
        _f("dash_cooldown", "Dash cooldown", "float", 4.0, min=0.3, max=60.0, step=0.5, unit="s"),
        _f("dash_dodge", "Dash dodges hits", "bool", True, hint="The first moments of a dash can't be hurt (like a player's)."),
    ],
    "trap": [
        _f("trap", "Drops homing traps", "bool", False, hint="Only entities set to do this ever place one."),
        _f("trap_mode", "Where it drops them", "choice", "ahead", options=["ahead", "target", "ward", "mixed"],
           hint="ahead = where the target is heading, target = on them, ward = around itself, mixed = any."),
        _f("trap_max", "Traps out at once", "int", 2, min=1, max=10, step=1),
        _f("trap_cooldown", "Cooldown", "float", 8.0, min=1.0, max=120.0, step=0.5, unit="s"),
        _f("trap_range", "Drops when target within", "int", 900, min=100, max=3000, step=50, unit="px"),
        _f("trap_arrow_count", "Arrows per trap", "int", 3, min=1, max=12, step=1,
           hint="Plus the arrow bonus its arrow properties give."),
        _f("trap_radius", "Swing radius", "int", 110, min=40, max=400, step=10, unit="px"),
        _f("trap_lifetime", "Lasts", "float", 18.0, min=3.0, max=120.0, step=1.0, unit="s"),
    ],
    "boss": [
        _f("boss", "Is a boss", "bool", False, hint="Gets a gold marker, a nameplate, and the boss bar if the level's goal is a boss fight."),
        _f("boss_title", "Boss title", "text", "", hint="Shown on the boss bar and over its head. Blank = its name."),
        _f("boss_health_mult", "Boss health", "float", 1.0, min=0.1, max=50.0, step=0.5, unit="x"),
        _f("boss_attack_mult", "Boss damage", "float", 1.0, min=0.1, max=20.0, step=0.1, unit="x"),
    ],
}

# What "Boss kit" fills in for each type (the button in the BOSS category). Applied on top of what is already set.
BOSS_KITS = {
    "Archer": {"boss": True, "health_mult": 1.0, "boss_health_mult": 6.0, "boss_attack_mult": 1.3, "regen": 2.0,
               "rage_below": 0.35, "rage_mult": 1.4, "dash": True, "dash_mode": "evade", "trap": True, "trap_mode": "mixed",
               "trap_max": 3, "fx": {"homing": 1, "arrow_bonus": 2, "pierce": 1}},
    "TNT": {"boss": True, "boss_health_mult": 6.0, "boss_attack_mult": 1.3, "rage_below": 0.35, "dash": True,
            "dash_mode": "chase", "fx": {"bomb_bonus": 3, "bomb_cap": 4, "blast_radius": 30}},
    "Torch": {"boss": True, "boss_health_mult": 6.0, "boss_attack_mult": 1.3, "rage_below": 0.35, "dash": True,
              "fx": {"fire_bonus": 3, "hot_coals": 2}},
    "Warrior": {"boss": True, "boss_health_mult": 7.0, "boss_attack_mult": 1.4, "rage_below": 0.35, "dash": True,
                "dash_mode": "chase", "fx": {"thorns": 0.15, "damage_cut": 0.15}},
    "Pawn": {"boss": True, "boss_health_mult": 8.0, "boss_attack_mult": 1.5, "rage_below": 0.35, "dash": True,
             "fx": {"damage_cut": 0.1}},
}

# ---------------------------------------------------------------------- #
# shop items an entity may be granted
# ---------------------------------------------------------------------- #
# Items that only make sense for a player carrying a wallet / minimap / charms.
PLAYER_ONLY_ITEMS = {
    "heal_small", "heal_full", "befriend_charm", "charm_duration", "charm_bond", "charm_range", "charm_limit",
    "target_pointers", "minimap", "treasure_radar", "magnet", "lucky_clover", "homing_trap",
}


def grantable_items():
    """The shop items that can be granted to an entity, in shop order, each tagged with its editor category."""
    out = []
    for item in SHOP_ITEMS:
        if item["id"] in PLAYER_ONLY_ITEMS:
            continue
        if item["kind"] not in ("level", "boost"):
            continue
        cat = TAB_TO_ITEM_CATEGORY.get(tab_of(item))
        if cat is None:
            continue
        out.append({"id": item["id"], "name": item["name"], "desc": item["desc"], "currency": item["currency"],
                    "kind": item["kind"], "max": len(item["prices"]) if item["kind"] == "level" else 1, "cat": cat})
    return out


def all_categories():
    return CATEGORIES + ITEM_CATEGORIES


# ---------------------------------------------------------------------- #
# the Homing Arrow Trap (placed by the level editor, no owner): its effects are set by hand
# ---------------------------------------------------------------------- #
TRAP_CATEGORIES = [
    ("effects", "ARROW EFFECTS", (255, 112, 92),  "What one arrow does to whoever it hits."),
    ("swing",   "SWING",         (240, 150, 40),  "How many arrows revolve around the spot and how wide they swing."),
    ("rules",   "RULES",         (110, 220, 130), "Who it hurts and how long it lasts."),
]

TRAP_FIELDS = {
    "effects": [
        _f("damage", "Damage per hit", "float", 12.0, "data", min=0.0, max=1000.0, step=1.0, unit="hp"),
        _f("knockback", "Knockback", "int", 160, "data", min=0, max=3000, step=20),
        _f("burn", "Burn", "float", 0.0, "data", min=0.0, max=30.0, step=0.5, unit="s",
           hint="Seconds a victim keeps burning after a hit."),
        _f("pierce", "Hits before an arrow is spent", "int", 0, "data", min=0, max=50, step=1,
           hint="0 = never spent: it keeps revolving forever."),
        _f("hit_gap", "Same-victim gap", "float", 0.55, "data", min=0.05, max=5.0, step=0.05, unit="s",
           hint="How soon an arrow can hurt the same victim again."),
    ],
    "swing": [
        _f("arrows", "Arrows", "int", 3, "data", min=1, max=12, step=1),
        _f("radius", "Swing radius", "int", 110, "data", min=40, max=500, step=10, unit="px"),
        _f("speed", "Arrow speed", "int", 420, "data", min=100, max=1200, step=20, unit="px/s"),
    ],
    "rules": [
        _f("hurt_players", "Hurts players", "bool", True, "data"),
        _f("hurt_enemies", "Hurts enemies", "bool", True, "data"),
        _f("lifetime", "Lasts", "float", 0.0, "data", min=0.0, max=600.0, step=1.0, unit="s", hint="0 = for the whole level."),
    ],
}
