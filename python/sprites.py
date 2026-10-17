#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Creature and item art for Pixel RPG — 64x64 characters, 24x24 icons.

Sprites are built from shaded primitives (limbs, torso, head, fur, wings, tails)
instead of ASCII maps, so a 64x64 frame can carry real volume: a lit side, a
shadowed side, contact shadow, outline and per-part detail.

Public API
    SPRITE, ICON                 canvas sizes
    build_sprites()              {key: Surface}
    item_icon_surface(icon_id)   cached 24x24 icon
    validate()                   -> list[str] of problems
"""

from __future__ import annotations

import math
import random

import pygame

from art import mix, shade

SPRITE = 64
ICON = 24

# ------------------------------------------------------------------ palettes
SKIN = {
    "light": (232, 190, 152), "tan": (206, 158, 118), "pale": (240, 214, 186),
    "green": (126, 168, 96), "darkgreen": (94, 134, 74), "grey": (168, 168, 172),
    "bone": (226, 220, 200), "red": (196, 92, 74), "stone": (140, 138, 136),
    "moss": (110, 140, 84), "blue": (128, 168, 196), "violet": (150, 122, 190),
}
HAIR = {
    "black": (44, 40, 46), "brown": (104, 70, 44), "blond": (214, 178, 96),
    "grey": (176, 176, 180), "red": (172, 84, 52), "white": (232, 232, 236),
}
CLOTH = {
    "red": (176, 66, 58), "blue": (62, 96, 158), "green": (74, 128, 78),
    "brown": (126, 88, 54), "grey": (110, 112, 122), "violet": (110, 78, 148),
    "white": (222, 220, 214), "yellow": (206, 172, 78), "teal": (56, 128, 128),
    "black": (54, 52, 60), "leather": (122, 82, 48), "rust": (146, 84, 48),
}
IRON, IRON_D, IRON_L = (108, 108, 116), (76, 76, 84), (156, 156, 166)
GOLD, GOLD_D = (232, 196, 96), (176, 140, 56)


def _ell(s, col, cx, cy, rx, ry) -> None:
    pygame.draw.ellipse(s, col, (int(cx - rx), int(cy - ry), int(rx * 2), int(ry * 2)))


def _limb(s, col, x1, y1, x2, y2, w) -> None:
    pygame.draw.line(s, col, (int(x1), int(y1)), (int(x2), int(y2)), int(w))
    _ell(s, col, x1, y1, w / 2, w / 2)
    _ell(s, col, x2, y2, w / 2, w / 2)


def _outline(s, col=(20, 17, 24), strength=0.85) -> None:
    w, h = s.get_size()
    mask = pygame.mask.from_surface(s)
    edge = []
    for y in range(h):
        for x in range(w):
            if not mask.get_at((x, y)):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and mask.get_at((nx, ny)):
                    continue
                edge.append((x, y))
                break
    for (x, y) in edge:
        s.set_at((x, y), mix(s.get_at((x, y))[:3], col, strength))


def _rim(s, col=(255, 248, 226), strength=0.34) -> None:
    """Light the upper-left silhouette edge: one key light for every sprite."""
    w, h = s.get_size()
    mask = pygame.mask.from_surface(s)
    lit = []
    for y in range(h):
        for x in range(w):
            if not mask.get_at((x, y)):
                continue
            up_open = (y - 1 < 0) or not mask.get_at((x, y - 1))
            left_open = (x - 1 < 0) or not mask.get_at((x - 1, y))
            if up_open or left_open:
                lit.append((x, y))
    for (x, y) in lit:
        s.set_at((x, y), mix(s.get_at((x, y))[:3], col, strength))


def _finish(s, *, outline=0.85, rim=0.34) -> None:
    """Every creature ends with the same pass: dark outline, then a rim light."""
    _outline(s, strength=outline)
    if rim:
        _rim(s, strength=rim)


def _shadow(s, cx, base_y, w=30, h=10) -> None:
    pygame.draw.ellipse(s, (0, 0, 0, 70), (int(cx - w / 2), int(base_y - h / 2), w, h))


# ------------------------------------------------------------ humanoid builder
def _head(s, cx, cy, r, skin, hair, view, *, hat=None, beard=None, ears=None,
          eyes="normal", horns=False) -> None:
    if isinstance(beard, str):                # accept a palette name
        beard = HAIR.get(beard, (200, 200, 200))
    _ell(s, skin, cx, cy, r, r * 1.02)
    _ell(s, shade(skin, 0.8), cx + r * 0.42, cy + r * 0.16, r * 0.55, r * 0.84)
    _ell(s, mix(skin, (255, 255, 255), 0.3), cx - r * 0.34, cy - r * 0.30, r * 0.46, r * 0.46)
    if view == "up":
        _ell(s, hair, cx, cy - r * 0.15, r * 1.06, r * 1.0)
    else:
        _ell(s, hair, cx, cy - r * 0.55, r * 1.04, r * 0.72)
        _ell(s, hair, cx - r * 0.85, cy - r * 0.05, r * 0.32, r * 0.72)
        _ell(s, hair, cx + r * 0.85, cy - r * 0.05, r * 0.32, r * 0.72)
        _ell(s, mix(hair, (255, 255, 255), 0.28), cx - r * 0.25, cy - r * 0.85,
             r * 0.55, r * 0.28)
    if ears == "pointed":
        pygame.draw.polygon(s, skin, [(cx - r * 0.9, cy - r * 0.1),
                                      (cx - r * 1.9, cy - r * 0.75),
                                      (cx - r * 0.8, cy + r * 0.35)])
        pygame.draw.polygon(s, skin, [(cx + r * 0.9, cy - r * 0.1),
                                      (cx + r * 1.9, cy - r * 0.75),
                                      (cx + r * 0.8, cy + r * 0.35)])
    elif ears == "round":
        _ell(s, skin, cx - r * 1.0, cy + r * 0.05, r * 0.3, r * 0.34)
        _ell(s, skin, cx + r * 1.0, cy + r * 0.05, r * 0.3, r * 0.34)
    if view == "down" and eyes != "none":
        ey = cy + r * 0.12
        if eyes == "glow":
            for sx in (-1, 1):
                pygame.draw.rect(s, (252, 244, 150),
                                 (int(cx + sx * r * 0.42) - 1, int(ey) - 1, 3, 3))
        elif eyes == "hollow":
            for sx in (-1, 1):
                pygame.draw.rect(s, (22, 18, 24),
                                 (int(cx + sx * r * 0.42) - 2, int(ey) - 2, 4, 4))
        else:
            # crisp pixel eyes: a white block, a dark pupil and one highlight pixel.
            # Tiny ellipses rasterise into a grey smear — that is what made faces blurry.
            for sx in (-1, 1):
                ex = int(cx + sx * r * 0.42)
                eyi = int(ey)
                pygame.draw.rect(s, (250, 250, 252), (ex - 1, eyi - 1, 3, 3))
                pygame.draw.rect(s, (38, 34, 42), (ex - 1 + (1 if sx > 0 else 0),
                                                   eyi - 1, 2, 2))
                s.set_at((ex - 1 + (1 if sx > 0 else 0), eyi - 1), (255, 255, 255))
        # brows, nose and mouth: the difference between a face and two dots
        brow = shade(hair, 0.7)
        w = max(1, int(r * 0.16))
        pygame.draw.line(s, brow, (cx - r * 0.66, ey - r * 0.40), (cx - r * 0.18, ey - r * 0.50), w)
        pygame.draw.line(s, brow, (cx + r * 0.66, ey - r * 0.40), (cx + r * 0.18, ey - r * 0.50), w)
        pygame.draw.rect(s, shade(skin, 0.82),
                         (int(cx - r * 0.10), int(ey + r * 0.24), max(2, int(r * 0.2)),
                          max(2, int(r * 0.22))))
        pygame.draw.line(s, shade(skin, 0.58), (cx - r * 0.26, ey + r * 0.66),
                         (cx + r * 0.26, ey + r * 0.66), max(1, int(r * 0.15)))
        pygame.draw.line(s, shade(skin, 0.72), (cx - r * 0.5, ey + r * 0.2),
                         (cx - r * 0.72, ey + r * 0.44), 1)
        pygame.draw.line(s, shade(skin, 0.72), (cx + r * 0.5, ey + r * 0.2),
                         (cx + r * 0.72, ey + r * 0.44), 1)
    elif view == "side" and eyes != "none":
        ey = cy + r * 0.12
        ex = int(cx + r * 0.34)
        if eyes == "glow":
            pygame.draw.rect(s, (252, 244, 150), (ex - 1, int(ey) - 1, 3, 3))
        elif eyes == "hollow":
            pygame.draw.rect(s, (22, 18, 24), (ex - 2, int(ey) - 2, 4, 4))
        else:
            pygame.draw.rect(s, (250, 250, 252), (ex - 1, int(ey) - 1, 3, 3))
            pygame.draw.rect(s, (38, 34, 42), (ex, int(ey) - 1, 2, 2))
    if beard:
        _ell(s, beard, cx, cy + r * 0.75, r * 0.72, r * 0.5)
        _ell(s, mix(beard, (255, 255, 255), 0.2), cx, cy + r * 0.55, r * 0.6, r * 0.24)
    if horns:
        pygame.draw.polygon(s, (226, 220, 204), [(cx - r * 0.7, cy - r * 0.7),
                                                  (cx - r * 1.15, cy - r * 1.6),
                                                  (cx - r * 0.35, cy - r * 0.9)])
        pygame.draw.polygon(s, (226, 220, 204), [(cx + r * 0.7, cy - r * 0.7),
                                                  (cx + r * 1.15, cy - r * 1.6),
                                                  (cx + r * 0.35, cy - r * 0.9)])
    if hat == "straw":
        _ell(s, (206, 176, 96), cx, cy - r * 0.75, r * 1.85, r * 0.42)
        _ell(s, (232, 206, 128), cx, cy - r * 0.95, r * 0.9, r * 0.55)
        _ell(s, (176, 146, 74), cx, cy - r * 0.62, r * 1.85, r * 0.16)
    elif hat == "hood":
        _ell(s, (86, 66, 118), cx, cy - r * 0.5, r * 1.2, r * 1.05)
        _ell(s, (48, 36, 66), cx, cy + r * 0.05, r * 0.78, r * 0.62)
    elif hat == "wizard":
        pygame.draw.polygon(s, (92, 68, 148), [(cx, cy - r * 2.6),
                                               (cx - r * 1.0, cy - r * 0.6),
                                               (cx + r * 1.0, cy - r * 0.6)])
        _ell(s, (72, 52, 120), cx, cy - r * 0.55, r * 1.35, r * 0.3)
        _ell(s, (232, 210, 140), cx, cy - r * 2.35, r * 0.2, r * 0.2)
    elif hat == "helm":
        _ell(s, IRON, cx, cy - r * 0.55, r * 1.1, r * 0.85)
        _ell(s, IRON_L, cx - r * 0.2, cy - r * 0.85, r * 0.6, r * 0.3)
        _ell(s, IRON_D, cx, cy - r * 0.2, r * 1.14, r * 0.22)
    elif hat == "cap":
        _ell(s, (146, 66, 58), cx, cy - r * 0.6, r * 1.05, r * 0.62)
        _ell(s, (176, 84, 72), cx - r * 0.2, cy - r * 0.8, r * 0.6, r * 0.25)


def _color(name, fallback=(200, 200, 200)):
    """Resolve a palette name (or pass a colour through) for any material."""
    if isinstance(name, tuple):
        return name
    return CLOTH.get(name) or SKIN.get(name) or HAIR.get(name) or fallback


def _humanoid(*, skin="light", hair="brown", shirt="blue", pants="grey",
              boots="brown", view="down", frame=0, hat=None, beard=None,
              ears=None, eyes="normal", build=1.0, cape=None, belt=True,
              shoulder=None, horns=False, size=1.0, base_y=62, cx=32,
              decorate=None) -> pygame.Surface:
    """Draw a person/creature-person. frame 0 = idle, 1 = step."""
    s = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
    skin_c, hair_c = _color(skin), _color(hair, HAIR["brown"])
    shirt_c, pants_c, boot_c = _color(shirt), _color(pants), _color(boots)
    step = 1 if frame else 0
    sc = size
    r = 7.0 * sc
    hip_y = base_y - 17 * sc
    shoulder_y = hip_y - 13 * sc * build
    head_cy = shoulder_y - r * 1.15
    _shadow(s, cx, base_y + 1, int(28 * sc), int(9 * sc))
    if cape:
        cape_c = _color(cape)
        pygame.draw.polygon(s, shade(cape_c, 0.8),
                            [(cx - 8 * sc, shoulder_y - 2), (cx + 8 * sc, shoulder_y - 2),
                             (cx + 10 * sc, hip_y + 9 * sc), (cx - 10 * sc, hip_y + 9 * sc)])
    if view == "side":
        front_x = cx + (2.5 if step else 0.5) * sc
        back_x = cx - (2.0 if step else 1.0) * sc
        for (lx, col) in ((back_x, shade(pants_c, 0.78)), (front_x, pants_c)):
            _limb(s, col, lx, hip_y, lx + (1.5 if step else 0) * sc, base_y - 4 * sc, 5.4 * sc)
            _ell(s, boot_c, lx + (1.5 if step else 0) * sc, base_y - 2.4 * sc, 3.4 * sc, 2.4 * sc)
    else:
        swing = 3.2 * sc if step else 1.6 * sc
        for (lx, col, dx) in ((cx - 4.6 * sc, shade(pants_c, 0.84), -swing),
                              (cx + 4.6 * sc, pants_c, swing)):
            _limb(s, col, lx, hip_y, lx + dx * 0.4, base_y - 4 * sc, 5.4 * sc)
            _ell(s, boot_c, lx + dx * 0.4, base_y - 2.4 * sc, 3.4 * sc, 2.4 * sc)
    tw = 9.0 * sc * build
    _ell(s, shirt_c, cx, (hip_y + shoulder_y) / 2, tw, (hip_y - shoulder_y) / 2 + 2.5 * sc)
    _ell(s, shade(shirt_c, 0.78), cx + tw * 0.42, (hip_y + shoulder_y) / 2 + 1.5 * sc,
         tw * 0.52, (hip_y - shoulder_y) / 2)
    _ell(s, mix(shirt_c, (255, 255, 255), 0.24), cx - tw * 0.35,
         shoulder_y + 2.5 * sc, tw * 0.42, 3.6 * sc)
    if belt:
        pygame.draw.rect(s, shade(pants_c, 0.7), (int(cx - tw), int(hip_y - 1.6 * sc),
                                                  int(tw * 2), int(2.6 * sc)))
        _ell(s, GOLD, cx, hip_y - 0.4 * sc, 1.6 * sc, 1.6 * sc)
    if shoulder:
        _ell(s, IRON, cx - tw * 0.95, shoulder_y + 1.5 * sc, 3.2 * sc, 2.6 * sc)
        _ell(s, IRON, cx + tw * 0.95, shoulder_y + 1.5 * sc, 3.2 * sc, 2.6 * sc)
        _ell(s, IRON_L, cx - tw * 1.0, shoulder_y + 0.6 * sc, 1.8 * sc, 1.0 * sc)
    if view == "side":
        _limb(s, shade(shirt_c, 0.78), cx - 2 * sc, shoulder_y + 2 * sc,
              cx - 3 * sc - (2 if step else 0) * sc, hip_y + 1 * sc, 4.4 * sc)
        _limb(s, shirt_c, cx + 2 * sc, shoulder_y + 2 * sc,
              cx + 3 * sc + (3 if step else 1) * sc, hip_y + 2 * sc, 4.6 * sc)
        _ell(s, skin_c, cx + 3 * sc + (3 if step else 1) * sc, hip_y + 3 * sc, 2.2 * sc, 2.2 * sc)
    else:
        for sx in (-1, 1):
            ax = cx + sx * (tw + 2.2 * sc)
            _limb(s, shirt_c if sx > 0 else shade(shirt_c, 0.84), ax,
                  shoulder_y + 2 * sc, ax + sx * (2.4 if step else 1.0) * sc,
                  hip_y + 2.5 * sc, 4.6 * sc)
            _ell(s, skin_c, ax + sx * (2.4 if step else 1.0) * sc, hip_y + 3.4 * sc,
                 2.2 * sc, 2.2 * sc)
    _head(s, cx, head_cy, r, skin_c, hair_c, view, hat=hat, beard=beard, ears=ears,
          eyes=eyes, horns=horns)
    if decorate:
        # lets a monster add its own face and gear at the right coordinates
        decorate(s, {"cx": cx, "head_cy": head_cy, "r": r, "shoulder_y": shoulder_y,
                     "hip_y": hip_y, "tw": tw, "size": sc, "view": view,
                     "skin": skin_c, "shirt": shirt_c})
    _finish(s)
    return s


# ------------------------------------------------------------------- monsters
def _goblin_face(s, m, *, big=False) -> None:
    """Long hooked nose, huge ears, a crude dagger — a goblin, not a small orc."""
    cx, cy, r, sc = m["cx"], m["head_cy"], m["r"], m["size"]
    skin = m["skin"]
    # big swept ears
    for sx in (-1, 1):
        pygame.draw.polygon(s, skin, [
            (cx + sx * r * 0.75, cy - r * 0.2),
            (cx + sx * r * 2.5, cy - r * 1.15),
            (cx + sx * r * 1.5, cy + r * 0.05),
            (cx + sx * r * 0.8, cy + r * 0.5)])
        pygame.draw.polygon(s, shade(skin, 0.72), [
            (cx + sx * r * 0.95, cy - r * 0.1),
            (cx + sx * r * 2.05, cy - r * 0.85),
            (cx + sx * r * 1.3, cy + r * 0.0)])
    # long hooked nose
    pygame.draw.polygon(s, shade(skin, 0.86),
                        [(cx + r * 0.06, cy + r * 0.02), (cx + r * 0.7, cy + r * 0.55),
                         (cx + r * 0.1, cy + r * 0.6)])
    pygame.draw.polygon(s, mix(skin, (255, 255, 255), 0.3),
                        [(cx + r * 0.12, cy + r * 0.06), (cx + r * 0.5, cy + r * 0.42),
                         (cx + r * 0.16, cy + r * 0.5)])
    # a jagged grin with two fangs
    pygame.draw.line(s, (58, 34, 30), (cx - r * 0.5, cy + r * 0.72),
                     (cx + r * 0.45, cy + r * 0.78), max(1, int(r * 0.14)))
    for sx in (-1, 1):
        pygame.draw.polygon(s, (246, 242, 224),
                            [(cx + sx * r * 0.36, cy + r * 0.72),
                             (cx + sx * r * 0.2, cy + r * 1.18),
                             (cx + sx * r * 0.05, cy + r * 0.74)])
    # ragged hem and a crude dagger
    pygame.draw.polygon(s, shade(m["shirt"], 0.72),
                        [(cx - m["tw"], m["hip_y"] - r * 0.2), (cx + m["tw"], m["hip_y"] - r * 0.2),
                         (cx + m["tw"] * 0.8, m["hip_y"] + r * 0.7),
                         (cx - m["tw"] * 0.9, m["hip_y"] + r * 0.5)])
    hx = cx + m["tw"] + 3.4 * sc
    hy = m["hip_y"] + 2.6 * sc
    pygame.draw.line(s, (92, 74, 58), (hx, hy), (hx + 1.5 * sc, hy - 8 * sc), max(2, int(2 * sc)))
    pygame.draw.polygon(s, (196, 198, 206), [(hx + 1.5 * sc, hy - 8 * sc),
                                             (hx + 1.0 * sc, hy - 15 * sc),
                                             (hx + 3.4 * sc, hy - 9 * sc)])
    if big:
        pygame.draw.polygon(s, IRON_D, [(cx - m["tw"] * 1.5, m["shoulder_y"] + 3 * sc),
                                        (cx - m["tw"] * 2.6, m["shoulder_y"] - 6 * sc),
                                        (cx - m["tw"] * 0.8, m["shoulder_y"] - 1 * sc)])
        pygame.draw.polygon(s, IRON_D, [(cx + m["tw"] * 1.5, m["shoulder_y"] + 3 * sc),
                                        (cx + m["tw"] * 2.6, m["shoulder_y"] - 6 * sc),
                                        (cx + m["tw"] * 0.8, m["shoulder_y"] - 1 * sc)])
        pygame.draw.rect(s, shade(IRON, 0.85),
                         (int(cx - m["tw"] * 0.75), int(m["shoulder_y"] + 2 * sc),
                          int(m["tw"] * 1.5), int(r * 1.5)), border_radius=int(r * 0.4))


def _goblin(frame=0, big=False, view="down") -> pygame.Surface:
    return _humanoid(skin="green", hair="black", shirt="rust" if not big else "brown",
                     pants="leather", boots="brown", view=view, frame=frame,
                     ears=None, eyes="glow" if big else "normal",
                     build=1.3 if big else 1.0, size=1.22 if big else 0.94,
                     belt=big, shoulder=big,
                     decorate=lambda s, m: _goblin_face(s, m, big=big))


def _orc_face(s, m) -> None:
    """War paint, a broad jaw with two big tusks, an iron chest plate and an axe."""
    cx, cy, r, sc = m["cx"], m["head_cy"], m["r"], m["size"]
    skin = m["skin"]
    # heavy jaw
    _ell(s, shade(skin, 0.9), cx, cy + r * 0.5, r * 0.85, r * 0.55)
    for sx in (-1, 1):                       # tusks that read from the front
        pygame.draw.polygon(s, (242, 238, 220),
                            [(cx + sx * r * 0.52, cy + r * 0.66),
                             (cx + sx * r * 0.34, cy + r * 0.02),
                             (cx + sx * r * 0.16, cy + r * 0.7)])
        pygame.draw.polygon(s, (206, 200, 180),
                            [(cx + sx * r * 0.46, cy + r * 0.62),
                             (cx + sx * r * 0.36, cy + r * 0.2),
                             (cx + sx * r * 0.26, cy + r * 0.64)])
    pygame.draw.line(s, (66, 34, 34), (cx - r * 0.6, cy + r * 0.78),
                     (cx + r * 0.6, cy + r * 0.78), max(1, int(r * 0.16)))
    # red war paint across the eyes
    pygame.draw.rect(s, (168, 54, 46), (int(cx - r * 0.95), int(cy - r * 0.32),
                                        int(r * 1.9), max(2, int(r * 0.3))))
    _ell(s, (250, 250, 252), cx - r * 0.42, cy + r * 0.12, r * 0.24, r * 0.22)
    _ell(s, (250, 250, 252), cx + r * 0.42, cy + r * 0.12, r * 0.24, r * 0.22)
    _ell(s, (188, 62, 52), cx - r * 0.38, cy + r * 0.12, r * 0.13, r * 0.14)
    _ell(s, (188, 62, 52), cx + r * 0.46, cy + r * 0.12, r * 0.13, r * 0.14)
    # iron chest plate and a big axe
    pygame.draw.polygon(s, IRON, [(cx - m["tw"] * 0.9, m["shoulder_y"] + 2 * sc),
                                  (cx + m["tw"] * 0.9, m["shoulder_y"] + 2 * sc),
                                  (cx + m["tw"] * 0.75, m["hip_y"] - 2 * sc),
                                  (cx - m["tw"] * 0.75, m["hip_y"] - 2 * sc)])
    pygame.draw.line(s, IRON_L, (cx - m["tw"] * 0.5, m["shoulder_y"] + 4 * sc),
                     (cx - m["tw"] * 0.4, m["hip_y"] - 3 * sc), max(1, int(1.4 * sc)))
    ax = cx - m["tw"] - 4.2 * sc
    ay = m["hip_y"] + 1.6 * sc
    pygame.draw.line(s, (98, 74, 52), (ax, ay + 2 * sc), (ax + 1.6 * sc, ay - 12 * sc),
                     max(2, int(2.2 * sc)))
    pygame.draw.polygon(s, (176, 180, 190), [(ax + 0.4 * sc, ay - 11 * sc),
                                             (ax - 5.4 * sc, ay - 13 * sc),
                                             (ax - 5.0 * sc, ay - 6.4 * sc),
                                             (ax + 2.0 * sc, ay - 7.4 * sc)])
    pygame.draw.polygon(s, (206, 210, 220), [(ax - 4.4 * sc, ay - 12.2 * sc),
                                             (ax - 1.2 * sc, ay - 10.6 * sc),
                                             (ax - 3.0 * sc, ay - 8.0 * sc)])


def _orc(frame=0, view="down") -> pygame.Surface:
    return _humanoid(skin="darkgreen", hair="black", shirt="grey", pants="black",
                     boots="black", view=view, frame=frame, ears="pointed",
                     build=1.35, size=1.18, shoulder=True, belt=True,
                     decorate=_orc_face)


def _skeleton(frame=0, view="down") -> pygame.Surface:
    s = _humanoid(skin="bone", hair="white", shirt="bone", pants="bone",
                  boots="bone", view=view, frame=frame, eyes="hollow",
                  size=1.02, belt=False)
    d = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    d.blit(s, (0, 0))
    for i in range(3):
        pygame.draw.line(d, (188, 182, 164), (26, 36 + i * 4), (38, 36 + i * 4), 1)
    _ell(d, (60, 54, 58), 32, 40, 3.4, 4.2)
    return d


def _wraith(frame=0, view="down") -> pygame.Surface:
    s = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
    _shadow(s, 32, 62, 24, 8)
    ghost = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
    pygame.draw.polygon(ghost, (168, 176, 214),
                        [(32, 10), (46, 26), (50, 56), (32, 60), (14, 56), (18, 26)])
    pygame.draw.polygon(ghost, (206, 212, 240),
                        [(32, 14), (40, 28), (43, 54), (32, 56), (21, 54), (24, 28)])
    pygame.draw.polygon(ghost, (96, 104, 148),
                        [(32, 4), (48, 20), (52, 30), (32, 22), (12, 30), (16, 20)])
    _ell(ghost, (18, 16, 26), 32, 22, 8.5, 7.5)
    _ell(ghost, (150, 240, 220), 28.5, 21, 1.8, 1.8)
    _ell(ghost, (150, 240, 220), 35.5, 21, 1.8, 1.8)
    for i in range(5):
        x = 18 + i * 7
        pygame.draw.polygon(ghost, (168, 176, 214), [(x, 54), (x + 4, 60), (x + 7, 54)])
    ghost.set_alpha(215)
    s.blit(ghost, (0, 0))
    _finish(s)
    return s


def _troll(frame=0, view="down") -> pygame.Surface:
    """A hunched giant: mossy back, huge jaw with tusks, long arms, a club."""
    def face(s, m):
        cx, cy, r, sc = m["cx"], m["head_cy"], m["r"], m["size"]
        _ell(s, shade(m["skin"], 0.88), cx, cy + r * 0.55, r * 0.95, r * 0.6)
        for sx in (-1, 1):
            pygame.draw.polygon(s, (238, 234, 214),
                                [(cx + sx * r * 0.6, cy + r * 0.7),
                                 (cx + sx * r * 0.5, cy - r * 0.05),
                                 (cx + sx * r * 0.22, cy + r * 0.72)])
        pygame.draw.line(s, (52, 44, 40), (cx - r * 0.62, cy + r * 0.8),
                         (cx + r * 0.62, cy + r * 0.8), max(1, int(r * 0.18)))
        _ell(s, (250, 244, 150), cx - r * 0.42, cy + r * 0.14, r * 0.2, r * 0.2)
        _ell(s, (250, 244, 150), cx + r * 0.42, cy + r * 0.14, r * 0.2, r * 0.2)
        # a club resting on the shoulder
        hx = cx + m["tw"] + 3.0 * sc
        hy = m["hip_y"] - 2 * sc
        pygame.draw.line(s, (104, 78, 52), (hx, hy + 10 * sc), (hx + 3 * sc, hy - 12 * sc),
                         max(3, int(3.2 * sc)))
        _ell(s, (128, 100, 68), hx + 3 * sc, hy - 14 * sc, 4.6 * sc, 4.4 * sc)
        _ell(s, (152, 122, 86), hx + 2 * sc, hy - 15.5 * sc, 2.6 * sc, 2.2 * sc)

    s = _humanoid(skin="moss", hair="brown", shirt="moss", pants="moss",
                  boots="brown", view=view, frame=frame, eyes="glow",
                  build=1.5, size=1.42, horns=True, belt=False, decorate=face)
    d = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    d.blit(s, (0, 0))
    for _ in range(16):                      # moss on the back and arms only
        x = random.choice([random.randrange(16, 26), random.randrange(38, 48)])
        _ell(d, (86, 148, 72), x, random.randrange(30, 56), 2.2, 1.6)
    return d


def _bandit(frame=0, view="down") -> pygame.Surface:
    """Brown leather, a red bandana over the face, a knife: never a second hero."""
    def gear(s, m):
        cx, cy, r, sc = m["cx"], m["head_cy"], m["r"], m["size"]
        # a red bandana across the lower face, tied at the back
        pygame.draw.polygon(s, (168, 52, 46),
                            [(cx - r * 1.0, cy + r * 0.24), (cx + r * 1.0, cy + r * 0.24),
                             (cx + r * 0.9, cy + r * 0.9), (cx - r * 0.9, cy + r * 0.9)])
        pygame.draw.polygon(s, (198, 70, 62), [(cx - r * 0.9, cy + r * 0.3),
                                               (cx + r * 0.1, cy + r * 0.34),
                                               (cx - r * 0.2, cy + r * 0.86)])
        _ell(s, (250, 250, 252), cx - r * 0.42, cy + r * 0.02, r * 0.24, r * 0.22)
        _ell(s, (250, 250, 252), cx + r * 0.42, cy + r * 0.02, r * 0.24, r * 0.22)
        _ell(s, (46, 38, 44), cx - r * 0.38, cy + r * 0.02, r * 0.13, r * 0.14)
        _ell(s, (46, 38, 44), cx + r * 0.46, cy + r * 0.02, r * 0.13, r * 0.14)
        # a leather jerkin over the shirt and a knife in the right hand
        pygame.draw.polygon(s, (122, 82, 48), [(cx - m["tw"] * 0.9, m["shoulder_y"] + 2 * sc),
                                               (cx + m["tw"] * 0.9, m["shoulder_y"] + 2 * sc),
                                               (cx + m["tw"] * 0.8, m["hip_y"] + 1 * sc),
                                               (cx - m["tw"] * 0.8, m["hip_y"] + 1 * sc)])
        pygame.draw.line(s, (86, 58, 36), (cx, m["shoulder_y"] + 3 * sc),
                         (cx, m["hip_y"]), max(1, int(1.6 * sc)))
        hx = cx + m["tw"] + 3.6 * sc
        hy = m["hip_y"] + 2.4 * sc
        pygame.draw.line(s, (74, 56, 40), (hx, hy), (hx + 1.2 * sc, hy - 7 * sc),
                         max(2, int(2 * sc)))
        pygame.draw.polygon(s, (204, 208, 216), [(hx + 1.2 * sc, hy - 7 * sc),
                                                 (hx + 0.8 * sc, hy - 14 * sc),
                                                 (hx + 3.0 * sc, hy - 8 * sc)])

    return _humanoid(skin="tan", hair="black", shirt="brown", pants="leather",
                     boots="black", view=view, frame=frame, hat="hood", belt=True,
                     decorate=gear)


def _imp(frame=0, view="down") -> pygame.Surface:
    s = _humanoid(skin="red", hair="black", shirt="red", pants="red", boots="red",
                  view=view, frame=frame, eyes="glow", horns=True, size=0.72,
                  belt=False)
    d = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    d.blit(s, (0, 0))
    for sx in (-1, 1):
        pygame.draw.polygon(d, (74, 44, 60), [(32 + sx * 8, 34),
                                              (32 + sx * 22, 24),
                                              (32 + sx * 20, 40)])
        pygame.draw.line(d, (40, 26, 34), (32 + sx * 12, 36), (32 + sx * 20, 30), 1)
    pygame.draw.line(d, (120, 44, 44), (34, 48), (44, 52), 2)
    return d


def _golem(frame=0, view="down") -> pygame.Surface:
    """Stone slabs with bevels, a chiselled face, cracks and a molten core."""
    s = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
    _shadow(s, 32, 62, 30, 10)
    step = 1 if frame else 0
    stone, stone_d, stone_l = (128, 128, 136), (88, 88, 96), (176, 176, 184)
    # legs: tapered slabs with a bevelled foot
    for x, off in ((17, -step), (35, step)):
        pygame.draw.polygon(s, stone_d, [(x, 34), (x + 13, 34), (x + 11, 60), (x + 2, 60)])
        pygame.draw.polygon(s, stone, [(x + 2, 35), (x + 8, 35), (x + 7, 59), (x + 3, 59)])
        pygame.draw.rect(s, stone_l, (x + 1, 57, 11, 4))
    # torso: a trapezoid, narrower at the waist, with a bright left face
    pygame.draw.polygon(s, stone_d, [(14, 14), (50, 14), (46, 52), (18, 52)])
    pygame.draw.polygon(s, stone, [(16, 15), (34, 15), (32, 51), (19, 51)])
    pygame.draw.polygon(s, stone_l, [(18, 16), (24, 16), (23, 50), (19, 50)])
    for y in (22, 31, 40):                    # seams between slabs
        pygame.draw.line(s, stone_d, (17, y), (47, y), 1)
        pygame.draw.line(s, (150, 150, 158), (17, y + 1), (47, y + 1), 1)
    pygame.draw.line(s, (70, 70, 78), (34, 26), (28, 38), 1)
    pygame.draw.line(s, (70, 70, 78), (28, 38), (36, 44), 1)
    # arms: heavy blocks that hang past the hips
    for x, sgn in ((4, -1), (48, 1)):
        pygame.draw.rect(s, stone_d, (x, 18, 12, 30))
        pygame.draw.rect(s, stone, (x + sgn * 1 + 1, 19, 7, 28))
        pygame.draw.rect(s, stone_l, (x + 2, 19, 3, 26))
        pygame.draw.rect(s, (104, 104, 112), (x, 44, 12, 7))
    # head: a block with a heavy brow, a jaw slot and glowing eyes
    pygame.draw.rect(s, stone_d, (21, 3, 22, 16))
    pygame.draw.rect(s, stone, (22, 4, 18, 14))
    pygame.draw.rect(s, stone_l, (23, 5, 7, 12))
    pygame.draw.rect(s, stone_d, (20, 3, 24, 3))            # brow ridge
    _ell(s, (120, 240, 200), 28, 11, 2.4, 2.2)
    _ell(s, (120, 240, 200), 36, 11, 2.4, 2.2)
    _ell(s, (196, 255, 236), 27, 10, 0.8, 0.8)
    _ell(s, (196, 255, 236), 35, 10, 0.8, 0.8)
    pygame.draw.rect(s, (58, 58, 66), (26, 15, 12, 2))      # jaw slot
    for x in range(27, 38, 3):
        pygame.draw.line(s, (104, 104, 112), (x, 15), (x, 17), 1)
    _ell(s, (110, 210, 180), 32, 32, 5.4, 5.4)
    _ell(s, (170, 245, 220), 32, 31, 2.6, 2.6)
    _finish(s)
    return s


# ------------------------------------------------------------------- animals
def _quadruped(*, body, belly, head_c, frame=0, size=1.0, ears="up", tail="bushy",
               tusks=False, mane=None, snout=None, eye=(30, 26, 32), hump=False,
               body_len=17.0, body_h=10.5, head_r=9.0, head_dx=16.0, head_dy=-8.0,
               leg_x=(20, 30, 40, 46), leg_w=4.6, leg_len=1.0, claws=False,
               hooves=False, udder=False, horns=False, snout_len=6.0, snout_ry=4.0,
               bristles=False, patches=False, fleece=False, neck=0.0,
               snout_disc=False, base_y=60) -> pygame.Surface:
    """A four-legged creature. The parameters are what make a wolf, a bear, a boar and a
    cow read as four different animals instead of one recoloured box."""
    s = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
    sc = size
    step = 1 if frame else 0
    body_cy = base_y - 14 * sc
    _shadow(s, 32, base_y + 1, int((body_len + 14) * sc), int(9 * sc))
    dark = shade(body, 0.62)
    # legs (back pair darker, so the body has depth)
    for i, lx in enumerate(leg_x):
        off = (2 if (i + step) % 2 else -2) * sc
        col = shade(body, 0.74) if i in (0, 3) else body
        x0 = lx * sc + (32 - 32 * sc)
        y_end = base_y - 2 * sc - (leg_len - 1.0) * 12 * sc
        _limb(s, col, x0, body_cy + 5 * sc, x0 + off, y_end, int(leg_w * sc))
        if hooves:
            _ell(s, (44, 40, 46), x0 + off, y_end + 0.6 * sc, leg_w * 0.62 * sc, 2.2 * sc)
        else:
            _ell(s, shade(body, 0.58), x0 + off, y_end, 2.6 * sc, 1.8 * sc)
            if claws:
                for k in (-1, 0, 1):
                    pygame.draw.line(s, (236, 232, 216),
                                     (x0 + off + k * 1.6 * sc, y_end + 1.4 * sc),
                                     (x0 + off + k * 1.9 * sc, y_end + 2.6 * sc), 1)
    # tail
    tx = 14 * sc + (32 - 32 * sc)
    if tail == "bushy":
        _ell(s, shade(body, 0.82), tx, body_cy - 4 * sc, 5.2 * sc, 4.2 * sc)
        _ell(s, body, tx - 3 * sc, body_cy - 8 * sc, 4.2 * sc, 3.6 * sc)
        _ell(s, mix(body, (255, 255, 255), 0.2), tx - 4 * sc, body_cy - 9.6 * sc,
             2.4 * sc, 1.8 * sc)
    elif tail == "thin":
        pygame.draw.line(s, body, (tx, body_cy), (6 * sc + (32 - 32 * sc), body_cy - 10 * sc),
                         int(2.4 * sc))
        _ell(s, shade(body, 0.8), 6 * sc + (32 - 32 * sc), body_cy - 10 * sc, 2.4 * sc, 2.0 * sc)
    elif tail == "tuft":
        pygame.draw.line(s, shade(body, 0.86), (tx, body_cy - 2 * sc),
                         (8 * sc + (32 - 32 * sc), body_cy - 9 * sc), int(2.2 * sc))
        _ell(s, (52, 46, 50), 8 * sc + (32 - 32 * sc), body_cy - 10 * sc, 2.6 * sc, 2.2 * sc)
    elif tail == "curl":
        pygame.draw.line(s, shade(body, 0.86), (tx, body_cy - 2 * sc),
                         (10 * sc + (32 - 32 * sc), body_cy - 9 * sc), int(2.0 * sc))
        pygame.draw.circle(s, mix(body, (255, 255, 255), 0.25),
                           (int(11 * sc + (32 - 32 * sc)), int(body_cy - 11 * sc)),
                           int(2.4 * sc), int(1.4 * sc))
    # body: three tones from the top light down to the belly
    _ell(s, body, 32, body_cy, body_len * sc, body_h * sc)
    _ell(s, mix(body, (255, 255, 255), 0.22), 32 - body_len * 0.12 * sc,
         body_cy - body_h * 0.42 * sc, body_len * 0.66 * sc, body_h * 0.36 * sc)
    _ell(s, shade(body, 0.82), 32 + body_len * 0.3 * sc, body_cy + body_h * 0.2 * sc,
         body_len * 0.62 * sc, body_h * 0.66 * sc)
    _ell(s, belly, 32, body_cy + body_h * 0.62 * sc, body_len * 0.78 * sc, body_h * 0.42 * sc)
    if hump:
        _ell(s, shade(body, 0.92), 30, body_cy - body_h * 0.82 * sc,
             body_len * 0.5 * sc, body_h * 0.42 * sc)
        _ell(s, mix(body, (255, 255, 255), 0.18), 29, body_cy - body_h * 0.95 * sc,
             body_len * 0.34 * sc, body_h * 0.2 * sc)
    if fleece:
        for i in range(9):
            fx = 32 + (i - 4) * body_len * 0.22 * sc
            _ell(s, mix(body, (255, 255, 255), 0.16), fx, body_cy - body_h * 0.8 * sc,
                 body_len * 0.14 * sc, body_h * 0.3 * sc)
    if bristles:
        for i in range(7):
            bx = 32 + (i - 3) * body_len * 0.2 * sc
            pygame.draw.line(s, shade(body, 0.5), (bx, body_cy - body_h * 0.9 * sc),
                             (bx + 1.5 * sc, body_cy - body_h * 1.5 * sc), 1)
    if patches:
        _ell(s, (48, 44, 48), 32 - body_len * 0.4 * sc, body_cy - body_h * 0.2 * sc,
             body_len * 0.24 * sc, body_h * 0.44 * sc)
        _ell(s, (48, 44, 48), 32 + body_len * 0.34 * sc, body_cy + body_h * 0.1 * sc,
             body_len * 0.2 * sc, body_h * 0.36 * sc)
    if udder:
        _ell(s, (226, 186, 178), 30, body_cy + body_h * 0.92 * sc, 4.4 * sc, 3.0 * sc)
    if mane:
        mane_c = _color(mane)
        for i in range(6):
            _ell(s, mane_c, 24 + i * 2.2, body_cy - body_h * 0.75 * sc - i * 0.6 * sc,
                 3.6 * sc, 4.0 * sc)
            _ell(s, shade(mane_c, 0.78), 24 + i * 2.2, body_cy - body_h * 0.45 * sc - i * 0.6 * sc,
                 3.0 * sc, 2.6 * sc)
    # neck and head
    hx = head_dx * sc + (32 - 32 * sc)
    hy = body_cy + head_dy * sc
    if neck:
        _limb(s, shade(body, 0.94), 32 + (body_len - 3) * sc, body_cy - 2 * sc,
              hx - 3 * sc, hy + 2 * sc, int(body_h * 0.85 * sc))
    _ell(s, head_c, hx, hy, head_r * sc, head_r * 0.92 * sc)
    _ell(s, mix(head_c, (255, 255, 255), 0.2), hx - head_r * 0.3 * sc, hy - head_r * 0.36 * sc,
         head_r * 0.5 * sc, head_r * 0.36 * sc)
    _ell(s, shade(head_c, 0.84), hx + head_r * 0.4 * sc, hy + head_r * 0.3 * sc,
         head_r * 0.5 * sc, head_r * 0.55 * sc)
    if snout:
        if snout_disc:
            _ell(s, snout, hx + head_r * 0.66 * sc, hy + head_r * 0.24 * sc,
                 snout_len * 0.62 * sc, snout_ry * 1.15 * sc)
            _ell(s, shade(snout, 0.6), hx + head_r * 0.66 * sc, hy + head_r * 0.24 * sc,
                 1.6 * sc, 1.6 * sc)
            _ell(s, (26, 22, 26), hx + head_r * 0.5 * sc, hy + head_r * 0.02 * sc,
                 1.2 * sc, 1.2 * sc)
            _ell(s, (26, 22, 26), hx + head_r * 0.86 * sc, hy + head_r * 0.02 * sc,
                 1.2 * sc, 1.2 * sc)
        else:
            _ell(s, snout, hx + head_r * 0.6 * sc, hy + head_r * 0.28 * sc,
                 snout_len * 0.72 * sc, snout_ry * sc)
            _ell(s, (32, 28, 34), hx + head_r * 0.6 * sc + snout_len * 0.55 * sc,
                 hy + head_r * 0.22 * sc, 1.9 * sc, 1.7 * sc)
            pygame.draw.line(s, shade(snout, 0.6), (hx + head_r * 0.5 * sc, hy + head_r * 0.62 * sc),
                             (hx + head_r * 0.95 * sc, hy + head_r * 0.62 * sc), 1)
    if ears == "up":
        pygame.draw.polygon(s, shade(head_c, 0.85), [(hx - 4 * sc, hy - 6 * sc),
                                                     (hx - 6.5 * sc, hy - 14 * sc),
                                                     (hx + 0.5 * sc, hy - 7 * sc)])
        pygame.draw.polygon(s, shade(head_c, 0.85), [(hx + 3 * sc, hy - 6 * sc),
                                                     (hx + 5.5 * sc, hy - 14 * sc),
                                                     (hx + 8.5 * sc, hy - 6 * sc)])
        pygame.draw.polygon(s, (74, 54, 58), [(hx - 4 * sc, hy - 7 * sc),
                                              (hx - 5.5 * sc, hy - 11.5 * sc),
                                              (hx - 0.5 * sc, hy - 7 * sc)])
    elif ears == "round":
        _ell(s, shade(head_c, 0.9), hx - 5 * sc, hy - 7 * sc, 3.2 * sc, 3.2 * sc)
        _ell(s, shade(head_c, 0.9), hx + 5 * sc, hy - 7 * sc, 3.2 * sc, 3.2 * sc)
        _ell(s, shade(head_c, 0.7), hx - 5 * sc, hy - 7 * sc, 1.4 * sc, 1.4 * sc)
        _ell(s, shade(head_c, 0.7), hx + 5 * sc, hy - 7 * sc, 1.4 * sc, 1.4 * sc)
    elif ears == "droop":
        _ell(s, shade(head_c, 0.88), hx - 6 * sc, hy + 2 * sc, 2.8 * sc, 4.4 * sc)
        _ell(s, shade(head_c, 0.88), hx + 6 * sc, hy + 2 * sc, 2.8 * sc, 4.4 * sc)
    if horns:
        pygame.draw.polygon(s, (232, 226, 206), [(hx - 4 * sc, hy - 5 * sc),
                                                 (hx - 9 * sc, hy - 11 * sc),
                                                 (hx - 2 * sc, hy - 8 * sc)])
        pygame.draw.polygon(s, (232, 226, 206), [(hx + 4 * sc, hy - 5 * sc),
                                                 (hx + 9 * sc, hy - 11 * sc),
                                                 (hx + 2 * sc, hy - 8 * sc)])
    if tusks:
        pygame.draw.polygon(s, (240, 236, 218), [(hx + head_r * 0.5 * sc, hy + head_r * 0.62 * sc),
                                                 (hx + head_r * 0.95 * sc, hy - head_r * 0.1 * sc),
                                                 (hx + head_r * 0.78 * sc, hy + head_r * 0.66 * sc)])
        pygame.draw.polygon(s, (240, 236, 218), [(hx + head_r * 0.16 * sc, hy + head_r * 0.66 * sc),
                                                 (hx + head_r * 0.02 * sc, hy - head_r * 0.05 * sc),
                                                 (hx - head_r * 0.1 * sc, hy + head_r * 0.7 * sc)])
    ex = hx + head_r * 0.3 * sc
    ey = hy - head_r * 0.16 * sc
    # crisp eye: white block, dark pupil, one highlight pixel
    pygame.draw.rect(s, (250, 250, 252), (int(ex) - 1, int(ey) - 1, 3, 3))
    pygame.draw.rect(s, eye, (int(ex), int(ey) - 1, 2, 2))
    s.set_at((int(ex), int(ey) - 1), (255, 255, 255))
    _finish(s)
    return s


def _spider(frame=0) -> pygame.Surface:
    s = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
    step = 1 if frame else 0
    _shadow(s, 32, 58, 30, 9)
    for i, (sx, sy) in enumerate(((-1, -1), (-1, 0), (-1, 1), (1, -1), (1, 0), (1, 1))):
        for k in range(4):
            ang = -0.9 + k * 0.5 + (0.12 if step and i % 2 else -0.12 if step else 0)
            bx, by = 32 + sx * 5, 36 + sy * 3
            mx = bx + sx * 10 * math.cos(ang * 0.6)
            my = by + 6 * math.sin(ang) - 4
            ex = mx + sx * 9
            ey = 52 + (2 if k % 2 else -2)
            pygame.draw.line(s, (58, 40, 34), (bx, by), (mx, my), 3)
            pygame.draw.line(s, (58, 40, 34), (mx, my), (ex, ey), 2)
            pygame.draw.line(s, (96, 70, 58), (bx, by - 1), (mx, my - 1), 1)
    _ell(s, (46, 32, 30), 32, 40, 13, 11)
    _ell(s, (74, 52, 44), 32, 38, 11, 9)
    _ell(s, (46, 32, 30), 32, 28, 7.5, 6.5)
    _ell(s, (86, 60, 50), 32, 27, 6, 5)
    for dx in (-3.4, -1.2, 1.2, 3.4):
        _ell(s, (200, 60, 60), 32 + dx, 27 + (1.6 if dx > 0 else -1.6), 1.5, 1.5)
    _finish(s)
    return s


def _slime(frame=0) -> pygame.Surface:
    """A glossy blob with a highlight, a mouth and drips."""
    s = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
    squash = 2 if frame else 0
    _shadow(s, 32, 60, 30, 9)
    pygame.draw.ellipse(s, (46, 122, 104), (12, 26 + squash, 40, 34 - squash * 2))
    pygame.draw.ellipse(s, (92, 186, 152), (14, 28 + squash, 36, 28 - squash * 2))
    pygame.draw.ellipse(s, (138, 214, 178), (16, 30 + squash, 30, 18 - squash))
    pygame.draw.ellipse(s, (150, 224, 190), (18, 30 + squash, 16, 10))
    pygame.draw.ellipse(s, (222, 250, 236), (20, 31 + squash, 8, 4))     # gloss
    pygame.draw.ellipse(s, (222, 250, 236), (34, 44 + squash, 4, 2))
    _ell(s, (26, 36, 40), 26, 40, 2.6, 3.2)                              # eyes
    _ell(s, (26, 36, 40), 38, 40, 2.6, 3.2)
    _ell(s, (250, 250, 252), 25.4, 39, 1.1, 1.3)
    _ell(s, (250, 250, 252), 37.4, 39, 1.1, 1.3)
    pygame.draw.arc(s, (32, 60, 52), (27, 42, 10, 7), 3.5, 6.0, 2)       # mouth
    _finish(s)
    return s


def _bat(frame=0) -> pygame.Surface:
    s = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
    up = 1 if frame else 0
    _shadow(s, 32, 60, 18, 6)
    for sx in (-1, 1):
        pygame.draw.polygon(s, (72, 52, 78), [(32 + sx * 4, 32 - up * 3),
                                              (32 + sx * 24, 22 - up * 5),
                                              (32 + sx * 20, 34),
                                              (32 + sx * 12, 32)])
        pygame.draw.line(s, (48, 34, 54), (32 + sx * 8, 31), (32 + sx * 22, 26), 1)
    _ell(s, (60, 46, 66), 32, 34, 8, 9)
    _ell(s, (88, 68, 94), 32, 32, 6.5, 7)
    pygame.draw.polygon(s, (60, 46, 66), [(27, 27), (25, 18), (31, 26)])
    pygame.draw.polygon(s, (60, 46, 66), [(37, 27), (39, 18), (33, 26)])
    _ell(s, (250, 200, 120), 29, 31, 1.6, 1.6)
    _ell(s, (250, 200, 120), 35, 31, 1.6, 1.6)
    _finish(s)
    return s


def _snake(frame=0) -> pygame.Surface:
    s = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
    _shadow(s, 32, 60, 30, 8)
    pts = [(14, 54), (24, 46), (38, 50), (48, 42), (42, 34), (30, 32)]
    for i in range(len(pts) - 1):
        col = (86, 148, 74) if i % 2 == 0 else (68, 124, 60)
        pygame.draw.line(s, col, pts[i], pts[i + 1], 9)
        pygame.draw.line(s, (118, 178, 96), pts[i], pts[i + 1], 3)
    hx, hy = 28, 26
    _ell(s, (86, 146, 72), hx, hy, 9.5, 7.4)
    _ell(s, (120, 184, 96), hx - 1, hy - 1, 7.2, 5.4)
    _ell(s, (150, 206, 116), hx - 2, hy - 3, 3.6, 2.2)
    pygame.draw.line(s, (52, 96, 46), (hx - 7, hy + 3.4), (hx + 8, hy + 3.0), 1)
    pygame.draw.line(s, (52, 96, 46), (hx - 6, hy - 3.4), (hx + 7, hy - 3.6), 1)
    _ell(s, (250, 230, 120), hx - 3.6, hy - 1.8, 2.0, 2.0)
    _ell(s, (250, 230, 120), hx + 3.8, hy - 1.8, 2.0, 2.0)
    _ell(s, (30, 26, 32), hx - 3.6, hy - 1.6, 0.9, 1.4)
    _ell(s, (30, 26, 32), hx + 3.8, hy - 1.6, 0.9, 1.4)
    _ell(s, (36, 30, 36), hx - 6.4, hy + 1.2, 0.8, 0.6)
    _ell(s, (36, 30, 36), hx + 7.0, hy + 1.2, 0.8, 0.6)
    pygame.draw.line(s, (200, 60, 60), (hx + 8, hy + 2), (hx + 14, hy + 4), 2)
    pygame.draw.line(s, (200, 60, 60), (hx + 14, hy + 4), (hx + 12, hy + 7), 2)
    _finish(s)
    return s


def _chicken(frame=0) -> pygame.Surface:
    s = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
    _shadow(s, 32, 60, 20, 7)
    pygame.draw.ellipse(s, (238, 234, 224), (20, 30, 24, 22))
    pygame.draw.ellipse(s, (252, 250, 244), (22, 32, 18, 14))
    _ell(s, (232, 228, 216), 40, 30, 7, 6.5)
    _ell(s, (220, 214, 200), 36, 26, 4, 3)
    pygame.draw.polygon(s, (230, 176, 60), [(44, 30), (50, 31), (44, 33)])
    pygame.draw.polygon(s, (206, 68, 60), [(40, 22), (42, 18), (45, 22)])
    pygame.draw.polygon(s, (206, 68, 60), [(38, 24), (39, 19), (43, 23)])
    _ell(s, (30, 26, 32), 40, 28, 1.2, 1.2)
    pygame.draw.line(s, (216, 176, 70), (30, 50), (30, 58), 2)
    pygame.draw.line(s, (216, 176, 70), (36, 50), (36, 58), 2)
    _finish(s)
    return s


def _cow(frame=0) -> pygame.Surface:
    """Heavy white body, black patches, horns, udder and hooves."""
    return _quadruped(body=(238, 236, 230), belly=(250, 248, 244), head_c=(244, 242, 236),
                      frame=frame, size=1.02, ears="droop", tail="tuft",
                      snout=(230, 178, 170), snout_len=5.6, snout_ry=4.2,
                      body_len=18.5, body_h=11.8, head_r=8.4, head_dx=17.0, head_dy=-9.0,
                      leg_x=(19, 29, 41, 47), leg_w=5.2, leg_len=0.98,
                      hooves=True, udder=True, horns=True, patches=True, neck=1.0)


def _sheep(frame=0) -> pygame.Surface:
    """Bumpy fleece, black face and legs."""
    s = _quadruped(body=(236, 234, 228), belly=(246, 244, 238), head_c=(64, 58, 56),
                   frame=frame, size=0.88, ears="droop", tail="bushy",
                   snout=(52, 48, 46), snout_len=4.0, snout_ry=3.2,
                   body_len=16.5, body_h=11.0, head_r=7.4, head_dx=15.0, head_dy=-7.0,
                   leg_x=(21, 30, 39, 45), leg_w=3.8, leg_len=0.94, fleece=True)
    for i in range(9):
        _ell(s, (250, 248, 244), 20 + (i % 5) * 5, 38 + (i // 5) * 5, 4, 3.4)
    return s


def _wolf(frame=0) -> pygame.Surface:
    """Lean and low, long muzzle, tall pointed ears, bushy tail, claws."""
    return _quadruped(body=(146, 148, 158), belly=(182, 184, 192), head_c=(158, 158, 168),
                      frame=frame, size=0.94, ears="up", tail="bushy",
                      snout=(112, 112, 122), snout_len=8.0, snout_ry=3.4,
                      body_len=17.0, body_h=8.6, head_r=7.8, head_dx=17.5, head_dy=-6.0,
                      leg_x=(22, 31, 39, 45), leg_w=3.6, leg_len=1.06,
                      claws=True, eye=(242, 200, 86), neck=0.6)


def _boar(frame=0) -> pygame.Surface:
    """Low and front-heavy: bristly ridge, flat snout disc, tusks, short thick legs."""
    return _quadruped(body=(104, 78, 58), belly=(138, 106, 78), head_c=(118, 90, 66),
                      frame=frame, size=1.0, ears="up", tail="thin",
                      tusks=True, snout=(154, 116, 100), snout_len=6.4, snout_ry=4.4,
                      snout_disc=True, body_len=17.5, body_h=10.6, head_r=8.6,
                      head_dx=15.5, head_dy=-5.4, leg_x=(20, 29, 40, 46), leg_w=5.0,
                      leg_len=0.9, hump=True, bristles=True, neck=0.8)


def _bear(frame=0) -> pygame.Surface:
    """Massive: shoulder hump, broad head, small round ears, thick legs, claws."""
    return _quadruped(body=(96, 70, 52), belly=(128, 96, 72), head_c=(112, 82, 62),
                      frame=frame, size=1.24, ears="round", tail="bushy",
                      snout=(148, 114, 90), snout_len=5.0, snout_ry=4.6,
                      body_len=19.0, body_h=13.0, head_r=9.6, head_dx=15.0, head_dy=-9.5,
                      leg_x=(19, 29, 41, 47), leg_w=6.0, leg_len=0.96,
                      hump=True, claws=True, neck=0.9)


MONSTER_BUILDERS = {
    "goblin": lambda f, v: _goblin(f, False, v),
    "brute": lambda f, v: _goblin(f, True, v),
    "orc": lambda f, v: _orc(f, v),
    "bandit": lambda f, v: _bandit(f, v),
    "skeleton": lambda f, v: _skeleton(f, v),
    "wraith": lambda f, v: _wraith(f, v),
    "troll": lambda f, v: _troll(f, v),
    "imp": lambda f, v: _imp(f, v),
    "golem": lambda f, v: _golem(f, v),
    "spider": lambda f, v: _spider(f),
    "slime": lambda f, v: _slime(f),
    "bat": lambda f, v: _bat(f),
    "snake": lambda f, v: _snake(f),
    "wolf": lambda f, v: _wolf(f),
    "boar": lambda f, v: _boar(f),
    "bear": lambda f, v: _bear(f),
    "cow": lambda f, v: _cow(f),
    "sheep": lambda f, v: _sheep(f),
    "chicken": lambda f, v: _chicken(f),
}

NPC_LOOKS = {
    "peasant": dict(skin="tan", hair="blond", shirt="brown", pants="leather",
                    boots="brown", hat="straw"),
    "farmer": dict(skin="tan", hair="brown", shirt="green", pants="leather",
                   boots="brown", hat="straw"),
    "smith": dict(skin="tan", hair="black", shirt="black", pants="black",
                  boots="black", build=1.22, shoulder=True, beard="brown"),
    "elder": dict(skin="pale", hair="white", shirt="violet", pants="violet",
                  boots="black", hat="wizard", beard="white"),
    "merchant": dict(skin="light", hair="brown", shirt="yellow", pants="teal",
                     boots="brown", hat="cap"),
    "guard": dict(skin="light", hair="brown", shirt="grey", pants="grey",
                  boots="black", hat="helm", shoulder=True, build=1.15),
    "healer": dict(skin="pale", hair="red", shirt="white", pants="teal",
                   boots="brown", hat="hood"),
    "child": dict(skin="light", hair="blond", shirt="red", pants="blue",
                  boots="brown", size=0.72),
}


_sprite_cache: dict[str, pygame.Surface] | None = None


def build_sprites() -> dict[str, pygame.Surface]:
    global _sprite_cache
    if _sprite_cache is not None:
        return _sprite_cache
    out: dict[str, pygame.Surface] = {}

    def add(key: str, surf: pygame.Surface) -> None:
        out[key] = surf
        out[key + "_f"] = pygame.transform.flip(surf, True, False)

    for view in ("down", "up", "side"):
        for frame in (0, 1):
            add(f"hero_{view}_{frame}",
                _humanoid(skin="light", hair="brown", shirt="red", pants="blue",
                          boots="brown", view=view, frame=frame))
    for name, look in NPC_LOOKS.items():
        for frame in (0, 1):
            add(f"npc_{name}_{frame}", _humanoid(view="down", frame=frame, **look))
    for kind, builder in MONSTER_BUILDERS.items():
        for frame in (0, 1):
            add(f"{kind}_down_{frame}", builder(frame, "down"))
            add(f"{kind}_side_{frame}", builder(frame, "side"))
    # the Ninja Adventure pack overrides the procedural actors when its assets are
    # present; the procedural art stays as the fallback for anything missing
    try:
        import packart
        for key, surf in packart.build().items():
            out[key] = surf
    except Exception:
        pass
    _sprite_cache = out
    return out


# ---------------------------------------------------------------- item icons
def _i_potion(s, col_l, col_d) -> None:
    pygame.draw.rect(s, (206, 198, 180), (9, 3, 6, 3))
    pygame.draw.polygon(s, col_d, [(11, 6), (13, 6), (15, 9), (15, 18), (9, 18), (9, 9)])
    pygame.draw.polygon(s, col_l, [(11, 7), (13, 7), (14, 10), (14, 17), (10, 17), (10, 10)])
    pygame.draw.ellipse(s, col_l, (9, 11, 7, 7))
    _ell(s, mix(col_l, (255, 255, 255), 0.5), 12, 12, 1.6, 1.4)
    pygame.draw.rect(s, (120, 110, 96), (9, 8, 7, 2))


def _i_sword(s, blade, guard, hilt) -> None:
    pygame.draw.polygon(s, blade, [(11, 2), (14, 2), (14, 15), (12.5, 17), (11, 15)])
    pygame.draw.line(s, mix(blade, (255, 255, 255), 0.5), (11.6, 3), (11.6, 14), 1)
    pygame.draw.rect(s, guard, (7, 15, 11, 2))
    pygame.draw.rect(s, hilt, (11, 17, 3, 5))
    _ell(s, mix(hilt, (255, 255, 255), 0.3), 12, 22, 1.6, 1.6)


def _i_axe(s, blade, handle) -> None:
    pygame.draw.line(s, handle, (12, 22), (12, 5), 3)
    pygame.draw.polygon(s, blade, [(12, 4), (19, 7), (18, 13), (12, 13)])
    pygame.draw.polygon(s, mix(blade, (255, 255, 255), 0.35),
                        [(13, 5), (17, 7), (16, 9), (13, 9)])


def _i_armor(s, col, col_d) -> None:
    pygame.draw.polygon(s, col_d, [(12, 3), (20, 6), (19, 17), (12, 21), (5, 17), (4, 6)])
    pygame.draw.polygon(s, col, [(12, 5), (18, 7), (17, 16), (12, 19), (7, 16), (6, 7)])
    pygame.draw.line(s, mix(col, (255, 255, 255), 0.35), (12, 6), (12, 18), 1)
    pygame.draw.line(s, col_d, (6, 11), (18, 11), 1)


def _i_shield(s, col, col_d) -> None:
    pygame.draw.polygon(s, col_d, [(12, 3), (20, 7), (18, 15), (12, 21), (6, 15), (4, 7)])
    pygame.draw.polygon(s, col, [(12, 5), (18, 8), (16, 14), (12, 19), (8, 14), (6, 8)])
    pygame.draw.line(s, GOLD, (12, 7), (12, 17), 2)
    pygame.draw.line(s, GOLD, (7, 10), (17, 10), 2)


def _i_ring(s, gem) -> None:
    pygame.draw.circle(s, GOLD, (12, 14), 6, 2)
    _ell(s, gem, 12, 6, 3, 3.4)
    _ell(s, mix(gem, (255, 255, 255), 0.5), 11, 5, 1.2, 1.2)


def _i_gem(s, col) -> None:
    pygame.draw.polygon(s, shade(col, 0.7), [(12, 3), (19, 9), (16, 19), (8, 19), (5, 9)])
    pygame.draw.polygon(s, col, [(12, 5), (17, 10), (15, 17), (9, 17), (7, 10)])
    pygame.draw.line(s, mix(col, (255, 255, 255), 0.6), (12, 6), (12, 16), 1)


def _i_coin(s) -> None:
    pygame.draw.circle(s, GOLD_D, (12, 13), 8)
    pygame.draw.circle(s, GOLD, (12, 12), 7)
    _ell(s, mix(GOLD, (255, 255, 255), 0.45), 10, 10, 3, 2.4)
    pygame.draw.line(s, GOLD_D, (12, 8), (12, 16), 1)


def _i_leaf(s, col) -> None:
    pygame.draw.polygon(s, shade(col, 0.75), [(12, 21), (5, 10), (9, 4), (16, 6), (18, 13)])
    pygame.draw.polygon(s, col, [(12, 19), (7, 10), (10, 6), (15, 8), (16, 13)])
    pygame.draw.line(s, mix(col, (255, 255, 255), 0.4), (11, 18), (12, 7), 1)
    pygame.draw.line(s, shade(col, 0.7), (8, 12), (14, 9), 1)


def _i_berry(s) -> None:
    """A little cluster of red berries with two leaves."""
    for (cx, cy) in ((8, 13), (16, 13), (12, 18)):
        pygame.draw.circle(s, (168, 34, 46), (cx, cy), 4)
        pygame.draw.circle(s, (222, 62, 66), (cx - 1, cy - 1), 3)
        pygame.draw.circle(s, (250, 176, 168), (cx - 2, cy - 2), 1)
    pygame.draw.line(s, (96, 150, 74), (12, 9), (12, 5), 2)
    pygame.draw.polygon(s, (110, 172, 84), [(12, 6), (17, 4), (13, 9)])
    pygame.draw.polygon(s, (86, 148, 66), [(12, 7), (7, 5), (11, 10)])


def _i_flower(s) -> None:
    """Five petals around a golden heart, with a stem."""
    pygame.draw.line(s, (96, 150, 74), (12, 12), (12, 21), 2)
    pygame.draw.polygon(s, (110, 172, 84), [(12, 16), (7, 13), (12, 19)])
    for a in range(5):
        ang = -math.pi / 2 + a * math.tau / 5
        px = 12 + math.cos(ang) * 5.2
        py = 10 + math.sin(ang) * 5.2
        pygame.draw.circle(s, (232, 108, 168), (int(px), int(py)), 4)
        pygame.draw.circle(s, (250, 168, 208), (int(px - 1), int(py - 1)), 2)
    pygame.draw.circle(s, (240, 200, 78), (12, 10), 3)
    pygame.draw.circle(s, (255, 238, 150), (11, 9), 1)


def _i_mushroom(s, cap, stem) -> None:
    pygame.draw.rect(s, stem, (10, 12, 5, 9))
    pygame.draw.ellipse(s, shade(cap, 0.7), (4, 5, 17, 11))
    pygame.draw.ellipse(s, cap, (5, 6, 15, 9))
    _ell(s, mix(cap, (255, 255, 255), 0.5), 9, 9, 1.8, 1.4)
    _ell(s, (250, 246, 240), 14, 11, 1.4, 1.2)


def _i_fang(s, col=(238, 232, 210)) -> None:
    pygame.draw.polygon(s, shade(col, 0.75), [(12, 3), (16, 12), (12, 21), (8, 12)])
    pygame.draw.polygon(s, col, [(12, 5), (15, 12), (12, 19), (9, 12)])
    pygame.draw.line(s, (255, 255, 255), (11, 7), (10, 14), 1)


def _i_pelt(s, col) -> None:
    pygame.draw.polygon(s, shade(col, 0.7), [(6, 5), (18, 4), (21, 12), (16, 21),
                                             (7, 20), (3, 12)])
    pygame.draw.polygon(s, col, [(8, 7), (17, 6), (19, 12), (15, 19), (8, 18), (5, 12)])
    pygame.draw.line(s, shade(col, 0.6), (12, 7), (12, 18), 1)


def _i_feather(s, col) -> None:
    pygame.draw.polygon(s, shade(col, 0.75), [(12, 2), (17, 10), (12, 20), (7, 10)])
    pygame.draw.polygon(s, col, [(12, 4), (16, 10), (12, 18), (8, 10)])
    pygame.draw.line(s, mix(col, (255, 255, 255), 0.4), (12, 5), (12, 17), 1)


def _i_ore(s, col) -> None:
    pygame.draw.polygon(s, shade((128, 128, 134), 0.7),
                        [(5, 18), (8, 8), (16, 5), (20, 12), (17, 20)])
    pygame.draw.polygon(s, (128, 128, 134), [(7, 17), (10, 9), (16, 7), (18, 12), (16, 18)])
    for (x, y) in ((11, 12), (15, 11), (13, 15)):
        _ell(s, col, x, y, 2.2, 2.2)
        _ell(s, mix(col, (255, 255, 255), 0.5), x - 0.6, y - 0.6, 1, 1)


def _i_bone(s) -> None:
    pygame.draw.line(s, (232, 226, 208), (7, 17), (17, 7), 3)
    for (x, y) in ((7, 17), (17, 7)):
        _ell(s, (238, 232, 214), x - 1.6, y - 1.6, 2.2, 2.2)
        _ell(s, (238, 232, 214), x + 1.6, y + 1.6, 2.2, 2.2)


def _i_scroll(s) -> None:
    pygame.draw.rect(s, (232, 220, 186), (6, 5, 13, 15))
    pygame.draw.rect(s, (204, 188, 150), (6, 5, 13, 3))
    pygame.draw.rect(s, (204, 188, 150), (6, 17, 13, 3))
    for y in (9, 12, 15):
        pygame.draw.line(s, (120, 108, 84), (8, y), (17, y), 1)


def _i_skull(s) -> None:
    _ell(s, (228, 222, 204), 12, 11, 7, 6.5)
    pygame.draw.rect(s, (228, 222, 204), (9, 14, 6, 5))
    _ell(s, (30, 28, 34), 9.5, 11, 2.2, 2.4)
    _ell(s, (30, 28, 34), 14.5, 11, 2.2, 2.4)
    pygame.draw.line(s, (150, 144, 128), (11, 16), (11, 19), 1)
    pygame.draw.line(s, (150, 144, 128), (13, 16), (13, 19), 1)


def _i_meat(s) -> None:
    pygame.draw.ellipse(s, (156, 78, 66), (5, 6, 14, 12))
    pygame.draw.ellipse(s, (188, 100, 84), (6, 7, 12, 10))
    _ell(s, (222, 140, 120), 10, 10, 3, 2.4)
    pygame.draw.rect(s, (232, 226, 208), (16, 14, 6, 3))
    _ell(s, (240, 236, 220), 21, 15.5, 2, 2)


def _i_key(s) -> None:
    pygame.draw.circle(s, GOLD, (8, 8), 4, 2)
    pygame.draw.line(s, GOLD, (10, 10), (18, 19), 2)
    pygame.draw.line(s, GOLD, (15, 16), (18, 13), 2)
    pygame.draw.line(s, GOLD, (17, 18), (20, 15), 2)


ICON_BUILDERS = {
    "potion_red": lambda s: _i_potion(s, (216, 66, 62), (150, 40, 40)),
    "potion_blue": lambda s: _i_potion(s, (78, 140, 220), (44, 88, 158)),
    "potion_green": lambda s: _i_potion(s, (96, 200, 118), (48, 138, 74)),
    "potion_gold": lambda s: _i_potion(s, (238, 200, 92), (176, 132, 44)),
    "sword_rusty": lambda s: _i_sword(s, (168, 156, 138), (110, 100, 88), (108, 74, 44)),
    "sword_iron": lambda s: _i_sword(s, (206, 210, 218), (120, 124, 134), (92, 62, 40)),
    "sword_steel": lambda s: _i_sword(s, (228, 236, 246), GOLD, (72, 50, 34)),
    "sword_dragon": lambda s: _i_sword(s, (236, 190, 120), (176, 60, 52), (60, 40, 30)),
    "axe_goblin": lambda s: _i_axe(s, (146, 150, 158), (110, 76, 44)),
    "axe_steel": lambda s: _i_axe(s, (216, 224, 234), (92, 62, 38)),
    "armor_leather": lambda s: _i_armor(s, (150, 104, 60), (108, 72, 40)),
    "armor_iron": lambda s: _i_armor(s, (170, 176, 188), (112, 118, 130)),
    "armor_steel": lambda s: _i_armor(s, (204, 212, 226), (140, 148, 162)),
    "armor_mage": lambda s: _i_armor(s, (126, 96, 186), (82, 60, 128)),
    "shield_wood": lambda s: _i_shield(s, (150, 108, 62), (104, 72, 40)),
    "shield_iron": lambda s: _i_shield(s, (176, 182, 194), (112, 118, 130)),
    "ring_gold": lambda s: _i_ring(s, (238, 200, 92)),
    "ring_ruby": lambda s: _i_ring(s, (206, 62, 62)),
    "ring_sapphire": lambda s: _i_ring(s, (72, 116, 214)),
    "amulet": lambda s: _i_ring(s, (120, 200, 190)),
    "gem_emerald": lambda s: _i_gem(s, (72, 190, 118)),
    "gem_ruby": lambda s: _i_gem(s, (204, 62, 62)),
    "gem_sapphire": lambda s: _i_gem(s, (72, 116, 214)),
    "gold": _i_coin,
    "herb": lambda s: _i_leaf(s, (110, 172, 84)),
    "leaf": lambda s: _i_leaf(s, (86, 148, 66)),
    "berry": _i_berry,
    "flower": _i_flower,
    "mushroom": lambda s: _i_mushroom(s, (204, 74, 70), (238, 232, 214)),
    "ear": lambda s: _i_fang(s, (196, 148, 132)),
    "fang": _i_fang,
    "claw": lambda s: _i_fang(s, (222, 214, 196)),
    "pelt": lambda s: _i_pelt(s, (128, 96, 68)),
    "feather": lambda s: _i_feather(s, (226, 222, 240)),
    "silk": lambda s: _i_feather(s, (216, 224, 236)),
    "ore_iron": lambda s: _i_ore(s, (168, 172, 182)),
    "ore_gold": lambda s: _i_ore(s, (238, 200, 92)),
    "ore_mithril": lambda s: _i_ore(s, (140, 216, 224)),
    "bone": _i_bone,
    "skull": _i_skull,
    "scroll": _i_scroll,
    "meat": _i_meat,
    "key": _i_key,
    "honey": lambda s: _i_potion(s, (232, 186, 76), (168, 122, 40)),
    "cloth": lambda s: _i_pelt(s, (196, 186, 170)),
    "tusk": lambda s: _i_fang(s, (240, 236, 220)),
    "venom": lambda s: _i_potion(s, (140, 196, 74), (78, 128, 48)),
    "soul": lambda s: _i_gem(s, (168, 156, 226)),
    "wood": lambda s: _i_pelt(s, (140, 104, 64)),
    "stone": lambda s: _i_ore(s, (150, 150, 156)),
    "default": lambda s: _i_gem(s, (176, 176, 184)),
}

_icon_cache: dict[str, pygame.Surface] = {}


def item_icon_surface(icon_id: str) -> pygame.Surface:
    surf = _icon_cache.get(icon_id)
    if surf is None:
        s = pygame.Surface((ICON, ICON), pygame.SRCALPHA)
        ICON_BUILDERS.get(icon_id, ICON_BUILDERS["default"])(s)
        surf = s
        _icon_cache[icon_id] = surf
    return surf


def validate() -> list[str]:
    problems: list[str] = []
    if not pygame.get_init():
        pygame.init()
    sprites = build_sprites()
    if len(sprites) < 60:
        problems.append(f"only {len(sprites)} sprites built")
    for key, surf in sprites.items():
        if surf.get_size() != (SPRITE, SPRITE):
            problems.append(f"sprite {key} is {surf.get_size()}, expected {(SPRITE, SPRITE)}")
        if not pygame.mask.from_surface(surf).count():
            problems.append(f"sprite {key} is empty")
    for icon_id in ICON_BUILDERS:
        icon = item_icon_surface(icon_id)
        if icon.get_size() != (ICON, ICON):
            problems.append(f"icon {icon_id} is {icon.get_size()}")
        if not pygame.mask.from_surface(icon).count():
            problems.append(f"icon {icon_id} is empty")
    return problems


if __name__ == "__main__":
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))
    issues = validate()
    sprites = build_sprites()
    print(f"sprites: {len(sprites)} at {SPRITE}x{SPRITE} | icons: {len(ICON_BUILDERS)}")
    print("problems:", len(issues))
    for p in issues[:12]:
        print("  -", p)
    if os.environ.get("ART_DUMP"):
        keys = sorted(k for k in sprites if not k.endswith("_f"))
        cols = 10
        rows = (len(keys) + cols - 1) // cols
        sheet = pygame.Surface((cols * (SPRITE + 6), rows * (SPRITE + 6)))
        sheet.fill((34, 44, 56))
        for i, k in enumerate(keys):
            sheet.blit(sprites[k], (6 + (i % cols) * (SPRITE + 6),
                                    6 + (i // cols) * (SPRITE + 6)))
        pygame.image.save(sheet, "sprite_sheet.png")
        icons = sorted(ICON_BUILDERS)
        isheet = pygame.Surface((12 * (ICON + 4), ((len(icons) + 11) // 12) * (ICON + 4)))
        isheet.fill((34, 44, 56))
        for i, k in enumerate(icons):
            isheet.blit(item_icon_surface(k), (4 + (i % 12) * (ICON + 4),
                                               4 + (i // 12) * (ICON + 4)))
        pygame.image.save(isheet, "icon_sheet.png")
        print("sheets written: sprite_sheet.png, icon_sheet.png")
