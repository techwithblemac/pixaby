import pygame
from pygame import Rect
from typing import Tuple, Any
from collections import OrderedDict

from ..assets import Assets
from ..settings import Settings
from ..entities.burn import Burn
from ..scripts.physics import PHYSICS
from ..scripts.cache import cache_img, _lru_touch, get_door, get_deco_sprites, get_tree_sprites
from ..scripts.asset_funcs import get_block, pallete_swap

CACHED_OBJECT_IMAGES = {'other': OrderedDict(), 'arrows': OrderedDict()}
CACHED_OBJECT_ZOOMED_IMAGES = OrderedDict()

class Object(PHYSICS):
    GRAVITY = 1
    total = 0

    def __init__(self, x, y, width, height, name=None, game=None):
        super().__init__()
        self.origin_rect = pygame.Rect(x, y, width, height)
        self.rect = pygame.Rect(x, y, width, height)
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.image = None
        self.mask = None
        self.color = (156, 77, 8)

        # Attributes
        self.name = name
        self.type = name

        # Decisions
        if not self.name == "block":
            self.game = game
            self.direction = "left"
            self.decision = 'left'
            self.choice = 'wl'
            self.jump_choice = 'single'
            self.activities = ['wl', 'wr', 'rl', 'rr', 'il', 'ir', 'c', 'j']

        # Status Values
        if not self.name == "block":
            self.kills = 0
            self.hit_count = 0
            self.fall_count = 0
            self.jump_count = 0
            self.hit_wall_for = 0        
            self.on_ground_for = 0
            self.in_air_for = 0
            
        self.health = 50
        
        if not self.name == "block":
            # Strength
            self.knockback_power = 10
            self.attack_power = 10

            # Times and Timers
            self.timer = 0
            self.time = 0

        # Sprites
        self.sprite_index = 0
        self.image_key = (self.name, )
        # Speeds
        if not self.name == "block":    
            self.animation_count = 0
            self.x_vel = 0
            self.y_vel = 0
            self.speed = 200
            self.jump_vel = -400
            self.walk_speed = 10
            self.acceleration = 50
            self.current_speed = self.speed
            self.current_gravity = Settings.GRAVITY
            self.current_jump = self.jump_vel
            self.duration = 0

        # Status
        self.dead = False
        self.death = False
        
        if not self.name == "block":
            self.hit_wall = False
            self.on_ground = False
            self.attacking = False
            self.hurt = False
        
            # Somethings
            self.activities = ['on', 'off']
            self.degree = 0
            self.title = 'Whookid'    
            self.sprite_sheet = 'idle'
            self.sheet_name = 'idle_left'
            self.oxygen = 100
            self.max_oxygen = 100
            self.sprites = []
        
        self.morex = 0
        self.morey = 0

        self.nature = 'object'
        self.knocking_back = 0
        self.type_name = 'rock_1'
        self.type_size = 'big'
        self.size = 50
        self.zoom = 1

        self.max_health = 100
        
        if not self.name == "block":
            self.zone = None
            self.time_accumulator = 0
            self.frame_duration = 0.1
            self.stuck = False
            self.elapsed = 0
            self.swim_strength = 300

            self._last_sheet_key = None
            self.landed_on = (0, 0)
        
        self.in_screen = False
    
    def personalise(self):
        if "platform" in self.name.lower():
            self.activities = ['onwl', 'onwr', 'onrl', 'onrr', 'offil']

    def return_to_pool(self):
        """
        Default no-op. Pooled objects (Bomb, Arrow, Fire — see objects.py /
        pooling.py) override this to hand themselves back to their object
        pool instead of being dropped for garbage collection. Safe to call
        on any Object subclass; only pooled ones do anything with it.
        """
        pass

    def hit(self, obj):
        self.health -= obj.attack_power
        self.animation_count = 0
        self.hurt = True
    
    def _resolve_sprites(self, sheet_name: str=""):
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

        cache_key = (self.name, self.sprite_sheet, self.sheet_name, self.direction, self.type, self.dead, self.death)
        
        if self.name == "bomb":
            
            if self.death or self.dead:
                cache_key = (self.name, self.sheet_name, self.death) 
            else:
                cache_key = (self.name, self.sheet_name, self.direction)

        elif self.name == 'arrow' and self.type == 'weapon':
            cache_key = (self.name, self.sheet_name)
        
        elif self.type == "fire":
            cache_key = (self.type, self.sheet_name)
        
        elif self.type == "tree":
            cache_key = (self.type, self.sheet_name, getattr(self, "deco_biome", "1"))
        
        elif self.type == "treasure":
            cache_key = (self.type, self.sheet_name)

        elif self.type == "deco":
            cache_key = (self.type, getattr(self, "deco_biome", "1"))

        elif self.type == "door":
            cache_key = (self.type, self.name)

        if cache_key not in self.game.object_sprite_cache:
            # Cache miss — walk the Assets dict once and store the result.
            # This branch runs at most once per unique (name, color, sheet_name)
            # combination for the lifetime of the entity.
            try:
                if self.name == "bomb":
                    
                    if self.death or self.dead:
                        sprites = Assets.EXPLOSION_SPRITES[self.sheet_name]
                    else:
                        sprites = Assets.BOMB_SPRITES[self.sheet_name]

                elif self.name == 'arrow' and self.type == 'weapon':
                    sprites = Assets.ARROW_SPRITES[self.sheet_name]            
                
                elif self.type == "fire":
                    sprites = Assets.FIRE_SPRITES[self.sheet_name]
                
                elif self.type == "tree":
                    sprites = get_tree_sprites(getattr(self, "deco_biome", "1"))[self.sheet_name]
                
                elif self.type == "treasure":
                    sprites = Assets.GEM_SPRITES[self.sheet_name]

                elif self.type == "deco":
                    sprites = get_deco_sprites(getattr(self, "deco_biome", "1"))
                
                elif self.type == "door":
                    sprites = get_door(self.name)

                self.game.object_sprite_cache[cache_key] = sprites
            except KeyError:
                # Sheet doesn't exist — return empty list so caller can handle it
                # gracefully (same behaviour as before, but now explicit).
                 self.game.object_sprite_cache[cache_key] = []

        return self.game.object_sprite_cache[cache_key]

    def get_key(self):
        if self.name == 'water':
            image_key = (self.name, self.water_type, self.color, (self.rect.width, self.rect.height),
                            self.sprite_sheet, self.sheet_name, self.sprite_index, self.direction)  
                        
        elif self.name == 'platform':
            image_key = (self.name, self.sprite_sheet, self.sheet_name, self.sprite_index, self.width, self.height)
        
        elif self.type == "block":
            image_key = (self.name, self.type_name, self.type_size, self.sprite_index)

        elif self.name == 'arrow' and self.type == 'weapon':
            image_key = (self.sprite_sheet, self.sheet_name, self.sprite_index,
                        int(self.degree), self.dead, self.death)

        elif self.name == 'bomb':
            image_key = (self.name, self.sprite_sheet, self.sheet_name, self.sprite_index, self.direction, self.dead, self.death)

        elif self.type == 'deco':
            image_key = (self.name, self.type, self.sheet_name, getattr(self, "deco_biome", "1"))

        else:
            image_key = (self.name, self.type, self.sprite_sheet, self.sheet_name, self.sprite_index, self.direction)

        return image_key
    
    def _place_arrow_tip(self, full_w, full_h, tip_offset, tip_size):
        """Put the arrow's tip hitbox (self.rect) where it belongs for the current angle.

        The arrow really lives at an anchor = the centre of its full sprite. The tip box
        sits at (anchor + how far the tip is from the sprite centre at this angle), so
        when the angle changes the tip moves by the CHANGE in that offset. The old code
        added the new offset on top of the previous one every time the angle changed,
        which made the arrow creep away from where it should be.

        The anchor is a float and follows whatever moved self.rect since the last call
        (physics, stuck-to-block follow, the spawner), so rounding can't build up.
        """
        tip_w, tip_h = tip_size
        off_x = tip_offset[0] + tip_w / 2 - full_w / 2
        off_y = tip_offset[1] + tip_h / 2 - full_h / 2

        anchor = getattr(self, "_tip_anchor", None)
        if anchor is None:
            # first placement: whatever the spawner put in self.rect is the anchor
            ax, ay = self.rect.centerx, self.rect.centery
        else:
            last_x, last_y = self._tip_last_topleft
            ax = anchor[0] + (self.rect.x - last_x)
            ay = anchor[1] + (self.rect.y - last_y)
        self._tip_anchor = (ax, ay)

        self.rect.size = (tip_w, tip_h)
        self.rect.center = (round(ax + off_x), round(ay + off_y))
        self._tip_last_topleft = self.rect.topleft

        # draw() blits the full sprite at rect.topleft - (morex, morey)
        self.morex, self.morey = tip_offset

    def update(self, return_image=False):
        image_key = self.get_key()

        image = None
        tip_offset = None
        
        # Use cached image if available
        if self.name == 'arrow' and self.type == 'weapon':
            if 'arrows' not in CACHED_OBJECT_IMAGES:
                CACHED_OBJECT_IMAGES['arrows'] = OrderedDict()

            if image_key in CACHED_OBJECT_IMAGES['arrows']:
                image, self.mask, rect, tip_offset = CACHED_OBJECT_IMAGES['arrows'][image_key]
        else:
            if 'other' not in CACHED_OBJECT_IMAGES:
                CACHED_OBJECT_IMAGES['other'] = OrderedDict()
                
            if image_key in CACHED_OBJECT_IMAGES['other']:
                image, self.mask, rect = CACHED_OBJECT_IMAGES['other'][image_key]
        
        if not image:
            if self.name == "block":
                image = get_block(self.type_name, self.type_size, self.width, self.height)
            
            elif self.type == "treasure" or self.name == "bomb" or self.type == "tree" or (self.name == 'arrow' and self.type == 'weapon') or self.type == "fire":
                sprites = self._resolve_sprites(self.sheet_name)
                image = sprites[self.sprite_index]
            
            elif self.type == "deco":
                sprites = self._resolve_sprites(self.sheet_name)
                image = sprites[self.sheet_name]
            
            elif self.name == "water":
                image = cache_img(self.rect.size, self.color)
                image.fill(self.color)
                image.set_alpha(50)
            
            elif self.type == "moving_platform":            
                image = cache_img(self.rect.size)
                image.fill(self.color)
            
            elif self.type == "door":
                image = self._resolve_sprites()

            else:
                image = self.image
                
        from_x = 0
        from_y = 0
        photo_width = 64
        photo_height = 64

        n = 0
        n2 = 0
        y = 0

        if self.type == 'deco':
            if self.sheet_name == 'scare_crow':
                from_x = 0
                photo_width = 64
                from_y = 0
                photo_height = 96
                #n = -20

            elif self.sheet_name == 'grass1':
                from_x = 20
                photo_width = 64
                from_y = 20
                photo_height = 64

            elif self.sheet_name == 'grass2':
                from_x = 20
                photo_width = 70
                from_y = 16
                photo_height = 64

            elif self.sheet_name == 'shrub1':
                from_x = 12
                photo_width = 64
                from_y = 25
                photo_height = 64

            elif self.sheet_name == 'shrub2':
                from_x = 17
                photo_width = 64
                from_y = 18
                photo_height = 64

            elif self.sheet_name == 'shrub3':
                from_x = 5
                photo_width = 64
                from_y = 15
                photo_height = 64

            elif self.sheet_name == 'shroom1':
                from_x = 20
                photo_width = 64
                from_y = 24
                photo_height = 64

            elif self.sheet_name == 'shroom2':
                from_x = 17
                photo_width = 64
                from_y = 22
                photo_height = 64

            elif self.sheet_name == 'shroom3':
                from_x = 12
                photo_width = 64
                from_y = 18
                photo_height = 64

            elif self.sheet_name == 'pumpkin1':
                from_x = 10
                photo_width = 64
                from_y = 18
                photo_height = 64

            elif self.sheet_name == 'pumpkin2':
                from_x = 12
                photo_width = 64
                from_y = 20
                photo_height = 64

            elif self.sheet_name == 'bone':
                from_x = 21
                photo_width = 64
                from_y = 22
                photo_height = 64

            elif self.sheet_name == 'exit':
                from_x = 0
                photo_width = 52
                from_y = 0
                photo_height = 96

            elif self.sheet_name == 'arrow':
                from_x = 0
                photo_width = 62
                from_y = 0
                photo_height = 85

        elif self.name == 'fire':

            from_x = 25
            from_y = 20
            photo_width = 128
            photo_height = 128

        elif self.name == 'tree':

            from_x = 80
            from_y = 80
            photo_width = 192
            photo_height = 192

            n = -55
        
        elif self.type == "door":
            n2 = -12

        elif self.name == 'bomb':
            from_x = 20 if not self.death else 84
            from_y = 12 if not self.death else 76
            photo_width = 64 if not self.death else 192
            photo_height = 64 if not self.death else 192
            if self.death:
                #n2 = -10
                n = -10

        elif self.name == 'arrow' and self.type == 'weapon':
            from_x = 0
            from_y = 28
            photo_width = 64
            photo_height = 64

            n = 28
            y = 5
        
        margin_distance_x = from_x * 2
        width_distance = photo_width - margin_distance_x

        margin_distance_y = from_y * 2 - y
        height_distance = photo_height - margin_distance_y

        trimarea = (from_x, from_y, width_distance, height_distance)

        self.morex = from_x - n2
        self.morey = from_y - n

        if (self.type not in {'block', 'treasure', 'moving_platform'}) and (self.name not in {'water', 'platform'}):
            if self.name == 'arrow' and self.type == 'weapon':
                if image_key not in CACHED_OBJECT_IMAGES['arrows']:
                    image = image.subsurface(trimarea)
            
            else:
                if image_key not in CACHED_OBJECT_IMAGES['other']:
                    try:
                        image = image.subsurface(trimarea)
                    except:
                        print(image_key, image.size)

        if self.name == 'arrow' and self.type == 'weapon':
            if image_key not in CACHED_OBJECT_IMAGES['arrows']:
                image = pygame.transform.rotate(image, self.degree)
                
                image_ = pallete_swap(image, (22, 28, 46), (0, 0, 0))
                image_ = pallete_swap(image_, (151, 123, 107), (0, 0, 0))
                image_ = pallete_swap(image_, (239, 225, 171), (0, 0, 0))
                image_ = pallete_swap(image_, (213, 181, 131), (0, 0, 0))
                image_.set_colorkey((0, 0, 0, 0))
                
                full_mask = pygame.mask.from_surface(image_)
                # Where the tip sits within the full rotated sprite, in that
                # sprite's own local coordinates (0, 0) == its top-left.
                local_bound = full_mask.get_bounding_rects()[0]

                # Crop the mask itself down to just the tip so it matches
                # self.rect's size exactly. pygame.sprite.collide_mask only
                # looks at rect.x/rect.y to line the two masks up — it
                # assumes rect.topleft IS the mask's local (0, 0) in world
                # space. Leaving self.mask as the full-sprite mask while
                # self.rect was the tip's bounding box (previous code) broke
                # that assumption, so collisions were checked at the wrong
                # spot relative to where the tip actually is on screen.
                tip_mask = pygame.mask.Mask(local_bound.size)
                tip_mask.draw(full_mask, (-local_bound.x, -local_bound.y))
                self.mask = tip_mask

                # How far the tip's center sits from the full sprite's own
                # center. This is the piece that was missing before: the old
                # code just re-centered the tip box on wherever the rect
                # happened to be, so the tip "snapped" back to the arrow's
                # nominal position every time the image/rotation changed
                # instead of staying offset the way it actually is drawn.
                tip_offset = (local_bound.x, local_bound.y)
                # size-only Rect for the cache: never store self.rect itself, it is live
                # and keeps moving with the arrow that happened to cache this angle.
                rect = pygame.Rect(0, 0, local_bound.w, local_bound.h)

            # Same placement code for a cache miss and a cache hit, so an arrow can't
            # land in a different spot depending on whether its angle was seen before.
            full_w, full_h = image.get_size()
            self._place_arrow_tip(full_w, full_h, tip_offset, rect.size)
            self.rect_2 = self.rect

            # draw() positions the *full* sprite at
            # (self.rect.x - self.morex, self.rect.y - self.morey). Since
            # self.rect is now the tip's own position, morex/morey must be
            # the tip's offset from the full sprite's top-left, or the
            # sprite renders shifted away from where its hitbox actually is.
            self.morex, self.morey = tip_offset

            image = image        


        else:
            if image_key not in CACHED_OBJECT_IMAGES['other']:
                self.rect = image.get_rect(topleft=self.rect.topleft)
            else:
                self.rect.size = rect.size

        if self.name == 'arrow' and self.type == 'weapon':
            if image_key not in CACHED_OBJECT_IMAGES['arrows']:
                CACHED_OBJECT_IMAGES['arrows'][image_key] = image, self.mask, rect, tip_offset
                _lru_touch(CACHED_OBJECT_IMAGES['arrows'], image_key, self.game.OBJECT_IMAGES_ARROWS_CAP)
                
        else:
            if image_key not in CACHED_OBJECT_IMAGES['other']:
                self.mask = pygame.mask.from_surface(image)
                CACHED_OBJECT_IMAGES['other'][image_key] = image, self.mask, self.rect
                _lru_touch(CACHED_OBJECT_IMAGES['other'], image_key, Settings.OBJECT_IMAGES_OTHER_CAP)
        
        self.image_key = image_key
        
        if return_image:
            return image

    def update_sprite_client(self):
        try:
            if self.name == "block" or self.type == "deco" or self.name == "water":
                self.update()
                return
            
            if self.name == "bomb":
                sheet_name = f"{self.sheet_name}_{self.dead}_{self.death}"
            else:
                sheet_name = self.sheet_name

            # OPT-6: only resolve from Assets when the key actually changed
            if sheet_name != self._last_sheet_key:
                self.sprites         = self._resolve_sprites(self.sheet_name)
                self._last_sheet_key = sheet_name
            
            if self.sprite_index > len(self.sprites) - 1:
                self.sprite_index = 0

            self.image = self.sprites[self.sprite_index]

        except Exception as e:
            print(e, " in update_sprite_client ", self.name, self.sheet_name)

        self.update()
        
    def update_health_bar(self) -> tuple[int, Any]:
        bar = int(self.health)

        # Health Bar
        if self.health <= 25:
            color = Settings.RED
        elif self.health <= 50:
            color = Settings.ORANGE
        elif self.health <= 75:
            color = Settings.YELLOW
        elif self.health <= 100:
            color = Settings.GREEN
        else:
            color = Settings.PURPLE
            bar = 100

        return bar, color

    def draw_health_bar(self, win, offset_x, offset_y, zoom=None) -> Rect:

        bar, color = self.update_health_bar()
        bar = 20
        health_bar_rect = pygame.Rect(self.rect.centerx - (bar / 2), self.rect.y - 20, bar, 10)

        pygame.draw.rect(win, color, (
            (health_bar_rect.x - offset_x) * zoom, (health_bar_rect.y - offset_y) * zoom,
            health_bar_rect.width * zoom,
            health_bar_rect.height * zoom), border_radius=20)
        
        if self.type == "weapon" and self.name == 'arrow':
            text = Settings.health_font.render(f"Stuck : {self.stuck} - {self.elapsed}", True, color)
        else:
            text = Settings.health_font.render(f"Health {getattr(self, 'health', 'hoyo')}", True, color)
        
        width = text.get_width()
        height = text.get_height()
        win.blit(pygame.transform.scale(text, (width * zoom, height * zoom)),
                 ((self.rect.centerx - (bar / 2) - offset_x + bar + 5) * zoom, (self.rect.y - 20 - offset_y) * zoom))
        
        return health_bar_rect

    def draw(self, see_through=False, window=None, cam=(0, 0), zoom=1, game=None) -> None:
        if self.type == "block":
            game = game
        else:
            game = self.game

        zoom = round(zoom, 2)
        self.zoom = zoom

        # Use game offset if None is provided
        if cam:
            offset_x = cam[0]
            offset_y = cam[1]

        # Bubbles
        if self.name == 'bubble':
            pygame.draw.circle(window, self.color, (round((self.x - offset_x) * zoom), round((self.y - offset_y) * zoom)),
                               self.radius * zoom)
            return

        # Platforms
        elif self.name == 'platform':
            scaled_rect = pygame.Rect(
                round((self.rect.x - offset_x) * zoom),
                round((self.rect.y - offset_y) * zoom),
                round(self.rect.width * zoom),
                round(self.rect.height * zoom)
            )
            pygame.draw.rect(window, self.color, scaled_rect)
            # Add support lines to platforms
            for i in range(3):
                pygame.draw.line(window, (100, 80, 60),
                                 (round((self.rect.x + i * (self.rect.width // 2) - offset_x) * zoom),
                                  round((self.rect.y + self.rect.height - offset_y) * zoom)),
                                 (round((self.rect.x + i * (self.rect.width // 2) - offset_x) * zoom),
                                  round((self.rect.y + self.rect.height + 10 - offset_y) * zoom)),
                                 round(2 * zoom))
            return

        # Key for checking cache
        if self.name == 'water':
            key = (self.name, self.water_type, self.color, (self.rect.width, self.rect.height),
                   self.sprite_sheet, self.sheet_name, self.sprite_index, self.direction,
                   see_through)  # Round to avoid excessive keys
        
        elif self.type == 'bomb':
            key = (self.name, self.sprite_sheet,
                   self.sheet_name, self.sprite_index, self.direction, 
                   self.dead, self.death)

        elif self.type == 'block':
            key = (self.name, (self.rect.width, self.rect.height),
                   self.type_size, self.type_name, self.sprite_index, self.perspective)  # Round to avoid excessive keys

        elif self.name == 'arrow' and self.type == 'weapon':
            key = (
                self.sprite_sheet, self.sheet_name, self.sprite_index, self.direction,
                round(self.degree)
            ) #, self.dead, self.death)  # Round to avoid excessive keys

        elif self.type == 'deco':
            key = (self.name, self.type, self.sheet_name, getattr(self, "deco_biome", "1"),
                   see_through, self.dead, self.death)

        elif self.type == 'tree':
            key = (self.name, self.type, self.sheet_name, getattr(self, "deco_biome", "1"),
                   see_through, self.dead, self.death, self.sprite_index, self.direction)

        else:
            key = (self.name, self.type, self.type_name, self.type_size,
                   self.sprite_sheet, self.sheet_name, self.sprite_index, self.direction,
                   see_through, self.dead, self.death)  # Round to avoid excessive keys

        if zoom not in CACHED_OBJECT_ZOOMED_IMAGES:
            CACHED_OBJECT_ZOOMED_IMAGES[zoom] = OrderedDict()
        
        # Use cached image if available
        if key in CACHED_OBJECT_ZOOMED_IMAGES[zoom]:
            scaled_image = CACHED_OBJECT_ZOOMED_IMAGES[zoom][key]
        else:
            if self.type == "block":
                image = get_block(self.type_name, self.type_size, self.width, self.height, self.perspective)
            
            elif self.type == "treasure" or self.name == "bomb" or self.type == "tree" or self.type == "fire":
                sprites = self._resolve_sprites(self.sheet_name)
                image = sprites[self.sprite_index]
            
            elif (self.name == 'arrow' and self.type == 'weapon'):
                image_key = self.get_key()
                if image_key in CACHED_OBJECT_IMAGES['arrows']:
                    image, _, _, _ = CACHED_OBJECT_IMAGES['arrows'][image_key]
                else:
                    image = self.update(return_image=True)

            elif self.type == "deco":
                sprites = self._resolve_sprites(self.sheet_name)
                image = sprites[self.sheet_name]
            
            elif self.name == "water":
                image = cache_img(self.rect.size, self.color)
                image.fill(self.color)
                image.set_alpha(50)
            
            elif self.type == "moving_platform":            
                image = cache_img(self.rect.size)
                image.fill(self.color)
            
            elif self.type == "door":
                image = self._resolve_sprites()

            else:
                image = self.image
            
            if not image:
                print("No image for ", self.name, " in object draw")
            
            scaled_image = image
            if zoom != 1:
                scaled_size = (
                    round(image.get_width() * zoom),
                    round(image.get_height() * zoom)
                )
                scaled_image = pygame.transform.scale(image, scaled_size).convert_alpha()

            if self.name != "water":
                if see_through:
                    scaled_image = scaled_image.copy()
                    scaled_image.set_alpha(100)
                    
            
            # also cache at zoom 1: that used to rebuild the image dict-lookups, get_block()
            # and (for water) a fill() for every object on every frame
            if True:
                CACHED_OBJECT_ZOOMED_IMAGES[zoom][key] = scaled_image
                _lru_touch(CACHED_OBJECT_ZOOMED_IMAGES[zoom], key, game.OBJECT_ZOOMED_IMAGES_MAX_PER_KEY if game else Settings.OBJECT_ZOOMED_IMAGES_MAX_PER_KEY)
            
        # Position centered on player
        draw_x = round((self.rect.x - offset_x - self.morex) * zoom)
        draw_y = round((self.rect.y - offset_y - self.morey) * zoom)

        window.blit(scaled_image, (draw_x, draw_y))

        if self.type in ("deco", "tree") and not self.dead and Burn.active(self):
            # a living tree's rect is only its stump, so burn the opaque pixels of the sprite (mask bounds); once it is chopped /
            # burnt down (death) the flames shrink back to the stump rect
            box = None
            if self.type == "tree" and not self.death:
                # self.mask / self.rect are the stump, so measure the opaque pixels of the sprite actually drawn
                # (already at zoom, blitted at draw_x / draw_y); cached per image so animation frames cost once
                cache = self.__dict__.setdefault("_burn_box_cache", {})
                hit = cache.get(id(scaled_image))
                if hit is None or hit[0] is not scaled_image:
                    if len(cache) > 12:
                        cache.clear()
                    hit = cache[id(scaled_image)] = (scaled_image, scaled_image.get_bounding_rect(min_alpha=20))
                br = hit[1]
                if br.width and br.height:
                    box = pygame.Rect(draw_x + br.x, draw_y + br.y, br.width, br.height)
            Burn.draw(window, self, offset_x, offset_y, zoom, box)
        
        if game:
            if game.DEBUGGING_MODE:
                if game.debug.get('0', False):
                    health_bar_rect = self.draw_health_bar(window, offset_x, offset_y, zoom)
                    draw_x_ = round((self.rect.x - offset_x) * zoom)
                    draw_y_ = round((self.rect.y - offset_y) * zoom)

                    scaled_rect = pygame.Rect(
                        draw_x_,
                        draw_y_,
                        round(self.rect.width * zoom),
                        round(self.rect.height * zoom)
                    )
                    pygame.draw.rect(window, self.color, scaled_rect)
                    
                    if self.mask:
                        image = self.mask.to_surface(unsetcolor=(0, 0, 0, 0), setcolor=(255, 255, 255, 255))
                    else:
                        image = None
                    
                    if image:
                        scaled_size = (
                            round(image.get_width() * zoom),
                            round(image.get_height() * zoom)
                        )
                        scaled_image = pygame.transform.scale(image, scaled_size)

                        window.blit(scaled_image, (draw_x_, draw_y_))
