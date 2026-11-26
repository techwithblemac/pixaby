import sys
from array import array
import pygame

# BLOCK PICKER
def get_block(type_="stone_2", size='big', width=None, height=None, perspective="fore"):
    from .cache import cache_img
    # type_ = random.choice(['rock_1', 'grass_1', 'rock_2', 'grass_2', 'rock_3', 'grass_3', 'sand', 'mud', 'ice'])
    # size = random.choice(['big', 'small'])

    if not width and not height and size == 'big':
        width, height = (64, 64)

    if not width and not height and size == 'small':
        width, height = (32, 32)

    key = (type_, size, width, height, perspective)
    return cache_img(key, fill=False, assets=True)
    # return Assets.blocks[type_][size]

# Rotating images from the center    
def blit_rotate_center(win, image, top_left, angle, offset_x=0, offset_y=0):
    rotated_image = pygame.transform.rotate(image, angle)
    new_rect = rotated_image.get_rect(
        center=image.get_rect(topleft=top_left).center)
    pygame.draw.rect(win, (2, 2, 2), (new_rect.topleft[0], new_rect.topleft[1], 10, 10))
    win.blit(rotated_image, (new_rect.topleft[0] - offset_x, new_rect.topleft[1] - offset_y))



def apply_pallete(unchanged_image, pallete, type_="single", obj_="block"):
    if type_ == "list":
        processed_images = []
        for image in unchanged_image:
            image_ = image.copy()
            for swap in pallete:
                image_ = pallete_swap(image_, (0, 0, 0), (0, 0, 1))
                image_ = pallete_swap(image_, swap[0], swap[1])
                image_.set_colorkey((0, 0, 1, 255))    
            processed_images.append(image_)
        
        return processed_images
    
    else:
        image_ = unchanged_image.copy()
        for swap in pallete:
            if obj_ == "block":
                image_ = pallete_swap(image_, swap[0], swap[1])
                image_.set_colorkey((0, 0, 0, 0))
            else:
                image_ = pallete_swap(image_, (0, 0, 0), (0, 0, 1))
                image_ = pallete_swap(image_, swap[0], swap[1])
                image_.set_colorkey((0, 0, 1, 255))

        return image_


def _build_door_sprite_slow(base, frame_swaps, portal_swaps):
    """The original pixel-by-pixel version. Used only when the fast path can't be (odd pixel formats)."""
    image = base.copy()
    width, height = image.get_size()
    for x in range(width):
        for y in range(height):
            r, g, b, a = image.get_at((x, y))
            if a == 0:
                continue
            new = (frame_swaps if a == 255 else portal_swaps).get((r, g, b))
            if new:
                image.set_at((x, y), (*new, a))
    return image


_to_bytes = getattr(pygame.image, "tobytes", None) or pygame.image.tostring
_from_bytes = getattr(pygame.image, "frombytes", None) or pygame.image.fromstring


def build_door_sprite(base, frame_swaps, portal_swaps):
    """Recolour a door sprite, keeping its per-pixel alpha.

    The door's portal is drawn semi-transparent in the *same* greys as its
    stone frame, so pixels are told apart by alpha: fully opaque pixels are
    frame (``frame_swaps``), partly transparent ones are portal
    (``portal_swaps``). Both are ``{old_rgb: new_rgb}`` dicts and every
    pixel is looked up once, so swaps can never chain into each other.

    Fast version: a sprite only has a handful of distinct colours, so each distinct pixel value is
    decided once (a tiny lookup table) and the pixel buffer is rewritten in one pass, instead of
    a get_at / set_at call per pixel (which froze the game for seconds when trees were first
    drawn). The result is pixel-for-pixel identical to the slow version.
    """
    if base.get_bitsize() != 32 or not (base.get_flags() & pygame.SRCALPHA) or array("I").itemsize != 4:
        return _build_door_sprite_slow(base, frame_swaps, portal_swaps)

    size = base.get_size()
    pixels = array("I")
    pixels.frombytes(_to_bytes(base, "RGBA"))

    order = sys.byteorder
    table = {}
    changed = False
    for value in set(pixels):
        table[value] = value                          # default: pixel stays as it is
        r, g, b, a = value.to_bytes(4, order)        # bytes come out in R, G, B, A memory order
        if a == 0:
            continue
        new = (frame_swaps if a == 255 else portal_swaps).get((r, g, b))
        if new:
            table[value] = int.from_bytes(bytes((new[0], new[1], new[2], a)), order)
            changed = True

    if not changed:
        return base.copy()

    pixels = array("I", map(table.__getitem__, pixels))     # every distinct value is in the table
    image = _from_bytes(pixels.tobytes(), size, "RGBA")
    try:
        return image.convert_alpha()                  # same pixel format as the original base.copy()
    except pygame.error:                              # no display yet: the surface is still correct
        return image


def pallete_swap(surf, old_c, new_c):
    # credit : DaFluffyPotato
    image_copy = pygame.Surface(surf.get_size())
    image_copy.fill(new_c)
    surf.set_colorkey(old_c)
    image_copy.blit(surf, (0, 0))
    return image_copy