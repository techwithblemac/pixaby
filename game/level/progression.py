"""
progression.py
==============
What happens when a level is won. Replaces the bare ``game.level += 1`` that
used to sit in two places (an objective completing, a door being walked through).

    story level        save the clear, move on to the next story level (shop, then load)
    last story level   the ending: celebration card, then Return to start / Crawl again
    anything else      co-op, My Worlds and test levels are one-offs: no save, no next level,
                       the same level simply plays again

Run stats for the ending (time, kills, achievements) are measured from
``begin_run``, which the game calls whenever a fresh run starts.
"""

from ..scripts import paths
from . import progress, sources


# ---------------------------------------------------------------------- #
# run bookkeeping
# ---------------------------------------------------------------------- #

def _kills(game):
    return sum(int(getattr(p, "kills", 0) or 0) for p in game.player_slots)


def _unlocked_ids():
    from ..scripts import achievements
    return set(achievements.tracker().unlocked)


def begin_run(game):
    """A fresh run starts now: zero the ending's counters."""
    game.run_clear_seconds = 0
    game.run_kills_start = _kills(game)
    game.run_ach_start = _unlocked_ids()


def run_stats(game):
    """What the ending card shows: clear time, kills, and achievements earned this run."""
    return {
        "seconds": int(getattr(game, "run_clear_seconds", 0)),
        "kills": max(0, _kills(game) - getattr(game, "run_kills_start", 0)),
        "achievements": len(_unlocked_ids() - getattr(game, "run_ach_start", set())),
        "loop": progress.get().ng_plus,
    }


# ---------------------------------------------------------------------- #
# winning a level
# ---------------------------------------------------------------------- #

def story_last_level():
    ids = sources.numeric_ids(paths.STORY)
    return ids[-1] if ids else 1


def level_won(game):
    """Call once when the current level is won (objective done, or exit door taken)."""
    folder = getattr(game, "level_folder", paths.STORY)

    if folder != paths.STORY:
        # one-off level: nothing is saved and there is no "next", so it just plays again
        game.level_completed = True
        game.new = True
        return

    game.run_clear_seconds = getattr(game, "run_clear_seconds", 0) + int(getattr(game, "elapsed_seconds", 0))
    progress.get().record_clear(game.level)

    if game.level >= story_last_level():
        finish_story(game)
        return

    game.level += 1
    game.level_completed = True         # -> shop, then the next level
    game.new = True


# ---------------------------------------------------------------------- #
# the ending
# ---------------------------------------------------------------------- #

def finish_story(game):
    """The last story level is won: celebrate, then start the next run the player picks."""
    from ..scripts import achievements, shop_effects, death_rules
    from ..ui import ending

    # The final floor never reaches the shop, so its achievements are paid out here.
    try:
        achievements.tracker().on_level_complete(game)
    except Exception as err:                        # a toast must never block the ending
        print(f"[ending] achievements skipped: {err!r}")

    prog = progress.get()
    choice = ending.show(game, run_stats(game), loop=prog.ng_plus)
    if choice is None:                              # window closed during the card
        return

    if choice == ending.CRAWL:
        prog.start_new_game_plus()                  # keeps upgrades and wallet, enemies get tougher
    else:
        shop_effects.reset_run(game.player_slots)   # a clean slate, like starting from the title
        if not getattr(game, "MULTIPLAYER", False):
            game._to_start = True                   # main() returns to the title screen
            game.running = False
            return

    death_rules.reset_run(game)
    begin_run(game)
    game.level = 1
    game.level_folder = paths.STORY
    game.level_completed = False                    # no shop after the ending
    game.new = True
