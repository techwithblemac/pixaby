"""
door_fx.py
==========
The effect layer for doors (objects/objects.py ``Door`` keeps ALL gameplay logic; this only looks).
Each kind is recognisable at a glance without reading its name:

    teleport  violet   motes spiral inward, pulsing ripples (faster when you are near)
                       enter: the traveller is sucked in (a squashing ghost) + violet flash
                       arrive: pop-out ring, sparkle burst, snap with a flash
    warp      cyan     a rotating rune ring, tiny sparks arcing up; near: dotted arrow previews
                       toward its targets
                       enter: cyan streak along the path; arrive: ripple + burst + camera whip-pan
    exit      green    LOCKED: dim red glow, a red padlock, slow ember drip
                       OPEN: warm green god-rays, rising leaves of light
                       enter: the door flares, the screen brightens, rays converge, ~0.35 s later the
                       level ends (the cleared card then starts from that flare)
                       unlock: a one-time burst + the camera looks at the door

Structure
    Door.draw      -> draw_back (glow, rays, rings) / the sprite / draw_front (motes, runes, lock)
                      Only doors that are ON SCREEN are drawn (draw_funcs culls), and all the
                      per-door animation state advances inside draw, so off-screen doors cost nothing.
    Door.update_sprite -> on_update: unlock detection, the light preset, the exit hand-off timer
    game.py        -> draw_world: the short-lived events (suction, arrival, streaks, unlock bursts)

Budgets: <= MAX_PARTS particles per door, <= MAX_EVENTS events in the world. Glow, ring and ray sprites
are cached; nothing is created per frame. Effects are OFF in the level editor (``game.EDIT_WORLD``).
Non-player travellers (enemies, bombs, arrows) get a smaller, cheaper version.
Real time (pygame ticks) drives everything, never the slow-mo scaled dt.
"""

import math
import random

import pygame

from . import ui_fx as fx
from ..data.palletes.doors import PORTAL_COLORS, frame_swaps

MAX_PARTS = 16
MAX_EVENTS = 24
NEAR_DISTANCE = 120
EXIT_DELAY_MS = 350            # flare time before the level actually ends
INK = (18, 17, 25)

_colors = {}
_rings = {}
_rays = {}


# ---------------------------------------------------------------------- #
# colours + cached sprites
# ---------------------------------------------------------------------- #
def colors(door):
    """(light, dark) of this door's portal, nudged 20% toward its biome's frame highlight."""
    key = (door.kind, door.biome)
    c = _colors.get(key)
    if c is None:
        light, dark = PORTAL_COLORS.get(door.kind, PORTAL_COLORS["teleport"])
        swaps = frame_swaps(door.biome)
        if swaps:
            tint = max(swaps.values(), key=sum)
            light, dark = fx.lerp_color(light, tint, 0.2), fx.lerp_color(dark, tint, 0.2)
        c = _colors[key] = (tuple(int(v) for v in light), tuple(int(v) for v in dark))
    return c


def _ring(radius, width, color):
    radius = max(2, int(radius) // 2 * 2)
    key = (radius, width, tuple(color[:3]))
    img = _rings.get(key)
    if img is None:
        if len(_rings) > 160:
            _rings.clear()
        img = pygame.Surface((radius * 2 + 6, radius * 2 + 6), pygame.SRCALPHA)
        pygame.draw.circle(img, (*color[:3], 255), (radius + 3, radius + 3), radius, max(1, width))
        _rings[key] = img
    return img


def _blit_ring(window, center, radius, width, color, alpha):
    if alpha <= 0:
        return
    img = _ring(radius, width, color)
    img.set_alpha(int(max(0, min(255, alpha))))
    window.blit(img, (int(center[0]) - img.get_width() // 2, int(center[1]) - img.get_height() // 2))


def _ray(w, h, color):
    w, h = max(4, int(w) // 4 * 4), max(4, int(h) // 4 * 4)      # coarse buckets: few distinct sprites, each built once
    key = (w, h, tuple(color[:3]))
    img = _rays.get(key)
    if img is None:
        if len(_rays) > 60:
            _rays.clear()
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            u = y / h                                          # 0 top .. 1 bottom
            half = max(1, int(w * (0.18 + 0.32 * u) / 2))     # a shaft that widens toward its source
            a = int(120 * (u ** 1.4))
            for x in range(-half, half + 1):
                edge = 1.0 - abs(x) / (half + 1)
                img.set_at((w // 2 + x, y), (*color[:3], int(a * edge)))
        _rays[key] = img
    return img


# ---------------------------------------------------------------------- #
# per-door state
# ---------------------------------------------------------------------- #
class DoorFx:
    __slots__ = ("parts", "last", "dt", "near", "t", "spawn", "was_open", "entering", "rune", "ring_t")

    def __init__(self):
        self.parts = []            # [kind, a, b, c, d, age, life]
        self.last = None
        self.dt = 0.0
        self.near = 0.0
        self.t = random.uniform(0, 6.0)
        self.spawn = 0.0
        self.was_open = None       # exit doors: was the exit open last frame
        self.entering = None       # exit doors: pygame ticks at which the level ends
        self.rune = 0.0
        self.ring_t = 0.0


def attach(door):
    door.fx = DoorFx()
    door.light_preset = None


def _editor(game):
    return bool(getattr(game, "EDIT_WORLD", False))


def _players(game):
    return getattr(game, "local_players", None) or getattr(game, "players", None) or []


def _is_open(door):
    obj = getattr(door.game, "objective", None)
    return obj is None or obj.exit_open()


# ---------------------------------------------------------------------- #
# gameplay-side hooks (called from Door.update_sprite / _try_*)
# ---------------------------------------------------------------------- #
def on_update(door):
    """Unlock detection, the light preset and the exit hand-off. Cheap; runs for every door."""
    f = door.fx
    game = door.game
    if _editor(game):
        return
    light, _ = colors(door)
    if door.kind == "exit":
        opened = _is_open(door)
        door.light_preset = (light, 170, 0.75, 0.04) if opened else ((255, 90, 70), 90, 0.32, 0.08)
        if f.was_open is None:
            f.was_open = opened
        elif opened and not f.was_open:
            _unlocked(door)
        f.was_open = opened
        if f.entering is not None and pygame.time.get_ticks() >= f.entering:
            f.entering = None
            from ..level import progression
            progression.level_won(game)
    elif door.kind == "warp":
        door.light_preset = (light, 140, 0.55, 0.04)
    else:
        door.light_preset = (light, 150, 0.6, 0.05)


def _event(game, **kw):
    ev = getattr(game, "_door_events", None)
    if ev is None:
        ev = game._door_events = []
    if len(ev) >= MAX_EVENTS:
        del ev[0]
    kw.setdefault("age", 0.0)
    kw.setdefault("seed", random.random() * 6.28)
    ev.append(kw)


def _unlocked(door):
    """Locked -> open: a one-time burst and the camera looks at the door."""
    game = door.game
    light, _ = colors(door)
    _event(game, kind="unlock", x=door.rect.centerx, y=door.rect.centery, col=light, life=1.1, scale=1.0)
    from . import lighting
    lighting.get(game).flash = max(lighting.get(game).flash, 0.35)
    for p in _players(game):
        cam = getattr(p, "camera", None)
        if cam is not None:
            cam.focus(door, 0.55, 1.5, 1.08)


def begin_exit(door, player):
    """A player walked into an OPEN exit: flare now, end the level a moment later (so it is seen)."""
    f = door.fx
    if f.entering is not None:
        return False
    f.entering = pygame.time.get_ticks() + EXIT_DELAY_MS
    light, _ = colors(door)
    game = door.game
    _event(game, kind="flare", x=door.rect.centerx, y=door.rect.centery, col=light, life=EXIT_DELAY_MS / 1000.0, scale=1.0)
    return True


def exiting(door):
    return door.fx.entering is not None


def on_teleport(door, obj, src, dst):
    """Something went through a teleport / warp door from ``src`` to ``dst`` (both world centres)."""
    game = door.game
    if _editor(game):
        return
    light, dark = colors(door)
    big = getattr(obj, "type", None) in ("player", "enemy")
    scale = 1.0 if big else 0.4
    size = (obj.rect.w, obj.rect.h)
    warp = door.kind == "warp"
    _event(game, kind="suck", x=src[0], y=src[1], x2=door.rect.centerx, y2=door.rect.centery, col=light, life=0.32 * (1 if big else 0.6),
           scale=scale, size=size)
    _event(game, kind="pop", x=dst[0], y=dst[1], col=light if not warp else (140, 235, 250), life=0.6 if big else 0.35, scale=scale,
           sparkle=big)
    if warp and big:
        _event(game, kind="trail", x=src[0], y=src[1], x2=dst[0], y2=dst[1], col=(140, 235, 250), life=0.4, scale=1.0)
    if getattr(obj, "type", None) == "player":
        from . import lighting
        lighting.get(game).flash = max(lighting.get(game).flash, 0.3 if not warp else 0.15)


def whip_camera(obj):
    """Warp doors: a very fast eased pan to the destination instead of a hard cut (teleports snap + flash)."""
    cam = getattr(obj, "camera", None)
    if cam is not None and hasattr(cam, "whip"):
        cam.whip(0.3)


# ---------------------------------------------------------------------- #
# world-space events (drawn from game.py once per view)
# ---------------------------------------------------------------------- #
def draw_world(game, window, cam, zoom):
    events = getattr(game, "_door_events", None)
    if not events or _editor(game):
        return
    now = pygame.time.get_ticks()
    last = getattr(game, "_door_events_t", None)
    game._door_events_t = now
    dt = 0.0 if last is None else min(0.05, (now - last) / 1000.0)
    # age once per frame, in the first view drawn this frame (a stamp stops split-screen from ageing twice)
    if getattr(game, "_door_events_frame", None) != now:
        game._door_events_frame = now
        for e in events:
            e["age"] += dt
        events[:] = [e for e in events if e["age"] < e["life"]]
    w, h = window.get_size()
    for e in events:
        sx, sy = (e["x"] - cam[0]) * zoom, (e["y"] - cam[1]) * zoom
        if e["kind"] == "trail":
            _draw_trail(window, e, cam, zoom)
            continue
        if sx < -200 or sy < -200 or sx > w + 200 or sy > h + 200:
            continue
        p = e["age"] / e["life"]
        k = e["scale"] * zoom
        col = e["col"]
        if e["kind"] == "suck":
            # a ghost squashes toward the door while a ring collapses
            ex, ey = (e["x2"] - cam[0]) * zoom, (e["y2"] - cam[1]) * zoom
            gx, gy = sx + (ex - sx) * p * p, sy + (ey - sy) * p * p
            gw, gh = e["size"][0] * zoom * max(0.05, 1 - p), e["size"][1] * zoom * (1 + 0.3 * p)
            if gw > 2:
                pygame.draw.ellipse(window, fx.lerp_color(col, (40, 22, 80), p), (gx - gw / 2, gy - gh / 2, gw, gh), max(1, int(2 * zoom)))
            _blit_ring(window, (ex, ey), (46 * (1 - p) + 4) * k, max(1, int(3 * zoom)), col, 230 * (1 - p))
        elif e["kind"] == "pop":
            ease = 1 - (1 - p) ** 3
            _blit_ring(window, (sx, sy), (8 + 54 * ease) * k, max(1, int(3 * zoom * (1 - p) + 1)), col, 240 * (1 - p))
            _blit_ring(window, (sx, sy), (4 + 30 * ease) * k, max(1, int(2 * zoom)), (255, 255, 255), 200 * (1 - p))
            fx.glow(window, (sx, sy), col, int(64 * k), 0.7 * (1 - p))
            if e.get("sparkle"):
                for i in range(10):
                    a = e["seed"] + i * math.tau / 10
                    d = (6 + 60 * ease) * k
                    pygame.draw.circle(window, fx.lerp_color(col, (255, 255, 255), 0.5), (int(sx + math.cos(a) * d), int(sy + math.sin(a) * d)),
                                       max(1, int(2.5 * zoom * (1 - p))))
        elif e["kind"] == "unlock":
            ease = 1 - (1 - p) ** 2
            _blit_ring(window, (sx, sy), (10 + 90 * ease) * k, max(1, int(4 * zoom * (1 - p) + 1)), col, 255 * (1 - p))
            _blit_ring(window, (sx, sy), (6 + 55 * ease) * k, max(1, int(2 * zoom)), (255, 255, 200), 220 * (1 - p))
            fx.glow(window, (sx, sy), col, int(150 * k), 0.9 * (1 - p))
            for i in range(14):
                a = e["seed"] + i * math.tau / 14
                d = (10 + 110 * ease) * k
                pygame.draw.circle(window, (230, 255, 200), (int(sx + math.cos(a) * d), int(sy - abs(math.sin(a)) * d * 0.9)),
                                   max(1, int(3 * zoom * (1 - p))))
        elif e["kind"] == "flare":
            fx.glow(window, (sx, sy), (220, 255, 220), int(240 * k * (0.5 + p)), min(1.4, 0.4 + 1.2 * p))
            for i in range(8):                                    # rays converge on the door
                a = i * math.tau / 8 + e["seed"]
                r0, r1 = (220 * (1 - p) + 10) * k, (220 * (1 - p) + 60) * k
                pygame.draw.line(window, fx.lerp_color(col, (255, 255, 255), p),
                                 (sx + math.cos(a) * r0, sy + math.sin(a) * r0), (sx + math.cos(a) * r1, sy + math.sin(a) * r1), max(1, int(3 * zoom)))
            from . import lighting
            lighting.get(game).flash = max(lighting.get(game).flash, 0.35 + 0.65 * p)   # the whole screen brightens


def _draw_trail(window, e, cam, zoom):
    p = e["age"] / e["life"]
    a = ((e["x"] - cam[0]) * zoom, (e["y"] - cam[1]) * zoom)
    b = ((e["x2"] - cam[0]) * zoom, (e["y2"] - cam[1]) * zoom)
    head = (a[0] + (b[0] - a[0]) * min(1.0, p * 2.2), a[1] + (b[1] - a[1]) * min(1.0, p * 2.2))
    tail = (a[0] + (b[0] - a[0]) * max(0.0, p * 2.2 - 0.6), a[1] + (b[1] - a[1]) * max(0.0, p * 2.2 - 0.6))
    w = max(1, int(5 * zoom * (1 - p)))
    col = fx.lerp_color(e["col"], (30, 70, 90), p)
    try:
        pygame.draw.line(window, col, tail, head, w)
        pygame.draw.circle(window, (255, 255, 255), (int(head[0]), int(head[1])), max(1, w))
    except (OverflowError, ValueError, TypeError):
        pass


# ---------------------------------------------------------------------- #
# per-door drawing (visible doors only)
# ---------------------------------------------------------------------- #
def _tick(door):
    f = door.fx
    now = pygame.time.get_ticks()
    f.dt = 0.0 if f.last is None else min(0.05, (now - f.last) / 1000.0)
    f.last = now
    f.t += f.dt
    # proximity of the nearest living local player
    cx, cy = door.rect.center
    inside = False
    for p in _players(door.game):
        if getattr(p, "dead", False) or getattr(p, "death", False):
            continue
        dx, dy = p.rect.centerx - cx, p.rect.centery - cy
        if dx * dx + dy * dy <= NEAR_DISTANCE * NEAR_DISTANCE:
            inside = True
            break
    f.near = fx.smooth_to(f.near, 1.0 if inside else 0.0, f.dt, 6.0)
    return f


def _spawn(f, kind, a, b, c, d, life):
    if len(f.parts) < MAX_PARTS:
        f.parts.append([kind, a, b, c, d, 0.0, life])


def _glow_level(base, near, t, f=2.0):
    return base + 0.28 * near + 0.05 * math.sin(t * f)


def draw_back(door, window, cam, zoom):
    """Behind the door sprite: glows, rays, ripples."""
    game = door.game
    if _editor(game):
        return
    f = _tick(door)
    zoom = round(zoom, 2)
    sx, sy = (door.rect.centerx - cam[0]) * zoom, (door.rect.centery - cam[1]) * zoom
    light, dark = colors(door)
    t, near = f.t, f.near

    if door.kind == "teleport":
        fx.glow(window, (sx, sy), light, int(72 * zoom), _glow_level(0.38, near, t))
        period = 1.5 - 0.8 * near                              # ripples speed up when you are close
        for i in range(2):
            u = ((t / period) + i * 0.5) % 1.0
            _blit_ring(window, (sx, sy), (6 + 30 * u) * zoom, max(1, int(2 * zoom)), light, 200 * (1 - u))
    elif door.kind == "warp":
        fx.glow(window, (sx, sy), light, int(66 * zoom), _glow_level(0.32, near, t, 2.6))
    else:                                                      # exit
        opened = _is_open(door)
        if f.entering is not None:
            u = 1.0 - max(0.0, (f.entering - pygame.time.get_ticks()) / EXIT_DELAY_MS)
            fx.glow(window, (sx, sy), (230, 255, 230), int(110 * zoom * (1 + u)), min(1.4, 0.7 + u))
        elif opened:
            fx.glow(window, (sx, sy), light, int(86 * zoom), _glow_level(0.5, near, t, 1.6))
            # warm god-rays, brighter and a touch wider when you are close
            rw, rh = 22 * zoom * (1 + 0.3 * near), 120 * zoom
            for i, off in enumerate((-20, -7, 7, 20)):
                ray = _ray(rw, rh, light)
                ray.set_alpha(int(255 * min(1.0, (0.35 + 0.25 * math.sin(t * 1.7 + i * 1.9)) * (1 + 0.8 * near))))
                window.blit(ray, (int(sx + off * zoom - ray.get_width() / 2 + 3 * zoom * math.sin(t * 0.9 + i)),
                                  int(sy + 10 * zoom - ray.get_height())))
        else:
            fx.glow(window, (sx, sy), (255, 90, 70), int(70 * zoom), 0.18 + 0.05 * math.sin(t * 2.2) + 0.1 * near)


def draw_front(door, window, cam, zoom):
    """In front of the sprite: motes, runes, the lock, previews."""
    game = door.game
    if _editor(game):
        return
    f = door.fx
    dt = f.dt
    zoom = round(zoom, 2)
    sx, sy = (door.rect.centerx - cam[0]) * zoom, (door.rect.centery - cam[1]) * zoom
    light, dark = colors(door)
    t, near = f.t, f.near
    f.spawn += dt * ({"teleport": 5.0 + 8.0 * near, "warp": 3.5 + 3.0 * near}.get(door.kind, 3.0))

    if door.kind == "teleport":
        while f.spawn >= 1.0:
            f.spawn -= 1.0
            life = 1.5 - 0.7 * near
            _spawn(f, "spiral", random.uniform(0, math.tau), 3.0 + 3.0 * near, 44.0, 44.0 / life, life)
        keep = []
        for p in f.parts:
            p[5] += dt
            if p[5] >= p[6]:
                continue
            p[1] += p[2] * dt                                  # angle
            p[3] = max(0.0, 44.0 - p[4] * p[5])                # radius shrinks toward the centre
            u = p[5] / p[6]
            x, y = sx + math.cos(p[1]) * p[3] * zoom, sy + math.sin(p[1]) * p[3] * zoom
            pygame.draw.circle(window, fx.lerp_color(light, (255, 255, 255), u * 0.6), (int(x), int(y)), max(1, int(2.4 * zoom * (1 - u * 0.6))))
            keep.append(p)
        f.parts = keep
    elif door.kind == "warp":
        f.rune += dt * (0.6 + 1.4 * near)
        r = 31 * zoom
        bright = 0.45 + 0.55 * near
        col = fx.lerp_color(dark, (210, 255, 255), bright)
        for i in range(8):                                     # the rune ring: ticks that rotate
            a = f.rune + i * math.tau / 8
            long = 0.18 if i % 2 == 0 else 0.1
            p1 = (sx + math.cos(a) * r * (1 - long), sy + math.sin(a) * r * (1 - long))
            p2 = (sx + math.cos(a) * r * 1.06, sy + math.sin(a) * r * 1.06)
            pygame.draw.line(window, col, p1, p2, max(1, int((2 + 2 * near) * zoom)))
        while f.spawn >= 1.0:
            f.spawn -= 1.0
            a = random.uniform(0, math.tau)
            _spawn(f, "spark", math.cos(a) * 28, math.sin(a) * 28, random.uniform(-12, 12), -random.uniform(40, 70), 0.9)
        keep = []
        for p in f.parts:
            p[5] += dt
            if p[5] >= p[6]:
                continue
            p[1] += p[3] * dt                                  # x
            p[2] += p[4] * dt                                  # y (a slight arc: slows while rising)
            p[4] *= 1 - 0.9 * dt
            u = p[5] / p[6]
            pygame.draw.circle(window, fx.lerp_color(light, (20, 60, 80), u), (int(sx + p[1] * zoom), int(sy + p[2] * zoom)), max(1, int(2 * zoom * (1 - u))))
            keep.append(p)
        f.parts = keep
        if near > 0.05 and door.targets:                       # dotted arrow toward where this door can send you
            for tgt in door.targets[:3]:
                dx, dy = tgt[0] - door.rect.centerx, tgt[1] - door.rect.centery
                dist = math.hypot(dx, dy)
                if dist < 60:
                    continue
                ux, uy = dx / dist, dy / dist
                reach = min(dist - 20, 210)
                march = (t * 90) % 28
                c = fx.lerp_color((20, 60, 80), light, near)
                d = 44 + march
                while d < reach:
                    pygame.draw.circle(window, c, (int(sx + ux * d * zoom), int(sy + uy * d * zoom)), max(1, int(2.2 * zoom)))
                    d += 28
                ax, ay = sx + ux * reach * zoom, sy + uy * reach * zoom
                s = 7 * zoom
                pygame.draw.polygon(window, c, [(ax + ux * s, ay + uy * s), (ax - ux * s - uy * s * 0.7, ay - uy * s + ux * s * 0.7),
                                                (ax - ux * s + uy * s * 0.7, ay - uy * s - ux * s * 0.7)])
    else:                                                      # exit
        opened = _is_open(door)
        if opened:
            while f.spawn >= 1.0:
                f.spawn -= 1.0
                _spawn(f, "leaf", random.uniform(-16, 16), 14.0, random.uniform(-6, 6), -random.uniform(18, 30), random.uniform(2.0, 3.2))
            keep = []
            for p in f.parts:
                if p[0] != "leaf":
                    continue
                p[5] += dt
                if p[5] >= p[6]:
                    continue
                p[2] += p[4] * dt
                u = p[5] / p[6]
                x = sx + (p[1] + math.sin(t * 2 + p[3]) * 6) * zoom
                col = fx.lerp_color((255, 240, 150), light, 0.5 + 0.5 * math.sin(t + p[3]))
                pygame.draw.circle(window, fx.lerp_color(col, (30, 60, 40), u * u), (int(x), int(sy + p[2] * zoom)), max(1, int(2.4 * zoom * (1 - u * 0.5))))
                keep.append(p)
            f.parts = keep
        else:
            while f.spawn >= 1.0:
                f.spawn -= 1.0
                _spawn(f, "drip", random.uniform(-14, 14), -24.0, 0.0, 14.0, 1.6)
            keep = []
            for p in f.parts:
                if p[0] != "drip":
                    continue
                p[5] += dt
                if p[5] >= p[6]:
                    continue
                p[4] += 60 * dt                                # an ember drips and speeds up
                p[2] += p[4] * dt
                u = p[5] / p[6]
                pygame.draw.circle(window, fx.lerp_color((255, 120, 70), (80, 20, 20), u), (int(sx + p[1] * zoom), int(sy + p[2] * zoom)),
                                   max(1, int(2.2 * zoom * (1 - u * 0.4))))
                keep.append(p)
            f.parts = keep
            _padlock(window, sx, sy - 2 * zoom, zoom, 0.6 + 0.4 * math.sin(t * 3))


def _padlock(window, x, y, zoom, glow):
    col = fx.lerp_color((120, 40, 40), (255, 100, 80), glow)
    w, h = 16 * zoom, 12 * zoom
    body = pygame.Rect(int(x - w / 2), int(y - h / 4), int(w), int(h))
    pygame.draw.arc(window, col, (int(x - w * 0.32), int(y - h * 0.95), int(w * 0.64), int(h * 1.1)), 0, math.pi, max(2, int(2.5 * zoom)))
    pygame.draw.rect(window, INK, body.inflate(3, 3), border_radius=3)
    pygame.draw.rect(window, col, body, border_radius=3)
    pygame.draw.circle(window, INK, body.center, max(1, int(2 * zoom)))
