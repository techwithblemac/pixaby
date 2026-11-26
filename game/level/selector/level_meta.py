"""
level_meta.py
=============
Data layer for the LEVEL SELECT screen.

This module is responsible for:
  - Reading `levels/story/metadata.json` (author / creation date / description /
    difficulty / tags / tier for every official level).
  - Scanning the raw `levels/story/<id>.json` files to compute real stats
    (enemy count, block count, treasure count, water, bounding box...).
  - Rendering small "radar style" thumbnail previews of each level from
    that same raw data (no separate image assets required).
  - A tiny local save file (`save/profile.json`) that stores whether the
    player has PRO+ unlocked.

NOTE on PRO+: there is no real payment processor wired up here. This is a
local/offline entitlement flag only, so the level-select UI has something
real to gate against. Hook `unlock_pro_plus()` up to your actual
store / receipt-validation flow before shipping a paid tier.
"""

import json
import os
from os.path import join, exists

import pygame

from ...scripts import paths

LEVELS_DIR = join(paths.LEVELS_ROOT, "story")        # the campaign; other folders are handled by level/sources.py
METADATA_PATH = join(LEVELS_DIR, "metadata.json")

SAVE_DIR = "save"
PROFILE_PATH = join(SAVE_DIR, "profile.json")

OFFICIAL_RANGE = range(1, 11)  # official campaign is levels 1-10

DIFFICULTY_LABELS = {
    1: "NOVICE",
    2: "APPRENTICE",
    3: "ADEPT",
    4: "VETERAN",
    5: "NIGHTMARE",
}

# Colour family used to paint the radar-style thumbnails, keyed by a
# substring found in the block's "name" field.
FAMILY_COLORS = {
    "grass": (70, 230, 150),
    "stone": (120, 180, 255),
    "brick": (255, 160, 80),
    "ice":   (140, 235, 255),
    "mud":   (190, 145, 90),
    "box":   (255, 225, 100),
}
DEFAULT_BLOCK_COLOR = (150, 160, 200)
WATER_COLOR = (50, 140, 255)
TREE_COLOR = (40, 180, 110)
TREASURE_COLOR = (255, 215, 70)
ENEMY_COLOR = (255, 80, 80)

_metadata_cache = None
_raw_level_cache = {}
_stats_cache = {}
_thumb_cache = {}


# --------------------------------------------------------------------------- #
# Metadata (author / date / description / tier)
# --------------------------------------------------------------------------- #

def load_metadata(force=False):
    """Load levels/metadata.json (author, created date, description, tier...)."""
    global _metadata_cache
    if force or _metadata_cache is None:
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                _metadata_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _metadata_cache = {}
    return _metadata_cache


def get_level_ids():
    """Every level found on disk. 1-10 are the official campaign; anything
    else discovered under levels/*.json is treated as a bonus level so the
    screen never hides content the dev drops into the folder."""
    ids = []
    if exists(LEVELS_DIR):
        for fname in os.listdir(LEVELS_DIR):
            if not fname.endswith(".json") or fname == "metadata.json":
                continue
            try:
                ids.append(int(fname[:-5]))
            except ValueError:
                continue
    return sorted(ids)


# --------------------------------------------------------------------------- #
# Raw level scanning -> stats
# --------------------------------------------------------------------------- #

def _load_raw_level(level_id):
    if level_id not in _raw_level_cache:
        path = join(LEVELS_DIR, f"{level_id}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                _raw_level_cache[level_id] = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _raw_level_cache[level_id] = []
    return _raw_level_cache[level_id]


def get_level_stats(level_id):
    """Scan the raw level json once (cached) and compute real gameplay
    stats used both by the detail panel and the thumbnail renderer."""
    if level_id in _stats_cache:
        return _stats_cache[level_id]

    data = _load_raw_level(level_id)

    blocks, waters, enemies = [], [], []
    treasures, trees = [], []
    enemy_types = {}
    minx = miny = float("inf")
    maxx = maxy = float("-inf")

    for obj in data:
        if not isinstance(obj, dict):
            continue
        t = obj.get("type")
        x, y = obj.get("x"), obj.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if x < minx: minx = x
            if x > maxx: maxx = x
            if y < miny: miny = y
            if y > maxy: maxy = y

        if t == "block":
            blocks.append(obj)
        elif t == "water":
            waters.append(obj)
        elif t == "enemy":
            enemies.append(obj)
            name = obj.get("name", "Unknown")
            enemy_types[name] = enemy_types.get(name, 0) + 1
        elif t == "treasure":
            treasures.append(obj)
        elif t == "tree":
            trees.append(obj)

    if minx == float("inf"):
        minx = miny = 0
        maxx = maxy = 1

    stats = {
        "blocks": blocks,
        "waters": waters,
        "enemies": enemies,
        "treasures": treasures,
        "trees": trees,
        "block_count": len(blocks),
        "water_count": len(waters),
        "enemy_count": len(enemies),
        "treasure_count": len(treasures),
        "tree_count": len(trees),
        "object_count": len(data),
        "enemy_types": enemy_types,
        "bounds": (minx, miny, maxx, maxy),
        "has_water": len(waters) > 0,
    }
    _stats_cache[level_id] = stats
    return stats


def _block_family(name):
    name = (name or "").lower()
    for fam in FAMILY_COLORS:
        if fam in name:
            return fam
    return None


# --------------------------------------------------------------------------- #
# Thumbnail rendering (radar-style, generated from real level layout data)
# --------------------------------------------------------------------------- #

def render_thumbnail(level_id, size=(240, 150)):
    """Render (and cache) a stylised top-down preview of the level built
    directly from its block/enemy/treasure positions - a real, if
    schematic, picture of what that level actually looks like."""
    key = (level_id, size)
    if key in _thumb_cache:
        return _thumb_cache[key]

    stats = get_level_stats(level_id)
    minx, miny, maxx, maxy = stats["bounds"]
    w = max(1, maxx - minx)
    h = max(1, maxy - miny)

    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill((5, 9, 20, 255))

    grid_color = (18, 55, 65, 255)
    for gx in range(0, size[0], 18):
        pygame.draw.line(surf, grid_color, (gx, 0), (gx, size[1]))
    for gy in range(0, size[1], 18):
        pygame.draw.line(surf, grid_color, (0, gy), (size[0], gy))

    pad = 6
    span_x = max(1, size[0] - pad * 2)
    span_y = max(1, size[1] - pad * 2)

    def project(x, y):
        px = pad + (x - minx) / w * span_x
        py = pad + (y - miny) / h * span_y
        return int(px), int(py)

    sw, sh = size

    for obj in stats["waters"]:
        px, py = project(obj.get("x", 0), obj.get("y", 0))
        if 0 <= px < sw and 0 <= py < sh:
            surf.set_at((px, py), WATER_COLOR)

    for obj in stats["blocks"]:
        px, py = project(obj.get("x", 0), obj.get("y", 0))
        if 0 <= px < sw and 0 <= py < sh:
            fam = _block_family(obj.get("name"))
            surf.set_at((px, py), FAMILY_COLORS.get(fam, DEFAULT_BLOCK_COLOR))

    for obj in stats["trees"]:
        px, py = project(obj.get("x", 0), obj.get("y", 0))
        if 0 <= px < sw and 0 <= py < sh:
            surf.set_at((px, py), TREE_COLOR)

    for obj in stats["treasures"]:
        px, py = project(obj.get("x", 0), obj.get("y", 0))
        pygame.draw.circle(surf, TREASURE_COLOR, (px, py), 2)
        pygame.draw.circle(surf, (255, 255, 210), (px, py), 3, 1)

    for obj in stats["enemies"]:
        px, py = project(obj.get("x", 0), obj.get("y", 0))
        pygame.draw.circle(surf, ENEMY_COLOR, (px, py), 2)
        pygame.draw.circle(surf, (255, 190, 190), (px, py), 4, 1)

    # faint scanline sheen for the "futuristic HUD" feel
    for y in range(0, sh, 3):
        pygame.draw.line(surf, (0, 255, 220, 12), (0, y), (sw, y))

    pygame.draw.rect(surf, (0, 255, 220, 100), surf.get_rect(), 1)

    _thumb_cache[key] = surf
    return surf


# --------------------------------------------------------------------------- #
# Combined level info (metadata + stats) + search
# --------------------------------------------------------------------------- #

def get_level_info(level_id):
    meta = load_metadata().get(str(level_id), {})
    stats = get_level_stats(level_id)

    info = {
        "id": level_id,
        "title": meta.get("title", f"Level {level_id}"),
        "author": meta.get("author", "Unknown"),
        "created": meta.get("created", "Unknown"),
        "description": meta.get("description", "No description available for this level yet."),
        "difficulty": meta.get("difficulty", 1),
        "tags": meta.get("tags", []),
        "tier": meta.get("tier", "free"),
        "recommended_players": meta.get("recommended_players", "1-4"),
        "category": meta.get(
            "category",
            "OFFICIAL CAMPAIGN" if level_id in OFFICIAL_RANGE else "BONUS LEVELS",
        ),
    }
    info["difficulty_label"] = DIFFICULTY_LABELS.get(info["difficulty"], "UNKNOWN")
    info.update(stats)
    return info


def get_all_level_infos():
    return [get_level_info(lid) for lid in get_level_ids()]


def search_levels(query, infos):
    q = (query or "").strip().lower()
    if not q:
        return infos

    out = []
    for info in infos:
        haystack = " ".join([
            info["title"], info["author"], info["description"],
            " ".join(info.get("tags", [])), str(info["id"]),
            info["category"], info["tier"],
        ]).lower()
        if q in haystack:
            out.append(info)
    return out


# --------------------------------------------------------------------------- #
# Local PRO+ entitlement (see module docstring for the caveat)
# --------------------------------------------------------------------------- #

def _ensure_save_dir():
    if not exists(SAVE_DIR):
        os.makedirs(SAVE_DIR, exist_ok=True)


def load_profile():
    _ensure_save_dir()
    if exists(PROFILE_PATH):
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {"pro_plus": False}


def save_profile(profile):
    _ensure_save_dir()
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


def is_pro_plus(profile=None):
    profile = profile if profile is not None else load_profile()
    return bool(profile.get("pro_plus", False))


def unlock_pro_plus():
    """Flip the local PRO+ flag on and persist it. Local/offline only -
    wire this to a real store transaction before shipping paid content."""
    profile = load_profile()
    profile["pro_plus"] = True
    save_profile(profile)
    return profile


def is_level_locked(level_id, profile=None):
    info = get_level_info(level_id)
    return info["tier"] == "pro" and not is_pro_plus(profile)
