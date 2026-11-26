"""
ending.py
=========
The card shown when the last story level is won. Replaces the old placeholder
victory card with a small celebration:

    particles + a banner          embers rise, sparks burst, the title waves
    run stats                     clear time, enemies slain, achievements earned
    two buttons                   RETURN TO START   /   CRAWL AGAIN (New Game+)

``show`` blocks until the player picks and returns ``START``, ``CRAWL`` or
``None`` (window closed). The caller decides what each choice means.

Cheap on purpose: one particle system, a few text renders per frame, nothing
allocated per pixel. Input is ignored for the first moments so a button mashed
at the end of the boss fight cannot pick for the player.
"""

import math
import random
import pygame

from . import ui_theme as ui
from . import ui_fx

START = "start"
CRAWL = "crawl"

INPUT_DELAY = 1.4           # seconds before a click or key counts
STAT_STAGGER = 0.45         # seconds between stat rows appearing


def _mmss(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02}:{seconds % 60:02}"


def _sound(game, name):
    try:
        from ..scripts.sounds import playit
        playit(name, game.player)
    except Exception:
        pass


def _layout(w, h):
    box = pygame.Rect(0, 0, min(w - 20, 700), min(h - 20, 430))
    box.center = (w // 2, h // 2)
    bw = min(box.width // 2 - 24, 250)
    bh = max(36, int(box.height * 0.11))
    y = box.bottom - bh - int(box.height * 0.07)
    gap = 18
    left = pygame.Rect(0, 0, bw, bh)
    right = pygame.Rect(0, 0, bw, bh)
    left.topright = (box.centerx - gap // 2, y)
    right.topleft = (box.centerx + gap // 2, y)
    return box, [left, right]


def _event_pos(event, size):
    if event.type == pygame.FINGERDOWN:
        return int(event.x * size[0]), int(event.y * size[1])
    return event.pos


def show(game, stats, loop=0):
    """Run the ending card. Returns START, CRAWL or None."""
    try:
        return _show(game, stats, loop)
    except Exception as err:                 # a cosmetic card must never trap the player
        print(f"[ending] fell back: {err!r}")
        return START


def _show(game, stats, loop):
    window = game.window
    clock = game.clock
    snapshot = window.copy().convert()
    particles = ui_fx.Particles()
    shake = ui_fx.Shake()
    fps = getattr(game, "FPS", 60) or 60

    labels = [("RETURN TO START", "A clean slate, floor 1"),
              ("CRAWL AGAIN", f"Keep everything. Enemies +{int((loop + 1) * 50)}%")]
    selected = 0
    t = 0.0
    next_burst = 0.0
    _sound(game, "win")
    shake.kick(9)

    rows = [("TIME", _mmss(stats["seconds"])),
            ("ENEMIES SLAIN", str(stats["kills"])),
            ("ACHIEVEMENTS", str(stats["achievements"]))]

    while True:
        w, h = window.get_size()
        box, buttons = _layout(w, h)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                game.running = False
                return None
            if t < INPUT_DELAY:
                continue
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_UP, pygame.K_w):
                    selected = 0
                elif event.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_DOWN, pygame.K_s, pygame.K_TAB):
                    selected = 1
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    game.keys = pygame.key.get_pressed()
                    return (START, CRAWL)[selected]
            elif event.type == pygame.JOYHATMOTION:
                if event.value[0] < 0:
                    selected = 0
                elif event.value[0] > 0:
                    selected = 1
            elif event.type == pygame.JOYBUTTONDOWN:
                game.keys = pygame.key.get_pressed()
                return (START, CRAWL)[selected]
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                pos = _event_pos(event, (w, h))
                for i, rect in enumerate(buttons):
                    if rect.collidepoint(pos):
                        game.keys = pygame.key.get_pressed()
                        return (START, CRAWL)[i]
            elif event.type == pygame.MOUSEMOTION:
                for i, rect in enumerate(buttons):
                    if rect.collidepoint(event.pos):
                        selected = i

        dt = min(clock.get_time() / 1000.0, 0.1) or 0.016
        t += dt

        # ---- particles: embers rise all the time, sparks burst every so often ----
        particles.ambient(dt, w, h, ui.CORAL, rate=26.0)
        if t >= next_burst:
            next_burst = t + random.uniform(0.35, 0.8)
            x = random.uniform(w * 0.15, w * 0.85)
            y = random.uniform(h * 0.12, h * 0.5)
            color = random.choice((ui.GOLD, ui.CREAM, ui.CORAL))
            particles.spark(x, y, color, count=16, speed=210, life=0.9, size=3, gravity=180)
            if random.random() < 0.4:
                particles.ring(x, y, color, count=18, speed=170, life=0.7)
        particles.update(dt)
        shake.update(dt)

        # ---- frame ----
        ox, oy = shake.offset()
        window.fill((0, 0, 0))
        window.blit(snapshot, (ox, oy))
        ui.dim_overlay(window, int(215 * ui_fx.clamp(t / 0.6)))
        particles.draw(window, t)

        pop = ui_fx.ease_out_back(ui_fx.clamp(t / 0.6))
        panel_rect = box.copy()
        panel_rect.width = max(10, int(box.width * (0.82 + 0.18 * min(1.0, pop))))
        panel_rect.height = max(10, int(box.height * (0.82 + 0.18 * min(1.0, pop))))
        panel_rect.center = box.center
        ui.panel(window, panel_rect, (28, 18, 26, 238), ui.GOLD, 2, 16)

        if t > 0.35:
            head = max(18, int(box.height * 0.098))
            ui_fx.wave_text(window, "THE ABYSS RELEASES YOU", (box.centerx, box.top + int(box.height * 0.14)),
                            head, ui.GOLD, ui.WHITE, t, amp=2.5, center=True)
            sub = "DESCENT COMPLETE" if loop == 0 else f"LOOP {loop + 1} COMPLETE"
            ui_fx.text_alpha(window, sub, (box.centerx, box.top + int(box.height * 0.285)),
                             max(11, int(box.height * 0.045)), ui.CORAL, 255 * ui_fx.clamp((t - 0.35) / 0.4),
                             True, center=True)

        # stats count in one after another
        row_h = int(box.height * 0.1)
        y = box.top + int(box.height * 0.38)
        for i, (label, value) in enumerate(rows):
            appear = 0.9 + i * STAT_STAGGER
            if t < appear:
                continue
            a = ui_fx.clamp((t - appear) / 0.3)
            slide = int((1 - ui_fx.ease_out_cubic(a)) * 40)
            row = pygame.Rect(box.left + int(box.width * 0.18), y + i * (row_h + 8), int(box.width * 0.64), row_h)
            ui.panel(window, row.move(slide, 0), (40, 25, 34, int(220 * a)), (101, 56, 60), 1, 9)
            lab = ui.font(max(11, int(box.height * 0.042)), True).render(label, True, ui.MUTED)
            lab.set_alpha(int(255 * a))
            window.blit(lab, lab.get_rect(midleft=(row.left + 16 + slide, row.centery)))
            val_surf = ui.font(max(14, int(box.height * 0.058)), True).render(value, True, ui.CREAM)
            val_surf.set_alpha(int(255 * a))
            window.blit(val_surf, val_surf.get_rect(midright=(row.right - 16 + slide, row.centery)))

        # buttons
        if t > 0.9 + len(rows) * STAT_STAGGER:
            ready = t >= INPUT_DELAY
            for i, rect in enumerate(buttons):
                active = ready and i == selected
                accent = ui.GOLD if i == 1 else ui.CORAL
                glow = 0.5 + 0.5 * math.sin(t * 4.0) if active else 0.0
                fill = (92, 44, 52) if active else (48, 27, 36)
                ui.panel(window, rect, fill, accent if active else (112, 64, 66), 2 if active else 1, 10)
                title, hint = labels[i]
                ui.text_centered(window, title, (rect.centerx, rect.centery - rect.height * 0.12),
                                 max(12, int(rect.height * 0.36)), ui.CREAM if active else ui.WHITE, True)
                ui.text_centered(window, hint, (rect.centerx, rect.centery + rect.height * 0.27),
                                 max(9, int(rect.height * 0.2)), ui.MUTED if not active else ui.GOLD)
                if active:
                    ui_fx.aura(window, rect, accent, 0.4 + 0.4 * glow)

        pygame.display.flip()
        clock.tick(fps)
