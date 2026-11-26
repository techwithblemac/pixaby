"""
charm_ui.py
===========
Everything the Befriend Charm draws (rules live in scripts/charm_mode.py):

    world   reticle on the selected target (rotating brackets, pulsing ring, a
            countdown arc that drains), dim markers on the other candidates,
            hearts over friends, particles (hearts / shards) and floating numbers
    hud     the charm button with its stock badge, the dash badge, the big
            timer + hint line, CONFIRM / CANCEL buttons (touch and mouse), banners
            and the vignette flashes

All animation runs on REAL time (``tick`` gets the raw frame time) so it stays
smooth while the world is in slow motion. Nothing here allocates a surface per
frame: shapes are drawn with ``pygame.draw`` and the vignettes are cached by
``ui_fx.vignette``.
"""

import math

import pygame

from . import ui_theme as ui
from . import ui_fx as fx
from ..data import charms as C
from ..settings import Settings

PINK = (255, 130, 190)
CYAN = (110, 230, 255)
RED = (255, 80, 70)
GOLD = ui.GOLD

MAX_PARTS = 140


def _state(game):
    st = getattr(game, "_charm_fx", None)
    if st is None:
        st = game._charm_fx = {"banners": [], "flash": None, "parts": [], "floats": [],
                               "rects": {}, "view": {}, "t": 0.0}
    return st


# ---------------------------------------------------------------------- #
# events other modules push
# ---------------------------------------------------------------------- #
def banner(game, text, color):
    st = _state(game)
    st["banners"].append({"text": text, "color": color, "age": 0.0})
    del st["banners"][:-3]


def flash(game, color, strength=1.0):
    _state(game)["flash"] = [tuple(color), 1.0, strength]


def burst(game, pos, kind):
    st = _state(game)
    import random
    n = 10 if kind == "hearts" else 14
    for _ in range(n):
        ang = random.uniform(0, math.tau)
        spd = random.uniform(40, 170)
        st["parts"].append([pos[0], pos[1], math.cos(ang) * spd, math.sin(ang) * spd - (60 if kind == "hearts" else 0),
                            random.uniform(0.6, 1.1), 1.1, kind, random.uniform(5, 9)])
    del st["parts"][:-MAX_PARTS]


def floating(game, pos, text, color):
    st = _state(game)
    st["floats"].append([pos[0], pos[1], text, color, 0.0])
    del st["floats"][:-8]


def tick(game, raw):
    st = _state(game)
    st["t"] += raw
    for b in st["banners"]:
        b["age"] += raw
    st["banners"] = [b for b in st["banners"] if b["age"] < 1.9]
    if st["flash"]:
        st["flash"][1] -= raw / 0.9
        if st["flash"][1] <= 0:
            st["flash"] = None
    for p in st["parts"]:
        p[0] += p[2] * raw
        p[1] += p[3] * raw
        p[3] += 200 * raw
        p[4] -= raw
    st["parts"] = [p for p in st["parts"] if p[4] > 0]
    for f in st["floats"]:
        f[1] -= 40 * raw
        f[4] += raw
    st["floats"] = [f for f in st["floats"] if f[4] < 1.2]


# ---------------------------------------------------------------------- #
# small shapes
# ---------------------------------------------------------------------- #
def heart(surf, cx, cy, r, color, outline=True):
    r = max(2, int(r))
    left, right = (int(cx - r * 0.5), int(cy - r * 0.2)), (int(cx + r * 0.5), int(cy - r * 0.2))
    tip = (int(cx), int(cy + r * 0.95))
    pts = [(cx - r * 0.98, cy - r * 0.05), tip, (cx + r * 0.98, cy - r * 0.05)]
    if outline:
        pygame.draw.circle(surf, ui.INK, left, int(r * 0.55) + 2)
        pygame.draw.circle(surf, ui.INK, right, int(r * 0.55) + 2)
        pygame.draw.polygon(surf, ui.INK, [(p[0], p[1]) for p in pts], 4)
    pygame.draw.circle(surf, color, left, int(r * 0.55))
    pygame.draw.circle(surf, color, right, int(r * 0.55))
    pygame.draw.polygon(surf, color, pts)


def _arc_ring(surf, center, radius, frac, color, width):
    """A ring that drains: ``frac`` 1 = full circle."""
    if frac <= 0:
        return
    rect = pygame.Rect(0, 0, radius * 2, radius * 2)
    rect.center = (int(center[0]), int(center[1]))
    pygame.draw.arc(surf, color, rect, math.pi / 2, math.pi / 2 + math.tau * min(1.0, frac), width)


# ---------------------------------------------------------------------- #
# the dash ring (the time bar of scripts/dash_bar.py, drawn as a circle)
#
#   DRAINING  while dashing: the ring shrinks and warms blue -> amber -> red, a pale "ghost" arc shows what was
#             just spent, the button shakes harder the lower it gets, embers fly off the head of the ring.
#   FILLING   while it recharges: a bright sheen sweeps round the filled part, sparkles come off the head,
#             a ping rolls out when a dash becomes possible again and a bigger one when the ring is full.
#   STILL     full: a slow breathing glow; part-full and waiting: a calm, steady ring.
# ---------------------------------------------------------------------- #
DASH_BLUE = (120, 190, 255)
DASH_AMBER = (255, 176, 70)
DASH_MINT = (120, 245, 205)


def _q(color):
    """Quantise a colour so the glow cache does not grow a new entry for every frame of a colour fade."""
    return tuple(min(255, int(c) // 32 * 32 + 16) for c in color[:3])


def _ring_poly(center, r_in, r_out, a0, a1):
    steps = max(4, int(abs(a1 - a0) / (math.tau / 96)) + 1)
    outer, inner = [], []
    for i in range(steps + 1):
        a = a0 + (a1 - a0) * i / steps
        c, s_ = math.cos(a), math.sin(a)
        outer.append((center[0] + c * r_out, center[1] + s_ * r_out))
        inner.append((center[0] + c * r_in, center[1] + s_ * r_in))
    return outer + inner[::-1]


def _ring_fill(surf, center, r_in, r_out, f0, f1, color):
    """Part of a ring, from fraction f0 to f1 of a full turn, starting at 12 o'clock and going clockwise."""
    f0, f1 = max(0.0, f0), min(1.0, f1)
    if f1 - f0 <= 0.002:
        return
    if f0 <= 0.0 and f1 >= 0.998:
        pygame.draw.circle(surf, color, (int(center[0]), int(center[1])), int(r_out), max(1, int(r_out - r_in)))
        return
    a0 = -math.pi / 2 + math.tau * f0
    a1 = -math.pi / 2 + math.tau * f1
    pygame.draw.polygon(surf, color, _ring_poly(center, r_in, r_out, a0, a1))


def _head(center, radius, frac):
    a = -math.pi / 2 + math.tau * frac
    return center[0] + math.cos(a) * radius, center[1] + math.sin(a) * radius


def _ping(surf, center, radius, age, life, color, width=3):
    """An expanding ring that fades out."""
    if age >= life:
        return
    k = age / life
    r = int(radius * (1.0 + 0.9 * (1 - (1 - k) ** 2)))
    size = r * 2 + width * 2 + 4
    layer = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(layer, (*color, int(210 * (1 - k))), (size // 2, size // 2), r, max(1, int(width * (1 - k * 0.6))))
    surf.blit(layer, (int(center[0]) - size // 2, int(center[1]) - size // 2))


def _dash_anim(st, player, frac, t, can_now):
    """Per-player animation state, advanced from the real-time HUD clock."""
    book = st.setdefault("dash", {})
    a = book.get(id(player))
    if a is None:
        a = book[id(player)] = {"t": t, "last": frac, "shown": frac, "state": "still", "since": 0.0, "ping": [],
                                "sparks": [], "can": can_now, "full": frac >= 0.999, "empty_t": -9.0}
    dt = max(0.0, min(0.1, t - a["t"]))
    a["t"] = t
    delta = frac - a["last"]
    a["last"] = frac
    if delta < -1e-4:
        a["state"], a["since"] = "drain", 0.0
    elif delta > 1e-4:
        a["state"], a["since"] = "fill", 0.0
    else:
        a["since"] += dt
        if a["since"] > 0.15:
            a["state"] = "still"
    # the ghost lags behind what was just spent; on the way up it simply follows
    a["shown"] = frac if frac >= a["shown"] else max(frac, a["shown"] - dt * 0.55)
    if can_now and not a["can"]:
        a["ping"].append({"age": 0.0, "life": 0.45, "color": DASH_BLUE, "scale": 1.0})       # a dash is possible again
    if frac >= 0.999 and not a["full"]:
        a["ping"].append({"age": 0.0, "life": 0.7, "color": DASH_MINT, "scale": 1.5})        # full
    if frac <= 0.001 and a["last"] > -1 and not getattr(player, "dashing", False) and a.get("was_dashing"):
        a["empty_t"] = t                                                                    # ran dry: shake + flash
    a["can"], a["full"] = can_now, frac >= 0.999
    a["was_dashing"] = bool(getattr(player, "dashing", False))
    for p in a["ping"]:
        p["age"] += dt
    a["ping"] = [p for p in a["ping"] if p["age"] < p["life"]]
    for sp in a["sparks"]:
        sp[0] += sp[2] * dt
        sp[1] += sp[3] * dt
        sp[3] += sp[5] * dt
        sp[4] -= dt
    a["sparks"] = [sp for sp in a["sparks"] if sp[4] > 0][-40:]
    return a, dt


def _draw_dash(window, rc, r2, k, st, t, player):
    from ..scripts import dash_bar
    top = max(0.01, dash_bar.max_time(player))
    frac = dash_bar.fraction(player)
    dashing = bool(getattr(player, "dashing", False))
    can_now = frac >= dash_bar.MIN_START or dashing
    low = not can_now
    a, dt = _dash_anim(st, player, frac, t, can_now)
    state = a["state"]

    # ----- colour: blue, warming as it drains; minty and shimmering while it refills -----
    if state == "drain":
        col = fx.lerp_color(DASH_BLUE, DASH_AMBER, min(1.0, (1.0 - frac) * 1.5))
        if frac < dash_bar.MIN_START:
            col = fx.lerp_color(col, RED, 0.5 + 0.5 * math.sin(t * 16))
    elif state == "fill":
        col = fx.lerp_color(DASH_BLUE, DASH_MINT, 0.35 + 0.25 * math.sin(t * 6))
    else:
        col = DASH_BLUE if can_now else fx.lerp_color(DASH_BLUE, RED, 0.5 + 0.5 * math.sin(t * 5))

    # ----- movement: a shake that grows as the bar runs down, a pop when it runs dry, breathing when full -----
    cx, cy = rc
    since_empty = t - a["empty_t"]
    shake = 0.0
    if state == "drain":
        shake = (0.8 + (1.0 - frac) * 2.2) * k
    if since_empty < 0.35:
        shake = max(shake, 4.0 * k * (1.0 - since_empty / 0.35))
    if shake > 0:
        cx += math.sin(t * 71) * shake
        cy += math.cos(t * 53) * shake * 0.8
    center = (int(cx), int(cy))
    breathe = 0.5 + 0.5 * math.sin(t * 2.2)
    swell = 0.0
    if state == "drain":
        swell = 0.05 * (0.5 + 0.5 * math.sin(t * 26))
    elif state == "fill":
        swell = 0.03 * (0.5 + 0.5 * math.sin(t * 9))
    elif frac >= 0.999:
        swell = 0.025 * breathe
    rb = int(r2 * (1.0 + swell))
    ring_w = max(5, int(7 * k))
    r_in, r_out = rb + int(3 * k), rb + int(3 * k) + ring_w

    # ----- glow behind everything -----
    if state == "fill":
        fx.glow(window, center, _q(col), int(r_out * 2.3), 0.35 + 0.15 * math.sin(t * 8))
    elif state == "drain":
        fx.glow(window, center, _q(col), int(r_out * 2.0), 0.25 + 0.2 * (1.0 - frac))
    elif frac >= 0.999:
        fx.glow(window, center, DASH_MINT, int(r_out * 2.2), 0.14 + 0.16 * breathe)

    # ----- the button disc (its inside flashes when a dash starts / runs dry) -----
    disc = (36, 50, 76)
    if low:
        disc = fx.lerp_color(disc, (70, 30, 36), 0.5 + 0.5 * math.sin(t * 8))
    elif dashing:
        disc = fx.lerp_color(disc, (70, 62, 40), 0.35)
    pygame.draw.circle(window, ui.INK, center, r_out + 3)
    pygame.draw.circle(window, (22, 30, 46), center, r_out)             # the empty track
    pygame.draw.circle(window, disc, center, r_in - 1)

    # ----- the ring: ghost of what was just spent, then the live fill, then the sheen -----
    if a["shown"] > frac + 0.004:
        _ring_fill(window, center, r_in, r_out, frac, a["shown"], fx.lerp_color(col, (255, 255, 255), 0.55))
    _ring_fill(window, center, r_in, r_out, 0.0, frac, col)
    mark = dash_bar.MIN_START                                           # the tick where a dash becomes possible
    ma = -math.pi / 2 + math.tau * mark
    pygame.draw.line(window, (210, 222, 240),
                     (center[0] + math.cos(ma) * (r_in - 1), center[1] + math.sin(ma) * (r_in - 1)),
                     (center[0] + math.cos(ma) * (r_out + 1), center[1] + math.sin(ma) * (r_out + 1)), 2)
    if state == "fill" and frac > 0.02:
        s0 = (t * 0.9) % 1.0 * frac                                     # a bright band sweeping round the filled part
        _ring_fill(window, center, r_in, r_out, s0, min(frac, s0 + 0.07), fx.lerp_color(col, (255, 255, 255), 0.7))

    # ----- sparkles / embers off the head of the ring -----
    if 0.01 < frac < 0.999 and state in ("fill", "drain"):
        hx, hy = _head(center, (r_in + r_out) / 2, frac)
        if int(t * 40) != int((t - dt) * 40):
            for _ in range(2 if state == "fill" else 1):
                ang = math.atan2(hy - center[1], hx - center[0]) + (math.pi / 2 if state == "fill" else -math.pi / 2)
                spd = (22 if state == "fill" else 60) * k
                a["sparks"].append([hx, hy, math.cos(ang) * spd + (hash((t, _)) % 9 - 4) * k,
                                    math.sin(ang) * spd - 18 * k, 0.45, -40 * k if state == "fill" else 120 * k,
                                    col if state == "drain" else DASH_MINT])
    for sp in a["sparks"]:
        life = max(0.0, min(1.0, sp[4] / 0.45))
        r = max(1, int(2.4 * k * life))
        c = fx.lerp_color((40, 40, 50), sp[6], life)
        pygame.draw.circle(window, c, (int(sp[0]), int(sp[1])), r)
    for p in a["ping"]:
        _ping(window, center, r_out * p["scale"], p["age"], p["life"], p["color"])

    # ----- the seconds inside -----
    left = dash_bar.ensure(player)
    txt_col = RED if low else (ui.WHITE if state != "drain" else fx.lerp_color(ui.WHITE, DASH_AMBER, 1.0 - frac))
    size = int(19 * k * (1.0 + (0.08 * math.sin(t * 20) if state == "drain" else 0.0)))
    fx.text_alpha(window, f"{left:0.1f}", (center[0], center[1] - int(2 * k)), size, txt_col, 255, True, True)
    fx.text_alpha(window, "SEC", (center[0], center[1] + int(11 * k)), int(9 * k), (150, 170, 200), 200, True, True, shadow=False)
    fx.text_alpha(window, "DASH", (center[0], rc[1] + r_out + int(10 * k)), int(12 * k),
                  RED if low else ui.WHITE, 255, True, True)


def _brackets(surf, center, r, ang, color, width=3):
    cx, cy = center
    for k in range(4):
        a = ang + k * math.pi / 2
        c, s = math.cos(a), math.sin(a)
        corner = (cx + (c - s) * r, cy + (s + c) * r)
        e1 = (cx + (c - s) * r + (-c) * r * 0.45, cy + (s + c) * r + (-s) * r * 0.45)
        e2 = (cx + (c - s) * r + (s) * r * 0.45, cy + (s + c) * r + (-c) * r * 0.45)
        pygame.draw.lines(surf, ui.INK, False, [e1, corner, e2], width + 3)
        pygame.draw.lines(surf, color, False, [e1, corner, e2], width)


def _hp_bar(surf, x, y, w, h, frac, color):
    pygame.draw.rect(surf, ui.INK, (x - 2, y - 2, w + 4, h + 4), border_radius=3)
    pygame.draw.rect(surf, (60, 40, 50), (x, y, w, h), border_radius=2)
    pygame.draw.rect(surf, color, (x, y, int(w * max(0.0, min(1.0, frac))), h), border_radius=2)


# ---------------------------------------------------------------------- #
# classification used by both drawing and rules text
# ---------------------------------------------------------------------- #
def verdict(player, target):
    """("ok" | "strong" | "boss", label)"""
    if getattr(target, "is_boss", False):
        return "boss", "BOSS - IMMUNE"
    if target.health > player.health:
        return "strong", f"TOO STRONG  HP {int(target.health)} / yours {int(player.health)}"
    return "ok", f"HP {int(target.health)} / yours {int(player.health)} - OK"


# ---------------------------------------------------------------------- #
# world layer
# ---------------------------------------------------------------------- #
def draw_world(game, window, cam_topleft, zoom, player):
    st = _state(game)
    st["view"][id(player)] = (cam_topleft, zoom, getattr(player, "view_rect", window.get_rect()))
    cx0, cy0 = cam_topleft
    t = st["t"]

    def to_screen(x, y):
        return (x - cx0) * zoom, (y - cy0) * zoom

    # hearts over friends
    for f in player.friends:
        if f.dead or f.death:
            continue
        sx, sy = to_screen(f.rect.centerx, f.rect.top)
        bob = math.sin(t * 4 + f.rect.x * 0.01) * 3 * zoom
        heart(window, sx, sy - 16 * zoom + bob, 8 * zoom, PINK)

    s = getattr(player, "charm_session", None)
    if s is not None:
        pulse = 0.5 + 0.5 * math.sin(s.age * 6)
        for e in s.candidates:
            if e is s.target:
                continue
            kind, _ = verdict(player, e)
            col = (150, 70, 70) if kind != "ok" else (110, 150, 170)
            sx, sy = to_screen(e.rect.centerx, e.rect.top)
            sy -= 14 * zoom
            d = 6 * zoom
            pygame.draw.polygon(window, ui.INK, [(sx, sy + d), (sx - d, sy - d * 0.4), (sx + d, sy - d * 0.4)], 3)
            pygame.draw.polygon(window, col, [(sx, sy + d), (sx - d, sy - d * 0.4), (sx + d, sy - d * 0.4)])

        tgt = s.target
        if tgt is not None:
            kind, label = verdict(player, tgt)
            col = CYAN if kind == "ok" else RED
            sx, sy = to_screen(*tgt.rect.center)
            r = max(tgt.rect.w, tgt.rect.h) * zoom * 0.62 + 14
            _brackets(window, (sx, sy), r + 4 * pulse, s.age * 1.6, col)
            pygame.draw.circle(window, (*col,), (int(sx), int(sy)), int(r * (0.78 + 0.1 * pulse)), 1)
            _arc_ring(window, (sx, sy), int(r + 10), s.left / max(0.01, s.total), ui.GOLD if kind == "ok" else col, 3)

            ty = sy - r - 46
            name = f"{tgt.name} - {str(tgt.color).title()}"
            fx.text_alpha(window, name, (sx, ty), 15, ui.WHITE, 255, True, True)
            _hp_bar(window, int(sx - 40), int(ty + 11), 80, 7, tgt.health / max(1, tgt.max_health), col)
            fx.text_alpha(window, label, (sx, ty + 28), 13, col, 255, True, True)

    # particles + floating numbers
    for p in st["parts"]:
        x, y = to_screen(p[0], p[1])
        life = max(0.0, p[4] / p[5])
        if p[6] == "hearts":
            heart(window, x, y, p[7] * zoom * (0.5 + life), PINK, outline=life > 0.35)
        else:
            d = max(2, int(p[7] * 0.45 * zoom))
            pygame.draw.polygon(window, (210, 90, 80), [(x, y - d), (x + d, y + d), (x - d, y + d)])
    for f in st["floats"]:
        x, y = to_screen(f[0], f[1])
        fx.text_alpha(window, f[2], (x, y), int(22 * max(0.8, zoom)), f[3], 255 * (1 - f[4] / 1.2), True, True)


# ---------------------------------------------------------------------- #
# HUD layer
# ---------------------------------------------------------------------- #
def _hint(player):
    ct = getattr(player, "control_type", "keyboard")
    if ct == "keyboard":
        keys = "ARROWS" if getattr(player, "keyboard_num", 0) == 0 else "WASD"
        return f"{keys} choose  -  ENTER confirm  -  ESC cancel"
    if ct == "touch":
        return "TAP an enemy to choose  -  TAP IT AGAIN to confirm"
    return "STICK choose  -  A confirm  -  B cancel"


def _button(surf, center, r, fill, border, hot=0.0):
    pygame.draw.circle(surf, ui.INK, center, r + 3)
    pygame.draw.circle(surf, fill, center, r)
    pygame.draw.circle(surf, border, center, r, 3)


def draw_hud(game, window, view_rect, player):
    from ..scripts import charm_mode
    st = _state(game)
    vw, vh = window.get_size()
    k = max(0.7, min(1.4, vh / 720))
    t = st["t"]
    rects = st["rects"].setdefault(id(player), {})
    rects.clear()

    # vignette tint while aiming + flashes
    slow = getattr(game, "_charm_slow", 1.0)
    amount = max(0.0, min(1.0, (1.0 - slow) / (1.0 - C.SLOWMO)))
    if amount > 0.02:
        v = fx.vignette((vw, vh), (40, 90, 220), 190)
        v.set_alpha(int(255 * amount))
        window.blit(v, (0, 0))
    if st["flash"]:
        color, life, strength = st["flash"]
        v = fx.vignette((vw, vh), color, 230)
        v.set_alpha(int(255 * max(0.0, min(1.0, life)) * strength))
        window.blit(v, (0, 0))

    story = charm_mode.available(game)
    s = player.charm_session
    R = int(34 * k)
    y = vh - int(R * 1.9)
    lc = (vw // 2 - int(R * 1.7), y)
    rc = (vw // 2 + int(R * 1.7), y)

    if story and s is None and not player.dead:
        # ----- charm button + stock badge -----
        have = player.charms > 0
        _button(window, lc, R, (92, 40, 70) if have else (50, 42, 52), PINK if have else (110, 100, 110))
        heart(window, lc[0], lc[1] - R * 0.08, R * 0.5, PINK if have else (120, 110, 120))
        badge = pygame.Rect(0, 0, int(R * 0.9), int(R * 0.6))
        badge.center = (lc[0] + int(R * 0.75), lc[1] - int(R * 0.7))
        pygame.draw.rect(window, ui.INK, badge.inflate(4, 4), border_radius=8)
        pygame.draw.rect(window, GOLD if have else (150, 60, 60), badge, border_radius=7)
        fx.text_alpha(window, f"x{player.charms}", badge.center, int(15 * k), ui.INK, 255, True, True, shadow=False)
        if getattr(player, "control_type", None) == "keyboard":
            key = Settings.CHARM_KEYS.get(getattr(player, "keyboard_num", 0))
            if key is not None:
                fx.text_alpha(window, pygame.key.name(key).upper(), (lc[0], lc[1] + R + int(10 * k)), int(13 * k),
                              ui.WHITE, 220, True, True)
        rects["charm"] = pygame.Rect(lc[0] - R, lc[1] - R, R * 2, R * 2).move(view_rect.x, view_rect.y)

        # ----- dash ring: the time bar as a circle around the dash button, seconds left inside -----
        _draw_dash(window, rc, int(R * 0.78), k, st, t, player)

    if s is not None:
        # ----- timer -----
        cx = vw // 2
        ty = int(vh * 0.2)
        left = max(0.0, s.left)
        urgent = left < 3
        col = fx.lerp_color(ui.GOLD, RED, 0.5 + 0.5 * math.sin(t * 12)) if urgent else ui.GOLD
        _arc_ring(window, (cx, ty), int(40 * k), left / max(0.01, s.total), col, 5)
        pygame.draw.circle(window, (*ui.INK,), (cx, ty), int(40 * k) - 5, 2)
        fx.text_alpha(window, f"{left:0.1f}", (cx, ty), int(30 * k), col, 255, True, True)
        fx.text_alpha(window, "CHARM", (cx, ty - int(54 * k)), int(15 * k), PINK, 255, True, True)
        fx.text_alpha(window, _hint(player), (cx, ty + int(60 * k)), int(14 * k), ui.WHITE, 235, True, True)

        # ----- confirm / cancel (touch + mouse) -----
        _button(window, lc, R, (30, 80, 50), ui.GREEN)
        fx.text_alpha(window, "OK", lc, int(20 * k), ui.WHITE, 255, True, True)
        _button(window, rc, R, (90, 34, 36), RED)
        fx.text_alpha(window, "X", rc, int(22 * k), ui.WHITE, 255, True, True)
        rects["confirm"] = pygame.Rect(lc[0] - R, lc[1] - R, R * 2, R * 2).move(view_rect.x, view_rect.y)
        rects["cancel"] = pygame.Rect(rc[0] - R, rc[1] - R, R * 2, R * 2).move(view_rect.x, view_rect.y)

    # ----- banners -----
    for i, b in enumerate(st["banners"][::-1]):
        age = b["age"]
        cy = int(vh * 0.36) + i * int(46 * k)
        done = fx.drop_text(window, b["text"], (vw // 2, cy), int((38 if i == 0 else 24) * k), b["color"], age, sway_t=t)


# ---------------------------------------------------------------------- #
# pointer input helpers (used by charm_mode.on_pointer)
# ---------------------------------------------------------------------- #
def hit_test(player, pos):
    """"charm" | "confirm" | "cancel" | None for a window position."""
    game = getattr(player, "game", None)
    if game is None:
        return None
    rects = _state(game)["rects"].get(id(player), {})
    for name, r in rects.items():
        if r.collidepoint(pos):
            return name
    return None


def pick(game, player, pos):
    """The candidate under a tap / click (world pick through the player's camera)."""
    st = _state(game)
    view = st["view"].get(id(player))
    s = getattr(player, "charm_session", None)
    if view is None or s is None:
        return None
    cam, zoom, vr = view
    wx = (pos[0] - vr.x) / zoom + cam[0]
    wy = (pos[1] - vr.y) / zoom + cam[1]
    radius = max(C.PICK_RADIUS, 44 / zoom)
    best, best_d = None, radius * radius
    for e in s.candidates:
        d = (e.rect.centerx - wx) ** 2 + (e.rect.centery - wy) ** 2
        if d <= best_d:
            best, best_d = e, d
    return best
