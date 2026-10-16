#!/usr/bin/env python3
"""Render frames to PNG for visual inspection (dev tool, not part of the game)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).parent))

import pygame
import game as G

OUT = Path(os.environ.get("TEMP", "."))
W, H, Z = 1920, 1080, 4


def base_renderer(seed=7):
    pygame.init()
    pygame.display.set_mode((64, 64))
    g = G.Game(seed=seed)
    r = G.Renderer(g, W, H, Z)
    return g, r


def settle(g):
    """Age transient effects so they show at full opacity in a still frame."""
    for t in g.toasts:
        t["t"] = 0.6
    for f in g.floaters:
        f["t"] = 0.3


def shot_play():
    g, r = base_renderer()
    g.player["x"], g.player["y"] = 50.5, 31.5
    g.add_item("sword_iron", 1)
    g.player["equip"]["weapon"] = "sword_iron"
    g.player["equip"]["armor"] = "armor_leather"
    for i, item in enumerate(("ear", "potion", "herb", "axe_goblin")):
        g.drops.append({"x": 52 + i * 1.2, "y": 30.5, "t": 1.0, "kind": item, "count": 1})
    g.drops.append({"x": 52, "y": 33.5, "t": 1.0, "kind": "gold", "count": 9})
    g.update(1 / 60, {"down": False, "up": False, "left": False, "right": False})
    settle(g)
    screen = pygame.Surface((W, H))
    r.draw(screen)
    pygame.image.save(screen, OUT / "shot_play.png")
    print("saved play")


def shot_inventory():
    g, r = base_renderer()
    g.player["x"], g.player["y"] = 50.5, 31.5
    for item, n in (("potion", 3), ("herb", 2), ("ear", 7), ("axe_goblin", 1),
                    ("sword_iron", 1), ("armor_iron", 1), ("key", 1)):
        g.add_item(item, n)
    g.player["equip"]["weapon"] = "sword_iron"
    g.player["equip"]["armor"] = "armor_leather"
    g.show_inventory = True
    g.inv_cursor = 0
    g.update(1 / 60, {"down": False, "up": False, "left": False, "right": False})
    settle(g)
    screen = pygame.Surface((W, H))
    r.draw(screen)
    pygame.image.save(screen, OUT / "shot_inventory.png")
    print("saved inventory")


def shot_menu():
    g, r = base_renderer()
    screen = pygame.Surface((W, H))
    entries = [("Новая игра", True), ("Продолжить   — нет сохранения", False),
               ("Настройки", True), ("Выход", True)]
    r.draw_menu(screen, "Пиксельное приключение",
                "Большой мир • гоблины • квесты • навыки", entries, 0, 3.5,
                note="Стрелки / W S — выбор     Enter / Пробел — подтвердить     Esc — выход")
    pygame.image.save(screen, OUT / "shot_menu.png")
    print("saved menu")


def shot_world():
    g, r = base_renderer()
    g.player["x"], g.player["y"] = 30.0, 22.0
    screen = pygame.Surface((W, H))
    r.draw(screen)
    pygame.image.save(screen, OUT / "shot_world.png")
    print("saved world (lake area)")


if __name__ == "__main__":
    shot_menu()
    shot_play()
    shot_inventory()
    shot_world()
    pygame.quit()
