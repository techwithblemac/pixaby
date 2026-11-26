import pygame
import math

from ..scripts.physics import get_degree
from ..settings import Settings
from ..objects.objects import Bomb, Arrow, Treasure, Tree
from ..scripts.sounds import playit


def _zoom_goal(player):
    """The zoom the player is easing toward: their own ``target_zoom`` (manual keys) times what the
    camera wants (speed / dash / focus, see scripts/camera.py). Quantised to 0.02 so the zoom-keyed
    sprite caches never see a stream of distinct float zooms."""
    goal = player.target_zoom
    cam = getattr(player, "camera", None)
    if cam is not None:
        goal = max(player.zoom_min * 0.8, min(player.zoom_max * 1.25, goal * cam.zoom_mult))
    return round(round(goal / 0.02) * 0.02, 2)


def try_dash(game, player):
    """The ONE place a dash is paid for (see scripts/charm_mode.try_dash). True = the dash may start."""
    from ..scripts import charm_mode          # lazy: charm_mode pulls in the UI
    return charm_mode.try_dash(game, player)


def _aiming(player):
    """True while this player is in charm mode: movement and attacks are frozen, the keys choose a target."""
    return getattr(player, "charm_session", None) is not None

'''
def handle_fingers(self, event):
    pressed = pygame.mouse.get_pressed()
    event_pos = pygame.mouse.get_pos()
    
    # PLAYER JOYSTICK
    radius = math.hypot(event_pos[0] - self.player_joystick_x, event_pos[1] - self.player_joystick_y)
    if radius < self.player_joystick_radius:
        self.player_joystick_power = radius / self.player_joystick_radius
    else:
        self.player_joystick_power = self.player_joystick_radius / self.player_joystick_radius

    self.player_joystick_angle = math.atan2(event_pos[1] - self.player_joystick_y, event_pos[0] - self.player_joystick_x)
    
    # BOMB JOYSTICK
    radius = math.hypot(event_pos[0] - self.bomb_joystick_x, event_pos[1] - self.bomb_joystick_y)
    if radius < self.bomb_joystick_radius:
        self.bomb_joystick_power = radius / self.bomb_joystick_radius
    else:
        self.bomb_joystick_power = self.bomb_joystick_radius / self.bomb_joystick_radius

    self.bomb_joystick_angle = math.atan2(event_pos[1] - self.bomb_joystick_y, event_pos[0] - self.bomb_joystick_x)
    
    if pressed[0] == True:    
        if math.hypot(event_pos[0] - self.player_joystick_x,
                        event_pos[1] - self.player_joystick_y) < self.player_joystick_radius:
            self.player_joystick_tapping = True

        if self.player.name in ["TNT", "Archer"] and not self.AUTO_SHOOT:
            if math.hypot(event_pos[0] - self.bomb_joystick_x, event_pos[1] - self.bomb_joystick_y) < self.bomb_joystick_radius:
                self.bomb_joystick_tapping = True
            
                self.bomb_joystick_power = math.hypot(event_pos[0] - self.bomb_joystick_x, event_pos[1] - self.bomb_joystick_y) / self.bomb_joystick_radius
                self.bomb_joystick_angle = math.atan2(event_pos[1] - self.bomb_joystick_y, event_pos[0] - self.bomb_joystick_x)
                
    else:    
        # Remove touch when lifted
        self.player_joystick_tapping = False
        self.player_joystick_angle = 0
        self.player_joystick_power = 0
        self.player_controlling_finger = None
        self.player.x_vel = 0
        
        if self.bomb_joystick_tapping:
            if self.player.name in ["TNT", "Archer"] and not self.AUTO_SHOOT:    
                bomb_x = self.player.rect.centerx
                bomb_y = self.player.rect.centery
                bomb_vel_x = (math.cos(self.bomb_joystick_angle) * self.bomb_joystick_power) * 500
                bomb_vel_y = (math.sin(self.bomb_joystick_angle) * self.bomb_joystick_power) * 1000
                if self.player.name == "TNT":
                    obj = Bomb(bomb_x, bomb_y, self.player, self.sounds)
                    obj.rect.bottom = self.player.rect.bottom - 50
                    obj.rect.x = self.player.rect.left if self.player.direction == "right" else self.player.rect.right
                else:
                    obj = Arrow(bomb_x, bomb_y, self.player, self.sounds)
                    obj.rect.center = self.player.rect.center
            
                obj.x_vel = bomb_vel_x
                obj.y_vel = bomb_vel_y

                if self.player.name == 'Archer':
                    obj.degree, _ = get_degree(obj.x_vel, obj.y_vel, obj.degree)

                    playit("arrow_fly", self.player)

                self.bombs.list.append(obj)
                self._draw_list_dirty = True

                self.player.wait = 0

            self.bomb_joystick_tapping = False
            self.bomb_joystick_angle = 0
            self.bomb_joystick_power = 0
            self.bomb_controlling_finger = None

'''

def handle_fingers(self, event):
    if event.type == pygame.FINGERDOWN:
        event_pos = (event.x * Settings.WIDTH, event.y * Settings.HEIGHT)
        
        # Register new touch
        self.touches[event.finger_id] = event_pos       

        if not self.player_controlling_finger:
            if math.hypot(event_pos[0] - self.player_joystick_x,
                          event_pos[1] - self.player_joystick_y) < self.player_joystick_radius:
                self.player_joystick_tapping = True
                self.player_controlling_finger = event.finger_id

        if self.player.name in ["TNT", "Archer"] and not self.AUTO_SHOOT:
            if not self.bomb_controlling_finger:
                if math.hypot(event_pos[0] - self.bomb_joystick_x,
                              event_pos[1] - self.bomb_joystick_y) < self.bomb_joystick_radius:
                    self.bomb_joystick_tapping = True
                    self.bomb_controlling_finger = event.finger_id

        # PLAYER JOYSTICK
        if self.player_controlling_finger == event.finger_id:
            radius = math.hypot(event_pos[0] - self.player_joystick_x, event_pos[1] - self.player_joystick_y)
            if radius < self.player_joystick_radius:
                self.player_joystick_power = radius / self.player_joystick_radius
            else:
                self.player_joystick_power = self.player_joystick_radius / self.player_joystick_radius

            self.player_joystick_angle = math.atan2(event_pos[1] - self.player_joystick_y, event_pos[0] - self.player_joystick_x)
            
        # BOMB JOYSTICK
        if self.bomb_controlling_finger == event.finger_id:
            radius = math.hypot(event_pos[0] - self.bomb_joystick_x, event_pos[1] - self.bomb_joystick_y)
            if radius < self.bomb_joystick_radius:
                self.bomb_joystick_power = radius / self.bomb_joystick_radius
            else:
                self.bomb_joystick_power = self.bomb_joystick_radius / self.bomb_joystick_radius

            self.bomb_joystick_angle = math.atan2(event_pos[1] - self.bomb_joystick_y, event_pos[0] - self.bomb_joystick_x)
       
        
    elif event.type == pygame.FINGERUP:
        # Remove touch when lifted
        if event.finger_id in self.touches:
            del self.touches[event.finger_id]

        if self.player_controlling_finger == event.finger_id:
            self.player_joystick_tapping = False
            self.player_joystick_angle = 0
            self.player_joystick_power = 0
            self.player_controlling_finger = None
            self.player.x_vel = 0

        if self.player.name in ["TNT", "Archer"] and not self.AUTO_SHOOT:
            if self.bomb_controlling_finger == event.finger_id:
                if self.bomb_joystick_tapping:
                    bomb_x = self.player.rect.x
                    bomb_y = self.player.rect.y
                    bomb_vel_x = math.cos(self.bomb_joystick_angle) * self.bomb_joystick_power * 500
                    bomb_vel_y = math.sin(self.bomb_joystick_angle) * self.bomb_joystick_power * 1000
                    if self.player.name == "TNT":
                        obj = Bomb.spawn(bomb_x, bomb_y, self.player, self.sounds)
                        obj.rect.bottom = self.player.rect.bottom - 50
                        obj.rect.x = self.player.rect.left if self.player.direction == "right" else self.player.rect.right
                    else:
                        obj = Arrow.spawn(bomb_x, bomb_y, self.player, self.sounds)
                        obj.rect.center = self.player.rect.center
                
                    obj.x_vel = bomb_vel_x
                    obj.y_vel = bomb_vel_y

                    if self.player.name == 'Archer':
                        obj.degree, _ = get_degree(obj.x_vel, obj.y_vel, obj.degree)

                        playit("arrow_fly", self.player)

                    self.bombs.list.append(obj)
                    self._draw_list_dirty = True

                    self.player.wait = 0

                self.bomb_joystick_tapping = False
                self.bomb_joystick_angle = 0
                self.bomb_joystick_power = 0
                self.bomb_controlling_finger = None

    elif event.type == pygame.FINGERMOTION:
        event_pos = (event.x * Settings.WIDTH, event.y * Settings.HEIGHT)

        # Update touch position
        self.touches[event.finger_id] = event_pos

        # PLAYER JOYSTICK
        if self.player_controlling_finger == event.finger_id:
            radius = math.hypot(event_pos[0] - self.player_joystick_x, event_pos[1] - self.player_joystick_y)
            if radius < self.player_joystick_radius:
                self.player_joystick_power = radius / self.player_joystick_radius
            else:
                self.player_joystick_power = self.player_joystick_radius / self.player_joystick_radius

            self.player_joystick_angle = math.atan2(event_pos[1] - self.player_joystick_y, event_pos[0] - self.player_joystick_x)
            
        # BOMB JOYSTICK
        if self.bomb_controlling_finger == event.finger_id:
            radius = math.hypot(event_pos[0] - self.bomb_joystick_x, event_pos[1] - self.bomb_joystick_y)
            if radius < self.bomb_joystick_radius:
                self.bomb_joystick_power = radius / self.bomb_joystick_radius
            else:
                self.bomb_joystick_power = self.bomb_joystick_radius / self.bomb_joystick_radius

            self.bomb_joystick_angle = math.atan2(event_pos[1] - self.bomb_joystick_y, event_pos[0] - self.bomb_joystick_x)
      
#'''
                    
def joybuttondown(self, player):
        player.attacking = False
        if _aiming(player):
            if not player.dashing:
                player.x_vel = 0
            return
        data = []
        x_vel = 0
        y_vel = 0

        x_axis = player.joystick.get_axis(0)  # Left-right movement
        y_axis = player.joystick.get_axis(1)  # Up-down movement

        # Update rectangle position
        x_vel = int(x_axis * 10)
        y_vel = int(y_axis * 10)

        for i in range(player.joystick.get_numbuttons()):
            if player.joystick.get_button(i):  # Check if the button is pressed
                data.append(i)

        if True:
            from ..scripts import dash_bar
            dash_bar.hold(player, 5 in data)          # the dash lasts while the button is held (and the bar lasts)
            if 5 in data:
                if try_dash(self, player):
                    player.dashing = True
                    player.startx = player.rect.x
                    if self.game_speed == self.max_game_speed:
                        self.game_speed = 0.1

            if x_vel < 0 and 5 not in data and not player.dashing:
                player.move_left(abs((x_vel / 10) * player.current_speed))
                self.request_x = -200

            elif x_vel > 0 and 5 not in data and not player.dashing:
                self.request_x = 200
                player.move_right(abs((x_vel / 10) * player.current_speed))

            if y_vel < 0:
                self.request_y = -200
                if player.zone:
                    player.swim_up()
                elif player.can_jump():
                    player.jump()

            if y_vel > 0:
                self.request_y = 200
                if player.zone:
                    player.swim_down()

        # Zoom control
        if 8 in data:  # Zoom in
            player.target_zoom = min(player.target_zoom + 0.05, player.zoom_max)
        elif 9 in data:  # Zoom out
            player.target_zoom = max(player.target_zoom - 0.05, player.zoom_min)
        
        if 7 in data:
            if player.target:
                player.shoot_arrow(quantity=player.ammo_count("arrow"))

        if 6 in data:
            #if not (player.name in ["TNT", "Archer"]) or self.AUTO_SHOOT:
                player.attacking = True

                self.request_attack = True
                player.animation_count += 1
                if "attack" not in player.sprite_sheet:
                    player.animation_count = 0

        goal = _zoom_goal(player)
        player.zoom += (goal - player.zoom) * 0.1  # Smooth transition
        if abs(goal - player.zoom) < 0.005:
            player.zoom = goal   # snap: an endless 0.1 ease keeps the zoom-keyed sprite caches rebuilding

def handle_finger_movement(self):
    if _aiming(self.player):                  # charm mode: the screen taps choose a target instead
        return
    if self.player_joystick_tapping:
        player = self.player

        x_vel = math.cos(self.player_joystick_angle) * self.player_joystick_power

        y_vel = math.sin(self.player_joystick_angle) * self.player_joystick_power * self.player_y_vel_power

        if x_vel < 0 and not player.dashing:
            player.move_left(abs(player.current_speed))
        elif x_vel > 0  and not player.dashing:
            player.move_right(abs(player.current_speed))

        if y_vel < -10:
            if player.zone:
                player.swim_up()
            elif player.can_jump():
                player.jump()
        
        if y_vel > 5:
            self.request_y = 200
            if player.zone:
                player.swim_down()

        
def handle_keypress(self, player):
    player.attacking = False
    keys = self.keys  # Universal pressed keys

    if not keys:
        return

    if _aiming(player):
        if not player.dashing:
            player.x_vel = 0
        return
    
    if keys[pygame.K_SPACE]:
        self.game_speed = 0.1

    # B is the charm key for the arrow-keys player now (scripts/charm_mode.py); the old debug
    # arrow barrage lives on F9 and only in debugging mode
    if Settings.DEBUGGING_MODE and keys[Settings.DEBUG_ARROW_KEY]:
        if player.target:
            player.shoot_arrow(quantity=player.ammo_count("arrow"))
        
        # DROP COINS
        #for i in range(100):
        '''
        self.damageable_objects.append(Tree(player.rect.x + 20, player.rect.y, self))
        self.damageable_objects_dirty = True
        '''
        '''
        bomb_obj = Bomb(player.rect.x, player.rect.y, player, self.sounds)
        bomb_obj.update_sprite()
        bomb_obj.x_vel = 32
        bomb_obj.y_vel = -400

        self.bombs.list.append(bomb_obj)
        '''
        '''treasure = Treasure(player.rect.centerx, player.rect.centery, 'green', self, 'dropped')
        treasure.rect.left = player.rect.right + 10
        treasure.x_vel = 320
        self.treasure_list.append(treasure)'''
        
    dash_pressed = ((keys[pygame.K_RCTRL] and player.keyboard_num == 0)
                    or (keys[pygame.K_LCTRL] and player.keyboard_num == 1))
    from ..scripts import dash_bar
    dash_bar.hold(player, dash_pressed)               # the dash lasts while the key is held (and the bar lasts)
    if dash_pressed:
        if try_dash(self, player):
            player.dashing = True
            player.startx = player.rect.x
            if self.game_speed == self.max_game_speed:
                self.game_speed = 1

    if ((keys[pygame.K_LEFT] and player.keyboard_num == 0) or (
            keys[pygame.K_a] and player.keyboard_num == 1)):
        player.move_left(abs(player.current_speed))
        self.request_x = -200

    if ((keys[pygame.K_RIGHT] and player.keyboard_num == 0) or (
            keys[pygame.K_d] and player.keyboard_num == 1)):
        self.request_x = 200
        player.move_right(abs(player.current_speed))

    if (keys[pygame.K_UP] and player.keyboard_num == 0) or (keys[pygame.K_w] and player.keyboard_num == 1):
        self.request_y = -200
        if player.zone:
            player.swim_up()
        elif player.can_jump():
            player.jump()

    if (keys[pygame.K_DOWN] and player.keyboard_num == 0) or (keys[pygame.K_s] and player.keyboard_num == 1):
        self.request_y = 200
        if player.zone:
            player.swim_down()

    if (keys[pygame.K_RSHIFT] and player.keyboard_num == 0) or (keys[pygame.K_LSHIFT] and player.keyboard_num == 1):
        #if not (player.name in ["TNT", "Archer"]) or self.AUTO_SHOOT:
            player.attacking = True

            self.request_attack = True
            player.animation_count += 1
            if "attack" not in player.sprite_sheet:
                player.animation_count = 0

    # Zoom control
    if (keys[pygame.K_z] and player.keyboard_num == 1) or (
            keys[pygame.K_n] and player.keyboard_num == 0):  # Zoom in
        player.target_zoom = min(player.target_zoom + 0.05, player.zoom_max)
    if (keys[pygame.K_x] and player.keyboard_num == 1) or (
            keys[pygame.K_m] and player.keyboard_num == 0):  # Zoom out
        player.target_zoom = max(player.target_zoom - 0.05, player.zoom_min)

    player.zoom += (_zoom_goal(player) - player.zoom) * 0.1  # Smooth transition
    player.zoom = round(player.zoom, 2)