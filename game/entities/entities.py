import random
import pygame

from .entity_utils import Entity
from .target_system import TargetSystem
from ..scripts.physics import PHYSICS
from ..data.palletes.entities import entity_pallete
from ..scripts.cache import CACHED_RECTS
from ..settings import Settings
from ..scripts.camera import Camera

# ENEMY CLASS
class Enemy(Entity, PHYSICS):
    COLOR = (255, 0, 0)
    total = -1

    def __init__(self, x, y, width, height, name="Archer", color="Red", game=None, auto=True, id=None, client=None):
        # Attributes
        self.type = 'enemy'
        self.auto = auto
        super().__init__(x, y, width, height, name, color, game)

        self.client = client

        Enemy.total += 1
        self.id = Enemy.total if not id else id
        Entity.total += 1
        self.entity_id = Entity.total if not id else id

        self.personalise()
        
    def decide_kill(self, target):
        if not getattr(target, 'nature', None) == "entity":
            return True
        else:
            if target.color != self.color:
                    return True
            if target.type == "player":
                pass
            else:
                pass
        return False


# PLAYER CLASS
class Player(Entity, PHYSICS):
    COLOR = (0, 0, 255)
    total = -1

    def __init__(self, x, y, width, height, name="TNT", color="Blue", game=None, auto=False, viewport=None, j=None,
                 id=None, client=None, groups=None):
        # Attributes
        self.type = 'player'
        self.auto = auto
        super().__init__(x, y, width, height, name, color, game, groups)
        
        self.joystick_id = None
        self.key = ["None", 0]
        self.keyboard_num = 1
        self.control_type = None

        self.ready = False
        self.client = client

        Player.total += 1
        self.id = Player.total if not id else id
        Entity.total += 1
        self.entity_id = Entity.total if not id else id

        self.personalise()
        self.health = 500
        self.max_health = self.health
        self.mad = True 

        self.shake_frames = 0  # Number of frames to apply shake
        self.shake_intensity = 6

        self.zoom = 1.0
        self.target_zoom = 1.0
        self.zoom_min = 0.5
        self.zoom_max = 2.0

        self.target_system = TargetSystem(self)
        self.camera = Camera(self)          # follow / look-ahead / focus, see scripts/camera.py

        self.player_types = ['TNT', 'Pawn', 'Warrior', 'Torch', 'Archer']
        self.player_colors = list(entity_pallete.keys())
        self.cam_rect_key = None
        self.viewport = pygame.Rect(0, 0, Settings.WIDTH, Settings.HEIGHT)
        self.cam_rect = self.viewport
        
    def reassign_joystick(self, new_joystick):
        self.joystick = new_joystick

    def decide_kill(self, target):
        if not getattr(target, 'nature', None) == "entity":
            return True
        else:
            if target.color != self.color:
                    return True
            if target.type == "player":
                pass
            else:
                pass
        return False
    
    def camera_update(self):
        if not getattr(self, "viewport", None):
            return
        
        key = (str(self.viewport), str(self.game.window_rect))
        if key not in CACHED_RECTS["player_wins"]:
            CACHED_RECTS["player_wins"][key] = self.viewport.clip(self.game.window_rect)

        self.view_rect = CACHED_RECTS["player_wins"][key]
        # if view_rect.width <= 0 or view_rect.height <= 0:
        #     continue

        # CAMERA: the rect is sized for the zoom, then scripts/camera.py positions it
        cam_width = int(self.viewport.width / self.zoom)
        cam_height = int(self.viewport.height / self.zoom)
        key = (cam_width, cam_height)
        if self.cam_rect_key != key:
            self.cam_rect_key = key
            self.cam_rect = pygame.Rect(0, 0, cam_width, cam_height)
            self.cam_rect.center = self.rect.center

        # Preview recording (extras/capture_previews.py): look at the level's preview point with the player out of
        # the shot. A level with no preview point keeps the normal camera on the spawn point instead.
        if self.game.type == "preview" and getattr(self.game, "preview_point", None):
            self.rect.x, self.rect.y = 9999, 9999
            self.camera.focus(self.game.preview_point)
            
        self.camera.update()

class Spawn_Point():
    total = -1

    def __init__(self, x, y, width, height, interval=10, limit=10, entities=None, game=None, id=None):

        # Attributes
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.interval = interval
        self.limit = limit
        self.game = game
        self.type = "spawn_point"
        self.nature = "spawn_point"
        self.entities = [("Pawn", "Red")] if not entities else entities
        Spawn_Point.total += 1
        self.id = Spawn_Point.total if not id else id

        # Spawners are invisible in gameplay, but the level editor needs
        # to hit-test and draw them like any other placed object.
        self.rect = pygame.Rect(x, y, width, height)
        self.origin_rect = pygame.Rect(x, y, width, height)

        self.health = 1000
        self.history = -10
        self.created = 0
        self.finished = False

    def update(self):
        # Never produce enemies while the level is being authored -- the
        # editor briefly runs the game logic during its load screen, and
        # spawned enemies would otherwise pile up in the editing session
        # and get written into the level on save.
        if getattr(self.game, "EDIT_WORLD", False):
            return

        if not self.entities:
            return

        # Survival levels run their own escalating waves instead
        objective = getattr(self.game, "objective", None)
        if objective is not None and objective.owns_spawning:
            return

        if self.game.seconds % self.interval == 0 and self.created < self.limit:
            if self.history != self.game.seconds:
                # (the roll only happens when a spawn is actually due)
                type_ = random.choice(self.entities)
                name = type_[0]
                color = type_[1]
                self.game.enemy_list.append(Enemy(self.x, self.y, 50, 50, name, color, game=self.game))
                self.game._draw_list_dirty = True
                self.game._entities_dirty = True
                
                self.history = self.game.seconds
                self.created += 1

        if self.created >= self.limit:
            self.finished = True
