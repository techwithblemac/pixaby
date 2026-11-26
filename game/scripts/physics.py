import math
import pygame
import random
import itertools

try:                                   # optional compiled helper, built by build_fast.py
    from ._fast import query as _fast_query
    from . import _fast as _fast_module
    print(f"[physics] compiled helper IN USE: {_fast_module.__file__}")
except ImportError as _fast_err:       # not built (or built for another Python): pure Python below
    _fast_query = None
    print(f"[physics] compiled helper NOT used (pure Python). Reason: {_fast_err}")
    print("[physics] build it with:  python build_fast.py   (run inside the game folder)")
print(f"[physics] physics module: {__file__}")   # ends in .py normally, .pyd/.so if built with --all

# Knockback kinematics (pixels / seconds). A hit launches the target with
# an initial speed v0 (px/s) that bleeds off under constant deceleration a:
#     v(t) = v0 - a*t        x(t) = v0*t - 0.5*a*t^2
# so total slide distance is v0^2 / (2a) and it lasts v0 / a seconds.
KNOCKBACK_DECEL_GROUND = 1200.0   # px/s^2, floor friction
KNOCKBACK_DECEL_AIR = 400.0       # px/s^2, air drag

# --- AABB collision settings -------------------------------------------------
# Each axis is moved and resolved on its own (x first, then y). A move bigger
# than MAX_STEP pixels is cut into smaller steps so fast things (arrows, dashes,
# long falls) can't skip over a thin block between two frames.
MAX_STEP = 16
PROJECTILES = {'arrow'}
FACE_LEFT = (-1, 0)    # block.outlines entries = which faces are exposed
FACE_RIGHT = (1, 0)
FACE_UP = (0, -1)
FACE_DOWN = (0, 1)


_playit = None
_dash_bar = None


def _get_playit():
    """sounds.playit, imported once (an import statement inside collide() ran every call)."""
    global _playit
    if _playit is None:
        from .sounds import playit
        _playit = playit
    return _playit


def _get_dash_bar():
    global _dash_bar
    if _dash_bar is None:
        from . import dash_bar
        _dash_bar = dash_bar
    return _dash_bar


def split_move(d, max_step=MAX_STEP):
    """Split a pixel move into near-equal steps no bigger than max_step."""
    if -max_step <= d <= max_step:      # common case: no splitting needed
        return (d,)
    sign = 1 if d > 0 else -1
    n = -(-abs(d) // max_step)
    base, rem = divmod(abs(d), n)
    return [sign * (base + (1 if i < rem else 0)) for i in range(n)]


def add_map(scope, grid, objects, obs, rect):
    if scope != 0:
        cx, cy = rect.centerx, rect.centery
        if grid:
            objects.extend([t for t in obs[1]
                            if abs(t[0].centerx - cx) < scope and abs(t[0].centery - cy) < scope])
        else:
            objects.extend([t for t in obs[1]
                            if abs(t.rect.centerx - cx) < scope and abs(t.rect.centery - cy) < scope])
    else:
        objects.extend(obs[1])


# Calculate the degree
def get_degree(x_vel, y_vel, current_degree):
    # Calculate the arrow angle based on its velocity

    needed_degree = int(math.degrees(math.atan2(-y_vel, x_vel)))

    if int(y_vel) == 0 and int(x_vel) == 0:
        pass
    else:
        rotation_speed = 20  # Adjust this value to control the rotation speed

        # Calculate the difference between the current angle and the target angle
        angle_diff = needed_degree - current_degree

        # If the angle difference is greater than 180 degrees, it's shorter to rotate in the other direction
        if angle_diff > 180:
            angle_diff -= 360
        elif angle_diff < -180:
            angle_diff += 360

        # Update the arrow's angle based on the direction of rotation
        if angle_diff > 0:
            current_degree = min(needed_degree, current_degree + rotation_speed)
        else:
            current_degree = max(needed_degree, current_degree - rotation_speed)

    return int(needed_degree), int(current_degree)


# Calculate distance                 
def find_distance(startx, starty, endx, endy, length=50):
    dx = startx - endx
    dy = starty - endy
    dist = math.hypot(dx, dy)
    angle = math.atan2(dy, dx)
    px = endx + math.cos(angle) * length
    py = endy + math.sin(angle) * length

    return dist, dx, dy, angle, px, py


# Calculate distance 2
def distance(x1, y1, x2, y2):
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


class PHYSICS:
    _rest_static = False     # last landed on plain terrain (not a moving platform)
    _rest_pos = None         # (x, y, w, h) of the rect after that landing


    # Calculate distance                 
    @staticmethod
    def find_distance(startx, starty, endx, endy, length=50):
        dx = startx - endx
        dy = starty - endy
        dist = math.hypot(dx, dy)
        angle = math.atan2(dy, dx)
        px = endx + math.cos(angle) * length
        py = endy + math.sin(angle) * length

        return dist, dx, dy, angle, px, py

    @staticmethod
    # Calculate distance 2
    def distance(x1, y1, x2, y2):
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    def mask_collided(self, obj):
        if self.mask and obj.mask:
            return pygame.sprite.collide_mask(self, obj)
        else:
            return False
        
    @staticmethod
    def get_objects(map, rect, scope=200, grid=False):
        objects = []
        if hasattr(map, "candidates"):
            # grid-indexed chunk map: only look at the chunks near the rect(s)
            cells = map.candidates_many(rect) if isinstance(rect, list) else map.candidates(rect)
        else:
            cells = map.values()
        for obs in cells:
            if not obs[1]:
                continue
            
            if isinstance(rect, list):
                index = obs[0].collidelistall(rect)
                if index:
                    add_map(scope, grid, objects, obs, rect)
            
            else:
                if obs[0].colliderect(rect):
                    if scope == 0:
                        objects.extend(obs[1])      # add_map()'s scope-0 case, minus the call
                    else:
                        add_map(scope, grid, objects, obs, rect)
        
        return objects
    
    @staticmethod
    def query_static(map, area):
        """(objects, rects) of a map's objects that overlap `area`, in map order, no duplicates.

        For maps that don't change while the level runs (terrain, water zones). Each chunk's
        rect list is built once and kept on the map, then filtered against `area` in C, so a
        lookup no longer builds a Python list of every block in the chunk. map_chunks() bumps
        map.version when it refills a map, which throws the cache away.
        """
        if _fast_query is not None:
            found = _fast_query(map, area)      # same answer, computed in C; None = can't handle
            if found is not None:
                return found

        if not hasattr(map, "candidates"):
            objs = PHYSICS.get_objects(map, area, 0)
            return objs, [o.rect for o in objs]

        cache = getattr(map, "_rect_cache", None)
        ver = getattr(map, "version", 0)
        if cache is None or cache[0] != ver:
            cache = map._rect_cache = (ver, {})
        per_cell = cache[1]

        cells = map.candidates(area)
        seen = set() if len(cells) > 1 else None
        objs, rects = [], []
        for cell in cells:
            items = cell[1]
            if not items or not cell[0].colliderect(area):
                continue
            key = id(items)
            n = len(items)
            ent = per_cell.get(key)
            if ent is None or ent[0] != n:
                ent = per_cell[key] = (n, [o.rect for o in items])
            crects = ent[1]
            hits = area.collidelistall(crects)
            for i in hits:
                if items[i].rect is not crects[i]:      # an object swapped its Rect: refresh the cell
                    ent = per_cell[key] = (n, [o.rect for o in items])
                    crects = ent[1]
                    hits = area.collidelistall(crects)
                    break
            for i in hits:
                o = items[i]
                if seen is not None:
                    if id(o) in seen:
                        continue
                    seen.add(id(o))
                objs.append(o)
                rects.append(crects[i])
        return objs, rects

    @staticmethod
    def get_outline_blocks(blocks, tile_size=32):
        """
        Return only blocks that are on the outer edge of the shape.

        Args:
            blocks: list of objects with.rect -> pygame.Rect. All rects should be tile_size aligned.
            tile_size: width/height of each block. Must be consistent.

        Returns:
            list[block]: only the perimeter blocks
        """
        if not blocks:
            return []

        # 1. Build a fast lookup: (grid_x, grid_y) -> block
        block_map = {}
        for b in blocks:
            gx = b.rect.x // tile_size
            gy = b.rect.y // tile_size
            block_map[(gx, gy)] = b

        outline = []
        # 2. Check 4 neighbors for each block
        dirs = {(1, 0), (-1, 0), (0, 1), (0, -1)} # right, left, down, up

        for b in blocks:
            gx = b.rect.x // tile_size
            gy = b.rect.y // tile_size
            
            is_outline = False   
            for dx, dy in dirs:
                neighbor_key = (gx + dx, gy + dy)
                if neighbor_key not in block_map:
                    is_outline = True
                    b.outlines.add((dx, dy))
                    #break  #Missing neighbor = this side is exposed
            if is_outline:
                outline.append(b)

        return outline

    def collide(self, destroy=False, depth=0):
        #return
        game = self.game
        dt = game.dt
        self.stepping_on_platform = False

        # If we were riding a moving platform last frame, move with it first
        # (before applying our own velocity). This keeps us glued to the
        # platform's surface regardless of which direction it's moving, so
        # our own x/y collision checks below start from the correct
        # position instead of seeing a stale overlap from the platform
        # having moved into/away from us.
        riding = getattr(self, 'riding_platform', None)
        if riding is not None:
            if riding in self.game.platforms and not getattr(riding, 'dead', False):
                self.rect.x += getattr(riding, 'dx', 0)
                self.rect.y += getattr(riding, 'dy', 0)
            else:
                riding = None
            self.riding_platform = riding

        # --- Knockback: constant-deceleration kinematics (x = v0*t - a*t^2/2) ---
        # A fresh hit (knocking_back = signed launch speed) starts a new slide.
        # The slide runs on its own clock, so movement code that resets
        # x_vel every frame can't cancel it.
        if self.knocking_back:
            self.kb_vel = float(self.knocking_back)
            self.kb_carry = 0.0
            self.knocking_back = 0

        kb_vel = getattr(self, "kb_vel", 0.0)
        base_x_vel = self.x_vel
        kb_px = 0
        if kb_vel:
            a = KNOCKBACK_DECEL_GROUND if getattr(self, "on_ground", False) else KNOCKBACK_DECEL_AIR
            speed = abs(kb_vel)
            sign = 1 if kb_vel > 0 else -1
            t_step = min(dt, speed / a)                 # stop exactly when v hits 0
            disp = speed * t_step - 0.5 * a * t_step ** 2
            new_speed = speed - a * t_step
            self.kb_vel = sign * new_speed if new_speed > 1e-6 else 0.0

            # keep sub-pixel remainder so slow tails still move correctly
            carry = getattr(self, "kb_carry", 0.0) + sign * disp
            kb_px = int(carry)
            self.kb_carry = carry - kb_px
            if not self.kb_vel:
                self.kb_carry = 0.0

            # x_vel carries the current knock velocity for the collision logic
            self.x_vel = base_x_vel + sign * speed

        x_vel = int(base_x_vel * dt) + kb_px
        y_vel = int(self.y_vel * dt)

        limit = 64
        if y_vel > limit:
            y_vel = limit

        if x_vel > limit:
            x_vel = limit

        if y_vel < -limit:
            y_vel = -limit

        if x_vel < -limit:
            x_vel = -limit

        if self.zone and y_vel > 200:
            self.y_vel = 200

        if self.type == "weapon" and self.name == 'arrow':
            # Angle comes from the real velocity (px/s). The old code used the clamped
            # px-per-frame move, which bends the angle on fast arrows and flips it to
            # vertical when int() rounds a slow x move down to 0.
            needed, turned = get_degree(self.x_vel, self.y_vel, self.degree)
            if not getattr(self, "_aimed", True) and (self.x_vel or self.y_vel):
                self.degree = int(needed)      # first frame: point straight along the shot
                self._aimed = True
            else:
                self.degree = int(turned)
        
        self.hit_wall = False

        # One broad-phase query for the whole path (start -> after x -> after y): the
        # bounding box of everything this move can touch.
        r = self.rect
        sweep = pygame.Rect(r.x + min(x_vel, 0), r.y + min(y_vel, 0),
                            r.width + abs(x_vel), r.height + abs(y_vel))
        blocks, rects = self.query_static(game.map, sweep)
        for plat in game.platforms:
            if plat.rect.colliderect(sweep):
                blocks.append(plat)
                rects.append(plat.rect)

        # ---- X axis: move, then push out of whatever we hit ----
        self.collide_x(x_vel, blocks, rects)

        if kb_vel:
            if self.hit_wall:
                # slammed into a wall: the slide ends
                self.kb_vel = 0.0
                self.kb_carry = 0.0
            else:
                self.x_vel = base_x_vel  # knock speed lives in kb_vel, not x_vel

        # ---- Y axis: same thing, using the x-corrected position ----
        self.on_ground = False
        self.riding_platform = None
        if not (self.name in PROJECTILES and getattr(self, "stuck", False)):
            self.collide_y(y_vel, blocks, rects, riding)

        # WORLD BOUNDARY RESOLUTIONS
        if self.nature == "entity":
            if self.rect.right > self.game.maxx:
                self.rect.right = self.game.maxx
                self.x_vel = 0
                self.hit_wall = True

            elif self.rect.x < self.game.minx:
                self.rect.x = self.game.minx
                self.x_vel = 0
                self.hit_wall = True
            
            if self.rect.top < self.game.miny:
                self.rect.top = self.game.miny
                self.y_vel = 0
                self.hit_head()
            
            if self.rect.bottom > self.game.maxy:
                if self.nature == "entity":
                    self.rect.x, self.rect.y = random.choice(getattr(self.game, "points", [(0, -64)])) # self.start_points
            
        if self.nature == "entity":
            if self.dead:
                self.decelerate()
        
        if self.nature == "entity" or self.name in ["bomb", "fire"]:
            zones, _ = self.query_static(game.zones_map, self.rect)
            self.zone = zones[0] if zones else None      # first zone we overlap
          
        if not self.on_ground and self.y_vel > 0:
            self.fall_count += dt

        # Update hit wall status
        if not self.on_ground:
            self.in_air_for += dt
        else:
            self.in_air_for = 0

        # Update hit wall status
        if self.on_ground or round(self.in_air_for, 1) < 0.2:
            self.on_ground_for += dt
        else:
            self.on_ground_for = 0

        # Dash time bar: drain while dashing, refill by time otherwise (players in the story campaign only)
        if self.type == "player":
            _get_dash_bar().tick(game, self, dt)

        # Update hit wall status
        if self.hit_wall:
            self.hit_wall_for += dt
            self.dashing = False
        else:
            self.hit_wall_for = 0

    def collide_resting(self):
        """collide() for things that just sit on the ground (trees, decorations).

        Gravity pulls them down a pixel every frame and collide() snaps them straight back, which
        was ~70% of all collide() calls on a real level. When nothing can have changed since the
        last landing - same position and size, no velocity, resting on plain terrain (the map is
        static) - skip the work and leave the state exactly as collide() would have. Anything that
        moves, resizes or pushes the object makes the checks fail and the full collide() runs.
        """
        r = self.rect
        if (self._rest_static and getattr(self, "on_ground", False) and not self.x_vel
                and not self.knocking_back and not getattr(self, "kb_vel", 0.0)
                and (r.x, r.y, r.w, r.h) == self._rest_pos):
            self.y_vel = 0
            self.hit_wall = False
            self.stepping_on_platform = False
            self.on_ground_for += self.game.dt
            return
        self.collide()
        r = self.rect
        self._rest_pos = (r.x, r.y, r.w, r.h)

    def collide_x(self, dx, blocks, rects):
        """Move dx pixels along x, snapping against any block we run into.

        Which side we snap to comes from the direction we actually moved
        (dx), not from x_vel. If dx is 0 but we're overlapping something
        (a platform moved into us) we get pushed out the nearest side.
        """
        if not rects:                       # nothing within reach: just move
            self.rect.x += dx
            return False

        projectile = self.type == "weapon" and self.name in PROJECTILES

        for step in split_move(dx):
            self.rect.x += step
            hit = False

            for i in self.rect.collidelistall(rects):
                block = blocks[i]
                faces = block.outlines
                if FACE_LEFT not in faces and FACE_RIGHT not in faces:
                    continue
                if not self.rect.colliderect(block.rect):
                    continue

                if projectile:
                    self.stick(block)
                    hit = True
                    break                      # stuck at the surface, don't keep moving

                is_platform = block.type == "moving_platform"
                if is_platform and getattr(self, 'riding_platform', None) is block:
                    # standing on this platform: its own motion isn't a wall
                    continue

                going_right = step > 0 if step else self.rect.centerx < block.rect.centerx

                if going_right:
                    if FACE_LEFT not in faces:   # a neighbour covers that side
                        continue
                    self.rect.right = block.rect.left
                else:
                    if FACE_RIGHT not in faces:
                        continue
                    self.rect.left = block.rect.right

                if is_platform and (self.nature == "entity" or self.name in PROJECTILES):
                    self.stepping_on_platform = True

                self.x_vel = 0
                self.hit_wall = True
                hit = True

            if hit:
                break

        return self.hit_wall

    def collide_y(self, dy, blocks, rects, riding):
        """Move dy pixels along y, snapping to floors / ceilings (and platforms)."""
        if not rects:                       # nothing within reach: just move
            self.rect.y += dy
            return

        projectile = self.type == "weapon" and self.name in PROJECTILES

        for step in split_move(dy):
            self.rect.y += step
            hit = False

            for i in self.rect.collidelistall(rects):
                block = blocks[i]
                faces = block.outlines
                if FACE_UP not in faces and FACE_DOWN not in faces:
                    continue
                if not self.rect.colliderect(block.rect):
                    continue

                if projectile:
                    self.stick(block)
                    hit = True
                    break

                going_down = step > 0 if step else self.rect.centery < block.rect.centery

                if block.type == "moving_platform" and self.nature == "entity":
                    # Landing only counts if we were above the platform before
                    # this step; otherwise its side slid into us -> act like a wall.
                    came_from_above = (self.rect.bottom - step) <= block.rect.top + 8
                    if came_from_above or riding is block:
                        self.rect.bottom = block.rect.top
                        if self.y_vel > 0:
                            self.landing_impact()
                        self.riding_platform = block
                        self.stepping_on_platform = True
                        self.landed()
                    else:
                        if self.rect.centerx < block.rect.centerx:
                            self.rect.right = block.rect.left
                        else:
                            self.rect.left = block.rect.right
                        self.hit_wall = True
                    hit = True

                elif going_down:
                    if FACE_UP not in faces:
                        continue
                    self.rect.bottom = block.rect.top
                    if self.nature == "entity":
                        self.landing_impact()
                    self.landed()
                    self._rest_static = block.type == "block"
                    if (self.nature == "damageable_object" and block.type == "block"
                            and self.landed_on != block.rect.topleft):
                        self.landed_on = block.rect.topleft
                        self.game.damageable_objects_dirty = True
                    hit = True

                else:
                    if FACE_DOWN not in faces:
                        continue
                    self.rect.top = block.rect.bottom
                    self.y_vel = 0
                    self.hit_head()
                    hit = True

            if hit:
                break

    def landing_impact(self):
        """Sound, fall damage and screen shake for an entity touching down."""
        if self.fall_count > 0.3:
            _get_playit()("land", self)
        if self.fall_count > 0.7:
            self.health -= int(self.fall_count * 5)
        if self.type == "player":
            self.shake_frames = max(self.shake_frames, int(self.fall_count * 2))
            self.shake_intensity = max(self.shake_intensity, int(self.fall_count * 5))

    def collision_bounce(self, player, target, backfire=True, x=True, y=True):
        try:
            # Calculate normal vector
            normal_x = target.rect.x - player.rect.x
            normal_y = target.rect.y - player.rect.y
            length = math.sqrt(normal_x ** 2 + normal_y ** 2)

            try:
                normal_x /= length
            except:
                normal_x = 0
            try:
                normal_y /= length
            except:
                normal_y = 0

            # Calculate tangent vector
            tangent_x = -normal_y
            tangent_y = normal_x

            # Project velocities onto tangent and normal vectors
            v1n = player.x_vel * normal_x + player.y_vel * normal_y
            v1t = player.x_vel * tangent_x + player.y_vel * tangent_y
            v2n = target.x_vel * normal_x + target.y_vel * normal_y
            v2t = target.x_vel * tangent_x + target.y_vel * tangent_y

            # Perform collision
            v1n, v2n = v2n, v1n

            # Convert back to Cartesian coordinates
            if backfire:
                if x:
                    player.x_vel = v1n * normal_x + v1t * tangent_x
                if y:
                    player.y_vel = (v1n * normal_y + v1t * tangent_y) / 2.5
            if x:
                target.x_vel = v2n * normal_x + v2t * tangent_x
            if y:
                target.y_vel = (v2n * normal_y + v2t * tangent_y)

        except Exception as e:
            print(e)

    def calculate_direction(self, start_x, start_y, end_x, end_y):
        # Calculate the direction vector
        direction_x = end_x - start_x
        direction_y = end_y - start_y
        # Normalize the direction vector
        magnitude = math.sqrt(direction_x ** 2 + direction_y ** 2)
        if magnitude != 0:
            direction_x /= magnitude
            direction_y /= magnitude
        return direction_x, direction_y

    def rect_collision(self, rect1, rect2):
        """Detects collision between two rectangles."""
        return rect1.colliderect(rect2)

    def pathfinding_decision(self, obstacles):
        pass

    def check_jump(self, dx, dy, objects=None):
        pass

    def check_fall(self, dx, dy, objects=None):
        pass

    def move(self, dx, dy, objects=None):
        pass

    def accelerate(self):
        self.x_vel = min(self.x_vel + self.acceleration, self.max_vel)

    def decelerate(self, cap=0):
        if not cap:
            cap = self.speed
        if self.x_vel > 0:
            self.x_vel = max(self.x_vel - self.acceleration, 0)
        elif self.x_vel < 0:
            self.x_vel = min(self.x_vel + self.acceleration, 0)

    def make_hit(self):
        self.hit = True

    def move_left(self, vel):
        self.x_vel = -vel 
        self.x_vel *= (1 if not getattr(self, "dashing", False) else 1.5)
        if self.direction != "left" and not self.attacking:
            self.direction = "left"
            self.animation_count = 0

    def move_right(self, vel):
        self.x_vel = vel * (1 if not getattr(self, "dashing", False) else 1.5)
        if self.direction != "right" and not self.attacking:
            self.direction = "right"
            self.animation_count = 0

    def jump(self, interval="single"):
        self.y_vel = self.current_jump * (1 if not getattr(self, "dashing", False) else 1.3)
        
        self.jump_count += 1
        if self.jump_count == 1:
            self.fall_count = 0
        self.on_ground = False

    def swim_up(self):
        self.y_vel = -self.swim_strength * (0.3 if not getattr(self, "dashing", False) else 0.6)
        self.jump_count = 0

    def swim_down(self):
        self.y_vel = self.swim_strength * (0.3 if not getattr(self, "dashing", False) else 0.6)

    def landed(self):
        self.fall_count = 0
        self.y_vel = 0
        self.jump_count = 0
        self.on_ground = True

    def hit_head(self):
        self.fall_count = 0
        self.y_vel *= -1
        self.bumped_head = True

    def in_proximity(self, target):
        if (
                target.rect.top < self.eye_range.bottom and 
                target.rect.bottom > self.eye_range.top) and (
                self.eye_range.left < target.rect.centerx < self.eye_range.right
            ):
            return True
        return False
    
    def get_nearest(self, target_list, target_list2, times=1):
        my_target = None
        found = False

        # Find the target with the minimum distance using Euclidean distance
        min_distance = 2000

        # Everything the loop needs is read once. The checks below have no side effects, so they
        # run cheapest-first: the range test (in_proximity, inlined) then the team / alive tests.
        eye = self.eye_range
        top, bottom, left, right = eye.top, eye.bottom, eye.left, eye.right
        my_type = self.type
        my_id = self.entity_id
        decide_kill = self.decide_kill
        my_x, my_y = self.rect.centerx, self.rect.centery

        for target in target_list:
            rect = target.rect

            # within vertical and horizontal range? (same test as in_proximity)
            if not (rect.top < bottom and rect.bottom > top and left < rect.centerx < right):
                continue

            if my_type == target.type:
                if target.nature == 'entity':
                    if my_id == target.entity_id or target.death or target.dead:
                        continue  # Skip self as target

            elif target.death or target.dead:
                continue

            if times == 1 and not decide_kill(target):
                continue

            found = True

            # Calculate Euclidean distance between self and the target
            dist = find_distance(rect.centerx, rect.centery, my_x, my_y)[0]

            if abs(dist) < min_distance:
                min_distance = dist
                my_target = target

        # If no targets are found in range
        if not found:
            if times == 1 and target_list2:
                self.get_nearest(target_list2, [], 2)
            """else:
                self.has_target = False
                self.target = None
            """
            return
        
        # Assign the nearest target if one is found
        if my_target and not my_target.dead and not my_target.death:
            if self.avenger:
                # If the current target is not dead, don't switch to the new nearest target
                if not self.target.death or self.target.dead:
                    return
                
            self.has_target = True
            self.target = my_target
        else:
            self.has_target = False
            self.target = None

    def knockback(self, dir_="none", target=None):
        
        if not target:
            target = self.target

        # combat_fx: crits and finishers set a one-shot shove multiplier
        power = self.knockback_power * getattr(self, "fx_knock_mult", 1.0)
        self.fx_knock_mult = 1.0

        if dir_ not in ['left', 'right']:
            if target.rect.centerx > self.rect.centerx:
                target.knocking_back = power # push right

            elif target.rect.centerx < self.rect.centerx:
                target.knocking_back = -power # push left

            
            # print(self.name, self.knockback_power, " : ", target.title, target.knocking_back)
            return
        
        if dir_ == 'left':
            target.knocking_back = -power
        elif dir_ == 'right':
            target.knocking_back = power

        
