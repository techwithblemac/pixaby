"""
Field-editor popup for the level editor (edit_world / windows.py).

Replaces the old `Game.enter_text()` flow, where an object's values were
edited as one raw, unlabeled ``"width;height"`` / ``"-1,1;1;100"`` style
string the developer had to remember the position of by heart.

This shows a floating, centered panel with one labeled row per value.
Each row knows its own type (int / float / bool / choice / text) and
rejects keystrokes that can't be valid for that type, so you can't end up
with a broken value in the first place. Confirming with an out-of-range
number keeps the popup open and points at the offending field instead of
silently placing a bad object.

Usage (see main.py add_block / add_water / add_platform for real call
sites):

    fields = [
        {"key": "width",  "label": "Width",  "type": "int", "default": 100, "min": 1, "max": 4000},
        {"key": "height", "label": "Height", "type": "int", "default": 20,  "min": 1, "max": 4000},
        {"key": "moving", "label": "Moving", "type": "bool", "default": True},
        {"key": "dir_x",  "label": "Direction X", "type": "choice", "options": [-1, 1], "default": 1},
    ]
    result = game.open_field_popup("Platform Settings", fields)
    if result is None:
        # user cancelled (Escape) - caller decides what to do
        ...
    else:
        width = result["width"]
"""

import sys
import pygame

from . import ui_theme


# Palette comes straight from ui_theme -- the same source the level
# selector, the loading screen and the editor's own overlays read from.
# This popup used to carry its own navy/violet scheme, which made it the
# one surface in the game that didn't look like the game.
PANEL_BG = (37, 23, 31, 242)
PANEL_BORDER = ui_theme.CORAL
TITLE_COLOR = ui_theme.CREAM
LABEL_COLOR = ui_theme.MUTED
VALUE_COLOR = ui_theme.WHITE
FIELD_BG = (32, 18, 26)
FIELD_BG_FOCUS = (60, 30, 39)
FIELD_BORDER = (112, 64, 66)
FIELD_BORDER_FOCUS = ui_theme.GOLD
FIELD_BORDER_ERROR = ui_theme.RED
ERROR_COLOR = ui_theme.RED
BOOL_TRUE_COLOR = (38, 74, 47)
BOOL_FALSE_COLOR = (82, 32, 38)
BOOL_TRUE_BORDER = ui_theme.GREEN
BOOL_FALSE_BORDER = ui_theme.RED
CONFIRM_COLOR = (48, 84, 54)
CONFIRM_GLOW = ui_theme.GREEN
CANCEL_COLOR = (74, 34, 42)
CANCEL_GLOW = ui_theme.MUTED
HINT_COLOR = ui_theme.MUTED
OVERLAY_ALPHA = 165


class FieldPopup:
    """A single modal popup with one or more labeled, typed fields."""

    def __init__(self, screen, title_font, label_font, value_font, title, fields):
        self.screen = screen
        # Snapshot the scene once, then re-blit it every frame. The popup
        # draws over whatever is already on the window, so dimming
        # per-frame without a snapshot would fade the editor to black.
        self.backdrop = screen.copy()
        self.title_font = title_font
        self.label_font = label_font
        self.value_font = value_font
        self.title = title
        self.fields = fields
        self.focus = 0
        self.error = ""
        self.done = False
        self.cancelled = False

        # Clickable regions populated fresh each draw() call.
        self._field_rects = []
        self._confirm_rect = None
        self._cancel_rect = None

        for field in self.fields:
            field.setdefault("min", None)
            field.setdefault("max", None)
            if field["type"] == "bool":
                field["value"] = bool(field.get("default", False))
            elif field["type"] == "choice":
                options = field["options"]
                default = field.get("default", options[0])
                field["index"] = options.index(default) if default in options else 0
                field["value"] = options[field["index"]]
            else:
                field["buffer"] = str(field.get("default", ""))
        
        sw, sh = self.screen.get_size()
        
        row_h = 46
        pad = 20
        panel_w = 420
        panel_h = pad * 2 + 46 + len(self.fields) * row_h + (24 if self.error else 0) + 60

        self.panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
        self.panel_rect.center = (sw // 2, sh // 2)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            self._handle_key(event)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_mouse(event.pos)

    def _handle_key(self, event):
        field = self.fields[self.focus]

        if event.key == pygame.K_TAB:
            step = -1 if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 1
            self.focus = (self.focus + step) % len(self.fields)
            self.error = ""
            return

        if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
            if self._validate_all():
                self.done = True
            return

        if event.key == pygame.K_ESCAPE:
            self.cancelled = True
            self.done = True
            return

        if field["type"] in ("bool", "choice"):
            if event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_SPACE):
                direction = -1 if event.key in (pygame.K_UP, pygame.K_LEFT) else 1
                self._cycle(field, direction)
                return

        if field["type"] in ("int", "float", "text"):
            self._handle_text_key(field, event)

    def _handle_text_key(self, field, event):
        buf = field["buffer"]
        if event.key == pygame.K_BACKSPACE:
            field["buffer"] = buf[:-1]
            self.error = ""
            return

        ch = event.unicode
        if not ch:
            return

        if field["type"] == "int":
            if ch.isdigit():
                field["buffer"] = buf + ch
            elif ch == "-" and buf == "":
                field["buffer"] = buf + ch
        elif field["type"] == "float":
            if ch.isdigit():
                field["buffer"] = buf + ch
            elif ch == "." and "." not in buf:
                field["buffer"] = buf + ch
            elif ch == "-" and buf == "":
                field["buffer"] = buf + ch
        else:  # free text
            if ch.isprintable():
                field["buffer"] = buf + ch

        self.error = ""

    def _cycle(self, field, direction):
        if field["type"] == "bool":
            field["value"] = not field["value"]
        else:
            field["index"] = (field["index"] + direction) % len(field["options"])
            field["value"] = field["options"][field["index"]]
        self.error = ""

    def _handle_mouse(self, pos):
        if not self.panel_rect.collidepoint(pos):
            self.cancelled = True
            self.done = True
            return

        for index, rect in self._field_rects:
            if rect.collidepoint(pos):
                self.focus = index
                field = self.fields[index]
                if field["type"] in ("bool", "choice"):
                    self._cycle(field, 1)
                self.error = ""
                return

        if self._confirm_rect and self._confirm_rect.collidepoint(pos):
            if self._validate_all():
                self.done = True
            return

        if self._cancel_rect and self._cancel_rect.collidepoint(pos):
            self.cancelled = True
            self.done = True

    # ------------------------------------------------------------------
    # Validation / result
    # ------------------------------------------------------------------
    def _validate_all(self):
        for index, field in enumerate(self.fields):
            if field["type"] in ("int", "float"):
                raw = field["buffer"]
                try:
                    value = int(raw) if field["type"] == "int" else float(raw)
                except ValueError:
                    self.focus = index
                    self.error = f"{field['label']} needs a valid number"
                    return False

                if field["min"] is not None and value < field["min"]:
                    self.focus = index
                    self.error = f"{field['label']} must be at least {field['min']}"
                    return False

                if field["max"] is not None and value > field["max"]:
                    self.focus = index
                    self.error = f"{field['label']} must be at most {field['max']}"
                    return False

                field["value"] = value

            elif field["type"] == "text":
                field["value"] = field["buffer"]

        return True

    def result(self):
        return {field["key"]: field["value"] for field in self.fields}

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self):
        sw, sh = self.screen.get_size()

        if self.backdrop.get_size() == (sw, sh):
            self.screen.blit(self.backdrop, (0, 0))
        ui_theme.dim_overlay(self.screen, OVERLAY_ALPHA)

        row_h = 46
        pad = 20
        panel_w = min(420, max(280, sw - 40))
        panel_h = pad * 2 + 46 + len(self.fields) * row_h + (24 if self.error else 0) + 60

        self.panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
        self.panel_rect.center = (sw // 2, sh // 2)

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(panel, PANEL_BG, panel.get_rect(), border_radius=14)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), width=2, border_radius=14)
        self.screen.blit(panel, self.panel_rect.topleft)

        title_surf = self.title_font.render(self.title, True, TITLE_COLOR)
        title_rect = title_surf.get_rect(midtop=(self.panel_rect.centerx, self.panel_rect.top + pad))
        self.screen.blit(title_surf, title_rect)
        pygame.draw.line(self.screen, (92, 50, 57),
                         (self.panel_rect.left + pad, title_rect.bottom + 7),
                         (self.panel_rect.right - pad, title_rect.bottom + 7), 1)

        self._field_rects = []
        y = title_rect.bottom + 14
        field_x = self.panel_rect.left + pad
        field_w = panel_w - pad * 2

        for index, field in enumerate(self.fields):
            focused = index == self.focus
            row_rect = pygame.Rect(field_x, y, field_w, row_h - 10)
            self._field_rects.append((index, row_rect))

            label_surf = self.label_font.render(field["label"], True, LABEL_COLOR)
            self.screen.blit(label_surf, (row_rect.left, row_rect.centery - label_surf.get_height() // 2))

            value_w = 150
            value_rect = pygame.Rect(row_rect.right - value_w, row_rect.top, value_w, row_rect.height)

            has_error = focused and self.error
            border_color = FIELD_BORDER_ERROR if has_error else (FIELD_BORDER_FOCUS if focused else FIELD_BORDER)
            bg_color = FIELD_BG_FOCUS if focused else FIELD_BG

            if field["type"] == "bool":
                bg_color = BOOL_TRUE_COLOR if field["value"] else BOOL_FALSE_COLOR
                if not focused:
                    border_color = BOOL_TRUE_BORDER if field["value"] else BOOL_FALSE_BORDER
                text = "ON" if field["value"] else "OFF"
            elif field["type"] == "choice":
                text = str(field["value"])
            else:
                text = field["buffer"]
                if focused and (pygame.time.get_ticks() // 500) % 2 == 0:
                    text += "|"

            pygame.draw.rect(self.screen, bg_color, value_rect, border_radius=8)
            pygame.draw.rect(self.screen, border_color, value_rect, width=2, border_radius=8)

            value_surf = self.value_font.render(text, True, VALUE_COLOR)
            value_text_rect = value_surf.get_rect(center=value_rect.center)
            self.screen.blit(value_surf, value_text_rect)

            if field["type"] == "choice" and len(field["options"]) > 1:
                hint = self.label_font.render("< tab/click >", True, HINT_COLOR)
                self.screen.blit(hint, (value_rect.left - hint.get_width() - 8,
                                        value_rect.centery - hint.get_height() // 2))

            y += row_h

        if self.error:
            err_surf = self.label_font.render(self.error, True, ERROR_COLOR)
            err_rect = err_surf.get_rect(midtop=(self.panel_rect.centerx, y))
            self.screen.blit(err_surf, err_rect)
            y += 24

        btn_w, btn_h = 130, 42
        gap = 20
        total_w = btn_w * 2 + gap
        btn_y = self.panel_rect.bottom - pad - btn_h

        self._confirm_rect = pygame.Rect(self.panel_rect.centerx - total_w // 2, btn_y, btn_w, btn_h)
        self._cancel_rect = pygame.Rect(self.panel_rect.centerx + total_w // 2 - btn_w, btn_y, btn_w, btn_h)

        self._draw_button(self._confirm_rect, "CONFIRM", CONFIRM_COLOR, CONFIRM_GLOW)
        self._draw_button(self._cancel_rect, "CANCEL", CANCEL_COLOR, CANCEL_GLOW)

        ui_theme.text_centered(
            self.screen, "TAB  move    ENTER  confirm    ESC  cancel",
            (self.panel_rect.centerx, btn_y - 12), 10, HINT_COLOR
        )

    def _draw_button(self, rect, text, color, glow_color):
        mouse_pos = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse_pos)

        if hovered:
            glow = pygame.Surface((rect.width + 10, rect.height + 10), pygame.SRCALPHA)
            pygame.draw.rect(glow, glow_color + (100,), glow.get_rect(), border_radius=12)
            self.screen.blit(glow, (rect.x - 5, rect.y - 5))

        pygame.draw.rect(self.screen, color, rect, border_radius=9)
        pygame.draw.rect(self.screen, glow_color, rect, width=2 if hovered else 1, border_radius=9)
        text_surf = self.value_font.render(
            text, True, ui_theme.CREAM if hovered else ui_theme.WHITE)
        text_rect = text_surf.get_rect(center=rect.center)
        self.screen.blit(text_surf, text_rect)


def run_field_popup(screen, clock, title_font, label_font, value_font, title, fields):
    """
    Blocking loop that drives a FieldPopup to completion.

    Returns a ``{key: value}`` dict on confirm, or ``None`` if the user
    cancelled with Escape / the Cancel button.
    """
    popup = FieldPopup(screen, title_font, label_font, value_font, title, fields)

    while not popup.done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            popup.handle_event(event)

        popup.draw()
        pygame.display.update()
        clock.tick(60)

    return None if popup.cancelled else popup.result()
