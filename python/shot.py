#!/usr/bin/env python3
"""Render frames to PNG for visual inspection (not part of the game)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).parent))

import pygame
import game as G


def shot(width, height, zoom, path, mode="play"):
    pygame.init()
    pygame.display.set_mode((64, 64))
    g = G.Game(seed=7)
    r = G.Renderer(g, width, height, zoom)
    screen = pygame.Surface((width, height))
    if mode == "play":
        # put the player in the village centre and open a quest panel
        g.player["x"], g.player["y"] = 50.5, 31.0
        g.update(1 / 60, {"down": False, "up": False, "left": False, "right": False})
        r.draw(screen)
    else:
        r.draw_menu(screen, G.DEFAULT_RES_INDEX, False, False)
    pygame.image.save(screen, path)
    print("saved", path, f"{width}x{height}", "zoom", zoom)
    pygame.quit()


if __name__ == "__main__":
    out = Path(os.environ.get("TEMP", "."))
    shot(1920, 1080, 4, str(out / "shot_1920.png"))
    shot(1920, 1080, 4, str(out / "shot_menu.png"), mode="menu")
    shot(1280, 720, 3, str(out / "shot_1280.png"))
    shot(960, 540, 2, str(out / "shot_960.png"))
