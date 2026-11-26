import pygame
from game.ui.ui_theme import UITheme

class OptimizedLevelRenderer:
    """
    Performance Best Practice: Bakes static tiles into a single surface 
    to avoid heavy draw calls in the main loop.
    """
    def __init__(self, tile_size=32):
        self.tile_size = tile_size
        self.baked_surface = None

    def bake(self, tile_map, assets):
        # tile_map is a 2D array of IDs
        rows = len(tile_map)
        cols = len(tile_map[0]) if rows > 0 else 0
        
        self.baked_surface = pygame.Surface((cols * self.tile_size, rows * self.tile_size), pygame.SRCALPHA)
        
        for y, row in enumerate(tile_map):
            for x, tile_id in enumerate(row):
                if tile_id in assets:
                    self.baked_surface.blit(assets[tile_id], (x * self.tile_size, y * self.tile_size))
        
        self.baked_surface = self.baked_surface.convert_alpha()

    def draw(self, surface, camera_offset=(0,0)):
        if self.baked_surface:
            surface.blit(self.baked_surface, camera_offset)
