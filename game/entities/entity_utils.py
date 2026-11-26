import random
import math
import pygame
from typing import Tuple, Any
from collections import OrderedDict

from ..objects.objects import Splash, Bubble, Treasure
from ..assets import Assets
from ..settings import Settings
from ..scripts.cache import CACHED_ENTITY_IMAGES, create_cache_img, cache_assets, _lru_touch
from ..scripts.physics import get_degree
from ..scripts.sounds import playit
from .mind import ACTIVITY
from ..scripts.shop_effects import apply_loadout, strip_loadout, drop_bonus as shop_drop_bonus
from ..data.charms import START_CHARMS as C_START_CHARMS, START_DASHES as C_START_DASHES
from ..scripts.death_rules import drop_wallet
from ..scripts import coop_loot
from ..ui import combat_fx
from .pathfinding import _manage_pathfinding, get_closest_node
from . import mods as mods_rt
from .burn import Burn


SPRITE_SHEET_ANGLES = {
    (155, -155): 'attack_270',
    (-20, 20): 'attack_90',
    (20, 70): 'attack_45',
    (70, 110): 'attack_0',
    (110, 155): 'attack_315',
    (-70, -20): 'attack_135',
    (-110, -70): 'attack_180',
    (-155, -110): 'attack_225'
}


# ENTITY CLASS
class Entity(ACTIVITY):
    GRAVITY = 800
    ANIMATION_DELAY = 1
    total = -1

    def __init__(self, x, y, width, height, name='TNT', color='Yellow', game='None', group=None):
        # Coordinates
        super().__init__()
        self.game = game
        
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        
        self.rect = pygame.Rect(x, y, 40, 50)
        
        self.origin_rect = pygame.Rect(x, y, width, height)
        self.eye_range = self.rect.copy()

        self.spawn_point = x
        self.a, self.b = (0, 0)
        
        self.kill_choice = 'kill my enemies with different color and players with different color'

        # Attributes
        self.name = name
        self.color = color
        self.nature = 'entity'
        self.entity_id = 0
        self.mass = 1

        # Entity value
        self.value = 5

        # Current Sprite
        sprite = cache_assets((name, color, "idle_right"), index=0)
        self.mask = pygame.mask.from_surface(sprite)
        self.animation_count = 0
        self.sprite_sheet = 'run'
        self.direction = "left"
        self.sheet_name = self.sprite_sheet + "_" + self.direction
        self.image_index = 0
        self.sprite_index = 0
        self.morex = 0
        self.morey = 0
        self.time_accumulator = 0
        self.frame_duration = 0.1
        
        self._sprite_cache    = {}
        # Last resolved key — if this matches the current key, skip the lookup.
        self._last_sheet_key  = None
        
        # Draw values
        self.see_through = False
        self.zoom = 1
        self.in_screen = True
        
        # Thoughts and Feelings
        self.feelings   = set()
        self.activities = {'wl', 'wr', 'rl', 'rr', 'il', 'ir', 'c', 'j'}
                
        # Speeds
        self.x_vel = 0
        self.y_vel = 0
        self.speed = 200
        self.walk_speed = 100
        self.jump_vel = -400
        self.acceleration = 10
        self.current_speed = self.speed
        self.current_gravity = Settings.GRAVITY
        self.current_jump = self.jump_vel

        # Some things        
        self.duration = 0
        self.knocking_back = 0
                
        # Targets
        self.target_list = []
        self.targets_in_range = []
        self.friends = []
        self.target = None
        self.has_target = False
        self.group = None

        # Status
        self.dead = False
        self.death = False
        
        # States
        self.crouching = False
        self.chasing = False
        self.attacking = False
        self.wandering = False
        self.evading = False
        self.patrolling = False
        self.dashing = False
        self.finding_way = False
        self.hit_wall = False
        self.on_land = False
        self.bumb_head = False
        self.on_ground = False
        
        # State timers
        self.on_ground_for = 0
        self.in_air_for = 0
        self.hit_wall_for = 0
        self.fall_count = 0
        self.jump_count = 0

        # Sound timers
        self.scream_lapse = 0
        self.pain_lapse = 0
        self.laugh_lapse = 0
        self.last_scream_lapse = 0
        self.last_pain_lapse = 0
        self.last_laugh_lapse = 0
        
        # Modes
        self.posted = False # An entity never walks away from that position no matter what
        self.patroller = True # Has a range of wandering distance
        self.mad = False
        self.auto_attack = False
        self.avenger = False  # Deals with one player until dead or gone
        self.ignore_objects = True # Mainly for player, when there is no enemy in range, they target decor
        self.bored = False # When bored, enemy starts destroying decor
        self.is_there = False # Friends in range
        
        # Status Values
        self.kills = 0
        self.health = 100
        self.max_health = self.health
        self.vitality = 1
        self.hit_count = 0
        self.count = 0
        
        # Treasure
        self.emerald_coins = 11110
        self.gold_coins = 11110
        self.ruby_coins = 11110
        self.pearl_coins = 11110

        # Shop (see scripts/shop_effects.py)
        self.upgrades = {}
        self.bought = {}                     # {shop item id: times bought this run} (charm-kind prices rise with it)
        self.charms, self.dashes = C_START_CHARMS, C_START_DASHES   # consumable stock, see data/charms.py
        self.traps = 0                       # Homing Trap kits carried (shop item 'homing_trap', objects/arrow_trap.py)
        self.mods = {}                       # Entity Editor tweaks (entities/mods.py); empty = a stock entity
        self.boss_title = ""
        self.extra_effects = {}              # raw shop effects granted by the Entity Editor (enemies only)
        self.charms_used = self.dashes_used = self.quick_buys = 0   # counters for achievements (WS-D)
        # Dash time bar (scripts/dash_bar.py): None = full, created on first use
        self.dash_energy = None
        self.dash_held, self.dash_pulse, self.dash_age, self.dash_idle = False, 0.0, 0.0, 0.0
        self.dash_timed = False
        self.second_winds_used = 0           # free revives spent this run (Second Wind)
        self.shield_left = 0                 # Shield Bubble hits left this floor
        self.charm_session = None            # an active charm-mode session, see scripts/charm_mode.py
        self.boosts = set()
        self._shop_applied = {}
        self.shop_stats = {}                 # derived counts (arrows, minimap level ...), see shop_effects.STAT_KEYS
        self.damage_taken_mult = 1.0
        self.lifesteal = 0.0
        self.coin_magnet = 0
        self.grace_until = 0                 # pygame ticks; can't be hurt before this (revive / restart)
        self.is_boss = False                 # set by the boss objective; draws a gold marker

        # Per-floor stats for achievements (reset by death_rules.begin_level)
        self.damage_this_level = 0.0
        self.lava_seconds = 0.0
        self.kill_times = []

        # Strength
        self.knockback_power = 200
        self.attack_power = 20
        self.attack_delay = 1

        # Times and Timers
        self.wandering_timer = 0
        self.wandering_time = 0
        self.evade_time = 0
        self.evade_max_time = 0

        self.initiate_ranges_and_limits()

        # Decisions
        self.decision = 'left'
        self.choice = 'wl'
        self.jump_choice = 'single'

        # Bombs
        self.bomb_limit = 5
        self.wait = 0

        # Projectiles knowledge
        self.clear_shot_up = 0
        self.clear_shot_down = 0
        self.missed = 0
        self.clear_shot_range = 0
        
        # Platform states
        self.stepping_on_platform = False
        self.riding_platform = None
        
        # Liquid Zones
        self.oxygen = 100
        self.max_oxygen = 100
        self.zone = None
        self.swim_strength = 300
        
        # Pathfinding
        self.path = []
        self._path_timer = 0.0   # seconds since last A* call
        self._path_target_pos = None  # (x, y) of target when path was computed
        self.completed_path = 0

        # Dash history
        self.startx = 0
        self.starty = 0
        self.history = []

        self.teleport_x = True

    def initiate_ranges_and_limits(self):
        # Ranges
        self.patrol_range_x = 1000
        self.patrol_range_y = 500
        
        self.chase_range = 10
        self.chase_bottom = 50
        self.chase_top = 50
        self.chase_space = 100
        
        self.evade_range = 43

        self.attack_que = 3
        self.attack_delay = 0.1

        self.acquire_up = 300
        self.acquire_down = 300
        self.acquire_range = 1000

        self.attack_up = 50
        self.attack_down = 50
        self.attack_range = 50

    def personalise(self, times=1):
        # Shop bonuses are taken out while the base stats are rebuilt below
        # (class stats, then the level's entity settings) and put back at the end.
        if self.type == "player":
            strip_loadout(self)

        self.title = f'The {self.color} {self.name} number {self.entity_id}'
        self.rect = pygame.Rect(self.rect.x, self.rect.y, 43, 37)
        
        self.initiate_ranges_and_limits()
        
        if self.type == "player":
            self.activities = {'wl', 'wr', 'rl', 'rr', 'il', 'ir', 'j'}

        elif self.type == "enemy":
            self.activities = {'wl', 'wr', 'rl', 'rr', 'il', 'ir', 'j', 'laugh', "confused", "bored", 'jwl', 'jwr', 'jrl', 'jrr', 'jil', 'jir'}

        if self.name == "Archer":
            if times == 1:
                self.health = 100
                
            # Ranges
            self.evade_range = 50

            self.attack_que = 5
            self.attack_delay = 0.1

            self.acquire_up = 500
            self.acquire_down = 500
            self.acquire_range = 1000

            self.attack_up = 300
            self.attack_down = 300
            self.attack_range = 600


        if self.name == "TNT":
            if times == 1:
                self.health = 100

            # Ranges
            self.evade_range = 50

            self.attack_que = 2
            self.attack_delay = 0.1

            self.acquire_up = 500
            self.acquire_down = 500
            self.acquire_range = 1000
            
            self.attack_up = 300
            self.attack_down = 300
            self.attack_range = 600

        elif self.name == "Warrior":
            if times == 1:
                self.health = 80
            
            self.initiate_ranges_and_limits()
            
            if self.type == 'player':
                self.attack_power = 15
            else:
                self.attack_power = 4

            # Ranges
            self.evade_range = 50

            self.attack_que = 3
            self.attack_delay = 0.1

            self.acquire_up = 500
            self.acquire_down = 500
            self.acquire_range = 1000

            self.attack_up = 50
            self.attack_down = 50
            self.attack_range = 50

        elif self.name == "Pawn":
            if times == 1:
                self.health = 50
            
            self.initiate_ranges_and_limits()

            if self.type == 'player':
                self.attack_power = 9
            else:
                self.attack_power = 2.5

            # Ranges
            self.evade_range = 50

            self.attack_que = 3
            self.attack_delay = 0.1

            self.acquire_up = 500
            self.acquire_down = 500
            self.acquire_range = 1000

            self.attack_up = 50
            self.attack_down = 50
            self.attack_range = 50

        elif self.name == "Torch":
            if times == 1:
                self.health = 65

            self.initiate_ranges_and_limits()

            if self.type == 'player':
                self.attack_power = 12
            else:
                self.attack_power = 3

            # Ranges
            self.evade_range = 50

            self.attack_que = 3
            self.attack_delay = 0.1

            self.acquire_up = 500
            self.acquire_down = 500
            self.acquire_range = 1000

            self.attack_up = 50
            self.attack_down = 50
            self.attack_range = 50

        self.game.personalise(self, times)

        if self.type == "player":
            apply_loadout(self)
    
    def update(self) -> None:
        if 'attack_' in self.sprite_sheet and self.name == 'Archer':
            self.sprite_sheet = 'attack'

        image_key = (self.name, self.sprite_sheet)  # Round to avoid excessive keys
        
        if image_key not in Assets.ENEMY_RECT_SPRITES:
            sprites = self._resolve_sprites(self.sheet_name)
            sprite = sprites[self.sprite_index]    
        
        # Use cached image if available
        if image_key in Assets.ENEMY_RECT_SPRITES:
            self.mask, size = Assets.ENEMY_RECT_SPRITES[image_key]

        self.morex = 0
        self.morey = 70
        
        if self.name == 'Warrior':
            self.morex = 76

        elif self.name == 'Torch':
            self.morex = 76

        elif self.name == 'TNT':
            self.morex = 76

        elif self.name == 'Pawn':
            self.morex = 80

        elif self.name == 'Archer':
            self.morex = 75

        if self.death:
            self.morey = 0
            self.morex = 0

        if image_key in Assets.ENEMY_RECT_SPRITES:
            self.rect.size = size
        else:
            self.rect = sprite.get_rect(topleft=self.rect.topleft)

        if image_key not in Assets.ENEMY_RECT_SPRITES:
            self.mask = pygame.mask.from_surface(sprite) # this process will need to be cached too just like the rects
        
        if image_key not in Assets.ENEMY_RECT_SPRITES:
            Assets.ENEMY_RECT_SPRITES[image_key] = self.mask, self.rect.size
        
        self.eye_range = pygame.Rect(self.rect.x - self.acquire_range / 2, self.rect.y - self.acquire_up, self.acquire_range, self.acquire_up + self.acquire_down)
        
        '''
        self.eye_range = self.rect.copy()
        self.eye_range.size = (1000, 1000)
        self.eye_range.x -= 500
        self.eye_range.y -= 500
        '''

    def get_sprite_sheet_name(self) -> str:
        """Get sprite sheet name based on entity state."""
        # Check if entity is attacking
        if self.attacking:
            if self.type == 'player':
                self.attack()
                self.duration += 1

            # Handle Archer's attack
            if self.name == 'Archer':
                if self.sprite_index == 1:
                    playit("pull_bow_string", self)
                return self.get_archer_attack_sprite_sheet()
            
            # Handle Pawn's attack on damagable objects
            elif self.target and self.target.nature == 'damageable_object' and self.name == "Pawn":
                return 'attack_2'
            
            # Default attack sprite sheet
            else:
                return 'attack_1'
        
        # Check if entity is running
        elif self.x_vel != 0:
            if self.type == 'player':
                if self.x_vel > 0:
                    self.move_right(self.x_vel)
                else:
                    self.move_left(abs(self.x_vel))
            return 'run'
        
        # Default idle sprite sheet
        else:
            return 'idle'

    def get_archer_attack_sprite_sheet(self) -> str:
        """Get sprite sheet name for Archer's attack."""

        start_pos = (self.rect.x, self.rect.y)
        if self.target:
            target_pos = (self.target.rect.x, self.target.rect.y)
        else:
            self.feelings.add('what')

            return 'attack_270'
            direction = 1 if self.direction == 'right' else -1
            big = max(10 * direction, 100 * direction)
            small = min(10 * direction, 100 * direction)
            target_pos = (self.rect.x + random.randint(small, big), self.rect.y + random.randint(-100, 100))

        time_to_hit = 1
        gravity = 9.8
        degree = 0

        dx = target_pos[0] - start_pos[0]
        dy = target_pos[1] - start_pos[1]
        
        true_distance = math.sqrt(dx ** 2 + dy ** 2)
        if true_distance == 0:
            # Handle division by zero
            return 'attack_270'
        
        x_vel = dx / time_to_hit
        y_vel = (dy - 0.5 * gravity * time_to_hit ** 2) / time_to_hit

        # Calculate degree
        degree, _ = get_degree(x_vel, y_vel, degree)

        # Determine sprite sheet based on angle
        for angle_range, sprite_sheet in SPRITE_SHEET_ANGLES.items():
            if angle_range[0] > angle_range[1]:
                if degree > angle_range[0] or degree <= angle_range[1]:
                    return sprite_sheet
            elif angle_range[0] <= degree < angle_range[1]:
                return sprite_sheet

        # Default sprite sheet
        return 'attack_270'

    def zone_process(self):
        if not self.in_screen or not self.zone:
            return
        
        if random.random() < 0.05:
            if self.zone.water_type == "normal":
                self.game.bubbles.append(Bubble(self.rect.centerx, self.rect.bottom, game=self.game))
                self.game._draw_list_dirty = True
            elif self.zone.water_type == "toxic":
                self.game.bubbles.append(
                    Bubble(self.rect.centerx, self.rect.bottom, color=(100, 255, 100), game=self.game))
                self.game._draw_list_dirty = True
            elif self.zone.water_type == "healing":
                self.game.bubbles.append(
                    Bubble(self.rect.centerx, self.rect.bottom, color=(100, 255, 100), game=self.game))
                self.game._draw_list_dirty = True
            elif self.zone.water_type == "lava":
                self.game.bubbles.append(
                    Bubble(self.rect.centerx, self.rect.bottom, color=(255, 100, 0), game=self.game))
                self.game._draw_list_dirty = True

        if self.fall_count >= 0.3:
            splash_color = {
                "normal": (50, 50, 255, 180),
                "current": (100, 100, 255, 180),
                "toxic": (50, 155, 50, 180),
                "healing": (100, 255, 100, 180),
                "lava": (255, 75, 0, 180)
            }.get(self.zone.water_type, (180, 220, 255, 180))
            self.game.splashes.extend([Splash(self.rect.centerx, self.zone.rect.top, color=splash_color, game=self.game) for i in range(10)])
            playit("splash", self)
            self.game._draw_list_dirty = True

    def manage(self) -> None:
        self.scream_lapse += self.game.dt
        self.pain_lapse += self.game.dt
        self.laugh_lapse += self.game.dt

        self.current_speed = self.speed
        self.current_gravity = Settings.GRAVITY
        self.current_jump = self.jump_vel

        if self.zone:
            self.current_jump = self.swim_strength
            self.current_speed = self.swim_strength
            self.zone.affect(self)

        mods_rt.tick(self)
        if self.health <= 0 and mods_rt.revive(self):
            pass
        if self.health <= 0:
            self.health = 0
            self.death = True

        self.y_vel += (self.current_gravity * self.mass) * self.game.dt
    
        self.collide()

        if not self.dead:
            hunt = True
            if self.target:
                if self.target.death or self.target.dead:
                    self.has_target = False
                    self.target = None
                else:
                    if self.type == "enemy":
                        if self.target.type == "player":
                            if self.in_proximity(self.target):
                                hunt = False
                                self.bored = False
                        elif self.in_proximity(self.target):
                            self.bored = False
                            self.wandering_time = 0
            else:
                self.has_target = False
                self.target = None
    
            '''for friend in self.friends:
                if friend in self.target_list:
                    self.target_list.remove(friend)
            '''
            
            nearby = []            
            if hunt:
                nearby = self.get_objects(self.game.entities_map, self.eye_range, 0)
            
            if not self.ignore_objects or self.bored:
                deco = self.get_objects(self.game.damageable_objects_map, self.eye_range, 0)
                self.acquire_target(nearby, deco)
            else:
                if nearby:
                    self.acquire_target(nearby)
                
        if self.death or self.dead or self.health <= 0:
            self.has_target = False
            self.target = None

        if self.zone:
            self.zone_process()
            self.fall_count = 0

        if not self.dead:
            if self.target:
                _manage_pathfinding(self)
                if self.type == "enemy":
                    if not self.posted:
                        if self.missed > 4:
                            self.clear_shot_range = min(self.attack_range - 64, 64 * (self.missed - 4))
                        elif self.missed > 9:
                            self.clear_shot_up = min(self.attack_up - 64, 64 * (self.missed - 9))
                            self.clear_shot_down = min(self.attack_down - 64, 64 * (self.missed - 9))
                    
                    if not self.path and self.name not in ["TNT", "Archer"]:
                        self.has_target = False
                        self.target = None

            if not self.target:
                # Clear space
                self.path = []
                self._path_timer      = 0.0
                self._path_target_pos = None
                
                # To reset to a distance where he can get a shot
                self.clear_shot_range = 0
                self.clear_shot_up = 0
                self.clear_shot_down = 0
                self.missed = 0

            self.think()

    
    def _resolve_sprites(self, sheet_name: str):
        """
        Return the sprite list for (self.name, self.color, sheet_name).

        Checks self._sprite_cache first.  Only walks Assets.ENEMY_SPRITES on a
        cache miss — i.e. the first time this combination is seen.

        The cache lives on the entity instance so it is automatically garbage-
        collected when the entity is removed.  No manual invalidation needed
        because name and color never change mid-life for an entity.

        Parameters
        ----------
        sheet_name : the full key into character_sprites, e.g. 'run_right'

        Returns
        -------
        list of pygame.Surface
        """
        cache_key = (self.name, self.color, sheet_name)

        if cache_key not in CACHED_ENTITY_IMAGES:
            # Cache miss — walk the Assets dict once and store the result.
            # This branch runs at most once per unique (name, color, sheet_name)
            # combination for the lifetime of the entity.
            try:
                if self.death or self.dead:
                    CACHED_ENTITY_IMAGES[cache_key] = Assets.DEAD_SPRITES[sheet_name]
                else:
                    cache_assets(cache_key, index=None)  # index=None returns the full list of sprites
            except KeyError:
                # Sheet doesn't exist — return empty list so caller can handle it
                # gracefully (same behaviour as before, but now explicit).
                 CACHED_ENTITY_IMAGES[cache_key] = []

        return CACHED_ENTITY_IMAGES[cache_key]

    def update_sprites_len(self):
        if self.death or self.dead:
            self.sprites_len = Assets.SHEET_LENS[self.sheet_name]
        else:
            self.sprites_len = Assets.SHEET_LENS[self.name][self.sheet_name]

    def update_sprite(self) -> None:
        if not self.dead:
            if not self.death:
                if self.type == 'enemy':
                    if self.hit_wall_for > 20 and self.jump_count < 2 and self.chasing:
                        self.jump()

                """Update sprite sheet."""
                self.sprite_sheet = self.get_sprite_sheet_name()
                
                if not (self.name == 'Archer' and 'attack' in self.sprite_sheet):
                    # Try to get sprite sheet with direction
                    self.sheet_name = self.sprite_sheet + "_" + self.direction
                
                # Fallback for Archer
                else:
                    self.sheet_name = self.sprite_sheet

                self.update_sprites_len()
            else:

                # PLAYER DEATH EVENT
                if not self.sprite_sheet == 'death' and not self.sprite_sheet == 'sink':
                    if self.name == "Warrior":
                        playit("drop", self)
                    
                    playit('death_2', self)

                    # A fallen player spills their coins (see scripts/death_rules.py)
                    if self.type == "player":
                        drop_wallet(self)

                    # CO-OP: a fallen enemy sometimes leaves a power-up (scripts/coop_loot.py)
                    coop_loot.maybe_drop(self.game, self)

                    # DROP COINS
                    for i in range(self.value + shop_drop_bonus(self.game, self.value)):
                        treasure = Treasure(self.rect.centerx, self.rect.centery, 'yellow', self.game, 'dropped')
                        treasure.rect.center = self.rect.center
                        self.game.treasure_list.append(treasure)
                        
                    self.game._draw_list_dirty = True
                    
                    self.value = 0
                    self.animation_count = 0
                    self.sprite_index = 0
                    self.sprite_sheet = 'death'
                    self.sheet_name = self.sprite_sheet + "_" + self.direction
                    self.update_sprites_len()

                if self.sprite_index == self.sprites_len - 1 and self.sprite_sheet == 'death':
                    self.sprite_sheet = 'sink'
                    self.animation_count = 0
                    self.sprite_index = 0
                
                if self.sprite_index == 5 and self.sprite_sheet == 'sink':
                    if self.fall_count < 2 or self.rect.y >= 2000:
                        if not self.dead:
                            self.game.dead_entities.append(self)
                            
                        self.dead = True
            
            self.time_accumulator += self.game.dt
            
            if self.animation_count == 0 and self.sprite_index != 0:
                self.sprite_index = 0
                self.time_accumulator = 0
            
            if (self.in_screen or self.death or 'attack' in self.sprite_sheet) and self.time_accumulator >= self.frame_duration:
                self.sprite_index = (self.sprite_index + 1) % self.sprites_len
                self.time_accumulator = 0
                self.animation_count += 1
    
            if self.sprite_index > self.sprites_len - 1:
                self.sprite_index = 0

            if self.sprite_index >= self.sprites_len - 1 and self.type == 'player':
                self.duration = 0
                self.attacking = False

            if self.attacking:
                self.wait += self.game.dt

            self.update()

        else:
            self.sheet_name = 'death_' + self.direction
            self.update_sprites_len()

            self.sprite_index = self.sprites_len - 1
            
            self.update()

        if not self.dead:
            self.update_thoughts_and_feelings()

    def update_sprite_client(self):
        try:
            sheet_name = self.sheet_name
            self.update_sprites_len()
            
            if self.sprite_index > self.sprites_len - 1:
                self.sprite_index = 0

        except Exception as e:
            print(e, " in update_sprite_client ", self.name, self.death, self.dead, self.sheet_name, self.sprites_len)

        self.update()

    def update_thoughts_and_feelings(self) -> None:

        self.is_there = False
        if self.friends and self.targets_in_range:
            for friend in self.friends:
                if friend in self.targets_in_range:
                    self.is_there = True
                    
                    self.activities.add('chat')

                    friend.activities.add('chat')
                    
                    if 'chat' in friend.feelings:
                        self.feelings.add('chat')

        if not self.is_there:
            self.activities.discard('chat')
            self.feelings.discard('chat')
            
        if self.health <= 25:
            self.feelings.add('tired')

        else:
            self.feelings.discard('tired')

        if self.fall_count > 0.75:
            self.feelings.add('huh')

        else:
            self.feelings.discard('huh')

        if self.target:
            self.feelings.add('kill')

            self.feelings.discard('confusion')
            self.feelings.discard('what')

        else:
            self.feelings.discard('kill')

        if self.chasing or self.evading:
            self.feelings.add('nerve')

        else:
            self.feelings.discard('nerve')

    def update_health_bar(self) -> tuple[int, Any]:

        bar = min(100, max(0, int(self.health)))

        # Health Bar
        if self.health <= 25:
            if self.game.seconds % 3 == 0:
                color = (0, 0, 0, 0) #Settings.BLACK
            else:
                color = Settings.RED

        elif self.health <= 50:
            color = Settings.ORANGE
        elif self.health <= 75:
            color = Settings.YELLOW
        elif self.health <= 100:
            color = Settings.GREEN
        else:
            color = Settings.PURPLE

        return bar, color

    def draw_health_bar(self, win, offset_x, offset_y, zoom=None) -> pygame.Rect:

        bar, color = self.update_health_bar()

        health_bar_rect = pygame.Rect(self.rect.centerx - (bar / 2), self.rect.y - 20, bar, 12)

        if color != (0, 0, 0, 0):
            pygame.draw.rect(win, color, (
                (health_bar_rect.x - offset_x) * zoom, (health_bar_rect.y - offset_y) * zoom,
                health_bar_rect.width * zoom,
                health_bar_rect.height * zoom), border_radius=20)

            zoom_key = (int(self.health), color)

            # Use cached image if available
            if zoom not in self.game.CACHED_ENTITY_ZOOM_IMAGES:
                self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom] = OrderedDict()
            
            if zoom_key in self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom]:
                scaled_image = self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom][zoom_key]
                width, height = scaled_image.get_size()
            else:    
                text = Settings.health_font.render(f"{int(self.health)}", True, color).convert_alpha()
                width = text.get_width()
                height = text.get_height()
                scaled_size = (
                    round(width * zoom),
                    round(height * zoom)
                )
                scaled_image = pygame.transform.scale(text, scaled_size)
                width, height = scaled_image.get_size()

                self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom][zoom_key] = scaled_image
                _lru_touch(self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom], zoom_key, self.game.ENTITY_ZOOM_CACHE_MAX_LEVELS)
                
            win.blit(scaled_image,
                    ((health_bar_rect.right + 5 - offset_x) * zoom, (health_bar_rect.y - offset_y) * zoom))

        if self.is_boss:
            # a gold diamond over the bar, so the boss can be told from its minions
            cx = (health_bar_rect.centerx - offset_x) * zoom
            cy = (health_bar_rect.y - offset_y - 18) * zoom
            r = 9 * zoom
            diamond = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
            pygame.draw.polygon(win, (255, 210, 70), diamond)
            pygame.draw.polygon(win, (20, 10, 14), diamond, max(1, int(2 * zoom)))
            title = getattr(self, "boss_title", "")
            if title:
                key = ("boss_title", title, zoom)
                plate = self.game.CACHED_ENTITY_ZOOM_IMAGES.setdefault(zoom, OrderedDict()).get(key)
                if plate is None:
                    raw = Settings.health_font.render(title.upper(), True, (255, 226, 140))
                    shadow = Settings.health_font.render(title.upper(), True, (20, 10, 14))
                    plate = pygame.Surface((raw.get_width() + 2, raw.get_height() + 2), pygame.SRCALPHA)
                    plate.blit(shadow, (2, 2))
                    plate.blit(raw, (0, 0))
                    plate = pygame.transform.smoothscale(plate, (max(1, int(plate.get_width() * zoom)), max(1, int(plate.get_height() * zoom))))
                    self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom][key] = plate
                win.blit(plate, (cx - plate.get_width() / 2, cy - r - plate.get_height() - 2 * zoom))

        return health_bar_rect

    def show_thoughts_and_feelings(self, health_bar_rect, win, offset_x, offset_y, zoom=None) -> None:
        for i, feeling in enumerate(self.feelings):
            zoom_key = (feeling)

            # Use cached image if available
            if zoom not in self.game.CACHED_ENTITY_ZOOM_IMAGES:
                self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom] = OrderedDict()
            
            if zoom_key in self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom]:
                scaled_image = self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom][zoom_key]
            
            else:
                sprite = Assets.EXPRESSION_SPRITES[feeling]
                width = sprite.get_width()
                height = sprite.get_height()
                scaled_size = (
                    round(width * zoom),
                    round(height * zoom)
                )
                scaled_image = pygame.transform.scale(sprite, scaled_size)
                
                self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom][zoom_key] = scaled_image
                _lru_touch(self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom], zoom_key, self.game.ENTITY_ZOOM_CACHE_MAX_LEVELS)
                
            win.blit(scaled_image,
                     ((health_bar_rect.x - offset_x - ((i + 1) * 20)) * zoom, (health_bar_rect.y - offset_y) * zoom))

    def draw(self, see_through=False, window=None, cam=(0, 0), zoom=None) -> None:
        zoom = self.game.zoom if not zoom else zoom
        zoom = round(zoom, 2)
        if self.type == 'enemy':
            self.zoom = zoom

        # combat_fx: dash i-frame start / enemy attack wind-up detection
        if not self.dead:
            combat_fx.watch(self)

        # Use game offset if None is provided
        if not cam:
            offset_x = self.game.offset_x
            offset_y = self.game.offset_y
        else:
            offset_x = cam[0]
            offset_y = cam[1]

        # Display on game window if None is provided
        if not window:
            window = self.game.window

        if not self.dead:
            if self.game.DEBUGGING_MODE:
                if self.game.debug.get('path', False): 
                    if self.path and self.target:
                        for path in self.path:
                            scaled_rect = pygame.Rect(
                                round((path.rect.x - offset_x) * zoom),
                                round((path.rect.y - offset_y) * zoom),
                                round(path.rect.width * zoom),
                                round(path.rect.height * zoom)
                            )

                            pygame.draw.rect(window, self.color, scaled_rect)

                    if self.type == 'player' and self.target and self.game.env_ready:
                        end = get_closest_node(self, self.target.rect)
                        if end:
                            scaled_rect = pygame.Rect(
                                round((end.rect.x - offset_x) * zoom),
                                round((end.rect.y - offset_y) * zoom),
                                round(end.rect.width * zoom),
                                round(end.rect.height * zoom)
                            )
                            pygame.draw.rect(window, (255, 0, 0), scaled_rect)
            
        if self.game:
            if self.game.DEBUGGING_MODE:
                if self.game.debug.get('range', False):
                    rect = self.eye_range
                    # Scale player rect
                    scaled_rect = pygame.Rect(
                        round((rect.x - offset_x) * zoom),
                        round((rect.y - offset_y) * zoom),
                        round(rect.width * zoom),
                        round(rect.height * zoom)
                    )
                    pygame.draw.rect(window, self.color, scaled_rect)
        
        if not self.dead and not self.death:
            zoom_key = (
                self.name, self.color, 
                self.sheet_name,
                self.sprite_index, self.direction
            )
        else:
            zoom_key = (
                self.sheet_name, self.sprite_index,
                self.direction #, self.death, self.dead,
            )
            
        # Use cached image if available
        if zoom not in self.game.CACHED_ENTITY_ZOOM_IMAGES:
            self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom] = OrderedDict()
        
        if zoom_key in self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom]:
            scaled_image = self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom][zoom_key]
        else:
            skip = False
            if not self.dead and not self.death and zoom == 1:
                zoom_key = (self.name, self.color, self.sheet_name)
                if zoom_key in CACHED_ENTITY_IMAGES:
                    try:
                        scaled_image = CACHED_ENTITY_IMAGES[zoom_key][self.sprite_index]
                        skip = True
                    except:
                        print(f"len {len(CACHED_ENTITY_IMAGES[zoom_key])}.... {zoom_key} {self.sprite_index}")
                else:
                    zoom_key = (
                        self.name, self.color, 
                        self.sheet_name,
                        self.sprite_index, self.direction
                    )

            if not skip:
                sprites = self._resolve_sprites(self.sheet_name)
                sprite = sprites[self.sprite_index]

                scaled_size = (
                    round(sprite.get_width() * zoom),
                    round(sprite.get_height() * zoom)
                )
                scaled_image = pygame.transform.scale(sprite, scaled_size)
                
                self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom][zoom_key] = scaled_image
                _lru_touch(self.game.CACHED_ENTITY_ZOOM_IMAGES[zoom], zoom_key, self.game.ENTITY_ZOOM_CACHE_MAX_LEVELS)
                
        # Position centered on player
        draw_x = round((self.rect.x - offset_x - self.morex) * zoom)
        draw_y = round((self.rect.y - offset_y - self.morey) * zoom)

        if self.dashing:
            if self.x_vel == 0 or self.hit_wall_for > 0.05:
                self.dashing = False
                self.startx = self.rect.x
                self.history = []

            else:
                if abs(self.rect.x - self.startx) > self.rect.width / 2:
                    self.history.append(
                        {
                            "pos": self.rect.topleft,
                            "dir": self.direction,
                            "key": zoom_key,
                            1: self.sheet_name,
                            2: self.sprite_index,
                            3: (self.death or self.dead),
                            'name': self.name,
                            'color': self.color
                        }
                    )
                    self.startx = self.rect.x
                    if getattr(self, "dash_timed", False):
                        del self.history[:-12]              # the bar, not the trail, decides how long a dash lasts

                for i, dat in enumerate(self.history[::-1]):
                    if dat[3]:
                        image = Assets.DEAD_SPRITES[dat[1]][dat[2]]
                    else:
                        image = cache_assets((dat['name'], dat['color'], dat[1]), index=dat[2])

                    image = create_cache_img(self.game.CACHED_ENTITY_ZOOM_IMAGES, dat["key"], image, zoom, index=dat[2]).copy()
                    image.set_alpha(255 - i * 30)
                    
                    drawx = round((dat["pos"][0] - offset_x - self.morex) * zoom)
                    drawy = round((dat["pos"][1] - offset_y - self.morey) * zoom)
                    window.blit(image, (drawx, drawy))

                    if i > 10:
                        if getattr(self, "dash_timed", False):
                            break                           # enough afterimages drawn; the dash carries on
                        self.dashing = False
                        self.startx = self.rect.x
                        self.history = []
                        break
        else:
            self.startx = self.rect.x
            self.history = []

        window.blit(combat_fx.tint(self, scaled_image) if not self.dead else scaled_image, (draw_x, draw_y))

        if not self.dead and not self.death and Burn.active(self):
            Burn.draw(window, self, offset_x, offset_y, zoom)

        if not self.dead:
            health_bar_rect = self.draw_health_bar(window, offset_x, offset_y, zoom)
            self.show_thoughts_and_feelings(health_bar_rect, window, offset_x, offset_y, zoom)
    