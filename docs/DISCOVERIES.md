# THINGS THAT REDUCE GAME SPEED
# Bare TRY : EXCEPT BLOCKS
# ERRORS
# NOT CACHING
# MANY LOOPS
# Surface generation
# After caching rects,, make sure you always update the x, y positions accordingly (Arrows problem)
# Pallette swap FROM (DaFluffyPotatoe)
# FIX NODES - DECO is causing some nodes to not connect
# Dict mapping is great for optimisations
> ##  `BATTLE SYSTEM` is taking a lot of CPU.

'''
in `entity_utils`:

"""
if tentative_g <= g_score[neighbor]:
    found = True
    came_from[neighbor] = current
    g_score[neighbor] = tentative_g
    heapq.heappush(open_set, (tentative_g + heuristic(neighbor, end_node), neighbor, new_history))
"""

that condition was:
"""
if tentative_g < g_score[neighbor]:
"""

which means it wouldn't jump to a node that has the same score as 
'''

# A homing arrow that targets a POINT orbits it
A pursuer with a fixed speed and a limited turn rate never reaches its target: it circles at radius = speed / turn rate. The Homing Arrow Trap relies on that (objects/arrow_trap.py). With a perfectly constant turn rate the ring is boring; breathing the rate by +-15% (`WOBBLE`) gives a flower that sweeps ~0.6x-1.6x of the radius. At +-35% the arrows flew out to 2.5x and through the centre.

# Shop effects were player-only only by accident
Every shop rule was gated by `type == "player"`, but the data (`shop_stats`, `apply_loadout`) works on any `Entity`. Removing the gates was enough; enemies simply have empty stats by default. Keep new effects off `type == "player"` checks.

# Hit credit for objects
`Entity.hit(obj=...)` never credited a kill (lava, fire, spikes have no killer). Owned trap arrows set `credit_owner = True`; only objects with that flag credit `obj.owner`, so fire / lava behaviour is unchanged.

# Dash in `Entity.draw`
The dash ends from the draw code (x_vel == 0, or a long history trail), so an AI dash must keep setting x_vel every frame and also own a timer (`_dash_t`) - off-screen enemies are never drawn.

