import pygame
import json
import os
from os.path import join
import copy

from ..scripts.functions import (
    parallax_bg, map_chunks
)
from ..scripts.menu import RPGMenu
from ..scripts import paths
from ..scripts.sounds import Sounds
from ..scripts.asset_funcs import get_block
from ..scripts.cache import (
    cache_assets, cache_img, get_door, get_deco_sprites
)
from ..data.palletes.doors import door_name
from ..scripts.physics import PHYSICS

from ..settings import Settings
from ..assets import Assets
from ..entities.entities import Player
from ..objects.objects import Bombs

from .level_select import select_level
from .main.draw_funcs import hide, draw
from .main.level_loader import Level_Loader
from .main.update_funcs import update_game_logic
from .editor.editor_tools import Level_Editor_Tools
from .editor import editor_palette
from .editor import spawner_tools
from .editor import start_tools
from .editor import preview_tools
from .editor import editor_launch
from .editor import layer_tools
from .editor import clipboard_store
from .editor import place_rules

from ..ui import ui_theme

EDITOR_HELP_SECTIONS = [
    ("PLACING & REMOVING", [
        "Left click a grid cell to select it, click it again to confirm — "
        "placing or removing depending on the current mode.",
        "Hold right click and drag across cells to paint continuously, "
        "without re-confirming each one.",
        "'Insert Mode' button (or 1 / I) switches between placing and "
        "deleting.",
    ]),
    ("MOVING AROUND", [
        "Left click and drag empty space to pan the camera.",
        "Scroll the mouse wheel to zoom in and out.",
        "'+' / '-' buttons, or the - and = keys, also adjust zoom.",
    ]),
    ("EDITING OPTIONS", [
        "'Type' and 'Size' cycle through variants for the selected "
        "category; Shift (or 3) reverses the cycle direction.",
        "'Category' switches between blocks, enemies, treasure, deco, "
        "water, platforms, spawners and start points.",
        "SELECT / DRAG: drag a box to select, drag the selection to move it, "
        "arrows nudge it. Ctrl+C copies; Ctrl+V shows a green preview with "
        "its top-left on the selected cell (click a cell or use arrows to "
        "move it). SPACE places it, ESC or END cancels - nothing changes until SPACE. "
        "Arrow keys on a selection also move a ghost: SPACE / ENTER places it, END cancels. "
        "Dragging a selection also shows a ghost: release to place it, "
        "END cancels the move.",
        "The mode button cycles INSERT -> DELETE -> MODIFY. In MODIFY, "
        "left-clicking anything already placed reopens its settings "
        "popup with its current values, so you can retune a patrol "
        "range or a spawner without deleting and replacing it. "
        "Clicking an ENEMY opens the ENTITY EDITOR instead (see below).",
        "ENTITY EDITOR (MODIFY an enemy): tweaks are grouped in categories on the left - Placement, Health, "
        "Combat, Arrows & Ammo, Movement & Dash, Homing Traps, Boss - plus the shop items (Upgrades, Perks, "
        "Rare, Arsenal, Boosts) it can be granted. UP/DOWN pick a row, LEFT/RIGHT change it (Shift = x10), "
        "TAB or [ ] change category, type digits for an exact number, DEL resets a row, ENTER applies, ESC cancels. "
        "Sliders and the dot beside a changed row work with the mouse. In Boss, 'Fill in kit' sets up a "
        "ready-made boss for that enemy type (the Archer kit gives homing arrows, a dash and homing traps).",
        "HOMING ARROW TRAP (Traps category, type 'homing'): a few homing arrows aimed at a spot instead of at an "
        "enemy, so they keep revolving around it and shoot whatever hostile passes. It has no owner, so MODIFY opens "
        "a window where its effects are set by hand (damage, knockback, burn, pierce, arrows, radius, who it hurts, "
        "how long it lasts). Traps dropped by players (TRAP key: V / E / pad button 3, needs a Homing Trap Kit from the "
        "shop) or by enemies given the ability use the owner's arrow properties instead.",
        "Start points are the player spawn pool. The first one (P1, "
        "gold) is where the level opens; the rest are used to spread "
        "local co-op players out. Click an existing point in INSERT or "
        "MODIFY mode to promote it to P1.",
        "V sets the level's MAP PREVIEW point, the spot the level selector's map "
        "picture is centred on: type its X / Y world coordinates (they start as the "
        "middle of what the camera sees) or tick Remove. It is drawn as a purple "
        "cross with a frame, and saved in the level as "
        "{'type': 'preview coordinates', 'x': 0, 'y': 0}.",
        "'Entity Stats' tunes health, damage and aggro ranges per enemy "
        "type for this level only.",
        "Ctrl+Z / Ctrl+Y undo or redo the last placement, deletion, or edit.",
        "Spawners drip enemies into the level while it's being played: "
        "'Type' and 'Colour' pick the enemy, then the popup sets how "
        "often they appear, how many in total, and the full roster.",
        "'Perspective' (or 2 / P) flips between foreground and background "
        "layers.",
        "Shortcuts: 4 Blocks, 5 Enemies, 6 Deco, 7 Water, 8 Platforms, T Traps, "
        "9 Doors, 0 Spawners.",
        "B (or the Biome button on Blocks) cycles the biome of the selected "
        "block; Shift reverses. On Deco and Doors, B cycles the palette / biome.",
        "F1 or Q toggles the placement grid overlay.",
        "LAYERS (the button bottom-left, or L) lists every category with its key and whether it is ON or OFF. "
        "While that panel is open, 1-9 and 0 show / hide BLOCKS, ENEMIES, TREASURE, DECO, WATER, PLATFORMS, "
        "DOORS, SPAWNERS, START POINTS and TRAPS; Alt + 1-9 / 0 does the same with the panel closed. "
        "Hidden layers are not drawn or selectable, and choosing a hidden category to place shows it again.",
        "With blocks selected, ] (or Page Up) turns them into FOREGROUND blocks and [ (or Page Down) into "
        "BACKGROUND blocks. OVER / BEHIND (below) decides what happens if something is in the way.",
        "Ctrl+C copies the selection and it stays copied when you open another level's editor: "
        "open that level, press Ctrl+V and place it as usual. Ctrl+X cuts: it copies and removes the selection.",
        "Moving or pasting onto things the placement rules do not allow beside each other: "
        "OVER replaces what is in the way, BEHIND keeps what is already there (pasted objects that "
        "conflict are skipped; moved ones stay where they were). Tab or the PLACE chip at the bottom switches; "
        "red crosses show what will be replaced or skipped.",
    ]),
    ("SAVING & LEAVING", [
        "'Save' (or Ctrl+S) writes the level to disk immediately.",
        "ESC or 'Back' leaves the editor — if you have unsaved edits "
        "you'll be asked whether to save them first.",
    ]),
]


def draw_selection_overlay(self):
        """Professional editor affordance: marquee, bounds, handles, count."""
        def draw_ghost(items, dx, dy, text, color=(120, 255, 160)):
            ghosts = []
            for item in items:
                rect = pygame.Rect(
                    int((item.get("x", 0) + dx - self.offset_x) * self.zoom),
                    int((item.get("y", 0) + dy - self.offset_y) * self.zoom),
                    max(4, int(item.get("width", 64) * self.zoom)),
                    max(4, int(item.get("height", 64) * self.zoom)),
                )
                ghosts.append(rect)
                shade = pygame.Surface(rect.size, pygame.SRCALPHA)
                shade.fill((*color, 70))
                self.window.blit(shade, rect.topleft)
                pygame.draw.rect(self.window, color, rect, 2)
            hull = ghosts[0].unionall(ghosts[1:]) if len(ghosts) > 1 else ghosts[0]
            pygame.draw.rect(self.window, (255, 224, 151), hull.inflate(8, 8), 1)
            label = pygame.font.SysFont("consolas", 14, bold=True).render(
                text, True, (255, 242, 207))
            self.window.blit(label, (hull.x, max(4, hull.y - 22)))

        def mark(items, dx, dy, color, dashed=False):
            """Outline objects the placement would replace (existing ones) or skip (ghosts)."""
            for item in items:
                rect = pygame.Rect(
                    int((item.get("x", 0) + dx - self.offset_x) * self.zoom),
                    int((item.get("y", 0) + dy - self.offset_y) * self.zoom),
                    max(4, int(item.get("width", 64) * self.zoom)),
                    max(4, int(item.get("height", 64) * self.zoom)),
                )
                pygame.draw.rect(self.window, color, rect, 1 if dashed else 3)
                pygame.draw.line(self.window, color, rect.topleft, rect.bottomright, 2)
                pygame.draw.line(self.window, color, rect.topright, rect.bottomleft, 2)

        if getattr(self, "pasting", False) and getattr(self, "clipboard", None):
            dx, dy = self.paste_offset()
            removed, skipped = place_rules.preview(self, self.clipboard, dx, dy)
            mark(removed, 0, 0, (255, 90, 80))
            draw_ghost(self.clipboard, dx, dy,
                       f"PASTE {len(self.clipboard)} {place_rules.mode(self).upper()}"
                       f"{f' (replaces {len(removed)})' if removed else ''}"
                       f"{f' (skips {len(skipped)})' if skipped else ''}"
                       f"  |  click / arrows move  |  SPACE place  |  Tab over/behind  |  ESC cancel")
            mark(skipped, 0, 0, (255, 90, 80), dashed=True)
            return
        moving = getattr(self, "move_preview", None)
        if (moving is not None or getattr(self, "dragging_selection", False)) and getattr(self, "selection", None):
            dx, dy = moving if moving is not None else self.drag_ghost_offset()
            removed, stayed = place_rules.preview(self, self.selection, dx, dy, moving=True) if (dx or dy) else ([], [])
            mark(removed, 0, 0, (255, 90, 80))
            for data in self.selection:
                home = pygame.Rect(
                    int((data.get("x", 0) - self.offset_x) * self.zoom),
                    int((data.get("y", 0) - self.offset_y) * self.zoom),
                    max(4, int(data.get("width", 64) * self.zoom)),
                    max(4, int(data.get("height", 64) * self.zoom)),
                )
                pygame.draw.rect(self.window, (100, 205, 255), home, 1)
            draw_ghost(self.selection, dx, dy,
                       (f"MOVE {len(self.selection)} {place_rules.mode(self).upper()}"
                        f"{f' (replaces {len(removed)})' if removed else ''}"
                        f"{f' (stays {len(stayed)})' if stayed else ''}"
                        f"  |  arrows move  |  SPACE / ENTER place  |  Tab over/behind  |  END cancel"
                        if moving is not None else
                        f"MOVE {len(self.selection)} {place_rules.mode(self).upper()}"
                        f"{f' (replaces {len(removed)})' if removed else ''}"
                        f"{f' (stays {len(stayed)})' if stayed else ''}"
                        f"  |  release to place  |  Tab over/behind  |  END cancel"),
                       color=(255, 200, 110))
            return
        if getattr(self, "selection_box", None):
            a, b = self.selection_box
            rect = pygame.Rect(min(a[0], b[0]), min(a[1], b[1]),
                               abs(b[0] - a[0]), abs(b[1] - a[1]))
            shade = pygame.Surface(rect.size, pygame.SRCALPHA)
            shade.fill((80, 170, 255, 35))
            self.window.blit(shade, rect.topleft)
            pygame.draw.rect(self.window, (100, 190, 255), rect, 2)
            return
        selected = getattr(self, "selection", [])
        if not selected:
            return
        bounds = []
        for data in selected:
            rect = pygame.Rect(
                int((data.get("x", 0) - self.offset_x) * self.zoom),
                int((data.get("y", 0) - self.offset_y) * self.zoom),
                max(4, int(data.get("width", 64) * self.zoom)),
                max(4, int(data.get("height", 64) * self.zoom)),
            )
            bounds.append(rect)
            pygame.draw.rect(self.window, (100, 205, 255), rect, 2)
            for corner in (rect.topleft, rect.topright, rect.bottomleft, rect.bottomright):
                pygame.draw.circle(self.window, (255, 224, 151), corner, 4)
        hull = bounds[0].unionall(bounds[1:]) if len(bounds) > 1 else bounds[0]
        pygame.draw.rect(self.window, (255, 224, 151), hull.inflate(8, 8), 1)
        label = pygame.font.SysFont("consolas", 14, bold=True).render(
            f"{len(selected)} selected  |  drag / arrows move  |  Ctrl+C then Ctrl+V", True, (255, 242, 207))
        self.window.blit(label, (hull.x, max(4, hull.y - 22)))


class Level_Editor(Level_Loader, Level_Editor_Tools, Settings):
    def __init__(self):
        
        self.initialise_grid()
        self.initialise_constants()

        # CACHE
        self.CACHED_ENTITY_ZOOM_IMAGES = {}
        self.entity_sprite_cache = {}
        self.object_sprite_cache = {}        
        self.cached_objects = {}
        
        
        self.players = []
        self.local_players = []
        self.player_slots = []
        self.saved_players = {}

        self.player = Player(0, 0, 50, 50, 'TNT', 'Green', game=self)
        self.player.control_type = 'keyboard'
        self.player.keyboard_num = 0
        self.saved_players[self.player.id] = self.player
        self.player_slots.append(self.player)

        self.bombs = Bombs(game=self)
        self.sounds = Sounds(self.player, 4)

        self.controllers = []
        self.controller_selection = True
        self.control_type = 'joystick'

        self.scroll_area_width = 200
        self.offset_x = 0
        self.offset_y = 0
        
        self.zoom = 1.0
        self.min_zoom = 0.5
        self.max_zoom = 1.5
        self.zoom_speed = 0.05

        self.chunk_w, self.chunk_h = (12, 12)
        
        self.debug = {}
        self.log = 0

        self.dt = 0
        self.game_speed = 1
        self.max_game_speed = 1

        self.bg_color = (10, 10, 10)
        self.parallax_color = (22, 19, 40)
        self.bg_particles = []

        self.MULTIPLAYER = False
        self.SERVER = False

    def initialise_constants(self):
        self.menu_bg = pygame.transform.scale(pygame.image.load(paths.asset("background", "menu_bg.jpg")), (self.WIDTH, self.HEIGHT)).convert()
        
    def get_fps(self):
        # Get and draw FPS
        fps = self.clock.get_fps()
        fps_surface = self.font.render(f"FPS: {int(fps)}", True, (255, 255, 255))
        self.window.blit(fps_surface, (10, 10))

    def start(self):
        if not editor_launch.editor_available():
            print("The level editor is only available when DEBUGGING_MODE is on.")
            return
        while True:    
            choice = select_level(self, paths.LEVELS_ROOT, dev=True)
            if choice is None:
                return
            self.level = int(choice.id)
            self.level_folder = choice.folder
            
            self.edit_world(load=True)

    def edit_world(self, level=None, load=False):
        # The editor is a debug tool: without DEBUGGING_MODE every way into it ends here.
        if not editor_launch.editor_available():
            print("The level editor is only available when DEBUGGING_MODE is on.")
            return
        self.level = level if level else self.level
        if load:
            self.load_world()

            # Timer variables
            self.start_ticks = pygame.time.get_ticks()
            self.current_ticks = pygame.time.get_ticks()
            self.pause_start = 0
            self.pause_total = 0
            self.elapsed_seconds = (self.current_ticks - self.start_ticks - self.pause_total) // 1000
            self.seconds = 0
            self.minutes = 0
            self.master_clock = 0

        self.editing_level = True

        self.EDIT_WORLD = True

        self.lastx = self.offset_x
        self.lasty = self.offset_y

        self.menu_btn_text = 'BACK'
        self.clicked = False

        self.size_rect = pygame.Rect(0, 0, 60, 40)
        self.item_size = '0;0'

        surf = cache_img((64, 64))

        self.skip = False

        sw, sh = self.window.get_size()
        
        text_font = pygame.font.SysFont("serif", int(sw * 0.01))
        font = pygame.font.SysFont("serif", int(sw * 0.03)) # 36

        def type_(object_):
            print("Changed type!")
            if object_.shift:
                # Backwards through every group of the category: from the first variant of a group, go to the
                # last variant of the previous group (forwards does the mirror image), wrapping at the ends.
                if object_.block_num == 0:
                    object_.type_num = (object_.type_num - 1) % len(object_.block_types)
                    object_.block_num = len(object_.block_types[object_.type_num]) - 1
                else:
                    object_.block_num -= 1
            else:
                object_.block_num += 1

            object_.skip = True

        def size(object_):
            print("Changed size or colour!")
            if object_.shift:
                # (-1 used to be clamped to 0 by the loop below, so Shift never went backwards or wrapped)
                count = len(object_.block_sizes)
                object_.size_num = (object_.size_num - 1) % count if count else 0
            else:
                object_.size_num += 1

            object_.skip = True

        def biome(object_):
            """Cycle the biome (colour variant) of the current category.

            Blocks: swap the ``_2``.. ``_8`` suffix of the selected block and
            keep its kind. Deco / Doors: same as their Palette / Biome button.
            """
            if object_.EDIT_GRID in (editor_palette.DECO, editor_palette.DOORS):
                size(object_)
                return
            if object_.EDIT_GRID != editor_palette.BLOCKS:
                return
            names = object_.block_types[object_.type_num]
            current = names[object_.block_num]
            base, cur = editor_palette.block_biome_split(current)
            if not editor_palette.block_has_biomes(current):
                return
            order = editor_palette.BIOMES
            step = -1 if object_.shift else 1
            nxt = order[(order.index(cur) + step) % len(order)]
            target = editor_palette.block_biome_name(base, nxt)
            if target in names:
                object_.block_num = names.index(target)
            object_.skip = True

        def category(object_):
            print("Changed category!")
            step = -1 if object_.shift else 1                      # Shift (or 3) reverses the cycle
            object_.EDIT_GRID = (object_.EDIT_GRID + step) % len(object_.edit_grid_settings)
            layer_tools.ensure_visible(object_, object_.EDIT_GRID)
            # Variant indices belong to the old category -- reset them so
            # switching never lands on an out-of-range type/size.
            object_.type_num = 0
            object_.block_num = 0
            object_.size_num = 0
            settings = object_.edit_grid_settings[object_.EDIT_GRID]
            # object_.EDIT_GRID_BTN.text = settings['button_text']
            # object_.CHANGE_SIZE_BTN.text = settings['change_size_text']
            object_.block_types = settings['block_types']
            object_.block_sizes = settings['block_sizes']

            object_.skip = True

        def category_to(object_, category_id):
            if category_id not in object_.edit_grid_settings:
                return
            object_.EDIT_GRID = category_id
            layer_tools.ensure_visible(object_, category_id)
            object_.type_num = object_.block_num = object_.size_num = 0
            settings = object_.edit_grid_settings[category_id]
            object_.block_types = settings["block_types"]
            object_.block_sizes = settings["block_sizes"]
            object_.skip = True
        
        def apply_changes(object_):
            changed_kinds = object_.changes
            
            if "block_fore" in changed_kinds:
                import threading
                object_.outline_objects = PHYSICS.get_outline_blocks(object_.objects, tile_size=64)
                
                blank_map = copy.deepcopy(object_.blank_map)
                object_.map = map_chunks(blank_map, object_.outline_objects, object_.minx, object_.miny, object_.maxx, object_.maxy, object_.chunk_w, object_.chunk_h)
                blank_map = copy.deepcopy(object_.blank_map)
                object_.objects_map = map_chunks(blank_map, object_.objects, object_.minx, object_.miny, object_.maxx, object_.maxy, object_.chunk_w, object_.chunk_h) 
                object_.env_ready = False
                threading.Thread(target=object_.create_nodes, daemon=True).start()
                ui_theme.processing_overlay(
                    object_, lambda: object_.env_ready,
                    message="APPLYING CHANGES...",
                    subtext="Recalculating enemy pathing for your edits.",
                )

            if "block_back" in changed_kinds:
                blank_map = copy.deepcopy(object_.blank_map)
                object_.bg_objects_map = map_chunks(blank_map, object_.bg_objects, object_.minx, object_.miny, object_.maxx, object_.maxy, object_.chunk_w, object_.chunk_h) 
        
            if "deco" in changed_kinds:
                blank_map = copy.deepcopy(object_.blank_map)
                object_.damageable_objects_map = map_chunks(
                    blank_map, object_.damageable_objects, object_.minx, object_.miny,
                    object_.maxx, object_.maxy, object_.chunk_w, object_.chunk_h
                )
            if "zones" in changed_kinds:
                blank_map = copy.deepcopy(object_.blank_map)
                object_.zones_map = map_chunks(
                    blank_map, object_.zones, object_.minx, object_.miny, object_.maxx, object_.maxy,
                    object_.chunk_w, object_.chunk_h
                )
            if "entities" in changed_kinds:    
                object_._entities_dirty = True
            
            object_.changes.clear()

        def save(object_):
            if not editor_launch.editor_available():
                print("The level editor is debug-only (debug mode is off): nothing saved.")
                object_.skip = True
                return
            print("Saved World!")
            # Save block coordinates
            path = object_.level_path()
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            if os.path.exists(path):
                with open(path, "r") as source, open(path + ".bak", "w") as backup:
                    backup.write(source.read())
            with open(path, "w") as f:
                json.dump(object_.world, f, indent=2)

            object_.changes.clear()
            object_.skip = True

        def how_to(object_):
            ui_theme.show_help_overlay(object_, "LEVEL EDITOR — HOW TO", EDITOR_HELP_SECTIONS)
            object_.skip = True

        def undo(object_):
            if object_.undo_edit():
                object_.skip = True

        def redo(object_):
            if object_.redo_edit():
                object_.skip = True

        def back_(object_):
            print("Quit Level Editor!")

            # Snapshot before anything (save/discard) can clear it, so we
            # still know what needs rebuilding either way.
            changed_kinds = set(object_.changes)

            if changed_kinds:
                should_save = ui_theme.confirm_dialog(
                    object_, "UNSAVED CHANGES",
                    "You've made changes to this level that haven't been "
                    "saved yet. Save before leaving the editor?",
                    yes_label="YES, SAVE", no_label="NO, DISCARD",
                )
                if should_save:
                    save(object_)

            object_.offset_x = object_.lastx
            object_.offset_y = object_.lasty
            object_.EDIT_WORLD = False
            object_.editing_level = False
            object_.skip = True

            apply_changes(object_)
            
        TOOL_CYCLE = ["insert", "delete", "modify", "select"]

        def change_mode(object_, tool=None):
            current = getattr(object_, "TOOL", "insert" if object_.INSERT else "delete")
            if tool is None:
                step = -1 if object_.shift else 1                  # Shift (or 3) reverses the cycle
                tool = TOOL_CYCLE[(TOOL_CYCLE.index(current) + step) % len(TOOL_CYCLE)]

            object_.TOOL = tool
            # Everything that still reads the old boolean sees "insert".
            object_.INSERT = tool == "insert"

            if tool != "insert":
                object_.platform = []
            object_.confirm = None

            print(f"{tool.capitalize()} Mode Activated!")
            object_.skip = True

        def entity_stats(object_):
            object_.edit_entity_settings()
            object_.skip = True

        def zoom_about_centre(object_, new_zoom):
            """Change the zoom keeping the world point in the middle of the screen where it is (the camera offset
            is the top-left corner of the view, so changing only the zoom made everything slide toward it)."""
            new_zoom = max(object_.min_zoom, min(object_.max_zoom, new_zoom))
            centre_x = object_.offset_x + Settings.WIDTH / object_.zoom / 2
            centre_y = object_.offset_y + Settings.HEIGHT / object_.zoom / 2
            object_.zoom = new_zoom
            object_.offset_x = centre_x - Settings.WIDTH / new_zoom / 2
            object_.offset_y = centre_y - Settings.HEIGHT / new_zoom / 2
            # the per-frame clamp keeps the view inside the level

        def zoom_in(object_):
            print("Zoomed In!")
            zoom_about_centre(object_, object_.zoom - object_.zoom_speed)
            object_.skip = True

        def zoom_out(object_):
            print("Zoomed Out!")
            zoom_about_centre(object_, object_.zoom + object_.zoom_speed)
            object_.skip = True
        
        def perspective(object_):
            object_.perspective = "fore" if object_.perspective == "back" else "back"
            print(f"Perspective changed to {object_.perspective}ground.")
            
            object_.skip = True

        def show_grid(object_):
            object_.show_grid = not object_.show_grid
            print(f"SHOW_GRID ~ {'OFF' if not object_.show_grid else 'ON'}")
            
            object_.skip = True

        button_data = [
            ("Back", back_, [self]), ("Insert Mode", change_mode, [self]),
            ("Size", size, [self]), ("Type", type_, [self]),
            ("Category", category, [self]), ("Undo", undo, [self]),
            ("Redo", redo, [self]), ("Save", save, [self]),
            ("+", zoom_out, [self]), ("-", zoom_in, [self]), ("Perspective", perspective, [self]),
            ("How To", how_to, [self]), ("Entity Stats", entity_stats, [self]),
            ("Biome", biome, [self])
        ]

        layout = [
             # X           # Y    # WIDTH  # HEIGHT
            (1 - 0.02 - 0.1, 0.02 + 0.06, 0.1, 0.06),
            (1 - 0.02 * 2 - 0.3, 0.02 + 0.06, 0.2, 0.06),
            (1 - 0.02 * 2 - 0.1, 0.02 * 2 + 0.06 * 2 + 0.05, 0.1, 0.06),
            (1 - 0.02 * 2 - 0.4, 0.02 * 2 + 0.06 * 2 + 0.05, 0.1, 0.06),
            (1 - 0.02 * 2 - 0.3, 0.35, 0.2, 0.06),
            (0.02, 0.18, 0.1, 0.06),
            (0.13, 0.18, 0.1, 0.06),
            (0.02, 0.26, 0.1, 0.06),
            (0.035, 0.1, 0.07, 0.05),
            (0.035, 0.02, 0.07, 0.05),
            (1 - 0.5 - 0.1, 0.02, 0.2, 0.06),
            (0.02, 0.26, 0.1, 0.06),
            (0.02, 0.34, 0.14, 0.06),
            (1 - 0.02 * 2 - 0.3, 0.43, 0.2, 0.06)
        ]

        rel_rect = (1 - 0.02 * 2 - 0.3, 0.02 * 2 + 0.06 + 0.06, 0.2, 0.06 * 3)

        display_rect = pygame.Rect(
            int(rel_rect[0] * sw),
            int(rel_rect[1] * sh),
            int(rel_rect[2] * sw),
            int(rel_rect[3] * sh)
        )

        menu = RPGMenu(self.window, font, button_data, layout)

        mode = "all"
        self.shift = False
        self.show_grid = True
        self._draw_list_dirty = True
        self.changes = set()
        self._undo_stack = []
        self._redo_stack = []
        self.selection = []
        self.clipboard = clipboard_store.load()        # survives closing the editor: paste it into another level
        layer_tools.init(self)                         # show / hide categories (L, Alt+1-9, LAYERS button)
        self.dragging_selection = False
        self._drag_pixels = [0, 0]
        self.selection_box = None
        self.pasting = False
        self._drag_cp = False

        while self.editing_level:
            if not self.env_ready:
                from ..windows import Windows
                # --------------------------------------------------------------------------------------------------------------
                # LOADING SCREEN
                # --------------------------------------------------------------------------------------------------------------
                Windows.loading(self)
                
                update_game_logic(self)
            
            menu.exclude((10, not self.EDIT_GRID == editor_palette.BLOCKS))
            menu.exclude((2, self.EDIT_GRID in editor_palette.NO_SIZE_CATEGORIES))
            menu.exclude((13, not (self.EDIT_GRID == editor_palette.BLOCKS
                                   and editor_palette.block_has_biomes(
                                       self.block_types[self.type_num][self.block_num]))))
            
            mouse_pos = pygame.mouse.get_pos()
            events = pygame.event.get()

            for event in events:
                if event.type == pygame.QUIT:
                    self.editing_level = False
                    break
                
                if event.type == pygame.JOYAXISMOTION:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event, "axis")
                    
                if event.type == pygame.JOYBUTTONDOWN:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event)
                    
                if event.type == pygame.KEYDOWN and getattr(self, "move_preview", None) is not None:
                    # Arrow-key move preview owns these keys until placed or cancelled.
                    move_step = {pygame.K_LEFT: (-64, 0), pygame.K_RIGHT: (64, 0),
                                 pygame.K_UP: (0, -64), pygame.K_DOWN: (0, 64)}
                    if event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER):
                        self.commit_move()
                        self.skip = True
                        continue
                    if event.key in (pygame.K_ESCAPE, pygame.K_END):
                        self.cancel_move()
                        self.skip = True
                        continue
                    if event.key in move_step:
                        self.nudge_selection(*move_step[event.key])
                        continue

                if event.type == pygame.KEYDOWN and getattr(self, "pasting", False):
                    # Paste preview owns these keys until it is placed or cancelled.
                    paste_step = {pygame.K_LEFT: (-64, 0), pygame.K_RIGHT: (64, 0),
                                  pygame.K_UP: (0, -64), pygame.K_DOWN: (0, 64)}
                    if event.key == pygame.K_SPACE:
                        self.commit_paste()
                        continue
                    if event.key in (pygame.K_ESCAPE, pygame.K_END):
                        self.cancel_paste()
                        continue
                    if event.key in paste_step:
                        self.move_paste_anchor(*paste_step[event.key])
                        continue

                if event.type == pygame.KEYDOWN and layer_tools.handle_key(self, event):
                    self.skip = True
                    continue

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and place_rules.chip_click(self, event.pos):
                    self.skip = True
                    continue

                if (event.type == pygame.KEYDOWN and event.key == pygame.K_TAB
                        and (getattr(self, "TOOL", "insert") == "select" or getattr(self, "pasting", False))):
                    place_rules.toggle_mode(self)
                    self.skip = True
                    continue

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and layer_tools.handle_click(self, event.pos):
                    self.skip = True
                    continue

                if event.type == pygame.MOUSEBUTTONUP and layer_tools.over_ui(self, event.pos):
                    continue

                if event.type == pygame.KEYDOWN and event.key == pygame.K_END:
                    # END backs out of whatever is in flight: a ghost drag or
                    # a half-drawn selection box. (Paste is handled above.)
                    if self.cancel_drag() or getattr(self, "selection_box", None):
                        self.selection_box = None
                        self.skip = True
                    continue

                if event.type == pygame.KEYDOWN and event.key == pygame.K_b:
                    biome(self)
                    continue

                if event.type == pygame.KEYDOWN:
                    if event.key in [pygame.K_RSHIFT, pygame.K_LSHIFT, pygame.K_3]:
                        self.shift = not self.shift
                    
                    if event.key in [pygame.K_F1, pygame.K_q]:
                        show_grid(self)

                    if event.key in [pygame.K_1, pygame.K_i]:
                        change_mode(self)

                    if event.key == pygame.K_m:
                        change_mode(self, "modify")

                    if event.key == pygame.K_F2:
                        change_mode(self, "select")

                    mods = pygame.key.get_mods()
                    if event.key == pygame.K_c and (mods & pygame.KMOD_CTRL):
                        self.copy_selection()
                    elif event.key in (pygame.K_RIGHTBRACKET, pygame.K_PAGEUP) and getattr(self, "selection", None):
                        if self.convert_selection("fore"):
                            self.skip = True
                    elif event.key in (pygame.K_LEFTBRACKET, pygame.K_PAGEDOWN) and getattr(self, "selection", None):
                        if self.convert_selection("back"):
                            self.skip = True
                    elif event.key == pygame.K_x and (mods & pygame.KMOD_CTRL):
                        if self.cut_selection():
                            self.skip = True
                    elif event.key == pygame.K_v and (mods & pygame.KMOD_CTRL):
                        if getattr(self, "clipboard", None):
                            if getattr(self, "TOOL", "insert") != "select":
                                change_mode(self, "select")
                            if self.begin_paste():
                                self.skip = True

                    if event.key == pygame.K_k:
                        entity_stats(self)

                    if event.key == pygame.K_v and not (mods & pygame.KMOD_CTRL):
                        # MAP PREVIEW: where the level selector's picture of this level is centred
                        preview_tools.edit_preview(self)
                        self.skip = True

                    if event.key in [pygame.K_2, pygame.K_p]:
                        perspective(self)

                    shortcut_categories = {
                        pygame.K_4: editor_palette.BLOCKS,
                        pygame.K_5: editor_palette.ENTITIES,
                        pygame.K_6: editor_palette.DECO,
                        pygame.K_7: editor_palette.WATER,
                        pygame.K_8: editor_palette.PLATFORMS,
                        pygame.K_9: editor_palette.DOORS,
                        pygame.K_0: editor_palette.SPAWNERS,
                        pygame.K_t: editor_palette.TRAPS,
                    }
                    if event.key in shortcut_categories:
                        category_to(self, shortcut_categories[event.key])
                        
                    if event.key == pygame.K_MINUS:
                        zoom_in(self)
                    
                    if event.key == pygame.K_EQUALS:
                        zoom_out(self)

                    if event.key == pygame.K_h:
                        how_to(self)

                    if event.key == pygame.K_s and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                        save(self)

                    if event.key == pygame.K_z and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                        if self.undo_edit():
                            self.skip = True
                    elif event.key == pygame.K_y and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                        if self.redo_edit():
                            self.skip = True
                    elif event.key == pygame.K_LEFT and self.TOOL == "select":
                        self.nudge_selection(-64, 0)
                    elif event.key == pygame.K_RIGHT and self.TOOL == "select":
                        self.nudge_selection(64, 0)
                    elif event.key == pygame.K_UP and self.TOOL == "select":
                        self.nudge_selection(0, -64)
                    elif event.key == pygame.K_DOWN and self.TOOL == "select":
                        self.nudge_selection(0, 64)
                    
                    if event.key == pygame.K_ESCAPE:
                        back_(self)

                    menu.handle_key(event.key)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    menu.handle_mouse(event)

                elif event.type == pygame.MOUSEWHEEL:
                    if event.y > 0:
                        zoom_in(self)
                    elif event.y < 0:
                        zoom_out(self)

                if not self.skip:
                    self.grid_settings_manager(event, events)

            tool = getattr(self, "TOOL", "insert" if self.INSERT else "delete")
            if tool != "select" and getattr(self, "pasting", False):
                self.cancel_paste()
            if tool != "select" and getattr(self, "move_preview", None) is not None:
                self.cancel_move()
            label, body, glow = {
                "insert": ("Insert Mode", (0, 90, 0), (0, 110, 0, 100)),
                "delete": ("Delete Mode", (90, 0, 0), (110, 0, 0, 100)),
                "modify": ("Modify Mode", (96, 74, 0), (140, 110, 0, 100)),
                "select": ("Select / Drag", (55, 70, 105), (80, 110, 160, 100)),
            }[tool]
            menu.buttons[1].text = label
            menu.buttons[1].color = body
            menu.buttons[1].glow_color = glow

            if self.EDIT_GRID == editor_palette.BLOCKS:
                menu.buttons[10].text = ("Fore" if self.perspective == "fore" else "Back") + "ground"
                menu.buttons[10].alpha = 255 if self.perspective == "fore" else 190
                
            self.skip = False

            self.size_num = max(0, self.size_num)
            self.type_num = max(0, self.type_num)
            self.block_num = max(0, self.block_num)

            if self.size_num > len(self.block_sizes) - 1:
                self.size_num = 0

            if self.type_num > len(self.block_types) - 1:
                self.type_num = 0

            if self.block_num > len(self.block_types[self.type_num]) - 1:
                self.type_num += 1
                self.block_num = 0

            if self.type_num > len(self.block_types) - 1:
                self.type_num = 0

            # Grid block settings
            self.type = self.block_types[self.type_num][self.block_num]

            if len(self.block_sizes):
                self.size = self.block_sizes[self.size_num]

            if self.EDIT_GRID == editor_palette.BLOCKS:
                if self.type not in ['sand', 'mud', 'ice', 'brick_small', 'stone_small', 'grass_small']:
                    self.size = "big"

            if self.EDIT_GRID == editor_palette.BLOCKS:
                menu.buttons[13].text = "Biome " + editor_palette.block_biome_split(
                    self.block_types[self.type_num][self.block_num])[1]

            if self.EDIT_GRID in editor_palette.COLOUR_CATEGORIES:
                menu.buttons[2].text = "Colour"
            elif self.EDIT_GRID in editor_palette.BIOME_CATEGORIES:
                menu.buttons[2].text = "Biome"
            elif self.EDIT_GRID == editor_palette.DECO:
                menu.buttons[2].text = "Palette"
            else:
                menu.buttons[2].text = "Size"

            self.offset_x = max(self.minx, min(self.offset_x, self.maxx - (Settings.WIDTH / self.zoom)))
            self.offset_y = max(self.miny, min(self.offset_y, self.maxy - (Settings.HEIGHT / self.zoom)))
            
            # --------------------------------------------------------------------------------------------------------------
            # DRAWING THE SCREEN
            # --------------------------------------------------------------------------------------------------------------
            self.window.fill((200, 200, 200))

            # PARALLAX BACKGROUND
            self.bg_particles = parallax_bg(
                self.window, 
                Settings.WIDTH, Settings.HEIGHT, 
                self.bg_particles, self.master_clock,
                threshold=20, height=0,
                parallax_color=Settings.PARALLAX, bg_color=Settings.BG_COLOR
            )
            
            # Grid Settings
            if self.show_grid:
                for grid_info in self.grid:
                    grid_rect = grid_info[0]
                    rect = pygame.Rect(
                                    int(grid_info[0].x - self.offset_x) * self.zoom,
                                    int(grid_info[0].y - self.offset_y) * self.zoom,
                                    int(grid_info[0].width) * self.zoom,
                                    int(grid_info[0].height) * self.zoom
                                )
                    if grid_info[1] == self.RED:
                        """
                        if not self.hide(rect, "rect"):
                            pygame.draw.rect(self.window, color, (
                                int(rect.x - self.offset_x) * self.zoom, int(rect.y - self.offset_y) * self.zoom,
                                int(rect.width * self.zoom), int(rect.height * self.zoom)), width=3)
                        """
                        pass
                    
                    elif grid_info[1] == self.BLUE:
                        pygame.draw.rect(self.window, grid_info[1], rect, width=3)
                    
                    else:
                        if not mode == "all":
                            if mode in grid_info[2]:
                                if not hide(self, grid_rect, "rect"):
                                    if "entities" in grid_info[2] and layer_tools.tag_visible(self, "entities"):
                                        pygame.draw.rect(self.window, grid_info[1], rect, width=1)
                        else:
                            if not hide(self, grid_rect, "rect"):
                                if "water" in grid_info[2] and layer_tools.tag_visible(self, "water"):
                                    pygame.draw.rect(self.window, (0, 0, 0), rect, width=5)
                                
                                if "block_back" in grid_info[2] and layer_tools.tag_visible(self, "block_back"):
                                    pygame.draw.rect(self.window, (250, 250, 250), rect, width=4)

                                if "treasure" in grid_info[2] and layer_tools.tag_visible(self, "treasure"):
                                    pygame.draw.rect(self.window, (0, 200, 200), rect, width=3)

                                if "platforms" in grid_info[2] and layer_tools.tag_visible(self, "platforms"):
                                    # width=3 because nothing can be in the same grid as this
                                    pygame.draw.rect(self.window, (100, 100, 0), rect, width=3)
                                
                                if "deco" in grid_info[2] and layer_tools.tag_visible(self, "deco"):
                                    pygame.draw.rect(self.window, (0, 200, 0), rect, width=3)

                                if "trap" in grid_info[2] and layer_tools.tag_visible(self, "trap"):
                                    pygame.draw.rect(self.window, (240, 130, 0), rect, width=3)

                                if "entities" in grid_info[2] and layer_tools.tag_visible(self, "entities"):
                                    pygame.draw.rect(self.window, (200, 0, 0), rect, width=2)

                                # pygame.draw.rect(self.window, grid_info[1], rect, width=3)

            visible = layer_tools.visible_objects(self)       # None = nothing hidden
            if visible is None:
                draw(self, type_="sub")
            elif visible:                                     # (an empty list would make draw() show everything)
                draw(self, type_="sub", objects_to_draw=visible)

            # Placed spawners are invisible in gameplay, so the editor
            # draws its own overlay for them on top of the world.
            if not layer_tools.is_hidden(self, editor_palette.SPAWNERS):
                spawner_tools.draw_spawn_points(self)
            if not layer_tools.is_hidden(self, editor_palette.START):
                start_tools.draw_start_points(self)
            preview_tools.draw_preview_point(self)

            pygame.draw.rect(self.window, (50, 20, 50), display_rect)
            info_text = ""                                   # filled in by the category branches below

            if self.EDIT_GRID == editor_palette.BLOCKS:
                self.window.blit(get_block(self.type, self.size),
                                    (display_rect.centerx - 32, display_rect.centery - 32))

            elif self.EDIT_GRID == editor_palette.ENTITIES:
                sprites = cache_assets((self.type, self.size, 'idle_right'))
                self.sprite_index = (self.animation_count //
                                        self.ANIMATION_DELAY) % len(sprites)
                self.sprite = sprites[self.sprite_index]
                self.animation_count += 1

                self.window.blit(self.sprite, (display_rect.centerx - 96, display_rect.centery - 96))

            elif self.EDIT_GRID == editor_palette.TREASURE and self.type == "charm":
                # the co-op Charm Crystal has no coin sprite: draw its orb (objects.draw_pickup)
                from ..objects.objects import draw_pickup
                draw_pickup(self.window, "charm", display_rect.center, 64, self.animation_count / 20.0)
                self.animation_count += 1

            elif self.EDIT_GRID == editor_palette.TREASURE:
                sprites = Assets.GEM_SPRITES[self.type]
                self.sprite_index = (self.animation_count //
                                        3) % len(sprites)
                self.sprite = sprites[self.sprite_index]
                self.animation_count += 1

                self.window.blit(pygame.transform.scale(self.sprite, (50, 50)),
                                    (display_rect.centerx - 25, display_rect.centery - 25))

            elif self.EDIT_GRID == editor_palette.DECO:
                selected = self.block_types[self.type_num][self.block_num]
                palette = str(getattr(self, "size", "1"))
                selected_name = selected if selected == "tree" or palette == "1" else f"{selected}_{palette}"
                if selected == 'tree':
                    from ..scripts.cache import get_tree_sprites
                    sprites = get_tree_sprites(palette)['idle_left']
                    self.sprite_index = (self.animation_count //
                                            3) % len(sprites)
                    self.sprite = sprites[self.sprite_index]
                    self.animation_count += 1

                    self.window.blit(pygame.transform.scale(self.sprite, (120, 120)),
                                        (display_rect.centerx - 60, display_rect.centery - 60))
                    ui_theme.text_centered(
                        self.window, f"tree / palette {palette}",
                        (display_rect.centerx, display_rect.bottom + 8),
                        12, ui_theme.MUTED, True
                    )
                else:
                    sprites = get_deco_sprites(palette)[selected]

                    self.window.blit(pygame.transform.scale(sprites, (120, 120)),
                                        (display_rect.centerx - 60, display_rect.centery - 60))
                    ui_theme.text_centered(
                        self.window, f"{selected} / palette {palette}",
                        (display_rect.centerx, display_rect.bottom + 8),
                        12, ui_theme.MUTED, True
                    )

            elif self.EDIT_GRID == editor_palette.TRAPS:
                sheets = Assets.TRAPS.get(self.type, {})
                frames = sheets.get("on") or next(iter(sheets.values()), [])
                if self.type == "homing":
                    from ..objects import arrow_trap
                    frames = [arrow_trap.icon(96)]
                if frames:
                    self.sprite_index = (self.animation_count // 3) % len(frames)
                    self.sprite = frames[self.sprite_index]
                    self.animation_count += 1
                    fit = min(1.0, 100 / self.sprite.get_height())
                    preview = pygame.transform.scale(
                        self.sprite, (int(self.sprite.get_width() * fit), int(self.sprite.get_height() * fit)))
                    self.window.blit(preview, (display_rect.centerx - preview.get_width() // 2,
                                               display_rect.centery - preview.get_height() // 2))
                ui_theme.text_centered(
                    self.window, f"{self.type}",
                    (display_rect.centerx, display_rect.bottom + 8),
                    12, ui_theme.MUTED, True
                )

            elif self.EDIT_GRID == editor_palette.WATER:
                surf.fill(self.color_zones.get(self.type, (50, 200, 50)))
                surf.set_alpha(120)
                self.window.blit(surf, (display_rect.centerx - 32, display_rect.centery - 32))

            elif self.EDIT_GRID == editor_palette.SPAWNERS:
                spawner_tools.draw_spawner_preview(self, display_rect)

            elif self.EDIT_GRID == editor_palette.START:
                start_tools.draw_start_preview(self, display_rect)

            elif self.EDIT_GRID == editor_palette.PLATFORMS:
                scaled_rect = pygame.Rect(display_rect.centerx - 45, display_rect.centery - 10, 90, 20)
                pygame.draw.rect(self.window, (50, 200, 50), scaled_rect)
                # Add support lines to platforms
                for i in range(3):
                    pygame.draw.line(self.window, (100, 80, 60),
                        (
                            int(scaled_rect.x + i * (scaled_rect.width // 2)),
                            int(scaled_rect.y + scaled_rect.height)
                        ),
                        (
                            int(scaled_rect.x + i * (scaled_rect.width // 2)),
                            int(scaled_rect.y + scaled_rect.height + 10)
                        ),
                        2
                    )

            elif self.EDIT_GRID == editor_palette.DOORS:
                self.sprite = get_door(door_name(self.type, self.size))
                self.window.blit(pygame.transform.scale(self.sprite, (64, 40)),
                                    (display_rect.centerx - 32, display_rect.centery - 20))
                info_text = f"{self.type} / biome {self.size}"

            # The Category button used to give no clue which category was
            # live -- you had to guess from the swatch.
            # Both lines sit on strips INSIDE the swatch box: the old spots above and below it were under the
            # Insert Mode and Category buttons.
            category_name = editor_palette.CATEGORY_NAMES.get(self.EDIT_GRID, "?")
            if self.EDIT_GRID in (editor_palette.ENTITIES, editor_palette.SPAWNERS):
                info_text = f"{self.type} / {self.size}"
            strip = max(18, int(display_rect.height * 0.15))
            top_strip = pygame.Rect(display_rect.left, display_rect.top, display_rect.width, strip)
            ui_theme.panel(self.window, top_strip, (18, 8, 22, 215), None, 0, 0)
            ui_theme.text_centered(self.window, category_name, top_strip.center, 14, ui_theme.CREAM, True)
            if info_text:
                bottom_strip = pygame.Rect(display_rect.left, display_rect.bottom - strip, display_rect.width, strip)
                ui_theme.panel(self.window, bottom_strip, (18, 8, 22, 215), None, 0, 0)
                ui_theme.text_centered(self.window, info_text, bottom_strip.center, 12, ui_theme.MUTED, True)
          
            if self.thing:
                self.thing.update_sprite()
                self.thing.draw(game=self)

            menu.update(mouse_pos)
            menu.draw()
            draw_selection_overlay(self)
            layer_tools.draw(self)
            place_rules.draw_chip(self)

            if self.DEBUGGING_MODE:
                self.get_fps()
            # fps_surface = self.font.render(f"{self.item_size}", True, (255, 255, 255))
            # elf.window.blit(fps_surface, (10, 10))
            
            details_surface = text_font.render(
                f"X: {self.selectedx} | Y: {self.selectedy}",
                True,
                (255, 255, 255)
            )
            self.window.blit(details_surface, (menu.buttons[7].rect.right + sw * 0.005, sh * 0.02))
            
            platform_details_surface = text_font.render(
                f"{[(o.x, o.y) for i, o in enumerate(self.platform)]}",
                True,
                (255, 255, 255)
            )
            self.window.blit(platform_details_surface, (menu.buttons[7].rect.right + sw * 0.005, sh * 0.06))
            
            #pygame.draw.rect(self.window, (255, 5, 255), self.size_rect)
            
            pygame.display.flip()

            self.clock.tick(self.FPS)
