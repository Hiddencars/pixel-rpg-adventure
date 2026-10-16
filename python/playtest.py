#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless playtest: fight for ~2000 frames, rendering every frame (dev tool).

Walks to the nearest enemy, attacks, loots, opens the inventory, and renders each
frame into a Surface — so render-time crashes (the "invalid destination position for
blit" bug in 1.3.0 was one) fail loudly here instead of in the player's face.

Usage:  python playtest.py [frames]
Exit code 0 = clean run.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pygame

import game as G

W, H, Z = 1920, 1080, 4


def main(frames: int = 2000) -> int:
    pygame.init()
    pygame.display.set_mode((64, 64))
    game = G.Game(seed=2026)
    renderer = G.Renderer(game, W, H, Z)
    screen = pygame.Surface((W, H))
    dt = 1 / 60
    kills = 0
    stuck = 0
    last = (game.player["x"], game.player["y"])

    try:
        i = 0
        for i in range(frames):
            alive = [m for m in game.mobs if m["alive"]]
            target = min(alive, key=lambda m: math.hypot(m["x"] - game.player["x"],
                                                         m["y"] - game.player["y"]),
                         default=None)
            # if the forest walls us off, step next to the target so the fight happens
            if target and math.hypot(game.player["x"] - last[0],
                                     game.player["y"] - last[1]) < 0.4:
                stuck += 1
                if stuck > 240:
                    game.player["x"], game.player["y"] = target["x"] - 1.2, target["y"]
                    stuck = 0
            else:
                stuck = 0
            last = (game.player["x"], game.player["y"])

            inp = {"up": False, "down": False, "left": False, "right": False}
            if target:
                dx = target["x"] - game.player["x"]
                dy = target["y"] - game.player["y"]
                if math.hypot(dx, dy) > 1.4:
                    inp["right"] = dx > 0.25
                    inp["left"] = dx < -0.25
                    inp["down"] = dy > 0.25
                    inp["up"] = dy < -0.25
                else:
                    game.player["dir"] = (("right" if dx > 0 else "left") if abs(dx) > abs(dy)
                                          else ("down" if dy > 0 else "up"))
                    if game.player["atk_t"] <= 0:
                        was_alive = target["alive"]
                        game.attack()
                        kills += 1 if was_alive and not target["alive"] else 0
            if i % 200 == 0:                      # render the inventory overlay too
                game.show_inventory = not game.show_inventory
            game.update(dt, inp)
            renderer.draw(screen)
    except Exception:  # noqa: BLE001 — the point of this tool is to surface crashes
        import traceback
        traceback.print_exc()
        print(f"PLAYTEST FAILED at frame {i}")
        pygame.quit()
        return 1

    print(f"playtest: {frames} frames rendered | kills {kills} | "
          f"level {game.player['level']} | gold {game.player['gold']} | "
          f"hp {game.player['hp']:.0f}/{game.player['hp_max']:.0f} | "
          f"mobs alive {sum(1 for m in game.mobs if m['alive'])} | drops {len(game.drops)}")
    print("PLAYTEST OK")
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000))
