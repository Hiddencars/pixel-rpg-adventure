#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""World generation for Pixel RPG 2.0 — a 250x128 island with biomes.

The map is 5x the area of 1.3 (32000 tiles).  Terrain comes from height +
moisture noise, which produces: deep sea, shallow water, beaches, meadows,
forest belts, a southern swamp, north-eastern rocky highlands and a snow peak.

Collision lives in a set of solid tiles (fast lookups) instead of scanning the
object list; the object list is only used for drawing and is y-sorted.

Public API
    World(seed)  ->  .tiles, .solid, .objects, .decor, .regions
    w.is_solid(x, y), w.walkable(x, y), w.reachable_from(tile)
    w.nearest_walkable(x, y), w.random_walkable_in(rect, rng), w.stats()
    SPAWN_TILE, VILLAGE_CENTER, MAP_W, MAP_H
"""

from __future__ import annotations

import math
import random
from collections import deque

import art
from art import (T_CROPS, T_DEEP, T_DIRT, T_FLOOR, T_FOREST, T_GRASS, T_MEADOW,
                 T_MUD, T_PATH, T_ROCK, T_SAND, T_SHALLOW, T_SNOW, T_STONE,
                 T_VOID, T_WATER, TILE)

MAP_W, MAP_H = 250, 128
VILLAGE_CENTER = (125, 64)
SPAWN_TILE = (125, 70)


# ------------------------------------------------------------------- noise
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


def fbm(x: float, y: float, octaves: int = 4) -> float:
    v, amp, f = 0.0, 0.5, 1.0
    for _ in range(octaves):
        v += value_noise(x * f, y * f) * amp
        amp *= 0.5
        f *= 2
    return v


# ------------------------------------------------------------------- world
class World:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self.tiles: list[list[int]] = [[T_GRASS] * MAP_W for _ in range(MAP_H)]
        self.solid: set[tuple[int, int]] = set()
        self.objects: list[dict] = []      # drawn, y-sorted: {x, y, kind}
        self.decor: list[dict] = []        # drawn under entities
        self.regions: list[dict] = []      # named areas used for spawning/quests
        self._generate()

    # -- queries -----------------------------------------------------------
    @staticmethod
    def in_bounds(x: int, y: int) -> bool:
        return 0 <= x < MAP_W and 0 <= y < MAP_H

    def tile(self, x: int, y: int) -> int:
        if not self.in_bounds(x, y):
            return T_VOID
        return self.tiles[y][x]

    def is_solid(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return True
        if (x, y) in self.solid:
            return True
        return self.tiles[y][x] in (T_VOID, T_DEEP, T_WATER)

    def walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and not self.is_solid(x, y)

    def blocked_rect(self, x: float, y: float, r: float) -> bool:
        return (self.is_solid(math.floor(x - r), math.floor(y - r))
                or self.is_solid(math.floor(x + r), math.floor(y - r))
                or self.is_solid(math.floor(x - r), math.floor(y + r))
                or self.is_solid(math.floor(x + r), math.floor(y + r)))

    def nearest_walkable(self, x: int, y: int, limit: int = 20):
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

    def reachable_from(self, start: tuple[int, int]) -> set[tuple[int, int]]:
        if not self.walkable(*start):
            found = self.nearest_walkable(*start)
            if not found:
                return set()
            start = found
        seen = {start}
        q = deque([start])
        while q:
            x, y = q.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) not in seen and self.walkable(nx, ny):
                    seen.add((nx, ny))
                    q.append((nx, ny))
        return seen

    def random_walkable_in(self, rect: tuple[int, int, int, int], rng: random.Random,
                           tries: int = 60):
        x0, y0, x1, y1 = rect
        for _ in range(tries):
            x, y = rng.randrange(x0, max(x0 + 1, x1)), rng.randrange(y0, max(y0 + 1, y1))
            if self.walkable(x, y) and not self.is_solid(x, y):
                return x, y
        return None

    def stats(self) -> dict:
        counts: dict[int, int] = {}
        for row in self.tiles:
            for t in row:
                counts[t] = counts.get(t, 0) + 1
        land = sum(v for k, v in counts.items() if k >= T_SAND)
        return {
            "land_pct": round(100 * land / (MAP_W * MAP_H)),
            "trees": sum(1 for o in self.objects if o["kind"].startswith(("oak", "pine", "birch"))),
            "houses": sum(1 for o in self.objects if o["kind"].startswith("house")),
            "objects": len(self.objects), "decor": len(self.decor),
            "solid": len(self.solid),
            "water_pct": round(100 * sum(v for k, v in counts.items()
                                         if k in (T_DEEP, T_WATER, T_SHALLOW))
                               / (MAP_W * MAP_H)),
        }

    # -- helpers -----------------------------------------------------------
    def _place(self, x: int, y: int, kind: str, solid=True, fw=1, fh=1) -> None:
        if not self.in_bounds(x, y):
            return
        self.objects.append({"x": x, "y": y, "kind": kind})
        if solid:
            for dy in range(fh):
                for dx in range(fw):
                    if self.in_bounds(x + dx, y + dy):
                        self.solid.add((x + dx, y + dy))

    def _deco(self, x: int, y: int, kind: str) -> None:
        if self.in_bounds(x, y):
            self.decor.append({"x": x, "y": y, "kind": kind})

    def _free(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and (x, y) not in self.solid

    def _scatter(self, count: int, kinds, tiles_ok, rect=None, solid=True) -> None:
        rng = self.rng
        x0, y0, x1, y1 = rect or (2, 2, MAP_W - 2, MAP_H - 2)
        placed = 0
        for _ in range(count * 6):
            if placed >= count:
                break
            x, y = rng.randrange(x0, x1), rng.randrange(y0, y1)
            if self.tiles[y][x] not in tiles_ok or not self._free(x, y):
                continue
            kind = kinds(rng) if callable(kinds) else rng.choice(kinds)
            self._place(x, y, kind, solid=solid)
            placed += 1

    def _road(self, x0: int, y0: int, x1: int, y1: int) -> None:
        """Draw a slightly wobbly road between two points, clearing objects."""
        steps = max(abs(x1 - x0), abs(y1 - y0))
        for i in range(steps + 1):
            t = i / max(1, steps)
            x = int(round(x0 + (x1 - x0) * t + math.sin(t * 9) * 1.8))
            y = int(round(y0 + (y1 - y0) * t + math.cos(t * 7) * 1.8))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if not self.in_bounds(nx, ny):
                        continue
                    if abs(dx) + abs(dy) == 2 and self.rng.random() < 0.5:
                        continue
                    if self.tiles[ny][nx] in (T_DEEP, T_WATER, T_VOID):
                        continue
                    self.tiles[ny][nx] = T_PATH if abs(dx) + abs(dy) < 2 else T_DIRT
            if self.in_bounds(x, y):
                self.solid.discard((x, y))

    # -- generation --------------------------------------------------------
    def _generate(self) -> None:
        rng = self.rng
        cx, cy = MAP_W / 2, MAP_H / 2
        for y in range(MAP_H):
            for x in range(MAP_W):
                dx = (x - cx) / (MAP_W / 2)
                dy = (y - cy) / (MAP_H / 2)
                dist = math.sqrt(dx * dx * 0.92 + dy * dy * 1.08)
                height = fbm(x * 0.045, y * 0.045) * 0.62 + 0.38 - dist * 0.30
                moist = fbm(x * 0.031 + 90.5, y * 0.031 + 20.25)
                cold = (y / MAP_H)                      # north is cold
                if height > 0.60:
                    t = T_SNOW if cold < 0.16 else (T_ROCK if height > 0.70 else T_STONE)
                elif height > 0.47:
                    t = T_FOREST if moist > 0.45 else T_GRASS
                elif height > 0.42:
                    t = T_MEADOW if moist > 0.48 else T_GRASS
                elif height > 0.34:
                    t = T_SAND
                elif height > 0.27:
                    t = T_SHALLOW
                elif height > 0.19:
                    t = T_WATER
                else:
                    t = T_DEEP
                # southern swamp
                if t in (T_GRASS, T_MEADOW, T_FOREST) and y > MAP_H * 0.72 and moist > 0.46:
                    t = T_MUD
                self.tiles[y][x] = t

        self._carve_lake(58, 38, 11)
        self._carve_lake(196, 96, 7)
        self._build_village()
        self._roads()
        self._forests()
        self._landmarks()
        self._beaches()
        self._scatter_decor()
        self._define_regions()

    def _carve_lake(self, lx: int, ly: int, r: float) -> None:
        for y in range(int(ly - r - 3), int(ly + r + 4)):
            for x in range(int(lx - r - 3), int(lx + r + 4)):
                if not self.in_bounds(x, y):
                    continue
                d = math.hypot(x - lx, y - ly)
                if d < r * (0.72 + hash2(x, y) * 0.5):
                    self.tiles[y][x] = T_WATER
                elif d < r + 2 and self.tiles[y][x] not in (T_DEEP, T_WATER):
                    self.tiles[y][x] = T_SAND
        # a sandy ring and no trees right on the shore
        self.objects = [o for o in self.objects
                        if math.hypot(o["x"] - lx, o["y"] - ly) > r + 1]

    def _build_village(self) -> None:
        vx, vy = VILLAGE_CENTER
        for y in range(vy - 11, vy + 12):
            for x in range(vx - 15, vx + 16):
                if self.in_bounds(x, y) and self.tiles[y][x] >= T_SAND:
                    self.tiles[y][x] = T_GRASS
        # main square + cross roads
        for x in range(vx - 15, vx + 16):
            for dy in (-1, 0, 1):
                if self.in_bounds(x, vy + dy):
                    self.tiles[vy + dy][x] = T_PATH
        for y in range(vy - 11, vy + 12):
            for dx in (-1, 0, 1):
                if self.in_bounds(vx + dx, y):
                    self.tiles[y][vx + dx] = T_PATH
        # houses around the square (4x2 footprints, fronts facing the road)
        house_spots = [(-11, -8, "house_a"), (-5, -8, "house_b"), (2, -8, "house_c"),
                       (8, -8, "house_a"), (-11, 6, "house_b"), (-4, 6, "house_c"),
                       (3, 6, "house_a"), (9, 6, "house_b")]
        for (ox, oy, kind) in house_spots:
            hx, hy = vx + ox, vy + oy
            for dy in range(2):
                for dx in range(3):
                    if self.in_bounds(hx + dx, hy + dy):
                        self.tiles[hy + dy][hx + dx] = T_FLOOR
            self._place(hx, hy, kind, solid=True, fw=3, fh=2)
            self._deco(hx - 1, hy + 2, "barrel" if rng_bool(ox) else "crate")
            self._deco(hx + 3, hy + 2, "lamp")
        self._place(vx, vy - 4, "well", solid=True)
        self._place(vx - 4, vy - 4, "stall", solid=True, fw=2)
        self._place(vx + 4, vy - 4, "stall", solid=True, fw=2)
        self._place(vx + 6, vy + 4, "campfire", solid=False)
        self._place(vx - 7, vy + 4, "signpost", solid=False)
        self._place(vx - 13, vy, "tent", solid=True, fw=2)
        self._place(vx + 13, vy, "tent", solid=True, fw=2)
        self._place(vx - 9, vy - 6, "haystack", solid=True)
        self._place(vx + 10, vy - 6, "haystack", solid=True)
        self._place(vx - 6, vy + 9, "flowerbed", solid=False)
        self._place(vx + 5, vy + 9, "flowerbed", solid=False)
        # crop fields east of the village
        for y in range(vy + 7, vy + 13):
            for x in range(vx + 16, vx + 28):
                if self.in_bounds(x, y) and self.tiles[y][x] in (T_GRASS, T_MEADOW):
                    self.tiles[y][x] = T_CROPS
        # fences around the square, gates on the roads
        for x in range(vx - 15, vx + 16):
            for fy in (vy - 12, vy + 12):
                if abs(x - vx) < 3 or (x - vx) % 9 in (0, 1):
                    continue
                if self.in_bounds(x, fy) and self.tiles[fy][x] == T_GRASS:
                    self._deco(x, fy, "fence")
        for fy in (vy - 12, vy + 12):
            for x in range(vx - 15, vx + 16):
                if abs(x - vx) >= 3 and (x - vx) % 9 not in (0, 1) \
                        and self.in_bounds(x, fy) and self.tiles[fy][x] == T_GRASS:
                    self.solid.add((x, fy))
        for fx in (vx - 17, vx + 17):
            for y in range(vy - 12, vy + 13):
                if abs(y - vy) < 3 or (y - vy) % 9 in (0, 1):
                    continue
                if self.in_bounds(fx, y) and self.tiles[y][fx] == T_GRASS:
                    self._deco(fx, y, "fence_v")
                    self.solid.add((fx, y))

    def _roads(self) -> None:
        vx, vy = VILLAGE_CENTER
        for (tx, ty) in ((36, 64), (60, 30), (212, 40), (196, 100), (60, 100),
                         (206, 96), (125, 16), (150, 110), (30, 40)):
            self._road(vx, vy, tx, ty)

    def _forests(self) -> None:
        rng = self.rng
        def tree_kind(r):
            roll = r.random()
            if roll < 0.45:
                return r.choice(("oak_big", "oak_big_b", "oak_big_c"))
            if roll < 0.7:
                return r.choice(("oak_small", "oak_small_b"))
            if roll < 0.92:
                return r.choice(("pine_big", "pine_big_b", "pine_small", "pine_small_b"))
            return "birch"
        for y in range(2, MAP_H - 2):
            for x in range(2, MAP_W - 2):
                t = self.tiles[y][x]
                if t == T_FOREST:
                    if rng.random() < 0.55 and self._free(x, y):
                        self._place(x, y, tree_kind(rng))
                elif t in (T_GRASS, T_MEADOW):
                    n = fbm(x * 0.09 + 5.5, y * 0.09 + 3.25)
                    if n > 0.56 and rng.random() < 0.28 and self._free(x, y):
                        self._place(x, y, tree_kind(rng))
                elif t == T_MUD:
                    if rng.random() < 0.12 and self._free(x, y):
                        self._place(x, y, rng.choice(("dead_tree", "bush", "berry_bush")))

    def _landmarks(self) -> None:
        rng = self.rng
        # ancient ruins (north-east)
        rx, ry = 212, 40
        for i in range(5):
            self._place(rx - 6 + i * 3, ry - 2 + (i % 2) * 5, "pillar", solid=True)
        for i in range(4):
            self._place(rx - 5 + i * 4, ry + 6, "ruin", solid=True, fw=2)
        self._place(rx, ry + 2, "cave", solid=True, fw=2)
        self._place(rx + 5, ry + 3, "grave", solid=False)
        self._place(rx - 8, ry + 4, "grave", solid=False)
        # graveyard (south-east)
        gx, gy = 196, 100
        for i in range(12):
            self._place(gx - 8 + (i % 6) * 3, gy - 3 + (i // 6) * 5, "grave", solid=False)
            self.solid.add((gx - 8 + (i % 6) * 3, gy - 3 + (i // 6) * 5))
        self._place(gx, gy + 5, "pillar", solid=True)
        # bandit camp (south-west)
        bx, by = 60, 100
        self._place(bx, by, "tent", solid=True, fw=2)
        self._place(bx + 6, by + 3, "tent", solid=True, fw=2)
        self._place(bx + 3, by + 1, "campfire", solid=False)
        self._place(bx - 3, by + 4, "crate", solid=True)
        self._place(bx + 9, by, "stall", solid=True, fw=2)
        for i in range(6):
            self._place(bx - 4 + i * 3, by - 4, "fence", solid=False)
        # lumber camp (west)
        lx, ly = 36, 64
        self._place(lx, ly, "tent", solid=True, fw=2)
        self._place(lx + 4, ly + 2, "log", solid=True)
        self._place(lx + 5, ly - 2, "stump", solid=False)
        self._place(lx - 2, ly + 3, "barrel", solid=True)
        # mountain pass (north)
        self._place(125, 16, "cave", solid=True, fw=2)
        self._place(120, 18, "rock_big", solid=True)
        self._place(130, 18, "rock_big", solid=True)
        # lake hut
        self._place(48, 34, "house_b", solid=True, fw=3, fh=2)
        self._place(52, 36, "well", solid=True)
        # beach camp (west shore)
        self._place(30, 40, "tent", solid=True, fw=2)
        self._place(33, 42, "campfire", solid=False)
        # east shore watchtower
        self._place(206, 96, "pillar", solid=True)
        self._place(210, 98, "ruin", solid=True, fw=2)
        # scatter rocks on stone / rock ground
        self._scatter(180, ("rock_big", "rock_small"), (T_STONE, T_ROCK, T_SNOW))
        self._scatter(90, ("stump", "log"), (T_GRASS, T_MEADOW, T_FOREST), solid=False)
        # a few caves in the highlands
        for _ in range(3):
            spot = self.random_walkable_in((10, 8, MAP_W - 10, 40), rng)
            if spot:
                self._place(spot[0], spot[1], "cave", solid=True, fw=2)

    def _beaches(self) -> None:
        for y in range(MAP_H):
            for x in range(MAP_W):
                if self.tiles[y][x] in (T_GRASS, T_MEADOW, T_FOREST):
                    for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        if self.in_bounds(x + ox, y + oy) and \
                                self.tiles[y + oy][x + ox] in (T_WATER, T_SHALLOW):
                            self.tiles[y][x] = T_SAND
                            break

    def _scatter_decor(self) -> None:
        rng = self.rng
        for y in range(2, MAP_H - 2):
            for x in range(2, MAP_W - 2):
                t = self.tiles[y][x]
                r = rng.random()
                if t in (T_GRASS, T_MEADOW):
                    if r < 0.10:
                        self._deco(x, y, "flower" if rng.random() < 0.7 else "bush")
                    elif r < 0.115:
                        self._deco(x, y, "berry_bush" if rng.random() < 0.5 else "rock_small")
                    elif r < 0.12:
                        self._deco(x, y, "stump")
                elif t == T_FOREST and r < 0.09:
                    self._deco(x, y, "bush" if rng.random() < 0.6 else "rock_small")
                elif t == T_SAND and r < 0.02:
                    self._deco(x, y, "rock_small")
                elif t == T_MUD and r < 0.06:
                    self._deco(x, y, "bush")

    def _define_regions(self) -> None:
        self.regions = [
            {"id": "village", "name": "Дубрава", "rect": (110, 52, 141, 77),
             "mobs": [], "level": 1},
            {"id": "meadow", "name": "Луга", "rect": (60, 40, 190, 92),
             "mobs": ["goblin", "slime", "chicken", "sheep", "cow", "boar"], "level": 1},
            {"id": "forest", "name": "Тёмный бор", "rect": (2, 2, 120, 128),
             "mobs": ["goblin", "brute", "wolf", "spider", "boar", "bear", "snake"], "level": 2},
            {"id": "swamp", "name": "Гнилая топь", "rect": (2, 90, 120, 128),
             "mobs": ["slime", "snake", "spider", "troll", "imp"], "level": 3},
            {"id": "highlands", "name": "Кряж", "rect": (120, 2, 250, 46),
             "mobs": ["orc", "golem", "troll", "skeleton", "bat", "imp"], "level": 4},
            {"id": "ruins", "name": "Руины Аргоса", "rect": (196, 24, 240, 60),
             "mobs": ["skeleton", "wraith", "bandit", "golem"], "level": 5},
            {"id": "graveyard", "name": "Погост", "rect": (180, 88, 220, 116),
             "mobs": ["skeleton", "wraith", "imp"], "level": 4},
            {"id": "camp", "name": "Логово разбойников", "rect": (44, 86, 84, 116),
             "mobs": ["bandit", "brute", "wolf"], "level": 3},
            {"id": "shore", "name": "Берег", "rect": (2, 30, 60, 70),
             "mobs": ["goblin", "slime", "chicken"], "level": 1},
        ]


def rng_bool(seed_val: int) -> bool:
    return (abs(seed_val) // 3) % 2 == 0


if __name__ == "__main__":
    import time
    t0 = time.time()
    w = World(seed=2026)
    build = time.time() - t0
    stats = w.stats()
    print(f"world {MAP_W}x{MAP_H} = {MAP_W * MAP_H} tiles in {build:.2f}s")
    print("stats:", stats)
    reach = w.reachable_from(SPAWN_TILE)
    print("reachable tiles from spawn:", len(reach))
    print("regions:", len(w.regions))
    problems = []
    if stats["land_pct"] < 55:
        problems.append(f"only {stats['land_pct']}% land")
    if len(reach) < 4000:
        problems.append(f"only {len(reach)} reachable tiles — the island is cut up")
    for reg in w.regions:
        x0, y0, x1, y1 = reg["rect"]
        if not any((x, y) in reach for x in range(x0, x1, 3) for y in range(y0, y1, 3)):
            problems.append(f"region {reg['id']} unreachable")
    print("problems:", problems if problems else "none")
    print("WORLD OK" if not problems else "WORLD FAILED")
