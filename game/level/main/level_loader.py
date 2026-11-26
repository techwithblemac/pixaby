import os
import pygame
import json
import threading
import time
import copy

from ...entities.entities import (
    Enemy, Spawn_Point
)
from ...scripts.physics import PHYSICS as physics
from ...scripts.functions import (
    map_chunks, remove_duplicates, find_last, create_chunks
)

from ...objects.objects import (
    Tree, Block, Deco, WaterZone, Platform, Treasure, Door, Trap, make_treasure
)
from ...objects import arrow_trap
from ...entities import mods as mods_rt
from ...data.coop_items import PLACEABLE
from ...entities.pathfinding import PlatformGraph, PlatformNode
from ..editor import editor_palette
from ...data.difficulty import scale_enemy, unscale_enemy
from ...data import biomes
from ...scripts import paths
from .. import preview

class Level_Loader:
    def initialise_grid(self):
        self.color_zones = {
            "normal": (50, 50, 255),
            "current": (50, 50, 200),
            "toxic": (70, 220, 70),
            "healing": (0, 200, 100),
            "lava": (255, 80, 0)
        }
        
        self.sprites = pygame.sprite.Group()
        self.sprite_index = 0
        self.animation_count = 1
        self.ANIMATION_DELAY = 2
        
        # Game Settings
        self.EDIT_WORLD = False
        
        # GRID BLOCK SETTINGS
        self.INSERT = True
        # "insert" | "delete" | "modify" -- INSERT is kept in sync as a
        # bool so existing call sites and the help screen still work.
        self.TOOL = "insert"
        self.EDIT_GRID = 0

        self.selectedx, self.selectedy = (0, 0)
        self.confirm = None
        
        # Category table and block vocabulary both come from
        # editor_palette so the editor and the loader can never drift
        # apart (they used to carry separate hand-copied versions).
        all_blocks = editor_palette.build_block_list()

        self.block_types = [all_blocks]
        self.block_sizes = ['big', 'small']

        self.type_num = 0
        self.block_num = 0
        self.size_num = 0

        self.prev = None
        self.platform = []
        self.prev_num = 0
        self.thing = None

        self.history = {'flow-rise': f'1;0'}
        self.perspective = "fore"
        self.pressed = False

        self.edit_grid_settings = editor_palette.build_edit_grid_settings()

        self.world_rules = {
            "platforms" : {"block_fore", "entities", "deco", "platforms", "treasure", "door", "trap"},
            "spawn_point" : {"block_fore", "entities", "platforms", "door", "trap"},
            "door" : {"block_fore", "entities", "platforms", "door", "start", "spawn_point", "trap"},
            "water" : {"water"},
            "trap" : {"block_fore", "trap", "deco", "platforms", "treasure", "door", "entities", "start"},
            "deco" : {"block_fore", "deco", "platforms", "treasure", "trap"},
            "treasure" : {"block_fore", "deco", "platforms", "block_back", "treasure", "trap"},
            "entities" : {"block_fore", "entities", "platforms", "door", "trap"},
            "block_fore" : {"block_fore", "entities", "deco", "platforms", "block_back", "door", "trap"},
            "block_back" : {"block_fore", "block_back"},
            "start" : {"block_fore", "platforms", "door", "trap"}
        }

    def create_grid(self):
        block_size = 64
        width = 2000
        height = 2000
        
        self.chunk_w, self.chunk_h = (12, 12)
        
        self.minx = float("inf")
        self.miny = float("inf")
        self.maxx = -float("inf")
        self.maxy = -float("inf")
        
        i = 0
        for h in range(-height // block_size, height // block_size):
            for w in range(-width // block_size, width // block_size):
                rect = pygame.Rect(w * block_size, h * block_size, block_size, block_size)
                self.grid.append([rect, self.RED, set(), i])
                i += 1

                self.minx = min(rect.left, self.minx)
                self.miny = min(rect.top, self.miny)
                self.maxx = max(rect.right, self.maxx)
                self.maxy = max(rect.bottom, self.maxy)
                        
        self.blank_map = create_chunks({}, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h, overlap=True)
        self.blank_map_mini = create_chunks({}, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w//2, self.chunk_h//2, overlap=True)
        
        self.world_rect = pygame.Rect(self.minx, self.miny, self.maxx, self.maxy)

    def personalise(self, entity, times=1):
        entity_settings = (getattr(self, 'settings', None) or {}).get("entity", None)

        unscale_enemy(entity)       # back to base stats before the level's settings go on

        if entity_settings:
            for k, v in entity_settings.get(entity.name, {}).items():
                if k == "health":
                    if entity.type == "player":
                        if times == 2:
                            continue
                setattr(entity, k, v)

        # Per-floor / co-op difficulty, applied once when an enemy is created
        scale_enemy(self, entity, entity_settings)

    @staticmethod
    def default_world():
        """The blank-slate world used for both brand-new sessions and any
        level file that's missing from disk. Returns a fresh list each call
        so callers (e.g. the level selector's "new level" flow) can freely
        mutate the result, such as embedding a ``_level_meta`` block into
        the first ("entity settings") entry, without touching this template.
        """
        return [
            {
                "type": "entity settings",
                "Torch": {
                    "acquire_range": 1000,
                    "acquire_down": 300,
                    "acquire_up": 300,
                    "attack_up": 50,
                    "attack_down": 50,
                    "attack_range": 50,
                    "attack_power": 4
                },
                "Pawn": {
                    "acquire_range": 1000,
                    "acquire_down": 300,
                    "acquire_up": 300,
                    "attack_up": 50,
                    "attack_down": 50,
                    "attack_range": 40,
                    "attack_power": 5
                },
                "Warrior": {
                    "acquire_range": 1000,
                    "acquire_down": 300,
                    "acquire_up": 300,
                    "attack_up": 50,
                    "attack_down": 50,
                    "attack_range": 50,
                    "attack_power": 6
                },
                "TNT": {
                    "acquire_range": 1000,
                    "acquire_down": 300,
                    "acquire_up": 300,
                    "attack_up": 300,
                    "attack_down": 300,
                    "attack_range": 600,
                    "attack_power": 8
                },
                "Archer": {
                    "acquire_range": 1000,
                    "acquire_down": 300,
                    "acquire_up": 300,
                    "attack_up": 300,
                    "attack_down": 300,
                    "attack_range": 600,
                    "attack_power": 7
                }
            },
            {
                "x": 0,
                "y": -64,
                "points": [[0, -128], [0, -64]],
                "width": 64,
                "height": 64,
                "type": "start"
            },
            {
                "x": 0,
                "y": -64,
                "width": 64,
                "height": 64,
                "interval": 5,
                "limit": 5,
                "type": "spawn_point",
                "entities": [
                    [
                        "Pawn",
                        "Red"
                    ]
                ]
            },
            {
                "x": 0,
                "y": 0,
                "width": 64,
                "height": 64,
                "type": "block",
                "name": "stone",
                "size": "big"
            }
        ]

    def _clear_projectiles(self):
        """Arrows, bombs and fire live in ``game.bombs.list``, which is built once at start-up, so a level change
        used to leave every projectile still in flight (homing arrows kept chasing in the next level). Hand them
        back to their pools and empty the list."""
        bombs = getattr(self, "bombs", None)
        if bombs is None:
            return
        for obj in list(getattr(bombs, "list", ())):
            try:
                obj.return_to_pool()
            except Exception:
                pass
        bombs.list = []

    def create_new_world(self):
        self._clear_projectiles()
        self.graph = PlatformGraph(self)

        self.map = {}
        self.node_map = {}
        
        self.nodes = []
        self.air_nodes = []
        
        self.grid = []
        
        self.start_points = (0, -64)
        self.points = [[0, -64]]
        self.preview_point = None       # (x, y) of the selector's map preview, from the "preview coordinates" entry
        self.spawn_points = []
        self.points_done = []
        
        self.platforms = []    
        self.enemy_list = []
        self.dead_entities = []
        self.objects = []
        self.bg_objects = []
        self.doors = []
        self.traps = []
        self.damageable_objects = []
        self.treasure_list = []
        self.fire_list = []
        self.projectile_list = []
        self.zones = []
        self.bubbles = []
        self.splashes = []

        self.all_entities = []
        self.all_entities_2    = ()
        self._entities_dirty = True
        
        self.blank_map = {}
        self.outline_objects_map = {}
        self.objects_map = {}
        self.bg_objects_map = {}
        self.entities_map = {}
        self.damageable_objects_map = {}
        self.zones_map = {}
        
        self.damageable_objects_dirty = False
        
        self.draw_list = []      # built once, reused until dirty
        self.draw_list_2 = []
        self._draw_list_dirty = True    # True on first frame → triggers build
        
        self.objects_to_draw = []
        
        self.settings = {}
        self.world = self.default_world()
        
        
    # Which levels/<folder>/ the current level lives in (see scripts/paths.py).
    # A plain class attribute so every host (game, editor, selector backdrop) has it.
    level_folder = paths.STORY

    def _coop_range(self):
        """(min, max) players of the chosen co-op world while playing Split Screen, else None."""
        if getattr(self, "SPLIT_SCREEN", False) and self.level_folder == paths.MULTIPLAYER:
            return getattr(self, "level_players", None)
        return None

    def max_local_players(self):
        """The story is a solo run; every other folder allows up to four local players. A co-op world
        played in Split Screen caps at the world's own maximum."""
        if self.level_folder == paths.STORY:
            return 1
        coop = self._coop_range()
        return min(4, coop[1]) if coop else 4

    def min_local_players(self):
        """Co-op worlds are built for 2 to 4 heroes: Split Screen waits on the join screen until enough have joined."""
        coop = self._coop_range()
        return max(1, coop[0]) if coop else 1

    def level_key(self):
        """Identifies the loaded level across folders: story 1 and My Worlds 1 are different levels."""
        return (self.level_folder, self.level)

    def level_path(self):
        return paths.level_file(self.level, self.level_folder)

    def load_world(self):
        self.create_new_world()
        self.env_ready = False

        path = self.level_path()
        try:
            with open(path, "r") as f:
                self.world = json.load(f)

        except FileNotFoundError as e:
            print(f"{e} in load_world() creating one")
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as w:
                json.dump(self.world, w, indent=2)

            with open(path, "r") as r:
                self.world = json.load(r)

        # which biome is this level (theme music, deco palettes) - see data/biomes.py
        try:
            biomes.analyse(self)
        except Exception as err:
            print(f"[biomes] {err!r}")
            self.biome_map = None

        threading.Thread(target=self.create_world, daemon=True).start()
   
    def create_world(self):
        self.start = time.time()
        
        self.create_grid()
        self.prep()
        self.create_nodes()

    def prep(self):
        self.world_rules = {
            "platforms" : {"block_fore", "entities", "deco", "platforms", "treasure", "door", "trap"},
            "spawn_point" : {"block_fore", "entities", "platforms", "door", "trap"},
            "door" : {"block_fore", "entities", "platforms", "door", "start", "spawn_point", "trap"},
            "water" : {"water"},
            "trap" : {"block_fore", "trap", "deco", "platforms", "treasure", "door", "entities", "start"},
            "deco" : {"block_fore", "deco", "platforms", "treasure", "trap"},
            "treasure" : {"block_fore", "deco", "platforms", "block_back", "treasure", "trap"},
            "entities" : {"block_fore", "entities", "platforms", "door", "trap"},
            "block_fore" : {"block_fore", "entities", "deco", "platforms", "block_back", "door", "trap"},
            "block_back" : {"block_fore", "block_back"},
            "start" : {"block_fore", "platforms", "door", "trap"}
        }
        
        level = str(self.level)[find_last(str(self.level), "/") + 1:]
        print(f"\nLOADING LEVEL : {level} ...\n")
        processed_data = []
        x, y, level = 10, 0, 0

        blank_map = copy.deepcopy(self.blank_map)
        self.temp_grid_map = map_chunks(blank_map, self.grid, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h, grid=True)
        
        # Checking to see if the grid rectangles are occupied
        self.preview_point = None
        for data in self.world:
            # The map-preview marker is level data, not an object in the world: keep it whatever its coordinates
            # (it may point outside the grid) and never let it take part in collision / grid work.
            if data.get("type") == preview.TYPE:
                self.preview_point = preview.point([data])
                processed_data.append(data)
                continue

            rect = pygame.Rect(data.get("x", 1), data.get("y", 1), data.get("width", 64), data.get("height", 64))
            added = False
            nearby_nodes = physics.get_objects(self.temp_grid_map, rect, 0, grid=True)
            nearby_nodes = remove_duplicates(nearby_nodes, grid=True)
            for index in nearby_nodes:
                grid_info = self.grid[index]
                # data['y'] = data.get("y", 0) - (64 * y if self.level == level else 0)
                # data['x'] = data.get("x", 0) - (64 * x if self.level == level else 0)
                
                skip = False
                delete = False
                collided = False
                
                type_ = data.get("type", None)

                if not added and type_ == "entity settings":
                    self.settings["entity"] = data
                    processed_data.append(data)
                    break

                elif not added and type_ == "start":
                    self.start_points = data.get("x", 0), data.get("y", 0)
                    self.points = data.get("points", [[0, -64]])
                    processed_data.append(data)
                    break

                if (
                    grid_info[0].x < data.get("x", 1) + data.get("width", 64) and
                    grid_info[0].x + grid_info[0].width > data.get("x", 1) and
                    grid_info[0].y < data.get("y", 1) + data.get("height", 64) and
                    grid_info[0].y + grid_info[0].height > data.get("y", 1)
                    ) and not skip:
                    grid_info[1] = (9, 8, 7)
                    collided = True
                
                if collided and type_ == "block":
                    perspective = data.get("perspective", "fore")
                    if perspective == "back":
                        blacklist = self.world_rules[f"{type_}_{perspective}"]
                        if grid_info[2].isdisjoint(blacklist):
                            grid_info[2].add("block_back")
                            if not added:
                                self.bg_objects.append(
                                    Block(data.get("x", None), data.get("y", None), data.get("width", None), data.get("height", None),
                                        data.get("name", None), data.get("size", None), perspective="back"))
                        else:
                            delete = True

                    else:
                        blacklist = self.world_rules[f"{type_}_{perspective}"]
                        if grid_info[2].isdisjoint(blacklist):
                            grid_info[2].add("block_fore")
                            if not added:
                                self.objects.append(
                                    Block(data.get("x", None), data.get("y", None), data.get("width", None), data.get("height", None),
                                        data.get("name", None), data.get("size", None), perspective="fore"))
                                skip = True  # Coz its no route for nodes
                                grid_info[1] = self.BLACK
                        else:
                            delete = True                           
                
                elif collided and type_ == "enemy":
                    blacklist = self.world_rules["entities"]
                    if grid_info[2].isdisjoint(blacklist):
                        grid_info[2].add("entities")
                        if not added:
                            obj_ = Enemy(data.get("x", None), data.get("y", None), data.get("width", None), data.get("height", None),
                                data.get("name", None), data.get("color", None), game=self)
                            
                            obj_.posted = data.get("posted", False)
                            obj_.patroller = data.get("patroller", False)
                            obj_.patrol_range_x = data.get("patrol_range_x", obj_.patrol_range_x)
                            obj_.patrol_range_y = data.get("patrol_range_y", obj_.patrol_range_y)
                            mods_rt.apply(obj_, data)           # Entity Editor tweaks: items, effects, boss, dash, traps ...
                            #print(obj_.__dict__)
                            #print("SIZE : ", get_total_size(obj_))

                            self.enemy_list.append(
                                obj_)
                            self._entities_dirty = True
                    else:
                        delete = True
                
                elif collided and type_ == "door":
                    blacklist = self.world_rules[type_]
                    if grid_info[2].isdisjoint(blacklist):
                        grid_info[2].add("door")
                        if not added:
                            self.doors.append(
                                Door(data.get("x", None), data.get("y", None), data.get("name", None), self,
                                     data.get("targets")))
                    else:
                        delete = True

                elif collided and type_ == "treasure":
                    blacklist = self.world_rules[type_]
                    if grid_info[2].isdisjoint(blacklist):
                        grid_info[2].add("treasure")
                        # a charm pick-up the author placed (co-op) is skipped over the network, which cannot sync it
                        if not added and not (data.get("name") in PLACEABLE and getattr(self, "MULTIPLAYER", False)):
                            self.treasure_list.append(
                                make_treasure(data.get("x", None), data.get("y", None), data.get("name", None), self))
                    else:
                        delete = True

                elif collided and type_ == "deco":
                    blacklist = self.world_rules[type_]
                    if grid_info[2].isdisjoint(blacklist):
                        grid_info[2].add("deco")
                        if not added:
                            deco = Deco(data.get("x", None), data.get("y", None), data.get("name", None), self)
                            self.damageable_objects.append(deco)
                            # recolour this biome's deco art now, on the loading screen (once per
                            # biome), not as a freeze the first time it scrolls into view
                            from ...scripts.cache import get_deco_sprites
                            get_deco_sprites(deco.deco_biome)
                    else:
                        delete = True
                
                elif collided and type_ == "tree":
                    blacklist = self.world_rules["deco"]
                    if grid_info[2].isdisjoint(blacklist):
                        grid_info[2].add("deco")
                        if not added:
                                tree_name = str(data.get("name", "tree"))
                                palette = tree_name.rsplit("_", 1)[-1] if tree_name.rsplit("_", 1)[-1] in biomes.BIOMES else "1"
                                self.damageable_objects.append(Tree(data.get("x", None), data.get("y", None), self, palette))
                                # Recolouring the tree art takes a moment. Do it now, on the loading
                                # screen (once per palette), instead of as a freeze the first time a
                                # tree scrolls into view.
                                from ...scripts.cache import get_tree_sprites
                                get_tree_sprites(palette)
                    else:
                        delete = True
                
                elif collided and type_ == "trap":
                    blacklist = self.world_rules[type_]
                    if grid_info[2].isdisjoint(blacklist):
                        grid_info[2].add("trap")
                        if not added:
                            if str(data.get("name", "")).lower() == arrow_trap.NAME:
                                self.traps.append(arrow_trap.ArrowTrap(data.get("x"), data.get("y"), self, props=data))
                            else:
                                self.traps.append(
                                    Trap(data.get("x", None), data.get("y", None), data.get("name", "spikes"), self,
                                         data.get("off_time"), data.get("on_time"), data.get("delay"),
                                         data.get("hurt_enemies", True)))
                    else:
                        delete = True

                elif collided and type_ == "water":
                    grid_info[1] = (1, 1, 1)
                    blacklist = self.world_rules[type_]
                    if grid_info[2].isdisjoint(blacklist):
                        grid_info[2].add("water")
                        if not added:
                            self.zones.append(WaterZone(data.get("x", None), data.get("y", None), data.get("width", None),
                                                        data.get("height", None), data.get("water_type", None), self,
                                                        tuple(data.get("color", None)), data.get("flow", None),
                                                        bool(data.get("rise", None))))
                        
                    else:
                        delete = True
                
                elif collided and type_ == "spawn_point":
                    blacklist = self.world_rules[type_]
                    if grid_info[2].isdisjoint(blacklist):
                        grid_info[2].add("entities")
                        if not added:
                            self.spawn_points.append(
                                Spawn_Point(
                                    data.get("x", None),
                                    data.get("y", None),
                                    data.get("width", None),
                                    data.get("height", None),
                                    data.get("interval", None),
                                    data.get("limit", None),
                                    data.get("entities", None),
                                    self
                                )
                            )
                    else:
                        delete = True
                    
                    self.log += 1
                
                elif collided and type_ == "moving_platform":
                    grid_info[1] = (1, 1, 1)
                    blacklist = self.world_rules["platforms"]
                    if grid_info[2].isdisjoint(blacklist):
                        grid_info[2].add("platforms")
                        if not added:
                            self.platforms.append(
                                Platform(
                                    data.get("x", None),
                                    data.get("y", None),
                                    data.get("width", None),
                                    data.get("height", None),
                                    data.get("moving", None),
                                    data.get("direction", None),
                                    data.get("speed", None),
                                    data.get("dest_x", [data.get("min_x", 0), data.get("max_x", 0)]),
                                    data.get("dest_y", [data.get("y", 0), data.get("y", 0)]),
                                    self
                                )
                            )
                    else:
                        delete = True

                # Delete is for unwanted overlaps with other elements
                if not delete:
                    if collided and not added:
                        added = True
                        processed_data.append(data)
                else:
                    grid_info[1] = self.RED
        
        self.world = processed_data

        self.outline_objects = physics.get_outline_blocks(self.objects, tile_size=64)
        
        a = copy.deepcopy(self.blank_map)
        b = copy.deepcopy(self.blank_map)
        c = copy.deepcopy(self.blank_map)
        d = copy.deepcopy(self.blank_map)
        e = copy.deepcopy(self.blank_map)

        # DIVIDE THE WORLD INTO CHUNKS (IMMOVABLE-STRUCTURES)
        self.map = map_chunks(a, self.outline_objects, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h) 
        self.objects_map = map_chunks(b, self.objects, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h) 
        
        self.bg_objects_map = map_chunks(c, self.bg_objects, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h) 
        
        self.damageable_objects_map = map_chunks(d, self.damageable_objects, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h) 
        self.zones_map = map_chunks(e, self.zones, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h) 
                            
        """
        for pos in self.map.values():
            print(f"Blocks : {len(pos[1])}")
        """
        
        self.all_entities = self.enemy_list + self.players
        self.all_entities_2    = (self.enemy_list, self.players)
        self._entities_dirty = True

    def create_nodes(self):
        nodes = []        
        for grid in self.grid:
            blacklist = {"block_fore"}
            if grid[2].isdisjoint(blacklist):
                nodes.append(grid)

        print("Len of nodes", len(nodes))
        
        a = copy.deepcopy(self.blank_map)
        self.temp_grid_map = map_chunks(a, self.grid, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h, grid=True)
        for node in nodes:
            var = 0
            nearby_nodes = physics.get_objects(self.temp_grid_map, node[0], 0, grid=True)
            nearby_nodes = remove_duplicates(nearby_nodes, grid=True)
            for index in nearby_nodes:
                grid_info = self.grid[index]
                if node == grid_info:
                    continue

                dx = abs(node[0].centerx - grid_info[0].centerx)
                dy = abs(node[0].centery - grid_info[0].centery)

                if dy < 66 and dx < 66 and grid_info[1] != self.BLACK:
                    var += 1

                if var >= 8:
                    break

            if var <= 7 or node[1] == (1, 1, 1):
                self.nodes.append(
                    PlatformNode(
                        node[0]
                    )
                )

            if var == 8 and node[1] == self.RED:
                self.air_nodes.append(
                    PlatformNode(
                        node[0]
                    )
                )
            
        
        print("Number of block (filled) nodes:", len(self.nodes))
        print("Number of air (blanks):", len(self.air_nodes))
        
        blank_map = copy.deepcopy(self.blank_map)
        temp_node_map = map_chunks(blank_map, self.nodes, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h)
        
        print(time.time() - self.start)
        self.start = time.time()
        
        self.connect_nodes(self.nodes, temp_node_map)

    def connect_nodes(self, nodes, map={}):
        self.g_score = {}
        for node in nodes:
            self.g_score[node] = float('inf')
            
            for other in remove_duplicates(physics.get_objects(map, node.rect, 0)):
                if node == other:
                    continue

                # Remove/Skip diagonal nodes
                diagonal = False
                x, y = node.rect.center
                size = 64
                for e, i in enumerate(
                        [(x + size, y + size), (x - size, y + size), (x + size, y - size), (x - size, y - size)]):
                    if other.rect.collidepoint(i):
                        diagonal = True
                        break

                if diagonal:
                    continue

                dx = abs(node.rect.centerx - other.rect.centerx)
                dy = abs(node.rect.centery - other.rect.centery)

                if dy < 66 and dx < 66:
                    node.neighbors.append(other)

        blank_map = copy.deepcopy(self.blank_map_mini)
        self.node_map = map_chunks(blank_map, self.nodes, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h)

        self.env_ready = True
        
        print("Connected nodes in ", time.time() - self.start)
        print("Prepertaions done. Level Ready!")

