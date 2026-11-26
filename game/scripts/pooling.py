"""
pooling.py
==========
Generic object pool used to recycle short-lived, frequently-spawned game
objects — currently `Bomb`, `Arrow` and `Fire` (see `objects.py`).

Why this exists
----------------
Every thrown bomb, fired arrow and lit patch of fire was previously a brand
new Python/pygame object: `Bomb(...)`, `Arrow(...)`, `Fire(...)`. Under
heavy combat (several enemies shooting at once) this means constant
allocation *and* garbage collection churn, which shows up as frame-time
spikes — exactly the kind of thing an object pool is for.

Instead of constructing a new instance every time one is needed, and
letting the old one become garbage once it dies, we keep a small free-list
of already-constructed, currently-unused instances per class. "Spawning"
a new projectile pops an instance off that free-list and re-initialises
("resets") it in place; "destroying" one just clears it and pushes it back
onto the free-list instead of dropping the last reference to it.

Usage
-----
Pooled classes implement two things (see `Bomb`/`Arrow`/`Fire` in
`objects.py`):

- `reset(self, *args, **kwargs)` — re-runs the same setup `__init__` does,
  so a recycled instance is indistinguishable from a freshly built one.
- `return_to_pool(self)` — clears any references the object was holding
  (owner, target, ...) and hands itself back to its pool.

Spawning goes through `cls.spawn(*args, **kwargs)` rather than calling the
class directly. `spawn()` resolves the pool from the owner's `game`
instance (each `Game`/game-like object gets its own set of pools, stored
in `game._object_pools`, so pools never leak across separate game
sessions or the level-select screen's lightweight fx "game").
"""


class ObjectPool:
    """A free-list of pre-built instances of a single class."""

    def __init__(self, cls, max_size=10):
        self.cls = cls
        self.max_size = max_size
        self._free = []
        self.created = 0     # total instances ever constructed
        self.reused = 0      # total times an instance was recycled

    def acquire(self, *args, **kwargs):
        obj = None
        if self._free:
            #print(self.stats())
            obj = self._free.pop()
            obj.reset(*args, **kwargs)
            self.reused += 1
            return obj

        if self.created < self.max_size:
            obj = self.cls(*args, **kwargs)
            self.created += 1
            #print(self.created)
        return obj

    def release(self, obj):
        # Guard against the same instance being released twice (e.g. once
        # from an explicit destroy() path and again from the generic
        # dead-object sweep) - that would let it be handed out to two
        # different owners at once.
        if getattr(obj, "_pool_released", False):
            return

        obj._pool_released = True

        if len(self._free) >= self.max_size:
            # Pool is full - let this one be garbage collected normally
            # rather than growing without bound.
            return

        self._free.append(obj)

    def stats(self):
        return {
            "class": self.cls.__name__,
            "free": len(self._free),
            "created": self.created,
            "reused": self.reused,
        }


def get_pool(game, cls, max_size=100):
    """Return (creating if necessary) the pool for `cls` on `game`.

    Returns None if `game` is None - callers should fall back to plain
    construction in that case rather than pooling.
    """
    if game is None:
        return None

    pools = getattr(game, "_object_pools", None)
    if pools is None:
        pools = {}
        try:
            game._object_pools = pools
        except Exception:
            return None

    pool = pools.get(cls)
    if pool is None:
        pool = ObjectPool(cls, max_size=max_size)
        pools[cls] = pool
        print("bla bla bla")

    return pool


def pool_stats(game):
    """Convenience for debug overlays: stats for every pool on `game`."""
    pools = getattr(game, "_object_pools", None)
    if not pools:
        return []
    return [pool.stats() for pool in pools.values()]
