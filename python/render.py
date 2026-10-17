#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rendering, UI screens and the main loop for Pixel patch 2.4.

The world layer is drawn on a small logical Surface and scaled by an integer zoom
(nearest neighbour); all text is drawn 1:1 on the real screen so the font stays
sharp.  Terrain tiles and world objects are pre-rendered surfaces (art.py), so a
frame only blits — that is what makes the bigger, more detailed art affordable.

The skill screen draws one great oak: a cached procedurally drawn tree with the
121 skill nodes placed along its five limbs.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Callable

import pygame

import art
import game as G
import items as IT
import lighting
import music as MUS
import quests as QST
import skills as SK
import sprites as SP
import world as W
from art import TILE

UI_BG = (12, 15, 24)
UI_EDGE = (96, 118, 158)
GOLD = (240, 210, 120)
OAK_GREEN = ((58, 122, 60), (74, 142, 68), (96, 164, 78), (124, 186, 92))
OAK_LEAF = ((30, 62, 38), (48, 96, 52), (72, 128, 62), (108, 168, 82))
OAK_BARK = ((46, 32, 22), (84, 58, 37), (118, 84, 54))


def _wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap for panel text (no dependencies on fonts)."""
    lines, cur = [], ""
    for word in text.split():
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _font(size: int) -> pygame.font.Font:
    for name in ("consolas", "couriernew", "dejavusansmono", "liberationmono"):
        try:
            f = pygame.font.SysFont(name, size)
            if f:
                return f
        except Exception:
            continue
    return pygame.font.Font(None, size)


# ----------------------------------------------------------------------------
# The great oak (skill tree backdrop)
#
# It is drawn straight onto the screen from tree coordinates instead of being
# pre-rendered, because the skill screen zooms and pans: a cached bitmap would
# need one copy per zoom step. Every shape is cheap, and the layout follows the
# real node positions from skills.py, so the limbs always point at their branches.
# ----------------------------------------------------------------------------
def _branch_directions() -> dict[str, tuple[float, float, float]]:
    """branch id -> (direction x, direction y, length) measured on the canvas."""
    root = SK.position_of(SK.ROOT)
    out = {}
    for branch in SK.BRANCHES:
        tips = [SK.position_of(s) for s in SK.branch_skills(branch["id"]) if s["tier"] == 8]
        if not tips:
            tips = [SK.position_of(s) for s in SK.branch_skills(branch["id"])]
        mx = sum(t[0] for t in tips) / len(tips)
        my = sum(t[1] for t in tips) / len(tips)
        dx, dy = mx - root[0], my - root[1]
        length = math.hypot(dx, dy) or 1.0
        out[branch["id"]] = (dx / length, dy / length, length)
    return out


# ---------------------------------------------------------------------------
# The oak: a gnarled, leafless world tree that doubles as the skill map.
# Reference layout: trunk in the middle, a wide fractal canopy of bare branches,
# roots below; the skill nodes read as the leaves. Colours stay warm and alive
# (the game is a sunny adventure, not a grimdark one), and each main limb is
# tinted with its branch colour so the five branches are readable at a glance.
# ---------------------------------------------------------------------------
BARK_D = (58, 40, 26)
BARK = (92, 65, 42)
BARK_M = (124, 90, 58)
BARK_L = (158, 118, 78)
BARK_EDGE = (38, 26, 18)


def _mix(a, b, t: float):
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


# ---------------------------------------------------------------------------
# The oak: a gnarled, leafless world tree that doubles as the skill map.
# Reference layout: trunk in the middle, a wide fractal canopy of bare branches,
# roots below; the skill nodes read as the leaves. Colours stay warm and alive
# (the game is a sunny adventure, not a grimdark one), and each main limb is
# tinted with its branch colour so the five branches are readable at a glance.
# ---------------------------------------------------------------------------
BARK_D = (58, 40, 26)
BARK = (92, 65, 42)
BARK_M = (124, 90, 58)
BARK_L = (158, 118, 78)
BARK_EDGE = (38, 26, 18)


def _mix(a, b, t: float):
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def _oak_bezier(p0, p1, p2, t):
    u = 1.0 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])


def _oak_shape(screen, P, pts, widths, tint: float = 0.0, tint_col=None):
    """Draw a limb as ONE tapered polygon (plus a lit strip and a shaded underside).

    Drawing it segment by segment left visible seams and a mismatch at the trunk,
    which read as two sprites glued together; a single silhouette has no seams.
    """
    n = len(pts)
    normals = []
    for i in range(n):
        a = pts[max(0, i - 1)]
        b = pts[min(n - 1, i + 1)]
        nx, ny = -(b[1] - a[1]), (b[0] - a[0])
        ln = math.hypot(nx, ny) or 1.0
        normals.append((nx / ln, ny / ln))
    left = [P((pts[i][0] + normals[i][0] * widths[i],
               pts[i][1] + normals[i][1] * widths[i])) for i in range(n)]
    right = [P((pts[i][0] - normals[i][0] * widths[i],
                pts[i][1] - normals[i][1] * widths[i])) for i in range(n)]
    pygame.draw.polygon(screen, BARK, left + right[::-1])
    # shaded underside (right/lower side)
    pygame.draw.polygon(screen, BARK_D, [
        P((pts[i][0] - normals[i][0] * widths[i],
           pts[i][1] - normals[i][1] * widths[i])) for i in range(n)]
        + [P((pts[i][0] - normals[i][0] * widths[i] * 0.30,
              pts[i][1] - normals[i][1] * widths[i] * 0.30)) for i in reversed(range(n))])
    # lit edge on the upper-left
    lit = _mix(BARK_M, tint_col, tint) if tint_col else BARK_M
    pygame.draw.polygon(screen, lit, [
        P((pts[i][0] + normals[i][0] * widths[i] * 0.97,
           pts[i][1] + normals[i][1] * widths[i] * 0.97)) for i in range(n)]
        + [P((pts[i][0] + normals[i][0] * widths[i] * 0.34,
              pts[i][1] + normals[i][1] * widths[i] * 0.34)) for i in reversed(range(n))])


def _oak_branch(screen, P, p0, ang, length, width, depth, rng,
                tint: float, tint_col, tips: list, unit_px: float):
    """Recursive limb: one smooth tapered shape, then two or three children."""
    dx, dy = math.cos(ang), math.sin(ang)
    p2 = (min(0.985, max(0.015, p0[0] + dx * length)),
          min(0.99, max(0.02, p0[1] + dy * length)))
    bend = rng.uniform(-0.34, 0.34) * length
    p1 = (p0[0] + dx * length * 0.55 - dy * bend,
          p0[1] + dy * length * 0.55 + dx * bend)
    steps = 7
    pts = [_oak_bezier(p0, p1, p2, i / steps) for i in range(steps + 1)]
    widths = [width * (1.0 - 0.68 * (i / steps) ** 0.9) for i in range(steps + 1)]
    _oak_shape(screen, P, pts, widths, tint, tint_col)
    # a rounded elbow at the joint: sharp polygon corners read as glued cardboard
    if depth < 4:
        pygame.draw.circle(screen, BARK, P(p0), max(2, int(width * 0.92 * unit_px)))
        pygame.draw.circle(screen, _mix(BARK_M, tint_col, tint) if tint_col else BARK_M,
                           P(p0), max(1, int(width * 0.55 * unit_px)))
    if depth <= 0:
        tips.append(p2)
        return
    kids = 3 if (depth >= 3 and rng.random() < 0.6) else 2
    base_spread = rng.uniform(0.46, 0.80)
    for k in range(kids):
        spread = (k - (kids - 1) / 2) * base_spread + rng.uniform(-0.12, 0.12)
        _oak_branch(screen, P, p2, ang + spread,
                    length * rng.uniform(0.58, 0.82), width * rng.uniform(0.58, 0.72),
                    depth - 1, rng, tint * 0.9, tint_col, tips, unit_px)


def draw_oak(screen: pygame.Surface, to_screen, unit_px: float) -> None:
    """Draw the oak in tree coordinates; `to_screen` maps (x, y) in 0..1 to pixels.

    Layout follows the reference (trunk, wide bare canopy, roots, nodes as leaves)
    but the palette is warm brown with green tints instead of grey, because the game
    is a bright adventure. Each of the five limbs is tinted with its branch colour,
    which is what makes the five skill branches readable without any labels.
    """
    rng = random.Random(20261017)

    def P(p):
        return to_screen(p)

    bx, by = 0.5, 0.975
    trunk_top = 0.62
    hb, ht = 0.072, 0.028

    # ---- backdrop: warm glow behind the canopy, so the tree sits in light
    glow = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    for i in range(10, 0, -1):
        a = int(8 * (1 - i / 10) ** 1.4)
        if a <= 0:
            continue
        pygame.draw.circle(glow, (96, 128, 84, a), P((0.5, 0.34)),
                           int(unit_px * 0.60 * i / 10))
    screen.blit(glow, (0, 0))

    # ---- ground shadow
    pygame.draw.ellipse(screen, (26, 34, 26),
                        pygame.Rect(int(P((0.20, 0.958))[0]), int(P((0.20, 0.958))[1]),
                                    int(unit_px * 0.60), int(unit_px * 0.05)))

    # ---- roots: smooth curved shapes flowing out of the trunk base
    for sx, spread, drop, w0 in ((-1, 0.23, 0.012, 0.052), (-1, 0.13, 0.030, 0.040),
                                 (1, 0.15, 0.026, 0.042), (1, 0.25, 0.010, 0.050),
                                 (-1, 0.07, 0.040, 0.032), (1, 0.08, 0.038, 0.032)):
        p0 = (bx + sx * hb * 0.5, by - 0.085)
        p2 = (bx + sx * spread, by + drop)
        p1 = (bx + sx * spread * 0.62, by - 0.045)
        pts = [_oak_bezier(p0, p1, p2, i / 6) for i in range(7)]
        widths = [w0 * (1.0 - 0.80 * (i / 6)) for i in range(7)]
        _oak_shape(screen, P, pts, widths)

    # ---- trunk: sampled spine with sway, drawn as one continuous shape
    spine = []
    for i in range(17):
        t = i / 16
        y = by - 0.02 + (trunk_top - by + 0.02) * t
        sway = 0.024 * math.sin(t * 2.4) - 0.010 * t
        w = hb * (1 - t) ** 0.8 + ht * t
        spine.append((bx + sway, y, w))
    _oak_shape(screen, P, [(x, y) for x, y, _w in spine],
               [w for _x, _y, w in spine])
    # bark cracks and knots
    for i in range(40):
        t = rng.random()
        x, y, w = spine[min(16, int(t * 16))]
        gx = x + w * rng.uniform(-0.82, 0.55)
        pygame.draw.line(screen, BARK_D, P((gx, y)),
                         P((gx + rng.uniform(-0.006, 0.006), y + rng.uniform(0.02, 0.06))),
                         max(1, int(unit_px * 0.0035)))
    for ky in (0.90, 0.80, 0.71):
        idx = max(0, min(16, int((by - ky) / (by - trunk_top) * 16)))
        kx, _, kw = spine[idx]
        rect = pygame.Rect(0, 0, max(3, int(kw * 0.6 * unit_px)),
                           max(3, int(kw * 0.5 * unit_px)))
        rect.center = P((kx + kw * 0.05, ky))
        pygame.draw.ellipse(screen, BARK_D, rect)
        pygame.draw.ellipse(screen, BARK_EDGE, rect, 1)

    # ---- main limbs: one per skill branch, tinted with the branch colour
    dirs = _branch_directions()
    tips: list[tuple[float, float]] = []
    for branch in SK.BRANCHES:
        dx, dy, length = dirs[branch["id"]]
        col = tuple(branch["color"])
        ang = math.atan2(dy, dx) + rng.uniform(-0.07, 0.07)
        start = (bx + dx * 0.045, trunk_top - 0.005 + rng.uniform(-0.02, 0.02))
        reach = max(0.10, length - (by - trunk_top) * 0.94) * rng.uniform(0.92, 1.06)
        _oak_branch(screen, P, start, ang, reach, 0.032, 4, rng,
                    0.40, _mix(BARK_M, col, 0.5), tips, unit_px)
    # two filler limbs so the canopy spreads wide instead of leaving bald gaps
    for ang_deg in (-158, -22):
        _oak_branch(screen, P, (bx, trunk_top + 0.06),
                    math.radians(ang_deg), 0.30, 0.022, 3, rng, 0.0, None, tips, unit_px)

    # ---- living touches: moss on the limb ends, grass and mushrooms at the roots
    for (tx, ty) in tips[:80]:
        if ty > 0.55 or abs(tx - 0.5) < 0.06:
            continue
        if rng.random() < 0.30:
            pygame.draw.circle(screen, (86, 132, 66), P((tx, ty)),
                               max(1, int(unit_px * rng.uniform(0.003, 0.007))))
    for i in range(24):
        gx = 0.24 + rng.random() * 0.52
        gy = 0.962 + rng.random() * 0.014
        for k in (-1, 0, 1):
            pygame.draw.line(screen, (58, 96, 54), P((gx, gy)),
                             P((gx + k * 0.006, gy - 0.010 - rng.random() * 0.008)), 1)
    for mx in (0.36, 0.40, 0.605, 0.64):
        my = 0.960 + rng.random() * 0.008
        pygame.draw.rect(screen, (206, 196, 176),
                         pygame.Rect(int(P((mx, my))[0]) - 1, int(P((mx, my))[1]) - 4, 2, 4))
        pygame.draw.ellipse(screen, (176, 66, 56),
                            pygame.Rect(int(P((mx, my))[0]) - 3, int(P((mx, my))[1]) - 6, 6, 4))


def build_oak(w: int, h: int) -> pygame.Surface:
    """Standalone oak bitmap (used by the self-test and the title backdrop)."""
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    draw_oak(surf, lambda p: (int(p[0] * w), int(p[1] * h)), min(w, h))
    return surf


# ----------------------------------------------------------------------------
# Renderer
# ----------------------------------------------------------------------------
class Renderer:
    def __init__(self, game: G.Game, width: int, height: int, zoom: int):
        self.game = game
        self.tiles = art.build_tiles()
        self.objects = art.build_objects()
        self.sprites = SP.build_sprites()
        self.resize(width, height, zoom)
        self.menu_rects: list[tuple[pygame.Rect, int, bool]] = []
        self.inv_rects: list[tuple[pygame.Rect, int]] = []
        self.tree_rects: list[tuple[pygame.Rect, str]] = []
        self.shop_rects: list[tuple[pygame.Rect, int]] = []
        self.minimap = self._build_minimap()
        self.minimap_scaled = pygame.transform.scale(self.minimap, (self.s(200), self.s(102)))
        self.t = 0.0
        self.light = lighting.LightLayer()
        self._text_cache: dict = {}
        self._scaled_cache: dict = {}
        self._marker_font = pygame.font.Font(None, 18)
        self._npc_quest_state: dict[str, tuple[int, int]] = {}
        self._quest_state_frame = -1
        self._light_objects = None
        self._shade_key: tuple[int, int] | None = None
        self._shade = pygame.Surface((1, 1), pygame.SRCALPHA)
        self._panel_cache: dict = {}
        self._glyph_cache: dict = {}
        self._outline_cache: dict = {}
        self._halo_cache: dict = {}
        self._oak_src: pygame.Surface | None = None
        self._oak_cache: dict[int, pygame.Surface] = {}
        self._build_glows()
        # three baked bush variants (they used to be redrawn every frame)
        self._bush_surfs = []
        for i in range(3):
            surf = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            art._canopy(surf, TILE / 2, TILE * 0.52, 11,
                        (art.LEAF_D, art.LEAF, art.LEAF_L, art.LEAF_XL),
                        random.Random(1000 + i * 77), lobes=5)
            self._bush_surfs.append(surf)

    # ------------------------------------------------------------ geometry
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
        self.ui = width / G.BASE_UI_WIDTH
        self.font_tiny = _font(max(10, round(10 * self.ui)))
        self.font_small = _font(max(11, round(12 * self.ui)))
        self.font = _font(max(13, round(15 * self.ui)))
        self.font_big = _font(max(17, round(20 * self.ui)))
        self.font_title = _font(max(26, round(38 * self.ui)))
        if getattr(self, "minimap", None) is not None:
            self.minimap_scaled = pygame.transform.scale(
                self.minimap, (self.s(200), self.s(102)))

    def s(self, v: float) -> int:
        return int(round(v * self.ui))

    def text(self, font, text: str, *args) -> pygame.Surface:
        """Cached font rendering: the HUD asks for the same strings every frame.

        Accepts both ``text(font, s, color)`` and the raw ``render`` signature
        ``text(font, s, True, color)`` so call sites can stay as they were."""
        color = args[-1] if args else (255, 255, 255)
        try:
            col = tuple(color)
        except TypeError:
            col = (255, 255, 255)
        key = (id(font), text, col)
        surf = self._text_cache.get(key)
        if surf is None:
            if len(self._text_cache) > 900:
                self._text_cache.clear()
            surf = font.render(text, True, col)
            self._text_cache[key] = surf
        return surf

    def _build_glows(self) -> None:
        """Pre-render the soft light discs once; per frame only the alpha changes."""
        self._glow_cache = {}
        # Concentric circles banded badly (they read as a flat white disc), so the
        # falloff is a real per-pixel gradient, built once per light kind.
        for kind, (r, col, a) in {"campfire": (44, (255, 168, 84), 92),
                                  "lamp": (34, (255, 214, 138), 70),
                                  "house": (38, (255, 208, 146), 50)}.items():
            size = r * 2
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            for y in range(size):
                dy = y - r + 0.5
                for x in range(size):
                    dx = x - r + 0.5
                    d = math.hypot(dx, dy) / r
                    if d >= 1.0:
                        continue
                    alpha = int(a * (1.0 - d) ** 2.1)
                    if alpha > 0:
                        surf.set_at((x, y), (col[0], col[1], col[2], alpha))
            self._glow_cache[kind] = surf

    def _oak_bitmap(self, unit: float) -> pygame.Surface:
        """Cached, zoom-scaled oak bitmap for the skill screen."""
        key = int(round(unit / 8.0)) * 8
        if self._oak_src is None:
            self._oak_src = build_oak(1400, 1400)
        cached = self._oak_cache.get(key)
        if cached is None:
            if len(self._oak_cache) > 6:
                self._oak_cache.clear()
            cached = pygame.transform.smoothscale(self._oak_src, (key, key))
            self._oak_cache[key] = cached
        return cached

    def _outlined(self, surf: pygame.Surface) -> pygame.Surface:
        """A dark rim around the hero so he never gets lost among the villagers."""
        key = id(surf)
        cached = self._outline_cache.get(key)
        if cached is not None:
            return cached
        pad = 2
        out = pygame.Surface((surf.get_width() + pad * 2, surf.get_height() + pad * 2),
                             pygame.SRCALPHA)
        dark = surf.copy()
        dark.fill((18, 20, 26, 255), special_flags=pygame.BLEND_RGBA_MULT)
        for dx, dy in ((pad, 0), (0, pad), (pad * 2, pad), (pad, pad * 2)):
            out.blit(dark, (dx, dy))
        out.blit(surf, (pad, pad))
        self._outline_cache[key] = out
        return out

    def _glyph(self, icon_name: str, size: int, tone) -> pygame.Surface:
        """A flat pale silhouette of an item icon — the reference's glyph language."""
        key = (icon_name, size, tuple(tone))
        cached = self._glyph_cache.get(key)
        if cached is not None:
            return cached
        icon = pygame.transform.scale(SP.item_icon_surface(icon_name), (size, size))
        icon.fill((255, 255, 255, 255), special_flags=pygame.BLEND_RGB_MAX)   # keep alpha
        icon.fill((*tone, 255), special_flags=pygame.BLEND_RGBA_MULT)
        if len(self._glyph_cache) > 400:
            self._glyph_cache.clear()
        self._glyph_cache[key] = icon
        return icon

    def _bush_surface(self, x: int, y: int) -> pygame.Surface:
        """Bushes used to be drawn disc by disc every single frame; now they are baked."""
        idx = (x * 31 + y * 17) % len(self._bush_surfs)
        return self._bush_surfs[idx]

    def _build_minimap(self) -> pygame.Surface:
        """Pre-render the whole island once; the HUD draws a marker on top."""
        w = W.MAP_W * 2
        h = W.MAP_H * 2
        surf = pygame.Surface((w, h))
        palette = {
            art.T_VOID: (9, 16, 26), art.T_DEEP: (22, 58, 112),
            art.T_WATER: (44, 100, 164), art.T_SHALLOW: (96, 150, 190),
            art.T_SAND: (216, 200, 152), art.T_GRASS: (74, 132, 62),
            art.T_MEADOW: (98, 152, 72), art.T_FOREST: (40, 92, 48),
            art.T_PATH: (156, 130, 96), art.T_DIRT: (110, 86, 60),
            art.T_STONE: (128, 128, 134), art.T_SNOW: (230, 236, 248),
            art.T_MUD: (88, 74, 56), art.T_CROPS: (150, 160, 80),
            art.T_FLOOR: (132, 98, 62), art.T_ROCK: (72, 72, 78),
        }
        for y in range(W.MAP_H):
            for x in range(W.MAP_W):
                col = palette.get(self.game.world.tiles[y][x], (0, 0, 0))
                surf.fill(col, (x * 2, y * 2, 2, 2))
        for o in self.game.world.objects:
            if o["kind"].startswith("house"):
                surf.fill((120, 60, 50), (o["x"] * 2, o["y"] * 2, 6, 4))
        return surf

    # --------------------------------------------------------------- helpers
    def anchor(self, x: float, y: float, cam_x: float, cam_y: float,
               scale: float = 1.0) -> tuple[float, float]:
        """64x64 sprites stand two tiles tall: feet on the tile's bottom edge."""
        h = SP.SPRITE * scale
        return ((x - cam_x + 0.5) * TILE - h / 2, (y - cam_y + 1.0) * TILE - h + 2)

    def to_logical(self, wx: float, wy: float) -> tuple[float, float]:
        return (wx - self.cam_x) * TILE, (wy - self.cam_y) * TILE

    def blit(self, surf: pygame.Surface, pos, scale: float = 1.0) -> None:
        if scale != 1.0:
            key = (id(surf), round(scale, 2))
            cached = self._scaled_cache.get(key)
            if cached is None:
                w = max(1, int(surf.get_width() * scale))
                h = max(1, int(surf.get_height() * scale))
                cached = pygame.transform.scale(surf, (w, h))
                self._scaled_cache[key] = cached
            surf = cached
        self.logical.blit(surf, pos)

    # ------------------------------------------------------------ main frame
    def draw(self, screen: pygame.Surface) -> None:
        g = self.game
        p = g.player
        cam_x = max(0.0, min(W.MAP_W - self.view_w, p["x"] - self.view_w / 2))
        cam_y = max(0.0, min(W.MAP_H - self.view_h, p["y"] - self.view_h / 2))
        if g.shake > 0:
            # a short, decaying nudge on hits (can be switched off in the settings)
            cam_x += math.sin(self.t * 61) * g.shake * 0.7
            cam_y += math.cos(self.t * 47) * g.shake * 0.7
        self.cam_x, self.cam_y = cam_x, cam_y

        self.logical.fill(art.VOID)
        self.draw_tiles(cam_x, cam_y)
        self.draw_decor(cam_x, cam_y)
        self.draw_glows(cam_x, cam_y)
        self.draw_corpses(cam_x, cam_y)
        self.draw_entities(cam_x, cam_y)
        self._apply_light(cam_x, cam_y)

        pygame.transform.scale(self.logical, (self.lw * self.zoom, self.lh * self.zoom),
                               self._scaled)
        screen.fill(art.VOID)
        screen.blit(self._scaled, (self.ox, self.oy))
        self.draw_text_layer(screen)
        if g.overlay != "skilltree":           # the oak screen is a full-screen page
            self.draw_hud(screen)
        if g.overlay == "inventory":
            self.draw_inventory(screen)
        elif g.overlay == "skilltree":
            self.draw_skill_tree(screen)
        elif g.overlay == "shop":
            self.draw_shop(screen)
        elif g.overlay == "quests":
            self.draw_quests(screen)
        if g.dialog and g.overlay is None:
            self.draw_dialog(screen)

    # ------------------------------------------------------------------ свет
    def _light_sources(self):
        """Источники света в мире: один скан при первом кадре, дальше кэш."""
        cached = getattr(self, "_lights", None)
        if cached is not None:
            return cached
        out: list = []
        for o in self.game.world.objects:
            kind = o["kind"]
            if kind == "campfire":
                out.append((o["x"], o["y"], 4.8, (255, 166, 88), 1.7))
            elif kind == "lamp":
                out.append((o["x"], o["y"], 3.4, (255, 214, 150), 1.8))
            elif kind.startswith("house"):
                out.append((o["x"], o["y"] - 0.4, 2.4, (255, 202, 146), 1.5))
        for d in self.game.world.decor:
            if d["kind"] == "campfire":
                out.append((d["x"], d["y"], 4.2, (255, 166, 88), 1.7))
            elif d["kind"] == "lamp":
                out.append((d["x"], d["y"], 3.2, (255, 214, 150), 1.8))
        self._lights = out
        return out

    def _apply_light(self, cam_x: float, cam_y: float) -> None:
        """HD-2D: амбиент по времени суток + свет от костров, окон и героя."""
        g = self.game
        p = g.player
        phase = self.light.forced_phase
        if phase is None:
            phase = (lighting.START_PHASE + g.time / lighting.DAY_LENGTH) % 1.0
        margin = 6.0
        lights = [(x, y, r, col, power) for (x, y, r, col, power) in self._light_sources()
                  if (cam_x - margin < x < cam_x + self.view_w + margin
                      and cam_y - margin < y < cam_y + self.view_h + margin)]
        # герой носит с собой немного света, иначе ночью не видно, куда идти
        lights.append((p["x"], p["y"] - 0.2, 3.2, (176, 186, 226), 1.6))
        self.light.render(self.logical, phase, cam_x, cam_y, lights,
                          enabled=bool(g.settings.get("atmosphere", True)))

    # ----------------------------------------------------------------- tiles
    def draw_tiles(self, cam_x: float, cam_y: float) -> None:
        w = self.game.world
        x0, y0 = int(cam_x), int(cam_y)
        wave = self.game.frame // 14
        for ty in range(y0 - 2, y0 + int(self.view_h) + 3):
            if not (0 <= ty < W.MAP_H):
                continue
            row = w.tiles[ty]
            for tx in range(x0 - 2, x0 + int(self.view_w) + 3):
                if not (0 <= tx < W.MAP_W):
                    continue
                ttype = row[tx]
                frames = self.tiles[ttype]
                idx = (tx * 7 + ty * 13) % len(frames)
                if ttype in art.WATER_TILES:
                    idx = (wave + tx // 3 + ty // 4) % len(frames)
                self.logical.blit(frames[idx], ((tx - cam_x) * TILE, (ty - cam_y) * TILE))

    def draw_decor(self, cam_x: float, cam_y: float) -> None:
        s = self.logical
        for d in self.game.world.decor:
            if not (cam_x - 1.5 < d["x"] < cam_x + self.view_w + 1.5
                    and cam_y - 1.5 < d["y"] < cam_y + self.view_h + 2):
                continue
            px, py = (d["x"] - cam_x) * TILE, (d["y"] - cam_y) * TILE
            kind = d["kind"]
            if kind == "flower":
                col = (244, 240, 220) if (d["x"] + d["y"]) % 2 else (238, 200, 90)
                pygame.draw.circle(s, col, (int(px + 16), int(py + 14)), 3)
                pygame.draw.circle(s, (240, 232, 150), (int(px + 16), int(py + 14)), 1)
                pygame.draw.line(s, (96, 152, 70), (px + 16, py + 16), (px + 16, py + 22), 1)
            elif kind == "bush":
                s.blit(self._bush_surface(d["x"], d["y"]), (int(px), int(py)))
            elif kind in ("lamp", "campfire"):
                data = self.objects.get(kind)
                if data:
                    surf = data["surface"]
                    ax, ay = data["anchor"]
                    s.blit(surf, (px + TILE / 2 - ax, py + TILE - ay))
                self.draw_glow(d, cam_x, cam_y)
            else:
                data = self.objects.get(kind)
                if data:
                    surf = data["surface"]
                    ax, ay = data["anchor"]
                    s.blit(surf, (px + TILE / 2 - ax, py + TILE - ay))

    def draw_corpses(self, cam_x: float, cam_y: float) -> None:
        for c in self.game.corpses:
            alpha = max(0, int(255 * (1 - c["t"] / 1.8)))
            key = f"{c['kind']}_down_0"
            surf = self.sprites.get(key)
            if not surf:
                continue
            spr = surf.copy()
            spr.set_alpha(alpha)
            scale = G.MOBS.get(c["kind"], {}).get("scale", 1.0)
            pos = self.anchor(c["x"], c["y"], cam_x, cam_y, scale)
            if alpha < 200:                     # sink into the ground as it fades
                spr = pygame.transform.rotate(spr, -70 if c["t"] > 0.9 else 0)
            self.blit(spr, pos, scale)

    # -------------------------------------------------------------- entities
    def draw_entities(self, cam_x: float, cam_y: float) -> None:
        g = self.game
        # refresh villager quest markers at most a few times a second, not per NPC/frame
        if g.frame != self._quest_state_frame:
            self._quest_state_frame = g.frame
            self._npc_quest_state = {
                n.get("kind", ""): (len(g.ready_quests(n.get("kind", ""))),
                                    len(g.available_quests(n.get("kind", ""))))
                for n in g.npcs if n.get("kind")}
        items: list[tuple[float, Callable[[], None]]] = []
        for o in g.world.objects:
            if not (cam_x - 4 < o["x"] < cam_x + self.view_w + 4
                    and cam_y - 5 < o["y"] < cam_y + self.view_h + 5):
                continue
            items.append((o["y"] + 0.5, lambda o=o: self.draw_object(o, cam_x, cam_y)))
        for d in g.drops:
            items.append((d["y"], lambda d=d: self.draw_drop(d, cam_x, cam_y)))
        for n in g.npcs:
            items.append((n["y"], lambda n=n: self.draw_npc(n, cam_x, cam_y)))
        for m in g.mobs:
            if m["alive"]:
                items.append((m["y"], lambda m=m: self.draw_mob(m, cam_x, cam_y)))
        for a in g.allies:
            items.append((a["y"], lambda a=a: self.draw_ally(a, cam_x, cam_y)))
        items.append((g.player["y"], lambda: self.draw_player(cam_x, cam_y)))
        for p in g.particles:
            items.append((p["y"] - 0.02, lambda p=p: self.draw_particle(p, cam_x, cam_y)))
        items.sort(key=lambda it: it[0])
        for _y, fn in items:
            fn()

    def draw_object(self, o: dict, cam_x: float, cam_y: float) -> None:
        data = self.objects.get(o["kind"])
        if not data:
            return
        surf = data["surface"]
        ax, ay = data["anchor"]
        px = (o["x"] - cam_x) * TILE + TILE / 2 - ax
        py = (o["y"] - cam_y) * TILE + TILE - ay
        if o["kind"].startswith("house"):
            fw, fh = data["footprint"]
            sh = pygame.Surface((int(fw * TILE * 1.15), int(TILE * 0.6)), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, 120), (0, 0, sh.get_width(), sh.get_height()))
            self.logical.blit(sh, ((o["x"] - cam_x) * TILE + TILE / 2 - sh.get_width() / 2,
                                   (o["y"] - cam_y) * TILE + TILE * 1.25))
        # A tree drawn in front of the hero used to hide him completely. Fade any
        # object whose sprite covers the player and whose base is nearer the camera.
        p = self.game.player
        if o["y"] > p["y"] - 0.55 and surf.get_height() > TILE:
            pax, pay = self.anchor(p["x"], p["y"], cam_x, cam_y)
            prect = pygame.Rect(pax, pay - 24, 64, 88)
            if pygame.Rect(px, py, surf.get_width(), surf.get_height()).colliderect(prect):
                surf = surf.copy()
                surf.set_alpha(140)
        self.logical.blit(surf, (px, py))

    def draw_glows(self, cam_x: float, cam_y: float) -> None:
        """All lamp, fire and window light, drawn ONCE under the entities.

        Light used to be drawn together with its object, which meant a glow could land
        on top of the player and wash the sprite out; light belongs to the ground."""
        if self._light_objects is None:
            # scan the ~3000 world objects once, not every frame
            self._light_objects = [o for o in self.game.world.objects
                                   if o["kind"].startswith("house")
                                   or o["kind"] in ("campfire", "lamp")]
        for o in self._light_objects:
            if not (cam_x - 4 < o["x"] < cam_x + self.view_w + 4
                    and cam_y - 5 < o["y"] < cam_y + self.view_h + 5):
                continue
            self.draw_glow(o, cam_x, cam_y)

    def draw_glow(self, o: dict, cam_x: float, cam_y: float) -> None:
        """Warm light around windows, lamps and fires (added, so it lights the ground)."""
        kind = o["kind"]
        if kind == "campfire":
            key, r = "campfire", 44
        elif kind == "lamp":
            key, r = "lamp", 34
        else:
            key, r = "house", 38
        surf = self._glow_cache.get(key)
        if surf is None:
            return
        pulse = 0.86 + 0.14 * math.sin(self.game.time * 3 + o["x"])
        surf.set_alpha(int(255 * min(1.0, pulse)))
        self.logical.blit(surf, ((o["x"] - cam_x) * TILE + TILE / 2 - r,
                                 (o["y"] - cam_y) * TILE + TILE / 2 - r),
                          special_flags=pygame.BLEND_RGBA_ADD)

    def draw_drop(self, d: dict, cam_x: float, cam_y: float) -> None:
        s = self.logical
        bob = math.sin(self.game.time * 4 + d["x"]) * 2
        px = (d["x"] - cam_x) * TILE
        py = (d["y"] - cam_y) * TILE + bob
        sh = pygame.Surface((14, 6), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 80), (0, 0, 14, 6))
        s.blit(sh, (px + 9, (d["y"] - cam_y) * TILE + 20))
        glow = pygame.Surface((28, 28), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 240, 170, 40), (14, 14), 12)
        s.blit(glow, (px + 2, py + 2))
        icon_id = "gold" if d["kind"] == "gold" else IT.item_icon(d["kind"])
        icon = SP.item_icon_surface(icon_id)
        self.logical.blit(pygame.transform.scale(icon, (20, 20)), (px + 6, py + 6))

    def draw_shadow(self, x: float, y: float, cam_x: float, cam_y: float,
                    w: int = 30) -> None:
        sh = pygame.Surface((w, int(w * 0.34)), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 85), (0, 0, w, int(w * 0.34)))
        self.logical.blit(sh, ((x - cam_x + 0.5) * TILE - w / 2,
                               (y - cam_y + 0.94) * TILE - w * 0.17))

    def draw_player(self, cam_x: float, cam_y: float) -> None:
        g, p = self.game, self.game.player
        view = "side" if p["dir"] in ("left", "right") else p["dir"]
        frame = 1 if (p["moving"] and p["frame"]) else 0
        key = f"hero_{view}_{frame}"
        flip = p["dir"] == "left"
        surf = self.sprites[key + ("_f" if flip else "")]
        surf = self._outlined(surf)
        self.draw_shadow(p["x"], p["y"], cam_x, cam_y, 32)
        # a warm ring so the player is never confused with the villagers
        ring = pygame.Surface((44, 20), pygame.SRCALPHA)
        pygame.draw.ellipse(ring, (255, 226, 140, 90), (0, 0, 44, 20), 2)
        self.logical.blit(ring, ((p["x"] - cam_x + 0.5) * TILE - 22,
                                 (p["y"] - cam_y + 0.86) * TILE - 10))
        ax, ay = self.anchor(p["x"], p["y"], cam_x, cam_y)
        bob = -1 if (p["moving"] and p["frame"]) else 0
        if p["stealth"] > 0:
            surf = surf.copy()
            surf.set_alpha(120)
        self.logical.blit(surf, (ax, ay + bob))
        wid = p["equip"]["weapon"]
        if wid:
            hx = ax + (52 if not flip else 6)
            hy = ay + 40 + bob
            pygame.draw.line(self.logical, (110, 90, 60), (hx, hy), (hx, hy + 14), 3)
            pygame.draw.line(self.logical, (206, 210, 218), (hx, hy), (hx, hy + 12), 2)
        if p["atk_anim"] > 0:
            self.draw_swing(cam_x, cam_y)
        st = self.stats_for_hud()
        if p["hp"] < st["hp_max"]:
            self.draw_bar(p["x"], p["y"] - 0.35, p["hp"] / st["hp_max"], cam_x, cam_y,
                          (92, 214, 108))

    def draw_swing(self, cam_x: float, cam_y: float) -> None:
        p = self.game.player
        t = 1 - p["atk_anim"] / 0.3
        fx, fy = self.game.face_dir()
        ang = math.atan2(fy, fx) - 1.3 + t * 1.9
        cx = (p["x"] - cam_x + 0.5) * TILE
        cy = (p["y"] - cam_y + 0.25) * TILE
        bx, by = math.cos(ang), math.sin(ang)
        pygame.draw.line(self.logical, (198, 200, 212), (cx + bx * 10, cy + by * 10),
                         (cx + bx * 34, cy + by * 34), 4)
        pygame.draw.line(self.logical, (240, 244, 252), (cx + bx * 12, cy + by * 12),
                         (cx + bx * 34, cy + by * 34), 2)
        for i in range(8):
            a = ang - 0.6 + i * 0.19
            pygame.draw.rect(self.logical, (255, 255, 214),
                             (cx + math.cos(a) * 22, cy + math.sin(a) * 22, 3, 3))
        swing = pygame.Surface((90, 90), pygame.SRCALPHA)
        pygame.draw.circle(swing, (255, 255, 220, 40), (45, 45), 36, 4)
        self.logical.blit(swing, (cx - 45, cy - 45))

    def draw_mob(self, m: dict, cam_x: float, cam_y: float) -> None:
        view = "side" if m["dir"] in ("left", "right") else m["dir"]
        if f"{m['kind']}_{view}_0" not in self.sprites:
            view = "down"
        frame = 1 if (m["moving"] and m["frame"]) else 0
        flip = m["dir"] == "left"
        key = f"{m['kind']}_{view}_{frame}" + ("_f" if flip else "")
        surf = self.sprites.get(key) or self.sprites.get(f"{m['kind']}_down_0")
        if not surf:
            return
        scale = m.get("scale", 1.0)
        self.draw_shadow(m["x"], m["y"], cam_x, cam_y, int(26 * scale))
        ax, ay = self.anchor(m["x"], m["y"], cam_x, cam_y, scale)
        lunge = 4 if m["atk_t"] > 0 else 0
        lx = lunge * (-1 if m["dir"] == "left" else 1 if m["dir"] == "right" else 0)
        ly = lunge * (-1 if m["dir"] == "up" else 1 if m["dir"] == "down" else 0)
        if m["hurt_t"] > 0:
            surf = surf.copy()
            surf.fill((255, 120, 120, 0), special_flags=pygame.BLEND_RGBA_ADD)
        if m["slow"] > 0:
            tint = surf.copy()
            tint.fill((90, 150, 255, 0), special_flags=pygame.BLEND_RGBA_ADD)
            surf = tint
        self.blit(surf, (ax + lx, ay + ly), scale)
        if m["hp"] < m["hp_max"]:
            self.draw_bar(m["x"], m["y"] - 0.35, m["hp"] / m["hp_max"], cam_x, cam_y,
                          (226, 84, 72))
        if m["aggro"] and math.hypot(m["x"] - self.game.player["x"],
                                     m["y"] - self.game.player["y"]) < m["aggro"] \
                and not m["passive"]:
            x = (m["x"] - cam_x + 0.5) * TILE
            pygame.draw.rect(self.logical, (255, 90, 60), (x - 2, ay - 10, 4, 8))

    def draw_ally(self, a: dict, cam_x: float, cam_y: float) -> None:
        key = f"wolf_side_{1 if a['frame'] else 0}"
        self.draw_shadow(a["x"], a["y"], cam_x, cam_y, 26)
        ax, ay = self.anchor(a["x"], a["y"], cam_x, cam_y)
        surf = self.sprites.get(key)
        if surf:
            tint = surf.copy()
            tint.fill((120, 160, 255, 0), special_flags=pygame.BLEND_RGBA_ADD)
            self.logical.blit(tint, (ax, ay))
        self.draw_bar(a["x"], a["y"] - 0.3, a["hp"] / a["hp_max"], cam_x, cam_y,
                      (140, 190, 255))

    def draw_npc(self, n: dict, cam_x: float, cam_y: float) -> None:
        view = "side" if n.get("dir") in ("left", "right") else n.get("dir", "down")
        if f"npc_{n['kind']}_{view}_0" not in self.sprites:
            view = "down"
        flip = n.get("dir") == "left"
        key = f"npc_{n['kind']}_{view}_{1 if n['anim_t'] > 0.4 else 0}"
        surf = self.sprites.get(key + ("_f" if flip else ""))
        if not surf:
            return
        self.draw_shadow(n["x"], n["y"], cam_x, cam_y, 30)
        ax, ay = self.anchor(n["x"], n["y"], cam_x, cam_y)
        bob = math.sin(self.game.time * 1.6 + n["x"]) * 1.5
        self.logical.blit(surf, (ax, ay + bob))
        g = self.game
        kind = n.get("kind", "")
        # quest state is refreshed once per frame for all villagers, not per NPC
        state = self._npc_quest_state.get(kind, (0, 0))
        turns, offers = state
        near = math.hypot(n["x"] - g.player["x"], n["y"] - g.player["y"]) < 2.2
        if turns or offers:
            # "!" over a villager with work, "?" when the work is done
            x = (n["x"] - cam_x + 0.5) * TILE
            y = ay - 16 + math.sin(g.time * 3) * 1.5
            mark = "?" if turns else "!"
            col = (150, 240, 150) if turns else (255, 232, 140)
            pygame.draw.circle(self.logical, (16, 20, 30), (int(x), int(y)), 8)
            pygame.draw.circle(self.logical, col, (int(x), int(y)), 8, 2)
            txt = self._marker_font.render(mark, True, col)
            self.logical.blit(txt, (x - txt.get_width() / 2, y - txt.get_height() / 2))
        if near:
            x = (n["x"] - cam_x + 0.5) * TILE
            y = ay - 12 + math.sin(g.time * 4) * 2
            pygame.draw.polygon(self.logical, (255, 240, 150),
                                [(x - 6, y), (x + 6, y), (x, y + 9)])

    def draw_particle(self, p: dict, cam_x: float, cam_y: float) -> None:
        alpha = max(0.0, 1 - p["t"] / p["life"])
        col = pygame.Color(p["color"])
        col.a = int(255 * alpha)
        surf = pygame.Surface((4, 4), pygame.SRCALPHA)
        surf.fill(col)
        self.logical.blit(surf, ((p["x"] - cam_x) * TILE, (p["y"] - cam_y) * TILE))

    def draw_bar(self, x, y, ratio, cam_x, cam_y, color, w=28) -> None:
        s = self.logical
        px = (x - cam_x + 0.5) * TILE - w / 2
        py = (y - cam_y) * TILE
        ratio = max(0.0, min(1.0, ratio))
        pygame.draw.rect(s, (18, 18, 24), (px - 1, py - 1, w + 2, 7))
        pygame.draw.rect(s, (96, 28, 28), (px, py, w, 5))
        pygame.draw.rect(s, color, (px, py, w * ratio, 5))

    def stats_for_hud(self) -> dict:
        return self.game.stats()

    # ------------------------------------------------------------ text layer
    def draw_text_layer(self, screen: pygame.Surface) -> None:
        g = self.game
        for n in g.npcs:
            if not (self.cam_x - 3 < n["x"] < self.cam_x + self.view_w + 3
                    and self.cam_y - 3 < n["y"] < self.cam_y + self.view_h + 3):
                continue
            ax, ay = self.anchor(n["x"], n["y"], self.cam_x, self.cam_y)
            label = self.text(self.font_small, n["name"], True, (248, 248, 254))
            x = (ax + SP.SPRITE / 2) * self.zoom - label.get_width() / 2 + self.ox
            y = ay * self.zoom - label.get_height() - self.s(2) + self.oy
            pad_x, pad_y = self.s(7), self.s(3)
            pill = pygame.Surface((label.get_width() + pad_x * 2,
                                   label.get_height() + pad_y * 2), pygame.SRCALPHA)
            pygame.draw.rect(pill, (12, 14, 22, 190),
                             (0, 0, pill.get_width(), pill.get_height()),
                             border_radius=self.s(7))
            pygame.draw.rect(pill, (206, 192, 140, 110),
                             (0, 0, pill.get_width(), pill.get_height()), 1,
                             border_radius=self.s(7))
            screen.blit(pill, (x - pad_x, y - pad_y))
            screen.blit(label, (x, y))
        for m in g.mobs:
            if not m["alive"] or m["hp"] >= m["hp_max"]:
                continue
            if not (self.cam_x - 3 < m["x"] < self.cam_x + self.view_w + 3
                    and self.cam_y - 3 < m["y"] < self.cam_y + self.view_h + 3):
                continue
            ax, ay = self.anchor(m["x"], m["y"], self.cam_x, self.cam_y,
                                 m.get("scale", 1.0))
            txt = self.text(self.font_small, f"{m['name']}  {max(0, int(m['hp']))}",
                                         True, (255, 190, 190))
            screen.blit(txt, ((ax + SP.SPRITE * m.get("scale", 1.0) / 2) * self.zoom
                              - txt.get_width() / 2 + self.ox,
                              ay * self.zoom - txt.get_height() - self.s(4) + self.oy))
        for f in g.floaters:
            alpha = max(0.0, 1 - f["t"] / f["life"])
            col = pygame.Color(f["color"])
            col.a = int(255 * alpha)
            txt = self.text(self.font, f["text"], True, col)
            lx, ly = self.to_logical(f["x"], f["y"])
            screen.blit(txt, (lx * self.zoom - txt.get_width() / 2 + self.ox,
                              ly * self.zoom - self.s(24) + self.oy))

    # ------------------------------------------------------------------- HUD
    def panel(self, screen, rect, fill=(11, 13, 21, 243), border=UI_EDGE, radius=0) -> None:
        """One panel style for the whole UI: opaque card, drop shadow, inner highlight.

        The composite is cached per size and colour — rebuilding the shadow surface
        every frame cost about 3 ms of the 60 fps budget on its own.
        """
        x, y, w, h = rect
        key = (w, h, tuple(fill), tuple(border) if not isinstance(border, str) else border,
               radius)
        surf = self._panel_cache.get(key)
        if surf is None:
            surf = pygame.Surface((w + 8, h + 8), pygame.SRCALPHA)
            for i, a in ((0, 26), (3, 20), (6, 12)):
                pygame.draw.rect(surf, (0, 0, 0, a), (i + 4, i + 4, w + 8 - i * 2, h + 8 - i * 2),
                                 border_radius=radius + 2 if radius else 0)
            body = pygame.Surface((w, h), pygame.SRCALPHA)
            if radius:
                pygame.draw.rect(body, fill, (0, 0, w, h), border_radius=radius)
                pygame.draw.rect(body, border, (0, 0, w, h), 1, border_radius=radius)
                pygame.draw.rect(body, (255, 255, 255, 16), (1, 1, w - 2, h - 2), 1,
                                 border_radius=max(0, radius - 1))
            else:
                body.fill(fill)
                pygame.draw.rect(body, border, (0, 0, w, h), 1)
                pygame.draw.line(body, (255, 255, 255, 18), (0, 0), (w, 0))
            surf.blit(body, (4, 4))
            if len(self._panel_cache) > 40:
                self._panel_cache.clear()
            self._panel_cache[key] = surf
        screen.blit(surf, (x - 4, y - 4))

    def draw_hud(self, screen) -> None:
        g, p, S = self.game, self.game.player, self.s
        st = g.stats()
        w = S(340)
        self.panel(screen, (S(10), S(10), w, S(104)), radius=S(6))
        screen.blit(self.text(self.font_big, "Pixel patch 2.4", True,
                                         (250, 246, 226)), (S(20), S(14)))
        screen.blit(self.text(self.font_small, 
            f"Ур. {p['level']}    Опыт {p['xp']}/{p['xp_next']}    Очки навыков: {g.skill_points}",
            True, (186, 206, 236)), (S(20), S(38)))
        # hp
        pygame.draw.rect(screen, (28, 28, 36), (S(20), S(58), S(210), S(11)))
        pygame.draw.rect(screen, (150, 40, 40), (S(20), S(58), S(210), S(11)))
        pygame.draw.rect(screen, (92, 214, 108),
                         (S(20), S(58), S(210) * max(0.0, p["hp"] / st["hp_max"]), S(11)))
        screen.blit(self.text(self.font_small, 
            f"{max(0, math.ceil(p['hp']))}/{int(st['hp_max'])}", True, (255, 255, 255)),
            (S(236), S(56)))
        # mana
        pygame.draw.rect(screen, (28, 28, 36), (S(20), S(73), S(210), S(9)))
        pygame.draw.rect(screen, (60, 120, 220),
                         (S(20), S(73), S(210) * max(0.0, p["mp"] / st["mp_max"]), S(9)))
        screen.blit(self.text(self.font_small, 
            f"{int(p['mp'])}/{int(st['mp_max'])} MP", True, (200, 220, 255)), (S(236), S(70)))
        screen.blit(self.text(self.font_small, f"Золото: {p['gold']}", True, GOLD),
                    (S(20), S(88)))
        screen.blit(self.text(self.font_small, 
            f"Атака {int(st['atk'])}   Защита {int(st['def'])}   Крит {st['crit_chance']:.0f}%",
            True, (232, 200, 170)), (S(120), S(88)))

        # время суток: без индикатора игрок не понимает, почему темнеет
        if g.settings.get("atmosphere", True):
            ph = self.light.forced_phase
            if ph is None:
                ph = (lighting.START_PHASE + g.time / lighting.DAY_LENGTH) % 1.0
            bw, bh = S(158), S(40)
            bx, by = self.width - bw - S(12), S(10)
            self.panel(screen, (bx, by, bw, bh), radius=S(6))
            cx, cy, rr = bx + S(22), by + bh // 2, S(9)
            if lighting.darkness(ph) < 0.42:
                pygame.draw.circle(screen, (255, 212, 104), (cx, cy), rr)
                pygame.draw.circle(screen, (255, 244, 196), (cx - S(2), cy - S(2)),
                                   max(1, S(3)))
            else:
                pygame.draw.circle(screen, (216, 228, 255), (cx, cy), rr)
                pygame.draw.circle(screen, (140, 156, 196), (cx + S(3), cy - S(3)),
                                   max(2, S(6)))
                pygame.draw.circle(screen, (12, 14, 22), (cx + S(7), cy - S(6)),
                                   max(2, S(6)))
            screen.blit(self.text(self.font_small, lighting.phase_name(ph), True,
                                  (232, 240, 252)), (bx + S(42), by + S(3)))
            hours = ph * 24.0
            screen.blit(self.text(self.font_tiny, f"{int(hours):02d}:{int(hours % 1 * 60):02d}",
                                  True, (150, 168, 190)), (bx + S(42), by + S(22)))

        # minimap + region, in their own panel so nothing overlaps
        show_minimap = g.settings.get("minimap", True)
        if show_minimap:
            mm_panel = (S(10), S(120), S(364), S(150))
            self.panel(screen, mm_panel, radius=S(6))
            screen.blit(self.minimap_scaled, (S(20), S(130)))
            pygame.draw.rect(screen, UI_EDGE, (S(20), S(130), S(200), S(102)), 1)
            mx = S(20) + int(p["x"] / W.MAP_W * S(200))
            my = S(130) + int(p["y"] / W.MAP_H * S(102))
            pygame.draw.circle(screen, (255, 255, 255), (mx, my), S(3))
            pygame.draw.circle(screen, (255, 90, 90), (mx, my), S(3), 1)
        region = g.region_at(p["x"], p["y"])
        info_x = S(232) if show_minimap else S(20)
        info_y = S(130) if show_minimap else S(120)
        if not show_minimap:
            self.panel(screen, (S(10), S(120), S(364), S(120)), radius=S(6))
        screen.blit(self.text(self.font_big, region["name"] if region else "—", True,
                                         (232, 240, 252)), (info_x, info_y))
        info_y += S(26)
        lines = [f"Исследовано: {len(g.visited)}/{len(g.world.regions)}",
                 f"Убито: {sum(g.kills.values())}   Смертей: {g.deaths}"]
        track = g.music_track if g.music_on else None
        lines.append("♪ " + (MUS.TRACKS.get(track, {}).get("title", track) if track
                             else "выкл (M)"))
        buffs = ", ".join(f"{k} {int(v['t'])}с" for k, v in p["buffs"].items())
        if buffs:
            lines.append("Эффекты: " + buffs)
        for i, text in enumerate(lines):
            screen.blit(self.text(self.font_small, text, True, (176, 194, 218)),
                        (info_x, info_y + i * S(18)))
        screen.blit(self.text(self.font_tiny, "N — другая мелодия", True, (140, 152, 170)),
                    (info_x, S(252)))

        # active quest tracker in its own panel under the minimap
        active = [q for q in g.quests if not q["done"]][:3]
        rows = max(1, len(active))
        tr_y = S(278) if show_minimap else S(248)
        tr_panel = (S(10), tr_y, S(364), S(28) + rows * S(22))
        self.panel(screen, tr_panel, radius=S(6))
        ready = sum(1 for q in g.quests if q.get("ready"))
        head = "Задания" + (f"   •   готово к сдаче: {ready}" if ready else "")
        screen.blit(self.text(self.font, head, True, (150, 240, 150) if ready else (236, 240, 248)),
                    (S(20), tr_y + S(6)))
        qy = tr_y + S(32)
        if not active:
            screen.blit(self.text(self.font_small, "нет заданий — поговори с жителями",
                                               True, (168, 180, 198)), (S(20), qy))
        for q in active:
            col = (150, 240, 150) if q.get("ready") else (222, 232, 246)
            mark = "★" if q.get("ready") else "•"
            screen.blit(self.text(self.font_small, f"{mark} {q['title']}", True, col),
                        (S(20), qy))
            screen.blit(self.text(self.font_small, f"{q['progress']}/{q['goal']}", True,
                                               (170, 200, 236)),
                        (S(340) - self.font_small.size(f"{q['progress']}/{q['goal']}")[0], qy))
            qy += S(22)

        # hints (the bottom legend can be switched off in the settings)
        if g.settings.get("hints", True):
            # the legend used to be bare text over the ground: now it sits on a card
            legend = ("WASD — движение     ПРОБЕЛ — атака     1–9 — умения     E — говорить/собрать"
                      "     I — сумка     K — дуб     Q — задания     H — зелье     F10 — меню")
            txt = self.text(self.font_small, legend, True, (206, 218, 240))
            pad = S(10)
            lw, lh = txt.get_width() + pad * 2, txt.get_height() + S(8)
            self.panel(screen, (S(10), self.height - lh - S(6), lw, lh), radius=S(5))
            screen.blit(txt, (S(10) + pad, self.height - lh - S(6) + S(4)))

        # what is within reach right now
        hint = ""
        node = g.nearest_node()
        if node:
            kind = node["kind"]
            verb = {"tree": "E — срубить дерево", "stump": "E — взять пень",
                    "bush": "E — собрать кусты", "berry_bush": "E — собрать ягоды",
                    "flower": "E — сорвать цветок", "rock_small": "E — добыть камень"}
            hint = verb.get(kind, "E — собрать")
        elif g.nearest_npc():
            n = g.nearest_npc()
            offers = g.available_quests(n.get("kind", ""))
            turns = g.ready_quests(n.get("kind", ""))
            if turns:
                hint = f"E — сдать задание {n['name']}"
            elif offers:
                hint = f"E — поговорить: {n['name']} (есть дело)"
            else:
                hint = f"E — поговорить: {n['name']}"
        if hint and g.settings.get("hints", True):
            txt = self.text(self.font, hint, True, (255, 244, 200))
            bx = self.width // 2 - txt.get_width() // 2
            by = self.height - S(150)
            bg = pygame.Surface((txt.get_width() + S(28), txt.get_height() + S(12)),
                                pygame.SRCALPHA)
            bg.fill((10, 12, 20, 200))
            screen.blit(bg, (bx - S(14), by - S(6)))
            pygame.draw.rect(screen, (226, 202, 132),
                             (bx - S(14), by - S(6), bg.get_width(), bg.get_height()), 1)
            screen.blit(txt, (bx, by))

        # hotbar
        hb_y = self.height - S(96)
        hotbar = p["hotbar"]
        for i in range(G.HOTBAR_KEYS):
            x = self.width // 2 - S(G.HOTBAR_KEYS * 62) // 2 + i * S(62)
            rect = pygame.Rect(x, hb_y, S(56), S(56))
            ready = i < len(hotbar)
            pygame.draw.rect(screen, (26, 31, 44) if ready else (20, 23, 33), rect,
                             border_radius=S(6))
            pygame.draw.rect(screen, (250, 220, 130) if ready else (74, 82, 102), rect, 2,
                             border_radius=S(6))
            cap = pygame.Rect(x + S(4), hb_y + S(38), S(16), S(15))
            pygame.draw.rect(screen, (34, 40, 56) if ready else (24, 28, 40), cap,
                             border_radius=S(3))
            pygame.draw.rect(screen, (250, 220, 130) if ready else (66, 74, 94), cap, 1,
                             border_radius=S(3))
            key = self.text(self.font_small, str(i + 1), True,
                                         (240, 244, 255) if ready else (140, 148, 168))
            screen.blit(key, (cap.centerx - key.get_width() // 2,
                              cap.centery - key.get_height() // 2))
            if ready:
                ab = G.ABILITIES[hotbar[i]]
                icon = SP.item_icon_surface(SK._ABILITY_ICON.get(hotbar[i], "scroll"))
                screen.blit(pygame.transform.scale(icon, (S(34), S(34))),
                            (x + S(11), hb_y + S(6)))
                cd = p["cooldowns"].get(hotbar[i], 0.0)
                if cd > 0:
                    overlay = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
                    overlay.fill((10, 12, 20, 170))
                    screen.blit(overlay, (x, hb_y))
                    txt = self.text(self.font_small, f"{cd:.1f}", True, (255, 240, 200))
                    screen.blit(txt, (x + S(28) - txt.get_width() / 2, hb_y + S(20)))
                if p["mp"] < ab["mana"]:
                    screen.blit(self.text(self.font_small, str(ab["mana"]), True, (120, 160, 255)),
                                (x + S(38), hb_y + S(38)))
            else:
                # an empty slot should look empty, not like a missing texture
                pygame.draw.circle(screen, (46, 52, 68), (x + S(28), hb_y + S(26)), S(4))
                if i == 0:
                    hint = self.text(self.font_tiny, "активные умения — на дубе (K)", True,
                                                 (146, 154, 172))
                    screen.blit(hint, (x + S(28) - hint.get_width() // 2, hb_y - S(34)))

        # toasts
        ty = self.height - S(150)
        for t in reversed(g.toasts[-4:]):
            a = (t["t"] / 0.2 if t["t"] < 0.2
                 else (t["life"] - t["t"]) / 0.6 if t["t"] > t["life"] - 0.6 else 1)
            surf = pygame.Surface((S(520), S(26)), pygame.SRCALPHA)
            pygame.draw.rect(surf, (10, 12, 18, int(210 * a)), (0, 0, S(520), S(26)),
                             border_radius=S(4))
            screen.blit(surf, (S(10), ty))
            txt = self.text(self.font_small, t["text"], True, pygame.Color(t["color"]))
            txt.set_alpha(int(255 * a))
            screen.blit(txt, (S(20), ty + S(7)))
            ty -= S(30)


    # ------------------------------------------------------------- inventory
    def draw_inventory(self, screen) -> None:
        g, S = self.game, self.s
        cols, rows = 6, 4
        cell = S(78)
        pad = S(12)
        w = pad * 2 + cols * (cell + pad) + S(300)
        h = pad * 2 + rows * (cell + pad) + S(46)
        x = (self.width - w) // 2
        y = (self.height - h) // 2
        self.panel(screen, (x, y, w, h), fill=(12, 15, 24, 246), border=(150, 172, 210),
                   radius=S(8))
        screen.blit(self.text(self.font_big, "Сумка", True, (250, 240, 210)), (x + pad, y + pad))
        screen.blit(self.text(self.font_small, 
            f"{len(g.player['inventory'])}/{G.INV_SLOTS} слотов   •   стрелки — выбор   •   "
            "E / Enter — использовать или надеть   •   ПРОБЕЛ — выбросить   •   I — закрыть",
            True, (186, 202, 226)), (x + pad + S(110), y + pad + S(10)))

        grid_x, grid_y = x + pad, y + pad + S(42)
        mouse = pygame.mouse.get_pos()
        hover = None
        self.inv_rects = []
        inv = g.player["inventory"]
        for i in range(G.INV_SLOTS):
            cx = grid_x + (i % cols) * (cell + pad)
            cy = grid_y + (i // cols) * (cell + pad)
            rect = pygame.Rect(cx, cy, cell, cell)
            self.inv_rects.append((rect, i))
            if rect.collidepoint(mouse):
                hover = i
            sel = (i == g.inv_cursor)
            pygame.draw.rect(screen, (34, 42, 60) if sel else (20, 25, 36), rect,
                             border_radius=S(6))
            pygame.draw.rect(screen, (250, 220, 130) if sel else (62, 74, 98), rect, 2,
                             border_radius=S(6))
            if i < len(inv):
                slot = inv[i]
                icon = SP.item_icon_surface(IT.item_icon(slot["id"]))
                screen.blit(pygame.transform.scale(icon, (S(52), S(52))),
                            (cx + (cell - S(52)) / 2, cy + S(8)))
                if slot["count"] > 1:
                    cnt = self.text(self.font_small, str(slot["count"]), True, (255, 255, 255))
                    bw, bh = cnt.get_width() + S(10), cnt.get_height() + S(4)
                    badge = pygame.Surface((bw, bh), pygame.SRCALPHA)
                    pygame.draw.rect(badge, (12, 14, 22, 220), (0, 0, bw, bh),
                                     border_radius=S(4))
                    screen.blit(badge, (cx + cell - bw - S(4), cy + cell - bh - S(4)))
                    screen.blit(cnt, (cx + cell - bw + S(3), cy + cell - bh - S(2)))
                equipped = slot["id"] in g.player["equip"].values()
                if equipped:
                    bx, by = cx + S(5), cy + S(5)
                    pygame.draw.rect(screen, (26, 40, 26), (bx, by, S(20), S(20)))
                    pygame.draw.rect(screen, (128, 226, 128), (bx, by, S(20), S(20)), 1)
                    pygame.draw.lines(screen, (150, 240, 150), False,
                                      [(bx + S(4), by + S(10)), (bx + S(8), by + S(15)),
                                       (bx + S(16), by + S(5))], 2)

        px = grid_x + cols * (cell + pad) + pad
        py = grid_y
        cursor = hover if hover is not None else g.inv_cursor
        self.panel(screen, (px, py, S(286), S(196)), fill=(16, 20, 30, 236),
                   border=(90, 108, 142), radius=S(6))
        if 0 <= cursor < len(inv):
            item_id = inv[cursor]["id"]
            data = IT.ITEMS[item_id]
            icon = SP.item_icon_surface(data["icon"])
            screen.blit(pygame.transform.scale(icon, (S(40), S(40))), (px + S(10), py + S(10)))
            screen.blit(self.text(self.font, data["name"], True, (252, 244, 216)),
                        (px + S(58), py + S(12)))
            screen.blit(self.text(self.font_small, data["desc"], True, (182, 198, 222)),
                        (px + S(58), py + S(36)))
            stats = []
            if data.get("atk"):
                stats.append(f"Атака +{data['atk']}")
            if data.get("def"):
                stats.append(f"Защита +{data['def']}")
            if data.get("hp"):
                stats.append(f"Здоровье +{data['hp']}")
            if data.get("mp"):
                stats.append(f"Мана +{data['mp']}")
            if data.get("heal"):
                stats.append(f"Лечит {data['heal']} HP")
            if data.get("crit"):
                stats.append(f"Крит +{data['crit']}%")
            stats.append(f"Цена {data['value']}   продажа {IT.sell_price(item_id)}")
            for i, line in enumerate(stats):
                screen.blit(self.text(self.font_small, line, True, (232, 214, 160)),
                            (px + S(12), py + S(62 + i * 18)))
            hint = {"consumable": "E — использовать", "weapon": "E — взять в руку",
                    "armor": "E — надеть", "ring": "E — надеть кольцо"}.get(
                        data["kind"], "Материал: продай торговцу")
            screen.blit(self.text(self.font_small, hint, True, (140, 200, 255)),
                        (px + S(12), py + S(168)))
        else:
            screen.blit(self.text(self.font_small, "Пустой слот", True, (140, 152, 176)),
                        (px + S(12), py + S(10)))

        eq_y = py + S(208)
        self.panel(screen, (px, eq_y, S(286), S(140)), fill=(16, 20, 30, 236),
                   border=(90, 108, 142), radius=S(6))
        screen.blit(self.text(self.font, "Экипировка", True, (252, 244, 216)), (px + S(12), eq_y + S(8)))
        for i, (key, label) in enumerate((("weapon", "Оружие"), ("armor", "Броня"),
                                          ("ring", "Кольцо"), ("amulet", "Амулет"))):
            item_id = g.player["equip"].get(key)
            name = IT.item_name(item_id) if item_id else "—"
            screen.blit(self.text(self.font_small, f"{label}: {name}", True, (206, 220, 240)),
                        (px + S(12), eq_y + S(32 + i * 20)))
        st = g.stats()
        screen.blit(self.text(self.font_small, 
            f"Итого: атака {int(st['atk'])}, защита {int(st['def'])}, HP {int(st['hp_max'])}, "
            f"MP {int(st['mp_max'])}", True, (240, 210, 140)), (px + S(12), eq_y + S(116)))

    # ------------------------------------------------------------------ shop
    def draw_shop(self, screen) -> None:
        g, S = self.game, self.s
        w, h = S(880), S(560)
        x = (self.width - w) // 2
        y = (self.height - h) // 2
        self.panel(screen, (x, y, w, h), fill=(14, 17, 26, 248), border=(200, 176, 120),
                   radius=S(8))
        screen.blit(self.text(self.font_big, "Торговец", True, (252, 240, 200)),
                    (x + S(18), y + S(14)))
        screen.blit(self.text(self.font_small, 
            f"Золото: {g.player['gold']}   •   TAB — продать/купить   •   стрелки — выбор   •   "
            "E / Enter — сделка   •   R — продать все материалы   •   ESC — выйти",
            True, (196, 212, 236)), (x + S(18), y + S(44)))
        for i, (tab, label) in enumerate((("sell", "Продать"), ("buy", "Купить"))):
            rect = pygame.Rect(x + S(18) + i * S(130), y + S(72), S(120), S(32))
            active = g.shop_tab == tab
            pygame.draw.rect(screen, (44, 36, 20) if active else (22, 26, 38), rect)
            pygame.draw.rect(screen, (248, 226, 152) if active else (90, 100, 124), rect, 2)
            screen.blit(self.text(self.font, label, True,
                                         (255, 236, 158) if active else (206, 216, 232)),
                        (rect[0] + S(24), rect[1] + S(6)))

        lines = g.shop_lines()
        g.shop_cursor = max(0, min(g.shop_cursor, max(0, len(lines) - 1)))
        list_y = y + S(116)
        self.shop_rects = []
        mouse = pygame.mouse.get_pos()
        for i, (item_id, price, count) in enumerate(lines[:12]):
            rect = pygame.Rect(x + S(18), list_y + i * S(34), w - S(36), S(30))
            self.shop_rects.append((rect, i))
            sel = i == g.shop_cursor
            if rect.collidepoint(mouse):
                sel = True
            if sel:
                pygame.draw.rect(screen, (34, 28, 16), rect)
                pygame.draw.rect(screen, (248, 226, 152), rect, 2)
            data = IT.ITEMS[item_id]
            icon = SP.item_icon_surface(data["icon"])
            screen.blit(pygame.transform.scale(icon, (S(24), S(24))), (rect[0] + S(6), rect[1] + S(3)))
            screen.blit(self.text(self.font_small, data["name"], True,
                                               (255, 236, 158) if sel else (216, 226, 240)),
                        (rect[0] + S(38), rect[1] + S(7)))
            screen.blit(self.text(self.font_small, f"x{count}", True, (170, 190, 216)),
                        (rect[0] + S(360), rect[1] + S(7)))
            price_col = (240, 210, 120) if (g.shop_tab == "sell" or
                                            g.player["gold"] >= price) else (220, 120, 120)
            screen.blit(self.text(self.font_small, 
                ("+" if g.shop_tab == "sell" else "−") + f"{price} золота", True, price_col),
                (rect[0] + S(470), rect[1] + S(7)))
            screen.blit(self.text(self.font_small, data["desc"][:52], True, (166, 182, 206)),
                        (rect[0] + S(620), rect[1] + S(7)))
        if not lines:
            screen.blit(self.text(self.font, 
                "Нечего продавать — принеси трофеи с монстров" if g.shop_tab == "sell"
                else "Товар закончился", True, (200, 180, 160)),
                (x + S(24), list_y + S(20)))
        elif len(lines) > 12:
            screen.blit(self.text(self.font_small, f"… и ещё {len(lines) - 12} позиций",
                                               True, (170, 186, 210)),
                        (x + S(24), list_y + S(12 * 34) + S(4)))
        screen.blit(self.text(self.font_small, 
            "Торговец платит 45% цены и берёт 160% за свой товар.", True, (176, 192, 216)),
            (x + S(18), y + h - S(28)))

    # ------------------------------------------------------------- quest log
    def draw_quests(self, screen) -> None:
        g, S = self.game, self.s
        active = [q for q in g.quests]
        rows = max(1, len(active))
        h = S(96 + min(rows, 9) * 54)
        x, y = S(300), S(60)
        w = S(880)
        self.panel(screen, (x, y, w, h), fill=(12, 15, 24, 244), border=(140, 170, 220),
                   radius=S(8))
        screen.blit(self.text(self.font_big, "Журнал заданий", True, (255, 255, 255)),
                    (x + S(18), y + S(14)))
        done = len(g.quest_done)
        screen.blit(self.text(self.font_small, 
            f"выполнено {done} из {len(QST.QUESTS)}   •   взято {len(active)}",
            True, (196, 210, 232)), (x + S(240), y + S(24)))
        screen.blit(self.text(self.font_small, "Q — закрыть   •   брать задания у жителей (E)",
                                           True, (170, 186, 210)),
                    (x + w - S(330), y + S(24)))
        yy = y + S(60)
        if not active:
            screen.blit(self.text(self.font, 
                "Пока заданий нет. Поговори с жителями деревни: у каждого есть дела.",
                True, (206, 216, 234)), (x + S(20), yy + S(10)))
        for q in active[:9]:
            ready = q.get("ready")
            col = (150, 240, 150) if ready else (232, 232, 242)
            mark = "★" if ready else "•"
            screen.blit(self.text(self.font, f"{mark} {q['title']}", True, col),
                        (x + S(18), yy))
            screen.blit(self.text(self.font_small, q["desc"], True, (176, 192, 216)),
                        (x + S(32), yy + S(24)))
            giver = next((k for k, ids in QST.GIVERS.items() if q["id"] in ids), "")
            who = G.GIVER_NAMES.get(giver, "").rstrip("у") if giver else ""
            reward = f"+{q['xp']} опыта, +{q['gold']} золота"
            if q.get("reward") and IT.ITEMS.get(q["reward"]):
                reward += ", " + IT.ITEMS[q["reward"]]["name"]
            screen.blit(self.text(self.font_tiny, f"Награда: {reward}" +
                                              (f"   •   заказчик: {who}" if who else ""),
                                              True, (150, 200, 160)),
                        (x + S(32), yy + S(40)))
            frac = q["progress"] / max(1, q["goal"])
            bar = pygame.Rect(int(x + w - S(240)), int(yy + S(10)), S(200), S(12))
            pygame.draw.rect(screen, (30, 34, 46), bar)
            if q["progress"]:
                pygame.draw.rect(screen, (120, 200, 130) if ready else (96, 150, 210),
                                 (bar.x, bar.y, max(2, int(bar.width * frac)), bar.height))
            pygame.draw.rect(screen, (66, 72, 88), bar, 1)
            screen.blit(self.text(self.font_small, f"{q['progress']}/{q['goal']}", True,
                                               (206, 226, 246)),
                        (bar.x + bar.width + S(10), yy + S(8)))
            if ready:
                screen.blit(self.text(self.font_tiny, "готово — сдай заказчику", True,
                                                  (150, 240, 150)),
                            (bar.x, yy + S(28)))
            yy += S(56)
        if len(active) > 9:
            screen.blit(self.text(self.font_small, f"… и ещё {len(active) - 9} заданий",
                                               True, (170, 186, 210)), (x + S(20), yy))

    # --------------------------------------------------------- the oak screen
    def draw_skill_tree(self, screen) -> None:
        g, S = self.game, self.s
        screen.fill((10, 13, 20))
        area_x, area_y = S(18), S(50)
        area_w = self.width - S(18) * 2 - S(348)
        area_h = self.height - S(50) - S(34)
        pygame.draw.rect(screen, (16, 20, 28), (area_x, area_y, area_w, area_h))
        pygame.draw.rect(screen, (150, 128, 78), (area_x, area_y, area_w, area_h), 2)

        # ---- camera: centred on the selected node, clamped so the oak stays framed ----
        learned = g.player["learned"]
        node = SK.by_id(g.tree_cursor) or SK.ROOT
        tx, ty = SK.position_of(node)

        zoom = g.tree_zoom
        unit = min(area_w, area_h) * zoom           # pixels per tree unit
        cx0 = area_x + area_w * 0.5
        cy0 = area_y + area_h * 0.5
        half_w = (area_w * 0.5) / unit
        half_h = (area_h * 0.5) / unit
        cam = g.tree_cam
        want_x = 0.5 if half_w >= 0.5 else max(half_w, min(1.0 - half_w, tx))
        want_y = 0.5 if half_h >= 0.5 else max(half_h, min(1.0 - half_h, ty))
        cam[0] += (want_x - cam[0]) * 0.22
        cam[1] += (want_y - cam[1]) * 0.22

        def to_screen(p):
            return (int(cx0 + (p[0] - cam[0]) * unit), int(cy0 + (p[1] - cam[1]) * unit))

        clip = screen.get_clip()
        screen.set_clip(pygame.Rect(area_x + 2, area_y + 2, area_w - 4, area_h - 4))
        # The oak is expensive to draw (thousands of leaves), so it is rendered once
        # into a bitmap and re-scaled only when the zoom changes: panning is one blit.
        oak = self._oak_bitmap(unit)
        screen.blit(oak, (int(cx0 - cam[0] * unit), int(cy0 - cam[1] * unit)))
        # dim it behind the nodes so the tree never fights the UI for attention
        if self._shade_key != (area_w, area_h):
            self._shade_key = (area_w, area_h)
            shade = pygame.Surface((area_w, area_h), pygame.SRCALPHA)
            shade.fill((7, 10, 16, 84))
            for i in range(7):                  # vignette towards the edges
                inset = i * 16
                pygame.draw.rect(shade, (6, 9, 14, 22),
                                 (inset, inset // 2, area_w - inset * 2, area_h - inset),
                                 16, border_radius=18)
            self._shade = shade
        screen.blit(self._shade, (area_x, area_y))

        # ---- requirement links ----
        for skill in SK.SKILLS:
            nx, ny = SK.position_of(skill)
            ax, ay = to_screen((nx, ny))
            for i, req in enumerate(skill["req"]):
                parent = SK.by_id(req)
                if not parent:
                    continue
                px_, py_ = SK.position_of(parent)
                bx_, by_ = to_screen((px_, py_))
                both = req in learned and skill["id"] in learned
                dim = node["branch"] != skill["branch"] and skill["branch"] != "root"
                primary = (i == 0)
                if both:
                    col = (240, 210, 120) if primary else (176, 152, 92)
                else:
                    col = (116, 108, 94) if primary else (74, 70, 64)
                if dim:
                    col = tuple(int(c * 0.62) for c in col)
                w = unit * (0.0065 if both and primary else 0.0045 if primary else 0.0028)
                pygame.draw.line(screen, col, (bx_, by_), (ax, ay), max(2, int(w)))

        # ---- nodes ----
        # Reference language: dark plate, branch-coloured ring, pale glyph icon and a
        # soft halo. Passive skills are round, active abilities are square badges, so
        # the two tiers are distinguishable at a glance even at the overview zoom.
        gap_px = SK.min_node_gap() * unit
        radius = max(S(7), min(S(21), int(gap_px * 0.37)))
        show_labels = radius >= S(10)
        self.tree_rects = []
        mouse = pygame.mouse.get_pos()
        hovered = None
        label_boxes: list[pygame.Rect] = []
        for skill in SK.SKILLS:
            nx, ny = SK.position_of(skill)
            cx, cy = to_screen((nx, ny))
            near_cursor = math.hypot(nx - tx, ny - ty) < 0.19
            if not (area_x - S(60) < cx < area_x + area_w + S(60)
                    and area_y - S(60) < cy < area_y + area_h + S(60)):
                continue
            pad = radius + S(4)
            rect = pygame.Rect(cx - pad, cy - pad, pad * 2, pad * 2)
            self.tree_rects.append((rect, skill["id"]))
            if rect.collidepoint(mouse):
                hovered = skill["id"]
            done = skill["id"] in learned
            avail = g.can_learn(skill["id"])
            branch = next((b for b in SK.BRANCHES if b["id"] == skill["branch"]), None)
            col = tuple(branch["color"]) if branch else (226, 214, 160)
            far = node["branch"] not in (skill["branch"], "root") and skill["branch"] != "root"
            active = skill["kind"] == "active"
            selected = skill["id"] == g.tree_cursor
            if far:                              # other branches recede, but stay coloured
                col = _mix(col, (86, 92, 108), 0.55)
            # halo
            if avail or done or selected:
                pulse = 0.5 + 0.5 * math.sin(self.t * 3.4 + nx * 6)
                halo = self._halo_cache.get((col, radius))
                if halo is None:
                    halo = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
                    for k in range(6, 0, -1):
                        pygame.draw.circle(halo, (*col, int(10 + 3 * k)),
                                           (radius * 2, radius * 2), int(radius * (1.0 + 0.16 * k)))
                    self._halo_cache[(col, radius)] = halo
                halo.set_alpha(int(150 + 90 * pulse) if avail else 120)
                screen.blit(halo, (cx - radius * 2, cy - radius * 2))
            # plate: square for abilities, circle for passives.
            # The ring keeps the BRANCH colour (identity); state is carried by
            # brightness, an extra gold ring and the halo, so the two never fight.
            ring_col = col if (done or avail) else _mix(col, (74, 78, 92), 0.62)
            fill = (26, 30, 42) if not done else _mix((38, 34, 26), col, 0.22)
            if not (done or avail):
                fill = (18, 21, 30)
            if active:
                box = pygame.Rect(0, 0, radius * 2, radius * 2)
                box.center = (cx, cy)
                pygame.draw.rect(screen, (8, 10, 16), box.inflate(S(4), S(4)),
                                 border_radius=max(2, S(5)))
                pygame.draw.rect(screen, fill, box, border_radius=max(2, S(4)))
                ring_w = max(2, S(3) if (done or avail) else S(2))
                pygame.draw.rect(screen, ring_col, box, ring_w,
                                 border_radius=max(2, S(4)))
                pygame.draw.rect(screen, _mix(col, (255, 255, 255), 0.45),
                                 box.inflate(-S(6), -S(6)), 1, border_radius=max(1, S(3)))
            else:
                pygame.draw.circle(screen, (8, 10, 16), (cx + S(1), cy + S(2)), radius + S(3))
                pygame.draw.circle(screen, fill, (cx, cy), radius + S(1))
                ring_w = max(2, S(3) if (done or avail) else S(2))
                pygame.draw.circle(screen, ring_col, (cx, cy), radius, ring_w)
            if done:
                # learned = a check badge, never a colour: gold and green are also
                # branch hues here, so state must not reuse them
                bx_, by_ = cx + int(radius * 0.72), cy + int(radius * 0.72)
                br = max(S(5), radius // 3)
                pygame.draw.circle(screen, (12, 16, 24), (bx_, by_), br + S(1))
                pygame.draw.circle(screen, (238, 208, 118), (bx_, by_), br)
                pygame.draw.lines(screen, (28, 26, 18), False,
                                  [(bx_ - br * 0.45, by_),
                                   (bx_ - br * 0.08, by_ + br * 0.42),
                                   (bx_ + br * 0.5, by_ - br * 0.40)],
                                  max(2, br // 3))
            # glyph: pale, tinted with the branch colour, readable on the dark plate
            icon_px = max(S(11), int(radius * 1.55))
            tone = (255, 250, 235) if done else _mix(col, (255, 255, 255), 0.62)
            if not (done or avail):
                tone = _mix(tone, (120, 124, 140), 0.55)
            glyph = self._glyph(skill["icon"], icon_px, tone)
            screen.blit(glyph, (cx - icon_px // 2, cy - icon_px // 2))
            if active:                           # abilities get a small gem marker
                pip = max(S(3), radius // 4)
                pygame.draw.circle(screen, (120, 200, 255) if (done or avail) else (86, 96, 120),
                                   (cx + radius - pip, cy - radius + pip), pip)
            # learned and learnable nodes always carry a name; locked ones only near
            # the cursor, so the overview stays quiet instead of turning into a word cloud
            label_it = (show_labels and (done or avail)) or near_cursor or rect.collidepoint(mouse)
            if label_it:
                name = self.text(self.font_tiny, skill["name"], True,
                                 (242, 246, 255) if (done or avail) else (166, 172, 188))
                bg = pygame.Surface((name.get_width() + S(8), name.get_height() + S(4)),
                                    pygame.SRCALPHA)
                bg.fill((8, 10, 16, 214))
                lx = cx - bg.get_width() // 2
                lx = max(area_x + S(3), min(area_x + area_w - bg.get_width() - S(3), lx))
                ly = cy + radius + S(3)
                box2 = pygame.Rect(lx - S(2), ly - S(1), bg.get_width() + S(4),
                                   bg.get_height() + S(2))
                if selected or not box2.collidelist(label_boxes) >= 0:
                    label_boxes.append(box2)
                    screen.blit(bg, (lx, ly))
                    screen.blit(name, (lx + S(4), ly + S(2)))
            if selected:
                pygame.draw.circle(screen, (255, 255, 255), (cx, cy), radius + S(7), max(2, S(2)))
                arrow = S(7 + int(3 * (0.5 + 0.5 * math.sin(self.t * 6))))
                pygame.draw.polygon(screen, (255, 240, 170),
                                    [(cx, cy - radius - S(11) - arrow),
                                     (cx - S(8), cy - radius - S(11)),
                                     (cx + S(8), cy - radius - S(11))])
            elif hovered == skill["id"]:
                pygame.draw.circle(screen, (255, 255, 255), (cx, cy), radius + S(7), S(2))

        # ---- branch names at the limb tips, so the tree reads at any zoom ----
        for branch in SK.BRANCHES:
            tips = [SK.position_of(s) for s in SK.branch_skills(branch["id"]) if s["tier"] == 8]
            if not tips:
                continue
            mx = sum(t[0] for t in tips) / len(tips)
            my = sum(t[1] for t in tips) / len(tips)
            bx_, by_ = to_screen((mx, my))
            if not (area_x < bx_ < area_x + area_w and area_y < by_ < area_y + area_h):
                continue
            done = sum(1 for s in SK.branch_skills(branch["id"]) if s["id"] in learned)
            total = len(SK.branch_skills(branch["id"]))
            label = self.text(self.font_big, branch["name"], True, tuple(branch["color"]))
            sub = self.text(self.font_tiny, f"{done}/{total}", True, (216, 222, 236))
            off = S(52) if by_ < area_y + area_h - S(40) else -S(30)
            ly = by_ - off
            ly = max(area_y + S(6), min(area_y + area_h - label.get_height() - sub.get_height() - S(6), ly))
            lx = max(area_x + S(6),
                     min(area_x + area_w - label.get_width() - S(6),
                         bx_ - label.get_width() // 2))
            plate = pygame.Surface((label.get_width() + S(10),
                                    label.get_height() + sub.get_height() + S(4)), pygame.SRCALPHA)
            plate.fill((10, 12, 18, 170))
            screen.blit(plate, (lx - S(5), ly - S(2)))
            screen.blit(label, (lx, ly))
            screen.blit(sub, (lx + label.get_width() // 2 - sub.get_width() // 2,
                              ly + label.get_height()))
        screen.set_clip(clip)

        # ---- legend, so the node rings and pips mean something ----
        legend_y = area_y + area_h - S(20)
        lx = area_x + S(10)
        # colour = branch, brightness = state, so the legend explains both
        for text, col, extra in (("цвет — ветвь", (198, 150, 92), "branch"),
                                 ("✓ изучено", (238, 208, 118), "check"),
                                 ("свечение — доступно", (150, 220, 190), "glow"),
                                 ("квадрат — активное", (120, 200, 255), "square")):
            cxx, cyy = lx + S(7), legend_y + S(5)
            if extra == "square":
                box = pygame.Rect(0, 0, S(12), S(12))
                box.center = (cxx, cyy)
                pygame.draw.rect(screen, (22, 26, 36), box, border_radius=S(3))
                pygame.draw.rect(screen, col, box, S(2), border_radius=S(3))
            elif extra == "check":
                pygame.draw.circle(screen, (12, 16, 24), (cxx, cyy), S(6))
                pygame.draw.circle(screen, col, (cxx, cyy), S(6))
                pygame.draw.lines(screen, (28, 26, 18), False,
                                  [(cxx - S(3), cyy), (cxx - S(1), cyy + S(3)),
                                   (cxx + S(3), cyy - S(3))], S(2))
            elif extra == "branch":
                for k, cc in enumerate(((210, 96, 92), (120, 168, 220), (186, 130, 220))):
                    pygame.draw.circle(screen, cc, (cxx - S(4) + k * S(4), cyy), S(4))
            else:
                pygame.draw.circle(screen, (26, 30, 40), (cxx, cyy), S(6))
                pygame.draw.circle(screen, col, (cxx, cyy), S(6), S(2))
                pygame.draw.circle(screen, (*col, 60), (cxx, cyy), S(9), 3)
            label = self.text(self.font_tiny, text, True, (176, 184, 200))
            screen.blit(label, (lx + S(18), legend_y))
            lx += S(18) + label.get_width() + S(20)

        # ---- top bar ----
        title = self.text(self.font_title, "Дуб навыков", True, (255, 238, 176))
        screen.blit(title, (area_x, S(8)))
        bar_x = area_x + title.get_width() + S(28)
        pts = self.text(self.font, f"Очки навыков: {g.skill_points}", True,
                               (255, 230, 140) if g.skill_points else (150, 152, 164))
        screen.blit(pts, (bar_x, S(14)))
        hint = ("колесо мыши / + − — приблизить   •   F — весь дуб   •   "
                "стрелки / мышь — выбор   •   Enter — изучить   •   K — закрыть")
        hint_x = bar_x + pts.get_width() + S(28)
        if hint_x + self.font_small.size(hint)[0] < self.width - S(16):
            screen.blit(self.text(self.font_small, hint, True, (168, 182, 206)), (hint_x, S(18)))

        # ---- side panel ----
        panel_x = self.width - S(348) + S(10)
        panel_w = S(330)
        self.panel(screen, (panel_x, S(50), panel_w, self.height - S(84)),
                   fill=(14, 17, 26, 246), border=(180, 158, 100), radius=S(8))
        focus = SK.by_id(hovered or g.tree_cursor) or SK.ROOT
        branch = next((b for b in SK.BRANCHES if b["id"] == focus["branch"]), None)
        branch_name = branch["name"] if branch else "Ствол"
        branch_col = tuple(branch["color"]) if branch else (226, 214, 160)
        x = panel_x + S(16)
        y = S(64)
        screen.blit(self.text(self.font_big, focus["name"], True, (255, 240, 200)), (x, y))
        y += S(30)
        pygame.draw.line(screen, (60, 66, 84), (x, y), (x + panel_w - S(32), y))
        y += S(10)
        for text, col in ((f"Ветвь: {branch_name}", branch_col),
                          (f"Ярус {focus['tier']}   •   " + ("активное умение" if focus["kind"] == "active" else "пассивное умение"),
                           (150, 200, 255) if focus["kind"] == "active" else (186, 196, 214))):
            screen.blit(self.text(self.font_small, text, True, col), (x, y))
            y += S(20)
        for line in _wrap(focus["desc"], 40):
            screen.blit(self.text(self.font_small, line, True, (208, 220, 238)), (x, y))
            y += S(19)
        y += S(4)
        state = ("Изучено" if focus["id"] in learned
                 else f"Доступно — Enter ({focus['cost']} очк.)" if g.can_learn(focus["id"])
                 else f"Заперто — нужно {focus['cost']} очк." if g.skill_points < focus["cost"]
                 else "Заперто — сначала предыдущее умение")
        state_col = ((150, 240, 150) if focus["id"] in learned
                     else (255, 230, 150) if g.can_learn(focus["id"]) else (206, 168, 168))
        screen.blit(self.text(self.font, state, True, state_col), (x, y))
        y += S(26)
        if focus["req"]:
            reqs = ", ".join(SK.by_id(r)["name"] for r in focus["req"] if SK.by_id(r))
            for line in _wrap("Требует: " + reqs, 42):
                screen.blit(self.text(self.font_small, line, True, (190, 200, 216)), (x, y))
                y += S(18)
        y += S(8)
        pygame.draw.line(screen, (60, 66, 84), (x, y), (x + panel_w - S(32), y))
        y += S(12)
        screen.blit(self.text(self.font, "Ветви", True, (240, 232, 200)), (x, y))
        y += S(24)
        for b in SK.BRANCHES:
            nodes = SK.branch_skills(b["id"])
            done = sum(1 for n in nodes if n["id"] in learned)
            here = focus["branch"] == b["id"]
            screen.blit(self.text(self.font_small, 
                f"{b['name']}: {done}/{len(nodes)}", True,
                tuple(b["color"]) if here else (176, 182, 196)), (x, y))
            bar_x, bar_w = x + S(112), panel_w - S(150)
            pygame.draw.rect(screen, (28, 32, 42), (bar_x, y + S(4), bar_w, S(9)))
            if done:
                pygame.draw.rect(screen, tuple(b["color"]),
                                 (bar_x, y + S(4), max(2, int(bar_w * done / len(nodes))), S(9)))
            pygame.draw.rect(screen, (58, 62, 74), (bar_x, y + S(4), bar_w, S(9)), 1)
            y += S(21)
        y += S(10)
        pygame.draw.line(screen, (60, 66, 84), (x, y), (x + panel_w - S(32), y))
        y += S(12)
        screen.blit(self.text(self.font, "Активные умения", True, (240, 232, 200)), (x, y))
        y += S(22)
        for i in range(G.HOTBAR_KEYS):
            key = g.player["hotbar"][i] if i < len(g.player["hotbar"]) else None
            slot = pygame.Rect(x + i * S(34), y, S(30), S(30))
            pygame.draw.rect(screen, (24, 28, 38), slot)
            pygame.draw.rect(screen, (72, 80, 98), slot, 1)
            if key:
                ab = G.ABILITIES[key]
                icon = SP.item_icon_surface(SK._ABILITY_ICON.get(key, "scroll"))
                screen.blit(pygame.transform.scale(icon, (S(22), S(22))),
                            (slot.x + S(4), slot.y + S(4)))
            num = self.text(self.font_tiny, str(i + 1), True, (168, 176, 194))
            screen.blit(num, (slot.x + S(2), slot.y + slot.height - S(11)))
        y += S(38)
        for i in range(G.HOTBAR_KEYS):
            key = g.player["hotbar"][i] if i < len(g.player["hotbar"]) else None
            if not key:
                continue
            ab = G.ABILITIES[key]
            screen.blit(self.text(self.font_tiny, 
                f"{i + 1}. {ab['name']} — мана {ab['mana']}", True, (188, 206, 232)), (x, y))
            y += S(15)
        screen.blit(self.text(self.font_small, 
            f"Изучено: {len(learned)}/{len(SK.SKILLS)}", True, (230, 220, 180)),
            (x, self.height - S(62)))

    # ----------------------------------------------------------------- dialog
    def draw_dialog(self, screen) -> None:
        if not self.game.dialog:
            return
        g = self.game
        d, S = g.dialog, self.s
        offers = [QST.by_id(q) for q in d.get("offers", [])]
        offers = [q for q in offers if q]
        turns = [QST.by_id(q) for q in d.get("turns", [])]
        turns = [q for q in turns if q]
        w = S(720)
        h = S(118) + S(26) * len(turns) + S(30) * len(offers)
        x, y = (self.width - w) / 2, self.height - h - S(96)
        self.panel(screen, (int(x), int(y), w, h), fill=(10, 13, 22, 246),
                   border=(226, 202, 132), radius=S(8))
        screen.blit(self.text(self.font_big, d["name"], True, (255, 226, 140)),
                    (x + S(20), y + S(12)))
        screen.blit(self.text(self.font, d["line"], True, (240, 242, 250)),
                    (x + S(20), y + S(46)))
        yy = y + S(78)
        for i, q in enumerate(turns):
            bar = pygame.Rect(int(x + S(14)), int(yy - S(3)), w - S(28), S(24))
            pygame.draw.rect(screen, (26, 44, 26), bar)
            pygame.draw.rect(screen, (150, 220, 140), bar, 1)
            screen.blit(self.text(self.font_small, 
                f"Готово: {q['title']} — Enter, чтобы сдать", True, (196, 244, 186)),
                (bar.x + S(8), bar.y + S(4)))
            yy += S(26)
        for i, q in enumerate(offers):
            bar = pygame.Rect(int(x + S(14)), int(yy - S(3)), w - S(28), S(28))
            pygame.draw.rect(screen, (24, 30, 44), bar)
            pygame.draw.rect(screen, (226, 202, 132), bar, 1)
            screen.blit(self.text(self.font_small, 
                f"{i + 1} — взять: {q['title']}", True, (255, 236, 158)),
                (bar.x + S(8), bar.y + S(3)))
            screen.blit(self.text(self.font_tiny, q["desc"], True, (196, 208, 228)),
                        (bar.x + S(8), bar.y + S(17)))
            yy += S(30)
        hint = "E — закрыть" + ("   •   TAB — торговля" if d.get("shop") else "")
        if offers or turns:
            hint = "1-3 — взять задание   •   Enter — сдать   •   " + hint
        txt = self.text(self.font_small, hint, True, (162, 178, 202))
        screen.blit(txt, (x + w - txt.get_width() - S(16), y + h - S(24)))

    # ------------------------------------------------------------- settings
    def draw_settings(self, screen, tab: str, row: int, res_index: int,
                      fullscreen: bool, note: str = "", capturing: bool = False) -> None:
        g, S = self.game, self.s
        screen.fill((9, 12, 20))
        # soft vignette so the panel reads as a page, not a popup
        for i in range(6):
            a = 18 - i * 3
            band = pygame.Surface((self.width, S(40)), pygame.SRCALPHA)
            band.fill((30, 44, 70, max(0, a)))
            screen.blit(band, (0, i * S(40)))
        w, h = S(820), S(600)
        x = (self.width - w) // 2
        y = (self.height - h) // 2
        self.panel(screen, (x, y, w, h), fill=(14, 18, 28, 250), border=(150, 170, 210),
                   radius=S(10))
        screen.blit(self.text(self.font_title, "Настройки", True, (252, 244, 220)),
                    (x + S(24), y + S(14)))
        screen.blit(self.text(self.font_small, "TAB — вкладка   •   ↑ ↓ — строка   •   "
                                           "← → — значение   •   Enter — выбрать   •   "
                                           "ESC — назад",
                                           True, (162, 178, 202)),
                    (x + S(24), y + S(52)))

        # tabs
        tx = x + S(24)
        ty = y + S(78)
        for key, label in G.Game.SETTINGS_TABS:
            tw = S(150)
            active = key == tab
            rect = pygame.Rect(tx, ty, tw, S(34))
            pygame.draw.rect(screen, (36, 46, 66) if active else (22, 26, 36), rect,
                             border_radius=S(6))
            pygame.draw.rect(screen, (250, 220, 140) if active else (62, 70, 88), rect, 2,
                             border_radius=S(6))
            txt = self.text(self.font, label, True,
                                   (255, 240, 190) if active else (176, 188, 206))
            screen.blit(txt, (rect.x + (tw - txt.get_width()) // 2, rect.y + S(6)))
            tx += tw + S(10)

        rows = g.settings_rows(tab, res_index, fullscreen)
        row = max(0, min(row, len(rows) - 1))
        ry = ty + S(50)
        # the controls tab has thirteen rows, so the row height adapts to fit them all
        avail = (y + h - S(44)) - ry
        rh = max(S(26), min(S(46), avail // max(1, len(rows))))
        for i, (action, label, value) in enumerate(rows):
            rect = pygame.Rect(x + S(24), ry + i * rh, w - S(48), rh - S(4))
            sel = i == row
            if sel:
                pygame.draw.rect(screen, (30, 38, 54), rect, border_radius=S(6))
                pygame.draw.rect(screen, (240, 206, 130), rect, 2, border_radius=S(6))
            text_y = rect.y + (rect.height - self.font.get_height()) // 2
            screen.blit(self.text(self.font, label, True,
                                         (248, 250, 255) if sel else (206, 216, 232)),
                        (rect.x + S(14), text_y))
            # value on the right: a slider for volumes, a pill for everything else
            if action in ("sfx_volume", "music_volume"):
                frac = float(g.settings[action])
                bar = pygame.Rect(rect.right - S(300), rect.centery - S(6), S(190), S(12))
                pygame.draw.rect(screen, (26, 30, 42), bar, border_radius=S(6))
                if frac > 0:
                    pygame.draw.rect(screen, (120, 200, 150),
                                     (bar.x, bar.y, max(3, int(bar.width * frac)), bar.height),
                                     border_radius=S(6))
                pygame.draw.rect(screen, (74, 84, 104), bar, 1, border_radius=S(6))
                vt = self.text(self.font, value, True, (236, 240, 250))
                screen.blit(vt, (bar.right + S(12), text_y))
            else:
                vt = self.text(self.font, value, True,
                                      (255, 236, 150) if sel else (216, 226, 242))
                vx = rect.right - vt.get_width() - S(16)
                if sel and not capturing:
                    screen.blit(self.text(self.font, "‹", True, (240, 206, 130)),
                                (vx - S(18), text_y))
                    screen.blit(self.text(self.font, "›", True, (240, 206, 130)),
                                (rect.right - S(14), text_y))
                screen.blit(vt, (vx, text_y))
        # key capture: the action name stays readable, only the value slot changes
        if capturing:
            rect = pygame.Rect(x + S(24), ry + row * rh, w - S(48), rh - S(4))
            pygame.draw.rect(screen, (44, 34, 16), rect, border_radius=S(6))
            pygame.draw.rect(screen, (250, 220, 140), rect, 2, border_radius=S(6))
            pulse = 0.5 + 0.5 * math.sin(self.t * 5)
            col = (int(210 + 45 * pulse), int(200 + 40 * pulse), 150)
            txt = self.text(self.font, "нажми клавишу…  (ESC — отмена)", True, col)
            screen.blit(txt, (rect.right - txt.get_width() - S(16),
                              rect.y + (rect.height - txt.get_height()) // 2))
        if note:
            screen.blit(self.text(self.font_small, note, True, (150, 230, 160)),
                        (x + S(24), y + h - S(30)))

    # ------------------------------------------------------------------ menus
    def draw_title_backdrop(self, screen: pygame.Surface) -> None:
        g = self.game
        cam_x = W.VILLAGE_CENTER[0] - self.view_w / 2 + math.sin(self.t * 0.1) * 8
        cam_y = W.VILLAGE_CENTER[1] - self.view_h / 2 + math.cos(self.t * 0.08) * 4
        cam_x = max(0.0, min(W.MAP_W - self.view_w, cam_x))
        cam_y = max(0.0, min(W.MAP_H - self.view_h, cam_y))
        self.cam_x, self.cam_y = cam_x, cam_y
        self.logical.fill(art.VOID)
        self.draw_tiles(cam_x, cam_y)
        self.draw_decor(cam_x, cam_y)
        for o in g.world.objects:
            if cam_x - 4 < o["x"] < cam_x + self.view_w + 4 and \
                    cam_y - 5 < o["y"] < cam_y + self.view_h + 5:
                self.draw_object(o, cam_x, cam_y)
        for n in g.npcs:
            self.draw_npc(n, cam_x, cam_y)
        self.draw_player(cam_x, cam_y)
        pygame.transform.scale(self.logical, (self.lw * self.zoom, self.lh * self.zoom),
                               self._scaled)
        screen.fill((8, 12, 20))
        screen.blit(self._scaled, (self.ox, self.oy))
        dim = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        dim.fill((6, 10, 20, 150))
        screen.blit(dim, (0, 0))
        for i in range(14):
            fx = (math.sin(self.t * 0.3 + i * 1.7) * 0.5 + 0.5) * self.width
            fy = (math.cos(self.t * 0.23 + i * 2.3) * 0.5 + 0.5) * self.height
            a = int(110 + 100 * math.sin(self.t * 2 + i))
            glow = pygame.Surface((self.s(9), self.s(9)), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 236, 160, max(0, min(255, a))),
                               (self.s(4), self.s(4)), self.s(2))
            screen.blit(glow, (fx, fy))

    def draw_menu(self, screen, title: str, subtitle: str, entries, selected: int,
                  backdrop: bool = True, note: str = "") -> None:
        S = self.s
        if backdrop:
            self.draw_title_backdrop(screen)
        else:
            screen.fill((10, 14, 24))
        row_h = S(52)
        panel_w = S(700)
        panel_h = S(150) + len(entries) * row_h + (S(52) if note else S(44))
        px = (self.width - panel_w) // 2
        py = (self.height - panel_h) // 2 - S(20)
        sh = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 130))
        screen.blit(sh, (px + S(7), py + S(7)))
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
        title_s = self.text(self.font_title, title, True, (255, 238, 176))
        title_sh = self.text(self.font_title, title, True, (24, 16, 6))
        tx = self.width / 2 - title_s.get_width() / 2
        ty = py + S(26)
        screen.blit(title_sh, (tx + 3, ty + 3))
        screen.blit(title_s, (tx, ty))
        pygame.draw.rect(screen, (150, 128, 78),
                         (px + S(60), ty + title_s.get_height() + S(10), panel_w - S(120), 1))
        if subtitle:
            sub = self.text(self.font, subtitle, True, (214, 226, 246))
            screen.blit(sub, (self.width / 2 - sub.get_width() / 2,
                              ty + title_s.get_height() + S(18)))
        mouse = pygame.mouse.get_pos()
        y = ty + title_s.get_height() + (S(66) if subtitle else S(44))
        self.menu_rects = []
        for i, (label, enabled) in enumerate(entries):
            rect = pygame.Rect(px + S(56), y, panel_w - S(112), row_h - S(8))
            self.menu_rects.append((rect, i, enabled))
            cur = (i == selected) or (rect.collidepoint(mouse) and enabled)
            if cur and enabled:
                pygame.draw.rect(screen, (34, 28, 16), rect)
                pygame.draw.rect(screen, (248, 226, 152), rect, 2)
            col = ((255, 236, 158) if (cur and enabled)
                   else (204, 214, 232) if enabled else (104, 112, 128))
            txt = self.text(self.font_big, label, True, col)
            screen.blit(txt, (self.width / 2 - txt.get_width() / 2,
                              rect[1] + (rect[3] - txt.get_height()) / 2))
            if cur and enabled and math.sin(self.t * 6) > -0.35:
                ax0 = rect[0] + S(16)
                ay0 = rect[1] + rect[3] / 2
                pygame.draw.polygon(screen, (255, 226, 140),
                                    [(ax0, ay0 - S(8)), (ax0 + S(10), ay0), (ax0, ay0 + S(8))])
            y += row_h
        footer_y = py + panel_h - S(38)
        pygame.draw.rect(screen, (150, 128, 78),
                         (px + S(60), footer_y - S(10), panel_w - S(120), 1))
        if note:
            n = self.text(self.font_small, note, True, (186, 204, 228))
            screen.blit(n, (self.width / 2 - n.get_width() / 2, footer_y))
        ver = self.text(self.font_small, "Pixel patch — версия 2.4", True,
                                     (150, 164, 188))
        screen.blit(ver, (self.width / 2 - ver.get_width() / 2, footer_y + S(16)))


# ----------------------------------------------------------------------------
# Input + main loop
# ----------------------------------------------------------------------------
def handle_overlay_key(game: G.Game, renderer: Renderer, key: int) -> None:
    """Keys while an overlay (inventory / tree / shop / quests) is open."""
    overlay = game.overlay
    if overlay == "inventory":
        inv = game.player["inventory"]
        if key in (pygame.K_LEFT, pygame.K_a):
            game.inv_cursor = (game.inv_cursor - 1) % G.INV_SLOTS
        elif key in (pygame.K_RIGHT, pygame.K_d):
            game.inv_cursor = (game.inv_cursor + 1) % G.INV_SLOTS
        elif key in (pygame.K_UP, pygame.K_w):
            game.inv_cursor = (game.inv_cursor - 6) % G.INV_SLOTS
        elif key in (pygame.K_DOWN, pygame.K_s):
            game.inv_cursor = (game.inv_cursor + 6) % G.INV_SLOTS
        elif key in (pygame.K_e, pygame.K_RETURN, pygame.K_KP_ENTER):
            msg = game.use_slot(game.inv_cursor)
            if msg:
                game.toast(msg, "#9ad7ff")
        elif key == pygame.K_SPACE and inv:
            if 0 <= game.inv_cursor < len(inv):
                game.drop_item(game.inv_cursor)
        elif key in (pygame.K_i, pygame.K_ESCAPE):
            game.overlay = None
            game.sound("menu_move", 0.5)
    elif overlay == "skilltree":
        if key in (pygame.K_LEFT, pygame.K_a):
            game.tree_move(-1, 0)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            game.tree_move(1, 0)
        elif key in (pygame.K_UP, pygame.K_w):
            game.tree_move(0, -1)
        elif key in (pygame.K_DOWN, pygame.K_s):
            game.tree_move(0, 1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_e):
            node = SK.by_id(game.tree_cursor)
            if node and not game.learn(node["id"]):
                if node["id"] in game.player["learned"]:
                    game.toast("Умение уже изучено", "#c8c8d0")
                else:
                    game.toast("Не хватает очков навыков", "#ffb0b0")
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS, pygame.K_PAGEUP):
            game.tree_zoom_by(G.TREE_ZOOM_STEP)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_PAGEDOWN):
            game.tree_zoom_by(-G.TREE_ZOOM_STEP)
        elif key == pygame.K_f:
            game.tree_show_all()
        elif key in (pygame.K_k, pygame.K_ESCAPE):
            game.overlay = None
            game.sound("menu_move", 0.5)
    elif overlay == "shop":
        lines = game.shop_lines()
        if key in (pygame.K_UP, pygame.K_w):
            game.shop_cursor = (game.shop_cursor - 1) % max(1, len(lines))
            game.sound("menu_move", 0.4)
        elif key in (pygame.K_DOWN, pygame.K_s):
            game.shop_cursor = (game.shop_cursor + 1) % max(1, len(lines))
            game.sound("menu_move", 0.4)
        elif key == pygame.K_TAB:
            game.shop_tab = "buy" if game.shop_tab == "sell" else "sell"
            game.shop_cursor = 0
            game.sound("menu_select", 0.6)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_e):
            game.toast(game.shop_action(), "#ffe066")
        elif key == pygame.K_r:
            game.toast(game.sell_all_junk(), "#ffe066")
        elif key in (pygame.K_ESCAPE, pygame.K_i):
            game.overlay = None
            game.sound("menu_move", 0.5)
    elif overlay == "quests" and key in (pygame.K_q, pygame.K_ESCAPE):
        game.overlay = None


def handle_play_key(game: G.Game, key: int) -> None:
    k = game.keys
    if key == k.get("inventory", pygame.K_i):
        game.overlay = "inventory"
        game.sound("menu_select", 0.5)
    elif key == k.get("skills", pygame.K_k):
        game.overlay = "skilltree"
        game.sound("menu_select", 0.6)
    elif key == k.get("quests", pygame.K_q):
        game.overlay = "quests"
        game.sound("menu_move", 0.5)
    elif key == k.get("interact", pygame.K_e):
        if game.dialog:
            if game.dialog.get("shop"):
                game.dialog = None
                game.open_shop()
            else:
                game.dialog = None
        else:
            game.interact()
    elif key == k.get("music", pygame.K_m):
        game.toast(game.toggle_music(), "#9ad7ff")
    elif key == k.get("next_track", pygame.K_n):
        game.toast(game.next_track(), "#9ad7ff")
    elif game.dialog and pygame.K_1 <= key <= pygame.K_3:
        msg = game.dialog_take_quest(key - pygame.K_1)
        if msg:
            game.toast(msg, "#ffe066")
    elif game.dialog and key in (pygame.K_RETURN, pygame.K_KP_ENTER):
        msg = game.dialog_turn_in()
        if msg:
            game.toast(msg, "#b6e3a0")
    elif key == pygame.K_TAB and game.dialog and game.dialog.get("shop"):
        game.dialog = None
        game.open_shop()
    elif key == k.get("attack", pygame.K_SPACE):
        game.attack()
    elif key == pygame.K_F5:
        game.save()
    elif key == pygame.K_F9:
        game.load()
    elif key == k.get("potion", pygame.K_h):
        game.use_potion_hotkey()
    elif pygame.K_1 <= key <= pygame.K_9:
        game.cast(key - pygame.K_1)


def run() -> int:
    pygame.init()
    pygame.display.set_caption("Pixel patch 2.4")
    cfg = G.load_config()
    res_index = G.parse_res_arg(sys.argv)
    if res_index is None:
        res_index = max(0, min(len(G.RESOLUTIONS) - 1,
                               cfg.get("res_index", G.DEFAULT_RES_INDEX)))
    fullscreen = bool(cfg.get("fullscreen", False)) or "--fullscreen" in sys.argv
    if not fullscreen:
        res_index = min(res_index, G.best_res_index_for_desktop())
    screen, width, height, zoom = G.apply_display(res_index, fullscreen)

    game = G.Game()
    renderer = Renderer(game, width, height, zoom)
    clock = pygame.time.Clock()
    has_save = G.SAVE_PATH.exists()
    state = "title"
    selected = 0
    settings_from = "title"
    settings_tab = "screen"
    settings_row = 0
    settings_note = ""
    capturing = False
    note = ""
    running = True

    while running:
        dt = min(0.05, clock.tick(G.FPS) / 1000.0)
        renderer.t += dt
        entries: list[tuple[str, bool]] = []
        if state == "title":
            entries = [("Новая игра", True),
                       ("Продолжить" + ("" if has_save else "   — нет сохранения"), has_save),
                       ("Настройки", True), ("Выход", True)]
        elif state == "pause":
            entries = [("Продолжить", True), ("Сохранить", True),
                       ("Загрузить" + ("" if has_save else "   — нет сохранения"), has_save),
                       ("Настройки", True), ("В главное меню", True), ("Выход", True)]
        elif state == "settings":
            entries = []          # the settings screen has its own tabs and rows

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    screen, width, height, zoom = G.apply_display(res_index, fullscreen)
                    renderer.resize(width, height, zoom)
                    G.save_config({"res_index": res_index, "fullscreen": fullscreen})
                    continue
                if state == "play":
                    if game.overlay:
                        handle_overlay_key(game, renderer, event.key)
                    elif event.key == pygame.K_ESCAPE:
                        state = "pause"
                        selected = 0
                        game.sound("menu_select", 0.5)
                    elif event.key == pygame.K_F10:
                        state = "pause"
                        selected = 0
                    else:
                        handle_play_key(game, event.key)
                    continue
                if state == "settings":
                    rows_now = game.settings_rows(settings_tab, res_index, fullscreen)
                    if capturing:
                        if event.key == pygame.K_ESCAPE:
                            settings_note = "Переназначение отменено"
                        else:
                            action = rows_now[min(settings_row, len(rows_now) - 1)][0]
                            if action.startswith("key:"):
                                name = action.split(":", 1)[1]
                                settings_note = "Назначено — " + game.bind_key(name, event.key)
                                game.sound("menu_select", 0.5)
                        capturing = False
                        continue
                    if event.key == pygame.K_TAB:
                        order = [k for k, _lbl in G.Game.SETTINGS_TABS]
                        settings_tab = order[(order.index(settings_tab) + 1) % len(order)]
                        settings_row = 0
                        settings_note = ""
                        game.sound("menu_move", 0.4)
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        settings_row = (settings_row - 1) % max(1, len(rows_now))
                        game.sound("menu_move", 0.3)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        settings_row = (settings_row + 1) % max(1, len(rows_now))
                        game.sound("menu_move", 0.3)
                    elif event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                        step = 1 if event.key in (pygame.K_RIGHT, pygame.K_d) else -1
                        action = rows_now[min(settings_row, len(rows_now) - 1)][0]
                        if action.startswith("key:"):
                            settings_note = "Enter — назначить клавишу"
                        elif action.startswith("res:"):
                            res_index = max(0, min(len(G.RESOLUTIONS) - 1,
                                                   int(action.split(":")[1]) + step))
                            screen, width, height, zoom = G.apply_display(res_index, fullscreen)
                            renderer.resize(width, height, zoom)
                            G.save_config({"res_index": res_index, "fullscreen": fullscreen})
                            settings_note = f"Разрешение: {width} × {height}"
                        elif action == "fullscreen":
                            fullscreen = not fullscreen
                            screen, width, height, zoom = G.apply_display(res_index, fullscreen)
                            renderer.resize(width, height, zoom)
                            G.save_config({"res_index": res_index, "fullscreen": fullscreen})
                            settings_note = "Полный экран: " + ("включён" if fullscreen else "выключен")
                        else:
                            settings_note = game.change_setting(action, step)
                        game.sound("menu_move", 0.3)
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        action = rows_now[min(settings_row, len(rows_now) - 1)][0]
                        game.sound("menu_select", 0.6)
                        if action.startswith("res:"):
                            res_index = int(action.split(":")[1])
                            screen, width, height, zoom = G.apply_display(res_index, fullscreen)
                            renderer.resize(width, height, zoom)
                            G.save_config({"res_index": res_index, "fullscreen": fullscreen})
                            settings_note = f"Разрешение: {width} × {height}"
                        elif action == "fullscreen":
                            fullscreen = not fullscreen
                            screen, width, height, zoom = G.apply_display(res_index, fullscreen)
                            renderer.resize(width, height, zoom)
                            G.save_config({"res_index": res_index, "fullscreen": fullscreen})
                            settings_note = "Полный экран: " + ("включён" if fullscreen else "выключен")
                        elif action.startswith("key:"):
                            capturing = True
                            settings_note = ""
                        elif action == "reset_keys":
                            settings_note = game.change_setting("reset_keys")
                        else:
                            settings_note = game.change_setting(action, 1)
                    elif event.key == pygame.K_ESCAPE:
                        state = settings_from
                        settings_row = 0
                        settings_note = ""
                        game.sound("menu_move", 0.4)
                    continue
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(entries)
                    while not entries[selected][1]:
                        selected = (selected - 1) % len(entries)
                    game.sound("menu_move", 0.35)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(entries)
                    while not entries[selected][1]:
                        selected = (selected + 1) % len(entries)
                    game.sound("menu_move", 0.35)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    label = entries[selected][0]
                    game.sound("menu_select", 0.6)
                    if state == "settings":
                        if selected < len(G.RESOLUTIONS):
                            res_index = selected
                            screen, width, height, zoom = G.apply_display(res_index, fullscreen)
                            renderer.resize(width, height, zoom)
                            G.save_config({"res_index": res_index, "fullscreen": fullscreen})
                            note = "Разрешение сохранено"
                        elif selected == len(G.RESOLUTIONS):
                            fullscreen = not fullscreen
                            screen, width, height, zoom = G.apply_display(res_index, fullscreen)
                            renderer.resize(width, height, zoom)
                            G.save_config({"res_index": res_index, "fullscreen": fullscreen})
                        else:
                            state = settings_from
                            selected = 0
                            note = ""
                    elif state == "title":
                        if label == "Новая игра":
                            game = G.Game()
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
            elif event.type == pygame.MOUSEWHEEL:
                if state == "play" and game.overlay == "skilltree":
                    game.tree_zoom_by(G.TREE_ZOOM_STEP * (1 if event.y > 0 else -1))
                elif state == "play" and game.overlay == "shop":
                    lines = game.shop_lines()
                    step = -1 if event.y > 0 else 1
                    game.shop_cursor = (game.shop_cursor + step) % max(1, len(lines))
                elif state == "play" and game.overlay == "inventory":
                    step = -6 if event.y > 0 else 6
                    game.inv_cursor = (game.inv_cursor + step) % G.INV_SLOTS
            elif event.type == pygame.MOUSEMOTION:
                if state == "play":
                    if game.overlay == "skilltree":
                        for rect, sid in renderer.tree_rects:
                            if rect.collidepoint(event.pos):
                                game.tree_cursor = sid
                    elif game.overlay == "shop":
                        for rect, i in renderer.shop_rects:
                            if rect.collidepoint(event.pos):
                                game.shop_cursor = i
                    elif game.overlay == "inventory":
                        for rect, i in renderer.inv_rects:
                            if rect.collidepoint(event.pos):
                                game.inv_cursor = i
                else:
                    for rect, i, enabled in renderer.menu_rects:
                        if rect.collidepoint(event.pos) and enabled:
                            selected = i
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state == "play":
                    if game.overlay == "skilltree":
                        for rect, sid in renderer.tree_rects:
                            if rect.collidepoint(event.pos):
                                game.tree_cursor = sid
                                node = SK.by_id(sid)
                                if node and not game.learn(sid):
                                    game.toast("Не хватает очков навыков", "#ffb0b0")
                                break
                    elif game.overlay == "shop":
                        for rect, i in renderer.shop_rects:
                            if rect.collidepoint(event.pos):
                                game.shop_cursor = i
                                game.toast(game.shop_action(), "#ffe066")
                                break
                    elif game.overlay == "inventory":
                        for rect, i in renderer.inv_rects:
                            if rect.collidepoint(event.pos):
                                if game.inv_cursor == i:
                                    msg = game.use_slot(i)
                                    if msg:
                                        game.toast(msg, "#9ad7ff")
                                game.inv_cursor = i
                                break
                    else:
                        game.attack()
                else:
                    for rect, i, enabled in renderer.menu_rects:
                        if rect.collidepoint(event.pos) and enabled:
                            selected = i
                            pygame.event.post(pygame.event.Event(pygame.KEYDOWN,
                                                                 key=pygame.K_RETURN))
                            break

        if state == "play":
            if not game.overlay:
                game.update(dt, G.gather_input(pygame.key.get_pressed(), game.keys))
            else:
                game.update(dt, {"up": False, "down": False, "left": False, "right": False})
            renderer.draw(screen)
        elif state == "title":
            renderer.draw_menu(screen, "Pixel patch",
                               "Большой мир • 19 существ • 121 навык • торговля",
                               entries, selected,
                               note=note or "Стрелки / W S — выбор     Enter — подтвердить     "
                                            "Esc — выход")
        elif state == "pause":
            renderer.draw(screen)
            renderer.draw_menu(screen, "Пауза", "", entries, selected, backdrop=False,
                               note=note or "Стрелки / W S — выбор     Enter — подтвердить     "
                                            "Esc — продолжить")
        else:
            renderer.draw_settings(screen, settings_tab, settings_row, res_index,
                                   fullscreen, note=settings_note, capturing=capturing)
        pygame.display.flip()

    game.save()
    G.save_config({"res_index": res_index, "fullscreen": fullscreen})
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
