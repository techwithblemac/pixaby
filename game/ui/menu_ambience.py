"""
menu_ambience.py
================
Makes every menu screen feel alive without touching its layout:

    - the background image slowly drifts (cheap Ken-Burns pan, 1 blit)
    - soft god-ray light shafts sway in from the top
    - embers / fireflies float upward and blink
    - a breathing vignette frames the screen
    - each new screen fades in from the abyss (driven by RPGMenu.age())

Usage (see Windows.draw_menu_bg):

    menu_ambience.get(game).draw(window, game.menu_bg, menu)

Everything is cached per window size, so a frame costs one big blit for the
background, ~3 additive blits for the rays, one per mote and one vignette.
"""

import math
import random

import pygame

from ..settings import Settings
from . import ui_theme as ui

LOW = bool(getattr(Settings, "LOW_SPEC_MODE", False))
MOTES = 26 if LOW else 60
RAYS = 2 if LOW else 4


def _glow_sprite(color, radius, _cache={}):
    key = (color, radius)
    img = _cache.get(key)
    if img is None:
        img = pygame.Surface((radius * 2, radius * 2))
        img.fill((0, 0, 0))
        steps = max(4, min(radius, 18))
        for i in range(steps):
            t = i / steps
            f = t * t
            pygame.draw.circle(img, tuple(int(c * f) for c in color), (radius, radius),
                               max(1, int(radius * (1 - t))))
        _cache[key] = img
        if len(_cache) > 200:
            _cache.clear()
    return img


class Mote:
    __slots__ = ("x", "y", "vy", "sway", "phase", "size", "color", "blink")

    def __init__(self, w, h, anywhere=True):
        self.reset(w, h, anywhere)

    def reset(self, w, h, anywhere=False):
        self.x = random.uniform(0, w)
        self.y = random.uniform(0, h) if anywhere else h + random.uniform(4, 40)
        self.vy = random.uniform(10, 34)
        self.sway = random.uniform(8, 26)
        self.phase = random.uniform(0, math.tau)
        self.size = random.choice((2, 2, 3, 3, 4))
        self.blink = random.uniform(0.6, 1.6)
        self.color = random.choice((ui.GOLD, ui.CORAL, ui.CREAM, (205, 255, 120), (255, 160, 90)))


class MenuAmbience:
    def __init__(self):
        self.t = 0.0
        self._last = pygame.time.get_ticks()
        self.motes = []
        self._size = None
        self._bg_src = None
        self._bg_big = None
        self._rays = []
        self._vignette = None

    # ---------------------------------------------------------------- #
    def _rebuild(self, size, bg):
        w, h = size
        self._size = size
        self.motes = [Mote(w, h, True) for _ in range(MOTES)]

        # rays: tall soft wedges, pre-rendered once on black (for additive blits)
        self._rays = []
        for i in range(RAYS):
            rw = int(w * random.uniform(0.10, 0.18))
            surf = pygame.Surface((rw * 3, h))
            surf.fill((0, 0, 0))
            col = random.choice((ui.CREAM, ui.GOLD, (255, 190, 150)))
            steps = 14
            for s in range(steps):
                k = 1 - s / steps
                inten = 0.05 * (s + 1) / steps
                c = tuple(int(ch * inten) for ch in col)
                top_w = rw * 0.35 * k
                bot_w = rw * 1.4 * k
                cx = rw * 1.5
                pygame.draw.polygon(surf, c, [(cx - top_w, 0), (cx + top_w, 0),
                                              (cx + bot_w + rw * 0.5, h), (cx - bot_w + rw * 0.5, h)])
            # fade the bottom so the ray dissolves into the scene
            fade = pygame.Surface((rw * 3, h))
            for y in range(0, h, 4):
                v = int(255 * max(0.0, 1 - y / (h * 0.9)) ** 1.4)
                fade.fill((v, v, v), pygame.Rect(0, y, rw * 3, 4))
            surf.blit(fade, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            self._rays.append((surf, w * (0.15 + 0.7 * (i + random.random() * 0.6) / max(1, RAYS)),
                               random.uniform(0, math.tau), random.uniform(0.15, 0.3)))

        # vignette (alpha surface)
        small = pygame.Surface((96, 54), pygame.SRCALPHA)
        small.fill((*ui.INK, 210))
        for r in range(60, 0, -1):
            f = max(0.0, (r - 22) / 38.0)
            rect = pygame.Rect(0, 0, int(r * 2.2), int(r * 1.25))
            rect.center = (48, 27)
            pygame.draw.ellipse(small, (*ui.INK, int(210 * f)), rect)
        self._vignette = pygame.transform.smoothscale(small, size)
        self._bg_src = None

    def _background(self, window, bg):
        w, h = window.get_size()
        if bg is not self._bg_src or self._bg_big is None:
            self._bg_src = bg
            bw, bh = int(w * 1.06), int(h * 1.06)
            self._bg_big = pygame.transform.smoothscale(bg, (bw, bh)).convert()
        bw, bh = self._bg_big.get_size()
        mx, my = (bw - w) / 2, (bh - h) / 2
        x = -mx + math.sin(self.t * 0.07) * mx * 0.9
        y = -my + math.cos(self.t * 0.05) * my * 0.9
        window.blit(self._bg_big, (int(x), int(y)))

    # ---------------------------------------------------------------- #
    def draw(self, window, bg=None, menu=None):
        now = pygame.time.get_ticks()
        dt = min(0.1, (now - self._last) / 1000.0)
        self._last = now
        self.t += dt

        size = window.get_size()
        if size != self._size:
            self._rebuild(size, bg)
        w, h = size

        if bg is not None:
            self._background(window, bg)

        # god rays
        for surf, x0, ph, spd in self._rays:
            sway = math.sin(self.t * spd + ph) * w * 0.03
            window.blit(surf, (int(x0 + sway - surf.get_width() / 2), 0), special_flags=pygame.BLEND_RGB_ADD)

        # motes
        t = self.t
        for m in self.motes:
            m.y -= m.vy * dt
            x = m.x + math.sin(t * 0.8 + m.phase) * m.sway
            if m.y < -20:
                m.reset(w, h)
                continue
            b = 0.55 + 0.45 * math.sin(t * 2.0 * m.blink + m.phase)
            col = tuple(int(c * b) for c in m.color)
            gr = m.size * 4
            window.blit(_glow_sprite(tuple(int(c * 0.45) for c in col), gr),
                        (int(x) - gr, int(m.y) - gr), special_flags=pygame.BLEND_RGB_ADD)
            pygame.draw.circle(window, col, (int(x), int(m.y)), max(1, m.size // 2 + 1))

        # breathing vignette
        if self._vignette is not None:
            self._vignette.set_alpha(int(205 + 40 * math.sin(t * 0.9)))
            window.blit(self._vignette, (0, 0))

        # fade-in for freshly opened screens
        if menu is not None and hasattr(menu, "age"):
            age = menu.age()
            if age < 0.45:
                a = int(255 * (1 - age / 0.45) ** 2)
                cover = pygame.Surface(size)
                cover.fill(ui.INK)
                cover.set_alpha(a)
                window.blit(cover, (0, 0))


def get(game):
    amb = getattr(game, "_menu_ambience", None)
    if amb is None:
        amb = MenuAmbience()
        game._menu_ambience = amb
    return amb
