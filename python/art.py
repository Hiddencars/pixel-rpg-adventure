#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pre-rendered world art for Pixel patch.

Everything here is procedural — no external asset files — but instead of drawing
shapes straight into the frame every tick, each tile variant and each object is
rendered ONCE into a Surface and then blitted.  That buys enough budget per pixel
to shade terrain with several tones, dither gradients, add ambient occlusion and
give objects real volume.

Public API
    TILE                     tile size in pixels (32)
    T_*                      tile type constants
    build_tiles()            {tile_type: [Surface, ...]}   (VARIANTS per type)
    build_objects()          {name: {"surface": Surface, "anchor": (ax, ay),
                                     "footprint": (w, h), "tall": int}}
    validate()               -> list[str] of problems (used by the self-test)
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import pygame

TILE = 32
VARIANTS = 14

# ---------------------------------------------------------------- tile types
T_VOID, T_DEEP, T_WATER, T_SHALLOW, T_SAND = 0, 1, 2, 3, 4
T_GRASS, T_MEADOW, T_FOREST, T_PATH, T_DIRT = 5, 6, 7, 8, 9
T_STONE, T_SNOW, T_MUD, T_CROPS, T_FLOOR, T_ROCK = 10, 11, 12, 13, 14, 15
TILE_NAMES = {
    T_VOID: "void", T_DEEP: "deep", T_WATER: "water", T_SHALLOW: "shallow",
    T_SAND: "sand", T_GRASS: "grass", T_MEADOW: "meadow", T_FOREST: "forest",
    T_PATH: "path", T_DIRT: "dirt", T_STONE: "stone", T_SNOW: "snow",
    T_MUD: "mud", T_CROPS: "crops", T_FLOOR: "floor", T_ROCK: "rock",
}

# ------------------------------------------------------------------- palette
VOID = (9, 16, 26)
DEEP = (22, 58, 112)
WATER = (44, 100, 164)
WATER_L = (96, 158, 214)
FOAM = (196, 224, 244)
SAND = (222, 204, 154)
SAND_D = (188, 168, 120)
SAND_L = (244, 232, 194)
GRASS = (74, 132, 62)
GRASS_D = (52, 100, 48)
GRASS_L = (112, 168, 84)
MEADOW = (98, 152, 72)
MEADOW_D = (74, 122, 58)
MEADOW_L = (134, 182, 92)
FOREST_F = (46, 84, 52)
FOREST_FD = (32, 62, 40)
PATH = (156, 130, 96)
PATH_D = (124, 100, 70)
PATH_L = (186, 160, 122)
DIRT = (122, 94, 64)
DIRT_D = (92, 68, 46)
DIRT_L = (154, 122, 86)
STONE = (128, 128, 134)
STONE_D = (94, 94, 102)
STONE_L = (166, 166, 172)
SNOW = (230, 236, 248)
SNOW_D = (192, 204, 224)
SNOW_L = (250, 252, 255)
MUD = (88, 74, 56)
MUD_D = (62, 52, 40)
MUD_L = (116, 100, 76)
WOOD = (126, 88, 54)
WOOD_D = (92, 62, 38)
WOOD_L = (162, 120, 76)
BARK = (96, 66, 44)
BARK_D = (68, 46, 30)
BARK_L = (128, 94, 62)
LEAF_D = (34, 84, 46)
LEAF = (58, 122, 60)
LEAF_L = (96, 160, 78)
LEAF_XL = (140, 194, 106)
PINE_D = (28, 74, 52)
PINE = (40, 96, 62)
PINE_L = (62, 126, 78)
ROOF_RED = (162, 66, 56)
ROOF_RED_D = (118, 44, 40)
ROOF_BROWN = (140, 104, 62)
ROOF_BROWN_D = (104, 74, 44)
ROOF_SLATE = (104, 112, 132)
ROOF_SLATE_D = (74, 80, 98)
PLASTER = (222, 208, 178)
PLASTER_D = (192, 176, 146)
STONE_WALL = (140, 138, 134)
GLASS = (150, 200, 210)
IRON = (108, 108, 116)
IRON_L = (150, 150, 158)
GOLD = (232, 196, 96)
METAL = (176, 180, 190)
METAL_D = (118, 122, 134)


# ------------------------------------------------------------------- helpers
def mix(a, b, t: float):
    return (int(round(a[0] + (b[0] - a[0]) * t)),
            int(round(a[1] + (b[1] - a[1]) * t)),
            int(round(a[2] + (b[2] - a[2]) * t)))


def shade(c, f: float):
    return (max(0, min(255, int(c[0] * f))),
            max(0, min(255, int(c[1] * f))),
            max(0, min(255, int(c[2] * f))))


def _px(surf: pygame.Surface, x: int, y: int, col) -> None:
    if 0 <= x < surf.get_width() and 0 <= y < surf.get_height():
        surf.set_at((x, y), col)


def _rect(surf, col, x, y, w, h) -> None:
    pygame.draw.rect(surf, col, (x, y, w, h))


def _disc(surf, col, cx, cy, r) -> None:
    pygame.draw.circle(surf, col, (int(cx), int(cy)), int(r))


def _soft_patch(surf, col, cx, cy, r, strength=0.35, dither=True) -> None:
    """Blend a soft round patch into the surface (dithering keeps it pixel-true)."""
    w, h = surf.get_width(), surf.get_height()
    r2 = r * r
    for dy in range(-r, r + 1):
        y = cy + dy
        if not 0 <= y < h:
            continue
        for dx in range(-r, r + 1):
            x = cx + dx
            if not 0 <= x < w:
                continue
            d2 = dx * dx + dy * dy
            if d2 > r2:
                continue
            edge = d2 / r2
            if dither and edge > 0.55 and (dx + dy) % 2:
                continue
            k = strength * (1 - edge * 0.7)
            surf.set_at((x, y), mix(surf.get_at((x, y))[:3], col, k))


def _speckle(surf, rng, cols, count, size=1) -> None:
    w, h = surf.get_width(), surf.get_height()
    for _ in range(count):
        x, y = rng.randrange(w), rng.randrange(h)
        col = rng.choice(cols)
        for dy in range(size):
            for dx in range(size):
                _px(surf, x + dx, y + dy, col)


def _blade(surf, rng, x, y, col, height=3) -> None:
    for i in range(height):
        _px(surf, x, y - i, col)
    if rng.random() < 0.5:
        _px(surf, x + (1 if rng.random() < 0.5 else -1), y - height + 1, col)


def _flower(surf, x, y, petal, core=(248, 240, 180)) -> None:
    _px(surf, x, y - 1, petal)
    _px(surf, x - 1, y, petal)
    _px(surf, x + 1, y, petal)
    _px(surf, x, y + 1, petal)
    _px(surf, x, y, core)


def _pebble(surf, x, y, col, dark) -> None:
    _rect(surf, dark, x, y + 1, 3, 2)
    _rect(surf, col, x, y, 3, 2)
    _px(surf, x, y, mix(col, (255, 255, 255), 0.35))


# --------------------------------------------------------------- tile builder
def _t_grass(surf, rng) -> None:
    surf.fill(GRASS)
    for _ in range(4):
        _soft_patch(surf, rng.choice((GRASS_L, GRASS_D)), rng.randrange(TILE),
                    rng.randrange(TILE), rng.randint(7, 14), 0.30)
    for _ in range(14):
        _blade(surf, rng, rng.randrange(TILE), rng.randrange(6, TILE),
               rng.choice((GRASS_L, GRASS_D, GRASS)), rng.randint(2, 4))
    if rng.random() < 0.35:
        _flower(surf, rng.randrange(4, TILE - 4), rng.randrange(6, TILE - 4),
                rng.choice(((244, 240, 220), (238, 214, 108), (206, 152, 214))))


def _t_meadow(surf, rng) -> None:
    surf.fill(MEADOW)
    for _ in range(5):
        _soft_patch(surf, rng.choice((MEADOW_L, MEADOW_D)), rng.randrange(TILE),
                    rng.randrange(TILE), rng.randint(8, 15), 0.34)
    for _ in range(18):
        _blade(surf, rng, rng.randrange(TILE), rng.randrange(6, TILE),
               rng.choice((MEADOW_L, MEADOW_D)), rng.randint(2, 5))
    for _ in range(rng.randint(0, 3)):
        _flower(surf, rng.randrange(3, TILE - 3), rng.randrange(5, TILE - 3),
                rng.choice(((250, 246, 226), (240, 220, 120), (216, 150, 210),
                            (226, 120, 120))))


def _t_forest_floor(surf, rng) -> None:
    surf.fill(FOREST_F)
    for _ in range(5):
        _soft_patch(surf, rng.choice((FOREST_FD, (58, 96, 58))), rng.randrange(TILE),
                    rng.randrange(TILE), rng.randint(7, 14), 0.32)
    for _ in range(22):                       # needles and twigs
        x, y = rng.randrange(TILE), rng.randrange(TILE)
        col = rng.choice((FOREST_FD, (72, 112, 64), (96, 88, 60)))
        _px(surf, x, y, col)
        _px(surf, x + 1, y + (1 if rng.random() < 0.5 else 0), col)
    for _ in range(rng.randint(1, 4)):        # moss
        _soft_patch(surf, (72, 128, 66), rng.randrange(TILE), rng.randrange(TILE),
                    rng.randint(3, 6), 0.45)


def _t_path(surf, rng) -> None:
    surf.fill(PATH)
    for _ in range(4):
        _soft_patch(surf, rng.choice((PATH_L, PATH_D)), rng.randrange(TILE),
                    rng.randrange(TILE), rng.randint(8, 14), 0.28)
    _speckle(surf, rng, (PATH_D, PATH_L), 26)
    for _ in range(rng.randint(1, 3)):
        _pebble(surf, rng.randrange(2, TILE - 5), rng.randrange(2, TILE - 4),
                mix(PATH_L, STONE_L, 0.5), PATH_D)
    # worn wheel ruts along the tile
    for y in (TILE // 3, TILE - TILE // 3):
        for x in range(0, TILE, 2):
            if rng.random() < 0.6:
                _px(surf, x, y, PATH_D)


def _t_dirt(surf, rng) -> None:
    surf.fill(mix(DIRT, MUD, 0.35))           # distinctly darker/browner than the road
    for _ in range(5):
        _soft_patch(surf, rng.choice((mix(DIRT_D, MUD, 0.4), mix(DIRT_L, MUD, 0.3))),
                    rng.randrange(TILE), rng.randrange(TILE), rng.randint(8, 15), 0.34)
    _speckle(surf, rng, (mix(DIRT_D, MUD, 0.5), DIRT_D, (74, 62, 46)), 34)
    for _ in range(rng.randint(0, 2)):
        _pebble(surf, rng.randrange(2, TILE - 5), rng.randrange(2, TILE - 4),
                mix(DIRT_D, STONE, 0.4), (58, 48, 36))


def _t_mud(surf, rng) -> None:
    surf.fill(MUD)
    for _ in range(5):
        _soft_patch(surf, rng.choice((MUD_D, MUD_L)), rng.randrange(TILE),
                    rng.randrange(TILE), rng.randint(7, 14), 0.34)
    for _ in range(rng.randint(2, 5)):        # puddle glints
        x, y = rng.randrange(3, TILE - 4), rng.randrange(3, TILE - 4)
        _rect(surf, mix(MUD_D, WATER_L, 0.35), x, y, rng.randint(3, 6), 2)


def _t_sand(surf, rng) -> None:
    surf.fill(SAND)
    for _ in range(5):
        _soft_patch(surf, rng.choice((SAND_L, SAND_D)), rng.randrange(TILE),
                    rng.randrange(TILE), rng.randint(8, 15), 0.26)
    _speckle(surf, rng, (SAND_D, SAND_L), 34)
    if rng.random() < 0.3:
        x, y = rng.randrange(4, TILE - 6), rng.randrange(4, TILE - 6)
        _rect(surf, (240, 234, 216), x, y, 3, 2)
        _px(surf, x + 1, y - 1, (252, 250, 244))


def _t_water(surf, rng, phase: int = 0) -> None:
    surf.fill(WATER)
    for y in range(TILE):
        k = 0.10 + 0.10 * math.sin((y + phase * 5) * 0.35)
        if k > 0.12:
            _rect(surf, mix(WATER, DEEP, k), 0, y, TILE, 1)
    for i in range(3):                        # moving wave crests
        y = int((i * 11 + phase * 4) % TILE)
        for x in range(0, TILE, 4):
            if (x // 4 + phase) % 3 == 0:
                _rect(surf, mix(WATER, WATER_L, 0.5), x, y, 3, 1)
    _speckle(surf, rng, (WATER_L, mix(WATER, WATER_L, 0.5)), 12)
    if rng.random() < 0.4:
        _rect(surf, FOAM, rng.randrange(TILE - 4), rng.randrange(TILE), 3, 1)


def _t_deep(surf, rng, phase: int = 0) -> None:
    surf.fill(DEEP)
    for y in range(TILE):
        k = 0.08 + 0.08 * math.sin((y + phase * 6) * 0.3)
        if k > 0.1:
            _rect(surf, mix(DEEP, WATER, k), 0, y, TILE, 1)
    for i in range(2):
        y = int((i * 15 + phase * 3) % TILE)
        for x in range(0, TILE, 5):
            if (x // 5 + phase) % 2 == 0:
                _rect(surf, mix(DEEP, WATER_L, 0.35), x, y, 3, 1)
    _speckle(surf, rng, (mix(DEEP, WATER, 0.6),), 8)


def _t_shallow(surf, rng, phase: int = 0) -> None:
    base = mix(WATER, SAND, 0.45)
    surf.fill(base)
    for _ in range(4):
        _soft_patch(surf, rng.choice((mix(base, WATER_L, 0.5), mix(base, SAND_L, 0.5))),
                    rng.randrange(TILE), rng.randrange(TILE), rng.randint(7, 13), 0.3)
    for i in range(3):
        y = int((i * 9 + phase * 4) % TILE)
        for x in range(0, TILE, 3):
            if (x // 3 + phase + i) % 3 == 0:
                _rect(surf, mix(base, (255, 255, 255), 0.5), x, y, 2, 1)
    _speckle(surf, rng, (mix(base, SAND_L, 0.6),), 10)


def _t_stone(surf, rng) -> None:
    surf.fill(STONE)
    for _ in range(4):
        _soft_patch(surf, rng.choice((STONE_L, STONE_D)), rng.randrange(TILE),
                    rng.randrange(TILE), rng.randint(8, 14), 0.3)
    for _ in range(rng.randint(1, 3)):        # cracks
        x, y = rng.randrange(TILE), rng.randrange(TILE)
        for i in range(rng.randint(3, 7)):
            _px(surf, x + i // 2, y + i, STONE_D)
    for _ in range(rng.randint(1, 3)):
        _pebble(surf, rng.randrange(2, TILE - 5), rng.randrange(2, TILE - 4),
                STONE_L, STONE_D)


def _t_snow(surf, rng) -> None:
    surf.fill(SNOW)
    for _ in range(4):
        _soft_patch(surf, rng.choice((SNOW_L, SNOW_D)), rng.randrange(TILE),
                    rng.randrange(TILE), rng.randint(8, 15), 0.24)
    for _ in range(14):                       # sparkle
        _px(surf, rng.randrange(TILE), rng.randrange(TILE), SNOW_L)
    for _ in range(rng.randint(1, 3)):        # buried rocks / grass tips
        x, y = rng.randrange(2, TILE - 4), rng.randrange(4, TILE - 3)
        _rect(surf, mix(SNOW_D, STONE, 0.5), x, y, 3, 2)


def _t_crops(surf, rng) -> None:
    surf.fill(mix(DIRT, MEADOW_D, 0.35))
    for y in range(2, TILE, 7):               # tilled rows
        _rect(surf, DIRT_D, 0, y, TILE, 1)
    for i in range(3):                        # plants
        x = 4 + i * 10 + rng.randint(0, 2)
        _rect(surf, (110, 138, 60), x, 8, 2, TILE - 9)
        _rect(surf, (146, 172, 72), x, 6, 2, 4)
        _rect(surf, (214, 200, 130), x - 1, 3, 4, 4)
        _px(surf, x, 3, (236, 226, 168))


def _t_floor(surf, rng) -> None:
    surf.fill(WOOD)
    for y in range(0, TILE, 8):               # planks
        _rect(surf, WOOD_D, 0, y, TILE, 1)
        _rect(surf, WOOD_L, 0, y + 1, TILE, 1)
        off = 0 if (y // 8) % 2 == 0 else 12
        _rect(surf, WOOD_D, off, y, 1, 8)
        _px(surf, off + 3, y + 3, WOOD_D)     # nail
    for _ in range(10):                       # grain
        x, y = rng.randrange(TILE), rng.randrange(TILE)
        _px(surf, x, y, mix(WOOD, WOOD_D, 0.5))


def _t_rock(surf, rng) -> None:
    surf.fill((52, 52, 58))                   # much darker than the stone floor
    for _ in range(3):
        _soft_patch(surf, rng.choice(((74, 74, 82), (38, 38, 44))), rng.randrange(TILE),
                    rng.randrange(TILE), rng.randint(7, 13), 0.4)
    for _ in range(rng.randint(2, 4)):        # slab lines
        y = rng.randrange(4, TILE - 2)
        _rect(surf, (28, 28, 34), 0, y, TILE, 1)
        _rect(surf, (86, 86, 94), 0, y + 1, TILE, 1)
    _speckle(surf, rng, ((96, 96, 104), (30, 30, 36)), 16)


def _t_void(surf, rng) -> None:
    surf.fill(VOID)
    _speckle(surf, rng, ((20, 32, 48), (14, 24, 38)), 20)


_TILE_BUILDERS = {
    T_VOID: lambda s, r, p: _t_void(s, r),
    T_DEEP: _t_deep,
    T_WATER: _t_water,
    T_SHALLOW: _t_shallow,
    T_SAND: lambda s, r, p: _t_sand(s, r),
    T_GRASS: lambda s, r, p: _t_grass(s, r),
    T_MEADOW: lambda s, r, p: _t_meadow(s, r),
    T_FOREST: lambda s, r, p: _t_forest_floor(s, r),
    T_PATH: lambda s, r, p: _t_path(s, r),
    T_DIRT: lambda s, r, p: _t_dirt(s, r),
    T_STONE: lambda s, r, p: _t_stone(s, r),
    T_SNOW: lambda s, r, p: _t_snow(s, r),
    T_MUD: lambda s, r, p: _t_mud(s, r),
    T_CROPS: lambda s, r, p: _t_crops(s, r),
    T_FLOOR: lambda s, r, p: _t_floor(s, r),
    T_ROCK: lambda s, r, p: _t_rock(s, r),
}

WATER_TILES = (T_DEEP, T_WATER, T_SHALLOW)
WATER_PHASES = 3


_tiles_cache: dict[int, list[pygame.Surface]] | None = None

def build_tiles() -> dict[int, list[pygame.Surface]]:
    global _tiles_cache
    if _tiles_cache is not None:
        return _tiles_cache
    tiles: dict[int, list[pygame.Surface]] = {}
    for ttype, builder in _TILE_BUILDERS.items():
        frames = WATER_PHASES if ttype in WATER_TILES else VARIANTS
        out = []
        for v in range(frames):
            surf = pygame.Surface((TILE, TILE))
            builder(surf, random.Random(ttype * 977 + v * 31), v)
            out.append(surf)
        tiles[ttype] = out
    _tiles_cache = tiles
    return tiles


# ------------------------------------------------------------- object helpers
def _outline(surf: pygame.Surface, col=(30, 24, 28), strength: float = 0.65,
             only_lower_right: bool = False) -> None:
    """Darken the silhouette edge so objects read against busy terrain."""
    w, h = surf.get_size()
    mask = pygame.mask.from_surface(surf)
    edge: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            if not mask.get_at((x, y)):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if only_lower_right and (dx, dy) not in ((1, 0), (0, 1)):
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and mask.get_at((nx, ny)):
                    continue
                edge.append((x, y))
                break
    for (x, y) in edge:
        base = surf.get_at((x, y))[:3]
        surf.set_at((x, y), mix(base, col, strength))


def _canopy(surf, cx, cy, r, palette, rng, lobes=7) -> None:
    """Round leafy crown: dark back mass, mid lobes, lit top-left, rim shadow."""
    dark, mid, light, xlight = palette
    deepest = shade(dark, 0.84)
    _disc(surf, deepest, cx, cy + r * 0.12, r)                 # back mass
    for i in range(lobes):
        a = i / lobes * math.tau
        lx = cx + math.cos(a) * r * 0.58
        ly = cy + math.sin(a) * r * 0.52
        _disc(surf, dark, lx, ly, r * 0.62)
    for i in range(lobes):
        a = i / lobes * math.tau - 0.4
        lx = cx + math.cos(a) * r * 0.42
        ly = cy + math.sin(a) * r * 0.38 - r * 0.08
        _disc(surf, mid, lx, ly, r * 0.58)
    _disc(surf, mid, cx, cy - r * 0.08, r * 0.80)
    _disc(surf, light, cx - r * 0.34, cy - r * 0.38, r * 0.46)  # lit top-left
    _disc(surf, light, cx + r * 0.22, cy - r * 0.30, r * 0.30)
    _disc(surf, xlight, cx - r * 0.40, cy - r * 0.48, r * 0.24)
    for _ in range(max(5, int(r * 0.8))):                       # leaf clusters
        a = rng.random() * math.tau
        d = rng.random() * r * 0.72
        px = cx + math.cos(a) * d
        py = cy + math.sin(a) * d
        tone = xlight if (px < cx and py < cy) else (light if py < cy else mid)
        _disc(surf, tone, px - r * 0.1, py - r * 0.2, rng.randint(1, max(2, int(r * 0.15))))
    for _ in range(max(4, int(r * 0.6))):                       # shadowed underside
        a = math.pi * (0.15 + rng.random() * 0.7)
        d = rng.random() * r * 0.78
        _disc(surf, deepest, cx + math.cos(a) * d,
              cy + math.sin(a) * d * 0.7 + r * 0.26, rng.randint(1, max(2, int(r * 0.13))))
    # rim: darken the lower-right arc of the crown
    for i in range(46):
        a = math.pi * (0.05 + 0.9 * (i / 45))
        rx = cx + math.cos(a) * (r - 1.5)
        ry = cy + math.sin(a) * (r - 1.5) + r * 0.08
        _disc(surf, deepest, rx, ry, max(1, r * 0.14))


def _trunk(surf, x, base_y, top_y, w, rng) -> None:
    _rect(surf, BARK_D, x, top_y, w, base_y - top_y)
    _rect(surf, BARK, x + 1, top_y, max(1, w - 2), base_y - top_y)
    _rect(surf, BARK_L, x + 1, top_y, 1, base_y - top_y)
    for _ in range((base_y - top_y) // 3):    # bark lines
        y = rng.randrange(top_y, base_y)
        _px(surf, x + rng.randrange(w), y, BARK_D)
    for dx in (-2, -1, w, w + 1):             # roots
        _rect(surf, BARK_D, x + dx, base_y - 3, 2, 4)


def _obj_oak(big: bool, rng: random.Random, tint=0) -> pygame.Surface:
    """A broad oak. The canvas is sized from the crown, so nothing is ever clipped,
    and the trunk is only ~1 tile tall: the visible trunk stays inside the tile that
    actually blocks movement, which is what makes the collision feel right."""
    if big:
        w, h = 116, 136
        trunk_w, trunk_top = 15, h - 30
        crown = (w // 2, 58, 42)
        sides = ((27, 82, 21), (88, 80, 20))
        lobes = 10
    else:
        w, h = 86, 102
        trunk_w, trunk_top = 12, h - 26
        crown = (w // 2, 44, 30)
        sides = ((22, 62, 15), (65, 60, 14))
        lobes = 7
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    palettes = ((LEAF_D, LEAF, LEAF_L, LEAF_XL),
                ((30, 78, 50), (52, 112, 62), (86, 150, 74), (128, 184, 96)),
                ((42, 88, 44), (66, 128, 54), (104, 168, 72), (150, 200, 104)))
    pal = palettes[tint % len(palettes)]
    base_y = h - 4
    # contact shadow, then roots and the trunk itself
    pygame.draw.ellipse(s, (0, 0, 0, 78), (w * 0.14, base_y - 7, w * 0.72, 13))
    for dx in (-3, -2, trunk_w + 1, trunk_w + 2):
        _rect(s, BARK_D, w // 2 - trunk_w // 2 + dx, base_y - 5, 2, 5)
    _trunk(s, w // 2 - trunk_w // 2, base_y, trunk_top, trunk_w, rng)
    # two forks climbing into the crown
    fork_y = trunk_top + 6
    for sx, dy, ln in ((-1, 2, 16), (1, -2, 18)):
        x0 = w // 2 + sx * (trunk_w // 2 - 1)
        for k in range(ln):
            _rect(s, BARK_D if k % 3 else BARK, x0 + sx * k, fork_y + dy - k, 4, 3)
    # crown: side masses first, then the main one on top
    for (cx, cy, r) in sides:
        _canopy(s, cx, cy, r, pal, rng, lobes=5)
    _canopy(s, crown[0], crown[1], crown[2], pal, rng, lobes=lobes)
    # a few leaves hanging below the crown so it does not read as a flat disc
    for _ in range(7 if big else 5):
        lx = crown[0] + rng.uniform(-crown[2] * 0.7, crown[2] * 0.7)
        ly = crown[1] + crown[2] * 0.85 + rng.uniform(0, 6)
        _disc(s, pal[0], lx, ly, rng.randint(2, 4))
        _disc(s, pal[1], lx - 1, ly - 1, rng.randint(1, 2))
    return s


def _obj_pine(big: bool, rng: random.Random, tint=0) -> pygame.Surface:
    """A spruce: stacked tiers that taper to a point, all inside the canvas."""
    if big:
        w, h = 92, 142
        trunk_w, trunk_top = 11, h - 34
        tiers, base_half, apex_y = 5, 36, 16
    else:
        w, h = 68, 106
        trunk_w, trunk_top = 8, h - 26
        tiers, base_half, apex_y = 4, 26, 12
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pals = ((PINE_D, PINE, PINE_L), ((22, 62, 50), (34, 84, 62), (54, 112, 76)),
            ((34, 80, 48), (48, 106, 56), (74, 138, 74)))
    dark, mid, light = pals[tint % len(pals)]
    base_y = h - 4
    pygame.draw.ellipse(s, (0, 0, 0, 78), (w * 0.18, base_y - 7, w * 0.64, 12))
    _trunk(s, w // 2 - trunk_w // 2, base_y, trunk_top, trunk_w, rng)
    top_y = trunk_top + 4
    span = top_y - apex_y
    for i in range(tiers):
        t = i / max(1, tiers - 1)
        y = int(top_y - span * 0.86 * t)
        half = int(base_half * (1.0 - 0.72 * t))
        height = int(span * 0.30)
        pts = [(w // 2, y - height), (w // 2 - half, y), (w // 2 + half, y)]
        pygame.draw.polygon(s, dark, pts)
        pygame.draw.polygon(s, mid, [(w // 2, y - height + 4), (w // 2 - half + 5, y - 1),
                                     (w // 2 + half - 5, y - 1)])
        pygame.draw.line(s, light, (w // 2, y - height + 3),
                         (w // 2 - half + 7, y - 2), 1)
        pygame.draw.line(s, dark, (w // 2 + 2, y - 1), (w // 2 + half - 3, y - 1), 1)
    for _ in range(12):                       # snow and needle speckles
        _px(s, rng.randrange(2, w - 2), rng.randrange(apex_y, trunk_top), light)
    return s


def _obj_birch(rng: random.Random) -> pygame.Surface:
    w, h = 72, 112
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    base_y = h - 4
    pal = ((78, 128, 62), (110, 162, 78), (150, 194, 96), (188, 216, 128))
    pygame.draw.ellipse(s, (0, 0, 0, 72), (16, base_y - 7, 40, 11))
    trunk_top = 58                              # up into the crown, not a floating stub
    _rect(s, (198, 194, 180), w // 2 - 3, trunk_top, 7, base_y - trunk_top)
    _rect(s, (232, 230, 222), w // 2 - 3, trunk_top, 3, base_y - trunk_top)
    for _ in range(9):                        # birch markings
        y = rng.randrange(trunk_top + 3, base_y)
        _rect(s, (74, 70, 62), w // 2 - 3, y, rng.randint(2, 5), 1)
    for sx in (-1, 1):                        # two thin branches into the lobes
        for k in range(10):
            _rect(s, (198, 194, 180), w // 2 + sx * (3 + k), trunk_top + 6 - k, 2, 2)
    _canopy(s, 18, 52, 16, pal, rng, lobes=5)
    _canopy(s, 54, 50, 15, pal, rng, lobes=5)
    _canopy(s, w // 2, 32, 24, pal, rng, lobes=7)
    return s


def _obj_dead_tree(rng: random.Random) -> pygame.Surface:
    w, h = 56, 92
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    base_y = h - 6
    pygame.draw.ellipse(s, (0, 0, 0, 60), (12, base_y - 4, 34, 9))
    _rect(s, (74, 58, 44), w // 2 - 3, 20, 7, base_y - 20)
    _rect(s, (96, 76, 58), w // 2 - 2, 20, 3, base_y - 20)
    for (x, y, dx, dy) in ((-10, 30, -8, -10), (8, 26, 10, -12), (-7, 46, -9, -6),
                           (7, 44, 8, -8)):
        pygame.draw.line(s, (84, 66, 50), (w // 2, y), (w // 2 + dx, y + dy), 2)
        pygame.draw.line(s, (74, 58, 44), (w // 2 + dx, y + dy),
                         (w // 2 + dx + (4 if dx > 0 else -4), y + dy - 4), 1)
    return s


def _obj_bush(rng: random.Random, berries=False) -> pygame.Surface:
    w, h = 40, 32
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 55), (6, 24, 28, 7))
    pal = ((40, 92, 48), (58, 122, 58), (92, 156, 76), (126, 182, 96))
    _canopy(s, w // 2, 17, 13, pal, rng, lobes=6)
    if berries:
        for _ in range(7):
            x, y = rng.randrange(8, w - 8), rng.randrange(8, 24)
            _px(s, x, y, (196, 52, 58))
            _px(s, x, y - 1, (226, 96, 96))
    return s


def _obj_rock(big: bool, rng: random.Random) -> pygame.Surface:
    w, h = (56, 46) if big else (34, 26)
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 70), (4, h - 9, w - 8, 8))
    body = [(w * 0.5, h * 0.08), (w * 0.86, h * 0.34), (w * 0.8, h * 0.78),
            (w * 0.42, h * 0.88), (w * 0.12, h * 0.66), (w * 0.16, h * 0.3)]
    pygame.draw.polygon(s, STONE_D, body)
    top = [(w * 0.5, h * 0.12), (w * 0.78, h * 0.36), (w * 0.7, h * 0.62),
           (w * 0.44, h * 0.7), (w * 0.22, h * 0.5), (w * 0.26, h * 0.32)]
    pygame.draw.polygon(s, STONE, top)
    lit = [(w * 0.5, h * 0.14), (w * 0.66, h * 0.32), (w * 0.56, h * 0.5),
           (w * 0.34, h * 0.44)]
    pygame.draw.polygon(s, STONE_L, lit)
    for _ in range(8):                        # cracks
        x, y = rng.randrange(int(w * 0.2), int(w * 0.8)), rng.randrange(int(h * 0.25), h - 6)
        _px(s, x, y, (78, 78, 86))
    for _ in range(3):                        # moss
        _soft_patch(s, (74, 122, 66), rng.randrange(int(w * 0.2), int(w * 0.8)),
                    rng.randrange(int(h * 0.5), h - 5), rng.randint(2, 4), 0.5)
    return s


def _obj_stump(rng: random.Random) -> pygame.Surface:
    w, h = 34, 26
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 60), (5, h - 8, 24, 6))
    _rect(s, WOOD_D, 7, 10, 20, h - 15)
    _rect(s, WOOD, 8, 10, 17, h - 16)
    pygame.draw.ellipse(s, WOOD_L, (7, 6, 20, 10))
    pygame.draw.ellipse(s, WOOD, (9, 8, 16, 7))
    pygame.draw.ellipse(s, mix(WOOD, WOOD_D, 0.4), (12, 10, 10, 4))
    _px(s, 17, 12, WOOD_D)
    return s


def _obj_grass_tuft(rng: random.Random) -> pygame.Surface:
    w, h = 18, 16
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 40), (2, h - 4, 14, 4))
    base = rng.choice(((64, 118, 56), (84, 142, 66), (52, 104, 52)))
    for i in range(5):
        x = 4 + i * 2 + rng.randrange(-1, 2)
        ln = 5 + rng.randrange(0, 4)
        col = mix(base, (140, 186, 88), i / 5)
        _rect(s, col, x, h - 6 - ln, 2, ln)
    return s


def _obj_flower2(rng: random.Random) -> pygame.Surface:
    w, h = 14, 16
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 45), (2, h - 3, 10, 3))
    _rect(s, (66, 122, 62), 6, 8, 2, 6)
    col = rng.choice(((118, 92, 200), (208, 120, 160), (240, 200, 120)))
    for k in range(5):
        a = k / 5 * math.tau
        _px(s, 7 + int(math.cos(a) * 4.2), 5 + int(math.sin(a) * 3.4), col)
    _px(s, 7, 5, (255, 236, 180))
    return s


def _obj_pebble(rng: random.Random) -> pygame.Surface:
    w, h = 16, 12
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 40), (2, h - 3, 12, 3))
    col = rng.choice(((150, 152, 158), (142, 138, 130), (132, 136, 146)))
    pygame.draw.ellipse(s, col, (2, 1, 12, 8))
    pygame.draw.ellipse(s, mix(col, (210, 212, 218), 0.5), (4, 1, 5, 3))
    return s


def _obj_shell(rng: random.Random) -> pygame.Surface:
    w, h = 14, 12
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 40), (1, h - 3, 12, 3))
    col = rng.choice(((238, 214, 180), (226, 200, 168), (214, 188, 158)))
    pygame.draw.ellipse(s, col, (2, 1, 10, 8))
    pygame.draw.line(s, mix(col, (150, 120, 96), 0.5), (4, 3), (11, 6), 1)
    pygame.draw.line(s, mix(col, (150, 120, 96), 0.5), (5, 5), (10, 7), 1)
    _px(s, 4, 2, mix(col, (255, 250, 230), 0.6))
    return s


def _obj_reed(rng: random.Random) -> pygame.Surface:
    w, h = 14, 24
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 40), (2, h - 4, 10, 4))
    _rect(s, (60, 108, 58), 6, 8, 2, h - 12)
    _px(s, 6, 5, (108, 78, 46))
    _rect(s, (126, 92, 56), 5, 2, 4, 7)
    _px(s, 5, 3, mix((126, 92, 56), (206, 168, 116), 0.5))
    return s


def _obj_mushroom(rng: random.Random) -> pygame.Surface:
    w, h = 16, 16
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 45), (2, h - 3, 12, 3))
    _rect(s, (224, 220, 206), 7, 7, 3, 6)
    cap = rng.choice(((196, 58, 52), (168, 96, 54), (150, 60, 130)))
    pygame.draw.ellipse(s, cap, (1, 2, 14, 9))
    _px(s, 5, 3, (255, 240, 240))
    _px(s, 9, 4, (255, 240, 240))
    _px(s, 3, 6, (255, 240, 240))
    return s


def _obj_log(rng: random.Random) -> pygame.Surface:
    w, h = 48, 22
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 55), (3, h - 7, 42, 6))
    _rect(s, WOOD_D, 3, 6, 42, 11)
    _rect(s, WOOD, 4, 7, 40, 8)
    pygame.draw.ellipse(s, WOOD_L, (2, 6, 8, 11))
    pygame.draw.ellipse(s, WOOD, (4, 8, 4, 7))
    for x in range(6, 44, 5):
        _px(s, x, 9 + (x % 3), WOOD_D)
    return s


def _obj_fence(rng: random.Random, vertical=False) -> pygame.Surface:
    w, h = (14, 36) if vertical else (36, 30)
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 50), (2, h - 6, w - 4, 5))
    if vertical:
        _rect(s, WOOD_D, 5, 4, 4, h - 8)
        _rect(s, WOOD, 6, 4, 2, h - 8)
        for y in (10, 20):
            _rect(s, WOOD_L, 2, y, 10, 3)
    else:
        _rect(s, WOOD_D, 4, 6, 4, h - 10)
        _rect(s, WOOD_D, w - 8, 6, 4, h - 10)
        for y in (12, 20):
            _rect(s, WOOD_L, 0, y, w, 3)
            _rect(s, WOOD_D, 0, y + 3, w, 1)
    return s


def _obj_well(rng: random.Random) -> pygame.Surface:
    w, h = 48, 54
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 70), (6, h - 9, 36, 8))
    _rect(s, STONE_D, 8, 30, 32, 18)
    for y in range(31, 48, 5):                # stone courses
        _rect(s, STONE, 8, y, 32, 4)
        for x in range(9, 40, 8):
            _rect(s, STONE_D, x, y, 1, 4)
    pygame.draw.ellipse(s, STONE_L, (8, 26, 32, 9))
    pygame.draw.ellipse(s, (22, 26, 34), (12, 28, 24, 6))
    _rect(s, WOOD_D, 11, 6, 4, 24)
    _rect(s, WOOD_D, 33, 6, 4, 24)
    _rect(s, WOOD, 6, 2, 36, 5)
    _rect(s, WOOD_L, 6, 2, 36, 1)
    _rect(s, WOOD_D, 23, 7, 3, 8)
    _rect(s, IRON, 21, 15, 7, 5)
    return s


def _obj_barrel(rng: random.Random) -> pygame.Surface:
    w, h = 26, 34
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 60), (3, h - 7, 20, 5))
    _rect(s, WOOD_D, 4, 5, 18, h - 12)
    _rect(s, WOOD, 5, 5, 15, h - 12)
    for x in (7, 11, 15):
        _rect(s, WOOD_D, x, 5, 1, h - 12)
    for y in (10, 20):
        _rect(s, IRON, 4, y, 18, 2)
    pygame.draw.ellipse(s, WOOD_L, (4, 3, 18, 6))
    pygame.draw.ellipse(s, mix(WOOD, WOOD_D, 0.5), (7, 5, 12, 3))
    return s


def _obj_crate(rng: random.Random) -> pygame.Surface:
    w, h = 28, 28
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 55), (3, h - 6, 22, 5))
    _rect(s, WOOD_D, 3, 4, 22, 20)
    _rect(s, WOOD, 4, 5, 20, 18)
    pygame.draw.line(s, WOOD_D, (4, 5), (23, 22), 2)
    pygame.draw.line(s, WOOD_D, (23, 5), (4, 22), 2)
    _rect(s, WOOD_L, 4, 5, 20, 1)
    return s


def _obj_lamp(rng: random.Random) -> pygame.Surface:
    w, h = 26, 62
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 55), (6, h - 7, 14, 5))
    _rect(s, (48, 46, 52), 11, 20, 4, h - 26)
    _rect(s, (72, 70, 78), 11, 20, 2, h - 26)
    _rect(s, (48, 46, 52), 6, 34, 14, 3)
    _rect(s, IRON, 6, 16, 14, 4)
    _rect(s, (40, 36, 30), 7, 20, 12, 13)
    _rect(s, (255, 226, 150), 8, 21, 10, 11)
    _rect(s, (255, 248, 216), 10, 23, 6, 6)
    _rect(s, IRON_L, 6, 33, 14, 2)
    return s


def _obj_signpost(rng: random.Random) -> pygame.Surface:
    w, h = 42, 46
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 55), (14, h - 7, 12, 5))
    _rect(s, WOOD_D, 19, 10, 4, h - 14)
    _rect(s, WOOD, 6, 6, 28, 12)
    _rect(s, WOOD_L, 6, 6, 28, 1)
    _rect(s, WOOD_D, 6, 17, 28, 1)
    for y in (9, 12, 15):
        _rect(s, WOOD_D, 9, y, 20, 1)
    pygame.draw.polygon(s, WOOD, [(34, 5), (40, 12), (34, 19)])
    pygame.draw.polygon(s, WOOD_L, [(34, 6), (38, 12), (34, 13)])
    return s


def _obj_haystack(rng: random.Random) -> pygame.Surface:
    w, h = 48, 42
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 55), (7, h - 8, 34, 6))
    pygame.draw.polygon(s, (168, 142, 66), [(24, 4), (42, h - 8), (6, h - 8)])
    pygame.draw.polygon(s, (200, 174, 88), [(24, 8), (36, h - 9), (12, h - 9)])
    for _ in range(26):
        x, y = rng.randrange(8, 40), rng.randrange(10, h - 8)
        _rect(s, (222, 198, 118) if rng.random() < 0.5 else (150, 126, 58), x, y, 3, 1)
    _rect(s, (120, 96, 44), 8, h - 9, w - 16, 2)
    return s


def _obj_campfire(rng: random.Random) -> pygame.Surface:
    w, h = 40, 34
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 60), (5, h - 8, 30, 6))
    for i in range(7):                        # stones
        a = i / 7 * math.tau
        _disc(s, mix(STONE, STONE_D, rng.random()), 20 + math.cos(a) * 13,
              26 + math.sin(a) * 4, 4)
    _rect(s, WOOD_D, 8, 22, 24, 4)
    _rect(s, WOOD_D, 12, 19, 18, 4)
    pygame.draw.polygon(s, (232, 120, 40), [(20, 6), (27, 22), (13, 22)])
    pygame.draw.polygon(s, (252, 186, 62), [(20, 11), (24, 22), (16, 22)])
    pygame.draw.polygon(s, (255, 240, 190), [(20, 16), (22, 22), (18, 22)])
    return s


def _obj_tent(rng: random.Random) -> pygame.Surface:
    w, h = 56, 44
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 60), (4, h - 8, 48, 6))
    pygame.draw.polygon(s, (150, 128, 96), [(28, 4), (54, h - 8), (2, h - 8)])
    pygame.draw.polygon(s, (186, 164, 128), [(28, 8), (48, h - 9), (8, h - 9)])
    pygame.draw.polygon(s, (44, 38, 32), [(28, 22), (36, h - 8), (20, h - 8)])
    _rect(s, WOOD_D, 27, 4, 2, 12)
    return s


def _obj_stall(rng: random.Random) -> pygame.Surface:
    w, h = 72, 56
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 60), (6, h - 9, 60, 7))
    _rect(s, WOOD_D, 8, 20, 6, h - 26)
    _rect(s, WOOD_D, w - 14, 20, 6, h - 26)
    _rect(s, WOOD, 4, 34, w - 8, 8)
    _rect(s, WOOD_L, 4, 34, w - 8, 1)
    for x in range(6, w - 8, 8):              # goods on the counter
        _rect(s, rng.choice(((196, 60, 60), (222, 180, 60), (120, 176, 84))), x, 29, 5, 5)
    for i in range(6):                        # striped awning
        col = (206, 76, 70) if i % 2 == 0 else (238, 232, 220)
        pygame.draw.polygon(s, col, [(2 + i * 11, 6), (13 + i * 11, 6),
                                     (10 + i * 11, 22), (5 + i * 11, 22)])
    _rect(s, WOOD_D, 2, 4, w - 4, 3)
    return s


def _obj_shrine(rng: random.Random) -> pygame.Surface:
    """Каменная арка с чашей огня — святилище на перекрёстках и в глуши."""
    w, h = 44, 66
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 70), (5, h - 9, 34, 7))
    _rect(s, STONE_D, 6, h - 14, 32, 8)          # основание
    _rect(s, STONE, 8, h - 16, 28, 4)
    _rect(s, STONE_D, 8, 20, 8, h - 34)          # левая опора
    _rect(s, STONE, 9, 20, 6, h - 34)
    _rect(s, STONE_D, 28, 20, 8, h - 34)         # правая опора
    _rect(s, STONE, 29, 20, 6, h - 34)
    _rect(s, STONE_D, 6, 12, 32, 9)              # перекладина
    _rect(s, STONE_L, 6, 12, 32, 2)
    for x in range(8, 36, 5):                    # насечки на арке
        _rect(s, STONE_D, x, 16, 1, 4)
    _rect(s, IRON, 17, h - 26, 10, 8)            # чаша
    _rect(s, IRON_L, 17, h - 26, 10, 2)
    _rect(s, (232, 152, 72), 19, h - 31, 6, 5)   # огонь
    _rect(s, (255, 214, 128), 20, h - 34, 4, 4)
    for _ in range(3):                           # мох и трещины
        _px(s, rng.randrange(9, 35), rng.randrange(22, h - 16), (86, 108, 72))
    return s


def _obj_tower(rng: random.Random) -> pygame.Surface:
    """Сторожевая башня: узнаваемый силуэт, видна издалека."""
    w, h = 58, 112
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 70), (8, h - 10, 42, 8))
    _rect(s, STONE_D, 12, h - 16, 34, 10)        # цоколь
    _rect(s, STONE, 14, 34, 30, h - 48)          # ствол
    _rect(s, STONE_L, 14, 34, 4, h - 48)
    _rect(s, STONE_D, 40, 34, 4, h - 48)
    for y in range(44, h - 20, 9):               # кладка
        _rect(s, STONE_D, 14, y, 30, 1)
    for x in range(18, 44, 7):
        _rect(s, STONE_D, x, 34, 1, h - 48)
    _rect(s, (34, 30, 36), 26, 56, 7, 12)        # бойница
    _rect(s, (34, 30, 36), 26, 84, 7, 10)
    _rect(s, STONE_D, 8, 24, 42, 12)             # площадка
    _rect(s, STONE, 8, 24, 42, 3)
    for i in range(6):                           # зубцы
        _rect(s, STONE, 9 + i * 7, 16, 5, 9)
        _rect(s, STONE_L, 9 + i * 7, 16, 5, 2)
    _rect(s, WOOD_D, 20, h - 30, 18, 5)          # дверь
    _rect(s, WOOD, 21, h - 29, 16, 3)
    for _ in range(4):
        _px(s, rng.randrange(16, 42), rng.randrange(40, h - 20), STONE_D)
    return s


def _obj_windmill(rng: random.Random) -> pygame.Surface:
    """Ветряная мельница: башня с конусом и лопастями."""
    w, h = 66, 116
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 70), (10, h - 10, 46, 8))
    _rect(s, WOOD_D, 14, 34, 38, h - 44)          # башня
    _rect(s, WOOD, 16, 34, 34, h - 44)
    _rect(s, WOOD_L, 16, 34, 5, h - 44)
    for y in range(48, h - 12, 10):               # брёвна
        _rect(s, WOOD_D, 16, y, 34, 2)
    _rect(s, WOOD_D, 26, 58, 12, 16)              # дверь
    _rect(s, WOOD, 27, 59, 10, 14)
    _rect(s, WOOD_D, 34, 88, 10, 8)               # окошко
    # конус крыши
    for i, (cy, cw) in enumerate(((26, 38), (18, 28), (12, 18))):
        _rect(s, STONE if i % 2 else STONE_D, 33 - cw // 2, cy, cw, 3)
        _rect(s, STONE_L, 33 - cw // 2, cy, cw, 1)
    # лопасти: крест из четырёх (начинается ниже края канваса)
    pygame.draw.line(s, WOOD_D, (33, 14), (14, 26), 3)
    pygame.draw.line(s, WOOD_D, (33, 14), (52, 26), 3)
    pygame.draw.line(s, WOOD_D, (33, 14), (33, 32), 3)
    for (x0, y0, x1, y1) in ((14, 26, 12, 36), (52, 26, 54, 36), (33, 32, 33, 42)):
        pygame.draw.line(s, WOOD_L, (x0, y0), (x1, y1), 2)
    for i in range(4):                            # малые лопасти-планки
        pygame.draw.line(s, WOOD, (33, 14), (33 + [10, -10, 2, 2][i],
                        14 + [2, 2, 12, -8][i]), 2)
    return s


def _obj_beehive(rng: random.Random) -> pygame.Surface:
    """Улей: стопка рам, стоящая на бревне; сбоку от него — дымок."""
    w, h = 36, 46
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 60), (6, h - 7, 24, 6))
    _rect(s, WOOD_D, 4, 18, 28, 6)                # крыша-рамка
    _rect(s, WOOD_L, 4, 18, 28, 2)
    for y in range(24, 44, 4):                    # корпус из реек
        _rect(s, WOOD, 5, y, 26, 4)
        _rect(s, WOOD_D, 5, y + 2, 26, 1)
    _rect(s, WOOD_L, 5, 24, 2, 20)                # боковая грань
    _rect(s, WOOD_L, 29, 24, 2, 20)
    _rect(s, (222, 190, 96), 11, 34, 4, 4)        # соты-окошко
    _rect(s, (222, 190, 96), 21, 30, 4, 4)
    # пчёлы-точки
    for _ in range(3):
        _px(s, rng.randrange(6, 30), rng.randrange(22, 40), (214, 168, 60))
    return s


def _obj_cart(rng: random.Random) -> pygame.Surface:
    """Вагонетка с рудой — примета шахт и брошенных лагерей."""
    w, h = 42, 30
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 60), (4, h - 6, 34, 5))
    _rect(s, IRON, 6, 8, 30, 12)                 # кузов
    _rect(s, IRON_L, 6, 8, 30, 2)
    _rect(s, (66, 66, 74), 8, 11, 26, 7)
    for _ in range(5):                           # руда
        _rect(s, (150, 132, 96), rng.randrange(9, 31), rng.randrange(9, 14), 4, 3)
    for cx in (13, 29):                          # колёса
        pygame.draw.circle(s, (58, 58, 66), (cx, h - 8), 5)
        pygame.draw.circle(s, IRON, (cx, h - 8), 3, 1)
    _rect(s, WOOD_D, 4, 6, 3, 8)                 # ручка
    return s


def _obj_pillar(rng: random.Random) -> pygame.Surface:
    w, h = 34, 78
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 65), (4, h - 8, 26, 6))
    _rect(s, STONE_D, 6, h - 12, 22, 8)
    _rect(s, STONE, 8, 10, 18, h - 20)
    for x in range(9, 26, 4):
        _rect(s, STONE_D, x, 10, 1, h - 20)
    _rect(s, STONE_L, 8, 10, 3, h - 20)
    _rect(s, STONE, 5, 4, 24, 8)
    _rect(s, STONE_L, 5, 4, 24, 2)
    for _ in range(3):                        # cracks / wear
        x, y = rng.randrange(10, 24), rng.randrange(14, h - 20)
        _px(s, x, y, STONE_D)
    return s


def _obj_ruin(rng: random.Random) -> pygame.Surface:
    w, h = 72, 46
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 55), (6, h - 8, 60, 6))
    heights = [26, 18, 30, 12, 22, 16, 28, 14]
    for i, hh in enumerate(heights):
        x = 4 + i * 8
        _rect(s, STONE_D, x, h - 8 - hh, 8, hh)
        _rect(s, STONE, x, h - 8 - hh, 7, hh - 1)
        _rect(s, STONE_L, x, h - 8 - hh, 7, 2)
        for y in range(h - 8 - hh, h - 8, 5):
            _rect(s, STONE_D, x, y, 7, 1)
    for _ in range(4):                        # fallen blocks
        _rect(s, STONE, rng.randrange(2, w - 6), h - 10, 5, 4)
    return s


def _obj_cave(rng: random.Random) -> pygame.Surface:
    w, h = 76, 60
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 70), (6, h - 10, 64, 9))
    pygame.draw.polygon(s, mix(STONE_D, (70, 70, 78), 0.5),
                        [(6, h - 8), (16, 18), (38, 6), (60, 16), (70, h - 8)])
    pygame.draw.polygon(s, STONE_D, [(12, h - 8), (20, 22), (38, 12), (56, 20), (64, h - 8)])
    pygame.draw.ellipse(s, (12, 12, 18), (26, 26, 26, 30))
    pygame.draw.ellipse(s, (26, 24, 34), (29, 29, 20, 26))
    for _ in range(10):
        x, y = rng.randrange(14, 62), rng.randrange(14, h - 10)
        _px(s, x, y, mix(STONE, STONE_L, rng.random()))
    return s


def _obj_bridge(rng: random.Random) -> pygame.Surface:
    w, h = 32, 44
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    _rect(s, WOOD_D, 2, 0, 28, h)
    for y in range(0, h, 6):                  # planks across
        _rect(s, WOOD, 3, y + 1, 26, 5)
        _rect(s, WOOD_L, 3, y + 1, 26, 1)
    _rect(s, WOOD_D, 2, 0, 2, h)
    _rect(s, WOOD_D, w - 4, 0, 2, h)
    return s


def _obj_flowerbed(rng: random.Random) -> pygame.Surface:
    w, h = 36, 26
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 45), (4, h - 7, 28, 5))
    _rect(s, DIRT_D, 4, 8, 28, 13)
    for _ in range(16):
        _px(s, rng.randrange(6, 30), rng.randrange(10, 20), (110, 148, 70))
    for _ in range(7):
        _flower(s, rng.randrange(7, 29), rng.randrange(11, 19),
                rng.choice(((244, 240, 220), (238, 200, 90), (222, 130, 190),
                            (226, 110, 110))))
    return s


def _obj_grave(rng: random.Random) -> pygame.Surface:
    w, h = 30, 40
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 55), (4, h - 7, 22, 5))
    _rect(s, STONE_D, 7, 10, 16, h - 16)
    _rect(s, STONE, 8, 10, 14, h - 17)
    pygame.draw.ellipse(s, STONE, (7, 4, 16, 12))
    pygame.draw.ellipse(s, STONE_L, (8, 5, 14, 9))
    _rect(s, STONE_D, 13, 14, 4, 10)
    _rect(s, STONE_D, 10, 17, 10, 3)
    return s


HOUSE_STYLES = (
    {"wall": WOOD, "wall_d": WOOD_D, "wall_l": WOOD_L, "roof": ROOF_RED,
     "roof_d": ROOF_RED_D, "plaster": False},
    {"wall": PLASTER, "wall_d": PLASTER_D, "wall_l": (244, 234, 210), "roof": ROOF_BROWN,
     "roof_d": ROOF_BROWN_D, "plaster": True},
    {"wall": STONE_WALL, "wall_d": STONE_D, "wall_l": STONE_L, "roof": ROOF_SLATE,
     "roof_d": ROOF_SLATE_D, "plaster": False},
)


def _obj_house(style: int, rng: random.Random, wide: bool = False) -> pygame.Surface:
    st = HOUSE_STYLES[style % len(HOUSE_STYLES)]
    w = 176 if wide else 144
    h = 152
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    base_y = h - 10
    wall_x, wall_w = 18, w - 36
    wall_top = 62
    pygame.draw.ellipse(s, (0, 0, 0, 80), (10, base_y - 6, w - 20, 16))
    # walls
    _rect(s, st["wall_d"], wall_x, wall_top, wall_w, base_y - wall_top)
    _rect(s, st["wall"], wall_x + 2, wall_top, wall_w - 4, base_y - wall_top - 2)
    if st["plaster"]:                          # timber framing
        for x in range(wall_x + 6, wall_x + wall_w - 6, 26):
            _rect(s, WOOD_D, x, wall_top, 5, base_y - wall_top)
        _rect(s, WOOD_D, wall_x, wall_top + 18, wall_w, 5)
    else:                                      # plank lines
        for y in range(wall_top + 4, base_y, 9):
            _rect(s, st["wall_d"], wall_x + 2, y, wall_w - 4, 1)
        _rect(s, st["wall_l"], wall_x + 2, wall_top + 1, wall_w - 4, 1)
    _rect(s, st["wall_d"], wall_x, wall_top, 5, base_y - wall_top)
    _rect(s, st["wall_d"], wall_x + wall_w - 5, wall_top, 5, base_y - wall_top)
    # stone foundation
    _rect(s, STONE_D, wall_x - 2, base_y - 12, wall_w + 4, 12)
    _rect(s, STONE, wall_x - 1, base_y - 11, wall_w + 2, 9)
    for x in range(wall_x, wall_x + wall_w, 10):
        _rect(s, STONE_D, x, base_y - 11, 1, 9)
    # roof: two slopes + ridge
    eave = 8
    roof_bottom = wall_top + 8
    ridge_y = 14
    pygame.draw.polygon(s, st["roof_d"],
                        [(2, roof_bottom), (w // 2, ridge_y - 4), (w - 2, roof_bottom),
                         (w - eave, roof_bottom + 6), (w // 2, ridge_y + 6),
                         (eave, roof_bottom + 6)])
    pygame.draw.polygon(s, st["roof"],
                        [(eave, roof_bottom), (w // 2, ridge_y), (w - eave, roof_bottom)])
    for i in range(7):                         # shingle rows along the slope
        t = i / 6
        y = int(ridge_y + (roof_bottom - ridge_y) * t)
        half = int((w / 2 - eave) * t)
        _rect(s, shade(st["roof"], 0.86 if i % 2 else 1.0), w // 2 - half, y,
              half * 2, 3)
        _rect(s, shade(st["roof_d"], 0.9), w // 2 - half, y + 3, half * 2, 1)
    _rect(s, shade(st["roof"], 1.22), w // 2 - 2, ridge_y - 1, 4, roof_bottom - ridge_y)
    pygame.draw.polygon(s, shade(st["roof_d"], 0.75),
                        [(2, roof_bottom), (w // 2, ridge_y - 4),
                         (w // 2 + 2, ridge_y - 3), (eave, roof_bottom + 6)])
    _rect(s, shade(st["roof"], 1.1), eave, roof_bottom, w - eave * 2, 2)
    _rect(s, (52, 40, 30), eave - 2, roof_bottom + 2, w - (eave - 2) * 2, 3)
    # chimney
    ch_x = int(w * 0.68)
    _rect(s, STONE_D, ch_x, 22, 18, 40)
    _rect(s, STONE, ch_x + 1, 22, 15, 40)
    _rect(s, STONE_L, ch_x - 2, 18, 22, 6)
    for y in range(26, 60, 6):
        _rect(s, STONE_D, ch_x + 1, y, 15, 1)
    # door
    door_w, door_h = 30, 46
    dx = w // 2 - door_w // 2
    dy = base_y - door_h - 6
    _rect(s, WOOD_D, dx - 3, dy - 3, door_w + 6, door_h + 6)
    _rect(s, (92, 62, 38), dx, dy, door_w, door_h)
    for x in range(dx + 4, dx + door_w - 3, 6):
        _rect(s, (72, 48, 30), x, dy + 2, 1, door_h - 4)
    _rect(s, (120, 84, 50), dx + 1, dy + 1, door_w - 2, 2)
    _disc(s, GOLD, dx + door_w - 6, dy + door_h // 2, 2)
    _rect(s, STONE, dx - 6, base_y - 5, door_w + 12, 5)
    # windows
    for wx in (wall_x + 10, wall_x + wall_w - 34):
        if wide and wx == wall_x + 10:
            pass
        wy = wall_top + 16
        _rect(s, WOOD_D, wx - 2, wy - 2, 28, 28)
        _rect(s, (58, 74, 84), wx, wy, 24, 24)
        _rect(s, GLASS, wx + 1, wy + 1, 22, 22)
        _rect(s, mix(GLASS, (255, 244, 200), 0.5), wx + 2, wy + 2, 20, 8)
        _rect(s, WOOD_D, wx + 11, wy, 2, 24)
        _rect(s, WOOD_D, wx, wy + 11, 24, 2)
        _rect(s, (168, 122, 74), wx - 6, wy - 2, 4, 28)
        _rect(s, (168, 122, 74), wx + 26, wy - 2, 4, 28)
    if wide:                                   # second window pair
        wx = wall_x + wall_w // 2 + 26
        wy = wall_top + 16
        _rect(s, WOOD_D, wx - 2, wy - 2, 28, 28)
        _rect(s, GLASS, wx, wy, 24, 24)
        _rect(s, WOOD_D, wx + 11, wy, 2, 24)
        _rect(s, WOOD_D, wx, wy + 11, 24, 2)
    return s


_OBJECT_BUILDERS = {
    "oak_big": lambda r: _obj_oak(True, r, 0),
    "oak_big_b": lambda r: _obj_oak(True, r, 1),
    "oak_big_c": lambda r: _obj_oak(True, r, 2),
    "oak_small": lambda r: _obj_oak(False, r, 0),
    "oak_small_b": lambda r: _obj_oak(False, r, 1),
    "pine_big": lambda r: _obj_pine(True, r, 0),
    "pine_big_b": lambda r: _obj_pine(True, r, 1),
    "pine_small": lambda r: _obj_pine(False, r, 0),
    "pine_small_b": lambda r: _obj_pine(False, r, 2),
    "birch": _obj_birch,
    "dead_tree": _obj_dead_tree,
    "bush": lambda r: _obj_bush(r, False),
        "berry_bush": lambda r: _obj_bush(r, True),
        "grass_tuft": _obj_grass_tuft,
        "flower2": _obj_flower2,
        "pebble": _obj_pebble,
        "shell": _obj_shell,
        "reed": _obj_reed,
        "mushroom": _obj_mushroom,
    "rock_big": lambda r: _obj_rock(True, r),
    "rock_small": lambda r: _obj_rock(False, r),
    "stump": _obj_stump,
    "log": _obj_log,
    "fence": lambda r: _obj_fence(r, False),
    "fence_v": lambda r: _obj_fence(r, True),
    "well": _obj_well,
    "barrel": _obj_barrel,
    "crate": _obj_crate,
    "lamp": _obj_lamp,
    "signpost": _obj_signpost,
    "haystack": _obj_haystack,
    "campfire": _obj_campfire,
    "tent": _obj_tent,
    "stall": _obj_stall,
    "pillar": _obj_pillar,
    "ruin": _obj_ruin,
    "cave": _obj_cave,
    "bridge": _obj_bridge,
    "flowerbed": _obj_flowerbed,
    "grave": _obj_grave,
    "shrine": _obj_shrine,
    "tower": _obj_tower,
    "cart": _obj_cart,
    "windmill": _obj_windmill,
    "beehive": _obj_beehive,
    "house_a": lambda r: _obj_house(0, r),
    "house_b": lambda r: _obj_house(1, r),
    "house_c": lambda r: _obj_house(2, r),
    "house_wide": lambda r: _obj_house(0, r, wide=True),
}

# Objects whose art is designed to run into the next tile, so touching the canvas
# edge is correct for them (everything else must fit inside its canvas).
TILING_OBJECTS = {"fence", "fence_v", "bridge", "house_a", "house_b", "house_c",
                  "house_wide", "grave", "pillar", "flowerbed"}

# collision footprint in tiles + how tall the sprite reaches above its tile
OBJECT_META = {
    "oak_big": (1, 1), "oak_big_b": (1, 1), "oak_big_c": (1, 1),
    "oak_small": (1, 1), "oak_small_b": (1, 1),
    "pine_big": (1, 1), "pine_big_b": (1, 1), "pine_small": (1, 1),
    "pine_small_b": (1, 1), "birch": (1, 1), "dead_tree": (1, 1),
    "bush": (1, 1), "berry_bush": (1, 1),
    "grass_tuft": (1, 1), "flower2": (1, 1), "pebble": (1, 1),
    "shell": (1, 1), "reed": (1, 1), "mushroom": (1, 1),
    "rock_big": (1, 1), "rock_small": (1, 1), "stump": (1, 1), "log": (1, 1),
    "fence": (1, 1), "fence_v": (1, 1), "well": (1, 1), "barrel": (1, 1),
    "crate": (1, 1), "lamp": (1, 1), "signpost": (1, 1), "haystack": (1, 1),
    "campfire": (1, 1), "tent": (2, 1), "stall": (2, 1), "pillar": (1, 1),
    "ruin": (2, 1), "cave": (2, 1), "bridge": (1, 1), "flowerbed": (1, 1),
    "shrine": (1, 1), "tower": (2, 1), "cart": (1, 1),
    "windmill": (2, 1), "beehive": (1, 1),
    "grave": (1, 1),
    "house_a": (3, 2), "house_b": (3, 2), "house_c": (3, 2), "house_wide": (4, 2),
}


_objects_cache: dict[str, dict] | None = None


def build_objects() -> dict[str, dict]:
    global _objects_cache
    if _objects_cache is not None:
        return _objects_cache
    objs: dict[str, dict] = {}
    for i, (name, builder) in enumerate(sorted(_OBJECT_BUILDERS.items())):
        surf = builder(random.Random(7000 + i * 137))
        _outline(surf)
        fw, fh = OBJECT_META.get(name, (1, 1))
        objs[name] = {
            "surface": surf,
            "anchor": (surf.get_width() // 2, surf.get_height() - 4),
            "footprint": (fw, fh),
        }
    _objects_cache = objs
    return objs


# ------------------------------------------------------------------ validate
def _border_hits(surf: pygame.Surface) -> dict[str, int]:
    """How many pixels of art sit on each edge of the canvas (0 = nothing clipped)."""
    w, h = surf.get_size()
    out = {"left": 0, "right": 0, "top": 0, "bottom": 0}
    for y in range(h):
        if surf.get_at((0, y))[3] > 0:
            out["left"] += 1
        if surf.get_at((w - 1, y))[3] > 0:
            out["right"] += 1
    for x in range(w):
        if surf.get_at((x, 0))[3] > 0:
            out["top"] += 1
        if surf.get_at((x, h - 1))[3] > 0:
            out["bottom"] += 1
    return out


def validate() -> list[str]:
    problems: list[str] = []
    if not pygame.get_init():
        pygame.init()
    tiles = build_tiles()
    for ttype, frames in tiles.items():
        if not frames:
            problems.append(f"tile {TILE_NAMES.get(ttype, ttype)} has no variants")
            continue
        for i, s in enumerate(frames):
            if s.get_size() != (TILE, TILE):
                problems.append(f"tile {TILE_NAMES.get(ttype, ttype)} #{i} is "
                                f"{s.get_size()}, expected {(TILE, TILE)}")
    objs = build_objects()
    for name, data in objs.items():
        surf = data["surface"]
        w, h = surf.get_size()
        if w < 12 or h < 12:
            problems.append(f"object {name} is too small: {surf.get_size()}")
        if not pygame.mask.from_surface(surf).count():
            problems.append(f"object {name} is fully transparent")
        ax, ay = data["anchor"]
        if not (0 <= ax <= w and 0 <= ay <= h):
            problems.append(f"object {name} anchor {data['anchor']} outside {surf.get_size()}")
        # nothing may be cut off sideways or upwards: a clipped canopy reads as a bug.
        # The bottom edge is where an object meets the ground, so it is allowed;
        # objects that tile into their neighbour are exempt altogether.
        if name not in TILING_OBJECTS:
            hits = _border_hits(surf)
            for side in ("left", "right", "top"):
                if hits[side]:
                    problems.append(f"object {name} is clipped on the {side} "
                                    f"({hits[side]}px of art on the canvas edge)")
    return problems


if __name__ == "__main__":
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))
    issues = validate()
    tiles = build_tiles()
    objs = build_objects()
    print(f"tiles: {len(tiles)} types, {sum(len(v) for v in tiles.values())} variants "
          f"({TILE}x{TILE})")
    print(f"objects: {len(objs)}  sizes: "
          f"{min(o['surface'].get_width() for o in objs.values())}-"
          f"{max(o['surface'].get_width() for o in objs.values())} px wide")
    print("problems:", len(issues))
    for p in issues:
        print("  -", p)
    if os.environ.get("ART_DUMP"):
        out = pygame.Surface((1024, 512))
        out.fill((30, 40, 50))
        x = y = 4
        for ttype, frames in sorted(tiles.items()):
            out.blit(frames[0], (x, y))
            x += TILE + 4
            if x > 900:
                x, y = 4, y + TILE + 4
        for name, data in sorted(objs.items()):
            surf = data["surface"]
            if x + surf.get_width() > 1010:
                x, y = 4, y + 120
            out.blit(surf, (x, y + 110 - surf.get_height()))
            x += surf.get_width() + 6
        pygame.image.save(out, "art_sheet.png")
        print("art sheet written to art_sheet.png")
