# Pixel Abyss — Project Structure

A file-by-file guide to what everything does, with the heaviest focus on
`game/`, since that's where the actual engine lives. Written as a reference
for future-you (and future-Claude) to get oriented quickly without having to
re-read 12,000+ lines from scratch.

---

## Top-level layout

```
PIXEL_ABYSS-v38/
├── pixaby.py                  # entry point - run this to launch the game
├── pixel_abyss_viewer.py      # standalone level viewer/debug tool
├── game/                      # the engine + game logic (this is the real codebase)
├── levels/                    # level data as JSON (1.json - 10.json)
├── assets/                    # sprites, sounds, terrain, fonts
├── data/                      # top-level font data used by extras/tools
├── extras/                    # packaging & versioning scripts, not shipped
├── AGENTS.md                  # instructions for AI agents working on this repo
├── README.md                  # project overview
├── CREDITS.md                 # asset/attribution credits
└── run.bat                    # Windows launch script
```

---

## Entry points

### `pixaby.py`
The actual thing you run. Prints the version, then does `game.Game(level).start()`
with `level = 1`. Everything else gets pulled in through `game/main.py`.

### `pixel_abyss_viewer.py`
A separate, standalone pygame tool for browsing level JSON files visually —
pan/zoom/layer-toggle, works with mouse or touch. Useful for inspecting a
level without booting the full game (physics, entities, networking, etc.).
Not part of the shipped game loop.

### `run.bat`
Windows batch script to launch the game without typing the python command
by hand.

---

## `game/` — the engine

This is organized as: **assets & loading** → **core objects & physics** →
**entities & AI** → **the main game loop** → **windows/UI** →
**networking/multiplayer**. Below is that same order.

### Assets & loading

**`file_loaders.py`**
Low-level sprite-sheet and sound loading helpers: `flip()` (mirror a list of
sprites for left/right facing), `load_sounds()`, `load_sprite_sheets()`, and
`load_sprite_sheets2()` (a more flexible variant with optional resizing).
Everything in `assets.py` is built on top of these.

**`assets.py`**
Loads every sprite, sound, and terrain texture into memory once at startup
and exposes them through the `Assets` class (a bag of class attributes, not
an instance — accessed as `Assets.ENEMY_SPRITES`, `Assets.blocks`, etc.).
Also does the enemy-sprite-sheet slicing (`create_enemy_sprites()`), tree/
arrow/death animation slicing, and terrain block assembly (`blocks_assets()`).
This is the one place where raw asset files become usable pygame `Surface`
objects — get this file right and blit speed for the whole game follows.

**`data/palletes/blocks.py`** and **`data/palletes/entities.py`**
Not source code so much as data tables: RGB source→destination color-swap
pairs used for the biome palette system (10 terrain variants) and enemy
recolor themes. Consumed by `apply_pallete()` in `functions.py`.

**`data/text.py`**
Bitmap font rendering — turns the font spritesheet + character-width table
in `settings.py` into actual renderable text glyphs.

### Core objects & physics

**`physics.py`**
Math and collision primitives everything else depends on: `get_degree()`,
`find_distance()`, `distance()`, and the `PHYSICS` class (gravity, velocity,
collision resolution). Nearly every object and entity class inherits from
`PHYSICS`. Also where the recent archer-arrow hit-detection fix landed (the
`scope != 0` vs `not scope` bug noted in `FIXES_&_ADDITIONS.md`).

**`object_utils.py`**
Defines the base `Object` class (inherits `PHYSICS`) that most in-world
things — platforms, blocks, decorations, treasure — build on. Handles the
shared logic: position, draw-list membership, generic collision behavior.

**`objects.py`**
The concrete object types built on `Object`: `Platform`, `Bubble`, `Splash`,
`WaterZone`, `Bombs`/`Bomb`, `Arrow`, `Fire`, `Tree`, `Block`, `Trap`, `Deco`,
`Treasure`. This is the "what can exist in a level" file — if you're adding
a new placeable thing, it probably goes here.

**`spatial_grid.py`**
`SpatialGrid` — a flat hash-map spatial partition (cell-based) for fast
nearest-neighbour / broad-phase collision queries, so physics and AI don't
have to check every entity against every other entity each frame. One of
the earlier optimization passes (OPT-1 in the reports).

**`pathfinding.py`**
A* pathfinding (`PlatformGraph`, `heuristic()`, `get_direction()`) used by
enemy AI to navigate between platforms. Cached rather than recomputed every
frame — only triggered when an entity actually needs a new route.

### Entities & AI

**`entity_utils.py`**
The big one for anything alive: `PlatformNode` (graph nodes for pathfinding),
`TargetSystem` (who's targeting whom), `ACTIVITY` (state/behavior base),
and `Entity` (the base class for anything with health, movement, and AI —
players and enemies both build on this). This is where enemy AI
decision-making and animation-state logic lives.

**`entities.py`**
Thin concrete layer on top of `entity_utils.py`: `Enemy`, `Player`, and
`Spawn_Point`. Short file — most of the actual behavior is inherited from
`Entity`/`ACTIVITY` in `entity_utils.py`; this is mostly what's specific to
being a player vs. being an enemy.

**`player_helper.py`**
Small player-account-style utilities: `remove()`, `save()`,
`change_color()`, `change_type()`, `back_()` — managing player config/state
between screens, not in-game physics.

**`controls.py`**
Input handling — `handle_fingers()` for touchscreen control mapping
(touch is used on touchscreen PCs; see `game/scripts/touch.py`).

### Shared utilities

**`functions.py`**
The utility-function grab-bag: caching (`cache_img`, `cache_assets`,
`cached_rect`, `glow_img` — all LRU-bounded now, see below),
`apply_pallete()`/`pallete_swap()` (the palette-swap rendering system),
`parallax_bg()` (menu background particle effect), `draw_minimap()`, sound
playback (`playit()`), and misc helpers (`remove_duplicates()`,
`find_last()`). Imported from almost everywhere else in `game/`.

**`calculate_class.py`**
Just `get_total_size()` — a recursive `sys.getsizeof()` walker for measuring
how much memory an object graph actually uses. A debugging/profiling tool,
not used in the normal game loop.

**`tests.py`**
A handful of standalone utility functions (`find_last`, `remove_duplicates`)
— looks like an earlier or parallel copy of helpers that also live in
`functions.py`. Worth checking whether this is still imported anywhere or
is leftover.

### The main loop & UI

**`main.py`** *(largest file, ~1,900 lines)*
Defines `Game(Settings, Windows)` — the central class that owns the game
loop, level loading (`load_world()`), the level editor/grid tools
(`initialise_grid()`, `add_block()`, `add_enemy()`, etc.), the draw
pipeline (`_rebuild_draw_list()`, `draw_sub()`, `draw_main()`, and the
viewport-culling `hide()` check), and per-frame update logic
(`update_game_logic()`). If you're tracing "what happens each frame,"
this is where it starts.

**`windows.py`** *(second-largest, ~1,650 lines)*
Defines `Windows` — all the non-gameplay screens: main menu, settings,
pause menu, player customization, and their button/layout logic. `Game`
inherits from this alongside `Settings`. Also where `parallax_bg()` gets
called for menu backgrounds.

**`ui_popup.py`**
`FieldPopup` and `run_field_popup()` — the field-editor popup used by the
level editor for editing an object's properties as labeled fields instead
of raw text strings (replaced an older "width;height" raw-text editing
flow, per the file's own docstring).

**`settings.py`**
Central config: window/display setup, fonts, `FPS`, `GRAVITY`, volume
levels, color constants, and (as of this month) `LOW_SPEC_MODE` —
auto-detected from logical core count, used to scale down cache sizes and
particle counts on weaker machines.

### Multiplayer

**`networking.py`**
Socket-based client/server networking: `initialize_server()`,
`get_clients()`, `broadcast_to_all_clients()`, `send_sync()`,
`handle_packet()`, object sync/destroy broadcasts. Raw networking layer —
no rendering.

**`server.py`** *(largest logically-central file after main.py, ~700 lines)*
The authoritative game-loop-plus-multiplayer file: split-screen viewport
rendering for up to 4 players, HUD, minimap, debug overlay, and the
per-frame **cache-handling block** (font/zoom/object cache size limits —
now with named constants instead of magic numbers, and lighter now that
`CACHED_IMAGES`/`CACHED_ENTITY_IMAGES`/`CACHED_RECTS['other']` self-manage
via LRU eviction instead of being force-cleared here). Also owns
`reset_cache()`, the full cache wipe used on level transitions.

### Docs inside `game/`

**`DISCOVERIES.md`**
A running log of non-obvious bugs and why they happened — e.g. the A*
tie-breaking `<=` vs `<` bug. Worth reading before touching pathfinding or
physics; whatever's documented here already cost debugging time once.

---

## `levels/`

`1.json` through `10.json` — full level data (terrain, entity placement,
water zones, spawn points). Sizes range from ~100KB to ~516KB
(`4.json` is the largest). Loaded by `Game.load_world()` in `main.py`.

## `assets/`

Raw sprite/sound/font files, organized by category (`Enemies/`, `Terrain/`,
`Deco/`, `Effects/`, `Weapons/`, `SOUNDS/`, etc.). `SOUNDS/` is the largest
at ~3.9MB; everything else is comparatively small pixel art. Loaded once at
startup through `assets.py`.

## `extras/`

Not shipped with the game — developer tooling only:
- **`bump_version.py`** — CLI script to bump the version string in `settings.py`
- **`steps_to_package.py`** — PyInstaller commands for building `--onefile`/`--onedir` distributables
- **`template.py`** — a bare pygame boilerplate starter, unrelated to the actual game (looks like a scratch/reference file)

---

## Quick map: "I want to change X, where do I look?"

| You want to... | Start here |
|---|---|
| Add a new enemy type | `entity_utils.py`, `entities.py`, `assets.py` (sprite loading) |
| Add a new placeable object (trap, deco, etc.) | `objects.py`, `object_utils.py` |
| Change how levels load or the level editor | `main.py` (`load_world`, `initialise_grid`) |
| Change a menu screen or button layout | `windows.py` |
| Tune performance / caching | `functions.py` (cache functions), `server.py` (per-frame cache block), `settings.py` (`LOW_SPEC_MODE`) |
| Fix collision or movement bugs | `physics.py`, `object_utils.py` |
| Fix pathfinding/AI bugs | `pathfinding.py`, `entity_utils.py` |
| Touch multiplayer sync | `networking.py`, `server.py` |
| Add/change a terrain biome palette | `data/palletes/blocks.py`, `assets.py` (`blocks_assets`) |

---

*Last updated: reflects the state of the project as of this month's
optimization pass (LRU cache eviction, `.convert_alpha()` fix, cache
constants in `server.py`).*


- game/data/ammo.py - arrows/fires/bombs per volley + bomb cap (data)
- game/ui/minimap.py - purchasable radar (WS-A)

- game/scripts/camera.py - Camera class: follow, look-ahead, focus, snap (WS-F)

- game/data/charms.py - every charm / dash tunable (WS-B)
- game/scripts/charm_mode.py - charm rules, friends, dash paywall (WS-B)
- game/ui/charm_ui.py - reticle, charm / dash HUD, banners (WS-B)
- game/ui/achievements_screen.py - the achievements window (WS-D)
- game/ui/window_kit.py - shared window kit: loop, frame, cards, pills, key glyphs (WS-E)
- game/ui/info_windows.py - Mode, Game Info, Author Info, Entity Info windows (WS-E)
- game/data/controls.py - the key table the Controls page is generated from (WS-E)
- game/data/info_pages.py - Game Info / Author / Mode text and tables (WS-E)
- tests/ - headless logic tests: python3 tests/test_charms.py, test_shop_items.py, test_achievements.py, test_windows_data.py
- game/ui/door_fx.py - door effect layer: idle, proximity, enter / arrive, exit flare, unlock (WS-G)
- VERSION - the one version number (read by game/version.py, game.json via extras/bump_version.py)
- game/version.py - NAME, TITLE, VERSION, WINDOW_TITLE
- game/scripts/paths.py - BASE_DIR, asset(), LEVELS_ROOT, enter_base_dir(), save_file()
- game/scripts/screen_mode.py - the three screen modes (full screen / 800x600 / 1280x960), remembered in display.json
- game/scripts/touch.py - decides whether the on-screen touch controls are used (touchscreen detection)
- game/data/music.py - which song plays where (tables)
- game/scripts/music.py - the music director: choose() + Music (cross-fade)
- tests/test_clean_setup.py, tests/test_music.py - paths / version / landscape and music tests
- game/ui/entity_editor.py - the Entity Editor: tabbed, categorised tweak window for enemies (and the Homing Trap's own window)
- game/data/entity_mods.py - the Entity Editor's schema: categories, fields, boss kits, grantable shop items, trap fields
- game/entities/mods.py - runtime for those tweaks: apply, regen / burn / rage, second wind, dash AI, trap-dropping AI, boss title
- game/objects/arrow_trap.py - the Homing Arrow Trap (ArrowTrap), arrow_profile, drop(), TRAP key / pad input, editor icon
- docs/ENTITY_EDITOR.md - reference for the above

## Quick map additions
| You want to... | Start here |
|---|---|
| Add a tweak to the Entity Editor | `data/entity_mods.py` (add a field), `entities/mods.py` (make it do something) |
| Grant / change what a shop item gives an enemy | `data/shop_items.py`, `data/entity_mods.PLAYER_ONLY_ITEMS`, `scripts/shop_effects.py` |
| Change how the homing trap behaves | `objects/arrow_trap.py` (`PROP_DEFAULTS`, `WOBBLE`, `ArrowTrap._strike`) |
| Change what an entity's arrows do | `arrow_trap.arrow_profile`, `objects.Arrow.reset` |
| Change the boss bar / title | `level/main/objectives.py` (Boss), `entity_utils.py` (nameplate) |
| Change the TRAP key | `settings.py` (`TRAP_KEYS`, `TRAP_JOY_BUTTON`) |

