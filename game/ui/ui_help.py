import math
import pygame

# Shared palette used by the level selector and the editor help surfaces.
INK = (18, 17, 25)
INK2 = (34, 23, 34)
MAROON = (79, 38, 49)
RED = (224, 78, 74)
CORAL = (255, 112, 92)
CREAM = (255, 224, 151)
WHITE = (255, 242, 207)
MUTED = (177, 139, 128)
GREEN = (108, 201, 117)
BLUE = (100, 170, 215)
PURPLE = (171, 105, 164)
GOLD = (255, 202, 80)


def _font(size, bold=False):
    return pygame.font.SysFont("consolas", max(12, int(size)), bold=bold)


def _panel(screen, rect, fill=(52, 24, 37), border=CORAL, width=2, radius=16):
    surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(surf, fill + (242,), surf.get_rect(), border_radius=radius)
    pygame.draw.rect(surf, border, surf.get_rect(), width=width, border_radius=radius)
    screen.blit(surf, rect.topleft)


def _text(screen, text, pos, size, color=WHITE, bold=False):
    s = _font(size, bold).render(str(text), True, color)
    screen.blit(s, (int(pos[0]), int(pos[1])))
    return s


def _button(screen, rect, label, accent=CORAL):
    hover = rect.collidepoint(pygame.mouse.get_pos())
    fill = (83, 37, 47) if hover else (48, 27, 36)
    pygame.draw.rect(screen, fill, rect, border_radius=9)
    pygame.draw.rect(screen, accent if hover else (112, 64, 66), rect, 2 if hover else 1, border_radius=9)
    s = _font(15, True).render(label, True, CREAM if hover else WHITE)
    screen.blit(s, s.get_rect(center=rect.center))
    return hover


def show_how_to(screen, mode="editor", clock=None, fps=60):
    """Modal help overlay. Returns False only when the user closes it."""
    clock = clock or pygame.time.Clock()
    running = True
    t = 0.0
    sw, sh = screen.get_size()
    while running:
        sw, sh = screen.get_size()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_h, pygame.K_F1):
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if close_rect.collidepoint(event.pos):
                    running = False

        # The caller's scene remains visible beneath the translucent overlay.
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((20, 7, 13, 205))
        screen.blit(shade, (0, 0))

        rw = min(820, sw - 28)
        rh = min(610, sh - 28)
        panel = pygame.Rect((sw-rw)//2, (sh-rh)//2, rw, rh)
        _panel(screen, panel)

        pulse = 2 * math.sin(t * 3)
        _text(screen, "HOW TO // CONTROLS", (panel.x + 25, panel.y + 20 + pulse), 24, CREAM, True)
        _text(screen, "Quick reference — designed for keyboard, mouse and controller/touch workflows.",
              (panel.x + 26, panel.y + 54), 13, MUTED)

        if mode == "editor":
            rows = [
                ("LMB", "Place the selected item. Hold + drag to paint repeatedly.", CORAL),
                ("RMB", "Hold and drag to pan the world without changing tiles.", BLUE),
                ("F1 / Q", "Toggle the editor grid / visual guides.", PURPLE),
                ("1 / I", "Cycle INSERT -> DELETE -> MODIFY mode.", GREEN),
                ("M", "Jump straight to MODIFY: click a placed item to edit it.", CORAL),
                ("K", "Open Entity Stats - per-level enemy health, damage, aggro.", PURPLE),
                ("2 / P", "Toggle foreground / background perspective.", GOLD),
                ("- / =", "Zoom out / zoom in. Use small steps for precise editing.", CORAL),
                ("SHIFT", "Reverse the Type / Size / Colour cycling direction.", BLUE),
                ("ESC", "Leave the editor. Unsaved changes trigger a save prompt.", PURPLE),
                ("MOUSE", "Click a grid cell to preview it; click again or drag to commit.", GREEN),
                ("TIP", "Use larger blocks for terrain, then switch to Entities/Deco for detail.", GOLD),
            ]
        else:
            rows = [
                ("KEYBOARD", "WASD / Arrow keys move the selected player.", CORAL),
                ("READY", "Press Right Ctrl / Left Ctrl to ready the matching keyboard player.", BLUE),
                ("JOYSTICK", "Connect a controller, then press its main/confirm button to join.", GREEN),
                ("REMOVE", "Press the same keyboard/joystick join input again to leave that slot.", PURPLE),
                ("TOUCH", "Use the on-screen movement joystick; the action joystick controls attacks when enabled.", GOLD),
                ("START", "Every joined player must be READY before the waiting room opens the game.", CORAL),
                ("MULTI", "Up to the available player slots can be joined before starting.", BLUE),
                ("TIP", "Use the player viewport label to verify which keyboard/controller owns each slot.", GREEN),
            ]

        top = panel.y + 91
        col_w = (panel.width - 66) // 2
        row_h = 48
        for i, (key, desc, accent) in enumerate(rows):
            col = i % 2
            row = i // 2
            r = pygame.Rect(panel.x + 22 + col * (col_w + 20), top + row * row_h, col_w, row_h - 5)
            pygame.draw.rect(screen, (39, 21, 31), r, border_radius=9)
            pygame.draw.rect(screen, accent, r, 1, border_radius=9)
            _text(screen, key, (r.x + 9, r.y + 6), 13, accent, True)
            # Compact two-line wrap.
            f = _font(11)
            words = desc.split()
            line, lines = "", []
            for word in words:
                test = word if not line else line + " " + word
                if f.size(test)[0] <= r.width - 112:
                    line = test
                else:
                    lines.append(line); line = word
            if line: lines.append(line)
            for j, line in enumerate(lines[:2]):
                screen.blit(f.render(line, True, WHITE), (r.x + 82, r.y + 5 + j * 14))

        close_rect = pygame.Rect(panel.right - 112, panel.bottom - 43, 88, 30)
        _button(screen, close_rect, "CLOSE", CORAL)
        _text(screen, "ESC / H / F1 also closes", (panel.x + 25, panel.bottom - 36), 11, MUTED)
        pygame.display.flip()
        t += clock.tick(fps) / 1000.0
    return True


def save_prompt(screen, clock=None, fps=60):
    """Returns True to save, False to discard, None to keep editing."""
    clock = clock or pygame.time.Clock()
    running = True
    while running:
        sw, sh = screen.get_size()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_y, pygame.K_RETURN, pygame.K_KP_ENTER): return True
                if event.key in (pygame.K_n, pygame.K_ESCAPE): return False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if yes_rect.collidepoint(event.pos): return True
                if no_rect.collidepoint(event.pos): return False

        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((15, 6, 12, 205))
        screen.blit(shade, (0, 0))
        w, h = min(560, sw - 30), min(260, sh - 30)
        panel = pygame.Rect((sw-w)//2, (sh-h)//2, w, h)
        _panel(screen, panel)
        _text(screen, "UNSAVED CHANGES", (panel.x+28, panel.y+28), 24, CREAM, True)
        _text(screen, "This level has edits that have not been saved.", (panel.x+29, panel.y+75), 14, WHITE)
        _text(screen, "Save them before leaving the editor?", (panel.x+29, panel.y+101), 14, MUTED)
        yes_rect = pygame.Rect(panel.x+80, panel.bottom-72, 150, 42)
        no_rect = pygame.Rect(panel.right-230, panel.bottom-72, 150, 42)
        _button(screen, yes_rect, "YES • SAVE", GREEN)
        _button(screen, no_rect, "NO • DISCARD", CORAL)
        _text(screen, "Y / ENTER = yes     N / ESC = no", (panel.x+29, panel.bottom-28), 11, MUTED)
        pygame.display.flip()
        clock.tick(fps)
    return None


def applying_window(self, screen, clock=None, fps=60, saved=True, changes=None):
    """Short, animated feedback while editor caches/maps are rebuilt."""
    clock = clock or pygame.time.Clock()
    started = pygame.time.get_ticks()
    duration = 950
    changes = list(changes or [])
    while pygame.time.get_ticks() - started < duration or not self.env_ready:
        sw, sh = screen.get_size()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
        shade = pygame.Surface((sw, sh), pygame.SRCALPHA)
        shade.fill((15, 6, 12, 225))
        screen.blit(shade, (0, 0))
        w, h = min(610, sw-30), min(310, sh-30)
        panel = pygame.Rect((sw-w)//2, (sh-h)//2, w, h)
        _panel(screen, panel)
        elapsed = pygame.time.get_ticks() - started
        progress = min(1.0, elapsed / duration)
        _text(screen, "APPLYING WORLD CHANGES", (panel.x+28, panel.y+27), 22, CREAM, True)
        status = "Saving level data…" if saved else "Applying in-memory edits…"
        _text(screen, status, (panel.x+29, panel.y+69), 14, WHITE)
        _text(screen, "Refreshing maps, entities and editor caches", (panel.x+29, panel.y+94), 12, MUTED)
        bar = pygame.Rect(panel.x+29, panel.y+137, panel.width-58, 18)
        pygame.draw.rect(screen, (39,21,31), bar, border_radius=9)
        fill = bar.copy(); fill.width = max(2, int(bar.width*progress))
        pygame.draw.rect(screen, CORAL, fill, border_radius=9)
        if changes:
            shown = ", ".join(changes[:4])
            _text(screen, "Touched: " + shown, (panel.x+29, panel.y+178), 11, PURPLE)
        _text(screen, f"{int(progress*100):02d}%", (panel.right-72, panel.y+174), 13, GOLD, True)
        _text(screen, "Please wait…", (panel.x+29, panel.bottom-43), 12, MUTED)
        pygame.display.flip()
        clock.tick(fps)
    return True
