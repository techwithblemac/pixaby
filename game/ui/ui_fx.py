"""
ui_fx.py
========
Small, reusable "juice" toolkit for the modal screens (shop, revive, ...).
Nothing in here knows about the shop or the game rules - it only draws and
animates.

    easing / lerp helpers      ease_out_back, smooth_to, lerp_color, ...
    draw_coin()                spinning coin taken from ``Assets.GEM_SPRITES``
                               (yellow=gold, red=ruby, green=emerald, pink=pearl)
    Particles                  sparks, ambient embers/ash, flying + falling
                               coins, floating text
    Shake                      screen-shake offset that decays by itself
    Layer                      draws a panel off-screen so it can pop in/out
                               (scale + fade) and queues additive glows
    wave_text / drop_text      animated lettering
    vignette / aura / glow     lighting helpers
"""

import math
import random

import pygame

from . import ui_theme as ui
from ..assets import Assets
from ..scripts.sounds import playit

# ---------------------------------------------------------------------- #
# Coins: every coin image comes from the Assets class
# ---------------------------------------------------------------------- #
COIN_SHEET = {"gold": "yellow", "ruby": "red", "emerald": "green", "pearl": "pink", "star": "star"}
COIN_COLORS = {
    "gold": ui.GOLD,
    "ruby": ui.RED,
    "emerald": ui.GREEN,
    "pearl": (240, 150, 200),
    "star": ui.GOLD,
}

_FRAME_CACHE = {}


def coin_frames(kind, size):
    """The spin frames of a coin at ``size`` px, straight from Assets.GEM_SPRITES."""
    key = (kind, size)
    frames = _FRAME_CACHE.get(key)
    if frames is None:
        sheet = list(getattr(Assets, "GEM_SPRITES", {}).get(COIN_SHEET.get(kind, kind)) or [])
        if len(sheet) > 2:
            sheet = sheet[:-1]          # last frame repeats the first: drop it so the loop is seamless
        frames = []
        for img in sheet:
            if img.get_width() != size:
                img = pygame.transform.scale(img, (size, size))
            frames.append(img)
        if not frames:                  # sheet missing: a plain drawn coin instead of a crash
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            c = size // 2
            pygame.draw.circle(surf, ui.INK, (c, c), max(2, c))
            pygame.draw.circle(surf, COIN_COLORS.get(kind, ui.GOLD), (c, c), max(1, c - 2))
            frames = [surf]
        _FRAME_CACHE[key] = frames
    return frames


def draw_coin(surface, center, kind, size, t=0.0, phase=0.0, fps=9.0, alpha=255):
    """Blit one frame of the spinning coin, centred on ``center``."""
    size = max(8, int(size))
    frames = coin_frames(kind, size)
    img = frames[int(t * fps + phase * len(frames)) % len(frames)]
    rect = img.get_rect(center=(int(center[0]), int(center[1])))
    if alpha < 255:
        img.set_alpha(max(0, int(alpha)))
        surface.blit(img, rect)
        img.set_alpha(255)
    else:
        surface.blit(img, rect)
    return rect


# ---------------------------------------------------------------------- #
# Math / easing
# ---------------------------------------------------------------------- #
def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    t = clamp(t)
    return tuple(int(a + (b - a) * t) for a, b in zip(c1[:3], c2[:3]))


def scale_color(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c[:3])


def ease_out_cubic(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out_back(t, s=1.70158):
    t = clamp(t) - 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def ease_out_bounce(t):
    t = clamp(t)
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


def smooth_to(current, target, dt, speed=14.0):
    """Frame-rate independent 'chase the target' used for every smooth number/colour."""
    value = current + (target - current) * (1 - math.exp(-speed * dt))
    return target if abs(target - value) < 0.002 else value


def pulse(t, speed=1.0):
    """0..1 sine wave."""
    return 0.5 + 0.5 * math.sin(t * speed * math.tau)


def heartbeat(t, bpm=64):
    """0..1 double-thump, like a pulse on a monitor."""
    ph = (t * bpm / 60.0) % 1.0
    return min(1.0, math.exp(-((ph - 0.05) / 0.05) ** 2) + 0.65 * math.exp(-((ph - 0.30) / 0.06) ** 2))


def bezier(p0, p1, p2, t):
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])


def sfx(origin, name):
    """Play a sound, never let a missing sound break the UI."""
    try:
        playit(name, origin)
    except Exception:
        pass


# ---------------------------------------------------------------------- #
# Lighting
# ---------------------------------------------------------------------- #
_GLOW = {}


def glow(surface, center, color, radius, strength=1.0, clip=None):
    """Soft additive light. ``clip`` keeps it inside a rect (e.g. one shop row)."""
    level = int(clamp(strength, 0.0, 1.5) * 10)
    if level <= 0:
        return
    radius = max(8, int(radius) // 8 * 8)
    key = (tuple(color[:3]), radius, level)
    img = _GLOW.get(key)
    if img is None:
        k = level / 10.0
        img = pygame.Surface((radius * 2, radius * 2))
        img.fill((0, 0, 0))
        steps = min(radius, 22)
        for i in range(steps):
            r = int(radius * (1 - i / steps))
            f = ((i + 1) / steps) ** 2 * 0.5 * k
            pygame.draw.circle(img, tuple(min(255, int(c * f)) for c in color[:3]), (radius, radius), max(1, r))
        _GLOW[key] = img
    old = surface.get_clip()
    if clip is not None:
        surface.set_clip(old.clip(clip))
    surface.blit(img, (int(center[0]) - radius, int(center[1]) - radius), special_flags=pygame.BLEND_RGB_ADD)
    surface.set_clip(old)


_VIGNETTES = {}


def vignette(size, color=(150, 10, 25), strength=220):
    """Dark-edged overlay, cached per window size."""
    key = (size, tuple(color), strength)
    img = _VIGNETTES.get(key)
    if img is None:
        small = pygame.Surface((96, 96), pygame.SRCALPHA)
        small.fill((*color, strength))
        for r in range(64, 0, -1):
            f = max(0.0, (r - 24) / 40.0)
            pygame.draw.circle(small, (*color, int(strength * f)), (48, 48), r)
        img = pygame.transform.smoothscale(small, size)
        _VIGNETTES[key] = img
    return img


def aura(surface, rect, color, intensity=1.0, radius=16):
    """A few soft rings around a panel."""
    for grow, alpha in ((10, 22), (6, 38), (3, 66)):
        ui.panel(surface, rect.inflate(grow * 2, grow * 2), (0, 0, 0, 0),
                 (*color[:3], int(alpha * clamp(intensity, 0.0, 1.5))), 2, radius + grow)


# ---------------------------------------------------------------------- #
# Text
# ---------------------------------------------------------------------- #
def text_alpha(surface, txt, pos, size, color, alpha=255, bold=False, center=False, shadow=True):
    f = ui.font(size, bold)
    img = f.render(str(txt), True, color)
    img.set_alpha(int(clamp(alpha, 0, 255)))
    rect = img.get_rect(center=(int(pos[0]), int(pos[1]))) if center else img.get_rect(topleft=(int(pos[0]), int(pos[1])))
    if shadow:
        sh = f.render(str(txt), True, ui.INK)
        sh.set_alpha(int(clamp(alpha * 0.6, 0, 255)))
        surface.blit(sh, rect.move(1, 1))
    surface.blit(img, rect)
    return rect


def wave_text(surface, txt, pos, size, c1, c2, t, amp=3.0, speed=2.2, bold=True, center=False):
    """Letters bob in a wave while a highlight sweeps across them."""
    f = ui.font(size, bold)
    widths = [f.size(ch)[0] for ch in txt]
    total = max(1, sum(widths))
    x = left = pos[0] - (total // 2 if center else 0)
    sweep = (t * 0.5) % 1.8 - 0.4
    for i, ch in enumerate(txt):
        if ch != " ":
            u = (x + widths[i] / 2 - left) / total
            col = lerp_color(c1, c2, 1 - abs(u - sweep) * 5)
            y = pos[1] + math.sin(t * speed + i * 0.5) * amp
            sh = f.render(ch, True, ui.INK)
            surface.blit(sh, (int(x) + 2, int(y) + 2))
            surface.blit(f.render(ch, True, col), (int(x), int(y)))
        x += widths[i]
    return total


def drop_text(surface, txt, center, size, color, age, stagger=0.07, drop=80, sway_t=None, glow_color=None):
    """Letters fall in one by one and bounce. Returns True once the last one has landed."""
    f = ui.font(size, True)
    widths = [f.size(ch)[0] for ch in txt]
    total = sum(widths)
    x = center[0] - total // 2
    done = True
    for i, ch in enumerate(txt):
        p = clamp((age - i * stagger) / 0.5)
        if p < 1:
            done = False
        if ch != " " and p > 0:
            y = center[1] - f.get_height() // 2 - (1 - ease_out_bounce(p)) * drop
            if sway_t is not None and p >= 1:
                y += math.sin(sway_t * 1.6 + i * 0.7) * 2.5
            sh = f.render(ch, True, ui.INK)
            sh.set_alpha(int(200 * p))
            surface.blit(sh, (int(x) + 3, int(y) + 3))
            img = f.render(ch, True, color)
            img.set_alpha(int(255 * clamp(p * 2)))
            surface.blit(img, (int(x), int(y)))
        x += widths[i]
    return done


# ---------------------------------------------------------------------- #
# Screen shake
# ---------------------------------------------------------------------- #
class Shake:
    def __init__(self):
        self.power = 0.0

    def kick(self, amount):
        self.power = min(14.0, self.power + amount)

    def update(self, dt):
        self.power *= math.exp(-9.0 * dt)
        if self.power < 0.05:
            self.power = 0.0

    def offset(self):
        if not self.power:
            return 0, 0
        return int(random.uniform(-1, 1) * self.power), int(random.uniform(-1, 1) * self.power)


# ---------------------------------------------------------------------- #
# Off-screen panel layer: pop-in / pop-out + deferred glows
# ---------------------------------------------------------------------- #
class Layer:
    def __init__(self):
        self.surf = None
        self.region = None
        self.glows = []

    def begin(self, screen_size, region):
        if self.surf is None or self.surf.get_size() != screen_size:
            self.surf = pygame.Surface(screen_size, pygame.SRCALPHA)
        region = region.clip(pygame.Rect(0, 0, screen_size[0], screen_size[1]))
        self.surf.fill((0, 0, 0, 0), region)
        self.region = region
        self.glows = []
        return self.surf

    def glow(self, center, color, radius, strength, clip=None):
        self.glows.append((center, color, radius, strength, clip))

    def commit(self, window, p=1.0, lift=16, min_scale=0.93):
        region = self.region
        sub = self.surf.subsurface(region)
        if abs(p - 1.0) < 0.002:
            window.blit(sub, region.topleft)
        else:
            s = min_scale + (1 - min_scale) * p
            size = (max(1, int(region.w * s)), max(1, int(region.h * s)))
            img = pygame.transform.smoothscale(sub, size)
            img.set_alpha(int(255 * clamp(p * 1.4)))
            window.blit(img, img.get_rect(center=(region.centerx, region.centery + int((1 - clamp(p)) * lift))))
        strength = clamp(p)
        for center, color, radius, st, clip in self.glows:
            glow(window, center, color, radius, st * strength, clip)
        self.glows = []


# ---------------------------------------------------------------------- #
# Particles
# ---------------------------------------------------------------------- #
class Particles:
    MAX = 600

    def __init__(self):
        self.items = []
        self._amb = 0.0

    def _add(self, p):
        if len(self.items) >= self.MAX:
            del self.items[0]
        self.items.append(p)

    # -------- spawners -------- #
    def spark(self, x, y, color, count=12, speed=170.0, life=0.65, size=3, gravity=260.0,
              spread=math.tau, angle=0.0):
        for _ in range(count):
            a = angle + random.uniform(-spread / 2, spread / 2)
            s = speed * random.uniform(0.35, 1.0)
            self._add({"k": "spark", "x": x, "y": y, "vx": math.cos(a) * s, "vy": math.sin(a) * s,
                       "age": 0.0, "life": life * random.uniform(0.6, 1.2), "size": size,
                       "color": color, "grav": gravity, "drag": 2.0})

    def ring(self, x, y, color, count=18, speed=220.0, life=0.6, size=3):
        for i in range(count):
            a = i / count * math.tau
            self._add({"k": "spark", "x": x, "y": y, "vx": math.cos(a) * speed, "vy": math.sin(a) * speed,
                       "age": 0.0, "life": life, "size": size, "color": color, "grav": 0.0, "drag": 3.0})

    def coin(self, x, y, cur, vx, vy, size=24, gravity=700.0, life=1.4):
        self._add({"k": "coin", "x": x, "y": y, "vx": vx, "vy": vy, "age": 0.0, "life": life, "size": size,
                   "cur": cur, "grav": gravity, "phase": random.random()})

    def burst_coins(self, x, y, cur, count, size=22):
        for _ in range(count):
            self.coin(x, y, cur, random.uniform(-190, 190), random.uniform(-460, -200), size)

    def shower(self, width, cur, count, size=22):
        for _ in range(count):
            self._add({"k": "coin", "x": random.uniform(0, width), "y": random.uniform(-200, -20),
                       "vx": random.uniform(-25, 25), "vy": random.uniform(150, 270), "age": 0.0, "life": 7.0,
                       "size": size, "cur": cur, "grav": 0.0, "phase": random.random(), "ymax": 4000})

    def text(self, x, y, txt, color, size=18, life=1.1, vy=-46.0):
        self._add({"k": "text", "x": x, "y": y, "vx": 0.0, "vy": vy, "age": 0.0, "life": life,
                   "txt": str(txt), "color": color, "size": size, "drag": 1.2, "grav": 0.0})

    def fly_coins(self, src, dst, cur, count=5, size=22, delay=0.0, dur=0.55, stagger=0.06, arc=90):
        for i in range(count):
            mid = ((src[0] + dst[0]) / 2 + random.uniform(-70, 70),
                   min(src[1], dst[1]) - arc * random.uniform(0.6, 1.4))
            self._add({"k": "fly", "p0": src, "p1": mid, "p2": dst, "cur": cur, "size": size,
                       "age": -(delay + i * stagger), "dur": dur, "life": 1e9, "phase": random.random()})

    def ambient(self, dt, w, h, color, rate=10.0, falling=False):
        """Slow drifting motes: embers rise, ash falls."""
        self._amb += dt * rate
        while self._amb >= 1.0:
            self._amb -= 1.0
            self._add({"k": "spark", "x": random.uniform(0, w), "y": -6 if falling else h + 6,
                       "vx": random.uniform(-8, 8),
                       "vy": random.uniform(16, 44) if falling else -random.uniform(18, 48),
                       "age": 0.0, "life": random.uniform(3.5, 7.0), "size": random.choice((1, 2, 2, 3)),
                       "color": color, "grav": 0.0, "drag": 0.0, "sway": random.uniform(6, 20),
                       "phase": random.uniform(0, math.tau), "env": "sin", "dim": 0.6})

    # -------- simulation -------- #
    def update(self, dt):
        keep, arrived = [], []
        for p in self.items:
            p["age"] += dt
            if p["age"] < 0:
                keep.append(p)
                continue
            kind = p["k"]
            if kind == "fly":
                if p["age"] >= p["dur"]:
                    arrived.append(p)
                else:
                    keep.append(p)
                continue
            if p["age"] >= p["life"]:
                continue
            drag = p.get("drag", 0.0)
            if drag:
                f = math.exp(-drag * dt)
                p["vx"] *= f
                p["vy"] *= f
            p["vy"] += p.get("grav", 0.0) * dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            if "sway" in p:
                p["x"] += math.sin(p["age"] * 1.7 + p["phase"]) * p["sway"] * dt
            if "ymax" in p and p["y"] > p["ymax"]:
                continue
            keep.append(p)
        self.items = keep
        for p in arrived:
            self.spark(p["p2"][0], p["p2"][1], COIN_COLORS.get(p["cur"], ui.GOLD),
                       count=7, speed=130, life=0.45, size=2, gravity=220)

    def draw(self, surface, t=0.0):
        for p in self.items:
            age = p["age"]
            if age < 0:
                continue
            kind = p["k"]
            if kind == "spark":
                if p.get("env") == "sin":
                    f = math.sin(math.pi * clamp(age / p["life"]))
                else:
                    f = clamp(1 - age / p["life"])
                f *= p.get("dim", 1.0)
                col = scale_color(p["color"], f)
                s = max(1, int(p["size"] * (0.5 + 0.5 * f)))
                surface.fill(col, (int(p["x"]), int(p["y"]), s, s), special_flags=pygame.BLEND_RGB_ADD)
            elif kind == "coin":
                a = 255 * clamp((p["life"] - age) / 0.35)
                draw_coin(surface, (p["x"], p["y"]), p["cur"], p["size"], t=age, phase=p["phase"], fps=12, alpha=a)
            elif kind == "text":
                q = age / p["life"]
                a = 255 * clamp(1 - (q - 0.55) / 0.45)
                pop = 1.0 + 0.35 * max(0.0, 1 - age / 0.18)
                text_alpha(surface, p["txt"], (p["x"], p["y"]), int(p["size"] * pop), p["color"], a, True, center=True)
            elif kind == "fly":
                u = clamp(age / p["dur"])
                x, y = bezier(p["p0"], p["p1"], p["p2"], ease_in_out(u))
                draw_coin(surface, (x, y), p["cur"], p["size"] * (1 - 0.25 * u), t=age, phase=p["phase"], fps=14)
