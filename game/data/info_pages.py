"""
info_pages.py
=============
Text and tables for the Game Info window. Anything with a number in it that lives elsewhere
(charm timings, health penalties, prices ...) is a ``{placeholder}`` filled from the real data at
runtime, so these pages cannot drift out of date. Change wording here, not in the window code.
"""

GAME_INFO_TABS = ("HOW TO PLAY", "CONTROLS", "CHARACTERS", "SHOP & COINS", "CHARMS & ALLIES", "TIPS")

HOW_TO_PLAY = [
    ("Fight your way down", "Each floor is a world of platforms, traps and enemies. Do what the mission card says "
     "(clear the enemies, find the key, survive the waves, beat the boss) and the exit door opens."),
    ("Step through the exit", "Walk into the green exit door to finish the floor. Doors of other colours "
     "(violet and cyan) teleport and warp you around the level."),
    ("Spend what you earn", "Fallen enemies and treasure drop coins. Between floors the shop turns them into health, "
     "upgrades, charms and dashes - open it, buy, and go on."),
    ("Fall? Get back up", "If you go down you can restart the floor, or revive with pearls. Some upgrades give a free "
     "second chance."),
    ("Build your own", "The Level Editor in Game Settings lets you build, save and test your own worlds. "
     "Shop items, charms and dashes belong to the story campaign only."),
]

# name -> (blurb, hp, speed, reach, special) ; bars are 1-5 and rough, hp and reach follow the real base stats
CHARACTERS = {
    "Warrior": ("A tough melee fighter. Hits hard up close.", 80, 4, 1, "Heavy sword"),
    "Pawn": ("Light and quick, fragile but nimble.", 50, 5, 1, "Fast strikes"),
    "Torch": ("Burns what it touches. Good all-rounder.", 65, 4, 1, "Fire damage"),
    "Archer": ("Shoots from a distance with homing-capable arrows.", 100, 3, 5, "Arrow volleys"),
    "TNT": ("Throws bombs from afar and keeps its distance.", 100, 3, 5, "Bombs"),
}

SHOP_LINES = [
    "Four coins, four jobs. Tabs in the shop group what they buy.",
    "Heal and boost items are single-use. Upgrades last the whole run and can be bought several times.",
    "Charm and dash stock is carried between floors, and prices go up as you buy.",
    "When a run starts over, everything bought is reset.",
]

CURRENCY_INFO = {
    "gold": ("Gold", "Everyday coins from enemies and treasure. Buys heals, charms and shields."),
    "ruby": ("Ruby", "Rarer. Buys permanent upgrades: more arrows, bombs and damage, Thorns and more."),
    "emerald": ("Emerald", "Run perks: the Minimap, Treasure Radar, Quick Hands, Piercing Tips ..."),
    "pearl": ("Pearl", "The rarest coin. Rare items and revives. Spend them wisely."),
}

CHARM_LINES = [
    "Press {charm_key} (or the heart button) to start charm mode. The world slows down and you have "
    "{time:g} seconds to pick an enemy.",
    "Choose with the movement keys, the D-pad or by tapping. Confirm to try the charm. Cancel within "
    "{refund:g} second and the charm is not used up.",
    "A charm only works on an enemy with no more health than you. Too strong, and you lose the charm and "
    "take damage; try it on a boss and you lose a lot of health (but never your last point).",
    "A friend follows you, fights for you and teleports to you if it falls behind. You can have {limit} "
    "friend at a time at first; at the limit the oldest friend leaves.",
    "Friends do not carry over to the next floor. Kill-all and boss missions ignore them.",
]

TIPS = [
    "Cancelling a charm in the first second costs nothing - use it to look around.",
    "Strong Bond makes friends hit harder and take less damage.",
    "The dash is a bar: it drains while you dash and refills when you stop. Dash Stamina lengthens it, Dash Recharge refills it faster.",
    "Hold the slow-motion key to line up arrows and bombs.",
    "Wide Charm lets you choose from further away; Long Charm gives you more time.",
    "Treasure Radar needs the Minimap and shows coins you cannot see yet.",
    "Shield Bubble swallows whole hits, so it is best spent on a boss floor.",
]

AUTHOR_NAME = "BLEMAC"
AUTHOR_FULL_NAME = "Blessing Machekeche"
AUTHOR_BLURB = "Independent game developer and Python creator."
AUTHOR_LINKS = [
    ("GitHub", "https://github.com/tech-with-blessing"),
    ("Pixel Abyss on itch.io", "https://techwithblemac.itch.io/pixel-abyss"),
    ("Facebook", "https://www.facebook.com/profile.php?id=61578165867167"),
    ("X", "https://x.com/techwithblemac/"),
]

MODES = [
    # key, title, tagline, description, (multiplayer, server, split_screen), features [(label, yes/no)]
    ("solo", "SOLO", "One hero, the whole abyss.",
     "Play the story campaign on this machine. Everything is available: the shop, charms, dashes and the "
     "achievements.", (False, False, False),
     [("Story campaign", True), ("Shop, charms and dashes", True), ("Achievements", True), ("Needs a network", False)]),
    ("split", "SPLIT SCREEN", "Up to four heroes, one screen.",
     "Local co-op on this machine: everyone gets their own view. Keyboards and gamepads join on the "
     "join screen. Co-op worlds, My Worlds and test levels all play locally, no network needed.", (False, False, True),
     [("Co-op worlds, 2 to 4 players", True), ("Keyboard and gamepad", True), ("Story campaign (solo run)", False),
      ("Needs a network", False)]),
    ("host", "HOST", "Be the server.",
     "Start a game for others to join over the network. Your machine runs the world. Gameplay-changing "
     "shop features are switched off online for now.", (True, True, False),
     [("Story campaign", True), ("Shop, charms and dashes", False), ("Achievements", True), ("Needs a network", True)]),
    ("join", "JOIN", "Drop into a friend's world.",
     "Connect to a host and play in their world. The host decides the level. Charms and the shop are "
     "not available online yet.", (True, False, False),
     [("Story campaign", True), ("Shop, charms and dashes", False), ("Achievements", True), ("Needs a network", True)]),
]
