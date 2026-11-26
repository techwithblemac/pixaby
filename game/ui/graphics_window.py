"""
graphics_window.py
==================
Game Settings -> GRAPHICS, built on ui/window_kit.py like the Mode and Game Info windows.

    SCREEN       three cards: FULLSCREEN / 800 x 600 / 1280 x 960, each with a little monitor that shows
                 how big the window is on the desktop. The active one is tagged; one that does not fit this
                 desktop is dimmed and cannot be picked (scripts/screen_mode.py).
    ATMOSPHERE   three switches with a live mini preview each: LIGHTING, SHADOWS, FIREFLIES
                 (Settings.LIGHTING / SHADOWS / FIREFLIES, remembered by scripts/graphics_prefs.py).

Keyboard / gamepad: arrows move over the six cards (left / right along a row, up / down between rows),
ENTER / A picks, ESC / B goes back. Mouse and touch: click a card.
"""

import math

import pygame

from . import ui_fx as fx
from . import ui_theme as ui
from .window_kit import (Action, KitWindow, card_ease, draw_card, fit, frame_at, panel, pill, sprite_frames,
                         tag, txt, wrap)
from ..scripts import graphics_prefs, screen_mode
from ..settings import Settings

CORAL, GOLD, MINT = (255, 112, 92), (255, 202, 80), (108, 201, 117)

SWITCHES = (
    ("LIGHTING", "LIGHTING", "Darkness with torches, fire, lava and player lights."),
    ("SHADOWS", "SHADOWS", "Soft shadows under heroes, enemies and coins."),
    ("FIREFLIES", "FIREFLIES", "Glowing fireflies drifting through the level."),
)


class GraphicsWindow(KitWindow):
    title = "GRAPHICS"
    width_frac, height_frac = 0.88, 0.84

    def __init__(self, game):
        super().__init__(game)
        self.row, self.col = 0, 0
        for i, m in enumerate(screen_mode.MODES):
            if m == screen_mode.current():
                self.col = i
        self.flash = {}                 # card key -> 1..0 flash after a change
        self.notice = ""
        self.notice_t = 0.0

    # ----- state -----
    def _mode_at(self, col):
        return screen_mode.MODES[col]

    def _activate(self, row, col):
        if row == 0:
            mode = self._mode_at(col)
            if not screen_mode.available(mode):
                self._say("That size does not fit this desktop.")
                return
            if screen_mode.apply(self.game, mode):
                self.flash[("m", col)] = 1.0
                self._say(f"Screen: {screen_mode.LABELS[mode]}")
        else:
            key = SWITCHES[col][0]
            setattr(Settings, key, not getattr(Settings, key, False))
            graphics_prefs.save()
            self.flash[("s", col)] = 1.0
            self._say(f"{SWITCHES[col][1].title()}: {'ON' if getattr(Settings, key) else 'OFF'}")

    def _say(self, text):
        self.notice, self.notice_t = text, 2.2

    # ----- input -----
    def on_action(self, action, data=None):
        if action == Action.LEFT:
            self.col = (self.col - 1) % 3
            return True
        if action == Action.RIGHT:
            self.col = (self.col + 1) % 3
            return True
        if action in (Action.UP, Action.DOWN, Action.PREV, Action.NEXT):
            self.row = 1 - self.row
            return True
        if action == Action.CONFIRM:
            self._activate(self.row, self.col)
            return True
        if action == Action.CLICK:
            for name, rect in self.rects.items():
                if name.startswith("card:") and rect.collidepoint(data):
                    _, r, c = name.split(":")
                    self.row, self.col = int(r), int(c)
                    self._activate(self.row, self.col)
                    return True
        return False

    def update(self, dt):
        for k in list(self.flash):
            self.flash[k] = max(0.0, self.flash[k] - dt * 2.5)
        self.notice_t = max(0.0, self.notice_t - dt)

    def hint(self):
        return "ARROWS move   ENTER or click to switch   ESC back"

    # ----- drawing -----
    def draw_body(self, surf, body, t):
        dt = 1 / 60
        label_h = max(16, int(body.h * 0.065))
        gap = max(10, int(body.w * 0.02))
        rows_h = body.h - label_h * 2 - int(body.h * 0.07)
        card_h = rows_h // 2
        card_w = (body.w - gap * 2) // 3
        y = body.y
        for row, (heading, sub) in enumerate((
                ("SCREEN", "How the game sits on your desktop"),
                ("ATMOSPHERE", "Lighting, shadows and fireflies"))):
            surf.blit(txt(heading, label_h, GOLD, True), (body.x + 4, y))
            hs = txt(sub, max(10, int(label_h * 0.62)), (170, 160, 168))
            surf.blit(hs, (body.right - hs.get_width() - 4, y + label_h - hs.get_height() - 2))
            y += label_h + 2
            for col in range(3):
                r = pygame.Rect(body.x + col * (card_w + gap), y, card_w, card_h - 6)
                self._card(surf, r, row, col, dt, t)
            y += card_h + int(body.h * 0.035)
        if self.notice_t > 0:
            s = txt(self.notice, max(12, int(body.h * 0.05)), MINT, True)
            surf.blit(s, (body.centerx - s.get_width() // 2, body.bottom - s.get_height() + 2))

    def _card(self, surf, r, row, col, dt, t):
        name = f"card:{row}:{col}"
        self.rects[name] = r
        focus = (row, col) == (self.row, self.col)
        if row == 0:
            mode = self._mode_at(col)
            ok = screen_mode.available(mode)
            on = ok and mode == screen_mode.current()
            title = screen_mode.LABELS[mode]
            key = ("m", col)
        else:
            skey, title, _ = SWITCHES[col]
            ok, on = True, bool(getattr(Settings, skey, False))
            key = ("s", col)
        e = card_ease(self.ease, key, (focus or r.collidepoint(self.hover_pos)) and ok, dt)
        accent = MINT if on else CORAL
        cr = draw_card(surf, r, e * 0.7, accent, selected=focus, fill=(36, 24, 34) if ok else (26, 20, 26))
        inner = cr.inflate(-int(r.w * 0.1), -int(r.h * 0.1))
        ts = max(13, int(r.h * 0.13))
        surf.blit(txt(title, ts, ui.CREAM if ok else (130, 122, 130), True), (inner.x, inner.y))
        if row == 0:
            if on:
                tag(surf, (inner.right, inner.y + 2), "ACTIVE", MINT, max(10, int(r.h * 0.07)), "topright")
            elif not ok:
                tag(surf, (inner.right, inner.y + 2), "TOO BIG", (150, 110, 110), max(10, int(r.h * 0.07)), "topright")
        else:
            self._switch(surf, pygame.Rect(0, 0, int(r.h * 0.34), int(r.h * 0.16)), inner, on, key)
        scene = pygame.Rect(inner.x, inner.y + ts + 8, inner.w, int(inner.h * 0.5))
        pygame.draw.rect(surf, (18, 13, 22), scene, border_radius=10)
        old = surf.get_clip()
        surf.set_clip(old.clip(scene))
        if row == 0:
            self._monitor(surf, scene, mode, ok, on, t)
        else:
            [self._lighting, self._shadows, self._fireflies][col](surf, scene, on, t)
        surf.set_clip(old)
        fs = max(10, int(r.h * 0.075))
        if row == 0:
            w, h = screen_mode.desktop_size() if mode == screen_mode.FULLSCREEN else screen_mode.SIZES[mode]
            line = f"{w} x {h}" + ("  desktop size" if mode == screen_mode.FULLSCREEN else "")
            lines = [line]
        else:
            lines = wrap(SWITCHES[col][2], fs, False, inner.w)[:2]
        yy = scene.bottom + 6
        for ln in lines:
            s = txt(ln, fs, (200, 190, 196) if ok else (120, 112, 120))
            surf.blit(s, (inner.x, yy))
            yy += s.get_height() + 1
        f = self.flash.get(key, 0.0)
        if f > 0:
            fx.glow(surf, r.center, MINT, int(r.w * 0.5), 0.45 * f, r)

    def _switch(self, surf, sw, inner, on, key):
        """A sliding ON / OFF switch in the top-right of a card."""
        sw.topright = (inner.right, inner.y)
        pygame.draw.rect(surf, MINT if on else (84, 66, 80), sw, border_radius=sw.h // 2)
        k = sw.h - 6
        x = sw.right - k - 3 if on else sw.x + 3
        pygame.draw.circle(surf, ui.CREAM, (x + k // 2, sw.centery), k // 2)

    # ----- previews -----
    def _monitor(self, surf, scene, mode, ok, on, t):
        """A desktop with the window drawn at its real share of it."""
        dw, dh = screen_mode.desktop_size()
        mh = int(scene.h * 0.8)
        mon = pygame.Rect(0, 0, int(mh * dw / dh), mh)
        mon.center = (scene.centerx, scene.centery - 2)
        if mon.w > scene.w - 8:
            mon.w = scene.w - 8
            mon.h = int(mon.w * dh / dw)
            mon.center = (scene.centerx, scene.centery - 2)
        pygame.draw.rect(surf, (60, 46, 62), mon, border_radius=5)
        screen = mon.inflate(-6, -6)
        pygame.draw.rect(surf, (30, 22, 40), screen, border_radius=3)
        if mode == screen_mode.FULLSCREEN:
            win = screen
        else:
            ww, wh = screen_mode.SIZES[mode]
            win = pygame.Rect(0, 0, min(screen.w, int(screen.w * ww / dw)), min(screen.h, int(screen.h * wh / dh)))
            win.center = screen.center
        col = MINT if on else (CORAL if ok else (110, 90, 100))
        pygame.draw.rect(surf, (52, 34, 48), win, border_radius=2)
        pygame.draw.rect(surf, col, win, 2, border_radius=2)
        if ok:
            pygame.draw.rect(surf, col, (win.x, win.y, win.w, max(3, win.h // 8)))
            # a tiny hero so the window looks alive
            fr = frame_at(sprite_frames("Warrior", "Blue", "idle_right", max(10, int(win.h * 0.5))), t)
            if fr is not None:
                surf.blit(fr, fr.get_rect(midbottom=(win.centerx, win.bottom - 3)))
        stand = pygame.Rect(0, 0, max(10, mon.w // 4), 4)
        stand.midtop = (mon.centerx, mon.bottom)
        pygame.draw.rect(surf, (60, 46, 62), stand, border_radius=2)

    def _scene_floor(self, surf, scene):
        pygame.draw.rect(surf, (50, 38, 52), (scene.x, scene.bottom - int(scene.h * 0.22), scene.w, int(scene.h * 0.22)))
        return scene.bottom - int(scene.h * 0.22)

    def _hero(self, surf, scene, floor, t, x=None, name="Warrior", color="Blue"):
        fr = frame_at(sprite_frames(name, color, "idle_right", max(12, int(scene.h * 0.5))), t)
        if fr is not None:
            surf.blit(fr, fr.get_rect(midbottom=(x if x is not None else scene.centerx, floor + 4)))
        return fr

    def _lighting(self, surf, scene, on, t):
        floor = self._scene_floor(surf, scene)
        self._hero(surf, scene, floor, t)
        if on:
            lm = pygame.Surface(scene.size)
            lm.fill((78, 70, 104))
            flick = 1.0 + 0.06 * math.sin(t * 11) + 0.04 * math.sin(t * 23)
            for cx, cy, c, rr in ((scene.w * 0.5, scene.h * 0.55, (255, 190, 120), scene.h * 0.95),
                                  (scene.w * 0.18, scene.h * 0.35, (255, 130, 70), scene.h * 0.6 * flick)):
                spot = pygame.Surface((int(rr * 2), int(rr * 2)))
                for i in range(12):
                    f = ((i + 1) / 12) ** 2
                    pygame.draw.circle(spot, tuple(int(v * f * 0.8) for v in c), (int(rr), int(rr)), int(rr * (1 - i / 12)))
                lm.blit(spot, (int(cx - rr), int(cy - rr)), special_flags=pygame.BLEND_RGB_ADD)
            sub = surf.subsurface(scene)
            sub.blit(lm, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            pygame.draw.circle(surf, (255, 200, 120), (scene.x + int(scene.w * 0.18), scene.y + int(scene.h * 0.35)), 3)

    def _shadows(self, surf, scene, on, t):
        floor = self._scene_floor(surf, scene)
        x = scene.centerx + int(math.sin(t * 1.4) * scene.w * 0.25)
        if on:
            sh = pygame.Surface((int(scene.h * 0.6), int(scene.h * 0.14)), pygame.SRCALPHA)
            for i in range(5):
                pygame.draw.ellipse(sh, (0, 0, 0, 38), sh.get_rect().inflate(-i * 6, -i * 2))
            surf.blit(sh, sh.get_rect(center=(x, floor + 3)))
        self._hero(surf, scene, floor, t, x)

    def _fireflies(self, surf, scene, on, t):
        floor = self._scene_floor(surf, scene)
        self._hero(surf, scene, floor, t)
        if not on:
            return
        for i in range(9):
            a = i * 1.7
            x = scene.x + scene.w * (0.5 + 0.42 * math.sin(t * 0.5 + a))
            y = scene.y + scene.h * (0.42 + 0.3 * math.sin(t * 0.7 + a * 1.3))
            b = 0.5 + 0.5 * math.sin(t * 2.5 + a * 2)
            fx.glow(surf, (x, y), (200, 255, 120), int(scene.h * 0.28), 0.5 * b, scene)
            pygame.draw.circle(surf, (235, 255, 170), (int(x), int(y)), 2)


def open_graphics(game):
    return GraphicsWindow(game).run()
