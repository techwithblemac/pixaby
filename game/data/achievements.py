"""
achievements.py
===============
The achievement list. Pure data: edit names, goals and payouts here.

Each entry:
    id        unique key (saved in achievements.json)
    name      toast / card title
    desc      one-line description
    reward    {currency: amount} paid straight into the player's wallet,
              once, the first time it is earned (ever, not per run)
    category  one of CATEGORIES (the window's tabs)
    tier      bronze | silver | gold | pearl (frame / medal colour, see TIER_COLORS)
    icon      a glyph name from ui/shop_icons.py (sword, bolt, heart, flame, ...)
    counter   (optional) the tracker counter that drives progress; with ``goal`` it
              unlocks by itself and the window shows "63 / 100"
    goal      (optional) the number the counter has to reach
    hidden    (optional) shown as "???" until earned

Pearls are the scarce, valuable currency (they buy revives), so only the
harder feats pay them out.

How each one is detected is in scripts/achievements.py:
    kills / streaks   counted when a player lands a killing blow
    flawless etc.     checked when a floor is completed
    revives           counted by death_rules.revive
    allies            scripts/charm_mode.py
    spending / arsenal  scripts/shop_effects.py, ui/shop_screen.py
"""

CATEGORIES = ("Combat", "Survival", "Wealth", "Allies", "Exploration", "Secrets")
TIER_ORDER = ("bronze", "silver", "gold", "pearl")
TIER_COLORS = {
    "bronze": (205, 127, 50),
    "silver": (200, 208, 222),
    "gold": (255, 202, 80),
    "pearl": (255, 178, 238),
}

ACHIEVEMENTS = [
    # ---------------- Combat ---------------- #
    {"id": "centurion", "name": "Centurion", "desc": "Land 100 killing blows.",
     "reward": {"ruby": 3}, "category": "Combat", "tier": "silver", "icon": "sword",
     "counter": "kills", "goal": 100},
    {"id": "chain5", "name": "Chain Reaction", "desc": "5 kills within 6 seconds.",
     "reward": {"emerald": 1}, "category": "Combat", "tier": "bronze", "icon": "bolt"},
    {"id": "chain10", "name": "Rampage", "desc": "10 kills within 8 seconds.",
     "reward": {"pearl": 1}, "category": "Combat", "tier": "gold", "icon": "bolt"},
    {"id": "boss_down", "name": "Giant Slayer", "desc": "Defeat a boss.",
     "reward": {"ruby": 2}, "category": "Combat", "tier": "silver", "icon": "fang"},
    {"id": "sharpshooter", "name": "Sharpshooter", "desc": "Hit 10 arrows in a row.",
     "reward": {"emerald": 2}, "category": "Combat", "tier": "silver", "icon": "crosshair",
     "counter": "best_arrow_streak", "goal": 10},
    {"id": "pyro", "name": "Pyromaniac", "desc": "25 kills by fire.",
     "reward": {"emerald": 1}, "category": "Combat", "tier": "bronze", "icon": "flame",
     "counter": "fire_kills", "goal": 25},
    {"id": "demolition", "name": "Demolition Crew", "desc": "25 kills by bomb.",
     "reward": {"emerald": 1}, "category": "Combat", "tier": "bronze", "icon": "bomb",
     "counter": "bomb_kills", "goal": 25},
    {"id": "arsenal", "name": "Arsenal", "desc": "Max out Bigger Quiver, Ember Stock or Bomb Bag.",
     "reward": {"pearl": 1}, "category": "Combat", "tier": "gold", "icon": "arrow"},

    # ---------------- Survival ---------------- #
    {"id": "flawless", "name": "Flawless", "desc": "Clear a floor without taking damage.",
     "reward": {"ruby": 2}, "category": "Survival", "tier": "silver", "icon": "shield"},
    {"id": "one_hp", "name": "By a Thread", "desc": "Clear a floor with under 5% health.",
     "reward": {"pearl": 1}, "category": "Survival", "tier": "gold", "icon": "heart"},
    {"id": "untouchable", "name": "Untouchable", "desc": "Defeat a boss without taking damage.",
     "reward": {"pearl": 2}, "category": "Survival", "tier": "pearl", "icon": "shield"},
    {"id": "hot_feet", "name": "Hot Feet", "desc": "Spend 5 seconds in lava and still clear the floor.",
     "reward": {"pearl": 1}, "category": "Survival", "tier": "gold", "icon": "flame"},
    {"id": "second_wind", "name": "Second Wind", "desc": "Revive for the first time.",
     "reward": {"emerald": 1}, "category": "Survival", "tier": "bronze", "icon": "cloud",
     "counter": "revives", "goal": 1},
    {"id": "phoenix", "name": "Phoenix", "desc": "Revive 3 times in one run.",
     "reward": {"ruby": 1}, "category": "Survival", "tier": "silver", "icon": "flame",
     "counter": "revives_run", "goal": 3},

    # ---------------- Wealth ---------------- #
    {"id": "hoarder", "name": "Dragon's Hoard", "desc": "Finish a floor holding 500 gold.",
     "reward": {"pearl": 1}, "category": "Wealth", "tier": "gold", "icon": "gem"},
    {"id": "big_spender", "name": "Big Spender", "desc": "Spend 100 coins in the shop.",
     "reward": {"ruby": 2}, "category": "Wealth", "tier": "silver", "icon": "magnet",
     "counter": "coins_spent", "goal": 100},

    # ---------------- Allies ---------------- #
    {"id": "first_friend", "name": "Unlikely Friend", "desc": "Befriend an enemy with a charm.",
     "reward": {"emerald": 1}, "category": "Allies", "tier": "bronze", "icon": "charm"},
    {"id": "entourage", "name": "Entourage", "desc": "Have 3 friends at once.",
     "reward": {"pearl": 1}, "category": "Allies", "tier": "gold", "icon": "heart",
     "counter": "friends_peak", "goal": 3},

    # ---------------- Exploration ---------------- #
    {"id": "explorer", "name": "Explorer", "desc": "Use every kind of door in one run.",
     "reward": {"ruby": 2}, "category": "Exploration", "tier": "gold", "icon": "radar",
     "counter": "door_kinds", "goal": 3},
    {"id": "deep_diver", "name": "Deep Diver", "desc": "Clear the fifth floor.",
     "reward": {"ruby": 2}, "category": "Exploration", "tier": "silver", "icon": "pointer"},

    # ---------------- Secrets (hidden until earned) ---------------- #
    {"id": "gambler", "name": "Gambler", "desc": "Survive a failed charm on a boss.",
     "reward": {"ruby": 1}, "category": "Secrets", "tier": "silver", "icon": "clover", "hidden": True},
    {"id": "last_second", "name": "Last Second", "desc": "Confirm a charm with under a second left.",
     "reward": {"emerald": 2}, "category": "Secrets", "tier": "gold", "icon": "charm", "hidden": True},
    {"id": "window_shopper", "name": "Window Shopper", "desc": "Open the shop 10 times in a row without buying.",
     "reward": {"gold": 25}, "category": "Secrets", "tier": "bronze", "icon": "drum", "hidden": True,
     "counter": "shop_empty_streak", "goal": 10},
]

# Tunables for the counters above
CENTURION_KILLS = 100
CHAIN5 = (5, 6.0)            # (kills, seconds)
CHAIN10 = (10, 8.0)
ONE_HP_FRACTION = 0.05
HOARD_GOLD = 500
LAVA_SECONDS = 5.0
PHOENIX_REVIVES = 3
DEEP_DIVER_FLOOR = 5
LAST_SECOND_SECONDS = 1.0
RUN_COUNTERS = ("revives_run", "door_kinds")      # reset when a new run starts
