import pygame
import random
import math
import time

from .object_utils import Object
from ..data.palletes.doors import parse_door_name
from ..data.palletes.deco import is_recolourable
from ..data.biomes import BIOMES
from ..data.traps import kind_for, CELL

from ..scripts.cache import cache_img
from ..scripts.asset_funcs import get_block
from ..scripts.sounds import playit
from ..scripts import achievements
from ..ui import door_fx

from ..assets import Assets
from ..settings import Settings
from ..scripts.physics import PHYSICS as physics
from ..scripts.pooling import get_pool
from ..entities.burn import Burn
from ..level import progression


class Platform(Object):
    total = -1

    def __init__(self, x, y, width, height, moving, direction, speed, dest_x, dest_y, game):
        super().__init__(x, y, width, height, "platform", game=game)
        Platform.total += 1
        self.id = Platform.total
        Object.total += 1
        self.object_id = Object.total
        self.type = "moving_platform"
        self.moving = moving
        self.direction = direction
        self.min_x = dest_x[0]
        self.max_x = dest_x[1]
        self.min_y = dest_y[0]
        self.max_y = dest_y[1]
        self.color = (150, 120, 80)
        self.speed = speed
        self.dx = 0
        self.dy = 0
        
        self.outlines = {(1, 0), (-1, 0), (0, 1), (0, -1)} # right, left, down, up

    def attack(self):
        pass

    def destroy(self):
        pass

    def update_sprite(self):
        # Track how far this platform actually moves this frame so riders
        # (players/entities standing on it) can be carried along by the
        # same amount. Reset each frame before recalculating.
        self.dx = 0
        self.dy = 0

        if self.moving:
            self.x_vel = int((self.speed * self.direction[0]) * self.game.dt)
            self.y_vel = int((self.speed * self.direction[1]) * self.game.dt)

            if self.rect.x + self.x_vel > self.max_x:
                self.direction[0] = -1
                self.x_vel = 0

            elif self.rect.x + self.x_vel < self.min_x:
                self.direction[0] = 1
                self.x_vel = 0

            elif not abs(self.min_x-self.max_x) > 64:
                self.x_vel = 0

            else:
                self.rect.x += self.x_vel
                self.dx = self.x_vel

            if self.rect.y + self.y_vel > self.max_y:
                self.direction[1] = -1
                self.y_vel = 0

            elif self.rect.y + self.y_vel < self.min_y:
                self.y_vel = 0
                self.direction[1] = 1

            elif not abs(self.min_y - self.max_y) > 64:
                self.y_vel = 0

            else:
                self.rect.y += self.y_vel
                self.dy = self.y_vel

        else:
            print(99999999)
    
        self.update()


# === Flow effect function ===
def apply_current(x_velocity, current_strength, current_direction, time,
                  max_velocity=3.0, turbulence=0.1, oscillation_freq=0.5, oscillation_amp=0.3):
    flow = current_strength * current_direction
    wave = math.sin(time * oscillation_freq * 2 * math.pi) * oscillation_amp
    jitter = random.uniform(-turbulence, turbulence)
    total_flow = flow + wave + jitter
    resistance = 1 - abs(x_velocity * current_direction)
    adjusted_velocity = x_velocity + total_flow * resistance
    return max(-max_velocity, min(max_velocity, adjusted_velocity))


class Bubble(Object):
    def __init__(self, x, y, color=(200, 200, 255), game=None):
        super().__init__(x, y, 10, 10, "bubble", game=game)
        self.x = x
        self.y = y
        self.y_vel = -random.uniform(30, 90)
        self.radius = random.randint(2, 4)
        self.spawn_time = time.time()
        self.color = color

    def update_sprite(self):
        self.y += self.y_vel * self.game.dt
        if not time.time() - self.spawn_time < 3.0:
            self.dead = True
            self.death = True


class Splash(Object):
    def __init__(self, x, y, color=(180, 220, 255, 180), game=None):
        super().__init__(x, y, 10, 10, "splash", game=game)
        self.x = x
        self.y = y
        self.spawn_time = time.time()
        self.size = random.randint(2, 5)
        self.image = cache_img((self.size * 2, self.size * 2))
        self.color = color
        alpha = int(255 * ((time.time() - self.spawn_time) / 0.5))
        color = (self.color[0], self.color[1], self.color[2], alpha)
        pygame.draw.circle(self.image, color, (self.size, self.size), self.size)
        self.vx = random.uniform(-2, 2)
        self.vy = random.uniform(-3, -1)

    def update_sprite(self):
        if not time.time() - self.spawn_time < 0.5:
            self.dead = True
            self.death = True
        else:
            self.rect.x += self.vx
            self.rect.y += self.vy
            self.vy += 0.1  # Gravity
            alpha = int(255 * ((time.time() - self.spawn_time) / 0.5))
            color = (self.color[0], self.color[1], self.color[2], alpha)
            pygame.draw.circle(self.image, color, (self.size, self.size), self.size)


# === Water Zones ===
class WaterZone(Object):
    def __init__(self, x, y, w, h, type="normal", game=None, color=(0, 100, 255), flow=0, rise=False):
        super().__init__(x, y, w, h, "water", game=game)
        self.id = Platform.total
        Object.total += 1
        self.object_id = Object.total
        self.rect = pygame.Rect(x, y, w, h)
        self.water_type = type
        self.color = color
        self.flow = flow
        self.rise = rise
        self.base_y = y
        self.wave_offset = 0
        self.mass = 0.5

    def update_sprite(self):
        if self.rise:
            self.wave_offset += self.game.dt * 5
            self.y_vel += int(20 * math.sin(self.wave_offset))

        if self.in_screen:
            if self.water_type == "toxic":
                if random.random() < 0.01:
                    self.game.bubbles.append(
                        Bubble(random.randint(self.rect.x, self.rect.right), self.rect.top, color=(50, 150, 50),
                            game=self.game))
                    self.game._draw_list_dirty = True

            elif self.water_type == "lava":
                if random.random() < 0.01:
                    self.game.bubbles.append(
                        Bubble(random.randint(self.rect.x, self.rect.right), self.rect.top, color=(255, 100, 0),
                            game=self.game))
                    self.game._draw_list_dirty = True

        self.update()

    def affect(self, target):
        ztype = self.water_type
        target.current_speed *= 0.5 if target.name not in ["arrow", "bomb"] else 1
        if ztype == "normal":
            target.current_gravity *= 0.05
            target.current_jump *= 0.1
            target.oxygen -= 30 * self.game.dt

        elif ztype == "current":
            if not target.name == "arrow":
                target.x_vel += apply_current(target.x_vel - (self.flow * 100), 0.6, self.flow, self.game.dt,
                                              max_velocity=target.current_speed, turbulence=0.2, oscillation_freq=0.5,
                                              oscillation_amp=0.7)
            target.current_gravity *= 0.05
            target.current_jump *= 0.1

            target.oxygen -= 30 * self.game.dt

        elif ztype == "toxic":
            target.current_gravity *= 0.05
            target.current_jump *= 0.1
            
            target.oxygen -= 30 * self.game.dt

            if not target.dead:
                # Apply damage at each burn interval
                self.attack_power = self.game.dt * 8
                if target.nature == 'damageable_object':
                    target.hit(self)
                elif target.nature == "entity":
                    if target.type == "player":
                        target.shake_frames = max(target.shake_frames, 8)  # Apply shake for next few frames
                        target.shake_intensity = max(target.shake_intensity, 6)

                    target.hit(obj=self, type_='toxic')

        elif ztype == "healing":
            target.current_gravity *= 0.05
            target.current_jump *= 0.1
            target.health += 30 * self.game.dt
            target.health = min(target.max_health, target.health)

        elif ztype == "lava":
            target.current_gravity *= 0.05
            target.current_jump *= 0.1
            
            if not target.dead:
                # Apply damage at each burn interval
                self.attack_power = self.game.dt * 5
                if target.nature == 'damageable_object':
                    target.hit(self)
                    Burn.ignite_object(target)
                elif target.nature == "entity":
                    if target.type == "player":
                        target.shake_frames = max(target.shake_frames, 8)  # Apply shake for next few frames
                        target.shake_intensity = max(target.shake_intensity, 6)

                    target.hit(obj=self, type_='lava')
                Burn.touch(target)

# BOMBS CLASS

class Bombs:
    COLOR = (255, 0, 0)
    GRAVITY = 1
    ANIMATION_DELAY = 3
    total = -1

    def __init__(self, bomb=None, game=None):
        self.list = []
        self.game = game
        self.total = len(self.list)

    def handle_proccesses(self):
        pass

# BOMB CLASS
class Bomb(Object, Bombs):
    total = -1

    def __init__(self, x, y, owner, sounds, bomb_lifespan=6):
        self._pool_released = False
        self.reset(x, y, owner, sounds, bomb_lifespan)

    @classmethod
    def spawn(cls, x, y, owner, sounds, bomb_lifespan=6):
        """
        Preferred way to create a bomb. Pulls a recycled instance from
        this owner's pool when one is free instead of always allocating a
        new object; falls back to a normal construction otherwise.
        """
        pool = get_pool(getattr(owner, 'game', None), cls)
        if pool is None:
            return cls(x, y, owner, sounds, bomb_lifespan)
        return pool.acquire(x, y, owner, sounds, bomb_lifespan)

    def reset(self, x, y, owner, sounds, bomb_lifespan=6):
        """Re-run the same setup as __init__ so a recycled instance from
        the pool is indistinguishable from a freshly built one."""
        Object.__init__(self, x, y, 10, 10, "bomb", game=owner.game)
        self.owner = owner
        self.targets = None
        self.target = None
        self.attack_power = 5
        self.knockback_power = 300
        self.timer = 10
        Bombs.total += 1
        self.id = Bombs.total
        Object.total += 1
        self.object_id = Object.total
        self.type = "weapon"
        self.sounds = sounds
        self.game = owner.game
        if self.owner.type == 'player':
            self.attack_power = 21
        else:
            self.attack_power = 9

        # Shop: Wide Blast (players only) - how many px further than its own box a bomb reaches
        self._reach = int(2 * getattr(owner, "shop_stats", {}).get("blast_radius", 0))

        self.lifespan = bomb_lifespan
        self.mass = 0.5
        self.sheet_name = "on_" + self.direction
        self._pool_released = False
        return self

    def return_to_pool(self):
        if getattr(self, "_pool_released", False):
            return

        pool = get_pool(getattr(self, "game", None), Bomb)
        if pool is None:
            return

        # Drop references so idle pooled bombs don't keep other game
        # objects (owner, last target) alive longer than necessary.
        self.owner = None
        self.target = None
        self.targets = None

        pool.release(self)

    def attack(self, targets):
        if self.death or self.dead:
            return

        self.targets = targets
        for target in targets:
            # For team purposes - The bomb won't hit a team member
            if target.color == self.owner.color:
                continue
            
            if not target.dead:
                if target.nature == 'entity':
                    if target.entity_id == self.owner.entity_id:
                        continue
                elif target.nature != 'damageable_object':
                    continue
                elif target.nature == 'damageable_object' and target.death:
                    continue

                if self.rect.inflate(self._reach, self._reach).colliderect(target.rect):
                    target = target

                    self.attacking = False
                    self.destroy()

                    if target.nature == 'damageable_object':
                        target.hit(self.owner)
                    else:
                        if target.type == "player":
                            target.shake_frames = 8  # Apply shake for next few frames
                            target.shake_intensity = 6

                        # opposites, kill slow-mo
                        if target.type != self.owner.type:
                            dist = physics.distance(target.rect.x, target.rect.y, self.rect.x, self.rect.y)
                            if dist < 128 and (target.health - self.attack_power <= 0):
                                self.game.game_speed = 0.1

                        target.hit(self.owner, 'bomb')

                        physics.knockback(self, target=target)
                        
                        # To reset to a distance where he can get a shot
                        self.owner.clear_shot_range = 0
                        self.owner.clear_shot_up = 0
                        self.owner.clear_shot_down = 0
                        self.owner.missed = 0

                    playit("hit_3", self)
                    break

                else:
                    self.attacking = True

    def destroy(self):
        playit('explosion_3', self)
        self.sprite_index = 0
        self.time_accumulator = 0
        self.animation_count = 0
        self.death = True

    def update_sprite(self, test=False):
        if not self.death:
            all_entities = physics.get_objects(self.game.entities_map, self.rect, 0)
            damageable_objects = physics.get_objects(self.game.damageable_objects_map, self.rect, 0)
            objects = all_entities + damageable_objects

            self.attack(objects)

            self.current_speed = self.x_vel
            self.current_gravity = Settings.GRAVITY

            if self.zone:
                self.zone.affect(self)

            self.y_vel += (self.current_gravity * self.mass) * self.game.dt

            self.x_vel = self.current_speed

            self.collide()
                     
            self.elapsed += self.game.dt

            if self.rect.y > 2000:
                self.destroy()

        self.sheet_name = "on_" + self.direction
        
        # Check bomb lifespan
        if self.elapsed >= self.lifespan:
            if not self.death:
                self.destroy()
                self.owner.missed += 1
        
        if self.death or self.dead:
            len_ = 7
            self.sheet_name = "on"
        else:
            len_ = 6
        
        if self.sprite_index == len_ - 1 and self.death:
            self.dead = True
            self.sprite_index = 0
            self.time_accumulator = 0
        
        if self.death or self.dead:
            len_ = 7
            self.sheet_name = "on"
        else:
            len_ = 6

        self.time_accumulator += self.game.dt
        if (self.in_screen or self.death) and self.time_accumulator >= self.frame_duration:
            self.sprite_index = (self.sprite_index + 1) % len_

            self.time_accumulator = 0
            self.animation_count += 1

        if self.animation_count == 0 and self.sprite_index != 0:
            self.sprite_index = 0
            self.time_accumulator = 0
        
        if self.sprite_index > len_ - 1:
            self.sprite_index = 0

        self.update()


# ARROW CLASS
class Arrow(Object, Bombs):
    total = -1

    def __init__(self, x, y, owner, sounds):
        self._pool_released = False
        self.reset(x, y, owner, sounds)

    @classmethod
    def spawn(cls, x, y, owner, sounds):
        """Preferred way to create an arrow — see Bomb.spawn()."""
        pool = get_pool(getattr(owner, 'game', None), cls)
        if pool is None:
            return cls(x, y, owner, sounds)
        return pool.acquire(x, y, owner, sounds)

    def reset(self, x, y, owner, sounds):
        """Re-run the same setup as __init__ so a recycled instance from
        the pool is indistinguishable from a freshly built one."""
        Object.__init__(self, x, y, 10, 10, "arrow", game=owner.game)
        self.owner = owner
        self.targets = None
        self.target = None
        self.attack_power = 5
        self.knockback_power = 300
        self.timer = 10
        Arrow.total += 1
        self.id = Arrow.total
        Object.total += 1
        self.object_id = Object.total
        self.type = "weapon"
        self.sounds = sounds
        self.game = owner.game
        self.degree = random.randint(-360, 360)   # replaced by the real flight angle on the first collide()
        self._aimed = False
        self._tip_anchor = None                    # pooled arrows must forget the old position
        self._tip_last_topleft = (0, 0)
        self.stuck = False
        
        if self.owner.type == 'player':
            self.attack_power = 18
        else:
            self.attack_power = 6

        self.mass = 0.25

        self.lifespan = 2

        # Arrow properties: pierce / homing / burn come from the owner (shop items for players; the Entity Editor
        # can grant the same to any enemy). The same profile feeds the homing traps the owner drops.
        stats = getattr(owner, "shop_stats", None) or {}
        mods = getattr(owner, "mods", None) or {}
        self.did_hit = False                  # for the Sharpshooter streak
        self.pierce_left = int(stats.get("pierce", 0))
        self.pierced = set()
        self.homing = bool(stats.get("homing", 0))
        self.homing_target = None
        self.burn = float(mods.get("arrow_burn", 0.0))
        self.knock_mult = float(mods.get("arrow_knockback_mult", 1.0))
        self.damage_mult = float(mods.get("arrow_damage_mult", 1.0))
        
        self.sheet_name = 'full'
        self.stuck_obj = None
        self.stuck_x = 0
        self.stuck_y = 0
        
        self._pool_released = False
        return self

    def return_to_pool(self):
        if getattr(self, "_pool_released", False):
            return

        pool = get_pool(getattr(self, "game", None), Arrow)
        if pool is None:
            return

        self.owner = None
        self.target = None
        self.targets = None
        
        pool.release(self)

    def attack(self, targets):
        if self.death or self.dead:
            return

        self.targets = targets
        for target in targets:
            if target.color == self.owner.color:
                    continue

            if not target.dead:
                if target.nature == 'entity':
                    if target.entity_id == self.owner.entity_id:
                        continue
                elif target.nature != 'damageable_object':
                    continue
                if target.type == "tree" and target.death:
                    continue
                
                if id(target) in self.pierced:
                    continue                      # already went through this one

                if self.rect.colliderect(target.rect):
                    self.attacking = False
                    if not self.did_hit:
                        self.did_hit = True
                        if self.owner.type == 'player':
                            achievements.tracker().on_arrow(self.owner, True)
                    if self.pierce_left > 0 and target.nature == 'entity':
                        self.pierce_left -= 1     # Piercing Tips: keep flying
                        self.pierced.add(id(target))
                    else:
                        self.destroy()

                    if target.nature == 'damageable_object':
                        target.hit(self.owner)
                        if self.burn > 0:
                            Burn.ignite_object(target, self.owner)
                    else:
                        if target.type == "player":
                            target.shake_frames = 8  # Apply shake for next few frames
                            target.shake_intensity = 6
                        
                        # opposites, kill slow-mo
                        if target.type != self.owner.type:
                            dist = physics.distance(target.rect.x, target.rect.y, self.rect.x, self.rect.y)
                            if dist < 128 and (target.health - self.attack_power <= 0):
                                self.game.game_speed = 0.1

                        before = target.health
                        target.hit(self.owner, 'arrow')
                        if self.damage_mult != 1.0 and target.health < before:
                            target.health = before - (before - target.health) * self.damage_mult
                        if self.burn > 0 and not target.dead:
                            Burn.apply(target, self.burn, 3.0 + self.owner.attack_power * 0.15, self.owner)

                        self.knockback_power = 300 * self.knock_mult
                        physics.knockback(self, target=target)

                        # To reset to a distance where he can get a shot
                        self.owner.clear_shot_range = 0
                        self.owner.clear_shot_up = 0
                        self.owner.clear_shot_down = 0
                        self.owner.missed = 0

                    playit("hit_3", self)

                else:
                    self.attacking = False
                    
    def destroy(self):
        self.stick()
        self.dead = True

    def stick(self, obj=None):
        if obj:
            self.stuck_obj = obj
            self.stuck_x = self.rect.x - obj.rect.x
            self.stuck_y = self.rect.y - obj.rect.y

        if not self.death or self.dead:
            if self.owner.type == 'enemy':
                self.owner.missed += 1
            elif self.owner.type == 'player' and not self.did_hit:
                achievements.tracker().on_arrow(self.owner, False)       # a miss ends the streak
        self.death = True
        self.stuck = True
        self.y_vel = 0
        self.x_vel = 0

    def _steer(self):
        """Homing Arrows: turn the velocity gently toward the nearest enemy ahead (picked once, kept)."""
        t = self.homing_target
        if t is None or t.dead or t.death:
            self.homing_target = t = None
            best = 700 ** 2
            foes = list(self.game.enemy_list) if self.owner.type == "player" else list(self.game.enemy_list) + list(getattr(self.game, "players", []))
            for e in foes:
                if e is self.owner or e.dead or e.death or e.color == self.owner.color:
                    continue
                dx, dy = e.rect.centerx - self.rect.centerx, e.rect.centery - self.rect.centery
                if dx * self.current_speed < 0:      # behind the arrow
                    continue
                d2 = dx * dx + dy * dy
                if d2 < best:
                    best, t = d2, e
            self.homing_target = t
        if t is None:
            return
        speed = math.hypot(self.current_speed, self.y_vel)
        if speed < 1:
            return
        want = math.atan2(t.rect.centery - self.rect.centery, t.rect.centerx - self.rect.centerx)
        have = math.atan2(self.y_vel, self.current_speed)
        diff = (want - have + math.pi) % math.tau - math.pi
        turn = max(-1, min(1, diff)) * min(abs(diff), 3.0 * self.game.dt)
        have += turn
        self.current_speed = math.cos(have) * speed          # update_sprite copies current_speed back to x_vel
        self.y_vel = math.sin(have) * speed - Settings.GRAVITY * self.mass * self.game.dt   # cancel this frame's gravity

    def update_sprite(self):
        all_entities = physics.get_objects(self.game.entities_map, self.rect, 0)
        damageable_objects = physics.get_objects(self.game.damageable_objects_map, self.rect, 0)
        objects = all_entities + damageable_objects

        self.attack(objects)
        
        self.current_speed = self.x_vel
        self.current_gravity = Settings.GRAVITY

        if self.zone:
            self.zone.affect(self)

        if self.homing and not self.stuck:
            self._steer()

        self.y_vel += (self.current_gravity * self.mass) * self.game.dt

        self.x_vel = self.current_speed
        
        if not self.stuck:
            self.collide(True)
        else:
            if self.stuck_obj:
                self.rect.x = self.stuck_obj.rect.x + self.stuck_x
                self.rect.y = self.stuck_obj.rect.y + self.stuck_y

        if self.stuck:
            self.elapsed += self.game.dt

            # Check arrow lifespan
            if self.elapsed >= self.lifespan:
                self.destroy()

        if self.rect.y > 2000:
            self.destroy()
        
        len_ = 1
        self.time_accumulator += self.game.dt
        if self.time_accumulator >= self.frame_duration:
            self.sprite_index = (self.sprite_index + 1) % len_
            self.time_accumulator = 0
            self.animation_count += 1

        if self.animation_count == 0 and self.sprite_index != 0:
            self.sprite_index = 0
            self.time_accumulator = 0
        
        if self.sprite_index > len_ - 1:
            self.sprite_index = 0

        self.update()


# FIRE CLASS
class Fire(Object):
    total = -1
    ANIMATION_DELAY = 2

    def __init__(self, x, y, owner, fire_lifespan=6):
        self._pool_released = False
        self.reset(x, y, owner, fire_lifespan)

    @classmethod
    def spawn(cls, x, y, owner, fire_lifespan=6):
        """Preferred way to create a fire patch — see Bomb.spawn()."""
        pool = get_pool(getattr(owner, 'game', None), cls)
        if pool is None:
            return cls(x, y, owner, fire_lifespan)
        return pool.acquire(x, y, owner, fire_lifespan)

    def reset(self, x, y, owner, fire_lifespan=6):
        """Re-run the same setup as __init__ so a recycled instance from
        the pool is indistinguishable from a freshly built one."""
        Object.__init__(self, x, y, 50, 50, "fire", owner.game)
        self.rect.bottomleft = (x, y)
        self.rect.centerx = x
        Fire.total += 1
        self.id = Fire.total
        Object.total += 1
        self.object_id = Object.total
        self.type = "fire"
        self.game = owner.game
        self.nature = 'weapon'
        self.owner = owner
        self.target = None
        self.targets = None
        self.game = owner.game
        self.lifespan = fire_lifespan
        self.heat = 1.0
        if True:                                    # Shop: Hot Coals (enemies can be granted it in the Entity Editor) - burns 1 s longer and 15% hotter per level
            coals = getattr(owner, "shop_stats", {}).get("hot_coals", 0)
            self.lifespan += coals
            self.heat += 0.15 * coals
        self.burning = False
        self.mass = 0.5
        self.sheet_name = "on"
        self._pool_released = False
        return self

    def return_to_pool(self):
        if getattr(self, "_pool_released", False):
            return

        pool = get_pool(getattr(self, "game", None), Fire)
        if pool is None:
            return

        self.owner = None
        self.target = None
        self.targets = None

        pool.release(self)

    def attack(self):
        all_entities = physics.get_objects(self.game.entities_map, self.rect, 0)
        damageable_objects = physics.get_objects(self.game.damageable_objects_map, self.rect, 0)
        self.targets = all_entities + damageable_objects

        for target in self.targets:
            if target.color == self.owner.color:
                    continue
            
            self.target = target
            
            if target.nature == 'entity':
                if target.entity_id == self.owner.entity_id:
                    continue
            elif target.nature != 'damageable_object':
                    continue

            if not target.dead:
                if self.rect.colliderect(target):

                    self.attacking = False
                    # Check fire lifespan
                    if self.elapsed < self.lifespan:
                        # Apply damage at each burn interval
                        self.attack_power = self.game.dt * 3 * self.heat
                        if target.nature == 'damageable_object':
                            target.hit(self.owner)
                            Burn.ignite_object(target, self.owner)
                        else:
                            if self.target.type == "player":
                                self.target.shake_frames = max(self.target.shake_frames,
                                                               8)  # Apply shake for next few frames
                                self.target.shake_intensity = max(self.target.shake_intensity, 6)

                            target.hit(self.owner, obj=self, type_='fire')
                        self.burning = True
                        Burn.touch(target)

                else:
                    self.attacking = False

    def destroy(self):
        self.sprite_index = 0
        self.animation_count = 0
        self.death = True

    def update_sprite(self):
        self.elapsed += self.game.dt

        if self.zone:
            self.dead = True
            self.death = True

        # Check fire lifespan
        if self.elapsed >= self.lifespan:
            self.dead = True
            self.death = True

        self.sheet_name = "on"
        len_ = 7
        self.time_accumulator += self.game.dt
        if self.in_screen and self.time_accumulator >= self.frame_duration:
            self.sprite_index = (self.sprite_index + 1) % len_
            self.time_accumulator = 0
            self.animation_count += 1

        if self.animation_count == 0 and self.sprite_index != 0:
            self.sprite_index = 0
            self.time_accumulator = 0
        
        if self.sprite_index > len_ - 1:
            self.sprite_index = 0

        self.update()
        self.attack()


# TREE CLASS
class Tree(Object):
    total = -1
    ANIMATION_DELAY = 2

    def __init__(self, x, y, game, palette="1"):
        super().__init__(x, y, 50, 50, "tree", game=game)
        Tree.total += 1
        self.id = Tree.total
        Object.total += 1
        self.object_id = Object.total
        self.type = "tree"
        self.deco_biome = str(palette)
        self.game = game
        self.nature = 'damageable_object'
        self.mass = 1

        self.sheet_name = "idle_" + self.direction
        self.update()
        
    def destroy(self):
        self.sprite_index = 0
        self.animation_count = 0
        self.death = True

    def update_sprite(self):
        Burn.tick(self, self.game.dt)
        self.y_vel += min(1, (self.fall_count / Settings.FPS) * self.GRAVITY)

        if self.y_vel < 0:
            self.y_vel = 0

        self.y_vel += (Settings.GRAVITY * self.mass) * self.game.dt
        self.x_vel = 0

        self.collide_resting()

        if self.health <= 0:
            self.health = 0
            if not self.death:
                self.death = True
                self.destroy()
                playit("chopped", self)

        self.sheet_name = "idle_" + self.direction
        len_ = 4
        if self.hurt:
            self.sheet_name = "hit_" + self.direction
            len_ = 2
        if self.death:
            self.sheet_name = "chopped_" + self.direction
            len_ = 1
            
        if self.hurt:
            if self.sprite_index == len_ - 1:
                self.hurt = False

        self.time_accumulator += self.game.dt
        if self.time_accumulator >= self.frame_duration:
            if self.in_screen and not self.hurt and not self.death:
                self.sprite_index = (self.sprite_index + 1) % len_
            elif self.hurt:
                self.sprite_index = (self.sprite_index + 1) % len_
            self.time_accumulator = 0
            self.animation_count += 1

        if self.animation_count == 0 and self.sprite_index != 0:
            self.sprite_index = 0
            self.time_accumulator = 0

        if self.sprite_index > len_ - 1:
            self.sprite_index = 0

        self.update()


# BLOCK CLASS
class Block(Object):
    COLOR = (0, 255, 0)
    GRAVITY = 1
    ANIMATION_DELAY = 3
    total = -1

    def __init__(self, x, y, width, height, type="rock_1", type_size="big", game=None, perspective="fore"):
        super().__init__(x, y, width, height, game=game, name='block')
        image = get_block(type, type_size, width, height)
        self.rect = image.get_rect(topleft=(x, y))
        self.mask = pygame.mask.from_surface(image)
        self.perspective = perspective
        self.type = 'block'
        self.type_name = type
        self.type_size = type_size
        self.size = self.rect.width
        Block.total += 1 
        self.id = Block.total
        Object.total += 1
        self.object_id = Object.total
        self.mass = 1
        self.outlines = set()

    def update_sprite(self):
        if self.dead:
            self.y_vel += min(1, (self.fall_count / Settings.FPS) * self.GRAVITY)
            self.move(self.x_vel, self.y_vel, self.game.objects)

        self.update()


# TRAP CLASS
class Trap(Object):
    """A floor hazard from assets/traps (definitions live in data/traps.py).

    ``x, y`` is the grid cell the trap sits in. The picture is centred in
    the cell and rests on its bottom edge (the fire burner is 32 wide, so it
    never leaves the 64x64 cell); ``rect`` is that picture (used for drawing
    and culling) while ``origin_rect`` stays the cell the editor
    places, selects and deletes by.
    """
    total = -1
    _MASKS = {}
    _BLANK = None

    def __init__(self, x, y, name, game, off_time=None, on_time=None, delay=None, hurt_enemies=True):
        name = str(name or "spikes").lower()
        super().__init__(x, y, CELL, CELL, name, game=game)
        Trap.total += 1
        self.id = Trap.total
        Object.total += 1
        self.object_id = Object.total
        self.type = "trap"
        self.nature = "object"          # a hazard, not something that can be hit
        self.kind = kind_for(name)
        self.sheets = Assets.TRAPS.get(name) or Assets.TRAPS.get("spikes") or {}
        self.cell_x, self.cell_y = x, y
        hx, hy, hw, hh = self.kind["hitbox"]
        self.hitbox = pygame.Rect(x + hx, y + hy, hw, hh)
        self.always_on = bool(self.kind.get("always_on"))
        self.off_time = max(0.1, self._num(off_time, self.kind.get("off_time", 1.0)))
        self.on_time = max(0.1, self._num(on_time, self.kind.get("on_time", 1.0)))
        self.delay = max(0.0, self._num(delay, self.kind.get("delay", 0.0)))
        self.hurt_enemies = bool(hurt_enemies)
        self.attack_power = 0
        self.cooldowns = {}
        self.clock = 0.0
        self.frame_t = 0.0
        self.phase_t = 0.0
        self.state = "on" if self.always_on else "off"
        self.sheet_name = self.state
        self.sprite_index = 0
        if not self.always_on and self.delay > 0:
            cycle = self.off_time + self._windup() + self.on_time
            self._advance(self.delay % cycle)
        self.update()

    @staticmethod
    def _num(value, default):
        try:
            return float(value) if value is not None else float(default)
        except (TypeError, ValueError):
            return float(default)

    # lighting.py looks for this: a burner only glows while its flame is up
    @property
    def animation_name(self):
        return self.state

    # ---- on / off cycle -------------------------------------------------
    def _windup(self):
        return len(self.sheets.get("hit", ())) * self.kind.get("windup_frame_time", 0.14)

    def _duration(self, state):
        if state == "off":
            return self.off_time
        if state == "hit":
            return self._windup()
        return self.on_time

    def _next(self, state):
        if state == "off":
            return "hit" if self._windup() > 0 else "on"
        return "on" if state == "hit" else "off"

    def _set_state(self, state):
        self.state = state
        self.sheet_name = state
        self.sprite_index = 0
        self.frame_t = 0.0

    def _advance(self, dt):
        t = self.phase_t + dt
        for _ in range(8):                      # guard against zero-length phases
            dur = self._duration(self.state)
            if t < dur:
                break
            t -= dur
            self._set_state(self._next(self.state))
        self.phase_t = t

    # ---- sprites --------------------------------------------------------
    def _frames(self):
        frames = self.sheets.get(self.state) or next(iter(self.sheets.values()), None)
        if frames:
            return frames
        if Trap._BLANK is None:
            Trap._BLANK = [pygame.Surface((CELL, CELL), pygame.SRCALPHA)]
        return Trap._BLANK

    def _animate(self, dt):
        frames = self._frames()
        if len(frames) > 1:
            step = self.kind.get("on_frame_time" if self.state == "on" else "windup_frame_time", 0.12)
            self.frame_t += dt
            while self.frame_t >= step:
                self.frame_t -= step
                if self.state == "hit":
                    self.sprite_index = min(self.sprite_index + 1, len(frames) - 1)
                else:
                    self.sprite_index = (self.sprite_index + 1) % len(frames)
        if self.sprite_index > len(frames) - 1:
            self.sprite_index = 0

    def update(self, return_image=False):
        frames = self._frames()
        if self.sprite_index > len(frames) - 1:
            self.sprite_index = 0
        image = frames[self.sprite_index]
        key = (self.name, self.state, self.sprite_index)
        mask = Trap._MASKS.get(key)
        if mask is None:
            mask = Trap._MASKS[key] = pygame.mask.from_surface(image)
        self.image, self.mask, self.image_key = image, mask, key
        w, h = image.get_size()
        # centred on the cell, resting on its bottom edge
        self.rect = pygame.Rect(self.cell_x + (CELL - w) // 2, self.cell_y + CELL - h, w, h)
        self.morex = self.morey = 0
        if return_image:
            return image

    def update_sprite(self):
        dt = self.game.dt
        if not self.always_on:
            self._advance(dt)
        self._animate(dt)
        self.update()
        if self.in_screen and not getattr(self.game, "EDIT_WORLD", False):
            self._hurt(dt)

    def update_sprite_client(self):
        # multiplayer client: the server owns the cycle and the damage and
        # sends the state / frame; this only shows it.
        if self.sheet_name in self.sheets:
            self.state = self.sheet_name
        self.update()

    # ---- damage ---------------------------------------------------------
    def _hurt(self, dt):
        if not (self.always_on or self.state == "on"):
            return
        self.clock += dt
        seen = set()
        for target in physics.get_objects(self.game.entities_map, self.hitbox, 0):
            if id(target) in seen:
                continue
            seen.add(id(target))
            if getattr(target, "nature", None) != "entity" or target.dead or target.death:
                continue
            if target.type != "player" and not self.hurt_enemies:
                continue
            if not self.hitbox.colliderect(target.rect):
                continue

            if self.kind.get("hit_type") == "fire":
                self.attack_power = dt * self.kind["damage_per_sec"]
                self._shake(target)
                target.hit(obj=self, type_="fire")
                Burn.touch(target)
            else:
                if self.cooldowns.get(id(target), 0.0) > self.clock:
                    continue
                self.cooldowns[id(target)] = self.clock + self.kind.get("cooldown", 0.8)
                self.attack_power = self.kind["damage"]
                self._shake(target)
                target.hit(obj=self, type_=self.kind.get("hit_type", "spikes"))

    @staticmethod
    def _shake(target):
        if target.type == "player":
            target.shake_frames = max(target.shake_frames, 8)
            target.shake_intensity = max(target.shake_intensity, 6)


# DECO CLASS
class Deco(Object):
    total = -1
    ANIMATION_DELAY = 3

    def __init__(self, x, y, name, game):
        super().__init__(x, y, 50, 50, name, game=game)
        Deco.total += 1
        self.id = Deco.total
        Object.total += 1
        self.object_id = Object.total
        self.type = "deco"
        self.game = game
        self.nature = 'damageable_object'
        self.mass = 0.5
        self.sheet_name, self.deco_biome = self._pick_biome(name, x, y, game)
        self.update()

    @staticmethod
    def _pick_biome(name, x, y, game):
        """(sprite name, biome) for this deco. ``shrub1_5`` forces biome 5;
        a plain ``shrub1`` takes the biome of the ground it sits on.
        Decorations without a palette (signs, bones...) stay in biome 1."""
        name = str(name)
        base, _, tail = name.rpartition("_")
        if base and tail in BIOMES and base in Assets.DECO_SPRITES:
            return base, (tail if is_recolourable(base) else "1")
        if not is_recolourable(name):
            return name, "1"
        # A plain decoration is intentionally neutral. Palette selection is
        # authored in the editor via an explicit ``name_palette`` suffix.
        return name, "1"

    def destroy(self):
        self.sprite_index = 0
        self.animation_count = 0
        self.death = True

    def update_sprite(self):
        Burn.tick(self, self.game.dt)
        self.y_vel += (Settings.GRAVITY * self.mass) * self.game.dt
        if self.y_vel < 0:
            self.y_vel = 0

        self.x_vel = 0

        self.collide_resting()

        if self.rect.y > 2000:
            self.destroy()
            self.dead = True

        if self.health <= 0:
            self.health = 0
            self.death = True
            self.dead = True

        if self.hurt:
            self.hurt = False

        self.update()

# DOOR CLASS
class Door(Object):
    """
    Three behaviours, picked from the door's name (see data/palletes/doors.py):

        teleport[_N]   sends whatever touches it to a random level start point
        warp[_N]       sends it to a random entry of this door's own ``targets``
                       list of [x, y] coordinates (start points are not used)
        exit[_N]       ends the level when a player touches it

    ``_N`` is the biome (2-8) and only changes the colours.
    """
    total = -1
    ANIMATION_DELAY = 3

    # A teleported thing may land on (or next to) another door. Without a
    # short shared cooldown the two doors would bounce it back and forth
    # every frame, so each object is ignored by *all* doors for a moment.
    TELEPORT_COOLDOWN_MS = 600
    _recent = {}        # id(object) -> (object, pygame ticks until it may use a door again)

    def __init__(self, x, y, name, game, targets=None):
        super().__init__(x, y, 50, 50, name, game=game)
        Door.total += 1
        self.id = Door.total
        Object.total += 1
        self.object_id = Object.total
        self.type = "door"
        self.game = game
        self.nature = 'door_object'
        self.mass = 0.5
        self.sheet_name = self.name
        self.kind, self.biome = parse_door_name(name)
        self.targets = [[int(t[0]), int(t[1])] for t in (targets or []) if len(t) >= 2]
        door_fx.attach(self)                    # the effect layer (ui/door_fx.py); gameplay stays below
        self.update()

    def destroy(self):
        self.sprite_index = 0
        self.animation_count = 0
        self.death = True

    def update_sprite(self):
        touching = physics.get_objects(self.game.entities_map, self.rect, 0)

        if self.kind == "exit":
            self._try_exit(touching)
        else:
            touching.extend(self.game.bombs.list)
            self._try_teleport(touching)

        door_fx.on_update(self)                 # unlock detection, light preset, the exit hand-off
        self.update()

    def draw(self, see_through=False, window=None, cam=(0, 0), zoom=1, game=None):
        door_fx.draw_back(self, window, cam, zoom)       # glow, rays, ripples behind the frame
        super().draw(see_through=see_through, window=window, cam=cam, zoom=zoom, game=game)
        door_fx.draw_front(self, window, cam, zoom)      # motes, runes, the lock in front

    def _destination(self):
        """Where this door sends things, or None if it has nowhere to."""
        if self.kind == "warp" and self.targets:
            return random.choice(self.targets)
        # teleport doors (and a warp door nobody gave targets to) fall back
        # to the level's start-point pool
        return random.choice(getattr(self.game, "points", None) or [(0, -64)])

    def _try_teleport(self, touching):
        now = pygame.time.get_ticks()
        if Door._recent:
            # The object itself is stored alongside its expiry so it stays
            # alive (and its id() can't be reused by a new object) until
            # the entry is pruned here.
            Door._recent = {k: v for k, v in Door._recent.items() if v[1] > now}

        for obj in touching:
            if not self.rect.colliderect(obj.rect) or id(obj) in Door._recent:
                continue

            src = obj.rect.center
            if self.kind == "warp" and getattr(obj, "type", None) == "player":
                door_fx.whip_camera(obj)        # warps pan the camera there; teleports snap with a flash
            obj.rect.x, obj.rect.y = self._destination()
            Door._recent[id(obj)] = (obj, now + Door.TELEPORT_COOLDOWN_MS)
            door_fx.on_teleport(self, obj, src, obj.rect.center)
            if getattr(obj, "type", None) == "player":
                achievements.tracker().on_door(obj, self.kind)       # Explorer: every kind in one run
            playit("teleport", self)

    def _try_exit(self, touching):
        game = self.game
        # `new` is False only while a level is actually running: it is True
        # for the frame a level change is already queued (so two players on
        # the same door can't skip two levels) and doesn't exist in the editor.
        if getattr(game, "new", None) is not False:
            return
        if getattr(game, "MULTIPLAYER", False) and not getattr(game, "SERVER", False):
            return      # in multiplayer only the server decides when a level ends
        objective = getattr(game, "objective", None)
        if objective is not None and not objective.exit_open():
            return      # survival/boss levels (or a locked exit) keep their doors shut

        if door_fx.exiting(self):
            return      # already flaring: door_fx ends the level a moment later so the effect is seen

        for obj in touching:
            if (getattr(obj, "type", None) == "player" and not getattr(obj, "dead", False)
                    and self.rect.colliderect(obj.rect)):
                playit("win", self)
                achievements.tracker().on_door(obj, "exit")
                door_fx.begin_exit(self, obj)       # -> progression.level_won(game) after ~0.35 s
                return


# TREASURE CLASS
class Treasure(Object):
    total = -1
    ANIMATION_DELAY = 3
    __slots__ = ('id', 'object_id', 'type', 'game', 'nature', 'mass', 'coin_type', 'y_vel', 'x_vel', 'sheet_name', 'elapsed', 'lifespan', 'amount')
    def __init__(self, x, y, name, game, coin_type='static'):
        super().__init__(x, y, 50, 50, name, game=game)
        Treasure.total += 1
        self.id = Treasure.total
        Object.total += 1
        self.object_id = Object.total
        self.type = "treasure"
        self.game = game
        self.nature = 'object'
        self.mass = 0.25
        self.coin_type = coin_type
        if coin_type == 'dropped':
            self.y_vel = -200
            self.x_vel = random.randint(-320, 320)
        self.sheet_name = self.name
        self.elapsed = 0
        self.lifespan = random.randint(15, 30)
        self.amount = 1             # how much one pick-up is worth (death piles carry several)
        
    def update_sprite(self):
        if self.coin_type == 'dropped':
            self.elapsed += self.game.dt
            
            self.y_vel += (Settings.GRAVITY * self.mass) * self.game.dt
            self.x_vel = min(-10, self.x_vel + 5) if self.x_vel < 0 else max(10, self.x_vel - 5)
            self.collide()

            if self.elapsed >= self.lifespan and not self.dead:
                self.dead = True
                self.death = True

        self.sheet_name = self.name
        
        self.time_accumulator += self.game.dt
        if self.in_screen and self.time_accumulator >= self.frame_duration:
            self.sprite_index = (self.sprite_index + 1) % 7
            self.time_accumulator = 0
            self.animation_count += 1

        if self.animation_count == 0 and self.sprite_index != 0:
            self.sprite_index = 0
            self.time_accumulator = 0
        
        if self.sprite_index > 7 - 1:
            self.sprite_index = 0

        # Shop: Coin Magnet drifts the coin toward any nearby player who bought it
        magnet_radius = getattr(self.game, "coin_magnet_radius", 0)
        if magnet_radius and self.in_screen and not self.dead:
            self._drift_to_players(magnet_radius)

        if self.in_screen:
            all_entities = physics.get_objects(self.game.entities_map, self.rect, 0)
            for player in all_entities:
                if player.type == "player" and not (player.dead or player.death):
                    if self.rect.colliderect(player.rect):
                        playit("coin", self)
                        
                        if self.name == 'green':
                            player.emerald_coins += self.amount
                        elif self.name == 'pink':
                            player.pearl_coins += self.amount
                        elif self.name == 'red':
                            player.ruby_coins += self.amount
                        elif self.name == 'yellow':
                            player.gold_coins += self.amount
                        self.dead = True
                        self.death = True

        self.update()

    def _drift_to_players(self, search_radius, eligible=None):
        """Coin Magnet: pull this coin toward the nearest player whose magnet reaches it.

        ``eligible(player)`` (optional) skips players the pull must not act on."""
        for player in physics.get_objects(self.game.entities_map, self.rect.inflate(search_radius * 2, search_radius * 2), 0):
            if player.type != "player" or player.dead:
                continue
            if eligible is not None and not eligible(player):
                continue
            reach = getattr(player, "coin_magnet", 0)
            if not reach:
                continue
            dx = player.rect.centerx - self.rect.centerx
            dy = player.rect.centery - self.rect.centery
            dist = math.hypot(dx, dy)
            if dist < 1 or dist > reach:
                continue
            # faster the closer it gets, never overshooting the player
            step = min(dist, (250 + 450 * (1 - dist / reach)) * self.game.dt)
            mx, my = dx / dist * step, dy / dist * step
            self.rect.x += int(mx) or (1 if mx > 0 else -1 if mx < 0 else 0)
            self.rect.y += int(my) or (1 if my > 0 else -1 if my < 0 else 0)
            return


# ---------------------------------------------------------------------- #
# Co-op pick-ups (power-ups and the placeable Charm Crystal): see scripts/coop_loot.py
# ---------------------------------------------------------------------- #
_ORB_CACHE = {}


def _orb_image(name, size):
    """The glassy orb with the item's shop icon inside, drawn once per (item, size) and reused."""
    key = (name, size)
    img = _ORB_CACHE.get(key)
    if img is None:
        from ..ui import shop_icons
        from ..scripts import coop_loot
        if len(_ORB_CACHE) > 80:
            _ORB_CACHE.clear()
        iid = coop_loot.item_id(name)
        color = shop_icons.ICON_MAP.get(iid, ("gem", (255, 255, 255)))[1]
        img = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        pygame.draw.circle(img, (16, 11, 22, 235), (c, c), c - 1)
        pygame.draw.circle(img, color, (c, c), c - 1, max(2, size // 14))
        pygame.draw.circle(img, (255, 255, 255, 60), (c - size // 6, c - size // 5), max(2, size // 9))
        if not shop_icons.draw_icon(img, iid, (c, c), size * 0.82):
            pygame.draw.circle(img, color, (c, c), size // 4)
        _ORB_CACHE[key] = img
    return img


def draw_pickup(window, name, center, size, t=0.0, glow_strength=0.5):
    """One pick-up orb centred on ``center`` (screen px), ``size`` px wide, with a soft glow. Used by the world
    draw and by the level editor's palette preview."""
    from ..ui import ui_fx, shop_icons
    from ..scripts import coop_loot
    color = shop_icons.ICON_MAP.get(coop_loot.item_id(name), ("gem", (255, 255, 255)))[1]
    size = max(12, int(size))
    ui_fx.glow(window, center, color, int(size * 1.1), glow_strength * (0.8 + 0.2 * math.sin(t * 4)))
    img = _orb_image(name, size)
    window.blit(img, img.get_rect(center=(int(center[0]), int(center[1]))))


class Pickup(Treasure):
    """A power-up (or the Charm Crystal) lying in the world.

    It lives in ``game.treasure_list`` like a coin, so drawing, the draw list, shadows, the minimap and the
    editor's place / delete tools all just work. ``name`` is the shop item id (or "charm"). A "dropped" pick-up
    pops out of a fallen enemy, falls, and fades after ``lifespan`` seconds; a level pick-up waits forever.
    Nobody who could not use it (full health, maxed level) picks it up: it stays for a teammate.
    """
    is_pickup = True

    def __init__(self, x, y, name, game, coin_type='static'):
        super().__init__(x, y, "yellow", game, coin_type)       # a real coin name keeps every coin-keyed lookup safe
        self.name = name
        self.sheet_name = name
        self.phase = random.random() * 6.28
        self._noticed = {}                                      # id(player) -> tick of the last "cannot use" banner

    def update_sprite(self):
        game = self.game
        dt = getattr(game, "dt", 0) or 0
        if self.coin_type == 'dropped':
            self.elapsed += dt
            self.y_vel += (Settings.GRAVITY * self.mass) * dt
            self.x_vel = min(-10, self.x_vel + 5) if self.x_vel < 0 else max(10, self.x_vel - 5)
            self.collide()
            if self.elapsed >= self.lifespan and not self.dead:
                self.dead = True
                self.death = True
                return

        if not self.in_screen or self.dead or getattr(game, "EDIT_WORLD", False):
            return

        from ..scripts import coop_loot
        magnet_radius = getattr(game, "coin_magnet_radius", 0)
        if magnet_radius:
            # the Coin Magnet only pulls a power-up toward someone who can actually use it: a maxed-out
            # (or full-health) player must not drag it along, it stays put for a teammate
            self._drift_to_players(magnet_radius, lambda player: coop_loot.can_collect(player, self.name))

        for player in physics.get_objects(game.entities_map, self.rect, 0):
            if player.type == "player" and not (player.dead or player.death) and self.rect.colliderect(player.rect):
                if coop_loot.collect(game, player, self.name):
                    playit("coin", self)
                    self.dead = True
                    self.death = True
                    return
                self._say_unusable(player)

    def _say_unusable(self, player):
        """The player touched a power-up they cannot use: leave it, and tell them why (not every frame)."""
        from ..data.coop_items import UNUSABLE_NOTICE_MS
        from ..scripts import coop_loot
        now = pygame.time.get_ticks()
        if now - self._noticed.get(id(player), -UNUSABLE_NOTICE_MS) < UNUSABLE_NOTICE_MS:
            return
        if coop_loot.explain_unusable(player, self.name):
            self._noticed[id(player)] = now

    def draw(self, see_through=False, window=None, cam=(0, 0), zoom=1, game=None):
        z = zoom or 1
        t = time.time() + self.phase
        bob = 4 + 3 * math.sin(t * 3)
        cx = (self.rect.centerx - cam[0]) * z
        cy = (self.rect.centery - cam[1] - bob) * z
        if self.coin_type == 'dropped' and self.lifespan - self.elapsed < 5 and int(t * 6) % 2:
            return                                          # blinks while about to fade
        draw_pickup(window, self.name, (cx, cy), 44 * z, t)


def make_treasure(x, y, name, game):
    """The one place a treasure entry becomes an object: a coin, or a pick-up for the placeable names."""
    from ..data.coop_items import PLACEABLE
    if name in PLACEABLE:
        return Pickup(x, y, name, game)
    return Treasure(x, y, name, game)
