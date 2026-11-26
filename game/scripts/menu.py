import random
import pygame
import math

from ..settings import Settings
from .physics import distance


# --- Palette (shared with ui/ui_theme.py) ---
from ..ui import ui_theme as ui

BTN_TOP = (92, 42, 54)
BTN_BOTTOM = (44, 24, 33)
BTN_TOP_HOT = (150, 62, 66)
BTN_BOTTOM_HOT = (82, 36, 46)
BTN_BORDER = (112, 64, 66)
SPARK_COLORS = (ui.GOLD, ui.CORAL, ui.CREAM, (255, 160, 90))


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def _lerp(a, b, t):
    return a + (b - a) * t


def _lerp_col(c1, c2, t):
    return tuple(int(_lerp(a, b, t)) for a, b in zip(c1, c2))


def _ease_out_back(t, s=1.4):
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def _ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def _pretty(label):
    """'game_info' -> 'GAME INFO' (keeps already-nice labels as they are)."""
    return str(label).replace("_", " ").upper()


_BODY_CACHE = {}
_MASK_CACHE = {}
_SHADOW_CACHE = {}


def _round_mask(size, radius):
    key = (size, radius)
    m = _MASK_CACHE.get(key)
    if m is None:
        m = pygame.Surface(size, pygame.SRCALPHA)
        m.fill((255, 255, 255, 0))
        pygame.draw.rect(m, (255, 255, 255, 255), m.get_rect(), border_radius=radius)
        _MASK_CACHE[key] = m
    return m


def _button_body(size, heat, radius, base=None, accent=None):
    """Gradient body with a glossy top edge, cached by (size, heat bucket, tint)."""
    hb = int(round(_clamp(heat) * 8))
    base = tuple(base[:3]) if base else BTN_TOP
    accent = tuple(accent[:3]) if accent else ui.CORAL
    key = (size, hb, radius, base, accent)
    img = _BODY_CACHE.get(key)
    if img is None:
        h = hb / 8.0
        if base == BTN_TOP:
            top = _lerp_col(BTN_TOP, BTN_TOP_HOT, h)
            bot = _lerp_col(BTN_BOTTOM, BTN_BOTTOM_HOT, h)
        else:                                   # custom tint (e.g. level editor mode button)
            hot = tuple(min(255, int(c * 1.5 + 20)) for c in base)
            top = _lerp_col(base, hot, h)
            bot = _lerp_col(tuple(int(c * 0.5) for c in base), base, h)
        w, ht = size
        img = pygame.Surface(size, pygame.SRCALPHA)
        for y in range(ht):
            c = _lerp_col(top, bot, y / max(1, ht - 1))
            pygame.draw.line(img, (*c, 255), (0, y), (w, y))
        # glossy upper half
        gloss = pygame.Surface((w, max(1, ht // 2)), pygame.SRCALPHA)
        gloss.fill((255, 240, 210, 18 + int(18 * h)))
        img.blit(gloss, (0, 0))
        pygame.draw.line(img, (*ui.CREAM, 70 + int(60 * h)), (radius, 1), (w - radius, 1))
        img.blit(_round_mask(size, radius), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        border = _lerp_col(BTN_BORDER, accent, h)
        pygame.draw.rect(img, (*border, 255), img.get_rect(), width=2, border_radius=radius)
        _BODY_CACHE[key] = img
        if len(_BODY_CACHE) > 160:
            _BODY_CACHE.clear()
    return img


def _drop_shadow(size, radius):
    key = (size, radius)
    img = _SHADOW_CACHE.get(key)
    if img is None:
        w, h = size
        img = pygame.Surface((w + 16, h + 16), pygame.SRCALPHA)
        for i in range(4):
            pygame.draw.rect(img, (8, 5, 12, 34), pygame.Rect(i * 2, i * 2, w + 16 - i * 4, h + 16 - i * 4),
                             border_radius=radius + 8 - i * 2)
        _SHADOW_CACHE[key] = img
        if len(_SHADOW_CACHE) > 80:
            _SHADOW_CACHE.clear()
    return img


def _ui_tick(volume=0.5):
    """Tiny hover/select click, routed through its own channel so it never
    changes the shared Sound volume used in game."""
    try:
        from ..assets import Assets
        snd = Assets.SOUNDS.get("tick") if hasattr(Assets, "SOUNDS") else None
        v = Settings.IN_GAME_SOUNDS_VOLUME * volume
        if snd is None or v <= 0:
            return
        ch = pygame.mixer.find_channel()
        if ch:
            ch.set_volume(v)
            ch.play(snd)
    except Exception:
        pass


# --- Particle Effect (palette sparks with a bit of gravity) ---
class Particle:
    def __init__(self, pos):
        self.pos = list(pos)
        ang = random.uniform(0, math.tau)
        spd = random.uniform(1.5, 5.5)
        self.vel = [math.cos(ang) * spd, math.sin(ang) * spd - 1.5]
        self.life = random.randint(22, 38)
        self.max_life = self.life
        self.color = random.choice(SPARK_COLORS)
        self.size = random.uniform(2, 4.5)

    def update(self):
        self.pos[0] += self.vel[0]
        self.pos[1] += self.vel[1]
        self.vel[0] *= 0.94
        self.vel[1] = self.vel[1] * 0.94 + 0.22
        self.life -= 1

    def draw(self, screen):
        if self.life <= 0:
            return
        k = self.life / self.max_life
        r = max(1, int(self.size * k + 0.5))
        x, y = int(self.pos[0]), int(self.pos[1])
        glow = int(r * 2.6)
        g = pygame.Surface((glow * 2, glow * 2))
        g.fill((0, 0, 0))
        pygame.draw.circle(g, tuple(int(c * 0.35 * k) for c in self.color), (glow, glow), glow)
        screen.blit(g, (x - glow, y - glow), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(screen, self.color, (x, y), r)


# --- RPG Button ---
class RPGButton:
    INTRO_TIME = 0.55      # seconds for the slide-in
    STAGGER = 0.06         # delay between consecutive buttons

    def __init__(self, text, font, screen, rel_rect, callback=None, args=None, index=0):
        self.text = text
        self.label = _pretty(text)
        self.args = args
        self.font = font
        self.screen = screen
        self.callback = callback
        self.index = index

        self.rel_rect = rel_rect
        sw, sh = screen.get_size()
        self._layout_size = (sw, sh)
        self.target_rect = self._rect_for(sw, sh)

        self.rect = self.target_rect.copy()
        self.rect.x -= sw

        # kept for compatibility with older code poking at these
        self.glow_color = (*ui.CORAL, 100)
        self.color = BTN_TOP
        self.fade_speed = 5
        self.slide_speed = 20

        self.alpha = 0
        self.selected = False
        self.hovered = False
        self.pulse_time = 0
        self.visible = False

        self.born = pygame.time.get_ticks()
        self._last = self.born
        self.heat = 0.0            # 0 idle -> 1 hovered/selected (smoothed)
        self.press_t = 1.0         # 0 right after a press -> 1 settled
        self.shine = -1.0          # sweep position, <0 = idle
        self._text_cache = {}

    # ---------------------------------------------------------------- #
    def _rect_for(self, sw, sh):
        r = self.rel_rect
        return pygame.Rect(int(r[0] * sw), int(r[1] * sh), int(r[2] * sw), int(r[3] * sh))

    def _follow_surface(self):
        """The screen mode can change under a menu that is already built: re-fit the button to the new size."""
        size = self.screen.get_size()
        if size != self._layout_size:
            self._layout_size = size
            self.target_rect = self._rect_for(*size)
            self.rect = self.target_rect.copy()
            self._text_cache.clear()

    def update(self, mouse_pos, pos=(0, 0)):
        self._follow_surface()
        now = pygame.time.get_ticks()
        dt = min(0.1, (now - self._last) / 1000.0)
        self._last = now
        age = (now - self.born) / 1000.0 - self.index * self.STAGGER

        p = _clamp(age / self.INTRO_TIME)
        sw = self.screen.get_width()
        self.rect.y = self.target_rect.y
        self.rect.x = int(self.target_rect.x - (1 - _ease_out_back(p)) * sw * 0.35) if p < 1 else self.target_rect.x
        if not self.visible:
            # after the intro, alpha belongs to the caller (the editor dims buttons this way)
            self.alpha = int(255 * _ease_out_cubic(p))
            if p >= 1:
                self.alpha = 255
                self.visible = True

        rect = self.target_rect.copy()
        rect.x += pos[0]
        rect.y += pos[1]
        was = self.hovered or getattr(self, "_was_sel", False)
        self.hovered = rect.collidepoint(mouse_pos)
        self._was_sel = self.selected
        if (self.hovered or self.selected) and not was and self.shine < 0:
            self.shine = 0.0

        hot = 1.0 if (self.selected or self.hovered) else 0.0
        self.heat += (hot - self.heat) * min(1.0, dt * 12)
        self.press_t = min(1.0, self.press_t + dt * 4.5)
        if self.shine >= 0:
            self.shine += dt * 1.6
            if self.shine > 1.4:
                self.shine = -1.0 if not (self.selected or self.hovered) else -0.6
        elif hot and self.shine < -0.05:
            # re-trigger the sweep every ~2.5s while focused
            self.shine += dt * 0.25
            if self.shine >= -0.05:
                self.shine = 0.0
        self.pulse_time += dt * 3

    def _text(self, color):
        if self.text != getattr(self, "_label_src", None):
            self._label_src = self.text
            self.label = _pretty(self.text)
        key = (self.label, color)
        surf = self._text_cache.get(key)
        if surf is None:
            surf = self.font.render(self.label, True, color)
            # small windows (800x600): shrink a label that would spill out of its button
            tw, th = surf.get_size()
            bw, bh = self.target_rect.size
            k = min(1.0, bw * 0.9 / max(1, tw), bh * 0.8 / max(1, th))
            if k < 1.0:
                surf = pygame.transform.smoothscale(surf, (max(1, int(tw * k)), max(1, int(th * k))))
            if len(self._text_cache) > 12:
                self._text_cache.clear()
            self._text_cache[key] = surf
        return surf

    def draw(self):
        if self.alpha <= 0:
            return
        h = self.heat
        breathe = 0.012 * math.sin(self.pulse_time * 2) * h
        press = 1 - 0.07 * (1 - _ease_out_cubic(self.press_t))
        scale = (1 + 0.018 * h + breathe) * press

        r = self.rect.copy()
        r.inflate_ip(int(r.width * (scale - 1)), int(r.height * (scale - 1)))
        r.center = (self.rect.centerx, self.rect.centery - int(2 * h))
        if r.width < 8 or r.height < 8:
            return
        radius = max(6, min(14, r.height // 3))

        # layer: drop shadow -> outer glow -> body -> shine -> text
        shadow = _drop_shadow(r.size, radius)
        shadow.set_alpha(int(self.alpha * (0.52 + 0.16 * h)))
        self.screen.blit(shadow, (r.x - 8, r.y - 8 + 4 + int(3 * h)))

        if h > 0.02:
            for grow, a in ((6, 18), (3, 42)):
                g = r.inflate(grow * 2, grow * 2)
                gs = pygame.Surface(g.size, pygame.SRCALPHA)
                pygame.draw.rect(gs, (*self.glow_color[:3], int(a * h * self.alpha / 255)), gs.get_rect(),
                                 width=2, border_radius=radius + grow)
                self.screen.blit(gs, g.topleft)

        custom = self.color if tuple(self.color[:3]) != BTN_TOP else None
        accent = self.glow_color if tuple(self.glow_color[:3]) != ui.CORAL else None
        body = _button_body(r.size, h, radius, custom, accent)
        if self.shine >= 0 or self.alpha < 255:
            body = body.copy()
            if self.shine >= 0:
                bw, bh = r.size
                x = int(-bh + (bw + bh * 2) * self.shine)
                band = pygame.Surface(r.size, pygame.SRCALPHA)
                pygame.draw.polygon(band, (255, 240, 210, 46),
                                    [(x, 0), (x + bh * 0.6, 0), (x + bh * 0.6 - bh, bh), (x - bh, bh)])
                pygame.draw.polygon(band, (255, 240, 210, 26),
                                    [(x + bh * 0.8, 0), (x + bh * 1.0, 0), (x, bh), (x - bh * 0.2, bh)])
                band.blit(_round_mask(r.size, radius), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                body.blit(band, (0, 0))
            if self.alpha < 255:
                body.set_alpha(self.alpha)
        self.screen.blit(body, r.topleft)

        # focus markers: little pulsing embers either side of the label
        txt_col = _lerp_col(ui.WHITE, ui.CREAM, h)
        text_surf = self._text(txt_col)
        tr = text_surf.get_rect(center=r.center)
        # Compact site badges keep external links visually obvious without
        # adding a second links panel to the start screen.
        if self.label.startswith(("GH ", "FB ", "LP ", "PX ")):
            badge = self.label[:2]
            badge_rect = pygame.Rect(r.left + 10, r.centery - 13, 26, 26)
            badge_colors = {"GH": (35, 35, 45), "FB": (55, 105, 190),
                            "LP": (210, 125, 55), "PX": (150, 65, 125)}
            pygame.draw.circle(self.screen, badge_colors.get(badge, ui.CORAL),
                               badge_rect.center, 13)
            icon = self.font.render(badge, True, ui.WHITE)
            self.screen.blit(icon, icon.get_rect(center=badge_rect.center))
            tr.centerx += 16
        if h > 0.15:
            d = 4 + int(2 * math.sin(self.pulse_time * 3))
            gap = 10 + int(6 * (1 - h))
            for cx in (tr.left - gap - d, tr.right + gap + d):
                cy = r.centery
                pts = [(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)]
                if r.left + 4 < cx < r.right - 4:
                    pygame.draw.polygon(self.screen, ui.GOLD, pts)

        shadow_txt = self._text(ui.INK)
        if self.alpha < 255:
            shadow_txt = shadow_txt.copy()
            shadow_txt.set_alpha(self.alpha)
            text_surf = text_surf.copy()
            text_surf.set_alpha(self.alpha)
        self.screen.blit(shadow_txt, (tr.x + 2, tr.y + 2))
        self.screen.blit(text_surf, tr)

    def press(self):
        self.press_t = 0.0
        self.shine = 0.0
        _ui_tick(0.9)
        if self.callback:
            if self.args:
                self.callback(*self.args)
            else:
                self.callback()


# --- RPG Menu ---
class RPGMenu:
    def __init__(self, screen, font, button_data, layout):
        self.screen = screen
        self.font = font
        self.buttons = []
        self.selected_index = 0
        self.particles = []
        self.excluded = {}
        self.born = pygame.time.get_ticks()
        self._last_sel = 0
        self.add(button_data, layout)
        
        if not self.buttons:
            return
        
        self.buttons[self.selected_index].selected = True

    def add(self, button_data, layout):
        for i, ((text, callback, args), rel_rect) in enumerate(zip(button_data, layout)):
            btn = RPGButton(text, self.font, self.screen, rel_rect, callback, args=args,
                            index=len(self.buttons))
            self.buttons.append(btn)

    def exclude(self, btns):
        if isinstance(btns, list):
            for btn_dat in btns:
                id_, pass_ = btn_dat
                if id_ not in self.excluded:
                    if pass_:
                        btn = self.buttons[id_]
                        self.excluded[id_] = (self.buttons.index(btn), btn)
                else:
                    if not pass_:
                        del self.excluded[id_]
                    
        else:
            id_, pass_ = btns
            if id_ not in self.excluded:
                if pass_:
                    btn = self.buttons[id_]
                    self.excluded[id_] = (self.buttons.index(btn), btn)
            else:
                if not pass_:
                    del self.excluded[id_]
                
                        
    def update(self, mouse_pos, pos=(0, 0)):
        for i, btn in enumerate(self.buttons):
            if (i, btn) in self.excluded.values():
                continue
            btn.update(mouse_pos, pos)  # PUT FINGER SUPPORT LATER
            if btn.hovered:
                self.buttons[self.selected_index].selected = False
                self.selected_index = i
                btn.selected = True

        for p in self.particles:
            p.update()

        self.particles = [p for p in self.particles if p.life > 0]

        if self.buttons and self.selected_index != self._last_sel:
            self._last_sel = self.selected_index
            _ui_tick(0.35)

    def age(self):
        """Seconds since this menu was built (used for screen fade-ins)."""
        return (pygame.time.get_ticks() - self.born) / 1000.0

    def draw(self):
        for index, btn in enumerate(self.buttons):
            if (index, btn) in self.excluded.values():
                continue
            btn.draw()

        for p in self.particles:
            p.draw(self.screen)

    def handle_dir(self, right=False, left=False, top=False, bottom=False):
        selected = self.buttons[self.selected_index]
        near = self.selected_index
        min_ = float('inf')
        min_2 = float('inf')
        for i, btn in enumerate(self.buttons):
            if i in self.excluded.keys():
                btn.selected = False
                continue
            if btn == selected:
                continue
            
            # If pressed right
            if right:
                if btn.rect.x > selected.rect.x:
                    current_min = abs(distance(selected.rect.right, selected.rect.y, btn.rect.x, btn.rect.y))
                    if current_min < min_:
                        min_ = current_min
                        near = i

            # If pressed left
            elif left:
                if btn.rect.x < selected.rect.x:
                    current_min = abs(distance(selected.rect.x, selected.rect.y, btn.rect.right, btn.rect.y))
                    if current_min < min_:
                        min_ = current_min
                        near = i

            # If pressed bottom
            elif bottom:
                if btn.rect.y > selected.rect.y:
                    current_min = abs(distance(selected.rect.bottom, selected.rect.y, btn.rect.x, btn.rect.x))
                    if current_min < min_:
                        min_ = current_min
                        near = i
            
            # If pressed top
            elif top:
                if btn.rect.y < selected.rect.y:
                    current_min = abs(distance(selected.rect.x, selected.rect.y, btn.rect.x, btn.rect.bottom))
                    if current_min < min_:
                        min_ = current_min
                        near = i

        self.selected_index = near
        
    def handle_joy(self, event, type_="button"):
        if not self.buttons or len(self.excluded.keys()) == len(self.buttons):
            return  
        self.buttons[self.selected_index].selected = False
        
        if type_ == "axis":
            top = int(event.value) < -0.75 and event.axis == 1
            bottom = round(event.value) > 0.75 and event.axis == 1
            left = int(event.value) < -0.75 and event.axis == 0
            right = round(event.value) > 0.75 and event.axis == 0
            
            self.handle_dir(right, left, top, bottom)
                    
        if type_ == "button":
            if event.button == 2:
                self.buttons[self.selected_index].press()
                self.spawn_particles(self.buttons[self.selected_index].rect.center)

        self.buttons[self.selected_index].selected = True
            
    def handle_key(self, key, id_='None'):
        if not self.buttons or len(self.excluded.keys()) == len(self.buttons):
            return  
        
        self.buttons[self.selected_index].selected = False
        
        bottom = (key == pygame.K_DOWN and id_ == 0) or (key == pygame.K_s and id_ == 1) or (
                (key == pygame.K_DOWN or key == pygame.K_s) and id_ == 'None')
        
        top = (key == pygame.K_UP and id_ == 0) or (key == pygame.K_w and id_ == 1) or (
                (key == pygame.K_UP or key == pygame.K_w) and id_ == 'None')
        
        right = (key == pygame.K_RIGHT and id_ == 0) or (key == pygame.K_d and id_ == 1) or (
                (key == pygame.K_RIGHT or key == pygame.K_d) and id_ == 'None')
        
        left = (key == pygame.K_LEFT and id_ == 0) or (key == pygame.K_a and id_ == 1) or (
                (key == pygame.K_LEFT or key == pygame.K_a) and id_ == 'None')
        
        self.handle_dir(right, left, top, bottom)

        if (key == pygame.K_RETURN and id_ == 0) or (key == pygame.K_f and id_ == 1) or (
                (key == pygame.K_RETURN or key == pygame.K_f) and id_ == 'None'):
            self.buttons[self.selected_index].press()
            self.spawn_particles(self.buttons[self.selected_index].rect.center)
        
        self.buttons[self.selected_index].selected = True

    def handle_mouse(self, event, pos=(0, 0), id_=0):
        if event.type == pygame.FINGERDOWN:
            event_pos = (event.x * Settings.WIDTH, event.y * Settings.HEIGHT)
            for index, btn in enumerate(self.buttons):
                if (index, btn) in self.excluded.values():
                    continue
                # THIS IS FOR SPLIT SCREENS (CHANGING TOPLEFT VALUE)
                rect = btn.rect.copy()
                rect.x += pos[0]
                rect.y += pos[1]
                if rect.collidepoint(event_pos):
                    btn.press()
                    self.spawn_particles(btn.rect.center)
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            for index, btn in enumerate(self.buttons):
                if (index, btn) in self.excluded.values():
                    continue
                # THIS IS FOR SPLIT SCREENS (CHANGING TOPLEFT VALUE)
                rect = btn.rect.copy()
                rect.x += pos[0]
                rect.y += pos[1]
                if rect.collidepoint(event.pos):
                    btn.press()
                    self.spawn_particles(btn.rect.center)

    def spawn_particles(self, center):
        for _ in range(20):
            self.particles.append(Particle(center))

