#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rendering, UI screens and the main loop for Pixel RPG 2.0.

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
import skills as SK
import sprites as SP
import world as W
from art import TILE

UI_BG = (12, 15, 24)
UI_EDGE = (96, 118, 158)
GOLD = (240, 210, 120)
OAK_GREEN = ((58, 122, 60), (74, 142, 68), (96, 164, 78), (124, 186, 92))


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
# The great oak (skill tree backdrop), built once and cached
# ----------------------------------------------------------------------------
_oak_cache: dict[tuple[int, int], pygame.Surface] = {}


def build_oak(w: int, h: int) -> pygame.Surface:
    key = (w, h)
    cached = _oak_cache.get(key)
    if cached:
        return cached
    rng = random.Random(20261017)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    base_x = w * 0.5
    base_y = h * 0.99
    # trunk: a tapered polygon with bark shading
    trunk_top = h * 0.52
    half_bottom = w * 0.052
    half_top = w * 0.022
    pygame.draw.polygon(surf, (74, 52, 34),
                        [(base_x - half_bottom, base_y), (base_x - half_top, trunk_top),
                         (base_x + half_top, trunk_top), (base_x + half_bottom, base_y)])
    pygame.draw.polygon(surf, (104, 74, 48),
                        [(base_x - half_bottom * 0.82, base_y),
                         (base_x - half_top * 0.7, trunk_top),
                         (base_x + half_top * 0.2, trunk_top),
                         (base_x + half_bottom * 0.3, base_y)])
    pygame.draw.polygon(surf, (126, 92, 60),
                        [(base_x - half_bottom * 0.55, base_y),
                         (base_x - half_top * 0.35, trunk_top),
                         (base_x - half_top * 0.05, trunk_top),
                         (base_x - half_bottom * 0.1, base_y)])
    for i in range(26):                      # bark grooves
        t = i / 25
        y = trunk_top + (base_y - trunk_top) * t
        wgt = 0.18 + 0.6 * (1 - t)
        x = base_x - half_bottom * wgt + rng.random() * half_bottom * 2 * wgt
        pygame.draw.line(surf, (58, 40, 26), (x, y), (x + rng.uniform(-3, 3), y + 18), 2)
    # roots
    for sx in (-1, 1):
        pygame.draw.polygon(surf, (70, 50, 32),
                            [(base_x + sx * half_bottom * 0.4, base_y - h * 0.06),
                             (base_x + sx * half_bottom * 2.4, base_y),
                             (base_x + sx * half_bottom * 0.5, base_y)])
    # five limbs following the branch angles from skills.py, drawn AFTER the
    # foliage so the branches stay visible behind the skill nodes
    for branch in SK.BRANCHES:
        ang = math.radians(branch["angle"])
        length = h * 0.42
        tip_x = base_x + math.sin(ang) * length * 1.5
        tip_y = trunk_top + h * 0.04 - math.cos(ang) * length
        mid_x = base_x + math.sin(ang) * length * 0.62
        mid_y = trunk_top + h * 0.03 - math.cos(ang) * length * 0.5
        width = max(9, int(h * 0.026))
        pygame.draw.line(surf, (92, 64, 40), (base_x, trunk_top + 6), (mid_x, mid_y), width)
        pygame.draw.line(surf, (118, 84, 52), (base_x, trunk_top + 2), (mid_x, mid_y - 2),
                         max(3, width // 3))
        pygame.draw.line(surf, (78, 54, 34), (mid_x, mid_y), (tip_x, tip_y), max(5, width // 2))
        for k in range(4):
            t = 0.3 + k * 0.18
            tx = base_x + (tip_x - base_x) * t
            ty = trunk_top + (tip_y - trunk_top) * t
            for s in (-1, 1):
                pygame.draw.line(surf, (92, 64, 40),
                                 (tx, ty), (tx + s * w * 0.045, ty - h * 0.045),
                                 max(3, width // 4))
    # foliage: sparse leaf clusters so the limbs stay readable underneath
    for branch in SK.BRANCHES:
        ang = math.radians(branch["angle"])
        for i in range(15):
            t = 0.34 + rng.random() * 0.72
            dist = h * 0.42 * t
            cx = base_x + math.sin(ang) * dist * 1.5 + rng.uniform(-w * 0.030, w * 0.030)
            cy = trunk_top + h * 0.04 - math.cos(ang) * dist + rng.uniform(-h * 0.028, h * 0.028)
            r = h * (0.026 + rng.random() * 0.024)
            pygame.draw.circle(surf, OAK_GREEN[0], (int(cx), int(cy)), int(r))
            pygame.draw.circle(surf, OAK_GREEN[1], (int(cx - r * 0.15), int(cy - r * 0.15)),
                               int(r * 0.72))
            if rng.random() < 0.6:
                pygame.draw.circle(surf, OAK_GREEN[2],
                                   (int(cx - r * 0.3), int(cy - r * 0.35)), int(r * 0.42))
    # crown highlight
    for i in range(26):
        a = rng.random() * math.tau
        d = rng.random() * h * 0.26
        cx = base_x + math.cos(a) * d * 1.5
        cy = h * 0.20 + math.sin(a) * d * 0.6
        pygame.draw.circle(surf, OAK_GREEN[3], (int(cx), int(cy)), rng.randint(3, 6))
    _oak_cache[key] = surf
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
        self.t = 0.0

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
        self.font_small = _font(max(11, round(12 * self.ui)))
        self.font = _font(max(13, round(15 * self.ui)))
        self.font_big = _font(max(17, round(20 * self.ui)))
        self.font_title = _font(max(26, round(38 * self.ui)))

    def s(self, v: float) -> int:
        return int(round(v * self.ui))

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
            w = max(1, int(surf.get_width() * scale))
            h = max(1, int(surf.get_height() * scale))
            surf = pygame.transform.scale(surf, (w, h))
        self.logical.blit(surf, pos)

    # ------------------------------------------------------------ main frame
    def draw(self, screen: pygame.Surface) -> None:
        g = self.game
        p = g.player
        cam_x = max(0.0, min(W.MAP_W - self.view_w, p["x"] - self.view_w / 2))
        cam_y = max(0.0, min(W.MAP_H - self.view_h, p["y"] - self.view_h / 2))
        self.cam_x, self.cam_y = cam_x, cam_y

        self.logical.fill(art.VOID)
        self.draw_tiles(cam_x, cam_y)
        self.draw_decor(cam_x, cam_y)
        self.draw_corpses(cam_x, cam_y)
        self.draw_entities(cam_x, cam_y)

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
                art._canopy(s, px + 16, py + 14, 11,
                            (art.LEAF_D, art.LEAF, art.LEAF_L, art.LEAF_XL),
                            random.Random(d["x"] * 31 + d["y"]), lobes=5)
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
        self.logical.blit(surf, (px, py))
        if o["kind"].startswith("house") or o["kind"] in ("campfire", "lamp"):
            self.draw_glow(o, cam_x, cam_y)

    def draw_glow(self, o: dict, cam_x: float, cam_y: float) -> None:
        """Warm light around windows, lamps and fires (added, so it lights the ground)."""
        kind = o["kind"]
        if kind == "campfire":
            r, col, a = 60, (255, 170, 80), 120
        elif kind == "lamp":
            r, col, a = 48, (255, 220, 140), 95
        else:
            r, col, a = 52, (255, 214, 150), 70
        pulse = 0.8 + 0.2 * math.sin(self.game.time * 3 + o["x"])
        glow = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        for i in range(8, 0, -1):
            rr = int(r * i / 8)
            pygame.draw.circle(glow, (*col, int(a * pulse / i)), (r, r), rr)
        self.logical.blit(glow, ((o["x"] - cam_x) * TILE + TILE / 2 - r,
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
        view = "side" if m["dir"] in ("left", "right") else "down"
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
        key = f"npc_{n['kind']}_{1 if n['anim_t'] > 0.4 else 0}"
        surf = self.sprites.get(key)
        if not surf:
            return
        self.draw_shadow(n["x"], n["y"], cam_x, cam_y, 30)
        ax, ay = self.anchor(n["x"], n["y"], cam_x, cam_y)
        bob = math.sin(self.game.time * 1.6 + n["x"]) * 1.5
        self.logical.blit(surf, (ax, ay + bob))
        if math.hypot(n["x"] - self.game.player["x"],
                      n["y"] - self.game.player["y"]) < 2.2:
            x = (n["x"] - cam_x + 0.5) * TILE
            y = ay - 12 + math.sin(self.game.time * 4) * 2
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
            label = self.font_small.render(n["name"], True, (248, 248, 254))
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
            txt = self.font_small.render(f"{m['name']}  {max(0, int(m['hp']))}",
                                         True, (255, 190, 190))
            screen.blit(txt, ((ax + SP.SPRITE * m.get("scale", 1.0) / 2) * self.zoom
                              - txt.get_width() / 2 + self.ox,
                              ay * self.zoom - txt.get_height() - self.s(4) + self.oy))
        for f in g.floaters:
            alpha = max(0.0, 1 - f["t"] / f["life"])
            col = pygame.Color(f["color"])
            col.a = int(255 * alpha)
            txt = self.font.render(f["text"], True, col)
            lx, ly = self.to_logical(f["x"], f["y"])
            screen.blit(txt, (lx * self.zoom - txt.get_width() / 2 + self.ox,
                              ly * self.zoom - self.s(24) + self.oy))

    # ------------------------------------------------------------------- HUD
    def panel(self, screen, rect, fill=(10, 12, 20, 224), border=UI_EDGE, radius=0) -> None:
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
        st = g.stats()
        w = S(340)
        self.panel(screen, (S(10), S(10), w, S(104)), radius=S(6))
        screen.blit(self.font_big.render("Пиксельное приключение 2.0", True,
                                         (250, 246, 226)), (S(20), S(14)))
        screen.blit(self.font_small.render(
            f"Ур. {p['level']}    Опыт {p['xp']}/{p['xp_next']}    Очки навыков: {g.skill_points}",
            True, (186, 206, 236)), (S(20), S(38)))
        # hp
        pygame.draw.rect(screen, (28, 28, 36), (S(20), S(58), S(210), S(11)))
        pygame.draw.rect(screen, (150, 40, 40), (S(20), S(58), S(210), S(11)))
        pygame.draw.rect(screen, (92, 214, 108),
                         (S(20), S(58), S(210) * max(0.0, p["hp"] / st["hp_max"]), S(11)))
        screen.blit(self.font_small.render(
            f"{max(0, math.ceil(p['hp']))}/{int(st['hp_max'])}", True, (255, 255, 255)),
            (S(236), S(56)))
        # mana
        pygame.draw.rect(screen, (28, 28, 36), (S(20), S(73), S(210), S(9)))
        pygame.draw.rect(screen, (60, 120, 220),
                         (S(20), S(73), S(210) * max(0.0, p["mp"] / st["mp_max"]), S(9)))
        screen.blit(self.font_small.render(
            f"{int(p['mp'])}/{int(st['mp_max'])} MP", True, (200, 220, 255)), (S(236), S(70)))
        screen.blit(self.font_small.render(f"Золото: {p['gold']}", True, GOLD),
                    (S(20), S(88)))
        screen.blit(self.font_small.render(
            f"Атака {int(st['atk'])}   Защита {int(st['def'])}   Крит {st['crit_chance']:.0f}%",
            True, (232, 200, 170)), (S(120), S(88)))

        # minimap + region
        mm = pygame.transform.scale(self.minimap, (S(200), S(102)))
        screen.blit(mm, (S(10), S(120)))
        pygame.draw.rect(screen, UI_EDGE, (S(10), S(120), S(200), S(102)), 1)
        mx = S(10) + int(p["x"] / W.MAP_W * S(200))
        my = S(120) + int(p["y"] / W.MAP_H * S(102))
        pygame.draw.circle(screen, (255, 255, 255), (mx, my), S(3))
        pygame.draw.circle(screen, (255, 90, 90), (mx, my), S(3), 1)
        region = g.region_at(p["x"], p["y"])
        screen.blit(self.font_small.render(region["name"] if region else "—", True,
                                           (214, 226, 246)), (S(216), S(122)))
        screen.blit(self.font_small.render(
            f"Исследовано: {len(g.visited)}/{len(g.world.regions)}", True, (168, 186, 212)),
            (S(216), S(140)))
        screen.blit(self.font_small.render(
            f"Убито: {sum(g.kills.values())}    Смертей: {g.deaths}", True, (168, 186, 212)),
            (S(216), S(158)))
        buffs = ", ".join(f"{k} {int(v['t'])}с" for k, v in p["buffs"].items())
        if buffs:
            screen.blit(self.font_small.render("Эффекты: " + buffs, True, (200, 240, 200)),
                        (S(216), S(176)))

        # hotbar
        hb_y = self.height - S(96)
        hotbar = p["hotbar"]
        for i in range(G.HOTBAR_KEYS):
            x = self.width // 2 - S(G.HOTBAR_KEYS * 62) // 2 + i * S(62)
            rect = pygame.Rect(x, hb_y, S(56), S(56))
            ready = i < len(hotbar)
            pygame.draw.rect(screen, (22, 26, 38) if ready else (16, 18, 26), rect,
                             border_radius=S(6))
            pygame.draw.rect(screen, (250, 220, 130) if ready else (62, 70, 88), rect, 2,
                             border_radius=S(6))
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
                    txt = self.font_small.render(f"{cd:.1f}", True, (255, 240, 200))
                    screen.blit(txt, (x + S(28) - txt.get_width() / 2, hb_y + S(20)))
                key = self.font_small.render(str(i + 1), True, (230, 236, 250))
                screen.blit(key, (x + S(4), hb_y + S(38)))
                if p["mp"] < ab["mana"]:
                    screen.blit(self.font_small.render(str(ab["mana"]), True, (120, 160, 255)),
                                (x + S(38), hb_y + S(38)))

        # toasts
        ty = self.height - S(150)
        for t in reversed(g.toasts[-4:]):
            a = (t["t"] / 0.2 if t["t"] < 0.2
                 else (t["life"] - t["t"]) / 0.6 if t["t"] > t["life"] - 0.6 else 1)
            surf = pygame.Surface((S(520), S(26)), pygame.SRCALPHA)
            pygame.draw.rect(surf, (10, 12, 18, int(210 * a)), (0, 0, S(520), S(26)),
                             border_radius=S(4))
            screen.blit(surf, (S(10), ty))
            txt = self.font_small.render(t["text"], True, pygame.Color(t["color"]))
            txt.set_alpha(int(255 * a))
            screen.blit(txt, (S(20), ty + S(7)))
            ty -= S(30)

        # active quest tracker (below the minimap so it does not cover it)
        active = [q for q in g.quests if not q["done"]][:3]
        if active:
            qy = S(236)
            for q in active:
                screen.blit(self.font_small.render(f"[ ] {q['title']}  {q['progress']}/{q['goal']}",
                                                   True, (222, 232, 246)), (S(14), qy))
                qy += S(18)

        # hints
        screen.blit(self.font_small.render(
            "WASD — движение   ПРОБЕЛ — атака   1–9 — умения   E — говорить/торговля   "
            "I — сумка   K — дуб навыков   Q — квесты   F5/F9 — сохранить/загрузить   F10 — меню",
            True, (196, 210, 234)), (S(10), self.height - S(22)))

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
        screen.blit(self.font_big.render("Сумка", True, (250, 240, 210)), (x + pad, y + pad))
        screen.blit(self.font_small.render(
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
                    cnt = self.font_small.render(str(slot["count"]), True, (255, 255, 255))
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
            screen.blit(self.font.render(data["name"], True, (252, 244, 216)),
                        (px + S(58), py + S(12)))
            screen.blit(self.font_small.render(data["desc"], True, (182, 198, 222)),
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
                screen.blit(self.font_small.render(line, True, (232, 214, 160)),
                            (px + S(12), py + S(62 + i * 18)))
            hint = {"consumable": "E — использовать", "weapon": "E — взять в руку",
                    "armor": "E — надеть", "ring": "E — надеть кольцо"}.get(
                        data["kind"], "Материал: продай торговцу")
            screen.blit(self.font_small.render(hint, True, (140, 200, 255)),
                        (px + S(12), py + S(168)))
        else:
            screen.blit(self.font_small.render("Пустой слот", True, (140, 152, 176)),
                        (px + S(12), py + S(10)))

        eq_y = py + S(208)
        self.panel(screen, (px, eq_y, S(286), S(140)), fill=(16, 20, 30, 236),
                   border=(90, 108, 142), radius=S(6))
        screen.blit(self.font.render("Экипировка", True, (252, 244, 216)), (px + S(12), eq_y + S(8)))
        for i, (key, label) in enumerate((("weapon", "Оружие"), ("armor", "Броня"),
                                          ("ring", "Кольцо"), ("amulet", "Амулет"))):
            item_id = g.player["equip"].get(key)
            name = IT.item_name(item_id) if item_id else "—"
            screen.blit(self.font_small.render(f"{label}: {name}", True, (206, 220, 240)),
                        (px + S(12), eq_y + S(32 + i * 20)))
        st = g.stats()
        screen.blit(self.font_small.render(
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
        screen.blit(self.font_big.render("Торговец", True, (252, 240, 200)),
                    (x + S(18), y + S(14)))
        screen.blit(self.font_small.render(
            f"Золото: {g.player['gold']}   •   TAB — продать/купить   •   стрелки — выбор   •   "
            "E / Enter — сделка   •   R — продать все материалы   •   ESC — выйти",
            True, (196, 212, 236)), (x + S(18), y + S(44)))
        for i, (tab, label) in enumerate((("sell", "Продать"), ("buy", "Купить"))):
            rect = pygame.Rect(x + S(18) + i * S(130), y + S(72), S(120), S(32))
            active = g.shop_tab == tab
            pygame.draw.rect(screen, (44, 36, 20) if active else (22, 26, 38), rect)
            pygame.draw.rect(screen, (248, 226, 152) if active else (90, 100, 124), rect, 2)
            screen.blit(self.font.render(label, True,
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
            screen.blit(self.font_small.render(data["name"], True,
                                               (255, 236, 158) if sel else (216, 226, 240)),
                        (rect[0] + S(38), rect[1] + S(7)))
            screen.blit(self.font_small.render(f"x{count}", True, (170, 190, 216)),
                        (rect[0] + S(360), rect[1] + S(7)))
            price_col = (240, 210, 120) if (g.shop_tab == "sell" or
                                            g.player["gold"] >= price) else (220, 120, 120)
            screen.blit(self.font_small.render(
                ("+" if g.shop_tab == "sell" else "−") + f"{price} золота", True, price_col),
                (rect[0] + S(470), rect[1] + S(7)))
            screen.blit(self.font_small.render(data["desc"][:52], True, (166, 182, 206)),
                        (rect[0] + S(620), rect[1] + S(7)))
        if not lines:
            screen.blit(self.font.render(
                "Нечего продавать — принеси трофеи с монстров" if g.shop_tab == "sell"
                else "Товар закончился", True, (200, 180, 160)),
                (x + S(24), list_y + S(20)))
        elif len(lines) > 12:
            screen.blit(self.font_small.render(f"… и ещё {len(lines) - 12} позиций",
                                               True, (170, 186, 210)),
                        (x + S(24), list_y + S(12 * 34) + S(4)))
        screen.blit(self.font_small.render(
            "Торговец платит 45% цены и берёт 160% за свой товар.", True, (176, 192, 216)),
            (x + S(18), y + h - S(28)))

    # ------------------------------------------------------------- quest log
    def draw_quests(self, screen) -> None:
        g, S = self.game, self.s
        h = S(52 + len(g.quests) * 52)
        x, y = S(430), S(70)
        self.panel(screen, (x, y, S(660), h), fill=(12, 15, 24, 240), border=(140, 170, 220),
                   radius=S(6))
        screen.blit(self.font_big.render("Журнал квестов", True, (255, 255, 255)),
                    (x + S(16), y + S(14)))
        screen.blit(self.font_small.render("Q — закрыть", True, (170, 186, 210)),
                    (x + S(400), y + S(22)))
        yy = y + S(52)
        for q in g.quests:
            col = (144, 224, 144) if q["done"] else (232, 232, 242)
            screen.blit(self.font.render(("[готово] " if q["done"] else "[ ] ") + q["title"],
                                         True, col), (x + S(16), yy))
            screen.blit(self.font_small.render(q["desc"], True, (174, 190, 214)),
                        (x + S(30), yy + S(22)))
            screen.blit(self.font_small.render(f"{q['progress']}/{q['goal']}", True,
                                               (120, 200, 255)), (x + S(560), yy + S(22)))
            yy += S(52)

    # --------------------------------------------------------- the oak screen
    def draw_skill_tree(self, screen) -> None:
        g, S = self.game, self.s
        screen.blit(pygame.Surface((self.width, self.height), pygame.SRCALPHA), (0, 0))
        dim = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        dim.fill((8, 10, 18, 210))
        screen.blit(dim, (0, 0))
        area_x, area_y = S(24), S(56)
        area_w, area_h = self.width - S(24) * 2 - S(340), self.height - S(56) - S(56)
        oak = build_oak(area_w, area_h)
        screen.blit(oak, (area_x, area_y))
        pygame.draw.rect(screen, (150, 128, 78), (area_x - 4, area_y - 4,
                                                  area_w + 8, area_h + 8), 2)
        screen.blit(self.font_title.render("Дуб навыков", True, (255, 238, 176)),
                    (area_x, S(6)))
        screen.blit(self.font_small.render(
            f"Очки навыков: {g.skill_points}   •   стрелки / WASD — по ветвям   •   "
            "Enter — изучить   •   K / ESC — закрыть", True, (200, 214, 236)),
            (area_x + S(330), S(24)))

        learned = g.player["learned"]
        # requirement links first, so nodes draw on top
        for node in SK.SKILLS:
            nx, ny = SK.position_of(node)
            for req in node["req"]:
                parent = SK.by_id(req)
                if not parent:
                    continue
                px_, py_ = SK.position_of(parent)
                both = req in learned and node["id"] in learned
                col = (240, 210, 120) if both else (110, 104, 96)
                pygame.draw.line(screen, col,
                                 (area_x + px_ * area_w, area_y + py_ * area_h),
                                 (area_x + nx * area_w, area_y + ny * area_h),
                                 3 if both else 2)
        self.tree_rects = []
        mouse = pygame.mouse.get_pos()
        hovered = None
        for node in SK.SKILLS:
            nx, ny = SK.position_of(node)
            cx = area_x + nx * area_w
            cy = area_y + ny * area_h
            rect = pygame.Rect(cx - S(22), cy - S(22), S(44), S(44))
            self.tree_rects.append((rect, node["id"]))
            if rect.collidepoint(mouse):
                hovered = node["id"]
            done = node["id"] in learned
            avail = g.can_learn(node["id"])
            branch = next((b for b in SK.BRANCHES if b["id"] == node["branch"]), None)
            col = tuple(branch["color"]) if branch else (200, 190, 150)
            if done:
                pygame.draw.circle(screen, (30, 44, 28), (int(cx), int(cy)), S(21))
                pygame.draw.circle(screen, (240, 210, 120), (int(cx), int(cy)), S(21), 4)
            elif avail:
                pulse = 3 + int(2 * (0.5 + 0.5 * math.sin(self.t * 4)))
                pygame.draw.circle(screen, (22, 26, 38), (int(cx), int(cy)), S(20))
                pygame.draw.circle(screen, col, (int(cx), int(cy)), S(20), pulse)
            else:
                pygame.draw.circle(screen, (18, 20, 26), (int(cx), int(cy)), S(19))
                pygame.draw.circle(screen, (96, 100, 112), (int(cx), int(cy)), S(19), 2)
            icon = SP.item_icon_surface(node["icon"])
            if not (done or avail):
                icon = icon.copy()
                icon.fill((120, 120, 130, 0), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(pygame.transform.scale(icon, (S(32), S(32))),
                        (cx - S(16), cy - S(16)))
            if node["kind"] == "active":
                pygame.draw.circle(screen, (120, 200, 255), (int(cx + S(17)), int(cy - S(17))), S(5))
            if node["id"] == g.tree_cursor:
                pygame.draw.circle(screen, (255, 255, 255), (int(cx), int(cy)), S(25), 3)
                arrow = S(8 + int(3 * (0.5 + 0.5 * math.sin(self.t * 6))))
                pygame.draw.polygon(screen, (255, 240, 170),
                                    [(cx, cy - S(29) - arrow), (cx - S(9), cy - S(29)),
                                     (cx + S(9), cy - S(29))])
            elif hovered == node["id"]:
                pygame.draw.circle(screen, (255, 255, 255), (int(cx), int(cy)), S(25), 2)

        focus = SK.by_id(hovered or g.tree_cursor) or SK.ROOT
        panel_x = self.width - S(340) + S(12)
        self.panel(screen, (panel_x, S(56), S(316), self.height - S(112)),
                   fill=(14, 17, 26, 244), border=(180, 158, 100), radius=S(8))
        branch = next((b for b in SK.BRANCHES if b["id"] == focus["branch"]), None)
        branch_name = branch["name"] if branch else "Ствол"
        branch_col = tuple(branch["color"]) if branch else (220, 210, 160)
        screen.blit(self.font_big.render(focus["name"], True, (255, 240, 200)),
                    (panel_x + S(14), S(70)))
        screen.blit(self.font_small.render(f"Ветвь: {branch_name}   •   уровень {focus['tier']}",
                                           True, branch_col), (panel_x + S(14), S(100)))
        screen.blit(self.font_small.render(focus["desc"], True, (208, 220, 238)),
                    (panel_x + S(14), S(124)))
        kind = "Активное умение (слот в панели)" if focus["kind"] == "active" else "Пассивное умение"
        screen.blit(self.font_small.render(kind, True, (150, 200, 255)),
                    (panel_x + S(14), S(168)))
        screen.blit(self.font_small.render(f"Стоимость: {focus['cost']} очк.",
                                           True, (240, 210, 140)), (panel_x + S(14), S(190)))
        if focus["req"]:
            reqs = ", ".join(SK.by_id(r)["name"] for r in focus["req"] if SK.by_id(r))
            screen.blit(self.font_small.render("Требует: " + reqs, True, (190, 200, 216)),
                        (panel_x + S(14), S(212)))
        state = ("Изучено" if focus["id"] in learned
                 else "Доступно — Enter" if g.can_learn(focus["id"])
                 else "Заперто")
        state_col = ((150, 240, 150) if focus["id"] in learned
                     else (255, 230, 150) if g.can_learn(focus["id"]) else (200, 160, 160))
        screen.blit(self.font.render(state, True, state_col), (panel_x + S(14), S(244)))
        screen.blit(self.font_small.render(
            "зелёная точка — активное умение, золотое кольцо — изучено",
            True, (170, 186, 210)), (panel_x + S(14), S(266)))

        yy = S(292)
        screen.blit(self.font.render("Ветви:", True, (240, 232, 200)), (panel_x + S(14), yy))
        yy += S(26)
        for b in SK.BRANCHES:
            nodes = SK.branch_skills(b["id"])
            done = sum(1 for n in nodes if n["id"] in learned)
            screen.blit(self.font_small.render(f"{b['name']}: {done}/{len(nodes)}",
                                               True, tuple(b["color"])), (panel_x + S(14), yy))
            bar_w = S(180)
            pygame.draw.rect(screen, (26, 30, 40), (panel_x + S(100), yy + S(4), bar_w, S(8)))
            pygame.draw.rect(screen, tuple(b["color"]),
                             (panel_x + S(100), yy + S(4), bar_w * done / len(nodes), S(8)))
            yy += S(22)
        yy += S(10)
        screen.blit(self.font_small.render("Активные умения:", True, (240, 232, 200)),
                    (panel_x + S(14), yy))
        yy += S(22)
        for i, key in enumerate(g.player["hotbar"][:G.HOTBAR_KEYS]):
            ab = G.ABILITIES[key]
            screen.blit(self.font_small.render(
                f"{i + 1}. {ab['name']}   мана {ab['mana']}", True, (196, 214, 240)),
                (panel_x + S(14), yy))
            yy += S(18)
        screen.blit(self.font_small.render(
            f"Всего изучено: {len(learned)}/{len(SK.SKILLS)}", True, (230, 220, 180)),
            (panel_x + S(14), self.height - S(76)))

    # ----------------------------------------------------------------- dialog
    def draw_dialog(self, screen) -> None:
        if not self.game.dialog:
            return
        d, S = self.game.dialog, self.s
        w, h = S(720), S(110)
        x, y = (self.width - w) / 2, self.height - h - S(120)
        self.panel(screen, (int(x), int(y), w, h), fill=(10, 13, 22, 244),
                   border=(226, 202, 132), radius=S(8))
        screen.blit(self.font_big.render(d["name"], True, (255, 226, 140)),
                    (x + S(20), y + S(12)))
        screen.blit(self.font.render(d["line"], True, (240, 242, 250)),
                    (x + S(20), y + S(46)))
        hint = "E — закрыть" + ("   •   TAB — торговля" if d.get("shop") else "")
        screen.blit(self.font_small.render(hint, True, (162, 178, 202)),
                    (x + w - S(220), y + h - S(28)))

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
            cur = (i == selected) or (rect.collidepoint(mouse) and enabled)
            if cur and enabled:
                pygame.draw.rect(screen, (34, 28, 16), rect)
                pygame.draw.rect(screen, (248, 226, 152), rect, 2)
            col = ((255, 236, 158) if (cur and enabled)
                   else (204, 214, 232) if enabled else (104, 112, 128))
            txt = self.font_big.render(label, True, col)
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
            n = self.font_small.render(note, True, (186, 204, 228))
            screen.blit(n, (self.width / 2 - n.get_width() / 2, footer_y))
        ver = self.font_small.render("Пиксельное приключение — версия 2.0", True,
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
    p = game.player
    if key == pygame.K_i:
        game.overlay = "inventory"
        game.sound("menu_select", 0.5)
    elif key == pygame.K_k:
        game.overlay = "skilltree"
        game.sound("menu_select", 0.6)
    elif key == pygame.K_q:
        game.overlay = "quests"
        game.sound("menu_move", 0.5)
    elif key == pygame.K_e:
        if game.dialog:
            if game.dialog.get("shop"):
                game.dialog = None
                game.open_shop()
            else:
                game.dialog = None
        else:
            game.interact()
    elif key == pygame.K_TAB and game.dialog and game.dialog.get("shop"):
        game.dialog = None
        game.open_shop()
    elif key == pygame.K_SPACE:
        game.attack()
    elif key == pygame.K_F5:
        game.save()
    elif key == pygame.K_F9:
        game.load()
    elif key == pygame.K_a:
        game.use_potion_hotkey()
    elif pygame.K_1 <= key <= pygame.K_9:
        game.cast(key - pygame.K_1)


def run() -> int:
    pygame.init()
    pygame.display.set_caption("Pixel RPG Adventure 2.0")
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
            entries = [(f"{w} x {h}" + ("   (Full HD)" if (w, h) == (1920, 1080) else ""), True)
                       for (w, h, _z) in G.RESOLUTIONS]
            entries.append((f"Полный экран: {'включён' if fullscreen else 'выключен'}", True))
            entries.append(("Назад", True))

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
                game.update(dt, G.gather_input(pygame.key.get_pressed()))
            else:
                game.update(dt, {"up": False, "down": False, "left": False, "right": False})
            renderer.draw(screen)
        elif state == "title":
            renderer.draw_menu(screen, "Пиксельное приключение",
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
            renderer.draw_menu(screen, "Настройки", "Разрешение экрана и режим окна",
                               entries, selected, backdrop=False,
                               note=note or "Enter — применить     Esc — назад")
        pygame.display.flip()

    game.save()
    G.save_config({"res_index": res_index, "fullscreen": fullscreen})
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
