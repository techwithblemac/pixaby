# v39 performance pass

Measured headless (same seeded run, Emerald Hollow, 1366x768, software rendering):
~36.5 ms/frame before -> ~31 ms with the code fixes alone, ~26 ms with adaptive quality on.

- scripts/functions.py: chunk maps are now `ChunkMap` (grid index). `physics.get_objects` and `map_chunks`
  look only at nearby chunks instead of testing all 144. Verified identical results/order on 5400 random queries.
- scripts/physics.py: `collide()` pre-filters blocks with `collidelistall` (C) before the Python loops; scope-0 path inlined.
- ui/lighting.py: light sprites bucketed by colour (the cache was thrashing on firefly colours); airborne shadow
  variants cached; adaptive quality governor (Settings.ADAPTIVE_QUALITY, default True):
  tier 1 cheap upscale, tier 2 quarter-res lightmap + no shadows + fewer fireflies/lava lights, tier 3 lighting off (only if ADAPTIVE_MAX_TIER = 3; default max is 2, ADAPTIVE_MIN_FPS = 30).
  Steps down when the frame rate sags, back up when there is headroom.
- level/main/draw_funcs.py: per-object `hide()` call inlined; shadow call skipped for blocks/deco.
- objects/object_utils.py: images are cached at zoom 1 too (they were rebuilt for every object every frame).
- settings.py: cache caps raised (they were smaller than one screen needs).
- ui/combat_fx.py: glow sprites cached. entities/controls.py: zoom ease snaps to target.
- main.py: added missing `calculate_viewports` import (crash on desktop Linux).

## HUD
- SPECTATE and VIEW buttons only appear when `DEBUGGING_MODE` is on; the in-game MENU button rests at low alpha (`MENU_BUTTON_ALPHA` in game.py).
