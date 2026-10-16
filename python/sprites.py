#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pixel art for Pixel RPG Adventure 1.3.

All character sprites are 32x32 (double the v1.2 size) with real detail:
outlines, shading, faces, clothing folds. The tile/object art lives in game.py
and is drawn procedurally with the same palette.

Rows are validated at import time — a typo raises immediately instead of
silently producing a broken sprite.
"""

from __future__ import annotations

import pygame

SPRITE = 32          # character sprite size (was 16 in v1.2)

# ---------------------------------------------------------------- palette ---
PAL: dict[str, tuple[int, int, int] | None] = {
    ".": None,
    "k": (26, 22, 30),        # outline
    "K": (14, 12, 18),        # deep shadow
    # skin
    "s": (240, 196, 156), "S": (206, 158, 118), "d": (170, 124, 90),
    # hair
    "h": (74, 46, 28), "H": (110, 74, 44), "j": (48, 30, 18),
    # eyes
    "e": (34, 28, 36), "w": (248, 248, 252),
    # hero clothing
    "r": (176, 58, 48), "R": (216, 92, 68), "t": (134, 40, 36),
    "b": (58, 86, 170), "B": (42, 62, 132), "n": (34, 50, 108),
    # metal / weapons
    "m": (176, 182, 196), "M": (226, 232, 240), "i": (108, 114, 128),
    # goblin
    "g": (96, 154, 78), "G": (128, 186, 104), "q": (66, 112, 54),
    "y": (232, 214, 120), "Y": (250, 240, 190),
    "o": (196, 60, 52),       # goblin eyes / cloth accent
    "f": (188, 152, 96), "F": (214, 180, 122),   # goblin cloth
    # npc clothing
    "a": (208, 178, 104), "A": (232, 206, 136),  # hat
    "c": (150, 118, 84),  "C": (182, 148, 108),  # tunic
    "u": (96, 72, 52),    "U": (128, 100, 72),   # trousers
    # mage
    "v": (128, 78, 178), "V": (162, 112, 210), "z": (88, 50, 128),
    "p": (248, 248, 255),  # robe trim / white
}

# ---------------------------------------------------------------- sprites ---
# Hero — facing the camera
P_DOWN_1 = [
    "................................",
    "................................",
    "................................",
    "................................",
    "...........kkkkkkkkkk...........",
    ".........kkhhhhhhhhhhkk.........",
    "........khhhhhhhhhhhhhhk........",
    ".......khhhhhhhhhhhhhhhhk.......",
    ".......khhHHHHHHHHHHHHhhk.......",
    ".......khHHHHHHHHHHHHHHhk.......",
    ".......khhssssssssssssshk.......",
    ".......khsssssssssssssssk.......",
    ".......kssssssssssssssssk.......",
    ".......kssseeksssseeksssk.......",
    ".......kssseeksssseeksssk.......",
    ".......kssssssssssssssssk.......",
    ".......ksssssSSSSSSsssssk.......",
    "........kssssssssssssssk........",
    ".........kssssssssssssk.........",
    "..........kkkkkkkkkkkk..........",
    ".........kRRrrrrrrrrRRk.........",
    "........kRrrrrrrrrrrrrRk........",
    ".......kRrrrrttttrrrrrrRk.......",
    ".......kRrrrrttttrrrrrrRk.......",
    "......ksRrrrttttttrrrrrRsk......",
    "......ksRrrrttttttrrrrrRsk......",
    "......ksrrrrttttttrrrrrrsk......",
    "......ksbrrrrrttrrrrrrrbsk......",
    "......kkbbbbbbbbbbbbbbbbkk......",
    "........kbbbbk....kbbbbk........",
    "........kbbbk......kbbbk........",
    "........kkkkk......kkkkk........",
]
P_DOWN_2 = P_DOWN_1[:28] + [
    "......kkbbbbbbbbbbbbbbbbkk......",
    ".......kbbbbk......kbbbbk.......",
    "......kbbbbk........kbbbbk......",
    "......kkkkk..........kkkkk......",
]

# Hero — back view
P_UP_1 = [
    "................................",
    "................................",
    "................................",
    "................................",
    "...........kkkkkkkkkk...........",
    ".........kkhhhhhhhhhhkk.........",
    "........khhhhhhhhhhhhhhk........",
    ".......khhhhhhhhhhhhhhhhk.......",
    ".......khhhhhhhhhhhhhhhhk.......",
    ".......khhhHHHHHHHHHHhhhk.......",
    ".......khhhhHHHHHHHHhhhhk.......",
    ".......khhhhhhhhhhhhhhhhk.......",
    ".......khhhhhhhhhhhhhhhhk.......",
    ".......khhhhhhhhhhhhhhhhk.......",
    ".......khhhhhhhhhhhhhhhhk.......",
    ".......khhhhhhhhhhhhhhhhk.......",
    ".......khhhhhhhhhhhhhhhhk.......",
    "........khhhhhhhhhhhhhhk........",
    ".........khhhhhhhhhhhhk.........",
    "..........kkkkkkkkkkkk..........",
    ".........kRRrrrrrrrrRRk.........",
    "........kRrrrrrrrrrrrrRk........",
    ".......kRrrrrttttrrrrrrRk.......",
    ".......kRrrrrttttrrrrrrRk.......",
    "......ksRrrrttttttrrrrrRsk......",
    "......ksRrrrttttttrrrrrRsk......",
    "......ksrrrrttttttrrrrrrsk......",
    "......ksbrrrrrttrrrrrrrbsk......",
    "......kkbbbbbbbbbbbbbbbbkk......",
    "........kbbbbk....kbbbbk........",
    "........kbbbk......kbbbk........",
    "........kkkkk......kkkkk........",
]
P_UP_2 = P_UP_1[:28] + [
    "......kkbbbbbbbbbbbbbbbbkk......",
    ".......kbbbbk......kbbbbk.......",
    "......kbbbbk........kbbbbk......",
    "......kkkkk..........kkkkk......",
]

# Hero — side view (facing right)
P_SIDE_1 = [
    "................................",
    "................................",
    "................................",
    "................................",
    "...........kkkkkkkkkk...........",
    ".........kkhhhhhhhhhhkk.........",
    "........khhhhhhhhhhhhhhk........",
    ".......khhhhhhhhhhhhhhhhk.......",
    ".......khhhhhhhhhhhHHHHhk.......",
    ".......khhhhhhhhhhHHHHHhk.......",
    ".......khhhssssssssssssh........",
    ".......khhsssssssssssss.........",
    ".......khssssssssssssss.........",
    ".......khsssesssssssssss........",
    ".......khsssesssssssssss........",
    ".......khssssssssssssss.........",
    ".......khsssssSSSSssssss........",
    "........khssssssssssss..........",
    ".........kssssssssssss..........",
    "..........kkkkkkkkkkk...........",
    ".........kRRrrrrrrrRRk..........",
    "........kRrrrrrrrrrrRk..........",
    ".......kRrrrrttttrrrrRk.........",
    ".......kRrrrrttttrrrrRk.........",
    "......ksRrrrttttttrrrrRsk.......",
    "......ksRrrrttttttrrrrRsk.......",
    "......ksrrrrttttttrrrrsk........",
    "......ksbrrrrtttrrrrrbsk........",
    "......kkbbbbbbbbbbbbbbkk........",
    "........kbbbbk....kbbbk.........",
    "........kbbbk......kbbk.........",
    "........kkkkk......kkkk.........",
]
P_SIDE_2 = P_SIDE_1[:28] + [
    "......kkbbbbbbbbbbbbbbkk........",
    ".......kbbbbk....kbbbbk.........",
    "......kbbbbk......kbbbbk........",
    "......kkkkk........kkkkk........",
]

# Goblin
G_1 = [
    "................................",
    "................................",
    "................................",
    "................................",
    ".......k................k.......",
    "......kqk..............kqk......",
    "......kqk..............kqk......",
    "......kqkkkkkkkkkkkkkkkkqk......",
    ".....kqgGGGGGGGGGGGGGGgqk.......",
    ".....kggGGGGGGGGGGGGGggk........",
    "....kggggGGGGGGGGGGggggk........",
    "....kggggggggggggggggggk........",
    "....kggooggggggoogggggggk.......",
    "....kggooggggggoogggggggk.......",
    "....kggggggggggggggggggk........",
    "....kggggyYYYYYYyggggggk........",
    "....kggggggggggggggggggk........",
    ".....kggggggggggggggggk.........",
    "......kkggggggggggggkk..........",
    ".......kkkkkkkkkkkkkk...........",
    "......kffFFffffFFffffk..........",
    ".....kffFFffffFFfffffk..........",
    "....kgffFFffffFFfffffgk.........",
    "....kggffffffffffffffggk........",
    "...kqggffffffffffffffggqk.......",
    "...kqggffffffffffffffggqk.......",
    "...kqgggffffffffffffgggqk.......",
    "....kkqgggggggggggggqkk.........",
    "......kkggggkkkggggkk...........",
    ".......kggkk....kkggk...........",
    "......kggk........kggk..........",
    "......kkk..........kkk..........",
]
G_2 = G_1[:28] + [
    "......kkggggkkkggggkk...........",
    ".....kggkk......kkggk...........",
    "....kggk..........kggk..........",
    "....kkk............kkk..........",
]

# Goblin brute — bigger, armoured
GB_1 = [
    "................................",
    "................................",
    "................................",
    ".....k..................k.......",
    "....kqk................kqk......",
    "...kqqkkkkkkkkkkkkkkkkkkqqk.....",
    "...kqgGGGGGGGGGGGGGGGGGGgqk.....",
    "..kqggGGGGGGGGGGGGGGGGGGggqk....",
    "..kggggGGGGGGGGGGGGGGGGggggk....",
    "..kgggggggggggggggggggggggggk...",
    "..kgggggggggggggggggggggggggk...",
    "..kggoogggggggggggoogggggggk....",
    "..kggoogggggggggggoogggggggk....",
    "..kggggggggggggggggggggggggk....",
    "..kgggggyYYYYYYYYYYyggggggk.....",
    "..kggggggyYYYYYYYYygggggggk.....",
    "..kggggggggggggggggggggggk......",
    "...kggggggggggggggggggggk.......",
    "....kkggggggggggggggggkk........",
    "......kkkkkkkkkkkkkkkkk.........",
    "....kmffffffffffffffffmk........",
    "...kmMffffffffffffffffMmk.......",
    "..kgmMffffffffffffffffMmgk......",
    "..kggmffffffffffffffffmggk......",
    ".kqggmffffffffffffffffmggqk.....",
    ".kqggmffffffffffffffffmggqk.....",
    ".kqggmffffffffffffffffmggqk.....",
    "..kkqmffffffffffffffffmqkk......",
    "....kkmffffffffffffmmkk.........",
    "....kggmmkkkkkkkkmmggk..........",
    "...kggkk..........kkggk.........",
    "...kkk..............kkk.........",
]
GB_2 = GB_1[:28] + [
    "..kkqmffffffffffffffffmqkk......",
    "....kkmffffffffffffffmmkk.......",
    "...kggmmkkkkkkkkkkmmggk.........",
    "...kkk..............kkk.........",
]

# Villager NPC
NPC_1 = [
    "................................",
    "................................",
    "................................",
    "................................",
    "..........kkkkkkkkkk............",
    "........kkaaaaaaaaaakk..........",
    ".......kaaaaaaaaaaaaaak.........",
    "......kaaaaaaaaaaaaaaaak........",
    "......kaAAaaaaaaaaaaaaaak.......",
    "......kkaaaaaaaaaaaaaaakk.......",
    "........kssssssssssssk..........",
    "........kssssssssssssk..........",
    "........kssssssssssssk..........",
    "........kseessssseessk..........",
    "........kseessssseessk..........",
    "........kssssssssssssk..........",
    "........ksssssSSSssssk..........",
    ".........kssssssssssk...........",
    "..........kssssssssk............",
    "..........kkkkkkkkkk............",
    "........kkCCccccccCCkk..........",
    ".......kCccccccccccccCk.........",
    "......ksCccccuuuuccccCsk........",
    "......ksCccccuuuuccccCsk........",
    "......kscccccuuuucccccsk........",
    "......kscccccuuuucccccsk........",
    "......ksccccccuuccccccsk........",
    "......kkccccccuucccccckk........",
    ".......kkuuuuuuuuuuuukk.........",
    "........kuuuuk..kuuuuk..........",
    "........kuuuk....kuuuk..........",
    "........kkkkk....kkkkk..........",
]
NPC_2 = NPC_1[:28] + [
    ".......kkuuuuuuuuuuuukk.........",
    "........kuuuuk....kuuuk.........",
    ".......kuuuk......kuuuk.........",
    ".......kkkkk......kkkkk.........",
]

# Elder mage
MAGE_1 = [
    "................................",
    "................................",
    "............kkkkkk..............",
    "..........kkVVVVVVkk............",
    ".........kVVVVVVVVVVk...........",
    "........kVVVVVVVVVVVVk..........",
    "........kVVzzzzzzzzVVk..........",
    ".......kkVVVVVVVVVVVVkk.........",
    "......kzzVVVVVVVVVVVVzzk........",
    ".....kzzzzzzzzzzzzzzzzzzk.......",
    ".....kzzkkkkkkkkkkkkkkzzk.......",
    ".....kzkssssssssssssskzzk.......",
    ".....kzkssssssssssssskzzk.......",
    ".....kzkseessssseesskkzzk.......",
    ".....kzkseessssseesskkzzk.......",
    ".....kzkssssssssssssskzzk.......",
    ".....kzkssssSSSSSsssskzzk.......",
    ".....kzzkssssssssssskzzk........",
    "......kzzzksssssssskzzzk........",
    ".......kzzzkkkkkkkkzzzk.........",
    "......kvvvvvvvvvvvvvvvvk........",
    ".....kvvvvvvvvvvvvvvvvvvk.......",
    "....kvvvvvvvvvvvvvvvvvvvvk......",
    "...kvvvvvvvvvvvvvvvvvvvvvvk.....",
    "...kvvvvvvpppppppppvvvvvvvk.....",
    "...kvvvvvvpppppppppvvvvvvvk.....",
    "...kvvvvvvpppppppppvvvvvvvk.....",
    "...kvvvvvvpppppppppvvvvvvvk.....",
    "...kvvvvvvvvvvvvvvvvvvvvvvk.....",
    "...kvvvvvvvvvvvvvvvvvvvvvvk.....",
    "...kkvvvvvvvvvvvvvvvvvvvvkk.....",
    "....kkkkkkkkkkkkkkkkkkkkkk......",
]
MAGE_2 = MAGE_1[:30] + [
    "....kkvvvvvvvvvvvvvvvvvvkk......",
    ".....kkkkkkkkkkkkkkkkkkkk.......",
]

SPRITES: dict[str, list[str]] = {
    "p_down_1": P_DOWN_1, "p_down_2": P_DOWN_2,
    "p_up_1": P_UP_1, "p_up_2": P_UP_2,
    "p_side_1": P_SIDE_1, "p_side_2": P_SIDE_2,
    "g_1": G_1, "g_2": G_2,
    "gb_1": GB_1, "gb_2": GB_2,
    "npc_1": NPC_1, "npc_2": NPC_2,
    "mage_1": MAGE_1, "mage_2": MAGE_2,
}

# ------------------------------------------------------------------ items ---
# 16x16 item icons, drawn by hand (shown in the inventory and on the ground).
ICON_POTION = [
    "................",
    "................",
    "......kkkk......",
    "......kwwk......",
    "......kwwk......",
    ".....kkwwkk.....",
    "....kkRRRRkk....",
    "...kRRrrrrRRk...",
    "...kRrrrrrrRk...",
    "...kRrrrrrrRk...",
    "...kRrrrrrrRk...",
    "...kRrrrrrrRk...",
    "...kkRrrrrRkk...",
    "....kkRRRRkk....",
    ".....kkkkkk.....",
    "................",
]
ICON_SWORD = [
    "................",
    ".............kk.",
    "............kMk.",
    "...........kMMk.",
    "..........kMMmk.",
    ".........kMMmk..",
    "........kMMmk...",
    ".......kMMmk....",
    "......kMMmk.....",
    ".....kMMmk......",
    "..kkkMmk........",
    ".kiMMMMk........",
    ".kiMMMkk........",
    "..kkik..........",
    "...kk...........",
    "................",
]
ICON_AXE = [
    "................",
    "..........kkk...",
    ".........kiiik..",
    "........kiMMMik.",
    "........kiMMMik.",
    ".........kiMik..",
    "..........kik...",
    "..........kik...",
    "..........kik...",
    "..........kik...",
    "..........kik...",
    "..........kik...",
    "..........kik...",
    "..........kik...",
    "..........kik...",
    "................",
]
ICON_ARMOR = [
    "................",
    "................",
    "....kkkkkkkk....",
    "...kmmmmmmmmk...",
    "..kmiiiiiiiimk..",
    ".kmiiiiiiiiiimk.",
    ".kmiiiiiiiiiimk.",
    ".kmiiiiiiiiiimk.",
    ".kmiiiiiiiiiimk.",
    "..kmiiiiiiiimk..",
    "..kmiiiiiiiimk..",
    "...kmmmmmmmmk...",
    "....kkkkkkkk....",
    "................",
    "................",
    "................",
]
ICON_GOLD = [
    "................",
    "................",
    "................",
    ".....kkkkkk.....",
    "....kyYYYYyk....",
    "...kyYYyyYYyk...",
    "...kYYykkyYYk...",
    "...kYYykkyYYk...",
    "...kyYYyyYYyk...",
    "....kyYYYYyk....",
    ".....kkkkkk.....",
    "................",
    "................",
    "................",
    "................",
    "................",
]
ICON_EAR = [
    "................",
    "................",
    ".......kk.......",
    "......kggk......",
    ".....kggggk.....",
    "....kggGGggk....",
    "....kgGGGGgk....",
    "....kgGGGGgk....",
    "....kggGGggk....",
    ".....kggggk.....",
    "......kggk......",
    ".......kk.......",
    "................",
    "................",
    "................",
    "................",
]
ICON_HERB = [
    "................",
    "................",
    ".......kk.......",
    "......kggk......",
    ".....kgGGgk.....",
    "....kgGGGGgk....",
    "...kgGGGGGGgk...",
    "....kgGGGGgk....",
    ".....kgGGgk.....",
    "......kggk......",
    ".......kk.......",
    "................",
    "................",
    "................",
    "................",
    "................",
]
ICON_KEY = [
    "................",
    "................",
    "......kkkk......",
    ".....kyyyyk.....",
    "....kyykkyyk....",
    "....kyykkyyk....",
    ".....kyyyyk.....",
    "......kyyk......",
    "......kyyk......",
    "......kyyk......",
    "......kyykk.....",
    "......kyyyk.....",
    "......kyyk......",
    "......kyyk......",
    "......kkkk......",
    "................",
]

ICONS = {
    "potion": ICON_POTION, "sword": ICON_SWORD, "axe": ICON_AXE,
    "armor": ICON_ARMOR, "gold": ICON_GOLD, "ear": ICON_EAR,
    "herb": ICON_HERB, "key": ICON_KEY,
}


def _validate() -> list[str]:
    """Return a list of human-readable problems (empty when the art is fine)."""
    problems: list[str] = []
    for name, rows in SPRITES.items():
        if len(rows) != SPRITE:
            problems.append(f"{name}: {len(rows)} rows (expected {SPRITE})")
        for i, row in enumerate(rows):
            if len(row) != SPRITE:
                problems.append(f"{name} row {i}: width {len(row)} (expected {SPRITE})")
    for name, rows in ICONS.items():
        if len(rows) != 16:
            problems.append(f"icon {name}: {len(rows)} rows (expected 16)")
        for i, row in enumerate(rows):
            if len(row) != 16:
                problems.append(f"icon {name} row {i}: width {len(row)} (expected 16)")
    return problems


def _surface(rows: list[str], size: int, palette: dict) -> pygame.Surface:
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            col = palette.get(ch)
            if col:
                surf.set_at((x, y), col)
    return surf


def build_surfaces() -> dict[str, pygame.Surface]:
    """Pre-render every sprite plus flipped and hurt variants."""
    problems = _validate()
    if problems:
        raise ValueError("sprite art problems:\n  " + "\n  ".join(problems))

    out: dict[str, pygame.Surface] = {}
    for name, rows in SPRITES.items():
        surf = _surface(rows, SPRITE, PAL)
        out[name] = surf
        out[name + "_f"] = pygame.transform.flip(surf, True, False)
        hurt = surf.copy()
        hurt.fill((150, 0, 0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        out[name + "_hurt"] = hurt
        out[name + "_hurt_f"] = pygame.transform.flip(hurt, True, False)
    for name, rows in ICONS.items():
        out["icon_" + name] = _surface(rows, 16, PAL)
    return out


if __name__ == "__main__":
    issues = _validate()
    if issues:
        print("SPRITE PROBLEMS:")
        for p in issues:
            print(" ", p)
    else:
        print(f"art OK: {len(SPRITES)} sprites of {SPRITE}x{SPRITE}, {len(ICONS)} icons of 16x16")
