import pygame
"""
ui_theme.py
===========
The "Pixel Abyss" visual language - palette + drawing helpers - lifted
from LevelSelector (game/level_select.py) so every other screen in the
game (loading screen, level editor overlays, multiplayer lobby) shares
the exact same look instead of each one inventing its own colours.

Also home to a handful of small, reusable, self-contained modal helpers:
    - confirm_dialog()      a blocking Yes/No prompt
    - show_help_overlay()   a blocking "how to" panel (keys/mouse/etc.)
    - processing_overlay()  a blocking "please wait" screen tied to a
                             condition (e.g. "while not game.env_ready")

Each of these runs its own tiny event loop and returns control to the
caller once dismissed - the same pattern already used throughout
windows.py for things like the exit confirmation screen.
"""

import math
import pygame

from ..scripts import paths

# ---------------------------------------------------------------------- #
# Palette (sampled from LevelSelector - keep these two in sync)
# ---------------------------------------------------------------------- #
INK    = (18, 17, 25)
INK2   = (34, 23, 34)
MAROON = (79, 38, 49)
RED    = (224, 78, 74)
CORAL  = (255, 112, 92)
CREAM  = (255, 224, 151)
WHITE  = (255, 242, 207)
MUTED  = (177, 139, 128)
GREEN  = (108, 201, 117)
BLUE   = (100, 170, 215)
PURPLE = (171, 105, 164)
GOLD   = (255, 202, 80)

_fonts = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        _fonts[key] = pygame.font.SysFont("serif", max(10, int(size)), bold=bold)
    return _fonts[key]


def text(screen, txt, pos, size, color=None, bold=False, max_width=None):
    f = font(size, bold)
    txt = str(txt)
    if max_width:
        while len(txt) > 1 and f.size(txt)[0] > max_width:
            txt = txt[:-1]
        if txt != str(txt):
            txt += "…"
    surf = f.render(txt, True, color or WHITE)
    screen.blit(surf, (int(pos[0]), int(pos[1])))
    return surf


def text_centered(screen, txt, center, size, color=None, bold=False):
    f = font(size, bold)
    surf = f.render(str(txt), True, color or WHITE)
    screen.blit(surf, surf.get_rect(center=center))
    return surf


def panel(screen, rect, fill, border=None, width=1, radius=12):
    surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(surf, fill, (0, 0, rect.width, rect.height), border_radius=radius)
    if border:
        pygame.draw.rect(surf, border, (0, 0, rect.width, rect.height), width=width, border_radius=radius)
    screen.blit(surf, rect.topleft)


def button(screen, rect, label, selected=False, accent=None, small=False):
    accent = accent or CORAL
    hover = rect.collidepoint(pygame.mouse.get_pos())
    active = selected or hover
    fill = (83, 37, 47) if active else (48, 27, 36)
    panel(screen, rect, fill, accent if active else (112, 64, 66), 2 if active else 1, 9)
    f = font(12 if small else 15, True)
    s = f.render(label, True, CREAM if active else WHITE)
    screen.blit(s, s.get_rect(center=rect.center))
    return hover


def wrap(txt, width, f):
    lines, line = [], ""
    for word in str(txt).split():
        test = word if not line else line + " " + word
        if f.size(test)[0] <= width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


_DIM_CACHE = {}


def dim_overlay(screen, alpha=175, color=INK):
    w, h = screen.get_size()
    # the overlay only depends on (size, colour, alpha): reuse it instead of allocating and
    # filling a new full-window surface on every call (a few are kept; fades just rotate them)
    key = (w, h, tuple(color), alpha)
    surf = _DIM_CACHE.get(key)
    if surf is None:
        if len(_DIM_CACHE) >= 4:
            _DIM_CACHE.pop(next(iter(_DIM_CACHE)))
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill((*color, alpha))
        _DIM_CACHE[key] = surf
    screen.blit(surf, (0, 0))


def spinner(screen, center, radius=16, t=0.0, color=None, dots=8):
    """A small ring of fading dots, rotating - used by the processing/
    loading screens instead of a fake progress bar (we usually don't
    have a real progress percentage to show)."""
    color = color or CORAL
    for i in range(dots):
        angle = t * 3.2 + (i / dots) * math.tau
        fade = (i / dots)
        r = int(3 + fade * 3)
        x = center[0] + math.cos(angle) * radius
        y = center[1] + math.sin(angle) * radius
        alpha = int(60 + fade * 195)
        dot_surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(dot_surf, (*color, alpha), (r, r), r)
        screen.blit(dot_surf, (x - r, y - r))


# ---------------------------------------------------------------------- #
# Blocking modal helpers
# ---------------------------------------------------------------------- #

def _bg_snapshot(game):
    """Grab whatever is already on screen so overlays can dim *over* the
    current scene instead of blanking it - keeps continuity with
    whatever screen the modal was opened from."""
    snap = game.window.copy().convert()
    return snap


def confirm_dialog(game, title, message, yes_label="YES", no_label="NO", accent=None):
    """Blocking Yes/No prompt. Returns True (yes) / False (no)."""
    accent = accent or CORAL
    snapshot = _bg_snapshot(game)
    clock = game.clock
    w, h = game.window.get_size()

    box_w, box_h = min(520, int(w * 0.8)), 220
    box = pygame.Rect(0, 0, box_w, box_h)
    box.center = (w // 2, h // 2)

    yes_rect = pygame.Rect(0, 0, box_w * 0.42, 46)
    no_rect = pygame.Rect(0, 0, box_w * 0.42, 46)
    yes_rect.bottomleft = (box.left + 24, box.bottom - 24)
    no_rect.bottomright = (box.right - 24, box.bottom - 24)

    result = None
    while result is None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                result = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_y, pygame.K_RETURN, pygame.K_KP_ENTER):
                    result = True
                elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                    result = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if yes_rect.collidepoint(event.pos):
                    result = True
                elif no_rect.collidepoint(event.pos):
                    result = False

        game.window.blit(snapshot, (0, 0))
        dim_overlay(game.window, 165)

        panel(game.window, box, (37, 23, 31), accent, 2, 14)
        text(game.window, title, (box.left + 24, box.top + 20), 20, CREAM, True)

        y = box.top + 56
        for line in wrap(message, box_w - 48, font(14)):
            text(game.window, line, (box.left + 24, y), 14, WHITE)
            y += 20

        button(game.window, yes_rect, yes_label, accent=GREEN, small=True)
        button(game.window, no_rect, no_label, accent=MUTED, small=True)

        pygame.display.flip()
        clock.tick(getattr(game, "FPS", 60))

    return bool(result)


def show_help_overlay(game, title, sections, hint="ESC / click outside to close"):
    """Blocking 'how to' panel. `sections` is a list of
    (heading, [line, line, ...]) tuples."""
    snapshot = _bg_snapshot(game)
    clock = game.clock
    w, h = game.window.get_size()

    box_w = min(720, int(w * 0.86))
    box_h = min(int(h * 0.86), 560)
    box = pygame.Rect(0, 0, box_w, box_h)
    box.center = (w // 2, h // 2)

    close_rect = pygame.Rect(0, 0, 30, 30)
    close_rect.topright = (box.right - 14, box.top + 14)
    scroll = 0

    open_ = True
    while open_:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                open_ = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                open_ = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_DOWN, pygame.K_PAGEDOWN):
                    scroll += 3 if event.key == pygame.K_PAGEDOWN else 1
                elif event.key in (pygame.K_UP, pygame.K_PAGEUP):
                    scroll = max(0, scroll - (3 if event.key == pygame.K_PAGEUP else 1))
            elif event.type == pygame.MOUSEWHEEL and box.collidepoint(pygame.mouse.get_pos()):
                scroll = max(0, scroll - event.y)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if close_rect.collidepoint(event.pos) or not box.collidepoint(event.pos):
                    open_ = False

        game.window.blit(snapshot, (0, 0))
        dim_overlay(game.window, 180)

        panel(game.window, box, (30, 19, 26), CORAL, 2, 16)
        text(game.window, title, (box.left + 26, box.top + 20), 24, CREAM, True)
        pygame.draw.line(game.window, (92, 50, 57), (box.left + 24, box.top + 56),
                          (box.right - 24, box.top + 56), 1)

        button(game.window, close_rect, "X", accent=CORAL, small=True)

        col_w = box_w - 52
        rows = []
        for heading, lines in sections:
            rows.append((heading, GOLD, True))
            for line in lines:
                for wrapped in wrap(line, col_w, font(13)):
                    rows.append((wrapped, WHITE, False))
            rows.append(("", WHITE, False))

        content_top = box.top + 72
        content_bottom = box.bottom - 42
        line_h = 19
        max_scroll = max(0, len(rows) - max(1, (content_bottom - content_top) // line_h))
        scroll = min(scroll, max_scroll)
        clip = game.window.get_clip()
        game.window.set_clip(pygame.Rect(box.left + 20, content_top, box.width - 40,
                                         content_bottom - content_top))
        y = content_top - scroll * line_h
        for value, color, bold in rows:
            if value:
                text(game.window, value, (box.left + 26, y), 13, color, bold)
            y += line_h
        game.window.set_clip(clip)
        if max_scroll:
            track = pygame.Rect(box.right - 15, content_top, 5, content_bottom - content_top)
            pygame.draw.rect(game.window, (72, 40, 50), track, border_radius=3)
            thumb_h = max(28, int(track.height * track.height / (len(rows) * line_h)))
            thumb_y = track.y + int((track.height - thumb_h) * scroll / max_scroll)
            pygame.draw.rect(game.window, CORAL, pygame.Rect(track.x, thumb_y, track.width, thumb_h),
                             border_radius=3)

        text(game.window, f"{hint}  |  ↑↓ / PgUp PgDn / wheel",
             (box.left + 26, box.bottom - 26), 10, MUTED)

        pygame.display.flip()
        clock.tick(getattr(game, "FPS", 60))


def processing_overlay(game, condition_fn, message="APPLYING CHANGES...", subtext=None):
    """Blocking 'please wait' screen. Keeps looping - drawing a small
    spinner over a dimmed snapshot of the current scene - until
    condition_fn() returns True (e.g. `lambda: game.env_ready`)."""
    snapshot = _bg_snapshot(game)
    clock = game.clock
    w, h = game.window.get_size()
    t = 0.0

    while not condition_fn():
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return

        game.window.blit(snapshot, (0, 0))
        dim_overlay(game.window, 195)

        center = (w // 2, h // 2 - 20)
        spinner(game.window, center, 20, t, CORAL)

        text_centered(game.window, message, (w // 2, h // 2 + 30), 20, CREAM, True)
        if subtext:
            text_centered(game.window, subtext, (w // 2, h // 2 + 58), 12, MUTED)

        pygame.display.flip()
        dt = clock.tick(getattr(game, "FPS", 60)) / 1000.0
        t += dt


# ---------------------------------------------------------------------- #
# Rotating "loading tip" ticker
# ---------------------------------------------------------------------- #

class TipTicker:
    """Cycles through a shuffled list of tip strings every `interval`
    seconds, with a short crossfade between them."""

    def __init__(self, tips, interval=3.8, fade=0.35):
        import random
        self.tips = list(tips)
        random.shuffle(self.tips)
        self.interval = interval
        self.fade = fade
        self.index = 0
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        if self.t >= self.interval:
            self.t = 0.0
            self.index = (self.index + 1) % len(self.tips)

    @property
    def current(self):
        return self.tips[self.index]

    @property
    def alpha(self):
        if self.t < self.fade:
            return self.t / self.fade
        if self.t > self.interval - self.fade:
            return max(0.0, (self.interval - self.t) / self.fade)
        return 1.0

    def draw(self, screen, pos, size, color=None, bold=False, max_width=None, center=False):
        f = font(size, bold)
        surf = f.render(str(self.current), True, color or WHITE)
        if max_width:
            surf = _fit_surface(self.current, f, max_width, color or WHITE)
        surf = surf.copy()
        surf.set_alpha(int(self.alpha * 255))
        rect = surf.get_rect(center=pos) if center else surf.get_rect(topleft=pos)
        screen.blit(surf, rect)


def _fit_surface(txt, f, max_width, color):
    lines = wrap(txt, max_width, f)
    line = lines[0] if lines else txt
    return f.render(line, True, color)

class UITheme:
    # Color Palette - Abyssal Theme
    BG_COLOR = (24, 20, 37)        
    PANEL_COLOR = (42, 38, 59)     
    ACCENT_COLOR = (251, 145, 10)  
    TEXT_MAIN = (240, 240, 245)    
    TEXT_MUTED = (140, 135, 160)   
    BORDER_COLOR = (75, 68, 102)   
    SUCCESS_COLOR = (50, 230, 100)
    
    _font_cache = {}

    @classmethod
    def get_font(cls, size):
        if size not in cls._font_cache:
            try:
                # Assuming the asset exists in the user's project
                cls._font_cache[size] = pygame.font.Font(paths.asset("fonts", "pixel_font.ttf"), size)
            except:
                cls._font_cache[size] = pygame.font.SysFont("Courier", size, bold=True)
        return cls._font_cache[size]

    @classmethod
    def draw_panel(cls, surface, rect, border_radius=4, alpha=230):
        """Standardized UI panel with subtle transparency."""
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, (*cls.PANEL_COLOR, alpha), (0, 0, *rect.size), border_radius=border_radius)
        pygame.draw.rect(s, cls.BORDER_COLOR, (0, 0, *rect.size), width=2, border_radius=border_radius)
        surface.blit(s, rect.topleft)

    @classmethod
    def draw_text(cls, surface, text, pos, size=18, color=None, center=False):
        if color is None: color = cls.TEXT_MAIN
        font = cls.get_font(size)
        text_surf = font.render(str(text), True, color)
        rect = text_surf.get_rect(topleft=pos)
        if center:
            rect.center = pos
        surface.blit(text_surf, rect)
