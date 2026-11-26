"""
difficulty.py
=============
How hard enemies are on a given floor. One place, a few numbers.

Enemy stats start from the level's own ``entity settings`` block (so a
level author still decides what a Warrior is *on that level*), and are then
multiplied once, when the enemy is created:

    health  x (1 + PER_FLOOR_HP     * floors_below_the_first)
    damage  x (1 + PER_FLOOR_DAMAGE * floors_below_the_first)
    health  x (1 + COOP_HP_PER_EXTRA_PLAYER * extra_players)

A level can override or switch this off with a ``_scaling`` entry inside its
``entity settings``:

    "_scaling": {"hp_per_floor": 0.08, "damage_per_floor": 0.05, "off": false}

Only the story folder scales by floor, and only the story gets New Game+
(level/progress.py): co-op levels, My Worlds and test maps keep exactly what
their own ``entity settings`` say, so a world numbered 7 is not "floor 7".

    health, damage  x (1 + 0.5 * loops_finished)          story only

Scaling happens when an enemy is created (and whenever the engine rebuilds
its stats), never per frame. The multipliers are remembered on the enemy
(``_scale``) so ``unscale_enemy`` can take them out again before the level's
settings are re-applied; that keeps repeat calls from compounding.
"""

PER_FLOOR_HP = 0.12
PER_FLOOR_DAMAGE = 0.10
MAX_SCALED_FLOOR = 10            # levels 11+ are test/extra maps and stop scaling here
COOP_HP_PER_EXTRA_PLAYER = 0.25


def enemy_multipliers(level, players=1, overrides=None):
    """(health_mult, damage_mult) for an enemy created on ``level``."""
    overrides = overrides or {}
    if overrides.get("off"):
        return 1.0, 1.0
    floors = max(0, min(int(level), MAX_SCALED_FLOOR) - 1)
    hp = 1.0 + overrides.get("hp_per_floor", PER_FLOOR_HP) * floors
    dmg = 1.0 + overrides.get("damage_per_floor", PER_FLOOR_DAMAGE) * floors
    hp *= 1.0 + COOP_HP_PER_EXTRA_PLAYER * max(0, int(players) - 1)
    return hp, dmg


def unscale_enemy(entity):
    """Undo scale_enemy (call before the base stats are rebuilt)."""
    done = getattr(entity, "_scale", None)
    if not done:
        return
    hp, dmg = done
    entity.health /= hp
    entity.max_health = entity.health
    entity.attack_power /= dmg
    entity._scale = None


def scale_enemy(game, entity, entity_settings=None):
    """Scale an enemy for the current floor. Safe to call repeatedly."""
    if entity.type == "player":
        return
    unscale_enemy(entity)

    story = getattr(game, "level_folder", "story") == "story"
    hp, dmg = enemy_multipliers(
        getattr(game, "level", 1) if story else 1,
        len(getattr(game, "local_players", None) or [1]),
        (entity_settings or {}).get("_scaling"),
    )
    if story:
        from ..level import progress             # local: keeps this module import-light
        loop = progress.get().enemy_multiplier()
        hp *= loop
        dmg *= loop
    if hp == 1.0 and dmg == 1.0:
        return
    entity.health *= hp
    entity.max_health = entity.health           # keep health bars honest
    entity.attack_power *= dmg
    entity._scale = (hp, dmg)
