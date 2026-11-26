"""
achievements_screen.py
======================
The achievements window, opened from the start menu and the pause menu
(``open_achievements(game)``).

    * a completion ring (X / Y and a percentage) next to the title
    * filter chips (ALL / UNLOCKED / IN PROGRESS / LOCKED), category tabs
      (Combat, Survival, Wealth, Allies, Exploration, Secrets) and a sort button
    * a scrolling list of cards: tier medal, name, description, a progress bar
      ("63 / 100"), the reward and - once earned - a CLAIMED stamp with the date
    * hidden feats read "???" until they are earned; fresh unlocks carry a NEW tag
      until the window has been looked at

Performance: each card is rendered ONCE (cache key = id, state, progress, size)
and only blitted afterwards; the per-frame extras (selection glow, bar shimmer,
medal shine, NEW pulse) are tiny draws on top. Only cards on screen are drawn.

Input: mouse (click, wheel, drag-to-scroll with inertia), keyboard
(UP/DOWN/PGUP/PGDN/HOME/END select, LEFT/RIGHT filter, [ ] or TAB category,
S sort, ESC back) and gamepad (hat / stick, B back, X sort, L1 / R1 category).
Touch relies on the mouse events SDL synthesises from it.
"""

import math
import time

import pygame

from . import ui_fx as fx
from . import ui_theme as ui
from . import shop_icons
from ..data import achievements as A
from ..scripts import achievements as ach_tracker
from ..scripts.menu import _ui_tick
from .window_kit import panel as _panel

FILTERS = ("ALL", "UNLOCKED", "IN PROGRESS", "LOCKED")
SORTS = ("NEWEST", "CATEGORY", "CLOSEST")
CATS = ("ALL",) + tuple(A.CATEGORIES)

_cards = {}          # card cache: key -> (surface, bar_rect, medal_center, medal_r)
_texts = {}          # (text, size, color, bold) -> surface
_shines = {}         # (radius, frame) -> surface
SHINE_FRAMES = 14


def _txt(text, size, color, bold=False):
    key = (text, size, tuple(color[:3]), bold)
    s = _texts.get(key)
    if s is None:
        if len(_texts) > 600:
            _texts.clear()
        s = _texts[key] = ui.font(size, bold).render(text, True, color)
    return s


def _fit(text, size, bold, width):
    f = ui.font(size, bold)
    if f.size(text)[0] <= width:
        return text
    while text and f.size(text + "...")[0] > width:
        text = text[:-1]
    return text.rstrip() + "..."


def _shine(radius, frame):
    key = (radius, frame)
    img = _shines.get(key)
    if img is None:
        if len(_shines) > 120:
            _shines.clear()
        size = radius * 2
        img = pygame.Surface((size, size), pygame.SRCALPHA)
        x = int((frame / (SHINE_FRAMES - 1)) * (size * 1.7)) - int(size * 0.35)
        pygame.draw.polygon(img, (255, 255, 255, 110), [(x, size), (x + size * 0.18, size), (x + size * 0.18 + size * 0.5, 0), (x + size * 0.5, 0)])
        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (radius, radius), radius - 3)
        img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        _shines[key] = img
    return img


def _padlock(surf, cx, cy, u, col):
    pygame.draw.arc(surf, col, (cx - u * 0.5, cy - u * 0.95, u, u * 1.1), 0, math.pi, max(2, int(u * 0.22)))
    body = pygame.Rect(0, 0, int(u * 1.5), int(u * 1.1))
    body.center = (cx, cy + int(u * 0.25))
    pygame.draw.rect(surf, ui.INK, body.inflate(4, 4), border_radius=5)
    pygame.draw.rect(surf, col, body, border_radius=4)
    pygame.draw.circle(surf, ui.INK, body.center, max(2, int(u * 0.16)))


# ---------------------------------------------------------------------- #
# one card, rendered once
# ---------------------------------------------------------------------- #
def render_card(e, w, h, k):
    key = (e["id"], e["state"], e["current"], e["name"], w, h)
    hit = _cards.get(key)
    if hit is not None:
        return hit
    if len(_cards) > 160:
        _cards.clear()

    tier = A.TIER_COLORS.get(e["tier"], ui.GOLD)
    unlocked, locked = e["state"] == "unlocked", e["state"] == "locked"
    dim = (96, 92, 108)
    accent = tier if unlocked else (fx.lerp_color(tier, dim, 0.55) if not locked else (84, 80, 98))
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    fill = (46, 31, 40) if unlocked else ((38, 28, 38) if e["state"] == "progress" else (28, 24, 33))
    pygame.draw.rect(surf, fill, (0, 0, w, h), border_radius=int(14 * k))
    pygame.draw.rect(surf, accent, (0, 0, w, h), width=3 if unlocked else 2, border_radius=int(14 * k))
    if unlocked:                                              # a soft tier-coloured wash on the left
        wash = pygame.Surface((int(w * 0.35), h - 8), pygame.SRCALPHA)
        for x in range(wash.get_width()):
            a = int(46 * (1 - x / wash.get_width()) ** 2)
            pygame.draw.line(wash, (*tier, a), (x, 0), (x, wash.get_height()))
        surf.blit(wash, (4, 4))

    # ----- medal -----
    r = int(h * 0.36)
    mc = (int(h * 0.5) + int(8 * k), h // 2)
    pygame.draw.circle(surf, ui.INK, mc, r + 3)
    pygame.draw.circle(surf, accent, mc, r)
    pygame.draw.circle(surf, (24, 18, 26) if not unlocked else lerp(tier, ui.INK, 0.72), mc, r - 5)
    if e["hidden"]:
        _padlock(surf, mc[0], mc[1], r * 0.55, (130, 124, 146))
    else:
        icon = shop_icons._FUNCS.get(e["icon"], shop_icons._FUNCS["sword"])
        icon(surf, mc[0], mc[1], r * 0.62, tier if unlocked else (110, 104, 122))
        if locked:
            _padlock(surf, mc[0] + int(r * 0.62), mc[1] + int(r * 0.62), r * 0.26, (150, 144, 166))

    # ----- text -----
    tx = mc[0] + r + int(18 * k)
    right_w = int(w * 0.24)
    text_w = w - tx - right_w - int(16 * k)
    name_size, desc_size = max(14, int(h * 0.23)), max(11, int(h * 0.16))
    surf.blit(_txt(_fit(e["name"], name_size, True, text_w), name_size, ui.CREAM if unlocked else (190, 184, 200), True),
              (tx, int(h * 0.12)))
    desc_col = (214, 200, 196) if unlocked else (150, 144, 160)
    surf.blit(_txt(_fit(e["desc"], desc_size, False, text_w), desc_size, desc_col), (tx, int(h * 0.12) + name_size + int(3 * k)))

    # ----- progress bar -----
    bar = None
    if e["goal"] > 1:
        bar = pygame.Rect(tx, h - int(h * 0.27), text_w, max(8, int(h * 0.12)))
        pygame.draw.rect(surf, ui.INK, bar.inflate(4, 4), border_radius=5)
        pygame.draw.rect(surf, (52, 40, 52), bar, border_radius=4)
        if e["frac"] > 0:
            fill_w = max(bar.height, int(bar.width * e["frac"])) if e["frac"] < 1 else bar.width
            pygame.draw.rect(surf, tier if unlocked else fx.lerp_color(tier, (255, 255, 255), 0.1),
                             (bar.x, bar.y, fill_w, bar.height), border_radius=4)
        label = _txt(f"{e['current']} / {e['goal']}", max(10, int(h * 0.13)), ui.WHITE, True)
        surf.blit(label, (bar.right - label.get_width(), bar.y - label.get_height() - 1))

    # ----- reward + stamp (right side) -----
    rx = w - right_w
    coin = max(14, int(h * 0.26))
    y = int(h * 0.20)
    for cur, amount in e["reward"].items():
        fx.draw_coin(surf, (rx + coin // 2 + int(6 * k), y + coin // 2), cur, coin, 0.0)
        label = _txt(f"+{amount}", max(12, int(h * 0.2)), fx.COIN_COLORS.get(cur, ui.GOLD), True)
        surf.blit(label, (rx + coin + int(10 * k), y + coin // 2 - label.get_height() // 2))
        y += coin + int(4 * k)
    if unlocked:
        stamp = _txt("CLAIMED", max(11, int(h * 0.15)), ui.GREEN, True)
        surf.blit(stamp, (rx + int(4 * k), h - int(h * 0.42)))
        when = e["unlocked_at"]
        if when:
            date = _txt(time.strftime("%d %b %Y", time.localtime(when)), max(9, int(h * 0.12)), (170, 160, 176))
            surf.blit(date, (rx + int(4 * k), h - int(h * 0.42) + stamp.get_height() + 1))
    else:
        surf.blit(_txt("REWARD", max(9, int(h * 0.12)), (130, 124, 146), True), (rx + int(4 * k), h - int(h * 0.30)))

    out = (surf, bar, mc, r)
    _cards[key] = out
    return out


def lerp(a, b, t):
    return fx.lerp_color(a, b, t)


# ---------------------------------------------------------------------- #
# list logic (pure, testable)
# ---------------------------------------------------------------------- #
def visible_entries(entries, filt, cat, sort):
    lst = list(entries)
    if cat != "ALL":
        lst = [e for e in lst if e["category"] == cat]
    if filt == 1:
        lst = [e for e in lst if e["state"] == "unlocked"]
    elif filt == 2:
        lst = [e for e in lst if e["state"] == "progress"]
    elif filt == 3:
        lst = [e for e in lst if e["state"] in ("locked", "progress")]
    if sort == 0:        # newest first, then the rest in list order
        lst.sort(key=lambda e: (e["state"] != "unlocked", -e["unlocked_at"] if e["state"] == "unlocked" else 0, e["order"]))
    elif sort == 1:      # by category, then tier
        lst.sort(key=lambda e: (A.CATEGORIES.index(e["category"]), A.TIER_ORDER.index(e["tier"]), e["order"]))
    else:                # closest to done first; finished ones last
        lst.sort(key=lambda e: (e["state"] == "unlocked", -e["frac"], e["order"]))
    return lst


def completion(entries):
    done = sum(1 for e in entries if e["state"] == "unlocked")
    return done, len(entries), (done / len(entries) if entries else 0.0)


# ---------------------------------------------------------------------- #
# the window
# ---------------------------------------------------------------------- #
class Screen:
    def __init__(self, game):
        self.game = game
        self.tracker = ach_tracker.tracker()
        self.entries = self.tracker.all_entries()
        self.filt, self.cat, self.sort = 0, 0, 0
        self.selected = 0
        self.scroll, self.scroll_v, self.scroll_t = 0.0, 0.0, None
        self.t, self.opened = 0.0, 0.0
        self.quit = False
        self.back = True
        self.drag = None            # (start_y, scroll_at_start, moved, last_y, last_time)
        self.stick_y = 0.0
        self.parts = fx.Particles()
        self.rects = {}             # chips / tabs / sort / back, rebuilt every layout
        self.card_rects = []        # (rect, index) for hit-testing, rebuilt every draw
        self._rebuild()
        done, total, frac = completion(self.entries)
        self.burst = 1.2 if (total and done == total) else None      # a 100% celebration

    # ---------------- state ---------------- #
    def _rebuild(self, keep=None):
        self.visible = visible_entries(self.entries, self.filt, CATS[self.cat], self.sort)
        self.selected = 0 if keep is None else max(0, min(len(self.visible) - 1, keep))
        self.scroll_t = 0.0 if self.visible else None
        self.opened = min(self.opened, 0.15)             # replay the cascade

    def _layout(self):
        w, h = self.game.window.get_size()
        k = max(0.6, min(1.5, min(w / 1280, h / 720)))
        L = type("L", (), {})()
        L.w, L.h, L.k = w, h, k
        L.margin = int(40 * k)
        L.head_h = int(96 * k)
        L.chip_h = int(34 * k)
        L.tab_y = L.head_h + int(14 * k) + L.chip_h + int(10 * k)
        L.list = pygame.Rect(L.margin, L.tab_y + int(40 * k) + int(10 * k), w - 2 * L.margin, h - (L.tab_y + int(40 * k) + int(10 * k)) - int(24 * k))
        L.card_w = min(L.list.w, int(940 * k))
        L.card_h = int(92 * k)
        L.gap = int(12 * k)
        L.row = L.card_h + L.gap
        L.content = max(0, len(self.visible) * L.row - L.gap)
        L.max_scroll = max(0, L.content - L.list.h)
        return L

    # ---------------- events ---------------- #
    def _set(self, filt=None, cat=None, sort=None):
        if filt is not None:
            self.filt = filt % len(FILTERS)
        if cat is not None:
            self.cat = cat % len(CATS)
        if sort is not None:
            self.sort = sort % len(SORTS)
        self._rebuild()
        _ui_tick()

    def _move(self, d, L):
        if not self.visible:
            return
        self.selected = max(0, min(len(self.visible) - 1, self.selected + d))
        top = self.selected * L.row
        if top < self.scroll:
            self.scroll_t = top
        elif top + L.card_h > self.scroll + L.list.h:
            self.scroll_t = top + L.card_h - L.list.h
        else:
            self.scroll_t = None
        self.scroll_v = 0.0
        _ui_tick(0.3)

    def _events(self, L):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.quit, self.back = True, False
            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                if k in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    self.quit = True
                elif k == pygame.K_DOWN:
                    self._move(1, L)
                elif k == pygame.K_UP:
                    self._move(-1, L)
                elif k == pygame.K_PAGEDOWN:
                    self._move(4, L)
                elif k == pygame.K_PAGEUP:
                    self._move(-4, L)
                elif k == pygame.K_HOME:
                    self._move(-10 ** 6, L)
                elif k == pygame.K_END:
                    self._move(10 ** 6, L)
                elif k == pygame.K_RIGHT:
                    self._set(filt=self.filt + 1)
                elif k == pygame.K_LEFT:
                    self._set(filt=self.filt - 1)
                elif k in (pygame.K_RIGHTBRACKET, pygame.K_TAB) and not (ev.mod & pygame.KMOD_SHIFT):
                    self._set(cat=self.cat + 1)
                elif k == pygame.K_LEFTBRACKET or (k == pygame.K_TAB and ev.mod & pygame.KMOD_SHIFT):
                    self._set(cat=self.cat - 1)
                elif k == pygame.K_s:
                    self._set(sort=self.sort + 1)
            elif ev.type == pygame.JOYHATMOTION:
                x, y = ev.value
                if y:
                    self._move(-y, L)
                elif x:
                    self._set(filt=self.filt + x)
            elif ev.type == pygame.JOYBUTTONDOWN:
                if ev.button == 1:
                    self.quit = True
                elif ev.button == 2:
                    self._set(sort=self.sort + 1)
                elif ev.button == 4:
                    self._set(cat=self.cat - 1)
                elif ev.button == 5:
                    self._set(cat=self.cat + 1)
            elif ev.type == pygame.JOYAXISMOTION and ev.axis == 1:
                self.stick_y = ev.value if abs(ev.value) > 0.25 else 0.0
            elif ev.type == pygame.MOUSEWHEEL:
                self.scroll_v -= ev.y * 900 * L.k
                self.scroll_t = None
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                self._press(ev.pos, L)
            elif ev.type == pygame.MOUSEMOTION and self.drag is not None and ev.buttons[0]:
                sy, s0, moved, ly, lt = self.drag
                dy = ev.pos[1] - sy
                now = time.time()
                if abs(dy) > 6:
                    moved = True
                if moved:
                    self.scroll = s0 - dy
                    self.scroll_t = None
                    self.scroll_v = -(ev.pos[1] - ly) / max(1e-3, now - lt)
                self.drag = (sy, s0, moved, ev.pos[1], now)
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.drag is not None:
                _, _, moved, _, _ = self.drag
                self.drag = None
                if not moved:
                    self._click(ev.pos, L)
                else:
                    self.scroll_v = max(-4000.0, min(4000.0, self.scroll_v))

    def _press(self, pos, L):
        if L.list.collidepoint(pos):
            self.drag = (pos[1], self.scroll, False, pos[1], time.time())
        else:
            self._click(pos, L)

    def _click(self, pos, L):
        for name, rect in self.rects.items():
            if rect.collidepoint(pos):
                kind, _, idx = name.partition(":")
                if kind == "back":
                    self.quit = True
                elif kind == "filter":
                    self._set(filt=int(idx))
                elif kind == "cat":
                    self._set(cat=int(idx))
                elif kind == "sort":
                    self._set(sort=self.sort + 1)
                return
        for rect, i in self.card_rects:
            if rect.collidepoint(pos) and L.list.collidepoint(pos):
                self.selected = i
                _ui_tick(0.3)
                return

    # ---------------- update ---------------- #
    def _update(self, dt, L):
        self.t += dt
        self.opened += dt
        self.parts.update(dt)
        self.scroll_v += self.stick_y * 2200 * L.k * dt
        if self.drag is None:
            if self.scroll_t is not None:
                self.scroll = fx.smooth_to(self.scroll, self.scroll_t, dt, 14)
                if abs(self.scroll - self.scroll_t) < 0.5:
                    self.scroll, self.scroll_t = self.scroll_t, None
            else:
                self.scroll += self.scroll_v * dt
                self.scroll_v *= math.exp(-6.0 * dt)
                if abs(self.scroll_v) < 8:
                    self.scroll_v = 0.0
        # rubber band at the ends
        if self.scroll < 0:
            self.scroll = fx.smooth_to(self.scroll, 0.0, dt, 18) if self.drag is None else self.scroll
        elif self.scroll > L.max_scroll:
            self.scroll = fx.smooth_to(self.scroll, float(L.max_scroll), dt, 18) if self.drag is None else self.scroll
        if self.burst is not None:
            self.burst -= dt
            if self.burst <= 0:
                self.burst = None
                for _ in range(5):
                    x = L.w * (0.2 + 0.6 * ((_ * 0.37) % 1.0))
                    for c in A.TIER_COLORS.values():
                        self.parts.spark(x, L.h * 0.3, c, count=18, speed=240, life=1.2, size=3, gravity=180)

    # ---------------- draw ---------------- #
    def _chip(self, surf, rect, label, active, accent, hover):
        fill = (84, 40, 52) if active else ((62, 34, 44) if hover else (40, 27, 36))
        _panel(surf, rect, fill, accent if (active or hover) else (92, 62, 66), 2 if active else 1, rect.height // 2)
        s = _txt(label, max(11, int(rect.height * 0.42)), ui.CREAM if active else (200, 190, 196), True)
        surf.blit(s, s.get_rect(center=rect.center))

    def _draw(self, L):
        game = self.game
        win = game.window
        k, t = L.k, self.t
        game.draw_menu_bg()
        mouse = pygame.mouse.get_pos()
        self.rects = {}

        # ----- header: ring + title -----
        done, total, frac = completion(self.entries)
        ring_c = (L.margin + int(46 * k), int(L.head_h * 0.5) + int(6 * k))
        rr = int(40 * k)
        pygame.draw.circle(win, ui.INK, ring_c, rr + 4)
        pygame.draw.circle(win, (44, 30, 40), ring_c, rr)
        steps = max(2, int(80 * frac))
        if frac > 0:
            pts = [ring_c]
            for i in range(steps + 1):
                a = -math.pi / 2 + math.tau * frac * i / steps
                pts.append((ring_c[0] + math.cos(a) * rr, ring_c[1] + math.sin(a) * rr))
            pygame.draw.polygon(win, fx.lerp_color(ui.GOLD, ui.CORAL, 0.5 + 0.5 * math.sin(t * 2)) if frac < 1 else ui.GOLD, pts)
        pygame.draw.circle(win, (30, 20, 28), ring_c, rr - int(9 * k))
        fx.text_alpha(win, f"{int(round(frac * 100))}%", ring_c, int(17 * k), ui.CREAM, 255, True, True, shadow=False)
        fx.wave_text(win, "ACHIEVEMENTS", (ring_c[0] + rr + int(24 * k), ring_c[1] - int(18 * k)), int(40 * k), ui.CREAM, ui.GOLD, t, amp=3 * k)
        fx.text_alpha(win, f"{done} of {total} unlocked", (ring_c[0] + rr + int(26 * k), ring_c[1] + int(24 * k)), int(15 * k),
                      (210, 196, 190), 255, False, False)

        back = pygame.Rect(L.w - L.margin - int(110 * k), int(18 * k), int(110 * k), int(38 * k))
        self.rects["back"] = back
        self._chip(win, back, "BACK", False, ui.CORAL, back.collidepoint(mouse))

        # ----- filter chips + sort -----
        cy = L.head_h + int(14 * k)
        x = L.margin
        for i, name in enumerate(FILTERS):
            wch = int(_txt(name, max(11, int(L.chip_h * 0.42)), ui.WHITE, True).get_width() + 34 * k)
            rect = pygame.Rect(x, cy, wch, L.chip_h)
            self.rects[f"filter:{i}"] = rect
            self._chip(win, rect, name, i == self.filt, ui.GOLD, rect.collidepoint(mouse))
            x += wch + int(8 * k)
        sort_rect = pygame.Rect(L.w - L.margin - int(190 * k), cy, int(190 * k), L.chip_h)
        self.rects["sort"] = sort_rect
        self._chip(win, sort_rect, f"SORT: {SORTS[self.sort]}", False, ui.CORAL, sort_rect.collidepoint(mouse))

        # ----- category tabs -----
        x = L.margin
        ty = L.tab_y
        th = int(36 * k)
        for i, name in enumerate(CATS):
            n_done = sum(1 for e in self.entries if (i == 0 or e["category"] == name) and e["state"] == "unlocked")
            n_all = sum(1 for e in self.entries if (i == 0 or e["category"] == name))
            label = f"{name.upper()}  {n_done}/{n_all}"
            wtab = int(_txt(label, max(11, int(th * 0.4)), ui.WHITE, True).get_width() + 28 * k)
            rect = pygame.Rect(x, ty, wtab, th)
            self.rects[f"cat:{i}"] = rect
            active = i == self.cat
            hover = rect.collidepoint(mouse)
            pygame.draw.rect(win, (62, 36, 46) if active else (34, 24, 32), rect, border_top_left_radius=9, border_top_right_radius=9)
            s = _txt(label, max(11, int(th * 0.4)), ui.GOLD if active else (190, 180, 188), True)
            win.blit(s, s.get_rect(center=rect.center))
            if active:
                pygame.draw.rect(win, ui.GOLD, (rect.x, rect.bottom - 3, rect.w, 3))
            elif hover:
                pygame.draw.rect(win, (150, 100, 100), (rect.x, rect.bottom - 2, rect.w, 2))
            x += wtab + int(4 * k)
        pygame.draw.line(win, (90, 60, 64), (L.margin, ty + th), (L.w - L.margin, ty + th), 1)

        # ----- list -----
        old = win.get_clip()
        win.set_clip(L.list)
        self.card_rects = []
        x0 = L.list.centerx - L.card_w // 2
        if not self.visible:
            fx.text_alpha(win, "Nothing here yet - keep playing!", L.list.center, int(22 * k), (190, 180, 188), 255, True, True)
        first = max(0, int((self.scroll) // L.row) - 1)
        last = min(len(self.visible), int((self.scroll + L.list.h) // L.row) + 2)
        for i in range(first, last):
            e = self.visible[i]
            surf, bar, mc, r = render_card(e, L.card_w, L.card_h, k)
            y = L.list.y + i * L.row - int(self.scroll)
            p = fx.clamp((self.opened - i * 0.045) / 0.4)
            if p <= 0:
                continue
            slide = (1 - fx.ease_out_back(p)) * -90 * k
            sel = i == self.selected
            lift = -int(4 * k) if sel else 0
            rect = pygame.Rect(x0 + int(slide), y + lift, L.card_w, L.card_h)
            self.card_rects.append((rect, i))
            if sel:
                tier = A.TIER_COLORS.get(e["tier"], ui.GOLD)
                fx.glow(win, rect.center, tier, int(L.card_w * 0.42), 0.55 + 0.2 * math.sin(t * 4), L.list)
            surf.set_alpha(int(255 * p))
            win.blit(surf, rect.topleft)
            if sel:
                pygame.draw.rect(win, ui.CREAM, rect, 2, border_radius=int(14 * k))
            # live extras on top of the cached card
            if bar is not None and e["state"] == "progress":
                sx = bar.x + int(((t * 0.6) % 1.4 - 0.2) * bar.width)
                strip = pygame.Rect(sx, rect.y + bar.y, int(bar.width * 0.12), bar.height).clip(
                    pygame.Rect(rect.x + bar.x, rect.y + bar.y, max(1, int(bar.width * e["frac"])), bar.height))
                if strip.width > 0:
                    win.fill((70, 70, 70), strip, special_flags=pygame.BLEND_RGB_ADD)
            if e["state"] == "unlocked":
                phase = (t + i * 0.37) % 3.4
                if phase < 0.8:
                    frame = int(phase / 0.8 * (SHINE_FRAMES - 1))
                    win.blit(_shine(r, frame), (rect.x + mc[0] - r, rect.y + mc[1] - r))
            if e["new"]:
                a = 0.6 + 0.4 * math.sin(t * 6)
                tag = pygame.Rect(0, 0, int(46 * k), int(20 * k))
                tag.topright = (rect.right - int(10 * k), rect.top + int(8 * k))
                _panel(win, tag, (214, 60, 80), ui.CREAM, 2, 8)
                s = _txt("NEW", max(10, int(14 * k)), ui.CREAM, True)
                s.set_alpha(int(255 * a))
                win.blit(s, s.get_rect(center=tag.center))
        win.set_clip(old)

        # scroll bar
        if L.max_scroll > 0:
            track = pygame.Rect(L.list.right - int(6 * k), L.list.y, int(4 * k), L.list.h)
            pygame.draw.rect(win, (50, 36, 44), track, border_radius=2)
            thumb_h = max(int(30 * k), int(track.h * L.list.h / (L.content or 1)))
            ty0 = track.y + int((track.h - thumb_h) * (max(0.0, min(1.0, self.scroll / L.max_scroll))))
            pygame.draw.rect(win, (150, 110, 110), (track.x, ty0, track.w, thumb_h), border_radius=2)

        fx.text_alpha(win, "UP / DOWN select   LEFT / RIGHT filter   [ ] category   S sort   ESC back",
                      (L.w // 2, L.h - int(12 * k)), int(12 * k), (150, 140, 150), 255, False, True, shadow=False)
        self.parts.draw(win, t)

    # ---------------- run ---------------- #
    def run(self):
        """Returns False if the game window was closed."""
        game, dt = self.game, 1 / 60
        while True:
            L = self._layout()
            self._events(L)
            if self.quit:
                break
            L = self._layout()
            self._update(dt, L)
            self._draw(L)
            pygame.display.flip()
            dt = min(0.05, game.clock.tick(getattr(game, "FPS", 60)) / 1000.0)
        self.tracker.mark_seen()
        return self.back


def open_achievements(game):
    """Open the window; blocks until it is closed. False if the game window was closed."""
    return Screen(game).run()
