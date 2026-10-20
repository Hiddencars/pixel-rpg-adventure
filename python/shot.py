#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render frames to PNG for visual inspection (dev tool, not part of the game)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pygame

import game as G
import render as R
import skills as SK
import world as WORLD

OUT = Path(os.environ.get("TEMP", "."))
W, H, Z = 1920, 1080, 2


def setup(seed=2026):
    pygame.init()
    pygame.display.set_mode((64, 64))
    g = G.Game(seed=seed, sound=False)
    r = R.Renderer(g, W, H, Z)
    return g, r


def settle(g):
    for t in g.toasts:
        t["t"] = 0.6
    for f in g.floaters:
        f["t"] = 0.3
    g.time = 3.0


def save(surf, name):
    pygame.image.save(surf, OUT / name)
    print("saved", name)


def shot_world():
    g, r = setup()
    vx, vy = G.VILLAGE_CENTER
    g.player["x"], g.player["y"] = vx + 1.0, vy + 2.0
    g.add_item("sword_steel", 1)
    g.player["equip"]["weapon"] = "sword_steel"
    g.player["equip"]["armor"] = "armor_iron"
    g.player["gold"] = 480
    for i, item in enumerate(("pelt", "tusk", "ore_iron", "gem_ruby")):
        g.drops.append({"x": vx + 4 + i * 1.3, "y": vy + 3.0, "t": 2.0, "kind": item, "count": 1})
    g.drops.append({"x": vx + 4, "y": vy + 5.0, "t": 2.0, "kind": "gold", "count": 14})
    g.update(1 / 60, {"down": False, "up": False, "left": False, "right": False})
    settle(g)
    surf = pygame.Surface((W, H))
    r.draw(surf)
    save(surf, "shot2_village.png")


def shot_wilds():
    g, r = setup()
    # stand in the forest next to monsters
    spot = None
    for m in g.mobs:
        if m["kind"] in ("wolf", "bear", "goblin") and m["alive"]:
            spot = m
            break
    if spot:
        g.player["x"], g.player["y"] = spot["x"] - 2.5, spot["y"]
    g.update(1 / 60, {"down": False, "up": False, "left": False, "right": False})
    for _ in range(30):
        g.update(1 / 60, {"down": False, "up": False, "left": False, "right": False})
    settle(g)
    surf = pygame.Surface((W, H))
    r.draw(surf)
    save(surf, "shot2_wilds.png")


def shot_inventory():
    g, r = setup()
    for item, n in (("potion", 5), ("potion_big", 2), ("mana_potion", 3), ("herb", 8),
                    ("pelt", 12), ("tusk", 6), ("ore_iron", 9), ("gem_ruby", 2),
                    ("sword_steel", 1), ("armor_iron", 1), ("ring_ruby", 1), ("soul", 4),
                    ("bone", 15), ("venom", 3), ("scroll", 1), ("meat", 2)):
        g.add_item(item, n)
    g.player["equip"]["weapon"] = "sword_steel"
    g.player["equip"]["armor"] = "armor_iron"
    g.player["equip"]["ring"] = "ring_ruby"
    g.overlay = "inventory"
    g.inv_cursor = 9
    settle(g)
    surf = pygame.Surface((W, H))
    r.draw(surf)
    save(surf, "shot2_inventory.png")


def shot_shop():
    g, r = setup()
    for item, n in (("pelt", 14), ("tusk", 8), ("ear", 22), ("ore_iron", 6),
                    ("bone", 18), ("venom", 5), ("gem_emerald", 2), ("cloth", 9)):
        g.add_item(item, n)
    g.player["gold"] = 640
    g.overlay = "shop"
    g.shop_tab = "sell"
    g.shop_cursor = 1
    settle(g)
    surf = pygame.Surface((W, H))
    r.draw(surf)
    save(surf, "shot2_shop.png")


def shot_tree():
    g, r = setup()
    # unlock a plausible mid-game build so the tree shows every state
    for node in SK.SKILLS:
        if node["tier"] <= 3 and node["lane"] == 1:
            g.skill_points += 6
            g.learn(node["id"])
    g.skill_points = 9
    g.tree_cursor = "blade_4_2"
    g.overlay = "skilltree"
    settle(g)
    surf = pygame.Surface((W, H))
    r.draw(surf)
    save(surf, "shot2_tree.png")


def shot_map():
    """Карта мира: проходим коридор, чтобы был виден туман войны."""
    g, r = setup()
    settle(g)
    p = g.player
    for _ in range(140):
        p["x"] = min(WORLD.MAP_W - 40, p["x"] + 18)
        p["y"] = min(WORLD.MAP_H - 40, p["y"] + 7)
        g.mark_explored()
    g.visited = {"village", "meadow", "forest"}
    g.overlay = "map"
    surf = pygame.Surface((W, H))
    r.draw(surf)
    save(surf, "shot2_map.png")


def shot_menu():
    g, r = setup()
    settle(g)
    surf = pygame.Surface((W, H))
    entries = [("Новая игра", True), ("Продолжить   — нет сохранения", False),
               ("Настройки", True), ("Выход", True)]
    r.draw_menu(surf, "Pixel patch",
                "Большой мир • 19 существ • 121 навык • торговля", entries, 0,
                note="Стрелки / W S — выбор     Enter — подтвердить     Esc — выход")
    save(surf, "shot2_menu.png")


if __name__ == "__main__":
    shot_menu()
    shot_world()
    shot_wilds()
    shot_inventory()
    shot_shop()
    shot_tree()
    shot_map()
    pygame.quit()
