"""
defeat_screen.py
================
Shown when every local human player is down. A blocking modal in the same
style as the shop (and the same "own little event loop" pattern):

    open_defeat(game)  ->  "restart"   put everyone back as they entered the floor
                           "continue"  somebody was revived; carry on playing
                           "quit"      the window was closed

Each fallen player gets a REVIVE row (pearls; the price rises with every
revive this run). RESTART FLOOR is always available, so the screen can never
be a dead end. CONTINUE appears once somebody is standing again.

Controls: Up/Down (W/S, joystick hat) select - Enter/Space/E (joystick
button 0) confirm - or hover/click/tap a row.

What you will see
-----------------
    * the colour drains out of the frozen game, a red vignette beats like a
      heart, ash drifts down
    * "YOU FELL" drops in letter by letter and lands with a thud; the rows
      slide up after it
    * the pearl (a spinning coin from Assets.GEM_SPRITES) glows and sheds
      embers while you can afford a revive
    * reviving bursts pearls, flashes, shakes - and the colour floods back
      before the game resumes. Restart fades to black.
"""

import math
import random
import types

import pygame

from . import ui_theme as ui
from . import ui_fx as fx
from ..scripts import death_rules as rules

PEARL = fx.COIN_COLORS["pearl"]
HINT = "Up/Down: select    Enter: confirm"
MESSAGE_SECONDS = 2.5


def open_defeat(game):
    return _Defeat(game).run()


def _bleak(snapshot):
    """The frozen scene, drained of colour with a cold crimson cast."""
    try:
        gray = pygame.transform.grayscale(snapshot)
    except Exception:
        gray = snapshot.copy()
    gray = gray.copy()
    gray.fill((205, 150, 160), special_flags=pygame.BLEND_RGB_MULT)
    return gray


class _Defeat:
    def __init__(self, game):
        self.game = game
        self.people = rules.humans(game)
        self.snapshot = game.window.copy().convert()
        self.gray = _bleak(self.snapshot)
        self._bg = None
        self.layer = fx.Layer()
        self.back, self.front, self.shake = fx.Particles(), fx.Particles(), fx.Shake()

        self.t = 0.0
        self.selected = 0
        self.quit = False
        self.ending = None
        self.title_done = False
        self.message, self.message_ok, self.message_age = "", True, 99.0
        self.flash, self.flash_color = 0.0, ui.WHITE
        self.row_y, self.hot, self.row_shake = {}, {}, {}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _key(kind, who):
        return (kind, id(who)) if who is not None else (kind,)

    def _rows(self):
        fallen = [p for p in self.people if p.dead]
        standing = [p for p in self.people if not p.dead]
        rows = [("revive", p) for p in fallen] + [("restart", None)] + ([("continue", None)] if standing else [])
        return fallen, rows

    def _layout(self, rows):
        w, h = self.game.window.get_size()
        sx, sy = self.shake.offset()
        box = pygame.Rect(0, 0, min(w - 20, 640), min(h - 20, 500))
        box.center = (w // 2, h // 2)
        box.move_ip(sx, sy)
        k = max(0.62, min(1.0, box.height / 460))
        pad = int(20 * k)
        rows_y = box.top + pad + int(112 * k)
        gap = int(8 * k)
        avail = box.bottom - pad - int(34 * k) - rows_y
        row_h = max(36, min(int(60 * k), avail // max(1, len(rows)) - gap))
        L = types.SimpleNamespace()
        L.box, L.k, L.pad, L.rows_y = box, k, pad, rows_y
        L.rects = [pygame.Rect(box.left + pad, rows_y + i * (row_h + gap), box.width - pad * 2, row_h)
                   for i in range(len(rows))]
        L.rows_clip = pygame.Rect(box.left + 2, rows_y - 8, box.width - 4, max(10, avail + 16))
        return L

    # ------------------------------------------------------------------ #
    # input
    # ------------------------------------------------------------------ #
    def _select(self, index):
        if index != self.selected:
            self.selected = index
            fx.sfx(self._origin(), "button")

    def _origin(self):
        return self.people[0] if self.people else None

    def _finish(self, result, dur, revived=False):
        if self.ending is None:
            self.ending = {"result": result, "t": 0.0, "dur": dur, "revived": revived}

    def _events(self, rows, L):
        activate = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.game.running = False
                self.quit = True
                return
            if self.ending is not None:
                continue
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    self._select((self.selected - 1) % len(rows))
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self._select((self.selected + 1) % len(rows))
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_e):
                    activate = True
            elif event.type == pygame.JOYHATMOTION:
                if event.value[1]:
                    self._select((self.selected - event.value[1]) % len(rows))
            elif event.type == pygame.JOYBUTTONDOWN and event.button == 0:
                activate = True
            elif event.type == pygame.MOUSEMOTION:
                for i, rect in enumerate(L.rects):
                    if rect.collidepoint(event.pos):
                        self._select(i)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, rect in enumerate(L.rects):
                    if rect.collidepoint(event.pos):
                        self.selected, activate = i, True

        if activate and self.ending is None:
            self._activate(rows, L)

    def _activate(self, rows, L):
        game = self.game
        kind, who = rows[self.selected]
        rect = L.rects[self.selected]
        if kind == "restart":
            fx.sfx(self._origin(), "button")
            self._finish("restart", 0.45)
            return
        if kind == "continue":
            fx.sfx(self._origin(), "button")
            self._finish("continue", 0.3)
            return

        price = rules.revive_price(game)
        ok, msg = rules.revive(game, who)
        self.message, self.message_ok, self.message_age = msg, ok, 0.0
        if not ok:
            self.row_shake[self._key(kind, who)] = 1.0
            self.shake.kick(2.5)
            self.flash, self.flash_color = 0.08, ui.CORAL
            fx.sfx(who, "miss")
            return

        cx, cy = rect.center
        self.front.burst_coins(cx, cy, "pearl", 9, size=26)
        self.front.ring(cx, cy, PEARL, count=26, speed=300, life=0.7)
        self.front.ring(cx, cy, ui.WHITE, count=16, speed=180, life=0.5, size=2)
        self.front.spark(cx, cy, ui.WHITE, count=34, speed=340, life=0.9, gravity=120)
        self.front.text(rect.right - int(60 * L.k), cy - 10, f"-{price}", ui.CORAL, 22)
        self.front.text(L.box.centerx, L.box.top + int(70 * L.k), "REVIVED!", PEARL, int(34 * L.k), life=1.5, vy=-26)
        self.flash, self.flash_color = 0.6, ui.WHITE
        self.shake.kick(8.0)
        fx.sfx(who, "win")

    # ------------------------------------------------------------------ #
    # simulation
    # ------------------------------------------------------------------ #
    def _grief(self):
        """1 = bleak, 0 = full colour. Drains in on open, floods back on a full revive."""
        g = fx.ease_in_out(self.t / 0.9)
        e = self.ending
        if e and e["revived"]:
            g *= 1 - fx.ease_in_out(e["t"] / 0.7)
        return g

    def _update(self, dt, rows, L, price):
        game = self.game
        w, h = game.window.get_size()
        self.t += dt
        self.message_age += dt
        self.shake.update(dt)
        self.flash = max(0.0, self.flash - dt * 1.6)
        if self.ending:
            self.ending["t"] += dt

        for i, (kind, who) in enumerate(rows):
            key = self._key(kind, who)
            target = L.rects[i].y
            self.row_y[key] = fx.smooth_to(self.row_y.get(key, target), target, dt, 12)
            self.hot[key] = fx.smooth_to(self.hot.get(key, 0.0), 1.0 if i == self.selected else 0.0, dt, 14)
        for key in list(self.row_shake):
            self.row_shake[key] = max(0.0, self.row_shake[key] - dt * 2.8)

        self.back.ambient(dt, w, h, (150, 140, 152), rate=16 * self._grief(), falling=True)

        # embers rise off a revive you can afford
        if self.ending is None and self.selected < len(rows):
            kind, who = rows[self.selected]
            if kind == "revive" and rules.can_revive(game, who) and random.random() < dt * 30:
                r = L.rects[self.selected]
                self.front.spark(random.uniform(r.left + 20, r.right - 20), r.centery, PEARL, count=1, speed=40,
                                 life=1.0, size=2, gravity=-130, spread=math.pi / 2, angle=-math.pi / 2)

        self.back.update(dt)
        self.front.update(dt)

    # ------------------------------------------------------------------ #
    # drawing
    # ------------------------------------------------------------------ #
    def _presence(self):
        e = self.ending
        if e is None:
            return fx.ease_out_back(self.t / 0.45, 1.2)
        if e["revived"]:
            return 1.0 - fx.ease_in_out((e["t"] - 0.6) / 0.6)
        if e["result"] == "continue":
            return 1.0 - fx.ease_in_out(e["t"] / e["dur"])
        return 1.0

    def _draw(self, rows, people, L, price):
        game = self.game
        window = game.window
        w, h = window.get_size()
        grief = self._grief()
        beat = fx.heartbeat(self.t)

        # once the colour has fully drained, snapshot + gray + dim never change: build that
        # picture once and reuse it (saves three full-window blits every frame)
        bg = self._bg if (grief >= 0.999 and self._bg is not None and self._bg.get_size() == (w, h)) else None
        if bg is not None:
            window.blit(bg, (0, 0))
        else:
            window.blit(self.snapshot, (0, 0))
            if grief > 0.01:
                self.gray.set_alpha(int(255 * grief))
                window.blit(self.gray, (0, 0))
            ui.dim_overlay(window, int(150 * grief))
            if grief >= 0.999:
                self._bg = window.copy()
        vig = fx.vignette((w, h))
        vig.set_alpha(int((110 + 145 * beat) * grief))
        window.blit(vig, (0, 0))
        self.back.draw(window, self.t)

        surf = self.layer.begin((w, h), L.box.inflate(100, 140))
        self._draw_panel(surf, rows, people, L, price, beat)
        self.layer.commit(window, self._presence())

        self.front.draw(window, self.t)
        if self.flash > 0.02:
            ui.dim_overlay(window, int(200 * self.flash), self.flash_color)
        e = self.ending
        if e and e["result"] == "restart":
            ui.dim_overlay(window, int(255 * fx.clamp(e["t"] / e["dur"])), (0, 0, 0))

    def _draw_panel(self, surf, rows, people, L, price, beat):
        game, t = self.game, self.t
        box, k, pad = L.box, L.k, L.pad
        e = self.ending
        revived = bool(e and e["revived"])

        tone = fx.lerp_color((220, 40, 60), PEARL, fx.clamp(e["t"] / 0.5) if revived else 0.0)
        fx.aura(surf, box, tone, 0.35 + 0.9 * beat)
        ui.panel(surf, box, (30, 19, 26), fx.lerp_color(ui.CORAL, PEARL, 1.0 if revived else 0.0), 2, 16)

        # ---- title ----
        title, tcolor, age = ("REVIVED", PEARL, e["t"]) if revived else ("YOU FELL", ui.CREAM, t - 0.15)
        tc = (box.centerx, box.top + pad + int(26 * k))
        self.layer.glow(tc, tone, int(170 * k), 0.3 + 0.45 * beat, clip=box)
        done = fx.drop_text(surf, title, tc, int(40 * k), tcolor, age, sway_t=t)
        if done and not self.title_done and not revived:
            self.title_done = True
            self.shake.kick(6.0)
            self.front.spark(tc[0], tc[1] + int(18 * k), (200, 190, 200), count=22, speed=200, life=0.7,
                             gravity=300, spread=math.pi, angle=-math.pi / 2)

        if not revived:
            a = 255 * fx.clamp((t - 0.9) / 0.4)
            plural = "" if price == 1 else "s"
            fx.text_alpha(surf, f"Floor {game.level}   -   next revive costs {price} pearl{plural}",
                          (box.centerx, box.top + pad + int(64 * k)), int(14 * k), ui.MUTED, a, center=True, shadow=False)
            fx.text_alpha(surf, "Spilled coins wait where you fell. Restart puts you back as you entered the floor.",
                          (box.centerx, box.top + pad + int(86 * k)), int(11 * k), ui.MUTED, a, center=True, shadow=False)

        # ---- rows ----
        if not revived:
            surf.set_clip(L.rows_clip)
            for i, (kind, who) in enumerate(rows):
                self._draw_row(surf, i, kind, who, L, people, price, beat)
            surf.set_clip(None)

        if self.message and self.message_age < MESSAGE_SECONDS:
            fx.text_alpha(surf, self.message, (box.centerx, box.bottom - pad - int(26 * k)), int(13 * k),
                          ui.GREEN if self.message_ok else ui.CORAL,
                          255 * fx.clamp((MESSAGE_SECONDS - self.message_age) / 0.5), True, center=True)
        ui.text_centered(surf, HINT, (box.centerx, box.bottom - pad), int(11 * k), ui.MUTED)

    def _draw_row(self, surf, i, kind, who, L, people, price, beat):
        game, t, k = self.game, self.t, L.k
        key = self._key(kind, who)
        appear = fx.clamp((t - 0.85 - 0.1 * i) / 0.4)
        if appear <= 0:
            return
        hot = self.hot.get(key, 0.0)
        rect = L.rects[i].copy()
        rect.y = int(self.row_y.get(key, rect.y)) + int((1 - fx.ease_out_back(appear, 1.2)) * 46)
        rect.x += int(math.sin(t * 70) * 7 * self.row_shake.get(key, 0.0))
        clip = rect.clip(L.rows_clip)
        pulse = fx.pulse(t, 0.8)
        gx, cy = rect.left + int(30 * k), rect.centery
        icon = max(18, int(36 * k))
        tx = rect.left + int(58 * k)
        two_line = rect.height >= 44

        if kind == "revive":
            can_pay = rules.can_revive(game, who)
            accent = PEARL
            ui.panel(surf, rect, fx.lerp_color((44, 26, 34), (83, 37, 47), hot),
                     fx.lerp_color((112, 64, 66), PEARL, hot), 2 if hot > 0.4 else 1, 10)
            if can_pay:
                self.layer.glow(rect.center, PEARL, max(rect.width // 2, 80), 0.1 + 0.2 * pulse + 0.25 * hot, clip=clip)
                self.layer.glow((gx, cy), PEARL, int(rect.height * 1.1), 0.35 + 0.35 * pulse, clip=clip)
            fx.draw_coin(surf, (gx, cy), "pearl", icon, t, fps=9 if can_pay else 3, alpha=255 if can_pay else 110)

            number = people.index(who) + 1
            name_y = rect.top + (int(8 * k) if two_line else rect.height // 2 - int(10 * k))
            ui.text(surf, f"Revive Player {number}", (tx, name_y), int(18 * k), ui.CREAM if can_pay else ui.MUTED, True)
            if two_line:
                pct = int(getattr(rules, "REVIVE_HEALTH", 0.5) * 100)
                ui.text(surf, f"Back on your feet with {pct}% HP and a moment of shelter",
                        (tx, name_y + int(24 * k)), int(11 * k), ui.MUTED)

            # cost: one pearl per pearl (max 4), right-aligned, and what you hold
            rx = rect.right - int(16 * k)
            have = getattr(who, "pearl_coins", 0)
            small = max(14, int(20 * k))
            shown = min(price, 4)
            iy = cy - (int(9 * k) if two_line else 0)
            for j in range(shown):
                fx.draw_coin(surf, (rx - small // 2 - j * int(15 * k), iy), "pearl", small, t, phase=j * 0.15,
                             fps=8 if can_pay else 3, alpha=255 if can_pay else 110)
            if price > shown:
                label = ui.font(int(15 * k), True).render(f"x{price}", True, ui.CREAM if can_pay else ui.CORAL)
                surf.blit(label, (rx - small - (shown - 1) * int(15 * k) - label.get_width() - 4, iy - label.get_height() // 2))
            if two_line:
                lab = ui.font(int(11 * k)).render(f"have {have}", True, ui.MUTED if can_pay else ui.CORAL)
                surf.blit(lab, (rx - lab.get_width(), cy + int(8 * k)))
            return

        # restart / continue rows
        accent = ui.GREEN if kind == "continue" else ui.CORAL
        ui.panel(surf, rect, fx.lerp_color((48, 27, 36), (83, 37, 47), hot), fx.lerp_color((112, 64, 66), accent, hot),
                 2 if hot > 0.4 else 1, 10)
        if hot > 0.05:
            self.layer.glow(rect.center, accent, max(rect.width // 2, 80), 0.2 * hot, clip=clip)
        r = int(12 * k)
        pygame.draw.circle(surf, (26, 16, 22), (gx, cy), r + 6)
        pygame.draw.circle(surf, fx.lerp_color((92, 60, 62), accent, 0.4 + 0.6 * hot), (gx, cy), r + 6, 2)
        if kind == "restart":
            spin = t * 2.5 * hot
            a0, a1 = 0.7 + spin, 5.6 + spin
            pygame.draw.arc(surf, accent, pygame.Rect(gx - r, cy - r, r * 2, r * 2), a0, a1, 3)
            px, py = gx + r * math.cos(a1), cy - r * math.sin(a1)
            dx, dy = -math.sin(a1), -math.cos(a1)
            pygame.draw.polygon(surf, accent, [(px + dx * 8, py + dy * 8), (px - dy * 5, py + dx * 5), (px + dy * 5, py - dx * 5)])
            label, sub = "RESTART FLOOR", f"Back to the start of floor {game.level}"
        else:
            bob = int(math.sin(t * 5) * 2 * (0.4 + hot))
            pygame.draw.polygon(surf, accent, [(gx - 5 + bob, cy - 8), (gx + 8 + bob, cy), (gx - 5 + bob, cy + 8)])
            label, sub = "CONTINUE", "Carry on with whoever is still standing"
        ty = rect.top + (int(9 * k) if two_line else rect.height // 2 - int(9 * k))
        ui.text(surf, label, (tx, ty), int(17 * k), ui.CREAM if hot > 0.3 else ui.WHITE, True)
        if two_line:
            ui.text(surf, sub, (tx, ty + int(24 * k)), int(11 * k), ui.MUTED)

    # ------------------------------------------------------------------ #
    # main loop
    # ------------------------------------------------------------------ #
    def run(self):
        game, dt = self.game, 1 / 60
        while True:
            fallen, rows = self._rows()
            if not fallen and self.ending is None:
                # the last fallen player was just revived: let the colour flood back first
                self._finish("continue", 1.2, revived=True)
            self.selected = max(0, min(self.selected, len(rows) - 1))
            price = rules.revive_price(game)
            L = self._layout(rows)

            self._events(rows, L)
            if self.quit:
                return "quit"

            fallen, rows = self._rows()
            if not fallen and self.ending is None:
                self._finish("continue", 1.2, revived=True)
            self.selected = max(0, min(self.selected, len(rows) - 1))
            price = rules.revive_price(game)
            L = self._layout(rows)

            self._update(dt, rows, L, price)
            if self.ending is not None and self.ending["t"] >= self.ending["dur"]:
                game.keys = pygame.key.get_pressed()
                return self.ending["result"]

            self._draw(rows, self.people, L, price)
            pygame.display.flip()
            dt = min(0.05, game.clock.tick(getattr(game, "FPS", 60)) / 1000.0)
