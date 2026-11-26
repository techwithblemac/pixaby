"""
music.py (data)
===============
Which song plays where. Tables only: no code, so changing the soundtrack never touches the game logic.
The logic that uses these tables is scripts/music.py.

Songs live in assets/sounds/themes/<stem>.ogg (a .wav with the same stem also works).

A level gets its song like this (first rule that applies wins; scripts/music.py explains it in code):

    1  the level's metadata (levels/story/metadata.json) has  "theme": "<biome id or file stem>"
    2  the level's metadata has  "biome": "<id>"        (the same switch that forces its look)
    3  the blocks it is built from say so - when they are conclusive: a non-stone biome clearly
       leads, or plain stone covers >= STONE_CONFIDENCE of the biome blocks
    4  its TYPE says so: its tags (data/biomes.py TAG_BIOMES: "Ruins" -> Dune Ruins ...), then its
       objective (OBJECTIVE_THEME below: boss / final fights get their own song)
    5  the blocks anyway (plain stone mixed with another biome counts for stone), else Abyss Stone

Non-level screens (the title / level-select hub, a menu) play SCENE_THEME[name]; a scene that is not
listed plays the generic title song (assets/sounds/theme.wav).
"""

# biome id (data/biomes.py BIOME_NAMES) -> song file stem
BIOME_THEMES = {
    "1": "theme_1_abyss_stone",
    "2": "theme_2_rust_hollow",
    "3": "theme_3_dune_ruins",
    "4": "theme_4_mossy_grove",
    "5": "theme_5_frostbite",
    "6": "theme_6_ember_forge",
    "7": "theme_7_void_choir",
    "8": "theme_8_harvest_dusk",
}

# level TYPE (the objective kind in the level's data) -> biome id whose song to use when the level's
# blocks and tags are not conclusive. kinds: clear_all, survival, exit, boss, final
OBJECTIVE_THEME = {
    "boss": "7",
    "final": "7",
}

# non-level screens -> biome id (or file stem). Empty = the generic title song everywhere.
#   e.g.  {"hub": "1", "shop": "8"}
SCENE_THEME = {}

# plain stone is the "default art" every dungeon uses, so it only decides the song alone when it clearly
# dominates: its share of all biome-bearing blocks must reach this
STONE_BIOME = "1"
STONE_CONFIDENCE = 0.75

FADE_OUT_MS = 900
FADE_IN_MS = 1600
EXTENSIONS = (".ogg", ".wav")
KEEP_LOADED = 2          # decoded songs are large: keep only the playing one and the next
