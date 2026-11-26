"""
coop_loot.py
============
The rules of loot in local co-op worlds (see data/coop_items.py for every number). No drawing here: the pick-up
object itself is ``objects.Pickup``.

Where power-ups come from when there is no shop
-----------------------------------------------
    drops      a fallen enemy sometimes leaves a generic power-up (``maybe_drop``)
    scatter    a few lie in random places when a level loads (``on_level_loaded``)
    kills      hero-specific upgrades are earned by kill milestones (``on_kill``), never found
    charms     the Befriend Charm only exists where the author placed one in the level editor
    dashes     free forever (charm_mode.dash_rules_apply is story-only)

A pick-up is applied exactly like a shop purchase: ``player.upgrades`` / ``player.boosts`` and then
``shop_effects.apply_loadout``, so every stat, HUD readout and "restart level" snapshot already understands it.
"""

import random

import pygame

from ..data import coop_items as D
from ..data.shop_items import ITEMS_BY_ID
from . import paths
from . import shop_effects as rules

GOLD = (255, 202, 80)
MINT = (108, 201, 117)
PINK = (255, 130, 190)
GREY = (190, 190, 205)


# ====================================================================== #
# when does this apply
# ====================================================================== #
def active(game):
    """Local co-op world: the co-op folder, on this machine (not the network), not the editor."""
    return (getattr(game, "level_folder", None) == paths.MULTIPLAYER
            and not getattr(game, "MULTIPLAYER", False)
            and not getattr(game, "EDIT_WORLD", False))


def item_id(name):
    """The shop item a pick-up named ``name`` stands for ("charm" is the Befriend Charm)."""
    return D.CHARM_ITEM if name == D.CHARM_NAME else name


def title(name):
    return ITEMS_BY_ID[item_id(name)]["name"]


# ====================================================================== #
# picking up
# ====================================================================== #
def can_collect(player, name):
    """False when the pick-up would be wasted on this player (full health, maxed level, full charm stock):
    it stays on the floor for a teammate."""
    item = ITEMS_BY_ID.get(item_id(name))
    if item is None or getattr(player, "dead", False) or getattr(player, "death", False):
        return False
    kind = item["kind"]
    if kind == "heal":
        return player.health < player.max_health
    if kind == "charm":
        return rules.stock_of(player, item) < rules.stock_cap(player, item)
    if kind == "boost":
        return item["id"] not in player.boosts
    return rules.level_of(player, item) < rules.max_level(item)


def unusable_note(player, name):
    """The banner line for a pick-up this player cannot use ('MAXED OUT', 'HEALTH IS FULL' ...), or None when
    it is usable, or when the player is dead (a dead player is simply not a pick-up candidate)."""
    item = ITEMS_BY_ID.get(item_id(name))
    if item is None or can_collect(player, name):
        return None
    if getattr(player, "dead", False) or getattr(player, "death", False):
        return None
    return D.UNUSABLE_NOTES.get(item["kind"], D.UNUSABLE_NOTES["upgrade"])


def explain_unusable(player, name):
    """Show the banner for a pick-up the player touched but cannot use. True if one was shown."""
    note = unusable_note(player, name)
    if note is None:
        return False
    _banner(player, title(name).upper(), GREY, note)
    return True


def grant(player, name):
    """Give the player the item (no checks: see can_collect). Returns the line to show."""
    item = ITEMS_BY_ID[item_id(name)]
    kind = item["kind"]
    if kind == "heal":
        player.health = min(player.max_health, player.health + player.max_health * item["heal_pct"])
        return "Healed"
    if kind == "charm":
        rules.add_stock(player, item, D.CHARM_AMOUNT)
        return f"Befriend Charm x{player.charms}"
    if kind == "boost":
        player.boosts.add(item["id"])
        rules.apply_loadout(player)
        return "Lasts this level"
    player.upgrades[item["id"]] = rules.level_of(player, item) + 1
    rules.apply_loadout(player, heal_gain=True)
    lvl, top = rules.level_of(player, item), rules.max_level(item)
    return f"Level {lvl}" + (" (MAX)" if lvl >= top else "")


def collect(game, player, name):
    """A player touched a pick-up. True if it was used up."""
    if not can_collect(player, name):
        return False
    note = grant(player, name)
    _banner(player, title(name).upper(), PINK if name == D.CHARM_NAME else MINT, note)
    return True


def _banner(player, text, color, sub=None):
    try:
        from ..ui import combat_fx
        combat_fx.fx().banner(player, text, color, sub)
    except Exception:
        pass                                    # a missing toast must never break a pick-up


# ====================================================================== #
# hero milestones (kills)
# ====================================================================== #
def reset_player(player):
    """A new run: kill count and milestones back to zero, and co-op charms start at the co-op amount."""
    player.coop_kills = 0
    player.coop_tiers = {}
    game = getattr(player, "game", None)
    if game is not None and getattr(game, "level_folder", None) == paths.MULTIPLAYER \
            and not getattr(game, "MULTIPLAYER", False):
        player.charms = D.START_CHARMS


def on_kill(player):
    """``player`` just killed something. Counts it and grants any hero milestone it reached."""
    game = getattr(player, "game", None)
    if game is None or not active(game):
        return
    player.coop_kills = getattr(player, "coop_kills", 0) + 1
    tiers = getattr(player, "coop_tiers", None)
    if tiers is None:
        tiers = player.coop_tiers = {}
    steps = D.MILESTONES.get(player.name, ())
    done = tiers.get(player.name, 0)
    while done < len(steps) and player.coop_kills >= steps[done][0]:
        _, iid = steps[done]
        done += 1
        item = ITEMS_BY_ID.get(iid)
        if item is None or rules.level_of(player, item) >= rules.max_level(item):
            continue                                    # already maxed: the milestone still counts
        grant(player, iid)
        _banner(player, D.MILESTONE_TITLE.format(hero=str(player.name).upper()), GOLD, item["name"])
    tiers[player.name] = done


def next_milestone(player):
    """(kills still needed, item name) for the next hero upgrade, or None when the list is finished."""
    steps = D.MILESTONES.get(player.name, ())
    done = getattr(player, "coop_tiers", {}).get(player.name, 0)
    if done >= len(steps):
        return None
    need, iid = steps[done]
    return max(0, need - getattr(player, "coop_kills", 0)), ITEMS_BY_ID[iid]["name"]


# ====================================================================== #
# drops
# ====================================================================== #
def _loose(game):
    return sum(1 for t in game.treasure_list if getattr(t, "is_pickup", False) and not t.dead)


def _roll_name():
    names, weights = zip(*D.DROP_POOL)
    return random.choices(names, weights)[0]


def maybe_drop(game, enemy):
    """A non-player entity just died: sometimes it leaves a power-up."""
    if not active(game) or getattr(enemy, "type", None) == "player":
        return
    if _loose(game) >= D.MAX_LOOSE:
        return
    chance = min(D.DROP_CHANCE_MAX, D.DROP_CHANCE + D.DROP_CHANCE_PER_VALUE * max(0, getattr(enemy, "value", 0)))
    if random.random() >= chance:
        return
    from ..objects.objects import Pickup
    p = Pickup(enemy.rect.centerx, enemy.rect.centery, _roll_name(), game, "dropped")
    p.rect.center = enemy.rect.center
    p.lifespan = D.DROP_LIFESPAN
    game.treasure_list.append(p)
    game._draw_list_dirty = True


# ====================================================================== #
# random places
# ====================================================================== #
def _surfaces(game):
    """Candidate spots: a 50 px square standing on top of a block with clear air above it."""
    blocks = [b for b in game.objects if getattr(b, "type", None) == "block"]
    taken = set()
    for b in blocks:
        r = b.rect
        for cx in range(r.left // 32, (r.right - 1) // 32 + 1):
            for cy in range(r.top // 32, (r.bottom - 1) // 32 + 1):
                taken.add((cx, cy))
    avoid = [z.rect for z in getattr(game, "zones", ())]                     # water, lava, toxic
    avoid += [t.rect.inflate(80, 80) for t in getattr(game, "traps", ())]
    avoid += [d.rect.inflate(80, 80) for d in getattr(game, "doors", ())]
    starts = [pygame.Rect(x - D.SCATTER_AVOID_START, y - D.SCATTER_AVOID_START,
                          D.SCATTER_AVOID_START * 2, D.SCATTER_AVOID_START * 2)
              for x, y in getattr(game, "points", ())]
    out = []
    for b in blocks:
        r = b.rect
        top = r.top // 32
        for cx in range(r.left // 32, (r.right - 1) // 32 + 1):
            if (cx, top - 1) in taken or (cx, top - 2) in taken or (cx, top - 3) in taken:
                continue
            spot = pygame.Rect(cx * 32 + 16 - 25, r.top - 50, 50, 50)
            if spot.collidelist(avoid) != -1 or spot.collidelist(starts) != -1:
                continue
            out.append(spot)
    return out


def on_level_loaded(game):
    """Scatter a few generic power-ups around a freshly loaded co-op level (and note the editor-placed charms)."""
    if not active(game):
        return
    spots = _surfaces(game)
    if not spots:
        return
    n = max(D.SCATTER_MIN, min(D.SCATTER_MAX, len(spots) // D.SCATTER_ONE_PER_CELLS))
    n += D.SCATTER_PER_EXTRA_PLAYER * max(0, len(getattr(game, "local_players", ())) - 2)
    random.shuffle(spots)
    placed = []
    from ..objects.objects import Pickup
    for spot in spots:
        if len(placed) >= n:
            break
        if any(abs(spot.centerx - p.centerx) + abs(spot.centery - p.centery) < D.SCATTER_MIN_GAP for p in placed):
            continue
        placed.append(spot)
        game.treasure_list.append(Pickup(spot.x, spot.y, _roll_name(), game))
    game._draw_list_dirty = True
