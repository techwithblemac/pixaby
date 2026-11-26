"""
ammo.py
=======
How many arrows / fires / bombs one volley throws, and how many bombs one
entity may have alive at once. Pure data - no magic numbers in mind.py or
controls.py. Shop bonuses (``arrow_bonus`` ...) are added on top, for players
only (see ``ACTIVITY.ammo_count``).
"""

AMMO_BASE = {
    "player": {"arrow": 3, "fire": 3, "bomb": 10},
    "enemy":  {"arrow": 1, "fire": 1, "bomb": 1},
}

# live bombs one owner may have on screen at once (anti-lag + balance)
BOMB_CAP = {"player": 12, "enemy": 5}
