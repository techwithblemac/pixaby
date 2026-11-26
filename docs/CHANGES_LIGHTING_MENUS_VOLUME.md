# Lighting, shadows, fireflies, living menus, palette volume screen

## New files
- `game/ui/lighting.py`  - dynamic 2D lighting + contact shadows + fireflies.
- `game/ui/menu_ambience.py` - animated backdrop shared by every menu.

## World atmosphere (`game/ui/lighting.py`)
- Per-viewport lightmap (half-res, quarter-res on LOW_SPEC_MODE) multiplied over the world.
- Light sources: players (warm), Torch enemies (flickering), fire patches, fire traps,
  bomb fuses + explosion flash, coins (gem-coloured), doors (cool), mushrooms (bioluminescent).
- Ambient darkness is tinted per level biome tag (lava, water, ice, grass, dungeon...).
- Soft contact shadows under entities and coins (shrink/fade while airborne).
- Fireflies drift around each camera, light the scene and glow above the darkness.
- Toggles in `settings.py`: `LIGHTING`, `SHADOWS`, `FIREFLIES`. Tune colours/radii at the top of lighting.py.
- Hooked in `game.py` (after world draw, before HUD) and `level/main/draw_funcs.py` (shadows).

## Menus (`scripts/menu.py`, `windows.py`, `scripts/functions.py`)
- RPGButton: palette gradient body, glossy edge, drop shadow, eased slide-in with stagger,
  smooth hover lift + glow rings, shine sweep, pulsing ember markers, press squash,
  palette spark particles, hover/select tick sound. Labels prettified (game_info -> GAME INFO).
  Same public API (text/color/glow_color/alpha/rect still work, the editor keeps its tints).
- Every menu backdrop now drifts, has swaying god rays, floating embers, breathing vignette,
  and fades in when a screen opens (`Windows.draw_menu_bg`).
- PIXEL ABYSS title: wave-animated letters with a breathing coral halo.

## Volume screen (`scripts/sounds.py`)
- Centered palette card "SOUND" with a row per channel (MUSIC / SOUND FX), accent colours from ui_theme.
- Click/drag anywhere on the bar (absolute, no more relative-drift), mouse wheel, arrow keys with hold-repeat,
  d-pad/stick, M/Space/Enter to mute, ESC back.
- Animated speaker icon, live level meter, sliding mute switch, glowing knob, % badge.
- Mute no longer wipes your volume; unmuting restores it. Sliders start at the real current values.
- SFX preview tick when you let go of the SFX slider.
