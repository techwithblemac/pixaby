# Combat feel, objective HUD, world intro

New files: game/ui/combat_fx.py, game/ui/objective_hud.py, game/ui/world_intro.py
Edited: game.py, entities/mind.py, entities/entity_utils.py, scripts/physics.py, level/main/objectives.py

Combat: hit flash, enemy red wind-up warning + "!", damage numbers (crit gold, finisher coral, damage taken red),
sparks/slash/debris, hit-stop, screen shake, combo chain (+3%/hit, finisher every 5th hit), 10% crit,
dash i-frames (0.24s, 0.9s cooldown) with DODGE / PERFECT DODGE, kill-streak banners, hurt + low-HP vignette.
Tuning constants are at the top of combat_fx.py.

Objective UI: mission card top-left (world, title, time, HP, plain-words objective, progress, status),
boss bar under the button row, goal pointer arrows, event banners (waves, exit open, boss phases).

World intro: iris reveal, letterbox, camera pull-back, animated title, objective typed out, GO!.
Retry of same world = short intro. Any key skips. WORLD CLEARED card with S/A/B/C rank before the shop.
