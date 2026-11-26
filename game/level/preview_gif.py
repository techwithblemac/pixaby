"""
preview_gif.py
==============
The animated half of the level selector's MAP PREVIEW.

Every level can have a short looping GIF of the real world running (the player idling, enemies moving, water and
decoration animating), recorded by ``extras/capture_previews.py`` after the world intro has finished. It lives
beside the level it belongs to:

    levels/<folder>/previews/<id>.gif

What lives here
---------------
    gif_path(level_id, folder)      where a level's GIF is (or would be)
    is_stale(level_id, folder)      True when the level was saved after the GIF was recorded
    Clip                            decoded frames + delays; ``frame(now_ms, size)`` returns the Surface to blit
    PreviewGifs                     per-selector cache: ``get(level, size)`` -> (Surface | None, stale)

The selector falls back to the static map picture (level/preview.py) whenever a level has no GIF, the GIF is broken
or Pillow is not installed, so nothing here can stop the selector from opening.

Pillow (``pip install pillow``) is only needed to *decode* the GIF; pygame itself cannot read the later frames.
"""

import bisect
import os

import pygame

from ..scripts import paths

try:                                    # optional: without Pillow the selector keeps its static preview
    from PIL import Image, ImageSequence
except Exception:                       # pragma: no cover - depends on the machine
    Image = None
    ImageSequence = None

MAX_FRAMES = 120                        # a runaway GIF must not eat memory
MIN_DELAY_MS = 40                       # browsers treat 0-10 ms delays as 100 ms; do something sane here too
DEFAULT_DELAY_MS = 80
CORNER = 12                             # matches the border_radius of the selector's art panel
STALE_GRACE_S = 2.0                     # level saved less than this long after the GIF does not count as newer


def available():
    """True when GIFs can be decoded on this machine."""
    return Image is not None


def gif_path(level_id, folder=paths.STORY):
    """Path of a level's preview GIF (it may not exist)."""
    return os.path.join(paths.folder_dir(folder), "previews", f"{level_id}.gif")


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def is_stale(level_id, folder=paths.STORY):
    """True when the level file was saved after its GIF was recorded (the GIF shows an older version)."""
    gif, level = _mtime(gif_path(level_id, folder)), _mtime(paths.level_file(level_id, folder))
    return gif is not None and level is not None and level > gif + STALE_GRACE_S


def _from_rgb(data, size):
    """pygame 2.1.3+ calls it frombytes; older pygame (and some forks) only know fromstring."""
    make = getattr(pygame.image, "frombytes", None) or pygame.image.fromstring
    return make(data, size, "RGB")


def _round_mask(size, radius):
    """White rounded rectangle on transparent: multiplied onto a frame it rounds the corners."""
    mask = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    return mask


def _cover(frame, size):
    """Scale ``frame`` so it fills ``size`` (keeping its shape) and crop the overflow evenly."""
    fw, fh = frame.get_size()
    w, h = size
    scale = max(w / fw, h / fh)
    sw, sh = max(w, int(round(fw * scale))), max(h, int(round(fh * scale)))
    scaled = pygame.transform.smoothscale(frame, (sw, sh))
    out = pygame.Surface((w, h))
    out.blit(scaled, ((w - sw) // 2, (h - sh) // 2))
    return out


class Clip:
    """A decoded GIF: native-size frames plus when each one ends. Scaled copies are cached per panel size."""

    def __init__(self, frames, delays):
        self.frames = frames
        self.ends = []
        total = 0
        for delay in delays:
            total += max(MIN_DELAY_MS, int(delay or DEFAULT_DELAY_MS))
            self.ends.append(total)
        self.total = max(1, total)
        self._sized = {}                # (w, h) -> list of ready-to-blit Surfaces

    @classmethod
    def load(cls, path):
        """Decode ``path``. Returns None when Pillow is missing or the file is unreadable."""
        if Image is None:
            return None
        try:
            frames, delays = [], []
            with Image.open(path) as gif:
                for raw in ImageSequence.Iterator(gif):
                    rgb = raw.convert("RGB")
                    surf = _from_rgb(rgb.tobytes(), rgb.size).convert()
                    frames.append(surf)
                    delays.append(raw.info.get("duration", DEFAULT_DELAY_MS))
                    if len(frames) >= MAX_FRAMES:
                        break
            return cls(frames, delays) if frames else None
        except Exception as exc:
            print(f"[preview gif] could not read {path}: {exc}")
            return None

    def _for_size(self, size):
        key = (int(size[0]), int(size[1]))
        ready = self._sized.get(key)
        if ready is None:
            mask = _round_mask(key, CORNER)
            ready = []
            for frame in self.frames:
                out = _cover(frame, key).convert_alpha()
                out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                ready.append(out)
            self._sized = {key: ready}  # only the current panel size is worth keeping
        return ready

    def frame(self, now_ms, size):
        """The Surface to show at ``now_ms`` (any clock; the clip loops), filled to ``size``."""
        ready = self._for_size(size)
        at = int(now_ms) % self.total
        return ready[min(bisect.bisect_right(self.ends, at), len(ready) - 1)]


class PreviewGifs:
    """Keeps the GIFs of the levels the player has looked at; reloads one when its file changes."""

    def __init__(self, limit=8):
        self.limit = limit
        self._clips = {}                # path -> (mtime, Clip | None)

    def clear(self):
        self._clips.clear()

    def _clip(self, path):
        stamp = _mtime(path)
        if stamp is None:
            self._clips.pop(path, None)
            return None
        cached = self._clips.get(path)
        if cached is None or cached[0] != stamp:
            if len(self._clips) >= self.limit:
                self._clips.pop(next(iter(self._clips)))
            cached = (stamp, Clip.load(path))
            self._clips[path] = cached
        return cached[1]

    def get(self, level, size, now_ms):
        """(Surface or None, stale) for a selector level dict. None means: draw the static map instead."""
        if Image is None:
            return None, False
        level_id, folder = level.get("id"), level.get("folder") or paths.STORY
        clip = self._clip(gif_path(level_id, folder))
        if clip is None:
            return None, False
        return clip.frame(now_ms, size), is_stale(level_id, folder)
