"""
window_kit.py
=============
The shared kit behind the Mode, Game Info, Author Info and Entity Info windows
(build it once, each window is then a small subclass).

    KitWindow        the loop: dimmed live background + drifting embers, an animated
                     frame, open / close animation, and ONE input mapping for keyboard,
                     gamepad, mouse and touch (touch arrives as SDL mouse events)
    draw_window_frame  shadow, panel, a light that travels round the border, wave-text title
    card_ease / draw_card  eased hover + selection (lift, glow) for cards
    pill / stat_bar / key_glyph / pad_glyph / tag   small cached-text widgets
    sprite_frames    recoloured, scaled animation frames of a character for previews

Subclass hooks::

    on_action(action, data)   Action.LEFT/RIGHT/UP/DOWN/CONFIRM/BACK/PREV/NEXT,
                              Action.CLICK (pos), Action.SCROLL (dy), Action.DRAG (dy)
    update(dt)                animate
    draw_body(surf, body, t)  draw inside the frame (``surf`` is the window, or a scratch
                              buffer while the open / close animation scales it)
    hint()                    the line at the bottom

Everything runs on REAL time, uses ``ui_theme.font`` only (no system-font lookups) and plays
``menu._ui_tick`` on every navigation step. The pattern of the old windows is kept:
``run()`` owns its own ``while`` loop and ``pygame.display.flip()``.
"""

import math
import time

import pygame

from . import ui_fx as fx
from . import ui_theme as ui
from ..scripts.menu import _ui_tick

BORDER = (255, 112, 92)
BORDER_2 = (255, 202, 80)
PANEL = (24, 17, 29)
OPEN_TIME = 0.30
CLOSE_TIME = 0.18


class Action:
    LEFT, RIGHT, UP, DOWN = "left", "right", "up", "down"
    CONFIRM, BACK, PREV, NEXT = "confirm", "back", "prev", "next"
    CLICK, SCROLL, DRAG = "click", "scroll", "drag"


# ---------------------------------------------------------------------- #
# text + sprite caches
# ---------------------------------------------------------------------- #
_texts = {}
_frames = {}


def txt(text, size, color=ui.CREAM, bold=False):
    """Cached rendered text (the same string every frame costs one dict lookup)."""
    key = (text, int(size), tuple(color[:3]), bold)
    s = _texts.get(key)
    if s is None:
        if len(_texts) > 700:
            _texts.clear()
        s = _texts[key] = ui.font(int(size), bold).render(text, True, color)
    return s


def fit(text, size, bold, width):
    f = ui.font(int(size), bold)
    if f.size(text)[0] <= width:
        return text
    while text and f.size(text + "...")[0] > width:
        text = text[:-1]
    return text.rstrip() + "..."


def wrap(text, size, bold, width):
    """Word-wrap to ``width`` px -> list of lines."""
    f = ui.font(int(size), bold)
    lines, line = [], ""
    for word in str(text).split():
        trial = (line + " " + word).strip()
        if f.size(trial)[0] <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def sprite_frames(name, color="Blue", sheet="idle_right", height=96):
    """Animation frames of a character, recoloured with the game's own palette swap and scaled to
    ``height`` px. Cached per (name, colour, sheet, height). [] if the sheet does not exist."""
    key = (name, color, sheet, height)
    out = _frames.get(key)
    if out is None:
        out = []
        try:
            from ..assets import Assets
            from ..data.palletes.entities import entity_pallete
            from ..scripts.asset_funcs import apply_pallete
            frames = Assets.ENEMY_SPRITES[name]["Blue"][sheet]
            if color != "Blue" and entity_pallete.get(color):
                frames = apply_pallete(frames, entity_pallete[color], "list")
            for f in frames:
                bbox = f.get_bounding_rect()
                if bbox.width and bbox.height:
                    f = f.subsurface(bbox)
                k = height / max(1, f.get_height())
                out.append(pygame.transform.smoothscale(f, (max(1, int(f.get_width() * k)), height)))
        except Exception:
            out = []
        _frames[key] = out
    return out


def frame_at(frames, t, fps=8):
    return frames[int(t * fps) % len(frames)] if frames else None


# ---------------------------------------------------------------------- #
# widgets
# ---------------------------------------------------------------------- #
_panels = {}


def _q(c):
    """Quantise a colour so an eased hover does not create a new cache entry every frame."""
    return tuple((v // 6) * 6 for v in c) if c is not None else None


def panel(surf, rect, fill, border=None, width=1, radius=12):
    """ui_theme.panel, cached: the same panel is blitted instead of re-created every frame."""
    key = (rect.size, _q(fill), _q(border), width, radius)
    img = _panels.get(key)
    if img is None:
        if len(_panels) > 400:
            _panels.clear()
        img = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(img, fill, (0, 0, rect.w, rect.h), border_radius=radius)
        if border:
            pygame.draw.rect(img, border, (0, 0, rect.w, rect.h), width=width, border_radius=radius)
        _panels[key] = img
    surf.blit(img, rect.topleft)


_shadows = {}
_dims = {}


def _shadow(size, radius):
    key = (size, radius)
    s = _shadows.get(key)
    if s is None:
        if len(_shadows) > 20:
            _shadows.clear()
        pad = 18
        s = pygame.Surface((size[0] + pad * 2, size[1] + pad * 2), pygame.SRCALPHA)
        for i in range(pad, 0, -2):
            pygame.draw.rect(s, (0, 0, 0, 7), pygame.Rect(pad - i, pad - i + 6, size[0] + i * 2, size[1] + i * 2), border_radius=radius + i)
        _shadows[key] = s
    return s


def draw_window_frame(surf, rect, title, t, radius=18, close=True):
    """Shadow + panel + travelling border light + wave-text title. Returns the close-button rect."""
    surf.blit(_shadow(rect.size, radius), (rect.x - 18, rect.y - 18))
    panel(surf, rect, (*PANEL, 238), None, 0, radius)
    pygame.draw.rect(surf, (96, 50, 58), rect, 2, border_radius=radius)
    # a light that travels round the border (two, opposite each other)
    per = 2 * (rect.w + rect.h)
    for k, col in ((0.0, BORDER), (0.5, BORDER_2)):
        d = ((t * 0.09 + k) % 1.0) * per
        if d < rect.w:
            p = (rect.x + d, rect.y)
        elif d < rect.w + rect.h:
            p = (rect.right, rect.y + d - rect.w)
        elif d < 2 * rect.w + rect.h:
            p = (rect.right - (d - rect.w - rect.h), rect.bottom)
        else:
            p = (rect.x, rect.bottom - (d - 2 * rect.w - rect.h))
        fx.glow(surf, p, col, int(rect.h * 0.16), 0.75, rect.inflate(10, 10))
    size = max(18, int(rect.h * 0.055))
    fx.wave_text(surf, title, (rect.x + 26, rect.y + 16), size, ui.CREAM, BORDER_2, t, amp=2.5)
    pygame.draw.line(surf, BORDER, (rect.x + 22, rect.y + size + 30), (rect.right - 22, rect.y + size + 30), 2)
    if not close:
        return None
    cb = pygame.Rect(0, 0, int(size * 1.5), int(size * 1.15))
    cb.topright = (rect.right - 18, rect.y + 12)
    return cb


def pill(surf, rect, label, active=False, hover=0.0, accent=BORDER, icon=None, size=None, pressed=0.0):
    """A rounded button with hover glow. ``hover`` 0..1 (eased by the caller)."""
    r = rect.move(0, int(pressed * 2))
    base = (62, 32, 44) if active else (42, 26, 36)
    fill = fx.lerp_color(base, (96, 44, 58), max(hover, 1.0 if active else 0.0) * 0.8)
    if hover > 0.05:
        fx.glow(surf, r.center, accent, int(r.w * 0.55), 0.35 * hover, r.inflate(24, 24))
    panel(surf, r, fill, accent if (active or hover > 0.3) else (110, 66, 68), 2 if active else 1, r.h // 2)
    s = txt(label, size or max(11, int(r.h * 0.42)), ui.CREAM if active or hover > 0.3 else (214, 202, 204), True)
    x = r.centerx - s.get_width() // 2
    if icon is not None:
        surf.blit(icon, (r.x + int(r.h * 0.3), r.centery - icon.get_height() // 2))
        x = r.x + int(r.h * 0.3) + icon.get_width() + int(r.h * 0.25)
    surf.blit(s, (x, r.centery - s.get_height() // 2))


def card_ease(store, key, active, dt, speed=14):
    """Eased 0..1 value per card (hover / selection)."""
    v = store.get(key, 0.0)
    v = fx.smooth_to(v, 1.0 if active else 0.0, dt, speed)
    store[key] = v
    return v


def draw_card(surf, rect, ease, accent=BORDER, selected=False, radius=14, fill=(40, 27, 36)):
    """A card with eased lift + glow. Returns the rect actually drawn (lifted)."""
    r = rect.move(0, -int(6 * ease))
    if ease > 0.05:
        fx.glow(surf, r.center, accent, int(max(r.w, r.h) * 0.62), 0.45 * ease, r.inflate(40, 40))
    panel(surf, r, fx.lerp_color(fill, (66, 38, 50), ease), accent if (selected or ease > 0.3) else (100, 62, 64),
             3 if selected else 2, radius)
    return r


def stat_bar(surf, rect, frac, color, label=None, value=None, size=None):
    """A labelled bar: label left, bar, value right. ``frac`` 0..1."""
    size = size or max(11, int(rect.h * 0.95))
    x, w = rect.x, rect.w
    if label:
        s = txt(label, size, (200, 190, 196), True)
        surf.blit(s, (x, rect.centery - s.get_height() // 2))
        lw = int(w * 0.28)
        x += lw
        w -= lw
    vw = 0
    if value is not None:
        v = txt(str(value), size, ui.CREAM, True)
        vw = v.get_width() + 8
        surf.blit(v, (rect.right - v.get_width(), rect.centery - v.get_height() // 2))
    bar = pygame.Rect(x, rect.y + rect.h // 4, w - vw, max(5, rect.h // 2))
    pygame.draw.rect(surf, ui.INK, bar.inflate(4, 4), border_radius=5)
    pygame.draw.rect(surf, (54, 40, 52), bar, border_radius=4)
    if frac > 0:
        pygame.draw.rect(surf, color, (bar.x, bar.y, max(bar.h, int(bar.w * min(1.0, frac))), bar.h), border_radius=4)


def key_glyph(surf, pos, label, size=22, anchor="topleft"):
    """A keycap. Returns its rect (so rows can be laid out left to right)."""
    s = txt(label, int(size * 0.62), ui.INK, True)
    w, h = max(size, s.get_width() + int(size * 0.6)), size
    r = pygame.Rect(0, 0, w, h)
    setattr(r, anchor, pos)
    pygame.draw.rect(surf, (20, 14, 22), r.move(0, 3), border_radius=6)
    pygame.draw.rect(surf, (235, 226, 214), r, border_radius=6)
    pygame.draw.rect(surf, (150, 136, 130), r, 2, border_radius=6)
    surf.blit(s, s.get_rect(center=(r.centerx, r.centery - 1)))
    return r


def pad_glyph(surf, pos, label, size=22, anchor="topleft", color=(120, 190, 255)):
    """A round gamepad button."""
    s = txt(label, int(size * 0.5), ui.INK, True)
    d = max(size, s.get_width() + 8)
    r = pygame.Rect(0, 0, d, size)
    setattr(r, anchor, pos)
    pygame.draw.ellipse(surf, (20, 14, 22), r.move(0, 3))
    pygame.draw.ellipse(surf, color, r)
    pygame.draw.ellipse(surf, (230, 240, 255), r, 2)
    surf.blit(s, s.get_rect(center=r.center))
    return r


def tag(surf, pos, label, color, size=12, anchor="topleft"):
    """A small coloured pill with text."""
    s = txt(label, size, ui.INK, True)
    r = pygame.Rect(0, 0, s.get_width() + 14, s.get_height() + 6)
    setattr(r, anchor, pos)
    pygame.draw.rect(surf, color, r, border_radius=r.h // 2)
    surf.blit(s, s.get_rect(center=r.center))
    return r


def _dim(size):
    d = _dims.get(size)
    if d is None:
        d = pygame.Surface(size, pygame.SRCALPHA)
        d.fill((10, 7, 16, 150))
        _dims[size] = d
    return d


# ---------------------------------------------------------------------- #
# the window loop
# ---------------------------------------------------------------------- #
class KitWindow:
    title = "WINDOW"
    close_on_back = True
    width_frac, height_frac = 0.84, 0.84

    def __init__(self, game):
        self.game = game
        self.t = 0.0
        self.opening = 0.0
        self.closing = None
        self.quit = False
        self.result = True              # False = the game window was closed inside
        self.parts = fx.Particles()
        self.hover_pos = (-1, -1)
        self.ease = {}                  # card / pill eases, by key
        self.rects = {}                 # clickable rects of this frame (name -> Rect), filled by draw
        self._buf = None
        self._axis = {}                 # joystick axis repeat state
        self._drag = None

    # ----- hooks -----
    def on_action(self, action, data=None):
        return False

    def update(self, dt):
        pass

    def draw_body(self, surf, body, t):
        pass

    def hint(self):
        return "ESC back"

    # ----- layout -----
    def frame_rect(self):
        w, h = self.game.window.get_size()
        r = pygame.Rect(0, 0, int(w * self.width_frac), int(h * self.height_frac))
        r.center = (w // 2, h // 2)
        return r

    def body_rect(self, frame):
        size = max(18, int(frame.h * 0.055))
        return pygame.Rect(frame.x + 24, frame.y + size + 44, frame.w - 48, frame.h - size - 44 - 40)

    def hovered(self, name):
        r = self.rects.get(name)
        return bool(r and r.collidepoint(self.hover_pos))

    def pill_ease(self, name, dt):
        return card_ease(self.ease, ("pill", name), self.hovered(name), dt)

    # ----- input -----
    def _axis_action(self, axis, value):
        st = self._axis.setdefault(axis, [0, 0.0])
        d = 1 if value > 0.6 else -1 if value < -0.6 else 0
        now = time.time()
        if d == 0:
            st[0] = 0
            return None
        if d != st[0] or now - st[1] > 0.28:
            st[0], st[1] = d, now
            if axis == 0:
                return Action.RIGHT if d > 0 else Action.LEFT
            if axis == 1:
                return Action.DOWN if d > 0 else Action.UP
        return None

    def _handle(self, action, data=None):
        if action == Action.BACK and self.close_on_back:
            if not self.on_action(action, data):
                self.begin_close()
            return
        if self.on_action(action, data):
            if action not in (Action.SCROLL, Action.DRAG, Action.CLICK):
                _ui_tick(0.3)

    def begin_close(self):
        if self.closing is None:
            self.closing = 0.0

    def _events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.result = False
                self.quit = True
            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                m = {pygame.K_ESCAPE: Action.BACK, pygame.K_BACKSPACE: Action.BACK,
                     pygame.K_LEFT: Action.LEFT, pygame.K_RIGHT: Action.RIGHT,
                     pygame.K_UP: Action.UP, pygame.K_DOWN: Action.DOWN,
                     pygame.K_a: Action.LEFT, pygame.K_d: Action.RIGHT,
                     pygame.K_w: Action.UP, pygame.K_s: Action.DOWN,
                     pygame.K_RETURN: Action.CONFIRM, pygame.K_KP_ENTER: Action.CONFIRM, pygame.K_SPACE: Action.CONFIRM,
                     pygame.K_LEFTBRACKET: Action.PREV, pygame.K_RIGHTBRACKET: Action.NEXT,
                     pygame.K_q: Action.PREV, pygame.K_e: Action.NEXT}
                if k == pygame.K_TAB:
                    self._handle(Action.PREV if ev.mod & pygame.KMOD_SHIFT else Action.NEXT)
                elif k in m:
                    self._handle(m[k])
            elif ev.type == pygame.JOYHATMOTION:
                x, y = ev.value
                if x:
                    self._handle(Action.RIGHT if x > 0 else Action.LEFT)
                elif y:
                    self._handle(Action.UP if y > 0 else Action.DOWN)
            elif ev.type == pygame.JOYAXISMOTION and ev.axis in (0, 1):
                a = self._axis_action(ev.axis, ev.value)
                if a:
                    self._handle(a)
            elif ev.type == pygame.JOYBUTTONDOWN:
                m = {0: Action.CONFIRM, 1: Action.BACK, 4: Action.PREV, 5: Action.NEXT}
                if ev.button in m:
                    self._handle(m[ev.button])
            elif ev.type == pygame.MOUSEWHEEL:
                self._handle(Action.SCROLL, ev.y)
            elif ev.type == pygame.MOUSEMOTION:
                self.hover_pos = ev.pos
                if self._drag is not None and ev.buttons[0]:
                    sy, moved, last = self._drag
                    if abs(ev.pos[1] - sy) > 6:
                        moved = True
                    if moved:
                        self._handle(Action.DRAG, ev.pos[1] - last)
                    self._drag = (sy, moved, ev.pos[1])
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                self.hover_pos = ev.pos
                self._drag = (ev.pos[1], False, ev.pos[1])
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                drag, self._drag = self._drag, None
                if drag is not None and not drag[1]:
                    close = self.rects.get("close")
                    if close is not None and close.collidepoint(ev.pos):
                        _ui_tick(0.4)
                        self.begin_close()
                    else:
                        self._handle(Action.CLICK, ev.pos)

    # ----- loop -----
    def run(self):
        game = self.game
        dt = 1 / 60
        while not self.quit:
            self._events()
            self.t += dt
            if self.closing is not None:
                self.closing += dt
                if self.closing >= CLOSE_TIME:
                    break
            else:
                self.opening = min(self.opening + dt, 10.0)
            self.update(dt)
            self._draw(dt)
            pygame.display.flip()
            dt = min(0.05, game.clock.tick(getattr(game, "FPS", 60)) / 1000.0)
        return self.result

    def _draw(self, dt):
        game = self.game
        win = game.window
        w, h = win.get_size()
        game.draw_menu_bg()
        win.blit(_dim((w, h)), (0, 0))
        self.parts.ambient(dt, w, h, (255, 150, 110), rate=6.0)
        self.parts.update(dt)
        self.parts.draw(win, self.t)

        # open / close: scale + fade through a reusable buffer, otherwise draw straight to the window
        if self.closing is not None:
            p = 1.0 - fx.clamp(self.closing / CLOSE_TIME)
            scale = 0.94 + 0.06 * p
        else:
            p = fx.clamp(self.opening / OPEN_TIME)
            scale = 0.9 + 0.1 * fx.ease_out_back(p)
        animating = p < 0.999
        if animating:
            if self._buf is None or self._buf.get_size() != (w, h):
                self._buf = pygame.Surface((w, h), pygame.SRCALPHA)
            self._buf.fill((0, 0, 0, 0))
            target = self._buf
        else:
            target = win

        frame = self.frame_rect()
        self.rects = {}
        close = draw_window_frame(target, frame, self.title, self.t)
        body = self.body_rect(frame)
        if close is not None:
            self.rects["close"] = close
            hv = card_ease(self.ease, ("pill", "close"), close.collidepoint(self.hover_pos), dt)
            pill(target, close, "X", False, hv, BORDER)
        self.draw_body(target, body, self.t)
        hint = fit(self.hint(), max(11, int(frame.h * 0.026)), False, frame.w - 40)
        s = txt(hint, max(11, int(frame.h * 0.026)), (150, 140, 150))
        target.blit(s, (frame.centerx - s.get_width() // 2, frame.bottom - s.get_height() - 12))

        if animating:
            size = (max(1, int(w * scale)), max(1, int(h * scale)))
            img = pygame.transform.smoothscale(self._buf, size)
            img.set_alpha(int(255 * fx.clamp(p * 1.5)))
            win.blit(img, img.get_rect(center=(w // 2, h // 2)))


def open_window(window):
    """Run a KitWindow; True normally, False if the game window was closed inside it."""
    return window.run()
