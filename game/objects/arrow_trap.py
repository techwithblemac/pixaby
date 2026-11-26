"""
arrow_trap.py
=============
The HOMING ARROW TRAP: a handful of homing arrows that are aimed at a *coordinate* instead of at an enemy.

An arrow that steers toward a fixed point but can only turn so fast never reaches it - it overshoots, swings
round and comes back, over and over. So the arrows keep revolving around the spot, and anything hostile that
wanders through their path is shot. Nothing is chasing anything; the point is the target.

Three ways to get one
---------------------
* The LEVEL EDITOR places one (TRAPS category, "homing"). It has NO OWNER: every effect is set by hand in the
  Modify popup (damage, knockback, burn, pierce, lifetime, who it hurts ...) and it lasts as long as the level.
* A PLAYER drops one with the TRAP key when they own a Homing Trap Kit (shop, ARSENAL tab).
* An ENEMY that was given the trap ability in the Entity Editor drops one (see entities/mods.py).

Owned traps take their effects from the owner's ARROW PROPERTIES (``arrow_profile``) at the moment they are
dropped, so a player with Piercing Tips / Hot Coals / more arrows, or a boss with fire arrows, drops traps with
those same effects. Owned traps never hurt their owner's colour and credit the owner with the kills.

World entry (type "trap", name "homing"): x, y (the cell), width, height, plus the keys in ``PROP_DEFAULTS``.
"""

import math
import random

import pygame

from .object_utils import Object
from ..data.traps import CELL
from ..scripts.physics import PHYSICS as physics
from ..scripts import shop_effects
from ..entities.burn import Burn

NAME = "homing"

# Every editable property of an editor-placed trap, with its default. (The Modify popup is built from this.)
PROP_DEFAULTS = {
    "arrows": 3,            # arrows revolving in the trap
    "radius": 110,          # px: how wide they swing round the spot
    "speed": 420,           # px/s
    "damage": 12.0,         # health lost per arrow hit
    "knockback": 160,       # shove given to whoever is hit
    "burn": 0.0,            # seconds of burning left on the victim (0 = none)
    "pierce": 0,            # hits one arrow can land before it is spent (0 = unlimited: it keeps revolving)
    "lifetime": 0.0,        # seconds before the trap fades (0 = permanent)
    "hit_gap": 0.55,        # seconds before the same arrow can hurt the same victim again
    "hurt_players": True,
    "hurt_enemies": True,
}

HIT_BOX = 22                # px: the hit box of one arrow
FADE = 1.2                  # seconds the trap takes to fade out at the end of its life
WOBBLE = 0.15               # how much the turn rate breathes in and out (flower-shaped sweeps, not a ring)


def _num(value, default, cast=float):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return cast(default)


def clean_props(raw):
    """Merge ``raw`` over the defaults, coercing every value to its type and clamping it to something sane."""
    raw = raw or {}
    out = {}
    for key, default in PROP_DEFAULTS.items():
        value = raw.get(key, default)
        if isinstance(default, bool):
            out[key] = bool(value)
        elif isinstance(default, int):
            out[key] = _num(value, default, int)
        else:
            out[key] = _num(value, default, float)
    out["arrows"] = max(1, min(12, out["arrows"]))
    out["radius"] = max(40, min(500, out["radius"]))
    out["speed"] = max(100, min(1200, out["speed"]))
    out["damage"] = max(0.0, out["damage"])
    out["knockback"] = max(0, out["knockback"])
    out["burn"] = max(0.0, out["burn"])
    out["pierce"] = max(0, out["pierce"])
    out["lifetime"] = max(0.0, out["lifetime"])
    out["hit_gap"] = max(0.05, out["hit_gap"])
    return out


def arrow_profile(entity):
    """What an entity's arrows do - the one definition shared by its arrows and the traps it drops.

    damage       health lost per arrow (its attack power x the arrow damage multiplier)
    knockback    shove
    pierce       enemies an arrow passes through
    homing       arrows steer toward a target
    burn         seconds of burning left on whoever is hit
    speed        arrow speed multiplier
    count        arrows per volley
    """
    stats = getattr(entity, "shop_stats", None) or {}
    mods = getattr(entity, "mods", None) or {}
    return {
        "damage": float(getattr(entity, "attack_power", 10)) * float(mods.get("arrow_damage_mult", 1.0)),
        "knockback": float(getattr(entity, "knockback_power", 200)) * float(mods.get("arrow_knockback_mult", 1.0)),
        "pierce": int(stats.get("pierce", 0)),
        "homing": bool(stats.get("homing", 0)),
        "burn": float(mods.get("arrow_burn", 0.0)),
        "speed": float(mods.get("arrow_speed_mult", 1.0)),
        "count": int(stats.get("arrow_bonus", 0)),
    }


def props_for_owner(owner, trap_cfg=None):
    """Trap properties derived from the owner's arrow profile (+ the owner's trap settings, if it has any)."""
    prof = arrow_profile(owner)
    stats = getattr(owner, "shop_stats", None) or {}
    cfg = trap_cfg or {}
    arrows = int(cfg.get("arrows", PROP_DEFAULTS["arrows"])) + int(stats.get("trap_arrows", 0)) + prof["count"] // 2
    life = float(cfg.get("lifetime", 18.0)) + float(stats.get("trap_time", 0))
    return clean_props({
        "arrows": arrows,
        "radius": cfg.get("radius", PROP_DEFAULTS["radius"]),
        "speed": PROP_DEFAULTS["speed"] * prof["speed"],
        "damage": max(1.0, prof["damage"] * 0.5),       # several arrows share the work: each one hits for half a shot
        "knockback": prof["knockback"] * 0.8,
        "burn": prof["burn"],
        "pierce": prof["pierce"] * 3 if prof["pierce"] else 0,   # spent after a few hits only if the owner pierces
        "lifetime": life,
        "hurt_players": True,
        "hurt_enemies": True,
    })


class ArrowTrap(Object):
    """``x, y`` is the grid cell (editor) - or pass ``center`` to drop one at an exact world coordinate."""

    total = -1

    def __init__(self, x, y, game, owner=None, props=None, center=None):
        cx, cy = center if center is not None else (x + CELL // 2, y + CELL // 2)
        cell_x, cell_y = (int(cx) // CELL) * CELL, (int(cy) // CELL) * CELL
        if center is None:
            cell_x, cell_y = x, y
        super().__init__(cell_x, cell_y, CELL, CELL, NAME, game=game)
        ArrowTrap.total += 1
        self.id = ArrowTrap.total
        Object.total += 1
        self.object_id = Object.total
        self.type = "trap"
        self.nature = "object"
        self.owner = owner
        self.credit_owner = owner is not None       # Entity.hit() gives the kill to the owner
        self.props = clean_props(props)
        self.cx, self.cy = float(cx), float(cy)
        self.cell_x, self.cell_y = cell_x, cell_y
        self.attack_power = self.props["damage"]
        self.age = 0.0
        self.pulse = random.random() * 6.28
        self.cooldowns = {}
        self.animation_name = "off"
        self.origin_rect = pygame.Rect(cell_x, cell_y, CELL, CELL)
        reach = int(self.props["radius"] * 2.1) + HIT_BOX
        self.rect = pygame.Rect(0, 0, reach * 2, reach * 2)
        self.rect.center = (int(cx), int(cy))
        self.color_rgb = self._team_color()
        self.arrows = []
        n = self.props["arrows"]
        r = self.props["radius"]
        start = random.random() * math.tau
        for i in range(n):
            a = start + math.tau * i / n
            # on the circle, heading along it, so the first moments are already a clean revolution
            self.arrows.append({
                "x": self.cx + math.cos(a) * r, "y": self.cy + math.sin(a) * r,
                "h": a + math.pi / 2, "phase": random.random() * 6.28, "hits": 0, "trail": [],
            })

    # ------------------------------------------------------------------ #
    def _team_color(self):
        if self.owner is None:
            return (240, 150, 40)                                   # the editor orange: nobody owns it
        from ..ui import combat_fx
        return combat_fx.rgb_of(self.owner)

    @property
    def editing(self):
        return bool(getattr(self.game, "EDIT_WORLD", False))

    def return_to_pool(self):
        pass

    def update(self, return_image=False):
        return None

    # ------------------------------------------------------------------ #
    # simulation
    # ------------------------------------------------------------------ #
    def update_sprite_client(self):
        self.update_sprite()

    def update_sprite(self):
        if self.editing:
            return
        dt = min(self.game.dt, 0.05)
        if dt <= 0 or self.dead:
            return
        self.age += dt
        life = self.props["lifetime"]
        if life > 0 and self.age >= life:
            self.dead = True
            self.game._draw_list_dirty = True
            return
        speed = self.props["speed"]
        turn0 = speed / self.props["radius"]
        t = self.age
        for arrow in self.arrows:
            if arrow.get("spent"):
                continue
            want = math.atan2(self.cy - arrow["y"], self.cx - arrow["x"])
            diff = (want - arrow["h"] + math.pi) % math.tau - math.pi
            rate = turn0 * (1.0 + WOBBLE * math.sin(t * 1.7 + arrow["phase"]))
            arrow["h"] += max(-rate * dt, min(rate * dt, diff))
            arrow["x"] += math.cos(arrow["h"]) * speed * dt
            arrow["y"] += math.sin(arrow["h"]) * speed * dt
            trail = arrow["trail"]
            trail.append((arrow["x"], arrow["y"]))
            if len(trail) > 9:
                del trail[0]
        self._strike()
        if self.arrows and all(a.get("spent") for a in self.arrows):
            self.dead = True
            self.game._draw_list_dirty = True

    def _may_hurt(self, target):
        if getattr(target, "nature", None) != "entity" or target.dead or target.death:
            return False
        if self.owner is not None:
            if target is self.owner or target.color == self.owner.color:
                return False
        if target.type == "player":
            return self.props["hurt_players"]
        return self.props["hurt_enemies"]

    def _strike(self):
        clock = self.age
        for arrow in self.arrows:
            if arrow.get("spent"):
                continue
            box = pygame.Rect(0, 0, HIT_BOX, HIT_BOX)
            box.center = (int(arrow["x"]), int(arrow["y"]))
            seen = set()
            for target in physics.get_objects(self.game.entities_map, box, 0):
                if id(target) in seen:
                    continue
                seen.add(id(target))
                if not self._may_hurt(target) or not box.colliderect(target.rect):
                    continue
                key = (id(arrow), id(target))
                if self.cooldowns.get(key, -9.0) > clock:
                    continue
                self.cooldowns[key] = clock + self.props["hit_gap"]
                self._hurt(target, arrow)
                if self.props["pierce"] and arrow["hits"] >= self.props["pierce"]:
                    arrow["spent"] = True
                    break
        if len(self.cooldowns) > 200:                                # forget old victims
            self.cooldowns = {k: v for k, v in self.cooldowns.items() if v > clock}

    def _hurt(self, target, arrow):
        arrow["hits"] += 1
        self.attack_power = self.props["damage"]
        if target.type == "player":
            target.shake_frames = max(target.shake_frames, 8)
            target.shake_intensity = max(target.shake_intensity, 5)
        target.hit(obj=self, type_="arrow")
        push = self.props["knockback"]
        if push:
            target.knocking_back = push if math.cos(arrow["h"]) >= 0 else -push
        if self.props["burn"] > 0:
            Burn.apply(target, self.props["burn"], 3.0 + self.props["damage"] * 0.25, self.owner)
        try:
            from ..scripts.sounds import playit
            if random.random() < 0.5:
                playit("hit_3", self)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # drawing
    # ------------------------------------------------------------------ #
    def _alpha(self):
        life = self.props["lifetime"]
        if life > 0 and self.age > life - FADE:
            return max(0.0, (life - self.age) / FADE)
        return 1.0

    def draw(self, see_through=False, window=None, cam=(0, 0), zoom=1, game=None):
        zoom = zoom or 1
        ox, oy = cam[0], cam[1]
        editing = self.editing
        fade = self._alpha()
        col = self.color_rgb
        now = pygame.time.get_ticks() / 1000.0
        sx, sy = (self.cx - ox) * zoom, (self.cy - oy) * zoom
        r = self.props["radius"] * zoom
        size = int(r * 2.6) + 8
        layer = pygame.Surface((size, size), pygame.SRCALPHA)
        mid = size // 2

        # the spot itself: a faint glyph that tells you where the arrows are aimed
        pulse = 0.5 + 0.5 * math.sin(now * 3 + self.pulse)
        core = max(4, int(7 * zoom))
        pygame.draw.circle(layer, (*col, int(40 * fade)), (mid, mid), int(r * 0.55 + pulse * 3 * zoom))
        for k in range(12):                                         # dashed ring
            a0 = now * 0.6 + k * math.tau / 12
            pygame.draw.arc(layer, (*col, int((90 if editing else 60) * fade)),
                            pygame.Rect(mid - r * 0.55, mid - r * 0.55, r * 1.1, r * 1.1),
                            a0, a0 + 0.28, max(1, int(2 * zoom)))
        pygame.draw.circle(layer, (255, 245, 220, int(230 * fade)), (mid, mid), core)
        pygame.draw.circle(layer, (*col, int(255 * fade)), (mid, mid), core, max(1, int(2 * zoom)))
        if editing:                                                 # show the swing radius while authoring
            pygame.draw.circle(layer, (*col, 70), (mid, mid), int(r), 1)

        if editing or not any("trail" in a and a["trail"] for a in self.arrows):
            # no simulation here: show an ideal revolution so the author sees what the trap will do
            n = self.props["arrows"]
            speed_ang = self.props["speed"] / self.props["radius"]
            for i in range(n):
                a = now * speed_ang * 0.9 + math.tau * i / n
                self._draw_arrow(layer, mid + math.cos(a) * r, mid + math.sin(a) * r, a + math.pi / 2, zoom, col, fade, [])
        else:
            for arrow in self.arrows:
                if arrow.get("spent"):
                    continue
                trail = [(mid + (x - self.cx) * zoom, mid + (y - self.cy) * zoom) for x, y in arrow["trail"]]
                self._draw_arrow(layer, mid + (arrow["x"] - self.cx) * zoom, mid + (arrow["y"] - self.cy) * zoom,
                                 arrow["h"], zoom, col, fade, trail)
        window.blit(layer, (sx - mid, sy - mid))

    @staticmethod
    def _draw_arrow(layer, x, y, heading, zoom, col, fade, trail):
        if len(trail) > 1:
            for i in range(1, len(trail)):
                alpha = int(150 * fade * i / len(trail))
                pygame.draw.line(layer, (*col, alpha), trail[i - 1], trail[i], max(1, int(3 * zoom * i / len(trail))))
        c, s = math.cos(heading), math.sin(heading)
        L = 15 * zoom
        tail = (x - c * L, y - s * L)
        tip = (x + c * L * 0.6, y + s * L * 0.6)
        pygame.draw.line(layer, (30, 20, 24, int(255 * fade)), tail, tip, max(3, int(4 * zoom)))
        pygame.draw.line(layer, (235, 215, 170, int(255 * fade)), tail, tip, max(1, int(2 * zoom)))
        head = [(x + c * L, y + s * L), (x + c * L * 0.35 - s * 6 * zoom, y + s * L * 0.35 + c * 6 * zoom),
                (x + c * L * 0.35 + s * 6 * zoom, y + s * L * 0.35 - c * 6 * zoom)]
        pygame.draw.polygon(layer, (*col, int(255 * fade)), head)
        pygame.draw.polygon(layer, (30, 20, 24, int(255 * fade)), head, 1)
        for off in (-5, 0):
            fx = (x - c * (L - 3 + off), y - s * (L - 3 + off))
            pygame.draw.line(layer, (*col, int(230 * fade)),
                             (fx[0] - s * 4 * zoom, fx[1] + c * 4 * zoom), (fx[0] + s * 4 * zoom, fx[1] - c * 4 * zoom),
                             max(1, int(2 * zoom)))


# ---------------------------------------------------------------------- #
# dropping one
# ---------------------------------------------------------------------- #
def drop(game, owner, center, props=None, trap_cfg=None):
    """Create an owned trap at world coordinate ``center`` and add it to the world. Returns it."""
    trap = ArrowTrap(0, 0, game, owner=owner, props=props or props_for_owner(owner, trap_cfg), center=center)
    game.traps.append(trap)
    game._draw_list_dirty = True
    return trap


def live_count(game, owner):
    return sum(1 for t in game.traps if isinstance(t, ArrowTrap) and t.owner is owner and not t.dead)


def player_drop(game, player):
    """The TRAP key / button. Returns a short message for the HUD (or None when it worked silently)."""
    if getattr(player, "dead", False) or getattr(player, "death", False):
        return None
    if getattr(player, "traps", 0) <= 0:
        return "NO TRAP KITS - BUY ONE IN THE SHOP"
    cap = 4 + int(shop_effects.stat(player, "trap_arrows"))
    if live_count(game, player) >= cap:
        return "TOO MANY TRAPS OUT"
    player.traps -= 1
    foot = (player.rect.centerx + (60 if player.direction == "right" else -60), player.rect.centery)
    drop(game, player, foot)
    return "TRAP DROPPED"


# ---------------------------------------------------------------------- #
# input (called from game.py's event loop)
# ---------------------------------------------------------------------- #
def _say(game, player, text):
    if not text:
        return
    try:
        from ..ui import charm_ui
        charm_ui.floating(game, player.rect.midtop, text, (255, 190, 90))
    except Exception:
        pass


def on_key(game, event):
    """KEYDOWN: the TRAP key of a keyboard player. True = consumed."""
    from ..settings import Settings
    from ..scripts import charm_mode
    for num, key in Settings.TRAP_KEYS.items():
        if event.key == key:
            player = charm_mode._kb_player(game, num)
            if player is not None:
                _say(game, player, player_drop(game, player))
                return True
    return False


def on_joy(game, event):
    """JOYBUTTONDOWN: the TRAP button of a gamepad player. True = consumed."""
    from ..settings import Settings
    from ..scripts import charm_mode
    if event.type != pygame.JOYBUTTONDOWN or event.button != Settings.TRAP_JOY_BUTTON:
        return False
    wanted = getattr(event, "instance_id", None)
    for p in charm_mode._locals(game):
        joy = getattr(p, "joystick", None)
        try:
            if joy is not None and joy.get_instance_id() == wanted:
                _say(game, p, player_drop(game, p))
                return True
        except Exception:
            pass
    return False


_ICONS = {}


def icon(size=64, color=(240, 150, 40)):
    """A small picture of the trap (ring + three arrows) for the editor palette, the map preview and the editor window."""
    key = (size, color)
    if key in _ICONS:
        return _ICONS[key]
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    mid, r = size / 2, size * 0.32
    pygame.draw.circle(surf, (*color, 50), (mid, mid), int(r * 0.9))
    pygame.draw.circle(surf, (*color, 130), (mid, mid), int(r), max(1, size // 32))
    pygame.draw.circle(surf, (255, 245, 220), (mid, mid), max(2, size // 14))
    for i in range(3):
        a = -1.0 + math.tau * i / 3
        ArrowTrap._draw_arrow(surf, mid + math.cos(a) * r, mid + math.sin(a) * r, a + math.pi / 2, size / 70, color, 1.0, [])
    _ICONS[key] = surf
    return surf
