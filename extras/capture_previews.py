#!/usr/bin/env python3
"""
capture_previews.py - record the live GIF the level selector plays on its MAP PREVIEW.

For every level it loads the REAL world (same loader, enemies, water, decoration and lighting as playing it),
waits for the world intro to finish, then records a short loop of what the player would see and writes

    levels/<folder>/previews/<id>.gif

The selector (game/level/level_select.py -> game/level/preview_gif.py) plays that file on the preview panel.
Levels without a GIF keep the static map picture, so you can record only the ones you care about.

Usage (from the project folder, with a display; a window opens for each level for a few seconds):

    python3 extras/capture_previews.py                      every level in story, multiplayer and user_worlds
    python3 extras/capture_previews.py --missing            only levels with no GIF yet, or saved since their GIF
    python3 extras/capture_previews.py --folder user_worlds --level 3
    python3 extras/capture_previews.py --headless           no visible window (SDL dummy video driver)

Options worth knowing:
    --frames 36 --every 2     36 frames, one in every 2 game frames (the game runs at 30 FPS -> ~15 FPS GIF, 2.4 s loop)
    --width 360 --aspect 1.33 size of the GIF; the selector fills its panel from the middle of it
    --crop 0.70               how much of the window's width is kept (the middle), which drops the HUD and buttons
    --no-fast-intro           play the intro in real time instead of skipping to its end (slower, same result)

Pillow is required to write the GIF:  pip install pillow
Each level runs in its own process so one broken level cannot spoil the rest, and no state leaks between levels.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOLDERS = ("story", "multiplayer", "user_worlds")


# ---------------------------------------------------------------------------------------------- #
# parent: decide what to record, one child process per level
# ---------------------------------------------------------------------------------------------- #
def _ids(folder):
    directory = ROOT / "levels" / folder
    ids = []
    if directory.is_dir():
        for name in os.listdir(directory):
            if name.endswith(".json") and name[:-5].isdigit():
                ids.append(int(name[:-5]))
    return sorted(ids)


def _needs_capture(folder, level_id):
    gif = ROOT / "levels" / folder / "previews" / f"{level_id}.gif"
    level = ROOT / "levels" / folder / f"{level_id}.json"
    return (not gif.exists()) or (level.exists() and level.stat().st_mtime > gif.stat().st_mtime + 2.0)


def _child_args(args, folder, level_id):
    cmd = [sys.executable, str(Path(__file__).resolve()), "--one", folder, str(level_id),
           "--frames", str(args.frames), "--every", str(args.every), "--width", str(args.width),
           "--aspect", str(args.aspect), "--crop", str(args.crop), "--settle", str(args.settle),
           "--timeout", str(args.timeout)]
    if args.headless:
        cmd.append("--headless")
    if args.no_fast_intro:
        cmd.append("--no-fast-intro")
    return cmd


def run_all(args):
    jobs = []
    for folder in (args.folder or DEFAULT_FOLDERS):
        for level_id in ([args.level] if args.level is not None else _ids(folder)):
            if args.level is not None and level_id not in _ids(folder):
                print(f"skip {folder}/{level_id}: no such level")
                continue
            if args.missing and not _needs_capture(folder, level_id):
                continue
            jobs.append((folder, level_id))

    if not jobs:
        print("Nothing to record.")
        return 0

    failed = []
    for n, (folder, level_id) in enumerate(jobs, 1):
        print(f"[{n}/{len(jobs)}] {folder}/{level_id} ...", flush=True)
        started = time.time()
        result = subprocess.run(_child_args(args, folder, level_id), cwd=str(ROOT))
        if result.returncode == 0:
            print(f"    done in {time.time() - started:.1f}s")
        else:
            print(f"    FAILED (exit code {result.returncode})")
            failed.append(f"{folder}/{level_id}")

    print(f"\nRecorded {len(jobs) - len(failed)} of {len(jobs)} level(s).")
    if failed:
        print("Failed: " + ", ".join(failed))
    return 1 if failed else 0


# ---------------------------------------------------------------------------------------------- #
# child: load one level in the real game and record it
# ---------------------------------------------------------------------------------------------- #
class _Finished(Exception):
    """Raised from inside the game loop to leave it once the recording is complete (or has failed)."""


def record_one(args):
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")           # no sound while recording
    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    sys.path.insert(0, str(ROOT))

    try:
        from PIL import Image
    except ImportError:
        print("Pillow is needed to write the GIF:  pip install pillow")
        return 2

    folder, level_id = args.one[0], int(args.one[1])

    import pygame
    import game.main as game_main                               # builds the window (settings.py)
    from game import game as game_loop
    from game.scripts import death_rules, shop_effects
    from game.scripts.functions import calculate_viewports
    from game.level import progression

    g = game_main.Game(level_id)
    g.type = "preview"
    # --- start the level the way the selector does -------------------------------------------- #
    g.level = level_id
    g.level_folder = folder
    g.level_players = None
    g.MULTIPLAYER = False
    shop_effects.reset_run(g.player_slots)
    death_rules.reset_run(g)
    progression.begin_run(g)
    g.level_completed = False
    g.new = True

    # --- and join one keyboard player who is already READY (skips the join screen) ------------- #
    hero = g.player
    hero.key = ["keyboard", 0]
    hero.keyboard_num = 0
    hero.control_type = "keyboard"
    hero.ready = True
    g.controllers = [hero.key]
    g.local_players = [hero]
    g.players = [hero]
    hero.viewport = pygame.Rect(*calculate_viewports(g, 1)[0])
    g.update_player_edit()

    # --- what to keep of each window frame ------------------------------------------------------ #
    win_w, win_h = g.window.get_size()
    crop_w = max(64, int(win_w * max(0.2, min(1.0, args.crop))))
    crop_h = max(64, min(int(win_h * 0.9), int(crop_w / max(0.5, args.aspect))))
    crop = pygame.Rect(0, 0, crop_w, crop_h)
    crop.center = (win_w // 2, win_h // 2)
    out_w = max(64, int(args.width))
    out_h = max(48, int(out_w / (crop.width / crop.height)))

    frames = []
    state = {"settle": 0, "tick": 0, "started": time.time(), "error": None}

    def on_frame():
        if time.time() - state["started"] > args.timeout:
            state["error"] = f"no recording after {args.timeout:.0f}s (level did not finish loading?)"
            raise _Finished
        # still loading, on the join screen or waiting to start its intro: nothing to do yet
        if not g.env_ready or g.controller_selection or getattr(g, "_intro_pending", False):
            return

        hud = getattr(g, "objective_hud", None)
        if hud is not None:
            hud.hidden = True                                   # the mission card is not part of the picture

        intro = getattr(g, "world_intro", None)
        if intro is not None and not intro.done:
            if not args.no_fast_intro:
                intro.fast_forward()                            # skip to the intro's last stretch; it still ends itself
            return

        # the intro is over: let the world settle a few frames (camera, first AI tick), then record
        state["settle"] += 1
        if state["settle"] <= args.settle:
            return
        state["tick"] += 1
        if state["tick"] % max(1, args.every):
            return

        view = pygame.display.get_surface()
        piece = view.subsurface(crop).copy()
        piece = pygame.transform.smoothscale(piece, (out_w, out_h))
        frames.append(Image.frombytes("RGB", (out_w, out_h), pygame.image.tostring(piece, "RGB")))
        if len(frames) >= args.frames:
            raise _Finished

    real_flip, real_update = pygame.display.flip, pygame.display.update

    def flip(*a, **k):
        result = real_flip(*a, **k)
        on_frame()
        return result

    def update(*a, **k):
        result = real_update(*a, **k)
        on_frame()
        return result

    pygame.display.flip, pygame.display.update = flip, update

    try:
        game_loop.main(g, code=3)
    except _Finished:
        pass
    finally:
        pygame.display.flip, pygame.display.update = real_flip, real_update

    if state["error"] or len(frames) < max(2, args.frames // 2):
        print(f"Could not record {folder}/{level_id}: {state['error'] or 'the game closed before enough frames were captured'}")
        pygame.quit()
        return 1

    # --- write the GIF (to a temp name first, so a crash never leaves a half-written file) ------ #
    target = ROOT / "levels" / folder / "previews" / f"{level_id}.gif"
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".gif.tmp")
    delay = int(round(1000.0 / 30 * max(1, args.every)))        # the game runs at 30 FPS
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=128, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(temp, format="GIF", save_all=True, append_images=pal[1:], duration=delay, loop=0,
                optimize=True, disposal=1)
    os.replace(temp, target)
    print(f"Wrote {target.relative_to(ROOT)}  ({len(frames)} frames, {target.stat().st_size / 1024:.0f} KB)")
    pygame.quit()
    return 0


# ---------------------------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Record the live GIFs shown on the level selector's map preview.")
    ap.add_argument("--folder", action="append", help="story | multiplayer | user_worlds | test_worlds (repeatable)")
    ap.add_argument("--level", type=int, help="only this level id (use with --folder)")
    ap.add_argument("--missing", action="store_true", help="only levels with no GIF, or saved after their GIF")
    ap.add_argument("--frames", type=int, default=36)
    ap.add_argument("--every", type=int, default=2, help="keep one of every N game frames")
    ap.add_argument("--width", type=int, default=360, help="GIF width in pixels")
    ap.add_argument("--aspect", type=float, default=1.33, help="GIF width / height")
    ap.add_argument("--crop", type=float, default=0.70, help="fraction of the window width kept (the middle)")
    ap.add_argument("--settle", type=int, default=60, help="game frames to wait after the intro before recording")
    ap.add_argument("--timeout", type=float, default=90.0, help="give up on a level after this many seconds")
    ap.add_argument("--no-fast-intro", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--one", nargs=2, metavar=("FOLDER", "ID"), help=argparse.SUPPRESS)   # internal: one level
    args = ap.parse_args()

    if args.one:
        return record_one(args)
    return run_all(args)


if __name__ == "__main__":
    sys.exit(main())
