"""Run the real game loop with no window and print the frame profile.

Repeatable benchmark for physics / AI / drawing changes: same level, same player, same report as
PIXABY_PROFILE (see frame_profiler.py), no need to play.

    python game/debug_tools/profile_headless.py             level 1 (story), 60 seconds
    python game/debug_tools/profile_headless.py 3 90        level 3, 90 seconds

The player just stands still and cannot die, so enemies come to it. Timing starts once the level
has loaded and the intro is over. Writes profile_report.txt + profile.prof in the project folder.
Levels in levels/story/<n>.json are used as they are.
"""
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # the folder that holds game/, assets/, levels/
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

LEVEL = int(sys.argv[1]) if len(sys.argv) > 1 else 1
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
os.environ["PIXABY_PROFILE"] = str(SECONDS)

import pygame                                        # noqa: E402
import game.main as gm                               # noqa: E402
import game.game as gg                               # noqa: E402
from game.scripts import paths, shop_effects, death_rules   # noqa: E402
from game.scripts.functions import calculate_viewports       # noqa: E402

g = gm.Game(LEVEL)
g.level, g.level_folder, g.level_players = LEVEL, paths.STORY, None
p = g.player
key = ["keyboard", 0]
g.controllers.append(key)
p.control_type = key[0]
g.players.append(p)
g.local_players.append(p)
p.viewport = pygame.Rect(*calculate_viewports(g, 1)[0])
g.update_player_edit()
p.ready = True
shop_effects.reset_run(g.player_slots)
death_rules.reset_run(g)
try:
    from game.level import progression
    progression.begin_run(g)
except Exception as err:                              # not needed for profiling
    print("progression.begin_run skipped:", repr(err))
g.level_completed = False
g.new = True

# don't count loading or the intro, and keep the player alive
_orig_start = gg._fp.frame_start


def _ready():
    intro = getattr(g, "world_intro", None)
    return (g.env_ready and not g.controller_selection and not getattr(g, "_intro_pending", False)
            and (intro is None or getattr(intro, "done", True)))


def _frame_start():
    if _ready():
        p.health = 10 ** 6
        p.dead = False
        _orig_start()


gg._fp.frame_start = _frame_start
threading.Timer(SECONDS + 40, lambda: setattr(g, "running", False)).start()    # safety stop
gg.main(g, code=0)
