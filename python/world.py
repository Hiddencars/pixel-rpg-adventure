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

import numpy as np

import art
from art import (T_CROPS, T_DEEP, T_DIRT, T_FLOOR, T_FOREST, T_GRASS, T_MEADOW,
                 T_MUD, T_PATH, T_ROCK, T_SAND, T_SHALLOW, T_SNOW, T_STONE,
                 T_VOID, T_WATER, TILE)

MAP_W, MAP_H = 3096, 1548          # площадь ×15: 4 792 608 тайлов
# во сколько раз выросла площадь относительно 800×400 — для плотности декора
AREA_SCALE = (MAP_W * MAP_H) / (800 * 400)
SCALE = MAP_W / 250.0            # насколько вырос мир относительно 2.4
VILLAGE_CENTER = (int(round(125 * SCALE)), int(round(64 * SCALE)))
# спавн привязан к деревне, а не к масштабу: сама деревня не растягивается
SPAWN_TILE = (VILLAGE_CENTER[0], VILLAGE_CENTER[1] + 6)


def _sc(v: float | int) -> int:
    """Масштабировать «старую» координату 250×128 под текущий размер."""
    return int(round(v * MAP_W / 250.0))

def _sc2(x, y):
    return _sc(x), _sc(y)


# Области мира как статические данные: quests.py берёт отсюда id, не строя мир.
# Прямоугольники заданы в старой системе 250×128 и масштабируются при построении.
_REGIONS_RAW = (
    ("village",   "Дубрава",            "village",   (110, 52, 141, 77),   [], 1),
    ("meadow",    "Луга",               "meadow",    (60, 40, 190, 92),    ["goblin", "slime", "chicken", "sheep", "cow", "boar"], 1),
    ("forest",    "Тёмный бор",         "forest",    (2, 2, 120, 128),     ["goblin", "brute", "wolf", "spider", "boar", "bear", "snake"], 2),
    ("swamp",     "Гнилая топь",        "swamp",     (2, 90, 120, 128),    ["slime", "snake", "spider", "troll", "imp"], 3),
    ("highlands", "Кряж",               "highlands", (120, 2, 250, 46),    ["orc", "golem", "troll", "skeleton", "bat", "imp"], 4),
    ("ruins",     "Руины Аргоса",       "ruins",     (196, 24, 240, 60),   ["skeleton", "wraith", "bandit", "golem"], 5),
    ("graveyard", "Погост",             "graveyard", (180, 88, 220, 116),  ["skeleton", "wraith", "imp"], 4),
    ("camp",      "Логово разбойников", "camp",      (44, 86, 84, 116),    ["bandit", "brute", "wolf"], 3),
    ("shore",     "Берег",              "shore",     (2, 30, 60, 70),      ["goblin", "slime", "chicken"], 1),
)

REGION_IDS = frozenset(r[0] for r in _REGIONS_RAW)


def _scaled_regions() -> list[dict]:
    """Собирает список регионов с прямоугольниками, отмасштабированными под MAP."""
    vx, vy = VILLAGE_CENTER
    out = []
    for (rid, name, _key, (rx0, ry0, rx1, ry1), mobs, level) in _REGIONS_RAW:
        if rid == "village":
            rect = (vx - 17, vy - 13, vx + 17, vy + 13)
        else:
            rect = (_sc(rx0), _sc(ry0), _sc(rx1), _sc(ry1))
        out.append({"id": rid, "name": name, "rect": rect, "mobs": list(mobs), "level": level})
    return out

REGIONS_DEF = _scaled_regions()


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


# -- векторные версии: те же формулы, но по массивам ----------------------
def hash2_np(x, y):
    n = np.sin(x * 127.1 + y * 311.7) * 43758.5453123
    return n - np.floor(n)


def value_noise_np(x, y):
    xi, yi = np.floor(x), np.floor(y)
    xf, yf = x - xi, y - yi
    a, b = hash2_np(xi, yi), hash2_np(xi + 1, yi)
    c, d = hash2_np(xi, yi + 1), hash2_np(xi + 1, yi + 1)
    u = xf * xf * (3 - 2 * xf)
    v = yf * yf * (3 - 2 * yf)
    return (a * (1 - u) + b * u) * (1 - v) + (c * (1 - u) + d * u) * v


def fbm_np(x, y, octaves: int = 4):
    v = np.zeros(np.broadcast(x, y).shape, dtype=np.float64)
    amp, f = 0.5, 1.0
    for _ in range(octaves):
        v = v + value_noise_np(x * f, y * f) * amp
        amp *= 0.5
        f *= 2
    return v


# ------------------------------------------------------------------- world
class SolidMask:
    """Битовая маска «непроходимых» тайлов вместо `set` кортежей.

    Кортеж в сете стоит ~100 байт; на 4.8 млн тайлов солидных клеток набегает
    под миллион — это сотни мегабайт и мусор в GC. Маска — один байт на тайл
    (4.8 МБ на всю карту) при том же API: add/discard/`in`/len.
    """

    __slots__ = ("w", "h", "bits", "count")

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.bits = bytearray(w * h)
        self.count = 0

    def add(self, key) -> None:
        x, y = key
        if 0 <= x < self.w and 0 <= y < self.h:
            i = y * self.w + x
            if not self.bits[i]:
                self.bits[i] = 1
                self.count += 1

    def discard(self, key) -> None:
        x, y = key
        if 0 <= x < self.w and 0 <= y < self.h:
            i = y * self.w + x
            if self.bits[i]:
                self.bits[i] = 0
                self.count -= 1

    def __contains__(self, key) -> bool:
        x, y = key
        if 0 <= x < self.w and 0 <= y < self.h:
            return bool(self.bits[y * self.w + x])
        return False

    def __len__(self) -> int:
        return self.count


class ReachSet:
    """Достижимые тайлы, хранимые как связность на сетке `cell`×`cell`.

    Совместим с `tile in reach`, но не материализует миллионы кортежей.
    """

    __slots__ = ("cells", "cell")

    def __init__(self, cells: set[tuple[int, int]], cell: int = 8):
        self.cells = cells
        self.cell = cell

    def __contains__(self, tile) -> bool:
        x, y = tile
        return (x // self.cell, y // self.cell) in self.cells

    def __len__(self) -> int:
        return len(self.cells)


class _Field:
    """Билинейно растянутое поле шума, которое считается построчно по запросу.

    Материализовать поле целиком в `list[list[float]]` на карте 3 100×1 550 —
    это 4.8 млн float-объектов и ~450 МБ на три поля. Потребители
    (`_generate`, `_forests`) обходят карту построчно, поэтому решётка хранится
    одна, а строка считается на месте.
    """

    __slots__ = ("freq", "ox", "oy", "step", "grid", "arr")

    def __init__(self, freq: float, ox: float = 0.0, oy: float = 0.0, step: int = 4):
        self.freq, self.ox, self.oy, self.step = freq, ox, oy, step
        gw = MAP_W // step + 2
        gh = MAP_H // step + 2
        gx = np.arange(gw) * step * freq + ox
        gy = np.arange(gh) * step * freq + oy
        X, Y = np.meshgrid(gx, gy)
        self.grid = fbm_np(X, Y)
        # билинейное растяжение решётки на всю карту — одна векторная операция
        ys, xs = np.arange(MAP_H), np.arange(MAP_W)
        gyi, ty = np.divmod(ys, step)
        gxi, tx = np.divmod(xs, step)
        tx = tx.astype(np.float64) / step
        ty = ty.astype(np.float64) / step
        g = self.grid
        g00 = g[np.ix_(gyi, gxi)]
        g01 = g[np.ix_(gyi, gxi + 1)]
        g10 = g[np.ix_(gyi + 1, gxi)]
        g11 = g[np.ix_(gyi + 1, gxi + 1)]
        top = g00 + (g01 - g00) * tx[None, :]
        bot = g10 + (g11 - g10) * tx[None, :]
        self.arr = (top + (bot - top) * ty[:, None]).astype(np.float32)

    def row(self, y: int):
        return self.arr[y]

    def __getitem__(self, y: int):
        return self.arr[y]


class World:
    # сколько стоянок ставить и какие шаблоны существуют (kind, npc_kind)
    SITE_COUNT = 46
    SITE_TEMPLATES = (
        ("ruins", "scout"), ("tower", "scout"),
        ("camp", "hunter"), ("homestead", "hunter"),
        ("mine", "miner"), ("mine", "miner"),
        ("shrine", "pilgrim"), ("shrine", "pilgrim"),
        ("fishing", "fisher"), ("fishing", "fisher"),
        ("graveyard", "hermit"), ("graveyard", "hermit"),
        ("nomad_camp", "nomad"), ("nomad_camp", "nomad"),
    )

    def __init__(self, seed: int | None = None, progress=None):
        self.rng = random.Random(seed)
        self._progress = progress          # callback(доля 0..1, подпись) для экрана загрузки
        # bytearray на строку: 1 байт на тайл вместо 8 байт указателя
        self.tiles: list[bytearray] = [bytearray([T_GRASS]) * MAP_W for _ in range(MAP_H)]
        self.solid: SolidMask = SolidMask(MAP_W, MAP_H)
        self.objects: list[dict] = []      # drawn, y-sorted: {x, y, kind}
        self.decor: list[dict] = []        # drawn under entities
        self.regions: list[dict] = []      # named areas used for spawning/quests
        self._generate()
        self._index()

    # -- queries -----------------------------------------------------------
    @staticmethod
    def in_bounds(x: int, y: int) -> bool:
        return 0 <= x < MAP_W and 0 <= y < MAP_H

    def _index(self) -> None:
        """Пространственные индексы для декора и объектов: на карте 320 000
        тайлов проход по списку из 50–100 тысяч элементов каждый кадр слишком
        дорог, поэтому декорации/объекты раскладываются по корзинам 8×8 тайлов
        и рендер обходит только корзины, попадающие в камеру."""
        self.decor_buckets: dict[tuple[int, int], list[dict]] = {}
        for d in self.decor:
            key = (d["x"] // 8, d["y"] // 8)
            self.decor_buckets.setdefault(key, []).append(d)
        self.object_buckets: dict[tuple[int, int], list[dict]] = {}
        for o in self.objects:
            key = (o["x"] // 8, o["y"] // 8)
            self.object_buckets.setdefault(key, []).append(o)

    def decor_in_view(self, x0: int, y0: int, x1: int, y1: int) -> list[dict]:
        """Декорации в прямоугольнике (в тайлах)."""
        out: list[dict] = []
        for by in range(y0 // 8 - 1, y1 // 8 + 2):
            for bx in range(x0 // 8 - 1, x1 // 8 + 2):
                bucket = self.decor_buckets.get((bx, by))
                if bucket:
                    out.extend(bucket)
        return out

    def objects_in_view(self, x0: int, y0: int, x1: int, y1: int) -> list[dict]:
        out: list[dict] = []
        for by in range(y0 // 8 - 1, y1 // 8 + 2):
            for bx in range(x0 // 8 - 1, x1 // 8 + 2):
                bucket = self.object_buckets.get((bx, by))
                if bucket:
                    out.extend(bucket)
        return out

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

    def reach_cells(self, start: tuple[int, int], cell: int = 8) -> set[tuple[int, int]]:
        """Связность «проходимой» суши на грубой сетке cell×cell тайлов.

        Точный BFS по всей карте на 4.8 млн тайлов стоил 12 секунд и держал в
        памяти set из 2.5 млн кортежей (~350 МБ). Для проверки «этот моб/NPC на
        той же земле, что и игрок» хватает сетки 8×8: погрешность — несколько
        тайлов, цена — доли секунды и мегабайты.
        """
        t = self._tile_array()
        solid = self._solid_array()
        blocked = (solid != 0) | (t == T_VOID) | (t == T_DEEP) | (t == T_WATER)
        cw = (MAP_W + cell - 1) // cell
        ch = (MAP_H + cell - 1) // cell
        pad = np.zeros((ch * cell, cw * cell), dtype=bool)
        pad[:MAP_H, :MAP_W] = ~blocked
        walk = pad.reshape(ch, cell, cw, cell).any(axis=(1, 3))

        sx, sy = start[0] // cell, start[1] // cell
        sx, sy = min(max(sx, 0), cw - 1), min(max(sy, 0), ch - 1)
        if not walk[sy, sx]:
            spot = np.argwhere(walk[max(0, sy - 6):sy + 7, max(0, sx - 6):sx + 7])
            if len(spot):
                dy, dx = spot[0]
                sy = max(0, sy - 6) + int(dy)
                sx = max(0, sx - 6) + int(dx)
            else:
                return set()

        seen = {(sx, sy)}
        q = deque([(sx, sy)])
        while q:
            x, y = q.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < cw and 0 <= ny < ch and (nx, ny) not in seen and walk[ny, nx]:
                    seen.add((nx, ny))
                    q.append((nx, ny))
        return seen

    def reachable_from(self, start: tuple[int, int]):
        cache = getattr(self, "_reach_cache", None)
        if cache is not None and cache[0] == start:
            return cache[1]
        result = ReachSet(self.reach_cells(start), 8)
        self._reach_cache = (start, result)
        return result

    def _reachable_bfs(self, start: tuple[int, int]) -> set[tuple[int, int]]:
        """Точный BFS по тайлам. Оставлен для отладки: на 4.8 млн тайлов это
        ~12 с и сотни мегабайт, игровые проверки идут через `reachable_from`."""
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
    def _field(self, freq: float, ox: float = 0.0, oy: float = 0.0,
               step: int = 4) -> _Field:
        """Гладкое поле шума: fbm считается на редкой сетке (шаг `step` тайлов)
        и билинейно растягивается на всю карту.

        fbm — гладкая функция: при частотах 0.03–0.09 потеря детализации на шаге 4
        глазу не видна, а время генерации падает примерно в 16 раз. На карте в
        320 000 тайлов это разница между «мир строится 16 секунд» и «за секунду».

        Поле возвращается ленивым: строка считается по запросу, а не вся карта.
        """
        return _Field(freq, ox, oy, step)

    def _tick(self, frac: float, label: str) -> None:
        """Сообщить экрану загрузки, сколько сделано (если он есть)."""
        if self._progress is not None:
            self._progress(frac, label)

    def _generate(self) -> None:
        rng = self.rng
        cx, cy = MAP_W / 2, MAP_H / 2
        # три гладких поля: рельеф, влажность, «лесность». Считаются на редкой сетке.
        self._tick(0.04, "Рельеф")
        height_f = self._field(0.045)
        moist_f = self._field(0.031, 90.5, 20.25)
        forest_f = self._field(0.09, 5.5, 3.25)
        half_w, half_h = MAP_W / 2, MAP_H / 2
        # классификация рельефа целиком на numpy: на 4.8 млн тайлов питоновский
        # цикл с sqrt на каждую клетку стоил ~8 секунд
        ys = np.arange(MAP_H, dtype=np.float64)
        xs = np.arange(MAP_W, dtype=np.float64)
        dx = ((xs - cx) / half_w) ** 2 * 0.92
        dy = ((ys - cy) / half_h) ** 2 * 1.08
        height = height_f.arr * 0.62 + 0.38 - np.sqrt(dx[None, :] + dy[:, None]) * 0.30
        moist = moist_f.arr
        cold = (ys / MAP_H)[:, None]
        swamp_y = (ys > MAP_H * 0.72)[:, None]

        t = np.full((MAP_H, MAP_W), T_DEEP, dtype=np.uint8)
        t = np.where(height > 0.19, T_WATER, t)
        t = np.where(height > 0.27, T_SHALLOW, t)
        t = np.where(height > 0.34, T_SAND, t)
        t = np.where(height > 0.42, np.where(moist > 0.48, T_MEADOW, T_GRASS), t)
        t = np.where(height > 0.47, np.where(moist > 0.45, T_FOREST, T_GRASS), t)
        t = np.where(height > 0.60,
                     np.where(cold < 0.16, T_SNOW,
                              np.where(height > 0.70, T_ROCK, T_STONE)), t)
        # southern swamp
        swamp = (((t == T_GRASS) | (t == T_MEADOW) | (t == T_FOREST))
                 & swamp_y & (moist > 0.46))
        t[swamp] = T_MUD
        t = t.astype(np.uint8)
        for y in range(MAP_H):
            self.tiles[y] = bytearray(t[y].tobytes())
        self.forest_f = forest_f.arr

        self._carve_lake(_sc(58), _sc(38), _sc(11))
        self._carve_lake(_sc(196), _sc(96), _sc(7))
        self._tick(0.40, "Деревня")
        self._build_village()
        self._tick(0.50, "Дороги")
        self._roads()
        self._tick(0.58, "Леса")
        self._forests()
        self._clear_village_trees()
        self._tick(0.74, "Достопримечательности")
        self._landmarks()
        self._tick(0.84, "Побережье")
        self._beaches()
        self._tick(0.90, "Трава и цветы")
        self._scatter_decor()
        self._define_regions()
        self._tick(0.94, "Стоянки")
        self._sites()
        self._tick(0.98, "Области")

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

    def _clear_village_trees(self) -> None:
        """Убрать деревья и камни из деревенского квадрата.

        `_forests` сажает деревья и на деревенской траве (T_GRASS), поэтому без
        этого прохода лес вырастает прямо между домами: NPC оказываются в кольце
        из стволов, а игрок упирается в дерево посреди площади."""
        vx, vy = VILLAGE_CENTER
        pad_x, pad_y = 19, 14          # деревня не масштабируется: те же ±15/±11 плюс запас
        x0, x1 = vx - pad_x, vx + pad_x
        y0, y1 = vy - pad_y, vy + pad_y
        trees = ("oak_big", "oak_big_b", "oak_big_c", "oak_small", "oak_small_b",
                 "pine_big", "pine_big_b", "pine_small", "pine_small_b",
                 "birch", "dead_tree", "rock_big", "rock_small")
        keep = []
        for o in self.objects:
            if (x0 <= o["x"] <= x1 and y0 <= o["y"] <= y1
                    and o["kind"] in trees):
                self.solid.discard((o["x"], o["y"]))
                continue
            keep.append(o)
        self.objects = keep

    def _roads(self) -> None:
        vx, vy = VILLAGE_CENTER
        # цели дорог заданы в старой системе 250×128 и масштабируются под мир
        for (tx, ty) in (_sc2(36, 64), _sc2(60, 30), _sc2(212, 40), _sc2(196, 100),
                         _sc2(60, 100), _sc2(206, 96), _sc2(125, 16), _sc2(150, 110),
                         _sc2(30, 40)):
            self._road(vx, vy, tx, ty)

    def _tile_array(self):
        """Numpy-копия карты тайлов (uint8) для векторных масок."""
        arr = np.frombuffer(b"".join(self.tiles), dtype=np.uint8).reshape(MAP_H, MAP_W)
        return arr.copy()

    def _solid_array(self):
        """Numpy-вид на маску непроходимости: запись идёт в оригинал."""
        return np.frombuffer(self.solid.bits, dtype=np.uint8).reshape(MAP_H, MAP_W)

    def _forests(self) -> None:
        """Деревья по биомам — векторные маски, а не 4.8 млн питоновских итераций.

        Дерево занимает ровно один тайл, поэтому предварительный расчёт масок не
        создаёт наложений: каждая клетка выбирается не более одного раза.
        """
        arr = self._tile_array()
        free = self._solid_array() == 0
        border = np.ones((MAP_H, MAP_W), dtype=bool)
        border[:2, :] = border[-2:, :] = False
        border[:, :2] = border[:, -2:] = False
        ffield = getattr(self, "forest_f", None)
        nrng = np.random.default_rng(self.rng.randrange(1 << 31))

        oaks = np.array(["oak_big", "oak_big_b", "oak_big_c"])
        smalls = np.array(["oak_small", "oak_small_b"])
        pines = np.array(["pine_big", "pine_big_b", "pine_small", "pine_small_b"])

        def tree_kinds(n: int):
            roll = nrng.random(n, dtype=np.float32)
            return np.select(
                [roll < 0.45, roll < 0.70, roll < 0.92],
                [nrng.choice(oaks, n), nrng.choice(smalls, n), nrng.choice(pines, n)],
                default="birch",
            )

        masks = [(arr == T_FOREST) & free & border
                 & (nrng.random((MAP_H, MAP_W), dtype=np.float32) < 0.55)]
        if ffield is not None:
            grassy = ((arr == T_GRASS) | (arr == T_MEADOW)) & free & border & (ffield > 0.56)
        else:
            grassy = np.zeros((MAP_H, MAP_W), dtype=bool)
        masks.append(grassy & (nrng.random((MAP_H, MAP_W), dtype=np.float32) < 0.28))
        masks.append((arr == T_MUD) & free & border
                     & (nrng.random((MAP_H, MAP_W), dtype=np.float32) < 0.12))

        append = self.objects.append
        add_solid = self.solid.add
        for i, mask in enumerate(masks):
            ys, xs = np.nonzero(mask)
            n = len(xs)
            if not n:
                continue
            if i == 2:
                ks = nrng.choice(("dead_tree", "bush", "berry_bush"), n)
            else:
                ks = tree_kinds(n)
            for x, y, k in zip(xs.tolist(), ys.tolist(), ks.tolist()):
                append({"x": x, "y": y, "kind": k})
                add_solid((x, y))

    def _landmarks(self) -> None:
        rng = self.rng
        # ancient ruins (north-east)
        rx, ry = _sc(212), _sc(40)
        for i in range(5):
            self._place(rx - 6 + i * 3, ry - 2 + (i % 2) * 5, "pillar", solid=True)
        for i in range(4):
            self._place(rx - 5 + i * 4, ry + 6, "ruin", solid=True, fw=2)
        self._place(rx, ry + 2, "cave", solid=True, fw=2)
        self._place(rx + 5, ry + 3, "grave", solid=False)
        self._place(rx - 8, ry + 4, "grave", solid=False)
        # graveyard (south-east)
        gx, gy = _sc(196), _sc(100)
        for i in range(12):
            self._place(gx - 8 + (i % 6) * 3, gy - 3 + (i // 6) * 5, "grave", solid=False)
            self.solid.add((gx - 8 + (i % 6) * 3, gy - 3 + (i // 6) * 5))
        self._place(gx, gy + 5, "pillar", solid=True)
        # bandit camp (south-west)
        bx, by = _sc(60), _sc(100)
        self._place(bx, by, "tent", solid=True, fw=2)
        self._place(bx + 6, by + 3, "tent", solid=True, fw=2)
        self._place(bx + 3, by + 1, "campfire", solid=False)
        self._place(bx - 3, by + 4, "crate", solid=True)
        self._place(bx + 9, by, "stall", solid=True, fw=2)
        for i in range(6):
            self._place(bx - 4 + i * 3, by - 4, "fence", solid=False)
        # lumber camp (west)
        lx, ly = _sc(36), _sc(64)
        self._place(lx, ly, "tent", solid=True, fw=2)
        self._place(lx + 4, ly + 2, "log", solid=True)
        self._place(lx + 5, ly - 2, "stump", solid=False)
        self._place(lx - 2, ly + 3, "barrel", solid=True)
        # mountain pass (north)
        mx, my = _sc(125), _sc(16)
        self._place(mx, my, "cave", solid=True, fw=2)
        self._place(mx - 5, my + 2, "rock_big", solid=True)
        self._place(mx + 5, my + 2, "rock_big", solid=True)
        # lake hut
        hx, hy = _sc(48), _sc(34)
        self._place(hx, hy, "house_b", solid=True, fw=3, fh=2)
        self._place(hx + 4, hy + 2, "well", solid=True)
        # beach camp (west shore)
        tx_, ty_ = _sc(30), _sc(40)
        self._place(tx_, ty_, "tent", solid=True, fw=2)
        self._place(tx_ + 3, ty_ + 2, "campfire", solid=False)
        # east shore watchtower
        wx, wy = _sc(206), _sc(96)
        self._place(wx, wy, "pillar", solid=True)
        self._place(wx + 4, wy + 2, "ruin", solid=True, fw=2)
        # scatter rocks on stone / rock ground
        # площадь выросла в 10 раз — и разброс камней/пней тоже
        self._scatter(int(1800 * AREA_SCALE), ("rock_big", "rock_small"), (T_STONE, T_ROCK, T_SNOW))
        self._scatter(int(900 * AREA_SCALE), ("stump", "log"), (T_GRASS, T_MEADOW, T_FOREST), solid=False)
        # a few caves in the highlands
        for _ in range(int(30 * AREA_SCALE)):
            spot = self.random_walkable_in((10, 8, MAP_W - 10, _sc(40)), rng)
            if spot:
                self._place(spot[0], spot[1], "cave", solid=True, fw=2)

    def _beaches(self) -> None:
        """Песок на стыке суши и воды — сдвиговые маски вместо 4.8 млн итераций."""
        arr = self._tile_array()
        water = (arr == T_WATER) | (arr == T_SHALLOW)
        near = np.zeros_like(water)
        near[1:, :] |= water[:-1, :]
        near[:-1, :] |= water[1:, :]
        near[:, 1:] |= water[:, :-1]
        near[:, :-1] |= water[:, 1:]
        land = ((arr == T_GRASS) | (arr == T_MEADOW) | (arr == T_FOREST)) & near
        arr[land] = T_SAND
        for y in range(MAP_H):
            self.tiles[y] = bytearray(arr[y].tobytes())

    def _scatter_decor(self) -> None:
        """Плотный «живой пол»: векторные маски вместо 4.8 млн итераций.

        Трава теперь стоит на каждой второй клетке, а не на каждой третьей:
        плоское поле из одинаковых квадратов читалось как пустое. Решения
        принимаются массивами, в питон уходят только сами декорации.
        """
        arr = self._tile_array()
        nrng = np.random.default_rng(self.rng.randrange(1 << 31))
        r = nrng.random((MAP_H, MAP_W), dtype=np.float32)
        r2 = nrng.random((MAP_H, MAP_W), dtype=np.float32)
        append = self.decor.append

        def add(mask, kinds):
            ys, xs = np.nonzero(mask)
            n = len(xs)
            if not n:
                return
            ks = (nrng.choice(kinds, n) if isinstance(kinds, (list, tuple))
                  else np.full(n, kinds))
            for x, y, k in zip(xs.tolist(), ys.tolist(), ks.tolist()):
                append({"x": x, "y": y, "kind": k})

        border = np.ones((MAP_H, MAP_W), dtype=bool)
        border[:2, :] = border[-2:, :] = False
        border[:, :2] = border[:, -2:] = False

        grass = ((arr == T_GRASS) | (arr == T_MEADOW)) & border
        add(grass & ((r < 0.30) | ((r >= 0.50) & (r < 0.62))), "grass_tuft")
        fl = grass & (r >= 0.30) & (r < 0.36)
        add(fl & (r2 < 0.6), "flower")
        add(fl & (r2 >= 0.6), "flower2")
        add(grass & (r >= 0.36) & (r < 0.40), "pebble")
        bush = grass & (r >= 0.40) & (r < 0.46)
        add(bush & (r2 < 0.55), "bush")
        add(bush & (r2 >= 0.55), "berry_bush")
        add(grass & (r >= 0.46) & (r < 0.50), "rock_small")

        forest = (arr == T_FOREST) & border
        add(forest & (r < 0.036), "mushroom")
        add(forest & (r < 0.12) & (r >= 0.036), "grass_tuft")
        add(forest & (r >= 0.12) & (r < 0.16) & (r2 < 0.5), "bush")
        add(forest & (r >= 0.12) & (r < 0.16) & (r2 >= 0.5), "rock_small")

        sand = (arr == T_SAND) & border
        add(sand & (r < 0.04), "shell")
        add(sand & (r >= 0.04) & (r < 0.08), "pebble")

        mud = (arr == T_MUD) & border
        add(mud & (r < 0.05), "reed")
        add(mud & (r >= 0.05) & (r < 0.10), "mushroom")

        stone = ((arr == T_ROCK) | (arr == T_STONE)) & border
        add(stone & (r < 0.05), "pebble")

    def _sites(self) -> None:
        """Постройки и стоянки по всей карте: руины, башни, шахты, святилища.

        До этого карта была почти пустой: девять областей и восемь
        достопримечательностей на 4.8 млн клеток. Сайты ставятся детерминированно
        от сида, с минимальным расстоянием друг от друга, и каждый помнит, кто
        там живёт — по этому списку `Game.spawn_npcs` рассаживает NPC.
        """
        rng = self.rng
        buckets: dict[tuple[int, int], list[dict]] = {}
        for o in self.objects:
            buckets.setdefault((o["x"] // 8, o["y"] // 8), []).append(o)
        for d in self.decor:
            buckets.setdefault((d["x"] // 8, d["y"] // 8), []).append(d)

        drop: set[int] = set()
        sites: list[dict] = []
        min_dist = 110
        # очередь шаблонов по кругу и перемешивание: чисто случайный выбор
        # давал перекос (2 хутора против 12 лагерей), а карте нужны все типы
        total = self.SITE_COUNT
        base = list(self.SITE_TEMPLATES)
        rng.shuffle(base)
        queue = [base[i % len(base)] for i in range(total)]
        rng.shuffle(queue)
        attempts = 0
        while len(sites) < total and attempts < total * 60:
            attempts += 1
            region = rng.choice(self.regions)
            x0, y0, x1, y1 = region["rect"]
            x0, y0 = max(4, x0), max(4, y0)
            x1, y1 = min(MAP_W - 6, x1), min(MAP_H - 6, y1)
            if x1 - x0 < 20 or y1 - y0 < 20:
                continue
            sx, sy = rng.randrange(x0, x1), rng.randrange(y0, y1)
            if not self.walkable(sx, sy) or self.is_solid(sx, sy):
                continue
            t = self.tiles[sy][sx]
            if t not in (T_GRASS, T_MEADOW, T_FOREST, T_MUD, T_STONE, T_SAND):
                continue
            if any(abs(sx - s["x"]) + abs(sy - s["y"]) < min_dist for s in sites):
                continue
            kind, npc_kind = queue[len(sites)]
            name = self._site_name(kind, region["name"], rng)
            self._clear_area(sx, sy, 6, buckets, drop)
            getattr(self, "_site_" + kind)(sx, sy, rng)
            sites.append({"id": f"site_{len(sites)}", "kind": kind, "name": name,
                          "x": sx, "y": sy, "region": region["id"],
                          "npc": npc_kind})
        if drop:
            self.objects = [o for o in self.objects if id(o) not in drop]
            self.decor = [d for d in self.decor if id(d) not in drop]
        self.sites = sites

    def _site_name(self, kind: str, region: str, rng: random.Random) -> str:
        """Имя стоянки: «Руины у Лугов», «Шахта в Кряже» — по шаблону и области."""
        heads = {
            "ruins": ("Руины", "Развалины", "Древние камни"),
            "tower": ("Башня", "Сторожевой пост", "Дозор"),
            "camp": ("Лагерь", "Стоянка", "Привал"),
            "homestead": ("Хутор", "Заимка", "Двор"),
            "mine": ("Шахта", "Заброшенный рудник", "Копи"),
            "shrine": ("Святилище", "Алтарь", "Капище"),
            "fishing": ("Рыбацкий стан", "Пристань", "Тоня"),
            "graveyard": ("Погост", "Могильник", "Курган"),
            "nomad_camp": ("Кочевье", "Стойбище", "Табор"),
        }
        tails = ("у Лугов", "в Тёмном бору", "на Кряже", "у Топи", "в Руинах",
                 "на Погосте", "у Берега", "в Глуши", "на Пустоши")
        head = rng.choice(heads.get(kind, ("Стоянка",)))
        return f"{head} {rng.choice(tails)}"

    def _clear_area(self, cx: int, cy: int, r: int,
                    buckets: dict, drop: set) -> None:
        """Расчистить площадку: убрать деревья и камни, выровнять землю."""
        for by in range((cy - r) // 8 - 1, (cy + r) // 8 + 2):
            for bx in range((cx - r) // 8 - 1, (cx + r) // 8 + 2):
                for o in buckets.get((bx, by), ()):
                    if abs(o["x"] - cx) <= r and abs(o["y"] - cy) <= r:
                        drop.add(id(o))
                        self.solid.discard((o["x"], o["y"]))
        for y in range(cy - r, cy + r + 1):
            if not (0 <= y < MAP_H):
                continue
            row = self.tiles[y]
            for x in range(cx - r, cx + r + 1):
                if not (0 <= x < MAP_W):
                    continue
                if row[x] in (T_VOID, T_DEEP, T_WATER, T_SHALLOW):
                    continue
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    row[x] = T_GRASS if row[x] in (T_FOREST, T_MUD) else row[x]

    # -- шаблоны стоянок ---------------------------------------------------
    def _site_ruins(self, x: int, y: int, rng: random.Random) -> None:
        for dx, dy in ((-3, -2), (3, -2), (-3, 2), (3, 2)):
            self._place(x + dx, y + dy, "pillar", solid=True)
        self._place(x, y - 1, "ruin", solid=True, fw=2)
        for dx, dy in ((-1, 2), (2, 3), (-4, 1)):
            self._place(x + dx, y + dy, "grave", solid=False)
        for _ in range(5):
            self._place(x + rng.randrange(-4, 5), y + rng.randrange(-3, 4),
                        "rock_small", solid=False)

    def _site_tower(self, x: int, y: int, rng: random.Random) -> None:
        self._place(x, y, "tower", solid=True, fw=2)
        self._place(x - 3, y + 2, "campfire", solid=False)
        self._place(x + 3, y + 2, "crate", solid=True)
        for dx in range(-4, 5):
            if abs(dx) > 1:
                self._place(x + dx, y + 3, "fence", solid=False)

    def _site_camp(self, x: int, y: int, rng: random.Random) -> None:
        self._place(x, y, "tent", solid=True, fw=2)
        self._place(x - 3, y + 1, "campfire", solid=False)
        self._place(x + 3, y + 2, "barrel", solid=True)
        self._place(x - 4, y + 3, "log", solid=False)
        self._place(x + 2, y - 3, "stump", solid=False)

    def _site_homestead(self, x: int, y: int, rng: random.Random) -> None:
        self._place(x, y, rng.choice(("house_a", "house_b", "house_c")),
                    solid=True, fw=3, fh=2)
        self._place(x + 5, y + 1, "haystack", solid=True)
        self._place(x + 4, y + 3, "well", solid=True)
        for dy in range(-1, 4):
            for dx in range(-6, -2):
                if self.in_bounds(x + dx, y + dy) and self.tiles[y + dy][x + dx] == T_GRASS:
                    self.tiles[y + dy][x + dx] = T_CROPS
        for dx in range(-7, 8, 2):
            self._place(x + dx, y + 4, "fence", solid=False)

    def _site_mine(self, x: int, y: int, rng: random.Random) -> None:
        self._place(x, y, "cave", solid=True, fw=2)
        # дорога перед забоем: без неё пещера, вагонетка и фонарь читались
        # как три отдельных спрайта на траве
        for dx in range(-5, 6):
            for dy in (2, 3):
                if self.in_bounds(x + dx, y + dy):
                    self.tiles[y + dy][x + dx] = T_PATH if dy == 3 else T_DIRT
        for dx in (0, 1):
            if self.in_bounds(x + dx, y + 1):
                self.tiles[y + 1][x + dx] = T_DIRT
        self._place(x - 4, y + 3, "cart", solid=True)
        self._place(x + 4, y + 3, "crate", solid=True)
        self._place(x + 3, y + 2, "lamp", solid=False)
        self._place(x - 6, y + 2, "barrel", solid=True)
        self._place(x - 3, y - 1, "rock_big", solid=True)
        self._place(x + 3, y - 1, "rock_big", solid=True)
        for _ in range(3):
            self._place(x + rng.randrange(-5, 6), y + rng.randrange(4, 6),
                        "rock_small", solid=False)

    def _site_shrine(self, x: int, y: int, rng: random.Random) -> None:
        self._place(x, y, "shrine", solid=True)
        for dx, dy in ((-2, -1), (2, -1), (-2, 2), (2, 2)):
            self._place(x + dx, y + dy, "pillar", solid=True)
        self._place(x, y + 3, "campfire", solid=False)
        for dx in range(-3, 4):
            if self.in_bounds(x + dx, y + 4) and self.tiles[y + 4][x + dx] == T_GRASS:
                self.tiles[y + 4][x + dx] = T_PATH

    def _site_fishing(self, x: int, y: int, rng: random.Random) -> None:
        self._place(x, y, "tent", solid=True, fw=2)
        self._place(x - 3, y + 2, "barrel", solid=True)
        self._place(x + 2, y + 2, "campfire", solid=False)
        self._place(x + 4, y + 1, "crate", solid=True)
        self._place(x - 4, y - 2, "log", solid=False)

    def _site_graveyard(self, x: int, y: int, rng: random.Random) -> None:
        for i in range(6):
            self._place(x - 4 + (i % 3) * 3, y - 2 + (i // 3) * 3, "grave", solid=False)
        self._place(x, y + 2, "pillar", solid=True)
        self._place(x + 4, y - 3, "dead_tree", solid=True)
        self._place(x - 5, y + 1, "shrine", solid=True)

    def _site_nomad_camp(self, x: int, y: int, rng: random.Random) -> None:
        self._place(x, y, "tent", solid=True, fw=2)
        self._place(x + 4, y + 1, "tent", solid=True, fw=2)
        self._place(x + 2, y + 3, "campfire", solid=False)
        self._place(x - 3, y + 2, "stall", solid=True, fw=2)
        self._place(x + 6, y + 3, "barrel", solid=True)

    def _define_regions(self) -> None:
        """Копия модульной REGIONS_DEF — чтобы экземпляр мог менять rect и т.п."""
        self.regions = [dict(r) for r in REGIONS_DEF]

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
