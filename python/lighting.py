"""HD-2D освещение для Pixel patch.

Идея: мир рисуется как раньше, а сверху кладётся карта света в ЛОГИЧЕСКОМ
разрешении (self.logical, обычно 640×360). Карта умножается на кадр
(BLEND_RGB_MULT), поэтому:

  * «амбиент» — это цвет множителя в точке: день (255,253,246) почти не меняет
    картинку, ночь (70,82,132) уводит всё в синий;
  * источники света добавляются к карте аддитивно (BLEND_RGB_ADD), то есть
    возвращают множитель к 255 — вокруг костра мир снова «дневной», но тёплый.

Стоимость: один fill + N blit'ов градиентов + один мультиплай по 640×360.
Попиксельные градиенты строятся ОДИН раз на радиус/цвет и кэшируются.

Чтобы свет читался как свет, а не как вырезанный кружок, интенсивность падает
по (1 - d)**power, а градиент строится в половинном разрешении и растягивается
smoothscale — на глаз неотличимо, а set_at-цикл вдвое короче.
"""
from __future__ import annotations

import math

import pygame

from art import TILE

DAY_LENGTH = 480.0          # секунд на полные сутки (8 минут)
START_PHASE = 0.16          # новая игра начинается утром

# Ключевые кадры суток: (фаза 0..1, цвет множителя). Между ними — линейная
# интерполяция, поэтому закат и рассвет получаются сами.
AMBIENT_KEYS = (
    (0.00, (150, 142, 168)),    # рассвет, холодный
    (0.06, (206, 192, 190)),
    (0.14, (240, 234, 220)),    # утро
    (0.30, (255, 253, 246)),    # полдень
    (0.44, (250, 236, 208)),    # после полудня, тёплый
    (0.50, (206, 158, 146)),    # закат
    (0.56, (138, 120, 158)),
    (0.66, (86, 96, 142)),      # сумерки
    (0.78, (70, 82, 132)),      # ночь
    (0.90, (96, 104, 148)),
    (1.00, (150, 142, 168)),    # снова рассвет
)


def _lerp(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def ambient_at(phase: float):
    """Цвет множителя для фазы суток."""
    phase %= 1.0
    prev_p, prev_c = AMBIENT_KEYS[0]
    for p, c in AMBIENT_KEYS[1:]:
        if phase <= p:
            span = max(1e-6, p - prev_p)
            return _lerp(prev_c, c, (phase - prev_p) / span)
        prev_p, prev_c = p, c
    return AMBIENT_KEYS[-1][1]


def darkness(phase: float) -> float:
    """0 — яркий день, 1 — глухая ночь. Для плавных эффектов (светлячки, окна)."""
    a = ambient_at(phase)
    lum = (a[0] * 0.299 + a[1] * 0.587 + a[2] * 0.114) / 255.0
    return max(0.0, min(1.0, (1.0 - lum) / 0.62))


PHASE_NAMES = (
    (0.04, "Рассвет"),
    (0.14, "Утро"),
    (0.40, "День"),
    (0.44, "После полудня"),
    (0.54, "Закат"),
    (0.66, "Сумерки"),
    (0.94, "Ночь"),
    (1.01, "Рассвет"),
)


def phase_name(phase: float) -> str:
    phase %= 1.0
    for limit, name in PHASE_NAMES:
        if phase < limit:
            return name
    return "Ночь"


class LightLayer:
    """Строит карту света и умножает ею логический кадр."""

    def __init__(self) -> None:
        self._grad: dict = {}
        self.map: pygame.Surface | None = None
        self._size = (0, 0)
        self.forced_phase: float | None = None   # для скриншотов/тестов
        self.phase = START_PHASE
        self.lights_drawn = 0

    # -- градиенты -----------------------------------------------------------
    def gradient(self, radius: int, color, power: float = 1.9) -> pygame.Surface:
        key = (int(radius), tuple(color), round(power, 2))
        surf = self._grad.get(key)
        if surf is not None:
            return surf
        radius = max(8, int(radius))
        half = max(4, radius // 2)
        small = pygame.Surface((half * 2, half * 2))
        small.fill((0, 0, 0))
        r = float(half)
        cr, cg, cb = color
        for y in range(half * 2):
            dy = y - r + 0.5
            for x in range(half * 2):
                dx = x - r + 0.5
                d = math.hypot(dx, dy) / r
                if d >= 1.0:
                    continue
                f = (1.0 - d) ** power
                small.set_at((x, y), (int(cr * f), int(cg * f), int(cb * f)))
        surf = pygame.transform.smoothscale(small, (radius * 2, radius * 2))
        self._grad[key] = surf
        return surf

    # -- кадр ----------------------------------------------------------------
    def render(self, logical: pygame.Surface, phase: float, cam_x: float,
               cam_y: float, lights, enabled: bool = True) -> None:
        """lights: [(tile_x, tile_y, radius_tiles, (r,g,b), power), ...]"""
        if not enabled:
            self.lights_drawn = 0
            return
        self.phase = phase
        w, h = logical.get_size()
        if self._size != (w, h) or self.map is None:
            self.map = pygame.Surface((w, h))
            self._size = (w, h)

        self.map.fill(ambient_at(phase))
        drawn = 0
        for (wx, wy, rad_t, col, power) in lights:
            px = (wx - cam_x + 0.5) * TILE
            py = (wy - cam_y + 0.5) * TILE
            rad = int(rad_t * TILE)
            if px + rad < 0 or px - rad > w or py + rad < 0 or py - rad > h:
                continue
            g = self.gradient(rad, col, power)
            self.map.blit(g, (int(px - rad), int(py - rad)),
                          special_flags=pygame.BLEND_RGB_ADD)
            drawn += 1
        self.lights_drawn = drawn
        logical.blit(self.map, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
