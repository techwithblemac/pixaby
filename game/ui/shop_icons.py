"""
shop_icons.py
=============
Tiny vector icons for the shop items, drawn with pygame primitives so the
shop needs no extra art. ``draw_icon`` returns False for an item it has no
icon for - the caller then falls back to the item's coin from Assets.
"""

import math

import pygame

from . import ui_theme as ui
from .ui_fx import lerp_color

PEARL = (240, 150, 200)


def _i(v):
    return int(round(v))


def _render(s, parts):
    """parts: ('c', x, y, r, color) or ('p', points, color). Outline pass, then fill pass."""
    for p in parts:
        if p[0] == "c":
            pygame.draw.circle(s, ui.INK, (_i(p[1]), _i(p[2])), _i(p[3]) + 2)
        else:
            pygame.draw.polygon(s, ui.INK, [(_i(x), _i(y)) for x, y in p[1]], 5)
    for p in parts:
        if p[0] == "c":
            pygame.draw.circle(s, p[4], (_i(p[1]), _i(p[2])), max(1, _i(p[3])))
        else:
            pygame.draw.polygon(s, p[2], [(_i(x), _i(y)) for x, y in p[1]])


def _line(s, col, a, b, w):
    pygame.draw.line(s, ui.INK, (_i(a[0]), _i(a[1])), (_i(b[0]), _i(b[1])), w + 4)
    pygame.draw.line(s, col, (_i(a[0]), _i(a[1])), (_i(b[0]), _i(b[1])), w)


def _heart(s, cx, cy, u, col):
    r = u * 0.46
    _render(s, [("c", cx - r * 0.95, cy - r * 0.45, r, col),
                ("c", cx + r * 0.95, cy - r * 0.45, r, col),
                ("p", [(cx - r * 1.85, cy - r * 0.1), (cx + r * 1.85, cy - r * 0.1), (cx, cy + u * 0.92)], col)])
    pygame.draw.circle(s, ui.WHITE, (_i(cx - r * 1.2), _i(cy - r * 0.9)), max(1, _i(u * 0.1)))


def _plus_heart(s, cx, cy, u, col):
    _heart(s, cx, cy, u, col)
    w = max(2, _i(u * 0.16))
    pygame.draw.line(s, ui.WHITE, (_i(cx), _i(cy - u * 0.3)), (_i(cx), _i(cy + u * 0.3)), w)
    pygame.draw.line(s, ui.WHITE, (_i(cx - u * 0.3), _i(cy)), (_i(cx + u * 0.3), _i(cy)), w)


def _potion(s, cx, cy, u, liquid):
    glass = (205, 225, 235)
    _render(s, [("p", [(cx - u * .2, cy - u * .75), (cx + u * .2, cy - u * .75),
                       (cx + u * .2, cy - u * .2), (cx - u * .2, cy - u * .2)], glass),
                ("c", cx, cy + u * .22, u * .55, glass)])
    pygame.draw.circle(s, liquid, (_i(cx), _i(cy + u * .28)), max(1, _i(u * .42)))
    pygame.draw.rect(s, (150, 100, 60), pygame.Rect(_i(cx - u * .26), _i(cy - u * .98), _i(u * .52), _i(u * .26)),
                     border_radius=2)
    pygame.draw.circle(s, ui.WHITE, (_i(cx - u * .2), _i(cy + u * .1)), max(1, _i(u * .09)))


def _drum(s, cx, cy, u, col):
    body = pygame.Rect(_i(cx - u * .7), _i(cy - u * .3), _i(u * 1.4), _i(u * .95))
    pygame.draw.rect(s, ui.INK, body.inflate(4, 4), border_radius=5)
    pygame.draw.rect(s, col, body, border_radius=3)
    dark = lerp_color(col, ui.INK, 0.55)
    for n in range(1, 4):
        x = body.left + body.width * n // 4
        pygame.draw.line(s, dark, (x, body.top + 3), (x, body.bottom - 3), 2)
    top = pygame.Rect(body.left, body.top - _i(u * .26), body.width, _i(u * .52))
    pygame.draw.ellipse(s, ui.INK, top.inflate(4, 4))
    pygame.draw.ellipse(s, ui.CREAM, top)
    _line(s, ui.WHITE, (cx - u * .35, cy - u * 1.0), (cx + u * .15, cy - u * .35), 2)
    _line(s, ui.WHITE, (cx + u * .35, cy - u * 1.0), (cx - u * .15, cy - u * .35), 2)


def _shield(s, cx, cy, u, col):
    pts = [(cx - u * .7, cy - u * .75), (cx + u * .7, cy - u * .75), (cx + u * .7, cy + u * .05),
           (cx, cy + u * .95), (cx - u * .7, cy + u * .05)]
    _render(s, [("p", pts, col)])
    light = lerp_color(col, ui.WHITE, 0.55)
    pygame.draw.line(s, light, (_i(cx), _i(cy - u * .62)), (_i(cx), _i(cy + u * .72)), max(2, _i(u * .16)))
    pygame.draw.line(s, light, (_i(cx - u * .55), _i(cy - u * .15)), (_i(cx + u * .55), _i(cy - u * .15)),
                     max(2, _i(u * .16)))


def _sword(s, cx, cy, u, col):
    d, p = (0.7071, -0.7071), (0.7071, 0.7071)
    g = (cx - u * .25, cy + u * .25)
    _line(s, (150, 100, 60), (g[0] - d[0] * u * .1, g[1] - d[1] * u * .1),
          (g[0] - d[0] * u * .55, g[1] - d[1] * u * .55), max(3, _i(u * .2)))
    _line(s, col, g, (cx + u * .8, cy - u * .8), max(3, _i(u * .3)))
    _line(s, ui.GOLD, (g[0] - p[0] * u * .45, g[1] - p[1] * u * .45), (g[0] + p[0] * u * .45, g[1] + p[1] * u * .45),
          max(3, _i(u * .2)))


def _fang(s, cx, cy, u, col):
    _render(s, [("p", [(cx - u * .6, cy - u * .85), (cx + u * .6, cy - u * .85), (cx + u * .08, cy + u * .95)], col)])
    pygame.draw.line(s, ui.WHITE, (_i(cx - u * .25), _i(cy - u * .6)), (_i(cx - u * .05), _i(cy + u * .2)), 2)
    pygame.draw.circle(s, ui.RED, (_i(cx + u * .08), _i(cy + u * 1.0)), max(1, _i(u * .1)))


def _bolt(s, cx, cy, u, col):
    _render(s, [("p", [(cx + u * .2, cy - u * .95), (cx - u * .55, cy + u * .1), (cx - u * .05, cy + u * .1),
                       (cx - u * .25, cy + u * .95), (cx + u * .6, cy - u * .2), (cx + u * .05, cy - u * .2)], col)])


def _magnet(s, cx, cy, u, col):
    big, small = u * .72, u * .36
    pts = [(cx + big * math.cos(math.pi * (1 - n / 12)), cy - big * math.sin(math.pi * (1 - n / 12)))
           for n in range(13)]
    pts += [(cx + big, cy + u * .7), (cx + small, cy + u * .7)]
    pts += [(cx + small * math.cos(math.pi * n / 12), cy - small * math.sin(math.pi * n / 12)) for n in range(13)]
    pts += [(cx - small, cy + u * .7), (cx - big, cy + u * .7)]
    _render(s, [("p", pts, col)])
    for side in (-1, 1):
        x0 = cx + side * (big + small) / 2
        pygame.draw.rect(s, ui.WHITE, pygame.Rect(_i(x0 - (big - small) / 2), _i(cy + u * .42),
                                                  _i(big - small), _i(u * .28)))


def _drop(s, cx, cy, u, col):
    _render(s, [("c", cx, cy + u * .25, u * .58, col),
                ("p", [(cx, cy - u * .95), (cx - u * .52, cy + u * .05), (cx + u * .52, cy + u * .05)], col)])
    pygame.draw.circle(s, ui.WHITE, (_i(cx - u * .2), _i(cy + u * .2)), max(1, _i(u * .11)))


def _spring(s, cx, cy, u, col):
    pts = [(cx - u * .5, cy + u * .55), (cx + u * .5, cy + u * .3), (cx - u * .5, cy + u * .05),
           (cx + u * .5, cy - u * .2), (cx - u * .5, cy - u * .45)]
    pygame.draw.lines(s, ui.INK, False, [(_i(x), _i(y)) for x, y in pts], max(3, _i(u * .3)) + 4)
    pygame.draw.lines(s, col, False, [(_i(x), _i(y)) for x, y in pts], max(3, _i(u * .3)))
    for yy in (cy + u * .62, cy - u * .8):
        r = pygame.Rect(_i(cx - u * .72), _i(yy), _i(u * 1.44), max(3, _i(u * .26)))
        pygame.draw.rect(s, ui.INK, r.inflate(4, 4), border_radius=3)
        pygame.draw.rect(s, (200, 210, 225), r, border_radius=2)


def _radar(s, cx, cy, u, col):
    pygame.draw.circle(s, ui.INK, (_i(cx), _i(cy)), _i(u * .95) + 2)
    pygame.draw.circle(s, lerp_color(col, ui.INK, 0.75), (_i(cx), _i(cy)), _i(u * .95))
    pygame.draw.circle(s, col, (_i(cx), _i(cy)), _i(u * .95), 2)
    pygame.draw.circle(s, col, (_i(cx), _i(cy)), _i(u * .48), 1)
    pygame.draw.line(s, col, (_i(cx), _i(cy)), (_i(cx + u * .62), _i(cy - u * .62)), 2)
    pygame.draw.circle(s, ui.WHITE, (_i(cx - u * .3), _i(cy + u * .25)), max(1, _i(u * .13)))
    pygame.draw.circle(s, ui.RED, (_i(cx + u * .32), _i(cy + u * .38)), max(1, _i(u * .11)))


def _pointer(s, cx, cy, u, col):
    pygame.draw.circle(s, col, (_i(cx), _i(cy)), max(2, _i(u * .22)))
    for a in (-0.9, 0.9, 2.4, 3.9):
        tip = (cx + math.cos(a) * u * .95, cy + math.sin(a) * u * .95)
        l = (cx + math.cos(a + 0.35) * u * .5, cy + math.sin(a + 0.35) * u * .5)
        r = (cx + math.cos(a - 0.35) * u * .5, cy + math.sin(a - 0.35) * u * .5)
        _render(s, [("p", [tip, l, r], col)])


def _charm(s, cx, cy, u, col):
    _heart(s, cx, cy + u * 0.05, u * 0.8, col)
    for a in (-2.3, -0.8, 0.6):                 # sparkles circling the heart
        pygame.draw.circle(s, ui.WHITE, (_i(cx + math.cos(a) * u * .95), _i(cy + math.sin(a) * u * .85)), max(1, _i(u * .09)))


def _dash(s, cx, cy, u, col):
    for k in range(3):
        x = cx - u * .55 + k * u * .5
        _render(s, [("p", [(x, cy - u * .55), (x + u * .5, cy), (x, cy + u * .55)], lerp_color(col, ui.WHITE, 0.18 * k))])


def _arrow(s, cx, cy, u, col):
    tail, tip = (cx - u * .85, cy + u * .85), (cx + u * .8, cy - u * .8)
    _line(s, (190, 150, 100), tail, (cx + u * .45, cy - u * .45), max(2, _i(u * .2)))
    _render(s, [("p", [tip, (cx + u * .2, cy - u * .62), (cx + u * .62, cy - u * .2)], col)])
    for k in (0.0, 0.3):                                       # fletching
        a = (cx - u * .85 + u * k, cy + u * .85 - u * k)
        _line(s, ui.WHITE, a, (a[0] - u * .32, a[1] - u * .05), 2)
        _line(s, ui.WHITE, a, (a[0] + u * .05, a[1] + u * .32), 2)


def _flame(s, cx, cy, u, col):
    pts = [(cx, cy - u), (cx + u * .55, cy - u * .1), (cx + u * .5, cy + u * .55), (cx, cy + u * .95),
           (cx - u * .5, cy + u * .55), (cx - u * .55, cy - u * .1), (cx - u * .12, cy - u * .35)]
    _render(s, [("p", pts, col)])
    _render(s, [("p", [(cx, cy - u * .1), (cx + u * .25, cy + u * .35), (cx, cy + u * .7), (cx - u * .25, cy + u * .35)],
                 lerp_color(col, ui.WHITE, .65))])


def _bomb(s, cx, cy, u, col):
    _render(s, [("c", cx, cy + u * .2, u * .72, col)])
    _line(s, (200, 170, 110), (cx + u * .35, cy - u * .35), (cx + u * .6, cy - u * .85), 3)
    pygame.draw.circle(s, (255, 200, 70), (_i(cx + u * .64), _i(cy - u * .9)), max(2, _i(u * .16)))
    pygame.draw.circle(s, ui.WHITE, (_i(cx - u * .25), _i(cy - u * .05)), max(1, _i(u * .12)))


def _clover(s, cx, cy, u, col):
    r = u * .4
    _render(s, [("c", cx - r, cy - r, r, col), ("c", cx + r, cy - r, r, col),
                ("c", cx - r, cy + r, r, col), ("c", cx + r, cy + r, r, col)])
    _line(s, lerp_color(col, ui.INK, .3), (cx, cy + r), (cx + u * .35, cy + u * .95), 3)


def _spikes(s, cx, cy, u, col):
    _render(s, [("p", [(cx - u * .9 + k * u * .6, cy + u * .55), (cx - u * .6 + k * u * .6, cy - u * .75),
                       (cx - u * .3 + k * u * .6, cy + u * .55)], col) for k in range(3)])
    pygame.draw.rect(s, ui.INK, (_i(cx - u), _i(cy + u * .5), _i(u * 2), _i(u * .32)), border_radius=3)


def _cloud(s, cx, cy, u, col):
    _render(s, [("c", cx - u * .5, cy + u * .1, u * .42, col), ("c", cx + u * .1, cy - u * .2, u * .55, col),
                ("c", cx + u * .6, cy + u * .15, u * .38, col),
                ("p", [(cx - u * .5, cy + u * .52), (cx + u * .6, cy + u * .52), (cx + u * .6, cy + u * .1),
                       (cx - u * .5, cy + u * .1)], col)])


def _gem(s, cx, cy, u, col):
    pts = [(cx - u * .75, cy - u * .2), (cx - u * .4, cy - u * .8), (cx + u * .4, cy - u * .8),
           (cx + u * .75, cy - u * .2), (cx, cy + u * .9)]
    _render(s, [("p", pts, col)])
    pygame.draw.line(s, lerp_color(col, ui.WHITE, .6), (_i(cx - u * .75), _i(cy - u * .2)), (_i(cx + u * .75), _i(cy - u * .2)), 2)


def _crosshair(s, cx, cy, u, col):
    pygame.draw.circle(s, ui.INK, (_i(cx), _i(cy)), _i(u * .7) + 2, 5)
    pygame.draw.circle(s, col, (_i(cx), _i(cy)), _i(u * .7), 2)
    for a in (0, 90, 180, 270):
        dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
        _line(s, col, (cx + dx * u * .45, cy + dy * u * .45), (cx + dx * u * 1.0, cy + dy * u * 1.0), 2)
    pygame.draw.circle(s, col, (_i(cx), _i(cy)), max(2, _i(u * .14)))


_FUNCS = {"arrow": _arrow, "flame": _flame, "bomb": _bomb, "clover": _clover, "spikes": _spikes,
          "cloud": _cloud, "gem": _gem, "crosshair": _crosshair, "charm": _charm, "dash": _dash, "radar": _radar, "pointer": _pointer, "heart": _heart, "plus_heart": _plus_heart, "potion": _potion, "drum": _drum, "shield": _shield,
          "sword": _sword, "fang": _fang, "bolt": _bolt, "magnet": _magnet, "drop": _drop, "spring": _spring}

ICON_MAP = {
    "heal_small": ("potion", ui.RED),
    "heal_full": ("potion", ui.PURPLE),
    "war_drum": ("drum", (190, 120, 70)),
    "iron_skin": ("shield", ui.BLUE),
    "vitality": ("plus_heart", ui.RED),
    "might": ("sword", (200, 210, 225)),
    "swiftness": ("bolt", (255, 220, 90)),
    "magnet": ("magnet", (224, 78, 74)),
    "lifesteal": ("drop", (200, 40, 70)),
    "springs": ("spring", ui.GREEN),
    "minimap": ("radar", (90, 230, 160)),
    "target_pointers": ("pointer", (255, 90, 80)),
    "befriend_charm": ("charm", (255, 130, 190)),
    "charm_duration": ("charm", (255, 190, 120)),
    "charm_range": ("charm", (120, 220, 255)),
    "charm_bond": ("heart", (255, 120, 150)),
    "charm_limit": ("charm", PEARL),
    "dash_charge": ("dash", (120, 190, 255)),
    "dash_pouch": ("dash", (110, 220, 170)),
    "dash_master": ("dash", (255, 210, 110)),
    "quiver": ("arrow", (230, 220, 200)),
    "ember_stock": ("flame", (255, 140, 60)),
    "bomb_bag": ("bomb", (90, 95, 120)),
    "blast_radius": ("bomb", (255, 120, 80)),
    "bomb_cap": ("bomb", (110, 200, 150)),
    "quick_hands": ("bolt", (120, 220, 255)),
    "piercing_tips": ("arrow", (160, 210, 255)),
    "hot_coals": ("flame", (255, 90, 50)),
    "homing_arrows": ("crosshair", (255, 120, 150)),
    "thorns": ("spikes", (150, 210, 110)),
    "lucky_clover": ("clover", (90, 210, 110)),
    "treasure_radar": ("gem", (120, 230, 200)),
    "shield_bubble": ("shield", (140, 210, 255)),
    "second_wind": ("cloud", (190, 230, 255)),
    "double_jump": ("cloud", PEARL),
    "abyssal_heart": ("heart", PEARL),
    "abyssal_fang": ("fang", (240, 235, 220)),
}


def _twinkle(s, x, y, r, t):
    pts = []
    for n in range(8):
        a = n * math.pi / 4 + t * 1.5
        rr = r if n % 2 == 0 else r * 0.28
        pts.append((_i(x + math.cos(a) * rr), _i(y + math.sin(a) * rr)))
    pygame.draw.polygon(s, ui.WHITE, pts)


def draw_icon(surface, item_id, center, size, t=0.0, hot=0.0):
    """Draw the icon for ``item_id`` inside a ``size`` px square. False if there is none."""
    entry = ICON_MAP.get(item_id)
    if entry is None:
        return False
    name, col = entry
    u = size * 0.36 * (1 + 0.12 * hot)
    cx, cy = center
    if item_id == "abyssal_heart":
        u *= 1 + 0.06 * math.sin(t * 6.0)       # a heart that beats
    _FUNCS[name](surface, cx, cy, u, col)
    if hot > 0.05:
        _twinkle(surface, cx + u * 0.85, cy - u * 0.85, u * 0.38 * hot * (0.7 + 0.3 * math.sin(t * 5.0)), t)
    return True
