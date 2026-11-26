"""
charm_mode.py
=============
The rules of the Befriend Charm and of bought dashes (WS-B). No drawing here:
``ui/charm_ui.py`` draws, ``data/charms.py`` holds every number.

State machine (per player, ``player.charm_session``)::

    IDLE -- press --> stock? --no--> quick-buy popup --declined--> IDLE
                         |yes / bought
                         v
                   ACTIVE (BASE_TIME real seconds, slow-mo, camera on the target)
                     |-- confirm --> try_charm --> friend / "too strong" / "boss"  --> IDLE
                     |-- timer hits 0 ----------> CHARM LOST ----------------------> IDLE
                     '-- cancel (ESC / button) -> refund inside the first second, else lost

One code path per action: ``press`` (key, pad, touch, mouse), ``confirm``,
``cancel``, ``befriend`` / ``unfriend`` / ``release_all`` (also used by the
entity-info window), ``try_dash`` (every dash trigger).

Decisions (owner): story mode only, no multiplayer (TODO(multiplayer)), no
friends carry over a level or a death, a target can only be charmed when its
HP <= the player's current HP, bosses never. If the friend limit is reached the
OLDEST friend is released (with a toast) and the new one joins; the charm is
never refused after being spent.

Friends are ordinary enemies that are recoloured to the player's colour (the
engine's existing team rule: same colour = ally, see ``decide_kill`` and the
projectile hit-tests) and marked ``is_friend``. They stay in ``game.enemy_list``
so every system keeps updating / drawing them; ``objectives.hostile_count``
subtracts them so "clear all" still works. Following is done by moving their
patrol centre (``spawn_point``) to the player every frame - the existing
``patrol()`` then walks them back whenever they stray past ``LEASH``.
"""

import math
import random

import pygame

from ..settings import Settings
from ..data import charms as C
from ..data.shop_items import ITEMS_BY_ID
from . import shop_effects as rules
from . import paths
from . import achievements
from ..ui import ui_fx as fx
from ..ui import charm_ui

_DIRS = {
    pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0), pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1),
    pygame.K_a: (-1, 0), pygame.K_d: (1, 0), pygame.K_w: (0, -1), pygame.K_s: (0, 1),
}
_CONFIRM = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)


# ====================================================================== #
# availability / queries
# ====================================================================== #
def story(game):
    """The story campaign (single machine, no editor): charms and dashes are bought in the shop."""
    return (not getattr(game, "MULTIPLAYER", False)
            and getattr(game, "level_folder", None) == paths.STORY
            and not getattr(game, "EDIT_WORLD", False))


def coop(game):
    """A local co-op world: charms only come from Charm Crystals the author placed, dashes are free forever."""
    return (not getattr(game, "MULTIPLAYER", False)
            and getattr(game, "level_folder", None) == paths.MULTIPLAYER
            and not getattr(game, "EDIT_WORLD", False))


def available(game):
    """Charm mode exists in the story and in local co-op worlds."""
    return story(game) or coop(game)


def active(player):
    return getattr(player, "charm_session", None) is not None


def any_active(game):
    return any(active(p) for p in _locals(game))


def _locals(game):
    return getattr(game, "local_players", None) or getattr(game, "players", None) or []


def time_scale(game):
    """Multiplier the main loop applies to ``dt`` (1.0 normally, ~SLOWMO while aiming)."""
    return getattr(game, "_charm_slow", 1.0)


def total_time(player):
    return C.BASE_TIME + rules.stat(player, "charm_duration")


def reach(player):
    return getattr(player, "acquire_range", 1000) + C.BASE_RANGE_BONUS + rules.stat(player, "charm_range")


def friend_limit(player):
    return C.BASE_FRIEND_LIMIT + rules.stat(player, "charm_limit")


def _alive(e):
    return not (getattr(e, "dead", False) or getattr(e, "death", False) or e.health <= 0)


class Session:
    def __init__(self, player, left):
        self.player = player
        self.left = left
        self.total = left
        self.elapsed = 0.0
        self.candidates = []
        self.target = None
        self.stick_cd = 0.0
        self.age = 0.0               # drives the reticle animation


def candidates(game, player):
    """Living, non-friend entities in reach. Bosses and stronger enemies ARE included on purpose
    (the owner wants the gamble); the UI marks them red."""
    px, py = player.rect.center
    r2 = reach(player) ** 2
    friends = {id(f) for f in player.friends}
    out = []
    for e in game.enemy_list:
        if id(e) in friends or not _alive(e) or getattr(e, "is_friend", False):
            continue
        if e.color == player.color:                 # already an ally under the team rule
            continue
        dx, dy = e.rect.centerx - px, e.rect.centery - py
        if dx * dx + dy * dy <= r2:
            out.append(e)
    return out


def _nearest(player, entities, origin=None):
    ox, oy = origin or player.rect.center
    return min(entities, key=lambda e: (e.rect.centerx - ox) ** 2 + (e.rect.centery - oy) ** 2, default=None)


# ====================================================================== #
# start / press / cancel
# ====================================================================== #
def press(game, player):
    """The charm key / button / pad button. Starts charm mode (after the quick-buy if out of stock)."""
    if not available(game) or active(player) or player.dead or player.death:
        return False
    if player.charms <= 0:
        if coop(game):                          # no shop here: charms are found, not bought
            charm_ui.banner(game, "NO CHARMS - FIND A CHARM CRYSTAL", (255, 130, 190))
            fx.sfx(player, "miss")
            return False
        if not quick_buy(game, player, "befriend_charm"):
            return False
    return start(game, player)


def start(game, player):
    found = candidates(game, player)
    if not found:
        charm_ui.banner(game, "NO ENEMIES IN RANGE", (255, 202, 80))
        fx.sfx(player, "miss")
        return False
    player.charms -= 1
    player.charms_used += 1
    s = Session(player, total_time(player))
    s.candidates = found
    s.target = _nearest(player, found)
    player.charm_session = s
    _focus(player, s.target)
    fx.sfx(player, "buy")
    return True


def cancel(player, refund=None):
    """End a session silently. ``refund``: None = by the misclick rule, True / False = force."""
    s = getattr(player, "charm_session", None)
    if s is None:
        return
    if refund is None:
        refund = s.elapsed < C.CANCEL_REFUND_WINDOW
    if refund:
        player.charms = min(rules.stock_cap(player, ITEMS_BY_ID["befriend_charm"]), player.charms + 1)
    player.charm_session = None
    _unfocus(player)


def player_cancel(game, player):
    """ESC / pad B / the on-screen button: refunded inside the first second, otherwise lost."""
    s = player.charm_session
    if s is None:
        return
    kept = s.elapsed < C.CANCEL_REFUND_WINDOW
    _end(game, player, "CHARM KEPT" if kept else "CHARM LOST",
         (108, 201, 117) if kept else (255, 90, 80), refund=kept)


def _end(game, player, why, color, refund=False, vignette=None):
    cancel(player, refund=refund)
    if why:
        charm_ui.banner(game, why, color)
    if vignette:
        charm_ui.flash(game, vignette)


def _focus(player, target):
    if target is not None and getattr(player, "camera", None) is not None:
        player.camera.focus(target, 0.85, None, C.FOCUS_ZOOM)


def _unfocus(player):
    if getattr(player, "camera", None) is not None:
        player.camera.clear_focus()


# ====================================================================== #
# selection + confirm
# ====================================================================== #
def select(player, entity):
    s = player.charm_session
    if s and entity in s.candidates and entity is not s.target:
        s.target = entity
        _focus(player, entity)
        return True
    return False


def select_dir(player, dx, dy):
    """Jump to the next candidate in a direction (angle-bucketed, not list order)."""
    s = player.charm_session
    if not s or s.target is None:
        return False
    mag = math.hypot(dx, dy)
    if mag == 0:
        return False
    ux, uy = dx / mag, dy / mag
    ox, oy = s.target.rect.center
    best, best_score = None, None
    for e in s.candidates:
        if e is s.target:
            continue
        vx, vy = e.rect.centerx - ox, e.rect.centery - oy
        dist = math.hypot(vx, vy) or 1.0
        cos = (vx * ux + vy * uy) / dist
        if cos < 0.35:                               # only within about +-70 degrees
            continue
        score = dist * (1.7 - cos)                   # near AND well aligned wins
        if best_score is None or score < best_score:
            best, best_score = e, score
    return select(player, best) if best is not None else False


def confirm(game, player):
    s = player.charm_session
    if s is None:
        return
    target = s.target
    if target is None or not _alive(target):
        return
    achievements.tracker().on_charm_confirm(player, s.left)       # Last Second
    player.charm_session = None
    _unfocus(player)                       # first, so a success can then add its own camera "pop"
    return try_charm(game, player, target)


def _penalty(player, amount, text, color):
    """Health lost for a bad gamble. Bypasses damage_taken_mult on purpose (armour can't trivialise it)."""
    floor = 0 if C.BOSS_CAN_KILL else 1
    player.health = max(floor, player.health - amount)
    game = player.game
    charm_ui.banner(game, text, color)
    charm_ui.flash(game, (190, 20, 30))
    charm_ui.burst(game, player.rect.center, "shards")
    fx.sfx(player, "miss")
    player.shake_frames = 14
    player.shake_intensity = 8
    charm_ui.floating(game, player.rect.midtop, f"-{int(amount)}", (255, 90, 80))


def try_charm(game, player, target):
    """Health gate, run on confirm. Returns "ok" | "strong" | "boss"."""
    if getattr(target, "is_boss", False):
        amount = max(C.BOSS_PENALTY_PCT * player.max_health, C.BOSS_PENALTY_MIN)
        _penalty(player, amount, "BOSSES CANNOT BE CHARMED!", (255, 202, 80))
        achievements.tracker().on_charm_gamble(player)                # Gambler: we are still standing
        return "boss"
    if target.health > player.health:
        gap = (target.health - player.health) * C.GAP_PENALTY_PCT
        amount = max(C.GAP_PENALTY_MIN_PCT * player.max_health, min(C.GAP_PENALTY_MAX_PCT * player.max_health, gap))
        _penalty(player, amount, "TOO STRONG!", (255, 112, 92))
        return "strong"
    befriend(player, target)
    return "ok"


# ====================================================================== #
# friends (one code path, also used by the entity-info window)
# ====================================================================== #
_SAVED = ("spawn_point", "patrol_range_x", "patroller", "posted", "attack_power", "damage_taken_mult")


def count_friends(game):
    return sum(len(p.friends) for p in (getattr(game, "players", None) or []))


def befriend(player, entity, announce=True):
    game = player.game
    if entity in player.friends:
        return False
    if len(player.friends) >= friend_limit(player):          # the OLDEST friend makes room
        oldest = player.friends[0]
        unfriend(player, oldest)
        if announce:
            charm_ui.banner(game, f"{oldest.name.upper()} LEFT YOUR SIDE", (200, 200, 220))

    player.friends.append(entity)
    if player not in entity.friends:
        entity.friends.append(player)
    entity._friend_saved = {k: getattr(entity, k, None) for k in _SAVED}
    entity.original_color = entity.color
    entity.color = player.color                              # the engine's team rule: same colour = ally
    entity.is_friend = True
    entity.has_target = False
    entity.target = None
    entity.posted = False
    entity.patroller = True

    bond = rules.stat(player, "charm_bond") * C.BOND_STAT_PER_LEVEL
    if bond:
        entity.attack_power *= 1 + bond
        entity.damage_taken_mult = max(0.3, getattr(entity, "damage_taken_mult", 1.0) * (1 - bond))

    game.friend_count = count_friends(game)
    achievements.tracker().on_friends(player, len(player.friends))    # First Friend / Entourage
    if announce:
        charm_ui.banner(game, "FRIEND MADE!", (255, 130, 190))
        charm_ui.burst(game, entity.rect.center, "hearts")
        charm_ui.flash(game, (255, 120, 190), 0.5)
        fx.sfx(player, "coin")
        fx.sfx(player, "buy")
        if getattr(player, "camera", None) is not None:
            player.camera.focus(entity, 0.7, 0.7, 1.15)      # the short "pop"
    return True


def unfriend(player, entity):
    if entity in player.friends:
        player.friends.remove(entity)
    if player in entity.friends:
        entity.friends.remove(player)
    saved = getattr(entity, "_friend_saved", None)
    if saved:
        for k, v in saved.items():
            if v is not None:
                setattr(entity, k, v)
        entity._friend_saved = None
    if getattr(entity, "original_color", None) is not None and getattr(entity, "is_friend", False):
        entity.color = entity.original_color
    entity.is_friend = False
    game = getattr(player, "game", None)
    if game is not None:
        game.friend_count = count_friends(game)


def release_all(player):
    """No friends remain: level end, level reload, death, new run."""
    for f in list(player.friends):
        unfriend(player, f)
    player.friends.clear()


def release_everyone(game):
    for p in (getattr(game, "players", None) or []):
        cancel(p, refund=False)
        release_all(p)
    game.friend_count = 0


def _update_friends(game, player):
    px, py = player.rect.center
    for f in list(player.friends):
        if not _alive(f):
            unfriend(player, f)
            charm_ui.burst(game, f.rect.center, "shards")
            continue
        f.spawn_point = player.rect.x                        # the patrol centre follows the player
        f.patrol_range_x = C.LEASH
        f.patroller = True
        f.posted = False
        dx, dy = f.rect.centerx - px, f.rect.centery - py
        far = math.hypot(dx, dy)
        if far > C.TELEPORT_DISTANCE or (abs(dy) > C.TELEPORT_DY and far > 600):
            side = random.choice((-1, 1))
            f.rect.center = (px + side * 70, py)
            f.x_vel = f.y_vel = 0
            charm_ui.burst(game, f.rect.center, "hearts")


# ====================================================================== #
# per-frame update (REAL time)
# ====================================================================== #
def update(game, raw_dt):
    """Call once per frame with the real frame time. Ticks the timer, the slow-mo and the friends."""
    raw = max(0.0, min(0.1, raw_dt))
    on = any_active(game)
    game._charm_slow = fx.smooth_to(getattr(game, "_charm_slow", 1.0), C.SLOWMO if on else 1.0, raw, C.SLOWMO_EASE)
    charm_ui.tick(game, raw)

    for player in list(_locals(game)):
        s = player.charm_session
        if player.dead or player.death:
            if s:
                _end(game, player, None, None, refund=False)
            release_all(player)
            continue
        if not available(game):
            if s:
                _end(game, player, None, None, refund=False)
            release_all(player)
            continue
        if s:
            s.left -= raw
            s.elapsed += raw
            s.age += raw
            s.stick_cd = max(0.0, s.stick_cd - raw)
            s.candidates = candidates(game, player)
            if s.target not in s.candidates:                 # died / left range: auto-advance
                s.target = _nearest(player, s.candidates, s.target.rect.center if s.target is not None else None)
                if s.target is None:
                    _end(game, player, "NO TARGETS LEFT", (255, 202, 80), refund=True)
                    continue
                _focus(player, s.target)
            _pad_input(player, s)
            if s.left <= 0:
                _end(game, player, "CHARM LOST", (255, 90, 80), refund=False, vignette=(150, 10, 25))
                charm_ui.burst(game, player.rect.center, "shards")
                fx.sfx(player, "miss")
        _update_friends(game, player)


def _pad_input(player, s):
    """Gamepad stick moves the selection (deadzone + repeat delay)."""
    joy = getattr(player, "joystick", None)
    if joy is None or s.stick_cd > 0:
        return
    try:
        x, y = joy.get_axis(0), joy.get_axis(1)
    except Exception:
        return
    if math.hypot(x, y) > C.STICK_DEADZONE and select_dir(player, x, y):
        s.stick_cd = C.STICK_REPEAT


# ====================================================================== #
# input entry points (called from game.py's event loop)
# ====================================================================== #
def _kb_player(game, num):
    for p in _locals(game):
        if getattr(p, "control_type", None) == "keyboard" and getattr(p, "keyboard_num", None) == num:
            return p
    return None


def on_key(game, event):
    """KEYDOWN. Returns True when the key was consumed (so ESC etc. don't also do their usual job)."""
    if not available(game):
        return False
    key = event.key
    # the charm key: edge event, one per player scheme
    for num, charm_key in Settings.CHARM_KEYS.items():
        if key == charm_key:
            p = _kb_player(game, num)
            if p is not None and not active(p):
                press(game, p)
                return True
    # while somebody is aiming
    for p in _locals(game):
        if not active(p):
            continue
        if key == pygame.K_ESCAPE:
            player_cancel(game, p)
            return True
        if key in _CONFIRM:
            confirm(game, p)
            return True
        if key in _DIRS:
            kb = getattr(p, "keyboard_num", None)
            scheme_ok = (kb == 0 and key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN)) or \
                        (kb == 1 and key in (pygame.K_a, pygame.K_d, pygame.K_w, pygame.K_s)) or kb is None
            if scheme_ok:
                select_dir(p, *_DIRS[key])
                return True
    return False


def on_joy(game, event):
    """JOYBUTTONDOWN / JOYHATMOTION. Returns True when consumed."""
    if not available(game):
        return False
    owner = None
    wanted = getattr(event, "instance_id", None)
    for p in _locals(game):
        joy = getattr(p, "joystick", None)
        try:
            if joy is not None and joy.get_instance_id() == wanted:
                owner = p
                break
        except Exception:
            pass
    if owner is None:
        return False
    if event.type == pygame.JOYBUTTONDOWN:
        if active(owner):
            if event.button == 0:
                confirm(game, owner)
                return True
            if event.button == 1:
                player_cancel(game, owner)
                return True
        elif event.button == Settings.CHARM_JOY_BUTTON:
            press(game, owner)
            return True
    elif event.type == pygame.JOYHATMOTION and active(owner):
        x, y = event.value
        if x or y:
            select_dir(owner, x, -y)
            return True
    return False


def on_pointer(game, pos):
    """Mouse click / tap at a window position. Returns True when consumed."""
    if not available(game):
        return False
    # a touch is often followed by a synthesised mouse click at the same spot: swallow the echo,
    # otherwise "tap to select" would be followed by "tap again = confirm" in the same instant
    now = pygame.time.get_ticks()
    last = getattr(game, "_charm_last_ptr", None)
    game._charm_last_ptr = (now, pos)
    if last and now - last[0] < 150 and math.hypot(pos[0] - last[1][0], pos[1] - last[1][1]) < 40:
        return any_active(game) or charm_ui.hit_test(_locals(game)[0], pos) is not None
    for p in _locals(game):
        hit = charm_ui.hit_test(p, pos)
        if hit == "charm":
            press(game, p)
            return True
        if active(p):
            if hit == "confirm":
                confirm(game, p)
                return True
            if hit == "cancel":
                player_cancel(game, p)
                return True
            target = charm_ui.pick(game, p, pos)
            if target is not None:
                if target is p.charm_session.target:
                    confirm(game, p)
                else:
                    select(p, target)
                return True
    return False


# ====================================================================== #
# bought dashes + quick-buy
# ====================================================================== #
def dash_rules_apply(game, player):
    """Dashes cost something for players in the story campaign only; in co-op they are free forever."""
    return getattr(player, "type", None) == "player" and story(game)


def quick_buy(game, player, item_id):
    """The out-of-stock popup. Blocking (the game is frozen behind it). True if one unit was bought."""
    from ..ui import ui_theme
    item = ITEMS_BY_ID[item_id]
    cost = rules.quick_price(player, item)
    gold = rules.wallet(player, item["currency"])
    what = "a Befriend Charm" if item_id == "befriend_charm" else "a Dash Charge"
    if rules.stock_of(player, item) >= rules.stock_cap(player, item):
        return False
    if gold < cost:
        ui_theme.confirm_dialog(game, "OUT OF " + ("CHARMS" if item_id == "befriend_charm" else "DASHES"),
                                f"{what.capitalize()} costs {cost} gold here - you only have {gold}.",
                                "OK", "CLOSE", accent=ui_theme.GOLD)
        return False
    ok = ui_theme.confirm_dialog(game, "OUT OF " + ("CHARMS" if item_id == "befriend_charm" else "DASHES"),
                                 f"Buy {what} for {cost} gold? You have {gold}.",
                                 "BUY", "NO THANKS", accent=ui_theme.GOLD)
    if not ok:
        return False
    player.gold_coins -= cost
    achievements.tracker().on_spend(player, cost)
    rules.add_stock(player, item, 1)
    player.bought[item_id] = player.bought.get(item_id, 0) + 1
    player.quick_buys += 1
    fx.sfx(player, "coin")
    return True


def try_dash(game, player):
    """The ONE place a dash is allowed (the time bar lives in scripts/dash_bar.py). True = the dash may start."""
    from . import dash_bar
    return dash_bar.try_dash(game, player)
