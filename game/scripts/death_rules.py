"""
death_rules.py
==============
What happens when players die: coins spill, pearls buy a revive, and
"restart level" puts everyone back exactly as they entered the floor.

The rules (decided in PIXEL_ABYSS_DESIGN_PLAN.md, open questions settled):

    Death      drop gold, ruby and emerald where you fell (recoverable for
               DEATH_DROP_LIFESPAN seconds). Upgrades are kept.
               Pearls are NOT dropped: they are the revive currency, so
               dropping them would make reviving impossible.
    Revive     costs pearls, on the spot, at REVIVE_HEALTH of max HP with a
               short grace period. The price starts at REVIVE_BASE_PRICE and
               rises by REVIVE_PRICE_STEP on EVERY revive for the whole run
               (it only resets when a new run starts), so restarting a level
               never makes revives cheap again.
    Restart    reloads the same floor and puts coins, upgrades, boosts and HP
               back to what each player had when the floor loaded.

Everything here is plain functions on the game/player objects; the drawing
is in ui/defeat_screen.py.
"""

import random
import pygame

from ..data.shop_items import WALLET_ATTR, CURRENCIES
from ..objects.objects import Treasure
from . import achievements

REVIVE_BASE_PRICE = 1            # pearls
REVIVE_PRICE_STEP = 1            # added per revive already used this run
REVIVE_HEALTH = 0.5              # fraction of max HP you come back with
GRACE_SECONDS = 2.0              # can't be hurt right after coming back

DEATH_DROP_LIFESPAN = 60         # seconds spilled coins wait to be picked up
MAX_DROP_PIECES = 6              # coin entities per currency (a pile is a few big coins, not hundreds)
DROPPED = ("gold", "ruby", "emerald")
COIN_NAME = {"gold": "yellow", "ruby": "red", "emerald": "green", "pearl": "pink"}


# ------------------------------------------------------------------ #
# who is playing
# ------------------------------------------------------------------ #

def humans(game):
    """The local human players (bots excluded)."""
    local = [p for p in (getattr(game, "local_players", None) or []) if not getattr(p, "auto", False)]
    return local or list(getattr(game, "player_slots", []))[:1]


def all_humans_dead(game):
    people = humans(game)
    return bool(people) and all(p.dead for p in people)


# ------------------------------------------------------------------ #
# dying: spill the coins
# ------------------------------------------------------------------ #

def drop_wallet(player):
    """Spill gold/ruby/emerald at the player's position. Called once, as the death starts."""
    game = player.game
    spilled = False
    for currency in DROPPED:
        attr = WALLET_ATTR[currency]
        total = getattr(player, attr, 0)
        if total <= 0:
            continue
        pieces = min(total, MAX_DROP_PIECES)
        each, extra = divmod(total, pieces)
        for i in range(pieces):
            coin = Treasure(player.rect.centerx, player.rect.centery, COIN_NAME[currency], game, "dropped")
            coin.rect.center = player.rect.center
            coin.amount = each + (1 if i < extra else 0)    # a coin can be worth several
            coin.lifespan = DEATH_DROP_LIFESPAN
            game.treasure_list.append(coin)
        setattr(player, attr, 0)
        spilled = True
    if spilled:
        game._draw_list_dirty = True


# ------------------------------------------------------------------ #
# reviving
# ------------------------------------------------------------------ #

def second_wind(game):
    """Shop: Second Wind. Everyone is down: a human with a free revive left stands back up at half
    health (no pearls, and NOT counted as a pearl revive - the *Second Wind* achievement is unchanged).
    Returns True if somebody got up."""
    from . import shop_effects
    from ..ui import charm_ui
    for p in humans(game):
        if p.dead and shop_effects.second_wind_ready(p):
            p.second_winds_used += 1
            if p.rect.y > getattr(game, "maxy", 10 ** 9):              # fell out of the world
                p.rect.x, p.rect.y = random.choice(game.points)
            bring_back(game, p, health=p.max_health * 0.5)
            charm_ui.banner(game, "SECOND WIND!", (140, 220, 255))
            charm_ui.burst(game, p.rect.center, "hearts")
            return True
    return False


def revive_price(game):
    return REVIVE_BASE_PRICE + REVIVE_PRICE_STEP * getattr(game, "run_revives", 0)


def can_revive(game, player):
    return player.dead and getattr(player, WALLET_ATTR["pearl"], 0) >= revive_price(game)


def bring_back(game, player, health=None, grace=GRACE_SECONDS):
    """Stand a dead player back up (also used when a new floor loads)."""
    player.dead = False
    player.death = False
    if health is None and player.health <= 0:
        health = player.max_health
    if health is not None:
        player.health = max(1, min(player.max_health, health))

    player.hurt = False
    player.x_vel = player.y_vel = 0
    player.fall_count = 0
    player.target = None
    player.sprite_sheet = "idle"
    player.sheet_name = "idle_" + player.direction
    player.sprite_index = 0
    player.animation_count = 0
    player.update_sprites_len()

    if player in game.dead_entities:
        game.dead_entities.remove(player)
    if player not in game.players:
        game.players.append(player)
    game._entities_dirty = True
    game._draw_list_dirty = True
    player.grace_until = pygame.time.get_ticks() + int(grace * 1000)


def revive(game, player):
    """Pay the pearls and stand up on the spot. Returns (ok, message)."""
    price = revive_price(game)
    if not player.dead:
        return False, "Not down."
    if not can_revive(game, player):
        return False, f"A revive costs {price} pearl{'s' if price != 1 else ''}."

    player.pearl_coins -= price
    game.run_revives = getattr(game, "run_revives", 0) + 1

    # Fell out of the bottom of the world? Come back at a start point instead.
    if player.rect.y > getattr(game, "maxy", 10 ** 9):
        player.rect.x, player.rect.y = random.choice(game.points)
    bring_back(game, player, health=player.max_health * REVIVE_HEALTH)
    achievements.tracker().on_revive(game, player)
    return True, "Revived."


# ------------------------------------------------------------------ #
# floor entry snapshot / restart
# ------------------------------------------------------------------ #

def snapshot(player):
    return {
        "wallet": {cur: getattr(player, WALLET_ATTR[cur], 0) for cur in CURRENCIES},
        "upgrades": dict(player.upgrades),
        "boosts": set(player.boosts),
        "health": player.health,
        # consumable stock + what has been bought, so a floor restart gives back exactly what you entered with
        "charms": player.charms, "dashes": player.dashes,
        "bought": dict(player.bought), "second_winds_used": player.second_winds_used,
        # co-op: kills and the hero milestones reached (the upgrades they gave are in "upgrades" above)
        "coop_kills": getattr(player, "coop_kills", 0), "coop_tiers": dict(getattr(player, "coop_tiers", {})),
    }


def restore(player, snap):
    for cur, amount in snap["wallet"].items():
        setattr(player, WALLET_ATTR[cur], amount)
    player.upgrades = dict(snap["upgrades"])
    player.boosts = set(snap["boosts"])
    player.health = snap["health"]
    player.charms, player.dashes = snap["charms"], snap["dashes"]
    player.bought = dict(snap["bought"])
    player.second_winds_used = snap["second_winds_used"]
    player.coop_kills = snap.get("coop_kills", 0)
    player.coop_tiers = dict(snap.get("coop_tiers", {}))


def begin_level(game):
    """Call once a floor has loaded (after the players were personalised)."""
    for player in game.player_slots:
        if player.dead or player.death:
            bring_back(game, player)            # a new floor is a fresh start for the fallen
        player._level_entry = snapshot(player)
        player.damage_this_level = 0.0              # per-floor achievement counters
        player.lava_seconds = 0.0
        player.kill_times = []


def restart_level(game):
    """Back to the floor's start, exactly as entered. Takes effect on the next loop."""
    for player in game.player_slots:
        entry = getattr(player, "_level_entry", None)
        if entry:
            restore(player, entry)
    game.level_completed = False                # a restart is not a victory: no shop
    game.new = True


def reset_run(game):
    """A brand-new run: the revive price starts over."""
    game.run_revives = 0
