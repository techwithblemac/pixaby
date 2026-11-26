"""
burn.py
=======
``Burn`` - the burning status effect: applied to whatever a burning arrow / trap hits, ticks damage over time,
credits the kill to whoever lit it, and draws the game's own fire sprites on the victim.

    Burn.apply(target, seconds, dps, by)   a hit that sets the target alight (stronger / longer burn wins)
    Burn.touch(target)                     lava / fire contact: flames show briefly, their own damage is separate
    Burn.tick(entity, dt)                  every frame from ``mods.tick``: damage over time, extinguishes itself
    Burn.active(entity)                    True while flames should be drawn
    Burn.glow_of(entity)                   (world x, world y, size) to light, or None - read by ui/lighting.py
    Burn.draw(window, entity, ox, oy, zoom, box=None)  animated ``Assets.FIRE_SPRITES["on"]`` frames cropped to their pixels
                                              and scaled to the entity; procedural flames if the sheet is missing

State lives on the entity as ``entity.burn`` (a ``Burn``), so nothing else needs new attributes.
"""
import math
import random
import pygame

FRAME_MS = 30
FLAMMABLE = {"deco": 2.0, "tree": 1.0}      # scenery that catches fire -> burn damage per second
BURN_TIME = 4.0              # seconds a deco / tree burns
SPREAD_RADIUS = 32           # fire jumps to scenery this close
SPREAD_CHANCE = 0.05         # per check (every 0.4 s) per neighbour
SLOTS = 5                    # flames alive on one body at a time


def _rand(a, b, c, d):
    """Cheap deterministic 0..1 hash, so every flame keeps its place / size until its cycle ends."""
    v = math.sin(a * 12.9898 + b * 78.233 + c * 37.719 + d * 4.581) * 43758.5453
    return v - math.floor(v)


def _snap(v, step=4):
    return max(step, int(v) // step * step)          # snapped so the scaled-image cache stays small
_CACHE = {}
_CACHE_MAX = 160
_CROPPED = {}


def _frames():
    try:
        from ..assets import Assets
        sheet = getattr(Assets, "FIRE_SPRITES", None) or {}
        frames = sheet.get("on") or []
    except Exception:
        return []
    key = id(frames)
    if key not in _CROPPED:
        out = []
        for f in frames:
            box = f.get_bounding_rect(min_alpha=20)
            out.append(f.subsurface(box).copy() if box.width and box.height else f)
        _CROPPED[key] = out
    return _CROPPED[key]


def _scaled(frame_idx, frames, w, h):
    key = (id(frames), frame_idx, w, h)
    img = _CACHE.get(key)
    if img is None:
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.clear()
        img = pygame.transform.scale(frames[frame_idx], (w, h))
        _CACHE[key] = img
    return img


class Burn:
    def __init__(self):
        self.left = 0.0          # seconds of damage-over-time left
        self.dps = 0.0
        self.by = None           # who lit it (kill credit)
        self.show_until = 0      # pygame tick the flames are visible until
        self.spread_clock = 0.0
        self.glow = None         # (world x, world y, size) of the flames, set by Burn.draw, read by ui/lighting.py

    # ------------------------------------------------------------- applying
    @classmethod
    def of(cls, entity):
        b = getattr(entity, "burn", None)
        if not isinstance(b, Burn):
            b = entity.burn = cls()
        return b

    @classmethod
    def apply(cls, target, seconds, dps, by=None):
        """A hit that sets ``target`` alight. Longer / hotter burns win over weaker ones already running."""
        if seconds <= 0 or getattr(target, "dead", False):
            return None
        b = cls.of(target)
        b.left = max(b.left, seconds)
        b.dps = max(b.dps, dps)
        if by is not None:
            b.by = by
        b.show_until = pygame.time.get_ticks() + int(b.left * 1000)
        target.burning = True
        return b

    @classmethod
    def flammable(cls, obj):
        return getattr(obj, "type", None) in FLAMMABLE

    @classmethod
    def ignite_object(cls, obj, by=None):
        """Fire / a burning arrow / lava / a burning neighbour touches scenery: deco burns away (its health runs
        out), trees burn but survive. Anything else is left alone."""
        if not cls.flammable(obj) or getattr(obj, "dead", False):
            return None
        return cls.apply(obj, BURN_TIME, FLAMMABLE[obj.type], by)

    @classmethod
    def touch(cls, target, ms=600):
        """Lava / fire contact: show flames for a moment (their own damage is dealt by the hazard itself)."""
        b = cls.of(target)
        b.show_until = max(b.show_until, pygame.time.get_ticks() + ms)
        target.burning = True

    # ------------------------------------------------------------- per frame
    @classmethod
    def active(cls, entity):
        b = getattr(entity, "burn", None)
        return isinstance(b, Burn) and (b.left > 0 or b.show_until > pygame.time.get_ticks())

    @classmethod
    def glow_of(cls, entity):
        b = getattr(entity, "burn", None)
        if isinstance(b, Burn) and b.glow is not None and cls.active(entity):
            return b.glow
        return None

    @classmethod
    def tick(cls, entity, dt):
        b = getattr(entity, "burn", None)
        if not isinstance(b, Burn) or b.left <= 0:
            return
        b.left -= dt
        b.spread_clock += dt
        if b.spread_clock >= 0.4:
            b.spread_clock = 0.0
            cls._spread(entity, b)
        entity.health -= b.dps * dt
        if entity.health <= 0:
            if b.by is not None and b.by is not entity and getattr(entity, "nature", "entity") == "entity":
                b.by.kills += 1
            b.left = 0.0
        if b.left <= 0:
            b.left = 0.0
            b.dps = 0.0
            b.by = None
            entity.burning = False

    @classmethod
    def _spread(cls, src, burn):
        """A burning thing sets nearby scenery alight (bushes next to a burning bush, a burning enemy walking by)."""
        game = getattr(src, "game", None)
        objs = getattr(game, "damageable_objects_map", None)
        if objs is None:
            return
        from ..scripts.physics import PHYSICS as physics
        for other in physics.get_objects(objs, src.rect.inflate(SPREAD_RADIUS, SPREAD_RADIUS), 0):
            if other is src or not cls.flammable(other) or cls.active(other):
                continue
            if random.random() < SPREAD_CHANCE:
                cls.ignite_object(other, burn.by)

    # ------------------------------------------------------------- drawing
    @classmethod
    def draw(cls, window, entity, offset_x, offset_y, zoom, box=None):
        """``box`` (optional): a screen-space ``pygame.Rect`` to put the flames on instead of ``entity.rect`` -
        a living tree passes its whole drawn sprite, because its rect is only the stump."""
        rect = entity.rect
        if box is not None:
            left, top = box.x, box.y
            w = max(8, box.width)
            h = max(8, box.height)
        else:
            w = max(8, int(rect.width * zoom))
            h = max(8, int(rect.height * zoom))
            left = round((rect.x - offset_x) * zoom)
            top = round((rect.y - offset_y) * zoom)
        b = getattr(entity, "burn", None)
        if isinstance(b, Burn):                  # where the flames are, in world px, for ui/lighting.py
            z = zoom or 1
            b.glow = (offset_x + (left + w * 0.5) / z, offset_y + (top + h * 0.6) / z, max(w, h) / z)
        frames = _frames()
        if not frames:
            return cls._draw_fallback(window, entity, offset_x, offset_y, zoom, w, h, left, top)
        t = pygame.time.get_ticks()
        eid = (getattr(entity, "entity_id", None) or getattr(entity, "object_id", 0) or 0)
        n = len(frames)
        for k in range(SLOTS):
            # each slot lives 0.45-0.9 s, then reappears somewhere else on the body at another size
            life = 450 + int(_rand(eid, k, 0, 0) * 450)
            cycle, age = divmod(t + int(_rand(eid, k, 9, 0) * life), life)
            fx = 0.12 + 0.76 * _rand(eid, k, cycle, 1)             # where on the body (0 = left / top, 1 = right / bottom)
            fy = 0.35 + 0.65 * _rand(eid, k, cycle, 2)
            size = 0.45 + 0.30 * _rand(eid, k, cycle, 3)           # random size
            grow = max(0.35, math.sin(math.pi * age / life) ** 0.6)  # flares up, then dies down
            ph = int(_rand(eid, k, cycle, 4) * n)
            fh = _snap(h * size * grow * 1.1)
            fw = _snap(w * size * grow * (0.55 + 0.5 * _rand(eid, k, cycle, 5)))
            img = _scaled((t // FRAME_MS + ph) % n, frames, fw, fh)
            window.blit(img, (left + int(w * fx) - fw // 2, top + int(h * fy) - fh + int(h * 0.05)))

    @classmethod
    def _draw_fallback(cls, window, entity, offset_x, offset_y, zoom, w, h, left=None, top=None):
        t = pygame.time.get_ticks() / 1000.0
        x0 = left if left is not None else round((entity.rect.x - offset_x) * zoom)
        y0 = (top + h) if top is not None else round((entity.rect.bottom - offset_y) * zoom)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for i in range(4):
            ph = t * (7 + i) + i * 2.1
            cx = w * (0.15 + 0.7 * i / 3)
            tall = h * (0.75 + 0.3 * math.sin(ph))
            for col, k in (((255, 70, 20, 170), 1.0), ((255, 150, 30, 200), 0.7), ((255, 232, 120, 220), 0.4)):
                pygame.draw.polygon(surf, col, [(cx - w * 0.2 * k, h), (cx + math.sin(ph) * 3, h - tall * k), (cx + w * 0.2 * k, h)])
        window.blit(surf, (x0, y0 - h))
