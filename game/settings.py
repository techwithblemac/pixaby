import os

import pygame

from .scripts import paths, screen_mode, graphics_prefs
from .version import VERSION, TITLE, WINDOW_TITLE      # VERSION comes from the VERSION file (game/version.py)

paths.enter_base_dir()          # the one place the working directory is set (see scripts/paths.py)
_icon_path = paths.asset("icons", "icon.png")

pygame.init()

# Initialize joystick
pygame.joystick.init()

class Settings:
    pygame.display.set_caption(WINDOW_TITLE)
    icon = pygame.image.load(_icon_path)
    
    pygame.display.set_icon(icon)
    
    # The game is LANDSCAPE ONLY: the window is always wider than tall, there is no portrait layout and
    # nothing reacts to rotation / resize events (so no WINDOWDISPLAYCHANGED handling is needed either).
    # The screen mode (full screen / 800x600 / 1280x960) is the remembered one, and changes at runtime
    # from Game Settings: scripts/screen_mode.py rewrites WIDTH, HEIGHT, window and window_rect.
    window = screen_mode.initial_window()
    WIDTH, HEIGHT = window.get_size()
    window_rect = window.get_rect()

    # Fonts
    font_size = 30
    font = pygame.font.Font(None, font_size)
    menu_font = pygame.font.SysFont("impact", 30)
    health_font = pygame.font.Font(None, 20)
    display_font = pygame.font.Font(None, 50)
    FONT = pygame.font.SysFont("consolas", 48)
    SMALL_FONT = pygame.font.SysFont("consolas", 32)

    FPS = 30
    GRAVITY = 800

    # Machines with 2 or fewer logical processors (older dual-core CPUs,
    # e.g. a Pentium with no hyperthreading) get scaled-down effects and
    # smaller caches by default - see functions.py cache_img/cache_assets/
    # parallax_bg. Override manually (True/False) if the heuristic guesses
    # wrong for a given machine.
    LOW_SPEC_MODE = (os.cpu_count() or 4) <= 2
    MODE_DETAILS = f"Detected {os.cpu_count()} logical processors, LOW_SPEC_MODE={LOW_SPEC_MODE}"
    print(MODE_DETAILS)
    
    # Atmosphere (see game/ui/lighting.py)
    # (switched in Game Settings -> GRAPHICS and remembered in graphics.json, see scripts/graphics_prefs.py)
    LIGHTING = graphics_prefs.saved("LIGHTING", True)      # dynamic darkness + torch / fire / player lights
    SHADOWS = graphics_prefs.saved("SHADOWS", True)        # soft contact shadows under entities and coins
    FIREFLIES = graphics_prefs.saved("FIREFLIES", True)    # glowing fireflies drifting around the camera

    # Befriend Charm keys, by keyboard_num: 0 = arrow-keys player (B), 1 = WASD player (C). Joystick: button 4.
    CHARM_KEYS = {0: pygame.K_b, 1: pygame.K_c}
    CHARM_JOY_BUTTON = 4
    # Homing Trap key (drops a bought trap kit), by keyboard_num: 0 = arrow-keys player (V), 1 = WASD player (E). Joystick: button 3.
    TRAP_KEYS = {0: pygame.K_v, 1: pygame.K_e}
    TRAP_JOY_BUTTON = 3
    DEBUG_ARROW_KEY = pygame.K_F9   # the old debug arrow barrage (Settings.DEBUGGING_MODE only)

    # Camera (see game/scripts/camera.py)
    CAMERA_MODE = "smooth"   # "smooth" (dead-zone, look-ahead, lag) or "classic" (locked to the player)
    SCREEN_SHAKE = True      # off for shake-sensitive players

    # Touchscreens (see game/scripts/touch.py): "auto" = use touch when a touch device is found,
    # "on" = always, "off" = never. The PIXABY_TOUCH environment variable overrides this.
    TOUCH_CONTROLS = "auto"

    BG_SOUNDS_VOLUME = 0.2
    IN_GAME_SOUNDS_VOLUME = 0.1

    # Colors
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    GRAY = (200, 200, 200)
    BLUE = (0, 0, 255)
    RED = (255, 0, 0)
    YELLOW = (255, 255, 0)
    ORANGE = (255, 100, 0)
    PURPLE = (255, 0, 255)
    GREEN = (0, 255, 0)
    DARK_BG = (15, 15, 25)
    SKY_BLUE = (135, 206, 235)    
    BG_COLOR = (10, 10, 10)
    PARALLAX = (22, 19, 40)
    
    clock = pygame.time.Clock()

    DEBUGGING_MODE = True

    ENTITY_ZOOM_CACHE_MAX_LEVELS = 400          # per-zoom sprite cache cap (100 was below what one screen needs, so it thrashed)
    OBJECT_ZOOMED_IMAGES_MAX_PER_KEY = 600      # per-zoom object image cache cap (now also holds zoom 1)
    OBJECT_IMAGES_OTHER_CAP = 200
    OBJECT_IMAGES_ARROWS_CAP = 150

    MAX_CACHED_IMAGES = 400
    MAX_CACHED_ENTITY_IMAGES = 20

