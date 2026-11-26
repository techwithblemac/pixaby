"""
start_tools.py
==============
Authoring for the level's ``"start"`` entry -- the player spawn points.

The JSON shape (unchanged, this module just edits it):

    {"x": 384, "y": 896,
     "points": [[-1664, -832], [-704, -256], [384, 896]],
     "width": 64, "height": 64, "type": "start"}

``points`` is the pool of spawn coordinates; ``x``/``y`` is the primary
spawn, which the loader reads into ``self.start_points``. The pool is
what local co-op players get spread across, so a level needs at least one
and usually wants several.

Unlike every other placeable, there is exactly *one* ``start`` dict per
level -- placing a start point appends to its ``points`` list rather than
appending a new world entry, and deleting the last one is refused so a
level can never be saved with nowhere to spawn.
"""

import pygame

from ..main.draw_funcs import hide
from ...ui import ui_theme


def start_data(game, create=True):
    """The level's single ``start`` entry, created on demand."""
    for data in game.world:
        if isinstance(data, dict) and data.get("type") == "start":
            return data

    if not create:
        return None

    data = {
        "x": 0,
        "y": -64,
        "points": [[0, -64]],
        "width": 64,
        "height": 64,
        "type": "start",
    }
    game.world.append(data)
    return data


def _sync(game, data):
    """Push the JSON back onto the live world state the loader populates."""
    points = data.get("points") or [[data.get("x", 0), data.get("y", -64)]]
    data["points"] = points
    data["x"], data["y"] = points[0][0], points[0][1]
    game.points = points
    game.start_points = (data["x"], data["y"])


def add_start_point(game, grid_info):
    """Add the clicked cell to the spawn pool.

    Clicking a cell that is already a spawn point promotes it to primary
    instead of adding a duplicate -- that's the only way to choose which
    of several spawns the level opens on.
    """
    data = start_data(game)
    points = list(data.get("points") or [])
    x, y = grid_info[0].x, grid_info[0].y

    existing = next((p for p in points if p[0] == x and p[1] == y), None)
    if existing is not None:
        points.remove(existing)
        points.insert(0, existing)
        promoted = True
    else:
        points.append([x, y])
        promoted = False

    data["points"] = points
    _sync(game, data)
    return promoted


def remove_start_point(game, grid_info):
    """Drop the clicked cell from the spawn pool.

    Returns False when it would empty the pool, so the caller can say why
    nothing happened rather than silently doing nothing.
    """
    data = start_data(game, create=False)
    if not data:
        return False

    points = list(data.get("points") or [])
    x, y = grid_info[0].x, grid_info[0].y
    match = next((p for p in points if p[0] == x and p[1] == y), None)

    if match is None:
        return False
    if len(points) <= 1:
        return False

    points.remove(match)
    data["points"] = points
    _sync(game, data)
    return True


def draw_start_points(game):
    """Overlay the spawn pool: a numbered flag per point, P1 highlighted."""
    points = getattr(game, "points", None)
    if not points:
        return

    zoom = game.zoom
    font = ui_theme.font(max(9, int(12 * zoom)), True)

    for order, point in enumerate(points):
        try:
            px, py = int(point[0]), int(point[1])
        except (TypeError, ValueError, IndexError):
            continue

        world_rect = pygame.Rect(px, py, 64, 64)
        if hide(game, world_rect, "rect"):
            continue

        rect = pygame.Rect(
            int(px - game.offset_x) * zoom,
            int(py - game.offset_y) * zoom,
            int(64 * zoom),
            int(64 * zoom),
        )
        primary = order == 0
        color = ui_theme.GOLD if primary else ui_theme.CREAM

        pygame.draw.rect(game.window, color, rect, width=max(2, int(3 * zoom)))

        # Flag pole on the left edge, pennant pointing right.
        pole_x = rect.left + max(3, int(6 * zoom))
        pygame.draw.line(game.window, color,
                         (pole_x, rect.bottom - int(4 * zoom)),
                         (pole_x, rect.top + int(6 * zoom)),
                         max(2, int(3 * zoom)))
        pennant = [
            (pole_x, rect.top + int(6 * zoom)),
            (pole_x + int(30 * zoom), rect.top + int(15 * zoom)),
            (pole_x, rect.top + int(24 * zoom)),
        ]
        pygame.draw.polygon(game.window,
                            ui_theme.GOLD if primary else ui_theme.CORAL,
                            pennant)

        label = f"P{order + 1}" + (" \u2605" if primary else "")
        surf = font.render(label, True, color)
        game.window.blit(surf, surf.get_rect(
            midtop=(rect.centerx, rect.bottom + 2)))


def draw_start_preview(game, display_rect):
    """The HUD swatch for the start-point category."""
    rect = pygame.Rect(0, 0, 54, 54)
    rect.center = display_rect.center

    pygame.draw.rect(game.window, ui_theme.GOLD, rect, width=3)
    pygame.draw.line(game.window, ui_theme.GOLD,
                     (rect.left + 8, rect.bottom - 6),
                     (rect.left + 8, rect.top + 6), 3)
    pygame.draw.polygon(game.window, ui_theme.CORAL, [
        (rect.left + 8, rect.top + 6),
        (rect.left + 34, rect.top + 15),
        (rect.left + 8, rect.top + 24),
    ])

    count = len(getattr(game, "points", None) or [])
    ui_theme.text_centered(
        game.window, f"{count} SPAWN{'' if count == 1 else 'S'}",
        (display_rect.centerx, display_rect.bottom + 8),
        12, ui_theme.MUTED, True
    )
