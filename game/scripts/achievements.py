"""
achievements.py
===============
Tracks the feats listed in data/achievements.py, pays the rewards and queues
the on-screen toasts.

Cheap by design: kills only push a timestamp, everything else is checked
once when a floor is completed; the save file is written only when
something is unlocked or a floor ends (never per frame / per kill).
Any file error is swallowed, because achievements must never crash a run.

Progress API (used by ui/achievements_screen.py):
    tracker().progress(id)     -> (current, goal)        goal 1 for yes/no feats
    tracker().all_entries()    -> [dict(...)]            one per achievement, window-ready
    tracker().unlocked_at      -> {id: epoch seconds}    0 for feats earned before timestamps existed

Counters (kills, revives, coins spent ...) are persisted in achievements.json
next to the unlocked flags, so progress survives restarts.
"""

import json
import os
import time

import pygame

from ..data import achievements as A
from ..data.shop_items import WALLET_ATTR
from . import paths

SAVE_PATH = paths.save_file("achievements.json")
TOAST_SECONDS = 4.0
MAX_TOASTS = 3
_BY_ID = {a["id"]: a for a in A.ACHIEVEMENTS}
_COUNTER_FEATS = {}                                   # counter -> [ids that unlock from it]
for _a in A.ACHIEVEMENTS:
    if _a.get("counter") and _a.get("goal"):
        _COUNTER_FEATS.setdefault(_a["counter"], []).append(_a["id"])


class Tracker:
    def __init__(self, path=SAVE_PATH):
        self.path = path
        self.unlocked = {}          # id -> True
        self.unlocked_at = {}       # id -> epoch seconds
        self.counters = {}          # name -> number (persisted)
        self.seen = set()           # unlocked ids the player has looked at in the window
        self.toasts = []            # [text, seconds_left, tier]
        self.arrow_streak = 0       # arrows hit in a row (not persisted; the best is)
        self.last_player = None
        self._dirty = False
        self._load()

    # ---------------- compat ---------------- #
    @property
    def total_kills(self):
        return self.counters.get("kills", 0)

    @total_kills.setter
    def total_kills(self, value):
        self.counters["kills"] = int(value)

    # ---------------- persistence ---------------- #
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.unlocked = {k: True for k in data.get("unlocked", []) if k in _BY_ID}
            self.unlocked_at = {k: int(v) for k, v in (data.get("unlocked_at") or {}).items() if k in _BY_ID}
            self.counters = {str(k): int(v) for k, v in (data.get("counters") or {}).items()}
            if "kills" not in self.counters:                      # saves from before counters existed
                self.counters["kills"] = int(data.get("total_kills", 0))
            self.seen = {k for k in data.get("seen", []) if k in _BY_ID}
            if "seen" not in data:                                # old saves: nothing is "new"
                self.seen = set(self.unlocked)
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def save(self):
        if not self._dirty:
            return
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump({"unlocked": sorted(self.unlocked), "unlocked_at": self.unlocked_at,
                           "counters": self.counters, "total_kills": self.total_kills,
                           "seen": sorted(self.seen & set(self.unlocked))}, fh, indent=2)
            self._dirty = False
        except OSError:
            pass

    # ---------------- unlocking ---------------- #
    def unlock(self, ach_id, player):
        if ach_id in self.unlocked or ach_id not in _BY_ID:
            return False
        ach = _BY_ID[ach_id]
        self.unlocked[ach_id] = True
        self.unlocked_at[ach_id] = int(time.time())
        self._dirty = True
        player = player or self.last_player
        for currency, amount in ach["reward"].items():
            attr = WALLET_ATTR[currency]
            if player is not None:
                setattr(player, attr, getattr(player, attr, 0) + amount)
        reward = ", ".join(f"+{n} {cur}" for cur, n in ach["reward"].items())
        self.toasts.append([f"{ach['name']}  ({reward})", TOAST_SECONDS, ach.get("tier", "gold")])
        self.save()
        return True

    # ---------------- counters ---------------- #
    def bump(self, counter, amount=1, player=None):
        """Add to a counter and unlock any feat that just reached its goal."""
        if player is not None:
            self.last_player = player
        self.counters[counter] = self.counters.get(counter, 0) + amount
        self._dirty = True
        self._check(counter, player)

    def set_max(self, counter, value, player=None):
        """Keep the best value ever seen (streaks, peaks)."""
        if player is not None:
            self.last_player = player
        if value > self.counters.get(counter, 0):
            self.counters[counter] = int(value)
            self._dirty = True
            self._check(counter, player)

    def set_value(self, counter, value, player=None):
        if self.counters.get(counter) != value:
            self.counters[counter] = int(value)
            self._dirty = True
            self._check(counter, player)

    def _check(self, counter, player):
        for ach_id in _COUNTER_FEATS.get(counter, ()):
            if ach_id not in self.unlocked and self.counters.get(counter, 0) >= _BY_ID[ach_id]["goal"]:
                self.unlock(ach_id, player)

    # ---------------- progress API (the window) ---------------- #
    def progress(self, ach_id):
        """(current, goal). Yes/no feats are (0, 1) or (1, 1)."""
        ach = _BY_ID[ach_id]
        goal = ach.get("goal") or 1
        if ach_id in self.unlocked:
            return goal, goal
        if ach.get("counter"):
            return min(goal, self.counters.get(ach["counter"], 0)), goal
        return 0, goal

    def state(self, ach_id):
        if ach_id in self.unlocked:
            return "unlocked"
        cur, goal = self.progress(ach_id)
        return "progress" if cur > 0 and goal > 1 else "locked"

    def all_entries(self):
        out = []
        for order, ach in enumerate(A.ACHIEVEMENTS):
            cur, goal = self.progress(ach["id"])
            state = self.state(ach["id"])
            hidden = bool(ach.get("hidden")) and state != "unlocked"
            out.append({
                "id": ach["id"], "order": order, "state": state,
                "name": "???" if hidden else ach["name"],
                "desc": "Keep playing to find out." if hidden else ach["desc"],
                "category": ach.get("category", "Combat"), "tier": ach.get("tier", "bronze"),
                "icon": ach.get("icon", "sword"), "reward": dict(ach["reward"]),
                "current": cur, "goal": goal, "frac": (cur / goal) if goal else 0.0,
                "hidden": hidden, "unlocked_at": self.unlocked_at.get(ach["id"], 0),
                "new": ach["id"] in self.unlocked and ach["id"] not in self.seen,
            })
        return out

    def mark_seen(self):
        """The window was looked at: nothing is NEW any more."""
        if not set(self.unlocked) <= self.seen:
            self.seen |= set(self.unlocked)
            self._dirty = True
            self.save()

    # ---------------- events ---------------- #
    def on_kill(self, player, kind=None):
        """A player landed a killing blow. ``kind``: 'fire' | 'bomb' | 'arrow' | None (melee)."""
        self.last_player = player
        self.bump("kills", 1, player)
        if kind == "fire":
            self.bump("fire_kills", 1, player)
        elif kind == "bomb":
            self.bump("bomb_kills", 1, player)
        now = pygame.time.get_ticks()
        stamps = player.kill_times
        stamps.append(now)
        while stamps and now - stamps[0] > 8000:
            stamps.pop(0)
        recent6 = sum(1 for t in stamps if now - t <= int(A.CHAIN5[1] * 1000))
        if recent6 >= A.CHAIN5[0]:
            self.unlock("chain5", player)
        if len(stamps) >= A.CHAIN10[0]:
            self.unlock("chain10", player)

    def on_arrow(self, player, hit):
        """A player's arrow ended: hit something (True) or stuck in a wall / the ground (False)."""
        if hit:
            self.arrow_streak += 1
            self.set_max("best_arrow_streak", self.arrow_streak, player)
        else:
            self.arrow_streak = 0

    def on_revive(self, game, player):
        self.bump("revives", 1, player)
        self.set_value("revives_run", getattr(game, "run_revives", 0), player)

    def on_spend(self, player, amount):
        if amount > 0:
            self.bump("coins_spent", int(amount), player)

    def on_max_ammo_upgrade(self, player):
        self.unlock("arsenal", player)

    def on_friends(self, player, count):
        if count >= 1:
            self.unlock("first_friend", player)
        self.set_max("friends_peak", count, player)

    def on_charm_gamble(self, player):
        """A charm on a boss failed and the player lived to tell."""
        self.unlock("gambler", player)

    def on_charm_confirm(self, player, seconds_left):
        if seconds_left < A.LAST_SECOND_SECONDS:
            self.unlock("last_second", player)

    def on_door(self, player, kind):
        """A player used a door of this kind (counted once per kind per run)."""
        seen = getattr(self, "_run_door_kinds", None)
        if seen is None:
            seen = self._run_door_kinds = set()
        if kind not in seen:
            seen.add(kind)
            self.set_value("door_kinds", len(seen), player)

    def on_shop_visit(self, player, bought_anything):
        if bought_anything:
            self.set_value("shop_empty_streak", 0, player)
        else:
            self.bump("shop_empty_streak", 1, player)
        self.save()

    def on_run_reset(self):
        """A brand-new run: per-run counters start over."""
        self._run_door_kinds = set()
        for name in A.RUN_COUNTERS:
            if self.counters.get(name):
                self.counters[name] = 0
                self._dirty = True
        self.save()

    def on_level_complete(self, game):
        """Called once when a floor is won, before the shop opens."""
        boss = getattr(getattr(game, "objective", None), "kind", "") in ("boss", "final")
        for player in game.player_slots:
            if player.dead or player.death:
                continue
            hurt = player.damage_this_level
            if hurt <= 0:
                self.unlock("untouchable" if boss else "flawless", player)
                if boss:
                    self.unlock("flawless", player)
            if boss:
                self.unlock("boss_down", player)
            if 0 < player.health <= player.max_health * A.ONE_HP_FRACTION:
                self.unlock("one_hp", player)
            if player.gold_coins >= A.HOARD_GOLD:
                self.unlock("hoarder", player)
            if player.lava_seconds >= A.LAVA_SECONDS:
                self.unlock("hot_feet", player)
            if getattr(game, "level", 0) >= A.DEEP_DIVER_FLOOR and getattr(game, "level_folder", None) == paths.STORY:
                self.unlock("deep_diver", player)
        self.save()

    # ---------------- toasts ---------------- #
    def draw_toasts(self, window, view_rect, dt):
        """Draw (and age) the pending toasts. Call once per frame from one view.

        ``dt`` must be REAL frame time: the game's own dt is scaled by slow-mo, which would make
        a toast earned during a kill-cam (or charm mode) crawl and hang around for ages."""
        if not self.toasts:
            return
        from ..ui import ui_theme as ui          # local: keeps this module importable without pygame display
        size = max(12, int(view_rect.width * 0.018))
        y = view_rect.y + int(view_rect.height * 0.16)
        for toast in self.toasts[:MAX_TOASTS]:
            tier = toast[2] if len(toast) > 2 else "gold"
            color = A.TIER_COLORS.get(tier, ui.GOLD)
            age = TOAST_SECONDS - toast[1]
            slide = max(0.0, 1.0 - age / 0.25)                  # drops in from above
            text = f"ACHIEVEMENT: {toast[0]}"
            surf = ui.font(size, True).render(text, True, ui.CREAM)
            box = pygame.Rect(0, 0, surf.get_width() + 24, surf.get_height() + 12)
            box.midtop = (view_rect.centerx, y - int(slide * slide * 40))
            ui.panel(window, box, (30, 19, 26), color, 2, 8)
            window.blit(surf, (box.x + 12, box.y + 6))
            pygame.draw.circle(window, color, (box.left - 9, box.centery), max(4, size // 3))
            y += box.height + 6
            toast[1] -= dt
        self.toasts = [t for t in self.toasts if t[1] > 0]


_tracker = None


def tracker():
    global _tracker
    if _tracker is None:
        _tracker = Tracker()
    return _tracker


def set_path(path):
    """Tests / alternative save locations."""
    global _tracker
    _tracker = Tracker(path)
    return _tracker
