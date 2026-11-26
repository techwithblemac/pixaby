"""
shop_effects.py
===============
The rules of the shop, with no drawing in it: what things cost, whether a
purchase is allowed, and how what a player owns turns into real stats.

State lives on the Player so it survives from level to level:

    player.upgrades   {item_id: level}   permanent for the run
    player.boosts     {item_id, ...}     one-level boosts, cleared by the shop
    player.<x>_coins  the four wallets (filled by Treasure pick-ups)

How stats are applied
---------------------
Stats are *derived*, never stored twice. ``apply_loadout`` writes the
bonuses onto the player and remembers exactly what it added
(``_shop_applied``); ``strip_loadout`` takes precisely that back out.
Entity.personalise() calls strip first and apply last, so every time the
engine rebuilds a player's base stats (each level load) the bonuses are
re-added exactly once instead of stacking.
"""

import math

from ..data.shop_items import ITEMS_BY_ID, WALLET_ATTR
from ..data import charms as C

_ZERO = {
    "max_health": 0, "attack_mult": 0.0, "speed_mult": 0.0, "jump_mult": 0.0,
    "damage_cut": 0.0, "lifesteal": 0.0, "coin_magnet": 0,
    # counts / levels that live in ``player.shop_stats`` (never written to the player twice)
    "minimap_level": 0, "pointer_level": 0,
    "arrow_bonus": 0, "fire_bonus": 0, "bomb_bonus": 0, "bomb_cap": 0,
    "reload_cut": 0.0, "blast_radius": 0.0, "pierce": 0,
    "charm_duration": 0, "charm_range": 0, "charm_limit": 0,
    "dash_cd_cut": 0.0, "extra_jumps": 0, "luck": 0.0,
    "charm_bond": 0, "dash_time": 0.0, "dash_regen": 0.0,
    "homing": 0, "hot_coals": 0, "thorns": 0.0, "shield_hits": 0, "second_wind": 0, "treasure_radar": 0,
    "trap_arrows": 0, "trap_time": 0,
}
# the _ZERO keys above that are read through ``stat()`` instead of being applied to the player
STAT_KEYS = tuple(list(_ZERO)[7:])
MAX_DAMAGE_CUT = 0.6


def wallet(player, currency):
    return getattr(player, WALLET_ATTR[currency], 0)


def owned_level(player, item_id):
    """Level of an owned ``level`` item (0 = not owned). Derived from ``player.upgrades``."""
    return player.upgrades.get(item_id, 0)


def stat(player, key, default=0):
    """A derived shop stat (see STAT_KEYS), e.g. ``stat(p, "arrow_bonus")``."""
    return getattr(player, "shop_stats", {}).get(key, default)


def level_of(player, item):
    return player.upgrades.get(item["id"], 0)


def max_level(item):
    return len(item["prices"]) if item["kind"] == "level" else 1


def readout(player, item):
    """"Arrows per volley 3 > 4" for items that declare a ``readout`` (None when maxed or none)."""
    spec = item.get("readout")
    if not spec or item["kind"] != "level" or level_of(player, item) >= max_level(item):
        return None
    label, base, key = spec[0], spec[1], spec[2]
    scale = spec[3] if len(spec) > 3 else 1
    unit = spec[4] if len(spec) > 4 else ""
    gain = next(iter(item["effects"].values()))
    now = base + stat(player, key) * scale
    nxt = base + (stat(player, key) + gain) * scale

    def fmt(v):
        return f"{int(round(v))}" if abs(v - round(v)) < 1e-6 or unit else f"{v:g}"
    return f"{label} {fmt(now)}{unit} > {fmt(nxt)}{unit}"


def second_wind_ready(player):
    """A free revive is still available this run."""
    return stat(player, "second_wind") > getattr(player, "second_winds_used", 0)


def drop_bonus(game, value):
    """Extra coins from a fallen enemy worth ``value`` (Lucky Clover, best of the local players)."""
    import random
    luck = max([stat(p, "luck", 0.0) for p in (getattr(game, "local_players", None) or [])] or [0.0])
    if luck <= 0 or value <= 0:
        return 0
    whole = value * luck
    return int(whole) + (1 if random.random() < whole - int(whole) else 0)


def stock_of(player, item):
    """How many of a ``charm``-kind item the player carries."""
    return getattr(player, item["stock"], 0)


def stock_cap(player, item):
    """Most of a ``charm``-kind item the player may carry."""
    return item.get("cap", 99) + (stat(player, item["cap_stat"]) if item.get("cap_stat") else 0)


def quick_price(player, item):
    """The premium price of ONE unit, as asked by the quick-buy popup."""
    unit = price(player, item) / max(1, item.get("stack", 1))
    return max(1, math.ceil(unit * C.QUICK_BUY_MULT))


def price(player, item):
    """What the next purchase of this item costs (None if sold out)."""
    if item["kind"] == "charm":
        bought = getattr(player, "bought", {}).get(item["id"], 0)
        return item["prices"][min(bought, len(item["prices"]) - 1)]
    if item["kind"] == "level":
        lvl = level_of(player, item)
        return item["prices"][lvl] if lvl < len(item["prices"]) else None
    return item["prices"][0]


def status(player, item):
    """(can_buy, label) - label explains why not, for the shop to show."""
    cost = price(player, item)
    if cost is None:
        return False, "MAX"
    if item["kind"] == "heal" and player.health >= player.max_health:
        return False, "FULL"
    if item["kind"] == "boost" and item["id"] in player.boosts:
        return False, "ACTIVE"
    if item["kind"] == "charm" and stock_of(player, item) >= stock_cap(player, item):
        return False, "FULL"
    if getattr(player, "dead", False):
        return False, "DEAD"
    if wallet(player, item["currency"]) < cost:
        return False, "NEED MORE"
    return True, ""


def buy(player, item):
    """Try to buy. Returns (ok, message)."""
    ok, why = status(player, item)
    if not ok:
        return False, {"MAX": f"{item['name']} is maxed out.",
                       "FULL": "You are already carrying the most you can.",
                       "ACTIVE": f"{item['name']} is already active.",
                       "DEAD": "Can't shop while dead.",
                       "NEED MORE": f"Not enough {item['currency']}."}[why]

    cost = price(player, item)
    attr = WALLET_ATTR[item["currency"]]
    setattr(player, attr, getattr(player, attr) - cost)
    from . import achievements                     # lazy: keeps this module importable on its own
    achievements.tracker().on_spend(player, cost)

    if item["kind"] == "heal":
        player.health = min(player.max_health, player.health + player.max_health * item["heal_pct"])
        return True, f"{item['name']}: healed."
    if item["kind"] == "charm":
        add_stock(player, item, item.get("stack", 1))
        player.bought[item["id"]] = player.bought.get(item["id"], 0) + 1
        return True, f"{item['name']}: stocked."
    if item["kind"] == "boost":
        player.boosts.add(item["id"])
        apply_loadout(player)
        return True, f"{item['name']} will last the next level."

    player.upgrades[item["id"]] = level_of(player, item) + 1
    apply_loadout(player, heal_gain=True)
    if item["id"] in ("quiver", "ember_stock", "bomb_bag") and level_of(player, item) >= max_level(item):
        achievements.tracker().on_max_ammo_upgrade(player)
    return True, f"{item['name']} upgraded."


def add_stock(player, item, n):
    """Add ``n`` to a charm-kind stock, never past the cap. Returns how many were really added."""
    have = stock_of(player, item)
    new = min(stock_cap(player, item), have + n)
    setattr(player, item["stock"], new)
    return new - have


# ------------------------------------------------------------------ #
# Turning what is owned into stats
# ------------------------------------------------------------------ #

def total_effects(player):
    """Sum every owned upgrade level and active boost into one dict."""
    total = dict(_ZERO)
    for item_id, lvl in player.upgrades.items():
        item = ITEMS_BY_ID.get(item_id)
        for key, amount in (item or {}).get("effects", {}).items():
            total[key] += amount * lvl
    for item_id in player.boosts:
        item = ITEMS_BY_ID.get(item_id)
        for key, amount in (item or {}).get("effects", {}).items():
            total[key] += amount
    # raw effects granted by the level editor's Entity Editor (data/entity_mods.py); players have none
    for key, amount in (getattr(player, "extra_effects", None) or {}).items():
        if key in total:
            total[key] += amount
    total["damage_cut"] = min(total["damage_cut"], MAX_DAMAGE_CUT)
    return total


def strip_loadout(player):
    """Remove exactly what apply_loadout added."""
    player.shop_stats = {}
    done = player._shop_applied
    if not done:
        return
    player.max_health -= done["max_health"]
    player.attack_power /= 1 + done["attack_mult"]
    player.speed /= 1 + done["speed_mult"]
    player.jump_vel /= 1 + done["jump_mult"]
    player.current_speed = player.speed
    player.current_jump = player.jump_vel
    player.damage_taken_mult = 1.0
    player.lifesteal = 0.0
    player.coin_magnet = 0
    player._shop_applied = {}


def apply_loadout(player, heal_gain=False):
    """(Re)apply everything the player owns. Safe to call any time."""
    old_hp_bonus = player._shop_applied.get("max_health", 0) if player._shop_applied else 0
    strip_loadout(player)
    fx = total_effects(player)

    player.max_health += fx["max_health"]
    if heal_gain and fx["max_health"] > old_hp_bonus:
        # a new max-HP upgrade also fills the HP it just added
        player.health = min(player.max_health, player.health + fx["max_health"] - old_hp_bonus)
    player.health = min(player.health, player.max_health)

    player.attack_power *= 1 + fx["attack_mult"]
    player.speed *= 1 + fx["speed_mult"]
    player.jump_vel *= 1 + fx["jump_mult"]
    player.current_speed = player.speed
    player.current_jump = player.jump_vel

    player.damage_taken_mult = 1.0 - fx["damage_cut"]
    player.lifesteal = fx["lifesteal"]
    player.coin_magnet = fx["coin_magnet"]
    player._shop_applied = {k: fx[k] for k in ("max_health", "attack_mult", "speed_mult", "jump_mult")}
    player.shop_stats = {k: fx[k] for k in STAT_KEYS}
    player.shield_left = int(fx["shield_hits"])         # Shield Bubble: hits it will still absorb this floor

    # Treasure only has to look for magnet targets when someone has one.
    game = getattr(player, "game", None)
    if game is not None:
        slots = getattr(game, "player_slots", None) or [player]
        game.coin_magnet_radius = max(getattr(p, "coin_magnet", 0) for p in slots)


def reset_run(players):
    """New run: forget every purchase and give the stats back."""
    from . import charm_mode        # lazy: charm_mode imports this module
    from . import achievements
    from . import coop_loot
    achievements.tracker().on_run_reset()
    for player in players:
        charm_mode.release_all(player)
        charm_mode.cancel(player, refund=False)
        strip_loadout(player)
        player.upgrades.clear()
        player.boosts.clear()
        player.bought.clear()
        player.second_winds_used = 0
        player.charms, player.dashes = C.START_CHARMS, C.START_DASHES
        player.traps = 0
        player.dash_energy = None                       # a new run starts with a full dash bar (scripts/dash_bar.py)
        coop_loot.reset_player(player)          # co-op: kill count / milestones, and the co-op starting charms
        apply_loadout(player)
