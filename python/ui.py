#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пиксельный UI: рамки, полосы, слоты, тосты.

Весь интерфейс рисуется целыми пикселями на реальном экране: никаких
скруглений, полупрозрачных подложек и сглаженного текста. Панель — это
1 px обводка почти чёрным, светлая грань сверху-слева и тёмная снизу-справа,
как у кнопок в 8-битных играх.

Модуль ничего не знает об игре: на вход только Surface и координаты.
"""

from __future__ import annotations

import pygame

# ------------------------------------------------------------------ палитра
INK = (7, 9, 14)             # обводка
BG = (17, 20, 30)            # тело панели
BG_DARK = (12, 14, 21)       # утопленная область
BG_HI = (30, 36, 51)         # верхняя грань
EDGE = (58, 70, 96)          # рамка
EDGE_HI = (104, 122, 158)    # светлая грань
GOLD = (240, 204, 108)
GOLD_DIM = (150, 126, 66)
TEXT = (238, 232, 214)
TEXT_DIM = (176, 184, 204)
TEXT_MUTED = (132, 140, 162)

HP = (188, 56, 52)
HP_HI = (232, 108, 88)
MP = (54, 96, 186)
MP_HI = (104, 152, 232)
XP = (206, 172, 74)
GREEN = (126, 206, 108)
RED = (222, 84, 76)


def frame(surf: pygame.Surface, rect, fill=BG, edge=EDGE, hi=EDGE_HI,
          shadow: bool = True) -> pygame.Rect:
    """Пиксельная панель: обводка, светлая грань сверху-слева, тень снизу-справа."""
    r = pygame.Rect(rect)
    if shadow:
        pygame.draw.rect(surf, INK, (r.x + 2, r.y + 2, r.w, r.h))
    pygame.draw.rect(surf, fill, r)
    pygame.draw.rect(surf, edge, r, 1)
    pygame.draw.line(surf, hi, (r.x + 1, r.y + 1), (r.right - 2, r.y + 1))
    pygame.draw.line(surf, hi, (r.x + 1, r.y + 1), (r.x + 1, r.bottom - 2))
    pygame.draw.line(surf, BG_DARK, (r.x + 1, r.bottom - 2), (r.right - 2, r.bottom - 2))
    pygame.draw.line(surf, BG_DARK, (r.right - 2, r.y + 1), (r.right - 2, r.bottom - 2))
    return r


def inset(surf: pygame.Surface, rect, fill=BG_DARK, edge=INK) -> pygame.Rect:
    """Утопленная область: рамка внутрь, без светлых граней."""
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, fill, r)
    pygame.draw.rect(surf, edge, r, 1)
    pygame.draw.line(surf, EDGE, (r.x + 1, r.y + 1), (r.right - 2, r.y + 1))
    pygame.draw.line(surf, EDGE, (r.x + 1, r.y + 1), (r.x + 1, r.bottom - 2))
    return r


def bar(surf: pygame.Surface, rect, ratio: float, color, hi=None,
        back=(38, 28, 30), ticks: int = 0) -> pygame.Rect:
    """Полоса в пиксельном стиле: заливка блоками, насечки каждые `ticks` px."""
    r = pygame.Rect(rect)
    ratio = max(0.0, min(1.0, ratio))
    inset(surf, r, back, INK)
    inner = r.inflate(-2, -2)
    if inner.w <= 0 or inner.h <= 0:
        return r
    w = int(inner.w * ratio)
    if w > 0:
        pygame.draw.rect(surf, color, (inner.x, inner.y, w, inner.h))
        if hi and inner.h > 3:
            pygame.draw.line(surf, hi, (inner.x, inner.y), (inner.x + w - 1, inner.y))
        if inner.h > 5:
            pygame.draw.line(surf, tuple(max(0, c - 40) for c in color),
                             (inner.x, inner.bottom - 2), (inner.x + w - 1, inner.bottom - 2))
    if ticks > 0:
        for x in range(inner.x + ticks, inner.right, ticks):
            pygame.draw.line(surf, (0, 0, 0), (x, inner.y), (x, inner.bottom - 1))
    return r


def slot(surf: pygame.Surface, rect, active: bool = False, filled: bool = True,
         hotkey: str = "") -> pygame.Rect:
    """Слот хотбара/инвентаря: утопленный квадрат с пиксельной рамкой."""
    r = pygame.Rect(rect)
    if active:
        pygame.draw.rect(surf, GOLD, (r.x - 2, r.y - 2, r.w + 4, r.h + 4), 1)
    pygame.draw.rect(surf, INK, (r.x + 1, r.y + 1, r.w, r.h))
    pygame.draw.rect(surf, BG_HI if filled else BG_DARK, r)
    pygame.draw.rect(surf, EDGE if filled else (44, 50, 66), r, 1)
    pygame.draw.line(surf, INK, (r.x + 1, r.y + 1), (r.right - 2, r.y + 1))
    pygame.draw.line(surf, INK, (r.x + 1, r.y + 1), (r.x + 1, r.bottom - 2))
    return r


def text(surf: pygame.Surface, font: pygame.font.Font, msg: str, pos,
         color=TEXT, shadow: bool = True) -> pygame.Rect:
    """Текст без сглаживания, с пиксельной тенью в один пиксель."""
    img = font.render(msg, False, color)
    x, y = int(pos[0]), int(pos[1])
    if shadow:
        dark = tuple(c // 3 for c in color)
        surf.blit(font.render(msg, False, dark), (x + 1, y + 1))
    surf.blit(img, (x, y))
    return pygame.Rect(x, y, img.get_width(), img.get_height())


def text_right(surf, font, msg, right_x: int, y: int, color=TEXT, shadow=True) -> pygame.Rect:
    w = font.size(msg)[0]
    return text(surf, font, msg, (right_x - w, y), color, shadow)


def text_center(surf, font, msg, center_x: int, y: int, color=TEXT, shadow=True) -> pygame.Rect:
    w = font.size(msg)[0]
    return text(surf, font, msg, (center_x - w // 2, y), color, shadow)


def dither_rect(surf: pygame.Surface, rect, color, step: int = 2, alpha_color=None) -> None:
    """Шахматный узор — «прозрачность» в пиксель-арте вместо альфа-канала."""
    r = pygame.Rect(rect)
    for y in range(r.y, r.bottom, step):
        for x in range(r.x + ((y // step) % 2) * step, r.right, step * 2):
            surf.set_at((x, y), color)


_OVERLAY_CACHE: dict = {}


def shade(size, color=(6, 9, 15), alpha: int = 168) -> pygame.Surface:
    """Ровное затемнение одним спрайтом (кэш): один blit на кадр.

    Шахматный дизер поверх живого мира читался как сетка тайлов, поэтому фон
    под меню затемняется обычным полупрозрачным слоем — он не «мылит» пиксели,
    потому что просто притемняет их.
    """
    key = ("shade", tuple(size), tuple(color), alpha)
    surf = _OVERLAY_CACHE.get(key)
    if surf is None:
        surf = pygame.Surface(tuple(size), pygame.SRCALPHA)
        surf.fill((*tuple(color)[:3], alpha))
        if len(_OVERLAY_CACHE) > 10:
            _OVERLAY_CACHE.clear()
        _OVERLAY_CACHE[key] = surf
    return surf


def dither_overlay(size, color, step: int = 2) -> pygame.Surface:
    """Полноэкранная шахматка 50%, собранная один раз и закэшированная.

    Поштучный `set_at` на 1080p — это миллион вызовов на кадр; numpy собирает
    узор за миллисекунды, а дальше это один blit. Шахматка 2×2 даёт ровно
    половину плотности — так пиксель-арт делает «полупрозрачное затемнение».
    """
    key = (tuple(size), tuple(color), step)
    surf = _OVERLAY_CACHE.get(key)
    if surf is None:
        try:
            import numpy as np
            w, h = int(size[0]), int(size[1])
            ys, xs = np.mgrid[0:h, 0:w]
            mask = ((xs // step + ys // step) % 2 == 0)
            arr = np.zeros((h, w, 4), dtype=np.uint8)
            arr[mask] = (color[0], color[1], color[2], 255)
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.surfarray.blit_array(surf, np.transpose(arr, (1, 0, 2)))
        except Exception:
            surf = None
        if surf is None:
            surf = pygame.Surface(tuple(size), pygame.SRCALPHA)
            surf.fill((0, 0, 0, 0))
            for y in range(0, int(size[1]), step * 2):
                for x in range(0, int(size[0]), step * 2):
                    pygame.draw.rect(surf, (*color, 255), (x, y, step, step))
        if len(_OVERLAY_CACHE) > 8:
            _OVERLAY_CACHE.clear()
        _OVERLAY_CACHE[key] = surf
    return surf


def icon_frame(surf: pygame.Surface, rect, color=EDGE) -> None:
    pygame.draw.rect(surf, color, pygame.Rect(rect), 1)
