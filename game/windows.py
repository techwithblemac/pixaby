import pygame
import math
import webbrowser

from .settings import Settings, VERSION

from .scripts.functions import ( 
    My_Text, TypeText,
    parallax_bg, get_dynamic_color, draw_vertical_gradient,
    refresh_joysticks
)
from .scripts.menu import RPGMenu
from .scripts.cache import cache_font

from .level.main.draw_funcs import draw
from .level.main.update_funcs import update_game_logic
from .level.level_editor import Level_Editor
from .level.level_editor import select_level

from .ui import ui_theme, menu_ambience
from .scripts import shop_effects
from .scripts import paths
from .scripts import death_rules
from .scripts import screen_mode
from .level.editor import editor_launch
from .level import progression


class Windows:

    def draw_menu_bg(self, menu=None, bg=True):
        """Animated backdrop for every menu: drifting bg image, god rays,
        floating embers, breathing vignette and a fade-in per screen
        (see ui/menu_ambience.py)."""
        menu_ambience.get(self).draw(self.window, self.menu_bg if bg else None, menu)

    def update_start_btns_pos(self):
        self.game_name.x, self.game_name.y = Settings.WIDTH // 2, 10
        self.game_name.update()
    
    def start(self):

        global game_started, message_text, message_timer
        
        typewriter = TypeText(
            "You awake in the dark.\nA voice whispers:\n'Five floors down... then I let you go.'",
            pos=(10, 10),
            font=Settings.font,
            color=(50, 50, 50),
            speed=15  # 20 characters per second
        )

        self.game_name = My_Text("PIXEL ABYSS")

        bg_particles = []
        master_clock = 0
        height = 2

        message_timer = 0
        message_text = ""
        self.displaying = True
        game_started = True

        times_box = [0]

        font = pygame.font.SysFont("serif", 36)

        def start():
            global game_started, message_text, message_timer
            print("Opening level selection...")
            choice = select_level(self, paths.LEVELS_ROOT)
            if choice is None:
                return
            self.level = int(choice.id)
            self.level_folder = choice.folder
            self.level_players = choice.players if choice.folder == "multiplayer" else None
            # Co-op levels switch the existing multiplayer mode on (network); going back to a solo level
            # turns it off again, but only if the selector was what turned it on. In Split Screen
            # mode the co-op world stays on this machine: no network, local players join on the join screen.
            if choice.folder == "multiplayer":
                if not self.MULTIPLAYER and not getattr(self, "SPLIT_SCREEN", False):
                    self.MULTIPLAYER = True
                    self._multiplayer_from_selector = True
            elif getattr(self, "_multiplayer_from_selector", False):
                self.MULTIPLAYER = False
                self._multiplayer_from_selector = False
            shop_effects.reset_run(self.player_slots)
            death_rules.reset_run(self)
            progression.begin_run(self)
            self.level_completed = False
            self.new = True
            # Straight into the game: its own intro/loading screen takes over from here
            from . import game as game
            game.main(self, code=times_box[0])
            times_box[0] += 1

        def mode(object_):
            print("Select preferred mode!")
            object_.modes()

        def game_info(object_):
            print("Select preferred game_info!")
            object_.game_info()

        def author_info(object_):
            print("Select preferred author_info!")
            object_.author_info()

        def open_link(url):
            def _open(object_):
                webbrowser.open(url)
            return _open

        self.start_link_icons = [
            ("github", "GitHub", "https://github.com/tech-with-blessing"),
            ("itch", "Pixel Abyss (itch.io)", "https://techwithblemac.itch.io/pixel-abyss"),
            ("facebook", "Facebook", "https://www.facebook.com/profile.php?id=61578165867167"),
            ("x", "X", "https://x.com/techwithblemac/"),
        ]
        link_icon_files = {
            "github": "Github_social_media_corporate_logo_icon-icons.com_67672 (2).png",
            "itch": "itch_icon_146025 (2).png",
            "facebook": "Facebook_social_media_corporate_logo_icon-icons.com_67686 (2).png",
            "x": "Twitter_social_media_corporate_logo_icon-icons.com_67685 (1).png",
        }
        self.start_link_icon_surfaces = {}
        for icon_name, _label, _url in self.start_link_icons:
            try:
                image = pygame.image.load(
                    paths.asset("icons", "links", link_icon_files[icon_name])
                ).convert_alpha()
                self.start_link_icon_surfaces[icon_name] = pygame.transform.smoothscale(image, (44, 44))
            except (FileNotFoundError, pygame.error):
                pass

        def game_settings(object_):
            print("Select preferred game_settings!")
            object_.game_settings(1)

        def achievements_(object_):
            from .ui.achievements_screen import open_achievements
            if open_achievements(object_) is False:          # the window was closed inside it
                object_.running = False
                object_.displaying = False

        def quit_(object_):
            print("Quit Game!")
            object_.running = False
            object_.displaying = False

        button_data = [
            ("Start", start, None), ("Mode", mode, [self]),
            ("game_info", game_info, [self]), ("author_info", author_info, [self]),
            ("game_settings", game_settings, [self]), ("ACHIEVEMENTS", achievements_, [self]),
            ("Quit", quit_, [self])
        ]
        layout = [
            (0.5, 0.18, 0.3, 0.06),
            (0.3, 0.28, 0.3, 0.06),
            (0.5, 0.38, 0.3, 0.06),
            (0.3, 0.48, 0.3, 0.06),
            (0.5, 0.58, 0.3, 0.06),
            (0.3, 0.68, 0.3, 0.06),
            (0.5, 0.78, 0.3, 0.06),
        ]

        menu = RPGMenu(self.window, font, button_data, layout)

        while self.displaying:
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.displaying = False
                    del self
                    return

                if event.type == (pygame.JOYDEVICEADDED or pygame.JOYDEVICEREMOVED):
                    refresh_joysticks(self)
                    
                if event.type == pygame.JOYAXISMOTION:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event, "axis")
                    
                if event.type == pygame.JOYBUTTONDOWN:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event)
                    
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        quit_(self)

                    menu.handle_key(event.key)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self._click_start_link_icon(event.pos):
                        continue
                    if not typewriter.done:
                        typewriter.skip()  # Skip to full text

                    menu.handle_mouse(event)

            self.game_name.update()

            # Clear the message after 2 seconds
            if message_text and pygame.time.get_ticks() - message_timer > 2000:
                message_text = ""

            self.window.fill(self.bg_color)

            bg_particles = parallax_bg(
                self.window, 
                Settings.WIDTH, Settings.HEIGHT, 
                bg_particles, master_clock,
                threshold=20, height=0,
                parallax_color=Settings.PARALLAX, bg_color=Settings.BG_COLOR
            )
            
            self.draw_menu_bg(menu, bg=False)
            self.game_name.draw()

            # Show feedback message if any
            if message_text:
                msg = Settings.SMALL_FONT.render(message_text, True, Settings.RED)
                msg_rect = msg.get_rect(center=(Settings.WIDTH // 2, Settings.HEIGHT - 100))
                Settings.window.blit(msg, msg_rect)

            typewriter.update()
            typewriter.draw(self.window, True)

            menu.update(mouse_pos)
            menu.draw()
            self._draw_start_link_icons()

            if self.DEBUGGING_MODE:
                self.get_fps()

            pygame.display.flip()

            # HANDLE DELTA TIME
            raw_dt = self.clock.tick(self.FPS) / 1000.0
            self.game_speed = min(self.max_game_speed, self.game_speed + 0.1)
            self.dt = min(0.1, raw_dt * self.game_speed)
            master_clock += int(raw_dt * 80)

    def _draw_start_link_icons(self):
        if not getattr(self, "start_link_icons", None):
            return
        mouse = pygame.mouse.get_pos()
        for i, (icon_name, _label, _url) in enumerate(self.start_link_icons):
            rect = pygame.Rect(24, 170 + i * 72, 52, 52)
            icon = self.start_link_icon_surfaces.get(icon_name)
            if not icon:
                continue
            if rect.collidepoint(mouse):
                icon = pygame.transform.smoothscale(icon, (50, 50))
            self.window.blit(icon, icon.get_rect(center=rect.center))

    def _click_start_link_icon(self, pos):
        if not getattr(self, "start_link_icons", None):
            return False
        for i, (_icon_name, _label, url) in enumerate(self.start_link_icons):
            rect = pygame.Rect(24, 170 + i * 72, 52, 52)
            if rect.collidepoint(pos):
                webbrowser.open(url)
                return True
        return False


    # Changing game modes
    def modes(self, code=0):
        """Solo / Host / Join as a card carousel (ui/info_windows.py)."""
        from .ui.info_windows import open_mode
        self.menu_btn_text = 'BACK'
        self.modes_window = True
        ok = open_mode(self)
        self.modes_window = False
        if ok is False:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def entity_info(self, entity):
        """Portrait, stat bars, facts and the shared befriend code path (ui/info_windows.py)."""
        from .ui.info_windows import open_entity
        self.info_displaying = True
        ok = open_entity(self, entity)
        self.info_displaying = False
        if ok is False:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def game_settings(self, code=0):

        self.menu_btn_text = 'BACK'

        font = pygame.font.SysFont("serif", 36)

        def volume_settings(object_):
            print("Volume settings selected!")
            object_.volumes.main()

        def back_(object_):
            print("Quit Game Settings!")
            object_.game_settings_window = False

        def world_editor(object_):
            print("Selected Level Editor!")
            object_.edit_world()

        def camera_mode(object_):
            Settings.CAMERA_MODE = "classic" if Settings.CAMERA_MODE == "smooth" else "smooth"

        def screen_shake(object_):
            Settings.SCREEN_SHAKE = not Settings.SCREEN_SHAKE

        def graphics(object_):
            # screen modes + lighting / shadows / fireflies (ui/graphics_window.py)
            from .ui.graphics_window import open_graphics
            if open_graphics(object_) is False:             # the window was closed inside it
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                object_.game_settings_window = False

        button_data = [
            ("Back", back_, [self]),
            ("VOLUME", volume_settings, [self]),
            ("WORLD EDITOR", world_editor, [self]),
            ("CAMERA", camera_mode, [self]),
            ("SHAKE", screen_shake, [self]),
            ("GRAPHICS", graphics, [self])
        ]

        layout = [
            (1 - 0.02 - 0.1, 0.02 + 0.06, 0.1, 0.06),
            (1 - 0.5 - 0.1, 0.5 - 0.03 - 0.06 - 0.02, 0.2, 0.06),
            (1 - 0.5 - 0.15, 0.5 - 0.03, 0.3, 0.06),
            (1 - 0.5 - 0.15, 0.5 + 0.06, 0.3, 0.06),
            (1 - 0.5 - 0.15, 0.5 + 0.14, 0.3, 0.06),
            (1 - 0.5 - 0.15, 0.5 + 0.22, 0.3, 0.06),
        ]

        menu = RPGMenu(self.window, font, button_data, layout)
        self.game_settings_window = True

        while self.game_settings_window:


            mouse_pos = pygame.mouse.get_pos()

            # WORLD EDITOR: only while DEBUGGING_MODE is on, and not from the start screen
            menu.exclude((2, bool(code) or not editor_launch.editor_available()))

            # the toggles show their current state
            for b in menu.buttons:
                if b.text.startswith("CAMERA"):
                    b.text = f"CAMERA: {Settings.CAMERA_MODE.upper()}"
                elif b.text.startswith("SHAKE"):
                    b.text = f"SHAKE: {'ON' if Settings.SCREEN_SHAKE else 'OFF'}"

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    displaying = False
                    break
                
                if event.type == pygame.JOYAXISMOTION:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event, "axis")
                    
                if event.type == pygame.JOYBUTTONDOWN:
                    
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event)
                    
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        back_(self)

                    menu.handle_key(event.key)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    menu.handle_mouse(event)

            self.window.fill((200, 0, 200))

            # Bg
            self.draw_menu_bg(menu)

            menu.update(mouse_pos)
            menu.draw()

            if self.DEBUGGING_MODE:
                self.get_fps()

            pygame.display.flip()

            self.clock.tick(self.FPS)

    def game_info(self):
        """Tabbed pages: how to play, controls, characters, shop, charms, tips (ui/info_windows.py)."""
        from .ui.info_windows import open_game_info
        self.game_info_window = True
        ok = open_game_info(self)
        self.game_info_window = False
        if ok is False:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def edit_world(self):
        Level_Editor.edit_world(self)
        return
    
    def author_info(self):
        """Hero card, link pills and the credits roll (ui/info_windows.py)."""
        from .ui.info_windows import open_author
        self.game_info_window = True
        ok = open_author(self)
        self.game_info_window = False
        if ok is False:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def links_info(self):
        self.author_info()


    def player_settings(self):
        pass


    def store(self):

        font = pygame.font.SysFont("serif", 36)

        def back_(object_):
            print("Quit Game Settings!")
            object_.game_info_window = False

        button_data = [
            ("Back", back_, [self])]

        layout = [
            (1 - 0.02 - 0.1, 0.02 + 0.06, 0.1, 0.06)]

        menu = RPGMenu(self.window, font, button_data, layout)
        self.game_info_window = True

        while self.game_info_window:


            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    displaying = False
                    break
                
                if event.type == pygame.JOYAXISMOTION:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event, "axis")
                    
                if event.type == pygame.JOYBUTTONDOWN:
                    
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event)
                    
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        back_(self)

                    menu.handle_key(event.key)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    menu.handle_mouse(event)

            self.window.fill((200, 0, 200))

            # Bg
            self.draw_menu_bg(menu)

            if self.DEBUGGING_MODE:
                self.get_fps()

            menu.update(mouse_pos)
            menu.draw()

            pygame.display.flip()

            self.clock.tick(self.FPS)

    def loading(self):

        LOADING_TIPS = [
            "Archers hold the high ground — check your sightlines before you climb.",
            "Not every enemy needs a fight. Some can be befriended instead.",
            "Keyboard co-op: press RIGHT SHIFT or LEFT SHIFT to join a local match.",
            "Gamepad co-op: press A to join, RB (button 5) to ready up.",
            "TNT enemies punish careless melee — keep your distance.",
            "In the level editor, press H any time for a full control reference.",
            "PRO+ unlocks the harder half of the Official Archive — levels 6 to 10.",
            "Water slows everyone down equally — use it to even the odds.",
            "Level editor tip: Ctrl+S quick-saves without leaving your seat.",
            "Dev note: PIXEL ABYSS is built solo by Blessing Machekeche (BLEMAC) "
            "from Zimbabwe 🇿🇼.",
        ]

        if not hasattr(self, "_loading_ticker") or self._loading_ticker is None:
            self._loading_ticker = ui_theme.TipTicker(LOADING_TIPS, interval=3.6)

        ticker = self._loading_ticker
        self.loading_window = True
        t = 0.0

        bg_scaled = None
        bg_size = None

        while not self.env_ready:


            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    break

            w, h = self.window.get_size()

            # Background: the real menu art, darkened, so the loading
            # screen still feels like part of the game rather than a
            # bare placeholder.
            if bg_scaled is None or bg_size != (w, h):
                bg_scaled = pygame.transform.smoothscale(self.menu_bg, (w, h))
                bg_size = (w, h)
            self.window.blit(bg_scaled, (0, 0))
            ui_theme.dim_overlay(self.window, 165, ui_theme.INK)

            for gx in range(0, w, 42):
                pygame.draw.line(self.window, (36, 24, 33), (gx, 0), (gx, h), 1)

            bob = math.sin(t * 2.2) * 4
            ui_theme.text(self.window, "PIXEL ABYSS", (w * 0.5 - 130, h * 0.32 + bob),
                          34, ui_theme.CREAM, True)
            ui_theme.text(self.window, "DESCENDING...", (w * 0.5 - 130, h * 0.32 + 42 + bob),
                          13, ui_theme.CORAL, True)

            ui_theme.spinner(self.window, (int(w * 0.5), int(h * 0.55)), 22, t, ui_theme.CORAL)

            ticker.update(self.dt if hasattr(self, "dt") and self.dt else self.clock.get_time() / 1000.0)
            tip_box_w = min(720, int(w * 0.7))
            ui_theme.text_centered(self.window, "TIP", (w // 2, int(h * 0.68)), 10, ui_theme.GOLD, True)
            ticker.draw(self.window, (w // 2, int(h * 0.68) + 22), 14, ui_theme.WHITE,
                        max_width=tip_box_w, center=True)

            ui_theme.text(self.window, f"PIXEL ABYSS v{VERSION}", (16, h - 26), 10, ui_theme.MUTED)

            if self.DEBUGGING_MODE:
                self.get_fps()

            pygame.display.flip()

            frame_ms = self.clock.tick(self.FPS)
            self.dt = frame_ms / 1000.0
            t += self.dt

        self._loading_ticker = None


    def exit(self, code=0) -> int:

        self.exiting = True

        sw, sh = self.window.get_rect().size
        font = cache_font(("impact", int(sw * 0.02)))
        
        def yes_(object_):
            print("Entered Yes, Exited!")
            if code == 1:
                pygame.quit()
                quit()
            else:
                object_.sounds.stop("theme")
                object_.exiting = False
                return 0


        def no_(object_):
            print("Canceled!")
            object_.exiting = False

        def back_(object_):
            print("Canceled!")
            object_.exiting = False

        button_data = [
            ("Back", back_, [self]),
            ("YES", yes_, [self]),
            ("NO", no_, [self])
        ]

        layout = [
            (1 - 0.02 - 0.1, 0.02 + 0.06, 0.1, 0.06),
            (0.5 - 0.2 - 0.1, 0.5 - 0.04, 0.2, 0.08),
            (0.5 + 0.1, 0.5 - 0.04, 0.2, 0.08)
        ]

        menu = RPGMenu(self.window, font, button_data, layout)

        menu.buttons[1].color = (100, 10, 5)
        menu.buttons[2].color = (5, 100, 5)
        
        while self.exiting:
            # CAPTURE EVENTS
            self.mouse_pos = pygame.mouse.get_pos()
            self.events = pygame.event.get()

            for event in self.events:
                if event.type == pygame.QUIT:
                    self.exiting = False
                    break
                    
                if event.type == pygame.KEYUP:
                    self.keys = pygame.key.get_pressed()

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        yes_(self)

                    # HANDLE MENU BUTTONS EVENTS
                    menu.handle_key(event.key)
                
                if event.type == pygame.JOYAXISMOTION:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event, "axis")
                    
                if event.type == pygame.JOYBUTTONDOWN:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event)

                if event.type == pygame.MOUSEBUTTONDOWN:        
                    # HANDLE BUTTON EVENTS
                    menu.handle_mouse(event)


            self.window.fill((200, 0, 200))

            # Bg
            self.draw_menu_bg(menu)

            text_surface = Settings.display_font.render(
                f'Are you sure you want to EXIT' if code == 1 else 'Are you sure you want to GO BACK STARTUP MENU',
                True, Settings.BLACK)
            rect = text_surface.get_rect()
            rect2 = pygame.Rect(0, 200, rect.width, rect.height)

            rect2.centerx = Settings.WIDTH / 2

            Settings.window.blit(text_surface, (rect2.x, rect2.y))
            
            # MENU BUTTONS
            menu.update(self.mouse_pos)
            menu.draw()
            
            if self.DEBUGGING_MODE:
                self.get_fps()

            pygame.display.flip()

            self.clock.tick(self.FPS)

    def menu(self):

        self.menu_btn_text = 'BACK'
        var = True

        font = pygame.font.SysFont("serif", 36)

        def game_info(object_):
            print("Select preferred game_info!")
            object_.game_info()

        def game_settings(object_):
            print("Select preferred game_settings!")
            object_.game_settings()

        def achievements_(object_):
            from .ui.achievements_screen import open_achievements
            if open_achievements(object_) is False:
                object_.running = False
                object_.MENU = False

        def quit_(object_):
            print("Quit Game!")
            object_.running = False
            object_.MENU = False

        def back_(object_):
            print("Quit Menu!")
            object_.MENU = False

        button_data = [
            ("Back", back_, [self]), ("game_settings", game_settings, [self]),
            ("game_info", game_info, [self]), ("ACHIEVEMENTS", achievements_, [self]),
            ("Quit", quit_, [self])
        ]
        layout = [
            (1 - 0.02 - 0.1, 0.02 + 0.06, 0.1, 0.06),
            (0.5, 0.15, 0.3, 0.06),
            (0.3, 0.25, 0.3, 0.06),
            (0.5, 0.35, 0.3, 0.06),
            (0.3, 0.45, 0.3, 0.06)
        ]

        view_rect = self.player.viewport.clip(self.window_rect)

        menu = RPGMenu(self.window, font, button_data, layout)

        while self.MENU:
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.menu_btn_text = 'MENU'
                    self.MENU = False
                    break
                
                if event.type == pygame.JOYAXISMOTION:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event, "axis")
                    
                if event.type == pygame.JOYBUTTONDOWN:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event)
                    
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        back_(self)

                    menu.handle_key(event.key)

                if event.type == pygame.MOUSEBUTTONDOWN:
                    menu.handle_mouse(event)

        
            # self.update_menu_btns_pos()

            self.window.fill((200, 0, 200))

            # Bg
            self.draw_menu_bg(menu)

            if self.DEBUGGING_MODE:
                self.get_fps()

            menu.update(mouse_pos)
            menu.draw()

            pygame.display.flip()

            self.clock.tick(self.FPS)

    def game_over(self):

        typewriter = TypeText(
            "You awake in the dark.\nA voice whispers:\n'Five floors... then I let you go.'",
            pos=(50, 400),
            font=Settings.font,
            color=(255, 255, 255),
            speed=20  # 20 characters per second
        )
        # self.sounds.play_bg('theme',  -1)

        run = True

        while run:

            for event in pygame.event.get():

                if event.type == pygame.MOUSEBUTTONUP:
                    if not self.SPECTATING_BTN.indicate:
                        self.SPECTATING_BTN.clicked = False

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.SPECTATING_BTN.is_clicked(event.pos, []):
                        self.spectate()

                if event.type == pygame.QUIT:
                    run = False
                    break
                if event.type == pygame.MOUSEBUTTONDOWN and not typewriter.done:
                    typewriter.skip()  # Skip to full text

            self.window.fill((105, 55, 55))

            # Bg
            self.draw_menu_bg(None)
            typewriter.update()
            typewriter.draw(self.window, True)
            self.SPECTATING_BTN.draw(self.window)

            if self.DEBUGGING_MODE:
                self.get_fps()

            pygame.display.flip()

            self.clock.tick(self.FPS)

        pygame.quit()
        quit()

    def spectate(self):

        self.SPECTATING = True
        self.spectating_btn_text = 'BACK'
        
        lastx = self.offset_x
        lasty = self.offset_y
        
        clicked = False
        font = pygame.font.SysFont("serif", 30)

        def menu(_object):
            print("Started Menu!")
            _object.MENU = True
            _object.pause_start = pygame.time.get_ticks()
            _object.menu()
            _object.pause_total += pygame.time.get_ticks() - _object.pause_start
            print("Menu Ended!")

        def exit_spectate(_object):
            _object.SPECTATING = False
            print("Exiting Spectate Window!")

        def view(_object):
            _object.VIEW = not _object.VIEW
            print(f"Object Info is {'ON' if _object.VIEW else 'OFF'}")

        button_data = [
            ("MENU", menu, [self]), 
            ("BACK", exit_spectate, [self]), 
            ("VIEW", view, [self])
        ]

        layout = [
            (1 - 0.08 - 0.02, 0.03, 0.08, 0.06),  
            (0.5 - 0.2 - 0.03, 0.03, 0.2, 0.06),
            (0.5 + 0.03, 0.03, 0.2, 0.06)
        ]

        menu = RPGMenu(self.window, font, button_data, layout)
        self._draw_list_dirty = True
 
        while self.SPECTATING:
            # CAPTURE EVENTS
            mouse_pos = pygame.mouse.get_pos()
            if self._entities_dirty:
               self._rebuild_all_entities()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.SPECTATING = False
                    break

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        clicked = True
                    
                    # HANDLE BUTTON EVENTS
                    menu.handle_mouse(event)
                
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        exit_spectate(self)

                    # HANDLE MENU BUTTONS EVENTS
                    menu.handle_key(event.key)

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        clicked = False
                
                elif event.type == pygame.MOUSEMOTION:
                    if clicked:
                        self.offset_x -= event.rel[0]
                        self.offset_y -= event.rel[1]

                elif event.type == pygame.JOYAXISMOTION:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event, "axis")
                    
                elif event.type == pygame.JOYBUTTONDOWN:
                    # HANDLE MENU JOY_BUTTONS EVENTS
                    menu.handle_joy(event)
                
            objects_to_draw = update_game_logic(self)

            self.window.fill((20, 0, 20))

            # PARALLAX BACKGROUND
            self.bg_particles = parallax_bg(
                self.window, 
                Settings.WIDTH, Settings.HEIGHT, 
                self.bg_particles, self.master_clock,
                threshold=20, height=0,
                parallax_color=Settings.PARALLAX, bg_color=Settings.BG_COLOR
            )

            draw(self, objects_to_draw=objects_to_draw, type_="sub")
            
            # MENU BUTTONS
            menu.update(mouse_pos)
            menu.draw()

            # GAME FPS
            if self.DEBUGGING_MODE:
                self.get_fps()
            
            pygame.display.flip()

            # HANDLE DELTA TIME
            raw_dt = self.clock.tick(self.FPS) / 1000.0
            self.game_speed = min(self.max_game_speed, self.game_speed + 0.1)
            self.dt = round(min(0.1, raw_dt * self.game_speed), 3)

            self.master_clock += int(raw_dt * 80)