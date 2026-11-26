import pygame
from collections import OrderedDict

from ..assets import Assets
from ..settings import Settings
from ..data.palletes.blocks import block_pallete
from ..data.palletes.entities import entity_pallete
from ..data.palletes.doors import parse_door_name, frame_swaps, portal_swaps
from ..data.palletes.deco import swaps_for
from .asset_funcs import apply_pallete, build_door_sprite


# Auto-detected in settings.py from logical core count (<=2 -> True).
# Override there if the heuristic guesses wrong for a given machine.
LOW_SPEC_MODE = Settings.LOW_SPEC_MODE
MAX_CACHED_IMAGES = Settings.MAX_CACHED_IMAGES
MAX_CACHED_ENTITY_IMAGES = Settings.MAX_CACHED_ENTITY_IMAGES

# Caches were previously plain dicts that grew forever for the life of the
# process (every new size/color/palette combo touched added a permanent
# entry). Switched to OrderedDict so we can do cheap LRU eviction: on a hit
# we move the key to the end, and once a cache exceeds its cap we drop the
# oldest (least-recently-used) entry. This bounds memory growth over a long
# session instead of letting it climb indefinitely.
CACHED_ENTITY_IMAGES = OrderedDict()
CACHED_IMAGES = OrderedDict()
CACHED_RECTS = {}
CACHED_RECTS['player_wins'] = {}
CACHED_RECTS['other'] = OrderedDict()
GLOW_CACHE = {}
FONTS = {}

MAX_CACHED_RECTS_OTHER = 50

def _lru_touch(cache: OrderedDict, key=None, max_size: int=100) -> None:
    """Mark `key` as most-recently-used and evict the oldest entry if over cap."""
    if key:
        cache.move_to_end(key)
    if len(cache) > max_size:
        cache.popitem(last=False)


def create_cache_img(cache_dict, zoom_key, sprite, zoom=1, index=0) -> pygame.Surface:
    # Use cached image if available
    if zoom not in cache_dict:
        cache_dict[zoom] = OrderedDict()

    if zoom_key in cache_dict[zoom]:
        scaled_image = cache_dict[zoom][zoom_key]
    else:
        skip = False
        if zoom == 1:
            if zoom_key in CACHED_ENTITY_IMAGES:
                scaled_image = CACHED_ENTITY_IMAGES[zoom_key][index]
                skip = True

        if not skip:
            scaled_size = (
                int(sprite.get_width() * zoom),
                int(sprite.get_height() * zoom)
            )
            scaled_image = pygame.transform.scale(sprite, scaled_size)
            cache_dict[zoom][zoom_key] = scaled_image
    
    return scaled_image


# CACHE FONTS
def cache_font(key):
    if key not in FONTS:
        FONTS[key] = pygame.font.SysFont(key[0], key[1])
    
    return FONTS[key]


# CACHE ASSET IMAGES
def cache_assets(cache_key, color=(0, 0, 0, 0), index=None):
    if cache_key not in CACHED_ENTITY_IMAGES:
        name, color, sheet_name = cache_key
        if name != "Blue":
            images = apply_pallete(Assets.ENEMY_SPRITES[name]["Blue"][sheet_name], entity_pallete[color], "list")
        else:
            images = Assets.ENEMY_SPRITES[name]["Blue"][sheet_name]
            
        CACHED_ENTITY_IMAGES[cache_key] = images

    _lru_touch(CACHED_ENTITY_IMAGES, cache_key, MAX_CACHED_ENTITY_IMAGES)
    
    if index == None:
        return CACHED_ENTITY_IMAGES[cache_key]
    else:
        return CACHED_ENTITY_IMAGES[cache_key][index]


# CACHE IMAGES
def cache_img(size, color=(0, 0, 0, 0), clear=False, alpha=True, fill=True, assets=False):
    from .functions import find_last
    cache_key = (size, color)
    if cache_key not in CACHED_IMAGES:
        if assets:
            type_, size_, width, height, perspective = size
            if ("stone" in type_ or "grass" in type_ or "brick" in type_) and find_last(type_, "_") != -1:
                    last = find_last(type_, "_")
                    i = type_[last+1:]
                    try:
                        image = apply_pallete(Assets.blocks[type_.replace("_" + i, "")][size_], block_pallete[type_[:5]][i])
                    except KeyError:
                        image = Assets.blocks[type_][size_]
                    surf = pygame.transform.scale(image, (width, height))
            
            else:
                surf = pygame.transform.scale(Assets.blocks[type_][size_], (width, height))
            
            if perspective == "back":
                surf.set_alpha(150)
                surf.convert_alpha()
        
        else:
            surf = pygame.Surface(size, pygame.SRCALPHA)
        
        if fill:
            surf.fill(color)

        CACHED_IMAGES[cache_key] = surf

    elif clear:
        CACHED_IMAGES[cache_key].fill(color)

    _lru_touch(CACHED_IMAGES, cache_key, MAX_CACHED_IMAGES)
    return CACHED_IMAGES[cache_key]


# CACHE DOORS
# 3 kinds x 8 biomes = 24 small surfaces at most, so this is a plain dict
# with no eviction. Each one is built once from Assets.DOOR on first use.
CACHED_DOOR_IMAGES = {}

def get_door(name):
    kind, biome = parse_door_name(name)
    key = (kind, biome)
    if key not in CACHED_DOOR_IMAGES:
        CACHED_DOOR_IMAGES[key] = build_door_sprite(
            Assets.DOOR, frame_swaps(biome), portal_swaps(kind)
        )
    return CACHED_DOOR_IMAGES[key]


# CACHE DECO (per-biome recolours, see data/palletes/deco.py)
# 8 biomes x ~15 small sprites, built once per biome on first use. Returns a
# dict shaped exactly like Assets.DECO_SPRITES so callers don't change.
CACHED_DECO_SPRITES = {}

def get_deco_sprites(biome="1"):
    biome = str(biome)
    sprites = CACHED_DECO_SPRITES.get(biome)
    if sprites is None:
        sprites = {}
        for name, image in Assets.DECO_SPRITES.items():
            swaps = swaps_for(name, biome)
            # same swaps for opaque + soft pixels so anti-aliased edges follow
            sprites[name] = build_door_sprite(image, swaps, swaps) if swaps else image
        CACHED_DECO_SPRITES[biome] = sprites
    return sprites

def get_tree_sprites(biome="1"):
    """Return animated tree frames recoloured with the chosen deco palette."""
    biome = str(biome)
    key = ("tree", biome)
    cached = CACHED_DECO_SPRITES.get(key)
    if cached is not None:
        return cached
    from ..data.palletes.deco import swaps_for
    swaps = swaps_for("tree", biome)
    cached = {}
    for sheet, frames in Assets.TREE_SPRITES.items():
        cached[sheet] = [build_door_sprite(frame, swaps, swaps) if swaps else frame
                         for frame in frames]
    CACHED_DECO_SPRITES[key] = cached
    return cached


# CACHE RECTS
def cached_rect(size, from_surf=None, rect=None):
    key = size if not from_surf else (size, from_surf.get_rect().size)
    if key not in CACHED_RECTS['other']:
        if from_surf:
            CACHED_RECTS['other'][key] = from_surf.get_rect()
        else:
            CACHED_RECTS['other'][key] = rect

        _lru_touch(CACHED_RECTS['other'], key, MAX_CACHED_RECTS_OTHER)
    
    if not rect:
        return CACHED_RECTS['other'][key]
    
def deep_cache_len(cache) -> int:
    """
    Total size of `cache`: its own len(), plus the len() of any dict
    nested inside it, recursively. Pass it any cache - CACHED_IMAGES
    (flat) or CACHED_OBJECT_ZOOMED_IMAGES (a dict of sub-caches) - and it
    works out on its own whether there's anything nested to add, instead
    of the caller having to know the shape ahead of time.
    """
    if not hasattr(cache, '__len__'):
        return 0

    total = len(cache)

    if isinstance(cache, dict):
        for value in cache.values():
            if isinstance(value, dict):
                total += deep_cache_len(value)

    return total


def _append_nested_cache_lines(cache, lines, depth):
    """
    Recurses into `cache`, appending one (text, depth) line per key whose
    value is itself a dict - showing that key's own deep length - and
    going one level deeper for every extra layer of nesting found. Does
    nothing for keys whose value isn't a dict (nothing to break down further).
    """
    if not isinstance(cache, dict):
        return

    for key, value in cache.items():
        if isinstance(value, dict):
            lines.append((f"{key}: {deep_cache_len(value)}", depth))
            _append_nested_cache_lines(value, lines, depth + 1)


def build_cache_debug_info(caches: dict) -> list:
    """
    Build the cache-size portion of the debug overlay from a dict of
    {label: cache_object} instead of a hand-written 'LABEL': len(cache)
    line per cache. Add/remove a cache from the `caches` dict passed in
    and this works out the label and (deep) length itself - nothing else
    to update by hand.

    Returns a flat list of (text, depth) pairs instead of a plain dict:
    each cache gets a depth-0 line with its total deep length, followed
    by a depth-1 line for each of its keys that is itself a dict (e.g.
    a zoom level), then depth-2 lines for anything nested inside THAT,
    and so on - as deep as the cache actually goes. Caches with no
    nested dicts (e.g. CACHED_IMAGES) just get their single depth-0 line.
    """
    lines = []
    for label, cache in caches.items():
        try:
            total = deep_cache_len(cache)
        except TypeError:
            lines.append((f"{label}: n/a", 0))
            continue

        lines.append((f"{label}: {total}", 0))
        _append_nested_cache_lines(cache, lines, 1)

    return lines

def remove_unused_key(cache_dict, zooms):
    """
    ### For removing unused zoom keys
    """
    for key in cache_dict.keys():
        if key not in zooms:
            del cache_dict[key]
            break # bRO YOU ARE REMOVING ONE ZOOM PER ITERATION, WHEN THERE CAN BE MOORE, COME BACK LATER
        
def reset_cache(self):
    from ..objects.object_utils import CACHED_OBJECT_IMAGES, CACHED_OBJECT_ZOOMED_IMAGES
    
    global GLOW_CACHE, CACHED_IMAGES, CACHED_RECTS, FONTS
    global CACHED_ENTITY_IMAGES
    
    CACHED_IMAGES.clear()

    CACHED_RECTS.clear()
    CACHED_RECTS['other'] = OrderedDict()
    CACHED_RECTS['player_wins'] = {}
    
    GLOW_CACHE.clear()
    FONTS.clear()
    
    CACHED_OBJECT_IMAGES['other'].clear()
    CACHED_OBJECT_ZOOMED_IMAGES.clear()
    self.object_sprite_cache.clear()
    
    CACHED_ENTITY_IMAGES.clear()
    self.CACHED_ENTITY_ZOOM_IMAGES.clear()
    self.entity_sprite_cache.clear()
    
    self.graph.clear_cache()

