import sys
import pygame
import random
import threading

from .assets import Assets
from .settings import Settings
from .entities.controls import handle_fingers
from .objects.object_utils import CACHED_OBJECT_IMAGES, CACHED_OBJECT_ZOOMED_IMAGES

from .scripts import player_helper as p_s
from .scripts.functions import (
    refresh_joysticks, calculate_viewports, 
    parallax_bg, player_settings,
    draw_minimap
)
from .scripts.physics import PHYSICS as physics
from .scripts.menu import RPGMenu
from .scripts.music import music
from .scripts.cache import (
    cache_font, CACHED_ENTITY_IMAGES,
    CACHED_IMAGES, CACHED_RECTS, GLOW_CACHE,
    FONTS, reset_cache, remove_unused_key,
    build_cache_debug_info
)

from .level.main.update_funcs import update_game_logic
from .level.main.draw_funcs import draw
from .ui import ui_theme
from .ui.shop_screen import open_shop
from .level.main.objectives import make_objective
from .scripts import death_rules
from .scripts import achievements
from .scripts import paths
from .ui.defeat_screen import open_defeat
from .ui import combat_fx, world_intro, lighting, minimap, charm_ui, door_fx
from .debug_tools import frame_profiler as _fp      # optional, off unless PIXABY_PROFILE is set
from .scripts import charm_mode
from .objects import arrow_trap
from .scripts import coop_loot
from .entities.controls import try_dash
from .scripts import shop_effects
from .ui.objective_hud import ObjectiveHUD


WORLD_WIDTH, WORLD_HEIGHT = 1600, 1200

JOIN_HELP_SECTIONS = [
    ("KEYBOARD", [
        "Press RIGHT SHIFT to join as a keyboard player using the arrow "
        "keys to move and RIGHT CTRL to ready up.",
        "Press LEFT SHIFT to join as a keyboard player using WASD to move "
        "and LEFT CTRL to ready up.",
        "Press the same Shift key again to leave.",
    ]),
    ("JOYSTICK / GAMEPAD", [
        "Press A (button 0) on any connected controller to join.",
        "Press RB (button 5) to ready up.",
        "Press A again to leave.",
    ]),
    ("STARTING THE RUN", [
        "The descent begins automatically once every joined player has "
        "marked themselves READY.",
    ]),
]

PLAYER_WINS_RECT_CACHE_PER_PLAYER = 2       # clear once entries > 2x player count
FONTS_CACHE_CAP = 5


# Camera shake effect
def apply_shake(cam_rect, intensity=5):
    cam_rect.x += random.randint(-intensity, intensity)
    cam_rect.y += random.randint(-intensity, intensity)


def main(self, code=0):
    music.scene("menu")                       # the title song until a level starts

    lastx = 0
    lasty = 0

    self.running = True
    self.done = False

    if self.MULTIPLAYER:
        if self.SERVER:
            from .networking import server
            server.initialize_server(self, "0.0.0.0", 12331)
            e2 = threading.Thread(target=server.get_clients, args=(self,))
            e2.start()
        else:
            from .networking import client
            # 192.168.43.192, 127.0.0.1, 192.168.43.249
            client.connect_to_server(self, "127.0.0.1", 12331)
            print("Connection Successful...")

    exit_code = True
    pos = (9999999, 9999999)
    abs_pos = (9999999, 9999999)

    clicked = False

    self.speed = 10  # Adjust speed sensitivity
    self.x_vel = 0
    self.x_axis = 0
    self.y_vel = 0
    self.y_axis = 0

    self.SECONDS = 0
    self.delta = 0
    
    # Timer variables
    self.start_ticks = pygame.time.get_ticks()
    self.current_ticks = pygame.time.get_ticks()
    self.pause_start = 0
    self.pause_total = 0
    self.elapsed_seconds = (self.current_ticks - self.start_ticks - self.pause_total) // 1000
    self.seconds = 0
    self.minutes = 0
    self.master_clock = 0
    
    height = 2

    # SCREEN BUTTONS
    sw, sh = self.window.get_rect().size
    font = cache_font(("impact", int(sw * 0.02)))
    
    def menu(_object):
        print("Start Menu!")
        _object.MENU = True
        _object.pause_start = pygame.time.get_ticks()
        _object.menu()
        _object.pause_total += pygame.time.get_ticks() - _object.pause_start
        print("Menu Ended!")

    def spectate(_object):
        print("Started Spectate Window!")
        _object.SPECATING = True
        _object.spectate()
        print("Ended Spectate Window!")

    def view(_object):
        _object.VIEW = not _object.VIEW
        print(f"Object Info is {'ON' if _object.VIEW else 'OFF'}")
        
    def attack(_object):
        if not (_object.player.name in ["TNT", "Archer"]) or _object.AUTO_SHOOT:
                if _object.player.duration == 0:
                    _object.player.animation_count = 0
                    _object.player.attacking = True

    def dash(_object):
        if try_dash(_object, _object.player):
            from .scripts import dash_bar
            dash_bar.pulse(_object.player)            # a tap cannot be "held": give it a short burst
            _object.player.dashing = True
            _object.player.startx = _object.player.rect.x
            if _object.game_speed == _object.max_game_speed:
                _object.game_speed = 0  

    button_data = [
        ("MENU", menu, [self]), 
        ("SPECTATE", spectate, [self]), 
        ("VIEW", view, [self]),
        ("ATTACK", attack, [self]),
        ("DASH", dash, [self])
    ]

    layout = [
        (1 - 0.08 - 0.01, 0.2, 0.08, 0.06), 
        (0.5 - 0.2 - 0.03, 0.03, 0.2, 0.06),
        (0.5 + 0.03, 0.03, 0.2, 0.06),
        (0.65, 0.89, 0.25, 0.06),
        (1 - 0.35, 1 - 0.5, 0.1, 0.08)
    ]

    menu = RPGMenu(self.window, font, button_data, layout)
    MENU_BUTTON_ALPHA = 120      # the in-game MENU button sits low-key over the world
    
    coin_data = {'yellow': 'gold', 'red': 'ruby', 'green': 'emerald', 'pink': 'pearl'}
    e = "NO ERROR"
    dead_overlay = None
    refresh_joysticks(self)

    while self.running:
        _fp.frame_start()
        # THE SHOOT BUTTONS (touch players with AUTO_SHOOT only)
        menu.exclude((3, (not self.AUTO_SHOOT or not self.touch_enabled)))
        menu.exclude((4, (not self.AUTO_SHOOT or not self.touch_enabled)))
        
        # SETTING BUTTONS ACCORDING TO MODE
        if self.controller_selection:
            menu.exclude(
                [
                    (0, self.controller_selection), 
                    (1, self.controller_selection), 
                    (2, self.controller_selection),
                    (3, self.controller_selection),
                    (4, self.controller_selection)
                ]
            )
        
        else:
            menu.exclude(
                [
                    (0, False), 
                    (1, len(self.local_players) != 1 or not self.DEBUGGING_MODE),    # SPECTATE: debug only
                    (2, len(self.local_players) != 1 or not self.DEBUGGING_MODE)     # VIEW: debug only
                ]
            )

        if self.MULTIPLAYER:
            if not self.SERVER:
                self.request_attack = False
                self.request_x, self.request_y = (0, 0)

        # CAPTURE EVENTS
        self.mouse_pos = pygame.mouse.get_pos()
        self.events = pygame.event.get()

        # CHECK IF NEW LEVEL
        if self.new:
            if getattr(self, "level_completed", False):
                achievements.tracker().on_level_complete(self)      # needs the objective, so before it is cleared
                if not self.MULTIPLAYER:
                    world_intro.play_cleared(self)                  # WORLD CLEARED card + rank, then the shop
            self.objective = None       # the old level's objective must not judge the next one
            # A finished level (not the first load of a run) goes through the shop first
            if getattr(self, "level_completed", False):
                self.level_completed = False
                # The shop belongs to the campaign; one-off levels (co-op, My Worlds, test maps) skip it
                if not self.MULTIPLAYER and self.level_folder == paths.STORY:
                    open_shop(self)

            # The same world loading again (not after a win) is a retry: a short intro
            self._intro_retry = getattr(self, "_intro_last_level", None) == self.level_key()
            self.world_intro = None
            self._intro_draw = None
            charm_mode.release_everyone(self)            # friends never carry over a level
            self.load_world()
            music.play_level(self)                      # the song for this level's biome / type (scripts/music.py)

            self.start_ticks = pygame.time.get_ticks()
            self.pause_total = 0

            self.new = False
            reset_cache(self)
        
        if not self.env_ready:
            # --------------------------------------------------------------------------------------------------------------
            # LOADING SCREEN
            # --------------------------------------------------------------------------------------------------------------
            self.loading()
            
            # AFTER LOADING WORLD DATA
            for player in self.player_slots:
                point = random.choice(self.points)
                player.rect.x, player.rect.y = point # self.start_points
                print(point)
                player.personalise(2)

            # Enemies exist now, so the level's objective can read them
            self.objective = make_objective(self)
            self.objective_hud = ObjectiveHUD()
            self.objective_hud.hidden = True            # shown once the world intro ends
            coop_loot.on_level_loaded(self)             # co-op worlds: a few power-ups in random places
            self._intro_pending = not self.MULTIPLAYER
            combat_fx.fx().reset_level()
            death_rules.begin_level(self)       # stand the fallen back up, snapshot for "restart level"

            if self.MULTIPLAYER:
                if not self.SERVER:
                    self.create_new_world()

        # WORLD INTRO: starts once the world is loaded and every player is ready
        if getattr(self, "_intro_pending", False) and self.env_ready and not self.controller_selection:
            self._intro_pending = False
            self.world_intro = world_intro.WorldIntro(self, quick=getattr(self, "_intro_retry", False))
            self._intro_last_level = self.level_key()
            self._intro_draw = None
        intro = getattr(self, "world_intro", None)
        if intro is not None:
            self.events = intro.filter_events(self.events)

        if not self.controller_selection:
            # Calculate elapsed time (in seconds)
            self.current_ticks = pygame.time.get_ticks()
            self.elapsed_seconds = (self.current_ticks - self.start_ticks - self.pause_total) // 1000
            self.minutes = self.elapsed_seconds // 60
            self.seconds = self.elapsed_seconds % 60
            self.game_time = f"{self.minutes:02}:{self.seconds:02}"

        '''if self.player.dead:
            self.GAME_OVER = True
            self.game_over()'''

        self.clicked = False
        for event in self.events:
            if event.type == pygame.QUIT:
                self.running = False
                break
                
            if event.type == pygame.KEYUP:
                self.keys = pygame.key.get_pressed()

            if event.type == pygame.KEYDOWN:
                self.keys = pygame.key.get_pressed()

                # CHARM MODE: its key, selection, confirm and ESC (story only; returns True when it used the key)
                if not self.controller_selection and charm_mode.on_key(self, event):
                    continue

                # HOMING TRAP KEY: drops a bought trap kit (objects/arrow_trap.py)
                if not self.controller_selection and not getattr(self, "EDIT_WORLD", False) and arrow_trap.on_key(self, event):
                    continue

                # HANDLE MENU BUTTONS EVENTS
                menu.handle_key(event.key)
                
                if self.controller_selection:
                    if event.key == pygame.K_h:
                        ui_theme.show_help_overlay(self, "JOIN THE ABYSS", JOIN_HELP_SECTIONS)
                        continue

                    if self.keys[pygame.K_LSHIFT] or self.keys[pygame.K_RSHIFT]:
                        if self.keys[pygame.K_RSHIFT]:
                            key = ["keyboard", 0]
                        else:
                            key = ["keyboard", 1]

                        if key in self.controllers:
                            for player in self.local_players:
                                if player.key == key:
                                    break
        
                            player.keyboard_num = None
                            player.control_type = None
                            self.local_players.remove(player)
                            self.players.remove(player)
                            self._draw_list_dirty = True
                            self._entities_dirty = True

                            self.controllers.remove(key)

                            for i, player in enumerate(self.local_players):
                                viewport = calculate_viewports(self, len(self.local_players))[i]
                                player.viewport = pygame.Rect(*viewport)
                                player.camera_update()
                            
                        
                        elif len(self.controllers) < 5 and len(self.local_players) < self.max_local_players():
                            slots = self.player_slots.copy()
                            [slots.remove(player) for player in self.local_players]
                            player = slots[0]
                            
                            self.controllers.append(key)
                            player.key = key
                            player.keyboard_num = key[1]
                            player.control_type = "keyboard"
                            self.local_players.append(player)
                            self.players.append(player)
                            self._draw_list_dirty = True
                            self._entities_dirty = True


                            for i, player in enumerate(self.local_players):
                                viewport = calculate_viewports(self, len(self.local_players))[i]
                                player.viewport = pygame.Rect(*viewport)
                                player.camera_update()
                            
                        self.update_player_edit()

                        
                    if self.keys[pygame.K_RCTRL] or self.keys[pygame.K_LCTRL]:
                        if self.keys[pygame.K_RCTRL]:
                            key = ["keyboard", 0]
                        else:
                            key = ["keyboard", 1]

                        for player in self.local_players:
                            if key == player.key:
                                p_s.ready(self, player.id)
                                break

                # DEBUG KEYS
                if self.DEBUGGING_MODE:
                    if self.keys[pygame.K_0]:
                        self.debug['0'] = not self.debug.get('0', False)

                    elif self.keys[pygame.K_1]:
                        self.debug['1'] = not self.debug.get('1', False)

                    elif self.keys[pygame.K_2]:
                        self.debug['win'] = not self.debug.get('win', False)

                    elif self.keys[pygame.K_3]:
                        self.debug['path'] = not self.debug.get('path', False)

                    elif self.keys[pygame.K_4]:
                        self.debug['map'] = not self.debug.get('map', False)
                    
                    elif self.keys[pygame.K_9]:
                        self.debug['range'] = not self.debug.get('range', False)

                # EXIT KEYS
                if self.keys[pygame.K_ESCAPE]:
                    # ESC opens the pause menu (same as the MENU button); QUIT lives in there
                    self.MENU = True
                    self.pause_start = pygame.time.get_ticks()
                    self.menu()
                    self.pause_total += pygame.time.get_ticks() - self.pause_start
                    self.keys = pygame.key.get_pressed()
            
            if event.type == pygame.JOYAXISMOTION:
                # HANDLE MENU JOY_BUTTONS EVENTS
                menu.handle_joy(event, "axis")
                
            if event.type == pygame.JOYHATMOTION and not self.controller_selection:
                if charm_mode.on_joy(self, event):
                    continue

            if event.type == pygame.JOYBUTTONDOWN:
                if not self.controller_selection and charm_mode.on_joy(self, event):
                    continue
                if not self.controller_selection and arrow_trap.on_joy(self, event):
                    continue
                
                # HANDLE MENU JOY_BUTTONS EVENTS
                menu.handle_joy(event)
                
                if self.controller_selection:
                    if event.button == 0:
                        key = ["joystick", event.joy]

                        if key in self.controllers:
                            for player in self.local_players:
                                if player.key == key:
                                    break
                         
                            player.keyboard_num = None
                            player.control_type = None
                            self.local_players.remove(player)
                            self.players.remove(player)
                            self._draw_list_dirty = True
                            self._entities_dirty = True

                            self.controllers.remove(key)

                            for i, player in enumerate(self.local_players):
                                viewport = calculate_viewports(self, len(self.local_players))[i]
                                player.viewport = pygame.Rect(*viewport)
                            

                        elif len(self.controllers) < 5 and len(self.local_players) < self.max_local_players():
                            slots = self.player_slots.copy()
                            [slots.remove(player) for player in self.local_players]
                            player = slots[0]

                            self.controllers.append(key)
                            player.key = key
                            player.joystick = self.active_joys[key[1]]
                            player.joystick_id = key[1]
                            player.control_type = key[0]
                            
                            self.local_players.append(player)
                            self.players.append(player)
                            self._draw_list_dirty = True
                            self._entities_dirty = True

                            for i, player in enumerate(self.local_players):
                                viewport = calculate_viewports(self, len(self.local_players))[i]
                                player.viewport = pygame.Rect(*viewport)
                            
                        self.update_player_edit()
                                
                    if event.button == 5:
                        for player in self.local_players:
                            if event.joy == player.joystick_id:
                                p_s.ready(self, player.id)
                                break

            if event.type == (pygame.JOYDEVICEADDED or pygame.JOYDEVICEREMOVED):
                refresh_joysticks(self)
                for player in self.local_players:
                    key = player.key
                    if player.control_type == "joystick":
                        player.joystick = self.active_joys[key[1]]
                        player.joystick_id = key[1]
                
            if event.type == pygame.MOUSEBUTTONUP:
                # MOUSE SCROLLING
                if event.button == 1:
                    clicked = False

            if event.type == pygame.MOUSEMOTION:
                # ABS_POS IS MOUSE POSITION BASED ON PLAYER'S (DISTANCE AND ZOOM) OFFSET.
                abs_pos = ((self.mouse_pos[0] / self.zoom) + self.offset_x, ((self.mouse_pos[1] / self.zoom) + self.offset_y))
                
                # MOUSE SCROLLING
                if clicked:
                    self.offset_x -= event.rel[0]
                    self.offset_y -= event.rel[1]

            if event.type == pygame.FINGERDOWN:
                # ABS_POS IS MOUSE POSITION BASED ON PLAYER'S (DISTANCE AND ZOOM) OFFSET.
                event_pos = (event.x * Settings.WIDTH, event.y * Settings.HEIGHT)
                if not self.controller_selection and charm_mode.on_pointer(self, (event.x * self.window.get_width(), event.y * self.window.get_height())):
                    continue

                # HANDLE BUTTON EVENTS
                menu.handle_mouse(event)

            if event.type == pygame.MOUSEBUTTONDOWN:
                if not self.controller_selection and event.button == 1 and charm_mode.on_pointer(self, event.pos):
                    continue
                # ABS_POS IS MOUSE POSITION BASED ON PLAYER'S (DISTANCE AND ZOOM) OFFSET.
                abs_pos = ((self.mouse_pos[0] / self.zoom) + self.offset_x, ((self.mouse_pos[1] / self.zoom) + self.offset_y))
        
                # HANDLE BUTTON EVENTS
                menu.handle_mouse(event)

                if self.controller_selection and event.button == 1 and self.join_help_rect.collidepoint(event.pos):
                    ui_theme.show_help_overlay(self, "JOIN THE ABYSS", JOIN_HELP_SECTIONS)

                # MOUSE SCROLLING
                if event.button == 1:
                    clicked = True

            if self.player.control_type == 'touch':
                handle_fingers(self, event)
                    
        if exit_code == 'quit':
            self.running = False
            del self
            return

        if not self.running:
            break
            
        # ENTITY INFO
        if self.VIEW:
            #all_entities = .get_objects(self.game.entities_map, self.rect, 0)
            for entity_ in self.all_entities:
                if entity_.rect.collidepoint(abs_pos):
                    self.pause_start = pygame.time.get_ticks()
                    self.entity_info(entity_)
                    self.pause_total += pygame.time.get_ticks() - self.pause_start

                    abs_pos = (99999999, 9999999)
        
        # MENU BUTTONS UPDATE
        menu.update(self.mouse_pos)
        menu.buttons[0].alpha = min(menu.buttons[0].alpha, MENU_BUTTON_ALPHA)   # keep the fade-in, cap the resting alpha

        if self.controller_selection:
            length_of_ready = len([player.key for player in self.player_slots if player.ready])
            if  length_of_ready != 0 and length_of_ready == len(self.local_players) \
                    and len(self.local_players) >= self.min_local_players():
                self.controller_selection = False
            
            objects_to_draw = []

        else:
            # UPDATE EVERYTHING
            # REMOVING DEAD OBJECTS
            _fp.lap("events / menus / setup")
            if intro is not None and not intro.done:
                # the world holds still while its intro plays: tick once to fill the lists, then reuse them
                if getattr(self, "_intro_draw", None) is None:
                    for player in self.local_players:
                        player.camera_update()
                    self._intro_draw = update_game_logic(self)
                objects_to_draw = self._intro_draw
            else:
                objects_to_draw = update_game_logic(self)
            _fp.lap("game logic (update_game_logic)")

        if not self.MULTIPLAYER or (self.MULTIPLAYER and self.SERVER):
            # CHECK LEVEL OBJECTIVE (see level/main/objectives.py)
            objective = getattr(self, "objective", None)
            if objective is not None and not self.controller_selection and (intro is None or intro.done):
                objective.update(self.dt)
                if objective.check():
                    objective.on_complete()
                    continue

            # EVERYONE DOWN -> revive with pearls, or restart the floor
            if not self.MULTIPLAYER and not self.controller_selection and (intro is None or intro.done) \
                    and death_rules.all_humans_dead(self):
                if death_rules.second_wind(self):
                    continue                                  # a free revive from the shop: no defeat screen
                if open_defeat(self) == "restart":
                    death_rules.restart_level(self)
                    continue

        
        # --------------------------------------------------------------------------------------------------------------
        # DRAWING THE SCREEN
        # --------------------------------------------------------------------------------------------------------------
        self.window.fill(self.bg_color)

        # PARALLAX BACKGROUND
        self.bg_particles = parallax_bg(
            self.window, 
            Settings.WIDTH, Settings.HEIGHT, 
            self.bg_particles, self.master_clock,
            threshold=20, height=0,
            parallax_color=Settings.PARALLAX, bg_color=Settings.BG_COLOR
        )

        if self.MULTIPLAYER:
            if self.SERVER:
                # NETWORKING SYNCING
                for player in self.client_list:
                    server.send_sync(self, player, objects_to_draw)
            else:
                client.send_sync(self, self.player)

        # WORLD INTRO + COMBAT EFFECTS: advance once per frame (before the cameras are computed)
        if intro is not None:
            intro.update(self.clock.get_time() / 1000.0)
            if intro.done:
                self.world_intro = None
                self._intro_draw = None
        if not self.controller_selection:
            combat_fx.fx().update(self.dt)
        intro = getattr(self, "world_intro", None)
        _cfx = combat_fx.fx()
        _light = lighting.get(self)
        _light.update(self.clock.get_time() / 1000.0)

        # DRAW EVERY PLAYER'S SCREEN
        for i, player in enumerate(self.local_players):
            player.camera_update()
            viewport = self.window.subsurface(player.view_rect)
            if self.controller_selection:
                # BORDERS FOR PLAYER WINDOWS
                pygame.draw.rect(self.window, (0, 200, 200), player.view_rect, 1, 20)
                sw, sh = player.view_rect.size

                font = cache_font(("impact", int(sw * 0.03)))

                # HUD
                label = font.render(f"{player.control_type.capitalize()} | {('WASD' if player.keyboard_num else '< ^ >') if player.control_type == 'keyboard' else player.joystick_id}", True, (255, 255, 255))
                self.window.blit(label, (player.view_rect.x + sw * 0.03, player.view_rect.y + sh * 0.05))

                label = font.render(f"PLAYER {player.id} : {'READY' if player.ready else 'NOT READY'}", True, (255, 255, 255))
                self.window.blit(label, (player.view_rect.x + sw * 0.5 - label.get_width() / 2, player.view_rect.y + sh * 0.8 + font.get_height()))
                
                player_settings(self, player)
                continue

            
            # SET GAME SETTINGS TO THE FIRST PLAYER
            if player.entity_id == 0:
                self.offset_x = player.cam_rect.x
                self.offset_y = player.cam_rect.y
                self.zoom = player.zoom

            # SHAKE FADE
            if player.shake_frames > 0:
                if Settings.SCREEN_SHAKE:
                    apply_shake(player.cam_rect, intensity=player.shake_intensity)
                player.shake_frames -= 1

            # DRAW EVERYTHING ON THE PLAYER'S PERSPECTIVE
            _fp.lap("camera / prep")
            draw(self, viewport, objects_to_draw, player.view_rect.size, player.cam_rect.topleft, player.zoom, player.rect, i)
            # LIGHTING: darkness + lights + fireflies over the world, under the HUD
            _light.apply(viewport, objects_to_draw, player.cam_rect.topleft, player.zoom, player)
            _cfx.draw_world(viewport, player.cam_rect.topleft, player.zoom, ui_theme.font)
            _fp.lap("world draw + lighting")

            # POINTERS + MINIMAP are shop items: drawn only once bought (story shop), never in the editor
            if not getattr(self, "EDIT_WORLD", False):
                if shop_effects.owned_level(player, "target_pointers") > 0:
                    player.target_system.draw_pointers(window=viewport, cam=player.cam_rect, zoom=player.zoom)
                mm_level = shop_effects.owned_level(player, "minimap")
                if mm_level > 0:
                    minimap.draw(self, viewport, player, mm_level, view_rect=player.view_rect,
                                 window_width=self.window.get_width())

            # CHARMS: reticle, hearts over friends, particles (world) + the charm / dash buttons, timer, banners (HUD)
            if not getattr(self, "EDIT_WORLD", False) and intro is None and self.type != "preview":
                door_fx.draw_world(self, viewport, player.cam_rect.topleft, player.zoom)     # door suction / arrival / flare
                charm_ui.draw_world(self, viewport, player.cam_rect.topleft, player.zoom, player)
                charm_ui.draw_hud(self, viewport, player.view_rect, player)

            # DRAW CONTROLLERS
            if player.control_type == 'joystick':
                pass

            elif player.control_type == 'touch':
                self.draw_shooting_stick()
                self.draw_player_stick()

            else:
                pass
            
            # DEBUG WINDOW
            if self.DEBUGGING_MODE:
                if self.debug.get('map', None):
                    # DRAW MAP CHUNKS
                    for pos in self.map.values():
                        pygame.draw.rect(self.window, (0, 200, 200), (int((pos[0].x - player.cam_rect.x) * player.zoom), int((pos[0].y - player.cam_rect.y) * player.zoom), int(pos[0].width * player.zoom), int(pos[0].height * player.zoom)), 5, 20)
                    
            # BORDERS FOR PLAYER WINDOWS
            pygame.draw.rect(self.window, (0, 200, 200), player.view_rect, 1, 20)
            sw, sh = player.view_rect.size

            font = cache_font(("impact", int(sw * 0.02)))

            # HUD: mission card (world, time, HP, what to do, progress) - see ui/objective_hud.py.
            # It lives top-left and is narrower than the gap before the SPECTATE button, so
            # nothing is hidden behind the buttons any more.
            intro_on = intro is not None
            hud = getattr(self, "objective_hud", None)
            if hud is not None and getattr(self, "objective", None) is not None:
                hud_bottom = hud.draw(self, self.window, player.view_rect, player, self.objective, self.dt,
                                      player.cam_rect.topleft, player.zoom, world_intro.world_info(self))
            else:
                label = font.render(f"LEVEL: {self.level}", True, (255, 255, 255))
                self.window.blit(label, (player.view_rect.x + sw * 0.03, player.view_rect.y + sh * 0.05))
                label = font.render(f"GAME_TIME: {self.minutes}:{self.seconds}", True, (255, 255, 255))
                self.window.blit(label, (player.view_rect.x + sw * 0.03, player.view_rect.y + sh * 0.06 + font.get_height()))
                hud_bottom = player.view_rect.y + sh * 0.07 + font.get_height() * 2

            if not intro_on:
                # combo counter, kill-streak banners, hurt / low-health vignette
                _cfx.draw_screen(self.window, player.view_rect, player, ui_theme.font, self.dt)

            if player is self.local_players[0] and not intro_on:
                achievements.tracker().draw_toasts(self.window, player.view_rect, min(0.1, getattr(self, "real_dt", self.dt)))

            if self.type != "preview":
                # PLAYER INFO (coins stack under the mission card)
                # Coins always show; they sit under whichever card (small or full) is up
                for j, data in enumerate(coin_data.items() if not intro_on else ()):
                    k, v = data
                    size = (player.view_rect.width * 0.04, player.view_rect.width * 0.04)
                    key = (k, v, size)
                    if key not in CACHED_IMAGES:
                        CACHED_IMAGES[key] = pygame.transform.scale(Assets.GEM_SPRITES[k][0], size)

                    self.window.blit(CACHED_IMAGES[key], (
                        player.view_rect.x + sw * 0.03, hud_bottom + (j * size[1])))
                    label = font.render(f"{getattr(player, f'{v}_coins')}", True, (255, 255, 255))
                    self.window.blit(label, (player.view_rect.x + sw * 0.03 + size[0] + sw * 0.01,
                                            hud_bottom + (j * size[1] + (size[1] / 4))))

            # DEBUG WINDOW
            if self.DEBUGGING_MODE:
                if self.debug.get('win', None):
                    font = cache_font(("impact", int(sw * 0.01)))
                    
                    # Cache sizes are derived automatically - add/remove a
                    # cache from this dict and build_cache_debug_info() works
                    # out the label and length itself, no hand-written len()
                    # line to keep in sync.
                    debug_lines = build_cache_debug_info({
                        'object_sprite_cache': self.object_sprite_cache,
                        'entity_sprite_cache': self.entity_sprite_cache,
                        'FONTS': FONTS,
                        'GLOW_CACHE': GLOW_CACHE,
                        'CACHED_IMAGES': CACHED_IMAGES,
                        "CACHED_RECTS": CACHED_RECTS,
                        'CACHED_ENTITY_IMAGES': CACHED_ENTITY_IMAGES,
                        'CACHED_ENTITY_ZOOM_IMAGES': self.CACHED_ENTITY_ZOOM_IMAGES,
                        'CACHED_OBJECT_IMAGES': CACHED_OBJECT_IMAGES,
                        'CACHED_OBJECT_ZOOMED_IMAGES': CACHED_OBJECT_ZOOMED_IMAGES,
                    })
                    debug_lines += [
                        (f"HIT-WALL-FOR: {player.hit_wall_for}", 0),
                        (f"BEEN_FALLING-FOR: {player.fall_count}", 0),
                        (f"ON-GROUND-FOR: {player.on_ground_for}", 0),
                        (f"IN-AIR-FOR: {self.dt}", 0),
                        (f"ENV_READY: {len(self.bombs.list)}", 0),
                        (f"MODE_DETAILS: {Settings.MODE_DETAILS}", 0),
                    ]

                    for i, (text, depth) in enumerate(debug_lines):
                        label = font.render(("  " * depth) + text, True, (255, 255, 255))
                        self.window.blit(label, (
                            player.view_rect.x + sw * 0.25 + depth * sw * 0.02, player.view_rect.y + sh * 0.1 + (font.get_height() + sw * 0.01) * i))
            
            if not self.controller_selection:
                if not dead_overlay:
                    dead_overlay = pygame.Surface(player.view_rect.size).convert_alpha()
                    dead_overlay.fill((222, 0, 0))
                    dead_overlay.set_alpha(100)
                
                if player.dead:
                    self.window.blit(dead_overlay, player.view_rect.topleft)

        if self.controller_selection:
            w, _ = self.window.get_size()
            btn_w, btn_h = 200, 40
            self.join_help_rect = pygame.Rect(0, 0, btn_w, btn_h)
            self.join_help_rect.midtop = (w // 2, 10)
            ui_theme.button(self.window, self.join_help_rect, "? HOW TO JOIN", accent=ui_theme.CORAL)
            if getattr(self, "SPLIT_SCREEN", False) and not self.MULTIPLAYER:
                low, high = self.min_local_players(), self.max_local_players()
                need = f"{low} to {high} players" if low != high else f"{high} players"
                if high <= 1:
                    note = "SPLIT SCREEN  -  this world is a solo run"
                elif len(self.local_players) < low:
                    note = f"SPLIT SCREEN  -  {len(self.local_players)} / {low} joined  -  this world needs {need}"
                else:
                    note = f"SPLIT SCREEN  -  {len(self.local_players)} joined  -  up to {high}, everyone press READY"
                ui_theme.text_centered(self.window, note, (w // 2, self.join_help_rect.bottom + 18), 12,
                                       ui_theme.GOLD if len(self.local_players) >= low else ui_theme.CORAL, True)

        # WORLD INTRO paints over everything except the menu buttons
        if intro is not None:
            intro.draw(self.window)

        # MENU BUTTONS (hidden while the intro plays, so the cinematic stays clean)
        if intro is None:
            if self.type != "preview":
                menu.draw()
        
        # GAME FPS
        if self.DEBUGGING_MODE:
            self.get_fps()

        # --------------------------------------------------------------------------------------------------------------
        # HANDLING CACHE
        # --------------------------------------------------------------------------------------------------------------
        
        # HANDLE RECT CACHE
        if len(CACHED_RECTS["player_wins"]) > PLAYER_WINS_RECT_CACHE_PER_PLAYER * len(self.local_players):
            CACHED_RECTS["player_wins"].clear()
        
        zooms = [self.zoom] + [player.zoom for player in self.local_players]
        remove_unused_key(CACHED_OBJECT_ZOOMED_IMAGES, zooms)
        remove_unused_key(self.CACHED_ENTITY_ZOOM_IMAGES, zooms)
        
        # HANDLE OTHER CACHE
        if len(FONTS) > FONTS_CACHE_CAP:
            FONTS.clear()

        _fp.lap("HUD / minimap / UI / cache")
        pygame.display.flip()
        _fp.lap("display.flip")
        
        # HANDLE DELTA TIME
        raw_dt = self.clock.tick(self.FPS) / 1000.0
        _fp.lap(_fp.IDLE)
        self.real_dt = raw_dt                           # unscaled: toasts and other UI must not follow slow-mo
        self.game_speed = min(self.max_game_speed, self.game_speed + 0.1)
        if not self.controller_selection:
            charm_mode.update(self, raw_dt)             # charm timer + slow-mo ease + friends, all in REAL time
        self.dt = round(min(0.1, raw_dt * self.game_speed * charm_mode.time_scale(self)), 3)

        self.master_clock += int(raw_dt * 80)

    if getattr(self, "_to_start", False):
        # "Return to start" from the ending: back to the title screen, the window stays open
        self._to_start = False
        self.new = True
        self.level_completed = False
        self.MENU = False
        return

    _fp.finish()
    pygame.quit()
    sys.exit(0)