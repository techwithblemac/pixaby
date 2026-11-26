"""
lighting.py
===========
Dynamic 2D lighting, soft contact shadows and fireflies for the world view.

How it works (per player viewport, once per frame):

    1. draw_shadow()   is called from draw_funcs.draw() right *before* each
                       entity / coin is drawn, so a soft ellipse sits on the
                       ground under its feet (behind the sprite, on top of
                       the blocks).
    2. apply()         builds a small "lightmap" (ambient darkness + every
                       visible light added on top), scales it up and
                       MULTIPLIES it over the viewport. Anything not near a
                       light falls into shadow.
    3. Fireflies       drift around each camera, add their own tiny light to
                       the lightmap and get a bright additive core drawn
                       *after* the multiply so they always glow.

Performance notes
    - The lightmap is rendered at LIGHT_SCALE of the viewport (0.5 normal,
      0.25 on LOW_SPEC_MODE) and every light sprite is a cached radial
      gradient bucketed by radius, so a frame is: 1 blit (ambient) +
      N small additive blits + 1 scale + 1 multiply blit.
    - Nothing here allocates per frame except tiny lists.

Toggle everything from Settings: LIGHTING, SHADOWS, FIREFLIES.
"""

import math
import random
from collections import OrderedDict

import pygame

from ..settings import Settings
from ..entities.burn import Burn
from . import ui_theme as ui


# ---------------------------------------------------------------------- #
# Tunables
# ---------------------------------------------------------------------- #
def _cfg(name, default):
    return getattr(Settings, name, default)


LOW = bool(getattr(Settings, "LOW_SPEC_MODE", False))
LIGHT_SCALE = 0.25 if LOW else 0.5
FIREFLY_COUNT = 14 if LOW else 34
SPRITE_CACHE_CAP = 360          # was 160: flickering lights + firefly colours evicted sprites every frame
COLOR_STEP = 8                  # light colours are bucketed to this step so gradients are shared

# Ambient darkness for the whole world (multiplied over the scene).
# Brighter = less moody. Per-biome tints are mixed in by ambient_for().
BASE_AMBIENT = (78, 70, 112)

# ambient tint from the level's block palette when no tag matched (data/biomes.py)
BIOME_PALETTE_AMBIENT = {
    "2": (112, 76, 70), "3": (110, 92, 70), "4": (80, 104, 84), "5": (90, 112, 138),
    "6": (120, 62, 52), "7": (74, 56, 110), "8": (118, 80, 58),
}

BIOME_AMBIENT = [            # first tag that matches wins
    ("lava", (120, 62, 52)), ("fire", (120, 62, 52)), ("ash", (98, 72, 66)),
    ("water", (56, 84, 120)), ("ice", (88, 110, 135)),
    ("overworld", (92, 100, 112)), ("grass", (92, 100, 112)),
    ("ruins", (100, 84, 78)), ("dungeon", (70, 58, 92)), ("stone", (78, 74, 98)),
]

# light presets: (color, radius in world px, strength 0..1, flicker 0..1)
WARM_PLAYER = ((255, 222, 176), 250, 0.95, 0.03)
TORCH = ((255, 150, 60), 230, 1.0, 0.16)
FIRE = ((255, 120, 40), 190, 1.0, 0.24)
FIRE_TRAP = ((255, 110, 45), 160, 0.9, 0.22)
BURN_GLOW = ((255, 128, 44), 0.85, 0.30)    # colour, strength, flicker - radius follows the size of the flames
BURN_RADIUS_PER_PX = 1.7                  # light radius = flame box size * this ...
BURN_RADIUS_MIN, BURN_RADIUS_MAX = 70, 190  # ... clamped to this
MAX_BURN_LIGHTS = 40                      # per viewport, so a forest fire stays cheap
BOMB_FUSE = ((255, 96, 40), 70, 0.8, 0.35)
BOMB_BLAST = ((255, 196, 110), 420, 1.0, 0.10)
DOOR = ((150, 200, 255), 130, 0.55, 0.04)
SHROOM = ((90, 225, 200), 95, 0.55, 0.05)
# lava pools: every tile on the surface throws a big warm glow, tiles deeper
# in the pool add a smaller one (on a checkerboard, so a huge lake stays cheap)
LAVA_SURFACE = ((255, 112, 34), 210, 1.0, 0.10)
LAVA_DEEP = ((255, 72, 20), 120, 0.75, 0.06)
LAVA_TILE = 64
MAX_LAVA_LIGHTS = 70            # per viewport; beyond this lava lights are thinned out evenly
FIREFLY = ((205, 255, 120), 46, 0.75, 0.0)

GEM_LIGHT = {
    "yellow": (255, 205, 90), "red": (255, 90, 90),
    "green": (110, 230, 140), "pink": (245, 150, 210),
}


# ---------------------------------------------------------------------- #
# Cached sprites
# ---------------------------------------------------------------------- #
_LIGHT_SPRITES = OrderedDict()
_SHADOWS = {}
_AMBIENT_BASE = {}
_CORES = {}


def _light_sprite(color, radius):
    """Radial gradient on black (for BLEND_RGB_ADD). Bucketed by radius."""
    radius = max(4, int(radius) // 4 * 4)
    color = tuple(min(255, (c + COLOR_STEP // 2) // COLOR_STEP * COLOR_STEP) for c in color)
    key = (color, radius)
    img = _LIGHT_SPRITES.get(key)
    if img is not None:
        _LIGHT_SPRITES.move_to_end(key)
        return img

    img = pygame.Surface((radius * 2, radius * 2))
    img.fill((0, 0, 0))
    steps = max(6, min(radius, 28))
    for i in range(steps):
        t = i / steps                       # 0 = outer ring, 1 = centre
        r = int(radius * (1 - t))
        f = t * t * (3 - 2 * t)             # smoothstep falloff
        c = tuple(min(255, int(ch * f)) for ch in color)
        pygame.draw.circle(img, c, (radius, radius), max(1, r))
    _LIGHT_SPRITES[key] = img
    if len(_LIGHT_SPRITES) > SPRITE_CACHE_CAP:
        _LIGHT_SPRITES.popitem(last=False)
    return img


def _shadow_sprite(w, h):
    w = max(6, int(w) // 2 * 2)
    h = max(3, int(h) // 2 * 2)
    key = (w, h)
    img = _SHADOWS.get(key)
    if img is None:
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        steps = 6
        for i in range(steps):
            k = 1 - i / steps
            rect = pygame.Rect(0, 0, int(w * k), int(h * k))
            rect.center = (w // 2, h // 2)
            pygame.draw.ellipse(img, (8, 6, 14, 26), rect)
        _SHADOWS[key] = img
        if len(_SHADOWS) > 120:
            _SHADOWS.clear()
    return img


_SHADOW_FADED = {}


def _shadow_faded(img, w, h, level):
    """Airborne shadows: a few cached alpha steps instead of a surface copy per entity per frame."""
    key = (img.get_width(), img.get_height(), level)
    out = _SHADOW_FADED.get(key)
    if out is None:
        out = img.copy()
        out.set_alpha(int(255 * (1 - 0.6 * level / 6.0)))
        if len(_SHADOW_FADED) > 200:
            _SHADOW_FADED.clear()
        _SHADOW_FADED[key] = out
    return out


def _ambient_base(size, color):
    """Ambient fill with slightly darker corners (cheap baked vignette)."""
    key = (size, color)
    img = _AMBIENT_BASE.get(key)
    if img is None:
        sw, sh = 64, 36
        dark = tuple(int(c * 0.55) for c in color)
        small = pygame.Surface((sw, sh))
        small.fill(dark)
        steps = 18
        for i in range(steps):
            t = i / steps                                  # 0 = outer, 1 = centre
            k = min(1.0, t / 0.55)
            c = tuple(int(dark[j] + (color[j] - dark[j]) * k) for j in range(3))
            rect = pygame.Rect(0, 0, int(sw * 1.6 * (1 - t)), int(sh * 1.6 * (1 - t)))
            rect.center = (sw // 2, sh // 2)
            pygame.draw.ellipse(small, c, rect)
        img = pygame.transform.smoothscale(small, size)
        _AMBIENT_BASE[key] = img
        if len(_AMBIENT_BASE) > 12:
            _AMBIENT_BASE.clear()
    return img


def _core_sprite(color, radius):
    key = (color, radius)
    img = _CORES.get(key)
    if img is None:
        img = pygame.Surface((radius * 2, radius * 2))
        img.fill((0, 0, 0))
        for i in range(radius, 0, -1):
            f = (1 - i / radius) ** 1.6
            pygame.draw.circle(img, tuple(int(c * f) for c in color), (radius, radius), i)
        _CORES[key] = img
    return img


# ---------------------------------------------------------------------- #
# Fireflies
# ---------------------------------------------------------------------- #
class Firefly:
    __slots__ = ("x", "y", "vx", "vy", "phase", "blink", "speed", "size", "hue")

    def __init__(self, area):
        self.respawn(area)

    def respawn(self, area):
        self.x = random.uniform(area.left, area.right)
        self.y = random.uniform(area.top, area.bottom)
        ang = random.uniform(0, math.tau)
        self.speed = random.uniform(14, 34)
        self.vx = math.cos(ang) * self.speed
        self.vy = math.sin(ang) * self.speed
        self.phase = random.uniform(0, math.tau)
        self.blink = random.uniform(0.6, 1.4)
        self.size = random.choice((2, 2, 3))
        self.hue = random.choice(((205, 255, 120), (255, 236, 130), (170, 255, 170)))

    def update(self, dt, t):
        # lazy wandering: steer the heading with a smooth noise-ish wobble
        wob = math.sin(t * 0.9 + self.phase) * 1.6 + math.sin(t * 2.3 + self.phase * 1.7) * 0.7
        ang = math.atan2(self.vy, self.vx) + wob * dt
        self.vx = math.cos(ang) * self.speed
        self.vy = math.sin(ang) * self.speed - math.sin(t * 1.3 + self.phase) * 4
        self.x += self.vx * dt
        self.y += self.vy * dt

    def brightness(self, t):
        b = 0.5 + 0.5 * math.sin(t * 2.2 * self.blink + self.phase)
        return b * b


class Swarm:
    """One swarm per camera; fireflies live in world space around it."""

    def __init__(self):
        self.flies = []

    def update(self, cam_world, dt, t, count=None):
        area = cam_world.inflate(cam_world.width * 0.3, cam_world.height * 0.3)
        target = FIREFLY_COUNT if count is None else count
        while len(self.flies) < target:
            self.flies.append(Firefly(area))
        if len(self.flies) > target:
            del self.flies[target:]
        for f in self.flies:
            f.update(dt, t)
            if not area.collidepoint(f.x, f.y):
                f.respawn(area)


# ---------------------------------------------------------------------- #
# Lighting system
# ---------------------------------------------------------------------- #
class Lighting:
    def __init__(self, game):
        self.game = game
        self.t = 0.0
        self.swarms = {}
        self._lightmaps = {}
        self._full = {}
        self._level = None
        self.ambient = BASE_AMBIENT
        self.flash = 0.0                # global screen flash (explosions)
        self._lava_kind = {}            # id(lava zone) -> LAVA_SURFACE / LAVA_DEEP / None

        # Adaptive quality: when the frame rate sags the lighting steps itself down
        # (cheaper upscale -> smaller lightmap, no shadows -> lighting off) and climbs
        # back when there is headroom. See QUALITY_TIERS and _govern().
        self.tier = 0
        self._ema = 1000.0 / max(1, _cfg("FPS", 60))
        self._last_change = -99.0
        self._last_up = -99.0
        self._up_cooldown = 8.0

    # ---- switches -------------------------------------------------- #
    @property
    def enabled(self):
        return _cfg("LIGHTING", True) and self.tier < 3

    @property
    def shadows(self):
        return _cfg("SHADOWS", True) and self.tier < 2

    @property
    def fireflies(self):
        return _cfg("FIREFLIES", True) and self.tier < 3

    # ---- per-frame --------------------------------------------------- #
    def _govern(self, frame_ms):
        """Frame-time governor with hysteresis. Spikes (loading, pause, window drag) are ignored.

        Settings: ADAPTIVE_QUALITY (on/off), ADAPTIVE_MIN_FPS (step down below this, default 30),
        ADAPTIVE_MAX_TIER (deepest tier it may use on its own, default 2: lighting itself is never
        switched off automatically; set 3 to allow it)."""
        if not _cfg("ADAPTIVE_QUALITY", True) or frame_ms <= 0 or frame_ms > 250:
            return
        self._ema += (frame_ms - self._ema) * 0.06
        min_fps = max(5.0, float(_cfg("ADAPTIVE_MIN_FPS", 30)))
        max_tier = int(_cfg("ADAPTIVE_MAX_TIER", 2))
        slow = 1000.0 / min_fps                     # below this: cut quality
        fast = 1000.0 / (min_fps * 1.45)            # comfortably above it: try a better tier again
        since = self.t - self._last_change
        if self._ema > slow and self.tier < max_tier and since > 2.0:
            if self.t - self._last_up < 8.0:        # stepped up and it hurt: wait longer next time
                self._up_cooldown = min(self._up_cooldown * 2, 120.0)
            self.tier += 1
            self._last_change = self.t
            self._ema = (slow + fast) / 2
        elif self._ema < fast and self.tier > 0 and since > self._up_cooldown:
            self.tier -= 1
            self._last_change = self._last_up = self.t
            self._ema = (slow + fast) / 2

    def update(self, dt):
        self.t += dt
        self._govern(dt * 1000.0)
        self.flash = max(0.0, self.flash - dt * 2.5)
        level = getattr(self.game, "level", None)
        if level != self._level:
            self._level = level
            self.ambient = self.ambient_for()
            self.swarms.clear()
            self._lava_kind.clear()

    def ambient_for(self):
        try:
            from .world_intro import world_info
            tags = [str(t).lower() for t in world_info(self.game).get("tags", [])]
        except Exception:
            tags = []
        tint = None
        for key, color in BIOME_AMBIENT:
            if any(key in t for t in tags):
                tint = color
                break
        if tint is None:
            try:
                from ..data.biomes import current
                tint = BIOME_PALETTE_AMBIENT.get(current(self.game))
            except Exception:
                tint = None
        if tint is None:
            return BASE_AMBIENT
        return tuple(int((a + b) / 2) for a, b in zip(BASE_AMBIENT, tint))

    # ---- shadows (called from draw_funcs.draw) ----------------------- #
    def draw_shadow(self, window, obj, cam, zoom):
        if not self.shadows:
            return
        nature = getattr(obj, "nature", None)
        kind = getattr(obj, "type", None)
        if nature != "entity" and kind != "treasure":
            return
        if getattr(obj, "dead", False) and nature == "entity":
            return

        rect = obj.rect
        # lift off the ground -> smaller, lighter shadow
        air = 0.0
        if nature == "entity" and not getattr(obj, "on_ground", True):
            air = min(1.0, getattr(obj, "fall_count", 0) / 1.2)
        k = 1.0 - 0.45 * air
        w = rect.width * 0.95 * k * zoom
        h = max(6, rect.width * 0.26 * k * zoom)
        img = _shadow_sprite(w, h)
        if air:
            img = _shadow_faded(img, w, h, int(air * 6 + 0.5))
        x = (rect.centerx - cam[0]) * zoom - img.get_width() / 2
        y = (rect.bottom - cam[1]) * zoom - img.get_height() * 0.55
        window.blit(img, (int(x), int(y)))

    # ---- lava ------------------------------------------------------- #
    def _classify_lava(self):
        """Sort every lava tile into surface (nothing lava above it) or deep.
        Done once per level; rising lava moves as a block so it stays valid."""
        zones = [z for z in getattr(self.game, "zones", ()) or ()
                 if getattr(z, "water_type", None) == "lava"]
        cells = {(z.rect.x // LAVA_TILE, z.rect.y // LAVA_TILE) for z in zones}
        for z in zones:
            gx, gy = z.rect.x // LAVA_TILE, z.rect.y // LAVA_TILE
            if (gx, gy - 1) not in cells:
                self._lava_kind[id(z)] = LAVA_SURFACE
            elif (gx + gy) % 2 == 0:
                self._lava_kind[id(z)] = LAVA_DEEP
            else:
                self._lava_kind[id(z)] = None

    def _lava_preset(self, obj):
        kinds = self._lava_kind
        if id(obj) not in kinds:
            self._classify_lava()
            kinds.setdefault(id(obj), LAVA_SURFACE)      # a zone we don't know about: just light it
        return kinds[id(obj)]

    # ---- collecting lights -------------------------------------------- #
    def _lights_for(self, objects, view):
        t = self.t
        out = []
        add = out.append
        hit = view.colliderect
        lava = []
        burning = 0
        for obj in objects:
            # plain attribute reads (try/except for the odd object without them) instead of
            # getattr(..., default): this loop runs over every object, every frame
            try:
                rect = obj.rect
            except AttributeError:
                continue
            if rect is None or not hit(rect):
                continue
            try:
                kind = obj.type
            except AttributeError:
                kind = None
            if kind == "water":
                if getattr(obj, "water_type", None) == "lava":
                    preset = self._lava_preset(obj)
                    if preset is not None:
                        lava.append((obj, preset))
                continue
            try:
                name = obj.name or ""
            except AttributeError:
                name = ""
            if name.__class__ is not str:
                name = str(name)
            preset = None

            if burning < MAX_BURN_LIGHTS:           # anything on fire (enemy, deco, tree ...) glows, whatever else it is
                glow = Burn.glow_of(obj)
                if glow is not None:
                    burning += 1
                    gx, gy, size = glow
                    color, strength, flicker = BURN_GLOW
                    seed = (id(obj) % 997) * 0.37
                    n = (math.sin(t * 13.0 + seed) * 0.5 + math.sin(t * 27.3 + seed * 2.1) * 0.3
                         + math.sin(t * 6.1 + seed * 0.7) * 0.2)
                    radius = max(BURN_RADIUS_MIN, min(BURN_RADIUS_MAX, size * BURN_RADIUS_PER_PX))
                    add((gx, gy, color, radius * (1.0 + flicker * 0.35 * n), strength))

            if kind == "player":
                if not getattr(obj, "dead", False):
                    preset = WARM_PLAYER
            elif kind == "enemy":
                if name == "Torch" and not getattr(obj, "dead", False):
                    preset = TORCH
            elif name == "fire" and kind != "trap":
                preset = FIRE
            elif name == "bomb":
                if getattr(obj, "death", False):
                    preset = BOMB_BLAST
                    self.flash = max(self.flash, 0.35)
                else:
                    preset = BOMB_FUSE
            elif kind == "treasure":
                c = GEM_LIGHT.get(name)
                if c:
                    preset = (c, 70, 0.6, 0.0)
            elif kind == "trap":
                if "fire" in name.lower() and getattr(obj, "animation_name", "") == "on":
                    preset = FIRE_TRAP
            elif getattr(obj, "nature", None) == "door_object":
                preset = getattr(obj, "light_preset", None) or DOOR      # door_fx sets it per kind / locked / open
            elif "shroom" in name:
                preset = SHROOM

            if preset is None:
                continue
            color, radius, strength, flicker = preset
            seed = (id(obj) % 997) * 0.37
            if flicker:
                n = (math.sin(t * 11.0 + seed) * 0.5 + math.sin(t * 23.7 + seed * 2.1) * 0.3
                     + math.sin(t * 5.3 + seed * 0.7) * 0.2)
                radius *= 1.0 + flicker * 0.35 * n
            else:
                radius *= 1.0 + 0.04 * math.sin(t * 2.0 + seed)
            add((rect.centerx, rect.centery, color, radius, strength))

        # lava glows from its surface; thin out evenly on huge lakes
        max_lava = MAX_LAVA_LIGHTS if self.tier < 2 else MAX_LAVA_LIGHTS // 2
        if len(lava) > max_lava:
            lava.sort(key=lambda p: p[1] is not LAVA_SURFACE)   # surface first
            step = len(lava) / max_lava
            lava = [lava[int(i * step)] for i in range(max_lava)]
            boost = min(1.6, step ** 0.5)                       # fewer, bigger lights
        else:
            boost = 1.0
        for obj, (color, radius, strength, flicker) in lava:
            rect = obj.rect
            seed = (rect.x * 0.013 + rect.y * 0.007)
            n = math.sin(t * 2.1 + seed) * 0.6 + math.sin(t * 5.3 + seed * 1.7) * 0.4   # slow lava "breathing"
            r = radius * boost * (1.0 + flicker * n)
            y = rect.top + 6 if (color, radius, strength, flicker) == LAVA_SURFACE else rect.centery
            add((rect.centerx, y, color, r, strength))
        return out

    # ---- the main pass ------------------------------------------------- #
    def apply(self, viewport, objects, cam, zoom, player=None):
        """Light the already-drawn viewport. Call after the world draw,
        before the HUD."""
        if not self.enabled:
            if self.fireflies:
                self._fireflies_only(viewport, cam, zoom, player)
            return

        vw, vh = viewport.get_size()
        if vw <= 0 or vh <= 0:
            return
        s = 0.25 if (LOW or self.tier >= 2) else LIGHT_SCALE
        lw, lh = max(1, int(vw * s)), max(1, int(vh * s))

        lm = self._lightmaps.get((lw, lh))
        if lm is None:
            lm = pygame.Surface((lw, lh)).convert()
            self._lightmaps[(lw, lh)] = lm

        amb = self.ambient
        if self.flash > 0:
            f = self.flash
            amb = tuple(min(255, int(c + (255 - c) * f * 0.6)) for c in amb)
        lm.blit(_ambient_base((lw, lh), amb), (0, 0))

        k = zoom * s
        cx, cy = cam
        z = zoom or 1
        view = pygame.Rect(int(cx), int(cy), int(vw / z), int(vh / z)).inflate(520, 520)
        for wx, wy, color, radius, strength in self._lights_for(objects or (), view):
            r = radius * k
            if r < 3:
                continue
            col = color if strength >= 0.99 else tuple(int(c * strength) for c in color)
            spr = _light_sprite(col, r)
            half = spr.get_width() // 2
            lm.blit(spr, (int((wx - cx) * k) - half, int((wy - cy) * k) - half),
                    special_flags=pygame.BLEND_RGB_ADD)

        swarm = self._swarm(player, viewport, cam, zoom) if self.fireflies else None
        if swarm:
            for f in swarm.flies:
                b = f.brightness(self.t)
                if b < 0.08:
                    continue
                b = round(b * 8) / 8.0                     # few brightness steps -> few cached sprites
                col = tuple(int(c * b * 0.75) for c in f.hue)
                spr = _light_sprite(col, FIREFLY[1] * k)
                half = spr.get_width() // 2
                lm.blit(spr, (int((f.x - cx) * k) - half, int((f.y - cy) * k) - half),
                        special_flags=pygame.BLEND_RGB_ADD)

        if (lw, lh) != (vw, vh):
            full = self._full.get((vw, vh))
            if full is None:
                full = pygame.Surface((vw, vh)).convert()
                self._full[(vw, vh)] = full
            if LOW or self.tier >= 1:
                pygame.transform.scale(lm, (vw, vh), full)
            else:
                pygame.transform.smoothscale(lm, (vw, vh), full)
            viewport.blit(full, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        else:
            viewport.blit(lm, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

        if swarm:
            self._draw_cores(viewport, swarm, cam, zoom)

        if len(self._lightmaps) > 6:
            self._lightmaps.clear()
            self._full.clear()

    # ---- fireflies helpers --------------------------------------------- #
    def _swarm(self, player, viewport, cam, zoom):
        key = getattr(player, "id", 0) if player is not None else 0
        swarm = self.swarms.get(key)
        if swarm is None:
            swarm = self.swarms[key] = Swarm()
        vw, vh = viewport.get_size()
        z = zoom or 1
        cam_world = pygame.Rect(int(cam[0]), int(cam[1]), int(vw / z), int(vh / z))
        dt = getattr(self.game, "dt", 1 / 60) or 1 / 60
        swarm.update(cam_world, dt, self.t, FIREFLY_COUNT // 2 if self.tier >= 2 else FIREFLY_COUNT)
        return swarm

    def _draw_cores(self, viewport, swarm, cam, zoom):
        cx, cy = cam
        for f in swarm.flies:
            b = f.brightness(self.t)
            if b < 0.05:
                continue
            r = max(3, int((f.size + 3) * zoom))
            b = round(b * 8) / 8.0
            col = tuple(int(c * (0.35 + 0.65 * b)) for c in f.hue)
            spr = _core_sprite(col, r)
            viewport.blit(spr, (int((f.x - cx) * zoom) - r, int((f.y - cy) * zoom) - r),
                          special_flags=pygame.BLEND_RGB_ADD)

    def _fireflies_only(self, viewport, cam, zoom, player):
        swarm = self._swarm(player, viewport, cam, zoom)
        self._draw_cores(viewport, swarm, cam, zoom)


# ---------------------------------------------------------------------- #
# Access
# ---------------------------------------------------------------------- #
def get(game):
    sys_ = getattr(game, "_lighting", None)
    if sys_ is None:
        sys_ = Lighting(game)
        game._lighting = sys_
    return sys_
