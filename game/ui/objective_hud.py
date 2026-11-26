"""
objective_hud.py
================
The in-level HUD: tells you *what you have to do* and *how close you are*.

Why this exists
---------------
The old HUD put one line of text at the top centre of the screen - exactly
where the SPECTATE and VIEW buttons live, so the objective was hidden behind
them, and it only said things like "ENEMIES LEFT: 12" with no hint of what
the level actually expects from you.

Layout (everything is relative to the player's viewport, so split screen works)
    top-left      MISSION CARD   world number + title, time, HP bar, the
                                 objective in plain words, a progress bar and a
                                 live status line.  The card is narrower than
                                 the gap before the SPECTATE button on purpose.
    top-centre    BOSS BAR       just *under* the button row (never behind it)
    anywhere      GOAL POINTER   a bobbing arrow over the goal, or an arrow on
                                 the screen edge pointing at it when off-screen,
                                 with the distance
    upper-centre  EVENT BANNERS  "WAVE 3", "THE EXIT IS OPEN", "PHASE 2" ...

Every objective in level/main/objectives.py supplies the words and numbers
(``brief``, ``progress()``, ``status()``, ``target()``); this module only draws.

Performance: text surfaces are cached by (text, size, colour), panels by size,
and nothing here allocates anything large per frame.
"""

import math
import time

import pygame

from . import ui_theme as ui

ACCENTS = {
    "clear_all": ui.CORAL,
    "survival": ui.BLUE,
    "exit": ui.GREEN,
    "boss": ui.RED,
    "final": ui.PURPLE,
}


def _now():
    return time.perf_counter()


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def _lerp_color(a, b, t):
    t = _clamp(t)
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def _ease_out_back(t, s=1.70158):
    t = _clamp(t) - 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def _ease_out_cubic(t):
    return 1 - (1 - _clamp(t)) ** 3


class ObjectiveHUD:
    def __init__(self):
        self._txt = {}
        self._panels = {}
        self.reset()

    # ------------------------------------------------------------------ #
    def reset(self):
        """Call whenever a new level's objective is created."""
        self.born = _now()
        self.events = []
        self.hp_ghost = {}
        self.boss_ghost = None
        self.ping_at = -9.0
        self._pkey = None
        self.hidden = False             # the world intro hides the HUD until it ends

    def restart_slide(self):
        """Slide the card in again (called when the world intro finishes)."""
        self.born = _now()

    def event(self, text, color=None, sub=None, life=2.6):
        """Queue a centre-screen announcement."""
        self.events.append({"text": text, "color": color or ui.CREAM, "sub": sub, "age": 0.0, "life": life})
        del self.events[6:]

    # ------------------------------------------------------------------ #
    # cached drawing helpers
    # ------------------------------------------------------------------ #
    def _text(self, txt, size, color, bold=True):
        key = (txt, size, color, bold)
        img = self._txt.get(key)
        if img is None:
            if len(self._txt) > 260:
                self._txt.clear()
            img = ui.font(size, bold).render(txt, True, color)
            self._txt[key] = img
        return img

    def _panel(self, size, fill, border, radius):
        key = (size, fill, border, radius)
        img = self._panels.get(key)
        if img is None:
            if len(self._panels) > 24:
                self._panels.clear()
            img = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.rect(img, fill, (0, 0, size[0], size[1]), border_radius=radius)
            pygame.draw.rect(img, border, (0, 0, size[0], size[1]), width=2, border_radius=radius)
            self._panels[key] = img
        return img

    def _draw_text(self, window, txt, size, color, pos, bold=True, shadow=True, anchor="topleft"):
        img = self._text(txt, size, color, bold)
        rect = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
        if shadow:
            sh = self._text(txt, size, ui.INK, bold)
            window.blit(sh, rect.move(1, 1))
        window.blit(img, rect)
        return rect

    # ------------------------------------------------------------------ #
    # main entry: one call per player viewport
    # ------------------------------------------------------------------ #
    def draw(self, game, window, view_rect, player, objective, dt, cam, zoom, info):
        """Returns the y just below the mission card so the caller can stack coins under it."""
        if self.hidden:
            return view_rect.y + int(view_rect.height * 0.025)
        now = _now()
        accent = ACCENTS.get(getattr(objective, "kind", "clear_all"), ui.CORAL)

        self._draw_pointer(window, view_rect, player, objective, cam, zoom, now)
        bottom = self._draw_card(game, window, view_rect, player, objective, dt, now, accent, info)
        self._draw_boss_bar(window, view_rect, objective, dt, now)
        if player is game.local_players[0]:
            self._draw_events(window, view_rect, dt)
        return bottom

    # ------------------------------------------------------------------ #
    # mission card
    # ------------------------------------------------------------------ #
    @staticmethod
    def info_held(game):
        """True while the player holds I: the full card (world, objective text, coins) is shown."""
        try:
            return bool(game.keys[pygame.K_i])
        except Exception:
            return False

    def _draw_compact(self, game, window, view_rect, player, objective, dt, now, accent):
        """The resting card: HP, time and objective progress in a small strip. Hold I for the rest."""
        vw, vh = view_rect.size
        base = max(11, int(vh * 0.024))
        pad = max(6, int(base * 0.5))
        cw = int(_clamp(vw * 0.17, 140, 300))
        w_in = cw - pad * 2 - 4
        small = base - 2
        line = int(base * 1.2)
        hp_h = max(10, int(base * 0.9))
        bar_h = max(5, int(base * 0.4))
        progress = objective.progress() if hasattr(objective, "progress") else None
        status = objective.status() if hasattr(objective, "status") else None

        h = pad + hp_h + 4 + line + (bar_h + 3 if progress else 0) + pad
        u = _ease_out_back((now - self.born) / 0.6)
        x0 = view_rect.x + int(vw * 0.015) - int((1.0 - min(1.0, u)) * (cw + 30))
        y0 = view_rect.y + int(vh * 0.025)
        rect = pygame.Rect(x0, y0, cw, h)

        key = (progress[1] if progress else None, status[0] if status else None)
        if key != self._pkey:
            if self._pkey is not None:
                self.ping_at = now
            self._pkey = key
        ping = _clamp(1.0 - (now - self.ping_at) / 0.7)
        border = _lerp_color(_lerp_color(accent, ui.INK2, 0.5), ui.WHITE, ping * 0.7)
        window.blit(self._panel((cw, h), (22, 16, 24, 150), border, max(8, base // 2 + 2)), rect.topleft)

        x, y = rect.x + pad + 4, rect.y + pad
        max_hp = max(1.0, float(getattr(player, "max_health", 1) or 1))
        frac = _clamp(player.health / max_hp)
        ghost = self.hp_ghost.get(id(player), frac)
        ghost = frac if frac >= ghost else ghost - (ghost - frac) * (1 - math.exp(-2.4 * max(dt, 0.001)))
        self.hp_ghost[id(player)] = ghost
        # time sits right of the HP bar, so the objective label below gets the full width
        time_img = self._text(getattr(game, "game_time", "00:00"), small, ui.MUTED)
        bar = pygame.Rect(x, y, w_in - time_img.get_width() - 8, hp_h)
        window.blit(time_img, time_img.get_rect(midright=(x + w_in, bar.centery)))
        pygame.draw.rect(window, (40, 22, 30), bar, border_radius=hp_h // 2)
        if ghost > frac:
            g = bar.copy()
            g.width = max(0, int(bar.width * ghost))
            pygame.draw.rect(window, (235, 225, 200), g, border_radius=hp_h // 2)
        if frac > 0:
            f = bar.copy()
            f.width = max(hp_h // 2, int(bar.width * frac))
            col = _lerp_color((214, 58, 62), (108, 201, 117), (frac - 0.15) / 0.6)
            if frac < 0.3:
                col = _lerp_color(col, (255, 150, 140), 0.5 + 0.5 * math.sin(now * 9))
            pygame.draw.rect(window, col, f, border_radius=hp_h // 2)
        pygame.draw.rect(window, (110, 70, 72), bar, width=1, border_radius=hp_h // 2)
        self._draw_text(window, f"{max(0, int(player.health))} / {int(max_hp)}", max(9, small - 2), ui.WHITE,
                        bar.center, anchor="center")
        y += hp_h + 4

        # progress (or the live status) gets the whole row; too long -> a smaller font
        def fit(txt):
            sz = small
            while sz > 8 and ui.font(sz, True).size(txt)[0] > w_in:
                sz -= 1
            return sz
        if progress:
            pfrac, label = progress
            self._draw_text(window, label, fit(label), _lerp_color(ui.CREAM, ui.WHITE, ping), (x, y))
            y += line + 1
            pb = pygame.Rect(x, y, w_in, bar_h)
            pygame.draw.rect(window, (40, 22, 30), pb, border_radius=bar_h // 2)
            if pfrac > 0:
                pf = pb.copy()
                pf.width = max(bar_h, int(pb.width * _clamp(pfrac)))
                pygame.draw.rect(window, accent, pf, border_radius=bar_h // 2)
        elif status:
            text, color = status
            self._draw_text(window, text, fit(text), color or ui.CREAM, (x, y))
        else:
            self._draw_text(window, "hold I for info", small, ui.MUTED, (x, y))
        return rect.bottom + max(4, int(vh * 0.01))

    def _draw_card(self, game, window, view_rect, player, objective, dt, now, accent, info):
        if not self.info_held(game):
            return self._draw_compact(game, window, view_rect, player, objective, dt, now, accent)
        vw, vh = view_rect.size
        base = max(11, int(vh * 0.024))
        pad = max(8, int(base * 0.7))
        # Narrower than the gap in front of the SPECTATE button (starts at 27% of the width)
        cw = int(_clamp(vw * 0.225, 170, 400))
        inner = cw - pad * 2

        f_body = ui.font(base - 1, False)
        brief = ui.wrap(getattr(objective, "brief", ""), inner, f_body)[:3]
        progress = objective.progress() if hasattr(objective, "progress") else None
        status = objective.status() if hasattr(objective, "status") else None

        small, title_sz = base - 2, base + 4
        line = int(base * 1.25)
        hp_h = max(10, int(base * 0.95))
        bar_h = max(7, int(base * 0.55))

        h = pad + line + int(title_sz * 1.25) + 6 + hp_h + 10 + 2 + 8            # header, title, hp, divider
        h += line + 4                                                            # badge row
        h += len(brief) * line                                                   # brief text
        if progress:
            h += 6 + line + bar_h
        if status:
            h += 8 + line
        h += pad

        # slide / pop in
        u = _ease_out_back((now - self.born) / 0.6)
        x0 = view_rect.x + int(vw * 0.015) - int((1.0 - min(1.0, u)) * (cw + 30))
        y0 = view_rect.y + int(vh * 0.025)
        rect = pygame.Rect(x0, y0, cw, h)

        ping = _clamp(1.0 - (now - self.ping_at) / 0.7)
        key = (progress[1] if progress else None, status[0] if status else None)
        if key != self._pkey:
            if self._pkey is not None:
                self.ping_at = now
            self._pkey = key

        border = _lerp_color(_lerp_color(accent, ui.INK2, 0.45), ui.WHITE, ping * 0.7)
        window.blit(self._panel((cw, h), (22, 16, 24, 205), border, max(8, base // 2 + 4)), rect.topleft)
        # accent strip down the left edge
        pygame.draw.rect(window, accent, (rect.x + 2, rect.y + 10, 4, h - 20), border_radius=2)

        x = rect.x + pad + 4
        w_in = inner - 4
        y = rect.y + pad

        # header: WORLD n .......... time
        self._draw_text(window, f"WORLD {info['number']}", small, ui.GOLD, (x, y))
        self._draw_text(window, getattr(game, "game_time", "00:00"), small, ui.MUTED, (x + w_in, y), anchor="topright")
        y += line
        self._draw_text(window, info["title"].upper(), title_sz, ui.CREAM, (x, y - 2))
        y += int(title_sz * 1.25) + 6

        # HP bar with a trailing "ghost" of the damage just taken
        max_hp = max(1.0, float(getattr(player, "max_health", 1) or 1))
        frac = _clamp(player.health / max_hp)
        ghost = self.hp_ghost.get(id(player), frac)
        ghost = frac if frac >= ghost else ghost - (ghost - frac) * (1 - math.exp(-2.4 * max(dt, 0.001)))
        self.hp_ghost[id(player)] = ghost
        bar = pygame.Rect(x, y, w_in, hp_h)
        pygame.draw.rect(window, (40, 22, 30), bar, border_radius=hp_h // 2)
        if ghost > frac:
            g = bar.copy()
            g.width = max(0, int(bar.width * ghost))
            pygame.draw.rect(window, (235, 225, 200), g, border_radius=hp_h // 2)
        if frac > 0:
            f = bar.copy()
            f.width = max(hp_h // 2, int(bar.width * frac))
            low = frac < 0.3
            col = _lerp_color((214, 58, 62), (108, 201, 117), (frac - 0.15) / 0.6)
            if low:
                col = _lerp_color(col, (255, 150, 140), 0.5 + 0.5 * math.sin(now * 9))
            pygame.draw.rect(window, col, f, border_radius=hp_h // 2)
        pygame.draw.rect(window, (110, 70, 72), bar, width=1, border_radius=hp_h // 2)
        self._draw_text(window, f"{max(0, int(player.health))} / {int(max_hp)}", max(9, small - 2), ui.WHITE,
                        bar.center, anchor="center")
        y += hp_h + 10
        pygame.draw.line(window, _lerp_color(accent, ui.INK2, 0.5), (x, y), (x + w_in, y), 1)
        y += 8

        # badge + sentence
        badge = getattr(objective, "badge", "OBJECTIVE")
        bimg = self._text(badge, small, ui.INK, True)
        brect = pygame.Rect(x, y, bimg.get_width() + 14, line - 2)
        pygame.draw.rect(window, accent, brect, border_radius=6)
        window.blit(bimg, bimg.get_rect(center=brect.center))
        self._draw_text(window, "OBJECTIVE", small, ui.MUTED, (brect.right + 8, y + 1))
        y += line + 4
        for text in brief:
            self._draw_text(window, text, base - 1, ui.WHITE, (x, y), bold=False)
            y += line

        if progress:
            y += 6
            pfrac, label = progress
            pop = 1.0 + 0.25 * ping
            self._draw_text(window, label, int((base - 1) * pop), _lerp_color(ui.CREAM, ui.WHITE, ping), (x, y))
            y += line
            pb = pygame.Rect(x, y, w_in, bar_h)
            pygame.draw.rect(window, (40, 22, 30), pb, border_radius=bar_h // 2)
            if pfrac > 0:
                pf = pb.copy()
                pf.width = max(bar_h, int(pb.width * _clamp(pfrac)))
                pygame.draw.rect(window, accent, pf, border_radius=bar_h // 2)
            pygame.draw.rect(window, (110, 70, 72), pb, width=1, border_radius=bar_h // 2)
            y += bar_h

        if status:
            y += 8
            text, color = status
            color = color or ui.CREAM
            if color in (ui.GREEN, ui.GOLD):                # "go!" states breathe
                color = _lerp_color(color, ui.WHITE, 0.25 + 0.25 * math.sin(now * 6))
            self._draw_text(window, text, base - 1, color, (x, y))

        return rect.bottom + max(6, int(vh * 0.012))

    # ------------------------------------------------------------------ #
    # boss bar - under the button row, never behind it
    # ------------------------------------------------------------------ #
    def _draw_boss_bar(self, window, view_rect, objective, dt, now):
        boss = getattr(objective, "boss", None)
        if boss is None or getattr(boss, "dead", False):
            return
        vw, vh = view_rect.size
        base = max(11, int(vh * 0.024))
        bw, bh = int(vw * 0.38), max(10, int(vh * 0.024))
        bx = view_rect.centerx - bw // 2
        by = view_rect.y + int(vh * 0.135)
        max_hp = max(1.0, float(getattr(boss, "max_health", 1) or 1))
        frac = _clamp(boss.health / max_hp)
        ghost = self.boss_ghost if self.boss_ghost is not None else frac
        ghost = frac if frac >= ghost else ghost - (ghost - frac) * (1 - math.exp(-2.2 * max(dt, 0.001)))
        self.boss_ghost = ghost

        name = getattr(objective, "label", "BOSS")
        phases = len(getattr(objective, "thresholds", [])) + 1
        self._draw_text(window, name, base + 2, ui.CREAM, (view_rect.centerx, by - 6), anchor="midbottom")
        self._draw_text(window, f"PHASE {getattr(objective, 'phase', 0) + 1}/{phases}", base - 3, ui.MUTED,
                        (bx + bw, by - 6), anchor="bottomright")

        rect = pygame.Rect(bx - 3, by - 3, bw + 6, bh + 6)
        pygame.draw.rect(window, (18, 10, 14), rect, border_radius=6)
        if ghost > frac:
            pygame.draw.rect(window, (235, 225, 200), (bx, by, int(bw * ghost), bh), border_radius=4)
        col = _lerp_color((214, 58, 62), (255, 120, 80), 0.5 + 0.5 * math.sin(now * 3) * (1.0 - frac))
        pygame.draw.rect(window, col, (bx, by, int(bw * frac), bh), border_radius=4)
        for t in getattr(objective, "thresholds", []):
            tx = bx + int(bw * t)
            pygame.draw.line(window, (255, 220, 160), (tx, by - 3), (tx, by + bh + 2), 2)
        pygame.draw.rect(window, (170, 90, 88), rect, width=2, border_radius=6)

    # ------------------------------------------------------------------ #
    # goal pointer
    # ------------------------------------------------------------------ #
    def _draw_pointer(self, window, view_rect, player, objective, cam, zoom, now):
        target = objective.target() if hasattr(objective, "target") else None
        if not target:
            return
        tx, ty, label, color = target
        sx = view_rect.x + (tx - cam[0]) * zoom
        sy = view_rect.y + (ty - cam[1]) * zoom
        base = max(11, int(view_rect.height * 0.024))
        margin = int(base * 2.2)
        safe = view_rect.inflate(-margin * 2, -margin * 2)
        dist = int(math.hypot(tx - player.rect.centerx, ty - player.rect.centery) / 64)
        size = max(9, int(base * 0.9))
        bob = math.sin(now * 4.5) * 5

        if safe.collidepoint(sx, sy):
            # bobbing chevron above the goal + its name
            ax, ay = sx, sy - int(base * 2.6) + bob
            pts = [(ax, ay + size), (ax - size, ay - size * 0.4), (ax + size, ay - size * 0.4)]
            pygame.draw.polygon(window, color, pts)
            pygame.draw.polygon(window, ui.INK, pts, 2)
            self._draw_text(window, label, base - 2, color, (ax, ay - size - 4), anchor="midbottom")
            return

        cx, cy = view_rect.center
        dx, dy = sx - cx, sy - cy
        half_w, half_h = safe.width / 2, safe.height / 2
        k = min(half_w / abs(dx) if dx else 1e9, half_h / abs(dy) if dy else 1e9)
        px, py = cx + dx * k, cy + dy * k
        ang = math.atan2(dy, dx)
        pulse = 0.85 + 0.15 * math.sin(now * 6)
        tip = (px + math.cos(ang) * size * 1.5 * pulse, py + math.sin(ang) * size * 1.5 * pulse)
        left = (px + math.cos(ang + 2.5) * size * 1.2, py + math.sin(ang + 2.5) * size * 1.2)
        right = (px + math.cos(ang - 2.5) * size * 1.2, py + math.sin(ang - 2.5) * size * 1.2)
        pygame.draw.polygon(window, color, (tip, left, right))
        pygame.draw.polygon(window, ui.INK, (tip, left, right), 2)
        # label + distance on the inner side of the arrow
        lx, ly = px - math.cos(ang) * size * 2.6, py - math.sin(ang) * size * 2.6
        self._draw_text(window, f"{label}  {dist} m", base - 3, color, (lx, ly), anchor="center")

    # ------------------------------------------------------------------ #
    # event banners
    # ------------------------------------------------------------------ #
    def _draw_events(self, window, view_rect, dt):
        if not self.events:
            return
        ev = self.events[0]
        ev["age"] += dt if dt > 0 else 0.016
        if ev["age"] >= ev["life"]:
            self.events.pop(0)
            return
        vw, vh = view_rect.size
        u = ev["age"] / ev["life"]
        slide = _ease_out_cubic(u / 0.12)
        fade = _clamp(1.0 - (u - 0.8) / 0.2)
        size = max(18, int(vh * 0.052))
        band_h = int(size * (2.5 if ev["sub"] else 1.9))
        band_w = int(vw * 0.6 * (0.55 + 0.45 * slide))
        cy = view_rect.y + int(vh * 0.215)
        band_w = max(8, band_w // 8 * 8)
        key = ("band", band_w, band_h)
        band = self._panels.get(key)
        if band is None:                              # built once, faded at both ends
            band = pygame.Surface((band_w, band_h), pygame.SRCALPHA)
            for i in range(band_w):
                e = min(i, band_w - 1 - i) / (band_w * 0.25)
                pygame.draw.line(band, (14, 10, 18, int(150 * _clamp(e))), (i, 0), (i, band_h))
            self._panels[key] = band
        band.set_alpha(int(255 * fade))
        window.blit(band, band.get_rect(center=(view_rect.centerx, cy)))
        col = ev["color"]
        img = self._text(ev["text"], size, col, True).copy()      # copy: alpha must not leak into the cache
        shadow = self._text(ev["text"], size, ui.INK, True)
        img.set_alpha(int(255 * fade * _clamp(u / 0.08)))
        rect = img.get_rect(center=(view_rect.centerx, cy - (int(size * 0.3) if ev["sub"] else 0)))
        window.blit(shadow, rect.move(3, 3))
        window.blit(img, rect)
        if ev["sub"]:
            sub = self._text(ev["sub"], max(11, int(size * 0.42)), ui.WHITE, False).copy()
            sub.set_alpha(int(255 * fade))
            window.blit(sub, sub.get_rect(center=(view_rect.centerx, rect.bottom + int(size * 0.35))))
