import random
import pygame

from ..settings import Settings
from ..data.ammo import AMMO_BASE, BOMB_CAP
from ..objects.objects import Arrow, Bomb, Fire
from ..scripts.sounds import playit
from ..scripts import achievements
from ..scripts import coop_loot
from ..ui import combat_fx
from . import mods as mods_rt
from .controls import handle_keypress, handle_finger_movement, joybuttondown

class ACTIVITY:
    """Entity behaviour (targeting, attacks, hit handling, the AI ``think`` loop).

    Shop effects (shield, thorns, extra jumps, bomb cap, reload, pierce, homing ...) are read from
    ``shop_stats`` for ANY entity, not just players; enemies get them from the Entity Editor
    (entities/mods.py). ``think`` also runs that module's dash and homing-trap AI.
    """

    def acquire_target(self, target_list, target_list2=None):
        self.get_nearest(target_list, target_list2)

    def can_jump(self, obj_list, vel):
        # Check each object in the obj_list
        for obj in obj_list:
            # Check if there is any vertical overlap between the player and the object
            if self.rect.bottom > obj.rect.top and self.rect.top < obj.rect.bottom:
                # Check if player is moving horizontally and could collide with the object
                if (self.rect.right + vel > obj.rect.left and self.rect.left < obj.rect.right) or (
                        self.rect.left + vel < obj.rect.right and self.rect.right > obj.rect.left):
                    # Check if there is enough space for the player to jump
                    if self.rect.bottom + vel < obj.rect.top:
                        return True  # Player can jump over object

        return False  # Not enough space to jump over object

    def reset_dir(self):
        self.wandering_timer = 0
        self.wandering_time = 0
        self.x_vel = 0

    def patrol(self):
        if self.rect.x + self.x_vel > self.spawn_point + self.patrol_range_x:
            self.reset_dir()
            self.patrolling = True

        elif self.rect.x + self.x_vel < self.spawn_point - self.patrol_range_x:
            self.reset_dir()
            self.patrolling = True

        if self.rect.x > self.spawn_point + self.patrol_range_x:
            self.move_left(self.current_speed)
            self.patrolling = True

        elif self.rect.x < self.spawn_point - self.patrol_range_x:
            self.move_right(self.current_speed)
            self.patrolling = True

        else:
            self.patrolling = False

    def chase(self):
        """
        Makes the object chase the target within vertical and horizontal bounds.

        """
        # Check if the target is within the vertical bounds of the object

        if self.rect.top - self.acquire_up < self.target.rect.bottom and self.rect.bottom + self.acquire_down > self.target.rect.top:

            # If the target is to the right and outside the chase range

            if self.target.rect.right <= self.rect.left and self.target.rect.right - self.rect.left <= -self.chase_range:

                self.move_left(self.current_speed)  # Move right to chase the target
                self.chasing = True
                self.attacking = False
                self.evading = False

            # If the target is to the left and outside the chase range

            elif self.target.rect.left >= self.rect.right and self.target.rect.left - self.rect.right >= self.chase_range:

                self.move_right(self.current_speed)  # Move right to chase the target
                self.chasing = True
                self.attacking = False
                self.evading = False

            # If the target is within the chase range
            else:
                self.chasing = False  # Stop chasing (target is close enough)

        # If the target is not within the vertical bounds
        else:
            self.chasing = False  # Stop chasing

    def evade_2(self):
        self.attacking = False
        self.chasing = False
        self.evading = True

        if self.evade_time > self.evade_max_time:
            self.evade_max_time = random.randint(3, 10)
            self.evade_time = 0
            self.decision = random.choice(['left', 'right'])

        self.evade_time += self.game.dt

        if self.decision == 'left':
            self.move_left(self.current_speed)
        else:
            self.move_right(self.current_speed)

    def follow_path(self):
        if not self.path or not self.target or not self.game.env_ready:
            return
        self.chasing = True
        self.attacking = False
        self.evading = False
        next_node = self.path[0]
        dx = next_node.rect.centerx - self.rect.centerx
        dy = next_node.rect.top - self.rect.bottom

        if dx > 0:
            self.move_right(self.current_speed)
            self.state = "Walking Right"
        elif dx < 0:
            self.move_left(self.current_speed)
            self.state = "Walking Left"

        if dy < -64:
            if self.zone:
                self.swim_up()
                self.state = "Swimming_Up"

            elif self.jump_count < 1 or self.jump_count == 1 and self.fall_count > 0.1:
                self.jump()
                self.state = "Jumping"

        if next_node.rect.collidepoint(self.rect.centerx, self.rect.bottom):
            self.path.pop(0)
            self.completed_path += 1

    def evade(self):
        if self.rect.colliderect(self.target.rect):
            self.evade_2()

        elif self.evading:
            self.evade_2()
            self.evading = False
            self.evade_time = 0

    def hit(self, enemy=None, obj=None, type_=None):
        if self.grace_until > pygame.time.get_ticks():
            return      # just revived / restarted: a moment of safety
        if combat_fx.dodged(self, enemy, obj, type_):
            return      # dash i-frames: a well timed dash cancels the hit
        hp_before = self.health
        if type_ == 'fire':
            if (int(self.scream_lapse) % 3 == 0) and self.last_scream_lapse != int(self.scream_lapse):
                playit("scream", self)
                self.scream_lapse = 0
                self.last_scream_lapse = int(self.scream_lapse) 

            self.health -= obj.attack_power
        
        elif type_ == 'lava':
            if (int(self.scream_lapse) % 3 == 0) and self.last_scream_lapse != int(self.scream_lapse):
                playit("burnt", self)
                playit("scream", self)
                self.scream_lapse = 0
                self.last_scream_lapse = int(self.scream_lapse) 

            self.health -= obj.attack_power
        
        else:
            if (int(self.pain_lapse) % 2 == 0) and self.last_pain_lapse != int(self.pain_lapse):
                playit('pain', self)
                self.pain_lapse = 0
                self.last_pain_lapse = int(self.pain_lapse) 
            
            if enemy:
                self.health -= enemy.attack_power
            elif obj:
                self.health -= obj.attack_power

        # Combat feel: crits, combo links and finishers add a share on top.
        extra = combat_fx.bonus_damage(enemy, self, hp_before - self.health, obj, type_)
        if extra:
            self.health -= extra

        # Shop: Iron Skin & co. shave a share off whatever this hit just took.
        cut = getattr(self, "damage_taken_mult", 1.0)
        if cut != 1.0 and self.health < hp_before:
            self.health = hp_before - (hp_before - self.health) * cut

        # Shop: Shield Bubble swallows whole hits (3 per floor); Thorns reflects a share of melee damage.
        # Enemies can own both (granted in the Entity Editor), so this is not for players only.
        if self.health < hp_before:
            if getattr(self, "shield_left", 0) > 0:
                self.health = hp_before
                self.shield_left -= 1
                combat_fx.on_shield(self)
            else:
                thorns = getattr(self, "shop_stats", {}).get("thorns", 0.0)
                if thorns and enemy and not obj and type_ not in ("fire", "lava", "arrow", "bomb") and enemy is not self:
                    enemy.health -= (hp_before - self.health) * min(0.9, thorns)

        if self.type == "player" and self.health < hp_before:
            self.damage_this_level += hp_before - self.health      # achievements: flawless / untouchable
            if type_ == "lava":
                self.lava_seconds += self.game.dt                  # achievements: hot feet

        # Combat feel: flash, numbers, sparks, hit-stop, kill bursts (ui/combat_fx.py)
        combat_fx.on_hit(self, enemy, obj, type_, hp_before)

        if self.health <= 0 and not (self.death or self.dead):
            '''if obj in ['arrow', 'bomb'] and self.type == 'player':
                self.game.game_speed = 0
            '''
            if not enemy and obj is not None and getattr(obj, "credit_owner", False):
                enemy = getattr(obj, "owner", None)          # a homing trap's kills belong to whoever dropped it
            if enemy:
                enemy.kills += 1
                if enemy.type == "player":
                    achievements.tracker().on_kill(enemy, type_)
                    coop_loot.on_kill(enemy)                # co-op: hero milestones by kill count
                # Shop: Lifesteal
                if getattr(enemy, "lifesteal", 0):
                    enemy.health = min(enemy.max_health, enemy.health + enemy.max_health * enemy.lifesteal)

        if not self.target:
            if enemy:
                self.target = enemy

        self.hurt = True

    def attack(self):

        if self.type == 'player':
            self.attacking = True
            self.sprite_sheet = "attack_1"

        if not self.target:
            return

        if (
            self.rect.top - self.attack_up - self.clear_shot_up < self.target.rect.bottom and 
            self.rect.bottom + self.attack_down + self.clear_shot_down > self.target.rect.top or self.name == "TNT"
            ):
            if (
                    self.target.rect.right <= self.rect.left and self.target.rect.right - self.rect.left >= 
                    -(self.attack_range - self.clear_shot_range)
                ) or (
                    self.target.rect.left >= self.rect.right and self.target.rect.left - self.rect.right <= 
                    (self.attack_range - self.clear_shot_range)
                ):
                self.attacking = True
                self.sprite_sheet = "attack_1"

                if self.rect.centerx < self.target.rect.centerx:
                    self.direction = "right"
                elif self.rect.centerx > self.target.rect.centerx:
                    self.direction = "left"

                if self.sprite_index == self.attack_que:

                    if self.name == 'Torch':
                        if self.wait > self.attack_delay * self.reload_mult():
                            playit("throw_2", self)
                            if self.type == 'player':
                                self.fire(self.target, quantity=self.ammo_count("fire"))
                            else:
                                self.fire(self.target)
                            return
                        else:
                            # Hit with fire stick
                            if self.target.type == "player":
                                self.target.shake_frames = max(self.target.shake_frames,
                                                               8)  # Apply shake for next few frames
                                self.target.shake_intensity = max(self.target.shake_intensity, 6)

                            self.target.hit(self)
                            if self.target.nature == 'entity':
                                self.knockback()

                    elif self.name == "TNT":
                        if self.wait > self.attack_delay * self.reload_mult():
                            # mine = [bomb for bomb in self.game.bombs.list if bomb.owner == self]

                            # if len(mine) <= self.bomb_limit:
                                playit("throw_2", self)
                                if self.type == 'player':
                                    self.bomb(quantity=self.ammo_count("bomb"))
                                else:
                                    self.bomb()

                    elif self.name == "Archer":
                        if self.wait > self.attack_delay * self.reload_mult():
                            playit("throw_2", self)
                            if self.type == 'player':
                                self.shoot_arrow(quantity=self.ammo_count("arrow"))
                            else:
                                self.shoot_arrow()

                    else:
                        if self.wait > self.attack_delay * self.reload_mult():
                            if self.target.nature == 'damageable_object' and self.name == "Pawn":
                                self.sprite_sheet = 'attack_2'
                                if self.target.type == "tree":
                                    playit("hit", self)
                                else:
                                    playit("hit_2", self)
                                self.target.hit(self)
                                return

                            if self.target.type == "player":
                                self.target.shake_frames = max(self.target.shake_frames,
                                                               8)  # Apply shake for next few frames
                                self.target.shake_intensity = max(self.target.shake_intensity, 4)

                            if self.name == "Pawn":
                                if self.target.type == "tree":
                                    playit("hit", self)
                                else:
                                    playit("hit_2", self)
                            else:
                                playit('cut_2', self)

                            self.target.hit(self)
                            if self.target.nature == 'entity':
                                self.knockback()
            else:
                if not self.type == 'player':
                    self.attacking = False
        else:
            if not self.type == 'player':
                self.attacking = False

    def ammo_count(self, kind):
        """Projectiles per volley: ``"arrow" | "fire" | "bomb"``. Shop bonuses are for players only."""
        who = "player" if self.type == "player" else "enemy"
        n = AMMO_BASE[who][kind]
        n += getattr(self, "shop_stats", {}).get(f"{kind}_bonus", 0)      # empty for enemies unless granted in the editor
        return max(1, int(n))

    def reload_mult(self):
        """Multiplier on the reload / throw delay: Quick Hands (players only), never below 40%."""
        return max(0.4, 1.0 - getattr(self, "shop_stats", {}).get("reload_cut", 0.0))

    def can_jump(self):
        """Ground jump, the existing second jump, plus Cloud Step air jumps (players only)."""
        extra = getattr(self, "shop_stats", {}).get("extra_jumps", 0)
        return self.jump_count < 1 or (1 <= self.jump_count <= 1 + extra and self.fall_count > 0.1)

    def bomb_cap(self):
        """Most bombs this entity may have alive at once."""
        who = "player" if self.type == "player" else "enemy"
        extra = getattr(self, "shop_stats", {}).get("bomb_cap", 0)
        return BOMB_CAP[who] + extra

    def live_bombs(self):
        return sum(1 for b in self.game.bombs.list if isinstance(b, Bomb) and b.owner is self)

    def fire(self, target=None, quantity=1):
        start_x = (self.rect.right if self.direction == "right" else self.rect.left) + 20
        start_y = self.rect.bottom - 36
        
        if target:
            start_x = target.rect.centerx
            start_y = target.rect.bottom - 36

        for i in range(quantity):
            fire_obj = Fire.spawn(start_x + (i * 36), start_y, self)
            if not fire_obj:
                continue
            self.game.fire_list.append(fire_obj)
        
        self.game._draw_list_dirty = True
        self.wait = 0

    def bomb(self, quantity=1, time_to_hit=1):
        quantity = min(quantity, max(0, self.bomb_cap() - self.live_bombs()))
        for i in range(quantity):
            bomb_obj = Bomb.spawn(self.rect.x, self.rect.y, self, self.game.sounds)
            if not bomb_obj:
                continue

            bomb_obj.rect.x = self.rect.left if self.direction == "left" else self.rect.right
            bomb_obj.rect.bottom = self.rect.centery
            
            start_pos = bomb_obj.rect.center
            target_pos = self.target.rect.center
            
            T_wanted = time_to_hit + (i * 0.5)
            
            vx, vy0, T_final = self.get_perfect_aim(start_pos, target_pos, bomb_obj.mass, T_wanted, 64)
            
            bomb_obj.x_vel = vx
            bomb_obj.y_vel = vy0
            bomb_obj.time = 0
            
            self.game.bombs.list.append(bomb_obj)
        
        self.game._draw_list_dirty = True

        #if self.type != 'player':
        self.wait = 0
    
    def get_perfect_aim(self, start_pos, target_pos, mass, time_to_hit=1.0, max_speed=64.0):
        G = Settings.GRAVITY # your GlobalGravity
        g_eff = G * mass # keep your 1.2 mult if you want

        dx = target_pos[0] - start_pos[0]
        dy = target_pos[1] - start_pos[1]

        T = time_to_hit
        T = T if T else 1
        vx = dx / T
        cap = 50
        if cap > vx > -cap:
            vx = cap if vx > 0 else -cap
            T = dx / vx
            T = T if T else 1

        vy0 = (dy - 0.5 * g_eff * T**2) / T

        return vx, vy0, T

    # USE IT LIKE THIS in shoot_arrow:
    def shoot_arrow(self, quantity=1, time_to_hit=1):
        for i in range(quantity):
            arrow_obj = Arrow.spawn(100, -200, self, self.game.sounds)
            if not arrow_obj: continue

            # fix your side bug
            if self.direction == "right":
                arrow_obj.rect.left = self.rect.right
            else:
                arrow_obj.rect.right = self.rect.left      # was rect.left: left shots started inside the shooter
            arrow_obj.rect.centery = self.rect.centery

            start_pos = arrow_obj.rect.center
            target_pos = self.target.rect.center

            # staggered time
            T_wanted = time_to_hit / max(0.3, float((self.mods or {}).get('arrow_speed_mult', 1.0))) + (i * 0.5)

            vx, vy0, T_final = self.get_perfect_aim(start_pos, target_pos, arrow_obj.mass, T_wanted, 64)

            arrow_obj.x_vel = vx
            arrow_obj.y_vel = vy0
            arrow_obj.time = 0

            self.game.bombs.list.append(arrow_obj)
        
        self.game._draw_list_dirty = True
        self.wait = 0

    def wander(self):

        self.wandering = True

        if self.wandering_timer >= self.wandering_time:
            self.choice = random.choice(sorted(self.activities))
            self.wandering_time = random.uniform(0.0, 1.5)
            self.wandering_timer = 0

            if self.bored:
                self.bored = False
                self.target = None
                self.has_target = False

        self.wandering_timer += self.game.dt

        if 'wl' in self.choice:
            self.move_left(self.walk_speed)

        elif 'wr' in self.choice:
            self.move_right(self.walk_speed)

        if 'rl' in self.choice:
            self.move_left(self.current_speed)

        elif 'rr' in self.choice:
            self.move_right(self.current_speed)

        if 'il' in self.choice:
            self.x_vel = 0
            self.direction = 'left'

        elif 'ir' in self.choice:
            self.x_vel = 0
            self.direction = 'right'

        if 'j' in self.choice:
            self.jump_choice = random.choice(['single', 'double'])
            if self.zone:
                self.swim_up()
            elif self.jump_count < 2:
                self.jump(self.jump_choice)

        if 'on' in self.choice:
            self.animation_name = 'on'

        elif 'off' in self.choice:
            self.animation_name = 'off'

        if "laugh" in self.choice:
            if (int(self.laugh_lapse) % 2 == 0) and self.last_laugh_lapse != int(self.laugh_lapse):
                playit('laugh', self)
                self.laugh_lapse = 0
                self.last_laugh_lapse = int(self.laugh_lapse) 
            
            self.wandering_time = 0

        if 'confused' in self.choice:
            self.feelings.add('confusion')
            self.wandering_time = 0

        if 'chat' in self.choice:
            self.feelings.add('chat')
            self.wandering_time = 0
        
        if 'bored' in self.choice:
            if random.random() < 0.01:
                self.bored = True

    def control(self):
        if self.control_type == "joystick":
            joybuttondown(self.game, self)

        elif self.control_type == "touch":
            if self.dead:
                if not self.game.done:
                    self.game.done = True
                # (no longer quits the app: the defeat screen offers revive / restart)

            handle_finger_movement(self.game)

        else:
            if self.game.keys:
                handle_keypress(self.game, self)
            if self.dead:
                if not self.game.done:
                    self.game.done = True

    def think(self):
        if self.auto and not self.death and not self.dead:
            if self.mods and mods_rt.ai_pre(self):
                return                       # mid-dash: the dash owns this frame (entities/mods.py)
            if not self.stepping_on_platform and not self.dashing:
                self.x_vel = 0
            if self.has_target:
                if self.mods:
                    mods_rt.ai(self)         # homing traps (entities/mods.py)
                if not self.posted:
                    if not self.evading and not self.attacking:  # and not self.finding_way
                        self.follow_path()  # self.chase()
                    self.evade()
                if not self.evading:
                    self.attack()
                self.wandering = False
                self.patrolling = False
                self.bored = False
            else:
                if self.patroller:
                    self.patrol()
                else:
                    self.patrolling = False

                if not self.patrolling and not self.posted:
                    self.wander()

                self.chasing = False
                self.evading = False
                self.attacking = False
                self.finding_way = False

        elif self.type == 'player':
            if not self.client:
                if not self.stepping_on_platform and not self.dashing:
                    self.x_vel = 0

                self.control()

            if self.auto_attack:
                self.attack()
