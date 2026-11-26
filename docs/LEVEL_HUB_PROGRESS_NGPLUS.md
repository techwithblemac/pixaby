# Level hub, progress save, New Game+ (v39)

## Folders
levels/story (1-10 + metadata.json) · levels/multiplayer (co-op, metadata.json: "players": 2-4)
levels/user_worlds (My Worlds, created on first use) · levels/test_worlds (debug / dev editor only)
game.level stays an int; game.level_folder says which folder. Paths resolve in game/scripts/paths.py.

## Saves (game/scripts/paths.py save_dir)
progress.json {highest_cleared, ng_plus} and achievements.json, both in the project folder (BASE_DIR).

## Flow
level_won() in game/level/progression.py replaces `game.level += 1` (objectives + exit door).
Story: save clear, next level, shop. Last story level: ui/ending.py (Return to start / Crawl again).
Other folders: no save, no shop, same level replays.
New Game+: story enemies x(1 + 0.5 * loops) health and damage (data/difficulty.py, NG_PLUS_STEP in level/progress.py).

## Selector
level/sources.py: each tab is a source with list()/load(). Add network sources there.
LevelSelector.SHOW_PRO = False hides the PRO+ button.
