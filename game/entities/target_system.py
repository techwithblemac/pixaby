"""
target_system.py
================
Enemy pointers around the player. A SHOP ITEM (``target_pointers``, ruby):
nothing is drawn until level 1 is owned.

    level 1   chevrons ring the player and point at the nearest enemies
    level 2   longer range, more pointers
    level 3   longest range, and a coloured type badge on every chevron

Colour is the threat: red (close / ranged attackers in reach), yellow, green.
Chevrons fade with distance, pulse when something is dangerously close, and
enemies already on screen and far away are skipped so the ring stays readable.
Chevron sprites are pre-rendered and cached; only a handful are rotated per
frame (the number drawn is capped).
"""

import heapq
import math

import pygame

from ..scripts import shop_effects

# level -> (range in world px, max pointers)
LEVELS = {1: (900, 4), 2: (1400, 6), 3: (2000, 8)}

DANGER_RED = (255, 70, 60)
WARNING_YELLOW = (255, 214, 60)
SAFE_GREEN = (90, 230, 120)

# level 3 type badge
TYPE_BADGE = {
    "Archer": (255, 160, 60),
    "TNT": (230, 90, 220),
    "Torch": (255, 120, 40),
    "Warrior": (150, 190, 255),
    "Pawn": (210, 210, 220),
}
BOSS_BADGE = (255, 202, 80)

_ranged = ("TNT", "Archer")
_chevrons = {}


def _chevron(size, color, badge):
    key = (size, color, badge)
    img = _chevrons.get(key)
    if img is None:
        if len(_chevrons) > 400:
            _chevrons.clear()
        img = pygame.Surface((size * 2 + 4, size * 2 + 4), pygame.SRCALPHA)
        c = size + 2
        pts = [(c + size, c), (c - size * 0.7, c - size * 0.85), (c - size * 0.25, c), (c - size * 0.7, c + size * 0.85)]
        pygame.draw.polygon(img, (18, 17, 25, 255), pts, 4)          # ink outline
        pygame.draw.polygon(img, (*color, 255), pts)
        if badge:
            pygame.draw.circle(img, (18, 17, 25, 255), (c - int(size * 0.2), c), max(3, size // 3) + 1)
            pygame.draw.circle(img, (*badge, 255), (c - int(size * 0.2), c), max(2, size // 3))
        _chevrons[key] = img
    return img


class TargetSystem:
    def __init__(self, owner, pointer_length=60):
        self.owner = owner
        self.game = self.owner.game
        self.pointer_length = pointer_length     # kept for old callers; the ring radius is derived from zoom

    # ------------------------------------------------------------------ #
    def level(self):
        return shop_effects.owned_level(self.owner, "target_pointers")

    @staticmethod
    def threat(enemy, distance):
        ranged = enemy.name in _ranged
        if distance < 300 or (ranged and distance < 600):
            return DANGER_RED, 2
        if distance < 600 or (ranged and distance < 900):
            return WARNING_YELLOW, 1
        return SAFE_GREEN, 0

    def draw_pointers(self, window=None, cam=None, zoom=None):
        level = self.level()
        if level <= 0 or window is None:
            return
        reach, cap = LEVELS[min(level, max(LEVELS))]
        owner = self.owner
        ox, oy = owner.rect.center
        reach2 = reach * reach
        friends = {id(f) for f in (getattr(owner, "friends", None) or ())}
        half_w = window.get_width() / (2 * zoom)
        half_h = window.get_height() / (2 * zoom)

        near = []
        for enemy in self.game.enemy_list:
            if enemy.death or enemy.dead or id(enemy) in friends:
                continue
            dx, dy = enemy.rect.centerx - ox, enemy.rect.centery - oy
            d2 = dx * dx + dy * dy
            if d2 > reach2:
                continue
            on_screen = abs(dx) < half_w and abs(dy) < half_h
            if on_screen and d2 > 450 * 450:     # already visible and not close: no clutter
                continue
            near.append((d2, id(enemy), enemy, dx, dy))
        if not near:
            return

        sx = (ox - cam.x) * zoom
        sy = (oy - cam.y) * zoom
        ring = (78 + 8 * math.sin(pygame.time.get_ticks() / 260.0)) * zoom
        t = pygame.time.get_ticks() / 1000.0

        for d2, _, enemy, dx, dy in heapq.nsmallest(cap, near):
            dist = math.sqrt(d2)
            color, danger = self.threat(enemy, dist)
            angle = math.atan2(dy, dx)
            # fade with distance: 255 close, ~90 at the edge of the range
            alpha = int(255 - 165 * min(1.0, dist / reach))
            size = int((9 + 4 * danger) * zoom * (1 + (0.12 * math.sin(t * 9) if danger == 2 else 0)))
            size = max(5, size)
            badge = None
            if level >= 3:
                badge = BOSS_BADGE if getattr(enemy, "is_boss", False) else TYPE_BADGE.get(enemy.name)
            base = _chevron(size, color, badge)
            deg = -math.degrees(angle)
            img = pygame.transform.rotate(base, round(deg / 5) * 5)
            img.set_alpha(alpha)
            px = sx + math.cos(angle) * ring
            py = sy + math.sin(angle) * ring
            window.blit(img, img.get_rect(center=(int(px), int(py))))
