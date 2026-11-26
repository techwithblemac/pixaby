"""
dash_bar.py
===========
The dash is a TIME BAR instead of a stock of bought charges (story campaign; in co-op dashes stay free).

    * Dashing drains the bar one second per second; the dash ends when the bar is empty, when the dash button is
      let go (after a short minimum burst) or at a wall, as before.
    * Standing still (not dashing) refills it by time, after a short pause.
    * Upgrades: ``dash_time`` = more seconds on a full bar (how long a dash lasts), ``dash_regen`` = faster refill.
    * A dash can start once the bar holds MIN_START of its length, so holding the button does not stutter at 0.

Touch / on-screen DASH button presses cannot be "held", so they call ``pulse()``: a dash that lasts at least
PULSE seconds (or until the bar runs out).

Numbers live here (not in data/) because they are the whole design of the mechanic; tune them freely.
"""

BASE_TIME = 1.2            # seconds of dash on a full bar
BASE_REGEN = 0.40          # bar seconds refilled per second (empty -> full in ~3 s)
REGEN_DELAY = 0.45         # seconds after a dash ends before the bar starts refilling
MIN_START = 0.20           # fraction of the bar needed to start a dash
MIN_BURST = 0.18           # a held dash lasts at least this long
PULSE = 0.35               # a tapped / on-screen dash lasts this long


def _stat(player, key):
    from . import shop_effects as rules
    return rules.stat(player, key)


def applies(game, player):
    """The bar rules apply to story-campaign players only (co-op dashes are free forever)."""
    from . import charm_mode
    return charm_mode.dash_rules_apply(game, player)


def max_time(player):
    return BASE_TIME + _stat(player, "dash_time")


def regen_rate(player):
    return BASE_REGEN * (1.0 + _stat(player, "dash_regen"))


def ensure(player):
    """Give a player their bar (full) the first time it is needed."""
    if getattr(player, "dash_energy", None) is None:
        player.dash_energy = max_time(player)
    return player.dash_energy


def fraction(player):
    """0..1 for the HUD."""
    top = max_time(player)
    return max(0.0, min(1.0, ensure(player) / top)) if top > 0 else 0.0


def refill(player):
    player.dash_energy = max_time(player)
    player.dash_idle = 0.0


def pulse(player):
    """An on-screen / tapped dash: guarantees a short burst even though nothing is held."""
    player.dash_pulse = PULSE


def hold(player, pressed):
    player.dash_held = bool(pressed)


def try_dash(game, player):
    """The ONE place a dash may start. True = it may (the caller sets ``dashing``)."""
    if player.dashing:
        return False
    if not applies(game, player):
        player.dash_timed = False                     # co-op: free, distance-limited like before
        return True
    top = max_time(player)
    if ensure(player) < top * MIN_START:
        return False
    player.dash_timed = True
    player.dash_age = 0.0
    player.dashes_used += 1
    return True


def tick(game, player, dt):
    """Once per frame per player: drain while dashing, refill otherwise."""
    if getattr(player, "type", None) != "player" or dt <= 0:
        return
    if not applies(game, player):
        player.dash_timed = False
        return
    top = max_time(player)
    energy = ensure(player)
    player.dash_timed = True
    pulse_left = getattr(player, "dash_pulse", 0.0)
    if player.dashing:
        player.dash_age = getattr(player, "dash_age", 0.0) + dt
        player.dash_idle = REGEN_DELAY
        energy = max(0.0, energy - dt)
        if energy <= 0.0:
            player.dashing = False
        elif (not getattr(player, "dash_held", False) and pulse_left <= 0.0
              and player.dash_age >= MIN_BURST):
            player.dashing = False
    else:
        player.dash_age = 0.0
        idle = getattr(player, "dash_idle", 0.0)
        if idle > 0.0:
            player.dash_idle = max(0.0, idle - dt)
        else:
            energy = min(top, energy + regen_rate(player) * dt)
    player.dash_pulse = max(0.0, pulse_left - dt)
    player.dash_energy = min(energy, top)
