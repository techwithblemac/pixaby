import pygame
from game.ui.ui_theme import UITheme

class ObjectiveType:
    COLLECT = "collect"
    KILL = "kill"
    EXIT = "exit"

class Objective:
    def __init__(self, obj_type, description, target_count=1):
        self.type = obj_type
        self.description = description
        self.target = target_count
        self.current = 0
        self.complete = False

    def update(self, count=1):
        if self.complete: return
        self.current += count
        if self.current >= self.target:
            self.current = self.target
            self.complete = True

class ObjectiveManager:
    def __init__(self):
        self.objectives = []
        self.level_active = False

    def load_from_level(self, level_data):
        """Parses level JSON for objectives as per Step 2 design."""
        self.objectives = []
        
        # Example parsing logic based on standard level keys
        if "gems" in level_data:
            gem_count = len(level_data["gems"])
            self.objectives.append(Objective(ObjectiveType.COLLECT, "Collect all Gems", gem_count))
            
        if "enemies" in level_data:
            enemy_count = len(level_data["enemies"])
            self.objectives.append(Objective(ObjectiveType.KILL, "Defeat all Enemies", enemy_count))
            
        # Global requirement
        self.objectives.append(Objective(ObjectiveType.EXIT, "Reach the Exit Portal", 1))
        self.level_active = True

    def trigger(self, obj_type, amount=1):
        for obj in self.objectives:
            if obj.type == obj_type:
                obj.update(amount)

    def is_all_complete(self):
        return all(obj.complete for obj in self.objectives)

    def draw_hud(self, surface):
        if not self.objectives: return
        
        width, height = 250, 40 + (len(self.objectives) * 25)
        x, y = surface.get_width() - width - 20, 20
        
        UITheme.draw_panel(surface, pygame.Rect(x, y, width, height))
        UITheme.draw_text(surface, "MISSION DIRECTIVES", (x + 15, y + 10), size=20, color=UITheme.ACCENT_COLOR)
        
        for i, obj in enumerate(self.objectives):
            color = UITheme.SUCCESS_COLOR if obj.complete else UITheme.TEXT_MAIN
            status = "[X]" if obj.complete else "[ ]"
            text = f"{status} {obj.description}"
            if obj.target > 1:
                text += f" ({obj.current}/{obj.target})"
            
            UITheme.draw_text(surface, text, (x + 15, y + 40 + (i * 25)), size=16, color=color)
