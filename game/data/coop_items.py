"""
coop_items.py
=============
Everything about loot in LOCAL co-op worlds (levels/multiplayer, played in Split Screen). Pure data: tune the
feel here, no code needs to change (rules live in scripts/coop_loot.py).

There is no shop in co-op, so power-ups come from the world instead:

    DROPS / SCATTER   generic power-ups (any hero): enemies drop them and a few lie around the level in random
                      places. Item ids are the shop's ids (data/shop_items.py), so a pick-up is applied exactly
                      like a purchase: levels stack up to the item's maximum, boosts last the level.
    MILESTONES        upgrades that suit ONE hero (arrows for the Archer, bombs for TNT, fire for the Torch ...)
                      are earned by kills, never found: every N kills of that hero grants the next one.
    CHARM             the Befriend Charm pick-up. Rare: it only exists where the level author placed one with the
                      Treasure tool in the level editor (name "charm"), never as a drop or random scatter.
    DASHES            free forever in co-op (scripts/charm_mode.py), nothing to collect.
"""

# ---- generic power-ups: (shop item id, weight) ---------------------------------------------------
# Heavier = more common. Hero-specific items (arrows, bombs, fire, thorns, ...) are NOT in here.
DROP_POOL = [
    ("heal_small", 26),        # Healing Draught: restores 30% HP, only picked up while hurt
    ("vitality", 11),          # +50 max HP
    ("might", 11),             # +10% damage
    ("swiftness", 9),          # +6% run speed
    ("springs", 7),            # +5% jump height
    ("magnet", 6),             # coins fly to you
    ("lifesteal", 6),          # heal on kill
    ("shield_bubble", 9),      # absorbs 3 hits, this level only
    ("war_drum", 6),           # +25% damage, this level only
    ("iron_skin", 6),          # -25% damage taken, this level only
    ("minimap", 3),
    ("target_pointers", 3),
    ("double_jump", 2),        # one extra air jump: rare
]

# ---- enemy drops -----------------------------------------------------------------------------------
DROP_CHANCE = 0.12             # base chance a fallen enemy leaves a power-up ...
DROP_CHANCE_PER_VALUE = 0.01   # ... plus this per coin the enemy was worth (tougher enemies drop more) ...
DROP_CHANCE_MAX = 0.30         # ... never more than this
MAX_LOOSE = 14                 # most pick-ups lying in the level at once (drops stop above this)
DROP_LIFESPAN = 40             # seconds a dropped power-up waits before it fades away

# ---- random places ---------------------------------------------------------------------------------
SCATTER_MIN, SCATTER_MAX = 3, 8        # how many lie around a level when it loads (scaled by level size)
SCATTER_PER_EXTRA_PLAYER = 1           # +1 for every local player beyond two
SCATTER_ONE_PER_CELLS = 80             # roughly one per this many walkable surfaces
SCATTER_MIN_GAP = 420                  # px between two scattered pick-ups
SCATTER_AVOID_START = 160              # px kept clear around spawn points

# ---- hero milestones: kills -> shop item id ----------------------------------------------------------
# Kills are counted per player for the whole run. Each hero walks down its own list; an item that is already
# at its maximum level is skipped (the milestone still counts).
MILESTONES = {
    "Archer": [(4, "quiver"), (10, "piercing_tips"), (18, "quiver"), (28, "homing_arrows"), (40, "quiver"),
               (55, "quick_hands")],
    "Torch": [(4, "ember_stock"), (10, "hot_coals"), (18, "ember_stock"), (28, "quick_hands"), (40, "ember_stock"),
              (55, "hot_coals")],
    "TNT": [(4, "bomb_bag"), (10, "blast_radius"), (18, "bomb_bag"), (28, "bomb_cap"), (40, "bomb_bag"),
            (55, "quick_hands")],
    "Warrior": [(4, "thorns"), (10, "abyssal_fang"), (18, "thorns"), (30, "abyssal_heart"), (45, "thorns")],
    "Pawn": [(4, "thorns"), (10, "abyssal_heart"), (18, "thorns"), (30, "abyssal_fang"), (45, "thorns")],
}
MILESTONE_TITLE = "{hero} MASTERY"

# ---- a pick-up the player cannot use ------------------------------------------------------------------
# Touching it leaves it where it is (for a teammate) and says why, at most once per this many milliseconds.
UNUSABLE_NOTICE_MS = 2500
UNUSABLE_NOTES = {              # item kind -> the line under the item's name
    "heal": "HEALTH IS FULL",
    "charm": "CHARMS ARE FULL",
    "boost": "ALREADY ACTIVE",
    "upgrade": "MAXED OUT",
}

# ---- the placeable charm pick-up -----------------------------------------------------------------------
CHARM_NAME = "charm"           # the "name" of its treasure entry in the level file
CHARM_ITEM = "befriend_charm"  # the shop item whose stock it fills
CHARM_AMOUNT = 1
START_CHARMS = 0               # charms a player starts a co-op run with
PLACEABLE = (CHARM_NAME,)      # treasure names the editor offers on top of the four coin colours
