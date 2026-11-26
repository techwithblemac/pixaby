"""
preview.py
==========
The level selector's MAP PREVIEW.

A level says which part of its map to show with one entry in its JSON:

    {"type": "preview coordinates", "x": 0, "y": 0}

``x`` / ``y`` are the world position (pixels) the preview is centred on. A level without the entry shows
"NO MAP PREVIEW". The level editor changes it with the V key (Level_Editor -> editor/preview_tools.py).

What lives here
---------------
    find / point / set_point / clear     read and write the entry in a level's world list
    render(objects, point, size)         a small picture of the map around the point (a pygame Surface)

The picture is drawn from the raw level JSON (the same ``objects`` the selector already holds), so no level has
to be loaded to show it. Blocks use the game's own block sprites; everything else is a simple marker.
"""

import pygame

TYPE = "preview coordinates"

# The preview always shows this many world pixels across; the height follows the shape of the panel.
VIEW_W = 768
# The editor outlines this much around the point (about what a normal selector panel shows).
VIEW_H = 640

# Light paper-white backdrop: the preview shows the map on a whitish background so the real sprites read clearly.
_BG = (246, 244, 239)
_SKY = (250, 249, 246)
_EDGE = (206, 200, 192)

# Sprites are only ever *looked up* here (never loaded from disk) and cached per (kind, name, colour/biome).
_RAW = {}
_SCALED = {}


# ---------------------------------------------------------------------- #
# the data value
# ---------------------------------------------------------------------- #
def make(x=0, y=0):
    """A fresh entry."""
    return {"type": TYPE, "x": int(x), "y": int(y)}


def find(world):
    """The level's preview entry, or None."""
    for data in world or ():
        if isinstance(data, dict) and data.get("type") == TYPE:
            return data
    return None


def point(world):
    """(x, y) of the preview, or None when the level has none (or the numbers are unusable)."""
    data = find(world)
    if data is None:
        return None
    try:
        return int(data.get("x", 0)), int(data.get("y", 0))
    except (TypeError, ValueError):
        return None


def set_point(world, x, y):
    """Create or update the entry in ``world`` (a level's JSON list). Returns the entry."""
    data = find(world)
    if data is None:
        data = make(x, y)
        world.append(data)
    else:
        data["x"], data["y"] = int(x), int(y)
    return data


def clear(world):
    """Remove the entry. True if there was one."""
    data = find(world)
    if data is None:
        return False
    world.remove(data)
    return True


# ---------------------------------------------------------------------- #
# real sprites (the game's own art, trimmed to the visible pixels)
# ---------------------------------------------------------------------- #
def _trim(img):
    """Crop a sprite to its visible pixels so it can be anchored on the ground it stands on."""
    try:
        box = img.get_bounding_rect()
        if box.width and box.height:
            return img.subsurface(box).copy()
    except Exception:
        pass
    return img


def _biome_of(name):
    """(base name, biome) for names like ``tree_5`` / ``shrub1_5``; plain names are biome 1."""
    from ..data.biomes import BIOMES
    base, _, tail = str(name).rpartition("_")
    if base and tail in BIOMES:
        return base, tail
    return str(name), "1"


def _sprite_key(data):
    kind = data.get("type")
    if kind == "spawn_point":
        ents = data.get("entities") or [[None, None]]
        first = ents[0] if isinstance(ents[0], (list, tuple)) else [ents[0], None]
        return (kind, first[0], first[1] if len(first) > 1 else None)
    return (kind, data.get("name"), data.get("color") if kind == "enemy" else None)


def _raw_sprite(data):
    """The unscaled, trimmed sprite for one level entry, or None when it has no picture."""
    kind, name = data.get("type"), data.get("name")
    key = _sprite_key(data)
    if key in _RAW:
        return _RAW[key]
    img = None
    try:
        from ..assets import Assets
        from ..scripts import cache
        if kind == "tree":
            _, biome = _biome_of(name)
            img = cache.get_tree_sprites(biome)["idle_right"][0]
        elif kind == "deco":
            base, biome = _biome_of(name)
            from ..data.palletes.deco import is_recolourable
            if base in Assets.DECO_SPRITES and is_recolourable(base):
                img = cache.get_deco_sprites(biome)[base]
            else:
                img = Assets.DECO_SPRITES.get(str(name))
                if img is None:
                    img = Assets.DECO_SPRITES.get(base)
        elif kind == "treasure":
            sheets = Assets.GEM_SPRITES
            frames = sheets.get(str(name)) or sheets.get("yellow") or next(iter(sheets.values()), None)
            img = frames[0] if frames else None
        elif kind == "door":
            img = cache.get_door(str(name))
        elif kind == "trap" and str(name).lower() == "homing":
            from ..objects import arrow_trap
            img = arrow_trap.icon(64)
        elif kind == "trap":
            sheets = Assets.TRAPS.get(str(name or "spikes").lower()) or Assets.TRAPS.get("spikes") or {}
            frames = sheets.get("on") or sheets.get("off") or next(iter(sheets.values()), None)
            img = frames[0] if frames else None
        elif kind in ("enemy", "spawn_point"):
            if kind == "spawn_point":
                ents = data.get("entities") or []
                if not ents:
                    return None
                name, color = ents[0][0], (ents[0][1] if len(ents[0]) > 1 and ents[0][1] else "Blue")
            else:
                color = data.get("color") or "Blue"
            from ..data.palletes.entities import entity_pallete
            from ..scripts.asset_funcs import apply_pallete
            frames = Assets.ENEMY_SPRITES[name]["Blue"]["idle_right"]
            if color != "Blue" and entity_pallete.get(color):
                frames = apply_pallete(frames, entity_pallete[color], "list")
            img = frames[0]
            if kind == "spawn_point":
                img = img.copy()
                img.set_alpha(130)
        if img is not None:
            pass
            #img = _trim(img)
    except Exception:
        img = None
    _RAW[key] = img
    return img


def _scaled_sprite(data, scale):
    raw = _raw_sprite(data)
    if raw is None:
        return None
    key = _sprite_key(data) + (round(scale, 3),)
    img = _SCALED.get(key)
    if img is None:
        size = (max(1, int(round(raw.get_width() * scale))), max(1, int(round(raw.get_height() * scale))))
        img = pygame.transform.scale(raw, size).convert_alpha()
        _SCALED[key] = img
    return img


# ---------------------------------------------------------------------- #
# the picture
# ---------------------------------------------------------------------- #
def render(objects, center, size):
    """A ``size`` (w, h) Surface showing the map around ``center`` (world x, y).

    ``objects`` is a level's raw JSON entries. The horizontal span is VIEW_W world pixels whatever the size,
    so a bigger panel shows more above and below, not a closer zoom. Everything is drawn with the game's own
    sprites (blocks, trees, decoration, doors, traps, gems, enemies) on a whitish background.
    """
    w, h = max(1, int(size[0])), max(1, int(size[1]))
    scale = w / float(VIEW_W)
    cx, cy = center
    left = cx - (w / scale) / 2.0
    top = cy - (h / scale) / 2.0
    right = left + w / scale
    bottom = top + h / scale

    surf = pygame.Surface((w, h))
    surf.fill(_BG)
    pygame.draw.rect(surf, _SKY, (0, 0, w, h // 2))

    pad = 160  # sprites reach past their cell, so keep entries a little outside the view too
    visible = []
    for data in objects or ():
        if not isinstance(data, dict) or "x" not in data or "y" not in data:
            continue
        try:
            x, y = float(data["x"]), float(data["y"])
            dw, dh = float(data.get("width", 64)), float(data.get("height", 64))
        except (TypeError, ValueError):
            continue
        if x + dw < left - pad or x > right + pad or y + dh < top - pad or y > bottom + pad:
            continue
        visible.append((data, x, y, dw, dh))

    sprites = {}

    def block_sprite(data, dw, dh, pw, ph):
        key = (data.get("name"), data.get("size", "big"), int(dw), int(dh), pw, ph)
        img = sprites.get(key)
        if img is None:
            try:
                from ..scripts.asset_funcs import get_block
                img = pygame.transform.scale(
                    get_block(data.get("name", "stone"), data.get("size", "big"), int(dw), int(dh)), (pw, ph))
            except Exception:
                img = pygame.Surface((pw, ph))
                img.fill((150, 140, 150))
            sprites[key] = img
        return img

    def to_screen(x, y, dw, dh):
        sx, sy = int((x - left) * scale), int((y - top) * scale)
        return sx, sy, max(1, int(dw * scale + 0.999)), max(1, int(dh * scale + 0.999))

    # back to front: back blocks, front blocks, water, scenery, then what stands on the ground
    for data, x, y, dw, dh in visible:
        if data.get("type") == "block" and data.get("perspective", "fore") == "back":
            sx, sy, pw, ph = to_screen(x, y, dw, dh)
            img = block_sprite(data, dw, dh, pw, ph).copy()
            img.fill((170, 170, 180), special_flags=pygame.BLEND_RGB_MULT)
            surf.blit(img, (sx, sy))

    for data, x, y, dw, dh in visible:
        if data.get("type") == "block" and data.get("perspective", "fore") != "back":
            sx, sy, pw, ph = to_screen(x, y, dw, dh)
            surf.blit(block_sprite(data, dw, dh, pw, ph), (sx, sy))
        elif data.get("type") == "moving_platform":
            sx, sy, pw, ph = to_screen(x, y, dw, dh)
            try:
                color = tuple(int(c) for c in data.get("color", (50, 50, 255)))[:3]
            except (TypeError, ValueError):
                color = (50, 50, 255)
            pygame.draw.rect(surf, color, (sx, sy, pw, max(2, ph)))

    for data, x, y, dw, dh in visible:
        if data.get("type") == "water":
            sx, sy, pw, ph = to_screen(x, y, dw, dh)
            try:
                color = tuple(int(c) for c in data.get("color", (60, 120, 220)))[:3]
            except (TypeError, ValueError):
                color = (60, 120, 220)
            tint = pygame.Surface((pw, ph), pygame.SRCALPHA)
            tint.fill((*color, 120))
            surf.blit(tint, (sx, sy))

    # everything below stands on the floor of its cell: bottom-centre of the sprite on the bottom-centre of the cell
    for kind in ("deco", "tree", "door", "trap", "treasure", "spawn_point", "enemy"):
        for data, x, y, dw, dh in visible:
            if data.get("type") != kind:
                continue
            img = _scaled_sprite(data, scale)
            if img is None:
                continue
            sx = int((x + dw / 2.0 - left) * scale) - img.get_width() // 2
            sy = int((y + dh - top) * scale) - img.get_height()
            
            if kind in ("spawn_point", "enemy"):
                sy += 38
            if kind in ("deco", "tree"):
                sy += 12

            surf.blit(img, (sx, sy))

    # thin soft frame so the white map does not bleed into the panel behind it
    pygame.draw.rect(surf, _EDGE, (0, 0, w, h), width=1)
    return surf
