# Pixel Abyss: progress and remaining tasks (handoff, 2026-11-26)

Give this file to Claude at the start of a new chat, together with your latest `pixaby.zip`, and say
"continue from this". It lists what is done, what is left, and the facts needed to carry on.

Related notes: `PIXEL_ABYSS_PERFORMANCE_NOTES.md` (earlier sessions) and
`PIXEL_ABYSS_CHANGES_2026-11-26.md` (today's changes, in `docs/` of `pixaby_merged.zip`).

---

## 1. Project facts

- Project root: `...\Desktop\pixaby\` (holds `game/`, `assets/`, `levels/`, `docs/`, `pixaby.py`).
  Commands like `python build_fast.py` run **inside `pixaby\game`**.
- Python 3.11 on Windows, PowerShell. Compiled files must be `cp311`.
- `game/` is a Python package (`import game.scripts._fast` works from the root).
- GitHub user `techwithblemac`, repo `pixaby` (push with `bash push.sh` from Git Bash).
- Profiling: `set PIXABY_PROFILE=40`, play, then send `profile_report.txt`.
  Headless: `python game/debug_tools/profile_headless.py <level> <seconds>` (sandbox numbers are relative only).
- Nothing has been run on Windows or Android by Claude, only on a Linux sandbox.

## 2. Done

| Area | What | Result |
|---|---|---|
| Collision | AABB rewrite, cached chunk lookups (`query_static`), `collide_resting` for Tree/Deco | about 20% faster, about 55% fewer `collide()` calls |
| Arrows | tip anchor model, angle, left spawn, sticking | tip error 300 px to under 0.5 px |
| Enemy AI | `get_nearest` inlined | 2x faster, identical choices |
| Sprites | faster `build_door_sprite`; tree sprites built on loading screen | 0 rebuilds in play |
| Profiling | frame profiler and headless runner | in `game/debug_tools/` |
| Lighting | `_lights_for` without `getattr` | 3.6x faster, identical lights |
| Pathfinding | `get_closest_node` computes target centre once | 5.5x faster, identical nodes |
| Deco | `get_deco_sprites` warmed up on loading screen | insurance, no cost on level 1 |
| Defeat screen | cached composite and cached `dim_overlay` | about 17 ms to 0.3 ms per frame |
| Console | physics prints whether compiled `_fast` is in use | `[physics] compiled helper IN USE/NOT used` |
| Tooling | `push.sh`, `.gitignore`, `requirements.txt`, workflows `build-fast.yml` and `build-windows.yml` | `build-windows` untested |
| Merge | newer `pixaby.zip` merged with all of the above (`pixaby_merged.zip`) | runs headless on levels 1, 3, 5 |

## 3. Remaining tasks (in order)

1. **Re-profile the real level** on the user's PC with the merged build, and send `profile_report.txt`. This
   shows what the fixes saved. (User)
2. **Confirm `_fast` is used.** Build with `python build_fast.py` inside `game`, run the game, and look for
   `[physics] compiled helper IN USE`. If it says NOT used, read the "Reason" text (usually a Python-version
   mismatch). (User)
3. **Trace the 2.6 s HUD/UI spike** seen in the first real profile. Needs the new profile. (Claude)
4. **Draw cost, remaining.** About 175 objects and 284 blits per frame. Options:
   - Cache static terrain into one layer (bigger win, bigger change).
   - Render the lightmap smaller (about 1 ms/frame in `transform.scale`; changes the look slightly, **ask first**).
   - Look at the 1,492 `transform.scale` calls around `combat_fx.draw_world`.
5. **Pathfinding, second step.** What is left in `get_closest_node` is the `get_objects` lookup; a spatial grid
   would remove it.
6. **AI target acquisition every other frame.** Changes enemy behaviour, **ask first**.
7. **Remote arrows** (`networking/client.py`): spawn them with a velocity so they get the first-frame angle snap.
8. **Windows build workflow.** Test `build-windows.yml`; fix `--add-data` lines if the exe can't find assets or levels.

## 4. Known issues and cautions

- GitHub "artifact storage quota" errors: delete old Actions artifacts, set `retention-days: 2` in the workflows,
  or make the repo public.
- With `build_fast.py --all`, a stale `physics.*.pyd` hides edits to `physics.py`. Rebuild or delete it.
- Do not use the sample `_fast.pyx` pasted early in the chat. The real one is `game/scripts/_fast.pyx` (196 lines).
- When merging zips: older copies of `physics.py`, `functions.py`, `asset_funcs.py`, and Tree/Deco in `objects.py`
  may lack the performance work. Check for `query_static`, `collide_resting`, `get_tree_sprites` and the `_fp`
  profiler hooks in `game.py` after any merge.
- Colliders thinner than about 16 px can still be skipped by fast entities (lower `MAX_STEP`).
