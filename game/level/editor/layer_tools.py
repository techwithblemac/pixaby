"""
layer_tools.py
==============
Show / hide the editor's object categories so a crowded level can be worked on one layer at a time.

    L  or the LAYERS button   open / close the layers panel (every category, with its key and ON / OFF)
    1-9 and 0                 while the panel is open: toggle BLOCKS, ENEMIES, TREASURE, DECO, WATER, PLATFORMS,
                              DOORS, SPAWNERS, START POINTS, TRAPS (0 is the tenth)
    Alt + 1-9 / 0             the same toggle without opening the panel
    click a row               toggle it too;  SHOW ALL / HIDE ALL at the bottom

The plain number keys keep their old jobs (1 mode, 2 perspective, 3 reverse cycle, 4-9 / 0 pick the category you
place) whenever the panel is closed, so nothing existing changes meaning.

A hidden category is not drawn (objects, spawner / start-point overlays and its grid outline), cannot be selected or
clicked on, and is skipped by select / copy. Picking it as the category to place un-hides it, so you never place
something you cannot see. Hiding is only a view: it never touches the level data and is not saved.
"""

import pygame

from . import editor_palette as pal
from ...ui import ui_theme
from ...objects.objects import WaterZone

# (key, category) in on-screen order. 1-9 are the first nine categories, 0 is the tenth.
LAYER_KEYS = (
    (pygame.K_1, pygame.K_KP1, pal.BLOCKS),
    (pygame.K_2, pygame.K_KP2, pal.ENTITIES),
    (pygame.K_3, pygame.K_KP3, pal.TREASURE),
    (pygame.K_4, pygame.K_KP4, pal.DECO),
    (pygame.K_5, pygame.K_KP5, pal.WATER),
    (pygame.K_6, pygame.K_KP6, pal.PLATFORMS),
    (pygame.K_7, pygame.K_KP7, pal.DOORS),
    (pygame.K_8, pygame.K_KP8, pal.SPAWNERS),
    (pygame.K_9, pygame.K_KP9, pal.START),
    (pygame.K_0, pygame.K_KP0, pal.TRAPS),
)
KEY_TO_CATEGORY = {}
for _k, _kp, _cat in LAYER_KEYS:
    KEY_TO_CATEGORY[_k] = _cat
    KEY_TO_CATEGORY[_kp] = _cat

LABELS = {cat: str(i + 1 if i < 9 else 0) for i, (_k, _kp, cat) in enumerate(LAYER_KEYS)}
DOT = {
    pal.BLOCKS: (250, 250, 250), pal.ENTITIES: (224, 78, 74), pal.TREASURE: (0, 200, 200),
    pal.DECO: (108, 201, 117), pal.WATER: (100, 170, 215), pal.PLATFORMS: (190, 190, 60),
    pal.DOORS: (171, 105, 164), pal.SPAWNERS: (255, 112, 92), pal.START: (255, 202, 80),
    pal.TRAPS: (240, 130, 0),
}

# live object / JSON "type" -> category (anything else, e.g. the player, is never hidden)
TYPE_TO_CATEGORY = {
    "block": pal.BLOCKS, "enemy": pal.ENTITIES, "treasure": pal.TREASURE, "deco": pal.DECO, "tree": pal.DECO,
    "water": pal.WATER, "moving_platform": pal.PLATFORMS, "door": pal.DOORS, "spawn_point": pal.SPAWNERS,
    "trap": pal.TRAPS,
}
# placement-grid outline tags -> category
TAG_TO_CATEGORY = {
    "water": pal.WATER, "block_back": pal.BLOCKS, "treasure": pal.TREASURE, "platforms": pal.PLATFORMS,
    "deco": pal.DECO, "trap": pal.TRAPS, "entities": pal.ENTITIES,
}

ROW_H, PANEL_W = 30, 292


# ------------------------------------------------------------------ state
def init(game):
    game.hidden_layers = set()
    game.layers_open = False
    game.layers_btn_rect = pygame.Rect(0, 0, 1, 1)
    game.layers_panel_rect = pygame.Rect(0, 0, 1, 1)
    game.layers_rows = []                 # [(rect, category)]
    game.layers_show_all_rect = pygame.Rect(0, 0, 1, 1)
    game.layers_hide_all_rect = pygame.Rect(0, 0, 1, 1)


def is_hidden(game, category):
    return category in getattr(game, "hidden_layers", ())


def tag_visible(game, tag):
    return not is_hidden(game, TAG_TO_CATEGORY.get(tag))


def type_visible(game, type_name):
    return not is_hidden(game, TYPE_TO_CATEGORY.get(type_name))


def category_of(obj):
    if isinstance(obj, WaterZone):
        return pal.WATER
    return TYPE_TO_CATEGORY.get(getattr(obj, "type", None))


def hidden_count(game):
    return len(getattr(game, "hidden_layers", ()))


def _drop_hidden_from_selection(game):
    selection = getattr(game, "selection", None)
    if selection:
        game.selection = [d for d in selection if type_visible(game, d.get("type"))]


def toggle(game, category):
    hidden = game.hidden_layers
    hidden.symmetric_difference_update({category})
    _drop_hidden_from_selection(game)
    game._draw_list_dirty = True
    state = "HIDDEN" if category in hidden else "SHOWN"
    print(f"Layer {pal.CATEGORY_NAMES.get(category, category)} {state}.")


def set_all(game, visible):
    game.hidden_layers = set() if visible else set(pal.CATEGORY_ORDER)
    _drop_hidden_from_selection(game)
    game._draw_list_dirty = True


def ensure_visible(game, category):
    """Choosing a category to place un-hides it."""
    if is_hidden(game, category):
        game.hidden_layers.discard(category)
        game._draw_list_dirty = True


def visible_objects(game):
    """The draw list without hidden categories, or None when nothing is hidden (draw the normal list).
    May be an empty list: the caller then skips drawing objects (draw() would treat [] as 'draw everything')."""
    if not game.hidden_layers:
        return None
    if game._draw_list_dirty:
        from ..main.update_funcs import _rebuild_draw_list
        _rebuild_draw_list(game)
    hidden = game.hidden_layers
    return [o for o in game.draw_list if category_of(o) not in hidden]


# ------------------------------------------------------------------ input
def handle_key(game, event):
    """True when the key was used here (the caller then ignores it)."""
    mods = pygame.key.get_mods()
    if event.key == pygame.K_l and not (mods & (pygame.KMOD_CTRL | pygame.KMOD_ALT)):
        game.layers_open = not game.layers_open
        return True
    if game.layers_open and event.key == pygame.K_ESCAPE:
        game.layers_open = False
        return True
    category = KEY_TO_CATEGORY.get(event.key)
    if category is not None and (game.layers_open or mods & pygame.KMOD_ALT):
        toggle(game, category)
        return True
    return False


def over_ui(game, pos):
    return game.layers_btn_rect.collidepoint(pos) or (game.layers_open and game.layers_panel_rect.collidepoint(pos))


def handle_click(game, pos):
    """True when the click landed on the LAYERS button or panel."""
    if game.layers_btn_rect.collidepoint(pos):
        game.layers_open = not game.layers_open
        return True
    if not (game.layers_open and game.layers_panel_rect.collidepoint(pos)):
        return False
    if game.layers_show_all_rect.collidepoint(pos):
        set_all(game, True)
    elif game.layers_hide_all_rect.collidepoint(pos):
        set_all(game, False)
    else:
        for rect, category in game.layers_rows:
            if rect.collidepoint(pos):
                toggle(game, category)
                break
    return True


# ------------------------------------------------------------------ drawing
def draw(game):
    """The LAYERS button (bottom-left) and, when open, the panel listing every category ON / OFF."""
    sw, sh = game.window.get_size()
    hidden = hidden_count(game)
    label = "LAYERS" if not hidden else f"LAYERS  ({hidden} off)"
    btn = pygame.Rect(0, 0, max(int(sw * 0.11), 150), max(30, int(sh * 0.055)))
    btn.bottomleft = (int(sw * 0.02), sh - int(sh * 0.03))
    game.layers_btn_rect = btn
    ui_theme.button(game.window, btn, label, selected=game.layers_open,
                    accent=ui_theme.GOLD if hidden else ui_theme.GREEN, small=True)

    game.layers_rows = []
    if not game.layers_open:
        game.layers_panel_rect = pygame.Rect(0, 0, 1, 1)
        return

    rows = len(LAYER_KEYS)
    height = 44 + rows * ROW_H + 52
    panel = pygame.Rect(0, 0, PANEL_W, height)
    panel.bottomleft = (btn.left, btn.top - 8)
    game.layers_panel_rect = panel
    ui_theme.panel(game.window, panel, (24, 14, 20, 238), (112, 64, 66), 2, 12)
    ui_theme.text(game.window, "LAYERS", (panel.left + 14, panel.top + 10), 16, ui_theme.CREAM, True)
    ui_theme.text(game.window, "1-9, 0 or click", (panel.right - 118, panel.top + 14), 12, ui_theme.MUTED)

    mouse = pygame.mouse.get_pos()
    y = panel.top + 40
    for _key, _kp, category in LAYER_KEYS:
        row = pygame.Rect(panel.left + 8, y, panel.width - 16, ROW_H - 3)
        game.layers_rows.append((row, category))
        off = category in game.hidden_layers
        if row.collidepoint(mouse):
            ui_theme.panel(game.window, row, (83, 37, 47, 200), None, 1, 7)
        dim = ui_theme.MUTED if off else ui_theme.WHITE
        ui_theme.text(game.window, LABELS[category], (row.left + 8, row.top + 5), 14, ui_theme.GOLD, True)
        pygame.draw.circle(game.window, (70, 60, 62) if off else DOT[category], (row.left + 40, row.centery), 6)
        ui_theme.text(game.window, pal.CATEGORY_NAMES[category], (row.left + 56, row.top + 5), 14, dim, True)
        pill = pygame.Rect(0, 0, 50, row.height - 6)
        pill.midright = (row.right - 6, row.centery)
        ui_theme.panel(game.window, pill, (60, 40, 44) if off else (36, 78, 50),
                       (112, 64, 66) if off else ui_theme.GREEN, 1, 8)
        ui_theme.text_centered(game.window, "OFF" if off else "ON", pill.center, 12,
                               ui_theme.MUTED if off else ui_theme.GREEN, True)
        y += ROW_H

    half = (panel.width - 24) // 2
    game.layers_show_all_rect = pygame.Rect(panel.left + 8, panel.bottom - 40, half, 30)
    game.layers_hide_all_rect = pygame.Rect(panel.left + 16 + half, panel.bottom - 40, half, 30)
    ui_theme.button(game.window, game.layers_show_all_rect, "SHOW ALL", accent=ui_theme.GREEN, small=True)
    ui_theme.button(game.window, game.layers_hide_all_rect, "HIDE ALL", accent=ui_theme.CORAL, small=True)
