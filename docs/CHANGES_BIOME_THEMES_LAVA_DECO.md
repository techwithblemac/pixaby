# Biome themes, glowing lava, per-biome deco palettes

## New files
- `game/data/biomes.py` - works out a level's biome (1-8, same numbers as block/door variants) and the biome at any spot.
- `game/data/palletes/deco.py` - per-biome colour swaps for plants, shrubs, mushrooms and pumpkins.
- `assets/sounds/themes/theme_<n>_<name>.ogg` - 8 seamless looping themes (original, procedurally composed for this game).

| Biome | Theme | Feel |
|---|---|---|
| 1 Abyss Stone | theme_1_abyss_stone | slow D minor, plucked arps, cave drips, flute |
| 2 Rust Hollow | theme_2_rust_hollow | A phrygian, bell arps, hand drums |
| 3 Dune Ruins | theme_3_dune_ruins | E phrygian dominant, oud-ish plucks, drone, tabla-ish toms |
| 4 Mossy Grove | theme_4_mossy_grove | bright G major, flute, shakers |
| 5 Frostbite | theme_5_frostbite | sparse C# minor, FM bells, long echoes |
| 6 Ember Forge | theme_6_ember_forge | driving C minor 120bpm, war drums, pulsing bass |
| 7 Void Choir | theme_7_void_choir | eerie clusters, detuned choir pads, deep booms |
| 8 Harvest Dusk | theme_8_harvest_dusk | F major folk, strums, fiddle + flute |

## How the biome is picked (`data/biomes.py`)
1. `"biome": <1-8>` in the level's entry in `levels/metadata.json` (override)
2. dominant block colour variant (`stone_6`, `grass_top_5`...; ice/snow -> 5, sand -> 3, mud -> 4, lava pools count toward 6)
3. level tags (ice -> 5, lava/fire/ash -> 6, ruins -> 3 ...)
4. biome 1

## Music (`scripts/sounds.py`, hooked in `game.py` right after `load_world()`)
- `Sounds.play_biome_theme(game)` cross-fades to the level's theme (0.9s out, 1.6s in). Retrying the same biome keeps the music going.
- Themes load lazily, at most 2 decoded in memory. Missing file -> falls back to the old `theme`.
- The MUSIC slider controls the biome theme live; `sounds.stop("theme")` stops it too.
- Note: `Settings.BG_SOUNDS_VOLUME` defaults to 0, so turn MUSIC up in the SOUND screen to hear it.

## Lava is a light source (`ui/lighting.py`)
- Surface lava tiles throw a big warm flickering glow, deeper tiles a smaller one on a checkerboard.
- Capped at `MAX_LAVA_LIGHTS` (70) per viewport; huge lakes get fewer, bigger lights so cost stays flat.
- Classified once per level. Levels with no matching tag also get an ambient tint from their biome palette.

## Deco palettes (`objects/objects.py`, `object_utils.py`, `scripts/cache.py`)
- grass1/2, shrub1-3, shroom1-3, pumpkin1/2 recolour per biome (outline untouched). Arrow sign, bone, exit, door, scarecrow stay as drawn.
- Each deco takes the biome of the block it sits on (falls back to the level biome), so mixed levels look right.
- Force one in the level JSON with a suffix: `"name": "shrub1_5"` = frosted shrub.
- Recoloured sets are built once per biome (`get_deco_sprites`) and every image cache key now includes the biome.
