# Pixel Abyss: changes made on 2026-11-26

Follow-up to `PIXEL_ABYSS_PERFORMANCE_NOTES.md`. All numbers come from a headless run in my sandbox
on your real `levels/story/1.json`, so treat them as relative, not absolute. Nothing was run on
Windows.

---

## 1. Code change (one file)

### `game/ui/lighting.py`: `Lighting._lights_for()` is about 3.6x faster

**Problem.** The profile showed about 1,900 `getattr(...)` calls per frame inside `_lights_for`
(857,000 over 453 frames). The function loops over every object in view on every frame to find light
sources, and each object cost 3 to 5 `getattr` calls.

**Fix.** Plain attribute reads (`obj.rect`, `obj.type`, `obj.name`) with `try/except AttributeError`
fallbacks, in place of `getattr(obj, "x", default)`. Which lights are returned is unchanged.

**Measured (30 s headless run, level 1):**

| | `_lights_for` cumulative time |
|---|---|
| Before | 0.571 s |
| After | 0.159 s |

**Checked for identical results.** I ran the old and new versions side by side on every call, on
levels 1 and 3: 3,276 calls, 18,549 lights, **0 mismatches** (including the screen-flash side effect).

**To apply:** replace `game/ui/lighting.py` with the file I sent. To undo, put your old copy back.

---

### `game/entities/pathfinding.py`: `get_closest_node()` is about 5.5x faster

It built a `PlatformNode` and called `heuristic()` for each of about 176 candidates per call. It now
computes the target centre once and compares distances inline, with the same tie-breaking.
Per call: about 0.34 ms before, about 0.06 ms after. Checked on 8,512 real calls on levels 1 and 3:
same node every time, 0 mismatches.

---

### `game/level/main/level_loader.py`: deco sprites warmed up on the loading screen

Trees already had this. Deco recolours (`get_deco_sprites(biome)`) are now built when the deco is
created during loading, once per biome, instead of as a hitch the first time it scrolls into view.
On level 1 deco was not a gameplay cost (it was already built), so this is insurance for levels with
recoloured deco. The game was run headless on levels 1, 3 and 5 with no errors.

### `game/ui/defeat_screen.py` and `game/ui/ui_theme.py`: defeat screen about 55x cheaper

- Once the colour has fully drained, the picture (frozen scene + gray + dim) never changes, so it is
  built once and reused: three full-window blits less per frame.
- `dim_overlay()` allocated a new full-window transparent surface on every call. It now reuses up to
  4 cached overlays (this helps every screen that uses it).
- Background cost at 1280x720: about 17 ms per frame before, about 0.3 ms after. Output checked
  pixel-identical. Not run in a real defeat on a real display, so check the screen once in play.

---

## 2. What the profile showed about drawing (no code changed)

- Drawing was the largest part of the frame in my run (about 53% of work).
- About 175 objects are drawn per frame; `object_utils.draw` alone is about 0.9 s of blit time.
  That is mostly the blits themselves, so only drawing fewer things would cut it.
- `transform.scale` is about 1 ms per frame, almost all of it the lightmap being scaled up to full
  size.
- `lighting.apply` does about 19 blits per frame, which is already low.

**Not done, needs your yes:**
- Render the lightmap at a smaller size (faster, but changes the look slightly).
- Cache static terrain into one layer (bigger win, bigger change).

---

## 3. `_fast.pyx` and the build

- Your zip already contained the real `scripts/_fast.pyx` (196 lines) and `build_fast.py`. **Ignore
  the sample `.pyx` I pasted earlier in the chat.** Use the original from the zip.
- `scripts/_fast.c` existed but there was no `.pyd`, so the build stopped at the C compile step. That
  means the C++ compiler is missing.
- `python build_fast.py` creates `scripts\_fast.cp311-win_amd64.pyd` (needs Microsoft C++ Build
  Tools, "Desktop development with C++").
- `python build_fast.py --all` also compiles `physics.py`. A stale `physics.*.pyd` hides edits to
  `physics.py`, so rebuild or delete it after editing.
- The game runs fine without `_fast`; it falls back to pure Python.
- Expected gain: `collide()` about 1.7x faster, which is a modest overall gain.
- Option to avoid installing the Build Tools: build the `.pyd` on GitHub Actions (Windows runner,
  Python 3.11) and download it. Not set up yet.

---

## 4. Setup note

- Cython failing with "No matching distribution" / "from versions: none" was caused by the firewall.
  Turning it off fixed it. Better: re-enable the firewall and allow `python.exe`.

---

## 5. To do next

1. **You:** re-profile your real level (`set PIXABY_PROFILE=40`, play, send `profile_report.txt`), to
   see what the earlier fixes saved and whether the 2.6 s HUD/UI spike remains.
2. **You:** decide on `_fast` (GitHub Actions build or Build Tools), the smaller lightmap, and the
   terrain layer cache.
3. Remote arrows first-frame angle in `networking/client.py` (from the earlier notes).

---

## 6. Merge with pixaby.zip (2026-11-26, later)

The newer zip had your new features (Burn, entity-editor mods, homing arrow trap) but carried older copies of
files that already had my performance work. Kept everything of yours and re-applied mine:

- `scripts/physics.py`, `scripts/functions.py`, `scripts/asset_funcs.py`: the zip held older versions with no
  features of yours in them, so these are the optimised versions (plus the console message that says whether
  the compiled `_fast` helper is in use).
- `objects/objects.py`: Tree and Deco call `collide_resting()` again (only those two lines changed; Burn etc. kept).
- `game.py`: profiler hooks added back (`PIXABY_PROFILE`); your arrow-trap key/joystick code kept.
- `level/main/level_loader.py`: tree sprite warm-up added back, plus the new deco warm-up; your `_clear_projectiles`,
  `mods_rt.apply` and arrow-trap loading kept.
- `ui/lighting.py` (faster `_lights_for`), `ui/ui_theme.py` and `ui/defeat_screen.py` (defeat screen cache),
  `entities/pathfinding.py` (faster `get_closest_node`).

Checked: whole game compiles, runs headless on levels 1, 3 and 5 with no errors. Not run on Windows or with the
arrow trap / entity editor features, so try those once.
