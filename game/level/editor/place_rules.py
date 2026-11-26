"""
place_rules.py
==============
OVER / BEHIND: what happens when a move or a paste lands on cells that already hold something the placement
rules do not allow next to it (the same rules the editor applies when you place one object by hand:
``game.world_rules`` -- e.g. two blocks, two enemies, a deco on a block, anything on a door, ...).

    OVER     the incoming objects win: whatever they conflict with is removed ("replaces what needs replacing")
    BEHIND   what is already there wins: incoming objects that conflict are skipped (when moving, they stay
             where they were; when pasting, they are not pasted)

Tab (or the PLACE chip at the bottom of the screen) switches between them while using the Select tool.
Objects that do not conflict are always placed. The mode is remembered for the session; the default is OVER.

Two objects conflict when they share a grid cell and either one's tag is on the other's blacklist (the loader
decides by world order, so the check is made both ways to get the same answer whichever came first).
"""

import pygame

CELL = 64
BUCKET = 8                     # cells per spatial-hash bucket

# Used only if the loader has not built game.world_rules yet; identical to Level_Loader.prep().
DEFAULT_RULES = {
    "platforms": {"block_fore", "entities", "deco", "platforms", "treasure", "door", "trap"},
    "spawn_point": {"block_fore", "entities", "platforms", "door", "trap"},
    "door": {"block_fore", "entities", "platforms", "door", "start", "spawn_point", "trap"},
    "water": {"water"},
    "trap": {"block_fore", "trap", "deco", "platforms", "treasure", "door", "entities", "start"},
    "deco": {"block_fore", "deco", "platforms", "treasure", "trap"},
    "treasure": {"block_fore", "deco", "platforms", "block_back", "treasure", "trap"},
    "entities": {"block_fore", "entities", "platforms", "door", "trap"},
    "block_fore": {"block_fore", "entities", "deco", "platforms", "block_back", "door", "trap"},
    "block_back": {"block_fore", "block_back"},
    "start": {"block_fore", "platforms", "door", "trap"},
}

OVER, BEHIND = "over", "behind"
TOAST_MS = 2600


def mode(game):
    return getattr(game, "place_mode", OVER)


def toggle_mode(game):
    game.place_mode = BEHIND if mode(game) == OVER else OVER
    game.place_note = None
    return game.place_mode


def _rule_and_tag(item):
    """(blacklist key, grid tag) of a world entry, or None for things that never conflict."""
    kind = item.get("type")
    if kind == "block":
        key = f"block_{item.get('perspective', 'fore')}"
        return key, key
    if kind == "enemy":
        return "entities", "entities"
    if kind == "spawn_point":
        return "spawn_point", "entities"
    if kind in ("deco", "tree"):
        return "deco", "deco"
    if kind == "moving_platform":
        return "platforms", "platforms"
    if kind in ("door", "treasure", "trap", "water"):
        return kind, kind
    return None


def _box(game, item):
    bx, by = getattr(game, "minx", 0), getattr(game, "miny", 0)
    x, y = item.get("x", 0), item.get("y", 0)
    w, h = max(1, item.get("width", CELL)), max(1, item.get("height", CELL))
    return ((x - bx) // CELL, (y - by) // CELL, (x + w - 1 - bx) // CELL, (y + h - 1 - by) // CELL)


def _buckets(box):
    x0, y0, x1, y1 = box
    for bx in range(x0 // BUCKET, x1 // BUCKET + 1):
        for by in range(y0 // BUCKET, y1 // BUCKET + 1):
            yield bx, by


class _Index:
    """The objects that stay put, in a spatial hash so a big paste does not compare everything with everything."""

    def __init__(self, game, entries):
        self.game = game
        self.rules = getattr(game, "world_rules", None) or DEFAULT_RULES
        self.buckets = {}
        for index, item in entries:
            info = _rule_and_tag(item)
            if info is None:
                continue
            box = _box(game, item)
            record = (index, info[0], info[1], box)
            for key in _buckets(box):
                self.buckets.setdefault(key, []).append(record)

    def hits(self, item):
        """Indices of indexed objects that conflict with ``item``."""
        info = _rule_and_tag(item)
        if info is None:
            return set()
        rule, tag = info
        box = _box(self.game, item)
        found = set()
        for key in _buckets(box):
            for index, other_rule, other_tag, other in self.buckets.get(key, ()):
                if index in found:
                    continue
                if other[0] > box[2] or other[2] < box[0] or other[1] > box[3] or other[3] < box[1]:
                    continue
                if other_tag in self.rules.get(rule, ()) or tag in self.rules.get(other_rule, ()):
                    found.add(index)
        return found


def resolve_paste(game, world, incoming, how=None):
    """(indices of world entries to remove, set of incoming positions to skip)."""
    how = how or mode(game)
    index = _Index(game, [(i, d) for i, d in enumerate(world) if isinstance(d, dict)])
    remove, skip = set(), set()
    for n, item in enumerate(incoming):
        hit = index.hits(item)
        if not hit:
            continue
        if how == OVER:
            remove |= hit
        else:
            skip.add(n)
    return remove, skip


def resolve_move(game, world, indices, dx, dy, how=None, updates=None):
    """(indices of world entries to remove, set of moving indices that must stay where they are)."""
    how = how or mode(game)
    moving = set(indices)
    others = [(i, d) for i, d in enumerate(world) if i not in moving and isinstance(d, dict)]
    shifted = {i: dict(world[i], x=world[i].get("x", 0) + dx, y=world[i].get("y", 0) + dy, **(updates or {}))
               for i in moving}
    if how == OVER:
        index = _Index(game, others)
        remove = set()
        for item in shifted.values():
            remove |= index.hits(item)
        return remove, set()
    stay = set()
    while True:                                        # an item that stays becomes an obstacle for the others
        index = _Index(game, others + [(i, world[i]) for i in stay])
        newly = {i for i, item in shifted.items() if i not in stay and index.hits(item)}
        if not newly:
            return set(), stay
        stay |= newly


# ------------------------------------------------------------------ feedback
def toast(game, text):
    game.place_note = (text, pygame.time.get_ticks() + TOAST_MS)


def summary(how, removed, skipped, placed_word):
    if how == OVER:
        return f"{placed_word}  (OVER: replaced {removed})" if removed else f"{placed_word}  (OVER: nothing to replace)"
    return f"{placed_word}  (BEHIND: skipped {skipped})" if skipped else f"{placed_word}  (BEHIND: nothing in the way)"


def preview(game, items, dx, dy, moving=False):
    """What the ghost would do right now: (existing entries it would remove, ghost items that would be skipped).
    Cached because it is asked for every frame while a ghost is on screen."""
    how = mode(game)
    key = (how, dx, dy, len(game.world), len(items), bool(moving))
    cached = getattr(game, "_place_preview", None)
    if cached and cached[0] == key:
        return cached[1]
    if moving:
        remove, stay = resolve_move(game, game.world, game._selection_indices(), dx, dy, how)
        result = ([game.world[i] for i in remove], [game.world[i] for i in stay])
    else:
        shifted = [dict(d, x=d.get("x", 0) + dx, y=d.get("y", 0) + dy) for d in items]
        remove, skip = resolve_paste(game, game.world, shifted, how)
        result = ([game.world[i] for i in remove], [shifted[n] for n in skip])
    game._place_preview = (key, result)
    return result


def draw_chip(game):
    """The PLACE: OVER / BEHIND chip (bottom centre) while the Select tool is active, plus the result toast."""
    sw, sh = game.window.get_size()
    from ...ui import ui_theme
    now = pygame.time.get_ticks()
    note = getattr(game, "place_note", None)
    if note and now < note[1]:
        ui_theme.text_centered(game.window, note[0], (sw // 2, sh - 76), 15, ui_theme.CREAM, True)
    game.place_chip_rect = pygame.Rect(0, 0, 1, 1)
    if getattr(game, "TOOL", "insert") != "select":
        return
    how = mode(game)
    chip = pygame.Rect(0, 0, 310, 30)
    chip.midbottom = (sw // 2, sh - 28)
    game.place_chip_rect = chip
    label = "PLACE: OVER   (replaces)" if how == OVER else "PLACE: BEHIND   (keeps existing)"
    ui_theme.button(game.window, chip, label + "  [Tab]", selected=False,
                    accent=ui_theme.GOLD if how == OVER else ui_theme.GREEN, small=True)


def chip_click(game, pos):
    rect = getattr(game, "place_chip_rect", None)
    if rect is not None and getattr(game, "TOOL", "insert") == "select" and rect.collidepoint(pos):
        toggle_mode(game)
        return True
    return False
