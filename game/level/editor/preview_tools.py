"""
preview_tools.py
================
Authoring for the level's MAP PREVIEW point (the ``{"type": "preview coordinates", "x": 0, "y": 0}`` entry,
see level/preview.py). Press V in the level editor:

    * a popup shows X and Y (the current values, or the middle of what the camera is looking at when the
      level has none yet) -- type the numbers you want;
    * "Remove preview" deletes the entry (the selector then says NO MAP PREVIEW);
    * Escape / Cancel changes nothing.

The point is drawn on the map as a cross with the outline of the part the selector will show.
"""

import pygame

from .. import preview
from ...ui import ui_theme
from ...ui.ui_popup import run_field_popup

COORD_LIMIT = 100000


def _view_center(game):
    """World position at the middle of the editor window (what the camera looks at)."""
    zoom = getattr(game, "zoom", 1) or 1
    w, h = game.window.get_size()
    return (int(getattr(game, "offset_x", 0) + w / 2 / zoom),
            int(getattr(game, "offset_y", 0) + h / 2 / zoom))


def edit_preview(game):
    """Open the popup. Returns True if the level's preview value changed."""
    current = preview.point(game.world)
    cx, cy = current if current else _view_center(game)

    fields = [
        {"key": "x", "label": "X (world)", "type": "int", "default": cx, "min": -COORD_LIMIT, "max": COORD_LIMIT},
        {"key": "y", "label": "Y (world)", "type": "int", "default": cy, "min": -COORD_LIMIT, "max": COORD_LIMIT},
    ]
    if current:
        fields.append({"key": "remove", "label": "Remove preview", "type": "bool", "default": False})

    if not hasattr(game, "_popup_title_font"):
        game._popup_title_font = pygame.font.SysFont("consolas", 26, bold=True)
        game._popup_label_font = pygame.font.SysFont("consolas", 18)
        game._popup_value_font = pygame.font.SysFont("consolas", 20, bold=True)

    values = run_field_popup(game.window, game.clock, game._popup_title_font, game._popup_label_font,
                             game._popup_value_font, "MAP PREVIEW", fields)
    if values is None:                      # cancelled: nothing changes, and a level with no preview stays without
        return False

    if values.get("remove"):
        game._checkpoint()
        changed = preview.clear(game.world)
    else:
        x, y = int(values["x"]), int(values["y"])
        if current == (x, y):
            return False
        game._checkpoint()
        preview.set_point(game.world, x, y)
        changed = True

    if changed:
        game.changes.add("preview")
        game._draw_list_dirty = True
    return changed


def draw_preview_point(game):
    """Overlay: a cross at the preview point and the outline of the area the selector will show."""
    pt = preview.point(game.world)
    if pt is None:
        return
    zoom = game.zoom
    sx = int((pt[0] - game.offset_x) * zoom)
    sy = int((pt[1] - game.offset_y) * zoom)
    w = int(preview.VIEW_W * zoom)
    h = int(preview.VIEW_H * zoom)
    color = ui_theme.PURPLE

    frame = pygame.Rect(0, 0, w, h)
    frame.center = (sx, sy)
    pygame.draw.rect(game.window, color, frame, width=2)
    arm = max(8, int(24 * zoom))
    pygame.draw.line(game.window, color, (sx - arm, sy), (sx + arm, sy), 3)
    pygame.draw.line(game.window, color, (sx, sy - arm), (sx, sy + arm), 3)

    surf = ui_theme.font(max(9, int(12 * zoom)), True).render(f"MAP PREVIEW  {pt[0]}, {pt[1]}", True, color)
    game.window.blit(surf, surf.get_rect(midbottom=(sx, frame.top - 4)))
