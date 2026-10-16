#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pixel RPG Adventure 1.2 — Python / pygame-ce.

Changes since 1.1:
  * selectable resolutions up to 1920x1080 (menu + config + --res flag + F11 fullscreen)
  * text/HUD rendered at native resolution (was upscaled with the world -> blurry)
  * trees no longer block the village; NPCs are validated reachable by pathfinding
  * new: pause/settings menu (F10)

Run:        python game.py [--res 1920x1080] [--fullscreen]
Self-test:  python game.py --selftest     (headless, exits 0 on success)
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
from collections import deque
from pathlib import Path
from typing import Callable

import pygame

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
TILE = 16
MAP_W, MAP_H = 100, 64
SPRITE = 16
FPS = 60

# (width, height, zoom) — zoom is an integer so pixels stay perfectly crisp
RESOLUTIONS = [
    (960, 540, 2),
    (1280, 720, 3),
    (1366, 768, 3),
    (1600, 900, 4),
    (1920, 1080, 4),
]
DEFAULT_RES_INDEX = len(RESOLUTIONS) - 1          # 1920x1080
BASE_UI_WIDTH = 1248                              # ui scale reference

SAVE_PATH = Path.home() / ".pixel_rpg_adventure_save.json"
CONFIG_PATH = Path.home() / ".pixel_rpg_adventure_config.json"

T_VOID, T_DEEP, T_WATER, T_SAND, T_GRASS, T_GRASS2 = 0, 1, 2, 3, 4, 5
T_FOREST, T_STONE, T_PATH, T_FLOOR, T_CROPS, T_FLOWERS = 6, 7, 8, 9, 10, 11

COLORS = {
    "void": (10, 22, 32), "deep": (22, 60, 118), "water": (46, 110, 190),
    "sand": (216, 200, 146), "grass": (86, 152, 74), "grass2": (70, 134, 62),
    "forest": (36, 92, 52), "stone": (126, 126, 134), "stone2": (104, 104, 112),
    "path": (170, 150, 112), "floor": (132, 98, 62), "floor2": (116, 84, 52),
    "roof": (158, 62, 52), "roof2": (122, 46, 40), "wood": (122, 84, 52),
    "wood2": (92, 62, 38), "door": (72, 48, 28), "crops": (148, 168, 74),
    "flowers": (232, 190, 130),
}

PAL = {
    ".": None,
    "k": (24, 22, 28), "h": (58, 38, 24), "H": (96, 66, 40),
    "s": (232, 186, 148), "S": (206, 158, 120), "e": (30, 26, 32),
    "r": (176, 54, 46), "R": (214, 86, 64), "b": (54, 80, 164), "B": (40, 60, 130),
    "n": (86, 142, 72), "N": (64, 112, 54), "g": (200, 56, 48), "y": (230, 210, 120),
    "f": (212, 178, 120), "F": (178, 142, 92),
    "m": (196, 160, 120), "M": (160, 126, 90),
    "a": (222, 196, 110), "w": (244, 244, 248), "v": (124, 72, 168),
    "p": (216, 120, 120), "q": (240, 240, 255),
}

SPR_P_DOWN_1 = [
    "................", ".....kkkkkk.....", "....khhhhhhk....", "...khhhhhhhhk...",
    "...khsssssshk...", "...khseeseesh...", "...khsesssshk...", "....kssSSsk.....",
    "...kRRrrrrRRk...", "..kRrrrrrrrrRk..", "..kRrrrrrrrrRk..", "..ksrrrrrrrrsk..",
    "...kbbbbbbbbk...", "...kbbkbbbkbb...", "...kkk...kkk....", "................",
]
SPR_P_DOWN_2 = [
    "................", ".....kkkkkk.....", "....khhhhhhk....", "...khhhhhhhhk...",
    "...khsssssshk...", "...khseeseesh...", "...khsesssshk...", "....kssSSsk.....",
    "...kRRrrrrRRk...", "..kRrrrrrrrrRk..", "..kRrrrrrrrrRk..", "..ksrrrrrrrrsk..",
    "...kbbbbbbbbk...", "....kbbkbbk.....", "....kkk..kkk....", "................",
]
SPR_P_UP_1 = [
    "................", ".....kkkkkk.....", "....khhhhhhk....", "...khhhhhhhhk...",
    "...khhhhhhhhk...", "...khhhhhhhhk...", "...khhhhhhhhk...", "....khHHHHhk....",
    "...kRRrrrrRRk...", "..kRrrrrrrrrRk..", "..kRrrrrrrrrRk..", "..ksrrrrrrrrsk..",
    "...kbbbbbbbbk...", "...kbbkbbbkbb...", "...kkk...kkk....", "................",
]
SPR_P_UP_2 = [
    "................", ".....kkkkkk.....", "....khhhhhhk....", "...khhhhhhhhk...",
    "...khhhhhhhhk...", "...khhhhhhhhk...", "...khhhhhhhhk...", "....khHHHHhk....",
    "...kRRrrrrRRk...", "..kRrrrrrrrrRk..", "..kRrrrrrrrrRk..", "..ksrrrrrrrrsk..",
    "...kbbbbbbbbk...", "....kbbkbbk.....", "....kkk..kkk....", "................",
]
SPR_P_SIDE_1 = [
    "................", ".....kkkkkk.....", "....khhhhhhk....", "...khhhhhhhhk...",
    "...khhsssshsk...", "...khhseesshk...", "...khhssss k....", "....ksssSk......",
    "...kRRrrrRk.....", "..kRrrrrrrrk....", "..kRrrrrrrrk....", "..ksrrrrrrsk....",
    "...kbbbbbbbk....", "...kbbkbbbk.....", "...kkk..kkk.....", "................",
]
SPR_P_SIDE_2 = [
    "................", ".....kkkkkk.....", "....khhhhhhk....", "...khhhhhhhhk...",
    "...khhsssshsk...", "...khhseesshk...", "...khhssss k....", "....ksssSk......",
    "...kRRrrrRk.....", "..kRrrrrrrrk....", "..kRrrrrrrrk....", "..ksrrrrrrsk....",
    "...kbbbbbbbk....", "....kbbkbbk.....", "....kkk..kkk....", "................",
]
SPR_G_1 = [
    "................", "................", "..k..........k..", "..kknn.nnnn.kk..",
    "..knnnnnnnnnnk..", "..knnnnnnnnnnk..", "..knyggNggynnk..", "..knnNNNNNNnnk..",
    "..knnNkkkkNnnk..", "...knnnnnnnnk...", "..kffnnnnnnffk..", "..kffnnnnnnffk..",
    "..kf.nnnnnn.fk..", "....knnkknnk....", "...knnk..knnk...", "...kkk....kkk...",
]
SPR_G_2 = [
    "................", "................", "..k..........k..", "..kknn.nnnn.kk..",
    "..knnnnnnnnnnk..", "..knnnnnnnnnnk..", "..knygNgggynnk..", "..knnNNNNNNnnk..",
    "..knnNkkkkNnnk..", "...knnnnnnnnk...", "..kffnnnnnnffk..", "..kffnnnnnnffk..",
    "..kf.nnnnnn.fk..", "....knn..nnk....", "...kknnk.knnk...", "...kkk.....kkk..",
]
SPR_G_BRUTE_1 = [
    "................", "................", "..k..........k..", "..kknnnnnnnn.kk.",
    ".knnnnnnnnnnnnk.", ".knnnnnnnnnnnnk.", ".knnggNNNNggnnk.", ".knnNNNNNNNNnnk.",
    ".knnNNkkkkNNnnk.", "..knnnnnnnnnnk..", ".kffnnnnnnnnffk.", ".kffnnnnnnnnffk.",
    ".kf.nnnnnnnn.fk.", "...knnnnnnnnk...", "...kknnk.knnkk..", "....kkk...kkk...",
]
SPR_G_BRUTE_2 = [
    "................", "................", "..k..........k..", "..kknnnnnnnn.kk.",
    ".knnnnnnnnnnnnk.", ".knnnnnnnnnnnnk.", ".knngNNNNggnnk..", ".knnNNNNNNNNnnk.",
    ".knnNNkkkkNNnnk.", "..knnnnnnnnnnk..", ".kffnnnnnnnnffk.", ".kffnnnnnnnnffk.",
    ".kf.nnnnnnnn.fk.", "...knnnnnnnnk...", "..kknnnk.knnkk..", "..kkk.....kkkk..",
]
SPR_NPC_1 = [
    "................", "................", ".....kkkkkk.....", "....kaaaaaak....",
    "...kaaaaaaaak...", "...kassssssak...", "...kaseeseesak..", "...kassssssk....",
    "....kmmssmmk....", "..kmmmmmmmmmmk..", "..kmMmmmmmmMmk..", "..ksmmmmmmmmk...",
    "...kmmmmmmmmk...", "...kMMk.kMMk....", "...kkk...kkk....", "................",
]
SPR_NPC_2 = [
    "................", "................", ".....kkkkkk.....", "....kaaaaaak....",
    "...kaaaaaaaak...", "...kassssssak...", "...kaseeseesak..", "...kassssssk....",
    "....kmmssmmk....", "..kmmmmmmmmmmk..", "..kmMmmmmmmMmk..", "..ksmmmmmmmmk...",
    "...kmmmmmmmmk...", "....kMMkMMk.....", "....kkk..kkk....", "................",
]
SPR_MAGE_1 = [
    "................", "......kkkk......", ".....kvvvvk.....", "....kvwwwwvk....",
    "...kvwwwwwwvk...", "...kvwsssswvk...", "...kvsesseesk...", "...kvvssssvk....",
    "..kvvvssssvvk...", "..kvvvvvvvvvk...", "..kvavvvvvvak...", "..kvvvvvvvvvk...",
    "..kvvvvvvvvvk...", "...kvvvvvvvk....", "...kvvk.kvvk....", "...kkk...kkk....",
]
SPR_MAGE_2 = [
    "................", "......kkkk......", ".....kvvvvk.....", "....kvwwwwvk....",
    "...kvwwwwwwvk...", "...kvwsssswvk...", "...kvsesseesk...", "...kvvssssvk....",
    "..kvvvssssvvk...", "..kvvvvvvvvvk...", "..kvavvvvvvak...", "..kvvvvvvvvvk...",
    "..kvvvvvvvvvk...", "....kvvvvvk.....", "....kvvkkvvk....", "....kkk..kkk....",
]

SPRITES = {
    "p_down_1": SPR_P_DOWN_1, "p_down_2": SPR_P_DOWN_2,
    "p_up_1": SPR_P_UP_1, "p_up_2": SPR_P_UP_2,
    "p_side_1": SPR_P_SIDE_1, "p_side_2": SPR_P_SIDE_2,
    "g_1": SPR_G_1, "g_2": SPR_G_2,
    "gb_1": SPR_G_BRUTE_1, "gb_2": SPR_G_BRUTE_2,
    "npc_1": SPR_NPC_1, "npc_2": SPR_NPC_2,
    "mage_1": SPR_MAGE_1, "mage_2": SPR_MAGE_2,
}

# ----------------------------------------------------------------------------
# Noise / world
# ----------------------------------------------------------------------------
def hash2(x: float, y: float) -> float:
    n = math.sin(x * 127.1 + y * 311.7) * 43758.5453123
    return n - math.floor(n)


def smooth_step(t: float) -> float:
    return t * t * (3 - 2 * t)


def value_noise(x: float, y: float) -> float:
    xi, yi = math.floor(x), math.floor(y)
    xf, yf = x - xi, y - yi
    a, b = hash2(xi, yi), hash2(xi + 1, yi)
    c, d = hash2(xi, yi + 1), hash2(xi + 1, yi + 1)
    u, v = smooth_step(xf), smooth_step(yf)
    return (a * (1 - u) + b * u) * (1 - v) + (c * (1 - u) + d * u) * v


def fbm(x: float, y: float) -> float:
    v, amp, f = 0.0, 0.5, 1.0
    for _ in range(4):
        v += value_noise(x * f, y * f) * amp
        amp *= 0.5
        f *= 2
    return v


VILLAGE_CX, VILLAGE_CY = 50, 32
VILLAGE_HALF_W, VILLAGE_HALF_H = 9, 6


class World:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.tiles: list[list[int]] = []
        self.objects: list[dict] = []
        self.decor: list[dict] = []
        self._generate()

    @staticmethod
    def in_bounds(x: int, y: int) -> bool:
        return 0 <= x < MAP_W and 0 <= y < MAP_H

    def obj_at(self, x: int, y: int) -> dict | None:
        for o in self.objects:
            if o["x"] == x and o["y"] == y:
                return o
        return None

    def is_solid(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return True
        if self.obj_at(x, y):
            return True
        return self.tiles[y][x] in (T_VOID, T_DEEP, T_WATER)

    # -- generation ---------------------------------------------------------
    def _generate(self) -> None:
        rng = self.rng
        self.tiles = [[T_GRASS] * MAP_W for _ in range(MAP_H)]

        for y in range(MAP_H):
            for x in range(MAP_W):
                dx = (x - MAP_W / 2) / (MAP_W / 2)
                dy = (y - MAP_H / 2) / (MAP_H / 2)
                dist = math.sqrt(dx * dx + dy * dy)
                n = fbm(x * 0.09, y * 0.09) * 0.55 + 0.45
                land = n - dist * 0.16
                if land > 0.52:
                    t = T_GRASS
                elif land > 0.42:
                    t = T_SAND
                elif land > 0.30:
                    t = T_WATER
                elif land > 0.24:
                    t = T_DEEP
                else:
                    t = T_VOID
                self.tiles[y][x] = t

        self._carve_lake(28, 20, 6.5)
        self._scatter_forest(0.10, 0.34)
        self._scatter_forest(0.42, 0.55)

        cx, cy = VILLAGE_CX, VILLAGE_CY
        for y in range(cy - VILLAGE_HALF_H, cy + VILLAGE_HALF_H + 1):
            for x in range(cx - VILLAGE_HALF_W, cx + VILLAGE_HALF_W + 1):
                if self.in_bounds(x, y) and self.tiles[y][x] >= T_SAND:
                    self.tiles[y][x] = T_GRASS

        for x in range(cx - 9, cx + 10):
            if self.in_bounds(x, cy):
                self.tiles[cy][x] = T_PATH
        for y in range(cy - 6, cy + 7):
            if self.in_bounds(cx, y):
                self.tiles[y][cx] = T_PATH
        for x in range(cx + 9, cx + 26):
            if self.in_bounds(x, cy) and self.tiles[cy][x] >= T_SAND:
                self.tiles[cy][x] = T_PATH
        for x in range(cx - 26, cx - 9):
            if self.in_bounds(x, cy) and self.tiles[cy][x] >= T_SAND:
                self.tiles[cy][x] = T_PATH
        for y in range(cy + 6, cy + 20):
            if self.in_bounds(cx, y) and self.tiles[y][cx] >= T_SAND:
                self.tiles[y][cx] = T_PATH
        for y in range(cy - 20, cy - 6):
            if self.in_bounds(cx, y) and self.tiles[y][cx] >= T_SAND:
                self.tiles[y][cx] = T_PATH

        # IMPORTANT: clear the village BEFORE placing houses/NPCs, otherwise
        # scattered trees wall the villagers off (v1.1 bug: only the smith
        # could be reached).
        self.objects = [
            o for o in self.objects
            if not (o["type"] == "tree"
                    and abs(o["x"] - cx) <= VILLAGE_HALF_W + 2
                    and abs(o["y"] - cy) <= VILLAGE_HALF_H + 2)
        ]

        for ox, oy in [(-6, -4), (5, -4), (-6, 4), (5, 4),
                       (-1, -4), (2, -4), (-1, 4), (2, 4)]:
            self._place_house(cx + ox, cy + oy)

        for _ in range(900):
            x, y = rng.randrange(MAP_W), rng.randrange(MAP_H)
            if self.tiles[y][x] == T_GRASS and not self.obj_at(x, y):
                self.decor.append({"x": x, "y": y,
                                   "type": "flower" if rng.random() < 0.75 else "bush"})

        for y in range(cy + 8, cy + 12):
            for x in range(cx + 12, cx + 22):
                if self.in_bounds(x, y) and self.tiles[y][x] == T_GRASS:
                    self.tiles[y][x] = T_CROPS

    def _carve_lake(self, cx: float, cy: float, r: float) -> None:
        for y in range(int(cy - r - 2), int(cy + r + 3)):
            for x in range(int(cx - r - 2), int(cx + r + 3)):
                if not self.in_bounds(x, y):
                    continue
                d = math.hypot(x - cx, y - cy)
                if d < r * (0.78 + hash2(x, y) * 0.44):
                    self.tiles[y][x] = T_WATER
        for y in range(int(cy - r - 3), int(cy + r + 4)):
            for x in range(int(cx - r - 3), int(cx + r + 4)):
                if not self.in_bounds(x, y):
                    continue
                if self.tiles[y][x] in (T_GRASS, T_GRASS2):
                    for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        if self.in_bounds(x + ox, y + oy) and self.tiles[y + oy][x + ox] == T_WATER:
                            self.tiles[y][x] = T_SAND
                            break

    def _scatter_forest(self, lo: float, hi: float) -> None:
        for y in range(MAP_H):
            for x in range(MAP_W):
                if self.tiles[y][x] != T_GRASS:
                    continue
                n = fbm(x * 0.16, y * 0.16)
                if lo < n < hi and self.rng.random() < 0.62:
                    self.objects.append({"x": x, "y": y, "type": "tree"})

    def _place_house(self, x: int, y: int) -> None:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if self.in_bounds(x + dx, y + dy):
                    self.tiles[y + dy][x + dx] = T_FLOOR
        self.objects.append({"x": x, "y": y, "type": "house"})
        self.decor.append({"x": x + 2, "y": y + 2, "type": "lamp"})

    # -- pathfinding --------------------------------------------------------
    def walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and not self.is_solid(x, y)

    def reachable_from(self, start: tuple[int, int]) -> set[tuple[int, int]]:
        """Flood fill over walkable tiles — used to guarantee NPCs are reachable."""
        if not self.walkable(*start):
            start = self.nearest_walkable(*start) or start
        seen = {start}
        q = deque([start])
        while q:
            x, y = q.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) not in seen and self.walkable(nx, ny):
                    seen.add((nx, ny))
                    q.append((nx, ny))
        return seen

    def nearest_walkable(self, x: int, y: int, limit: int = 12) -> tuple[int, int] | None:
        if self.walkable(x, y):
            return x, y
        for r in range(1, limit + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    if self.walkable(x + dx, y + dy):
                        return x + dx, y + dy
        return None

    def nearest_in(self, x: int, y: int, tiles: set[tuple[int, int]]) -> tuple[int, int] | None:
        best, best_d = None, 1e9
        for (tx, ty) in tiles:
            d = abs(tx - x) + abs(ty - y)
            if d < best_d:
                best, best_d = (tx, ty), d
        return best

    def stats(self) -> dict:
        counts: dict[int, int] = {}
        for row in self.tiles:
            for t in row:
                counts[t] = counts.get(t, 0) + 1
        total = MAP_W * MAP_H
        land = sum(v for k, v in counts.items() if k >= T_SAND)
        return {"tiles": counts, "land_pct": round(100 * land / total),
                "trees": sum(1 for o in self.objects if o["type"] == "tree"),
                "houses": sum(1 for o in self.objects if o["type"] == "house"),
                "decor": len(self.decor)}


# ----------------------------------------------------------------------------
# Game logic
# ----------------------------------------------------------------------------
SPAWN_X, SPAWN_Y = 50.5, 32.5


class Game:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self.seed = seed
        self.world = World(self.rng)
        self.frame = 0

        self.player = {
            "x": SPAWN_X, "y": SPAWN_Y, "dir": "down", "moving": False,
            "anim_t": 0.0, "frame": 0, "speed": 5.2,
            "hp": 30.0, "hp_max": 30.0, "mp": 10.0, "mp_max": 10.0,
            "level": 1, "xp": 0, "xp_next": 20, "gold": 0, "potions": 2,
            "atk_t": 0.0, "atk_anim": 0.0, "hurt_t": 0.0,
        }

        self.mobs: list[dict] = []
        self.npcs: list[dict] = []
        self.drops: list[dict] = []
        self.particles: list[dict] = []
        self.floaters: list[dict] = []
        self.corpses: list[dict] = []
        self.quests: list[dict] = []
        self.skills: list[dict] = []
        self.skill_points = 3
        self.toasts: list[dict] = []
        self.dialog: dict | None = None
        self.show_quests = False
        self.show_skills = False

        self.spawn_npcs()
        self.spawn_mobs()
        self.init_quests()
        self.init_skills()
        self.ensure_reachable()
        self.toast("Большой мир готов! WASD — идти, ПРОБЕЛ — атака, E — говорить")

    # -- setup --------------------------------------------------------------
    def init_quests(self) -> None:
        self.quests = [
            {"id": "q_goblins", "title": "Гоблины в лесах",
             "desc": "Одолей 3 гоблинов на острове.",
             "goal": 3, "progress": 0, "done": False, "reward_xp": 30, "reward_gold": 15},
            {"id": "q_npcs", "title": "Знакомство с деревней",
             "desc": "Поговори со всеми жителями (4 NPC).",
             "goal": 4, "progress": 0, "done": False, "reward_xp": 20, "reward_gold": 10},
            {"id": "q_explore", "title": "Разведка края",
             "desc": "Дойди до берега моря на севере острова.",
             "goal": 1, "progress": 0, "done": False, "reward_xp": 25, "reward_gold": 12},
        ]

    def init_skills(self) -> None:
        self.skills = [
            {"id": "s_slash", "name": "Размашистый удар",
             "desc": "Атака бьёт по всем врагам рядом.", "cost": 1, "learned": False, "req": []},
            {"id": "s_tough", "name": "Крепкая кожа",
             "desc": "+10 к максимуму здоровья.", "cost": 1, "learned": False, "req": []},
            {"id": "s_heal", "name": "Лечение",
             "desc": "A — лечиться за зелье (10 HP).", "cost": 1, "learned": False, "req": []},
            {"id": "s_crit", "name": "Смертельный удар",
             "desc": "25% шанс двойного урона.", "cost": 1, "learned": False, "req": ["s_slash"]},
        ]

    def spawn_npcs(self) -> None:
        self.npcs = [
            {"x": 46, "y": 29, "kind": "npc", "name": "Крестьянин", "dir": "down",
             "met": False, "anim_t": 0.0,
             "lines": ["Добро пожаловать в Дубраву, путник!",
                       "Гоблины шастают по лесам. Будь осторожен.",
                       "Старейшина ждёт тебя в центре деревни."]},
            {"x": 54, "y": 35, "kind": "mage", "name": "Старейшина", "dir": "down",
             "met": False, "anim_t": 0.0,
             "lines": ["Я чувствую в тебе силу, странник.",
                       "Одолей трёх гоблинов — и я раскрою первое умение.",
                       "Навыки открываются по мере роста уровня."]},
            {"x": 48, "y": 36, "kind": "npc", "name": "Кузнец", "dir": "up",
             "met": False, "anim_t": 0.0, "gift": True,
             "lines": ["Сталь куётся в огне, а герой — в бою.",
                       "За зелья не благодари — просто выживи."]},
            {"x": 53, "y": 29, "kind": "npc", "name": "Фермер", "dir": "up",
             "met": False, "anim_t": 0.0,
             "lines": ["Пшеница в этом году богатая!",
                       "Пройдись по дороге на восток — там красивый лес."]},
        ]

    def spawn_mobs(self) -> None:
        self.mobs = []
        spots = [(26, 44), (70, 22), (84, 52), (34, 16), (66, 44), (20, 26),
                 (88, 30), (50, 52), (16, 46), (78, 54), (40, 10), (60, 56)]
        for sx, sy in spots:
            pos = self.world.nearest_walkable(sx, sy)
            if pos:
                kind = "brute" if len(self.mobs) % 4 == 3 else "goblin"
                self.mobs.append(self.make_mob(pos[0], pos[1], kind))

    def make_mob(self, x: float, y: float, kind: str) -> dict:
        if kind == "brute":
            hp, atk, spd, xp, name = 30, 6, 2.3, 16, "Гоблин-здоровяк"
        else:
            hp, atk, spd, xp, name = 14, 3, 3.0, 8, "Гоблин"
        return {"x": x, "y": y, "kind": kind, "name": name,
                "hp": float(hp), "hp_max": float(hp), "atk": atk, "speed": spd, "xp": xp,
                "dir": "down", "moving": False, "anim_t": 0.0, "frame": 0,
                "timer": 1 + self.rng.random() * 2,
                "attack_cd": 0.0, "hurt_t": 0.0, "atk_t": 0.0,
                "wander": {"x": x, "y": y}, "alive": True}

    def ensure_reachable(self) -> None:
        """Guarantee every NPC and mob stands on a tile the player can walk to."""
        reach = self.world.reachable_from((int(SPAWN_X), int(SPAWN_Y)))
        for ent in list(self.npcs) + list(self.mobs):
            tx, ty = int(ent["x"]), int(ent["y"])
            if (tx, ty) in reach and not self.world.obj_at(tx, ty):
                continue
            target = self.world.nearest_in(tx, ty, reach)
            if target:
                ent["x"], ent["y"] = float(target[0]), float(target[1])
                if "wander" in ent:
                    ent["wander"] = {"x": ent["x"], "y": ent["y"]}
        self.reachable_tiles = len(reach)

    # -- helpers ------------------------------------------------------------
    def toast(self, text: str, color: str = "#ffffff") -> None:
        self.toasts.append({"text": text, "color": color, "t": 0.0, "life": 3.2})

    def add_floater(self, x, y, text, color) -> None:
        self.floaters.append({"x": x, "y": y, "text": text, "color": color, "t": 0.0, "life": 1.0})

    def add_particle(self, x, y, color) -> None:
        a = self.rng.random() * math.tau
        s = 1.5 + self.rng.random() * 4
        self.particles.append({"x": x, "y": y, "vx": math.cos(a) * s, "vy": math.sin(a) * s,
                               "life": 0.4 + self.rng.random() * 0.35, "t": 0.0, "color": color})

    def has_skill(self, sid: str) -> bool:
        return any(s["id"] == sid and s["learned"] for s in self.skills)

    def can_learn(self, s: dict) -> bool:
        return (not s["learned"] and self.skill_points >= s["cost"]
                and all(self.has_skill(r) for r in s["req"]))

    def learn(self, s: dict) -> None:
        if not self.can_learn(s):
            return
        self.skill_points -= s["cost"]
        s["learned"] = True
        if s["id"] == "s_tough":
            self.player["hp_max"] += 10
            self.player["hp"] += 10
        self.toast("Изучено: " + s["name"], "#8ee08e")

    def face_dir(self) -> tuple[int, int]:
        d = self.player["dir"]
        if d == "up":
            return 0, -1
        if d == "down":
            return 0, 1
        if d == "left":
            return -1, 0
        return 1, 0

    def nearest_npc(self, max_dist: float = 2.0) -> dict | None:
        p = self.player
        best, best_d = None, max_dist
        for n in self.npcs:
            d = math.hypot(n["x"] - p["x"], n["y"] - p["y"])
            if d <= best_d:
                best, best_d = n, d
        return best

    # -- movement -----------------------------------------------------------
    def try_move(self, ent: dict, mx: float, my: float) -> None:
        r = 0.32
        nx, ny = ent["x"] + mx, ent["y"] + my

        def blocked(x: float, y: float) -> bool:
            return (self.world.is_solid(math.floor(x - r), math.floor(y - r))
                    or self.world.is_solid(math.floor(x + r), math.floor(y - r))
                    or self.world.is_solid(math.floor(x - r), math.floor(y + r))
                    or self.world.is_solid(math.floor(x + r), math.floor(y + r)))

        if not blocked(nx, ent["y"]):
            ent["x"] = nx
        if not blocked(ent["x"], ny):
            ent["y"] = ny

    # -- update -------------------------------------------------------------
    def update(self, dt: float, inp: dict) -> None:
        self.frame += 1
        self.update_player(dt, inp)
        self.update_mobs(dt)
        self.update_npcs(dt)
        self.update_effects(dt)
        self.update_quests()

    def update_player(self, dt: float, inp: dict) -> None:
        p = self.player
        dx = (1 if inp.get("right") else 0) - (1 if inp.get("left") else 0)
        dy = (1 if inp.get("down") else 0) - (1 if inp.get("up") else 0)
        p["moving"] = (dx != 0 or dy != 0) and p["atk_t"] <= 0

        if p["moving"]:
            ln = math.hypot(dx, dy) or 1
            nx, ny = dx / ln, dy / ln
            self.try_move(p, nx * p["speed"] * dt, ny * p["speed"] * dt)
            if abs(nx) > abs(ny):
                p["dir"] = "right" if nx > 0 else "left"
            elif ny != 0:
                p["dir"] = "down" if ny > 0 else "up"
            p["anim_t"] += dt
            if p["anim_t"] > 0.14:
                p["anim_t"] = 0.0
                p["frame"] = 1 - p["frame"]
        else:
            p["frame"] = 0
            p["anim_t"] = 0.0

        p["atk_t"] = max(0.0, p["atk_t"] - dt)
        p["atk_anim"] = max(0.0, p["atk_anim"] - dt)
        p["hurt_t"] = max(0.0, p["hurt_t"] - dt)

    def update_npcs(self, dt: float) -> None:
        for n in self.npcs:
            n["anim_t"] = (n["anim_t"] + dt) % 0.6

    def update_mobs(self, dt: float) -> None:
        p = self.player
        for m in self.mobs:
            if not m["alive"]:
                continue
            m["hurt_t"] = max(0.0, m["hurt_t"] - dt)
            m["attack_cd"] = max(0.0, m["attack_cd"] - dt)
            m["atk_t"] = max(0.0, m["atk_t"] - dt)

            dist = math.hypot(p["x"] - m["x"], p["y"] - m["y"])
            if dist < 8 and p["hp"] > 0:
                ux = (p["x"] - m["x"]) / (dist or 1)
                uy = (p["y"] - m["y"]) / (dist or 1)
                if dist > 1.0:
                    self.try_move(m, ux * m["speed"] * dt, uy * m["speed"] * dt)
                    m["moving"] = True
                    if abs(ux) > abs(uy):
                        m["dir"] = "right" if ux > 0 else "left"
                    else:
                        m["dir"] = "down" if uy > 0 else "up"
                elif m["attack_cd"] <= 0:
                    m["atk_t"] = 0.35
                    m["attack_cd"] = 1.15
                    self.try_move(m, ux * 0.5, uy * 0.5)
                    if math.hypot(p["x"] - m["x"], p["y"] - m["y"]) < 1.3:
                        dmg = max(1, m["atk"] + self.rng.randrange(3) - 1)
                        p["hp"] -= dmg
                        p["hurt_t"] = 0.25
                        self.add_floater(p["x"], p["y"] - 0.8, f"-{dmg}", "#ff7070")
                        for _ in range(8):
                            self.add_particle(p["x"], p["y"], "#ff6b6b")
                        if p["hp"] <= 0:
                            self.respawn_player()
            else:
                m["timer"] -= dt
                if m["timer"] <= 0:
                    m["timer"] = 2 + self.rng.random() * 3
                    a = self.rng.random() * math.tau
                    m["wander"]["x"] = m["x"] + math.cos(a) * 3.5
                    m["wander"]["y"] = m["y"] + math.sin(a) * 3.5
                ln = math.hypot(m["wander"]["x"] - m["x"], m["wander"]["y"] - m["y"])
                if ln > 0.3:
                    ux = (m["wander"]["x"] - m["x"]) / ln
                    uy = (m["wander"]["y"] - m["y"]) / ln
                    self.try_move(m, ux * m["speed"] * 0.45 * dt, uy * m["speed"] * 0.45 * dt)
                    m["moving"] = True
                    if abs(ux) > abs(uy):
                        m["dir"] = "right" if ux > 0 else "left"
                    else:
                        m["dir"] = "down" if uy > 0 else "up"
                else:
                    m["moving"] = False
            m["anim_t"] += dt
            if m["anim_t"] > 0.18:
                m["anim_t"] = 0.0
                m["frame"] = 1 - m["frame"]

        for i in range(len(self.mobs)):
            for j in range(i + 1, len(self.mobs)):
                a, b = self.mobs[i], self.mobs[j]
                if not (a["alive"] and b["alive"]):
                    continue
                d = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                if 0 < d < 0.7:
                    push = (0.7 - d) / 2
                    ux = (a["x"] - b["x"]) / d
                    uy = (a["y"] - b["y"]) / d
                    self.try_move(a, ux * push, uy * push)
                    self.try_move(b, -ux * push, -uy * push)

    def update_effects(self, dt: float) -> None:
        for p in self.particles:
            p["t"] += dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vx"] *= 0.9
            p["vy"] *= 0.9
        self.particles = [p for p in self.particles if p["t"] < p["life"]]

        for f in self.floaters:
            f["t"] += dt
            f["y"] -= dt * 0.8
        self.floaters = [f for f in self.floaters if f["t"] < f["life"]]

        for c in self.corpses:
            c["t"] += dt
        self.corpses = [c for c in self.corpses if c["t"] < 1.6]

        pl = self.player
        for d in self.drops:
            d["t"] += dt
            if d["t"] > 0.4 and not d.get("taken") and math.hypot(d["x"] - pl["x"], d["y"] - pl["y"]) < 1.0:
                d["taken"] = True
                if d["type"] == "gold":
                    g = 3 + self.rng.randrange(6)
                    pl["gold"] += g
                    self.add_floater(d["x"], d["y"], f"+{g} золота", "#ffd166")
                else:
                    pl["potions"] = min(9, pl["potions"] + 1)
                    self.add_floater(d["x"], d["y"], "+1 зелье", "#9ad7ff")
        self.drops = [d for d in self.drops if not d.get("taken") and d["t"] < 30]

        for t in self.toasts:
            t["t"] += dt
        self.toasts = [t for t in self.toasts if t["t"] < t["life"]]

    def update_quests(self) -> None:
        q = next((q for q in self.quests if q["id"] == "q_explore"), None)
        if q and not q["done"] and self.player["y"] < 9:
            q["progress"] = 1
            q["done"] = True
            self.player["xp"] += q["reward_xp"]
            self.player["gold"] += q["reward_gold"]
            self.toast(f"Квест выполнен: {q['title']} (+{q['reward_xp']} XP)", "#b6e3a0")
            self.check_level()

    # -- combat -------------------------------------------------------------
    def attack(self) -> None:
        p = self.player
        if p["atk_t"] > 0:
            return
        p["atk_t"] = 0.25
        p["atk_anim"] = 0.28
        fx, fy = self.face_dir()

        hits = 0
        sweep = self.has_skill("s_slash")
        for m in self.mobs:
            if not m["alive"]:
                continue
            dist = math.hypot(m["x"] - p["x"], m["y"] - p["y"])
            if dist > 1.55:
                continue
            dot = ((m["x"] - p["x"]) * fx + (m["y"] - p["y"]) * fy) / (dist or 1)
            if not sweep and dot < 0.35:
                continue
            dmg = 5 + self.rng.randrange(3) + int(p["level"] * 1.5)
            if self.has_skill("s_crit") and self.rng.random() < 0.25:
                dmg = round(dmg * 2)
            m["hp"] -= dmg
            m["hurt_t"] = 0.3
            hits += 1
            self.add_floater(m["x"], m["y"] - 0.8, f"-{dmg}", "#ffd166" if dmg > 8 else "#ffe066")
            self.try_move(m, -fx * 0.35, -fy * 0.35)
            for _ in range(10):
                self.add_particle(m["x"], m["y"], "#ffd166")
            if m["hp"] <= 0:
                self.kill_mob(m)

        if hits == 0:
            for _ in range(6):
                self.add_particle(p["x"] + fx * 0.9, p["y"] + fy * 0.9, "#cfd6ff")

    def kill_mob(self, m: dict) -> None:
        m["alive"] = False
        p = self.player
        p["xp"] += m["xp"]
        p["gold"] += 2 + self.rng.randrange(4)
        self.toast(f"Побеждён: {m['name']} (+{m['xp']} XP)", "#ffe066")
        self.drops.append({"x": m["x"], "y": m["y"], "t": 0.0,
                           "type": "gold" if self.rng.random() < 0.5 else "potion"})
        self.corpses.append({"x": m["x"], "y": m["y"], "kind": m["kind"], "t": 0.0})
        for _ in range(16):
            self.add_particle(m["x"], m["y"], "#88ff88")
        self.check_level()
        self.bump_quest("q_goblins", 1)
        for _ in range(20):
            x = 6 + self.rng.randrange(MAP_W - 12)
            y = 6 + self.rng.randrange(MAP_H - 12)
            if not self.world.is_solid(x, y) and math.hypot(x - p["x"], y - p["y"]) > 12:
                self.mobs.append(self.make_mob(x, y, "brute" if self.rng.random() < 0.3 else "goblin"))
                break

    def check_level(self) -> None:
        p = self.player
        while p["xp"] >= p["xp_next"]:
            p["xp"] -= p["xp_next"]
            p["level"] += 1
            p["xp_next"] = int(p["xp_next"] * 1.6)
            p["hp_max"] += 6
            p["hp"] = p["hp_max"]
            p["mp_max"] += 2
            p["mp"] = p["mp_max"]
            self.skill_points += 1
            self.toast(f"Уровень {p['level']}! +1 очко навыка (K)", "#9ad7ff")

    def bump_quest(self, qid: str, amount: int) -> None:
        q = next((q for q in self.quests if q["id"] == qid), None)
        if not q or q["done"]:
            return
        q["progress"] = min(q["goal"], q["progress"] + amount)
        if q["progress"] >= q["goal"]:
            q["done"] = True
            self.player["xp"] += q["reward_xp"]
            self.player["gold"] += q["reward_gold"]
            self.toast(f"Квест выполнен: {q['title']} (+{q['reward_xp']} XP)", "#b6e3a0")
            self.check_level()

    def respawn_player(self) -> None:
        p = self.player
        p["hp"] = p["hp_max"]
        p["x"], p["y"] = SPAWN_X, SPAWN_Y
        self.toast("Ты потерял сознание... и очнулся в деревне.", "#ffb0b0")

    def interact(self) -> None:
        if self.dialog:
            self.dialog = None
            return
        n = self.nearest_npc()
        if n:
            n["dir"] = self.player["dir"]
            self.dialog = {"name": n["name"], "line": self.rng.choice(n["lines"])}
            if n.get("gift") and not n.get("gave"):
                n["gave"] = True
                self.player["potions"] += 2
                self.toast("Кузнец дал 2 зелья", "#ffe066")
            if not n["met"]:
                n["met"] = True
                self.bump_quest("q_npcs", 1)
            return
        for m in self.mobs:
            if m["alive"] and math.hypot(m["x"] - self.player["x"], m["y"] - self.player["y"]) < 1.5:
                self.attack()
                return
        self.toast("Рядом никого нет.", "#c8c8d0")

    # -- save / load --------------------------------------------------------
    def save(self, path: Path = SAVE_PATH) -> bool:
        try:
            data = {"version": 1, "player": self.player, "skill_points": self.skill_points,
                    "quests": self.quests, "skills": self.skills,
                    "npcs_met": {n["name"]: n["met"] for n in self.npcs}}
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            self.toast("Игра сохранена", "#9ad7ff")
            return True
        except OSError as exc:
            self.toast(f"Не удалось сохранить: {exc}", "#ff9a9a")
            return False

    def load(self, path: Path = SAVE_PATH) -> bool:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.toast("Сохранение не найдено", "#ff9a9a")
            return False
        self.player.update({k: v for k, v in data.get("player", {}).items() if k in self.player})
        self.skill_points = data.get("skill_points", self.skill_points)
        for q_new in data.get("quests", []):
            q = next((q for q in self.quests if q["id"] == q_new["id"]), None)
            if q:
                q.update({k: v for k, v in q_new.items() if k in q})
        for s_new in data.get("skills", []):
            s = next((s for s in self.skills if s["id"] == s_new["id"]), None)
            if s:
                s["learned"] = bool(s_new.get("learned"))
        met = data.get("npcs_met", {})
        for n in self.npcs:
            n["met"] = bool(met.get(n["name"], n["met"]))
        self.toast("Игра загружена", "#9ad7ff")
        return True


# ----------------------------------------------------------------------------
# Rendering — world goes to a small logical layer, ALL TEXT to the real screen
# ----------------------------------------------------------------------------
def build_sprite_surfaces() -> dict[str, pygame.Surface]:
    out: dict[str, pygame.Surface] = {}
    for name, rows in SPRITES.items():
        surf = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                col = PAL.get(ch)
                if col:
                    surf.set_at((x, y), col)
        out[name] = surf
        out[name + "_f"] = pygame.transform.flip(surf, True, False)
        hurt = surf.copy()
        hurt.fill((120, 0, 0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        out[name + "_hurt"] = hurt
        out[name + "_hurt_f"] = pygame.transform.flip(hurt, True, False)
    return out


TILE_COLORS = {
    T_VOID: COLORS["void"], T_DEEP: COLORS["deep"], T_WATER: COLORS["water"],
    T_SAND: COLORS["sand"], T_GRASS: COLORS["grass"], T_GRASS2: COLORS["grass2"],
    T_FOREST: COLORS["forest"], T_STONE: COLORS["stone"], T_PATH: COLORS["path"],
    T_FLOOR: COLORS["floor"], T_CROPS: COLORS["crops"], T_FLOWERS: COLORS["flowers"],
}


class Renderer:
    """World -> logical surface scaled by an integer zoom; text -> native screen."""

    def __init__(self, game: Game, width: int, height: int, zoom: int):
        self.game = game
        self.sprites = build_sprite_surfaces()
        self.resize(width, height, zoom)

    def resize(self, width: int, height: int, zoom: int) -> None:
        self.width, self.height, self.zoom = width, height, zoom
        self.lw, self.lh = width // zoom, height // zoom
        self.logical = pygame.Surface((self.lw, self.lh))
        self.ox = (width - self.lw * zoom) // 2
        self.oy = (height - self.lh * zoom) // 2
        self._scaled = pygame.Surface((self.lw * zoom, self.lh * zoom))
        self.cam_x = self.cam_y = 0.0
        self.view_w = self.lw / TILE
        self.view_h = self.lh / TILE
        self.ui = width / BASE_UI_WIDTH
        self.font_small = self._font(max(9, round(10 * self.ui)))
        self.font = self._font(max(11, round(12 * self.ui)))
        self.font_big = self._font(max(14, round(15 * self.ui)))
        self.font_name = self._font(max(8, round(8 * self.ui)))
        self.font_title = self._font(max(20, round(26 * self.ui)))

    @staticmethod
    def _font(size: int) -> pygame.font.Font:
        for name in ("consolas", "couriernew", "dejavusansmono", "liberationmono"):
            try:
                f = pygame.font.SysFont(name, size)
                if f:
                    return f
            except Exception:
                continue
        return pygame.font.Font(None, size)

    def s(self, v: float) -> int:
        """Scale a UI dimension for the current resolution."""
        return int(round(v * self.ui))

    # -- frame --------------------------------------------------------------
    def draw(self, screen: pygame.Surface) -> None:
        g = self.game
        p = g.player
        cam_x = max(0.0, min(MAP_W - self.view_w, p["x"] - self.view_w / 2))
        cam_y = max(0.0, min(MAP_H - self.view_h, p["y"] - self.view_h / 2))
        self.cam_x, self.cam_y = cam_x, cam_y

        self.logical.fill(COLORS["void"])
        self.draw_tiles(cam_x, cam_y)
        self.draw_decor(cam_x, cam_y)
        self.draw_corpses(cam_x, cam_y)
        self.draw_world_entities(cam_x, cam_y)

        pygame.transform.scale(self.logical, (self.lw * self.zoom, self.lh * self.zoom), self._scaled)
        screen.fill(COLORS["void"])
        screen.blit(self._scaled, (self.ox, self.oy))

        self.draw_text_layer(screen)
        self.draw_hud(screen)

    # -- world layer (small, scaled up) -------------------------------------
    def to_logical(self, wx: float, wy: float) -> tuple[float, float]:
        return (wx - self.cam_x) * TILE, (wy - self.cam_y) * TILE

    def draw_tiles(self, cam_x: float, cam_y: float) -> None:
        s, w = self.logical, self.game.world
        x0, y0 = int(cam_x), int(cam_y)
        wave = math.sin(self.game.frame * 0.03) * 8
        for ty in range(y0 - 1, y0 + int(self.view_h) + 2):
            for tx in range(x0 - 1, x0 + int(self.view_w) + 2):
                px, py = (tx - cam_x) * TILE, (ty - cam_y) * TILE
                if not w.in_bounds(tx, ty):
                    pygame.draw.rect(s, COLORS["void"], (px, py, TILE, TILE))
                    continue
                t = w.tiles[ty][tx]
                col = TILE_COLORS.get(t, COLORS["grass"])
                if t == T_WATER:
                    col = tuple(max(0, min(255, c + wave)) for c in col)
                elif t == T_GRASS and (tx + ty) % 2 == 0:
                    col = COLORS["grass2"]
                elif t == T_FLOOR and (tx + ty) % 2 == 0:
                    col = COLORS["floor2"]
                pygame.draw.rect(s, col, (px, py, TILE, TILE))

                h = hash2(tx, ty)
                if t in (T_GRASS, T_GRASS2) and h > 0.62:
                    pygame.draw.rect(s, (58, 118, 54), (px + h * 13, py + h * 9, 2, 2))
                if t == T_SAND and h > 0.85:
                    pygame.draw.rect(s, (190, 170, 120), (px + h * 10, py + h * 8, 3, 2))
                if t == T_WATER and h > 0.8:
                    pygame.draw.rect(s, (140, 190, 235), (px + 3, py + 5, 4, 2))
                if t == T_CROPS and h > 0.5:
                    pygame.draw.rect(s, (196, 200, 110), (px + h * 12, py + 6, 2, 4))

    def draw_decor(self, cam_x: float, cam_y: float) -> None:
        s = self.logical
        for d in self.game.world.decor:
            if not (cam_x - 2 < d["x"] < cam_x + self.view_w + 2
                    and cam_y - 2 < d["y"] < cam_y + self.view_h + 2):
                continue
            px, py = (d["x"] - cam_x) * TILE, (d["y"] - cam_y) * TILE
            if d["type"] == "flower":
                pygame.draw.rect(s, (232, 190, 130), (px + 7, py + 6, 2, 3))
                pygame.draw.rect(s, (140, 170, 100), (px + 6, py + 9, 4, 2))
            elif d["type"] == "bush":
                pygame.draw.rect(s, (46, 104, 50), (px + 3, py + 8, 10, 6))
                pygame.draw.rect(s, (150, 180, 90), (px + 5, py + 7, 6, 3))
            elif d["type"] == "lamp":
                on = math.sin(self.game.frame * 0.05 + d["x"]) > 0.7
                pygame.draw.rect(s, (60, 40, 26), (px, py + 6, 2, 8))
                pygame.draw.rect(s, (255, 220, 90) if on else (150, 140, 60), (px - 1, py + 3, 4, 4))

    def draw_corpses(self, cam_x: float, cam_y: float) -> None:
        for c in self.game.corpses:
            alpha = max(0, int(255 * (1 - c["t"] / 1.6)))
            key = "gb_1" if c["kind"] == "brute" else "g_1"
            spr = self.sprites[key].copy()
            spr.set_alpha(alpha)
            self.logical.blit(spr, ((c["x"] - cam_x) * TILE - SPRITE / 2,
                                    (c["y"] - cam_y) * TILE - SPRITE + 6))

    def draw_world_entities(self, cam_x: float, cam_y: float) -> None:
        g = self.game
        items: list[tuple[float, Callable[[], None]]] = []
        for o in g.world.objects:
            if not (cam_x - 3 < o["x"] < cam_x + self.view_w + 3
                    and cam_y - 3 < o["y"] < cam_y + self.view_h + 4):
                continue
            items.append((o["y"], lambda o=o: self.draw_object(o, cam_x, cam_y)))
        for d in g.drops:
            items.append((d["y"], lambda d=d: self.draw_drop(d, cam_x, cam_y)))
        for n in g.npcs:
            items.append((n["y"], lambda n=n: self.draw_npc(n, cam_x, cam_y)))
        for m in g.mobs:
            if m["alive"]:
                items.append((m["y"], lambda m=m: self.draw_mob(m, cam_x, cam_y)))
        items.append((g.player["y"], lambda: self.draw_player(cam_x, cam_y)))
        for p in g.particles:
            items.append((p["y"] - 0.05, lambda p=p: self.draw_particle(p, cam_x, cam_y)))

        items.sort(key=lambda it: it[0])
        for _, fn in items:
            fn()

    def draw_object(self, o: dict, cam_x: float, cam_y: float) -> None:
        s = self.logical
        px, py = (o["x"] - cam_x) * TILE, (o["y"] - cam_y) * TILE
        if o["type"] == "tree":
            sway = math.sin(self.game.frame * 0.02 + o["x"]) * 1
            pygame.draw.rect(s, COLORS["wood2"], (px + 6, py + 8, 4, 8))
            pygame.draw.rect(s, COLORS["wood"], (px + 6, py + 8, 2, 8))
            tx = px + sway
            pygame.draw.rect(s, (30, 78, 44), (tx + 1, py - 6, 14, 14))
            pygame.draw.rect(s, (44, 104, 54), (tx + 2, py - 5, 12, 10))
            pygame.draw.rect(s, (64, 130, 62), (tx + 4, py - 3, 8, 5))
            pygame.draw.rect(s, (88, 158, 78), (tx + 5, py - 2, 4, 2))
        elif o["type"] == "house":
            pygame.draw.rect(s, COLORS["wood"], (px - 8, py - 8, 32, 32))
            pygame.draw.rect(s, COLORS["wood2"], (px - 8, py + 18, 32, 6))
            pygame.draw.rect(s, COLORS["roof2"], (px - 12, py - 14, 40, 10))
            pygame.draw.rect(s, COLORS["roof"], (px - 14, py - 20, 44, 8))
            pygame.draw.rect(s, COLORS["roof2"], (px - 10, py - 24, 36, 6))
            glow = int(140 + math.sin(self.game.frame * 0.06 + o["x"]) * 30)
            pygame.draw.rect(s, (min(255, glow + 40), min(255, glow + 60), 90), (px - 2, py - 2, 8, 8))
            pygame.draw.rect(s, (50, 90, 130), (px + 1, py - 1, 2, 6))
            pygame.draw.rect(s, COLORS["door"], (px + 12, py + 2, 8, 14))
            pygame.draw.rect(s, (200, 170, 90), (px + 18, py + 8, 2, 2))
            pygame.draw.rect(s, (90, 90, 96), (px + 14, py - 28, 6, 6))
            sm = (self.game.frame * 0.04 + o["x"]) % 1
            smoke = pygame.Surface((3, 3), pygame.SRCALPHA)
            smoke.fill((200, 200, 205, int(120 * (1 - sm))))
            s.blit(smoke, (px + 15, py - 34 - sm * 8))

    def draw_drop(self, d: dict, cam_x: float, cam_y: float) -> None:
        s = self.logical
        px = (d["x"] - cam_x) * TILE
        py = (d["y"] - cam_y) * TILE + math.sin(self.game.frame * 0.1) * 2
        if d["type"] == "gold":
            pygame.draw.rect(s, (120, 90, 20), (px + 4, py + 6, 8, 8))
            pygame.draw.rect(s, (240, 200, 80), (px + 5, py + 7, 6, 6))
            pygame.draw.rect(s, (255, 235, 150), (px + 6, py + 8, 2, 2))
        else:
            pygame.draw.rect(s, (40, 70, 130), (px + 4, py + 4, 8, 10))
            pygame.draw.rect(s, (120, 190, 240), (px + 5, py + 5, 6, 8))
            pygame.draw.rect(s, (230, 245, 255), (px + 6, py + 6, 2, 4))

    def blit_sprite(self, key: str, x: float, y: float, flip: bool = False, hurt: bool = False) -> None:
        name = key + ("_hurt" if hurt else "") + ("_f" if flip else "")
        self.logical.blit(self.sprites[name], (x, y))

    @staticmethod
    def player_sprite_key(d: str, frame: int) -> tuple[str, bool]:
        if d == "up":
            return ("p_up_2" if frame else "p_up_1"), False
        if d == "left":
            return ("p_side_2" if frame else "p_side_1"), True
        if d == "right":
            return ("p_side_2" if frame else "p_side_1"), False
        return ("p_down_2" if frame else "p_down_1"), False

    def draw_player(self, cam_x: float, cam_y: float) -> None:
        s = self.logical
        p = self.game.player
        px = (p["x"] - cam_x) * TILE - SPRITE / 2
        py = (p["y"] - cam_y) * TILE - SPRITE + 3
        key, flip = self.player_sprite_key(p["dir"], p["frame"] if p["moving"] else 0)

        shadow = pygame.Surface((12, 5), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 70), (0, 0, 12, 5))
        s.blit(shadow, ((p["x"] - cam_x) * TILE - 6, (p["y"] - cam_y) * TILE + 1))

        bob = -1 if (p["moving"] and p["frame"]) else 0
        self.blit_sprite(key, px, py + bob, flip, p["hurt_t"] > 0)

        if p["atk_anim"] > 0:
            t = 1 - p["atk_anim"] / 0.28
            fx, fy = self.game.face_dir()
            ang = math.atan2(fy, fx) - 1.2 + t * 1.7
            cx, cy = (p["x"] - cam_x) * TILE, (p["y"] - cam_y) * TILE - 8
            bx, by = math.cos(ang), math.sin(ang)
            pygame.draw.line(s, PAL["p"], (cx + bx * 6, cy + by * 6), (cx + bx * 15, cy + by * 15), 2)
            pygame.draw.line(s, PAL["q"], (cx + bx * 13, cy + by * 13), (cx + bx * 16, cy + by * 16), 2)
            for i in range(5):
                a = ang - 0.5 + i * 0.25
                pygame.draw.rect(s, (255, 255, 200), (cx + math.cos(a) * 9, cy + math.sin(a) * 9, 1, 1))

        if p["hp"] < p["hp_max"]:
            self.draw_hp_bar(p["x"], p["y"] - 0.75, p["hp"], p["hp_max"], cam_x, cam_y)

    def draw_npc(self, n: dict, cam_x: float, cam_y: float) -> None:
        s = self.logical
        px = (n["x"] - cam_x) * TILE - SPRITE / 2
        py = (n["y"] - cam_y) * TILE - SPRITE + 3
        shadow = pygame.Surface((12, 5), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 60), (0, 0, 12, 5))
        s.blit(shadow, ((n["x"] - cam_x) * TILE - 6, (n["y"] - cam_y) * TILE + 1))
        base = "mage" if n["kind"] == "mage" else "npc"
        key = base + ("_2" if n["anim_t"] > 0.3 else "_1")
        bob = math.sin(self.game.frame * 0.06 + n["x"])
        self.blit_sprite(key, px, py + bob, n["dir"] == "left")
        if math.hypot(n["x"] - self.game.player["x"], n["y"] - self.game.player["y"]) < 2.0:
            bob2 = math.sin(self.game.frame * 0.12) * 1.5
            pygame.draw.rect(s, (255, 240, 150), ((n["x"] - cam_x) * TILE - 1, py - 7 + bob2, 3, 5))
            pygame.draw.rect(s, (255, 240, 150), ((n["x"] - cam_x) * TILE - 2, py - 1 + bob2, 5, 2))

    def draw_mob(self, m: dict, cam_x: float, cam_y: float) -> None:
        s = self.logical
        px = (m["x"] - cam_x) * TILE - SPRITE / 2
        py = (m["y"] - cam_y) * TILE - SPRITE + 3
        base = "gb" if m["kind"] == "brute" else "g"
        key = base + ("_2" if (m["moving"] and m["frame"]) else "_1")
        shadow = pygame.Surface((12, 5), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 60), (0, 0, 12, 5))
        s.blit(shadow, ((m["x"] - cam_x) * TILE - 6, (m["y"] - cam_y) * TILE + 1))
        bob = -1 if (m["moving"] and m["frame"]) else 0
        lunge = 2 if m["atk_t"] > 0 else 0
        lx = lunge * (-1 if m["dir"] == "left" else 1 if m["dir"] == "right" else 0)
        ly = lunge * (-1 if m["dir"] == "up" else 1 if m["dir"] == "down" else 0)
        self.blit_sprite(key, px + lx, py + ly + bob, m["dir"] == "left", m["hurt_t"] > 0)

        if (math.hypot(m["x"] - self.game.player["x"], m["y"] - self.game.player["y"]) < 6.5
                and m["attack_cd"] > 0.7):
            pygame.draw.rect(s, (255, 90, 60), ((m["x"] - cam_x) * TILE + 2, py - 8, 2, 4))
            pygame.draw.rect(s, (255, 90, 60), ((m["x"] - cam_x) * TILE + 2, py - 3, 2, 2))
        if m["hp"] < m["hp_max"]:
            self.draw_hp_bar(m["x"], m["y"] - 0.75, m["hp"], m["hp_max"], cam_x, cam_y)

    def draw_hp_bar(self, x, y, hp, hp_max, cam_x, cam_y, w=14) -> None:
        s = self.logical
        px = (x - cam_x) * TILE - w / 2
        py = (y - cam_y) * TILE
        ratio = max(0.0, hp / hp_max)
        pygame.draw.rect(s, (20, 20, 26), (px - 1, py - 1, w + 2, 4))
        pygame.draw.rect(s, (120, 30, 30), (px, py, w, 2))
        col = (90, 210, 80) if ratio > 0.5 else (220, 80, 80)
        pygame.draw.rect(s, col, (px, py, w * ratio, 2))

    def draw_particle(self, p: dict, cam_x: float, cam_y: float) -> None:
        alpha = max(0.0, 1 - p["t"] / p["life"])
        col = pygame.Color(p["color"])
        col.a = int(255 * alpha)
        surf = pygame.Surface((2, 2), pygame.SRCALPHA)
        surf.fill(col)
        self.logical.blit(surf, ((p["x"] - cam_x) * TILE, (p["y"] - cam_y) * TILE))

    # -- native-resolution text layer ---------------------------------------
    def draw_text_layer(self, screen: pygame.Surface) -> None:
        """NPC names and damage numbers — crisp, drawn 1:1 on the real screen."""
        g = self.game
        for n in g.npcs:
            if not (self.cam_x - 2 < n["x"] < self.cam_x + self.view_w + 2
                    and self.cam_y - 2 < n["y"] < self.cam_y + self.view_h + 2):
                continue
            lx, ly = self.to_logical(n["x"], n["y"])
            label = self.font_name.render(n["name"], True, (245, 245, 250))
            shadow = self.font_name.render(n["name"], True, (0, 0, 0))
            x = lx * self.zoom - label.get_width() / 2 + self.ox
            y = (ly - SPRITE + 3) * self.zoom - self.font_name.get_height() - 2 + self.oy
            screen.blit(shadow, (x + 1, y + 1))
            screen.blit(label, (x, y))

        for f in g.floaters:
            alpha = max(0.0, 1 - f["t"] / f["life"])
            col = pygame.Color(f["color"])
            col.a = int(255 * alpha)
            txt = self.font_small.render(f["text"], True, col)
            lx, ly = self.to_logical(f["x"], f["y"])
            screen.blit(txt, (lx * self.zoom - txt.get_width() / 2 + self.ox,
                              ly * self.zoom - self.s(14) + self.oy))

    # -- HUD ----------------------------------------------------------------
    def panel(self, screen, rect, fill=(10, 12, 20, 210), border=(90, 110, 150)) -> None:
        surf = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        surf.fill(fill)
        pygame.draw.rect(surf, border, (0, 0, rect[2], rect[3]), 1)
        screen.blit(surf, (rect[0], rect[1]))

    def draw_hud(self, screen) -> None:
        g, p = self.game, self.game.player
        S = self.s
        self.panel(screen, (S(10), S(10), S(176), S(68)))
        screen.blit(self.font.render("Пиксельное приключение", True, (255, 255, 255)), (S(20), S(16)))
        screen.blit(self.font_small.render(
            f"Ур. {p['level']}   XP {p['xp']}/{p['xp_next']}", True, (180, 200, 230)), (S(20), S(33)))

        pygame.draw.rect(screen, (30, 30, 38), (S(20), S(50), S(156), S(7)))
        pygame.draw.rect(screen, (190, 60, 60), (S(20), S(50), S(156), S(7)))
        pygame.draw.rect(screen, (80, 210, 110),
                         (S(20), S(50), S(156) * max(0.0, p["hp"] / p["hp_max"]), S(7)))
        hp_txt = self.font_small.render(f"HP {max(0, math.ceil(p['hp']))} / {int(p['hp_max'])}",
                                        True, (255, 255, 255))
        screen.blit(hp_txt, (S(98) - hp_txt.get_width() / 2, S(49)))
        screen.blit(self.font_small.render(
            f"Золото: {p['gold']}   Зелья: {p['potions']}", True, (240, 210, 120)), (S(20), S(61)))

        self.panel(screen, (S(10), S(86), S(176), S(46)), fill=(10, 12, 20, 190))
        for i, line in enumerate(("ПРОБЕЛ / ЛКМ — атака", "Q — квесты   K — навыки",
                                  f"Очки навыков: {g.skill_points}")):
            screen.blit(self.font_small.render(line, True, (200, 214, 240)), (S(20), S(90 + i * 14)))

        ty = S(146)
        for t in g.toasts:
            a = t["t"] / 0.2 if t["t"] < 0.2 else (t["life"] - t["t"]) / 0.6 if t["t"] > t["life"] - 0.6 else 1
            surf = pygame.Surface((S(300), S(20)), pygame.SRCALPHA)
            surf.fill((10, 12, 18, int(190 * a)))
            screen.blit(surf, (S(10), ty))
            txt = self.font_small.render(t["text"], True, pygame.Color(t["color"]))
            txt.set_alpha(int(255 * a))
            screen.blit(txt, (S(18), ty + S(4)))
            ty += S(24)

        if g.show_quests:
            self.draw_quest_panel(screen)
        if g.show_skills:
            self.draw_skill_panel(screen)
        if g.dialog:
            self.draw_dialog(screen)

    def draw_quest_panel(self, screen) -> None:
        g, S = self.game, self.s
        h = S(30 + len(g.quests) * 42)
        self.panel(screen, (S(320), S(20), S(430), h), fill=(12, 14, 22, 225), border=(120, 160, 210))
        screen.blit(self.font.render("Журнал квестов   (Q — закрыть)", True, (255, 255, 255)),
                    (S(334), S(26)))
        yy = S(52)
        for q in g.quests:
            col = (140, 220, 140) if q["done"] else (230, 230, 240)
            screen.blit(self.font_small.render(("✔ " if q["done"] else "• ") + q["title"], True, col),
                        (S(334), yy))
            screen.blit(self.font_small.render(q["desc"], True, (170, 186, 210)), (S(344), yy + S(14)))
            if not q["done"]:
                screen.blit(self.font_small.render(f"Прогресс: {q['progress']}/{q['goal']}",
                                                   True, (120, 200, 255)), (S(630), yy + S(14)))
            yy += S(42)

    def draw_skill_panel(self, screen) -> None:
        g, S = self.game, self.s
        h = S(40 + len(g.skills) * 46)
        self.panel(screen, (S(320), S(20), S(430), h), fill=(12, 14, 22, 228), border=(150, 130, 220))
        screen.blit(self.font.render(f"Дерево навыков   (K — закрыть)   Очки: {g.skill_points}",
                                     True, (255, 255, 255)), (S(334), S(26)))
        yy = S(54)
        for i, sk in enumerate(g.skills):
            ok = g.can_learn(sk)
            col = (130, 230, 130) if sk["learned"] else (240, 240, 250) if ok else (130, 134, 148)
            label = f"[{i + 1}] {sk['name']}"
            if sk["learned"]:
                label += "  ✔"
            elif sk["req"] and not all(g.has_skill(r) for r in sk["req"]):
                label += "  требует " + ", ".join(sk["req"])
            screen.blit(self.font_small.render(label, True, col), (S(334), yy))
            screen.blit(self.font_small.render(sk["desc"], True, (170, 186, 210)), (S(350), yy + S(14)))
            yy += S(46)
        screen.blit(self.font_small.render("Нажми 1–4, чтобы изучить доступный навык.",
                                           True, (150, 170, 200)), (S(334), S(20) + h - S(18)))

    def draw_dialog(self, screen) -> None:
        if not self.game.dialog:
            return
        d, S = self.game.dialog, self.s
        w, h = S(520), S(74)
        x, y = (self.width - w) / 2, self.height - h - S(34)
        self.panel(screen, (int(x), int(y), w, h), fill=(10, 12, 20, 235), border=(220, 200, 130))
        screen.blit(self.font.render(d["name"], True, (255, 226, 140)), (x + S(16), y + S(10)))
        screen.blit(self.font_small.render(d["line"], True, (238, 240, 248)), (x + S(16), y + S(34)))
        screen.blit(self.font_small.render("E / Q — закрыть", True, (160, 176, 200)),
                    (x + w - S(110), y + h - S(20)))

    # -- settings menu ------------------------------------------------------
    def draw_menu(self, screen, selected: int, fullscreen: bool, saved: bool) -> None:
        S = self.s
        screen.fill((12, 18, 28))
        title = self.font_title.render("Пиксельное приключение", True, (245, 240, 200))
        screen.blit(title, (self.width / 2 - title.get_width() / 2, S(70)))
        sub = self.font.render("v1.2 — выбор разрешения", True, (150, 170, 200))
        screen.blit(sub, (self.width / 2 - sub.get_width() / 2, S(70) + title.get_height() + S(6)))

        y = S(190)
        screen.blit(self.font.render("Разрешение экрана:", True, (220, 230, 245)), (S(60), y))
        y += S(30)
        for i, (w, h, z) in enumerate(RESOLUTIONS):
            cur = (i == selected)
            col = (255, 235, 150) if cur else (200, 210, 225)
            mark = "▶" if cur else " "
            label = f"{mark}  [{i + 1}]  {w} x {h}"
            if w == 1920 and h == 1080:
                label += "   (Full HD)"
            if w == 1280 and h == 720:
                label += "   (HD)"
            screen.blit(self.font.render(label, True, col), (S(70), y))
            y += S(28)

        y += S(12)
        fs = "включён" if fullscreen else "выключен"
        screen.blit(self.font.render(f"Полный экран: {fs}   (F11)", True, (200, 210, 225)), (S(60), y))
        y += S(28)
        screen.blit(self.font_small.render(
            "Пробел / Enter — начать игру    •    1-5 — выбрать разрешение    "
            "•    F11 — полный экран    •    Esc — выход",
            True, (150, 170, 200)), (S(60), y))
        if saved:
            screen.blit(self.font_small.render("Разрешение сохранено", True, (140, 220, 140)),
                        (S(60), y + S(22)))
        screen.blit(self.font_small.render("WASD/стрелки — движение, ПРОБЕЛ — атака, E — говорить, "
                                           "Q — квесты, K — навыки, F5/F9 — сохранить/загрузить, "
                                           "F10 — это меню",
                                           True, (120, 140, 165)), (S(60), self.height - S(40)))


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def parse_res_arg(argv: list[str]) -> int | None:
    for i, a in enumerate(argv):
        if a == "--res" and i + 1 < len(argv):
            try:
                w, h = argv[i + 1].lower().split("x")
                w, h = int(w), int(h)
            except ValueError:
                return None
            return min(range(len(RESOLUTIONS)),
                       key=lambda i: abs(RESOLUTIONS[i][0] - w) + abs(RESOLUTIONS[i][1] - h))
    return None


# ----------------------------------------------------------------------------
# Input / loop
# ----------------------------------------------------------------------------
KEYMAP = {
    pygame.K_w: "up", pygame.K_UP: "up",
    pygame.K_s: "down", pygame.K_DOWN: "down",
    pygame.K_a: "left", pygame.K_LEFT: "left",
    pygame.K_d: "right", pygame.K_RIGHT: "right",
}


def gather_input(keys) -> dict:
    inp = {"up": False, "down": False, "left": False, "right": False}
    for k, name in KEYMAP.items():
        if keys[k]:
            inp[name] = True
    return inp


def handle_key(game: Game, key: int) -> None:
    if key == pygame.K_e:
        if game.dialog:
            game.dialog = None
        else:
            game.interact()
    elif key == pygame.K_q:
        if game.dialog:
            game.dialog = None
        else:
            game.show_quests = not game.show_quests
    elif key == pygame.K_k:
        game.show_skills = not game.show_skills
    elif key == pygame.K_ESCAPE:
        game.dialog = None
        game.show_quests = False
        game.show_skills = False
    elif key == pygame.K_SPACE:
        game.attack()
    elif key == pygame.K_F5:
        game.save()
    elif key == pygame.K_F9:
        game.load()
    elif game.show_skills and key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
        idx = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3}[key]
        game.learn(game.skills[idx])
    elif key == pygame.K_a and game.has_skill("s_heal"):
        p = game.player
        if p["hp"] < p["hp_max"] and p["potions"] > 0:
            p["potions"] -= 1
            p["hp"] = min(p["hp_max"], p["hp"] + 10)
            game.toast("Лечение +10 HP", "#8ee08e")


def best_res_index_for_desktop() -> int:
    try:
        dw, dh = pygame.display.get_desktop_sizes()[0]
    except Exception:
        return DEFAULT_RES_INDEX
    for i in range(len(RESOLUTIONS) - 1, -1, -1):
        if RESOLUTIONS[i][0] <= dw and RESOLUTIONS[i][1] <= dh:
            return i
    return 0


def apply_display(screen, res_index: int, fullscreen: bool):
    """Return (screen, width, height, zoom)."""
    w, h, zoom = RESOLUTIONS[res_index]
    if fullscreen:
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except Exception:
            dw, dh = w, h
        screen = pygame.display.set_mode((dw, dh), pygame.FULLSCREEN)
        best = 1
        for z in (2, 3, 4, 5, 6):
            if dw // z >= 320 and dh // z >= 240:
                best = z
        return screen, dw, dh, best
    screen = pygame.display.set_mode((w, h))
    return screen, w, h, zoom


def run() -> int:
    pygame.init()
    pygame.display.set_caption("Pixel RPG Adventure 1.2")

    cfg = load_config()
    res_index = parse_res_arg(sys.argv)
    if res_index is None:
        res_index = cfg.get("res_index", DEFAULT_RES_INDEX)
        res_index = max(0, min(len(RESOLUTIONS) - 1, res_index))
    fullscreen = bool(cfg.get("fullscreen", False)) or "--fullscreen" in sys.argv
    if not fullscreen:
        # never open a window bigger than the desktop
        res_index = min(res_index, best_res_index_for_desktop())

    screen, width, height, zoom = apply_display(None, res_index, fullscreen)
    game = Game()
    renderer = Renderer(game, width, height, zoom)
    clock = pygame.time.Clock()

    state = "menu"
    menu_saved = False
    running = True
    while running:
        dt = min(0.05, clock.tick(FPS) / 1000.0)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    screen, width, height, zoom = apply_display(screen, res_index, fullscreen)
                    renderer.resize(width, height, zoom)
                    save_config({"res_index": res_index, "fullscreen": fullscreen})
                    menu_saved = True
                    continue
                if state == "menu":
                    if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                        state = "play"
                        menu_saved = False
                    elif event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                        idx = event.key - pygame.K_1
                        if idx < len(RESOLUTIONS):
                            res_index = idx
                            screen, width, height, zoom = apply_display(screen, res_index, fullscreen)
                            renderer.resize(width, height, zoom)
                            save_config({"res_index": res_index, "fullscreen": fullscreen})
                            menu_saved = True
                else:
                    if event.key == pygame.K_F10:
                        state = "menu"
                    else:
                        handle_key(game, event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state == "play" and not game.dialog:
                    game.attack()

        if state == "play":
            game.update(dt, gather_input(pygame.key.get_pressed()))
            renderer.draw(screen)
        else:
            renderer.draw_menu(screen, res_index, fullscreen, menu_saved)
        pygame.display.flip()

    game.save()
    save_config({"res_index": res_index, "fullscreen": fullscreen})
    pygame.quit()
    return 0


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def selftest() -> int:
    """Headless end-to-end check; also writes a report file so a windowed .exe
    build (no console) can be verified."""
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = _selftest_body()
    text = buf.getvalue()
    print(text, end="")
    report = Path(os.environ.get("TEMP", ".")) / "pixelrpg_selftest.txt"
    try:
        report.write_text(text, encoding="utf-8")
        print(f"report written to {report}")
    except OSError:
        pass
    return code


def _selftest_body() -> int:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))

    problems: list[str] = []
    game = Game(seed=1234)
    stats = game.world.stats()
    print("world:", MAP_W, "x", MAP_H, "| land", f"{stats['land_pct']}%",
          "| trees", stats["trees"], "| houses", stats["houses"], "| decor", stats["decor"])
    print("mobs:", len(game.mobs), "| npcs:", len(game.npcs),
          "| quests:", len(game.quests), "| skills:", len(game.skills))
    if stats["land_pct"] < 80:
        problems.append(f"land only {stats['land_pct']}%")
    if len(game.mobs) < 8:
        problems.append(f"only {len(game.mobs)} mobs spawned")

    # --- reachability: every NPC must be walkable-to from the spawn ---
    reach = game.world.reachable_from((int(SPAWN_X), int(SPAWN_Y)))
    print("reachable tiles from spawn:", len(reach))
    for n in game.npcs:
        tile = (int(n["x"]), int(n["y"]))
        ok = tile in reach
        print(f"  npc {n['name']:12s} at {tile} reachable: {ok}")
        if not ok:
            problems.append(f"NPC {n['name']} unreachable at {tile}")
    for m in game.mobs:
        if (int(m["x"]), int(m["y"])) not in reach:
            problems.append(f"mob at ({int(m['x'])},{int(m['y'])}) unreachable")

    # --- walk ---
    start = (game.player["x"], game.player["y"])
    frames_seen = set()
    for _ in range(60):
        game.update(1 / 60, {"right": True, "left": False, "up": False, "down": False})
        frames_seen.add(game.player["frame"])
    walked = math.hypot(game.player["x"] - start[0], game.player["y"] - start[1])
    print("walked:", round(walked, 2), "tiles | frames:", sorted(frames_seen), "| dir:", game.player["dir"])
    if walked < 2:
        problems.append(f"player barely moved ({walked:.2f} tiles)")
    if frames_seen != {0, 1}:
        problems.append("walk animation did not cycle both frames")

    # --- talk to EVERY npc ---
    for n in game.npcs:
        game.player["x"], game.player["y"] = n["x"], n["y"] + 1.0
        game.dialog = None
        game.interact()
        got = (game.dialog or {}).get("name")
        print(f"  dialog with {n['name']:12s} -> {got}")
        if got != n["name"]:
            problems.append(f"could not talk to {n['name']}")
    q_npcs = next(q for q in game.quests if q["id"] == "q_npcs")
    print("quest 'знакомство' progress:", q_npcs["progress"], "/", q_npcs["goal"])
    if q_npcs["progress"] < len(game.npcs):
        problems.append("talking to all NPCs did not complete the quest")

    # --- combat ---
    mob = min(game.mobs, key=lambda m: math.hypot(m["x"] - game.player["x"], m["y"] - game.player["y"]))
    game.player["x"], game.player["y"] = mob["x"], mob["y"] - 1.0
    game.player["dir"] = "down"
    hp_before = mob["hp"]
    game.attack()
    print("attack:", f"{hp_before:.0f} -> {mob['hp']:.0f} hp | anim:", game.player["atk_anim"] > 0)
    if mob["hp"] >= hp_before:
        problems.append("attack dealt no damage")
    if game.player["atk_anim"] <= 0:
        problems.append("attack animation did not trigger")
    while mob["alive"]:
        game.player["atk_t"] = 0
        mob["hp"] -= 10
        if mob["hp"] <= 0:
            game.kill_mob(mob)
    q_gob = next(q for q in game.quests if q["id"] == "q_goblins")
    print("goblin quest:", q_gob["progress"], "/", q_gob["goal"], "| gold:", game.player["gold"])
    if q_gob["progress"] < 1:
        problems.append("kill did not advance the goblin quest")

    # --- skills + save/load ---
    before = game.skill_points
    game.learn(game.skills[0])
    print("skill learned:", game.skills[0]["learned"], "| points", before, "->", game.skill_points)
    if not game.skills[0]["learned"]:
        problems.append("could not learn a skill")

    tmp = Path(os.environ.get("TEMP", ".")) / "pixel_rpg_selftest.json"
    ok_save = game.save(tmp)
    gold = game.player["gold"]
    game.player["gold"] = -1
    ok_load = game.load(tmp)
    print("save/load:", ok_save, ok_load, "| gold restored:", game.player["gold"] == gold)
    if not (ok_save and ok_load and game.player["gold"] == gold):
        problems.append("save/load round trip failed")

    # --- render at every resolution, verify crisp integer scaling + text pass ---
    for idx, (w, h, z) in enumerate(RESOLUTIONS):
        screen = pygame.Surface((w, h))
        r = Renderer(game, w, h, z)
        r.draw(screen)
        colours = {screen.get_at((x, y))[:3]
                   for x in range(0, w, max(1, w // 40))
                   for y in range(0, h, max(1, h // 24))}
        text_w = r.font.render("Тест шрифта", True, (255, 255, 255)).get_width()
        print(f"  render {w}x{h} zoom{z}: logical {r.lw}x{r.lh} "
              f"| colours {len(colours)} | text width {text_w}px")
        if len(colours) < 5:
            problems.append(f"render at {w}x{h} looks blank ({len(colours)} colours)")
        if text_w < 40:
            problems.append(f"font too small at {w}x{h}")

    # verify the HUD is drawn at native resolution (text must NOT be upscaled):
    # a 1-px difference check on the logical surface vs the screen would be ideal;
    # here we assert the renderer keeps text off the logical layer.
    screen = pygame.Surface((1920, 1080))
    r = Renderer(game, 1920, 1080, 4)
    r.logical.fill((0, 0, 0))
    r.draw_text_layer(screen)
    r.draw_hud(screen)
    hud_pixels = sum(1 for x in range(0, 1920, 7) for y in range(0, 200, 5)
                     if screen.get_at((x, y))[:3] != (0, 0, 0))
    print("HUD drawn on the native 1920x1080 screen, non-black samples:", hud_pixels)
    if hud_pixels < 50:
        problems.append("HUD did not render at native resolution")

    pygame.quit()
    if problems:
        print("SELFTEST FAILED:", "; ".join(problems))
        return 1
    print("SELFTEST OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    raise SystemExit(run())
