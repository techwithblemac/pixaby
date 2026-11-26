# Entity Editor, shop effects on entities, and Homing Arrow Traps

## Opening it
Level editor -> MODIFY mode -> click an enemy. (Clicking a Homing Arrow Trap opens a smaller window.)

Keys: UP/DOWN row, LEFT/RIGHT change (Shift = x10), TAB or `[` `]` category, digits = exact value,
DEL reset row, ENTER apply, ESC cancel. Mouse: click, drag sliders, wheel to scroll; the dot on a changed row resets it.

## Categories
| Category | What it holds |
|---|---|
| Placement | x/y inside the cell, facing, posted, patroller + ranges, sight range |
| Health | health override/multiplier, bonus max HP, regen (+delay), damage reduction, shield bubble, second wind, lifesteal, rage |
| Combat | attack power/bonus, reach, attack speed, knockback, crit chance/damage, thorns |
| Arrows & Ammo | arrow properties (damage, speed, knockback, burn) and shop effects: extra arrows/fires/bombs, pierce, homing, hot coals, bomb cap, blast radius |
| Movement & Dash | run speed, jump height, air jumps, **dash** (style, length, cooldown, dodge) |
| Homing Traps | lets the enemy drop traps: mode, max out, cooldown, range, arrows, radius, lifetime |
| Boss | is a boss, **boss title**, boss health/damage multipliers, "Fill in kit" |
| Shop items | every grantable shop item by tab (Upgrades, Perks, Rare, Arsenal, Boosts) with level pips |

## Saved format
Only values that differ from the default are written, under `mods` on the enemy entry:

```json
{"type": "enemy", "name": "Archer", "color": "Red", "x": 640, "y": 128, "facing": "left",
 "mods": {"boss": true, "boss_title": "The Hollow Warden", "boss_health_mult": 6.0, "regen": 2.0,
          "dash": true, "dash_mode": "evade", "trap": true, "trap_mode": "mixed",
          "arrow_burn": 2.0,
          "fx":    {"homing": 1, "arrow_bonus": 2, "pierce": 1},
          "items": {"quiver": 3}}}
```
`fx` = raw shop effects (keys of `shop_effects._ZERO`), added on top of what `items` give.
Schema: `data/entity_mods.py`. Runtime: `entities/mods.py`. Window: `ui/entity_editor.py`.

## Shop effects are not player-only
Shield, thorns, extra jumps, bomb cap, reload, pierce, homing and hot coals are read from `shop_stats` for any entity.
Enemies get them through `shop_effects.apply_loadout`, the same code the shop uses.

## Arrow properties
An entity's arrows use its arrow properties (`objects/arrow_trap.arrow_profile`): attack power x arrow damage,
knockback, pierce, homing, burn, speed, extra arrows. Homing arrows fired by an enemy target players.

## Homing Arrow Traps (`objects/arrow_trap.py`)
Homing arrows aimed at a **coordinate**. They can't turn fast enough to reach it, so they keep revolving around it
and hurt whatever hostile passes (never the owner's colour).

* **Level editor** (Traps category, type `homing`): no owner; effects are set by hand in Modify
  (arrows, radius, speed, damage, knockback, burn, pierce, hit gap, who it hurts, lifetime).
* **Players**: buy a *Homing Trap Kit* (Arsenal, rubies); drop with `V` (arrow-keys player), `E` (WASD player) or pad button 3.
  *Trap Mastery* adds arrows and lifetime. Owned traps copy the owner's arrow properties; kills credit the owner.
* **Enemies**: only those given "Drops homing traps" place them. Modes: `ahead` (where the target is heading),
  `target`, `ward` (around itself), `mixed`. The Archer boss kit turns on homing arrows, a dash and traps.

Not synced in multiplayer (the server skips homing traps).

## Where things live
| File | Role |
|---|---|
| `ui/entity_editor.py` | the window (`edit_entity`, `edit_trap`) |
| `data/entity_mods.py` | categories, fields, boss kits, grantable items, trap fields |
| `entities/mods.py` | `apply`, `tick`, `revive`, `ai_pre` (dash), `ai` (traps) |
| `objects/arrow_trap.py` | `ArrowTrap`, `arrow_profile`, `drop`, key / pad input |
| `level/editor/object_edit.py` | `apply_entity`, rebuilds the live enemy from its entry |
