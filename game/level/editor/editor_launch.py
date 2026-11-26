"""
editor_launch.py
================
Opens the level editor on a specific level, from wherever the caller
happens to be -- currently the pencil button on the level selector's
details panel.

The selector deliberately does not import the editor itself. It takes an
``on_edit(game, level_id)`` callback, and this module is the default
implementation of that callback. That keeps the selector usable in
contexts that have no editor (a shipped build, a kiosk mode, a test
harness) simply by passing ``on_edit=None``.

The import of ``Level_Editor`` is deferred to call time on purpose:
``level_editor`` imports ``level_select`` at module scope, so a top-level
import here would close the cycle.
"""

from ...scripts import paths
from ...settings import Settings


def editor_available():
    """The level editor exists only while ``Settings.DEBUGGING_MODE`` is on.

    With the flag off nothing reaches it: no WORLD EDITOR button, no pencil or NEW + in the level selector,
    and the standalone launcher refuses to start. Every way in also ends at ``Level_Editor.edit_world``,
    which checks this again.
    """
    return bool(Settings.DEBUGGING_MODE)


def story_editing_locked(folder):
    """True when the editor may not open ``folder`` (kept for older callers).

    The whole editor is debug-only now (see ``editor_available``), so this is True for every folder
    while DEBUGGING_MODE is off, the story campaign included.
    """
    return not editor_available()


def can_edit(game):
    """True if ``game`` is a host the editor loop can actually run on.

    Both hosts qualify today: ``Game`` (Level_Loader + Level_Editor_Tools
    + Windows) and the standalone ``Level_Editor``.
    """
    return callable(getattr(game, "edit_world", None))


def launch_editor(game, level, folder=None):
    """Run the editor on ``level`` (in level ``folder``), then hand control back to the caller.

    The editor loads the level into the host's world state, so the host's
    previous level selection is restored afterwards and ``new`` is set so
    the next play re-reads the level from disk (picking up any edits the
    user just saved).
    """
    from ..level_editor import Level_Editor

    previous_level = getattr(game, "level", None)
    previous_folder = getattr(game, "level_folder", "story")
    if folder:
        game.level_folder = folder
    try:
        Level_Editor.edit_world(game, level=level, load=True)
    finally:
        game.level = previous_level if previous_level is not None else level
        game.level_folder = previous_folder
        # Force a reload on the next descent so saved edits take effect
        # and the editor's world state is never played directly.
        game.new = True
        game.EDIT_WORLD = False
        game.editing_level = False

    return True
