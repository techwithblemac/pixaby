import time
import random
import pygame
import math

from ..settings import Settings
from .physics import PHYSICS
from .cache import (
    cache_assets, cache_img, GLOW_CACHE
)
 
def remove_duplicates(garbage_list, grid=False) -> list:
    clean_list = set()
    for garbage in garbage_list:
        clean_list.add(garbage if not grid else garbage[3])

    return list(clean_list)

def remove_duplicates_2(garbage_list) -> list:
    return list(dict.fromkeys(garbage_list))

def find_last(word, char):
    last_index = -1
    while word.find(char) != -1:
        last_index = word.find(char)
        word = word[:last_index] + "&" + word[last_index + 1:]
    return last_index

# CACHED GLOW IMAGES
def glow_img(size, color):
    if (size, color) not in GLOW_CACHE:
        surf = pygame.Surface((size * 2 + 2, size * 2 + 2))
        pygame.draw.circle(surf, color, (surf.get_width() // 2, surf.get_height() // 2), size)
        surf.set_colorkey((0, 0, 0))
        GLOW_CACHE[(size, color)] = surf
    return GLOW_CACHE[(size, color)]


def parallax_bg(window, WIDTH, HEIGHT, bg_particles, master_clock, threshold=None, height=0, parallax_color=(0,20, 9), bg_color=(60, 0, 0)):
    # PARALLAX BACKGROUND
    if threshold is None:
        # Fewer ambient particles on low-spec machines: each one costs 2
        # set_at() pixel writes + 2 alpha-blended blits per frame.
        threshold = 60 if Settings.LOW_SPEC_MODE else 200

    parallax = random.random()
    if parallax < 0.1:
        bg_particles.append(
            [[random.random() * WIDTH, random.random() * HEIGHT - height * parallax], parallax,
             random.randint(1, 10),
             random.random() * 1 + 1, [0, random.uniform(-1, 1), random.uniform(-1, 1)],
             random.choice([parallax_color, bg_color])])

    # Only need reverse-index order so pop() during iteration is safe -
    # sorted() was doing an unnecessary O(n log n) comparison sort every
    # single frame for that. reversed(list(enumerate(...))) gets the same
    # iteration order in O(n).
    for i, p in reversed(list(enumerate(bg_particles))):
        # Reduce size
        size = p[2]
        p[2] -= 0.01

        # Move around
        p[0][1] += p[4][2]
        p[0][0] += p[4][1]

        # Timer
        p[4][0] += 1

        if size < 1:
            window.set_at((int(p[0][0]), int(p[0][1] + height * p[1])), bg_color)
        else:
            if p[4][0] > 60:
                p[4][1] = random.uniform(-1, 1)
                p[4][2] = random.uniform(-0.1, 1)
                p[4][0] = 0

        r1 = int(9 + math.sin((master_clock * random.uniform(1.2, 2)) / 40) * 3) 
        r2 = int(5 + math.sin((master_clock * random.uniform(1, 2)) / 30) * 2)

        window.blit(glow_img(r1, (12, 8, 2)), (p[0][0] - r1 - 1, p[0][1] + height - r1 - 2),
                    special_flags=pygame.BLEND_RGBA_ADD)
        window.blit(glow_img(r2, (24, 16, 3)), (p[0][0] - r2 - 1, p[0][1] + height - r2 - 2),
                    special_flags=pygame.BLEND_RGBA_ADD)

        window.set_at((int(p[0][0]), int(p[0][1] + height)), (255, 255, 255))

        if size < 0:
            bg_particles.pop(i)

    if len(bg_particles) > threshold:
        bg_particles = bg_particles[-threshold:]
    
    return bg_particles
    

# Minimap overlay: the real thing lives in ui/minimap.py (a shop item, see WS-A).
def draw_minimap(surface, player, all_players=None, radius=500, size=(120, 120), map={}):
    """Kept for old callers: draws the level-1 radar for ``player``."""
    from ..ui import minimap
    minimap.draw(player.game, surface, player, 1)

# Grouping world into chunks

class ChunkMap(dict):
    """The chunk dict ({(x, y, w, h): [chunk_rect, [objects]]}) plus a grid index.

    Chunks are a regular grid, so the chunks a rect can touch are found with a
    few integer divisions instead of testing the rect against every chunk
    (physics.get_objects and map_chunks used to do 144 colliderect() calls per
    lookup). candidates() returns a row-major superset of the touching chunks,
    in the same order dict iteration gave them, so callers still run their own
    colliderect() and get identical results.
    """

    def setup_grid(self, minx, miny, sw, sh, nx, ny, padl, padr, padt, padb, cells):
        self.minx, self.miny = minx, miny
        self.sw, self.sh = sw, sh
        self.nx, self.ny = nx, ny
        self.padl, self.padr, self.padt, self.padb = padl, padr, padt, padb
        self.cells = cells                      # same cell lists as the dict values, row-major
        self._cand_memo = {}                    # (c0, c1, r0, r1) -> tuple of cells; cells never change

    def candidates(self, rect):
        sw, sh = self.sw, self.sh
        if sw <= 0 or sh <= 0:
            return self.cells
        nx, ny = self.nx, self.ny
        c0 = max(0, int((rect.left - self.minx - self.padr) // sw) - 1)
        c1 = min(nx - 1, int((rect.right - self.minx + self.padl) // sw) + 1)
        r0 = max(0, int((rect.top - self.miny - self.padb) // sh) - 1)
        r1 = min(ny - 1, int((rect.bottom - self.miny + self.padt) // sh) + 1)
        if c0 > c1 or r0 > r1:
            return ()
        key = (c0, c1, r0, r1)
        found = self._cand_memo.get(key)
        if found is not None:
            return found
        cells = self.cells
        if c0 == 0 and c1 == nx - 1:
            out = tuple(cells[r0 * nx:(r1 + 1) * nx])
        else:
            out = []
            for r in range(r0, r1 + 1):
                base = r * nx
                out.extend(cells[base + c0:base + c1 + 1])
            out = tuple(out)
        self._cand_memo[key] = out      # callers only iterate it, so sharing one tuple is safe
        return out

    def candidates_many(self, rects):
        """Union of candidates() for several rects, still row-major and unique."""
        seen = {}
        for rect in rects:
            for cell in self.candidates(rect):
                seen[id(cell)] = cell
        if len(seen) <= 1:
            return list(seen.values())
        order = {id(c): i for i, c in enumerate(self.cells)}
        return sorted(seen.values(), key=lambda c: order[id(c)])


def create_chunks(map, minx, miny, maxx, maxy, chunk_w=6, chunk_h=6, clear_chunks=False, overlap=True):
    if clear_chunks:
        map = {}

    # a fresh, empty map becomes an indexed ChunkMap; a map that already holds
    # chunks keeps being filled the old way
    indexed = not map
    if indexed:
        map = ChunkMap()
        cells = []

    size = (0, 0)
    height = miny
    for h in range(chunk_h):
        width = minx
        for w in range(chunk_w):
            size = abs(maxx - minx) // chunk_w, abs(maxy - miny) // chunk_h
            rect = (width, height, size[0], size[1])
            width += size[0]
            rect_ = pygame.Rect(rect)
            if overlap:
                rect_ = rect_.inflate(128, 128)
                rect_.x -= 64
                rect_.y -= 64
            cell = [rect_, []]
            map[rect] = cell
            if indexed:
                cells.append(cell)

        height += size[1]

    if indexed and chunk_w > 0 and chunk_h > 0 and len(cells) == chunk_w * chunk_h:
        # how far the (possibly shifted) chunk rect sticks out of its base cell
        r0 = cells[0][0]
        sw, sh = size
        padl, padt = minx - r0.x, miny - r0.y
        padr, padb = r0.right - (minx + sw), r0.bottom - (miny + sh)
        map.setup_grid(minx, miny, sw, sh, chunk_w, chunk_h, padl, padr, padt, padb, cells)
    elif indexed:
        map.cells = list(map.values())
        map.sw = map.sh = 0

    return map


def map_chunks(map, objects, minx, miny, maxx, maxy, chunk_w=6, chunk_h=6, clear_chunks=False, grid=False, overlap=True, strip_outline_blocks=False):
    if not map:
        map = create_chunks(map, minx, miny, maxx, maxy, chunk_w, chunk_h, clear_chunks, overlap)
    else:
        # Reuse the existing chunk rects/list objects in place instead of
        # rebuilding the whole grid from scratch every time this is
        # called (previously the caller had to deepcopy a blank template
        # map for this — now the same map can just be cleared and refilled).
        for cell in map.values():
            cell[1].clear()

    if strip_outline_blocks:
        objects = PHYSICS.get_outline_blocks(objects, tile_size=64)

    indexed = isinstance(map, ChunkMap) and hasattr(map, "cells")
    for object_ in objects:
        if getattr(object_, "type", None) == "moving_platform":
            continue
        rect = object_[0] if grid else object_.rect
        for obs in (map.candidates(rect) if indexed else map.values()):
            if obs[0].colliderect(rect):
                obs[1].append(object_)

    map.version = getattr(map, "version", 0) + 1     # lets physics drop its cached rect lists
    return map

def calculate_viewports(self, n):
    sw, sh = Settings.WIDTH, Settings.HEIGHT
    if n == 1:
        return [(0, 0, sw, sh)]
    elif n == 2:
        return [(0, 0, sw // 2, sh), (sw // 2, 0, sw // 2, sh)]
    elif n == 3:
        return [(0, 0, sw // 2, sh // 2), (sw // 2, 0, sw // 2, sh // 2), (sw // 4, sh // 2, sw // 2, sh // 2)]
    else:
        return [
                   (0, 0, sw // 2, sh // 2), (sw // 2, 0, sw // 2, sh // 2),
                   (0, sh // 2, sw // 2, sh // 2), (sw // 2, sh // 2, sw // 2, sh // 2)
               ][:n]


def refresh_joysticks(self):
    self.active_joys = []
    for i in range(pygame.joystick.get_count()):
        j = pygame.joystick.Joystick(i)
        j.init()
        j.rumble(1, 1, 500)
        jid = j.get_id()
        self.active_joys.append(j)

def player_settings(self, player):
    mouse_pos = self.mouse_pos
    
    players = self.players_config
    id_ = player.id
    menu = players[id_]['menu']
    
    for event in self.events:
        if player.control_type == "joystick":
            if event.type == pygame.JOYAXISMOTION:
                if event.joy == player.joystick_id:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event, "axis")
                
            if event.type == pygame.JOYBUTTONDOWN:
                if event.joy == player.joystick_id:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event)
            
        else:
            if event.type == pygame.KEYDOWN:
                menu.handle_key(event.key, player.keyboard_num)
            
        if event.type == pygame.MOUSEBUTTONDOWN:
            menu.handle_mouse(event, player.viewport.topleft,
                                                    player.keyboard_num)

    # DRAW
    if True:
        player = players[id_]['player']
        if players[id_]['player_color_num'] > len(player.player_colors) - 1:
            players[id_]['player_color_num'] = 0

        if players[id_]['player_type_num'] > len(player.player_types) - 1:
            players[id_]['player_type_num'] = 0

        players[id_]['player_type'] = player.player_types[players[id_]['player_type_num']]

        try:
            players[id_]['player_color'] = player.player_colors[players[id_]['player_color_num']]
        except Exception as e:
            print(e)
        
        sprites = cache_assets((players[id_]['player_type'], players[id_]['player_color'], 'idle_right'))
        self.sprite_index = (self.animation_count //
                                3) % len(sprites)
        self.sprite = pygame.transform.scale(sprites[self.sprite_index], players[id_]['display_rect'].size)
        self.animation_count += 1

        players[id_]['window'].blit(self.sprite, players[id_]['display_rect'].topleft)

        players[id_]['menu'].update(mouse_pos, player.viewport.topleft)
        players[id_]['menu'].draw()
        
def draw_vertical_gradient(start_color, end_color, window, HEIGHT, WIDTH):
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(start_color[0] * (1 - ratio) + end_color[0] * ratio)
        g = int(start_color[1] * (1 - ratio) + end_color[1] * ratio)
        b = int(start_color[2] * (1 - ratio) + end_color[2] * ratio)
        pygame.draw.line(window, (r, g, b), (0, y), (WIDTH, y))


def get_dynamic_color(time_offset=0):
    # Create smooth RGB cycling using sine wave functions
    r = int(128 + 127 * math.sin(pygame.time.get_ticks() * 0.001 + time_offset))
    g = int(128 + 127 * math.sin(pygame.time.get_ticks() * 0.001 + 2 + time_offset))
    b = int(128 + 127 * math.sin(pygame.time.get_ticks() * 0.001 + 4 + time_offset))
    return r, g, b

                
# Function to draw text on the screen
def draw_text(surface, text, position, font, color):
    text_surface = font.render(text, True, color)
    surface.blit(text_surface, position)

# Text ------------------------------------------------------- #

class My_Text:
    def __init__(self, text=None, x=None, y=None):
        self.text = 'WHOOKID' if not text else text
        self.initialize(x, y)
        self.offset_x = 0
        self.offset_y = 10

        self.update()
        # Title animation
        self.glow_alpha = 0
        self.animation_speed = 2  # animation speed
        self.glow_max = 100
        self.glow_min = 0
        self.alpha_direction = 1

    def initialize(self, x=None, y=None):
        self.x = Settings.WIDTH // 2 if not x else x
        self.y = 10 if not y else y

    def update(self):
        self.title_surface = Settings.FONT.render(self.text, True, Settings.WHITE)
        self.rect = self.title_surface.get_rect(topleft=(self.x, self.y))

    def draw(self):
        """Animated title: letters bob in a slow wave, warm palette glow
        breathes behind them, with a crisp ink drop-shadow."""
        from ..ui import ui_theme as ui
        t = pygame.time.get_ticks() / 1000.0
        size = max(36, int(Settings.WIDTH * 0.045))
        if getattr(self, "_glyph_size", None) != size:
            self._glyph_size = size
            f = pygame.font.SysFont("serif", size, bold=True)
            self._glyphs = [(ch, f.render(ch, True, ui.CREAM), f.render(ch, True, ui.INK),
                             f.render(ch, True, ui.CORAL)) for ch in self.text]
            self._title_w = sum(g[1].get_width() for g in self._glyphs) + int(size * 0.08) * (len(self.text) - 1)
            self._title_h = f.get_height()
            halo = pygame.Surface((self._title_w + size * 2, self._title_h * 2))
            halo.fill((0, 0, 0))
            hw, hh = halo.get_size()
            for i in range(20):
                k = 1 - i / 20
                c = tuple(int(ch * 0.05 * (i + 1) / 20 * 4) for ch in ui.CORAL)
                r = pygame.Rect(0, 0, int(hw * k), int(hh * k))
                r.center = (hw // 2, hh // 2)
                pygame.draw.ellipse(halo, c, r)
            self._halo = halo

        win = Settings.window
        x = self.x - self._title_w // 2
        y = self.y + int(size * 0.15)

        # breathing halo (additive)
        pulse = 0.75 + 0.25 * math.sin(t * 1.6)
        halo = self._halo
        if pulse < 0.999:
            hv = int(255 * pulse)
            tmp = halo.copy()
            tmp.fill((hv, hv, hv), special_flags=pygame.BLEND_RGB_MULT)
            halo = tmp
        win.blit(halo, (self.x - halo.get_width() // 2, y + self._title_h // 2 - halo.get_height() // 2),
                 special_flags=pygame.BLEND_RGB_ADD)

        spacing = int(size * 0.08)
        for i, (ch, main, shadow, glow) in enumerate(self._glyphs):
            dy = math.sin(t * 2.2 - i * 0.45) * size * 0.06
            gx, gy = x, int(y + dy)
            glow.set_alpha(int(90 + 60 * math.sin(t * 2.2 - i * 0.45)))
            win.blit(glow, (gx, gy + 2))
            win.blit(shadow, (gx + 3, gy + 4))
            win.blit(main, (gx, gy))
            x += main.get_width() + spacing

        self.rect = pygame.Rect(self.x - self._title_w // 2, y, self._title_w, self._title_h)


class TypeText:
    def __init__(self, text, pos, font, color=(255, 255, 255), speed=50):
        self.full_text = text
        self.current_text = ""
        self.font = font
        self.color = color
        self.pos = pos
        self.speed = speed  # characters per second

        self.index = 0
        self.start_time = time.time()
        self.done = False

    def update(self):
        if self.done:
            return

        elapsed = time.time() - self.start_time
        chars_to_show = int(elapsed * self.speed)

        if chars_to_show >= len(self.full_text):
            self.current_text = self.full_text
            self.done = True
        else:
            self.current_text = self.full_text[:chars_to_show]

    def draw(self, surface, infinite=False):
        if self.done and not infinite:
            return
        lines = self.current_text.split('\n')
        y_offset = 0
        for line in lines:
            rendered_line = self.font.render(line, True, self.color)
            surface.blit(rendered_line, (self.pos[0], self.pos[1] + y_offset))
            y_offset += self.font.get_height()

    def skip(self):
        self.current_text = self.full_text
        self.done = True

