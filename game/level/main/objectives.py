"""
objectives.py
=============
How a level is won. Replaces the old hard-coded "no enemies left -> next
level" test in game.py with one small object per level:

    clear_all   kill every enemy (the old behaviour, and the default)
    survival    hold out for ``duration`` seconds against escalating waves
    exit        reach an ``exit`` door (optionally locked until enemies are dead)
    boss        kill the boss: one of the level's own enemies, promoted
    final       the last boss; a bigger boss, then the run ends

A level picks its objective with a ``_objective`` entry inside its first
``entity settings`` block (the same place ``_level_meta`` lives), e.g.

    "_objective": {"type": "survival", "duration": 150, "max_alive": 20}
    "_objective": {"type": "boss", "boss": {"name": "Warrior", "health_mult": 6}}
    "_objective": {"type": "exit", "lock": "clear"}

No ``_objective`` means clear_all, so every existing level keeps working.

Performance rules this file follows
-----------------------------------
* Win checks run 4 times a second, not every frame (``CHECK_INTERVAL``).
* Per-frame work is a few comparisons; nothing allocates in ``update``.
* Enemy counts use ``hostile_count(game)`` = ``len(enemy_list)`` minus charmed allies (O(1)); lists are never scanned per frame.
* Survival/boss spawns are *queued and trickled* (one enemy per ``spawn_gap``)
  so a wave never makes a single-frame spike, and are capped by ``max_alive``
  (lower on LOW_SPEC_MODE devices).
* Spawn positions come from points the level author already placed enemies on,
  so nothing can appear inside a wall, and the farthest-from-players one is
  preferred so enemies don't pop in on screen.
* HUD text is rendered once and re-rendered only when the words change.
"""

import random
import pygame

from ...entities.entities import Enemy
from ...scripts.cache import cache_font
from ...scripts import achievements
from ...scripts.death_rules import humans as _humans
from ...data.shop_items import WALLET_ATTR
from ...settings import Settings
from ...ui import ui_theme as ui
from .. import progression

CHECK_INTERVAL = 0.25            # seconds between win-condition checks
LOW_SPEC_FACTOR = 0.6            # enemy caps shrink on weak devices


class ObjectiveUnavailable(Exception):
    """The level lacks what this objective needs; fall back to clear_all."""


# ---------------------------------------------------------------------- #
# helpers
# ---------------------------------------------------------------------- #

def hostile_count(game):
    """Enemies still against the players: the enemy list minus allies (befriended with a charm)."""
    return len(game.enemy_list) - getattr(game, "friend_count", 0)


def hostile_list(game):
    """The enemies still against the players (a scan, only used where the count is small)."""
    if not getattr(game, "friend_count", 0):
        return game.enemy_list
    return [e for e in game.enemy_list if not getattr(e, "is_friend", False)]


def _players(game):
    return getattr(game, "local_players", None) or [game.player]


def _cap(value):
    return max(4, int(value * (LOW_SPEC_FACTOR if Settings.LOW_SPEC_MODE else 1.0)))


def _harvest(game, exclude=None):
    """Safe spawn positions and the enemy mix, taken from what the author placed."""
    slots, roster = [], []
    for enemy in game.enemy_list:
        if enemy is exclude:
            continue
        slots.append((enemy.rect.x, enemy.rect.y))
        roster.append((enemy.name, enemy.color))
    for point in game.spawn_points:
        slots.append((point.x, point.y))
        roster.extend(tuple(entry) for entry in point.entities)
    return slots, roster


def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _sound(game, name):
    """Play a sound; a missing sound or mixer must never break an objective."""
    try:
        from ...scripts.sounds import playit
        playit(name, game.player)
    except Exception:
        pass


def _shake_players(game, frames=20, intensity=8):
    for player in _players(game):
        player.shake_frames = max(getattr(player, "shake_frames", 0), frames)
        player.shake_intensity = max(getattr(player, "shake_intensity", 0), intensity)


def _mmss(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02}:{seconds % 60:02}"


def _spawn(game, x, y, name, color):
    game.enemy_list.append(Enemy(x, y, 50, 50, name, color, game=game))
    game._draw_list_dirty = True
    game._entities_dirty = True


def _farthest_slot(game, slots, tries=8):
    """Of a few random slots, the one farthest from every player (no pop-in)."""
    centres = [p.rect.center for p in _players(game)]
    sample = random.sample(slots, min(tries, len(slots)))
    return max(sample, key=lambda s: min(_dist2(s, c) for c in centres))


# ---------------------------------------------------------------------- #
# base
# ---------------------------------------------------------------------- #

class Objective:
    kind = "clear_all"
    owns_spawning = False       # True: the level's Spawn_Points stay quiet

    # What the HUD shows (ui/objective_hud.py). Subclasses fill these in.
    badge = "OBJECTIVE"         # short tag on the mission card
    brief = ""                  # the objective in plain words: "what is expected of me"

    def __init__(self, game, cfg):
        self.game = game
        self.cfg = cfg
        self._since_check = 0.0
        self._hud_key = None
        self._hud_surf = None

    # ---- called by game.py every frame (keep cheap) ---- #
    def update(self, dt):
        pass

    def check(self):
        """True once the level is won. Throttled to CHECK_INTERVAL."""
        self._since_check += self.game.dt
        if self._since_check < CHECK_INTERVAL:
            return False
        self._since_check = 0.0
        return self._evaluate()

    def _evaluate(self):
        return False

    def on_complete(self):
        game = self.game
        self._pay_reward()
        progression.level_won(game)     # story: save + next level (shop first); one-off levels replay

    def _pay_reward(self):
        """Optional ``"reward": {"pearl": 1}`` in the level's _objective: paid to each standing player."""
        reward = self.cfg.get("reward")
        if not reward:
            return
        text = ", ".join(f"+{n} {cur}" for cur, n in reward.items())
        for player in _humans(self.game):
            if player.dead or player.death:
                continue
            for currency, amount in reward.items():
                attr = WALLET_ATTR.get(currency)
                if attr:
                    setattr(player, attr, getattr(player, attr, 0) + amount)
        achievements.tracker().toasts.append([f"Floor reward  ({text})", 4.0])

    def exit_open(self):
        """May exit doors end the level right now?"""
        return True

    # ---- HUD ---- #
    # The old one-line text HUD sat behind the SPECTATE / VIEW buttons. The
    # mission card, boss bar, pointer and banners are now drawn by
    # ui/objective_hud.py, which asks the objective for these four things:
    def progress(self):
        """(0..1, "label") for the card's progress bar, or None."""
        return None

    def status(self):
        """("live status line", colour or None), or None."""
        return None

    def target(self):
        """(world_x, world_y, "LABEL", colour) the pointer should aim at, or None."""
        return None

    def announce(self, text, color=None, sub=None):
        """Flash a centre-screen banner (wave start, exit opened, boss phase ...)."""
        hud = getattr(self.game, "objective_hud", None)
        if hud is not None:
            hud.event(text, color, sub)

    def hud_text(self):
        return ""

    def draw_hud(self, window, view_rect):
        """Kept for compatibility; see ui/objective_hud.py."""
        pass


# ---------------------------------------------------------------------- #
# clear_all
# ---------------------------------------------------------------------- #

class ClearAll(Objective):
    kind = "clear_all"
    badge = "CLEAR"
    brief = "Defeat every enemy on this floor to open the way down."

    def __init__(self, game, cfg):
        super().__init__(game, cfg)
        self.total = max(1, self._left())
        self._warned = False

    def _unspawned(self):
        return sum(max(0, p.limit - p.created) for p in self.game.spawn_points)

    def _left(self):
        return hostile_count(self.game) + self._unspawned()

    def _evaluate(self):
        game = self.game
        left = hostile_count(game)
        if not self._warned and 0 < left <= 3 and self.total >= 6 and not self._unspawned():
            self._warned = True
            self.announce("FINAL FOES", (255, 202, 80), f"{left} left - follow the arrows")
            _sound(game, "incoming")
        return hostile_count(game) == 0 and game.points_done == len(game.spawn_points)

    def progress(self):
        left = self._left()
        self.total = max(self.total, left)
        done = self.total - left
        return done / self.total, f"{done} / {self.total} ENEMIES SLAIN"

    def status(self):
        left = self._left()
        if left == 0:
            return "ALL CLEAR!", (108, 201, 117)
        if left <= 3 and not self._unspawned():
            return f"LAST {left} - HUNT THEM DOWN", (255, 202, 80)
        return f"{left} ENEMIES REMAIN", None

    def target(self):
        enemies = hostile_list(self.game)
        if not enemies or len(enemies) > 3 or self._unspawned():
            return None
        centre = _players(self.game)[0].rect.center
        nearest = min(enemies, key=lambda e: _dist2(e.rect.center, centre))
        return nearest.rect.centerx, nearest.rect.centery, "ENEMY", (255, 112, 92)

    def hud_text(self):
        return f"ENEMIES LEFT: {hostile_count(self.game)}"


# ---------------------------------------------------------------------- #
# survival
# ---------------------------------------------------------------------- #

class Survival(Objective):
    kind = "survival"
    owns_spawning = True
    badge = "SURVIVE"

    def __init__(self, game, cfg):
        super().__init__(game, cfg)
        self.duration = int(cfg.get("duration", 150))
        # Never carry more enemies than the level already shipped with, so
        # survival waves *replace* kills instead of adding load (FPS).
        self.max_alive = _cap(cfg["max_alive"]) if "max_alive" in cfg \
            else min(32, max(12, hostile_count(game)))
        self.wave_interval = float(cfg.get("wave_interval", 10))
        self.wave_start = int(cfg.get("wave_size", 3))
        self.wave_growth = int(cfg.get("wave_growth", 1))
        self.wave_cap = int(cfg.get("wave_cap", 8))
        self.spawn_gap = float(cfg.get("spawn_gap", 0.6))
        self.next_wave_at = float(cfg.get("first_wave", 6))
        self.wave = 0
        self.pending = 0
        self.cooldown = 0.0
        self.slots, self.roster = _harvest(game)
        if not self.slots or not self.roster:
            raise ObjectiveUnavailable("survival needs authored enemies or spawn points to copy")
        self.brief = (f"Hold out for {_mmss(self.duration)}. Waves arrive faster and bigger - "
                      f"keep moving, keep fighting.")
        self._warned_end = False

    def update(self, dt):
        game = self.game
        if not self._warned_end and self.duration - game.elapsed_seconds <= 10 and game.elapsed_seconds > 0:
            self._warned_end = True
            self.announce("10 SECONDS LEFT", (255, 202, 80), "Almost there - don't die now")
            _sound(game, "tick")
        if game.elapsed_seconds >= self.next_wave_at:
            self.wave += 1
            size = min(self.wave_cap, self.wave_start + self.wave_growth * (self.wave - 1))
            self.announce(f"WAVE {self.wave}", (100, 170, 215), f"{size} enemies incoming")
            _sound(game, "incoming")
            self.pending = min(self.max_alive, self.pending + size)
            # waves come a little faster as the clock runs
            self.next_wave_at += max(4.0, self.wave_interval - 0.5 * (self.wave - 1))

        self.cooldown -= dt
        if self.pending and self.cooldown <= 0 and hostile_count(game) < self.max_alive:
            x, y = _farthest_slot(game, self.slots)
            name, color = random.choice(self.roster)
            _spawn(game, x, y, name, color)
            self.pending -= 1
            self.cooldown = self.spawn_gap

    def _evaluate(self):
        return self.game.elapsed_seconds >= self.duration

    def exit_open(self):
        return False            # an exit door must not skip the survival timer

    def progress(self):
        done = min(self.duration, self.game.elapsed_seconds)
        left = max(0, self.duration - done)
        return done / max(1, self.duration), f"{_mmss(left)} LEFT   -   WAVE {self.wave}"

    def status(self):
        if self.pending:
            return "ENEMIES INCOMING!", (255, 112, 92)
        nxt = int(self.next_wave_at - self.game.elapsed_seconds)
        return (f"NEXT WAVE IN {max(0, nxt)}s", None)

    def hud_text(self):
        left = max(0, self.duration - self.game.elapsed_seconds)
        return f"SURVIVE  {left // 60:02}:{left % 60:02}   WAVE {self.wave}"


# ---------------------------------------------------------------------- #
# exit
# ---------------------------------------------------------------------- #

class Exit(Objective):
    kind = "exit"
    badge = "ESCAPE"

    def __init__(self, game, cfg):
        super().__init__(game, cfg)
        self.lock = str(cfg.get("lock", "none")).lower()
        doors = [d for d in game.doors if getattr(d, "kind", None) == "exit"]
        if not doors:
            raise ObjectiveUnavailable("exit objective but the level has no exit door")
        self.door = doors[0]
        self.total = max(1, hostile_count(game))
        self._was_open = self.exit_open()
        self.brief = ("Find the skull-gated crypt door and step through it." if self.lock != "clear" else
                      "Defeat every enemy to unseal the crypt door, then step through it.")

    def exit_open(self):
        return self.lock != "clear" or hostile_count(self.game) == 0

    def update(self, dt):
        opened = self.exit_open()
        if opened and not self._was_open:
            self.announce("THE EXIT IS OPEN", (108, 201, 117), "Reach the crypt door!")
            _sound(self.game, "open")
        self._was_open = opened

    def progress(self):
        if self.lock != "clear":
            return None
        left = hostile_count(self.game)
        self.total = max(self.total, left)
        done = self.total - left
        return done / self.total, f"{done} / {self.total} ENEMIES SLAIN"

    def status(self):
        if self.exit_open():
            return "THE EXIT IS OPEN - GO!", (108, 201, 117)
        return f"SEALED - {hostile_count(self.game)} ENEMIES LEFT", (255, 112, 92)

    def target(self):
        x, y = self.door.rect.center
        if self.exit_open():
            return x, y, "EXIT", (108, 201, 117)
        return x, y, "SEALED", (255, 112, 92)

    def hud_text(self):
        if self.exit_open():
            return "REACH THE EXIT"
        return f"EXIT LOCKED - ENEMIES LEFT: {hostile_count(self.game)}"


# ---------------------------------------------------------------------- #
# boss / final
# ---------------------------------------------------------------------- #

class Boss(Objective):
    kind = "boss"
    owns_spawning = False
    badge = "BOSS"
    DEFAULTS = {"name": "Warrior", "health_mult": 6.0, "attack_mult": 1.4,
                "phases": [0.66, 0.33], "minions": 3}
    ENRAGE = 1.15               # attack power x this at every phase

    def __init__(self, game, cfg):
        super().__init__(game, cfg)
        spec = {**self.DEFAULTS, **cfg.get("boss", {})}
        # an enemy marked "Is a boss" in the Entity Editor wins; otherwise the usual matching-name rule
        marked = [e for e in hostile_list(game) if getattr(e, "mods", None) and e.mods.get("boss")]
        pool = marked or [e for e in hostile_list(game) if e.name == spec["name"]] or hostile_list(game)
        if not pool:
            raise ObjectiveUnavailable("boss objective but the level has no enemies to promote")

        # The boss is the matching enemy farthest from where players start, so
        # it waits at the far end of the level and its position is known-good.
        starts = [tuple(p) for p in (game.points or [[0, -64]])]
        self.boss = max(pool, key=lambda e: min(_dist2(e.rect.topleft, s) for s in starts))
        if self.boss in marked and "health_mult" not in cfg.get("boss", {}):
            spec["health_mult"] = 1.0          # the author already sized this boss in the Entity Editor
        if self.boss in marked and "attack_mult" not in cfg.get("boss", {}):
            spec["attack_mult"] = 1.0
        self.boss.health *= spec["health_mult"]
        self.boss.max_health = self.boss.health
        self.boss.attack_power *= spec["attack_mult"]
        self.boss.is_boss = True

        self.thresholds = sorted(spec["phases"], reverse=True)
        self.minions = int(spec["minions"])
        # Room for the summoned minions on top of what the level started with
        self.max_alive = _cap(cfg["max_alive"]) if "max_alive" in cfg \
            else min(36, max(12, hostile_count(game) + self.minions))
        self.phase = 0
        title = getattr(self.boss, "boss_title", "")
        self.label = f"BOSS: {title.upper()}" if title else f"BOSS: {self.boss.name.upper()}"
        self.slots, self.roster = _harvest(game, exclude=self.boss)
        self.brief = (f"Slay the {self.boss.name}. It grows stronger as it weakens "
                      f"and calls minions at every phase.")
        if self.kind == "final":
            self.brief = f"Defeat the {self.boss.name}. Survive this, and the descent ends."

    def update(self, dt):
        boss = self.boss
        if self.phase < len(self.thresholds) and 0 < boss.health <= boss.max_health * self.thresholds[self.phase]:
            self.phase += 1
            boss.attack_power *= self.ENRAGE
            self.announce(f"PHASE {self.phase + 1}", (224, 78, 74), f"{getattr(boss, 'boss_title', '') or 'The ' + boss.name} is enraged - minions incoming!")
            _sound(self.game, "incoming")
            _shake_players(self.game, 24, 9)
            self._summon()

    def _summon(self):
        """Phase change: call minions in from the points nearest the boss."""
        game = self.game
        if not self.slots or not self.roster:
            return
        near = sorted(self.slots, key=lambda s: _dist2(s, self.boss.rect.topleft))[:6]
        for _ in range(self.minions):
            if hostile_count(game) >= self.max_alive:
                break
            x, y = random.choice(near)
            name, color = random.choice(self.roster)
            _spawn(game, x, y, name, color)

    def _evaluate(self):
        boss = self.boss
        return boss.dead or getattr(boss, "death", False) or boss.health <= 0

    def exit_open(self):
        return False

    # the boss bar itself is drawn by ui/objective_hud.py (it reads .boss, .label,
    # .phase and .thresholds), under the button row instead of behind it
    def status(self):
        minions = max(0, hostile_count(self.game) - 1)
        phase = f"PHASE {self.phase + 1} OF {len(self.thresholds) + 1}"
        return (f"{phase}  -  {minions} MINIONS" if minions else phase), (255, 112, 92)

    def target(self):
        boss = self.boss
        if boss.dead or getattr(boss, "death", False):
            return None
        return boss.rect.centerx, boss.rect.centery, (getattr(boss, 'boss_title', '') or boss.name).upper(), (224, 78, 74)

    def hud_text(self):
        return f"{self.label}   PHASE {self.phase + 1}"


class Final(Boss):
    kind = "final"
    badge = "FINAL BOSS"
    DEFAULTS = {"name": "Warrior", "health_mult": 8.0, "attack_mult": 1.6,
                "phases": [0.75, 0.5, 0.25], "minions": 4}

    def on_complete(self):
        """The ending: celebration card, then Return to start or Crawl again (see level/progression.py).

        Normally this is level 10, the last story level. On any other folder the final
        boss is just another one-off level, so progression treats it like one.
        """
        progression.level_won(self.game)


# ---------------------------------------------------------------------- #
# factory
# ---------------------------------------------------------------------- #

OBJECTIVES = {
    "clear_all": ClearAll,
    "survival": Survival,
    "exit": Exit,
    "boss": Boss,
    "final": Final,
}


def make_objective(game):
    """Build the objective for the level that just loaded (never raises)."""
    settings = (getattr(game, "settings", None) or {}).get("entity") or {}
    cfg = settings.get("_objective") or {}
    kind = str(cfg.get("type", "clear_all")).lower()
    cls = OBJECTIVES.get(kind)
    if cls is None:
        print(f"[objective] unknown type {kind!r}; using clear_all")
        cls = ClearAll
    try:
        return cls(game, cfg)
    except ObjectiveUnavailable as why:
        print(f"[objective] {why}; falling back to clear_all")
    except Exception as err:                         # a bad config must never crash a level load
        print(f"[objective] could not build {kind!r} ({err!r}); falling back to clear_all")
    return ClearAll(game, {})
