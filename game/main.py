import pygame
import threading
import math

from .settings import Settings
from .windows import Windows
from .entities.entities import Player
from .objects.objects import Bombs
from .data.palletes.entities import entity_pallete

from .scripts import player_helper as p_s
from .scripts import paths
from .scripts.touch import touch_enabled
from .scripts.functions import calculate_viewports   # was missing: create_players() crashed on Linux
from .scripts.sounds import Sounds, Volume, Volumes
from .scripts.menu import RPGMenu

from .level.main.level_loader import Level_Loader
from .level.editor.editor_tools import Level_Editor_Tools


'''
TARGET:
    LEVEL 10
    FUCTIONAL LOOK
    FUCTIONAL LOGIC & FLOW
    FUCTIONAL AI
    STORY
    GOOD UI & UX
'''

# GAME CLASS
class Game(Level_Loader, Level_Editor_Tools, Settings, Windows):
    def __init__(self, level):
        self.create_new_world()
        self.env_ready = False
        
        self.create_grid()
        self.level = level
        self.new = True
    
        self.initialise_constants() 
        self.initialise_main_window()
        self.initialise_grid()
        self.initialise_player_edit()

        self.type = "normal"
        
        # CACHE
        self.CACHED_ENTITY_ZOOM_IMAGES = {}
        self.entity_sprite_cache = {}
        self.object_sprite_cache = {}        
        self.cached_objects = {}
        
        self.players = []
        self.local_players = []
        self.player_slots = []
        self.saved_players = {}

        self.controllers = []
        self.controller_selection = True
        self.join_help_rect = pygame.Rect(0, 0, 0, 0)
        self.control_type = 'joystick'

        self.create_players()
        
        self.volumes = Volumes([Volume(y=200 * i, sound="Background" if i == 0 else 'In Game') for i in range(2)], self)
        self.bombs = Bombs(game=self)
        self.sounds = Sounds(self.player, 4)

        # Dictionary to store active touches
        self.touches = {}
        self.keys = {}
    
        self.zoom = 1.0
        self.min_zoom = 0.5
        self.max_zoom = 1.5
        self.zoom_speed = 0.05
    
        self.scroll_area_width = 200
        self.offset_x = 0
        self.offset_y = 0
        
        self.lock = threading.Lock()
        self.log = 0
        self.debug = {}
        
        self.dt = 0
        self.game_speed = 1
        self.max_game_speed = 1

        self.bg_color = (10, 10, 10)
        self.parallax_color = (22, 19, 40)
        self.bg_particles = []
        
        self.chunk_w, self.chunk_h = (12, 12)
        

    def create_players(self):
        self.player = Player(0, 0, 50, 50, 'TNT', 'Green', game=self)
        self.player.control_type = 'keyboard'
        self.player.keyboard_num = 0
        self.saved_players[self.player.id] = self.player
        self.player_slots.append(self.player)

        # WHEN YOU WANT TO LAUNCH THE GAME WITH DEFAULT KEYBOARD -> if True:
        if False:
            key = ["keyboard", 0]
            #self.controller_selection = False
            self.controllers.append(key)
            self.player.control_type = key[0]
            self.players.append(self.player)
            self.local_players.append(self.player)

            for i, player in enumerate(self.local_players):
                viewport = calculate_viewports(self, len(self.local_players))[i]
                player.viewport = pygame.Rect(*viewport)
        
            self.update_player_edit()

        # TOUCHSCREEN: join player 1 with the on-screen sticks when a touch device is present
        # (Settings.TOUCH_CONTROLS / PIXABY_TOUCH, see scripts/touch.py). Keyboards and gamepads
        # still join the normal way on the join screen.
        self.touch_enabled = touch_enabled(Settings.TOUCH_CONTROLS)
        if self.touch_enabled:
            key = ["touch", 0]
            self.controllers.append(key)
            self.player.control_type = key[0]
            self.local_players.append(self.player)
            self.players.append(self.player)
            
            for i, player in enumerate(self.local_players):
                viewport = calculate_viewports(self, len(self.local_players))[i]
                player.viewport = pygame.Rect(*viewport)
        
            self.update_player_edit()
            
        player2 = Player(0, 0, 50, 50, 'TNT', 'Green', game=self)
        player2.control_type = 'keyboard'
        player2.keyboard_num = 1
        self.saved_players[player2.id] = player2
        self.player_slots.append(player2)

        player3 = Player(0, 0, 50, 50, 'TNT', 'Green', game=self)
        player3.control_type = 'joystick'
        self.saved_players[player3.id] = player3
        self.player_slots.append(player3)

        player4 = Player(0, 0, 50, 50, 'Pawn', 'Blue', game=self)
        player4.control_type = 'joystick'
        self.saved_players[player4.id] = player4
        self.player_slots.append(player4)
            
    def initialise_constants(self):
        self.menu_bg = pygame.transform.scale(pygame.image.load(paths.asset("background", "menu_bg.jpg")),
                                              (self.WIDTH, self.HEIGHT)).convert()

    def update_main_window_btns_pos(self):
        self.bomb_joystick_x, self.bomb_joystick_y = Settings.WIDTH - self.bomb_joystick_radius - 50, Settings.HEIGHT - self.bomb_joystick_radius - 50

        self.player_joystick_x, self.player_joystick_y = self.player_joystick_radius + 50, Settings.HEIGHT - self.player_joystick_radius - 50


    def layout_touch_sticks(self):
        """Size and place the two on-screen sticks from the current window (also re-run on a screen-mode change)."""
        width_space = Settings.WIDTH * 0.025
        height_space = Settings.HEIGHT * 0.025

        self.bomb_joystick_radius = Settings.WIDTH * 0.125
        self.bomb_joystick_x, self.bomb_joystick_y = Settings.WIDTH - self.bomb_joystick_radius - width_space, Settings.HEIGHT - self.bomb_joystick_radius - height_space

        self.player_joystick_radius = Settings.WIDTH * 0.11
        self.player_joystick_x, self.player_joystick_y = self.player_joystick_radius + width_space, Settings.HEIGHT - self.player_joystick_radius - height_space

    def initialise_main_window(self):
        self.SENSOR_DISTANCE = 100

        self.layout_touch_sticks()

        # Set up the bomb joystick
        self.bomb_joystick_angle = 0
        self.bomb_joystick_power = 0
        self.bomb_joystick_tapping = False
        self.bomb_controlling_finger = None
        self.power_factor = 500
        
        # Set up the player joystick
        self.player_joystick_angle = 0
        self.player_joystick_power = 0
        self.player_joystick_tapping = False
        self.player_controlling_finger = None
        self.player_x_vel_power = 20
        self.player_y_vel_power = 20
        
        self.VIEW = False        
        self.SPECTATING = False
        self.MENU = False
        self.MULTIPLAYER = False
        self.SERVER = False
        self.SPLIT_SCREEN = False       # local co-op on this machine (Mode -> SPLIT SCREEN), see level_loader.max_local_players
        self.level_players = None       # (min, max) players of the chosen co-op world, None for every other level
        
        # Player Settings
        self.AUTO_SHOOT = False

        self.window_rect = self.window.get_rect()

    # -------------------------------------------------- PLAYER EDITOR --------------------------------------------------- #
    def initialise_player_edit(self):
        self.player_types = ['TNT', 'Pawn', 'Warrior', 'Torch', 'Archer']
        self.player_colors = list(entity_pallete.keys())
        self.players_config = {}

    def update_player_edit(self):
        for player in self.players:
            if player.id not in self.players_config:
                self.players_config[player.id] = {
                    'player': player,
                    'confirm_player': None,
                    'player_type_num': player.player_types.index(player.name),
        
                    'player_num': 0,
                    'player_color_num': player.player_colors.index(player.color),

                }

            if player.id in self.players_config:
                data = self.players_config[player.id]

                view_rect = player.viewport.clip(self.window_rect)
                viewport = self.window.subsurface(view_rect)

                sw, sh = viewport.get_size()
                font = pygame.font.SysFont("impact", int(sw * 0.02))
                
                button_data = [
                    ("Back", p_s.back_, [self])
                ]
                menu = RPGMenu(viewport, font, button_data, p_s.layout)

                width = 0.12
                height = 0.06
                menu.add([('TYPE', p_s.change_type, [self, player.id])],
                            [(0.5 - (width / 2) - 0.15, 0.2, width, height)])
                menu.add([('COLOR', p_s.change_color, [self, player.id])],
                            [(0.5 - (width / 2) + 0.15, 0.2, width, height)])

                if player.control_type == "touch":                            
                    menu.add([('READY', p_s.ready, [self, player.id])],
                            [(0.5 - (0.15 / 2), 1 - height - 0.01, 0.15, height)])
                    menu.add([('AUTO_SHOOT', p_s.auto, [self])],
                            [(0.5 - (0.15 / 2), 0.3 + 0.08, 0.15, height)])

                data['window'] = viewport
                data['menu'] = menu

                display_rect = pygame.Rect(
                    int(p_s.rel_rect[0] * sw),
                    int(p_s.rel_rect[1] * sh),
                    int(p_s.rel_rect[2] * sw),
                    int(p_s.rel_rect[3] * sh)
                )
                data['display_rect'] = display_rect

        for player in self.player_slots:
            if player not in self.players and player.id in self.players_config:
                del self.players_config[player.id]

    def get_fps(self):
        # Get and draw FPS
        fps = self.clock.get_fps()
        fps_surface = self.font.render(f"FPS: {int(fps)}", True, (255, 255, 255))
        self.window.blit(fps_surface, (10, 10))

    def draw_player_stick(self):
        # Draw the player joystick
        pygame.draw.circle(self.window, Settings.BLUE, (self.player_joystick_x, self.player_joystick_y),
                           self.player_joystick_radius, 4)

        if self.player_joystick_tapping:
            player_joystick_end_x = self.player_joystick_x + math.cos(
                self.player_joystick_angle) * self.player_joystick_radius * self.player_joystick_power

            player_joystick_end_y = self.player_joystick_y + math.sin(
                self.player_joystick_angle) * self.player_joystick_radius * self.player_joystick_power

            pygame.draw.line(self.window, Settings.BLUE, (self.player_joystick_x, self.player_joystick_y),
                             (int(player_joystick_end_x), int(player_joystick_end_y)), 2)

            pygame.draw.circle(self.window, Settings.BLUE, (int(player_joystick_end_x), int(player_joystick_end_y)),
                               10)

    def draw_shooting_stick(self):

        if self.player.name in ["TNT", "Archer"] and not self.AUTO_SHOOT:
            # Draw the bomb joystick
            pygame.draw.circle(self.window, Settings.RED, (self.bomb_joystick_x, self.bomb_joystick_y),
                               self.bomb_joystick_radius, 5)

            if self.bomb_joystick_tapping:
                bomb_joystick_end_x = self.bomb_joystick_x + math.cos(
                    self.bomb_joystick_angle) * self.bomb_joystick_radius * self.bomb_joystick_power

                bomb_joystick_end_y = self.bomb_joystick_y + math.sin(
                    self.bomb_joystick_angle) * self.bomb_joystick_radius * self.bomb_joystick_power

                pygame.draw.line(self.window, Settings.RED, (self.bomb_joystick_x, self.bomb_joystick_y),
                                 (int(bomb_joystick_end_x), int(bomb_joystick_end_y)), 2)

                pygame.draw.circle(self.window, Settings.RED, (int(bomb_joystick_end_x), int(bomb_joystick_end_y)),
                                   10)

            # Draw the trajectory
            if self.bomb_joystick_tapping:
                trajectory = []
                bomb_x = self.player.rect.centerx
                bomb_y = self.player.rect.centery
                bomb_vel_x = (math.cos(self.bomb_joystick_angle) * self.bomb_joystick_power) * 500
                bomb_vel_y = (math.sin(self.bomb_joystick_angle) * self.bomb_joystick_power) * 1000
                
                if self.player.name == "Archer":
                    gravity = (self.GRAVITY * 0.25) * 0.01
                else:
                    gravity = (self.GRAVITY * 0.5) * 0.01
                
                x_vel = bomb_vel_x * 0.1
                y_vel = bomb_vel_y * 0.1
                
                for _ in range(25):
                    y_vel += gravity

                    bomb_x, bomb_y = (bomb_x + x_vel, bomb_y + y_vel)
                    trajectory.append((bomb_x, bomb_y))

                for dot_x, dot_y in trajectory:
                    pygame.draw.circle(self.window, Settings.RED,
                                       (int(dot_x) - self.offset_x, int(dot_y) - self.offset_y), 5)
                    