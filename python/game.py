#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pixel RPG Adventure 1.3 — Python / pygame-ce.

New in 1.3:
  * 32x32 character sprites (double size, real detail) + richer tile/object art
  * full inventory with loot, equipment (weapon/armor) and item use
  * animated main menu, settings screen and pause menu

Run:        python game.py [--res 1920x1080] [--fullscreen]
Self-test:  python game.py --selftest
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

import items as IT
import sprites as SP

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
TILE = 16
SPRITE = SP.SPRITE               # 32
MAP_W, MAP_H = 100, 64
FPS = 60
BASE_UI_WIDTH = 1248

RESOLUTIONS = [
    (960, 540, 2),
    (1280, 720, 3),
    (1366, 768, 3),
    (1600, 900, 4),
    (1920, 1080, 4),
]
DEFAULT_RES_INDEX = len(RESOLUTIONS) - 1

SAVE_PATH = Path.home() / ".pixel_rpg_adventure_save.json"
CONFIG_PATH = Path.home() / ".pixel_rpg_adventure_config.json"

T_VOID, T_DEEP, T_WATER, T_SAND, T_GRASS, T_GRASS2 = 0, 1, 2, 3, 4, 5
T_FOREST, T_STONE, T_PATH, T_FLOOR, T_CROPS, T_FLOWERS = 6, 7, 8, 9, 10, 11

COLORS = {
    "void": (10, 22, 32), "deep": (22, 60, 118), "water": (46, 110, 190),
    "water_l": (96, 158, 222), "sand": (216, 200, 146), "sand_d": (188, 170, 118),
    "grass": (86, 152, 74), "grass2": (70, 134, 62), "grass_d": (58, 118, 54),
    "grass_l": (120, 176, 92),
    "forest": (36, 92, 52), "stone": (126, 126, 134), "stone2": (104, 104, 112),
    "path": (170, 150, 112), "path_d": (146, 126, 92), "path_l": (198, 178, 138),
    "floor": (132, 98, 62), "floor2": (116, 84, 52), "floor_d": (98, 70, 42),
    "roof": (158, 62, 52), "roof2": (122, 46, 40), "roof_d": (96, 34, 30),
    "wood": (122, 84, 52), "wood2": (92, 62, 38), "wood_l": (146, 104, 66),
    "door": (72, 48, 28), "crops": (148, 168, 74), "crops_d": (118, 138, 58),
    "flowers": (232, 190, 130),
}

UI_BG = (10, 12, 20)
UI_EDGE = (96, 118, 158)
GOLD = (240, 210, 120)


def hexc(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


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
SPAWN_X, SPAWN_Y = 50.5, 32.5


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

        # keep the village square clear so every villager stays reachable
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
        for kind, count in (("rock", 150), ("stump", 90)):
            for _ in range(count):
                x, y = rng.randrange(MAP_W), rng.randrange(MAP_H)
                if self.tiles[y][x] == T_GRASS and not self.obj_at(x, y):
                    self.decor.append({"x": x, "y": y, "type": kind})
        # decorative fences around the village (gates left open on the roads)
        for fy in (cy - VILLAGE_HALF_H - 2, cy + VILLAGE_HALF_H + 2):
            for x in range(cx - VILLAGE_HALF_W - 2, cx + VILLAGE_HALF_W + 3):
                if x % 8 in (0, 1) or abs(x - cx) < 2:
                    continue
                if self.in_bounds(x, fy) and self.tiles[fy][x] == T_GRASS:
                    self.decor.append({"x": x, "y": fy, "type": "fence"})
        for fx in (cx - VILLAGE_HALF_W - 2, cx + VILLAGE_HALF_W + 2):
            for y in range(cy - VILLAGE_HALF_H - 2, cy + VILLAGE_HALF_H + 3):
                if y % 8 in (0, 1) or abs(y - cy) < 2:
                    continue
                if self.in_bounds(fx, y) and self.tiles[y][fx] == T_GRASS:
                    self.decor.append({"x": fx, "y": y, "type": "fence"})

        for y in range(cy + 8, cy + 12):
            for x in range(cx + 12, cx + 22):
                if self.in_bounds(x, y) and self.tiles[y][x] == T_GRASS:
                    self.tiles[y][x] = T_CROPS

    def _carve_lake(self, cx: float, cy: float, r: float) -> None:
        for y in range(int(cy - r - 2), int(cy + r + 3)):
            for x in range(int(cx - r - 2), int(cx + r + 3)):
                if not self.in_bounds(x, y):
                    continue
                if math.hypot(x - cx, y - cy) < r * (0.78 + hash2(x, y) * 0.44):
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
        # props that make the village read as lived-in
        props = ("barrel", "well", "barrel", "bush", "barrel", "well",
                 "barrel", "bush")
        idx = (x * 7 + y * 3) % len(props)
        self.decor.append({"x": x - 2, "y": y + 2, "type": props[idx]})

    # -- pathfinding --------------------------------------------------------
    def walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and not self.is_solid(x, y)

    def reachable_from(self, start: tuple[int, int]) -> set[tuple[int, int]]:
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
        land = sum(v for k, v in counts.items() if k >= T_SAND)
        return {"land_pct": round(100 * land / (MAP_W * MAP_H)),
                "trees": sum(1 for o in self.objects if o["type"] == "tree"),
                "houses": sum(1 for o in self.objects if o["type"] == "house"),
                "decor": len(self.decor)}


# ----------------------------------------------------------------------------
# Game
# ----------------------------------------------------------------------------
INV_SLOTS = 20


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
            "level": 1, "xp": 0, "xp_next": 20, "gold": 0,
            "atk_t": 0.0, "atk_anim": 0.0, "hurt_t": 0.0,
            "inventory": [],
            "equip": {"weapon": None, "armor": None},
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
        self.show_inventory = False
        self.inv_cursor = 0

        self.spawn_npcs()
        self.spawn_mobs()
        self.init_quests()
        self.init_skills()
        self.ensure_reachable()
        for item_id, count in (("potion", 2), ("herb", 1)):
            self.add_item(item_id, count)
        self.toast("Новая игра: исследуй деревню и победи гоблинов!")

    # -- inventory ----------------------------------------------------------
    def add_item(self, item_id: str, count: int = 1) -> bool:
        if item_id not in IT.ITEMS:
            return False
        stack = IT.ITEMS[item_id].get("stack", 1)
        inv = self.player["inventory"]
        if stack > 1:
            for slot in inv:
                if slot["id"] == item_id and slot["count"] < stack:
                    space = stack - slot["count"]
                    put = min(space, count)
                    slot["count"] += put
                    count -= put
                    if count <= 0:
                        return True
        while count > 0 and len(inv) < INV_SLOTS:
            put = min(count, stack)
            inv.append({"id": item_id, "count": put})
            count -= put
        return count <= 0

    def remove_item(self, item_id: str, count: int = 1) -> bool:
        inv = self.player["inventory"]
        have = sum(s["count"] for s in inv if s["id"] == item_id)
        if have < count:
            return False
        for slot in list(inv):
            if slot["id"] != item_id:
                continue
            take = min(slot["count"], count)
            slot["count"] -= take
            count -= take
            if slot["count"] <= 0:
                inv.remove(slot)
            if count <= 0:
                break
        return True

    def count_item(self, item_id: str) -> int:
        return sum(s["count"] for s in self.player["inventory"] if s["id"] == item_id)

    def use_slot(self, index: int) -> str:
        """Use/equip the item in inventory slot `index`. Returns a message."""
        inv = self.player["inventory"]
        if not (0 <= index < len(inv)):
            return ""
        slot = inv[index]
        item_id = slot["id"]
        data = IT.ITEMS[item_id]
        kind = data["kind"]

        if kind == "consumable":
            p = self.player
            if p["hp"] >= p["hp_max"]:
                return "Здоровье уже полное"
            p["hp"] = min(p["hp_max"], p["hp"] + data.get("heal", 0))
            slot["count"] -= 1
            if slot["count"] <= 0:
                inv.pop(index)
            return f"{data['name']}: +{data.get('heal', 0)} HP"

        if kind in ("weapon", "armor"):
            slot_key = "weapon" if kind == "weapon" else "armor"
            old = self.player["equip"][slot_key]
            self.player["equip"][slot_key] = item_id
            inv.pop(index)
            if old:
                self.add_item(old, 1)
            return f"Экипировано: {data['name']}"

        if kind == "material":
            return f"{data['name']}: материал ({data['value']} золота)"
        return f"{data['name']}: квестовый предмет"

    def attack_bonus(self) -> int:
        wid = self.player["equip"]["weapon"]
        return IT.ITEMS[wid].get("atk", 0) if wid else 0

    def defense(self) -> int:
        aid = self.player["equip"]["armor"]
        return IT.ITEMS[aid].get("def", 0) if aid else 0

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
             "desc": "A — лечиться зельем из сумки.", "cost": 1, "learned": False, "req": []},
            {"id": "s_crit", "name": "Смертельный удар",
             "desc": "25% шанс двойного урона.", "cost": 1, "learned": False, "req": ["s_slash"]},
        ]

    def spawn_npcs(self) -> None:
        # placed on the open square BETWEEN the house rows — never inside a house
        # footprint, otherwise the building (drawn later by y-sort) hides them
        self.npcs = [
            {"x": 46, "y": 31, "kind": "npc", "name": "Крестьянин", "dir": "down",
             "met": False, "anim_t": 0.0,
             "lines": ["Добро пожаловать в Дубраву, путник!",
                       "Гоблины шастают по лесам. Будь осторожен.",
                       "Старейшина ждёт тебя в центре деревни."]},
            {"x": 57, "y": 31, "kind": "npc", "name": "Фермер", "dir": "down",
             "met": False, "anim_t": 0.0,
             "lines": ["Пшеница в этом году богатая!",
                       "Гоблины таскают уши... то есть, мы их — им!"]},
            {"x": 46, "y": 34, "kind": "npc", "name": "Кузнец", "dir": "up",
             "met": False, "anim_t": 0.0, "gift": True,
             "lines": ["Сталь куётся в огне, а герой — в бою.",
                       "Держи пару зелий — и не благодари."]},
            {"x": 57, "y": 34, "kind": "mage", "name": "Старейшина", "dir": "up",
             "met": False, "anim_t": 0.0,
             "lines": ["Я чувствую в тебе силу, странник.",
                       "Одолей трёх гоблинов — и я раскрою первое умение.",
                       "Собранное в бою можно продать."]},
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
        self.floaters.append({"x": x, "y": y, "text": text, "color": color, "t": 0.0, "life": 1.1})

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
                        raw = max(1, m["atk"] + self.rng.randrange(3) - 1)
                        dmg = max(1, raw - self.defense())
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
            if d["t"] > 0.35 and not d.get("taken") and math.hypot(d["x"] - pl["x"], d["y"] - pl["y"]) < 1.0:
                d["taken"] = True
                if d["kind"] == "gold":
                    pl["gold"] += d["count"]
                    self.add_floater(d["x"], d["y"], f"+{d['count']} золота", "#ffd166")
                else:
                    got = self.add_item(d["kind"], d["count"])
                    if got:
                        self.add_floater(d["x"], d["y"], f"+{d['count']} {IT.item_name(d['kind'])}",
                                         "#9ad7ff")
                    else:
                        d["taken"] = False
                        d["t"] = 0.0
                        self.toast("Сумка полна!", "#ffb0b0")
        self.drops = [d for d in self.drops if not d.get("taken") and d["t"] < 60]

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
            dmg = 5 + self.rng.randrange(3) + int(p["level"] * 1.5) + self.attack_bonus()
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
        lo, hi = IT.GOLD_LOOT.get(m["kind"], (1, 5))
        gold = self.rng.randint(lo, hi)
        p["gold"] += gold
        self.toast(f"Побеждён: {m['name']} (+{m['xp']} XP, +{gold} золота)", "#ffe066")
        self.drops.append({"x": m["x"], "y": m["y"], "t": 0.0, "kind": "gold", "count": gold})
        for item_id in IT.roll_loot(m["kind"], self.rng):
            self.drops.append({"x": m["x"] + self.rng.uniform(-0.4, 0.4),
                               "y": m["y"] + self.rng.uniform(-0.4, 0.4),
                               "t": 0.0, "kind": item_id, "count": 1})
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
                self.add_item("potion", 2)
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

    def use_potion_hotkey(self) -> None:
        for i, slot in enumerate(self.player["inventory"]):
            if slot["id"] == "potion" and self.player["hp"] < self.player["hp_max"]:
                self.toast(self.use_slot(i), "#8ee08e")
                return
        self.toast("Зелий нет или здоровье полное", "#c8c8d0")

    # -- save / load --------------------------------------------------------
    def save(self, path: Path = SAVE_PATH) -> bool:
        try:
            data = {"version": 3, "player": self.player, "skill_points": self.skill_points,
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
        for k, v in data.get("player", {}).items():
            if k in self.player and k not in ("inventory", "equip"):
                self.player[k] = v
        inv = data.get("player", {}).get("inventory")
        if isinstance(inv, list):
            self.player["inventory"] = [s for s in inv
                                        if isinstance(s, dict) and s.get("id") in IT.ITEMS][:INV_SLOTS]
        equip = data.get("player", {}).get("equip")
        if isinstance(equip, dict):
            self.player["equip"] = {
                "weapon": equip.get("weapon") if equip.get("weapon") in IT.ITEMS else None,
                "armor": equip.get("armor") if equip.get("armor") in IT.ITEMS else None,
            }
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
# Renderer
# ----------------------------------------------------------------------------
class Renderer:
    def __init__(self, game: Game, width: int, height: int, zoom: int):
        self.game = game
        self.sprites = SP.build_surfaces()
        # villagers share one sprite sheet; tint them apart so they read as
        # different people at a glance
        self.npc_tint = {
            "Крестьянин": (255, 255, 255),
            "Фермер": (206, 240, 178),
            "Кузнец": (252, 214, 172),
            "Старейшина": (255, 255, 255),
        }
        self._tint_cache: dict = {}
        self.resize(width, height, zoom)

    def npc_surface(self, key: str, name: str) -> pygame.Surface:
        tint = self.npc_tint.get(name, (255, 255, 255))
        if tint == (255, 255, 255):
            return self.sprites[key]
        cached = self._tint_cache.get((key, tint))
        if cached is None:
            cached = self.sprites[key].copy()
            cached.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
            self._tint_cache[(key, tint)] = cached
        return cached

    def resize(self, width: int, height: int, zoom: int) -> None:
        self.width, self.height, self.zoom = width, height, zoom
        self.lw, self.lh = width // zoom, height // zoom
        self.logical = pygame.Surface((self.lw, self.lh))
        self._scaled = pygame.Surface((self.lw * zoom, self.lh * zoom))
        self.ox = (width - self.lw * zoom) // 2
        self.oy = (height - self.lh * zoom) // 2
        self.cam_x = self.cam_y = 0.0
        self.view_w = self.lw / TILE
        self.view_h = self.lh / TILE
        self.ui = width / BASE_UI_WIDTH
        self.font_small = self._font(max(10, round(11 * self.ui)))
        self.font = self._font(max(12, round(13 * self.ui)))
        self.font_big = self._font(max(16, round(17 * self.ui)))
        self.font_title = self._font(max(24, round(34 * self.ui)))

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

    def to_logical(self, wx: float, wy: float) -> tuple[float, float]:
        return (wx - self.cam_x) * TILE, (wy - self.cam_y) * TILE

    # -- tiles --------------------------------------------------------------
    def draw_tiles(self, cam_x: float, cam_y: float) -> None:
        s, w = self.logical, self.game.world
        x0, y0 = int(cam_x), int(cam_y)
        wave = math.sin(self.game.frame * 0.04) * 10
        for ty in range(y0 - 1, y0 + int(self.view_h) + 2):
            for tx in range(x0 - 1, x0 + int(self.view_w) + 2):
                px, py = (tx - cam_x) * TILE, (ty - cam_y) * TILE
                if not w.in_bounds(tx, ty):
                    pygame.draw.rect(s, COLORS["void"], (px, py, TILE, TILE))
                    continue
                t = w.tiles[ty][tx]
                h = hash2(tx, ty)
                h2 = hash2(tx * 3.1, ty * 2.7)
                self._draw_tile(s, w, t, px, py, tx, ty, h, h2, wave)

    def _draw_tile(self, s, w, t, px, py, tx, ty, h, h2, wave) -> None:
        if t == T_WATER or t == T_DEEP:
            base = COLORS["water"] if t == T_WATER else COLORS["deep"]
            pygame.draw.rect(s, base, (px, py, TILE, TILE))
            w1 = int(wave * 0.6)
            pygame.draw.rect(s, COLORS["water_l"],
                             (px + 2, py + 4 + w1 % 3, 5, 1))
            pygame.draw.rect(s, COLORS["water_l"],
                             (px + 9, py + 10 - w1 % 3, 4, 1))
            if h > 0.8:
                pygame.draw.rect(s, (170, 214, 244), (px + 5, py + 7, 3, 1))
            return
        if t == T_SAND:
            pygame.draw.rect(s, COLORS["sand"], (px, py, TILE, TILE))
            if h > 0.55:
                pygame.draw.rect(s, COLORS["sand_d"], (px + int(h * 11), py + int(h2 * 11), 2, 2))
            if h2 > 0.75:
                pygame.draw.rect(s, (238, 226, 176), (px + int(h2 * 12), py + int(h * 10), 2, 1))
            return
        if t == T_PATH:
            pygame.draw.rect(s, COLORS["path"], (px, py, TILE, TILE))
            pygame.draw.rect(s, COLORS["path_d"], (px, py, TILE, 1))
            if h > 0.45:
                pygame.draw.rect(s, COLORS["path_d"], (px + int(h * 12), py + int(h2 * 12), 3, 2))
            if h2 > 0.6:
                pygame.draw.rect(s, COLORS["path_l"], (px + int(h2 * 11), py + int(h * 11), 2, 2))
            return
        if t == T_FLOOR:
            pygame.draw.rect(s, COLORS["floor"] if (tx + ty) % 2 == 0 else COLORS["floor2"],
                             (px, py, TILE, TILE))
            for i in range(0, TILE, 4):
                pygame.draw.rect(s, COLORS["floor_d"], (px, py + i, TILE, 1))
            pygame.draw.rect(s, COLORS["floor_d"], (px + 7, py + 2, 1, 2))
            pygame.draw.rect(s, COLORS["floor_d"], (px + 3, py + 10, 1, 2))
            return
        if t == T_CROPS:
            pygame.draw.rect(s, COLORS["grass2"], (px, py, TILE, TILE))
            for i in range(3):
                ox = 2 + i * 5
                pygame.draw.rect(s, COLORS["crops_d"], (px + ox, py + 6, 1, 9))
                pygame.draw.rect(s, COLORS["crops"], (px + ox, py + 3, 1, 3))
                pygame.draw.rect(s, (216, 206, 128), (px + ox, py + 2, 1, 1))
            return
        if t == T_FOREST:
            pygame.draw.rect(s, COLORS["forest"], (px, py, TILE, TILE))
            return
        # grass (default) — very subtle variation so the tile grid stays invisible
        hh = hash2(tx * 0.7, ty * 1.3)
        if hh < 0.34:
            base = (80, 143, 68)
        elif hh > 0.72:
            base = (86, 152, 74)
        else:
            base = (83, 147, 71)
        pygame.draw.rect(s, base, (px, py, TILE, TILE))
        # transition edges where grass meets sand / path / floor
        for (ox, oy, other, edge) in ((0, -1, (T_SAND, T_PATH, T_FLOOR), (0, 0, TILE, 1)),
                                      (0, 1, (T_SAND, T_PATH, T_FLOOR), (0, TILE - 1, TILE, 1)),
                                      (-1, 0, (T_SAND, T_PATH, T_FLOOR), (0, 0, 1, TILE)),
                                      (1, 0, (T_SAND, T_PATH, T_FLOOR), (TILE - 1, 0, 1, TILE))):
            nx, ny = tx + ox, ty + oy
            if w.in_bounds(nx, ny) and w.tiles[ny][nx] in other:
                pygame.draw.rect(s, COLORS["grass_d"], (px + edge[0], py + edge[1], edge[2], edge[3]))
        if h > 0.30:
            pygame.draw.rect(s, COLORS["grass_d"], (px + int(h * 10), py + int(h2 * 9), 4, 2))
        if h2 > 0.40:
            pygame.draw.rect(s, COLORS["grass_l"], (px + int(h2 * 11), py + int(h * 11), 3, 2))
        bx = int(h * 13)
        by = int(h2 * 10)
        pygame.draw.rect(s, COLORS["grass_d"], (px + bx, py + by, 1, 3))
        pygame.draw.rect(s, COLORS["grass_l"], (px + bx + 1, py + by + 1, 1, 2))

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
                pygame.draw.rect(s, (46, 104, 50), (px + 2, py + 7, 12, 7))
                pygame.draw.rect(s, (60, 126, 58), (px + 3, py + 6, 10, 5))
                pygame.draw.rect(s, (150, 180, 90), (px + 5, py + 6, 5, 3))
            elif d["type"] == "lamp":
                pulse = (math.sin(self.game.frame * 0.05 + d["x"]) + 1) / 2
                pygame.draw.rect(s, (58, 40, 26), (px + 7, py + 4, 3, 12))
                pygame.draw.rect(s, (58, 40, 26), (px + 4, py + 8, 9, 2))
                pygame.draw.rect(s, (74, 52, 32), (px + 3, py + 1, 11, 2))
                pygame.draw.rect(s, (46, 32, 20), (px + 4, py + 3, 9, 7))
                glass = (int(200 + 55 * pulse), int(170 + 60 * pulse), int(80 + 60 * pulse))
                pygame.draw.rect(s, glass, (px + 5, py + 4, 7, 5))
                pygame.draw.rect(s, (255, 250, 210), (px + 7, py + 5, 3, 2))
                glow = pygame.Surface((22, 22), pygame.SRCALPHA)
                pygame.draw.circle(glow, (255, 214, 120, int(30 + 30 * pulse)), (11, 11), 10)
                s.blit(glow, (px - 3, py - 9))
            elif d["type"] == "well":
                pygame.draw.ellipse(s, (0, 0, 0, 70), (px + 1, py + 10, 15, 5))
                pygame.draw.rect(s, (112, 112, 118), (px + 2, py + 4, 13, 8))
                pygame.draw.rect(s, (140, 140, 146), (px + 2, py + 3, 13, 2))
                pygame.draw.rect(s, (26, 30, 40), (px + 5, py + 4, 7, 3))
                pygame.draw.rect(s, COLORS["wood2"], (px + 1, py - 4, 3, 10))
                pygame.draw.rect(s, COLORS["wood2"], (px + 12, py - 4, 3, 10))
                pygame.draw.rect(s, COLORS["wood"], (px, py - 7, 16, 3))
                pygame.draw.rect(s, COLORS["wood2"], (px + 6, py - 5, 4, 2))
            elif d["type"] == "barrel":
                pygame.draw.ellipse(s, (0, 0, 0, 60), (px + 3, py + 9, 11, 4))
                pygame.draw.rect(s, COLORS["wood"], (px + 3, py + 1, 10, 11))
                pygame.draw.rect(s, COLORS["wood_l"], (px + 4, py + 1, 2, 11))
                pygame.draw.rect(s, (108, 74, 44), (px + 3, py + 3, 10, 1))
                pygame.draw.rect(s, (108, 74, 44), (px + 3, py + 8, 10, 1))
                pygame.draw.ellipse(s, COLORS["wood_l"], (px + 3, py, 10, 4))
                pygame.draw.ellipse(s, (86, 58, 34), (px + 5, py + 1, 6, 2))

    def draw_corpses(self, cam_x: float, cam_y: float) -> None:
        for c in self.game.corpses:
            alpha = max(0, int(255 * (1 - c["t"] / 1.6)))
            key = "gb_1" if c["kind"] == "brute" else "g_1"
            spr = self.sprites[key].copy()
            spr.set_alpha(alpha)
            self.logical.blit(spr, *self.anchor(c["x"], c["y"], cam_x, cam_y))

    @staticmethod
    def anchor(x: float, y: float, cam_x: float, cam_y: float) -> tuple[float, float]:
        """Sprite is 32x32 and stands on a 16px tile: feet on the tile's bottom edge."""
        return ((x - cam_x + 0.5) * TILE - SPRITE / 2,
                (y - cam_y + 1.0) * TILE - SPRITE)

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
        h = hash2(o["x"], o["y"])
        if o["type"] == "rock":
            pygame.draw.ellipse(s, (0, 0, 0, 55), (px + 1, py + 9, 14, 5))
            pygame.draw.polygon(s, (120, 120, 128), [(px + 8, py - 2), (px + 13, py + 5),
                                                     (px + 10, py + 11), (px + 4, py + 11),
                                                     (px + 2, py + 5)])
            pygame.draw.polygon(s, (152, 152, 160), [(px + 8, py - 1), (px + 11, py + 5),
                                                     (px + 8, py + 7), (px + 4, py + 5)])
            pygame.draw.rect(s, (178, 178, 186), (px + 6, py + 1, 3, 2))
            return
        if o["type"] == "stump":
            pygame.draw.ellipse(s, (0, 0, 0, 50), (px + 2, py + 9, 12, 4))
            pygame.draw.rect(s, COLORS["wood2"], (px + 4, py + 4, 8, 8))
            pygame.draw.ellipse(s, COLORS["wood"], (px + 4, py + 2, 8, 5))
            pygame.draw.ellipse(s, COLORS["wood_l"], (px + 6, py + 3, 4, 2))
            return
        if o["type"] == "fence":
            pygame.draw.rect(s, COLORS["wood2"], (px + 2, py + 6, 2, 9))
            pygame.draw.rect(s, COLORS["wood2"], (px + 12, py + 6, 2, 9))
            pygame.draw.rect(s, COLORS["wood"], (px, py + 8, TILE, 2))
            pygame.draw.rect(s, COLORS["wood"], (px, py + 12, TILE, 2))
            return
        if o["type"] == "tree":
            variant = int(hash2(o["x"] * 1.7, o["y"] * 2.3) * 3) % 3
            gsel = int(hash2(o["x"] * 0.9, o["y"] * 2.1) * 3) % 3
            g0, g1, g2, g3 = (((30, 78, 44), (44, 104, 54), (62, 128, 62), (118, 186, 96)),
                              ((26, 70, 50), (38, 94, 58), (54, 116, 68), (100, 168, 92)),
                              ((38, 86, 40), (52, 110, 50), (72, 138, 60), (128, 190, 90)))[gsel]
            sc = 0.85 + hash2(o["y"] * 1.4, o["x"] * 2.6) * 0.3
            sway = math.sin(self.game.frame * 0.02 + o["x"] * 1.3) * 1.2
            tx = px + 8 + sway
            ty = py + 6
            sh = pygame.Surface((30, 10), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, 115), (0, 0, 30, 10))
            s.blit(sh, (px - 7, py + 12))
            # trunk with roots
            pygame.draw.rect(s, COLORS["wood2"], (px + 6, py - 4, 5, 20))
            pygame.draw.rect(s, COLORS["wood"], (px + 7, py - 4, 2, 20))
            pygame.draw.rect(s, COLORS["wood2"], (px + 3, py + 13, 4, 3))
            pygame.draw.rect(s, COLORS["wood2"], (px + 10, py + 13, 4, 3))
            if variant == 0:      # broadleaf
                pygame.draw.circle(s, g0, (tx, ty - 6), int(11 * sc))
                pygame.draw.circle(s, g1, (tx - 4, ty - 4), int(8 * sc))
                pygame.draw.circle(s, g1, (tx + 4, ty - 5), int(8 * sc))
                pygame.draw.circle(s, g2, (tx, ty - 9), int(7 * sc))
                for (lx, ly, lr) in ((-6, -3, 3), (5, -7, 3), (-2, -13, 3), (3, -12, 2)):
                    pygame.draw.circle(s, g1, (tx + lx, ty + ly), max(1, int(lr * sc)))
                pygame.draw.circle(s, g3, (tx - 2, ty - 11), max(1, int(4 * sc)))
            elif variant == 1:    # pine
                for (cy, w, col) in ((-2, 12, g0), (-9, 9, g1), (-15, 6, g2)):
                    pygame.draw.polygon(s, col, [(tx, ty + cy - 8), (tx - int(w * sc), ty + cy + 3),
                                                 (tx + int(w * sc), ty + cy + 3)])
                pygame.draw.polygon(s, g3, [(tx, ty - 25), (tx - 3, ty - 18), (tx + 3, ty - 18)])
            else:                 # young tree
                pygame.draw.circle(s, g0, (tx, ty - 3), int(8 * sc))
                pygame.draw.circle(s, g1, (tx - 2, ty - 5), int(6 * sc))
                pygame.draw.circle(s, g2, (tx - 3, ty - 7), max(1, int(3 * sc)))
        elif o["type"] == "house":
            style = int(hash2(o["x"] * 3.3, o["y"] * 1.9) * 3) % 3
            hsh = pygame.Surface((44, 42), pygame.SRCALPHA)
            pygame.draw.rect(hsh, (0, 0, 0, 105), (0, 0, 44, 42))
            s.blit(hsh, (px - 3, py - 4))
            roof_l, roof_m = (((168, 68, 56), (128, 48, 42)),
                              ((140, 98, 62), (104, 70, 42)),
                              ((108, 116, 138), (80, 86, 104)))[style]
            roof_d = tuple(int(c * 0.78) for c in roof_m)
            # stone foundation
            pygame.draw.rect(s, (118, 118, 124), (px - 11, py + 20, 38, 6))
            for i in range(0, 38, 6):
                pygame.draw.rect(s, (94, 94, 100), (px - 11 + i, py + 22, 1, 4))
            # walls: planks + corner beams
            pygame.draw.rect(s, COLORS["wood"], (px - 10, py - 12, 36, 34))
            for i in range(0, 34, 5):
                pygame.draw.rect(s, COLORS["wood2"], (px - 10, py - 12 + i, 36, 1))
            pygame.draw.rect(s, COLORS["wood2"], (px - 10, py - 12, 3, 34))
            pygame.draw.rect(s, COLORS["wood2"], (px + 23, py - 12, 3, 34))
            pygame.draw.rect(s, COLORS["wood_l"], (px - 10, py - 12, 36, 1))
            # eaves shadow
            pygame.draw.rect(s, (74, 50, 30), (px - 14, py - 12, 44, 4))
            # roof: shingle rows with a ridge line
            for (rx, ry, rw, rh, col) in ((-14, -19, 44, 7, roof_m),
                                          (-16, -25, 48, 7, roof_l),
                                          (-12, -30, 40, 6, roof_m)):
                pygame.draw.rect(s, col, (px + rx, py + ry, rw, rh))
                pygame.draw.rect(s, (206, 190, 164), (px + rx, py + ry, rw, 1))
            for i in range(0, 48, 6):
                pygame.draw.rect(s, roof_d, (px - 16 + i, py - 25, 1, 7))
            pygame.draw.rect(s, roof_d, (px - 10, py - 31, 36, 2))
            pygame.draw.rect(s, tuple(min(255, int(c * 1.25)) for c in roof_l),
                             (px - 9, py - 30, 34, 1))
            # window: frame, glass glow, cross bars, shutters
            glow = int(150 + math.sin(self.game.frame * 0.06 + o["x"]) * 40)
            pygame.draw.rect(s, (74, 50, 30), (px - 6, py - 5, 14, 14))
            pygame.draw.rect(s, (min(255, glow), min(255, glow + 40), 130), (px - 5, py - 4, 12, 12))
            pygame.draw.rect(s, (74, 50, 30), (px - 1, py - 4, 2, 12))
            pygame.draw.rect(s, (74, 50, 30), (px - 5, py + 1, 12, 2))
            pygame.draw.rect(s, (168, 122, 74), (px - 8, py - 5, 2, 14))
            pygame.draw.rect(s, (168, 122, 74), (px + 8, py - 5, 2, 14))
            # door with frame and handle (+ porch step on some houses)
            pygame.draw.rect(s, (74, 50, 30), (px + 12, py + 1, 12, 23))
            pygame.draw.rect(s, COLORS["door"], (px + 13, py + 2, 10, 22))
            pygame.draw.rect(s, (92, 62, 36), (px + 13, py + 12, 10, 1))
            pygame.draw.rect(s, (92, 62, 36), (px + 17, py + 2, 1, 22))
            pygame.draw.rect(s, (232, 200, 112), (px + 20, py + 13, 2, 2))
            if style == 1:
                pygame.draw.rect(s, (146, 146, 152), (px + 11, py + 24, 14, 3))
                pygame.draw.rect(s, (112, 112, 118), (px + 11, py + 27, 14, 1))
            # chimney with cap + smoke
            pygame.draw.rect(s, (98, 98, 104), (px + 15, py - 42, 9, 11))
            pygame.draw.rect(s, (126, 126, 132), (px + 14, py - 44, 11, 3))
            sm = (self.game.frame * 0.04 + o["x"]) % 1
            puff = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.circle(puff, (208, 208, 214, int(150 * (1 - sm))), (3, 3), 3)
            s.blit(puff, (px + 17, py - 50 - sm * 14))

    def draw_drop(self, d: dict, cam_x: float, cam_y: float) -> None:
        s = self.logical
        bob = math.sin(self.game.frame * 0.12 + d["x"]) * 1.5
        px, py = (d["x"] - cam_x) * TILE, (d["y"] - cam_y) * TILE + bob
        ground_y = (d["y"] - cam_y) * TILE + 5
        sh = pygame.Surface((12, 5), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 70), (0, 0, 12, 5))
        s.blit(sh, (px + 2, ground_y))
        glow = pygame.Surface((16, 16), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 240, 170, 45), (8, 8), 7)
        s.blit(glow, (px, py - 6))
        key = "icon_" + ("gold" if d["kind"] == "gold" else IT.item_icon(d["kind"]))
        icon = self.sprites.get(key)
        if icon:
            s.blit(pygame.transform.scale(icon, (12, 12)), (px + 2, py - 8))

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

    def draw_shadow(self, x: float, y: float, cam_x: float, cam_y: float, w: int = 14) -> None:
        sh = pygame.Surface((w, 6), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 80), (0, 0, w, 6))
        self.logical.blit(sh, ((x - cam_x + 0.5) * TILE - w / 2, (y - cam_y + 0.95) * TILE - 3))

    def draw_player(self, cam_x: float, cam_y: float) -> None:
        p = self.game.player
        key, flip = self.player_sprite_key(p["dir"], p["frame"] if p["moving"] else 0)
        self.draw_shadow(p["x"], p["y"], cam_x, cam_y)
        ax, ay = self.anchor(p["x"], p["y"], cam_x, cam_y)
        bob = -1 if (p["moving"] and p["frame"]) else 0
        self.blit_sprite(key, ax, ay + bob, flip, p["hurt_t"] > 0)

        # weapon in hand when equipped
        wid = p["equip"]["weapon"]
        if wid and p["atk_anim"] <= 0:
            hx = ax + (SPRITE - 10 if not flip else 2)
            hy = ay + 20 + bob
            pygame.draw.line(self.logical, SP.PAL["i"], (hx, hy), (hx, hy + 9), 2)
            pygame.draw.line(self.logical, SP.PAL["m"], (hx, hy), (hx, hy + 8), 1)

        if p["atk_anim"] > 0:
            t = 1 - p["atk_anim"] / 0.28
            fx, fy = self.game.face_dir()
            ang = math.atan2(fy, fx) - 1.2 + t * 1.7
            cx, cy = (p["x"] - cam_x + 0.5) * TILE, (p["y"] - cam_y + 0.2) * TILE
            bx, by = math.cos(ang), math.sin(ang)
            pygame.draw.line(self.logical, SP.PAL["i"], (cx + bx * 6, cy + by * 6),
                             (cx + bx * 18, cy + by * 18), 3)
            pygame.draw.line(self.logical, SP.PAL["M"], (cx + bx * 7, cy + by * 7),
                             (cx + bx * 18, cy + by * 18), 1)
            for i in range(6):
                a = ang - 0.55 + i * 0.22
                pygame.draw.rect(self.logical, (255, 255, 210),
                                 (cx + math.cos(a) * 11, cy + math.sin(a) * 11, 2, 2))
            swing = pygame.Surface((44, 44), pygame.SRCALPHA)
            pygame.draw.circle(swing, (255, 255, 220, 45), (22, 22), 18, 3)
            self.logical.blit(swing, (cx - 22, cy - 22))

        if p["hp"] < p["hp_max"]:
            self.draw_hp_bar(p["x"], p["y"] - 0.55, p["hp"], p["hp_max"], cam_x, cam_y)

    def draw_npc(self, n: dict, cam_x: float, cam_y: float) -> None:
        self.draw_shadow(n["x"], n["y"], cam_x, cam_y)
        base = "mage" if n["kind"] == "mage" else "npc"
        key = base + ("_2" if n["anim_t"] > 0.3 else "_1") + ("_f" if n["dir"] == "left" else "")
        ax, ay = self.anchor(n["x"], n["y"], cam_x, cam_y)
        bob = math.sin(self.game.frame * 0.06 + n["x"]) * 1.2
        self.logical.blit(self.npc_surface(key, n["name"]), (ax, ay + bob))
        if math.hypot(n["x"] - self.game.player["x"], n["y"] - self.game.player["y"]) < 2.0:
            bob2 = math.sin(self.game.frame * 0.12) * 2
            x = (n["x"] - cam_x + 0.5) * TILE
            pygame.draw.rect(self.logical, (255, 240, 150), (x - 2, ay - 14 + bob2, 4, 6))
            pygame.draw.rect(self.logical, (255, 240, 150), (x - 3, ay - 6 + bob2, 6, 2))

    def draw_mob(self, m: dict, cam_x: float, cam_y: float) -> None:
        self.draw_shadow(m["x"], m["y"], cam_x, cam_y)
        base = "gb" if m["kind"] == "brute" else "g"
        key = base + ("_2" if (m["moving"] and m["frame"]) else "_1")
        ax, ay = self.anchor(m["x"], m["y"], cam_x, cam_y)
        bob = -1 if (m["moving"] and m["frame"]) else 0
        lunge = 2 if m["atk_t"] > 0 else 0
        lx = lunge * (-1 if m["dir"] == "left" else 1 if m["dir"] == "right" else 0)
        ly = lunge * (-1 if m["dir"] == "up" else 1 if m["dir"] == "down" else 0)
        self.blit_sprite(key, ax + lx, ay + ly + bob, m["dir"] == "left", m["hurt_t"] > 0)
        if (math.hypot(m["x"] - self.game.player["x"], m["y"] - self.game.player["y"]) < 6.5
                and m["attack_cd"] > 0.7):
            x = (m["x"] - cam_x + 0.5) * TILE
            pygame.draw.rect(self.logical, (255, 90, 60), (x - 1, ay - 14, 3, 6))
            pygame.draw.rect(self.logical, (255, 90, 60), (x - 1, ay - 7, 3, 3))
        if m["hp"] < m["hp_max"]:
            self.draw_hp_bar(m["x"], m["y"] - 0.55, m["hp"], m["hp_max"], cam_x, cam_y)

    def draw_hp_bar(self, x, y, hp, hp_max, cam_x, cam_y, w=16) -> None:
        s = self.logical
        px = (x - cam_x + 0.5) * TILE - w / 2
        py = (y - cam_y) * TILE
        ratio = max(0.0, hp / hp_max)
        pygame.draw.rect(s, (18, 18, 24), (px - 1, py - 1, w + 2, 5))
        pygame.draw.rect(s, (110, 28, 28), (px, py, w, 3))
        pygame.draw.rect(s, (96, 214, 96) if ratio > 0.5 else (226, 84, 72), (px, py, w * ratio, 3))

    def draw_particle(self, p: dict, cam_x: float, cam_y: float) -> None:
        alpha = max(0.0, 1 - p["t"] / p["life"])
        col = pygame.Color(p["color"])
        col.a = int(255 * alpha)
        surf = pygame.Surface((3, 3), pygame.SRCALPHA)
        surf.fill(col)
        self.logical.blit(surf, ((p["x"] - cam_x) * TILE, (p["y"] - cam_y) * TILE))

    # -- native text --------------------------------------------------------
    def draw_text_layer(self, screen: pygame.Surface) -> None:
        g = self.game
        for n in g.npcs:
            if not (self.cam_x - 2 < n["x"] < self.cam_x + self.view_w + 2
                    and self.cam_y - 2 < n["y"] < self.cam_y + self.view_h + 2):
                continue
            ax, ay = self.anchor(n["x"], n["y"], self.cam_x, self.cam_y)
            label = self.font_small.render(n["name"], True, (248, 248, 254))
            x = (ax + SPRITE / 2) * self.zoom - label.get_width() / 2 + self.ox
            y = ay * self.zoom - label.get_height() - 2 + self.oy
            pad_x, pad_y = self.s(7), self.s(3)
            pill = pygame.Surface((label.get_width() + pad_x * 2,
                                   label.get_height() + pad_y * 2), pygame.SRCALPHA)
            pygame.draw.rect(pill, (12, 14, 22, 185),
                             (0, 0, pill.get_width(), pill.get_height()),
                             border_radius=self.s(7))
            pygame.draw.rect(pill, (206, 192, 140, 110),
                             (0, 0, pill.get_width(), pill.get_height()), 1,
                             border_radius=self.s(7))
            screen.blit(pill, (x - pad_x, y - pad_y))
            screen.blit(label, (x, y))

        for f in g.floaters:
            alpha = max(0.0, 1 - f["t"] / f["life"])
            col = pygame.Color(f["color"])
            col.a = int(255 * alpha)
            txt = self.font_small.render(f["text"], True, col)
            lx, ly = self.to_logical(f["x"], f["y"])
            screen.blit(txt, (lx * self.zoom - txt.get_width() / 2 + self.ox,
                              ly * self.zoom - self.s(16) + self.oy))

    # -- HUD ----------------------------------------------------------------
    def panel(self, screen, rect, fill=(10, 12, 20, 214), border=UI_EDGE, radius=0) -> None:
        surf = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        if radius:
            pygame.draw.rect(surf, fill, (0, 0, rect[2], rect[3]), border_radius=radius)
            pygame.draw.rect(surf, border, (0, 0, rect[2], rect[3]), 1, border_radius=radius)
        else:
            surf.fill(fill)
            pygame.draw.rect(surf, border, (0, 0, rect[2], rect[3]), 1)
        screen.blit(surf, (rect[0], rect[1]))

    def draw_hud(self, screen) -> None:
        g, p, S = self.game, self.game.player, self.s
        self.panel(screen, (S(10), S(10), S(258), S(88)), radius=S(6))
        screen.blit(self.font_big.render("Пиксельное приключение", True, (250, 246, 226)), (S(20), S(16)))
        screen.blit(self.font_small.render(
            f"Ур. {p['level']}    XP {p['xp']}/{p['xp_next']}", True, (186, 206, 236)), (S(20), S(40)))

        pygame.draw.rect(screen, (28, 28, 36), (S(20), S(58), S(180), S(9)))
        pygame.draw.rect(screen, (150, 40, 40), (S(20), S(58), S(180), S(9)))
        pygame.draw.rect(screen, (92, 214, 108),
                         (S(20), S(58), S(180) * max(0.0, p["hp"] / p["hp_max"]), S(9)))
        hp_txt = self.font_small.render(f"{max(0, math.ceil(p['hp']))} / {int(p['hp_max'])}",
                                        True, (255, 255, 255))
        screen.blit(hp_txt, (S(206), S(57)))

        screen.blit(self.font_small.render(
            f"Золото: {p['gold']}", True, GOLD), (S(20), S(74)))
        atk = 5 + self.game.attack_bonus()
        screen.blit(self.font_small.render(
            f"Атака: {atk}    Защита: {self.game.defense()}", True, (232, 200, 170)),
            (S(120), S(74)))

        self.panel(screen, (S(10), S(106), S(258), S(50)), fill=(10, 12, 20, 190), radius=S(6))
        for i, line in enumerate(("ПРОБЕЛ / ЛКМ — атака", "I — сумка   Q — квесты   K — навыки",
                                  f"Очки навыков: {g.skill_points}")):
            screen.blit(self.font_small.render(line, True, (204, 218, 242)), (S(20), S(110 + i * 15)))

        ty = self.height - S(124)
        for t in reversed(g.toasts[-4:]):
            a = t["t"] / 0.2 if t["t"] < 0.2 else (t["life"] - t["t"]) / 0.6 if t["t"] > t["life"] - 0.6 else 1
            surf = pygame.Surface((S(360), S(24)), pygame.SRCALPHA)
            pygame.draw.rect(surf, (10, 12, 18, int(205 * a)), (0, 0, S(360), S(24)),
                             border_radius=S(4))
            screen.blit(surf, (S(10), ty))
            txt = self.font_small.render(t["text"], True, pygame.Color(t["color"]))
            txt.set_alpha(int(255 * a))
            screen.blit(txt, (S(20), ty + S(6)))
            ty -= S(28)

        if g.show_inventory:
            self.draw_inventory(screen)
        if g.show_quests:
            self.draw_quest_panel(screen)
        if g.show_skills:
            self.draw_skill_panel(screen)
        if g.dialog:
            self.draw_dialog(screen)

    # -- inventory ----------------------------------------------------------
    def draw_inventory(self, screen) -> None:
        g, S = self.game, self.s
        cols, rows = 5, 4
        cell = S(64)
        pad = S(10)
        w = pad * 2 + cols * (cell + pad) + S(250)
        h = pad * 2 + rows * (cell + pad) + S(40)
        x = (self.width - w) // 2
        y = (self.height - h) // 2
        self.panel(screen, (x, y, w, h), fill=(12, 15, 24, 240), border=(140, 160, 200), radius=S(8))
        screen.blit(self.font_big.render("Сумка", True, (250, 240, 210)), (x + pad, y + pad))
        screen.blit(self.font_small.render(
            f"{len(g.player['inventory'])}/{INV_SLOTS} слотов   •   стрелки — выбор   •   "
            "E / Enter — использовать   •   I — закрыть", True, (186, 202, 226)),
            (x + pad + S(90), y + pad + S(8)))

        grid_x = x + pad
        grid_y = y + pad + S(34)
        mouse = pygame.mouse.get_pos()
        hover_index = None
        for i in range(INV_SLOTS):
            cx = grid_x + (i % cols) * (cell + pad)
            cy = grid_y + (i // cols) * (cell + pad)
            rect = pygame.Rect(cx, cy, cell, cell)
            if rect.collidepoint(mouse):
                hover_index = i
            sel = (i == g.inv_cursor)
            pygame.draw.rect(screen, (30, 38, 54) if sel else (20, 25, 36), rect, border_radius=S(6))
            pygame.draw.rect(screen, (250, 220, 130) if sel else (62, 74, 98), rect, 2,
                             border_radius=S(6))
            inv = g.player["inventory"]
            if i < len(inv):
                slot = inv[i]
                icon = self.sprites.get("icon_" + IT.item_icon(slot["id"]))
                if icon:
                    big = pygame.transform.scale(icon, (S(44), S(44)))
                    screen.blit(big, (cx + (cell - S(44)) / 2, cy + S(6)))
                if slot["count"] > 1:
                    cnt = self.font_small.render(str(slot["count"]), True, (255, 255, 255))
                    bw, bh = cnt.get_width() + S(8), cnt.get_height() + S(2)
                    badge = pygame.Surface((bw, bh), pygame.SRCALPHA)
                    pygame.draw.rect(badge, (12, 14, 22, 215), (0, 0, bw, bh), border_radius=S(4))
                    screen.blit(badge, (cx + cell - bw - S(4), cy + cell - bh - S(4)))
                    screen.blit(cnt, (cx + cell - bw, cy + cell - bh - S(3)))
                equipped = slot["id"] in (g.player["equip"]["weapon"], g.player["equip"]["armor"])
                if equipped:
                    bx, by = cx + S(5), cy + S(5)
                    pygame.draw.rect(screen, (26, 40, 26), (bx, by, S(19), S(19)))
                    pygame.draw.rect(screen, (128, 226, 128), (bx, by, S(19), S(19)), 1)
                    pygame.draw.lines(screen, (150, 240, 150), False,
                                      [(bx + S(4), by + S(10)), (bx + S(8), by + S(14)),
                                       (bx + S(15), by + S(5))], 2)

        # right column: details + equipment
        px = grid_x + cols * (cell + pad) + pad
        py = grid_y
        inv = g.player["inventory"]
        cursor = hover_index if hover_index is not None else g.inv_cursor
        self.panel(screen, (px, py, S(238), S(150)), fill=(16, 20, 30, 230), border=(90, 108, 142),
                   radius=S(6))
        if 0 <= cursor < len(inv):
            item_id = inv[cursor]["id"]
            data = IT.ITEMS[item_id]
            screen.blit(self.font.render(data["name"], True, (252, 244, 216)), (px + S(10), py + S(8)))
            screen.blit(self.font_small.render(data["desc"], True, (182, 198, 222)),
                        (px + S(10), py + S(32)))
            stats = []
            if "atk" in data:
                stats.append(f"Атака +{data['atk']}")
            if "def" in data:
                stats.append(f"Защита +{data['def']}")
            if "heal" in data:
                stats.append(f"Лечит {data['heal']} HP")
            stats.append(f"Цена {data['value']} золота")
            for i, line in enumerate(stats):
                screen.blit(self.font_small.render(line, True, (232, 214, 160)),
                            (px + S(10), py + S(56 + i * 18)))
            screen.blit(self.font_small.render(
                {"consumable": "E — использовать", "weapon": "E — взять в руку",
                 "armor": "E — надеть"}.get(data["kind"], "Материал для продажи"),
                True, (140, 200, 255)), (px + S(10), py + S(126)))
        else:
            screen.blit(self.font_small.render("Пустой слот", True, (140, 152, 176)),
                        (px + S(10), py + S(8)))

        eq_y = py + S(162)
        self.panel(screen, (px, eq_y, S(238), S(96)), fill=(16, 20, 30, 230), border=(90, 108, 142),
                   radius=S(6))
        screen.blit(self.font.render("Экипировка", True, (252, 244, 216)), (px + S(10), eq_y + S(6)))
        for i, (key, label) in enumerate((("weapon", "Оружие"), ("armor", "Броня"))):
            item_id = g.player["equip"][key]
            name = IT.item_name(item_id) if item_id else "—"
            screen.blit(self.font_small.render(f"{label}: {name}", True, (206, 220, 240)),
                        (px + S(10), eq_y + S(28 + i * 20)))
        screen.blit(self.font_small.render(
            f"Итого: атака {5 + g.attack_bonus()}, защита {g.defense()}",
            True, (240, 210, 140)), (px + S(10), eq_y + S(70)))

    def draw_quest_panel(self, screen) -> None:
        g, S = self.game, self.s
        h = S(34 + len(g.quests) * 44)
        self.panel(screen, (S(330), S(20), S(440), h), fill=(12, 15, 24, 232), border=(120, 160, 210),
                   radius=S(6))
        screen.blit(self.font.render("Журнал квестов   (Q — закрыть)", True, (255, 255, 255)),
                    (S(346), S(28)))
        yy = S(56)
        for q in g.quests:
            col = (144, 224, 144) if q["done"] else (232, 232, 242)
            screen.blit(self.font_small.render(("[готово] " if q["done"] else "[ ] ") + q["title"],
                                               True, col), (S(346), yy))
            screen.blit(self.font_small.render(q["desc"], True, (174, 190, 214)), (S(358), yy + S(15)))
            if not q["done"]:
                screen.blit(self.font_small.render(f"{q['progress']}/{q['goal']}", True, (120, 200, 255)),
                            (S(700), yy + S(15)))
            yy += S(44)

    def draw_skill_panel(self, screen) -> None:
        g, S = self.game, self.s
        h = S(42 + len(g.skills) * 48)
        self.panel(screen, (S(330), S(20), S(440), h), fill=(12, 15, 24, 234), border=(150, 130, 220),
                   radius=S(6))
        screen.blit(self.font.render(f"Дерево навыков   (K — закрыть)   Очки: {g.skill_points}",
                                     True, (255, 255, 255)), (S(346), S(28)))
        yy = S(58)
        for i, sk in enumerate(g.skills):
            ok = g.can_learn(sk)
            col = (140, 232, 140) if sk["learned"] else (242, 242, 252) if ok else (132, 136, 150)
            label = f"[{i + 1}] {sk['name']}"
            if sk["learned"]:
                label += "  (изучено)"
            elif sk["req"] and not all(g.has_skill(r) for r in sk["req"]):
                label += "  требует " + ", ".join(sk["req"])
            screen.blit(self.font_small.render(label, True, col), (S(346), yy))
            screen.blit(self.font_small.render(sk["desc"], True, (174, 190, 214)), (S(362), yy + S(15)))
            yy += S(48)
        screen.blit(self.font_small.render("Нажми 1–4, чтобы изучить доступный навык.",
                                           True, (152, 172, 202)), (S(346), S(20) + h - S(20)))

    def draw_dialog(self, screen) -> None:
        if not self.game.dialog:
            return
        d, S = self.game.dialog, self.s
        w, h = S(620), S(96)
        x, y = (self.width - w) / 2, self.height - h - S(46)
        self.panel(screen, (int(x), int(y), w, h), fill=(10, 13, 22, 240), border=(226, 202, 132),
                   radius=S(8))
        screen.blit(self.font.render(d["name"], True, (255, 226, 140)), (x + S(18), y + S(12)))
        screen.blit(self.font_small.render(d["line"], True, (240, 242, 250)), (x + S(18), y + S(40)))
        screen.blit(self.font_small.render("E / Q — закрыть", True, (162, 178, 202)),
                    (x + w - S(130), y + h - S(24)))

    # -- menus --------------------------------------------------------------
    def draw_title_backdrop(self, screen: pygame.Surface, t: float) -> None:
        """The live world behind the title screen, slowly panning, dimmed."""
        g = self.game
        cam_x = VILLAGE_CX - self.view_w / 2 + math.sin(t * 0.12) * 6
        cam_y = VILLAGE_CY - self.view_h / 2 + math.cos(t * 0.09) * 3
        cam_x = max(0.0, min(MAP_W - self.view_w, cam_x))
        cam_y = max(0.0, min(MAP_H - self.view_h, cam_y))
        self.cam_x, self.cam_y = cam_x, cam_y
        self.logical.fill(COLORS["void"])
        self.draw_tiles(cam_x, cam_y)
        self.draw_decor(cam_x, cam_y)
        for o in g.world.objects:
            if cam_x - 3 < o["x"] < cam_x + self.view_w + 3 and cam_y - 3 < o["y"] < cam_y + self.view_h + 4:
                self.draw_object(o, cam_x, cam_y)
        for n in g.npcs:
            self.draw_npc(n, cam_x, cam_y)
        self.draw_player(cam_x, cam_y)

        pygame.transform.scale(self.logical, (self.lw * self.zoom, self.lh * self.zoom), self._scaled)
        screen.fill((8, 12, 20))
        screen.blit(self._scaled, (self.ox, self.oy))

        # dim + vignette
        dim = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        dim.fill((6, 10, 20, 150))
        screen.blit(dim, (0, 0))
        vignette = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        for i in range(6):
            a = 26 - i * 4
            pygame.draw.rect(vignette, (0, 0, 0, max(0, a)),
                             (i * self.s(18), i * self.s(14),
                              self.width - i * self.s(36), self.height - i * self.s(28)),
                             self.s(18))
        screen.blit(vignette, (0, 0))

        # fireflies (sparse, so they don't fight the menu for attention)
        for i in range(14):
            fx = (math.sin(t * 0.3 + i * 1.7) * 0.5 + 0.5) * self.width
            fy = (math.cos(t * 0.23 + i * 2.3) * 0.5 + 0.5) * self.height
            a = int(110 + 100 * math.sin(t * 2 + i))
            glow = pygame.Surface((self.s(9), self.s(9)), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 236, 160, max(0, min(255, a))),
                               (self.s(4), self.s(4)), self.s(2))
            screen.blit(glow, (fx, fy))

    def draw_menu(self, screen, title: str, subtitle: str, entries, selected: int,
                  t: float, backdrop: bool = True, note: str = "") -> None:
        S = self.s
        if backdrop:
            self.draw_title_backdrop(screen, t)
        else:
            screen.fill((10, 14, 24))

        row_h = S(52)
        panel_w = S(660)
        panel_h = S(150) + len(entries) * row_h + (S(52) if note else S(44))
        px = (self.width - panel_w) // 2
        py = (self.height - panel_h) // 2 - S(20)

        # hard-edged pixel drop shadow
        screen.blit(pygame.Surface((1, 1)))
        sh = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 130))
        screen.blit(sh, (px + S(7), py + S(7)))

        # pixel-style frame: flat panel, 2px border, corner ticks
        self.panel(screen, (px, py, panel_w, panel_h), fill=(13, 16, 26, 252),
                   border=(150, 128, 78), radius=0)
        pygame.draw.rect(screen, (222, 196, 130), (px, py, panel_w, panel_h), 2)
        tick = S(14)
        for (cx, cy, dx, dy) in ((px, py, 1, 1), (px + panel_w, py, -1, 1),
                                 (px, py + panel_h, 1, -1), (px + panel_w, py + panel_h, -1, -1)):
            pygame.draw.rect(screen, (246, 224, 156),
                             (min(cx, cx + dx * tick), min(cy, cy + dy * tick), tick, 3))
            pygame.draw.rect(screen, (246, 224, 156),
                             (min(cx, cx + dx * 3), min(cy, cy + dy * tick), 3, tick))

        title_s = self.font_title.render(title, True, (255, 238, 176))
        title_sh = self.font_title.render(title, True, (24, 16, 6))
        tx = self.width / 2 - title_s.get_width() / 2
        ty = py + S(26)
        screen.blit(title_sh, (tx + 3, ty + 3))
        screen.blit(title_s, (tx, ty))
        pygame.draw.rect(screen, (150, 128, 78),
                         (px + S(60), ty + title_s.get_height() + S(10), panel_w - S(120), 1))
        if subtitle:
            sub = self.font.render(subtitle, True, (214, 226, 246))
            screen.blit(sub, (self.width / 2 - sub.get_width() / 2,
                              ty + title_s.get_height() + S(18)))

        mouse = pygame.mouse.get_pos()
        y = ty + title_s.get_height() + (S(66) if subtitle else S(44))
        self.menu_rects = []
        for i, (label, enabled) in enumerate(entries):
            rect = pygame.Rect(px + S(56), y, panel_w - S(112), row_h - S(8))
            self.menu_rects.append((rect, i, enabled))
            hovered = rect.collidepoint(mouse) and enabled
            cur = (i == selected) or hovered
            if cur and enabled:
                # dark plate + bright gold text: the active row is the most contrasty
                pygame.draw.rect(screen, (34, 28, 16), rect)
                pygame.draw.rect(screen, (248, 226, 152), rect, 2)
            col = ((255, 236, 158) if (cur and enabled)
                   else (204, 214, 232) if enabled else (104, 112, 128))
            txt = self.font_big.render(label, True, col)
            screen.blit(txt, (self.width / 2 - txt.get_width() / 2,
                              rect[1] + (rect[3] - txt.get_height()) / 2))
            if cur and enabled:
                if math.sin(t * 6) > -0.35:
                    # drawn, not a font glyph: SysFont has no reliable ▶
                    ax0 = rect[0] + S(16)
                    ay0 = rect[1] + rect[3] / 2
                    pygame.draw.polygon(screen, (255, 226, 140),
                                        [(ax0, ay0 - S(8)), (ax0 + S(10), ay0),
                                         (ax0, ay0 + S(8))])
            y += row_h

        footer_y = py + panel_h - S(38)
        pygame.draw.rect(screen, (150, 128, 78), (px + S(60), footer_y - S(10), panel_w - S(120), 1))
        if note:
            n = self.font_small.render(note, True, (186, 204, 228))
            screen.blit(n, (self.width / 2 - n.get_width() / 2, footer_y))
        ver = self.font_small.render("Пиксельное приключение — версия 1.3", True, (150, 164, 188))
        screen.blit(ver, (self.width / 2 - ver.get_width() / 2, footer_y + S(16)))


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


def best_res_index_for_desktop() -> int:
    try:
        dw, dh = pygame.display.get_desktop_sizes()[0]
    except Exception:
        return DEFAULT_RES_INDEX
    for i in range(len(RESOLUTIONS) - 1, -1, -1):
        if RESOLUTIONS[i][0] <= dw and RESOLUTIONS[i][1] <= dh:
            return i
    return 0


def apply_display(res_index: int, fullscreen: bool):
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


# ----------------------------------------------------------------------------
# Input
# ----------------------------------------------------------------------------
KEYMAP = {
    pygame.K_w: "up", pygame.K_UP: "up",
    pygame.K_s: "down", pygame.K_DOWN: "down",
    pygame.K_a: "left", pygame.K_LEFT: "left",
    pygame.K_d: "right", pygame.K_RIGHT: "right",
}
MOVE_KEYS = set(KEYMAP)


def gather_input(keys) -> dict:
    inp = {"up": False, "down": False, "left": False, "right": False}
    for k, name in KEYMAP.items():
        if keys[k]:
            inp[name] = True
    return inp


def handle_game_key(game: Game, key: int) -> None:
    if game.show_inventory:
        inv_len = len(game.player["inventory"])
        if key in (pygame.K_LEFT, pygame.K_a):
            game.inv_cursor = (game.inv_cursor - 1) % INV_SLOTS
        elif key in (pygame.K_RIGHT, pygame.K_d):
            game.inv_cursor = (game.inv_cursor + 1) % INV_SLOTS
        elif key in (pygame.K_UP, pygame.K_w):
            game.inv_cursor = (game.inv_cursor - 5) % INV_SLOTS
        elif key in (pygame.K_DOWN, pygame.K_s):
            game.inv_cursor = (game.inv_cursor + 5) % INV_SLOTS
        elif key in (pygame.K_e, pygame.K_RETURN, pygame.K_KP_ENTER):
            msg = game.use_slot(game.inv_cursor)
            if msg:
                game.toast(msg, "#9ad7ff")
            game.inv_cursor = min(game.inv_cursor, max(0, INV_SLOTS - 1))
        elif key == pygame.K_i:
            game.show_inventory = False
        return

    if key == pygame.K_i:
        game.show_inventory = True
        game.show_quests = False
        game.show_skills = False
    elif key == pygame.K_e:
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
        game.learn(game.skills[{pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3}[key]])
    elif key == pygame.K_a and game.has_skill("s_heal"):
        game.use_potion_hotkey()


# ----------------------------------------------------------------------------
# Main loop with menus
# ----------------------------------------------------------------------------
def run() -> int:
    pygame.init()
    pygame.display.set_caption("Pixel RPG Adventure 1.3")

    cfg = load_config()
    res_index = parse_res_arg(sys.argv)
    if res_index is None:
        res_index = max(0, min(len(RESOLUTIONS) - 1, cfg.get("res_index", DEFAULT_RES_INDEX)))
    fullscreen = bool(cfg.get("fullscreen", False)) or "--fullscreen" in sys.argv
    if not fullscreen:
        res_index = min(res_index, best_res_index_for_desktop())

    screen, width, height, zoom = apply_display(res_index, fullscreen)
    game = Game()
    renderer = Renderer(game, width, height, zoom)
    clock = pygame.time.Clock()
    has_save = SAVE_PATH.exists()

    state = "title"
    selected = 0
    settings_from = "title"
    t = 0.0
    note = ""
    running = True

    while running:
        dt = min(0.05, clock.tick(FPS) / 1000.0)
        t += dt
        entries: list[tuple[str, bool]] = []

        if state == "title":
            entries = [("Новая игра", True),
                       ("Продолжить" + ("" if has_save else "   — нет сохранения"), has_save),
                       ("Настройки", True),
                       ("Выход", True)]
        elif state == "pause":
            entries = [("Продолжить", True), ("Сохранить", True),
                       ("Загрузить" + ("" if has_save else "   — нет сохранения"), has_save),
                       ("Настройки", True), ("В главное меню", True), ("Выход", True)]
        elif state == "settings":
            entries = [(f"{w} x {h}" + ("   (Full HD)" if (w, h) == (1920, 1080) else
                                        "   (HD)" if (w, h) == (1280, 720) else ""), True)
                       for (w, h, _z) in RESOLUTIONS]
            entries.append((f"Полный экран: {'включён' if fullscreen else 'выключен'}", True))
            entries.append(("Назад", True))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    screen, width, height, zoom = apply_display(res_index, fullscreen)
                    renderer.resize(width, height, zoom)
                    save_config({"res_index": res_index, "fullscreen": fullscreen})
                    continue
                if state == "play":
                    if event.key == pygame.K_ESCAPE and not (game.show_inventory or game.show_quests
                                                             or game.show_skills or game.dialog):
                        state = "pause"
                        selected = 0
                    elif event.key == pygame.K_F10:
                        state = "pause"
                        selected = 0
                    else:
                        handle_game_key(game, event.key)
                    continue

                # menu navigation
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(entries)
                    while not entries[selected][1]:
                        selected = (selected - 1) % len(entries)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(entries)
                    while not entries[selected][1]:
                        selected = (selected + 1) % len(entries)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    label = entries[selected][0]
                    if state == "settings":
                        if selected < len(RESOLUTIONS):
                            res_index = selected
                            screen, width, height, zoom = apply_display(res_index, fullscreen)
                            renderer.resize(width, height, zoom)
                            save_config({"res_index": res_index, "fullscreen": fullscreen})
                            note = "Разрешение сохранено"
                        elif selected == len(RESOLUTIONS):
                            fullscreen = not fullscreen
                            screen, width, height, zoom = apply_display(res_index, fullscreen)
                            renderer.resize(width, height, zoom)
                            save_config({"res_index": res_index, "fullscreen": fullscreen})
                        else:
                            state = settings_from
                            selected = 0
                            note = ""
                    elif state == "title":
                        if label == "Новая игра":
                            game = Game()
                            renderer.game = game
                            state = "play"
                            note = ""
                        elif label == "Продолжить":
                            if game.load():
                                state = "play"
                                note = ""
                        elif label == "Настройки":
                            settings_from = "title"
                            state = "settings"
                            selected = res_index
                            note = ""
                        else:
                            running = False
                    elif state == "pause":
                        if label == "Продолжить":
                            state = "play"
                        elif label == "Сохранить":
                            game.save()
                            has_save = True
                        elif label == "Загрузить":
                            game.load()
                        elif label == "Настройки":
                            settings_from = "pause"
                            state = "settings"
                            selected = res_index
                        elif label == "В главное меню":
                            state = "title"
                            selected = 0
                        else:
                            running = False
                elif event.key == pygame.K_ESCAPE:
                    if state == "settings":
                        state = settings_from
                        selected = 0
                        note = ""
                    elif state == "pause":
                        state = "play"
                    elif state == "title":
                        running = False
            elif event.type == pygame.MOUSEMOTION and state != "play":
                for rect, i, enabled in getattr(renderer, "menu_rects", []):
                    if rect.collidepoint(event.pos) and enabled:
                        selected = i
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state == "play":
                    if not (game.dialog or game.show_inventory):
                        game.attack()
                else:
                    for rect, i, enabled in getattr(renderer, "menu_rects", []):
                        if rect.collidepoint(event.pos) and enabled:
                            selected = i
                            pygame.event.post(pygame.event.Event(
                                pygame.KEYDOWN, key=pygame.K_RETURN))
                            break

        if state == "play":
            game.update(dt, gather_input(pygame.key.get_pressed()))
            renderer.draw(screen)
        elif state == "title":
            renderer.draw_menu(screen, "Пиксельное приключение",
                               "Большой мир • гоблины • квесты • навыки",
                               entries, selected, t,
                               note=note or "Стрелки / W S — выбор     Enter / Пробел — подтвердить     Esc — выход")
        elif state == "pause":
            renderer.draw(screen)
            renderer.draw_menu(screen, "Пауза", "", entries, selected, t,
                               backdrop=False,
                               note=note or "Стрелки / W S — выбор     Enter — подтвердить     Esc — продолжить")
        else:  # settings
            renderer.draw_menu(screen, "Настройки", "Разрешение экрана и режим окна",
                               entries, selected, t, backdrop=False,
                               note=note or "Enter — применить     Esc — назад")
        pygame.display.flip()

    game.save()
    save_config({"res_index": res_index, "fullscreen": fullscreen})
    pygame.quit()
    return 0


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def selftest() -> int:
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

    # ---- art ----
    art_issues = SP._validate()
    print(f"art: {len(SP.SPRITES)} sprites {SP.SPRITE}x{SP.SPRITE}, {len(SP.ICONS)} icons,"
          f" problems: {len(art_issues)}")
    if art_issues:
        problems.extend(art_issues[:5])

    game = Game(seed=1234)
    stats = game.world.stats()
    print("world:", MAP_W, "x", MAP_H, "| land", f"{stats['land_pct']}%",
          "| trees", stats["trees"], "| houses", stats["houses"], "| decor", stats["decor"])
    print("mobs:", len(game.mobs), "| npcs:", len(game.npcs))
    if stats["land_pct"] < 80:
        problems.append(f"land only {stats['land_pct']}%")

    # ---- reachability ----
    reach = game.world.reachable_from((int(SPAWN_X), int(SPAWN_Y)))
    print("reachable tiles from spawn:", len(reach))
    for n in game.npcs:
        tile = (int(n["x"]), int(n["y"]))
        print(f"  npc {n['name']:12s} {tile} reachable: {tile in reach}")
        if tile not in reach:
            problems.append(f"NPC {n['name']} unreachable")

    # ---- inventory ----
    p = game.player
    print("start inventory:", [(s['id'], s['count']) for s in p["inventory"]])
    if not game.add_item("ear", 3):
        problems.append("add_item(ear x3) failed")
    if not game.add_item("ear", 3):
        problems.append("add_item(ear stacking) failed")
    ears = game.count_item("ear")
    slots = len([s for s in p["inventory"] if s["id"] == "ear"])
    print(f"after adding 6 ears: count={ears}, slots used={slots} (stacking works: {slots == 1})")
    if ears != 6:
        problems.append(f"ear count wrong: {ears}")
    if slots != 1:
        problems.append("ear did not stack into one slot")

    # fill the bag and check the overflow guard
    for _ in range(INV_SLOTS + 3):
        game.add_item("sword_rusty", 1)
    print("bag slots after overflow attempt:", len(p["inventory"]), "/", INV_SLOTS)
    if len(p["inventory"]) > INV_SLOTS:
        problems.append("inventory exceeded its slot limit")

    # ---- consume ----
    game2 = Game(seed=99)
    p2 = game2.player
    p2["hp"] = 5
    idx = next(i for i, s in enumerate(p2["inventory"]) if s["id"] == "potion")
    msg = game2.use_slot(idx)
    print("use potion:", msg, "| hp:", p2["hp"])
    if p2["hp"] != 20:
        problems.append(f"potion healed to {p2['hp']}, expected 20")

    # ---- equipment changes damage and defence ----
    base_atk = 5 + game2.attack_bonus()
    game2.add_item("sword_iron", 1)
    idx = next(i for i, s in enumerate(p2["inventory"]) if s["id"] == "sword_iron")
    game2.use_slot(idx)
    armed_atk = 5 + game2.attack_bonus()
    print(f"attack: bare {base_atk} -> armed {armed_atk} (weapon {p2['equip']['weapon']})")
    if armed_atk <= base_atk:
        problems.append("equipping a weapon did not raise attack")
    game2.add_item("armor_iron", 1)
    idx = next(i for i, s in enumerate(p2["inventory"]) if s["id"] == "armor_iron")
    game2.use_slot(idx)
    print("defence with armor:", game2.defense())
    if game2.defense() <= 0:
        problems.append("equipping armor did not raise defence")

    # armour actually reduces incoming damage
    mob = game2.mobs[0]
    game2.player["x"], game2.player["y"] = mob["x"], mob["y"] + 0.5
    hp_before = p2["hp"]
    mob["attack_cd"] = 0
    game2.update_mobs(0.016)
    taken = hp_before - p2["hp"]
    print(f"damage taken with defence {game2.defense()}: {taken}")
    if taken >= mob["atk"] + 2:
        problems.append("armour did not reduce damage")

    # ---- loot ----
    drops_seen: dict[str, int] = {}
    for _ in range(200):
        for item_id in IT.roll_loot("brute", game2.rng):
            drops_seen[item_id] = drops_seen.get(item_id, 0) + 1
    print("loot sample (200 brute rolls):", dict(sorted(drops_seen.items())))
    if len(drops_seen) < 3:
        problems.append("loot table looks empty")

    # killing a mob drops gold + items on the ground, pickup fills the bag
    bag_before = len(p2["inventory"])
    target = game2.mobs[1]
    game2.player["x"], game2.player["y"] = target["x"], target["y"] - 0.6
    target["hp"] = 1
    game2.attack()
    ground = len(game2.drops)
    print("drops on ground after kill:", ground)
    if ground < 1:
        problems.append("no loot dropped on kill")
    for _ in range(120):
        game2.update_effects(1 / 60)
    print("bag slots before/after pickup:", bag_before, "->", len(p2["inventory"]))

    # ---- walk + animation ----
    start = (p2["x"], p2["y"])
    frames = set()
    for _ in range(60):
        game2.update(1 / 60, {"right": True, "left": False, "up": False, "down": False})
        frames.add(p2["frame"])
    walked = math.hypot(p2["x"] - start[0], p2["y"] - start[1])
    print("walked:", round(walked, 2), "tiles | frames:", sorted(frames))
    if walked < 2:
        problems.append("player barely moved")
    if frames != {0, 1}:
        problems.append("walk animation did not cycle")

    # ---- talk to every npc ----
    for n in game2.npcs:
        p2["x"], p2["y"] = n["x"], n["y"] + 1.0
        game2.dialog = None
        game2.interact()
        got = (game2.dialog or {}).get("name")
        if got != n["name"]:
            problems.append(f"could not talk to {n['name']}")
    print("talked to all npcs:", not any("could not talk" in x for x in problems))

    # ---- save / load with inventory ----
    tmp = Path(os.environ.get("TEMP", ".")) / "pixel_rpg_selftest.json"
    ok_save = game2.save(tmp)
    gold, inv_len, weapon = p2["gold"], len(p2["inventory"]), p2["equip"]["weapon"]
    p2["gold"], p2["inventory"], p2["equip"]["weapon"] = -1, [], None
    ok_load = game2.load(tmp)
    print("save/load:", ok_save, ok_load, "| gold", p2["gold"] == gold,
          "| inventory", len(p2["inventory"]) == inv_len, "| weapon", p2["equip"]["weapon"] == weapon)
    if not (ok_save and ok_load and p2["gold"] == gold and len(p2["inventory"]) == inv_len
            and p2["equip"]["weapon"] == weapon):
        problems.append("save/load did not restore gold/inventory/equipment")

    # ---- render every resolution, incl. the inventory overlay ----
    for (w, h, z) in RESOLUTIONS:
        screen = pygame.Surface((w, h))
        r = Renderer(game2, w, h, z)
        r.draw(screen)
        colours = {screen.get_at((x, y))[:3]
                   for x in range(0, w, max(1, w // 40))
                   for y in range(0, h, max(1, h // 24))}
        if len(colours) < 5:
            problems.append(f"render at {w}x{h} looks blank")
    print("render ok at all", len(RESOLUTIONS), "resolutions")

    r = Renderer(game2, 1920, 1080, 4)
    screen = pygame.Surface((1920, 1080))
    game2.show_inventory = True
    r.draw(screen)
    inv_pixels = sum(1 for x in range(600, 1400, 11) for y in range(300, 800, 9)
                     if screen.get_at((x, y))[:3] != (0, 0, 0))
    print("inventory overlay rendered, non-black samples:", inv_pixels)
    if inv_pixels < 500:
        problems.append("inventory overlay did not render")

    # title menu renders with its animated backdrop
    game2.show_inventory = False
    r.draw_menu(screen, "Пиксельное приключение", "Большой мир", [("Новая игра", True)], 0, 1.0)
    menu_pixels = sum(1 for x in range(0, 1920, 13) for y in range(0, 1080, 11)
                      if screen.get_at((x, y))[:3] != (0, 0, 0))
    print("title screen rendered, non-black samples:", menu_pixels)
    if menu_pixels < 500:
        problems.append("title menu did not render")

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
