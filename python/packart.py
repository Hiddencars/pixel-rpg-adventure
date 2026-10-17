"""Sprite sheets from the Ninja Adventure asset pack (CC0, by Pixel-Boy).

The pack draws 16x16 actors: 4 columns = down / up / left / right, and one row per
walk frame (characters have 7, monsters 4, most animals 4). We re-cut them into the
same keys the procedural sprite builder already produces — ``<kind>_<view>_<frame>``
plus a flipped ``_f`` side view — so the renderer needs no special cases.

Everything falls back to the procedural art when a sheet is missing, so the game
still runs if the assets folder is not packaged.
"""
from __future__ import annotations

import os
import sys

import pygame

PACK_SCALE = 3                     # 16 px art -> 48 px, about 1.5 tiles of 32 px
CELL = 64                          # same canvas the procedural sprites use
FRAME_ROWS = (0, 2, 4)             # walk frames we use, out of the 4-7 available
VIEW_COL = {"down": 0, "up": 1, "side": 3}

# our game kind -> folder under assets/ninja
KINDS = {
    "hero", "peasant", "farmer", "smith", "merchant", "elder", "guard", "healer",
    "bandit", "imp", "golem", "skeleton",
    "bat", "bear", "brute", "goblin", "orc", "slime", "snake", "spider", "troll",
    "wraith",
    "boar", "chicken", "cow", "sheep", "wolf",
}

NPCS = {"peasant", "farmer", "smith", "merchant", "elder", "guard", "healer"}

_cache: dict[str, pygame.Surface] = {}
_loaded = False


def base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", "."), "assets", "ninja")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "ninja")


def _sheet_path(kind: str) -> str | None:
    folder = os.path.join(base_dir(), kind)
    if not os.path.isdir(folder):
        return None
    names = [n for n in os.listdir(folder) if n.lower().endswith(".png")]
    if not names:
        return None
    # prefer the plain sheet, then a white one, then anything
    def rank(n: str) -> tuple:
        low = n.lower()
        return ("side" in low, "sheet" not in low, "white" not in low, low)
    names.sort(key=rank)
    return os.path.join(folder, names[0])


def _cut(img: pygame.Surface, col: int, row: int) -> pygame.Surface:
    w = min(16, img.get_width() - col * 16)
    h = min(16, img.get_height() - row * 16)
    cell = img.subsurface(pygame.Rect(col * 16, row * 16, w, h)).copy()
    big = pygame.transform.scale(cell, (w * PACK_SCALE, h * PACK_SCALE))
    canvas = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
    canvas.blit(big, ((CELL - big.get_width()) // 2, CELL - big.get_height()))
    return canvas


def build() -> dict[str, pygame.Surface]:
    """All pack sprites, keyed like the procedural ones."""
    global _loaded
    if _loaded:
        return _cache
    _loaded = True
    for kind in sorted(KINDS):
        path = _sheet_path(kind)
        if not path:
            continue
        try:
            img = pygame.image.load(path).convert_alpha()
        except Exception:
            continue
        rows = img.get_height() // 16
        cols = max(1, img.get_width() // 16)
        if rows <= 1:
            # farm animals ship as a single side-view strip of one or two frames
            for idx in range(min(2, cols)):
                surf = _cut(img, idx, 0)
                flip = pygame.transform.flip(surf, True, False)
                _cache[f"{kind}_side_{idx}"] = surf
                _cache[f"{kind}_side_{idx}_f"] = flip
                _cache[f"{kind}_down_{idx}"] = surf
                _cache[f"{kind}_up_{idx}"] = surf
            continue
        frames = [r for r in FRAME_ROWS if r < rows] or [0]
        for view, col in VIEW_COL.items():
            if col >= cols:
                continue
            for idx, row in enumerate(frames):
                surf = _cut(img, col, row)
                _cache[f"{kind}_{view}_{idx}"] = surf
                if kind in NPCS:            # villagers are keyed npc_<kind>_<frame>
                    _cache[f"npc_{kind}_{view}_{idx}"] = surf
                    if view == "down":
                        _cache[f"npc_{kind}_{idx}"] = surf
                if view == "side":
                    flip = pygame.transform.flip(surf, True, False)
                    _cache[f"{kind}_{view}_{idx}_f"] = flip
                    if kind in NPCS:
                        _cache[f"npc_{kind}_{view}_{idx}_f"] = flip
    return _cache


def available() -> bool:
    return bool(build())
