"""
mods.py
=======
The runtime half of the Entity Editor (ui/entity_editor.py, data/entity_mods.py): what an enemy DOES with the
tweaks the level author gave it.

    apply(entity, data)   once, right after the enemy is built (loader / editor): reads ``data["mods"]``
    tick(entity)          every frame from Entity.manage(): regeneration, burning, rage
    revive(entity)        Second Wind for enemies
    ai(entity)            every frame from ACTIVITY.think(): the dash and the homing-trap dropping
    boss_title(entity)    the name the boss bar and nameplate show

Shop items and shop effects are applied through the very same code the player's shop uses
(``shop_effects.apply_loadout``), so "Bigger Quiver level 3" means the same thing on an Archer boss as it does in
the shop.
"""

import math
import random
import time

from ..data.shop_items import ITEMS_BY_ID
from ..scripts import shop_effects
from ..objects import arrow_trap
from .burn import Burn

DASH_IFRAMES = 0.24


def mods_of(entity):
    return getattr(entity, "mods", None) or {}


def clean(raw):
    """A copy of ``raw`` that is safe to use (dicts where dicts belong)."""
    raw = dict(raw or {})
    raw["fx"] = {k: v for k, v in dict(raw.get("fx") or {}).items() if isinstance(v, (int, float))}
    raw["items"] = {k: int(v) for k, v in dict(raw.get("items") or {}).items() if k in ITEMS_BY_ID and int(v) > 0}
    return raw


# ---------------------------------------------------------------------- #
# apply
# ---------------------------------------------------------------------- #
def apply(entity, data):
    """Give ``entity`` everything its world entry's ``mods`` ask for. Safe to call on an entity with none."""
    data = data or {}
    if data.get("facing") in ("left", "right"):
        entity.direction = data["facing"]
    mods = clean(data.get("mods"))
    entity.mods = mods
    entity._trap_cd = random.uniform(1.5, 4.0)
    entity._dash_cd = random.uniform(1.0, 3.0)
    entity._dash_t = 0.0
    entity._hit_clock = 99.0
    entity._last_hp = entity.health
    entity._raged = False
    entity.dash_dodge = bool(mods.get("dash_dodge", True)) and bool(mods.get("dash"))
    if not any(mods.get(k) for k in mods) and not data.get("facing"):
        return

    boss = bool(mods.get("boss"))
    hp = float(mods.get("health", 0) or 0)
    if hp > 0:
        entity.health = hp
    entity.health *= float(mods.get("health_mult", 1.0))
    if boss:
        entity.health *= float(mods.get("boss_health_mult", 1.0))
    entity.max_health = entity.health

    if float(mods.get("attack_power", 0) or 0) > 0:
        entity.attack_power = float(mods["attack_power"])
    if boss:
        entity.attack_power *= float(mods.get("boss_attack_mult", 1.0))
    reach = float(mods.get("attack_range_mult", 1.0))
    for key in ("attack_range", "attack_up", "attack_down"):
        setattr(entity, key, getattr(entity, key) * reach)
    entity.acquire_range *= float(mods.get("acquire_range_mult", 1.0))
    if int(mods.get("knockback_power", 0) or 0) > 0:
        entity.knockback_power = int(mods["knockback_power"])
    entity.crit_chance = float(mods.get("crit_chance", 0.0))
    entity.crit_bonus = float(mods.get("crit_bonus", 0.75))
    entity.regen = float(mods.get("regen", 0.0))
    entity.regen_delay = float(mods.get("regen_delay", 3.0))

    # shop items + raw shop effects, through the shop's own rules
    entity.upgrades, entity.boosts = {}, set()
    for item_id, level in mods["items"].items():
        item = ITEMS_BY_ID[item_id]
        if item["kind"] == "boost":
            entity.boosts.add(item_id)
        else:
            entity.upgrades[item_id] = min(level, len(item["prices"]))
    entity.extra_effects = dict(mods["fx"])
    if entity.upgrades or entity.boosts or entity.extra_effects:
        shop_effects.apply_loadout(entity, heal_gain=True)
        entity.max_health = max(entity.max_health, entity.health)

    if boss:
        entity.is_boss = True
    entity.boss_title = str(mods.get("boss_title", "") or "").strip() if boss else ""


def boss_title(entity):
    title = getattr(entity, "boss_title", "")
    return title or str(getattr(entity, "name", "BOSS"))


# ---------------------------------------------------------------------- #
# per frame
# ---------------------------------------------------------------------- #
def tick(entity):
    """Regeneration, burning and rage. Cheap when an entity has none of them."""
    burning = Burn.active(entity) and entity.burn.left > 0
    regen = getattr(entity, "regen", 0.0)
    rage = (getattr(entity, "mods", None) or {}).get("rage_below", 0.0)
    if not (burning or regen or rage):
        return
    dt = entity.game.dt
    if dt <= 0 or entity.dead or entity.death:
        return

    if entity.health < getattr(entity, "_last_hp", entity.health):
        entity._hit_clock = 0.0
    else:
        entity._hit_clock = getattr(entity, "_hit_clock", 99.0) + dt
    if regen > 0 and entity.health < entity.max_health and entity._hit_clock >= getattr(entity, "regen_delay", 3.0):
        entity.health = min(entity.max_health, entity.health + regen * dt)

    if burning:
        Burn.tick(entity, dt)
    entity._last_hp = entity.health

    if rage and not getattr(entity, "_raged", False) and entity.health <= entity.max_health * rage:
        mult = float((entity.mods or {}).get("rage_mult", 1.5))
        entity._raged = True
        entity.attack_power *= mult
        entity.speed *= 1 + (mult - 1) * 0.3
        entity.walk_speed *= 1 + (mult - 1) * 0.3
        try:
            from ..ui import combat_fx
            combat_fx.fx().banner(entity, "ENRAGED", (255, 90, 80), life=1.3)
        except Exception:
            pass


def revive(entity):
    """Second Wind for an enemy that just ran out of health. True = it stood back up."""
    if entity.type != "enemy" or entity.health > 0:
        return False
    if shop_effects.stat(entity, "second_wind") <= getattr(entity, "second_winds_used", 0):
        return False
    entity.second_winds_used += 1
    entity.health = entity.max_health * 0.5
    entity._last_hp = entity.health
    try:
        from ..ui import combat_fx
        combat_fx.fx().banner(entity, "SECOND WIND", (190, 230, 255), life=1.2)
    except Exception:
        pass
    return True


# ---------------------------------------------------------------------- #
# AI
# ---------------------------------------------------------------------- #
def _sign(v):
    return 1 if v >= 0 else -1


def _incoming(entity):
    """A hostile arrow / bomb heading our way, close by."""
    game = entity.game
    for proj in getattr(game.bombs, "list", ()):
        owner = getattr(proj, "owner", None)
        if owner is None or proj.dead or getattr(proj, "stuck", False) or owner.color == entity.color:
            continue
        dx = entity.rect.centerx - proj.rect.centerx
        dy = abs(entity.rect.centery - proj.rect.centery)
        if abs(dx) < 260 and dy < 160 and dx * (proj.x_vel or 0) > 0:
            return True
    return False


def _start_dash(entity, direction):
    m = entity.mods
    entity.dashing = True
    entity.startx = entity.rect.x
    entity._dash_dir = direction
    entity._dash_t = (float(m.get("dash_len", 0.35)) + shop_effects.stat(entity, "dash_time")) * 1.0
    entity._dash_cd = float(m.get("dash_cooldown", 4.0)) / (1.0 + shop_effects.stat(entity, "dash_regen"))
    if entity.dash_dodge:
        entity._fx_iframes_until = time.perf_counter() + DASH_IFRAMES


def ai_pre(entity):
    """Runs before the normal AI each frame. True = a dash is in progress and owns this frame."""
    m = getattr(entity, "mods", None)
    if not m or not m.get("dash") or entity.dead or entity.death:
        return False
    dt = entity.game.dt
    if entity.dashing and getattr(entity, "_dash_t", 0.0) > 0:
        entity._dash_t -= dt
        if entity._dash_t <= 0 or entity.hit_wall:
            entity.dashing = False
            return False
        (entity.move_right if entity._dash_dir > 0 else entity.move_left)(entity.current_speed)
        return True
    entity._dash_cd = getattr(entity, "_dash_cd", 0.0) - dt
    target = entity.target
    if entity._dash_cd > 0 or target is None or not entity.has_target or entity.zone:
        return False
    mode = m.get("dash_mode", "both")
    dx = target.rect.centerx - entity.rect.centerx
    dist = abs(dx)
    want = 0
    if mode in ("evade", "both") and entity.on_ground:
        if _incoming(entity) or (dist < 90 and entity.name in ("Archer", "TNT")):
            want = -_sign(dx)
    if not want and mode in ("chase", "both") and entity.on_ground:
        if entity.attack_range * 1.3 < dist < max(400.0, entity.acquire_range * 0.55):
            want = _sign(dx)
    if want:
        _start_dash(entity, want)
        (entity.move_right if want > 0 else entity.move_left)(entity.current_speed)
        return True
    entity._dash_cd = 0.25                                # look again in a moment, not every frame
    return False


def _trap_center(entity, target, mode):
    dx = target.rect.centerx - entity.rect.centerx
    if mode == "mixed":
        mode = "ward" if abs(dx) < 260 else random.choice(("ahead", "target"))
    if mode == "target":
        return target.rect.centerx, target.rect.centery
    if mode == "ward":
        return entity.rect.centerx + _sign(dx) * 90, entity.rect.centery
    lead = getattr(target, "x_vel", 0) or (140 if getattr(target, "direction", "right") == "right" else -140)
    lead = max(-220, min(220, lead * 0.6))
    return target.rect.centerx + lead, target.rect.centery


def ai(entity):
    """Runs while the entity has a target: drops a homing trap when it is allowed to."""
    m = getattr(entity, "mods", None)
    if not m or not m.get("trap") or entity.dead or entity.death:
        return
    entity._trap_cd = getattr(entity, "_trap_cd", 0.0) - entity.game.dt
    target = entity.target
    if entity._trap_cd > 0 or target is None or getattr(target, "nature", None) != "entity":
        return
    if abs(target.rect.centerx - entity.rect.centerx) > float(m.get("trap_range", 900)):
        return
    if arrow_trap.live_count(entity.game, entity) >= int(m.get("trap_max", 2)):
        entity._trap_cd = 0.5
        return
    entity._trap_cd = float(m.get("trap_cooldown", 8.0))
    cfg = {"arrows": int(m.get("trap_arrow_count", 3)), "radius": int(m.get("trap_radius", 110)),
           "lifetime": float(m.get("trap_lifetime", 18.0))}
    arrow_trap.drop(entity.game, entity, _trap_center(entity, target, m.get("trap_mode", "ahead")), trap_cfg=cfg)
