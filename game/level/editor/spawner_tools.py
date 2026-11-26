"""
spawner_tools.py
================
Everything the level editor needs to place, preview and render
``spawn_point`` objects -- the continuous enemy spawners that already
existed in the level JSON format but had no way to be authored except by
hand-editing the file.

A spawner's JSON shape (unchanged, this module just writes it):

    {
      "x": 960, "y": -64, "width": 64, "height": 64,
      "interval": 4,        # seconds between spawns
      "limit": 12,          # max enemies this spawner ever produces
      "type": "spawn_point",
      "entities": [["Archer", "Red"], ["TNT", "Red"]]
    }

The roster (``entities``) is authored as a short text field -- e.g.
``Archer:Red, TNT:Red`` -- because the field popup only speaks
int/float/bool/choice/text. Parsing is deliberately forgiving about
separators and case but *strict* about the resulting values: a name or
colour that isn't in the engine's vocabulary is snapped back to the
current editor selection rather than written out to disk, since the
engine raises a KeyError on an unknown colour string.
"""

import math
import pygame

from ...scripts.functions import cache_assets
from ..main.draw_funcs import hide
from .editor_palette import ENTITY_NAMES, entity_colors
from ...ui import ui_theme


# ---------------------------------------------------------------------- #
# Roster parsing / formatting
# ---------------------------------------------------------------------- #

def _snap(value, options, fallback):
    """Case-insensitive match against a fixed vocabulary."""
    value = str(value).strip()
    for option in options:
        if option.lower() == value.lower():
            return option
    return fallback


def parse_roster(text, fallback_name="Pawn", fallback_color="Red"):
    """``"Archer:Red, TNT/Red"`` -> ``[["Archer", "Red"], ["TNT", "Red"]]``.

    Accepts ``:``, ``/`` or ``;`` between a name and its colour, and
    ``,`` or ``|`` between pairs. Unknown names/colours fall back to the
    current editor selection, and an empty result yields a single
    fallback pair so a spawner is never written with an empty roster
    (which would make ``random.choice`` raise at runtime).
    """
    colors = entity_colors()
    fallback_name = _snap(fallback_name, ENTITY_NAMES, "Pawn")
    fallback_color = _snap(fallback_color, colors, colors[0] if colors else "Red")

    pairs = []
    for chunk in str(text).replace("|", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue

        for separator in (":", "/", ";"):
            if separator in chunk:
                name, _, color = chunk.partition(separator)
                break
        else:
            name, color = chunk, fallback_color

        pair = [_snap(name, ENTITY_NAMES, fallback_name),
                _snap(color, colors, fallback_color)]
        if pair not in pairs:
            pairs.append(pair)

    return pairs or [[fallback_name, fallback_color]]


def format_roster(pairs):
    """The inverse of parse_roster, for pre-filling the popup field."""
    return ", ".join(f"{name}:{color}" for name, color in pairs)


# ---------------------------------------------------------------------- #
# Drawing
# ---------------------------------------------------------------------- #

def _entity_sprite(name, color, size):
    """First idle frame for an entity, via the central asset cache.

    Sprites are never loaded from an asset folder directly -- they come
    through cache_assets exactly like the real game classes do.
    """
    try:
        sprites = cache_assets((name, color, 'idle_right'))
        if sprites:
            return pygame.transform.scale(sprites[0], size)
    except Exception:
        pass
    return None


def _portal_ring(surface, center, radius, t, color, width=3):
    """A slowly rotating dashed ring -- reads as 'things come out of here'
    without needing a dedicated art asset."""
    dashes = 10
    for i in range(dashes):
        if i % 2:
            continue
        start = t * 1.1 + (i / dashes) * math.tau
        end = start + (math.tau / dashes)
        try:
            pygame.draw.arc(surface, color,
                            pygame.Rect(center[0] - radius, center[1] - radius,
                                        radius * 2, radius * 2),
                            start, end, width)
        except (ValueError, TypeError):
            return


def draw_spawner_preview(game, display_rect):
    """The 'currently selected item' swatch shown in the editor's HUD."""
    t = pygame.time.get_ticks() / 1000.0
    center = display_rect.center

    _portal_ring(game.window, center, 34, t, ui_theme.PURPLE, 3)
    _portal_ring(game.window, center, 26, -t * 1.4, ui_theme.CORAL, 2)

    sprite = _entity_sprite(game.type, game.size, (44, 44))
    if sprite:
        game.window.blit(sprite, sprite.get_rect(center=center))
    else:
        pygame.draw.circle(game.window, ui_theme.CORAL, center, 12)


def draw_spawn_points(game):
    """Overlay every placed spawner on the editor canvas.

    Spawners have no sprite of their own in gameplay (they are invisible
    logic), so they are drawn here as an editor-only overlay rather than
    being pushed into the shared draw list. That keeps the gameplay draw
    order and its hard-coded list indices untouched.
    """
    points = getattr(game, "spawn_points", None)
    if not points:
        return

    t = pygame.time.get_ticks() / 1000.0
    zoom = game.zoom
    font = ui_theme.font(max(9, int(11 * zoom)), True)

    for point in points:
        rect = getattr(point, "rect", None)
        if rect is None:
            continue
        if hide(game, rect, "rect"):
            continue

        screen_rect = pygame.Rect(
            int(rect.x - game.offset_x) * zoom,
            int(rect.y - game.offset_y) * zoom,
            int(rect.width * zoom),
            int(rect.height * zoom),
        )
        center = screen_rect.center
        radius = max(8, int(screen_rect.width * 0.46))

        glow = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*ui_theme.PURPLE, 55),
                           (radius + 4, radius + 4), radius)
        game.window.blit(glow, (center[0] - radius - 4, center[1] - radius - 4))

        _portal_ring(game.window, center, radius, t, ui_theme.PURPLE,
                     max(2, int(3 * zoom)))
        pygame.draw.rect(game.window, ui_theme.CORAL, screen_rect,
                         width=max(1, int(2 * zoom)))

        roster = getattr(point, "entities", None) or [["Pawn", "Red"]]
        name, color = roster[0][0], roster[0][1]
        sprite = _entity_sprite(name, color,
                                (int(38 * zoom) or 1, int(38 * zoom) or 1))
        if sprite:
            game.window.blit(sprite, sprite.get_rect(center=center))

        label = f"x{getattr(point, 'limit', '?')} / {getattr(point, 'interval', '?')}s"
        surf = font.render(label, True, ui_theme.CREAM)
        game.window.blit(surf, surf.get_rect(
            midtop=(center[0], screen_rect.bottom + 2)))

        if len(roster) > 1:
            extra = font.render(f"+{len(roster) - 1}", True, ui_theme.GOLD)
            game.window.blit(extra, extra.get_rect(
                midbottom=(center[0], screen_rect.top - 2)))
