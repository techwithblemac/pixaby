"""
minimap.py
==========
The radar in the corner. It is a SHOP ITEM (``minimap``, emerald): nothing is
drawn until the player owns level 1 (see ``scripts/shop_effects.owned_level``).

    level 1   terrain, you, the other players, allies
    level 2   wider radius
    level 3   enemies as dots (bosses are big and gold)
    level 4   doors (violet / cyan / green like the portals) and treasure
    (the Treasure Radar shop item shows treasure from level 1 on; see draw())

Design notes
------------
* The level's solid terrain is rendered ONCE per level into a big static
  surface (``_static``). Every frame only the window around the player is
  cut out of it and scaled into the radar - no per-frame allocation, no
  per-block loop.
* Everything per-size (frame, rounded mask, scratch surfaces) is cached.
* Tapping / clicking the radar toggles small <-> large (touch friendly).
* Placement is per viewport, below the in-game MENU button, so split-screen
  players each get their own radar and nothing hides behind a button.
"""

import heapq
import math

import pygame

from . import ui_theme as ui
from .ui_fx import lerp_color, pulse
from ..data.palletes.doors import PORTAL_COLORS

# level -> (radius in world px, show enemies, show doors + treasure)
LEVELS = {
    1: (500, False, False),
    2: (720, False, False),
    3: (720, True, False),
    4: (880, True, True),
}
BIG_FACTOR = 1.6            # size multiplier when toggled large
BIG_RADIUS_FACTOR = 1.35    # ...and how much more of the world it shows

STATIC_SCALE = 0.125        # world px -> static layer px (a 64 px block is 8 px)
STATIC_MAX = 1800           # never build a static layer bigger than this (px)

BG = (14, 15, 24, 255)
BLOCK = (66, 80, 108, 255)
EDGE = (128, 150, 190, 255)
WATER = (60, 120, 200, 150)
ACCENT = (90, 230, 160)
SELF_COL = (255, 242, 207)
FRIEND_COL = (120, 255, 190)
TREASURE_COL = (255, 202, 80)

_static = {}                # id(game) -> (key, surface, bounds_rect, scale)
_frames = {}                # (size, level) -> frame overlay
_masks = {}                 # size -> rounded mask
_scratch = {}               # (size, win) -> (view, out, sweep)
_state = {}                 # id(player) -> {"big": bool, "rect": Rect}


def _rgb_of(entity):
    from . import combat_fx
    return combat_fx.rgb_of(entity)


# ---------------------------------------------------------------------- #
# static terrain layer
# ---------------------------------------------------------------------- #
def _static_layer(game):
    objs = getattr(game, "objects", None) or []
    key = (game.level_key() if hasattr(game, "level_key") else None, id(objs), len(objs))
    cached = _static.get(id(game))
    if cached and cached[0] == key:
        return cached[1:]

    if not objs:
        _static[id(game)] = (key, None, None, STATIC_SCALE)
        return None, None, STATIC_SCALE

    rects = [o.rect for o in objs]
    bounds = rects[0].unionall(rects[1:]).inflate(512, 512)
    scale = min(STATIC_SCALE, STATIC_MAX / max(bounds.w, bounds.h))
    surf = pygame.Surface((max(1, int(bounds.w * scale)), max(1, int(bounds.h * scale))), pygame.SRCALPHA)

    def paint(r, color):
        surf.fill(color, (int((r.x - bounds.x) * scale), int((r.y - bounds.y) * scale),
                          max(1, math.ceil(r.w * scale)), max(1, math.ceil(r.h * scale))))

    for z in getattr(game, "zones", None) or ():
        if hasattr(z, "rect"):
            paint(z.rect, WATER)
    for o in objs:
        paint(o.rect, BLOCK)
    for o in getattr(game, "outline_objects", None) or ():
        paint(o.rect, EDGE)

    _static[id(game)] = (key, surf, bounds, scale)
    return surf, bounds, scale


# ---------------------------------------------------------------------- #
# cached per-size pieces
# ---------------------------------------------------------------------- #
def _mask(size):
    m = _masks.get(size)
    if m is None:
        m = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(m, (255, 255, 255, 255), m.get_rect(), border_radius=max(6, size // 8))
        _masks[size] = m
    return m


def _frame(size, level):
    key = (size, level)
    f = _frames.get(key)
    if f is None:
        pad = 6
        f = pygame.Surface((size + pad * 2, size + pad * 2), pygame.SRCALPHA)
        rad = max(6, size // 8)
        box = pygame.Rect(pad, pad, size, size)
        for i in range(pad, 0, -1):               # soft outer glow
            pygame.draw.rect(f, (*ACCENT, int(5 + 3 * (pad - i))), box.inflate(i * 2, i * 2), 2,
                             border_radius=rad + i)
        pygame.draw.rect(f, ui.INK, box.inflate(4, 4), 3, border_radius=rad + 2)
        pygame.draw.rect(f, (*ACCENT, 230), box, 2, border_radius=rad)
        pygame.draw.rect(f, (255, 255, 255, 40), box.inflate(-6, -6), 1, border_radius=max(2, rad - 3))
        tick = max(5, size // 16)                 # corner ticks, a little HUD flavour
        for cx, cy, sx, sy in ((box.left, box.top, 1, 1), (box.right - 1, box.top, -1, 1),
                               (box.left, box.bottom - 1, 1, -1), (box.right - 1, box.bottom - 1, -1, -1)):
            pygame.draw.line(f, ui.WHITE, (cx + sx * 3, cy + sy * 3), (cx + sx * (3 + tick), cy + sy * 3), 1)
            pygame.draw.line(f, ui.WHITE, (cx + sx * 3, cy + sy * 3), (cx + sx * 3, cy + sy * (3 + tick)), 1)
        # level pips, bottom-left
        pip = max(3, size // 28)
        for n in range(max(LEVELS)):
            col = ACCENT if n < level else (60, 66, 84)
            pygame.draw.rect(f, col, (pad + 10 + n * (pip + 3), pad + size - 10 - pip, pip, pip))
        label = ui.font(max(9, size // 11), True).render("RADAR", True, ui.WHITE)
        f.blit(label, (pad + size - label.get_width() - 10, pad + size - label.get_height() - 6))
        _frames[key] = f
    return f


def _buffers(size, win):
    key = (size, win)
    b = _scratch.get(key)
    if b is None:
        if len(_scratch) > 12:
            _scratch.clear()
        b = (pygame.Surface((win, win), pygame.SRCALPHA),
             pygame.Surface((size, size), pygame.SRCALPHA),
             pygame.Surface((size, size)))
        _scratch[key] = b
    return b


# ---------------------------------------------------------------------- #
# drawing
# ---------------------------------------------------------------------- #
def _dims(view_rect, big):
    vw, vh = view_rect.size
    size = int(max(96, min(220, vw * 0.17, vh * 0.30)))
    if big:
        size = int(min(size * BIG_FACTOR, min(vw, vh) * 0.5))
    return size


def _edge_pos(off, half):
    """Clamp an offset (from the radar centre) onto the square frame."""
    m = max(abs(off.x), abs(off.y), 1e-6)
    k = (half - 10) / m
    return pygame.Vector2(half + off.x * k, half + off.y * k)


def _arrow(surf, pos, ang, col, r=6):
    pts = [(pos.x + math.cos(ang) * r, pos.y + math.sin(ang) * r),
           (pos.x + math.cos(ang + 2.5) * r, pos.y + math.sin(ang + 2.5) * r),
           (pos.x + math.cos(ang - 2.5) * r, pos.y + math.sin(ang - 2.5) * r)]
    pygame.draw.polygon(surf, ui.INK, pts, 3)
    pygame.draw.polygon(surf, col, pts)


def draw(game, viewport, player, level, view_rect=None, window_width=None, t=None):
    """Draw the radar for ``player`` into ``viewport`` (its own screen)."""
    level = max(1, min(level, max(LEVELS)))
    radius, show_enemies, show_extras = LEVELS[level]
    st = _state.setdefault(id(player), {"big": False, "rect": pygame.Rect(0, 0, 0, 0)})
    view_rect = view_rect or viewport.get_rect()
    t = pygame.time.get_ticks() / 1000.0 if t is None else t

    # tap / click toggles the size
    for ev in getattr(game, "events", ()) or ():
        pos = None
        if ev.type == pygame.MOUSEBUTTONDOWN and getattr(ev, "button", 1) == 1:
            pos = ev.pos
        elif ev.type == pygame.FINGERDOWN:
            ww, wh = game.window.get_size()
            pos = (ev.x * ww, ev.y * wh)
        if pos is not None and st["rect"].collidepoint(pos):
            st["big"] = not st["big"]

    size = _dims(view_rect, st["big"])
    if st["big"]:
        radius = int(radius * BIG_RADIUS_FACTOR)
    S = size
    half = S / 2
    ms = S / (2 * radius)                               # world px -> radar px

    static, bounds, sscale = _static_layer(game)
    win = max(8, int(2 * radius * sscale))
    view, out, sweep = _buffers(S, win)

    cx, cy = player.rect.center
    view.fill(BG)
    if static is not None:
        view.blit(static, (int(win / 2 - (cx - bounds.x) * sscale), int(win / 2 - (cy - bounds.y) * sscale)))
    pygame.transform.scale(view, (S, S), out)

    me = pygame.Vector2(cx, cy)
    friends = {id(f) for f in (getattr(player, "friends", None) or ())}
    r2 = radius * radius

    def to_radar(rect_center):
        return pygame.Vector2((rect_center[0] - cx) * ms + half, (rect_center[1] - cy) * ms + half)

    # ----- extras: treasure + doors (level 4) -----
    # Treasure Radar (shop): L1 shows treasure, L2 points at the 3 nearest far ones, L3 pings close ones
    from ..scripts import shop_effects
    radar = shop_effects.stat(player, "treasure_radar")
    if show_extras or radar >= 1:
        far = []
        for tr in getattr(game, "treasure_list", None) or ():
            dx, dy = tr.rect.centerx - cx, tr.rect.centery - cy
            d2 = dx * dx + dy * dy
            if d2 <= r2:
                p = to_radar(tr.rect.center)
                pygame.draw.rect(out, TREASURE_COL, (int(p.x) - 1, int(p.y) - 1, 3, 3))
                if radar >= 3 and d2 <= 600 * 600:
                    ping = (t * 1.6 + d2 * 1e-6) % 1.0
                    pygame.draw.circle(out, TREASURE_COL, (int(p.x), int(p.y)), 3 + int(ping * S * 0.08), 1)
            elif radar >= 2:
                far.append((d2, dx, dy))
        for d2, dx, dy in heapq.nsmallest(3, far):
            off = pygame.Vector2(dx, dy)
            _arrow(out, _edge_pos(off * ms, half), math.atan2(dy, dx), TREASURE_COL, 4)
    if show_extras:
        for door in getattr(game, "doors", None) or ():
            if getattr(door, "death", False):
                continue
            col = PORTAL_COLORS.get(door.kind, PORTAL_COLORS["teleport"])[0]
            off = pygame.Vector2(door.rect.centerx - cx, door.rect.centery - cy)
            if off.length_squared() <= r2:
                p = to_radar(door.rect.center)
                d = max(3, S // 28)
                pts = [(p.x, p.y - d), (p.x + d, p.y), (p.x, p.y + d), (p.x - d, p.y)]
                pygame.draw.polygon(out, ui.INK, pts, 3)
                pygame.draw.polygon(out, col, pts)
            elif door.kind == "exit":                    # the exit is worth an arrow even when far
                _arrow(out, _edge_pos(off * ms, half), math.atan2(off.y, off.x), col, 5)

    # ----- enemies (level 3) -----
    if show_enemies:
        blink = 0.6 + 0.4 * pulse(t, 1.4)
        for e in getattr(game, "enemy_list", None) or ():
            if e.dead or e.death:
                continue
            dx, dy = e.rect.centerx - cx, e.rect.centery - cy
            if dx * dx + dy * dy > r2:
                continue
            p = to_radar(e.rect.center)
            ip = (int(p.x), int(p.y))
            if id(e) in friends:
                pygame.draw.circle(out, FRIEND_COL, ip, 3)
            elif getattr(e, "is_boss", False):
                pygame.draw.circle(out, ui.INK, ip, 7)
                pygame.draw.circle(out, lerp_color(ui.GOLD, ui.WHITE, 1 - blink), ip, 5)
            else:
                pygame.draw.circle(out, ui.INK, ip, 4)
                pygame.draw.circle(out, _rgb_of(e), ip, 3)

    # ----- other players (always) -----
    for p in getattr(game, "players", None) or ():
        if p is player or p.dead or p.death:
            continue
        off = pygame.Vector2(p.rect.centerx - cx, p.rect.centery - cy)
        col = _rgb_of(p)
        if off.length_squared() <= r2:
            q = to_radar(p.rect.center)
            pygame.draw.circle(out, ui.INK, (int(q.x), int(q.y)), 6)
            pygame.draw.circle(out, col, (int(q.x), int(q.y)), 4)
        else:
            _arrow(out, _edge_pos(off * ms, half), math.atan2(off.y, off.x), col)

    # ----- you: a facing arrow with a blinking ring -----
    facing = 0.0 if getattr(player, "direction", "right") == "right" else math.pi
    centre = pygame.Vector2(half, half)
    ring = 6 + int(3 * pulse(t, 1.2))
    pygame.draw.circle(out, (*SELF_COL, 255), (int(half), int(half)), ring, 1)
    _arrow(out, centre, facing, SELF_COL, 6)

    # ----- scan sweep (additive, on a reused scratch surface) -----
    sweep.fill((0, 0, 0))
    a0 = (t * 1.3) % math.tau
    reach = S * 0.75
    steps = 9
    for k in range(steps):
        f = 1 - k / steps
        a1, a2 = a0 - k * 0.09, a0 - (k + 1) * 0.09
        pts = [(half, half), (half + math.cos(a1) * reach, half + math.sin(a1) * reach),
               (half + math.cos(a2) * reach, half + math.sin(a2) * reach)]
        pygame.draw.polygon(sweep, (int(10 * f), int(48 * f), int(30 * f)), pts)
    out.blit(sweep, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    # rounded corners
    out.blit(_mask(S), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

    # ----- placement: top-right, under the MENU button when the view reaches the window edge -----
    vw, vh = view_rect.size
    margin = max(8, int(vw * 0.012))
    ww = window_width if window_width is not None else game.window.get_width()
    top = int(vh * 0.28) if view_rect.right >= ww - 2 else margin
    pad = 6
    x = vw - S - margin - pad
    y = top
    frame = _frame(S, level)
    viewport.blit(out, (x, y))
    viewport.blit(frame, (x - pad, y - pad))
    st["rect"] = pygame.Rect(view_rect.x + x, view_rect.y + y, S, S)
