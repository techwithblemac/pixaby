import copy
import json
import os
import time
import pygame

from ...settings import Settings
from ...entities.entities import Enemy, Spawn_Point
from ...scripts.asset_funcs import get_block
from ...objects.objects import Tree, Block, Deco, WaterZone, Platform, Treasure, Door, Trap, make_treasure
from ...ui.ui_popup import run_field_popup
from . import editor_palette
from . import spawner_tools
from . import start_tools
from . import door_tools
from . import object_edit
from . import layer_tools
from . import clipboard_store
from . import place_rules
from ...data.palletes.doors import door_name
from ...data.traps import kind_for
from ...objects import arrow_trap

class Level_Editor_Tools:
    HISTORY_LIMIT = 40

    def _checkpoint(self):
        """Capture the JSON source of truth before a destructive edit."""
        if not hasattr(self, "_undo_stack"):
            self._undo_stack, self._redo_stack = [], []
        self._undo_stack.append(copy.deepcopy(self.world))
        del self._undo_stack[:-self.HISTORY_LIMIT]
        self._redo_stack.clear()

    def _reload_editor_world(self):
        from ..main.update_funcs import update_game_logic
        """Rebuild every live object after an undo/redo."""
        restored_world = copy.deepcopy(self.world)
        self.create_new_world()
        self.world = restored_world
        try:
            from ...data import biomes
            biomes.analyse(self)
        except Exception:
            self.biome_map = None
        
        self.env_ready = False
        self.create_world()
        self._draw_list_dirty = False
        update_game_logic(self)

    # ------------------------------------------------------------------
    # Selection helpers
    #
    # The selection holds references to dicts inside self.world. Every
    # reload deep-copies the world, so after one the selection is rebuilt
    # from world *indices* (order is preserved by the deep copy) instead of
    # matching on (type, x, y, name), which broke as soon as two objects
    # shared a key.
    # ------------------------------------------------------------------
    def _selection_indices(self):
        selected = getattr(self, "selection", [])
        return [i for i, d in enumerate(self.world)
                if any(d is s for s in selected)]

    def _reselect(self, indices):
        self.selection = [self.world[i] for i in indices if i < len(self.world)]

    def _cell_at(self, pos):
        """The grid cell under a screen position, or None."""
        for grid_info in self.grid:
            rect = pygame.Rect(
                int((grid_info[0].x - self.offset_x) * self.zoom),
                int((grid_info[0].y - self.offset_y) * self.zoom),
                int(grid_info[0].width * self.zoom),
                int(grid_info[0].height * self.zoom),
            )
            if rect.collidepoint(pos):
                return grid_info
        return None

    def selection_hit(self, pos):
        """True when a screen position lies on a currently selected object."""
        world_pos = (pos[0] / self.zoom + self.offset_x,
                     pos[1] / self.zoom + self.offset_y)
        for data in getattr(self, "selection", []):
            rect = pygame.Rect(data.get("x", 0), data.get("y", 0),
                               data.get("width", 64), data.get("height", 64))
            if rect.collidepoint(world_pos):
                return True
        return False

    def select_object(self, grid_info):
        """Select what is in this cell. An empty cell still becomes the
        active cell, so it can be used as a paste target."""
        self.selectedx, self.selectedy = grid_info[0].topleft
        data = object_edit.pick(self, grid_info)
        if data is None:
            self.selection = []
            return False
        self.selection = [data]
        self.selection_origin = (data.get("x", 0), data.get("y", 0))
        return True

    def copy_selection(self):
        """Copy the selection. Nothing selected keeps the previous clipboard. The copy is also remembered outside this
        level (clipboard_store), so it can be pasted after opening another level."""
        selected = copy.deepcopy(getattr(self, "selection", []))
        if selected:
            self.clipboard = selected
            clipboard_store.save(selected)
        return bool(selected)

    def cut_selection(self):
        """Ctrl+X: copy the selection (it can be pasted into any level) and remove it from this one."""
        if not self.copy_selection():
            return False
        indices = set(self._selection_indices())
        if not indices:
            return False
        self._checkpoint()
        self.world[:] = [d for i, d in enumerate(self.world) if i not in indices]
        self.selection = []
        self._reload_editor_world()
        self.changes.update({"entities", "deco", "zones"})
        self._draw_list_dirty = True
        place_rules.toast(self, f"Cut {len(self.clipboard)}")
        return True

    def convert_selection(self, perspective):
        """[ / ] (or PageDown / PageUp): turn the selected blocks into BACKGROUND ("back") or FOREGROUND ("fore").
        The same OVER / BEHIND rule as a move decides what happens when the new layer cannot sit beside something
        already there (a foreground block cannot share a cell with an enemy, a door, a trap...)."""
        world = self.world
        chosen = self._selection_indices()
        blocks = [i for i in chosen if world[i].get("type") == "block"
                  and world[i].get("perspective", "fore") != perspective]
        name = "foreground" if perspective == "fore" else "background"
        if not blocks:
            place_rules.toast(self, f"No selected blocks to make {name}")
            return False
        how = place_rules.mode(self)
        remove, stay = place_rules.resolve_move(self, world, blocks, 0, 0, how, {"perspective": perspective})
        change = [i for i in blocks if i not in stay]
        if not change:
            place_rules.toast(self, f"Nothing changed (BEHIND: everything was blocked)")
            return False
        self._checkpoint()
        for i in change:
            world[i]["perspective"] = perspective
        keep = [i for i in range(len(world)) if i not in remove]
        new_index = {old: new for new, old in enumerate(keep)}
        world[:] = [world[i] for i in keep]
        self._reload_editor_world()
        self.changes.update({"block_fore", "block_back", "entities", "deco", "zones"})
        self._reselect([new_index[i] for i in chosen if i in new_index])
        self._draw_list_dirty = True
        place_rules.toast(self, place_rules.summary(how, len(remove), len(stay), f"{len(change)} to {name}"))
        return True

    def select_rect(self, rect):
        selected = []
        for data in self.world:
            if not isinstance(data, dict) or data.get("type") not in object_edit.EDITABLE:
                continue
            if not layer_tools.type_visible(self, data.get("type")):     # hidden layers cannot be selected
                continue
            obj_rect = pygame.Rect(data.get("x", 0), data.get("y", 0),
                                   data.get("width", 64), data.get("height", 64))
            if rect.colliderect(obj_rect):
                selected.append(data)
        self.selection = selected
        if selected:
            self.selection_origin = (min(d.get("x", 0) for d in selected),
                                     min(d.get("y", 0) for d in selected))
            self.selectedx, self.selectedy = self.selection_origin
        return bool(selected)

    def nudge_selection(self, dx, dy):
        """Arrow keys move a *ghost*, not the objects. SPACE / ENTER places
        it, END / ESC cancels; nothing in the level changes until then."""
        if not getattr(self, "selection", None):
            return False
        mx, my = getattr(self, "move_preview", None) or (0, 0)
        self.move_preview = (mx + dx, my + dy)
        return True

    def commit_move(self):
        mp = getattr(self, "move_preview", None)
        self.move_preview = None
        if mp and (mp[0] or mp[1]):
            return self.drag_selection(mp[0], mp[1])
        return False

    def cancel_move(self):
        was = getattr(self, "move_preview", None) is not None
        self.move_preview = None
        return was

    def drag_selection(self, dx, dy, checkpoint=True):
        if not getattr(self, "selection", None):
            return False
        indices = self._selection_indices()
        if not indices:
            return False
        how = place_rules.mode(self)
        remove, stay = place_rules.resolve_move(self, self.world, indices, dx, dy, how)
        if len(stay) == len(indices):
            place_rules.toast(self, "Nothing moved (BEHIND: everything was blocked)")
            return False
        if checkpoint:
            self._checkpoint()
        for i in indices:
            if i not in stay:
                self.world[i]["x"] = self.world[i].get("x", 0) + dx
                self.world[i]["y"] = self.world[i].get("y", 0) + dy
        # OVER removes what the moved objects land on; indices shift down, so keep a map for the reselect.
        keep = [i for i in range(len(self.world)) if i not in remove]
        new_index = {old: new for new, old in enumerate(keep)}
        self.world[:] = [self.world[i] for i in keep]
        self._reload_editor_world()
        self.changes.update({"entities", "deco", "zones"})
        self._reselect([new_index[i] for i in indices])
        self.selection_origin = self.clipboard_top_left_of(self.selection)
        self.selectedx, self.selectedy = self.selection_origin
        place_rules.toast(self, place_rules.summary(how, len(remove), len(stay), "Moved"))
        return True

    # ------------------------------------------------------------------
    # Paste
    #
    # Ctrl+V only starts a *preview*: the clipboard is drawn as a ghost
    # with its top-left corner on the selected cell, and nothing in the
    # level is touched. Click a cell (or use the arrows) to move it, SPACE
    # to place it, ESC to cancel.
    # ------------------------------------------------------------------
    def clipboard_top_left(self):
        clip = getattr(self, "clipboard", None) or []
        if not clip:
            return (0, 0)
        return (min(i.get("x", 0) for i in clip), min(i.get("y", 0) for i in clip))

    def paste_offset(self):
        """How far every clipboard item moves so its top-left lands on the anchor."""
        ax, ay = getattr(self, "paste_anchor", (self.selectedx, self.selectedy))
        cx, cy = self.clipboard_top_left()
        return ax - cx, ay - cy

    def begin_paste(self):
        if not getattr(self, "clipboard", None):
            return False
        self.paste_anchor = (self.selectedx, self.selectedy)
        self.pasting = True
        return True

    # Kept so existing callers of the old one-shot paste still work.
    def paste_selection(self):
        return self.begin_paste()

    def cancel_paste(self):
        self.pasting = False

    # ------------------------------------------------------------------
    # Drag preview
    #
    # Dragging a selection works like paste: the objects stay where they
    # are and a ghost follows the mouse (snapped to the 64px grid). The
    # move is only applied when the button is released; END cancels it.
    # ------------------------------------------------------------------
    def drag_ghost_offset(self):
        if not getattr(self, "dragging_selection", False):
            return (0, 0)
        px, py = getattr(self, "_drag_total", (0, 0))
        step = max(1.0, 64 * self.zoom)
        return (int(round(px / step)) * 64, int(round(py / step)) * 64)

    def cancel_drag(self):
        """Throw the drag preview away; nothing in the level changed."""
        was = getattr(self, "dragging_selection", False)
        self.dragging_selection = False
        self._drag_total = (0, 0)
        self._drag_pixels = [0, 0]
        if was:
            self._drag_cancelled = True
        return was

    def move_paste_anchor(self, dx, dy):
        ax, ay = getattr(self, "paste_anchor", (self.selectedx, self.selectedy))
        self.paste_anchor = (ax + dx, ay + dy)
        self.selectedx, self.selectedy = self.paste_anchor

    def set_paste_anchor_at(self, pos):
        grid_info = self._cell_at(pos)
        if grid_info is None:
            return False
        self.paste_anchor = tuple(grid_info[0].topleft)
        self.selectedx, self.selectedy = self.paste_anchor
        return True

    def commit_paste(self):
        """Place the previewed clipboard. Only now does the world change."""
        if not getattr(self, "pasting", False) or not getattr(self, "clipboard", None):
            self.pasting = False
            return False
        dx, dy = self.paste_offset()
        items = copy.deepcopy(self.clipboard)
        for item in items:
            item["x"] = item.get("x", 0) + dx
            item["y"] = item.get("y", 0) + dy

        # OVER: what the paste conflicts with is replaced. BEHIND: pasted objects that conflict are skipped.
        # (place_rules uses the editor's own placement rules, so nothing is left for the loader to silently drop.)
        how = place_rules.mode(self)
        remove, skip = place_rules.resolve_paste(self, self.world, items, how)
        items = [item for n, item in enumerate(items) if n not in skip]
        if not items:
            self.pasting = False
            place_rules.toast(self, "Nothing pasted (BEHIND: everything was blocked)")
            return False
        self._checkpoint()
        self.world[:] = [d for i, d in enumerate(self.world) if i not in remove]
        first_new = len(self.world)
        self.world.extend(items)
        place_rules.toast(self, place_rules.summary(how, len(remove), len(skip), f"Pasted {len(items)}"))
        self._reload_editor_world()
        self.changes.update({"entities", "deco", "zones"})
        self._reselect(range(first_new, first_new + len(items)))
        self.selection_origin = self.clipboard_top_left_of(self.selection)
        self.pasting = False
        self._draw_list_dirty = True
        return True

    @staticmethod
    def clipboard_top_left_of(items):
        if not items:
            return (0, 0)
        return (min(i.get("x", 0) for i in items), min(i.get("y", 0) for i in items))

    def undo_edit(self):
        if not getattr(self, "_undo_stack", None):
            return False
        self._redo_stack.append(copy.deepcopy(self.world))
        self.world = self._undo_stack.pop()
        self.selection = []
        self._reload_editor_world()
        self.changes.add("entities")
        return True

    def redo_edit(self):
        if not getattr(self, "_redo_stack", None):
            return False
        self._undo_stack.append(copy.deepcopy(self.world))
        self.world = self._redo_stack.pop()
        self.selection = []
        self._reload_editor_world()
        self.changes.add("entities")
        return True

    def open_field_popup(self, title, fields):
        """
        Labeled, type-restricted replacement for enter_text() when placing
        objects in the level editor. Shows one row per field (int/float/
        bool/choice/text) in a floating panel instead of a single raw
        "a;b;c" string you have to remember the order of.

        Returns a {key: value} dict. Escape / Cancel falls back to each
        field's default, matching enter_text()'s old "revert on Escape"
        behavior, so callers don't need a separate cancel path.
        """
        if not hasattr(self, '_popup_title_font'):
            self._popup_title_font = pygame.font.SysFont("consolas", 26, bold=True)
            self._popup_label_font = pygame.font.SysFont("consolas", 18)
            self._popup_value_font = pygame.font.SysFont("consolas", 20, bold=True)

        result = run_field_popup(
            self.window, self.clock,
            self._popup_title_font, self._popup_label_font, self._popup_value_font,
            title, fields
        )

        if result is None:
            result = {field["key"]: field.get("default") for field in fields}

        return result

    def grid_settings_manager(self, event, events):
        if self.control_type == "touch":
            self.clicked = True

        # While a paste preview is up, the mouse only moves the preview.
        if getattr(self, "pasting", False):
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.clicked = True
                self.set_paste_anchor_at(event.pos)
            elif event.type == pygame.MOUSEMOTION and self.clicked:
                self.set_paste_anchor_at(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.clicked = False
            return

        # Inserting or Deleting Items from the Grid
        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 3:
                self.pressed = False
            if event.button == 1:
                self.clicked = False
                if self.dragging_selection:
                    gx, gy = self.drag_ghost_offset()
                    if gx or gy:
                        self.drag_selection(gx, gy)
                self.dragging_selection = False
                self._drag_total = (0, 0)
                self._drag_pixels = [0, 0]
                if getattr(self, "TOOL", "insert") == "select" and getattr(self, "selection_box", None):
                    self.selection_box[1] = event.pos
                    a, b = self.selection_box
                    world_rect = pygame.Rect(
                        int(min(a[0], b[0]) / self.zoom + self.offset_x),
                        int(min(a[1], b[1]) / self.zoom + self.offset_y),
                        int(abs(b[0] - a[0]) / self.zoom),
                        int(abs(b[1] - a[1]) / self.zoom),
                    )
                    if world_rect.width < 8 and world_rect.height < 8:
                        for grid_info in self.grid:
                            rect = pygame.Rect(
                                int((grid_info[0].x - self.offset_x) * self.zoom),
                                int((grid_info[0].y - self.offset_y) * self.zoom),
                                int(grid_info[0].width * self.zoom),
                                int(grid_info[0].height * self.zoom),
                            )
                            if rect.collidepoint(event.pos):
                                self.select_object(grid_info)
                                break
                    else:
                        self.select_rect(world_rect)
                    self.selection_box = None

        if event.type == pygame.MOUSEMOTION:
            if getattr(self, "TOOL", "insert") == "select" and self.clicked:
                if getattr(self, "selection_box", None):
                    self.selection_box[1] = event.pos
                    return
                if not self.dragging_selection:
                    return
                # Only the ghost moves while the button is held.
                tx, ty = getattr(self, "_drag_total", (0, 0))
                self._drag_total = (tx + event.rel[0], ty + event.rel[1])
                return
            if self.EDIT_WORLD and self.clicked:
                new_offset_x = self.offset_x - event.rel[0]
                new_offset_y = self.offset_y - event.rel[1]

                self.offset_x = max(self.minx, min(new_offset_x, self.maxx - (Settings.WIDTH / self.zoom)))
                self.offset_y = max(self.miny, min(new_offset_y, self.maxy - (Settings.HEIGHT / self.zoom)))
            
            if self.pressed:
                self.handle_grid_click(event)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3:
                self.pressed = True
                return

            if event.button == 1:
                self.clicked = True
                self._drag_pixels = [0, 0]
                self._drag_total = (0, 0)
                self._drag_cancelled = False
                self.move_preview = None
                if getattr(self, "TOOL", "insert") == "select":
                    if self.selection and self.selection_hit(event.pos):
                        # Pressed on the selection: drag it (ghost preview).
                        self.dragging_selection = True
                        self._drag_cp = False
                    else:
                        # Pressed elsewhere: draw a new selection box.
                        self.selection_box = [event.pos, event.pos]
                    return
                if self.EDIT_WORLD:
                    self.edit_grid_settings = editor_palette.build_edit_grid_settings()

                self.handle_grid_click(event)

    def handle_grid_click(self, event):
        self.mode = editor_palette.mode_for(self.EDIT_GRID, self.perspective)
        
        for index, grid_info in enumerate(self.grid):
            grid_rect = pygame.Rect(int(grid_info[0].x - self.offset_x) * self.zoom,
                                    int(grid_info[0].y - self.offset_y) * self.zoom,
                                    int(grid_info[0].width) * self.zoom,
                                    int(grid_info[0].height) * self.zoom)
            
            if grid_rect.collidepoint(event.pos):
                addable = grid_info[2].isdisjoint(self.world_rules[self.mode])
                tool = getattr(self, "TOOL", "insert" if self.INSERT else "delete")

                if tool == "select":
                    self.select_object(grid_info)
                    self._draw_list_dirty = True
                elif tool == "modify":
                    # Modify acts on the first click: there is nothing
                    # destructive to confirm, and the popup is its own
                    # confirmation step.
                    self.modify_object(index, grid_info)

                elif tool == "insert" and (self.confirm == grid_info[0]  or self.pressed) and addable:
                        self.insert_object(index, grid_info)

                elif tool == "delete" and (self.confirm == grid_info[0] or self.pressed):
                    self.delete_object(index, grid_info)
                    
                else:
                    self.confirm = grid_info[0]
                    if (
                            addable or tool != "insert"
                    ):
                        if self.prev:
                            self.grid[self.prev[0]][1] = self.prev[1]
                        self.prev = (index, grid_info[1], addable)
                        grid_info[1] = self.BLUE

                        self.selectedx, self.selectedy = grid_info[0].topleft

                        if self.EDIT_GRID == editor_palette.PLATFORMS:
                            if addable:
                                self.platform.append(grid_info[0])
                                self.platform = self.platform[-2:]

                                if len(self.platform) == 2:
                                    self.confirm = grid_info[0]
                                self._draw_list_dirty = True
                    
                break

    def insert_object(self, index, grid_info):
        self._checkpoint()
        grid_info[1] = self.BLACK
        # A mode can occupy a cell under a different tag than its own name
        # (spawn points share the "entities" tag with enemies), so the tag
        # is resolved rather than assumed to equal self.mode.
        grid_info[2].add(editor_palette.grid_tag_for(self.mode))

        change_tag = editor_palette.change_tag_for(self.EDIT_GRID, self.perspective)

        if self.EDIT_GRID == editor_palette.BLOCKS:
            self.add_block(grid_info)
            self.changes.add(change_tag)
        elif self.EDIT_GRID == editor_palette.ENTITIES:
            self.add_enemy(grid_info)
            self.changes.add(change_tag)
        elif self.EDIT_GRID == editor_palette.TREASURE:
            self.add_treasure(grid_info)
            self.changes.add(change_tag)
        elif self.EDIT_GRID == editor_palette.DECO:
            self.add_deco(grid_info)
            self.changes.add(change_tag)
        elif self.EDIT_GRID == editor_palette.WATER:
            self.add_water(grid_info)
            self.changes.add(change_tag)
        elif self.EDIT_GRID == editor_palette.SPAWNERS:
            self.add_spawn_point(grid_info)
            self.changes.add(change_tag)
        elif self.EDIT_GRID == editor_palette.START:
            self.add_start_point(grid_info)
            self.changes.add(change_tag)
        elif self.EDIT_GRID == editor_palette.DOORS:
            self.add_door(grid_info)
            self.changes.add(change_tag)
        elif self.EDIT_GRID == editor_palette.TRAPS:
            self.add_trap(grid_info)
            self.changes.add(change_tag)
        elif self.EDIT_GRID == editor_palette.PLATFORMS:
            if len(self.platform) == 2:
                self.add_platform(grid_info)
                
                self.changes.add(change_tag)

        self.prev = (index, grid_info[1])
        self._draw_list_dirty = True                                   
        self.confirm = None
        self.platform = []

    def delete_object(self, index, grid_info):
        self._checkpoint()
        self.prev = (index, grid_info[1])
        self._draw_list_dirty = True

        if self.EDIT_GRID == editor_palette.START:
            # Start points live inside the single "start" entry rather
            # than as world entries of their own, so the generic
            # world-scanning remove() can't reach them.
            if start_tools.remove_start_point(self, grid_info):
                self.changes.add("start")
            else:
                print("Nothing to remove here, or this is the last start point.")
            self.confirm = None
            return

        self.remove(grid_info)

        self.confirm = None
        if not grid_info[2]:
            grid_info[1] = self.RED
    
    def add_platform(self, grid_info):
        fields = [
            {"key": "width", "label": "Width", "type": "int", "default": 100, "min": 1, "max": 4000},
            {"key": "height", "label": "Height", "type": "int", "default": 20, "min": 1, "max": 4000},
            {"key": "dir_x", "label": "Direction X", "type": "choice",
             "options": [-1, 1], "default": -1 if self.platform[0].x > self.platform[1].x else 1},
            {"key": "dir_y", "label": "Direction Y", "type": "choice",
             "options": [-1, 1], "default": -1 if self.platform[0].y > self.platform[1].y else 1},
            {"key": "moving", "label": "Moving", "type": "bool", "default": True},
            {"key": "speed", "label": "Speed", "type": "int", "default": 100, "min": 1, "max": 2000},
        ]
        values = self.open_field_popup("Platform Settings", fields)

        width = values["width"]
        height = values["height"]
        direction = [values["dir_x"], values["dir_y"]]
        moving = values["moving"]
        speed = values["speed"]
        color = self.color_zones.get(self.type, (50, 200, 50))
        minx = min(self.platform[0].left, self.platform[1].left)
        maxx = max(self.platform[1].right, self.platform[0].right)

        miny = min(self.platform[0].top, self.platform[1].top)
        maxy = max(self.platform[1].bottom, self.platform[0].bottom)

        plat = Platform(grid_info[0].x, grid_info[0].y, width, height, moving, direction, speed, (minx,
                        maxx),(miny,
                        maxy), self)
        self.platforms.append(
            plat
        )
        """self.objects.append(
            plat
        )"""
        data = {
            "x": grid_info[0].x,
            "y": grid_info[0].y,
            "width": width,
            "height": height,
            "moving": moving,
            "direction": direction,
            "type": "moving_platform",
            "speed": speed,
            "dest_x": [minx, maxx],
            "dest_y": [miny, maxy],
            "min_x": minx,
            "max_x": maxx,
            "path": [[0, 0]],
            "color": list(color)
        }
        self.world.append(data)


    def add_water(self, grid_info):
        try:
            prev_flow, prev_rise = self.history['flow-rise'].split(';')
            prev_flow = int(prev_flow)
            prev_rise = prev_rise in ('1', 'True', 'true')
        except (ValueError, KeyError):
            prev_flow, prev_rise = 1, False

        fields = [
            {"key": "width", "label": "Width", "type": "int", "default": 64, "min": 1, "max": 4000},
            {"key": "height", "label": "Height", "type": "int", "default": 64, "min": 1, "max": 4000},
            {"key": "flow", "label": "Flow", "type": "int", "default": prev_flow, "min": -100, "max": 100},
            {"key": "rise", "label": "Rise", "type": "bool", "default": prev_rise},
        ]

        if not self.pressed:
            values = self.open_field_popup("Water Zone Settings", fields)
        else:
            values = {field["key"]: field["default"] for field in fields}

        width = values["width"]
        height = values["height"]
        flow = values["flow"]
        rise = values["rise"]

        self.item_size = f'{width};{height}'
        self.history['flow-rise'] = f'{flow};{rise}'
        color = self.color_zones.get(self.type, (50, 200, 50))

        self.zones.append(WaterZone(grid_info[0].x, grid_info[0].y, width, height, self.type, self,
                                    color, flow,
                                    rise))

        data = {
            "x": grid_info[0].x,
            "y": grid_info[0].y,
            "width": width,
            "height": height,
            "type": "water",
            "water_type": self.type,
            "color": list(color),
            "flow": flow,
            "rise": rise
        }
        self.world.append(data)

    def add_block(self, grid_info):
        image = get_block(self.type, self.size)

        fields = [
            {"key": "width", "label": "Width", "type": "int", "default": image.get_width(), "min": 1, "max": 4000},
            {"key": "height", "label": "Height", "type": "int", "default": image.get_height(), "min": 1, "max": 4000},
        ]

        if not self.pressed:
            values = self.open_field_popup("Block Settings", fields)
        else:
            values = {field["key"]: field["default"] for field in fields}

        width = values["width"]
        height = values["height"]
        
        if self.perspective == "back":
            self.bg_objects.append(Block(grid_info[0].x, grid_info[0].y, width, height, self.type, self.size, game=self, perspective=self.perspective))
        else:
            self.objects.append(Block(grid_info[0].x, grid_info[0].y, width, height, self.type, self.size, game=self, perspective=self.perspective))
        
        data = {
            "x": grid_info[0].x,
            "y": grid_info[0].y,
            "width": width,
            "height": height,
            "type": "block",
            "name": self.type,
            "size": self.size,
            "perspective": self.perspective
        }

        self.world.append(data)

    def add_enemy(self, grid_info):
        max_x = grid_info[0].x + 63
        max_y = grid_info[0].y + 63
        fields = [
            {"key": "x", "label": "X", "type": "int", "default": grid_info[0].x, "min": grid_info[0].x, "max": max_x},
            {"key": "y", "label": "Y", "type": "int", "default": grid_info[0].y, "min": grid_info[0].y, "max": max_y},
            {"key": "posted", "label": "Posted", "type": "bool", "default": False},
            {"key": "patroller", "label": "Patroller", "type": "bool", "default": False},
            {"key": "patrol_range_x", "label": "Patrol Range X", "type": "int", "default": 1000, "min": 64, "max": 2000},
            {"key": "patrol_range_y", "label": "Patrol Range Y", "type": "int", "default": 1000, "min": 64, "max": 2000},
        ]

        if not self.pressed:
            values = self.open_field_popup("Entity Settings", fields)
        else:
            values = {field["key"]: field["default"] for field in fields}

        x = values["x"]
        y = values["y"]
        posted = values["posted"]
        patroller = values["patroller"]
        patrol_range_x = values["patrol_range_x"]
        patrol_range_y = values["patrol_range_y"]

        enemy = Enemy(x, y, grid_info[0].width, grid_info[0].width, self.type, self.size,
                      self)
        enemy.update_sprite()
        
        enemy.posted = posted
        enemy.patroller = patroller
        enemy.patrol_range_x = patrol_range_x
        enemy.patrol_range_y = patrol_range_y

        data = {
            "x": x,
            "y": y,
            "width": enemy.rect.width,
            "height": enemy.rect.height,
            "type": "enemy",
            "name": self.type,
            "color": self.size,
            "posted": posted,
            "patroller": patroller,
            "patrol_range_x": patrol_range_x,
            "patrol_range_y": patrol_range_y
        }

        self.world.append(data)

        self.enemy_list.append(enemy)
        self._entities_dirty = True

    def add_door(self, grid_info):
        max_x = grid_info[0].x + 63
        max_y = grid_info[0].y + 63
        fields = [
            {"key": "x", "label": "X", "type": "int", "default": grid_info[0].x, "min": grid_info[0].x, "max": max_x},
            {"key": "y", "label": "Y", "type": "int", "default": grid_info[0].y, "min": grid_info[0].y, "max": max_y},
        ]

        # The Type button picks the kind (teleport / warp / exit) and the
        # Size ("Biome") button the colour variant: warp + 4 -> "warp_4".
        name = door_name(self.type, self.size)
        is_warp = self.type == "warp"

        if is_warp:
            fields.append({
                "key": "targets", "label": "Targets (x,y; x,y)", "type": "text",
                "default": self.history.get("door-targets", "0,-64"),
            })

        if not self.pressed:
            values = self.open_field_popup("Door Settings", fields)
        else:
            values = {field["key"]: field["default"] for field in fields}

        x = values["x"]
        y = values["y"]

        targets = []
        if is_warp:
            targets = door_tools.parse_targets(values["targets"])
            if targets:
                # Remember them so painting a row of doors doesn't mean
                # retyping the list for every cell.
                self.history["door-targets"] = door_tools.format_targets(targets)
            else:
                print("Warp door has no valid targets - it will fall back to the start points.")

        door = Door(x, y, name, self, targets)

        data = {
            "x": x,
            "y": y,
            "width": 64,
            "height": 64,
            "type": "door",
            "name": name,
        }
        if is_warp:
            data["targets"] = targets

        self.world.append(data)

        self.doors.append(door)

    def add_spawn_point(self, grid_info):
        """Place a continuous enemy spawner on the selected cell.

        The roster is authored as free text (``Archer:Red, TNT:Red``) and
        validated by spawner_tools before it ever reaches the JSON, so an
        unknown colour can't be saved into a level and crash the engine
        later.
        """
        default_roster = self.history.get(
            'spawner-roster', spawner_tools.format_roster([[self.type, self.size]])
        )
        default_interval = int(self.history.get('spawner-interval', 5))
        default_limit = int(self.history.get('spawner-limit', 5))

        fields = [
            {"key": "interval", "label": "Interval (sec)", "type": "int",
             "default": default_interval, "min": 1, "max": 600},
            {"key": "limit", "label": "Spawn Limit", "type": "int",
             "default": default_limit, "min": 1, "max": 999},
            {"key": "roster", "label": "Roster (Name:Colour)", "type": "text",
             "default": default_roster},
        ]

        if not self.pressed:
            values = self.open_field_popup("Spawner Settings", fields)
        else:
            values = {field["key"]: field["default"] for field in fields}

        interval = values["interval"]
        limit = values["limit"]
        entities = spawner_tools.parse_roster(
            values["roster"], fallback_name=self.type, fallback_color=self.size
        )

        # Remember the last roster so painting a row of spawners doesn't
        # mean retyping it for every single cell.
        self.history['spawner-roster'] = spawner_tools.format_roster(entities)
        self.history['spawner-interval'] = interval
        self.history['spawner-limit'] = limit

        point = Spawn_Point(
            grid_info[0].x, grid_info[0].y,
            grid_info[0].width, grid_info[0].height,
            interval, limit, entities, self
        )
        self.spawn_points.append(point)

        data = {
            "x": grid_info[0].x,
            "y": grid_info[0].y,
            "width": grid_info[0].width,
            "height": grid_info[0].height,
            "interval": interval,
            "limit": limit,
            "type": "spawn_point",
            "entities": entities
        }

        self.world.append(data)

    def add_start_point(self, grid_info):
        """Add the clicked cell to the level's player spawn pool."""
        promoted = start_tools.add_start_point(self, grid_info)
        if promoted:
            print("Start point promoted to primary (P1).")
        else:
            print(f"Start point added ({len(self.points)} total).")

    def modify_object(self, index, grid_info):
        """Reopen the settings popup for whatever already sits here."""
        self.prev = (index, grid_info[1])
        self.confirm = None

        if self.EDIT_GRID == editor_palette.START:
            # The start "object" is the pool itself; clicking a cell
            # promotes that spawn to primary.
            if start_tools.add_start_point(self, grid_info):
                self.changes.add("start")
                print("Start point promoted to primary (P1).")
            else:
                print("No start point on this cell.")
            return

        data = object_edit.pick(self, grid_info)
        if data is None:
            print("Nothing editable on this cell.")
            return

        from ...ui import entity_editor
        if data.get("type") == "enemy":
            # enemies get the full Entity Editor window (tabs, shop items, boss, dash, traps ...)
            result = entity_editor.edit_entity(self, data)
            if result is None:
                return
            self._checkpoint()
            object_edit.apply_entity(self, data, result, grid_info)
            return
        if data.get("type") == "trap" and str(data.get("name", "")).lower() == arrow_trap.NAME:
            values = entity_editor.edit_trap(self, data)
            if values is None:
                return
            self.history["homing-props"] = dict(values)       # the next one you place starts from these
            self._checkpoint()
            object_edit.apply(self, data, values, grid_info)
            return

        fields = object_edit.fields_for(data)
        values = self.open_field_popup(object_edit.title_for(data), fields)
        self._checkpoint()
        object_edit.apply(self, data, values, grid_info)

    def edit_entity_settings(self):
        """Per-level enemy stat tuning (the "entity settings" entry)."""
        from . import entity_settings
        name = entity_settings.edit(self)
        if name:
            print(f"Entity settings updated for {name}.")

    def add_treasure(self, grid_info):

        data = {
            "x": grid_info[0].x,
            "y": grid_info[0].y,
            "width": grid_info[0].width,
            "height": grid_info[0].height,
            "type": "treasure",
            "name": self.type
        }

        self.world.append(data)

        treasure = make_treasure(grid_info[0].x, grid_info[0].y, self.type, self)
        treasure.update_sprite()

        self.treasure_list.append(treasure)

    def add_trap(self, grid_info):
        """Place the selected trap. Timings go into the entry so the Modify
        tool can change them per trap afterwards."""
        name = str(self.type).lower()
        if name == arrow_trap.NAME:
            return self.add_homing_trap(grid_info)
        data = {
            "x": grid_info[0].x,
            "y": grid_info[0].y,
            "width": grid_info[0].width,
            "height": grid_info[0].height,
            "type": "trap",
            "name": name,
            "hurt_enemies": True,
        }
        kind = kind_for(name)
        if not kind.get("always_on"):
            data["off_time"] = kind["off_time"]
            data["on_time"] = kind["on_time"]
            data["delay"] = kind["delay"]

        self.world.append(data)

        trap = Trap(grid_info[0].x, grid_info[0].y, name, self,
                    data.get("off_time"), data.get("on_time"), data.get("delay"), True)
        self.traps.append(trap)

    def add_homing_trap(self, grid_info):
        """The Homing Arrow Trap: ownerless, so every effect is written into the entry by hand (Modify edits them)."""
        data = {"x": grid_info[0].x, "y": grid_info[0].y, "width": grid_info[0].width, "height": grid_info[0].height,
                "type": "trap", "name": arrow_trap.NAME}
        data.update(arrow_trap.clean_props(self.history.get("homing-props")))
        self.world.append(data)
        self.traps.append(arrow_trap.ArrowTrap(grid_info[0].x, grid_info[0].y, self, props=data))

    def add_deco(self, grid_info):
        selected = self.block_types[self.type_num][self.block_num]
        palette = str(getattr(self, "size", "1"))
        selected_name = selected if selected == "tree" or palette == "1" else f"{selected}_{palette}"

        if selected == 'tree':

            data = {
                "x": grid_info[0].x,
                "y": grid_info[0].y,
                "width": grid_info[0].width,
                "height": grid_info[0].height,
                "type": "tree",
                "name": f"tree_{palette}" if palette != "1" else "tree"
            }

            self.world.append(data)
            
            tree = Tree(grid_info[0].x, grid_info[0].y, self, palette)
            tree.update_sprite()

            self.damageable_objects.append(tree)

        else:
            data = {
                "x": grid_info[0].x,
                "y": grid_info[0].y,
                "width": grid_info[0].width,
                "height": grid_info[0].height,
                "type": "deco",
                "name": selected_name
            }

            self.world.append(data)
            
            deco = Deco(grid_info[0].x, grid_info[0].y, selected_name, self)
            deco.update_sprite()

            self.damageable_objects.append(deco)

    def remove(self, grid_info):
        for data in self.world[:]:
            if grid_info[0].collidepoint(data.get("x", 1), data.get("y", 1)):
                done = False
                self._draw_list_dirty = True
                if not grid_info[2]:
                    continue

                order = str(list(grid_info[2])[0])
                # print(order, data)
                if data.get("type", None) == "block" and ("block_fore" == order or "block_back" == order):
                    if data.get("perspective", "fore") == "back":
                        for block in self.bg_objects[:]:
                            if block.rect.colliderect(grid_info[0]):
                                self.bg_objects.remove(block)
                                done = True
                                self.changes.add(f"block_{self.perspective}")
                                break
                    else:
                        for block in self.objects[:]:
                            if block.rect.colliderect(grid_info[0]):
                                self.objects.remove(block)
                                done = True
                                self.changes.add(f"block_{self.perspective}")
                                break
    
                elif data.get("type", None) == "enemy" and order == "entities":
                    for block in self.enemy_list[:]:
                        if grid_info[0].collidepoint(block.origin_rect.x, block.origin_rect.y):
                            self.enemy_list.remove(block)
                            self._entities_dirty = True
                            done = True
                            self.changes.add("entities")
                            break

                elif data.get("type", None) == "spawn_point" and order == "entities":
                    for point in self.spawn_points[:]:
                        if grid_info[0].collidepoint(point.origin_rect.x, point.origin_rect.y):
                            self.spawn_points.remove(point)
                            done = True
                            self.changes.add("entities")
                            break

                elif data.get("type", None) == "treasure" and order == "treasure":
                    for block in self.treasure_list[:]:
                        if grid_info[0].collidepoint(block.origin_rect.x, block.origin_rect.y):
                            self.treasure_list.remove(block)
                            done = True
                            self.changes.add("treasure")
                            break
                
                elif data.get("type", None) == "door" and order == "door":
                    for block in self.doors[:]:
                        if grid_info[0].collidepoint(block.origin_rect.x, block.origin_rect.y):
                            self.doors.remove(block)
                            done = True
                            self.changes.add("door")
                            break

                elif data.get("type", None) == "deco" and order == "deco":
                    for block in self.damageable_objects[:]:
                        if grid_info[0].collidepoint(block.origin_rect.x, block.origin_rect.y):
                            self.damageable_objects.remove(block)
                            done = True
                            self.changes.add("deco")
                            break

                elif data.get("type", None) == "tree" and order == "deco":
                    for block in self.damageable_objects[:]:
                        if grid_info[0].collidepoint(block.origin_rect.x, block.origin_rect.y):
                            self.damageable_objects.remove(block)
                            done = True
                            self.changes.add("deco")
                            break

                elif data.get("type", None) == "trap" and order == "trap":
                    for block in self.traps[:]:
                        if grid_info[0].collidepoint(block.origin_rect.x, block.origin_rect.y):
                            self.traps.remove(block)
                            done = True
                            self.changes.add("trap")
                            break

                elif data.get("type", None) == "water" and order == "water":
                    for block in self.zones[:]:
                        if grid_info[0].collidepoint(block.origin_rect.x, block.origin_rect.y):
                            self.zones.remove(block)
                            done = True
                            self.changes.add("zones")
                            break

                elif data.get("type", None) == "moving_platform" and order == "platforms":
                    for block in self.platforms[:]:
                        if grid_info[0].collidepoint(block.origin_rect.x, block.origin_rect.y):
                            self.platforms.remove(block)
                            done = True
                            self.changes.add("platforms")
                            break
                if done:
                    self.world.remove(data)
                    grid_info[2].discard(order)
                    break