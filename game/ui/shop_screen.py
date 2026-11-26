"""
shop_screen.py
==============
The between-levels shop: a blocking modal in the same Pixel Abyss style
(and the same "own little event loop" pattern) as ui_theme.confirm_dialog.

    open_shop(game)     call once when a level is completed; every local
                        human player gets a turn, then it returns

What is sold, what it costs and how it changes a player lives in
data/shop_items.py and scripts/shop_effects.py - this file only draws and
reads input. The animation toolkit (coins from Assets, particles, glow,
shake, easing) lives in ui_fx.py and the item icons in shop_icons.py.

Controls
--------
    Left / Right  (A / D, joystick hat)   switch currency tab
    Up / Down     (W / S, joystick hat)   select an item
    Enter / Space (joystick button 0)     buy the selected item
    Esc / C       (joystick button 1)     leave the shop
    Mouse / touch: hover or tap a row to select it, tap a tab, tap the
                   price to buy, tap CONTINUE to leave.

What you will see
-----------------
    * the panel pops in/out, rows slide in one after another on every tab
    * spinning coins (Assets.GEM_SPRITES) in the wallet, tabs, prices and a
      coin shower for what you are carrying when the shop opens
    * buying flies coins from your wallet to the item, bursts sparks, flashes
      the row, pops the new level pip, rolls the wallet number down and
      shakes the panel; a refused purchase shakes the row instead
    * a live HP bar + stat preview (what the selected item would change)
    * lantern-style glows that follow the selection and the active currency
"""

import math
import types

import pygame

from . import ui_theme as ui
from . import ui_fx as fx
from .shop_icons import draw_icon
from ..data.shop_items import CURRENCIES, TABS, items_for_tab
from ..scripts import shop_effects as rules
from ..scripts import achievements

COIN_COLORS = fx.COIN_COLORS
HINT = "Left/Right: tab    Up/Down: select    Enter: buy    Esc: continue"
MESSAGE_SECONDS = 2.5
GAIN_LABEL = {"heal": "HEALED", "boost": "NEXT FLOOR", "level": "UPGRADED", "charm": "STOCKED"}
OPEN_TIME = 0.34
CLOSE_TIME = 0.24


def _shoppers(game):
    local = [p for p in getattr(game, "local_players", []) if not getattr(p, "auto", False)]
    return local or list(getattr(game, "player_slots", []))[:1]


def open_shop(game):
    """Run the shop for every local human player, one after another."""
    shoppers = _shoppers(game)
    if not shoppers:
        return

    for number, player in enumerate(shoppers, start=1):
        # Boosts bought last time lasted exactly the level that just ended.
        player.boosts.clear()
        rules.apply_loadout(player)
        visit = _ShopVisit(game, player, number, len(shoppers))
        result = visit.run()
        achievements.tracker().on_shop_visit(player, visit.bought_any)
        if not result:
            break

    # The modal swallowed key-up events; don't let the game think a key is still held.
    game.keys = pygame.key.get_pressed()


def _preview(player, item):
    """What buying ``item`` would change: {'hp','max_hp','dmg','spd'} (only the keys that change)."""
    try:
        ok, _ = rules.status(player, item)
        if not ok:
            return None
        pv = {}
        if item["kind"] == "heal":
            pv["hp"] = min(player.max_health, player.health + player.max_health * item["heal_pct"])
            pv["max_hp"] = player.max_health
            return pv
        add = item.get("effects", {})
        now = rules.total_effects(player)
        if add.get("max_health"):
            pv["max_hp"] = player.max_health + add["max_health"]
            pv["hp"] = min(pv["max_hp"], player.health + add["max_health"])
        if add.get("attack_mult"):
            pv["dmg"] = player.attack_power / (1 + now["attack_mult"]) * (1 + now["attack_mult"] + add["attack_mult"])
        if add.get("speed_mult"):
            pv["spd"] = player.speed / (1 + now["speed_mult"]) * (1 + now["speed_mult"] + add["speed_mult"])
        return pv or None
    except Exception:
        return None


class _ShopVisit:
    """One player's visit to the shop."""

    def __init__(self, game, player, number, total):
        self.game, self.player, self.number, self.total = game, player, number, total
        self.snapshot = game.window.copy().convert()
        self.layer = fx.Layer()
        self.back, self.front, self.shake = fx.Particles(), fx.Particles(), fx.Shake()

        self.t = 0.0
        self.bought_any = False                          # for Window Shopper
        self.quit = False
        self.closing = None
        self.tab, self.selected = 0, 0
        self.tab_dir, self.tab_age = 1, -0.12          # rows wait a moment for the panel to pop in
        self.tab_color = COIN_COLORS[TABS[0]["color"]]
        self.tab_hot = [1.0 if i == 0 else 0.0 for i in range(len(TABS))]
        self.scroll, self.scroll_t = 0.0, 0.0           # rows scroll when a tab has more than fit
        self.ul_x = None

        self.hot, self.row_flash, self.row_shake, self.pip_pop = {}, {}, {}, {}
        self.shown = {c: float(rules.wallet(player, c)) for c in CURRENCIES}
        self.bump = {c: 0.0 for c in CURRENCIES}
        self.hp, self.hp_max = float(player.health), float(player.max_health)
        self.dmg, self.spd = float(player.attack_power), float(player.speed)
        self.preview = None

        self.message, self.message_ok, self.message_age = "", True, 99.0
        self.flash, self.flash_color = 0.0, ui.WHITE

        # a little shower of whatever you are carrying
        w = game.window.get_width()
        for cur in CURRENCIES:
            count = min(int(rules.wallet(player, cur)), 8)
            if count:
                self.front.shower(w, cur, count, size=24)
        fx.sfx(player, "open")

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _layout(self, items):
        w, h = self.game.window.get_size()
        sx, sy = self.shake.offset()
        box = pygame.Rect(0, 0, min(w - 20, 900), min(h - 20, 640))
        box.center = (w // 2, h // 2)
        box.move_ip(sx, sy)
        k = max(0.62, min(1.0, box.height / 560))
        pad = int(18 * k)

        title_y = box.top + int(pad * 0.7)
        wallet_y = box.top + pad + int(46 * k)
        tabs_y = wallet_y + int(34 * k)
        tab_h = int(34 * k)
        caption_y = tabs_y + tab_h + int(6 * k)
        rows_y = caption_y + int(20 * k)
        footer_h = int(52 * k)
        rows_h = box.bottom - pad - footer_h - rows_y
        row_h = max(44, min(int(84 * k), rows_h // max(1, len(items))))
        inner_w = box.width - pad * 2
        n = len(TABS)
        tab_w = inner_w // n
        coin_px = max(20, int(30 * k))
        buy_w = int(124 * k)

        L = types.SimpleNamespace()
        L.box, L.k, L.pad = box, k, pad
        L.title_y, L.wallet_y, L.tabs_y, L.tab_h, L.caption_y, L.rows_y = title_y, wallet_y, tabs_y, tab_h, caption_y, rows_y
        L.inner_w, L.coin_px, L.buy_w = inner_w, coin_px, buy_w
        L.tab_rects = [pygame.Rect(box.left + pad + i * tab_w, tabs_y, tab_w - 6, tab_h) for i in range(n)]
        L.row_h, L.rows_h = row_h, rows_h
        L.max_scroll = max(0, len(items) * row_h - rows_h)
        off = int(min(self.scroll, L.max_scroll))
        L.row_rects = [pygame.Rect(box.left + pad, rows_y + i * row_h - off, inner_w, row_h - 6) for i in range(len(items))]
        L.buy_rects = [pygame.Rect(r.right - buy_w - 8, r.top + 8, buy_w, r.height - 16) for r in L.row_rects]
        L.rows_clip = pygame.Rect(box.left + 2, rows_y - 6, box.width - 4, max(10, rows_h + 10))
        L.continue_rect = pygame.Rect(0, 0, int(min(260, inner_w * 0.4)), int(42 * k))
        L.continue_rect.bottomright = (box.right - pad, box.bottom - pad)
        chip_w = inner_w // len(CURRENCIES)
        L.chip_centers = [(box.left + pad + i * chip_w + coin_px // 2 + 4, wallet_y + int(12 * k)) for i in range(n)]
        bar_h = max(8, int(12 * k))
        L.hp_bar = pygame.Rect(box.left + pad, L.continue_rect.centery - bar_h // 2, int(150 * k), bar_h)
        return L

    # ------------------------------------------------------------------ #
    # input
    # ------------------------------------------------------------------ #
    def _select(self, index):
        if index != self.selected:
            self.selected = index
            fx.sfx(self.player, "button")

    def _set_tab(self, new, direction, L):
        if new == self.tab:
            return
        self.tab, self.selected, self.tab_dir, self.tab_age = new, 0, direction, 0.0
        self.scroll = self.scroll_t = 0.0
        fx.sfx(self.player, "button")
        c = L.tab_rects[new].center
        self.front.spark(c[0], c[1], COIN_COLORS[TABS[new]["color"]], count=10, speed=130, life=0.5, size=2)

    def _close(self):
        if self.closing is None:
            self.closing = 0.0
            fx.sfx(self.player, "back")

    def _events(self, items, L):
        n, cont = len(TABS), len(items)
        activate = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.game.running = False
                self.quit = True
                return
            if self.closing is not None:
                continue

            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_c):
                    self._close()
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    self._set_tab((self.tab - 1) % n, -1, L)
                elif event.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_TAB):
                    self._set_tab((self.tab + 1) % n, 1, L)
                elif event.key in (pygame.K_UP, pygame.K_w):
                    self._select((self.selected - 1) % (cont + 1))
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self._select((self.selected + 1) % (cont + 1))
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_e):
                    activate = True

            elif event.type == pygame.JOYHATMOTION:
                hx, hy = event.value
                if hx:
                    self._set_tab((self.tab + hx) % n, 1 if hx > 0 else -1, L)
                if hy:
                    self._select((self.selected - hy) % (cont + 1))

            elif event.type == pygame.JOYBUTTONDOWN:
                if event.button == 0:
                    activate = True
                elif event.button == 1:
                    self._close()

            elif event.type == pygame.MOUSEWHEEL:
                self._select(max(0, min(cont, self.selected - event.y)))

            elif event.type == pygame.MOUSEMOTION:
                for i, rect in enumerate(L.row_rects):
                    if rect.collidepoint(event.pos) and L.rows_clip.collidepoint(event.pos):
                        self._select(i)
                if L.continue_rect.collidepoint(event.pos):
                    self._select(cont)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if L.continue_rect.collidepoint(event.pos):
                    self._close()
                for i, rect in enumerate(L.tab_rects):
                    if rect.collidepoint(event.pos):
                        self._set_tab(i, 1 if i > self.tab else -1, L)
                for i, rect in enumerate(L.row_rects):
                    if rect.collidepoint(event.pos) and L.rows_clip.collidepoint(event.pos):
                        self._select(i)
                        if L.buy_rects[i].collidepoint(event.pos):
                            activate = True

        if activate and self.closing is None:
            self._activate(items, L)

    def _activate(self, items, L):
        cont = len(items)
        if self.selected >= cont:
            self._close()
            return

        player = self.player
        item = items[self.selected]
        cur = item["currency"]
        col = COIN_COLORS[cur]
        key = (TABS[self.tab]["id"], self.selected)
        cost = rules.price(player, item) or 0
        row, buy = L.row_rects[self.selected], L.buy_rects[self.selected]
        tile_c = (row.left + 8 + (row.height - 16) // 2, row.centery)

        ok, msg = rules.buy(player, item)
        self.message, self.message_ok, self.message_age = msg, ok, 0.0
        if ok:
            self.bought_any = True

        if not ok:                                              # refused: the row shakes its head
            self.row_shake[key] = 1.0
            self.shake.kick(2.0)
            self.flash, self.flash_color = 0.07, ui.CORAL
            self.front.spark(buy.centerx, buy.centery, ui.CORAL, count=8, speed=110, life=0.4, size=2)
            fx.sfx(player, "miss")
            return

        src = L.chip_centers[CURRENCIES.index(cur)]
        self.front.fly_coins(src, tile_c, cur, count=min(max(cost, 1), 7), size=22, dur=0.5)
        self.front.text(src[0] + 36, src[1] - 6, f"-{cost}", ui.CORAL, 20)
        self.front.text(row.centerx - 20, row.top + 6, GAIN_LABEL.get(item["kind"], "BOUGHT"), ui.GREEN, 18, life=1.3)
        self.front.spark(tile_c[0], tile_c[1], col, count=22, speed=230, life=0.7)
        self.front.ring(tile_c[0], tile_c[1], ui.WHITE, count=14, speed=170, life=0.45, size=2)
        self.row_flash[key] = 1.0
        self.bump[cur] = 1.0
        self.flash, self.flash_color = 0.16, col
        self.shake.kick(4.0)
        if item["kind"] == "level":
            self.pip_pop[(item["id"], rules.level_of(player, item) - 1)] = 0.0
        if item["kind"] == "heal" or item.get("effects", {}).get("max_health"):
            hb = L.hp_bar
            self.front.spark(hb.centerx, hb.centery, ui.RED, count=14, speed=150, life=0.6, size=3, gravity=-40)
            self.front.text(hb.right, hb.top - 8, "+HP", ui.GREEN, 16)
        fx.sfx(player, "coin")
        fx.sfx(player, "buy")

    # ------------------------------------------------------------------ #
    # simulation
    # ------------------------------------------------------------------ #
    def _update(self, dt, items, L):
        player, w = self.player, self.game.window.get_width()
        self.t += dt
        self.tab_age += dt
        self.message_age += dt
        if self.closing is not None:
            self.closing += dt
        self.shake.update(dt)
        self.flash = max(0.0, self.flash - dt * 2.2)

        self.tab_color = fx.lerp_color(self.tab_color, COIN_COLORS[TABS[self.tab]["color"]], min(1.0, dt * 9))
        for i in range(len(self.tab_hot)):
            self.tab_hot[i] = fx.smooth_to(self.tab_hot[i], 1.0 if i == self.tab else 0.0, dt, 14)
        target_x = L.tab_rects[self.tab].left
        self.ul_x = target_x if self.ul_x is None else fx.smooth_to(self.ul_x, target_x, dt, 16)

        tab_id = TABS[self.tab]["id"]
        # keep the selected row in view
        if self.selected >= len(items):
            self.scroll_t = L.max_scroll
        else:
            top = self.selected * L.row_h
            if top < self.scroll_t:
                self.scroll_t = top
            elif top + L.row_h > self.scroll_t + L.rows_h:
                self.scroll_t = top + L.row_h - L.rows_h
        self.scroll_t = max(0.0, min(float(L.max_scroll), self.scroll_t))
        self.scroll = fx.smooth_to(self.scroll, self.scroll_t, dt, 16)
        for i in range(len(items)):
            key = (tab_id, i)
            self.hot[key] = fx.smooth_to(self.hot.get(key, 0.0), 1.0 if i == self.selected else 0.0, dt, 14)
        for table, speed in ((self.row_flash, 2.6), (self.row_shake, 2.8)):
            for key in list(table):
                table[key] = max(0.0, table[key] - dt * speed)
        for key in list(self.pip_pop):
            self.pip_pop[key] += dt
            if self.pip_pop[key] > 0.6:
                del self.pip_pop[key]
        for c in CURRENCIES:
            self.shown[c] = fx.smooth_to(self.shown[c], float(rules.wallet(player, c)), dt, 9)
            self.bump[c] = max(0.0, self.bump[c] - dt * 3.2)

        self.hp = fx.smooth_to(self.hp, float(player.health), dt, 8)
        self.hp_max = fx.smooth_to(self.hp_max, float(player.max_health), dt, 8)
        self.dmg = fx.smooth_to(self.dmg, float(player.attack_power), dt, 8)
        self.spd = fx.smooth_to(self.spd, float(player.speed), dt, 8)
        self.preview = _preview(player, items[self.selected]) if self.selected < len(items) else None

        self.back.ambient(dt, w, self.game.window.get_height(), self.tab_color, rate=9.0)
        self.back.update(dt)
        self.front.update(dt)

    # ------------------------------------------------------------------ #
    # drawing
    # ------------------------------------------------------------------ #
    def _presence(self):
        if self.closing is None:
            return fx.ease_out_back(self.t / OPEN_TIME, 1.3)
        return 1.0 - fx.ease_in_out(self.closing / CLOSE_TIME)

    def _draw(self, items, L):
        window = self.game.window
        w, h = window.get_size()
        p = self._presence()
        bg = fx.clamp(self.t / 0.28) if self.closing is None else fx.clamp(p)

        window.blit(self.snapshot, (0, 0))
        ui.dim_overlay(window, int(205 * bg))
        self.back.draw(window, self.t)

        surf = self.layer.begin((w, h), L.box.inflate(100, 140))
        self._draw_panel(surf, items, L)
        self.layer.commit(window, p)

        self.front.draw(window, self.t)
        if self.flash > 0.02:
            ui.dim_overlay(window, int(110 * self.flash), self.flash_color)

    def _draw_panel(self, surf, items, L):
        player, t = self.player, self.t
        box, k, pad = L.box, L.k, L.pad
        tab_id = TABS[self.tab]["id"]
        breathe = fx.pulse(t, 0.45)

        fx.aura(surf, box, self.tab_color, 0.5 + 0.5 * breathe)
        ui.panel(surf, box, (30, 19, 26), fx.scale_color(fx.lerp_color(ui.CORAL, self.tab_color, 0.75), 0.8 + 0.2 * breathe), 2, 16)

        # ---- title ----
        star = int(28 * k)
        fx.draw_coin(surf, (box.left + pad + star // 2, L.title_y + int(14 * k)), "star", star, t, fps=8)
        fx.wave_text(surf, "ABYSS MARKET", (box.left + pad + star + 10, L.title_y), int(26 * k), ui.CREAM, ui.WHITE, t, amp=2.0)
        who = f"Player {self.number}/{self.total}   -   Floor {max(1, self.game.level - 1)} cleared" if self.total > 1 \
            else f"Floor {max(1, self.game.level - 1)} cleared   -   next: floor {self.game.level}"
        who_surf = ui.font(int(13 * k)).render(who, True, ui.MUTED)
        surf.blit(who_surf, (box.right - pad - who_surf.get_width(), L.title_y + int(8 * k)))
        ui.text(surf, HINT, (box.left + pad, L.title_y + int(30 * k)), int(11 * k), ui.MUTED)

        # ---- wallet: spinning coins from Assets, numbers that roll and pop ----
        for i, c in enumerate(CURRENCIES):
            cc = L.chip_centers[i]
            fx.draw_coin(surf, cc, c, L.coin_px, t, phase=i * 0.2, fps=12 if c == TABS[self.tab]["color"] else 7)
            b = self.bump[c]
            label = ui.font(int(18 * k * (1 + 0.4 * b)), True).render(
                f"x {int(round(self.shown[c]))}", True, fx.lerp_color(ui.CREAM if i == self.tab else ui.WHITE, ui.CORAL, b))
            surf.blit(label, (cc[0] + L.coin_px // 2 + 6, cc[1] - label.get_height() // 2))

        # ---- tabs ----
        mouse = pygame.mouse.get_pos()
        pulse = fx.pulse(t, 0.9)
        for i, rect in enumerate(L.tab_rects):
            c = TABS[i]["color"]
            col = COIN_COLORS[c]
            hot = max(self.tab_hot[i], 0.35 if rect.collidepoint(mouse) else 0.0)
            ui.panel(surf, rect, fx.lerp_color((48, 27, 36), (83, 37, 47), hot), fx.lerp_color((112, 64, 66), col, hot),
                     2 if hot > 0.5 else 1, 9)
            ico = max(16, int(rect.height * 0.7))
            fx.draw_coin(surf, (rect.left + ico // 2 + 8, rect.centery), c, ico, t, phase=i * 0.17, fps=4 + 9 * hot)
            ui.text_centered(surf, TABS[i]["label"], (rect.centerx + ico // 4, rect.centery), int(12 * k),
                             ui.CREAM if hot > 0.5 else ui.WHITE, True)
            affordable = sum(1 for it in items_for_tab(TABS[i]["id"]) if rules.status(player, it)[0])
            if affordable:
                bc, r = (rect.right - int(14 * k), rect.centery), int(8 * k + 1 + 1.5 * pulse)
                pygame.draw.circle(surf, ui.INK, bc, r + 2)
                pygame.draw.circle(surf, col, bc, r)
                ui.text_centered(surf, str(affordable), bc, int(11 * k), ui.INK, True)
        ul = pygame.Rect(int(self.ul_x), L.tabs_y + L.tab_h + 1, L.tab_rects[0].width, 3)
        pygame.draw.rect(surf, self.tab_color, ul, border_radius=2)
        self.layer.glow(ul.center, self.tab_color, 48, 0.55, clip=box)

        slide = int((1 - fx.ease_out_cubic(self.tab_age / 0.3)) * 14 * self.tab_dir)
        fx.text_alpha(surf, TABS[self.tab]["caption"], (box.left + pad + slide, L.caption_y), int(12 * k), ui.MUTED,
                      255 * fx.clamp(self.tab_age / 0.2), shadow=False)

        # ---- rows ----
        surf.set_clip(L.rows_clip)
        for i, item in enumerate(items):
            self._draw_row(surf, i, item, L, tab_id, COIN_COLORS[item["currency"]])
        surf.set_clip(None)

        self._draw_footer(surf, items, L, pulse)

    def _draw_row(self, surf, i, item, L, tab_id, col):
        k, t, player = L.k, self.t, self.player
        cur = item["currency"]                       # the price coin; the tab only decides where the row lives
        key = (tab_id, i)
        p = fx.clamp((self.tab_age - 0.05 * i) / 0.38)
        if p <= 0:
            return
        hot = self.hot.get(key, 0.0)
        ox = int((1 - fx.ease_out_back(p, 1.1)) * self.tab_dir * 80)
        ox += int(math.sin(t * 70) * 7 * self.row_shake.get(key, 0.0)) + int(hot * 5)
        rect, buy = L.row_rects[i].move(ox, 0), L.buy_rects[i].move(ox, 0)
        visible = L.rows_clip

        ui.panel(surf, rect, fx.lerp_color((44, 26, 34), (83, 37, 47), hot), fx.lerp_color((112, 64, 66), col, hot),
                 2 if hot > 0.4 else 1, 10)
        flash = self.row_flash.get(key, 0.0)
        if flash > 0.02:
            ui.panel(surf, rect, (*fx.lerp_color(col, ui.WHITE, 0.5), int(120 * flash)), None, 1, 10)

        th = rect.height - 16
        tile = pygame.Rect(rect.left + 8, rect.top + 8, th, th)
        if hot > 0.05:
            self.layer.glow(rect.center, col, max(rect.width // 3, 64), 0.22 * hot, clip=rect.clip(visible))
            self.layer.glow(tile.center, col, rect.height, 0.5 * hot, clip=rect.clip(visible))

        # icon tile
        ui.panel(surf, tile, fx.lerp_color((26, 16, 22), fx.scale_color(col, 0.35), 0.15 + 0.8 * hot),
                 fx.lerp_color((92, 60, 62), col, 0.4 + 0.6 * hot), 2 if hot > 0.5 else 1, 9)
        bob = int(math.sin(t * 3 + i) * 2 * hot)
        if not draw_icon(surf, item["id"], (tile.centerx, tile.centery + bob), th, t, hot):
            fx.draw_coin(surf, tile.center, cur, int(th * 0.6), t, fps=6 + 8 * hot)

        # name + level pips
        nx = tile.right + 12
        name_size = int(17 * k)
        ui.text(surf, item["name"], (nx, rect.top + int(7 * k)), name_size, ui.CREAM if hot > 0.3 else ui.WHITE, True)
        if item["kind"] == "level" and rules.max_level(item) > 1:
            lvl, pip = rules.level_of(player, item), int(9 * k)
            name_w = ui.font(name_size, True).size(item["name"])[0]
            for n in range(rules.max_level(item)):
                age = self.pip_pop.get((item["id"], n))
                grow = int(pip * 0.8 * (1 - age / 0.5)) if age is not None and age < 0.5 else 0
                pr = pygame.Rect(nx + name_w + 14 + n * (pip + 4) - grow // 2, rect.top + int(12 * k) - grow // 2,
                                 pip + grow, pip + grow)
                filled = n < lvl
                pygame.draw.rect(surf, col if filled else (108, 74, 82), pr, border_radius=2)
                if filled:
                    pygame.draw.rect(surf, fx.lerp_color(col, ui.WHITE, 0.55),
                                     (pr.left + 1, pr.top + 1, max(1, pr.width // 3), max(1, pr.height // 3)))

        if item["kind"] == "charm":                              # how many are carried
            have, cap = rules.stock_of(player, item), rules.stock_cap(player, item)
            name_w = ui.font(name_size, True).size(item["name"])[0]
            ui.text(surf, f"OWNED {have}/{cap}", (nx + name_w + 14, rect.top + int(10 * k)), int(12 * k),
                    col if have < cap else ui.CORAL, True)

        ro = rules.readout(player, item)                         # "Arrows per volley 3 > 4"
        if ro:
            rw_ = ui.font(int(12 * k), True).size(ro)[0]
            ui.text(surf, ro, (buy.left - rw_ - 14, rect.top + int(9 * k)), int(12 * k), ui.GREEN, True)

        # description
        y = rect.top + int(8 * k) + int(20 * k)
        for line in ui.wrap(item["desc"], max(40, buy.left - nx - 14), ui.font(int(12 * k)))[:2]:
            ui.text(surf, line, (nx, y), int(12 * k), ui.WHITE)
            y += int(16 * k)

        # price / buy box
        can_buy, why = rules.status(player, item)
        cost = rules.price(player, item)
        pulse = fx.pulse(t, 0.9)
        if can_buy:
            ui.panel(surf, buy, (52, 78, 52), fx.lerp_color(ui.GREEN, ui.WHITE, 0.4 * pulse), 2, 9)
            self.layer.glow(buy.center, ui.GREEN, buy.width, 0.18 + 0.22 * pulse, clip=buy.clip(visible))
        else:
            ui.panel(surf, buy, (40, 28, 34), (92, 60, 62), 1, 9)
        if why in ("MAX", "FULL", "ACTIVE", "DEAD"):
            ui.text_centered(surf, why, buy.center, int(14 * k), ui.MUTED, True)
        else:
            sub = buy.height >= 40
            cy = buy.centery - (int(7 * k) if sub else 0)
            fx.draw_coin(surf, (buy.left + int(22 * k), cy), cur, max(16, int(22 * k)), t, phase=i * 0.13,
                         fps=5 + (8 * hot if can_buy else 0))
            ui.text(surf, f"{cost}", (buy.left + int(38 * k), cy - int(10 * k)), int(18 * k),
                    ui.CREAM if can_buy else ui.CORAL, True)
            if sub:
                label = "BUY" if can_buy else f"need {max(0, cost - rules.wallet(player, cur))} more"
                ui.text_centered(surf, label, (buy.centerx, buy.bottom - int(11 * k)), int(11 * k),
                                 ui.GREEN if can_buy else ui.MUTED, True)

    def _draw_footer(self, surf, items, L, pulse):
        box, k, pad, t = L.box, L.k, L.pad, self.t
        cont = len(items)
        cr = L.continue_rect
        sel = self.selected == cont
        act = sel or cr.collidepoint(pygame.mouse.get_pos())

        ui.button(surf, cr, "CONTINUE", selected=sel, accent=ui.GREEN)
        bx = cr.right - int(22 * k) + int(math.sin(t * 5) * 3 * (1.0 if act else 0.4))
        pygame.draw.polygon(surf, ui.GREEN if act else ui.MUTED, [(bx - 5, cr.centery - 6), (bx + 3, cr.centery), (bx - 5, cr.centery + 6)])
        if act:
            self.layer.glow(cr.center, ui.GREEN, int(cr.width * 0.7), 0.2 + 0.12 * pulse, clip=cr.inflate(16, 16))

        # live HP bar with a ghost of what the selected item would add
        bar, pv = L.hp_bar, self.preview or {}
        ui.panel(surf, bar.inflate(4, 4), (40, 24, 30), (92, 60, 62), 1, 5)
        ratio = fx.clamp(self.hp / max(1.0, self.hp_max))
        fill_w = int(bar.width * ratio)
        hp_col = fx.lerp_color(ui.RED, ui.GREEN, ratio)
        if fill_w > 0:
            pygame.draw.rect(surf, hp_col, (bar.left, bar.top, fill_w, bar.height), border_radius=4)
            pygame.draw.rect(surf, fx.lerp_color(hp_col, ui.WHITE, 0.4),
                             (bar.left + 2, bar.top + 1, max(1, fill_w - 4), max(1, bar.height // 3)), border_radius=2)
        if "hp" in pv:
            new_w = int(bar.width * fx.clamp(pv["hp"] / max(1.0, pv.get("max_hp", self.hp_max))))
            if new_w > fill_w:
                ui.panel(surf, pygame.Rect(bar.left + fill_w, bar.top, new_w - fill_w, bar.height),
                         (255, 255, 255, int(70 + 90 * pulse)), None, 1, 4)

        x, y, size = bar.right + 12, cr.centery - int(7 * k), int(12 * k)
        limit = cr.left - 16

        def seg(txt, color):
            nonlocal x
            if x < limit:
                x += ui.text(surf, txt, (x, y), size, color).get_width()

        seg(f"HP {int(round(self.hp))}/{int(round(self.hp_max))}", ui.MUTED)
        if "hp" in pv and (pv["hp"] > self.hp + 0.5 or pv.get("max_hp", self.hp_max) > self.hp_max + 0.5):
            seg(f" > {int(pv['hp'])}/{int(pv.get('max_hp', self.hp_max))}", ui.GREEN)
        seg(f"    DMG {self.dmg:.1f}", ui.MUTED)
        if "dmg" in pv and pv["dmg"] > self.dmg + 0.04:
            seg(f" > {pv['dmg']:.1f}", ui.GREEN)
        seg(f"    SPD {int(round(self.spd))}", ui.MUTED)
        if "spd" in pv and pv["spd"] > self.spd + 0.5:
            seg(f" > {int(round(pv['spd']))}", ui.GREEN)

        if self.message and self.message_age < MESSAGE_SECONDS:
            rise = int(8 * fx.ease_out_cubic(self.message_age / 0.2))
            fx.text_alpha(surf, self.message, (box.left + pad, cr.top - int(20 * k) - rise), int(13 * k),
                          ui.GREEN if self.message_ok else ui.CORAL,
                          255 * fx.clamp((MESSAGE_SECONDS - self.message_age) / 0.5), True)

    # ------------------------------------------------------------------ #
    # main loop
    # ------------------------------------------------------------------ #
    def run(self):
        """Returns False if the game window was closed."""
        game, dt = self.game, 1 / 60
        while True:
            items = items_for_tab(TABS[self.tab]["id"])
            self.selected = max(0, min(self.selected, len(items)))
            L = self._layout(items)

            self._events(items, L)
            if self.quit:
                return False

            items = items_for_tab(TABS[self.tab]["id"])             # a tab switch changes the rows
            self.selected = max(0, min(self.selected, len(items)))
            L = self._layout(items)

            self._update(dt, items, L)
            if self.closing is not None and self.closing >= CLOSE_TIME:
                return True

            self._draw(items, L)
            pygame.display.flip()
            dt = min(0.05, game.clock.tick(getattr(game, "FPS", 60)) / 1000.0)
