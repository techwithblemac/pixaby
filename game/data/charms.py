"""
charms.py
=========
Every number of the Befriend Charm and the bought-dash economy. Pure data:
tune the feel here, no code needs to change (see scripts/charm_mode.py).
"""

# ---- charm mode ----------------------------------------------------------
BASE_TIME = 10.0                 # REAL seconds to choose a target (+charm_duration per shop level)
SLOWMO = 0.15                    # world speed while aiming
SLOWMO_EASE = 9.0                # how fast the slow-mo eases in / out (1/s)
CANCEL_REFUND_WINDOW = 1.0       # ESC inside this many seconds refunds the charm (misclick guard)
BASE_RANGE_BONUS = 0             # px added to the player's acquire_range (shop adds charm_range)
PICK_RADIUS = 70                 # world px: how close a tap must be to a candidate to select it
STICK_DEADZONE = 0.55            # pad stick / hat threshold for "move the selection"
STICK_REPEAT = 0.28              # seconds between selection jumps while the stick is held
FOCUS_ZOOM = 1.12                # camera zoom while a target is selected

# ---- health gate ---------------------------------------------------------
BOSS_CAN_KILL = False            # False: the boss penalty can never take the player below 1 HP
BOSS_PENALTY_PCT = 0.35          # of max health ...
BOSS_PENALTY_MIN = 150           # ... but at least this much
GAP_PENALTY_PCT = 0.25           # of (target hp - player hp)
GAP_PENALTY_MIN_PCT = 0.10       # clamp: of max health
GAP_PENALTY_MAX_PCT = 0.30

# ---- friends -------------------------------------------------------------
BASE_FRIEND_LIMIT = 111            # friends at once (+charm_limit per shop level)
LEASH = 260                      # px: friends wander this far from the player before walking back
TELEPORT_DISTANCE = 1200         # px: further than this and a friend pops next to the player
TELEPORT_DY = 520                # px: ...or this far above / below while also fairly far away
BOND_STAT_PER_LEVEL = 0.15       # charm_bond: friend damage +15% and damage taken -15% per level

# ---- economy -------------------------------------------------------------
QUICK_BUY_MULT = 1.5             # quick-buy popup costs the shop price x this
START_DASHES = 1111                 # every new run starts with this many dashes
START_CHARMS = 1111
DASH_BASE_CAP = 1111               # most dashes you can carry (+dash_cap per shop level)
CHARM_CAP = 1111                    # most charms you can carry
