"""
entity_editor.py
================
The ENTITY EDITOR: the window that opens when you click an enemy with the level editor's MODIFY tool (and, with
a different schema, a Homing Arrow Trap).

    left   the entity (animated), a summary, and its CATEGORIES - every tweak is grouped. A coloured badge shows
           how many things in a category differ from the default.
    right  the rows of the chosen category. Numbers get a slider, a - / + stepper and a typed value; switches
           are real switches; shop items show level pips. A row that differs from the default has a dot you
           can click to reset it.

Keyboard: UP/DOWN pick a row, LEFT/RIGHT change it (SHIFT = x10), [ ] or TAB switch category, type digits to
enter an exact number, ENTER = apply, ESC = cancel. Mouse: click, drag the sliders, wheel to scroll.

``edit_entity(game, data)`` -> ``{"data": {...}, "mods": {...}}`` or None when cancelled; the caller
(level/editor/object_edit.py) writes it into the world entry.  The schema is data/entity_mods.py.
"""

import math
import sys
import time

import pygame

from . import ui_theme as ui
from . import ui_fx as fx
from .window_kit import (txt, fit, wrap, panel, tag, key_glyph, sprite_frames, frame_at, draw_window_frame,
                         BORDER, BORDER_2)
from ..data import entity_mods as schema
from ..data.entity_mods import FIELDS, CATEGORIES, ITEM_CATEGORIES

ROW_H = 58
ITEM_H = 66
SIDE_W = 290


# ---------------------------------------------------------------------- #
# value helpers
# ---------------------------------------------------------------------- #
def _same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-6
    return a == b


def _fmt(field, value):
    scale = field.get("scale", 1)
    kind = field["type"]
    if kind == "bool":
        return "ON" if value else "OFF"
    if kind == "choice":
        return str(value).upper()
    if kind == "text":
        return str(value)
    shown = value * scale
    text = f"{int(round(shown))}" if kind == "int" or scale != 1 and abs(shown - round(shown)) < 1e-6 else f"{round(shown, 3):g}"
    return text


def _clamp(field, value):
    lo, hi = field.get("min"), field.get("max")
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return int(round(value)) if field["type"] == "int" else round(float(value), 4)


class TweakWindow:
    """A modal, categorised tweak editor. Build with a schema, ``run()`` returns the values or None."""

    def __init__(self, window, clock, title, subject, categories, fields, values, items=None, levels=None,
                 on_kit=None):
        self.win, self.clock = window, clock
        self.backdrop = window.copy()
        self.title = title
        self.subject = subject            # {"name", "color", "icon", "subtitle"} for the header card
        self.categories = categories      # [(id, label, accent, blurb)]
        self.fields = fields              # {cat_id: [field, ...]}
        self.items = items or []          # grantable shop items
        self.values = dict(values)
        self.levels = dict(levels or {})
        self.defaults = {f["key"]: f["default"] for fs in fields.values() for f in fs}
        self.on_kit = on_kit
        self.cat = 0
        self.sel = 0
        self.scroll = 0.0
        self.scroll_goal = 0.0
        self.edit = None                  # (row key, buffer) while typing
        self.t = 0.0
        self.hits = []
        self.drag = None
        self.done = False
        self.result = None
        self.toast = ("", 0.0)
        self.frames = sprite_frames(subject.get("name", "Pawn"), subject.get("color", "Blue"), "idle_right", 110) \
            if subject.get("name") else []

    # ------------------------------------------------------------------ rows
    def rows(self, cat=None):
        cid = self.categories[self.cat if cat is None else cat][0]
        if cid.startswith("i_"):
            return [("item", it) for it in self.items if it["cat"] == cid]
        rows = [("field", f) for f in self.fields.get(cid, [])]
        if cid == "boss" and self.on_kit:
            rows.insert(0, ("kit", None))
        return rows

    def changed(self, cat):
        cid = self.categories[cat][0]
        if cid.startswith("i_"):
            return sum(1 for it in self.items if it["cat"] == cid and self.levels.get(it["id"], 0) > 0)
        return sum(1 for f in self.fields.get(cid, []) if not _same(self.values[f["key"]], f["default"]))

    def total_changed(self):
        return sum(self.changed(i) for i in range(len(self.categories)))

    # ------------------------------------------------------------------ edits
    def set_value(self, field, value):
        if field["type"] in ("int", "float"):
            value = _clamp(field, value)
        self.values[field["key"]] = value

    def step(self, row, direction, big=False):
        kind, obj = row
        if kind == "item":
            level = self.levels.get(obj["id"], 0) + direction
            self.levels[obj["id"]] = max(0, min(obj["max"], level))
            return
        if kind == "kit":
            return
        f = obj
        k = f["key"]
        if f["type"] == "bool":
            self.values[k] = not self.values[k]
        elif f["type"] == "choice":
            opts = f["options"]
            self.values[k] = opts[(opts.index(self.values[k]) + direction) % len(opts)]
        elif f["type"] in ("int", "float"):
            step = f.get("step", 1) * (10 if big else 1)
            self.set_value(f, self.values[k] + direction * step)

    def reset_row(self, row):
        kind, obj = row
        if kind == "item":
            self.levels[obj["id"]] = 0
        elif kind == "field":
            self.values[obj["key"]] = obj["default"]

    def reset_category(self):
        for row in self.rows():
            self.reset_row(row)
        self.say("Category reset")

    def say(self, text):
        self.toast = (text, 2.2)

    def commit_edit(self):
        if not self.edit:
            return
        key, buf = self.edit
        self.edit = None
        for fs in self.fields.values():
            for f in fs:
                if f["key"] == key:
                    if f["type"] == "text":
                        self.values[key] = buf
                    else:
                        try:
                            self.set_value(f, float(buf) / f.get("scale", 1))
                        except ValueError:
                            self.say("That is not a number")
                    return

    def goto(self, cat):
        self.commit_edit()
        self.cat = cat % len(self.categories)
        self.sel = 0
        self.scroll = self.scroll_goal = 0.0

    # ------------------------------------------------------------------ input
    def handle(self, ev):
        rows = self.rows()
        if ev.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if ev.type == pygame.KEYDOWN:
            self.on_key(ev, rows)
        elif ev.type == pygame.MOUSEWHEEL:
            self.scroll_goal -= ev.y * 70
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.on_click(ev.pos)
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            self.drag = None
        elif ev.type == pygame.MOUSEMOTION and self.drag and ev.buttons[0]:
            self.slide(self.drag, ev.pos[0])

    def on_key(self, ev, rows):
        key = ev.key
        big = bool(ev.mod & pygame.KMOD_SHIFT)
        if self.edit:
            k, buf = self.edit
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.commit_edit()
            elif key == pygame.K_ESCAPE:
                self.edit = None
            elif key == pygame.K_BACKSPACE:
                self.edit = (k, buf[:-1])
            elif ev.unicode and ev.unicode.isprintable():
                self.edit = (k, buf + ev.unicode)
            return
        if key == pygame.K_ESCAPE:
            self.done, self.result = True, None
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.done, self.result = True, True
        elif key in (pygame.K_TAB, pygame.K_RIGHTBRACKET, pygame.K_PAGEDOWN):
            self.goto(self.cat + (-1 if big and key == pygame.K_TAB else 1))
        elif key in (pygame.K_LEFTBRACKET, pygame.K_PAGEUP):
            self.goto(self.cat - 1)
        elif key == pygame.K_UP:
            self.sel = max(0, self.sel - 1)
            self.reveal(rows)
        elif key == pygame.K_DOWN:
            self.sel = min(len(rows) - 1, self.sel + 1)
            self.reveal(rows)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT) and rows:
            self.step(rows[self.sel], -1 if key == pygame.K_LEFT else 1, big)
        elif key == pygame.K_SPACE and rows and rows[self.sel][0] == "field" and rows[self.sel][1]["type"] in ("bool", "choice"):
            self.step(rows[self.sel], 1)
        elif key == pygame.K_DELETE and rows:
            self.reset_row(rows[self.sel])
        elif rows and rows[self.sel][0] == "field":
            f = rows[self.sel][1]
            ch = ev.unicode
            if f["type"] == "text" and ch and ch.isprintable():
                self.edit = (f["key"], str(self.values[f["key"]]) + ch)
            elif f["type"] in ("int", "float") and ch and (ch.isdigit() or ch in "-."):
                self.edit = (f["key"], ch)

    def reveal(self, rows):
        top = sum(self.row_h(r) for r in rows[:self.sel])
        bottom = top + self.row_h(rows[self.sel])
        view = self.view_h
        if top < self.scroll_goal:
            self.scroll_goal = top
        elif bottom > self.scroll_goal + view:
            self.scroll_goal = bottom - view

    @staticmethod
    def row_h(row):
        return ITEM_H if row[0] == "item" else ROW_H

    def slide(self, hit, mx):
        rect, field = hit
        frac = max(0.0, min(1.0, (mx - rect.x) / max(1, rect.w)))
        lo, hi = field["min"], field["max"]
        value = lo + (hi - lo) * frac
        step = field.get("step", 1)
        self.set_value(field, round(value / step) * step)

    def on_click(self, pos):
        for rect, action, arg in reversed(self.hits):
            if not rect.collidepoint(pos):
                continue
            if action == "cat":
                self.goto(arg)
            elif action == "row":
                self.commit_edit()
                self.sel = arg
            elif action == "step":
                self.sel = arg[0]
                self.step(self.rows()[arg[0]], arg[1], bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))
            elif action == "level":
                self.sel = arg[0]
                self.levels[arg[1]["id"]] = 0 if self.levels.get(arg[1]["id"], 0) == arg[2] else arg[2]
            elif action == "slider":
                self.drag = (rect, arg)
                self.slide(self.drag, pos[0])
            elif action == "type":
                self.commit_edit()
                f = arg
                self.edit = (f["key"], str(self.values[f["key"]]) if f["type"] == "text" else _fmt(f, self.values[f["key"]]))
            elif action == "reset":
                self.reset_row(arg)
            elif action == "apply":
                self.commit_edit()
                self.done, self.result = True, True
            elif action == "cancel":
                self.done, self.result = True, None
            elif action == "reset_cat":
                self.reset_category()
            elif action == "kit":
                self.on_kit(self)
            return

    # ------------------------------------------------------------------ drawing
    def frame_rect(self):
        w, h = self.win.get_size()
        r = pygame.Rect(0, 0, min(w - 24, 1180), min(h - 24, 760))
        r.center = (w // 2, h // 2)
        return r

    def draw(self, dt):
        win = self.win
        w, h = win.get_size()
        if self.backdrop.get_size() == (w, h):
            win.blit(self.backdrop, (0, 0))
        ui.dim_overlay(win, 190)
        frame = self.frame_rect()
        close = draw_window_frame(win, frame, self.title, self.t, close=False)
        self.hits = []
        top = frame.y + max(18, int(frame.h * 0.055)) + 44
        body = pygame.Rect(frame.x + 22, top, frame.w - 44, frame.bottom - top - 78)
        side = pygame.Rect(body.x, body.y, SIDE_W, body.h)
        main = pygame.Rect(side.right + 18, body.y, body.right - side.right - 18, body.h)
        self.draw_side(side)
        self.draw_main(main)
        self.draw_footer(frame)
        if self.toast[1] > 0:
            s = txt(self.toast[0], 15, ui.INK, True)
            r = s.get_rect(center=(frame.centerx, frame.bottom - 92)).inflate(26, 12)
            pygame.draw.rect(win, ui.GOLD, r, border_radius=r.h // 2)
            win.blit(s, s.get_rect(center=r.center))

    def draw_side(self, rect):
        win = self.win
        # --- subject card
        card = pygame.Rect(rect.x, rect.y, rect.w, 132)
        panel(win, card, (40, 27, 36, 235), (110, 66, 68), 2, 14)
        img = frame_at(self.frames, self.t)
        if img is not None:
            win.blit(img, img.get_rect(midbottom=(card.x + 62, card.bottom - 12)))
        else:
            icon = self.subject.get("icon")
            if icon is not None:
                win.blit(icon, icon.get_rect(center=(card.x + 62, card.centery)))
        name = self.subject.get("name", "")
        win.blit(txt(fit(name, 24, True, card.w - 140), 24, ui.CREAM, True), (card.x + 118, card.y + 14))
        win.blit(txt(fit(self.subject.get("subtitle", ""), 13, False, card.w - 130), 13, ui.MUTED), (card.x + 118, card.y + 44))
        n = self.total_changed()
        chip = f"{n} TWEAK{'S' if n != 1 else ''}" if n else "STOCK"
        tag(win, (card.x + 118, card.y + 68), chip, ui.GOLD if n else (120, 110, 120), 12)
        x = card.x + 118
        y = card.y + 96
        for label, col in self.badges():
            r = tag(win, (x, y), label, col, 11)
            x = r.right + 4
            if x > card.right - 40:
                break
        # --- category list
        y = card.bottom + 12
        cats = list(enumerate(self.categories))
        groups = 2 if any(c[0].startswith('i_') for c in self.categories) and any(not c[0].startswith('i_') for c in self.categories) else 1
        ch_fit = max(26, min(38, (rect.bottom - y - 18 * groups) // max(1, len(cats))))
        last_group = None
        for i, (cid, label, accent, blurb) in cats:
            group = "items" if cid.startswith("i_") else "tweaks"
            if group != last_group:
                last_group = group
                head = "SHOP ITEMS" if group == "items" else "TWEAKS"
                win.blit(txt(head, 11, (150, 130, 130), True), (rect.x + 6, y))
                y += 17
            ch = ch_fit
            r = pygame.Rect(rect.x, y, rect.w, ch - 4)
            active = i == self.cat
            hover = r.collidepoint(pygame.mouse.get_pos())
            panel(win, r, (68, 36, 48, 245) if active else (46, 29, 39, 220 if hover else 160),
                  accent if active else (96, 60, 62), 2 if active else 1, 10)
            pygame.draw.rect(win, accent, (r.x + 6, r.y + 7, 5, r.h - 14), border_radius=3)
            win.blit(txt(label, 15, ui.CREAM if active else (214, 200, 200), True), (r.x + 22, r.centery - 9))
            c = self.changed(i)
            if c:
                badge = txt(str(c), 12, ui.INK, True)
                br = badge.get_rect(midright=(r.right - 12, r.centery)).inflate(12, 4)
                pygame.draw.rect(win, accent, br, border_radius=br.h // 2)
                win.blit(badge, badge.get_rect(center=br.center))
            self.hits.append((r, "cat", i))
            y += ch

    def badges(self):
        v = self.values
        out = []
        if v.get("boss"):
            out.append(("BOSS", (255, 210, 70)))
        if v.get("dash"):
            out.append(("DASH", (150, 220, 255)))
        if v.get("trap"):
            out.append(("TRAPS", (240, 150, 40)))
        if v.get("homing"):
            out.append(("HOMING", (255, 202, 80)))
        if v.get("regen"):
            out.append(("REGEN", (110, 220, 130)))
        if v.get("posted"):
            out.append(("POSTED", (122, 200, 255)))
        items = sum(1 for lv in self.levels.values() if lv)
        if items:
            out.append((f"{items} ITEM{'S' if items != 1 else ''}", (240, 150, 200)))
        return out

    def draw_main(self, rect):
        win = self.win
        cid, label, accent, blurb = self.categories[self.cat]
        win.blit(txt(label, 22, accent, True), (rect.x, rect.y - 2))
        win.blit(txt(fit(blurb, 14, False, rect.w - 150), 14, ui.MUTED), (rect.x, rect.y + 26))
        hr = pygame.Rect(rect.right - 134, rect.y, 134, 28)
        hover = hr.collidepoint(pygame.mouse.get_pos())
        panel(win, hr, (62, 32, 44, 240) if hover else (42, 26, 36, 220), (110, 66, 68), 1, 14)
        win.blit(txt("RESET GROUP", 12, ui.CREAM if hover else (200, 185, 185), True),
                 txt("RESET GROUP", 12, ui.CREAM, True).get_rect(center=hr.center))
        self.hits.append((hr, "reset_cat", None))

        view = pygame.Rect(rect.x, rect.y + 54, rect.w, rect.h - 54)
        self.view_h = view.h
        rows = self.rows()
        total = sum(self.row_h(r) for r in rows)
        self.scroll_goal = max(0, min(self.scroll_goal, max(0, total - view.h)))
        self.scroll += (self.scroll_goal - self.scroll) * 0.35
        if abs(self.scroll - self.scroll_goal) < 0.4:
            self.scroll = self.scroll_goal
        self.sel = max(0, min(self.sel, len(rows) - 1))

        old = win.get_clip()
        win.set_clip(view)
        y = view.y - int(self.scroll)
        for i, row in enumerate(rows):
            h = self.row_h(row)
            if y + h > view.y - 4 and y < view.bottom + 4:
                r = pygame.Rect(view.x, y, view.w - 14, h - 6)
                self.draw_row(i, row, r, accent)
            y += h
        win.set_clip(old)
        if total > view.h:                                           # scrollbar
            bar = pygame.Rect(view.right - 8, view.y, 6, view.h)
            pygame.draw.rect(win, (50, 34, 44), bar, border_radius=3)
            th = max(30, int(view.h * view.h / total))
            ty = view.y + int((view.h - th) * (self.scroll / max(1, total - view.h)))
            pygame.draw.rect(win, accent, (bar.x, ty, 6, th), border_radius=3)
        if not rows:
            win.blit(txt("Nothing to tweak here.", 16, ui.MUTED), (view.x + 8, view.y + 8))

    def draw_row(self, index, row, r, accent):
        win = self.win
        kind, obj = row
        selected = index == self.sel
        hover = r.collidepoint(pygame.mouse.get_pos())
        panel(win, r, (62, 36, 48, 245) if selected else (40, 27, 36, 235 if hover else 200),
              accent if selected else (84, 54, 58), 2 if selected else 1, 12)
        self.hits.append((r, "row", index))
        if kind == "kit":
            self.draw_kit_row(r, accent)
        elif kind == "item":
            self.draw_item_row(index, obj, r, accent)
        else:
            self.draw_field_row(index, row, obj, r, accent)

    def draw_kit_row(self, r, accent):
        win = self.win
        win.blit(txt("BOSS KIT", 17, ui.CREAM, True), (r.x + 16, r.y + 8))
        win.blit(txt(fit(self.on_kit.__doc__ or "", 12, False, r.w - 250), 12, ui.MUTED), (r.x + 16, r.y + 30))
        b = pygame.Rect(r.right - 190, r.y + 8, 176, r.h - 16)
        hover = b.collidepoint(pygame.mouse.get_pos())
        panel(win, b, (112, 80, 28, 250) if hover else (84, 60, 24, 240), accent, 2, 12)
        win.blit(txt("FILL IN KIT", 14, ui.INK if hover else ui.CREAM, True), txt("FILL IN KIT", 14, ui.CREAM, True).get_rect(center=b.center))
        self.hits.append((b, "kit", None))

    def draw_item_row(self, index, it, r, accent):
        win = self.win
        level = self.levels.get(it["id"], 0)
        coin = {"gold": (255, 214, 120), "ruby": (255, 120, 110), "emerald": (110, 220, 140), "pearl": (240, 150, 200)}[it["currency"]]
        pygame.draw.circle(win, coin, (r.x + 22, r.y + 22), 8)
        pygame.draw.circle(win, ui.INK, (r.x + 22, r.y + 22), 8, 2)
        win.blit(txt(it["name"], 16, ui.CREAM if level else (225, 212, 212), True), (r.x + 40, r.y + 8))
        lines = wrap(it["desc"], 12, False, r.w - 250)[:2]
        for k, line in enumerate(lines):
            win.blit(txt(line, 12, ui.MUTED), (r.x + 40, r.y + 29 + k * 15))
        # level pips + stepper
        right = r.right - 12
        minus = pygame.Rect(right - 112 - 32 * it["max"] + 32, r.centery - 14, 28, 28)
        x = right
        plus = pygame.Rect(x - 28, r.centery - 14, 28, 28)
        x = plus.x - 6
        pips = []
        for lv in range(it["max"], 0, -1):
            pr = pygame.Rect(x - 22, r.centery - 11, 22, 22)
            pips.append((lv, pr))
            x = pr.x - 4
        minus = pygame.Rect(x - 28, r.centery - 14, 28, 28)
        for lv, pr in pips:
            on = lv <= level
            pygame.draw.rect(win, accent if on else (52, 38, 48), pr, border_radius=6)
            pygame.draw.rect(win, ui.INK if on else (96, 66, 70), pr, 2, border_radius=6)
            self.hits.append((pr, "level", (index, it, lv)))
        self.stepper_button(minus, "-", (index, -1))
        self.stepper_button(plus, "+", (index, 1))
        if it["kind"] == "boost":
            tag(win, (minus.x - 8, r.y + 6), "ONE LEVEL", (255, 214, 120), 10, "topright")

    def stepper_button(self, rect, label, arg):
        hover = rect.collidepoint(pygame.mouse.get_pos())
        panel(self.win, rect, (96, 44, 58, 250) if hover else (52, 32, 42, 240), (130, 80, 80), 1, 8)
        s = txt(label, 18, ui.CREAM, True)
        self.win.blit(s, s.get_rect(center=(rect.centerx, rect.centery - 1)))
        self.hits.append((rect, "step", arg))

    def draw_field_row(self, index, row, f, r, accent):
        win = self.win
        key = f["key"]
        value = self.values[key]
        modified = not _same(value, f["default"])
        win.blit(txt(f["label"], 16, ui.CREAM if modified else (225, 212, 212), True), (r.x + 30, r.y + 9))
        hint = f.get("hint", "")
        if hint:
            win.blit(txt(fit(hint, 12, False, r.w * 0.5 - 40), 12, ui.MUTED), (r.x + 30, r.y + 31))
        if modified:                                                   # the reset dot
            dot = pygame.Rect(r.x + 8, r.y + 12, 16, 16)
            hov = dot.collidepoint(pygame.mouse.get_pos())
            pygame.draw.circle(win, ui.GOLD if not hov else ui.WHITE, dot.center, 5 if not hov else 7)
            self.hits.append((dot.inflate(8, 8), "reset", row))
        right = r.right - 14
        kind = f["type"]
        editing = self.edit and self.edit[0] == key
        if kind == "bool":
            sw = pygame.Rect(right - 64, r.centery - 14, 64, 28)
            on = bool(value)
            pygame.draw.rect(win, (46, 92, 58) if on else (88, 36, 42), sw, border_radius=14)
            pygame.draw.rect(win, ui.GREEN if on else ui.RED, sw, 2, border_radius=14)
            knob_x = sw.right - 15 if on else sw.x + 15
            pygame.draw.circle(win, ui.WHITE, (knob_x, sw.centery), 10)
            lab = txt("ON" if on else "OFF", 11, ui.WHITE, True)
            win.blit(lab, (sw.x + 10, sw.centery - 7) if on else (sw.right - 10 - lab.get_width(), sw.centery - 7))
            self.hits.append((sw, "step", (index, 1)))
        elif kind == "choice":
            box = pygame.Rect(right - 220, r.centery - 15, 220, 30)
            panel(win, box, (32, 18, 26, 240), (112, 64, 66), 1, 9)
            win.blit(txt(str(value).upper(), 15, ui.WHITE, True), txt(str(value).upper(), 15, ui.WHITE, True).get_rect(center=box.center))
            left = pygame.Rect(box.x - 34, box.y + 1, 28, 28)
            more = pygame.Rect(box.right + 6, box.y + 1, 28, 28)
            self.stepper_button(left, "<", (index, -1))
            self.stepper_button(more, ">", (index, 1))
            self.hits.append((box, "step", (index, 1)))
        elif kind == "text":
            box = pygame.Rect(right - 330, r.centery - 15, 330, 30)
            panel(win, box, (32, 18, 26, 240), ui.GOLD if editing else (112, 64, 66), 2 if editing else 1, 9)
            shown = self.edit[1] if editing else str(value)
            if editing and int(self.t * 2) % 2 == 0:
                shown += "|"
            win.blit(txt(fit(shown or "(none)", 15, True, box.w - 18), 15, ui.WHITE if shown else (130, 110, 110), True),
                     (box.x + 10, box.centery - 9))
            self.hits.append((box, "type", f))
        else:
            plus = pygame.Rect(right - 28, r.centery - 14, 28, 28)
            box = pygame.Rect(plus.x - 6 - 118, r.centery - 15, 118, 30)
            minus = pygame.Rect(box.x - 6 - 28, r.centery - 14, 28, 28)
            panel(win, box, (32, 18, 26, 240), ui.GOLD if editing else (112, 64, 66), 2 if editing else 1, 9)
            unit = f.get("unit", "")
            text = (self.edit[1] + ("|" if int(self.t * 2) % 2 == 0 else "")) if editing else _fmt(f, value)
            surf = txt(text, 16, ui.WHITE, True)
            if unit and not editing:
                u = txt(unit, 10, ui.MUTED)
                total = surf.get_width() + 4 + u.get_width()
                win.blit(surf, (box.centerx - total // 2, box.centery - surf.get_height() // 2))
                win.blit(u, (box.centerx - total // 2 + surf.get_width() + 4, box.centery - u.get_height() // 2 + 3))
            else:
                win.blit(surf, surf.get_rect(center=box.center))
            self.stepper_button(minus, "-", (index, -1))
            self.stepper_button(plus, "+", (index, 1))
            self.hits.append((box, "type", f))
            lo, hi = f.get("min"), f.get("max")
            if lo is not None and hi is not None and hi > lo and (hi - lo) / f.get("step", 1) <= 4000:
                track = pygame.Rect(minus.x - 250, r.centery - 3, 236, 6)
                if track.x > r.x + r.w * 0.36:
                    frac = (value - lo) / (hi - lo)
                    pygame.draw.rect(win, (20, 12, 20), track.inflate(4, 6), border_radius=6)
                    pygame.draw.rect(win, (62, 46, 58), track, border_radius=3)
                    dflt = (f["default"] - lo) / (hi - lo)
                    pygame.draw.line(win, (150, 130, 130), (track.x + int(track.w * dflt), track.y - 5),
                                     (track.x + int(track.w * dflt), track.bottom + 4), 1)
                    pygame.draw.rect(win, accent, (track.x, track.y, max(6, int(track.w * frac)), 6), border_radius=3)
                    pygame.draw.circle(win, ui.WHITE, (track.x + int(track.w * frac), track.centery), 7)
                    pygame.draw.circle(win, accent, (track.x + int(track.w * frac), track.centery), 7, 2)
                    self.hits.append((track.inflate(12, 22), "slider", f))

    def draw_footer(self, frame):
        win = self.win
        y = frame.bottom - 64
        hint = "UP/DOWN row  LEFT/RIGHT change (SHIFT x10)  TAB group  type a number  DEL reset"
        win.blit(txt(fit(hint, 12, False, frame.w - 420), 12, (150, 140, 150)), (frame.x + 24, y + 22))
        for label, action, color, w in (("CANCEL  (ESC)", "cancel", (74, 34, 42), 150), ("APPLY  (ENTER)", "apply", (48, 84, 54), 170)):
            pass
        cancel = pygame.Rect(frame.right - 24 - 150, y + 8, 150, 42)
        apply_ = pygame.Rect(cancel.x - 12 - 170, y + 8, 170, 42)
        for rect, label, fill, glow, action in ((cancel, "CANCEL  (ESC)", (74, 34, 42), ui.MUTED, "cancel"),
                                                (apply_, "APPLY  (ENTER)", (48, 84, 54), ui.GREEN, "apply")):
            hover = rect.collidepoint(pygame.mouse.get_pos())
            if hover:
                g = pygame.Surface((rect.w + 12, rect.h + 12), pygame.SRCALPHA)
                pygame.draw.rect(g, (*glow, 90), g.get_rect(), border_radius=14)
                win.blit(g, (rect.x - 6, rect.y - 6))
            pygame.draw.rect(win, fill, rect, border_radius=10)
            pygame.draw.rect(win, glow, rect, 2 if hover else 1, border_radius=10)
            s = txt(label, 15, ui.CREAM if hover else ui.WHITE, True)
            win.blit(s, s.get_rect(center=rect.center))
            self.hits.append((rect, action, None))

    # ------------------------------------------------------------------ loop
    def run(self):
        dt = 1 / 60
        pygame.key.set_repeat(320, 55)
        try:
            while not self.done:
                for ev in pygame.event.get():
                    self.handle(ev)
                self.t += dt
                self.toast = (self.toast[0], max(0.0, self.toast[1] - dt))
                self.draw(dt)
                pygame.display.flip()
                dt = min(0.05, self.clock.tick(60) / 1000.0)
        finally:
            pygame.key.set_repeat()
        return self.result


# ---------------------------------------------------------------------- #
# entry points
# ---------------------------------------------------------------------- #
def _flatten(fields):
    return [f for fs in fields.values() for f in fs]


def entity_fields(data):
    """Copies of the schema's fields with the placement defaults taken from this entity's own entry."""
    x, y = int(data.get("x", 0)), int(data.get("y", 0))
    cell_x, cell_y = (x // 64) * 64, (y // 64) * 64
    out = {}
    for cid, fs in FIELDS.items():
        out[cid] = []
        for f in fs:
            f = dict(f)
            if f["key"] == "x":
                f.update(default=x, min=cell_x, max=cell_x + 63)
            elif f["key"] == "y":
                f.update(default=y, min=cell_y, max=cell_y + 63)
            elif f["store"] == "data" and f["key"] in data:
                f["default"] = data[f["key"]] if f["key"] in ("x", "y") else f["default"]
            out[cid].append(f)
    return out


def entity_values(fields, data):
    mods = data.get("mods") or {}
    fx_ = mods.get("fx") or {}
    values = {}
    for f in _flatten(fields):
        k = f["key"]
        if f["store"] == "data":
            values[k] = data.get(k, f["default"])
        elif f["store"] == "fx":
            raw = fx_.get(k, f["default"])
            values[k] = bool(raw) if f["type"] == "bool" else raw
        else:
            values[k] = mods.get(k, f["default"])
    return values


def edit_entity(game, data):
    """Open the Entity Editor for an enemy's world entry. Returns {"data": {...}, "mods": {...}} or None."""
    from ..objects import arrow_trap  # noqa: F401  (keeps the import order of the editor stable)
    fields = entity_fields(data)
    values = entity_values(fields, data)
    items = schema.grantable_items()
    levels = dict((data.get("mods") or {}).get("items") or {})
    name, color = data.get("name", "Pawn"), data.get("color", "Blue")

    def kit(window):
        """Fill in this type's boss kit (health, damage, abilities). Everything stays editable."""
        spec = schema.BOSS_KITS.get(name)
        if not spec:
            window.say("No kit for this type")
            return
        for k, v in spec.items():
            if k == "fx":
                for fk, fv in v.items():
                    window.values[fk] = bool(fv) if fk == "homing" else max(window.values.get(fk, 0), fv)
            elif k in window.values:
                window.values[k] = v
        window.say(f"{name} boss kit filled in - tweak anything")

    title = f"ENTITY EDITOR  -  {name.upper()}"
    win = TweakWindow(game.window, game.clock, title,
                      {"name": name, "color": color, "subtitle": f"{color} {name}  -  cell {data.get('x', 0) // 64}, {data.get('y', 0) // 64}"},
                      schema.all_categories(), fields, values, items, levels, on_kit=kit)
    if not win.run():
        return None

    out_data, mods = {}, {}
    fx_ = {}
    for f in _flatten(fields):
        k, v = f["key"], win.values[f["key"]]
        if f["store"] == "data":
            out_data[k] = v
        elif _same(v, f["default"]):
            continue
        elif f["store"] == "fx":
            fx_[k] = 1 if f["type"] == "bool" else v
        else:
            mods[k] = v
    if fx_:
        mods["fx"] = fx_
    held = {k: lv for k, lv in win.levels.items() if lv > 0}
    if held:
        mods["items"] = held
    return {"data": out_data, "mods": mods}


def edit_trap(game, data):
    """The Homing Arrow Trap's own window: its effects are set by hand because nobody owns it."""
    from ..objects import arrow_trap
    from ..data.entity_mods import TRAP_CATEGORIES, TRAP_FIELDS
    props = arrow_trap.clean_props(data)
    fields = {cid: [dict(f) for f in fs] for cid, fs in TRAP_FIELDS.items()}
    values = {f["key"]: props[f["key"]] for f in _flatten(fields)}
    win = TweakWindow(game.window, game.clock, "HOMING ARROW TRAP",
                      {"name": "", "icon": arrow_trap.icon(96),
                       "subtitle": "No owner - effects are set here by hand"},
                      TRAP_CATEGORIES, fields, values)
    win.subject["name"] = "Homing Trap"
    win.frames = []
    if not win.run():
        return None
    return {k: win.values[k] for k in win.values}
