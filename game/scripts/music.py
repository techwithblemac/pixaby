"""
music.py
========
The music director: decides which song a level / screen gets (``choose``) and plays it with a
cross-fade (``Music``). The tables are in data/music.py; this is the only module that touches the
songs. The volume is Settings.BG_SOUNDS_VOLUME (the MUSIC slider) and follows the slider live.

    from ..scripts.music import music
    music.play_level(game)      # after a level has loaded: picks + cross-fades
    music.scene("menu")         # a non-level screen
    music.stop(fade_ms=500)

A missing file, a song that will not decode, or a muted mixer never raises: the game falls back to the
generic title song (or silence) and prints one line.
"""

import os
from collections import OrderedDict

import pygame

from ..data import music as table
from ..data.biomes import BIOMES, BIOME_NAMES, tag_biome, level_meta


# ---------------------------------------------------------------------- #
# choosing (pure: no pygame objects, easy to test)
# ---------------------------------------------------------------------- #
def stem_of(theme_id):
    """Song file stem for a theme id: a biome id ("3") or an explicit stem ("theme_3_dune_ruins")."""
    return table.BIOME_THEMES.get(str(theme_id), str(theme_id)) if theme_id else None


def _stone_share(counts):
    total = sum(counts.values())
    return (counts.get(table.STONE_BIOME, 0) / total) if total else 0.0


def choose(counts, meta=None, objective_kind=None):
    """Pick a theme id for a level.

    counts          {biome id: weighted block count} from data/biomes.BiomeMap
    meta            the level's metadata entry (tags, optional "theme" / "biome")
    objective_kind  "clear_all" | "survival" | "exit" | "boss" | "final" | None

    Returns (theme_id, reason). The rule order is documented in data/music.py.
    """
    meta = meta or {}
    counts = counts or {}

    if meta.get("theme"):                                              # 1  explicit
        return str(meta["theme"]), "metadata theme"
    forced = str(meta["biome"]) if meta.get("biome") is not None else ""
    if forced in BIOMES:                                               # 2  forced look
        return forced, "metadata biome"

    top = max(counts, key=counts.get) if counts else None
    if top is not None:                                                # 3  conclusive blocks
        if top != table.STONE_BIOME or _stone_share(counts) >= table.STONE_CONFIDENCE:
            return top, "blocks"

    hint = tag_biome(meta.get("tags"))                                 # 4  the level's type
    if hint:
        return hint, "tags"
    if objective_kind in table.OBJECTIVE_THEME:
        return table.OBJECTIVE_THEME[objective_kind], f"{objective_kind} objective"

    if top is not None:                                                # 5  whatever the blocks say
        return top, "blocks (weak)"
    return table.STONE_BIOME, "default"


# ---------------------------------------------------------------------- #
# playing
# ---------------------------------------------------------------------- #
class Music:
    def __init__(self):
        self.theme = None            # theme id playing now (None = nothing, "generic" = the title song)
        self.sound = None            # the pygame Sound playing now
        self._cache = OrderedDict()  # stem -> Sound (only the last KEEP_LOADED)
        self._warned = set()

    # ----- volume -----
    @staticmethod
    def _volume():
        from ..settings import Settings
        return Settings.BG_SOUNDS_VOLUME

    def set_volume(self, value=None):
        """Apply the MUSIC volume to whatever is playing (the slider calls this while it moves)."""
        if self.sound is not None:
            self.sound.set_volume(self._volume() if value is None else value)

    # ----- loading -----
    def _load(self, stem):
        if stem in self._cache:
            self._cache.move_to_end(stem)
            return self._cache[stem]
        from . import paths
        snd = None
        for ext in table.EXTENSIONS:
            path = paths.asset("sounds", "themes", stem + ext)
            if os.path.exists(path):
                try:
                    snd = pygame.mixer.Sound(path)
                except Exception as err:                 # an undecodable file must never stop the game
                    self._warn(stem, f"{path}: {err}")
                break
        else:
            self._warn(stem, f"no song file for {stem!r} in assets/sounds/themes")
        if snd is not None:
            self._cache[stem] = snd
            while len(self._cache) > table.KEEP_LOADED:
                old = next(iter(self._cache))
                if self._cache[old] is self.sound:
                    self._cache.move_to_end(old)
                    old = next(iter(self._cache))
                self._cache.pop(old)
        return snd

    def _warn(self, key, message):
        if key not in self._warned:
            self._warned.add(key)
            print(f"[music] {message}")

    # ----- transport -----
    def stop(self, fade_ms=0):
        snd = self.sound
        if snd is not None:
            try:
                snd.fadeout(fade_ms) if fade_ms else snd.stop()
            except Exception:
                pass
        self.sound, self.theme = None, None

    def _generic(self):
        from ..assets import Assets
        return Assets.SOUNDS.get("theme")

    def play_generic(self):
        """The title song (assets/sounds/theme.wav)."""
        snd = self._generic()
        if snd is None or (self.theme == "generic" and snd.get_num_channels() > 0):
            return
        self.stop(table.FADE_OUT_MS)
        snd.set_volume(self._volume())
        snd.play(-1, fade_ms=table.FADE_IN_MS)
        self.sound, self.theme = snd, "generic"

    def play(self, theme_id):
        """Cross-fade to a theme (a biome id or a file stem); the title song if it cannot be played."""
        if not theme_id:
            return self.play_generic()
        snd = self._load(stem_of(theme_id))
        if snd is None:
            return self.play_generic()
        if self.theme == str(theme_id) and snd.get_num_channels() > 0:
            return                                                  # already playing (e.g. a retry)
        old = self._generic()
        self.stop(table.FADE_OUT_MS)
        if old is not None:
            old.fadeout(table.FADE_OUT_MS)
        snd.set_volume(self._volume())
        snd.play(-1, fade_ms=table.FADE_IN_MS)
        self.sound, self.theme = snd, str(theme_id)

    # ----- what the game calls -----
    def pick_for_level(self, game):
        """(theme_id, reason) for the level that is loaded in ``game``."""
        bm = getattr(game, "biome_map", None)
        counts = getattr(bm, "counts", None) if bm else None
        meta = level_meta(getattr(game, "level", None), getattr(game, "level_folder", "story"))
        kind = getattr(getattr(game, "objective", None), "kind", None)
        return choose(counts, meta, kind)

    def play_level(self, game):
        theme, why = self.pick_for_level(game)
        self.play(theme)
        print(f"[music] {BIOME_NAMES.get(theme, theme)} ({why})")
        return theme

    def scene(self, name):
        """A non-level screen: its SCENE_THEME entry, else the title song."""
        theme = table.SCENE_THEME.get(name)
        self.play(theme) if theme else self.play_generic()


music = Music()
