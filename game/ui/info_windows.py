"""
info_windows.py
===============
The Mode, Game Info, Author Info and Entity Info windows, built on ui/window_kit.py.

    open_mode(game)            Solo / Split Screen / Host / Join as a card carousel (live animated preview)
    open_game_info(game)       tabbed pages: How to play, Controls, Characters, Shop & coins,
                               Charms & allies, Tips - all generated from data (no stale text)
    open_author(game)          hero card, link pills, credits roll read from docs/CREDITS.md
    open_entity(game, entity)  portrait, stat bars, facts and the shared befriend code path

Each returns True, or False when the game window was closed inside it (callers re-post QUIT).

Note on "Mode": the old window only switched Solo / Multiplayer and Host / Join, so that is what the
carousel presents (one card per mode). The hero type / colour picker is part of the in-game player
editor and is untouched.
"""

import math
import re
import webbrowser
from pathlib import Path

import pygame

from . import ui_fx as fx
from . import ui_theme as ui
from .window_kit import (Action, KitWindow, card_ease, draw_card, fit, frame_at, key_glyph, pad_glyph, panel, pill,
                         sprite_frames, stat_bar, tag, txt, wrap)
from ..data import charms as C
from ..data import info_pages as P
from ..data.controls import control_rows, key_label
from ..data.shop_items import CURRENCIES, TABS, items_for_tab
from ..scripts import paths
from ..settings import Settings
from ..version import VERSION

CORAL, GOLD, MINT = (255, 112, 92), (255, 202, 80), (108, 201, 117)


def _clip(surf, rect):
    old = surf.get_clip()
    surf.set_clip(rect)
    return old


# ====================================================================== #
# MODE
# ====================================================================== #
class ModeWindow(KitWindow):
    title = "MODE"
    width_frac, height_frac = 0.86, 0.80

    def __init__(self, game):
        super().__init__(game)
        self.modes = P.MODES
        self.index = self.current()
        self.pos = float(self.index)
        self.flash = 0.0

    def _state(self):
        """(multiplayer, server, split_screen) of the game right now, the shape of the MODES tuples."""
        g = self.game
        multi = bool(g.MULTIPLAYER)
        return (multi, bool(g.SERVER) if multi else False,
                bool(getattr(g, "SPLIT_SCREEN", False)) and not multi)

    def current(self):
        state = self._state()
        return next((i for i, m in enumerate(self.modes) if m[4] == state), 0)

    def apply(self, i):
        multi, server, split = self.modes[i][4]
        self.game.MULTIPLAYER = multi
        self.game.SPLIT_SCREEN = split              # local co-op: levels stay on this machine (level_loader.max_local_players)
        if multi:
            self.game.SERVER = server
        else:
            self.game.SERVER = False
        self.game._multiplayer_from_selector = False
        self.game.CONNECTION_TYPE = 'HOST (server)' if self.game.SERVER else 'JOIN (client)'
        self.flash = 1.0

    def on_action(self, action, data=None):
        n = len(self.modes)
        if action in (Action.LEFT, Action.PREV):
            self.index = (self.index - 1) % n
            return True
        if action in (Action.RIGHT, Action.NEXT):
            self.index = (self.index + 1) % n
            return True
        if action == Action.CONFIRM:
            self.apply(self.index)
            return True
        if action == Action.BACK:
            return False
        if action == Action.CLICK:
            for name, rect in self.rects.items():
                if name.startswith("card:") and rect.collidepoint(data):
                    i = int(name.split(":")[1])
                    if i == self.index:
                        self.apply(i)
                    else:
                        self.index = i
                    return True
            if "apply" in self.rects and self.rects["apply"].collidepoint(data):
                self.apply(self.index)
                return True
            for name in ("prev", "next"):
                if name in self.rects and self.rects[name].collidepoint(data):
                    self.index = (self.index + (-1 if name == "prev" else 1)) % n
                    return True
        return False

    def update(self, dt):
        self.pos = fx.smooth_to(self.pos, float(self.index), dt, 10)
        self.flash = max(0.0, self.flash - dt * 2.5)

    def hint(self):
        return "LEFT / RIGHT choose   ENTER or click to select   ESC back"

    # ----- previews -----
    def _heroes(self, surf, rect, key, t):
        """Little live scene per mode, from the real character sprites."""
        cx, cy = rect.centerx, rect.bottom - int(rect.h * 0.1)
        h = int(rect.h * 0.55)
        if key == "split":
            self._split_preview(surf, rect, t)
            return
        cast = {"solo": [("Warrior", "Blue")],
                "host": [("Warrior", "Blue"), ("Archer", "Red"), ("Pawn", "Green")],
                "join": [("Torch", "Purple"), ("Archer", "Blue")]}[key]
        n = len(cast)
        for i, (name, color) in enumerate(cast):
            sheet = "idle_right" if name == "Archer" else "idle_right"
            fr = frame_at(sprite_frames(name, color, sheet, h), t + i * 0.3)
            if fr is None:
                continue
            x = cx + (i - (n - 1) / 2) * int(rect.w * 0.28)
            fx.glow(surf, (x, cy - fr.get_height() // 2), (255, 160, 110), int(h * 0.7), 0.25, rect)
            surf.blit(fr, fr.get_rect(midbottom=(int(x), cy + int(2 * math.sin(t * 2 + i)))))
        if key != "solo":                                   # a link between the players
            y = cy - int(h * 0.55)
            x0, x1 = cx - int(rect.w * 0.28 * (n - 1) / 2), cx + int(rect.w * 0.28 * (n - 1) / 2)
            for k in range(12):
                u = (k / 11.0)
                x = x0 + (x1 - x0) * u
                bob = math.sin(t * 3 - u * 6) * 4
                col = (120, 190, 255) if key == "join" else (255, 202, 80)
                pygame.draw.circle(surf, col, (int(x), int(y + bob)), 2 + (k + int(t * 6)) % 3 // 2)

    def _split_preview(self, surf, rect, t):
        """Four little viewports, one hero in each, with the divider cross a real split screen has."""
        gap = 4
        pw, ph = (rect.w - gap * 3) // 2, (rect.h - gap * 3) // 2
        cast = [("Warrior", "Blue"), ("Archer", "Red"), ("Pawn", "Green"), ("Torch", "Purple")]
        for n, (name, color) in enumerate(cast):
            pane = pygame.Rect(rect.x + gap + (n % 2) * (pw + gap), rect.y + gap + (n // 2) * (ph + gap), pw, ph)
            pygame.draw.rect(surf, (34, 24, 44) if n % 3 == 0 else (28, 20, 38), pane, border_radius=8)
            pygame.draw.rect(surf, (0, 200, 200), pane, 1, border_radius=8)
            # a floor line so each pane reads as its own little world
            pygame.draw.line(surf, (70, 50, 70), (pane.x + 6, pane.bottom - 10), (pane.right - 6, pane.bottom - 10), 2)
            fr = frame_at(sprite_frames(name, color, "idle_right", max(14, int(ph * 0.62))), t + n * 0.27)
            if fr is not None:
                fx.glow(surf, pane.center, (255, 160, 110), int(ph * 0.45), 0.2, pane)
                surf.blit(fr, fr.get_rect(midbottom=(pane.centerx, pane.bottom - 10 + int(1.5 * math.sin(t * 2 + n)))))
            tag(surf, (pane.x + 5, pane.y + 5), f"P{n + 1}", (255, 202, 80), max(9, int(ph * 0.13)))

    def draw_body(self, surf, body, t):
        dt = 1 / 60
        # centre card + two peeking neighbours
        cw, ch = int(body.w * 0.44), int(body.h * 0.88)
        centre = body.center
        for i, m in enumerate(self.modes):
            off = i - self.pos
            if abs(off) > 1.6:
                continue
            near = 1.0 - min(1.0, abs(off))
            w = int(cw * (0.72 + 0.28 * near))
            h = int(ch * (0.78 + 0.22 * near))
            r = pygame.Rect(0, 0, w, h)
            r.center = (int(centre[0] + off * cw * 0.82), centre[1])
            self.rects[f"card:{i}"] = r
            e = card_ease(self.ease, ("mode", i), i == self.index or r.collidepoint(self.hover_pos), dt)
            active = i == self.current()
            accent = MINT if active else CORAL
            cr = draw_card(surf, r, e * 0.7, accent, selected=i == self.index, fill=(36, 24, 34) if near > 0.5 else (28, 20, 28))
            if near < 0.45:
                s = txt(m[1], max(16, int(h * 0.1)), (160, 150, 160), True)
                surf.blit(s, s.get_rect(center=cr.center))
                continue
            inner = cr.inflate(-int(w * 0.1), -int(h * 0.08))
            title = txt(m[1], max(22, int(h * 0.1)), ui.CREAM, True)
            surf.blit(title, (inner.x, inner.y))
            if active:
                tag(surf, (inner.right, inner.y + 4), "ACTIVE", MINT, max(11, int(h * 0.04)), "topright")
            surf.blit(txt(m[2], max(12, int(h * 0.05)), GOLD, True), (inner.x, inner.y + title.get_height() + 2))
            scene = pygame.Rect(inner.x, inner.y + int(h * 0.17), inner.w, int(h * 0.36))
            pygame.draw.rect(surf, (20, 14, 24), scene, border_radius=12)
            old = _clip(surf, scene)
            self._heroes(surf, scene, m[0], t)
            surf.set_clip(old)
            y = scene.bottom + int(h * 0.03)
            for line in wrap(m[3], max(11, int(h * 0.04)), False, inner.w)[:4]:
                s = txt(line, max(11, int(h * 0.04)), (214, 202, 204))
                surf.blit(s, (inner.x, y))
                y += s.get_height() + 1
            y += int(h * 0.015)
            for label, yes in m[5]:
                col = MINT if yes else (190, 100, 100)
                x = inner.x
                pygame.draw.circle(surf, col, (x + 7, y + 8), 7)
                if yes:
                    pygame.draw.lines(surf, ui.INK, False, [(x + 3, y + 8), (x + 6, y + 11), (x + 11, y + 5)], 2)
                else:
                    pygame.draw.line(surf, ui.INK, (x + 4, y + 5), (x + 10, y + 11), 2)
                    pygame.draw.line(surf, ui.INK, (x + 10, y + 5), (x + 4, y + 11), 2)
                s = txt(label, max(11, int(h * 0.04)), (214, 202, 204) if yes else (160, 150, 156))
                surf.blit(s, (x + 20, y))
                y += s.get_height() + 3
        # arrows + select button
        for name, sign, x in (("prev", -1, body.x + 4), ("next", 1, body.right - 4)):
            r = pygame.Rect(0, 0, 44, 64)
            r.center = (x + (22 if sign < 0 else -22), centre[1])
            self.rects[name] = r
            hv = self.pill_ease(name, dt)
            pill(surf, r, "<" if sign < 0 else ">", False, hv, CORAL, size=26)
        ap = pygame.Rect(0, 0, int(body.w * 0.2), 40)
        ap.midbottom = (body.centerx, body.bottom + 8)
        self.rects["apply"] = ap
        pill(surf, ap, "SELECT" if self.index != self.current() else "SELECTED", self.index == self.current(),
             self.pill_ease("apply", dt), MINT)
        if self.flash > 0:
            fx.glow(surf, body.center, MINT, int(body.w * 0.4), 0.4 * self.flash, body)


# ====================================================================== #
# GAME INFO
# ====================================================================== #
class _Page:
    def __init__(self, surf, live=None):
        self.surf, self.live = surf, live or []     # live: [(rect_in_page, kind, data)]
        self.height = surf.get_height()


class GameInfoWindow(KitWindow):
    title = "GAME INFO"

    def __init__(self, game):
        super().__init__(game)
        self.tab = 0
        self.scroll, self.scroll_v = 0.0, 0.0
        self.pages = {}

    # ---------- page builders (rendered once per tab + width) ----------
    def _build(self, tab, width):
        k = max(0.75, min(1.4, self.game.window.get_height() / 720))
        fs, hs = max(13, int(16 * k)), max(16, int(21 * k))
        name = P.GAME_INFO_TABS[tab]
        blocks = []        # (height, painter(surf, y))
        live = []
        rows = []

        def para(text, size=fs, color=(224, 212, 214), bold=False, indent=0):
            lines = wrap(text, size, bold, width - indent)
            return [(txt(l, size, color, bold), indent) for l in lines]

        y = 6
        surf_ops = []   # (callable)

        def heading(text):
            nonlocal y
            surf_ops.append(("txt", txt(text, hs, GOLD, True), 0, y))
            y += hs + 8

        def text(text_, color=(224, 212, 214), indent=0, gap=8):
            nonlocal y
            for s, ind in para(text_, fs, color, False, indent):
                surf_ops.append(("txt", s, ind, y))
                y += s.get_height() + 2
            y += gap

        if name == "HOW TO PLAY":
            surf_ops.append(("txt", txt(f"PIXEL ABYSS  v{VERSION}", int(hs * 1.15), ui.CREAM, True), 0, y))
            y += int(hs * 1.15) + 6
            text("A pixel-art action platformer with exploration, combat, biomes, level editing, doors, enemies "
                 "and collectibles.", (190, 180, 186), gap=14)
            for head, body in P.HOW_TO_PLAY:
                heading(head)
                text(body)
        elif name == "CONTROLS":
            self._controls(surf_ops, width, k, fs, hs)
            y = self._controls_height
        elif name == "CHARACTERS":
            heading("Heroes and foes share the same five fighters")
            text("Bars are rough guides; health and reach are the real base values.", (170, 160, 166), gap=10)
            card_h = int(112 * k)
            for cname, (blurb, hp, spd, rng, special) in P.CHARACTERS.items():
                r = pygame.Rect(0, y, width, card_h)
                surf_ops.append(("card", r))
                sprite = pygame.Rect(10, y + 8, int(card_h * 0.8), card_h - 16)
                live.append((sprite, "sprite", cname))
                x = sprite.right + 18
                surf_ops.append(("txt", txt(cname.upper(), hs, ui.CREAM, True), x, y + 8))
                surf_ops.append(("txt", txt(special, fs - 2, GOLD, True), x + width // 5, y + 12))
                for i, line in enumerate(wrap(blurb, fs - 1, False, width - x - 20)[:2]):
                    surf_ops.append(("txt", txt(line, fs - 1, (214, 202, 204)), x, y + 8 + hs + 2 + i * (fs + 1)))
                by = y + card_h - int(30 * k)
                bw = (width - x - 30) // 3
                for j, (lab, val, mx) in enumerate((("HEALTH", hp, 100), ("SPEED", spd, 5), ("REACH", rng, 5))):
                    surf_ops.append(("bar", pygame.Rect(x + j * (bw + 10), by, bw, int(18 * k)), val / mx,
                                     (MINT, (120, 190, 255), CORAL)[j], lab, val if lab == "HEALTH" else None))
                y += card_h + 10
        elif name == "SHOP & COINS":
            for line in P.SHOP_LINES:
                text(line, gap=4)
            y += 8
            heading("Coins")
            for cur in CURRENCIES:
                label, blurb = P.CURRENCY_INFO[cur]
                r = pygame.Rect(0, y, width, int(54 * k))
                surf_ops.append(("card", r))
                surf_ops.append(("coin", cur, (28 + 4, r.centery), int(34 * k)))
                surf_ops.append(("txt", txt(label.upper(), hs, fx.COIN_COLORS.get(cur, ui.CREAM), True), 70, r.y + 6))
                lines = wrap(blurb, fs - 1, False, width - 200)
                surf_ops.append(("txt", txt(lines[0], fs - 1, (214, 202, 204)), 70 + int(width * 0.16), r.y + 8))
                if len(lines) > 1:
                    surf_ops.append(("txt", txt(lines[1], fs - 1, (214, 202, 204)), 70 + int(width * 0.16), r.y + 8 + fs + 2))
                y += r.h + 8
            y += 6
            heading("What the shop sells")
            for tab_ in TABS:
                its = items_for_tab(tab_["id"])
                surf_ops.append(("txt", txt(f"{tab_['label']}  ({len(its)})", fs + 1, ui.CREAM, True), 0, y))
                y += fs + 5
                text(", ".join(i["name"] for i in its), (190, 180, 186), indent=14, gap=6)
        elif name == "CHARMS & ALLIES":
            keys = [key_label(v) for v in Settings.CHARM_KEYS.values()]
            fmt = {"charm_key": " / ".join(keys), "time": C.BASE_TIME, "refund": C.CANCEL_REFUND_WINDOW,
                   "limit": C.BASE_FRIEND_LIMIT}
            heading("Befriend Charms")
            for line in P.CHARM_LINES:
                text("-  " + line.format(**fmt), gap=6)
            y += 6
            heading("The rules in numbers")
            for lab, val in (("Time to choose", f"{C.BASE_TIME:g} s (+ Long Charm)"),
                             ("Misclick refund window", f"{C.CANCEL_REFUND_WINDOW:g} s"),
                             ("Boss penalty", f"{int(C.BOSS_PENALTY_PCT * 100)}% max health, at least {C.BOSS_PENALTY_MIN}"),
                             ("Too-strong penalty", f"{int(C.GAP_PENALTY_MIN_PCT * 100)}-{int(C.GAP_PENALTY_MAX_PCT * 100)}% max health"),
                             ("Friends at once", f"{C.BASE_FRIEND_LIMIT} (+ Entourage)"),
                             ("Friend stays within", f"{C.LEASH} px of you")):
                surf_ops.append(("txt", txt(lab, fs, (190, 180, 186)), 14, y))
                surf_ops.append(("txt", txt(val, fs, ui.CREAM, True), int(width * 0.42), y))
                y += fs + 8
        else:  # TIPS
            for tip in P.TIPS:
                r_h = max(fs + 14, len(wrap(tip, fs, False, width - 56)) * (fs + 3) + 14)
                surf_ops.append(("card", pygame.Rect(0, y, width, r_h)))
                surf_ops.append(("dot", (22, y + r_h // 2)))
                for i, line in enumerate(wrap(tip, fs, False, width - 56)):
                    surf_ops.append(("txt", txt(line, fs, (224, 212, 214)), 42, y + 7 + i * (fs + 3)))
                y += r_h + 8

        total = y + 20
        surf = pygame.Surface((width, max(total, 10)), pygame.SRCALPHA)
        for op in surf_ops:
            kind = op[0]
            if kind == "txt":
                surf.blit(op[1], (op[2], op[3]))
            elif kind == "card":
                panel(surf, op[1], (40, 27, 36), (100, 62, 64), 2, 12)
            elif kind == "bar":
                stat_bar(surf, op[1], op[2], op[3], op[4], op[5], size=max(10, op[1].h - 6))
            elif kind == "coin":
                fx.draw_coin(surf, op[2], op[1], op[3], 0.0)
            elif kind == "dot":
                pygame.draw.circle(surf, GOLD, op[1], 6)
            elif kind == "glyphs":
                op[1](surf)
        return _Page(surf, live)

    def _controls(self, ops, width, k, fs, hs):
        """The key table (data/controls.py) drawn as rows of keycaps. Records its own height."""
        rows = control_rows()
        row_h = int(44 * k)
        head_h = int(34 * k)
        cols = [0.0, 0.25, 0.43, 0.61, 0.79]     # action | P1 | P2 | PAD | TOUCH
        y = 4
        ops.append(("txt", txt("Every action, for every way of playing", hs, GOLD, True), 0, y))
        y += hs + 12
        titles = ("ACTION", "KEYBOARD 1 (arrows)", "KEYBOARD 2 (WASD)", "GAMEPAD", "TOUCH")
        for i, ttl in enumerate(titles):
            ops.append(("txt", txt(ttl, max(10, fs - 3), (170, 160, 166), True), int(width * cols[i]) + (0 if i == 0 else 4), y))
        y += head_h - 8
        for n, row in enumerate(rows):
            r = pygame.Rect(0, y, width, row_h - 4)
            ops.append(("card", r))
            ops.append(("txt", txt(row["action"], fs, ui.CREAM, True), 12, y + 5))
            note = fit(row["note"], fs - 4, False, int(width * 0.24) - 16)
            ops.append(("txt", txt(note, fs - 4, (160, 150, 156)), 12, y + 5 + fs + 1))

            def paint(surf, row=row, y=y, r=r):
                for ci, key in ((1, "p1"), (2, "p2"), (3, "pad")):
                    x = int(width * cols[ci]) + 4
                    for lab in row[key]:
                        if lab in ("-",):
                            surf.blit(txt("-", fs, (110, 104, 110)), (x, r.centery - fs // 2))
                            continue
                        gl = (pad_glyph if key == "pad" else key_glyph)
                        rect = gl(surf, (x, r.centery - int(k * 11)), lab, int(22 * k))
                        x = rect.right + 5
                t = fit(row["touch"], fs - 2, False, int(width * 0.21))
                surf.blit(txt(t, fs - 2, (200, 190, 196)), (int(width * cols[4]) + 4, r.centery - (fs - 2) // 2 - 1))
            ops.append(("glyphs", paint))
            y += row_h
        self._controls_height = y + 14

    def _page(self, body):
        key = (self.tab, body.w, self.game.window.get_height())
        page = self.pages.get(key)
        if page is None:
            if len(self.pages) > 12:
                self.pages.clear()
            page = self.pages[key] = self._build(self.tab, body.w - 22)
        return page

    # ---------- input ----------
    def _max_scroll(self, body):
        return max(0, self._page(body).height - self._tab_body(body).h)

    def _tab_body(self, body):
        return pygame.Rect(body.x, body.y + 52, body.w, body.h - 52)

    def on_action(self, action, data=None):
        n = len(P.GAME_INFO_TABS)
        body = self._last_body if hasattr(self, "_last_body") else None
        if action in (Action.LEFT, Action.PREV):
            self._set_tab(self.tab - 1)
            return True
        if action in (Action.RIGHT, Action.NEXT):
            self._set_tab(self.tab + 1)
            return True
        if body is None:
            return False
        if action == Action.DOWN:
            self.scroll_v += 700
            return True
        if action == Action.UP:
            self.scroll_v -= 700
            return True
        if action == Action.SCROLL:
            self.scroll_v -= data * 900
            return True
        if action == Action.DRAG:
            self.scroll = max(0.0, min(float(self._max_scroll(body)), self.scroll - data))
            self.scroll_v = 0.0
            return True
        if action == Action.CLICK:
            for name, rect in self.rects.items():
                if name.startswith("tab:") and rect.collidepoint(data):
                    self._set_tab(int(name[4:]))
                    return True
        return False

    def _set_tab(self, i):
        self.tab = i % len(P.GAME_INFO_TABS)
        self.scroll = self.scroll_v = 0.0

    def hint(self):
        return "LEFT / RIGHT or [ ] change page   UP / DOWN or wheel scroll   ESC back"

    def update(self, dt):
        self.scroll += self.scroll_v * dt
        self.scroll_v *= math.exp(-7 * dt)
        if abs(self.scroll_v) < 6:
            self.scroll_v = 0.0

    def draw_body(self, surf, body, t):
        dt = 1 / 60
        self._last_body = body
        x = body.x
        h = max(26, int(body.h * 0.075))
        for i, name in enumerate(P.GAME_INFO_TABS):
            w = int(txt(name, int(h * 0.42), ui.CREAM, True).get_width() + h * 0.9)
            r = pygame.Rect(x, body.y, w, h)
            self.rects[f"tab:{i}"] = r
            pill(surf, r, name, i == self.tab, self.pill_ease(f"tab:{i}", dt), CORAL)
            x += w + 8
        area = self._tab_body(body)
        page = self._page(body)
        maxs = max(0, page.height - area.h)
        self.scroll = max(-30.0, min(maxs + 30.0, self.scroll))
        if self.scroll < 0 or self.scroll > maxs:
            self.scroll = fx.smooth_to(self.scroll, max(0.0, min(float(maxs), self.scroll)), dt, 12)
        off = int(self.scroll)
        old = _clip(surf, area)
        surf.blit(page.surf, (area.x, area.y - off))
        for rect, kind, data in page.live:                  # animated bits drawn over the cached page
            if kind == "sprite":
                fr = frame_at(sprite_frames(data, "Blue", "idle_right", rect.h), t)
                if fr is not None:
                    dest = fr.get_rect(center=(area.x + rect.centerx, area.y + rect.centery - off))
                    surf.blit(fr, dest)
        surf.set_clip(old)
        if maxs > 0:                                          # scroll bar
            track = pygame.Rect(area.right - 6, area.y, 4, area.h)
            pygame.draw.rect(surf, (50, 36, 44), track, border_radius=2)
            th = max(30, int(track.h * area.h / max(1, page.height)))
            ty = track.y + int((track.h - th) * (self.scroll / maxs))
            pygame.draw.rect(surf, (150, 110, 110), (track.x, ty, track.w, th), border_radius=2)


# ====================================================================== #
# AUTHOR
# ====================================================================== #
_EMOJI = re.compile("[\u2600-\u27BF\uFE00-\uFE0F\U0001F000-\U0001FFFF\u200d]")


def load_credits():
    """Parse docs/CREDITS.md into [(kind, text)], kind in title|section|name|label|text|quote.
    Missing file -> a short fallback so the window never fails."""
    candidates = [paths.DOCS_DIR / "CREDITS.md"]
    text = ""
    for p in candidates:
        try:
            text = p.read_text(encoding="utf-8")
            break
        except OSError:
            continue
    if not text:
        return [("section", "CREDITS"), ("text", "Made by Blessing Machekeche (BLEMAC).")]
    out = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = _EMOJI.sub("", raw).rstrip()
        s = line.strip()
        if not s or s == "---" or s.startswith("# "):
            continue
        s = s.replace("**", "").replace("`", "")
        if s.startswith("### "):
            out.append(("name", s[4:].strip()))
        elif s.startswith("## "):
            out.append(("section", s[3:].strip()))
        elif s.startswith("> "):
            out.append(("quote", s[2:].strip()))
        elif s.startswith("- "):
            out.append(("label", s[2:].strip()))
        else:
            if out and out[-1][0] in ("label", "quote", "text") and raw.startswith(" "):
                out[-1] = (out[-1][0], out[-1][1] + " " + s)
            else:
                out.append(("text", s))
    return out


class AuthorWindow(KitWindow):
    title = "AUTHOR"

    def __init__(self, game):
        super().__init__(game)
        self.credits = load_credits()
        self.scroll = 0.0
        self.pause = 0.0
        self.sel = 0
        self._credit_surf = None
        self._credit_w = 0
        try:
            self.avatar = pygame.image.load(paths.asset("icons", "icon.png")).convert_alpha()
        except Exception:
            self.avatar = None

    def _fades(self, width):
        if getattr(self, "_fade_w", None) != width:
            self._fade_list = []
            for i in range(10):
                f = pygame.Surface((width, 2), pygame.SRCALPHA)
                f.fill((30, 21, 31, int(255 * (1 - i / 10))))
                self._fade_list.append(f)
            self._fade_w = width
        return self._fade_list

    def _build_credits(self, width):
        k = max(0.75, min(1.4, self.game.window.get_height() / 720))
        fs = max(12, int(15 * k))
        ops, y = [], 6
        for kind, text in self.credits:
            if kind == "section":
                y += 14
                ops.append((txt(text, int(fs * 1.35), GOLD, True), 0, y))
                y += int(fs * 1.35) + 8
            elif kind == "name":
                y += 8
                ops.append((txt(text, int(fs * 1.15), ui.CREAM, True), 0, y))
                y += int(fs * 1.15) + 4
            else:
                color = {"quote": (170, 160, 170), "label": (214, 202, 204)}.get(kind, (200, 190, 196))
                indent = 12 if kind == "label" else 0
                for line in wrap(text, fs, False, width - indent):
                    ops.append((txt(line, fs, color), indent, y))
                    y += fs + 3
        surf = pygame.Surface((width, y + 40), pygame.SRCALPHA)
        for s, x, yy in ops:
            surf.blit(s, (x, yy))
        return surf

    def on_action(self, action, data=None):
        n = len(P.AUTHOR_LINKS)
        if action == Action.UP:
            self.sel = (self.sel - 1) % n
            return True
        if action == Action.DOWN:
            self.sel = (self.sel + 1) % n
            return True
        if action == Action.CONFIRM:
            webbrowser.open(P.AUTHOR_LINKS[self.sel][1])
            return True
        if action == Action.SCROLL:
            self.scroll = max(0.0, self.scroll - data * 60)
            self.pause = 3.0
            return True
        if action == Action.DRAG:
            self.scroll = max(0.0, self.scroll - data)
            self.pause = 3.0
            return True
        if action == Action.CLICK:
            for name, rect in self.rects.items():
                if name.startswith("link:") and rect.collidepoint(data):
                    i = int(name[5:])
                    self.sel = i
                    webbrowser.open(P.AUTHOR_LINKS[i][1])
                    return True
        return False

    def hint(self):
        return "UP / DOWN choose a link   ENTER open   wheel / drag scrolls the credits   ESC back"

    def update(self, dt):
        if self.pause > 0:
            self.pause -= dt
        else:
            self.scroll += 30 * dt

    def draw_body(self, surf, body, t):
        dt = 1 / 60
        left = pygame.Rect(body.x, body.y, int(body.w * 0.40), body.h)
        right = pygame.Rect(left.right + 18, body.y, body.w - left.w - 18, body.h)

        # ----- hero card -----
        panel(surf, left, (36, 24, 34), (100, 62, 64), 2, 16)
        cx = left.centerx
        ay = left.y + int(left.h * 0.19)
        rad = int(min(left.w, left.h) * 0.14)
        for i in range(3):
            fx.glow(surf, (cx, ay), (CORAL, GOLD, (255, 224, 151))[i], rad * (2.4 - i * 0.5), 0.3 + 0.1 * math.sin(t * 2 + i), left)
        pygame.draw.circle(surf, ui.INK, (cx, ay), rad + 4)
        if self.avatar is not None:
            img = pygame.transform.smoothscale(self.avatar, (rad * 2, rad * 2))
            surf.blit(img, img.get_rect(center=(cx, ay)))
        fx.wave_text(surf, P.AUTHOR_NAME, (cx, ay + rad + 26), max(26, int(left.h * 0.085)), ui.CREAM, GOLD, t, amp=3, center=True)
        s = txt(P.AUTHOR_FULL_NAME, max(13, int(left.h * 0.034)), (220, 206, 204))
        surf.blit(s, s.get_rect(center=(cx, ay + rad + 26 + int(left.h * 0.075))))
        s = txt(P.AUTHOR_BLURB, max(11, int(left.h * 0.028)), (170, 160, 166))
        surf.blit(s, s.get_rect(center=(cx, ay + rad + 26 + int(left.h * 0.075) + int(left.h * 0.05))))
        tag(surf, (cx, left.y + int(left.h * 0.575)), f"PIXEL ABYSS  v{VERSION}", GOLD, max(11, int(left.h * 0.03)), "midtop")

        ph = max(30, int(left.h * 0.075))
        y = left.y + int(left.h * 0.66)
        for i, (label, _) in enumerate(P.AUTHOR_LINKS):
            r = pygame.Rect(0, 0, int(left.w * 0.78), ph)
            r.midtop = (cx, y)
            self.rects[f"link:{i}"] = r
            hv = max(self.pill_ease(f"link:{i}", dt), 0.8 if i == self.sel else 0.0)
            pill(surf, r, label, i == self.sel, hv, GOLD)
            y += ph + 8

        # ----- credits roll -----
        panel(surf, right, (30, 21, 31), (100, 62, 64), 2, 16)
        surf.blit(txt("CREDITS", max(14, int(right.h * 0.045)), GOLD, True), (right.x + 20, right.y + 12))
        area = pygame.Rect(right.x + 20, right.y + int(right.h * 0.09), right.w - 40, right.h - int(right.h * 0.09) - 14)
        if self._credit_surf is None or self._credit_w != area.w:
            self._credit_surf, self._credit_w = self._build_credits(area.w), area.w
        h = self._credit_surf.get_height()
        span = h + area.h
        pos = self.scroll % span                 # loops: the roll starts again from below
        old = _clip(surf, area)
        surf.blit(self._credit_surf, (area.x, area.bottom - int(pos)))
        surf.set_clip(old)
        for i, fade in enumerate(self._fades(area.w)):   # fade the top and bottom edges into the panel
            surf.blit(fade, (area.x, area.y + i * 2))
            surf.blit(fade, (area.x, area.bottom - 2 - i * 2))


# ====================================================================== #
# ENTITY
# ====================================================================== #
class EntityWindow(KitWindow):
    title = "ENTITY INFO"
    width_frac, height_frac = 0.78, 0.78

    def __init__(self, game, entity):
        super().__init__(game)
        self.entity = entity
        self.message = ""
        self.message_t = 0.0

    def _story(self):
        from ..scripts import charm_mode
        return charm_mode.available(self.game)

    def _is_friend(self):
        return self.entity in self.game.player.friends

    def toggle_friend(self):
        from ..scripts import charm_mode
        player, ent = self.game.player, self.entity
        if self._is_friend():
            charm_mode.unfriend(player, ent)
            self.message = f"{ent.name} is no longer your friend."
        elif self._story():
            self.message = "In the story, use a charm in the game (heart button / charm key)."
        else:
            charm_mode.befriend(player, ent, announce=False)
            self.message = f"{ent.name} is now your friend."
        self.message_t = 3.0

    def on_action(self, action, data=None):
        if action == Action.CONFIRM:
            self.toggle_friend()
            return True
        if action == Action.CLICK and "friend" in self.rects and self.rects["friend"].collidepoint(data):
            self.toggle_friend()
            return True
        return False

    def update(self, dt):
        self.message_t = max(0.0, self.message_t - dt)

    def hint(self):
        return "ENTER friend / unfriend   ESC back"

    def draw_body(self, surf, body, t):
        dt = 1 / 60
        e = self.entity
        left = pygame.Rect(body.x, body.y, int(body.w * 0.34), body.h)
        right = pygame.Rect(left.right + 18, body.y, body.w - left.w - 18, body.h)
        panel(surf, left, (36, 24, 34), (100, 62, 64), 2, 16)
        h = int(left.h * 0.5)
        fr = frame_at(sprite_frames(e.name, e.color, "idle_right", h), t)
        fx.glow(surf, (left.centerx, left.y + int(left.h * 0.36)), (255, 160, 110), int(left.w * 0.45), 0.35, left)
        if fr is not None:
            surf.blit(fr, fr.get_rect(midbottom=(left.centerx, left.y + int(left.h * 0.58) + int(3 * math.sin(t * 2)))))
        s = txt(e.name.upper(), max(22, int(left.h * 0.07)), ui.CREAM, True)
        surf.blit(s, s.get_rect(center=(left.centerx, left.y + int(left.h * 0.66))))
        s = txt(f"The {e.color} {e.name}", max(12, int(left.h * 0.035)), GOLD, True)
        surf.blit(s, s.get_rect(center=(left.centerx, left.y + int(left.h * 0.73))))
        tag(surf, (left.centerx, left.y + int(left.h * 0.82)), e.type.upper(), MINT if e.type == "player" else CORAL,
            max(11, int(left.h * 0.032)), "midtop")
        if getattr(e, "is_friend", False) or self._is_friend():
            tag(surf, (left.centerx, left.y + int(left.h * 0.90)), "FRIEND", (255, 130, 190), max(11, int(left.h * 0.032)), "midtop")

        panel(surf, right, (30, 21, 31), (100, 62, 64), 2, 16)
        bar_h = max(18, int(right.h * 0.06))
        y = right.y + 18
        ix = right.x + 22
        iw = right.w - 44
        mh = max(1, getattr(e, "max_health", e.health) or 1)
        for label, frac, color, value in (
                ("HEALTH", e.health / mh, MINT, f"{int(e.health)} / {int(mh)}"),
                ("ATTACK", min(1.0, getattr(e, "attack_power", 0) / 20.0), CORAL, f"{getattr(e, 'attack_power', 0):g}"),
                ("SPEED", min(1.0, getattr(e, "speed", 0) / 12.0), (120, 190, 255), f"{getattr(e, 'speed', 0):g}"),
                ("REACH", min(1.0, getattr(e, "attack_range", 0) / 600.0), GOLD, f"{int(getattr(e, 'attack_range', 0))} px")):
            stat_bar(surf, pygame.Rect(ix, y, iw, bar_h), max(0.0, min(1.0, frac)), color, label, value)
            y += bar_h + 10
        y += 6
        facts = [("Kills", str(getattr(e, "kills", 0))), ("Friends", str(len(e.friends))),
                 ("Entity id", str(getattr(e, "entity_id", "-"))), ("Colour", str(e.color))]
        colw = iw // 2
        fs = max(13, int(right.h * 0.04))
        for i, (lab, val) in enumerate(facts):
            cx = ix + (i % 2) * colw
            cy = y + (i // 2) * (fs * 2 + 10)
            surf.blit(txt(lab.upper(), max(10, fs - 3), (160, 150, 156), True), (cx, cy))
            surf.blit(txt(val, fs + 3, ui.CREAM, True), (cx, cy + fs - 1))
        y += 2 * (fs * 2 + 10) + 8

        # ----- befriend -----
        player = self.game.player
        friend = self._is_friend()
        story = self._story()
        btn = pygame.Rect(0, 0, int(iw * 0.55), max(34, int(right.h * 0.08)))
        btn.topleft = (ix, y)
        self.rects["friend"] = btn
        label = "UNFRIEND" if friend else ("BEFRIEND" if not story else "BEFRIEND (use a charm)")
        pill(surf, btn, label, friend, self.pill_ease("friend", dt), (255, 130, 190))
        cost = "Free here - no charm needed." if not story else f"Costs 1 charm - you carry {player.charms}."
        if friend:
            cost = "Friends fight for you and follow you."
        surf.blit(txt(cost, max(11, fs - 2), (190, 180, 186)), (btn.right + 14, btn.centery - fs // 2))
        if self.message_t > 0:
            s = txt(self.message, fs, GOLD, True)
            surf.blit(s, (ix, btn.bottom + 12))


# ====================================================================== #
# entry points
# ====================================================================== #
def open_mode(game):
    return ModeWindow(game).run()


def open_game_info(game):
    return GameInfoWindow(game).run()


def open_author(game):
    return AuthorWindow(game).run()


def open_entity(game, entity):
    return EntityWindow(game, entity).run()
