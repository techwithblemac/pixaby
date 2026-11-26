"""
biomes.py
=========
One place that answers "what biome is this level (or this spot) in?".

A biome is the colour variant number used everywhere else in the game:
block names ``stone_6`` / ``grass_top_5``, doors ``warp_3`` ... (see
data/palletes/blocks.py). "1" is the default look.

    1  Abyss Stone     default grey stone + green grass
    2  Rust Hollow     terracotta / chocolate-red
    3  Dune Ruins      sandy, warm
    4  Mossy Grove     deep moss green
    5  Frostbite       snow + ice
    6  Ember Forge     nether / scorched, lava country
    7  Void Choir      obsidian / void purple
    8  Harvest Dusk    autumn orange

How a level's biome is picked (first rule that answers wins):
    1. ``"biome": <1-8>`` in that level's entry of levels/metadata.json
    2. the dominant block colour variant in the level (special blocks count
       too: ice/snow -> 5, sand -> 3, lava pools -> 6, mud -> 4)
    3. the level's tags (ice -> 5, lava/fire/ash -> 6, ruins -> 3, ...)
    4. "1"

Each spot also gets its own biome (the block under / around it), so a deco
sitting on snowy grass in a mixed level comes out frosted even if the level
as a whole is "1". Used by:
    scripts/sounds.py   picks the per-biome theme music
    objects/objects.py  Deco recolours itself via data/palletes/deco.py
"""

from collections import Counter

BIOMES = ("1", "2", "3", "4", "5", "6", "7", "8")

BIOME_NAMES = {
    "1": "Abyss Stone", "2": "Rust Hollow", "3": "Dune Ruins", "4": "Mossy Grove",
    "5": "Frostbite", "6": "Ember Forge", "7": "Void Choir", "8": "Harvest Dusk",
}

# the songs for each biome live in data/music.py (BIOME_THEMES); scripts/music.py picks them

# blocks without a numeric suffix that still clearly belong to a biome
SPECIAL_BLOCKS = {"ice": "5", "snow": "5", "sand": "3", "mud": "4"}

# fallback when a level has no coloured blocks to go on (first match wins)
TAG_BIOMES = [
    ("lava", "6"), ("fire", "6"), ("ash", "6"), ("inferno", "6"), ("nether", "6"),
    ("ice", "5"), ("snow", "5"), ("frozen", "5"), ("frost", "5"),
    ("void", "7"), ("obsidian", "7"), ("sky", "7"),
    ("autumn", "8"), ("harvest", "8"), ("warcamp", "8"),
    ("desert", "3"), ("sand", "3"), ("ruins", "3"),
    ("moss", "4"), ("verdant", "4"), ("overworld", "4"), ("grass", "4"), ("maze", "4"),
    ("brick", "2"), ("fortress", "2"),
]

TILE = 64
LAVA_WEIGHT = 0.6           # a lava tile counts a bit less than a solid block


def block_biome(name):
    """``"grass_top_5"`` -> ``"5"``, ``"stone"`` -> ``"1"``, ``"ice"`` -> ``"5"``,
    ``"box1"`` -> ``None`` (crates etc. don't say anything about the biome)."""
    if not isinstance(name, str):
        return None
    base, _, tail = name.rpartition("_")
    if base and tail in BIOMES and base.split("_")[0] in ("stone", "grass", "brick"):
        return tail
    if name.split("_")[0] in ("stone", "grass", "brick"):
        return "1"
    return SPECIAL_BLOCKS.get(name)


def tag_biome(tags):
    lowered = [str(t).lower() for t in tags or ()]
    for key, biome in TAG_BIOMES:
        if any(key in t for t in lowered):
            return biome
    return None


class BiomeMap:
    """Biome of a whole level plus a per-tile lookup."""

    def __init__(self, world, meta=None):
        meta = meta or {}
        self.tiles = {}
        counts = Counter()
        for data in world or ():
            if not isinstance(data, dict):
                continue
            kind = data.get("type")
            if kind == "block":
                b = block_biome(data.get("name"))
                if b is None:
                    continue
                w = 0.35 if data.get("perspective") == "back" else 1.0
                counts[b] += w
                self.tiles[(int(data.get("x", 0)) // TILE, int(data.get("y", 0)) // TILE)] = b
            elif kind == "water" and data.get("water_type") == "lava":
                counts["6"] += LAVA_WEIGHT

        forced = str(meta.get("biome", "")) if meta.get("biome") is not None else ""
        if forced in BIOMES:
            self.biome = forced
        elif counts:
            self.biome = counts.most_common(1)[0][0]
        else:
            self.biome = tag_biome(meta.get("tags")) or "1"
        self.counts = dict(counts)

    def at(self, x, y, default=None):
        """Biome at a world position: the block under it first, then the
        closest block in a small ring around it, else the level biome."""
        gx, gy = int(x) // TILE, int(y) // TILE
        for dx, dy in ((0, 1), (0, 0), (-1, 1), (1, 1), (0, 2), (-1, 0), (1, 0), (0, -1)):
            b = self.tiles.get((gx + dx, gy + dy))
            if b:
                return b
        return default or self.biome


def level_meta(level, folder="story"):
    """metadata.json entry for a story level. Other folders carry their own _level_meta."""
    if folder != "story":
        return {}
    try:
        from ..level.selector import level_meta as lm
        return lm.load_metadata().get(str(level), {}) or {}
    except Exception:
        return {}


def analyse(game):
    """Build (and store on ``game.biome_map``) the BiomeMap for game.world."""
    bm = BiomeMap(getattr(game, "world", None),
                  level_meta(getattr(game, "level", None), getattr(game, "level_folder", "story")))
    game.biome_map = bm
    return bm


def current(game):
    bm = getattr(game, "biome_map", None)
    return bm.biome if bm else "1"
