import pygame
import math
from os.path import join, exists

from ..assets import Assets
from ..settings import Settings
from .physics import distance
from .menu import RPGMenu
from .music import music

# ---------------------------------------------------------------------- #
# Volume screen helpers (palette from ui/ui_theme.py)
# ---------------------------------------------------------------------- #
CHANNEL_STYLE = {
    # mode        title        subtitle                 accent
    "Background": ("MUSIC", "Theme & ambience", (100, 170, 215)),
    "In Game": ("SOUND FX", "Hits, bombs, footsteps", (255, 112, 92)),
}


def _ui():
    from ..ui import ui_theme
    return ui_theme


def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def _lerp_col(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _alpha_rect(surface, rect, color, radius, width=0):
    if rect.width <= 0 or rect.height <= 0:
        return
    s = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(s, color, s.get_rect(), width=width, border_radius=radius)
    surface.blit(s, rect.topleft)


def _soft_glow(surface, center, color, radius, strength=0.6):
    radius = max(4, int(radius))
    img = pygame.Surface((radius * 2, radius * 2))
    img.fill((0, 0, 0))
    for i in range(12):
        t = i / 12
        c = tuple(int(ch * t * t * strength) for ch in color[:3])
        pygame.draw.circle(img, c, (radius, radius), max(1, int(radius * (1 - t))))
    surface.blit(img, (int(center[0]) - radius, int(center[1]) - radius), special_flags=pygame.BLEND_RGB_ADD)


def _speaker(surface, rect, color, level, muted, t):
    """Speaker glyph with 0-3 animated sound waves (or an X when muted)."""
    cx, cy = rect.center
    u = rect.height / 10.0
    body = [(cx - 4 * u, cy - 1.6 * u), (cx - 2.2 * u, cy - 1.6 * u), (cx + 0.2 * u, cy - 3.8 * u),
            (cx + 0.2 * u, cy + 3.8 * u), (cx - 2.2 * u, cy + 1.6 * u), (cx - 4 * u, cy + 1.6 * u)]
    pygame.draw.polygon(surface, color, body)
    if muted:
        w = max(2, int(u * 0.7))
        pygame.draw.line(surface, color, (cx + 1.6 * u, cy - 1.8 * u), (cx + 5 * u, cy + 1.8 * u), w)
        pygame.draw.line(surface, color, (cx + 5 * u, cy - 1.8 * u), (cx + 1.6 * u, cy + 1.8 * u), w)
        return
    waves = 0 if level <= 0.001 else 1 if level < 0.34 else 2 if level < 0.67 else 3
    for i in range(waves):
        r = (2.2 + i * 1.6) * u
        wob = 0.25 * u * math.sin(t * 6 + i)
        arc = pygame.Rect(0, 0, int((r + wob) * 2), int((r + wob) * 2))
        arc.center = (int(cx - 0.4 * u), cy)
        pygame.draw.arc(surface, color, arc, -0.85, 0.85, max(2, int(u * 0.55)))


# VOLUME SYS CLASS
class Volumes(Settings):
    """The SOUND settings screen: one palette-styled card per channel with a
    big draggable slider, live level meter and a mute switch."""

    KEY_STEP = 0.05

    def __init__(self, volumes, game):
        self.game = game
        self.volumes = volumes
        self.selected = None
        self.name = "volume"
        self.dragging = None
        self.initialize()

    def initialize(self):
        pass

    # ------------------------------------------------------------------ #
    def _apply(self):
        for v in self.volumes:
            eff = 0.0 if v.is_muted else v.volume
            if v.mode == 'In Game':
                Settings.IN_GAME_SOUNDS_VOLUME = eff
            elif v.mode == 'Background':
                Settings.BG_SOUNDS_VOLUME = eff
                try:
                    v.sounds[0].set_volume(eff)
                except Exception as e:
                    print(e)
                music.set_volume(eff)                    # the level theme follows the MUSIC slider live

    def _set(self, vol, value, preview=False):
        value = round(_clamp(value), 2)
        if value != vol.volume:
            vol.volume = value
            if value > 0:
                vol.is_muted = False
        vol.handle_x = vol.slider_rect.left + vol.volume * vol.slider_rect.width
        if preview:
            self._preview(vol)

    def _preview(self, vol):
        if vol.mode != 'In Game' or vol.is_muted or vol.volume <= 0:
            return
        try:
            snd = Assets.SOUNDS.get('tick')
            ch = pygame.mixer.find_channel()
            if snd and ch:
                ch.set_volume(vol.volume)
                ch.play(snd)
        except Exception as e:
            print(e)

    def _layout(self):
        w, h = self.window.get_size()
        k = max(0.6, min(w / 1280, h / 720))
        n = max(1, len(self.volumes))
        row_h = int(118 * k)
        gap = int(18 * k)
        head = int(112 * k)
        pw = int(min(w * 0.86, 760 * k))
        ph = head + n * row_h + (n - 1) * gap + int(70 * k)
        panel = pygame.Rect(0, 0, pw, ph)
        panel.center = (w // 2, int(h * 0.53))
        rows = []
        for i, v in enumerate(self.volumes):
            r = pygame.Rect(panel.left + int(28 * k), panel.top + head + i * (row_h + gap),
                            pw - int(56 * k), row_h)
            icon = pygame.Rect(r.left + int(18 * k), r.top + int(18 * k), int(44 * k), int(44 * k))
            mute = pygame.Rect(0, 0, int(96 * k), int(36 * k))
            mute.topright = (r.right - int(18 * k), r.top + int(20 * k))
            track = pygame.Rect(r.left + int(22 * k), r.bottom - int(40 * k),
                                r.width - int(44 * k) - int(92 * k), int(14 * k))
            v.slider_rect = track
            v.slider_x, v.slider_y = track.x, track.y
            v.slider_width, v.slider_height = track.width, track.height
            v.button_rect = mute
            v.handle_x = track.left + v.volume * track.width
            v.handle_radius = int(13 * k)
            rows.append((v, r, icon, mute, track))
        return k, panel, rows

    # ------------------------------------------------------------------ #
    def main(self):
        ui = _ui()
        from ..ui import menu_ambience

        try:
            self.selected = self.volumes[0]
        except Exception as e:
            print(e)

        font = pygame.font.SysFont("serif", 36)

        def back_(object_):
            print("Quit Game Settings!")
            object_.volume_settings_window = False
            object_.selected = None

        button_data = [
            ("Back", back_, [self])
        ]

        layout = [
            (1 - 0.02 - 0.1, 0.02 + 0.06, 0.1, 0.06)
        ]

        menu = RPGMenu(self.game.window, font, button_data, layout)
        self.volume_settings_window = True
        self.dragging = None
        self.pulse_time = 0
        t = 0.0
        hold_dir, hold_t = 0, 0.0
        born = pygame.time.get_ticks()

        for v in self.volumes:
            v.display = v.volume
            v.mute_anim = 1.0 if v.is_muted else 0.0
            v.heat = 0.0

        while self.volume_settings_window:
            k, panel, rows = self._layout()
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.volume_settings_window = False
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
                    break

                elif event.type == pygame.KEYDOWN:
                    idx = self.volumes.index(self.selected) if self.selected in self.volumes else 0
                    if event.key == pygame.K_ESCAPE:
                        back_(self)
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        self.selected = self.volumes[(idx - 1) % len(self.volumes)]
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        self.selected = self.volumes[(idx + 1) % len(self.volumes)]
                    elif event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                        hold_dir = 1 if event.key in (pygame.K_RIGHT, pygame.K_d) else -1
                        hold_t = -0.35
                        if self.selected:
                            self._set(self.selected, self.selected.volume + hold_dir * self.KEY_STEP, True)
                    elif event.key in (pygame.K_m, pygame.K_SPACE, pygame.K_RETURN, pygame.K_f):
                        if self.selected:
                            self.selected.is_muted = not self.selected.is_muted

                elif event.type == pygame.KEYUP:
                    if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                        hold_dir = 0

                elif event.type == pygame.JOYHATMOTION or event.type == pygame.JOYAXISMOTION:
                    if event.type == pygame.JOYHATMOTION:
                        hx, hy = event.value
                        hy = -hy
                    else:
                        hx = round(event.value) if event.axis == 0 and abs(event.value) > 0.75 else 0
                        hy = round(event.value) if event.axis == 1 and abs(event.value) > 0.75 else 0
                    idx = self.volumes.index(self.selected) if self.selected in self.volumes else 0
                    if hy:
                        self.selected = self.volumes[(idx + hy) % len(self.volumes)]
                    if hx and self.selected:
                        self._set(self.selected, self.selected.volume + hx * self.KEY_STEP, True)

                elif event.type == pygame.JOYBUTTONDOWN:
                    if event.button == 2 and self.selected:
                        self.selected.is_muted = not self.selected.is_muted
                    elif event.button == 1:
                        back_(self)

                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    menu.handle_mouse(event)
                    for v, r, icon, mute, track in rows:
                        if mute.collidepoint(event.pos) or icon.collidepoint(event.pos):
                            v.is_muted = not v.is_muted
                            self.selected = v
                        elif track.inflate(int(30 * k), int(34 * k)).collidepoint(event.pos):
                            self.selected = v
                            self.dragging = v
                            self._set(v, (event.pos[0] - track.left) / max(1, track.width))
                        elif r.collidepoint(event.pos):
                            self.selected = v

                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if self.dragging:
                        self._preview(self.dragging)
                    self.dragging = None

                elif event.type == pygame.MOUSEMOTION and self.dragging:
                    tr = self.dragging.slider_rect
                    self._set(self.dragging, (event.pos[0] - tr.left) / max(1, tr.width))

                elif event.type == pygame.MOUSEWHEEL:
                    for v, r, icon, mute, track in rows:
                        if r.collidepoint(mouse_pos):
                            self.selected = v
                            self._set(v, v.volume + event.y * self.KEY_STEP, True)

            if not self.volume_settings_window:
                break

            dt = self.game.clock.tick(self.game.FPS) / 1000.0
            dt = min(0.1, dt)
            t += dt
            self.pulse_time += dt

            # held arrow keys -> smooth repeat
            if hold_dir and self.selected:
                hold_t += dt
                if hold_t >= 0.05:
                    hold_t = 0.0
                    self._set(self.selected, self.selected.volume + hold_dir * 0.01)

            self._apply()

            # ---------------- draw ---------------- #
            win = self.window
            menu_ambience.get(self.game).draw(win, getattr(self.game, "menu_bg", None), menu)

            intro = _clamp((pygame.time.get_ticks() - born) / 450.0)
            ease = 1 - (1 - intro) ** 3
            dy = int((1 - ease) * 40 * k)
            panel = panel.move(0, dy)

            # card
            for grow, a in ((14, 18), (8, 30), (3, 50)):
                _alpha_rect(win, panel.inflate(grow * 2, grow * 2), (*ui.CORAL, int(a * ease)), 20 + grow, 2)
            _alpha_rect(win, panel, (30, 19, 26, int(232 * ease)), 20)
            _alpha_rect(win, panel, (*ui.MAROON, int(255 * ease)), 20, 2)

            ui.text_centered(win, "SOUND", (panel.centerx, panel.top + int(44 * k)), int(38 * k), ui.CREAM, True)
            ui.text_centered(win, "drag / click the bar  -  arrows to tune  -  M to mute  -  ESC back",
                             (panel.centerx, panel.top + int(80 * k)), max(11, int(14 * k)), ui.MUTED)
            pygame.draw.line(win, (92, 50, 57), (panel.left + int(30 * k), panel.top + int(98 * k)),
                             (panel.right - int(30 * k), panel.top + int(98 * k)), 1)

            for i, (v, r, icon, mute, track) in enumerate(rows):
                r, icon, mute = r.move(0, dy), icon.move(0, dy), mute.move(0, dy)
                track = track.move(0, dy)
                title, sub, accent = CHANNEL_STYLE.get(v.mode, (str(v.mode).upper(), "", ui.GOLD))
                sel = v is self.selected
                hovering = r.collidepoint(mouse_pos)
                v.heat += ((1.0 if sel else 0.35 if hovering else 0.0) - v.heat) * min(1, dt * 10)
                v.display += (v.volume - v.display) * min(1, dt * 14)
                v.mute_anim += ((1.0 if v.is_muted else 0.0) - v.mute_anim) * min(1, dt * 12)
                live = 0.0 if v.is_muted else v.display
                col = _lerp_col(accent, ui.MUTED, v.mute_anim)

                # row card
                fill = _lerp_col((40, 24, 32), (58, 30, 40), v.heat)
                _alpha_rect(win, r, (*fill, 245), 14)
                _alpha_rect(win, r, (*_lerp_col((92, 50, 57), col, v.heat), 255), 14, 2)
                if v.heat > 0.05:
                    bar = pygame.Rect(r.left, r.top + int(14 * k), max(3, int(5 * k)), r.height - int(28 * k))
                    _alpha_rect(win, bar, (*col, int(255 * v.heat)), 3)

                # icon + labels
                _speaker(win, icon, col, live, v.is_muted, t)
                tx = icon.right + int(14 * k)
                ui.text(win, title, (tx, r.top + int(14 * k)), int(22 * k), ui.CREAM if sel else ui.WHITE, True)
                ui.text(win, sub, (tx, r.top + int(44 * k)), max(10, int(13 * k)), ui.MUTED)

                # live level meter (little dancing bars)
                mx = tx + int(190 * k)
                for b in range(7):
                    lvl = live * (0.45 + 0.55 * abs(math.sin(t * (3.1 + b * 0.7) + b * 1.3)))
                    bh = max(2, int(30 * k * lvl))
                    bar = pygame.Rect(mx + b * int(9 * k), r.top + int(48 * k) - bh, int(6 * k), bh)
                    pygame.draw.rect(win, _lerp_col(col, ui.GOLD, b / 6), bar, border_radius=2)

                # mute switch
                _alpha_rect(win, mute, (*_lerp_col(col, (60, 36, 44), v.mute_anim), 255), mute.height // 2)
                knob_r = mute.height // 2 - int(4 * k)
                kx = int(mute.right - mute.height // 2 - (mute.width - mute.height) * v.mute_anim)
                pygame.draw.circle(win, ui.WHITE, (kx, mute.centery), max(3, knob_r))
                lbl = "ON" if not v.is_muted else "MUTED"
                lx = mute.left + int(12 * k) if not v.is_muted else mute.right - int(12 * k)
                surf = ui.font(max(10, int(13 * k)), True).render(lbl, True, ui.INK if not v.is_muted else ui.CREAM)
                rect = surf.get_rect(midleft=(lx, mute.centery)) if not v.is_muted else surf.get_rect(midright=(lx, mute.centery))
                win.blit(surf, rect)

                # slider track + fill
                _alpha_rect(win, track.inflate(int(6 * k), int(6 * k)), (*ui.INK, 255), track.height)
                fill_w = int(track.width * live)
                if fill_w > 0:
                    fr = pygame.Rect(track.left, track.top, fill_w, track.height)
                    grad = pygame.Surface(fr.size, pygame.SRCALPHA)
                    for x in range(0, fr.width, 3):
                        c = _lerp_col(col, ui.GOLD, x / max(1, track.width))
                        pygame.draw.line(grad, (*c, 255), (x, 0), (x, fr.height), 3)
                    mask = pygame.Surface(fr.size, pygame.SRCALPHA)
                    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=track.height // 2)
                    grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                    win.blit(grad, fr.topleft)
                for tick in range(1, 10):
                    x = track.left + track.width * tick / 10
                    pygame.draw.line(win, (*ui.INK,), (int(x), track.top + 2), (int(x), track.bottom - 3), 1)

                # knob
                kx = int(track.left + track.width * (v.display if not v.is_muted else 0))
                active = (self.dragging is v) or (sel and v.heat > 0.5)
                kr = int(v.handle_radius * (1.25 if self.dragging is v else 1.0 + 0.06 * math.sin(t * 4) * v.heat))
                if not v.is_muted:
                    _soft_glow(win, (kx, track.centery), col, kr * (3.2 if active else 2.2), 0.9 if active else 0.5)
                pygame.draw.circle(win, ui.INK, (kx, track.centery + 2), kr + 2)
                pygame.draw.circle(win, col, (kx, track.centery), kr + 2)
                pygame.draw.circle(win, ui.WHITE, (kx, track.centery), kr - 2)

                # value badge
                pct = f"{int(round(v.display * 100))}%" if not v.is_muted else "--"
                badge = pygame.Rect(0, 0, int(70 * k), int(30 * k))
                badge.midleft = (track.right + int(20 * k), track.centery)
                _alpha_rect(win, badge, (*ui.INK, 255), badge.height // 2)
                _alpha_rect(win, badge, (*col, 255), badge.height // 2, 2)
                ui.text_centered(win, pct, badge.center, max(11, int(16 * k)), ui.CREAM, True)

            menu.update(mouse_pos)
            menu.draw()

            pygame.display.flip()

        self._apply()


# VOLUME CLASS
class Volume:
    def __init__(self, x=0, y=0, sound=None, sounds=None):
        if sounds is None:
            sounds = [Assets.SOUNDS['theme']]
        self.settings = Settings()
        self.sounds = sounds
        self.mode = sound
        self.initialise_volume(x, y)

    def initialise_volume(self, x, y):
        self.x = x
        self.y = y

        # Volume settings: start from whatever the game is currently using
        if self.mode == 'In Game':
            self.volume = Settings.IN_GAME_SOUNDS_VOLUME
        elif self.mode == 'Background':
            self.volume = Settings.BG_SOUNDS_VOLUME
        else:
            self.volume = 0.5
        self.is_muted = False
        self.dragging = False

        # visual state (animated by Volumes.main)
        self.display = self.volume
        self.mute_anim = 0.0
        self.heat = 0.0

        # Slider properties
        self.slider_width = 300
        self.slider_height = 30

        self.handle_radius = 15

        # Button properties
        self.button_width = 100
        self.button_height = 50

        self.initialize()

    def initialize(self):
        # Legacy rects (Volumes.main re-lays these out responsively every frame)
        self.slider_x = (self.settings.WIDTH - self.slider_width) // 2 + self.x
        self.slider_y = self.settings.HEIGHT // 2 + self.y
        self.slider_rect = pygame.Rect(self.slider_x, self.slider_y, self.slider_width, self.slider_height)

        self.handle_x = self.slider_x + int(self.volume * self.slider_width)

        self.button_x = (self.settings.WIDTH - self.button_width) // 2 + self.x
        self.button_y = self.settings.HEIGHT // 2 + 60 + self.y
        self.button_rect = pygame.Rect(self.button_x, self.button_y, self.button_width, self.button_height)


# SOUNDS 
class Sounds:
    def __init__(self, player, degree=1):
        self.protagonist = player
        self.degree = degree
        self.bg_volume = 0.5
        self.bg_degree = 1

    def play_bg(self, sound, loop=None):
        if loop == -1:
            Assets.SOUNDS[sound].set_volume(Settings.BG_SOUNDS_VOLUME)
            Assets.SOUNDS[sound].play(loop)
            return

        Assets.SOUNDS[sound].set_volume(Settings.BG_SOUNDS_VOLUME)
        Assets.SOUNDS[sound].play()

    def stop(self, sound):
        if sound == "theme":
            music.stop()                    # "stop the music" means the level theme too
        if sound in Assets.SOUNDS:
            Assets.SOUNDS[sound].stop()

    def get_volume(self, enemy):
        the_distance = abs(distance(self.protagonist.rect.x, self.protagonist.rect.y, enemy.rect.x, enemy.rect.y))
        max_distance = Settings.WIDTH
        volume = max(0, 1 - the_distance / (max_distance / 2))
        return volume
    

# SOUND PLAYER
def playit(song, origin):
    volume = origin.game.sounds.get_volume(origin)
    main_vol = volume * Settings.IN_GAME_SOUNDS_VOLUME

    channel = pygame.mixer.find_channel()
    if channel and main_vol > 0:
        channel.set_volume(main_vol)
        channel.play(Assets.SOUNDS[song])