# Pixel Abyss: collision, arrows, performance and profiling

Everything done in this session, what was measured, what is still open, and what comes next.
All code changes are in `game.zip` (the `game/` folder).

---

## 1. Quick summary

| Area | What changed | Result |
|---|---|---|
| Collision | `collide()` rewritten as axis-separated AABB (move x, resolve, move y, resolve) | Same features, more robust snapping |
| Collision speed | Cached rect lists, memoised chunk lookups, no per-call imports | About 20% faster than your original on a large level |
| Compiled option | Optional Cython module `_fast.pyx` + `build_fast.py` | 1.7x faster `collide()` (2.1x with `--all`) once built |
| Arrows | Tip-position drift, wrong angle, left-spawn, stick depth | Tip error went from over 300 px to under 0.5 px in tests |
| Profiling | Built-in frame profiler (`PIXABY_PROFILE`) + headless runner | Found the real hotspots (below) |
| Enemy AI | `get_nearest` rewritten (inline, cheapest-first checks) | 2x faster, identical choices on 20,000 random cases |
| Static objects | Trees/deco skip physics while resting on terrain | About 55% fewer `collide()` calls in the real loop |
| Sprite freezes | Faster `build_door_sprite` + tree sprites built on the loading screen | 0 rebuilds during gameplay (was 28 of 42) |

The biggest lesson: **collision itself was never the main problem.** Your real profile showed the cost
was thousands of unnecessary `collide()` calls on static objects, plus sprite building, plus drawing.

---

## 2. Collision (AABB)

**Request:** implement DaFluffyPotato's AABB collision approach.

**Caveat:** I can't watch YouTube, so I built the standard technique his platformer tutorials use, not a
copy of his code. Move on x, push out of whatever you hit, then do the same on y.

**What your old `collide()` already did:** axis-separated movement. What changed:

- Snap side now comes from the direction actually moved (`dx` / `dy`), not from `x_vel` / `y_vel`.
  A platform or knockback pushing an entity with zero velocity could previously leave it inside a block.
- New methods `collide_x()`, `collide_y()` and `landing_impact()` (fall damage, shake, land sound were
  copy-pasted twice).
- Moves over 16 px are split into steps (`MAX_STEP`), so fast movers are far less likely to skip a block.
- One broad-phase lookup per frame using a sweep rectangle of the whole move.
- Kept: knockback, moving-platform riding and push-out, arrow sticking, fall damage, `outlines` face
  culling, world bounds.
- Removed: the old fallback that teleported an entity out the far side of a block when it started inside one.
  Entities spawned inside blocks now land on top or get pushed out the nearest side.

### Honest limits of "no skip through"
It is much harder to skip a block now, but **not guaranteed**:

- Colliders thinner than about 16 px can still be skipped by tiny fast entities (lower `MAX_STEP` to fix).
- A fast moving platform can push an entity out the wrong side (only tested slow ones).
- Blocks whose `outlines` data is wrong can be passed through.
- Anything that moves `rect` outside `collide()` (teleports, respawns) is not protected.

---

## 3. Performance work on collision

| Version (large level, 100 entities) | Time per `collide()` |
|---|---|
| Your original | about 15 to 17 µs |
| My first rewrite | about 16 µs (**slightly slower** than yours; I should have caught that earlier) |
| Optimised | about 12 µs |

Changes in `scripts/physics.py` and `scripts/functions.py`:

- `query_static()`: each map chunk's rect list is built once and cached; lookups filter in C.
  `map_chunks()` bumps `map.version` so the cache refreshes when a map is rebuilt (editor).
- `ChunkMap.candidates()` memoises its results.
- Zone lookup uses the same cache; imports (`sounds`, `dash_bar`) happen once, not every call.
- Entity positions matched the original code exactly on three level types.

**Assumption:** `game.map` terrain does not move after the level is built. I checked that `game.map` only
receives `Block` objects. Platforms, doors, treasure and splashes live in other lists.
(My earlier remark that the cache "notices a swapped Rect" only holds when something touches the old
position. Blocks that genuinely move are not supported.)

---

## 4. Optional compiled speed-up (Cython)

Files: `scripts/_fast.pyx`, `build_fast.py`.

```
pip install cython setuptools
python build_fast.py            # builds scripts/_fast.*.pyd / .so
python build_fast.py --all      # also compiles physics.py itself
```

| Mode | Time per `collide()` |
|---|---|
| Pure Python | 9.4 µs |
| `_fast` only | 5.6 µs (1.7x) |
| `--all` | 4.4 µs (2.1x) |

- Falls back to pure Python automatically if the compiled file is missing. Delete the file to undo.
- Verified on 12,000 random lookups: identical results to the Python version.
- **Not tested on Windows or Android.** Windows needs Microsoft C++ Build Tools. For Android/Buildozer,
  compiled extensions need extra setup (the Python fallback still works).
- With `--all`, a stale `physics.*.pyd` will hide later edits to `physics.py`. Rebuild or delete it.
- **Your real profile showed pure-Python physics, so you have not built this yet. On your level it is worth doing.**

---

## 5. Arrow fixes

Cause of "wrong degree / wrong position" was in the tip positioning code, as you guessed.

- **Position drift (`object_utils.py`):** every angle change added the new tip offset on top of the old one.
  Replaced with a stable anchor model (`_place_arrow_tip`). Simulated spin-up error: over 300 px before,
  under 0.5 px after.
- **Cache bug:** the cache stored the arrow's live `rect`. It now stores a size-only copy.
- **Pooled arrows (`objects.py`):** `Arrow.reset()` now clears the anchor and aim flag.
- **Angle:** snaps to the real flight direction on the first frame and uses real velocity, instead of
  starting at a random angle and turning 20 degrees per frame (arrows that stuck early stayed wrong).
- **Spawn (`mind.py`):** left-facing arrows started inside the shooter; now `rect.right = shooter.left`.
- **Sticking (`physics.py`):** arrows stop at first contact and no longer keep moving after sticking.

**Not covered:** `networking/client.py` spawns remote arrows without a velocity, so they do not get the
first-frame angle snap. Tell me if remote arrows look off.

---

## 6. Profiling tools

- `debug_tools/frame_profiler.py` plus small hooks in `game.py`. Off unless `PIXABY_PROFILE` is set
  (about 0.3 µs per frame when off).
  - Windows cmd: `set PIXABY_PROFILE=40`, then launch the game as usual.
  - First half: plain timers per frame section. Second half: `cProfile` per function.
  - Writes `profile_report.txt` and `profile.prof` (open with `snakeviz`).
- `debug_tools/profile_headless.py`: runs the real loop with no window, player standing still and
  invulnerable, timing starts after the intro.
  `python game/debug_tools/profile_headless.py 1 60` (level 1, 60 seconds).

I ran the real game headless in my sandbox using your `assets.zip`. The zip had no `levels/` folder, so
those runs used generated stand-in levels. Treat those numbers as relative, not absolute.

---

## 7. What the profiles found

### Stand-in levels (my sandbox)
- Typical level: about 10 ms of work per frame. Drawing about 43%, HUD/UI about 35%, logic about 14%.
  Physics about 3.7% of Python time (`collide()` about 1%).
- Stress level (crowd of enemies): enemy target search (`get_nearest` / `in_proximity`) was the biggest
  logic cost, about 7 million calls in 35 seconds.
  - Fix: inline, cheapest-first checks. 2x faster on a 213-entity crowd, same choice on 20,000 fuzz cases.
  - Real loop: average frame 22.2 to 19.3 ms; game logic 8.0 to 6.2 ms (two runs each).

### Your real level (`profile_report.txt`)
- Average about 44 ms of work per frame against a 33 ms budget, so well under 30 FPS.
- Spikes: 2.6 s in the HUD/UI section, about 1 s in world draw.
- About 179 `collide()` calls per frame: 34 from entities, about 75 from Trees, about 53 from Deco.
  Trees and deco were about 72% of all calls. Gravity pulled them down 1 px and `collide()` snapped them
  back every frame.
- `collide()` was about half of game-logic time. Physics overall was about 17% of profiled Python time.
- Sprite building: `get_tree_sprites` took 3.5 s (42 `build_door_sprite` calls, 1.5 million `get_at` calls).

---

## 8. Fixes from your real profile

1. **Resting objects (`collide_resting()` in `physics.py`; used by `Tree` and `Deco` in `objects.py`).**
   Skips physics when the object is on plain terrain, same position and size, no velocity.
   Any change runs the full `collide()`.
   - 8 scenarios compared frame-by-frame with the old code (landing, resize, teleport, push, knockback,
     moving platform, gap): 0 differences.
   - Real loop on my props level: `collide()` calls about 29,000 to about 13,000 (-55%); logic time -10 to 15%.
   - On your level I expect a bigger gain (estimate only). Re-profile to see the real number.
2. **`build_door_sprite` (`asset_funcs.py`).** One lookup per distinct colour instead of a `get_at` /
   `set_at` per pixel. Pixel-identical on 300 random sprites and 98 real tree-frame/biome combinations.
   About 5x faster. Non-alpha surfaces still use the old slow path.
3. **Tree sprite warm-up (`level_loader.py`).** Sprites are built on the loading screen, once per palette.
   Before: 14 builds while loading, 28 during gameplay. After: 42 while loading, **0 during gameplay**.

---

## 9. Files changed

| File | Change |
|---|---|
| `scripts/physics.py` | AABB rewrite, `query_static`, `collide_resting`, faster `get_nearest`, arrow angle/stick |
| `scripts/functions.py` | `candidates()` memo, `map.version` bump |
| `scripts/_fast.pyx` (new) | Compiled map lookup |
| `build_fast.py` (new) | Build script for the compiled module |
| `objects/object_utils.py` | Arrow tip anchor model |
| `objects/objects.py` | `Arrow.reset` fields; Tree/Deco use `collide_resting` |
| `entities/mind.py` | Left-facing arrow spawn |
| `game.py` | Profiler hooks |
| `debug_tools/frame_profiler.py` (new) | Frame profiler |
| `debug_tools/profile_headless.py` (new) | Headless profiling runner |
| `scripts/asset_funcs.py` | Faster `build_door_sprite` |
| `level/main/level_loader.py` | Tree sprite warm-up |

---

## 10. What is coming next

Ordered by expected payoff. Items 1 and 2 need you; the rest I can start right away.

1. **Re-profile your real level** with the new zip (`PIXABY_PROFILE=40`) and send `profile_report.txt`.
   This tells us what the fixes above actually saved.
2. **Build `_fast`** (`python build_fast.py`) and profile again to see the compiled gain on your level.
3. **Draw cost (largest remaining).** About 240 object draws and 400 blits per frame.
   Skip drawing off-screen objects; check `combat_fx.draw_world` and the `transform.scale` calls
   (1,492 calls, about 1.3 s).
4. **Lighting.** `lighting._lights_for` took about 2.3 s over 722 frames. Options: cache per frame, or
   render lighting at half resolution (a visual change, so I would ask first).
5. **Pathfinding.** `get_closest_node` costs about 0.4 ms per call (6,494 calls, 2.6 s total). A spatial
   lookup instead of a linear scan should help a lot.
6. **Deco palette builds.** `apply_pallete` (35 calls, about 0.5 s) can get the same loading-screen
   warm-up as trees.
7. **Unexplained 2.6 s HUD/UI spike.** Re-check after the sprite fix; if it persists, trace it.
8. **Defeat screen.** About 23 ms per frame in my first run (repeated full-screen overlays). Only matters
   while the player is dead, but easy to cache.
9. **Possible AI change (behaviour change, would ask first):** acquire targets every other frame instead
   of every frame.
10. **Networking:** first-frame angle for remote arrows in `client.py`.

### Caveats to keep in mind
- Sandbox numbers are relative; absolute numbers come from your machine.
- Nothing has been run on Windows, Android, or a real display.
- Re-run the profiler after each change instead of trusting estimates.
