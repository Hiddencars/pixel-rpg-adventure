#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rendering, UI screens and the main loop for Pixel patch 2.7.

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

import numpy as np
import pygame

import art
import game as G
import items as IT
import lighting
import music as MUS
import quests as QST
import skills as SK
import sprites as SP
import ui
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


def _asset_root() -> Path:
    """Где лежат ресурсы: в exe — во временной папке PyInstaller, в исходниках — рядом."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent


FONT_DIR = _asset_root() / "assets" / "fonts"
_FONT_PIXEL = FONT_DIR / "PixelifySans.ttf"          # текст интерфейса
_FONT_TITLE = FONT_DIR / "PressStart2P-Regular.ttf"  # логотип и крупные заголовки


def _font(size: int, family: str = "pixel") -> pygame.font.Font:
    """Пиксельный шрифт с кириллицей; системный — только если файла нет."""
    path = _FONT_TITLE if family == "title" else _FONT_PIXEL
    try:
        return pygame.font.Font(str(path), size)
    except Exception:
        pass
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


def draw_loading(screen: pygame.Surface, width: int, height: int,
                 frac: float, label: str) -> None:
    """Экран загрузки: мир 3 096×1 548 строится ~4 секунды.

    Модульная функция, а не метод: рисовать её нужно до того, как появится
    Renderer — он сам создаётся после мира, потому что печёт миникарту.
    """
    scale = width / G.BASE_UI_WIDTH
    S = lambda v: int(round(v * scale))
    f_title = _font(max(24, round(32 * scale)), "title")
    f_small = _font(max(12, round(14 * scale)))
    f_tiny = _font(max(11, round(12 * scale)))

    screen.fill(ui.BG_DARK)
    screen.blit(ui.shade((width, height), (18, 23, 34), 130), (0, 0))
    px, py = width // 2 - S(240), height // 2 - S(40)

    logo = f_title.render("PIXEL PATCH", False, ui.GOLD)
    screen.blit(logo, (width // 2 - logo.get_width() // 2, py - S(90)))
    ui.text_center(screen, f_small, "ГЕНЕРАЦИЯ МИРА", width // 2, py - S(40), ui.TEXT_DIM)

    ui.frame(screen, (px, py, S(480), S(26)), fill=ui.BG_DARK)
    inner = pygame.Rect(px + S(3), py + S(3), S(474), S(20))
    fill = int(inner.w * max(0.0, min(1.0, frac)))
    if fill > 0:
        pygame.draw.rect(screen, ui.GOLD, (inner.x, inner.y, fill, inner.h))
        pygame.draw.line(screen, (255, 238, 176), (inner.x, inner.y),
                         (inner.x + fill - 1, inner.y))
    for x in range(inner.x, inner.right, S(6)):
        pygame.draw.line(screen, ui.BG_DARK, (x, inner.y), (x, inner.bottom - 1))

    ui.text_center(screen, f_small, label, width // 2, py + S(38), ui.TEXT)
    ui.text_center(screen, f_tiny, f"{int(frac * 100)}%", width // 2, py + S(62), ui.TEXT_MUTED)


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
        self.minimap_scaled = pygame.transform.scale(self.minimap, (self.s(160), self.s(80)))
        self._map_scaled: tuple[tuple[int, int], pygame.Surface] | None = None
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
        self.font_tiny = _font(max(11, round(12 * self.ui)))
        self.font_small = _font(max(12, round(14 * self.ui)))
        self.font = _font(max(14, round(16 * self.ui)))
        self.font_big = _font(max(18, round(20 * self.ui)))
        self.font_title = _font(max(24, round(32 * self.ui)), "title")
        if getattr(self, "minimap", None) is not None:
            self.minimap_scaled = pygame.transform.scale(
                self.minimap, (self.s(160), self.s(80)))
        self._vignette = self._build_vignette(width, height)

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
            surf = font.render(text, False, col)
            self._text_cache[key] = surf
        return surf

    def _build_glows(self) -> None:
        """Pre-render the soft light discs once; per frame only the alpha changes."""
        self._glow_cache = {}
        # Concentric circles banded badly (they read as a flat white disc), so the
        # falloff is a real per-pixel gradient, built once per light kind.
        # ядро не должно выжигать землю: гасим центр, растягиваем спад,
        # снижаем альфу — иначе ночью под фонарём не видно ни тайлов, ни лута
        for kind, (r, col, a) in {"campfire": (42, (255, 170, 96), 62),
                                  "lamp": (32, (255, 206, 132), 46),
                                  "house": (36, (255, 200, 140), 32)}.items():
            size = r * 2
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            for y in range(size):
                dy = y - r + 0.5
                for x in range(size):
                    dx = x - r + 0.5
                    d = math.hypot(dx, dy) / r
                    if d >= 1.0:
                        continue
                    # центр притушен на 25%, спад мягче (степень 2.8)
                    alpha = int(a * (1.0 - d) ** 2.8 * (0.6 + 0.4 * min(1.0, d * 3)))
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
        """Pre-render the whole island once; the HUD draws a marker on top.

        Кэш висит на мире: selftest строит рендерер на каждое разрешение, и без
        этого карта в 320 000 тайлов пеклась бы заново пять раз."""
        cached = getattr(self.game.world, "_minimap", None)
        if cached is not None:
            return cached
        w = W.MAP_W
        h = W.MAP_H
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
        # потайловый fill на 4.8 млн клеток — это секунды; палитра применяется
        # одной векторной операцией (LUT), один пиксель на тайл
        lut = np.zeros((16, 3), dtype=np.uint8)
        for tile_id, col in palette.items():
            lut[tile_id] = col
        rgb = lut[self.game.world._tile_array()]
        pygame.surfarray.blit_array(surf, rgb.transpose(1, 0, 2))
        for o in self.game.world.objects:
            if o["kind"].startswith("house"):
                surf.fill((120, 60, 50), (o["x"], o["y"], 3, 2))
        self.game.world._minimap = surf
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
        if g.settings.get("atmosphere", True) and getattr(self, "_vignette", None):
            screen.blit(self._vignette, (0, 0))
        self.draw_text_layer(screen)
        if g.overlay != "skilltree" and g.overlay != "map":  # oak screen и карта — полные страницы
            self.draw_hud(screen)
        if g.overlay == "inventory":
            self.draw_inventory(screen)
        elif g.overlay == "map":
            self.draw_map(screen)
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
    # Семьи тайлов: стык внутри семьи не затеняем, стык между семьями — затеняем.
    TILE_FAMILY = {
        art.T_GRASS: "grass", art.T_MEADOW: "grass", art.T_FOREST: "grass",
        art.T_SAND: "sand", art.T_PATH: "path", art.T_DIRT: "path",
        art.T_STONE: "rock", art.T_ROCK: "rock", art.T_SNOW: "snow",
        art.T_MUD: "mud", art.T_CROPS: "crops", art.T_FLOOR: "floor",
        art.T_SHALLOW: "water", art.T_WATER: "water", art.T_DEEP: "water",
        art.T_VOID: "void",
    }

    def _build_vignette(self, width: int, height: int) -> pygame.Surface:
        """Тёмная рамка по краям экрана: 60 px градиента, собранная один раз.

        Даёт глубину кадру и не даёт ярким кострам «выжигать» край экрана.
        """
        depth = self.s(80)
        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        if depth <= 0:
            return surf
        for i in range(depth):
            a = int(190 * (1.0 - i / depth) ** 2.0)
            if not a:
                continue
            pygame.draw.rect(surf, (6, 9, 15, a),
                             (0, i, width, 1))
            pygame.draw.rect(surf, (6, 9, 15, a),
                             (0, height - 1 - i, width, 1))
        for i in range(depth):
            a = int(155 * (1.0 - i / depth) ** 2.0)
            if not a:
                continue
            pygame.draw.rect(surf, (6, 9, 15, a), (i, 0, 1, height))
            pygame.draw.rect(surf, (6, 9, 15, a), (width - 1 - i, 0, 1, height))
        return surf

    def _build_edge_strips(self) -> None:
        """Край земли в пиксельном стиле: жёсткая линия, гаснущая дизером.

        Раньше это был гладкий десятипиксельный градиент — он читался как мыло
        рядом с чётким пиксель-артом. Теперь 1 px контур и две дизерованные
        полосы: стык остаётся мягким, но остаётся пиксельным.
        """
        if getattr(self, "_edge_strips", None) is not None:
            return
        n = 4
        # (альфа, шаг дизера) по глубине полосы: линия -> 50% -> реже -> реже
        profile = ((170, 1), (110, 2), (70, 2), (40, 3))
        strips = {}
        for side in ("n", "s", "w", "e"):
            if side in ("n", "s"):
                surf = pygame.Surface((TILE, n), pygame.SRCALPHA)
                for i, (a, step) in enumerate(profile):
                    for x in range(0, TILE):
                        if step > 1 and (x // step) % 2:
                            continue
                        surf.set_at((x, i), (9, 13, 20, a))
                if side == "s":
                    surf = pygame.transform.flip(surf, False, True)
            else:
                surf = pygame.Surface((n, TILE), pygame.SRCALPHA)
                for i, (a, step) in enumerate(profile):
                    for y in range(0, TILE):
                        if step > 1 and (y // step) % 2:
                            continue
                        surf.set_at((i, y), (9, 13, 20, a))
                if side == "e":
                    surf = pygame.transform.flip(surf, True, False)
            strips[side] = surf
        self._edge_strips = strips
        self._ao_tiles = {}

    def _tile_surface(self, ttype: int, tx: int, ty: int, wave: int) -> pygame.Surface:
        """Тайл с затенёнными стыками; собирается лениво и кэшируется."""
        frames = self.tiles[ttype]
        if ttype in art.WATER_TILES:
            idx = (wave + tx // 3 + ty // 4) % len(frames)
        else:
            # xor-хэш вместо линейной суммы: линейный давал диагональные полосы
            idx = ((tx * 73856093) ^ (ty * 19349663)) % len(frames)
        w = self.game.world
        fam = self.TILE_FAMILY.get(ttype, "grass")
        mask = 0
        if ty > 0 and self.TILE_FAMILY.get(w.tiles[ty - 1][tx]) != fam:
            mask |= 1
        if tx + 1 < W.MAP_W and self.TILE_FAMILY.get(w.tiles[ty][tx + 1]) != fam:
            mask |= 2
        if ty + 1 < W.MAP_H and self.TILE_FAMILY.get(w.tiles[ty + 1][tx]) != fam:
            mask |= 4
        if tx > 0 and self.TILE_FAMILY.get(w.tiles[ty][tx - 1]) != fam:
            mask |= 8
        if not mask:
            return frames[idx]
        key = (ttype, mask, idx)
        surf = self._ao_tiles.get(key)
        if surf is None:
            surf = frames[idx].copy()
            s_ = self._edge_strips
            if mask & 1:
                surf.blit(s_["n"], (0, 0))
            if mask & 4:
                surf.blit(s_["s"], (0, TILE - s_["s"].get_height()))
            if mask & 8:
                surf.blit(s_["w"], (0, 0))
            if mask & 2:
                surf.blit(s_["e"], (TILE - s_["e"].get_width(), 0))
            self._ao_tiles[key] = surf
        return surf

    def draw_tiles(self, cam_x: float, cam_y: float) -> None:
        self._build_edge_strips()
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
                self.logical.blit(self._tile_surface(row[tx], tx, ty, wave),
                                  ((tx - cam_x) * TILE, (ty - cam_y) * TILE))

    def draw_decor(self, cam_x: float, cam_y: float) -> None:
        s = self.logical
        for d in self.game.world.decor_in_view(int(cam_x), int(cam_y),
                                               int(cam_x + self.view_w),
                                               int(cam_y + self.view_h)):
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
        # отсечение по камере до создания лямбд: на карте 3 100×1 550 мобов
        # почти две тысячи, и каждый кадр их всех сортировать и рисовать — 40 мс
        x0, y0 = cam_x - 2, cam_y - 2
        x1, y1 = cam_x + self.view_w + 2, cam_y + self.view_h + 2

        def vis(e) -> bool:
            return x0 <= e["x"] <= x1 and y0 <= e["y"] <= y1

        for o in self.game.world.objects_in_view(int(cam_x), int(cam_y),
                                                 int(cam_x + self.view_w),
                                                 int(cam_y + self.view_h)):
            items.append((o["y"] + 0.5, lambda o=o: self.draw_object(o, cam_x, cam_y)))

        for d in g.drops:
            if vis(d):
                items.append((d["y"], lambda d=d: self.draw_drop(d, cam_x, cam_y)))
        for n in g.npcs:
            if vis(n):
                items.append((n["y"], lambda n=n: self.draw_npc(n, cam_x, cam_y)))
        for m in g.mobs:
            if m["alive"] and vis(m):
                items.append((m["y"], lambda m=m: self.draw_mob(m, cam_x, cam_y)))
        for a in g.allies:
            if vis(a):
                items.append((a["y"], lambda a=a: self.draw_ally(a, cam_x, cam_y)))
        items.append((g.player["y"], lambda: self.draw_player(cam_x, cam_y)))
        for p in g.particles:
            if vis(p):
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
        if self._glow_gain_now() <= 0.02:
            return

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

    def _glow_gain_now(self) -> float:
        """Яркость световых пятен: 0 днём, 1 глухой ночью.

        Считается раз в кадр: днём аддитивные круги читались как отладочные
        маркеры, а ночью они и есть освещение.
        """
        if getattr(self, "_gain_frame", None) == self.game.frame:
            return self._glow_gain
        ph = self.light.forced_phase
        if ph is None:
            ph = (lighting.START_PHASE + self.game.time / lighting.DAY_LENGTH) % 1.0
        dark = lighting.darkness(ph)
        self._glow_gain = 0.0 if dark < 0.30 else min(1.0, (dark - 0.30) / 0.40)
        self._gain_frame = self.game.frame
        return self._glow_gain

    def draw_glow(self, o: dict, cam_x: float, cam_y: float) -> None:
        """Warm light around windows, lamps and fires (added, so it lights the ground)."""
        gain = self._glow_gain_now()
        if gain <= 0.02:
            return
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
        gain = getattr(self, "_glow_gain", 1.0)
        surf.set_alpha(int(255 * min(1.0, pulse) * gain))
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
        """Тень-дизер вместо гладкого эллипса: держит пиксельный стиль.

        Гладкая полупрозрачная клякса рядом с пиксель-артом читалась как декаль.
        Тень собирается один раз на ширину и кэшируется.
        """
        cache = getattr(self, "_shadow_cache", None)
        if cache is None:
            cache = self._shadow_cache = {}
        sh = cache.get(w)
        if sh is None:
            hh = max(3, int(w * 0.30))
            sh = pygame.Surface((w, hh), pygame.SRCALPHA)
            rx, ry = w / 2.0, hh / 2.0
            for yy in range(hh):
                for xx in range(w):
                    dx = (xx - rx + 0.5) / rx
                    dy = (yy - ry + 0.5) / ry
                    if dx * dx + dy * dy <= 1.0 and (xx + yy) % 2 == 0:
                        sh.set_at((xx, yy), (5, 7, 11, 150))
            cache[w] = sh
        self.logical.blit(sh, ((x - cam_x + 0.5) * TILE - w / 2,
                               (y - cam_y + 0.94) * TILE - w * 0.30))

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
        """Пиксельная панель: обводка, светлая грань, тень — без скруглений.

        `radius` остался в подписи, чтобы не править три десятка вызовов, но
        игнорируется: в пиксель-арте скруглённых углов нет.
        """
        f = tuple(fill)[:3] if isinstance(fill, (tuple, list)) else ui.BG
        b = tuple(border)[:3] if isinstance(border, (tuple, list)) else ui.EDGE
        ui.frame(screen, rect, f, b)

    def draw_hud(self, screen) -> None:
        """HUD по зонам, в пиксельном стиле.

        низ   — жизнь/мана/опыт и хотбар с иконками и перезарядкой;
        лево  — миникарта (уменьшена) и статы;
        право — часы, эффекты и трекер заданий;
        право-низ — тосты. Подсказка управления ушла в меню: в игре она только
        мешала смотреть на мир.
        """
        g, p, S = self.game, self.game.player, self.s
        st = g.stats()
        region = g.region_at(p["x"], p["y"])

        # ------------------------------------------------------------ миникарта
        show_minimap = g.settings.get("minimap", True)
        left_h = 0
        if show_minimap:
            mm_w, mm_h = S(160), S(80)
            self.panel(screen, (S(8), S(8), S(176), S(136)))
            screen.blit(self.minimap_scaled, (S(16), S(16)))
            pygame.draw.rect(screen, ui.INK, (S(16), S(16), mm_w, mm_h), 1)
            mx = S(16) + int(p["x"] / W.MAP_W * mm_w)
            my = S(16) + int(p["y"] / W.MAP_H * mm_h)
            pygame.draw.rect(screen, ui.INK, (mx - 2, my - 2, 5, 5))
            pygame.draw.rect(screen, ui.GOLD, (mx - 1, my - 1, 3, 3))
            ui.text_center(screen, self.font_small,
                           (region["name"] if region else "—").upper(),
                           S(96), S(100), ui.GOLD)
            ui.text_center(screen, self.font_tiny,
                           f"ОТКРЫТО {len(g.visited)}/{len(g.world.regions)}   M — КАРТА",
                           S(96), S(118), ui.TEXT_DIM)
            left_h = S(142)

        # статы: узкая панель под миникартой
        sy = S(8) + left_h
        self.panel(screen, (S(8), sy, S(176), S(62)))
        ui.text(screen, self.font_small, f"ЗОЛОТО {p['gold']}", (S(16), sy + S(5)), ui.GOLD)
        ui.text(screen, self.font_tiny,
                f"АТК {int(st['atk'])}  ЗАЩ {int(st['def'])}  КРИТ {st['crit_chance']:.0f}%",
                (S(16), sy + S(24)), ui.TEXT_DIM)
        ui.text(screen, self.font_tiny,
                f"УБИТО {sum(g.kills.values())}  СМЕРТЕЙ {g.deaths}",
                (S(16), sy + S(40)), ui.TEXT_MUTED)

        # --------------------------------------------------------------- часы
        ph = None
        if g.settings.get("atmosphere", True):
            ph = self.light.forced_phase
            if ph is None:
                ph = (lighting.START_PHASE + g.time / lighting.DAY_LENGTH) % 1.0
        right_y = S(8)
        if ph is not None:
            bw, bh = S(132), S(40)
            bx = self.width - bw - S(8)
            self.panel(screen, (bx, right_y, bw, bh))
            self._sun_moon(screen, bx + S(14), right_y + S(20), S(7), ph)
            ui.text(screen, self.font_small, lighting.phase_name(ph),
                    (bx + S(30), right_y + S(4)), ui.TEXT)
            hours = ph * 24.0
            ui.text(screen, self.font_tiny, f"{int(hours):02d}:{int(hours % 1 * 60):02d}",
                    (bx + S(30), right_y + S(24)), ui.TEXT_DIM)
            right_y += bh + S(6)

        # эффекты — компактной строкой, только когда есть
        if p["buffs"]:
            names = "  ".join(f"{k} {int(v['t'])}" for k, v in p["buffs"].items())
            f = self.font_tiny
            bw = f.size(names)[0] + S(16)
            bx = self.width - bw - S(8)
            self.panel(screen, (bx, right_y, bw, S(20)))
            ui.text(screen, f, names, (bx + S(8), right_y + S(5)), ui.GREEN)
            right_y += S(26)

        # трекер заданий
        active = [q for q in g.quests if not q["done"]][:3]
        ready = sum(1 for q in g.quests if q.get("ready"))
        qw = S(268)
        qx = self.width - qw - S(8)
        rows = max(1, len(active))
        qh = S(24) + rows * S(17)
        self.panel(screen, (qx, right_y, qw, qh))
        head = "ЗАДАНИЯ" + (f"  ГОТОВО {ready}" if ready else "")
        ui.text(screen, self.font_small, head, (qx + S(8), right_y + S(4)),
                ui.GREEN if ready else ui.TEXT)
        if not active:
            ui.text(screen, self.font_tiny, "нет заданий — поговори с жителями",
                    (qx + S(8), right_y + S(24)), ui.TEXT_DIM)
        for i, q in enumerate(active):
            col = ui.GREEN if q.get("ready") else ui.TEXT
            mark = ">" if q.get("ready") else "-"
            yy = right_y + S(24) + i * S(17)
            ui.text(screen, self.font_tiny, f"{mark} {q['title']}", (qx + S(8), yy), col)
            ui.text_right(screen, self.font_tiny, f"{q['progress']}/{q['goal']}",
                          qx + qw - S(8), yy, ui.TEXT_DIM)

        # ------------------------------------------------- низ: жизнь и хотбар
        slot = S(42)
        gap = S(5)
        n = G.HOTBAR_KEYS
        hb_w = n * slot + (n - 1) * gap
        hb_x = self.width // 2 - hb_w // 2
        hb_y = self.height - slot - S(8)

        vit_w, vit_h = hb_w, S(46)
        vit_y = hb_y - vit_h - S(6)
        self.panel(screen, (hb_x, vit_y, vit_w, vit_h))

        lv = S(32)
        ui.slot(screen, (hb_x + S(6), vit_y + S(7), lv, lv))
        ui.text_center(screen, self.font_big, str(p["level"]),
                       hb_x + S(6) + lv // 2,
                       vit_y + S(7) + (lv - self.font_big.get_height()) // 2, ui.GOLD)

        bx = hb_x + lv + S(14)
        num_w = S(62)
        bw = vit_w - (bx - hb_x) - num_w - S(10)
        hp_ratio = p["hp"] / max(1.0, st["hp_max"])
        mp_ratio = p["mp"] / max(1.0, st["mp_max"])
        xp_ratio = p["xp"] / max(1, p["xp_next"])
        ui.bar(screen, (bx, vit_y + S(7), bw, S(12)), hp_ratio, ui.HP, ui.HP_HI, ticks=S(10))
        ui.text_right(screen, self.font_tiny, f"{max(0, math.ceil(p['hp']))}/{int(st['hp_max'])}",
                      bx + bw + num_w, vit_y + S(6), ui.TEXT)
        ui.bar(screen, (bx, vit_y + S(22), bw, S(9)), mp_ratio, ui.MP, ui.MP_HI)
        ui.text_right(screen, self.font_tiny, f"{int(p['mp'])}/{int(st['mp_max'])}",
                      bx + bw + num_w, vit_y + S(20), ui.MP_HI)
        ui.bar(screen, (bx, vit_y + S(34), bw, S(5)), xp_ratio, ui.XP)

        # слоты умений: иконка, клавиша, перезарядка
        hotbar = p["hotbar"]
        for i in range(n):
            x = hb_x + i * (slot + gap)
            filled = i < len(hotbar)
            ui.slot(screen, (x, hb_y, slot, slot), filled=filled)
            ui.text(screen, self.font_tiny, str(i + 1), (x + S(3), hb_y + S(1)),
                    ui.GOLD if filled else ui.TEXT_MUTED, shadow=False)
            if not filled:
                continue
            ab = G.ABILITIES[hotbar[i]]
            icon = SP.item_icon_surface(SK._ABILITY_ICON.get(hotbar[i], "scroll"))
            icon = pygame.transform.scale(icon, (S(28), S(28)))
            screen.blit(icon, (x + (slot - S(28)) // 2, hb_y + S(8)))
            cd = p["cooldowns"].get(hotbar[i], 0.0)
            if cd > 0:
                ui.dither_rect(screen, (x + 1, hb_y + 1, slot - 2, slot - 2), ui.INK, 2)
                ui.text_center(screen, self.font_tiny, f"{cd:.0f}",
                               x + slot // 2, hb_y + slot // 2 - S(5), ui.TEXT)
            if p["mp"] < ab["mana"]:
                ui.text_right(screen, self.font_tiny, str(ab["mana"]),
                              x + slot - S(3), hb_y + slot - S(13), ui.MP_HI, shadow=False)

        # ------------------------------------------------------------ подсказка
        hint = ""
        node = g.nearest_node()
        if node:
            verb = {"tree": "E — срубить дерево", "stump": "E — взять пень",
                    "bush": "E — собрать кусты", "berry_bush": "E — собрать ягоды",
                    "flower": "E — сорвать цветок", "rock_small": "E — добыть камень"}
            hint = verb.get(node["kind"], "E — собрать")
        else:
            npc = g.nearest_npc()
            if npc:
                if g.ready_quests(npc.get("kind", "")):
                    hint = f"E — сдать задание: {npc['name']}"
                elif g.available_quests(npc.get("kind", "")):
                    hint = f"E — поговорить: {npc['name']} (есть дело)"
                else:
                    hint = f"E — поговорить: {npc['name']}"
        if hint and g.settings.get("hints", True):
            w = self.font_small.size(hint)[0] + S(20)
            hx = self.width // 2 - w // 2
            hy = vit_y - S(30)
            ui.frame(screen, (hx, hy, w, S(24)), fill=ui.BG_DARK, edge=ui.GOLD_DIM,
                     hi=ui.GOLD)
            ui.text_center(screen, self.font_small, hint, self.width // 2, hy + S(5),
                           ui.GOLD)

        # --------------------------------------------------------------- тосты
        ty = hb_y - S(8)
        tw = S(320)
        tx = self.width - tw - S(8)
        for t in reversed(g.toasts[-4:]):
            a = (t["t"] / 0.2 if t["t"] < 0.2
                 else (t["life"] - t["t"]) / 0.6 if t["t"] > t["life"] - 0.6 else 1)
            if a <= 0.05:
                ty -= S(24)
                continue
            ui.frame(screen, (tx, ty - S(22), tw, S(22)), fill=ui.BG_DARK)
            msg = t["text"]
            f = self.font_tiny
            while msg and f.size(msg)[0] > tw - S(14):
                msg = msg[:-2]
            ui.text(screen, f, msg, (tx + S(7), ty - S(19)),
                    pygame.Color(t["color"]) if a > 0.5 else ui.TEXT_MUTED)
            ty -= S(24)

    def _sun_moon(self, screen, cx: int, cy: int, r: int, phase: float) -> None:
        """Пиксельные солнце и луна: квадраты вместо кругов, без сглаживания."""
        if lighting.darkness(phase) < 0.42:
            pygame.draw.rect(screen, (255, 208, 96), (cx - r, cy - r, r * 2, r * 2))
            pygame.draw.rect(screen, (255, 244, 190), (cx - r + 2, cy - r + 2, r, r))
        else:
            pygame.draw.rect(screen, (208, 220, 250), (cx - r, cy - r, r * 2, r * 2))
            pygame.draw.rect(screen, (150, 166, 206), (cx + 2, cy - r, r, r))
            pygame.draw.rect(screen, ui.BG, (cx + r - 2, cy - r - 2, r, r * 2))

    def draw_map(self, screen) -> None:
        """Карта мира на M: весь остров, туман войны, подписи открытых областей."""
        g, p, S = self.game, self.game.player, self.s
        screen.fill(ui.BG_DARK)

        ui.text_center(screen, self.font_title, "КАРТА МИРА", self.width // 2, S(8), ui.GOLD)

        avail_w = self.width - S(64)
        avail_h = self.height - S(150)
        scale = min(avail_w / W.MAP_W, avail_h / W.MAP_H)
        mw, mh = max(1, int(W.MAP_W * scale)), max(1, int(W.MAP_H * scale))
        key = (mw, mh)
        if self._map_scaled is None or self._map_scaled[0] != key:
            self._map_scaled = (key, pygame.transform.scale(self.minimap, key))
        map_surf = self._map_scaled[1]

        mx0 = (self.width - mw) // 2
        my0 = S(52) + max(0, (avail_h - mh) // 2)
        ui.frame(screen, (mx0 - S(4), my0 - S(4), mw + S(8), mh + S(8)), fill=ui.BG)
        screen.blit(map_surf, (mx0, my0))

        # туман войны: одна клетка = 32×32 тайла, рисуется мелкой маской и
        # растягивается — так дёшево и остаётся пиксельно-блочным
        cell = G.MAP_CELL
        cw = (W.MAP_W + cell - 1) // cell
        ch = (W.MAP_H + cell - 1) // cell
        fog_key = (cw, ch, len(g.explored))
        if getattr(self, "_fog_key", None) != fog_key:
            fog = pygame.Surface((cw, ch), pygame.SRCALPHA)
            fog.fill((7, 9, 15, 255))
            for (cx, cy) in g.explored:
                if 0 <= cx < cw and 0 <= cy < ch:
                    fog.set_at((cx, cy), (0, 0, 0, 0))
            self._fog = pygame.transform.scale(fog, (mw, mh))
            self._fog_key = fog_key
        screen.blit(self._fog, (mx0, my0))
        pygame.draw.rect(screen, ui.INK, (mx0, my0, mw, mh), 1)

        # подписи только тех областей, чей центр игрок уже видел
        for r in g.world.regions:
            if r["id"] not in g.visited:
                continue
            x0, y0, x1, y1 = r["rect"]
            ccx, ccy = (x0 + x1) // 2 // cell, (y0 + y1) // 2 // cell
            if (ccx, ccy) not in g.explored:
                continue
            cx = mx0 + int((x0 + x1) / 2 * scale)
            cy = my0 + int((y0 + y1) / 2 * scale)
            ui.text_center(screen, self.font_tiny, r["name"].upper(), cx, cy, ui.TEXT)

        # метка игрока: крупный крест с обводкой, мигает — на карте 3 000 тайлов
        # в ширину пиксель-маркер иначе просто не найти
        px = mx0 + int(p["x"] * scale)
        py = my0 + int(p["y"] * scale)
        on = int(self.t * 2) % 2 == 0
        col = (255, 240, 168) if on else ui.GOLD
        pygame.draw.rect(screen, ui.INK, (px - 7, py - 7, 15, 15))
        pygame.draw.rect(screen, col, (px - 6, py - 6, 13, 13))
        pygame.draw.rect(screen, ui.INK, (px - 4, py - 4, 9, 9))
        pygame.draw.rect(screen, (255, 255, 255), (px - 3, py - 3, 7, 7))

        # подвал: что открыто и как закрыть
        fy = my0 + mh + S(10)
        ui.text(screen, self.font_small,
                f"ОБЛАСТИ: {len(g.visited)}/{len(g.world.regions)}",
                (mx0, fy), ui.TEXT_DIM)
        ui.text_right(screen, self.font_small,
                      f"КАРТА ПРОЙДЕНА: {len(g.explored) * G.MAP_CELL * G.MAP_CELL * 100 // (W.MAP_W * W.MAP_H)}%",
                      mx0 + mw, fy, ui.TEXT_DIM)
        ui.text_center(screen, self.font_small, "M или ESC — закрыть",
                       self.width // 2, self.height - S(26), ui.TEXT_MUTED)

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
        """Живой мир за меню, притемнённый пиксельным дизером.

        Раньше здесь был полупрозрачный слой и четырнадцать светлячков; на
        пиксельном фоне это читалось как мыло. Теперь — шахматная сетка: она и
        затемняет, и держит стиль.
        """
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
        screen.blit(ui.shade((self.width, self.height), (6, 9, 15), 186), (0, 0))

    def draw_menu(self, screen, title: str, subtitle: str, entries, selected: int,
                  backdrop: bool = True, note: str = "") -> None:
        """Пиксельное меню: ровные пункты-слоты, логотип пиксельным шрифтом."""
        S = self.s
        if backdrop:
            self.draw_title_backdrop(screen)
        else:
            screen.fill(ui.BG_DARK)
            screen.blit(ui.shade((self.width, self.height), (18, 22, 33), 120), (0, 0))

        row_h = S(44)
        panel_w = min(self.width - S(60), S(700))
        panel_h = S(126) + len(entries) * row_h + (S(38) if note else S(18))
        px = (self.width - panel_w) // 2
        py = (self.height - panel_h) // 2

        ui.frame(screen, (px, py, panel_w, panel_h), fill=ui.BG,
                 edge=ui.GOLD_DIM, hi=ui.GOLD)

        logo = self.text(self.font_title, title.upper(), True, ui.GOLD)
        screen.blit(logo, (self.width // 2 - logo.get_width() // 2, py + S(14)))
        ly = py + S(14) + logo.get_height() + S(10)
        pygame.draw.line(screen, ui.GOLD_DIM, (px + S(24), ly), (px + panel_w - S(24), ly))
        if subtitle:
            sub = self.text(self.font, subtitle, True, ui.TEXT_DIM)
            screen.blit(sub, (self.width // 2 - sub.get_width() // 2, ly + S(8)))

        y = ly + (S(34) if subtitle else S(18))
        self.menu_rects = []
        mouse = pygame.mouse.get_pos()
        for i, (label, enabled) in enumerate(entries):
            rect = pygame.Rect(px + S(26), y, panel_w - S(52), row_h - S(6))
            self.menu_rects.append((rect, i, enabled))
            ui.slot(screen, rect, active=(i == selected and enabled), filled=enabled)
            if i == selected and enabled:
                pygame.draw.rect(screen, (46, 38, 20), rect.inflate(-4, -4))
                pygame.draw.rect(screen, ui.GOLD, (rect.x + 2, rect.y + 2, 3, rect.h - 4))
            elif rect.collidepoint(mouse) and enabled:
                pygame.draw.rect(screen, (36, 31, 18), rect.inflate(-4, -4))
            col = (ui.GOLD if (i == selected and enabled)
                   else ui.TEXT if enabled else ui.TEXT_MUTED)
            txt = self.text(self.font_big, label, True, col)
            screen.blit(txt, (rect.centerx - txt.get_width() // 2,
                              rect.centery - txt.get_height() // 2))
            if i == selected and enabled and math.sin(self.t * 6) > -0.35:
                ax = rect.x + S(10)
                ay = rect.centery
                pygame.draw.polygon(screen, ui.GOLD,
                                    [(ax, ay - S(7)), (ax + S(9), ay), (ax, ay + S(7))])
            y += row_h

        if note:
            ny = py + panel_h - S(26)
            pygame.draw.line(screen, ui.EDGE, (px + S(24), ny - S(10)),
                             (px + panel_w - S(24), ny - S(10)))
            ui.text_center(screen, self.font_small, note, self.width // 2, ny, ui.TEXT_DIM)

def handle_overlay_key(game: G.Game, renderer: Renderer, key: int) -> None:
    """Keys while an overlay (inventory / tree / shop / quests) is open."""
    overlay = game.overlay
    if overlay == "map":
        if key in (pygame.K_ESCAPE, pygame.K_m):
            game.overlay = None
            game.sound("menu_move", 0.5)
        return
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
    elif key == k.get("map", pygame.K_m):
        game.overlay = "map"
        game.sound("menu_select", 0.5)
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
    pygame.display.set_caption("Pixel patch 2.7")
    cfg = G.load_config()
    res_index = G.parse_res_arg(sys.argv)
    if res_index is None:
        res_index = max(0, min(len(G.RESOLUTIONS) - 1,
                               cfg.get("res_index", G.DEFAULT_RES_INDEX)))
    fullscreen = bool(cfg.get("fullscreen", False)) or "--fullscreen" in sys.argv
    if not fullscreen:
        res_index = min(res_index, G.best_res_index_for_desktop())
    screen, width, height, zoom = G.apply_display(res_index, fullscreen)

    def on_progress(frac: float, label: str) -> None:
        """Экран загрузки: без него первые 4 секунды — чёрный экран."""
        draw_loading(screen, width, height, frac, label)
        pygame.display.flip()

    on_progress(0.0, "Рельеф")
    game = G.Game(progress=on_progress)
    on_progress(0.99, "Миникарта")
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
                            game.reset_progress()   # мир уже сгенерирован: не строим заново
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
                               f"{W.MAP_W} × {W.MAP_H} тайлов  •  {len(game.world.regions)} областей  •  19 существ  •  121 навык",
                               entries, selected,
                               note=note or "W S / стрелки — выбор     Enter — выбрать     Esc — выход")
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
