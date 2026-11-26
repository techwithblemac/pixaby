"""
world_intro.py
==============
Two small cinematics that bracket every world:

WorldIntro   plays when a new world has finished loading
             * the screen is black, then an iris opens on the player
             * cinematic letterbox bars slide in, the camera pulls back from a
               close-up to the normal zoom
             * "WORLD 3" slides in with wide letter-spacing, the world's name
               drops in letter by letter and bounces, embers drift past
             * its biome tags + difficulty, then the objective is typed out so
               you know what the world expects *before* you can die to it
             * bars slide away, "GO!" pops, and the mission card slides in
             It is NOT blocking: the game loop keeps drawing the (frozen)
             world underneath and the intro paints over it.  Any key / click
             fast-forwards it.

play_cleared()
             a short blocking card when a world is beaten: time, kills, best
             combo, damage taken and a rank (S / A / B / C) that is stamped
             onto the card, with a shower of coins on a good run.  Shown right
             before the shop.

Both only draw and animate; the rules of the game are not touched.
"""

import math
import random
import time

import pygame

from . import ui_theme as ui
from . import ui_fx
from . import combat_fx

DURATION = 4.3                  # seconds, start to end
SKIP_AFTER = 0.6                # keys are ignored for this long (so the load-screen keypress doesn't skip it)
OUTRO = 0.8                     # the last stretch (bars leave, GO!, card slides in)

BIOME_COLORS = [                # first tag that matches wins
    ("lava", (255, 128, 50)), ("fire", (255, 128, 50)), ("ash", (255, 140, 70)),
    ("water", ui.BLUE), ("ice", (150, 215, 240)), ("overworld", ui.GREEN),
    ("grass", ui.GREEN), ("ruins", ui.GOLD), ("brick", (220, 130, 100)),
    ("dungeon", ui.CORAL), ("stone", (200, 180, 190)),
]


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


# ---------------------------------------------------------------------- #
# what world are we in?
# ---------------------------------------------------------------------- #
def world_info(game):
    """Number, title, tags and difficulty of the current level (cached per level)."""
    level = getattr(game, "level", 1)
    folder = getattr(game, "level_folder", "story")
    key = (folder, level)
    cached = getattr(game, "_world_info", None)
    if cached and cached.get("key") == key:
        return cached
    info = {"level": level, "key": key, "number": level if isinstance(level, int) else "?",
            "title": f"Level {level}" if isinstance(level, int) else "Custom World",
            "tags": [], "difficulty": 1, "description": ""}
    try:
        from ..level.selector import level_meta
        if folder == "story":
            meta = level_meta.load_metadata().get(str(level), {})
        else:
            # co-op, My Worlds and test levels describe themselves in the level's own _level_meta
            world = getattr(game, "world", None) or [{}]
            meta = dict(world[0].get("_level_meta", {})) if isinstance(world[0], dict) else {}
            if not meta.get("title"):
                meta["title"] = {"multiplayer": "Co-op", "user_worlds": "World"}.get(folder, "Test") + f" {level}"
            label = str(meta.get("difficulty", "")).upper()
            meta["difficulty"] = {"EASY": 1, "STANDARD": 3, "HARD": 4, "EXTREME": 5}.get(label, 1) \
                if not isinstance(meta.get("difficulty"), int) else meta["difficulty"]
        info["title"] = meta.get("title", info["title"])
        info["tags"] = list(meta.get("tags", []))
        info["difficulty"] = int(meta.get("difficulty", 1))
        info["description"] = meta.get("description", "")
        info["difficulty_label"] = level_meta.DIFFICULTY_LABELS.get(info["difficulty"], "")
    except Exception as err:
        print(f"[world_info] {err!r}")
    game._world_info = info
    return info


def biome_color(tags):
    lowered = [str(t).lower() for t in tags]
    for key, color in BIOME_COLORS:
        if any(key in t for t in lowered):
            return color
    return ui.CORAL


def _sfx(game, name):
    try:
        ui_fx.sfx(game.player, name)
    except Exception:
        pass


# ---------------------------------------------------------------------- #
# lettering helpers
# ---------------------------------------------------------------------- #
def _spaced(surface, txt, center, size, color, spacing, alpha=255, bold=True):
    """Text with adjustable letter-spacing (wide at first, tightening as it settles)."""
    f = ui.font(size, bold)
    imgs = [f.render(ch, True, color) for ch in txt]
    total = sum(i.get_width() for i in imgs) + spacing * (len(imgs) - 1)
    x = center[0] - total / 2
    for img in imgs:
        img.set_alpha(int(_clamp(alpha, 0, 255)))
        surface.blit(img, (int(x), int(center[1] - img.get_height() / 2)))
        x += img.get_width() + spacing


def _first_sentence(text):
    for end in (". ", "! "):
        if end in text:
            return text.split(end)[0] + end.strip()
    return text


# ---------------------------------------------------------------------- #
# the intro
# ---------------------------------------------------------------------- #
class WorldIntro:
    def __init__(self, game, quick=False):
        self.game = game
        self.quick = quick                       # a retry of the same world: short and sweet
        self.D = 1.9 if quick else DURATION
        self.OUT = 0.6 if quick else OUTRO
        self.info = world_info(game)
        self.objective = getattr(game, "objective", None)
        self.accent = biome_color(self.info["tags"])
        self.t = 0.0
        self.done = False
        self.particles = ui_fx.Particles()
        self._iris = None
        self._iris_size = None
        self._band = {}
        self._outro_started = False
        self._go_burst = False
        self._started_at = time.perf_counter()
        hud = getattr(game, "objective_hud", None)
        if hud is not None:
            hud.hidden = True
        for p in game.local_players:
            p._intro_zoom = p.target_zoom
        combat_fx.fx().reset_level()
        _sfx(game, "teleport")

    # ---------------- input ---------------- #
    def filter_events(self, events):
        """Eat key / click presses so they skip the intro instead of pressing buttons."""
        kept = []
        for event in events:
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.JOYBUTTONDOWN, pygame.FINGERDOWN):
                if self.t >= SKIP_AFTER:
                    self.fast_forward()
                continue
            kept.append(event)
        return kept

    def fast_forward(self):
        self.t = max(self.t, self.D - self.OUT)

    # ---------------- update ---------------- #
    def update(self, dt):
        if self.done:
            return
        self.t += min(dt, 0.1)
        game = self.game
        w, h = game.window.get_size()

        # camera pull-back: close-up -> normal zoom
        u = ui_fx.ease_out_cubic(self.t / (self.D * 0.62))
        for p in game.local_players:
            target = getattr(p, "_intro_zoom", p.target_zoom)
            p.zoom = target * (1.0 + 0.55 * (1.0 - u))

        self.particles.ambient(dt, w, h, self.accent, rate=16)
        self.particles.update(min(dt, 0.1))

        if self.t >= self.D - self.OUT and not self._outro_started:
            self._outro_started = True
            hud = getattr(game, "objective_hud", None)
            if hud is not None:
                hud.hidden = False
                hud.restart_slide()
            _sfx(game, "boost")
        if self.t >= self.D - self.OUT * 0.55 and not self._go_burst:
            self._go_burst = True
            for p in game.local_players:
                cx, cy = getattr(p, "view_rect", game.window.get_rect()).center
                self.particles.ring(cx, cy, self.accent, count=28, speed=360, life=0.7, size=3)
                self.particles.spark(cx, cy, ui.CREAM, count=24, speed=300, life=0.8, size=3)
        if self.t >= self.D:
            self.finish()

    def finish(self):
        if self.done:
            return
        self.done = True
        game = self.game
        for p in game.local_players:
            p.zoom = getattr(p, "_intro_zoom", p.target_zoom)
        hud = getattr(game, "objective_hud", None)
        if hud is not None and hud.hidden:
            hud.hidden = False
            hud.restart_slide()
        # The world's clock starts now (not during loading / the join screen / this intro),
        # so survival timers and the time rank begin at 00:00 when you can actually move.
        game.start_ticks = pygame.time.get_ticks()
        game.pause_total = 0

    # ---------------- draw ---------------- #
    def draw(self, window):
        if self.done:
            return
        w, h = window.get_size()
        t = self.t
        outro = _clamp((t - (self.D - self.OUT)) / self.OUT)

        # 1) dark band behind the lettering (fades in, then out)
        text_alpha = _clamp((t - 0.35) / 0.4) * (1.0 - _clamp(outro * 1.6))
        if text_alpha > 0.01:
            band_h = int(h * 0.34)
            key = (w, band_h)
            band = self._band.get(key)
            if band is None:
                band = pygame.Surface((w, band_h), pygame.SRCALPHA)
                for y in range(band_h):
                    e = 1.0 - abs(y - band_h / 2) / (band_h / 2)
                    pygame.draw.line(band, (10, 8, 14, int(190 * _clamp(e * 1.6))), (0, y), (w, y))
                self._band[key] = band
            band.set_alpha(int(255 * text_alpha))
            window.blit(band, (0, int(h * 0.47 - band_h / 2)))

        self.particles.draw(window, t)

        # 2) lettering
        center_x = w // 2
        if text_alpha > 0.01:
            slide = 1.0 - ui_fx.ease_out_cubic((t - 0.5) / 0.9)
            if self.quick:
                _spaced(window, "TRY AGAIN", (center_x, int(h * 0.43)), max(18, int(h * 0.06)), self.accent,
                        spacing=4 + int(30 * slide), alpha=255 * text_alpha)
                ui.text_centered(window, f"WORLD {self.info['number']}  -  {self.info['title'].upper()}",
                                 (center_x, int(h * 0.50)), max(12, int(h * 0.03)), ui.CREAM, True)
                text_alpha = 0.0
        if text_alpha > 0.01:
            _spaced(window, f"WORLD  {self.info['number']}", (center_x, int(h * 0.355)), max(14, int(h * 0.036)),
                    self.accent, spacing=6 + int(60 * slide), alpha=255 * text_alpha * _clamp((t - 0.5) / 0.5))
            title = self.info["title"].upper()
            size = max(24, int(h * 0.105))
            while ui.font(size, True).size(title)[0] > w * 0.92 and size > 16:
                size -= 2
            if t > 0.95:
                ui_fx.drop_text(window, title, (center_x, int(h * 0.47)), size, ui.CREAM, t - 0.95,
                                stagger=0.055, drop=int(h * 0.12), sway_t=t, glow_color=self.accent)
            if t > 1.8:
                a = 255 * text_alpha * _clamp((t - 1.8) / 0.5)
                tags = "   -   ".join(str(x).upper() for x in self.info["tags"][:4]) or "UNCHARTED"
                f = ui.font(max(11, int(h * 0.024)), True)
                img = f.render(tags, True, ui.MUTED)
                img.set_alpha(int(a))
                window.blit(img, img.get_rect(center=(center_x, int(h * 0.555))))
                # difficulty pips
                diff = max(1, min(5, int(self.info.get("difficulty", 1))))
                pip = max(6, int(h * 0.012))
                px = center_x - (5 * pip * 2.4) / 2
                for i in range(5):
                    col = self.accent if i < diff else (60, 44, 52)
                    pts = [(px + i * pip * 2.4 + pip, h * 0.59 - pip), (px + i * pip * 2.4 + pip * 2, h * 0.59),
                           (px + i * pip * 2.4 + pip, h * 0.59 + pip), (px + i * pip * 2.4, h * 0.59)]
                    pygame.draw.polygon(window, col, pts)
                label = self.info.get("difficulty_label", "")
                if label:
                    ui.text_centered(window, label, (center_x, int(h * 0.59 + pip * 2.6)), max(10, int(h * 0.02)),
                                     ui.MUTED, True)
            if t > 2.3 and self.objective is not None:
                self._draw_objective_line(window, w, h, text_alpha)

        # 3) cinematic bars
        bar_in = ui_fx.ease_out_cubic((t - 0.1) / 0.6)
        bar_out = ui_fx.ease_in_out(outro)
        bar_h = int(h * 0.12 * bar_in * (1.0 - bar_out))
        if bar_h > 0:
            pygame.draw.rect(window, (6, 5, 9), (0, 0, w, bar_h))
            pygame.draw.rect(window, (6, 5, 9), (0, h - bar_h, w, bar_h))
            pygame.draw.line(window, self.accent, (0, bar_h), (w, bar_h), 1)
            pygame.draw.line(window, self.accent, (0, h - bar_h), (w, h - bar_h), 1)

        # 4) iris from black
        iris = _clamp(t / 1.0)
        if iris < 1.0:
            if self._iris is None or self._iris_size != (w, h):
                self._iris = pygame.Surface((w, h), pygame.SRCALPHA)
                self._iris_size = (w, h)
            self._iris.fill((0, 0, 0, 255))
            radius = int(math.hypot(w, h) * 0.5 * ui_fx.ease_in_out(iris))
            if radius > 0:
                pygame.draw.circle(self._iris, (0, 0, 0, 0), (w // 2, int(h * 0.5)), radius)
                pygame.draw.circle(self._iris, (*self.accent, 255), (w // 2, int(h * 0.5)), radius + 5, 3)
            window.blit(self._iris, (0, 0))

        # 5) "GO!" + skip hint
        if outro > 0:
            q = _clamp(outro * 1.4)
            go = int(max(30, h * 0.16) * (0.6 + 0.8 * ui_fx.ease_out_back(q)))
            a = 255 * (1.0 - _clamp((outro - 0.6) / 0.4))
            ui_fx.text_alpha(window, "GO!", (center_x, int(h * 0.42)), go, ui.CREAM, a, True, center=True)
        elif t > 1.2 and not self.done:
            a = 90 + 90 * math.sin(t * 4)
            ui_fx.text_alpha(window, "PRESS ANY KEY TO SKIP", (center_x, int(h * 0.93)), max(10, int(h * 0.02)),
                             ui.MUTED, a, False, center=True, shadow=False)

    def _draw_objective_line(self, window, w, h, text_alpha):
        obj = self.objective
        text = _first_sentence(getattr(obj, "brief", "") or "")
        if not text:
            return
        shown = int((self.t - 2.3) * 42)                      # typewriter
        text = text[:max(0, shown)]
        badge = getattr(obj, "badge", "OBJECTIVE")
        f_badge = ui.font(max(11, int(h * 0.022)), True)
        f_text = ui.font(max(12, int(h * 0.03)), False)
        bimg = f_badge.render(badge, True, ui.INK)
        timg = f_text.render(text, True, ui.WHITE)
        total = bimg.get_width() + 24 + 12 + timg.get_width()
        x = w // 2 - total // 2
        y = int(h * 0.66)
        brect = pygame.Rect(x, y - bimg.get_height() // 2 - 3, bimg.get_width() + 20, bimg.get_height() + 6)
        pygame.draw.rect(window, self.accent, brect, border_radius=7)
        window.blit(bimg, bimg.get_rect(center=brect.center))
        timg.set_alpha(int(255 * text_alpha))
        window.blit(timg, timg.get_rect(midleft=(brect.right + 12, y)))
        if shown < len(_first_sentence(getattr(obj, "brief", "") or "")) and int(self.t * 3) % 2 == 0:
            cur = timg.get_rect(midleft=(brect.right + 12, y)).right + 3
            pygame.draw.rect(window, ui.CREAM, (cur, y - f_text.get_height() // 2 + 3, 3, f_text.get_height() - 6))


# ---------------------------------------------------------------------- #
# world cleared card (blocking)
# ---------------------------------------------------------------------- #
def _rank(game):
    humans = [p for p in getattr(game, "player_slots", []) if getattr(p, "type", "") == "player"
              and p in (getattr(game, "local_players", None) or [])]
    humans = humans or list(getattr(game, "local_players", []) or [game.player])
    damage = sum(float(getattr(p, "damage_this_level", 0.0)) for p in humans)
    hp = sum(float(getattr(p, "max_health", 1) or 1) for p in humans)
    frac = damage / max(1.0, hp)
    if damage <= 0.5:
        return "S", ui.GOLD, damage
    if frac < 0.25:
        return "A", ui.GREEN, damage
    if frac < 0.6:
        return "B", ui.BLUE, damage
    return "C", ui.MUTED, damage


def play_cleared(game):
    """Blocking 'WORLD CLEARED' card. Any key / click / button continues."""
    try:
        _play_cleared(game)
    except Exception as err:                 # a cosmetic card must never block the game
        print(f"[world cleared] skipped: {err!r}")


def _play_cleared(game):
    window = game.window
    snapshot = window.copy().convert()
    clock = game.clock
    info = getattr(game, "_world_info", None) or world_info(game)
    accent = biome_color(info.get("tags", []))
    fx = combat_fx.fx()
    rank, rank_color, damage = _rank(game)
    objective = getattr(game, "objective", None)
    reward = (getattr(objective, "cfg", None) or {}).get("reward") or {}

    stats = [
        ("TIME", getattr(game, "game_time", "--:--"), None),
        ("ENEMIES SLAIN", fx.kills_this_world, 0),
        ("BEST COMBO", f"x{fx.best_combo}" if fx.best_combo else "-", None),
        ("DAMAGE TAKEN", int(damage), 0),
    ]
    particles = ui_fx.Particles()
    shake = ui_fx.Shake()
    t = 0.0
    stamped = False
    min_time = 1.7
    _sfx(game, "win")

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                game.running = False
                return
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.JOYBUTTONDOWN, pygame.FINGERDOWN):
                if t >= min_time:
                    game.keys = pygame.key.get_pressed()
                    return
        dt = min(clock.get_time() / 1000.0, 0.1) or 0.016
        t += dt
        w, h = window.get_size()

        shake.update(dt)
        ox, oy = shake.offset()
        window.fill((0, 0, 0))
        window.blit(snapshot, (ox, oy))
        ui.dim_overlay(window, int(200 * _clamp(t / 0.5)))

        box = pygame.Rect(0, 0, min(w - 20, int(w * 0.5)), min(h - 20, int(h * 0.62)))
        box.center = (w // 2, h // 2)
        p = ui_fx.ease_out_back(t / 0.55)
        scaled = box.copy()
        scaled.width = max(10, int(box.width * (0.8 + 0.2 * min(1.0, p))))
        scaled.height = max(10, int(box.height * (0.8 + 0.2 * min(1.0, p))))
        scaled.center = box.center
        ui.panel(window, scaled, (28, 18, 26, 235), accent, 2, 16)

        if t > 0.3:
            head = max(18, int(box.height * 0.1))
            ui_fx.wave_text(window, "WORLD CLEARED", (box.centerx, box.top + int(box.height * 0.13)), head,
                            ui.CREAM, ui.WHITE, t, amp=2.0, center=True)
            ui.text_centered(window, info.get("title", "").upper(), (box.centerx, box.top + int(box.height * 0.24)),
                             max(11, int(box.height * 0.05)), accent, True)

        # stats count in one after another
        row_h = int(box.height * 0.105)
        y = box.top + int(box.height * 0.34)
        for i, (label, value, _) in enumerate(stats):
            q = _clamp((t - 0.6 - i * 0.22) / 0.35)
            if q <= 0:
                continue
            shown = value
            if isinstance(value, int):
                shown = int(value * ui_fx.ease_out_cubic(q))
            lx = box.left + int(box.width * 0.12) - int((1 - q) * 40)
            ui_fx.text_alpha(window, label, (lx, y), max(11, int(box.height * 0.045)), ui.MUTED, 255 * q, True)
            ui_fx.text_alpha(window, str(shown), (box.left + int(box.width * 0.5), y),
                             max(12, int(box.height * 0.052)), ui.WHITE, 255 * q, True)
            y += row_h

        # the rank stamp slams down
        stamp_at = 0.6 + len(stats) * 0.22 + 0.15
        if t >= stamp_at:
            q = _clamp((t - stamp_at) / 0.22)
            size = int(box.height * (0.34 - 0.12 * ui_fx.ease_out_cubic(q) + (0.18 * (1 - q))))
            cx, cy = box.right - int(box.width * 0.2), box.top + int(box.height * 0.6)
            ui_fx.text_alpha(window, rank, (cx, cy), max(20, size), rank_color, 255 * _clamp(q * 2.5), True, center=True)
            if q >= 1.0:
                ring_r = int(box.height * 0.2)
                pygame.draw.circle(window, rank_color, (cx, cy), ring_r, 3)
            ui.text_centered(window, "RANK", (cx, cy - int(box.height * 0.25)), max(10, int(box.height * 0.04)),
                             ui.MUTED, True)
            if not stamped:
                stamped = True
                shake.kick(10 if rank in ("S", "A") else 6)
                _sfx(game, "hit_3")
                particles.ring(cx, cy, rank_color, count=26, speed=280, life=0.6, size=3)
                particles.spark(cx, cy, rank_color, count=22, speed=240, life=0.7, size=3)
                if rank == "S":
                    particles.burst_coins(cx, cy, "gold", 14)
                    ui_fx.sfx(game.player, "coin")
            if rank == "S" and q >= 1.0:
                ui.text_centered(window, "FLAWLESS", (cx, cy + int(box.height * 0.22)),
                                 max(11, int(box.height * 0.045)), ui.GOLD, True)

        if reward and t > stamp_at + 0.4:
            text = "   ".join(f"+{n} {cur.upper()}" for cur, n in reward.items())
            ui.text_centered(window, f"REWARD   {text}", (box.centerx, box.bottom - int(box.height * 0.2)),
                             max(12, int(box.height * 0.05)), ui_fx.COIN_COLORS.get(next(iter(reward)), ui.GOLD), True)

        if t >= min_time:
            a = 120 + 120 * math.sin(t * 4)
            ui_fx.text_alpha(window, "PRESS ANY KEY  -  VISIT THE SHOP", (box.centerx, box.bottom - int(box.height * 0.08)),
                             max(10, int(box.height * 0.04)), ui.CREAM, a, True, center=True, shadow=False)

        particles.update(dt)
        particles.draw(window, t)
        pygame.display.flip()
        clock.tick(getattr(game, "FPS", 60))
