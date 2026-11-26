"""
combat_fx.py
============
Everything that makes a hit *feel* like a hit.

The combat rules themselves (who can hurt whom, ranges, cooldowns) are
untouched; this module only adds feedback and a little skill expression on
top of them:

    hit flash        victims flash white for a moment; enemies glow red as an
                     attack winds up, so you can read it and dash away
    damage numbers   floating, colour-coded (white / gold CRIT / coral FINISHER /
                     red = you got hit)
    impact sparks    directional sparks, slash lines, a flash of light, and
                     chunky pixel debris when something dies
    hit-stop         a few frames of "freeze" on heavy hits / kills (re-uses the
                     game's own ``game_speed`` ramp, so it eases back by itself)
    combos           chain hits within ``COMBO_WINDOW`` seconds: +3% damage per
                     link (max +30%), every 5th hit is a FINISHER (+50% damage,
                     big knockback + launch)
    crits            10% chance for +75% damage
    dash dodge       the first moments of a dash are invulnerable
                     (``DASH_IFRAMES`` seconds, then a short cooldown) so a well
                     timed dash *cancels* an attack - "PERFECT" slow-mo included
    kill streaks     DOUBLE / TRIPLE / ... banners, slow-mo on big streaks
    hurt vignette    red edge flash when hit, a heartbeat vignette when low

Performance rules (this runs inside the hot loop of a pygame game):
    * Module level imports are only pygame / stdlib, so mind.py and
      entity_utils.py can import this file without any import cycle.
    * Particle count is capped (halved on LOW_SPEC devices).
    * Nothing allocates per frame while idle; ``draw_*`` early-outs when empty.
    * Every public hook is wrapped so a bug here can never crash a fight.

Public hooks (called from the game code):
    dodged(victim, attacker, obj, type_)            -> bool   (i-frames)
    bonus_damage(attacker, victim, dealt, obj, type_) -> float (crit / combo)
    on_hit(victim, attacker, obj, type_, hp_before)
    watch(entity)                  once per frame per drawn entity (dash edge /
                                   enemy wind-up edge)
    tint(entity, image)            returns the flashed image when needed
    fx()                           the singleton: update(dt), draw_world(...),
                                   draw_screen(...), reset_level()
"""

import math
import random
import time

import pygame

# ---------------------------------------------------------------------- #
# tuning
# ---------------------------------------------------------------------- #
COMBO_WINDOW = 1.7          # seconds to land the next hit and keep the chain
COMBO_STEP_BONUS = 0.03     # +3% damage per link ...
COMBO_BONUS_CAP = 0.30      # ... up to +30%
FINISHER_EVERY = 5          # every Nth hit of a chain is a finisher
FINISHER_BONUS = 0.50
CRIT_CHANCE = 0.10
CRIT_BONUS = 0.75
DASH_IFRAMES = 0.24         # seconds of invulnerability at the start of a dash
DASH_COOLDOWN = 0.90        # before the next dash grants i-frames again
STREAK_WINDOW = 3.0         # seconds between kills that keep a kill streak

STREAK_NAMES = {2: "DOUBLE KILL", 3: "TRIPLE KILL", 4: "MULTI KILL", 5: "RAMPAGE", 6: "UNSTOPPABLE"}

GOLD = (255, 202, 80)
CORAL = (255, 112, 92)
CREAM = (255, 224, 151)
WHITE = (255, 242, 207)
RED = (232, 64, 60)
INK = (18, 17, 25)

COLOR_RGB = {
    "red": (224, 84, 80), "blue": (84, 130, 235), "yellow": (236, 214, 90),
    "purple": (170, 100, 200), "green": (110, 200, 110), "black": (110, 115, 125),
}

_LOW_SPEC = False


def _low_spec():
    global _LOW_SPEC
    try:
        from ..settings import Settings
        _LOW_SPEC = bool(Settings.LOW_SPEC_MODE)
    except Exception:
        pass
    return _LOW_SPEC


def _now():
    return time.perf_counter()


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def _scale(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))), max(0, min(255, int(c[2] * f))))


def _rgb_of(entity):
    return COLOR_RGB.get(str(getattr(entity, "color", "")).lower(), (210, 210, 220))


def rgb_of(entity):
    """Public: the on-screen RGB of an entity's colour name."""
    return _rgb_of(entity)


def _is_entity(obj):
    return getattr(obj, "type", None) in ("player", "enemy")


_warned = set()


def _safe(fn):
    """A broken effect must never break combat: log once, carry on."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as err:        # pragma: no cover - defensive
            if fn.__name__ not in _warned:
                _warned.add(fn.__name__)
                print(f"[combat_fx] {fn.__name__} failed: {err!r}")
            return None
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# ---------------------------------------------------------------------- #
# the effects manager
# ---------------------------------------------------------------------- #
class CombatFX:
    MAX_PARTS = 420

    def __init__(self):
        self.parts = []         # sparks / debris      (world space)
        self.texts = []         # damage numbers       (world space)
        self.flashes = []       # light bursts + rings (world space)
        self.slashes = []       # slash lines          (world space)
        self.banners = []       # kill-streak banners  (screen space)
        self._font_cache = {}
        self.kills_this_world = 0
        self.best_combo = 0
        self._t = 0.0
        self._tint_cache = {}

    # ------------------------------------------------------------------ #
    # life-cycle
    # ------------------------------------------------------------------ #
    def reset_level(self):
        """New world: clear every transient effect and the per-world counters."""
        self.parts.clear()
        self.texts.clear()
        self.flashes.clear()
        self.slashes.clear()
        self.banners.clear()
        self.kills_this_world = 0
        self.best_combo = 0

    def update(self, dt):
        if dt <= 0 and not self.parts and not self.texts:
            return
        dt = min(dt, 0.1)
        self._t += dt
        if self.parts:
            keep = []
            for p in self.parts:
                p[4] += dt
                if p[4] >= p[5]:
                    continue
                drag = p[9]
                if drag:
                    f = math.exp(-drag * dt)
                    p[2] *= f
                    p[3] *= f
                p[3] += p[8] * dt
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                keep.append(p)
            self.parts = keep
        if self.texts:
            keep = []
            for q in self.texts:
                q["age"] += dt
                if q["age"] >= q["life"]:
                    continue
                q["x"] += q["vx"] * dt
                q["y"] += q["vy"] * dt
                q["vy"] *= math.exp(-2.4 * dt)
                keep.append(q)
            self.texts = keep
        if self.flashes:
            self.flashes = [f for f in (self._age(f, dt) for f in self.flashes) if f]
        if self.slashes:
            self.slashes = [s for s in (self._age(s, dt) for s in self.slashes) if s]
        if self.banners:
            self.banners = [b for b in (self._age(b, dt) for b in self.banners) if b]

    @staticmethod
    def _age(item, dt):
        item["age"] += dt
        return item if item["age"] < item["life"] else None

    # ------------------------------------------------------------------ #
    # spawners
    # ------------------------------------------------------------------ #
    def _cap(self, n):
        return max(1, n // 2) if _LOW_SPEC else n

    def _part(self, x, y, vx, vy, life, size, color, grav=0.0, drag=0.0, additive=True):
        if len(self.parts) >= self.MAX_PARTS:
            del self.parts[0]
        # x, y, vx, vy, age, life, size, color, grav, drag, additive
        self.parts.append([x, y, vx, vy, 0.0, life, size, color, grav, drag, additive])

    def sparks(self, x, y, color, angle, spread, count, speed, life=0.4, size=3):
        for _ in range(self._cap(count)):
            a = angle + random.uniform(-spread / 2, spread / 2)
            s = speed * random.uniform(0.35, 1.0)
            self._part(x, y, math.cos(a) * s, math.sin(a) * s, life * random.uniform(0.6, 1.2),
                       size, color, grav=420.0, drag=2.2, additive=True)

    def debris(self, rect, color, count):
        """Chunky pixels that fall: what is left when something dies."""
        for _ in range(self._cap(count)):
            x = random.uniform(rect.left, rect.right)
            y = random.uniform(rect.top, rect.bottom)
            tone = random.choice((0.55, 0.8, 1.0, 1.0, 1.25))
            self._part(x, y, random.uniform(-190, 190), random.uniform(-340, -90),
                       random.uniform(0.55, 1.0), random.choice((3, 4, 5, 6)),
                       _scale(color, tone), grav=900.0, drag=0.6, additive=False)

    def text(self, x, y, txt, color, size=18, life=0.9, vx=0.0, vy=-90.0, pop=0.5):
        if len(self.texts) > 60:
            del self.texts[0]
        self.texts.append({"x": x, "y": y, "vx": vx, "vy": vy, "age": 0.0, "life": life,
                           "txt": str(txt), "color": color, "size": size, "pop": pop})

    def flash(self, x, y, color, radius, life=0.16, ring=False, ring_to=None):
        self.flashes.append({"x": x, "y": y, "color": color, "radius": radius, "age": 0.0,
                             "life": life, "ring": ring, "ring_to": ring_to or radius * 2.2})

    def slash(self, x, y, angle, color, length=46, life=0.16, width=4):
        self.slashes.append({"x": x, "y": y, "a": angle, "color": color, "len": length,
                             "age": 0.0, "life": life, "w": width})

    def banner(self, owner, txt, color=GOLD, sub=None, life=1.7, big=False):
        # one banner of the same kind per owner at a time
        self.banners = [b for b in self.banners if not (b["owner"] is owner and b["txt"] == txt)]
        self.banners.append({"owner": owner, "txt": txt, "color": color, "sub": sub, "age": 0.0,
                             "life": life, "big": big})

    # ------------------------------------------------------------------ #
    # drawing - world space (called with the player's viewport surface)
    # ------------------------------------------------------------------ #
    def draw_world(self, surface, cam, zoom, ui_font):
        """Sparks, debris, slashes, light bursts and damage numbers."""
        if not (self.parts or self.texts or self.flashes or self.slashes):
            return
        cx, cy = cam
        w, h = surface.get_size()
        z = zoom

        for f in self.flashes:
            u = f["age"] / f["life"]
            sx, sy = (f["x"] - cx) * z, (f["y"] - cy) * z
            if -200 < sx < w + 200 and -200 < sy < h + 200:
                if f["ring"]:
                    r = int((f["radius"] + (f["ring_to"] - f["radius"]) * u) * z)
                    col = _scale(f["color"], 1.0 - u)
                    if r > 2 and col != (0, 0, 0):
                        ring = pygame.Surface((r * 2 + 4, r * 2 + 4))
                        pygame.draw.circle(ring, col, (r + 2, r + 2), r, max(1, int(4 * (1 - u))))
                        surface.blit(ring, (int(sx) - r - 2, int(sy) - r - 2), special_flags=pygame.BLEND_RGB_ADD)
                else:
                    self._glow(surface, (sx, sy), f["color"], f["radius"] * z * (0.6 + 0.6 * u), 1.0 - u)

        for s in self.slashes:
            u = s["age"] / s["life"]
            sx, sy = (s["x"] - cx) * z, (s["y"] - cy) * z
            length = s["len"] * z * (0.35 + 0.65 * min(1.0, u * 2.2))
            fade = 1.0 - u
            for off, wd, col in ((-0.34, 1, CORAL), (0.0, max(2, int(s["w"] * z * fade)), WHITE), (0.34, 1, CORAL)):
                a = s["a"] + off
                x1, y1 = sx + math.cos(a) * length * 0.25, sy + math.sin(a) * length * 0.25
                x2, y2 = sx + math.cos(a) * length, sy + math.sin(a) * length
                pygame.draw.line(surface, _scale(col, fade + 0.2), (x1, y1), (x2, y2), wd)

        for p in self.parts:
            sx, sy = int((p[0] - cx) * z), int((p[1] - cy) * z)
            if sx < -8 or sy < -8 or sx > w or sy > h:
                continue
            f = _clamp(1.0 - p[4] / p[5])
            size = max(1, int(p[6] * z * (0.45 + 0.55 * f)))
            if p[10]:
                surface.fill(_scale(p[7], 0.35 + 0.65 * f), (sx, sy, size, size), special_flags=pygame.BLEND_RGB_ADD)
            else:
                surface.fill(_scale(p[7], 0.5 + 0.5 * f), (sx, sy, size, size))

        for q in self.texts:
            sx, sy = (q["x"] - cx) * z, (q["y"] - cy) * z
            if sx < -80 or sy < -40 or sx > w + 80 or sy > h + 40:
                continue
            u = q["age"] / q["life"]
            alpha = 255 * _clamp(1.0 - (u - 0.6) / 0.4)
            pop = 1.0 + q["pop"] * max(0.0, 1.0 - q["age"] / 0.16)
            size = max(10, int(q["size"] * pop * max(0.8, min(1.4, z))))
            font = ui_font(size, True)
            img = font.render(q["txt"], True, q["color"])
            sh = font.render(q["txt"], True, INK)
            img.set_alpha(int(alpha))
            sh.set_alpha(int(alpha * 0.8))
            rect = img.get_rect(center=(int(sx), int(sy)))
            surface.blit(sh, rect.move(2, 2))
            surface.blit(img, rect)

    _glow_cache = {}

    @staticmethod
    def _glow(surface, center, color, radius, strength):
        radius = max(8, int(radius))
        if strength <= 0.02:
            return
        # the gradient only depends on (radius, colour, strength): cache it (bucketed)
        # instead of building a new surface and 8 circles on every call
        radius = radius // 2 * 2
        key = (radius, tuple(color)[:3], round(strength * 12))
        img = CombatFX._glow_cache.get(key)
        if img is None:
            size = radius * 2
            img = pygame.Surface((size, size))
            steps = 8
            for i in range(steps):
                r = int(radius * (1 - i / steps))
                f = ((i + 1) / steps) ** 2 * 0.55 * (key[2] / 12.0)
                pygame.draw.circle(img, _scale(color, f), (radius, radius), max(1, r))
            if len(CombatFX._glow_cache) > 120:
                CombatFX._glow_cache.clear()
            CombatFX._glow_cache[key] = img
        surface.blit(img, (int(center[0]) - radius, int(center[1]) - radius), special_flags=pygame.BLEND_RGB_ADD)

    # ------------------------------------------------------------------ #
    # drawing - screen space (one call per player viewport)
    # ------------------------------------------------------------------ #
    def draw_screen(self, window, view_rect, player, ui_font, dt):
        """Hurt / low-health vignette, combo counter, kill-streak banners."""
        now = _now()
        w, h = view_rect.size

        # ---- hurt vignette + low health heartbeat ---- #
        hurt_until = getattr(player, "_fx_hurt_until", 0.0)
        strength = 0.0
        if now < hurt_until:
            strength = max(strength, _clamp((hurt_until - now) / 0.45) * getattr(player, "_fx_hurt_str", 0.6))
        max_hp = max(1.0, float(getattr(player, "max_health", 1) or 1))
        frac = _clamp(player.health / max_hp)
        if 0 < frac < 0.3 and not player.dead and not getattr(player, "death", False):
            beat = 0.5 + 0.5 * math.sin(now * (5.5 + (0.3 - frac) * 14))
            strength = max(strength, (0.18 + 0.32 * beat) * (1.0 - frac / 0.3 * 0.5))
        if strength > 0.02:
            img = self._vignette((w, h))
            img.set_alpha(int(255 * _clamp(strength)))
            window.blit(img, view_rect.topleft)

        # ---- combo counter ---- #
        count = getattr(player, "_fx_combo", 0)
        until = getattr(player, "_fx_combo_until", 0.0)
        if count >= 2 and now < until:
            left = _clamp((until - now) / COMBO_WINDOW)
            pop = _clamp((now - getattr(player, "_fx_combo_pop", 0.0)) / 0.18)
            size = int(max(22, h * 0.07) * (1.0 + 0.45 * (1 - pop)))
            heat = _clamp((count - 2) / 8.0)
            col = (255, int(224 - 112 * heat), int(151 - 59 * heat))
            finisher_next = (count + 1) % FINISHER_EVERY == 0
            x = view_rect.right - int(w * 0.04)
            y = view_rect.y + int(h * 0.30)
            font = ui_font(size, True)
            img = font.render(f"x{count}", True, col)
            sh = font.render(f"x{count}", True, INK)
            window.blit(sh, sh.get_rect(topright=(x + 3, y + 3)))
            rect = window.blit(img, img.get_rect(topright=(x, y)))
            lab = ui_font(max(11, int(h * 0.026)), True)
            tag = "FINISHER READY" if finisher_next else "COMBO"
            tl = lab.render(tag, True, CORAL if finisher_next else CREAM)
            window.blit(tl, tl.get_rect(topright=(x, rect.bottom - 2)))
            bar_w = max(60, int(w * 0.09))
            bar = pygame.Rect(0, 0, bar_w, max(4, int(h * 0.009)))
            bar.topright = (x, rect.bottom + tl.get_height())
            pygame.draw.rect(window, (40, 24, 32), bar, border_radius=3)
            fill = bar.copy()
            fill.width = int(bar.width * left)
            pygame.draw.rect(window, col, fill, border_radius=3)

        # ---- banners ---- #
        if self.banners:
            stack = 0
            for b in self.banners:
                if b["owner"] is not None and b["owner"] is not player:
                    continue
                u = b["age"] / b["life"]
                slide = 1.0 - (1.0 - _clamp(u / 0.12)) ** 3
                alpha = 255 * _clamp(1.0 - (u - 0.75) / 0.25)
                size = int(max(20, h * (0.075 if b["big"] else 0.052)) * (0.7 + 0.3 * slide))
                font = ui_font(size, True)
                img = font.render(b["txt"], True, b["color"])
                sh = font.render(b["txt"], True, INK)
                img.set_alpha(int(alpha))
                sh.set_alpha(int(alpha * 0.8))
                cx = view_rect.centerx
                cy = view_rect.y + int(h * 0.33) + stack
                rect = img.get_rect(center=(cx, cy))
                window.blit(sh, rect.move(3, 3))
                window.blit(img, rect)
                stack += int(size * 1.15)
                if b["sub"]:
                    sf = ui_font(max(11, int(h * 0.026)), True)
                    si = sf.render(b["sub"], True, CREAM)
                    si.set_alpha(int(alpha))
                    window.blit(si, si.get_rect(center=(cx, cy + int(size * 0.75))))
                    stack += int(size * 0.35)

    def _vignette(self, size):
        """Red, opaque at the screen edges and clear in the middle (cached per size)."""
        key = ("vig", size)
        img = self._font_cache.get(key)
        if img is None:
            n = 48
            small = pygame.Surface((n, n), pygame.SRCALPHA)
            half = (n - 1) / 2.0
            for y in range(n):
                for x in range(n):
                    d = math.hypot((x - half) / half, (y - half) / half)
                    a = _clamp((d - 0.55) / 0.55)
                    small.set_at((x, y), (200, 20, 30, int(215 * a * a)))
            img = pygame.transform.smoothscale(small, size)
            if len(self._font_cache) > 12:
                self._font_cache.clear()
            self._font_cache[key] = img
        return img


_FX = None


def fx():
    global _FX
    if _FX is None:
        _FX = CombatFX()
        _low_spec()
    return _FX


# ---------------------------------------------------------------------- #
# hooks
# ---------------------------------------------------------------------- #
def _hitstop(game, speed):
    """Freeze-frame: the game's own game_speed ramps back up +0.1 / frame."""
    try:
        if game is not None and game.game_speed > speed:
            game.game_speed = speed
    except Exception:
        pass


@_safe
def dodged(victim, attacker, obj, type_):
    """True when a player is inside dash i-frames: the hit is cancelled."""
    if getattr(victim, "type", None) != "player" and not getattr(victim, "dash_dodge", False):
        return False                                   # (enemies dodge only when the Entity Editor gave them a dodging dash)
    now = _now()
    if now >= getattr(victim, "_fx_iframes_until", 0.0):
        return False
    center = victim.rect.center
    f = fx()
    if now - getattr(victim, "_fx_dodge_text", 0.0) > 0.3:
        victim._fx_dodge_text = now
        f.text(center[0], victim.rect.top - 12, "DODGE", (150, 220, 255), 20, life=0.8, vy=-60)
        f.sparks(center[0], center[1], (150, 220, 255), -math.pi / 2, math.pi, 8, 150, 0.35, 2)
        if _is_entity(attacker) and now - getattr(victim, "_fx_perfect_at", 0.0) > 1.2:
            victim._fx_perfect_at = now
            f.banner(victim, "PERFECT DODGE", (150, 220, 255), life=1.1)
            f.flash(center[0], center[1], (150, 220, 255), 30, 0.35, ring=True, ring_to=90)
            _hitstop(getattr(victim, "game", None), 0.12)
    return True


@_safe
def bonus_damage(attacker, victim, dealt, obj, type_):
    """Crit / combo / finisher extra damage for player hits. Returns the extra amount."""
    f = fx()
    f._pending = None
    if getattr(attacker, "type", None) == "enemy" and getattr(attacker, "crit_chance", 0.0) > 0:
        # an enemy given a crit chance in the Entity Editor: crits only (no combo chain)
        if dealt > 0 and type_ not in ("fire", "lava", "toxic") and random.random() < attacker.crit_chance:
            f._pending = (True, False, 1)
            return dealt * float(getattr(attacker, "crit_bonus", CRIT_BONUS))
        return 0.0
    if getattr(attacker, "type", None) != "player" or getattr(victim, "type", None) != "enemy":
        return 0.0
    if type_ in ("fire", "lava", "toxic") or dealt <= 0:
        return 0.0
    now = _now()
    count = getattr(attacker, "_fx_combo", 0) if now < getattr(attacker, "_fx_combo_until", 0.0) else 0
    count += 1
    attacker._fx_combo = count
    attacker._fx_combo_until = now + COMBO_WINDOW
    attacker._fx_combo_pop = now
    f.best_combo = max(f.best_combo, count)
    finisher = count % FINISHER_EVERY == 0
    chance = CRIT_CHANCE + float(getattr(attacker, "crit_chance", 0.0))
    crit = random.random() < chance
    mult = min(COMBO_BONUS_CAP, COMBO_STEP_BONUS * (count - 1))
    if finisher:
        mult += FINISHER_BONUS
    if crit:
        mult += CRIT_BONUS
    f._pending = (crit, finisher, count)
    return dealt * mult


@_safe
def on_shield(victim):
    """Shield Bubble swallowed a hit."""
    f = fx()
    cx, _ = victim.rect.center
    f.sparks(cx, victim.rect.top + 8, (120, 200, 255), -math.pi / 2, 2.4, 12, 160, 0.5, 2)
    from . import charm_ui
    charm_ui.floating(victim.game, victim.rect.midtop, f"BLOCKED  {victim.shield_left} left", (140, 210, 255))


@_safe
def on_hit(victim, attacker, obj, type_, hp_before):
    """Spawn every bit of feedback for one landed hit (and the kill, if it was one)."""
    f = fx()
    dealt = hp_before - victim.health
    pending, f._pending = getattr(f, "_pending", None), None
    if dealt <= 0:
        return
    game = getattr(victim, "game", None)
    now = _now()
    cx, cy = victim.rect.center
    victim_is_player = getattr(victim, "type", None) == "player"
    killed = victim.health <= 0 and not (getattr(victim, "death", False) or getattr(victim, "dead", False)) \
        and not getattr(victim, "_fx_killed", False)

    # ---------------- environment damage (fire, lava, water spikes ...) ---------------- #
    kind = type_ if isinstance(type_, str) else (obj if isinstance(obj, str) else None)
    from_entity = _is_entity(attacker)
    if not from_entity or kind in ("fire", "lava", "toxic"):
        if now - getattr(victim, "_fx_env_at", 0.0) > 0.28:
            victim._fx_env_at = now
            col = (255, 150, 60) if kind != "toxic" else (140, 220, 90)
            f.sparks(cx, victim.rect.top + 8, col, -math.pi / 2, 1.2, 4, 120, 0.55, 2)
            if victim_is_player:
                victim._fx_hurt_until = now + 0.25
                victim._fx_hurt_str = 0.35
        if killed:
            f.debris(victim.rect, _rgb_of(victim), 16)
            victim._fx_killed = True
        return

    crit, finisher, count = pending if pending else (False, False, 0)

    # ---------------- direction + palette ---------------- #
    ax, ay = attacker.rect.center
    dx = cx - ax
    angle = math.atan2(cy - ay, dx) if (dx or cy != ay) else 0.0
    if abs(dx) < 4:
        angle = -math.pi / 2
    frac = _clamp(dealt / max(1.0, float(getattr(victim, "max_health", 1) or 1)))
    amount = max(1, int(round(dealt)))

    if victim_is_player:
        num_col, size, spark_col = (255, 96, 84), 22 + int(24 * frac), RED
    elif finisher:
        num_col, size, spark_col = CORAL, 30, (255, 150, 90)
    elif crit:
        num_col, size, spark_col = GOLD, 28, GOLD
    else:
        num_col, size, spark_col = WHITE, 17 + int(10 * min(1.0, frac * 4)), (255, 236, 190)

    label = str(amount)
    if finisher and not victim_is_player:
        label = f"{amount}!"
    elif crit and not victim_is_player:
        label = f"{amount}!"
    f.text(cx + random.uniform(-10, 10), victim.rect.top - 6, label, num_col, size,
           life=1.05 if (crit or finisher) else 0.85, vx=random.uniform(-26, 26),
           vy=-130 if (crit or finisher) else -95, pop=0.9 if (crit or finisher) else 0.5)
    if crit and not victim_is_player:
        f.text(cx, victim.rect.top - 30 - size, "CRIT", GOLD, 15, life=0.7, vy=-70)

    # ---------------- sparks, light, slash ---------------- #
    heavy = crit or finisher or killed
    f.sparks(cx - math.cos(angle) * 10, cy, spark_col, angle, 1.5 if not heavy else 2.4,
             7 + int(18 * min(1.0, frac * 3)) + (10 if heavy else 0), 230 if not heavy else 330,
             0.42, 3)
    f.flash(cx, cy, spark_col, 34 if not heavy else 60, 0.14 if not heavy else 0.22)
    f.slash(cx - math.cos(angle) * 14, cy - 4, angle, spark_col, 44 if not heavy else 70,
            0.16 if not heavy else 0.22, 4 if not heavy else 6)
    if finisher and not victim_is_player:
        f.flash(cx, cy, CORAL, 24, 0.4, ring=True, ring_to=110)

    victim._fx_flash_until = now + (0.16 if heavy else 0.1)

    # ---------------- weight: hit-stop, shake, knockback ---------------- #
    if victim_is_player:
        victim._fx_hurt_until = now + 0.45
        victim._fx_hurt_str = _clamp(0.45 + frac * 5.0, 0.45, 1.0)
        victim.shake_frames = max(getattr(victim, "shake_frames", 0), 8 + int(frac * 20))
        victim.shake_intensity = max(getattr(victim, "shake_intensity", 0), int(3 + 14 * min(1.0, frac * 4)))
        _hitstop(game, 0.0 if frac > 0.12 else 0.2)
    elif getattr(attacker, "type", None) == "player":
        if finisher:
            attacker.shake_frames = max(getattr(attacker, "shake_frames", 0), 12)
            attacker.shake_intensity = max(getattr(attacker, "shake_intensity", 0), 9)
            attacker.fx_knock_mult = 2.0
            try:                                    # launch the victim a little
                victim.y_vel = min(getattr(victim, "y_vel", 0), -240)
            except Exception:
                pass
            f.banner(attacker, "FINISHER!", CORAL, life=0.9)
            _hitstop(game, 0.0)
        elif crit:
            attacker.shake_frames = max(getattr(attacker, "shake_frames", 0), 8)
            attacker.shake_intensity = max(getattr(attacker, "shake_intensity", 0), 6)
            attacker.fx_knock_mult = 1.4
            _hitstop(game, 0.0)
        else:
            attacker.shake_frames = max(getattr(attacker, "shake_frames", 0), 4)
            attacker.shake_intensity = max(getattr(attacker, "shake_intensity", 0), 3)
            _hitstop(game, 0.3)

    # ---------------- kills ---------------- #
    if killed:
        victim._fx_killed = True
        _on_kill(f, game, now, attacker, victim)


def _on_kill(f, game, now, attacker, victim):
    color = _rgb_of(victim)
    f.debris(victim.rect, color, 22 if getattr(victim, "type", None) == "enemy" else 34)
    cx, cy = victim.rect.center
    f.flash(cx, cy, WHITE, 26, 0.35, ring=True, ring_to=100)

    if getattr(victim, "type", None) == "player":
        f.banner(victim, "YOU FELL", RED, life=1.6, big=True)
        _hitstop(game, 0.0)
        return

    f.kills_this_world += 1
    boss = getattr(victim, "is_boss", False)
    if boss:
        f.debris(victim.rect, (255, 220, 160), 40)
        f.flash(cx, cy, GOLD, 50, 0.8, ring=True, ring_to=260)
        for p in getattr(game, "local_players", None) or []:
            p.shake_frames = max(getattr(p, "shake_frames", 0), 40)
            p.shake_intensity = max(getattr(p, "shake_intensity", 0), 10)
        f.banner(None, "BOSS DEFEATED", GOLD, life=2.6, big=True)
        _hitstop(game, 0.0)
        try:
            game.game_speed = 0.0
        except Exception:
            pass
        return

    if getattr(attacker, "type", None) == "player":
        streak = getattr(attacker, "_fx_streak", 0) if now < getattr(attacker, "_fx_streak_until", 0.0) else 0
        streak += 1
        attacker._fx_streak = streak
        attacker._fx_streak_until = now + STREAK_WINDOW
        name = STREAK_NAMES.get(min(streak, max(STREAK_NAMES)))
        if streak >= 2 and name:
            f.banner(attacker, name, GOLD if streak < 4 else CORAL, sub=f"{streak} kills in a row", life=1.7,
                     big=streak >= 4)
            if streak >= 3:
                _hitstop(game, 0.18)
        _hitstop(game, 0.05)


@_safe
def watch(entity):
    """Once per drawn entity: detect a dash starting / an enemy winding up an attack."""
    kind = getattr(entity, "type", None)
    now = _now()
    if kind == "player":
        dashing = bool(getattr(entity, "dashing", False))
        if dashing and not getattr(entity, "_fx_was_dashing", False):
            if now >= getattr(entity, "_fx_dash_ready", 0.0):
                entity._fx_iframes_until = now + DASH_IFRAMES
                entity._fx_dash_ready = now + DASH_COOLDOWN
                f = fx()
                x, y = entity.rect.midbottom
                back = -1 if getattr(entity, "direction", "right") == "right" else 1
                f.sparks(x, y - 4, (190, 190, 210), math.pi / 2 + back * 0.9, 1.1, 8, 120, 0.45, 3)
                f.flash(entity.rect.centerx, entity.rect.centery, (150, 200, 255), 20, 0.3, ring=True, ring_to=60)
        entity._fx_was_dashing = dashing
    elif kind == "enemy":
        target = getattr(entity, "target", None)
        winding = bool(getattr(entity, "attacking", False)) and getattr(target, "type", None) == "player"
        if winding and not getattr(entity, "_fx_was_attacking", False):
            if now - getattr(entity, "_fx_warn_at", 0.0) > 0.7:
                entity._fx_warn_at = now
                entity._fx_warn_until = now + 0.2
                fx().text(entity.rect.centerx, entity.rect.top - 28, "!", RED, 26, life=0.55, vy=-35, pop=0.8)
        entity._fx_was_attacking = winding


_TINT_CACHE = {}


def tint(entity, image):
    """The entity's image, brightened while it is flashing (hit) or winding up (warning)."""
    flash_until = getattr(entity, "_fx_flash_until", 0.0)
    warn_until = getattr(entity, "_fx_warn_until", 0.0)
    if not flash_until and not warn_until:
        return image
    now = _now()
    if now < flash_until:
        add = (170, 170, 170, 255)
    elif now < warn_until:
        add = (140, 10, 10, 255)
    else:
        return image
    try:
        key = (id(image), add)
        hit = _TINT_CACHE.get(key)
        if hit is not None and hit[0] is image:
            return hit[1]
        out = pygame.mask.from_surface(image).to_surface(unsetcolor=(0, 0, 0, 0), setcolor=add)
        if len(_TINT_CACHE) > 80:
            _TINT_CACHE.clear()
        _TINT_CACHE[key] = (image, out)
        return out
    except Exception:
        return image
