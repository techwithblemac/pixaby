"""
shop_items.py
=============
Everything the shop sells. Pure data - edit prices and numbers here, no
code needs to change.

Four currencies, one tab each (the colours match the HUD coins):

    gold     consumables        heal, one-level boosts      (repeatable)
    ruby     permanent upgrades max HP, damage, speed       (levels)
    emerald  run perks          coin magnet, lifesteal, jump (levels)
    pearl    rare items         one-of-a-kind big upgrades  (once)

Item fields
-----------
id        unique key, stored in ``player.upgrades`` / ``player.boosts``
name/desc what the shop shows
currency  gold | ruby | emerald | pearl
kind      "charm"    a consumable STOCK (befriend charms, dashes): ``stock`` names the player
                     attribute, ``stack`` how many one purchase adds (default 1), ``cap`` the most
                     carried (+ the ``cap_stat`` shop stat). ``prices`` rise with how many have been
                     bought this run (the last price repeats).
          "heal"     instant: restore ``heal_pct`` of max HP
          "boost"    lasts for the NEXT level only, then expires
          "level"    permanent for the run, bought level by level
prices    cost of each purchase. ``level`` items have one price per level
          (so ``len(prices)`` is the max level); ``heal``/``boost`` items
          have a single price that is paid every time.
effects   what ONE level / one boost adds. Keys:
              max_health   +HP
              attack_mult  +fraction of damage dealt   (0.10 = +10%)
              speed_mult   +fraction of run speed
              jump_mult    +fraction of jump power
              damage_cut   -fraction of damage taken
              lifesteal    +fraction of max HP healed per kill
              coin_magnet  +pixels coins are pulled from
              minimap_level   +1 minimap level (0 = no minimap)
              pointer_level   +1 target-pointer level (0 = no pointers)
              charm_duration  +seconds of charm mode      charm_range  +px of charm reach
              charm_limit     +friends at once            charm_bond   +friend strength per level
              dash_time       +seconds of dash on a full bar   dash_regen   +fraction faster dash-bar refill
              arrow_bonus / fire_bonus / bomb_bonus   +projectiles per volley
              bomb_cap        +bombs alive at once        reload_cut   fraction off the reload time
              blast_radius    +px a bomb reaches          pierce       +enemies an arrow passes through
              homing          arrows steer to a target    hot_coals    +fire damage / seconds
              trap_arrows     +arrows per Homing Trap      trap_time    +seconds a Homing Trap lasts
              extra_jumps     +air jumps                  thorns       fraction of melee damage reflected
              luck            +coin drop chance           shield_hits  hits the Shield Bubble absorbs
              second_wind     free revives per run        treasure_radar  treasure on the minimap
          These effects are NOT for players only: the level editor's Entity Editor (data/entity_mods.py,
          entities/mods.py) can grant any shop item, or any raw effect, to an enemy; the same code runs.
          Items that only make sense for a player (heals, charms, minimap, magnet ...) are listed in
          ``entity_mods.PLAYER_ONLY_ITEMS`` and are not offered there.
          ``homing_trap`` is a charm-style stock (``player.traps``) dropped with the TRAP key (objects/arrow_trap.py).
          Optional ``readout``: (label, base, stat_key[, scale, unit]) draws "label now > next" in the shop row.
          Optional ``tab``: which shop tab lists the item (default: by currency, see TAB_OF_CURRENCY).
          Count-style keys (minimap_level, arrow_bonus ...) are read back with
          ``shop_effects.stat(player, key)``; see STAT_KEYS there.
"""

CURRENCIES = ("gold", "ruby", "emerald", "pearl")

# attribute on the player that holds each currency
WALLET_ATTR = {
    "gold": "gold_coins",
    "ruby": "ruby_coins",
    "emerald": "emerald_coins",
    "pearl": "pearl_coins",
}

SHOP_ITEMS = [
    # ---------------- GOLD: consumables ---------------- #
    {"id": "heal_small", "name": "Healing Draught", "currency": "gold", "kind": "heal",
     "desc": "Restore 30% of your max HP.", "prices": [30], "heal_pct": 0.30},
    {"id": "heal_full", "name": "Abyss Elixir", "currency": "gold", "kind": "heal",
     "desc": "Restore all of your HP.", "prices": [80], "heal_pct": 1.0},
    {"id": "war_drum", "name": "War Drum", "currency": "gold", "kind": "boost",
     "desc": "+25% damage for the next level only.", "prices": [60],
     "effects": {"attack_mult": 0.25}},
    {"id": "iron_skin", "name": "Iron Skin", "currency": "gold", "kind": "boost",
     "desc": "Take 25% less damage in the next level only.", "prices": [60],
     "effects": {"damage_cut": 0.25}},

    # ---------------- GOLD: charm + dash stock (story only) ---------------- #
    {"id": "befriend_charm", "name": "Befriend Charm", "currency": "gold", "kind": "charm",
     "stock": "charms", "cap": 9,
     "desc": "Turn an enemy into a friend. B (arrows player) / C (WASD player) / the charm button aims one. Only enemies with no more HP than you.",
     "prices": [40, 55, 75, 100, 130]},
    {"id": "shield_bubble", "name": "Shield Bubble", "currency": "gold", "kind": "boost",
     "desc": "Absorbs the next 3 hits on the next floor.", "prices": [18], "effects": {"shield_hits": 3}},

    # ---------------- RUBY: permanent upgrades ---------------- #
    {"id": "thorns", "name": "Thorns", "currency": "ruby", "kind": "level",
     "desc": "Reflect 15% of melee damage back at the attacker, per level.",
     "prices": [2, 3, 4], "effects": {"thorns": 0.15}, "readout": ("Reflected", 0, "thorns", 100, "%")},
    {"id": "charm_duration", "name": "Long Charm", "currency": "ruby", "kind": "level",
     "desc": "+2 seconds to choose a target in charm mode.",
     "prices": [2, 3, 4], "effects": {"charm_duration": 2}},
    {"id": "charm_bond", "name": "Strong Bond", "currency": "ruby", "kind": "level",
     "desc": "Friends hit harder and take less damage.",
     "prices": [3, 4, 5], "effects": {"charm_bond": 1}},
    {"id": "dash_master", "name": "Dash Recharge", "currency": "ruby", "kind": "level",
     "desc": "The dash bar refills 30% faster, per level.",
     "prices": [2, 3, 4], "effects": {"dash_regen": 0.30}, "readout": ("Refill speed", 100, "dash_regen", 100, "%")},
    {"id": "target_pointers", "name": "Target Pointers", "currency": "ruby", "kind": "level",
     "desc": "Arrows around you point at enemies. +range per level; level 3 colours them by type.",
     "prices": [2, 3, 4], "effects": {"pointer_level": 1}},
    {"id": "vitality", "name": "Vitality", "currency": "ruby", "kind": "level",
     "desc": "+50 max HP per level.", "prices": [2, 3, 4, 5, 6],
     "effects": {"max_health": 50}},
    {"id": "might", "name": "Might", "currency": "ruby", "kind": "level",
     "desc": "+10% damage per level.", "prices": [2, 3, 4, 5, 6],
     "effects": {"attack_mult": 0.10}},
    {"id": "swiftness", "name": "Swiftness", "currency": "ruby", "kind": "level",
     "desc": "+6% run speed per level.", "prices": [2, 3, 4],
     "effects": {"speed_mult": 0.06}},

    # ---------------- EMERALD: run perks ---------------- #
    {"id": "treasure_radar", "name": "Treasure Radar", "currency": "emerald", "kind": "level",
     "desc": "Needs the Minimap. L1 shows treasure, L2 points to far treasure, L3 pings it when close.",
     "prices": [2, 3, 4], "effects": {"treasure_radar": 1}},
    {"id": "lucky_clover", "name": "Lucky Clover", "currency": "emerald", "kind": "level",
     "desc": "+10% more coins dropped by fallen enemies, per level.",
     "prices": [2, 3, 4], "effects": {"luck": 0.10}, "readout": ("Extra coins", 0, "luck", 100, "%")},
    {"id": "charm_range", "name": "Wide Charm", "currency": "emerald", "kind": "level",
     "desc": "Charm mode can pick enemies from further away.",
     "prices": [2, 3, 4], "effects": {"charm_range": 250}},
    {"id": "dash_pouch", "name": "Dash Stamina", "currency": "emerald", "kind": "level",
     "desc": "A longer dash bar: +0.5 seconds of dash on a full bar, per level.",
     "prices": [2, 3, 4], "effects": {"dash_time": 0.5}, "readout": ("Dash seconds", 1.2, "dash_time", 1)},
    {"id": "minimap", "name": "Minimap", "currency": "emerald", "kind": "level",
     "desc": "A radar in the corner. L2 wider, L3 shows enemies, L4 shows doors and treasure.",
     "prices": [2, 3, 4, 5], "effects": {"minimap_level": 1}},
    {"id": "magnet", "name": "Coin Magnet", "currency": "emerald", "kind": "level",
     "desc": "Pulls coins to you from +110 px per level.", "prices": [2, 3, 4],
     "effects": {"coin_magnet": 110}},
    {"id": "lifesteal", "name": "Lifesteal", "currency": "emerald", "kind": "level",
     "desc": "Heal 3% of max HP per kill, per level.", "prices": [3, 4, 5],
     "effects": {"lifesteal": 0.03}},
    {"id": "springs", "name": "Spring Boots", "currency": "emerald", "kind": "level",
     "desc": "+5% jump height per level.", "prices": [2, 3, 4],
     "effects": {"jump_mult": 0.05}},

    # ---------------- PEARL: rare items ---------------- #
    {"id": "abyssal_heart", "name": "Abyssal Heart", "currency": "pearl", "kind": "level",
     "desc": "+120 max HP. One of a kind.", "prices": [3],
     "effects": {"max_health": 120}},
    {"id": "abyssal_fang", "name": "Abyssal Fang", "currency": "pearl", "kind": "level",
     "desc": "+30% damage. One of a kind.", "prices": [3],
     "effects": {"attack_mult": 0.30}},
    {"id": "second_wind", "name": "Second Wind", "currency": "pearl", "kind": "level",
     "desc": "Fall in battle and stand back up for free, at half health. Once per level bought.",
     "prices": [3, 5], "effects": {"second_wind": 1}},
    {"id": "double_jump", "name": "Cloud Step", "currency": "pearl", "kind": "level",
     "desc": "One extra jump in mid air. One of a kind.", "prices": [3], "effects": {"extra_jumps": 1}},
    {"id": "charm_limit", "name": "Entourage", "currency": "pearl", "kind": "level",
     "desc": "+1 friend at once. Befriended enemies follow you and fight for you.",
     "prices": [3, 5], "effects": {"charm_limit": 1}},

    # ---------------- ARSENAL: everything that throws, shoots or burns ---------------- #
    {"id": "quiver", "name": "Bigger Quiver", "currency": "ruby", "kind": "level", "tab": "arsenal",
     "desc": "+1 arrow per volley, per level.",
     "prices": [2, 2, 3, 3, 4], "effects": {"arrow_bonus": 1}, "readout": ("Arrows per volley", 3, "arrow_bonus")},
    {"id": "ember_stock", "name": "Ember Stock", "currency": "ruby", "kind": "level", "tab": "arsenal",
     "desc": "+1 fire per cast, per level.",
     "prices": [2, 2, 3, 3, 4], "effects": {"fire_bonus": 1}, "readout": ("Fires per cast", 3, "fire_bonus")},
    {"id": "bomb_bag", "name": "Bomb Bag", "currency": "ruby", "kind": "level", "tab": "arsenal",
     "desc": "+1 bomb per throw, per level.",
     "prices": [2, 2, 3, 3, 4], "effects": {"bomb_bonus": 1}, "readout": ("Bombs per throw", 10, "bomb_bonus")},
    {"id": "blast_radius", "name": "Wide Blast", "currency": "ruby", "kind": "level", "tab": "arsenal",
     "desc": "Bombs reach 10 px further, per level.",
     "prices": [2, 3, 4], "effects": {"blast_radius": 10}, "readout": ("Bomb reach", 0, "blast_radius", 1, " px")},
    {"id": "bomb_cap", "name": "Bomb Belt", "currency": "emerald", "kind": "level", "tab": "arsenal",
     "desc": "+2 bombs allowed alive at once, per level.",
     "prices": [2, 3, 4], "effects": {"bomb_cap": 2}, "readout": ("Live bombs", 12, "bomb_cap")},
    {"id": "quick_hands", "name": "Quick Hands", "currency": "emerald", "kind": "level", "tab": "arsenal",
     "desc": "8% faster reload and throw, per level.",
     "prices": [2, 3, 3, 4], "effects": {"reload_cut": 0.08}, "readout": ("Reload time", 100, "reload_cut", -100, "%")},
    {"id": "piercing_tips", "name": "Piercing Tips", "currency": "emerald", "kind": "level", "tab": "arsenal",
     "desc": "Arrows pass through 1 more enemy, per level.",
     "prices": [2, 3, 4], "effects": {"pierce": 1}, "readout": ("Extra targets", 0, "pierce")},
    {"id": "hot_coals", "name": "Hot Coals", "currency": "emerald", "kind": "level", "tab": "arsenal",
     "desc": "Fire burns 1 s longer and 15% hotter, per level.",
     "prices": [2, 3, 4], "effects": {"hot_coals": 1}},
    {"id": "homing_arrows", "name": "Homing Arrows", "currency": "pearl", "kind": "level", "tab": "arsenal",
     "desc": "Arrows curve toward the nearest enemy ahead. One of a kind.",
     "prices": [3], "effects": {"homing": 1}},
    {"id": "homing_trap", "name": "Homing Trap Kit", "currency": "ruby", "kind": "charm", "tab": "arsenal",
     "stock": "traps", "cap": 5,
     "desc": "A trap you drop with the TRAP key (V / E / pad button 3): homing arrows circle that spot and shoot down "
             "anything hostile that passes. They use your arrow properties.",
     "prices": [3, 4, 5, 6]},
    {"id": "trap_mastery", "name": "Trap Mastery", "currency": "emerald", "kind": "level", "tab": "arsenal",
     "desc": "+1 arrow in every trap and +4 s before it fades, per level.",
     "prices": [2, 3, 4], "effects": {"trap_arrows": 1, "trap_time": 4}, "readout": ("Arrows per trap", 3, "trap_arrows")},
]

# ---------------------------------------------------------------------- #
# shop tabs. A tab lists the items whose ``tab`` matches (default: by currency).
# ``color`` is the currency whose colour / coin the tab wears.
# ---------------------------------------------------------------------- #
TABS = (
    {"id": "consumables", "label": "CONSUMABLES", "color": "gold",
     "caption": "CONSUMABLES - heal up, boost the next floor, stock charms"},
    {"id": "upgrades", "label": "UPGRADES", "color": "ruby",
     "caption": "UPGRADES - permanent for this run"},
    {"id": "perks", "label": "PERKS", "color": "emerald",
     "caption": "RUN PERKS - utility that lasts the whole run"},
    {"id": "rare", "label": "RARE", "color": "pearl",
     "caption": "RARE ITEMS - one of a kind"},
    {"id": "arsenal", "label": "ARSENAL", "color": "ruby",
     "caption": "ARSENAL - more arrows, fire and bombs, and better ones"},
)
TAB_OF_CURRENCY = {"gold": "consumables", "ruby": "upgrades", "emerald": "perks", "pearl": "rare"}

ITEMS_BY_ID = {item["id"]: item for item in SHOP_ITEMS}


def tab_of(item):
    return item.get("tab") or TAB_OF_CURRENCY[item["currency"]]


def items_for_tab(tab_id):
    return [item for item in SHOP_ITEMS if tab_of(item) == tab_id]


def items_for(currency):
    """Every item priced in ``currency`` (all tabs)."""
    return [item for item in SHOP_ITEMS if item["currency"] == currency]
