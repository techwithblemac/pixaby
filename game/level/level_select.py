"""PIXEL ABYSS - lively, responsive level selection.

The selector deliberately uses the game's own pixel-art language instead of a
"dashboard" aesthetic: the menu background, terrain, enemies, bombs and gems
are reused as decoration. Level previews are intentionally *not* rendered as
maps; the selector shows the level name/number and a playful animated scene,
while the details panel explains what the JSON actually contains.
"""
import os
import json
import math
import random
import datetime
import copy
import subprocess
import sys
import pygame

from ..settings import Settings
from ..assets import Assets
from ..entities.entities import Player
from ..objects.objects import Bombs
from ..scripts.sounds import Sounds
from .main.level_loader import Level_Loader
from . import sources as level_sources
from . import preview as level_preview
from . import preview_gif
from . import progress
from ..scripts import paths
from .main.update_funcs import update_game_logic
from .main.draw_funcs import draw
from .editor import editor_launch
from ..ui import ui_theme
from ..scripts.functions import calculate_viewports

# Distinguishes "caller said nothing about editing" from "caller
# explicitly asked for no pencil".
_DEFAULT = object()


class _SelectorWorld(Level_Loader, Settings):
    """Isolated mini-world using the same grid, Block, Enemy and A* graph rules.

    It intentionally does not create a second pathfinding implementation. The
    64px grid is built from the selector map, blocks are real Block instances,
    navigation nodes are PlatformNodes, and movement is driven by the real
    Enemy pathfinding/collision methods.
    """
    TILE = 64

    def __init__(self, game, map_path):
        self.game = game
        self.type = "level_selector"
        self.MULTIPLAYER = game.MULTIPLAYER
        self.SERVER = game.SERVER
        self.log = 0
        self.create_new_world()
        self.env_ready = False
        
        self.create_grid()
        
        self.settings = {"entity": {}}
        
        self.map_path = map_path
        self.level = "selector_world/level_select_map_standard"
        
        self.players = []
        self.player = Player(0, 0, 50, 50, 'TNT', 'Green', game=self)
        self.player.rect.center = (Settings.WIDTH//2, Settings.HEIGHT//2)
        self.player.camera_update()

        self.bombs = Bombs(game=self)
        self.sounds = Sounds(self.player, 4)

        self.dt = 0.1 #1.0 / max(1, getattr(Settings, "FPS", 30))
        self.seconds = 0
        
        self.zoom = 1.0
        self.DEBUGGING_MODE = False
        self.debug = {}
        self.offset_x = 0
        self.offset_y = 0
        self.CACHED_ENTITY_ZOOM_IMAGES = {}
        self.entity_sprite_cache = {}
        self.object_sprite_cache = {}
        self.objects_to_draw = []
        
        self.running = True
        self.done = False
        
        self.game_speed = 1
        self.max_game_speed = 1
        self.master_clock = 0
        
        self.keys = {}

        self.chunk_w, self.chunk_h = (12, 12)

        self.load_world()

    def personalise(self, entity, times=1):
        data = self.settings.get("entity", {}).get(entity.name, {})
        for key, value in data.items():
            if key == "health" and entity.type == "player":
                continue
            setattr(entity, key, value)
        entity.max_health = getattr(entity, "health", 100)

    def update(self):
        self.seconds = int(pygame.time.get_ticks() / 1000)
        
        if self.env_ready:
            self.objects_to_draw = update_game_logic(self)
    
    def draw(self, screen, map_rect, source_rect=None):
        """Render a world slice while preserving the real world coordinates."""
        player = self.player
        player.viewport = pygame.Rect(0, 0, Settings.WIDTH, Settings.HEIGHT)
        player.camera_update()
        viewport = screen.subsurface(player.view_rect)
        
        # SET GAME SETTINGS TO THE FIRST PLAYER
        if player.entity_id == 0:
            self.offset_x = player.cam_rect.x
            self.offset_y = player.cam_rect.y
            self.zoom = player.zoom
        
        # DRAW EVERYTHING ON THE PLAYER'S PERSPECTIVE
        draw(self, viewport, self.objects_to_draw, player.view_rect.size, player.cam_rect.topleft, player.zoom, player.rect)
        

class LevelSelector:
    # Palette sampled conceptually from the existing menu background.
    # Sourced from ui_theme so every other screen (loading, editor
    # overlays, lobby) stays visually consistent with this one.
    INK = ui_theme.INK
    INK2 = ui_theme.INK2
    MAROON = ui_theme.MAROON
    RED = ui_theme.RED
    CORAL = ui_theme.CORAL
    CREAM = ui_theme.CREAM
    WHITE = ui_theme.WHITE
    MUTED = ui_theme.MUTED
    GREEN = ui_theme.GREEN
    BLUE = ui_theme.BLUE
    PURPLE = ui_theme.PURPLE
    GOLD = ui_theme.GOLD

    # The PRO+ pop-up is a mock-up with nothing behind it and every level is free
    # for now, so its button stays hidden. Flip this to bring it back.
    SHOW_PRO = False

    # Card/title prefix per tab
    PREFIX = {"story": "LEVEL", "coop": "CO-OP", "worlds": "WORLD", "test": "TEST"}

    def __init__(self, game, levels_dir=paths.LEVELS_ROOT, on_edit=None, dev=False):
        self.game = game
        # dev = the standalone level editor: every story level open, the pencil on every tab
        # dev (the standalone editor) only opens everything while DEBUGGING_MODE is on
        self.dev = bool(dev) and bool(Settings.DEBUGGING_MODE)
        self.edit_only = bool(dev)       # the standalone editor can only open levels it may edit
        self.screen = game.window
        self.levels_dir = levels_dir
        # on_edit(game, level_id) opens an editor for that level and
        # returns once the user leaves it. None simply hides the pencil,
        # which is how the selector stays usable in builds that ship
        # without an editor.
        self.on_edit = on_edit
        self.edit_rect = pygame.Rect(0, 0, 1, 1)
        self.edit_hover = False
        self._edit_request = None
        self.fonts = {}
        self.images = {}
        self.levels = []
        self.filtered = []
        self.selected = 0
        self.scroll = 0
        self.search = ""
        self.search_active = False
        self.sources = level_sources.build_sources(debug=bool(Settings.DEBUGGING_MODE), dev=self.dev)
        # Solo (story mode) opens only the story tabs; split screen / online open everything BUT the story.
        # The standalone editor is exempt, it has to reach every folder.
        self.play_mode = level_sources.play_mode(game)
        self.preview_cache = {}
        self.preview_gifs = preview_gif.PreviewGifs()     # live GIF of each world, see preview_gif.py
        self.preview_jobs = {}                            # (folder, id) -> running extras/capture_previews.py process
        self.preview_btn_rect = pygame.Rect(0, 0, 1, 1)   # LOAD PREVIEW / UPDATE button of the selected level
        self.preview_btn_level = None
        # Playing together (split screen / online) opens straight on the CO-OP tab; solo and the editor start on tab 0.
        self.tab = 0
        if not self.dev and self.play_mode != level_sources.SOLO:
            for idx, src in enumerate(self.sources):
                if src.key == "coop":
                    self.tab = idx
                    break
        self.source = self.sources[self.tab]
        self.upload_rect = pygame.Rect(0, 0, 1, 1)
        self.notice = ""
        self.notice_until = 0
        self.favorites = set()
        self.running = True
        self.result = None
        self.card_rects = []
        self.category_rects = []
        self.search_rect = pygame.Rect(0, 0, 1, 1)
        self.play_rect = pygame.Rect(0, 0, 1, 1)
        self.back_rect = pygame.Rect(0, 0, 1, 1)
        self.pro_rect = pygame.Rect(0, 0, 1, 1)
        self.pro_open = False
        self.new_open = False
        self.new_fields = {
            "title": "Untitled Descent",
            "description": "A custom PIXEL ABYSS level waiting to be shaped.",
            "theme": "Abyss",
            "difficulty": "STANDARD",
            "tags": "custom, editor",
            "objective": "Descend, survive, and reach the exit."
        }
        self.new_field_order = ["title", "description", "theme", "difficulty", "tags", "objective"]
        self.new_active_field = 0
        self.new_field_rects = {}
        self.new_create_rect = pygame.Rect(0, 0, 1, 1)
        self.new_cancel_rect = pygame.Rect(0, 0, 1, 1)
        self.new_rect = pygame.Rect(0, 0, 1, 1)
        self.pro_close_rect = pygame.Rect(0, 0, 1, 1)
        self.t = 0
        self.particles = []
        self.mini_world = None
        self._load_assets()
        self._load_mini_world()
        self._load_levels()
        self._apply_filter()
        self._select_default()

    # ---------------- data ----------------
    def _tab_lock(self, source=None):
        """Why ``source`` (default: the open tab) is closed in the current play mode, or None when it is open."""
        if self.dev:
            return None
        return (source or self.source).mode_lock(self.play_mode)

    def _load_levels(self):
        """Ask the active tab's source for its levels."""
        self.levels = list(self.source.list())
        lock = self._tab_lock()
        if lock:
            # the whole tab is closed in this mode: every card shows the padlock and the reason
            for level in self.levels:
                level["locked"] = True
                level["mode_locked"] = True
                level["lock_text"] = lock

    def _stats(self, objects):
        return level_sources.level_stats(objects)

    @staticmethod
    def _difficulty(n):
        return level_sources.difficulty_by_number(n)

    def _may_edit_source(self):
        return (not self.source.placeholder) and (self.source.editable or self.dev)

    def _can_edit(self):
        """The pencil: only while DEBUGGING_MODE is on (the editor does not exist otherwise).
        My Worlds, and every real folder in the dev editor."""
        return bool(Settings.DEBUGGING_MODE) and bool(self.on_edit) and self._may_edit_source()

    def _can_create(self):
        """NEW +: makes a level to edit, so it is debug-only like the editor itself."""
        if not Settings.DEBUGGING_MODE or self.source.placeholder:
            return False
        return self.source.can_create or self.dev

    def _flash(self, text, ms=2600):
        self.notice = text
        self.notice_until = pygame.time.get_ticks() + ms

    def _select_default(self):
        """Story opens on the level you are up to; every other tab on its first card."""
        self.selected = 0
        if self.source.key == "story" and self.filtered:
            wanted = None
            for i, level in enumerate(self.filtered):
                if not level.get("locked"):
                    wanted = i
                if progress.get().highest_cleared < level["id"]:
                    break
            if wanted is not None:
                self.selected = wanted
        self.scroll = max(0, min(self.selected - 4, max(0, len(self.filtered) - 5)))
        if self.selected < self.scroll:
            self.scroll = self.selected

    def _switch_tab(self, index):
        if index == self.tab or not (0 <= index < len(self.sources)):
            return
        self.tab = index
        self.source = self.sources[index]
        self.search_active = False
        self.levels = []
        self._load_levels()
        self._apply_filter()
        self._select_default()

    # ---------------- assets ----------------
    def _load_assets(self):
        """Resolve selector art exclusively through the central Assets registry.

        This screen never opens an image file from the assets folders. Gameplay
        entities/objects resolve their own sprites through Assets, while the
        few static references below are also sourced directly from Assets.
        """
        self.images = {
            "bg": getattr(Assets, "MENU_BG", None),
        }
        self.bg_scaled = None
        self.bg_size = None

    def _load_mini_world(self):
        """Load the standard-format editor map and build its real sandbox."""
        candidates = [
            os.path.join(paths.LEVELS_ROOT, "selector_world", "level_select_map_standard.json"),
        ]
        for path in candidates:
            path = os.path.normpath(path)
            if os.path.isfile(path):
                try:
                    self.mini_world = _SelectorWorld(self.game, path)
                except Exception as exc:
                    print(f"Level selector mini-world disabled: {exc}")
                return

    def _asset_sprite(self, key, size=None):
        """Get a static sprite from Assets, never from a filesystem path."""
        img = None
        if key == "gem":
            sprites = getattr(Assets, "GEM_SPRITES", {})
            pack = sprites.get("star", []) if isinstance(sprites, dict) else []
            img = pack[0] if pack else None
        elif key == "fire":
            sprites = getattr(Assets, "FIRE_SPRITES", {})
            pack = sprites.get("on", []) if isinstance(sprites, dict) else []
            img = pack[0] if pack else None
        elif key == "explosion":
            sprites = getattr(Assets, "EXPLOSION_SPRITES", {})
            pack = sprites.get("on", []) if isinstance(sprites, dict) else []
            img = pack[0] if pack else None
        elif key == "tree":
            sprites = getattr(Assets, "TREE_SPRITES", {})
            pack = sprites.get("idle_right", []) if isinstance(sprites, dict) else []
            img = pack[0] if pack else None
        elif key == "shroom":
            sprites = getattr(Assets, "DECO_SPRITES", {})
            img = sprites.get("shroom1") if isinstance(sprites, dict) else None
        elif key == "bone":
            sprites = getattr(Assets, "DECO_SPRITES", {})
            img = sprites.get("bone") if isinstance(sprites, dict) else None
        elif key == "arrow":
            sprites = getattr(Assets, "ARROW_SPRITES", {})
            pack = sprites.get("full", []) if isinstance(sprites, dict) else []
            img = pack[0] if pack else None
        elif key == "exit":
            sprites = getattr(Assets, "DECO_SPRITES", {})
            img = sprites.get("exit") if isinstance(sprites, dict) else None
        if img is None:
            return None
        return pygame.transform.scale(img, size) if size else img

    def _sprite(self, key, size=None):
        # Compatibility helper for the rest of the selector. All art is now
        # resolved from Assets rather than from direct folder loads.
        return self._asset_sprite(key, size)

    # ---------------- helpers ----------------
    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.SysFont("serif", max(10, int(size)), bold=bold)
        return self.fonts[key]

    def _text(self, text, pos, size, color=None, bold=False, max_width=None):
        font = self._font(size, bold)
        text = str(text)
        if max_width:
            while len(text) > 1 and font.size(text)[0] > max_width:
                text = text[:-1]
            if text != str(text): text += "…"
        surf = font.render(text, True, color or self.WHITE)
        self.screen.blit(surf, (int(pos[0]), int(pos[1])))
        return surf

    def _panel(self, rect, fill, border=None, width=1, radius=12):
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surf, fill, (0, 0, rect.width, rect.height), border_radius=radius)
        if border:
            pygame.draw.rect(surf, border, (0, 0, rect.width, rect.height), width=width, border_radius=radius)
        self.screen.blit(surf, rect.topleft)

    def _button(self, rect, label, selected=False, accent=None, small=False):
        accent = accent or self.CORAL
        hover = rect.collidepoint(pygame.mouse.get_pos())
        active = selected or hover
        fill = (83, 37, 47) if active else (48, 27, 36)
        self._panel(rect, fill, accent if active else (112, 64, 66), 2 if active else 1, 9)
        f = self._font(12 if small else 15, True)
        s = f.render(label, True, self.CREAM if active else self.WHITE)
        self.screen.blit(s, s.get_rect(center=rect.center))
        return hover

    def _wrap(self, text, width, font):
        lines, line = [], ""
        for word in str(text).split():
            test = word if not line else line + " " + word
            if font.size(test)[0] <= width: line = test
            else:
                if line: lines.append(line)
                line = word
        if line: lines.append(line)
        return lines

    # ---------------- lively scene ----------------
    def _draw_background(self):
        w, h = self.screen.get_size()
        if self.bg_scaled is None or self.bg_size != (w, h):
            bg = self.images.get("bg")
            if bg:
                self.bg_scaled = pygame.transform.smoothscale(bg, (w, h))
                self.bg_size = (w, h)
        if self.bg_scaled:
            self.screen.blit(self.bg_scaled, (0, 0))
        else:
            self.screen.fill(self.INK)
        # A warm translucent wash keeps the menu palette coherent.
        wash = pygame.Surface((w, h), pygame.SRCALPHA)
        wash.fill((19, 12, 21, 105))
        self.screen.blit(wash, (0, 0))
        # Drifting dust / ember pixels.
        random.seed(7)
        for i in range(38):
            x = (random.random() * w + self.t * (8 + i % 5)) % w
            y = (random.random() * h - self.t * (3 + i % 4)) % h
            a = 45 + (i % 4) * 25
            dot = pygame.Surface((3, 3), pygame.SRCALPHA)
            dot.fill((*self.CORAL, a))
            self.screen.blit(dot, (int(x), int(y)))

    def _lock_icon(self, center, size=16, color=None):
        """A vector padlock (the serif system font has no reliable lock glyph)."""
        color = color or self.MUTED
        cx, cy = center
        bw, bh = int(size * 0.9), int(size * 0.62)
        body = pygame.Rect(0, 0, bw, bh)
        body.center = (cx, cy + int(size * 0.18))
        sw = int(size * 0.55)
        shackle = pygame.Rect(0, 0, sw, int(size * 0.7))
        shackle.midbottom = (cx, body.top + 2)
        pygame.draw.arc(self.screen, color, shackle, 0, math.pi, 2)
        pygame.draw.line(self.screen, color, (shackle.left, shackle.centery), (shackle.left, body.top + 1), 2)
        pygame.draw.line(self.screen, color, (shackle.right - 1, shackle.centery), (shackle.right - 1, body.top + 1), 2)
        pygame.draw.rect(self.screen, color, body, border_radius=3)
        pygame.draw.circle(self.screen, self.INK, body.center, max(1, size // 10))

    def _draw_card_art(self, rect, level, selected):
        locked = bool(level.get("locked"))
        if locked:
            self._panel(rect, (33, 22, 28), (118, 74, 78) if selected else (66, 44, 50), 2 if selected else 1, 14)
        else:
            self._panel(rect, (49, 27, 35) if selected else (37, 23, 31), self.CORAL if selected else (92, 50, 57), 2 if selected else 1, 14)
        n = self._font(26, True).render(str(level["id"]), True, self.MUTED if locked else self.CREAM)
        self.screen.blit(n, (rect.left + 15, rect.top + 12))
        title = level["meta"].get("title") or f"LEVEL {level['id']}"
        self._text(title.upper(), (rect.left + 56, rect.top + 12), 15, self.MUTED if locked else self.WHITE, True, rect.width - 115)
        self._text(level["meta"].get("theme", "ABYSS"), (rect.left + 57, rect.top + 35), 12, (110, 84, 88) if locked else self.MUTED, True)
        if locked:
            self._lock_icon((rect.right - 26, rect.top + 22), 18, self.MUTED)
            self._text(level.get("lock_text") or "Locked", (rect.left + 15, rect.bottom - 27), 10, self.MUTED, True, rect.width - 30)
            return
        diff = str(level["meta"].get("difficulty", "STANDARD")).upper()
        self._text("★ " + diff, (rect.left + 15, rect.bottom - 27), 10, self.GOLD if diff != "EXTREME" else self.CORAL, True)
        if level["id"] in self.favorites:
            self._text("♥", (rect.right - 25, rect.top + 10), 17, self.CORAL, True)

    # ---------------- filtering ----------------
    def _apply_filter(self):
        q = self.search.strip().lower()
        out = []
        for level in self.levels:
            m = level["meta"]
            hay = " ".join([str(level["id"]), str(m.get("title", "")), str(m.get("theme", "")),
                            str(m.get("author", "")), str(m.get("description", "")),
                            " ".join(map(str, m.get("tags", []))) ]).lower()
            if q and q not in hay: continue
            out.append(level)
        self.filtered = out
        self.selected = min(self.selected, max(0, len(out) - 1))
        self.scroll = min(self.scroll, max(0, len(out) - 1))

    # ---------------- responsive drawing ----------------
    def draw(self, t):
        self.t = t
        w, h = self.screen.get_size()
        self._draw_background()
        if Settings.DEBUGGING_MODE:
            # Get and draw FPS
            fps = int(Settings.clock.get_fps())
        else:
            fps = ""

        # Start-menu-like title treatment: large serif, warm, slightly bouncy.
        bob = int(math.sin(t / 500.0) * 2)
        self._text(f"PIXEL ABYSS {fps}", (24, 18 + bob), 28 if w > 600 else 22, self.CREAM, True)
        self._text("CHOOSE YOUR DESCENT", (27, 49 + bob), 11, self.CORAL, True)
        self._text("THE ABYSS IS WAITING.", (27, 64 + bob), 9, self.MUTED)

        # Source tabs wrap on narrow displays.
        self.category_rects = []
        x, y = 22, 91
        for idx, src in enumerate(self.sources):
            tab_locked = bool(self._tab_lock(src))
            tw = max(56 if w < 500 else 78, self._font(12, True).size(src.label)[0] + (18 if w < 500 else 28))
            if tab_locked:
                tw += 22                                    # room for the padlock
            if x + tw > w - 22:
                x, y = 22, y + 34
            r = pygame.Rect(x, y, tw, 27)
            self._button(r, src.label, idx == self.tab, self.CORAL, True)
            if tab_locked:
                self._lock_icon((r.right - 14, r.centery - 1), 12, self.CREAM if idx == self.tab else self.MUTED)
            self.category_rects.append((r, idx))
            x += tw + 7
        content_y = y + 39

        middle_block = 448
        bottom_top = 640
        top_bottom = 64
        # Normal windows: two columns. Small windows: cards on top, details below.
        compact = w < 760 or h < 540
        if compact:
            list_h = max(190, int(h * .40))
            left = pygame.Rect(14, content_y, w - 28, list_h)
            right = pygame.Rect(14, left.bottom + 10, w - 28, h - left.bottom - 20)
        else:
            left_w = max(250, min(385, int(w * .36)))
            left = pygame.Rect(18, content_y, middle_block - (64 + 18) - 16, bottom_top - content_y - 16)
            right_y = content_y + top_bottom + 16
            right = pygame.Rect(middle_block + 16, right_y, w - middle_block - 30, h - right_y - 18)

        self._panel(left, (27, 18, 25), (101, 56, 60), 1, 16)
        if self.source.placeholder:
            self._text(self.source.archive_label, (left.left + 13, left.top + 10), 11, self.CREAM, True)
        else:
            self._text(f"{self.source.archive_label}  •  {len(self.filtered)} FOUND", (left.left + 13, left.top + 10), 11, self.CREAM, True)

        self.card_rects = []
        card_gap = 7
        card_h = 78 if compact else 82
        visible = 5
        self.scroll = max(0, min(self.scroll, max(0, len(self.filtered) - visible)))
        for row, level in enumerate(self.filtered[self.scroll:self.scroll + visible]):
            idx = self.scroll + row
            r = pygame.Rect(left.left + 9, left.top + 31 + row * (card_h + card_gap), left.width - 18, card_h)
            self.card_rects.append((r, idx))
            self._draw_card_art(r, level, idx == self.selected)


        
        # Footer controls stay visible and feel like the original game's menu.
        hint = "↑↓ / W S  choose     TAB  switch tab     ENTER  descend     F  favourite     ESC  back"
        if self._can_edit():
            hint = ("↑↓ / W S  choose     TAB  switch tab     ENTER  descend     E  edit     "
                    "F  favourite     ESC  back")
        self._text(hint, (20, h - 13), 8, self.MUTED)

        if self.mini_world and not compact:
            # Vertical and top Z sections sit in the exact UI gaps/edges shown
            # in the reference screenshot; they are still the same world cells.
            gap_left = left.right + 2
            gap_right = right.left - 2
            
            # Re-outline the UI panels so the map reads as terrain in the gap,
            # while the information text remains legible.
            pygame.draw.rect(self.screen, (101, 56, 60), left, 1, border_radius=16)
            pygame.draw.rect(self.screen, (101, 56, 60), right, 1, border_radius=16)

            if gap_right > gap_left:
                mid = pygame.Rect(gap_left, left.top + 20, gap_right - gap_left,
                                  max(40, left.height - 40))
                self.mini_world.draw(self.screen, mid, pygame.Rect(-96, -256, 192, 896))
            top = pygame.Rect(right.left + 8, max(0, right.top - 18),
                              max(20, right.width - 16), 28)
            self.mini_world.draw(self.screen, top, pygame.Rect(0, -256, 1088, 64))

        # Search field scales down in small windows.
        sw = min(300, max(120, w - 270))
        self.search_rect = pygame.Rect((w / 2) - (sw / 2), 22, sw, 38)
        self._panel(self.search_rect, (35, 21, 29), self.CORAL if self.search_active else (108, 61, 64), 1, 12)
        self._text("⌕", (self.search_rect.left + 10, self.search_rect.top + 8), 17, self.CREAM)
        size = 16
        self._text(self.search or "search the abyss...", (self.search_rect.left + 34, self.search_rect.centery - size / 2), size, self.WHITE if self.search else self.MUTED)
        
        # Bottom action buttons are large enough for fingers.
        bw = min(150, max(150, w - 50))
        self.back_rect = pygame.Rect(w - bw - 16, 22, bw, 38)
        self._button(self.back_rect, "BACK", False, self.MUTED, True)
        
        anchor = self.back_rect
        if self.SHOW_PRO:
            pw = min(150, max(150, w - 50))
            self.pro_rect = pygame.Rect(self.back_rect.x - pw - 16, 22, pw, 38)
            self._button(self.pro_rect, "PRO+ CHAOS", False, self.PURPLE, True)
            anchor = self.pro_rect
        else:
            self.pro_rect = pygame.Rect(0, 0, 1, 1)

        # NEW+ only where a level can be created: My Worlds (and every folder in the dev editor).
        if self._can_create():
            nw = min(110, max(90, w - 50))
            self.new_rect = pygame.Rect(anchor.x - nw - 16, 22, nw, 38)
            self._button(self.new_rect, "NEW +", False, self.GREEN, True)
        else:
            self.new_rect = pygame.Rect(0, 0, 1, 1)

        # Reset per-frame hit areas so a tab with no details panel never leaves a live button behind.
        self.play_rect = pygame.Rect(0, 0, 1, 1)
        self.edit_rect = pygame.Rect(0, 0, 1, 1)
        self.upload_rect = pygame.Rect(0, 0, 1, 1)
        self.preview_btn_rect = pygame.Rect(0, 0, 1, 1)
        self.preview_btn_level = None
        self.edit_hover = False

        self._panel(right, (27, 18, 25, 200), (101, 56, 60, 200), 1, 16)
        
        if self.source.placeholder:
            headline, body = self.source.placeholder
            if self._tab_lock():
                headline, body = "LOCKED", self._tab_lock() + "."
            self._text(headline, (right.centerx - self._font(30, True).size(headline)[0] / 2, right.top + 70), 30, self.CREAM, True)
            f = self._font(14)
            for i, line in enumerate(self._wrap(body, min(420, right.width - 60), f)):
                self._text(line, (right.centerx - min(420, right.width - 60) / 2, right.top + 125 + i * 20), 14, self.MUTED)
            self._text("NOTHING HERE YET.", (left.centerx - 70, left.centery), 13, self.CORAL, True)
        elif not self.filtered:
            self._text(self.source.empty_text, (left.left + 22, left.centery - 8), 13, self.CORAL, True, left.width - 40)

        if self.filtered:
            self._draw_details(right, self.filtered[self.selected], compact)

        if self.notice and pygame.time.get_ticks() < self.notice_until:
            nf = self._font(13, True)
            nw_ = nf.size(self.notice)[0] + 28
            tip = pygame.Rect(0, 0, min(nw_, w - 20), 30)
            tip.midbottom = (w // 2, h - 28)
            self._panel(tip, (34, 20, 28, 235), self.GOLD, 1, 8)
            self._text(self.notice, (tip.left + 14, tip.top + 7), 13, self.CREAM, True, tip.width - 24)

        if self.pro_open:
            self._draw_pro_overlay()
        if self.new_open:
            self._draw_new_overlay()
        
    def _preview_surface(self, level, size):
        """The map crop for a level's "preview coordinates", drawn once per level and panel size.
        None when the level has no preview value."""
        pt = level.get("preview")
        if not pt:
            return None
        key = (level.get("folder"), level["id"], int(size[0]), int(size[1]), tuple(pt))
        shot = self.preview_cache.get(key)
        if shot is None:
            try:
                shot = level_preview.render(level.get("objects", []), pt, size)
            except Exception as exc:
                print(f"Map preview failed for level {level['id']}: {exc}")
                shot = False
            self.preview_cache[key] = shot
        return shot or None

    # ---------------- recording a preview from the selector ----------------
    def _draw_preview_button(self, art, level, label, compact):
        """LOAD PREVIEW (no GIF yet) / UPDATE (level saved after its GIF) at the bottom of the preview panel.
        While the recorder runs it turns into a RECORDING... pill that cannot be clicked."""
        key = self._preview_key(level)
        h = 22 if compact else 28
        busy = key in self.preview_jobs
        if busy:
            label = "RECORDING" + "." * (1 + (pygame.time.get_ticks() // 400) % 3)
        width = max(96, self._font(12, True).size("RECORDING...")[0] + 26, self._font(12, True).size(label)[0] + 26)
        btn = pygame.Rect(0, 0, width, h)
        btn.midbottom = (art.centerx, art.bottom - 10)
        if busy:
            self._panel(btn, (40, 26, 33), (92, 58, 62), 1, 9)
            txt = self._font(12, True).render(label, True, self.MUTED)
            self.screen.blit(txt, txt.get_rect(center=btn.center))
        else:
            self._button(btn, label, False, self.GREEN if label != "UPDATE" else self.GOLD, True)
            self.preview_btn_rect = btn
            self.preview_btn_level = level

    @staticmethod
    def _preview_key(level):
        return (level.get("folder") or paths.STORY, level.get("id"))

    def _start_preview_job(self, level):
        """Record the level's GIF with extras/capture_previews.py (a separate process, so the selector keeps running)."""
        key = self._preview_key(level)
        if key in self.preview_jobs:
            return
        if not preview_gif.available():
            self._flash("Pillow is needed for previews:  pip install pillow", 4200)
            return
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        tool = os.path.join(root, "extras", "capture_previews.py")
        if not os.path.exists(tool):
            self._flash("extras/capture_previews.py is missing.", 3200)
            return
        try:
            self.preview_jobs[key] = subprocess.Popen(
                [sys.executable, tool, "--folder", str(key[0]), "--level", str(key[1]), "--headless"], cwd=root)
            self._flash("Recording preview in the background...", 3200)
        except OSError as exc:
            self._flash(f"Could not start the recorder: {exc}", 4200)

    def _poll_preview_jobs(self):
        for key, proc in list(self.preview_jobs.items()):
            code = proc.poll()
            if code is None:
                continue
            del self.preview_jobs[key]
            self.preview_gifs.clear()
            self._flash("Preview ready." if code == 0 else "Preview recording failed (see the console).", 3200)

    def _stop_preview_jobs(self):
        for proc in self.preview_jobs.values():
            if proc.poll() is None:
                proc.terminate()
        self.preview_jobs.clear()

    def _preview_badge(self, art, label, color, right=False):
        """A small pill in a corner of the preview (OLDER SAVE: the recording predates the last save)."""
        size = 9 if art.height < 120 else 10
        width = len(label) * (size - 1) + 18
        pill = pygame.Rect(0, 0, width, size + 10)
        if right:
            pill.topright = (art.right - 8, art.top + 8)
        else:
            pill.topleft = (art.left + 8, art.top + 8)
        self._panel(pill, (24, 14, 18, 190), color, 1, 8)
        self._text(label, (pill.left + 9, pill.top + 5), size, color, True)

    def _draw_details(self, rect, level, compact):
        m, s = level["meta"], level["stats"]
        title = m.get("title") or f"LEVEL {level['id']}"
        locked = bool(level.get("locked"))
        prefix = self.PREFIX.get(self.source.key, "LEVEL")
        self._text(f"{prefix} {level['id']:02d}", (rect.left + 18, rect.top + 15), 12, self.CORAL, True)
        self._text(title.upper(), (rect.left + 18, rect.top + 32), 24 if not compact else 19, self.CREAM, True, rect.width - 36)
        if locked:
            self._text(level.get("lock_text") or "Locked", (rect.left + 20, rect.top + 61), 11, self.CORAL, True, rect.width - 40)
        else:
            self._text(m.get("subtitle", self.source.default_subtitle), (rect.left + 20, rect.top + 61), 11, self.MUTED, True)

        # Static vignette panel -- no entities, no animation.
        art_h = 320 if not compact else 88
        art = pygame.Rect(rect.centerx + 16, rect.top + 16, (rect.width / 2) - 32, art_h)
        self._panel(art, (50, 26, 31, 200), (91, 48, 53, 200), 1, 12)
        if locked:
            self._lock_icon((art.centerx, art.centery - 10), 30, self.MUTED)
            self._text("LOCKED", (art.centerx - 28, art.centery + 14), 12, self.MUTED, True)
        else:
            # A recorded GIF of the real world running wins; the static map crop is the fallback.
            live, stale = self.preview_gifs.get(level, (int(art.width), int(art.height)), pygame.time.get_ticks())
            shot = live if live is not None else self._preview_surface(level, art.size)
            if shot is not None:
                self.screen.blit(shot, art.topleft)
                pygame.draw.rect(self.screen, (91, 48, 53), art, 1, border_radius=12)
            else:
                self._text("NO MAP PREVIEW", (art.centerx - 55, art.centery - 6), 12, self.CREAM, True)
            if live is not None and stale:
                self._preview_badge(art, "OLDER SAVE", self.GOLD, right=True)
            if live is None:
                self._draw_preview_button(art, level, "LOAD PREVIEW", compact)
            elif stale:
                self._draw_preview_button(art, level, "UPDATE", compact)

        y = rect.top + 83
        # Detail chips are intentionally concrete data from the level JSON.
        details = [
            ("DIFFICULTY", m.get("difficulty", "—")),
            ("THEME", m.get("theme", "—")),
            ("AUTHOR", m.get("author", "—")),
            ("CREATED", m.get("created", "Not recorded")),
            ("UPDATED", m.get("updated", "Not recorded")),
            ("MODE", m.get("mode", "—")),
            ("RUN", m.get("estimated_time", "—")),
        ]
        cols = 2 if rect.width >= 500 else 1
        cell_w = (rect.width / 2) // cols
        for i, (label, value) in enumerate(details):
            col, row = i % cols, i // cols
            x = rect.left + 18 + col * (cell_w + 8)
            yy = y + row * 34
            self._text(label, (x, yy), 9, self.MUTED, True)
            self._text(str(value)[:34], (x, yy + 10), 12, self.WHITE, True if label == "DIFFICULTY" else False)

        rows = math.ceil(len(details) / cols)
        y += rows * 34 + 4
        # "What's inside" telemetry: the user explicitly asked for this.
        self._text("WHAT'S HIDING INSIDE", (rect.left + 18, y), 12, self.CORAL, True)
        y += 16
        telemetry = [
            ("blocks", s["blocks"]), ("hostiles", s["enemies"]),
            ("treasure", s["treasures"]), ("objects", s["objects"])
        ]
        width = rect.width / 2
        for i, (label, val) in enumerate(telemetry):
            col, row = i % 2, i // 2
            if width < 430: col, row = i % 2, i // 2
            gap = (width - 36) / (4 if width >= 430 else 2)
            x = rect.left + 18 + col * gap
            yy = y + row * 27
            self._text(str(val), (x, yy), 14, self.CREAM, True)
            self._text(label, (x + 3 + len(str(val)) * 9, yy + 3), 11, self.MUTED, True)
        
        rows2 = math.ceil(len(telemetry) / (4 if width >= 430 else 2))
        y += rows2 * 27 + 4

        # Description/objective.
        self._text("THE WHISPER", (rect.left + 18, y), 12, self.CORAL, True)
        font = self._font(12)
        lines = self._wrap(m.get("description", ""), (rect.width / 2) - 16, font)
        for i, line in enumerate(lines[:2]): self._text(line, (rect.left + 18, y + 13 + i * 13), 12, self.WHITE)
        y = y + 13 + i * 13 + 25
        self._text("OBJECTIVE  " + str(m.get("objective", "Descend."))[:90], (rect.left + 18, y), 12, self.MUTED)

        # Tags.
        tag_y = y + 17
        tx = rect.left + 18
        for tag in list(m.get("tags", []))[:4]:
            tw = self._font(8, True).size(str(tag).upper())[0] + 15
            if tx + tw > rect.right - 18: break
            self._button(pygame.Rect(tx, tag_y, tw + 5, 20), str(tag).upper(), False, self.PURPLE, True)
            tx += tw + 10

        # Bottom action buttons are large enough for fingers.
        self.play_rect = pygame.Rect(rect.right - 150, rect.bottom - 47, 132, 39)
        if locked:
            self._panel(self.play_rect, (40, 26, 33), (92, 58, 62), 1, 9)
            lbl = self._font(12, True).render("LOCKED", True, self.MUTED)
            self.screen.blit(lbl, lbl.get_rect(center=self.play_rect.center))
        else:
            self._button(self.play_rect, "DESCEND  ▶", True, self.CORAL, True)

        # Pencil: jump straight into the editor for the selected level.
        left_edge = self.play_rect.left - 10
        if self._can_edit():
            self.edit_rect = pygame.Rect(self.play_rect.left - 54, self.play_rect.top, 44, 39)
            self.edit_hover = self._button(self.edit_rect, "", False, self.GOLD, True)
            self._pencil_icon(self.edit_rect.center, 19,
                              self.CREAM if self.edit_hover else self.WHITE)
            if self.edit_hover:
                hint = "EDIT THIS LEVEL"
                hw = self._font(9, True).size(hint)[0] + 14
                tip = pygame.Rect(self.edit_rect.centerx - hw // 2,
                                  self.edit_rect.top - 24, hw, 19)
                self._panel(tip, (34, 20, 28), self.GOLD, 1, 6)
                self._text(hint, (tip.left + 7, tip.top + 4), 9, self.CREAM, True)
            left_edge = self.edit_rect.left - 10
        else:
            self.edit_rect = pygame.Rect(0, 0, 1, 1)
            self.edit_hover = False

        # Upload is not built yet: the button is here so the place for it is settled.
        if self.source.can_upload:
            self.upload_rect = pygame.Rect(left_edge - 124, self.play_rect.top, 124, 39)
            self._panel(self.upload_rect, (40, 26, 33), (92, 58, 62), 1, 9)
            f = self._font(11, True)
            a = f.render("UPLOAD", True, self.MUTED)
            b = self._font(8, True).render("COMING SOON", True, (122, 96, 100))
            self.screen.blit(a, a.get_rect(center=(self.upload_rect.centerx, self.upload_rect.centery - 6)))
            self.screen.blit(b, b.get_rect(center=(self.upload_rect.centerx, self.upload_rect.centery + 9)))

    def _pencil_icon(self, center, size=18, color=None):
        """A vector pencil.

        Drawn rather than rendered as a glyph: the selector uses a serif
        system font, and '✏' silently falls back to tofu on plenty of the
        machines this runs on.
        """
        color = color or self.CREAM
        cx, cy = center
        ux, uy = 0.7071, -0.7071          # along the pencil, pointing up-right
        px, py = 0.7071, 0.7071           # across it
        length = size
        half = size * 0.19

        def at(t, off):
            return (cx - ux * length * 0.5 + ux * t + px * off,
                    cy - uy * length * 0.5 + uy * t + py * off)

        # Sharpened wooden tip.
        pygame.draw.polygon(self.screen, color,
                            [at(0, 0), at(length * 0.30, half), at(length * 0.30, -half)])
        # Barrel.
        pygame.draw.polygon(self.screen, color,
                            [at(length * 0.30, half), at(length, half),
                             at(length, -half), at(length * 0.30, -half)])
        # Graphite point and eraser, so it reads as a pencil at 19px.
        pygame.draw.polygon(self.screen, self.INK,
                            [at(0, 0), at(length * 0.11, half * 0.5), at(length * 0.11, -half * 0.5)])
        pygame.draw.polygon(self.screen, self.CORAL,
                            [at(length * 0.84, half), at(length, half),
                             at(length, -half), at(length * 0.84, -half)])

    # ---------------- create-new-level overlay ----------------
    def _next_level_id(self):
        return level_sources.next_id(self.source.folder)

    def _open_new_level(self):
        if not self._can_create():
            return
        self.new_open = True
        self.new_active_field = 0
        self.new_fields["title"] = f"Untitled Descent {self._next_level_id():02d}"
        if hasattr(pygame.key, "start_text_input"):
            pygame.key.start_text_input()

    def _create_new_level(self):
        level_id = self._next_level_id()
        now = datetime.date.today().isoformat()
        title = self.new_fields["title"].strip() or f"Untitled Descent {level_id:02d}"
        description = self.new_fields["description"].strip() or "A custom PIXEL ABYSS level."
        theme = self.new_fields["theme"].strip() or "Abyss"
        difficulty = self.new_fields["difficulty"].strip().upper() or "STANDARD"
        tags = [x.strip() for x in self.new_fields["tags"].split(",") if x.strip()]
        objective = self.new_fields["objective"].strip() or "Descend, survive, and reach the exit."

        # Start from the game's own entity settings so a fresh level behaves
        # exactly like an existing level instead of inventing a second format.
        entity_settings = None
        template = level_sources.read_json(paths.level_file(1, paths.STORY), [])
        for item in template if isinstance(template, list) else []:
            if isinstance(item, dict) and item.get("type") == "entity settings":
                entity_settings = copy.deepcopy(item)
                break

        if entity_settings is None:
            entity_settings = {"type": "entity settings"}

        meta = {
            "title": title,
            "subtitle": self.source.default_subtitle,
            "author": "BLEMAC",
            "created": now,
            "updated": now,
            "description": description,
            "difficulty": difficulty,
            "theme": theme,
            "tags": tags,
            "estimated_time": "5–10 min",
            "mode": "Solo + Local Co-op",
            "objective": objective,
            "official": bool(getattr(self.source, "official", False)),
            "campaign": "CUSTOM"
        }
        entity_settings["_level_meta"] = meta

        # A useful blank canvas: spawn point plus a small editable starter floor.
        world = [
            entity_settings,
            {"x": 0, "y": -64, "points": [[0, -128], [0, -64]], "width": 64, "height": 64, "type": "start"},
            level_preview.make(0, -64),
            {"x": -192, "y": 0, "width": 64, "height": 64, "type": "block", "name": "stone", "size": "big"},
            {"x": -128, "y": 0, "width": 64, "height": 64, "type": "block", "name": "stone", "size": "big"},
            {"x": -64, "y": 0, "width": 64, "height": 64, "type": "block", "name": "stone", "size": "big"},
            {"x": 0, "y": 0, "width": 64, "height": 64, "type": "block", "name": "stone", "size": "big"},
            {"x": 64, "y": 0, "width": 64, "height": 64, "type": "block", "name": "stone", "size": "big"},
            {"x": -192, "y": -64, "width": 32, "height": 52, "type": "enemy", "name": "Pawn", "color": "Yellow", "posted": False, "patroller": True, "patrol_range_x": 384, "patrol_range_y": 1000},
            {"x": -128, "y": -64, "width": 32, "height": 52, "type": "enemy", "name": "Pawn", "color": "Yellow", "posted": False, "patroller": True, "patrol_range_x": 384, "patrol_range_y": 1000},
            {"x": 1408, "y": -64, "width": 32, "height": 52, "type": "enemy", "name": "Pawn", "color": "Yellow", "posted": False, "patroller": True, "patrol_range_x": 384, "patrol_range_y": 1000},
        ]

        folder = self.source.folder
        paths.ensure_folder(folder)
        path = paths.level_file(level_id, folder)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(world, f, indent=2)

        # Folders that keep a metadata.json index (story, co-op) get the new entry too.
        # My Worlds does not need one: each world carries its own _level_meta.
        metadata_path = paths.metadata_file(folder)
        if os.path.exists(metadata_path):
            metadata = level_sources.read_json(metadata_path, {}) or {}
            metadata[str(level_id)] = meta
            try:
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)
            except OSError:
                pass

        # Refresh the selector without forcing a restart.
        self.levels.clear()
        self._load_levels()
        self._apply_filter()
        self.result = level_sources.LevelChoice(folder, level_id)
        self.running = False
        self.new_open = False
        if hasattr(pygame.key, "stop_text_input"):
            pygame.key.stop_text_input()

    def _draw_new_overlay(self):
        w, h = self.screen.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((18, 7, 14, 205))
        self.screen.blit(shade, (0, 0))
        rw, rh = min(720, w - 24), min(610, h - 24)
        rect = pygame.Rect((w-rw)//2, (h-rh)//2, rw, rh)
        self._panel(rect, (49, 24, 35), self.CORAL, 2, 18)
        self._text("NEW+  //  CREATE LEVEL", (rect.left + 22, rect.top + 18), 21, self.CREAM, True)
        self._text("Build a fresh canvas, then open it directly in the editor.", (rect.left + 25, rect.top + 47), 15, self.MUTED)

        labels = {
            "title": "TITLE", "description": "DESCRIPTION", "theme": "THEME",
            "difficulty": "DIFFICULTY", "tags": "TAGS  (comma separated)", "objective": "OBJECTIVE"
        }
        self.new_field_rects = {}
        y = rect.top + 92
        for i, key in enumerate(self.new_field_order):
            tall = key in ("description", "objective")
            fh = 66 if tall else 38
            fr = pygame.Rect(rect.left + 22, y, rect.width - 44, fh)
            active = i == self.new_active_field
            self.new_field_rects[key] = fr
            self._text(labels[key], (fr.left, fr.top - 18), 12, self.CORAL if active else self.MUTED, True)
            self._panel(fr, (32, 18, 26), self.CORAL if active else (100, 57, 64), 1 if not active else 2, 9)
            value = self.new_fields[key]
            font = self._font(14)
            lines = self._wrap(value, fr.width - 18, font) if tall else [value]
            for li, line in enumerate(lines[:4]):
                self._text(line, (fr.left + 9, fr.top + 8 + li * 16), 14, self.WHITE)
            y += fh + (27 if tall else 24)
            if y > rect.bottom - 95: break

        self.new_cancel_rect = pygame.Rect(rect.left + 22, rect.bottom - 48, 100, 32)
        self.new_create_rect = pygame.Rect(rect.right - 160, rect.bottom - 48, 138, 32)
        self._button(self.new_cancel_rect, "CANCEL", False, self.MUTED, True)
        self._button(self.new_create_rect, "CREATE  +", True, self.CORAL, True)
        self._text("TAB / ↑↓ fields   •   ENTER create   •   ESC cancel", (rect.centerx - 145, rect.bottom - 20), 8, self.MUTED)

    def _draw_pro_overlay(self):
        w, h = self.screen.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((20, 7, 13, 185))
        self.screen.blit(shade, (0, 0))
        rw, rh = min(680, w - 28), min(440, h - 30)
        rect = pygame.Rect((w-rw)//2, (h-rh)//2, rw, rh)
        self._panel(rect, (52, 24, 37), self.CORAL, 2, 18)
        self._text("PRO+ // THE FUN STUFF", (rect.left + 24, rect.top + 22), 21, self.CREAM, True)
        self._text("Built as premium surfaces — wire these to your entitlement later.", (rect.left + 25, rect.top + 50), 15, self.MUTED)
        features = [
            ("ROUTE GHOSTS", "Watch the best run haunt the level."),
            ("ABYSS CHALLENGES", "Mutators, time hunts and cursed rules."),
            ("DEEP TELEMETRY", "Personal stats for every official sector."),
            ("SMART DISCOVERY", "Find levels by mood, danger and style."),
            ("CLOUD FAVOURITES", "Keep your descent list across devices."),
            ("SECRET STARS", "Unlockable surprises hidden in the selector."),
        ]
        for i, (a, b) in enumerate(features):
            col, row = i % 2, i // 2
            x = rect.left + 24 + col * ((rw - 62)//2)
            y = rect.top + 86 + row * 62
            self._panel(pygame.Rect(x, y, (rw - 62)//2, 50), (39, 21, 31), (112, 55, 69), 1, 10)
            self._text("◆ " + a, (x + 10, y + 8), 14, self.PURPLE, True)
            self._text(b, (x + 10, y + 26), 13, self.WHITE)
        self.pro_close_rect = pygame.Rect(rect.right - 102, rect.bottom - 43, 78, 30)
        self._button(self.pro_close_rect, "CLOSE", False, self.CORAL, True)

    # ---------------- interaction ----------------
    def _move_selection(self, delta):
        if not self.filtered: return
        self.selected = (self.selected + delta) % len(self.filtered)
        if self.selected < self.scroll: self.scroll = self.selected
        if self.selected >= self.scroll + 5: self.scroll = self.selected - 4

    def _activate(self):
        if not self.filtered:
            return
        entry = self.filtered[self.selected]
        if entry.get("locked"):
            self._flash(entry.get("lock_text") or "This level is locked")
            return
        if self.edit_only and not self._may_edit_source():
            self._flash("Only My Worlds can be edited here")
            return
        self.result = level_sources.LevelChoice(entry["folder"], entry["id"], entry.get("players"))
        self.running = False

    def _request_edit(self):
        """Queue an editor session; run() picks it up after the event
        pump so the editor never starts mid-way through event handling."""
        if self._can_edit() and self.filtered:
            entry = self.filtered[self.selected]
            if entry.get("locked") and not entry.get("mode_locked"):   # a mode lock only closes playing, not editing
                self._flash(entry.get("lock_text") or "This level is locked")
                return
            self._edit_request = (entry["folder"], entry["id"])

    def _run_editor(self, folder, level_id):
        """Hand control to the editor, then re-read the level from disk."""
        if hasattr(pygame.key, "stop_text_input"):
            pygame.key.stop_text_input()
        try:
            self.on_edit(self.game, level_id, folder)
        except Exception as exc:
            print(f"Could not open the level editor for level {level_id}: {exc}")
        finally:
            if hasattr(pygame.key, "start_text_input"):
                pygame.key.start_text_input()

        # Edits change titles, stats and difficulty, so the card and the
        # details panel are rebuilt from the saved file.
        self.refresh(keep=level_id)
        pygame.event.clear()

    def refresh(self, keep=None):
        """Reload every level from disk, holding the current selection."""
        if keep is None and self.filtered:
            keep = self.filtered[self.selected]["id"]
        self.preview_cache.clear()
        self.preview_gifs.clear()
        self.levels.clear()
        self._load_levels()
        self._apply_filter()
        for index, level in enumerate(self.filtered):
            if level["id"] == keep:
                self.selected = index
                if self.selected < self.scroll:
                    self.scroll = self.selected
                if self.selected >= self.scroll + 5:
                    self.scroll = self.selected - 4
                break

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False; self.result = None; return
        if event.type == pygame.KEYDOWN:
            if self.new_open:
                if event.key == pygame.K_ESCAPE:
                    self.new_open = False
                    if hasattr(pygame.key, "stop_text_input"): pygame.key.stop_text_input()
                    return
                if event.key in (pygame.K_TAB, pygame.K_DOWN):
                    self.new_active_field = (self.new_active_field + 1) % len(self.new_field_order)
                    return
                if event.key == pygame.K_UP:
                    self.new_active_field = (self.new_active_field - 1) % len(self.new_field_order)
                    return
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._create_new_level()
                    return
                if event.key == pygame.K_BACKSPACE:
                    key = self.new_field_order[self.new_active_field]
                    self.new_fields[key] = self.new_fields[key][:-1]
                    return
                return
            if self.pro_open:
                if event.key in (pygame.K_ESCAPE, pygame.K_p): self.pro_open = False
                return
            if event.key == pygame.K_TAB and not self.search_active:
                step = -1 if (event.mod & pygame.KMOD_SHIFT) else 1
                self._switch_tab((self.tab + step) % len(self.sources))
                return
            if event.key == pygame.K_ESCAPE:
                self.running = False; self.result = None
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER): self._activate()
            elif event.key in (pygame.K_UP, pygame.K_w, pygame.K_LEFT): self._move_selection(-1)
            elif event.key in (pygame.K_DOWN, pygame.K_s, pygame.K_RIGHT): self._move_selection(1)
            elif event.key == pygame.K_f and self.filtered:
                lid = self.filtered[self.selected]["id"]
                if lid in self.favorites: self.favorites.remove(lid)
                else: self.favorites.add(lid)
            elif event.key == pygame.K_e and not self.search_active: self._request_edit()
            elif event.key == pygame.K_p and self.SHOW_PRO and not self.search_active: self.pro_open = True
            elif event.key == pygame.K_BACKSPACE and self.search_active:
                self.search = self.search[:-1]; self._apply_filter()
            elif self.search_active and event.unicode and event.unicode.isprintable() and len(self.search) < 40:
                self.search += event.unicode; self._apply_filter()
        elif event.type == pygame.TEXTINPUT:
            if self.new_open:
                key = self.new_field_order[self.new_active_field]
                max_len = 180 if key in ("description", "objective") else 70
                if len(self.new_fields[key]) < max_len:
                    self.new_fields[key] += event.text
            elif self.search_active:
                if len(self.search) < 40:
                    self.search += event.text; self._apply_filter()
        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
            if event.type == pygame.FINGERDOWN:
                pos = (int(event.x * self.screen.get_width()), int(event.y * self.screen.get_height()))
                button = 1
            else:
                pos = event.pos; button = event.button
            if button == 1:
                if self.new_open:
                    for i, key in enumerate(self.new_field_order):
                        if key in self.new_field_rects and self.new_field_rects[key].collidepoint(pos):
                            self.new_active_field = i
                            return
                    if self.new_create_rect.collidepoint(pos):
                        self._create_new_level(); return
                    if self.new_cancel_rect.collidepoint(pos):
                        self.new_open = False
                        if hasattr(pygame.key, "stop_text_input"): pygame.key.stop_text_input()
                    return
                if self.pro_open:
                    if self.pro_close_rect.collidepoint(pos): self.pro_open = False
                    return
                self.search_active = self.search_rect.collidepoint(pos)
                if self.search_active and hasattr(pygame.key, "start_text_input"):
                    pygame.key.start_text_input()
                    return
                for r, idx in self.category_rects:
                    if r.collidepoint(pos):
                        self._switch_tab(idx); return
                for r, idx in self.card_rects:
                    if r.collidepoint(pos): self.selected = idx; return
                if self._can_create() and self.new_rect.collidepoint(pos): self._open_new_level()
                elif self._can_edit() and self.edit_rect.collidepoint(pos): self._request_edit()
                elif self.source.can_upload and self.upload_rect.collidepoint(pos):
                    self._flash("Uploading worlds is coming soon.")
                elif self.preview_btn_level is not None and self.preview_btn_rect.collidepoint(pos):
                    self._start_preview_job(self.preview_btn_level)
                elif self.play_rect.collidepoint(pos): self._activate()
                elif self.back_rect.collidepoint(pos): self.running = False; self.result = None
                elif self.SHOW_PRO and self.pro_rect.collidepoint(pos): self.pro_open = True
            elif button == 4: self.scroll = max(0, self.scroll - 1)
            elif button == 5: self.scroll = min(max(0, len(self.filtered) - 1), self.scroll + 1)
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(max(0, len(self.filtered) - 1), self.scroll - event.y))

    def run(self):
        clock = Settings.clock
        if hasattr(pygame.key, "start_text_input"): pygame.key.start_text_input()
        try:
            dt = 0.1
            while self.running:
                for event in pygame.event.get(): self.handle_event(event)

                if self._edit_request is not None:
                    (folder, level_id), self._edit_request = self._edit_request, None
                    self._run_editor(folder, level_id)
                    continue

                self.mini_world.update() if self.mini_world else None
                self._poll_preview_jobs()
                self.draw(pygame.time.get_ticks())
                
                pygame.display.flip()
                
                # HANDLE DELTA TIME
                dt = clock.tick(getattr(Settings, "FPS", 30))
                if self.mini_world:
                    raw_dt = dt / 1000.0
                    self.mini_world.game_speed = min(self.mini_world.max_game_speed, self.mini_world.game_speed + 0.1)
                    self.mini_world.dt = round(min(0.1, raw_dt * self.mini_world.game_speed), 3)

                    self.mini_world.master_clock += int(raw_dt * 80)
        finally:
            self._stop_preview_jobs()
            if hasattr(pygame.key, "stop_text_input"): pygame.key.stop_text_input()
        return self.result


def select_level(game, levels_dir=paths.LEVELS_ROOT, on_edit=_DEFAULT, dev=False):
    """Open the level hub and return a ``LevelChoice(folder, id, players)``, or None if backed out.

    ``on_edit`` defaults to the in-place level editor when the host object
    can run one. Pass ``None`` to hide the pencil, or your own
    ``callable(game, level_id, folder)`` to route editing somewhere else.
    ``dev=True`` is for the standalone editor: all story levels open, the
    pencil on every tab.
    """
    if on_edit is _DEFAULT:
        on_edit = editor_launch.launch_editor if editor_launch.can_edit(game) else None
    return LevelSelector(game, levels_dir, on_edit=on_edit, dev=dev).run()
