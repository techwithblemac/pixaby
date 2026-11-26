import os
import pygame
from os import listdir
from os.path import join

from .scripts.file_loaders import (
    flip, load_sounds, load_sprite_sheets,
    load_sprite_sheets2
)
from .scripts import paths
# TRAPS

# ENEMY SPRITES
_ENEMY_KEYS = {'tnt': 'TNT'}   # folder name -> enemy type name (folders are lowercase)

def create_enemy_sprites():
    states = ['idle', 'run', 'attack_1', 'attack_2']
    names = sorted(_ENEMY_KEYS.get(d, d.capitalize()) for d in listdir(paths.asset('enemies')))
    ENEMY_SPRITES = dict()
    ENEMY_RECT_SPRITES = dict()

    for name in names:
        ENEMY_SPRITES[name] = dict()

        colors = ["Blue"]
        states = ['idle', 'run', 'attack_1', 'attack_2']
        if name == 'Archer':
            states = [('idle_right', 'idle_left'), ('run_right', 'run_left'), ('attack_0', 'attack_0_2'),
                        ('attack_45', 'attack_315'), ('attack_90', 'attack_270'), ('attack_135', 'attack_225'),
                        ('attack_180', 'attack_180_2')]
        
        if name == "Warrior":
            w_ = 6
            h_ = 8
            s = 4
        elif name == "Pawn":
            w_ = 6
            h_ = 6
            s = 4
        elif name == "Torch":
            w_ = 7
            h_ = 5
            s = 3
        elif name == 'TNT':
            w_ = 7
            h_ = 3
            s = 3
        else:
            w_ = 8
            h_ = 7
            s = 7

        for color in colors:
            real_image = pygame.image.load(paths.asset('enemies', name.lower(), f"{name}.png")).convert_alpha()
            ENEMY_SPRITES[name][color] = dict()

            width = real_image.get_width() / w_
            height = real_image.get_height() / h_
            w = 0
            for h, state in enumerate(states[:s]):
                if name == 'Archer':
                    ENEMY_SPRITES[name][color][state[0]] = []
                    ENEMY_SPRITES[name][color][state[1]] = []
                    
                else:
                    ENEMY_SPRITES[name][color][state + '_right'] = []
                    ENEMY_SPRITES[name][color][state + '_left'] = []

                sprites = []
                rect_sprites = []

                for w in range(w_):
                    if (name == 'TNT' and w == 6 and h < 2) or (name == 'Torch' and w == 6 and h > 0) or (
                            name == 'Archer' and w > 5 and h < 2):
                        continue
                    try:
                        trimarea = (w * width, h * height, width, height)
                        sprite = real_image.subsurface(trimarea)

                        from_x = 0
                        from_y = 0

                        if name == 'Warrior':
                            from_x = 76
                            from_y = 67

                        elif name == 'Torch':
                            from_x = 76
                            from_y = 67

                        elif name == 'TNT':
                            from_x = 76
                            from_y = 67

                        elif name == 'Pawn':
                            from_x = 80
                            from_y = 70

                        elif name == 'Archer':
                            from_x = 75
                            from_y = 67

                        photo_width = 192
                        photo_height = 192

                        margin_distance_x = from_x * 2
                        margin_distance_y = from_y * 2

                        width_distance = photo_width - margin_distance_x
                        height_distance = photo_height - margin_distance_y

                        trimarea = (from_x, from_y, width_distance, height_distance)

                        try:
                            sprite_ = sprite.subsurface(trimarea)
                        except:
                            continue
                        rect_sprites.append(sprite_.convert_alpha())
                        sprites.append(sprite.convert_alpha())
                    except Exception as e:
                        print(e)

                if name == 'Archer':
                    ENEMY_SPRITES[name][color][state[0]] = sprites
                    ENEMY_SPRITES[name][color][state[1]] = flip(sprites)
                    
                    sprite = rect_sprites[0]
                    
                    if 'attack_' in state[0]:
                        image_key = (name, 'attack')
                    
                    else:
                        image_key = (name, state[0].replace('_right', '').replace('_left', ''))
                    
                    if image_key in ENEMY_RECT_SPRITES:
                        continue
                    
                    rect = sprite.get_rect(topleft=(0, 0))
                    mask = pygame.mask.from_surface(sprite)
                
                    ENEMY_RECT_SPRITES[image_key] = mask, rect.size

                else:
                    ENEMY_SPRITES[name][color][state + '_right'] = sprites
                    ENEMY_SPRITES[name][color][state + '_left'] = flip(sprites)
                    
                    sprite = rect_sprites[0]
                    image_key = (name, state)
                    
                    rect = sprite.get_rect(topleft=(0, 0))
                    mask = pygame.mask.from_surface(sprite)
                
                    ENEMY_RECT_SPRITES[image_key] = mask, rect.size

    return ENEMY_RECT_SPRITES, ENEMY_SPRITES

SHEET_LENS = dict()
for (name, color) in create_enemy_sprites()[1].items():
    SHEET_LENS[name] = {}
    #print(name)
    for (color, sheet_name) in color.items():
        for (sheet_name, list_) in sheet_name.items():
            SHEET_LENS[name][sheet_name] = len(list_)
            #print("        ", sheet_name, ":", len(list_)) 

def trees():
    # TREE SPRITES
    states = ['idle', 'hit', 'chopped']
    TREE_SPRITES = dict()

    real_image = pygame.image.load(paths.asset('trees', "Tree.png")).convert_alpha()
    width = real_image.get_width() / 4
    height = real_image.get_height() / 3
    w = 0
    for h, state in enumerate(states):

        TREE_SPRITES[state + '_right'] = []
        TREE_SPRITES[state + '_left'] = []

        sprites = []

        for w in range(4):
            if (state == 'hit' and w >= 2 and h == 1) or (state == 'chopped' and w >= 1 and h == 2):
                continue
            try:
                trimarea = (w * width, h * height, width, height)
                sprite = real_image.subsurface(trimarea).convert_alpha()
                sprites.append(sprite)
            except Exception as e:
                print(e)

        TREE_SPRITES[state + '_left'] = flip(sprites)
        TREE_SPRITES[state + '_right'] = sprites

    return TREE_SPRITES

def traps():
    """Slice assets/traps/<Name>/<state>.png into scaled frames.

    Returns ``{"fire": {"off": [..], "hit": [..], "on": [..]}, "spikes": {...}}``.
    Each state is a horizontal strip of FRAME_W-wide frames; every frame is
    scaled up by the trap's own scale (see data/traps.py; nearest neighbour,
    to keep the pixel art crisp).
    """
    from .data.traps import FRAME_W, SCALE, kind_for

    root = paths.asset("traps")
    out = {}
    if not os.path.isdir(root):
        return out

    for name in sorted(listdir(root)):
        folder = join(root, name)
        if not os.path.isdir(folder):
            continue
        scale = kind_for(name).get("scale", SCALE)
        states = {}
        for file in sorted(listdir(folder)):
            if not file.lower().endswith(".png"):
                continue
            sheet = pygame.image.load(join(folder, file)).convert_alpha()
            frames = []
            for i in range(max(1, sheet.get_width() // FRAME_W)):
                frame = sheet.subsurface((i * FRAME_W, 0, FRAME_W, sheet.get_height()))
                frames.append(pygame.transform.scale(
                    frame, (FRAME_W * scale, sheet.get_height() * scale)).convert_alpha())
            states[file[:-4].lower()] = frames
        if states:
            out[name.lower()] = states
    return out

def arrows():
    # ARROW SPRITES
    ARROW_SPRITES = dict()
    states = ["full", "stuck"]
    real_image = pygame.image.load(paths.asset("weapons/arrow/Arrow.png")).convert_alpha()

    for h, state in enumerate(states):
        ARROW_SPRITES[f'{state}'] = []
        ARROW_SPRITES[f'{state}'] = []

        sprites = []
        trimarea = (0, h * 64, 64, 64)
        sprite = real_image.subsurface(trimarea).convert_alpha()
        sprites.append(sprite)

        ARROW_SPRITES[f'{state}'] = sprites

    return ARROW_SPRITES

def death():
    # DEATH SPRITES
    DEAD_SPRITES = dict()
    states = ["death", "sink"]
    real_image = pygame.image.load(paths.asset("dead/dead.png")).convert_alpha()

    for h, state in enumerate(states):
        DEAD_SPRITES[f'{state}_right'] = []
        DEAD_SPRITES[f'{state}_left'] = []

        sprites = []
        for w in range(7):
            trimarea = (w * 128, h * 128, 128, 128)
            sprite = real_image.subsurface(trimarea).convert_alpha()
            from_x = 40
            from_y = 40
            photo_width = 128
            photo_height = 128

            margin_distance_x = from_x * 2
            margin_distance_y = from_y * 2

            width_distance = photo_width - margin_distance_x
            height_distance = photo_height - margin_distance_y

            trimarea = (from_x, from_y, width_distance, height_distance)

            try:
                sprite = sprite.subsurface(trimarea).convert_alpha()
            except Exception as e:
                print(e)
                pass
            sprites.append(sprite)

        DEAD_SPRITES[f'{state}_left'] = flip(sprites)
        DEAD_SPRITES[f'{state}_right'] = sprites

    return DEAD_SPRITES

for (sheet_name, list_) in death().items():
    SHEET_LENS[sheet_name] = len(list_)
    #print(sheet_name, ":", len(list_)) 

def blocks_assets():
    # LOAD BLOCKS
    blocks = {}

    width = 48
    height = 48
    path = paths.asset("terrain", "Terrain2.png")
    image = pygame.image.load(path).convert()
    block_types2 = ['sand', 'mud', 'ice']
    block_sizes2 = ['big', 'small']

    for w, type in enumerate(block_types2):
        blocks[type] = dict()
        for h, size in enumerate(block_sizes2):
            the_width = 48
            the_height = 48
            if h == 1:
                the_width = 32
                the_height = 32
            trimarea = (w * width + (w * 16), h * height, the_width, the_height)
            sprite = image.subsurface(trimarea)
            if size == 'big':
                sprite = pygame.transform.scale(sprite, (64, 64)).convert()
            blocks[type][size] = sprite

    path = paths.asset("terrain")
    for name in os.listdir(path):
        image_pth = paths.asset("terrain", name)
        name = name.replace('.png', '')
        if name in ['Terrain', 'Terrain2']:
            continue
        
        blocks[name] = dict()

        if name == 'window':
            image = pygame.transform.scale(pygame.image.load(image_pth).convert_alpha(), (64, 64))
        else:
            image = pygame.image.load(image_pth).convert()

            if "small" in name:
                image_ = pygame.transform.scale(image, (32, 32))
                blocks[name]["small"] = image_
            
            # big 
            image = pygame.transform.scale(image, (64, 64))

        
        blocks[name]["big"] = image

    return blocks

class Assets:
    # MENU / BACKGROUND
    # Keep all asset-file access centralized here. UI code should consume
    # Assets.MENU_BG rather than opening files from the assets tree itself.
    MENU_BG = pygame.image.load(paths.asset("background", "menu_bg.jpg")).convert()
    
    DOOR = pygame.image.load(paths.asset("doors", "door_open.png")).convert_alpha()
    
    # LOAD MUSIC
    SOUNDS = load_sounds("sounds")

    # DECO SPRITES
    DECO_SPRITES = load_sprite_sheets2("deco", None, 32, 32, False, False)

    # GEM SPRITES
    GEM_SPRITES = load_sprite_sheets2("items", "gems", 16, 16, False, True, 32, 32)

    COLLECTED = load_sprite_sheets2("items", None, 32, 32, False, True, 64, 64)

    # BOMB SPRITES
    BOMB_SPRITES = load_sprite_sheets2("weapons", "bomb", 64, 64, True)

    # EXPLOSION SPRITES
    EXPLOSION_SPRITES = load_sprite_sheets("effects", "explosion", 192, 192, False)

    # FIRE SPRITES
    FIRE_SPRITES = load_sprite_sheets("effects", "fire", 128, 128)

    # EXPRESSION SPRITES
    EXPRESSION_SPRITES = load_sprite_sheets2("expressions", None, 4, 4, False, False, 15, 15)

    blocks = blocks_assets()
    block_types = [['stone_1', 'grass_1'], ['stone_2', 'grass_2'], ['stone_3', 'grass_3']]
    block_sizes = ['big', 'small']

    DEAD_SPRITES = death()
    ARROW_SPRITES = arrows()
    TREE_SPRITES = trees()
    ENEMY_RECT_SPRITES, ENEMY_SPRITES = create_enemy_sprites()
    SHEET_LENS = SHEET_LENS

    TRAPS = traps()  # assets/traps -> {name: {state: [frames]}}

# print(get_total_size(Assets))