import itertools
import copy

from ...scripts.functions import map_chunks, remove_duplicates_2
from ...scripts.physics import PHYSICS as physics

IDX_BG_OBJECTS = 0
IDX_DOORS = 1
IDX_BUBBLES = 2
IDX_BOMBS_LIST = 3
IDX_OBJECTS = 4
IDX_TRAPS = 5
IDX_PLATFORMS = 6
IDX_PLAYERS = 7
IDX_ENEMY_LIST = 8
IDX_DEAD_ENTITIES = 9
IDX_DAMAGEABLE_OBJECTS = 10
IDX_FIRE_LIST = 11
IDX_TREASURE_LIST = 12
IDX_ZONES = 13
IDX_SPLASHES = 14

STATIC_OBJS = {IDX_BG_OBJECTS, IDX_OBJECTS, IDX_PLAYERS, IDX_ENEMY_LIST, IDX_DEAD_ENTITIES}
UNDYING = {IDX_PLATFORMS, IDX_DEAD_ENTITIES, IDX_ZONES}

def _rebuild_all_entities(self) -> None:
    """
    Rebuild self.all_entities from enemy_list + players.
    Call only when _entities_dirty is True.
    spatial_grid.rebuild() already iterates this list — zero extra cost.
    """
    self.all_entities    = self.enemy_list + self.players
    self.all_entities_2    = (self.enemy_list, self.players)
    self._entities_dirty = False

def _rebuild_draw_list(self, code = 1) -> None:
    """
    Rebuild self.draw_list from all source lists.

    Uses itertools.chain so no intermediate list is allocated — objects are
    yielded from each source list in order without copying.

    Call this only when self._draw_list_dirty is True.  draw_sub() calls it
    automatically; you should not need to call it manually.
    """
    self.draw_list_2 = (
        self.bg_objects,
        self.doors,
        self.bubbles,
        self.bombs.list,
        self.objects,
        self.traps,
        self.platforms,
        self.players,
        self.enemy_list,
        self.dead_entities,
        self.damageable_objects,
        self.fire_list,
        self.treasure_list,
        self.zones,
        self.splashes
    )
    self.draw_list = list(itertools.chain.from_iterable(self.draw_list_2))
    
    self._draw_list_dirty = False

def update_game_logic(self):
    # MANAGE SPAWN POINTS
    self.points_done = 0
    for point in self.spawn_points:
        point.update()
        if point.finished:
            self.points_done += 1
                
    if self._entities_dirty:
        _rebuild_all_entities(self)

    for objects in self.all_entities_2:
        for i in range(len(objects) - 1, -1, -1):
            entity = objects[i]
            if not entity.dead:
                if self.MULTIPLAYER:
                    if self.SERVER:
                        entity.manage() 
                        entity.update_sprite()
                    else:
                        if entity == self.player:
                            entity.control()
                        entity.update_sprite_client()
                        
                else:
                    entity.manage()
                    entity.update_sprite()
                
            else:
                objects.pop(i)
    
    for entity in self.dead_entities:
        entity.manage()

    self.entities_map = map_chunks(self.entities_map, self.all_entities, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h, clear_chunks=True) 

    return exec(self, update)

def update(self, obj_list):
    alive = []
    extend_alive = alive.extend
    on = True
    
    if getattr(self, "local_players", None):
        if len(self.local_players) < 2:
            player_cams = self.player.cam_rect
        else:
            if self.MULTIPLAYER and self.SERVER:
                player_cams = [player.cam_rect for player in self.players]
            else:
                player_cams = [player.cam_rect for player in self.local_players]
    
    else:
        player_cams = self.player.cam_rect

    for i, objects in enumerate(obj_list):
        if i in STATIC_OBJS: # or i == IDX_ZONES:
            if i == IDX_BG_OBJECTS:
                if on:
                    objects = remove_duplicates_2(physics.get_objects(self.bg_objects_map, player_cams, 0))
            if i == IDX_OBJECTS:
                if on:
                    objects = remove_duplicates_2(physics.get_objects(self.objects_map, player_cams, 0))
            if i == IDX_PLAYERS or i == IDX_ENEMY_LIST:
                if on:
                    objects = remove_duplicates_2(physics.get_objects(self.entities_map, player_cams, 0))
               
            extend_alive(objects)
            continue

        for o in range(len(objects) - 1, -1, -1):
            obj = objects[o]
            #try:
            if (i == IDX_ZONES and not obj.in_screen):
                continue

            if not obj.dead or (i == IDX_DEAD_ENTITIES and obj.nature == 'entity'):
                if self.MULTIPLAYER:
                    if self.SERVER:
                        obj.update_sprite()
                    else:
                        obj.update_sprite_client()
                        
                else:
                    obj.update_sprite()

            elif obj.dead and i not in UNDYING:
                # Hand pooled objects (Bomb/Arrow/Fire) back to their
                # pool instead of just dropping the reference; no-op
                # for every other object type.
                obj.return_to_pool()
                objects.pop(o)
                if i == IDX_DAMAGEABLE_OBJECTS:
                    self.damageable_objects_dirty = True
            
            # except Exception as e:
            #     print("In static update ", obj.name, obj.type, e)
    
        if i == IDX_DAMAGEABLE_OBJECTS:
            if self.damageable_objects_dirty:
                self.damageable_objects_map = map_chunks(self.damageable_objects_map, self.damageable_objects, self.minx, self.miny, self.maxx, self.maxy, self.chunk_w, self.chunk_h, clear_chunks=True) 
                self.damageable_objects_dirty = False
                print("updated deco")
            
            if on:
                objects = remove_duplicates_2(physics.get_objects(self.damageable_objects_map, player_cams, 0))

        if i == IDX_ZONES:
            if on:
                objects = remove_duplicates_2(physics.get_objects(self.zones_map, player_cams, 0))
             

        extend_alive(objects)
    
    return alive

def exec(self, func):
    if self._draw_list_dirty:
        _rebuild_draw_list(self)

    return func(self, self.draw_list_2)
