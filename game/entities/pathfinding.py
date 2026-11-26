import heapq


PATH_COOLDOWN        = 0.35   # seconds between forced recomputes
                               # Lower = more responsive but more CPU
                               # Higher = cheaper but path feels "late"
                               # 0.25–0.5 is the sweet spot for most games.

PATH_RECOMPUTE_DIST  = 80     # pixels the TARGET must move before we
                               # recompute regardless of the timer.
                               # Should be roughly 1–2 tile widths.

# Platform graph node
class PlatformNode:
    def __init__(self, rect):
        self.rect = rect
        self.neighbors = []
        self.unwanted_neighbors = []

    def __lt__(self, other):
        return (self.rect.x, self.rect.y) < (other.rect.x, other.rect.y)


def isnext(self, a, b, history):
        return len(history[history.index(a):history.index(b)]) == 2

def heuristic(a, b):
    return abs(a.rect.centerx - b.rect.centerx) + abs(a.rect.centery - b.rect.centery)

def get_closest_node(self, rect):
    # Same result as before (first node with the smallest Manhattan distance between
    # centres), but the target centre is computed once instead of building a PlatformNode
    # and calling heuristic() for every candidate.
    cx, cy = rect.center
    closest = None
    min_dist = float('inf')
    for node in self.get_objects(self.game.node_map, rect, 0):
        r = node.rect
        dist = abs(r.centerx - cx) + abs(r.centery - cy)
        if dist < min_dist:
            min_dist = dist
            closest = node

    return closest

def get_direction(from_node, to_node):
    dx = to_node.rect.x - from_node.rect.x
    dy = to_node.rect.y - from_node.rect.y
    if dy > 0:
        return "down"
    elif dy < 0:
        return "up"
    elif dx > 0:
        return "right"
    elif dx < 0:
        return "left"
    return "none"


def _manage_pathfinding(obj):
    """
    Cached A* pathfinding.  Drop this method into the Entity class and
    call   obj._manage_pathfinding()   in manage() instead of the raw
    find_path block.

    Recomputes the path only when:
    • PATH_COOLDOWN seconds have elapsed  (time-based throttle)
    • The target has moved >= PATH_RECOMPUTE_DIST pixels  (position check)
    • obj.path is empty  (no path yet — covers first frame & path exhausted)

    obj.game.dt must be correct (non-zero) for the timer to work.
    """

    # Nothing to do if there is no target or physics aren't ready
    if not obj.target:
        obj.path             = []
        obj._path_timer      = 0.0
        obj._path_target_pos = None
        return

    # Only pathfind when grounded (or in water) — same condition as before
    can_pathfind = (
        obj.game.env_ready and
        ((obj.in_air_for < 0.5 and obj.jump_count == 0) or obj.zone)
    )
    if not can_pathfind:
        return

    # ── Decide whether to recompute ─────────────────────────────────────
    target_pos    = (obj.target.rect.centerx, obj.target.rect.centery)
    timer_expired = obj._path_timer <= 0.0
    path_empty    = not obj.path

    target_moved  = False
    if obj._path_target_pos is not None:
        dx = target_pos[0] - obj._path_target_pos[0]
        dy = target_pos[1] - obj._path_target_pos[1]
        # Use squared distance to avoid sqrt — compare against dist²
        target_moved = (dx * dx + dy * dy) > PATH_RECOMPUTE_DIST ** 2

    should_recompute = timer_expired or path_empty or target_moved

    if should_recompute:
        start = get_closest_node(obj, obj.rect)
        end   = get_closest_node(obj, obj.target.rect)

        if start and end:
            obj.path = obj.game.graph.find_path(start, end)

        # Reset the timer and record where the target was
        obj._path_timer      = PATH_COOLDOWN
        obj._path_target_pos = target_pos

    else:
        # Just tick the cooldown timer down
        obj._path_timer = max(0.0, obj._path_timer - obj.game.dt)


class PlatformGraph:
    def __init__(self, game):
        self.game = game
        self.path_cache = {} # {(start_id, end_id): path}
        self.reach_cache = {} # {(start_id, end_id): bool} for "no path" memory

    def node_id(self, node):
        return id(node)

    def find_path(self, start_node, end_node):
        if start_node == end_node:
            return []

        start_id, end_id = self.node_id(start_node), self.node_id(end_node)
        cache_key = (start_id, end_id)

        # 1. CACHE HIT: return instantly if we already solved this
        if cache_key in self.path_cache:
            return self.path_cache[cache_key][:]
        if cache_key in self.reach_cache: # we already know it's unreachable
            return []

        # 2. EARLY OUT: if nodes are too far, don't even search
        if heuristic(start_node, end_node) > 1200: # tune this to your map size
            self.reach_cache[cache_key] = False
            return []

        open_set = []
        heapq.heappush(open_set, (heuristic(start_node, end_node), 0, start_node, []))

        came_from = {}
        g_score = {start_node: 0}
        visited = set()
        tie_breaker = 0

        nodes_searched = 0
        MAX_NODES = 20 # bail if graph is huge. Prevents 2 second freeze

        while open_set:
            f, _, current, history = heapq.heappop(open_set)

            if current == end_node:
                path = self._reconstruct(came_from, current)
                self.path_cache[cache_key] = path
                return path[:]

            if current in visited:
                continue
            visited.add(current)

            nodes_searched += 1
            if nodes_searched > MAX_NODES: # gave up to prevent lag
                self.reach_cache[cache_key] = False
                return []

            for neighbor in current.neighbors:
                if neighbor in current.unwanted_neighbors or neighbor in visited:
                    continue

                direction = get_direction(current, neighbor)
                recent_dirs = history[-2:] + [direction]

                # Anti spam-jump
                if len(recent_dirs) == 3 and recent_dirs[0] == recent_dirs[1] == recent_dirs[2] == ("up" or "down"):
                    continue

                move_cost = 2.0 if (direction == "up" or direction == "down") else 1.0
                tentative_g = g_score[current] + move_cost

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + heuristic(neighbor, end_node)
                    came_from[neighbor] = current
                    tie_breaker += 1
                    heapq.heappush(open_set, (f_score, tie_breaker, neighbor, recent_dirs))

        # 3. No path found - cache it so we don't search again
        self.reach_cache[cache_key] = False
        return []

    def _reconstruct(self, came_from, current):
        path = []
        while current in came_from:
            path.append(current)
            current = came_from[current]
        path.reverse()
        return path

    def clear_cache(self):
        # call this when platforms change / break
        self.path_cache.clear()
        self.reach_cache.clear()
        
        
"""        
# in enemy update
if self.path_timer <= 0: # recalc every 0.5s instead of 60fps
    self.path = graph.find_path(self.current_platform, player_platform)
    self.path_timer = 30 # 30 frames = 0.5s at 60fps
self.path_timer -= 1"""