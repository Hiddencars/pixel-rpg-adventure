"""Собрать resources/icon.ico из пиксель-арта игры (dev-инструмент).

Иконка не рисуется отдельно: берётся спрайт героя из атласа и кладётся на
тёмный квадрат с золотой рамкой — тот же язык, что у интерфейса.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pygame
from PIL import Image

pygame.init()
pygame.display.set_mode((64, 64))

HERE = Path(__file__).resolve().parent
OUT = HERE / "resources" / "icon.ico"
SIZE = 256

BG = (17, 20, 30)
INK = (7, 9, 14)
GOLD = (240, 204, 108)
EDGE = (58, 70, 96)

surf = pygame.Surface((SIZE, SIZE))
surf.fill(BG)
# рамка в два пикселя
pygame.draw.rect(surf, INK, (0, 0, SIZE, SIZE), 8)
pygame.draw.rect(surf, EDGE, (8, 8, SIZE - 16, SIZE - 16), 4)
pygame.draw.rect(surf, GOLD, (16, 16, SIZE - 32, SIZE - 32), 3)
# уголки
for cx, cy, dx, dy in ((24, 24, 1, 1), (SIZE - 24, 24, -1, 1),
                       (24, SIZE - 24, 1, -1), (SIZE - 24, SIZE - 24, -1, -1)):
    pygame.draw.rect(surf, GOLD, (min(cx, cx + dx * 22), min(cy, cy + dy * 22), 22, 6))
    pygame.draw.rect(surf, GOLD, (min(cx, cx + dx * 6), min(cy, cy + dy * 22), 6, 22))

import sprites as SP  # noqa: E402  (после pygame.init)

built = SP.build_sprites()
spr = built.get("hero_down_0")
if spr is None:
    spr = next((v for k, v in built.items() if k.startswith("hero")), None)

if spr is not None:
    w, h = spr.get_size()
    scale = max(1, min((SIZE - 64) // w, (SIZE - 64) // h))
    spr = pygame.transform.scale(spr, (w * scale, h * scale))
    # тень под героем, чтобы он не висел в воздухе
    sh = pygame.Surface((spr.get_width(), max(6, spr.get_height() // 4)), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 120), sh.get_rect())
    surf.blit(sh, ((SIZE - spr.get_width()) // 2,
                   (SIZE + spr.get_height()) // 2 - sh.get_height() + 4))
    surf.blit(spr, ((SIZE - spr.get_width()) // 2, (SIZE - spr.get_height()) // 2))
else:
    pygame.draw.circle(surf, GOLD, (SIZE // 2, SIZE // 2), 60)

OUT.parent.mkdir(parents=True, exist_ok=True)
pygame.image.save(surf, str(HERE / "resources" / "icon_px.png"))
img = Image.open(HERE / "resources" / "icon_px.png").convert("RGBA")
img.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon ->", OUT, OUT.stat().st_size, "bytes")
