"""
camera.py
=========
A camera that feels like a camera (WS-F). One ``Camera`` lives on each local
player (``player.camera``); ``Player.camera_update()`` is a thin wrapper that
calls ``Camera.update()`` and keeps the old name / signature.

Behaviour (``Settings.CAMERA_MODE == "smooth"``; ``"classic"`` is the old
hard lock to the player centre):

* dead-zone     the player can drift inside a small box without the camera
                moving; the box closes once they stand still, so the camera
                re-centres (~0.5 s) instead of staying off-centre
* smooth follow frame-rate independent exponential chase, X faster than Y so
                jumps don't make the screen bob
* look-ahead    the camera leads in the direction of travel, then eases back
* vertical      falling pulls the view down, standing nudges it up, holding
                DOWN / UP for 0.6 s peeks
* landing kick  a small dip after a hard landing that settles
* zoom          ``zoom_mult`` (speed / dash / crowds) multiplies the player's
                ``target_zoom``; the zoom itself is quantised in controls.py
                so the zoom-keyed sprite caches don't thrash
* focus         ``focus(target, weight, duration, zoom)`` pulls the camera
                toward an entity or point (charm targeting, boss intros,
                exit reveal ...); ``clear_focus()`` lets go
* snap          a big one-frame jump (teleport, level start) snaps the camera
                instead of smearing across the level
* whip          ``whip()`` (armed by warp doors) turns that jump into a fast eased pan

Smoothing uses REAL time (pygame ticks), never the slow-mo scaled ``game.dt``,
so the camera does not turn to jelly while time is slowed.

Shake is NOT handled here: the existing ``shake_frames / shake_intensity``
system (combat_fx, game.apply_shake) still owns it and is applied on top of
the rect this class writes.
"""

import math

import pygame

from ..settings import Settings

# tunables (fractions of the view size unless noted)
DEAD_X, DEAD_Y = 0.03, 0.09          # half-size of the dead-zone box
FOLLOW_X, FOLLOW_Y = 8.0, 3.8        # chase speeds (1/s)
LOOK_X = 0.25                        # max look-ahead
LOOK_GAIN = 0.5                      # seconds of travel the camera leads by
LOOK_IN, LOOK_OUT = 3.0, 6.0         # easing speeds when moving / when stopped
SAFE_X, SAFE_Y = 0.32, 0.30          # the player is never allowed further than this from centre
FALL_FOLLOW_Y = 9.0                  # vertical chase speed while falling fast
FALL_SPEED = 380.0                   # px/s that counts as "falling"
PEEK_TIME = 0.6
PEEK_AMOUNT = 0.30
SNAP_DISTANCE = 700.0                # a one-update jump this big snaps the camera
IDLE_SPEED = 25.0                    # px/s under which the player counts as standing still
WHIP_SPEED = 24.0                    # chase speed during a door whip-pan (1/s)
ZOOM_MIN_MULT = 0.9                  # most the speed / combat zoom-out may take


def _ease(current, target, dt, speed):
    """Frame-rate independent chase (same maths as ui_fx.smooth_to, without the snap)."""
    return current + (target - current) * (1.0 - math.exp(-speed * dt))


class Camera:
    def __init__(self, owner):
        self.owner = owner
        self.cx = self.cy = None          # smoothed centre (float world px); None = not placed yet
        self.look_x = self.look_y = 0.0
        self.vx = self.vy = 0.0           # smoothed velocity estimate (px/s)
        self.dead_scale = 1.0             # 1 = dead-zone open (moving), 0 = closed (standing)
        self.idle_for = 0.0
        self.peek = 0.0
        self.peek_hold = 0.0
        self.kick = 0.0
        self.zoom_mult = 1.0
        self._last_center = None
        self._last_tick = None
        self._was_grounded = True
        self._peak_fall = 0.0
        self._level_key = None
        # focus request
        self._focus = None
        self._focus_weight = 0.0
        self._focus_left = None
        self._focus_zoom = None
        self._focus_blend = 0.0
        self._whip_t = 0.0                # > 0: a door just moved the player far away -> pan there fast instead of snapping

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def focus(self, target, weight=1.0, duration=None, zoom=None):
        """Pull the camera toward ``target`` (an entity with ``.rect`` or an (x, y) point).

        weight   0..1, how much of the way (1 = fully on the target)
        duration seconds of REAL time, or None to hold until ``clear_focus()``
        zoom     optional zoom multiplier while focused (>1 = closer)
        """
        self._focus = target
        self._focus_weight = max(0.0, min(1.0, weight))
        self._focus_left = duration
        self._focus_zoom = zoom

    def clear_focus(self):
        self._focus = None
        self._focus_left = None
        self._focus_zoom = None

    def whip(self, duration=0.3):
        """Armed by warp doors just before they move the player: the next big position jump becomes a
        very fast eased pan (the camera sweeps to the destination) instead of a hard snap."""
        self._whip_t = duration

    def snap(self):
        """Forget the smoothing: the next update puts the camera exactly on its goal."""
        self.cx = self.cy = None
        self.look_x = self.look_y = 0.0
        self.vx = self.vy = 0.0
        self.kick = 0.0
        self._last_center = None

    # ------------------------------------------------------------------ #
    def _focus_point(self):
        t = self._focus
        if t is None:
            return None
        if hasattr(t, "rect"):
            return t.rect.center
        try:
            return float(t[0]), float(t[1])
        except Exception:
            return None

    def _keys_down(self):
        """(up, down) held by this player's own keyboard scheme."""
        p = self.owner
        game = p.game
        try:
            if getattr(p, "control_type", "keyboard") != "keyboard":
                return False, False
            keys = game.keys
            if getattr(p, "keyboard_num", 0) == 1:
                return keys[pygame.K_w], keys[pygame.K_s]
            return keys[pygame.K_UP], keys[pygame.K_DOWN]
        except Exception:
            return False, False

    def _clamp_center(self, x, y, cam_w, cam_h):
        game = self.owner.game
        minx, maxx, miny, maxy = game.minx, game.maxx, game.miny, game.maxy
        if cam_w >= maxx - minx:
            x = (minx + maxx) / 2          # level narrower than the view: centre it
        else:
            x = max(minx + cam_w / 2, min(maxx - cam_w / 2, x))
        if cam_h >= maxy - miny:
            y = (miny + maxy) / 2
        else:
            y = max(miny + cam_h / 2, min(maxy - cam_h / 2, y))
        return x, y

    # ------------------------------------------------------------------ #
    def update(self):
        p = self.owner
        cam = p.cam_rect
        cam_w, cam_h = cam.size
        px, py = p.rect.center

        now = pygame.time.get_ticks()
        dt = 0.0 if self._last_tick is None else (now - self._last_tick) / 1000.0
        self._last_tick = now
        dt = max(0.0, min(0.05, dt))

        # ----- classic (or a screen with no world bounds): the old hard lock -----
        if getattr(Settings, "CAMERA_MODE", "smooth") != "smooth" or not hasattr(p.game, "maxx"):
            self.snap()
            self.zoom_mult = 1.0
            cam.center = (px, py)
            self._clamp_rect(cam)
            return

        # ----- level change / first frame / teleport: snap, never sweep -----
        level_key = None
        try:
            level_key = p.game.level_key()
        except Exception:
            pass
        jumped = (self._last_center is not None and
                  math.hypot(px - self._last_center[0], py - self._last_center[1]) > SNAP_DISTANCE)
        if jumped and self._whip_t > 0 and self.cx is not None and level_key == self._level_key:
            jumped = False                                # whip pan: keep the old centre and race to the new one
            self.vx = self.vy = self.look_x = self.look_y = 0.0
            self._last_center = (px, py)
            self.idle_for = 0.0
        if self._whip_t > 0:
            self._whip_t = max(0.0, self._whip_t - dt)
        if self.cx is None or level_key != self._level_key or jumped:
            self._level_key = level_key
            self.cx, self.cy = float(px), float(py)
            self.look_x = self.look_y = self.vx = self.vy = self.kick = 0.0
            self._last_center = (px, py)
            self._was_grounded = bool(getattr(p, "on_ground", True))
            self._peak_fall = 0.0
            dt = 0.0

        # ----- velocity from real movement (works for dashes, knockback, platforms) -----
        if dt > 0.004:
            raw_vx = (px - self._last_center[0]) / dt
            raw_vy = (py - self._last_center[1]) / dt
            self.vx = _ease(self.vx, raw_vx, dt, 12.0)
            self.vy = _ease(self.vy, raw_vy, dt, 12.0)
            self._last_center = (px, py)
        speed = math.hypot(self.vx, self.vy)

        # ----- standing still closes the dead-zone so the view re-centres -----
        if dt > 0.0:
            if speed < IDLE_SPEED:
                self.idle_for += dt
            else:
                self.idle_for = 0.0
            self.dead_scale = _ease(self.dead_scale, 0.0 if self.idle_for > 0.15 else 1.0, dt, 9.0)

        # ----- look-ahead -----
        if dt > 0.0:
            want_x = max(-LOOK_X * cam_w, min(LOOK_X * cam_w, self.vx * LOOK_GAIN))
            moving = abs(self.vx) > IDLE_SPEED
            self.look_x = _ease(self.look_x, want_x if moving else 0.0, dt, LOOK_IN if moving else LOOK_OUT)

            # ----- vertical bias, peek, landing kick -----
            grounded = bool(getattr(p, "on_ground", False))
            if self.vy > FALL_SPEED:
                want_y = min(0.22 * cam_h, self.vy * 0.18)
            elif grounded:
                want_y = -0.04 * cam_h
            else:
                want_y = 0.0
            up, down = self._keys_down()
            if grounded and speed < IDLE_SPEED and (up or down):
                self.peek_hold += dt
            else:
                self.peek_hold = 0.0
            peek_target = 0.0
            if self.peek_hold >= PEEK_TIME:
                peek_target = PEEK_AMOUNT * cam_h * (1 if down else -1)
            self.peek = _ease(self.peek, peek_target, dt, 5.0)
            self.look_y = _ease(self.look_y, want_y, dt, 4.0)

            if not grounded:
                self._peak_fall = max(self._peak_fall, self.vy)
            if grounded and not self._was_grounded:
                if self._peak_fall > 750:
                    self.kick = min(0.05 * cam_h, self._peak_fall * 0.03)
                self._peak_fall = 0.0
            self._was_grounded = grounded
            self.kick = _ease(self.kick, 0.0, dt, 9.0)

        # ----- goal: the camera may rest anywhere inside a dead-zone box around the look target -----
        # (target = player + look-ahead / vertical bias; the box closes when standing, so it re-centres)
        tx = px + self.look_x
        ty = py + self.look_y + self.peek + self.kick
        dzx, dzy = DEAD_X * cam_w * self.dead_scale, DEAD_Y * cam_h * self.dead_scale
        goal_x = max(tx - dzx, min(tx + dzx, self.cx))
        goal_y = max(ty - dzy, min(ty + dzy, self.cy))

        # ----- focus request: blend toward the target -----
        fp = self._focus_point()
        want_blend = self._focus_weight if fp is not None else 0.0
        if dt > 0.0:
            self._focus_blend = _ease(self._focus_blend, want_blend, dt, 5.0)
            if self._focus is not None and self._focus_left is not None:
                self._focus_left -= dt
                if self._focus_left <= 0:
                    self.clear_focus()
        if fp is not None and self._focus_blend > 0.001:
            b = self._focus_blend
            goal_x += (fp[0] - goal_x) * b
            goal_y += (fp[1] - goal_y) * b

        # ----- chase -----
        if dt > 0.0:
            if self._whip_t > 0:                          # the whip: both axes race to the destination
                self.cx = _ease(self.cx, goal_x, dt, WHIP_SPEED)
                self.cy = _ease(self.cy, goal_y, dt, WHIP_SPEED)
            else:
                self.cx = _ease(self.cx, goal_x, dt, FOLLOW_X)
                self.cy = _ease(self.cy, goal_y, dt, FALL_FOLLOW_Y if self.vy > FALL_SPEED else FOLLOW_Y)

        # the player may never leave the safe box (fast falls, dashes, knockback) - unless we are
        # deliberately looking elsewhere
        if self._focus_blend < 0.05 and self._whip_t <= 0:
            sx, sy = SAFE_X * cam_w, SAFE_Y * cam_h
            self.cx = max(px - sx, min(px + sx, self.cx))
            self.cy = max(py - sy, min(py + sy, self.cy))

        # keep the state inside the world so the camera does not "wind up" past an edge
        self.cx, self.cy = self._clamp_center(self.cx, self.cy, cam_w, cam_h)

        # ----- zoom multiplier (speed / dash / crowds), applied by controls.py -----
        if dt > 0.0:
            mult = 1.0 - min(0.07, max(0.0, speed - 350.0) / 4000.0)       # run / fall faster -> see more
            if getattr(p, "dashing", False):
                mult -= 0.04
            mult = max(ZOOM_MIN_MULT, mult)
            if fp is not None and self._focus_zoom and self._focus_blend > 0.3:
                mult *= self._focus_zoom                                    # focus zoom may exceed the limits
            self.zoom_mult = _ease(self.zoom_mult, mult, dt, 3.0)

        # ----- write the rect: round only the FINAL position (no sprite shimmer) -----
        cam.center = (round(self.cx), round(self.cy))
        self._clamp_rect(cam)

    def _clamp_rect(self, cam):
        game = self.owner.game
        if not hasattr(game, "maxx"):
            return
        if cam.width >= game.maxx - game.minx:
            cam.centerx = (game.minx + game.maxx) // 2
        else:
            cam.right = min(cam.right, game.maxx)
            cam.left = max(cam.left, game.minx)
        if cam.height >= game.maxy - game.miny:
            cam.centery = (game.miny + game.maxy) // 2
        else:
            cam.bottom = min(cam.bottom, game.maxy)
            cam.top = max(cam.top, game.miny)
