"""
deco.py
=======
Per-biome colour swaps for the decorations in assets/Deco.

Same idea as blocks.py: ``deco_pallete[family][biome]`` is a list of
``[old_rgb, new_rgb]`` pairs. Biome "1" is the original art. The dark
outline (22, 28, 46) is never touched, so every variant keeps the same
crisp silhouette.

Only decorations whose colours *mean* something about the place get a
palette (plants, mushrooms, pumpkins). Signs, bones, the exit and the
scarecrow keep their original colours in every biome (see DECO_FAMILIES).
"""

# which colour family every deco sprite uses (sprites not listed are left alone)
DECO_FAMILIES = {
    "grass1": ("grass",), "grass2": ("grass",),
    "shrub1": ("shrub",), "shrub2": ("shrub",), "shrub3": ("shrub",),
    "shroom1": ("shroom",), "shroom2": ("shroom",), "shroom3": ("shroom",),
    "pumpkin1": ("pumpkin", "grass"), "pumpkin2": ("pumpkin", "grass"),
    # Trees use the same living-green palette family as grass. The editor
    # stores the chosen biome on the tree name, so they no longer stay fixed.
    # Tree foliage uses the shrub colours in the source sprite sheet.
    # The bright leaf highlight on top of the tree has its own family.
    "tree": ("shrub", "treetop"),
}

# original colours, light -> dark
_GRASS = [(124, 187, 78), (82, 150, 80), (56, 114, 83), (61, 79, 77)]
_SHRUB = [(90, 182, 89), (47, 150, 106), (39, 113, 111), (42, 72, 94)]
_TREETOP = [(189, 215, 99)]   # tree-top leaf highlight (lighter than the shrub greens)
_SHROOM = [(219, 76, 76), (124, 78, 95), (241, 226, 185), (188, 173, 167)]   # cap, cap shade, stem, stem shade
_PUMPKIN = [(224, 189, 96), (204, 128, 75), (165, 90, 80), (119, 67, 82)]


def _swap(old, new):
    return [[o, n] for o, n in zip(old, new)]


deco_pallete = {
    "grass": {
        "1": [],
        "2": _swap(_GRASS, [(214, 140, 84), (176, 92, 62), (132, 58, 56), (88, 40, 52)]),      # rust
        "3": _swap(_GRASS, [(214, 196, 118), (180, 156, 86), (140, 116, 62), (100, 80, 52)]),  # dry dune grass
        "4": _swap(_GRASS, [(98, 196, 84), (52, 150, 60), (28, 110, 48), (24, 72, 46)]),       # lush moss
        "5": _swap(_GRASS, [(232, 246, 255), (182, 214, 238), (132, 170, 206), (96, 122, 160)]),  # frosted
        "6": _swap(_GRASS, [(255, 168, 72), (220, 92, 44), (156, 40, 30), (92, 22, 26)]),      # embers
        "7": _swap(_GRASS, [(186, 132, 236), (132, 84, 196), (88, 52, 150), (54, 34, 98)]),    # void
        "8": _swap(_GRASS, [(246, 182, 70), (220, 120, 40), (172, 70, 30), (112, 46, 34)]),    # autumn
    },
    "shrub": {
        "1": [],
        "2": _swap(_SHRUB, [(222, 132, 90), (184, 84, 66), (138, 52, 60), (84, 34, 54)]),
        "3": _swap(_SHRUB, [(200, 190, 110), (164, 150, 80), (124, 110, 64), (88, 72, 56)]),
        "4": _swap(_SHRUB, [(110, 200, 80), (60, 158, 70), (34, 116, 66), (26, 76, 60)]),
        "5": _swap(_SHRUB, [(226, 244, 255), (170, 210, 236), (118, 164, 204), (78, 108, 150)]),
        "6": _swap(_SHRUB, [(250, 150, 64), (214, 80, 44), (150, 36, 34), (84, 20, 30)]),
        "7": _swap(_SHRUB, [(176, 120, 232), (124, 78, 196), (82, 50, 150), (48, 32, 96)]),
        "8": _swap(_SHRUB, [(240, 170, 60), (214, 104, 38), (166, 62, 32), (104, 42, 40)]),
    },
    "treetop": {
        "1": [],
        "2": _swap(_TREETOP, [(240, 176, 132)]),
        "3": _swap(_TREETOP, [(226, 218, 152)]),
        "4": _swap(_TREETOP, [(170, 226, 110)]),
        "5": _swap(_TREETOP, [(246, 252, 255)]),
        "6": _swap(_TREETOP, [(255, 200, 110)]),
        "7": _swap(_TREETOP, [(212, 168, 248)]),
        "8": _swap(_TREETOP, [(252, 208, 106)]),
    },
    "shroom": {
        "1": [],
        "2": _swap(_SHROOM, [(232, 140, 70), (150, 70, 60), (244, 222, 190), (196, 166, 150)]),  # rust caps
        "3": _swap(_SHROOM, [(196, 150, 96), (130, 96, 70), (240, 226, 196), (196, 178, 156)]),  # desert puffballs
        "4": _swap(_SHROOM, [(120, 200, 150), (60, 120, 104), (234, 236, 200), (180, 186, 160)]),  # moss caps
        "5": _swap(_SHROOM, [(130, 210, 255), (70, 120, 180), (240, 248, 255), (190, 206, 226)]),  # ice caps
        "6": _swap(_SHROOM, [(255, 200, 60), (210, 90, 30), (90, 50, 50), (60, 34, 40)]),         # glowing ember caps
        "7": _swap(_SHROOM, [(232, 96, 232), (120, 50, 150), (210, 196, 240), (150, 136, 190)]),  # void glow
        "8": _swap(_SHROOM, [(184, 92, 40), (110, 56, 40), (238, 214, 168), (190, 160, 128)]),    # autumn browns
    },
    "pumpkin": {
        "1": [],
        "2": _swap(_PUMPKIN, [(236, 170, 110), (206, 104, 70), (160, 62, 60), (104, 40, 56)]),
        "3": _swap(_PUMPKIN, [(240, 220, 150), (220, 176, 106), (180, 132, 80), (130, 90, 70)]),  # gourds
        "4": _swap(_PUMPKIN, [(200, 220, 110), (140, 180, 80), (90, 136, 70), (60, 92, 64)]),     # green squash
        "5": _swap(_PUMPKIN, [(244, 250, 255), (206, 222, 238), (160, 180, 206), (112, 128, 162)]),  # frost-white
        "6": _swap(_PUMPKIN, [(255, 220, 90), (240, 120, 40), (180, 50, 30), (100, 24, 28)]),     # jack-o'-lantern
        "7": _swap(_PUMPKIN, [(196, 160, 236), (142, 100, 200), (96, 62, 154), (60, 38, 104)]),
        "8": [],                                                                                    # already autumn
    },
}


def swaps_for(name, biome):
    """``{old_rgb: new_rgb}`` for deco ``name`` in ``biome`` (empty = keep)."""
    out = {}
    for fam in DECO_FAMILIES.get(name, ()):
        for old, new in deco_pallete[fam].get(str(biome), []):
            out.setdefault(tuple(old), tuple(new))
    return out


def is_recolourable(name):
    return name in DECO_FAMILIES
