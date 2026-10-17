#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless playtest for Pixel RPG 2.1 — fights, loots, trades and learns.

Walks to the nearest hostile monster, attacks, casts abilities, picks up loot,
sells everything at the merchant, spends skill points on the oak and renders every
frame.  Any exception (render or logic) fails the run.

Usage:  python playtest.py [frames]
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pygame

import game as G
import render as R
import skills as SK
import world as W

WIDTH, HEIGHT, ZOOM = 1920, 1080, 2


def main(frames: int = 3000) -> int:
    pygame.init()
    pygame.display.set_mode((64, 64))
    game = G.Game(seed=2027, sound=False)
    renderer = R.Renderer(game, WIDTH, HEIGHT, ZOOM)
    screen = pygame.Surface((WIDTH, HEIGHT))
    dt = 1 / 60
    kills = 0
    gold_start = game.player["gold"]
    learned_start = len(game.player["learned"])
    stuck = 0
    last = (game.player["x"], game.player["y"])
    sold = 0
    harvested = 0
    quests_taken = 0
    quests_done = 0

    try:
        i = 0
        for i in range(frames):
            p = game.player
            if game.overlay:
                game.update(dt, {"up": False, "down": False, "left": False, "right": False})
                renderer.draw(screen)
                continue

            # every so often: sell loot, spend a skill point, open an overlay
            if i % 260 == 0 and i > 0:
                game.overlay = "shop"
                game.shop_tab = "sell"
                game.shop_cursor = 0
                for _ in range(6):
                    if game.shop_lines():
                        game.shop_action()
                        sold += 1
                    game.shop_cursor = (game.shop_cursor + 1) % max(1, len(game.shop_lines()))
                game.overlay = None
            if i % 420 == 0 and game.skill_points > 0:
                for node in SK.SKILLS:
                    if game.learn(node["id"]):
                        break
            if i % 700 == 0:
                game.overlay = "skilltree"
                renderer.draw(screen)
                game.overlay = None
            if i % 900 == 0:
                game.overlay = "inventory"
                renderer.draw(screen)
                game.overlay = None
            # take work from the villagers and hand in whatever is finished
            if i % 300 == 0:
                for n in game.npcs:
                    for q in game.available_quests(n.get("kind", ""))[:2]:
                        if game.accept_quest(q["id"]):
                            quests_taken += 1
                    for q in game.ready_quests(n.get("kind", "")):
                        if "сдано" in game.turn_in_quest(q["id"]):
                            quests_done += 1
            # harvest whatever is in reach
            if i % 45 == 0:
                node = game.nearest_node()
                if node:
                    game.harvest(node)
                    harvested += 1
            if i % 150 == 0:
                game.overlay = "quests"
                renderer.draw(screen)
                game.overlay = None

            alive = [m for m in game.mobs if m["alive"] and not m["passive"]]
            target = min(alive, key=lambda m: math.hypot(m["x"] - p["x"], m["y"] - p["y"]),
                         default=None)
            if target and math.hypot(p["x"] - last[0], p["y"] - last[1]) < 0.4:
                stuck += 1
                if stuck > 300:            # teleport past an impassable thicket
                    p["x"], p["y"] = target["x"] - 1.4, target["y"]
                    stuck = 0
            else:
                stuck = 0
            last = (p["x"], p["y"])

            inp = {"up": False, "down": False, "left": False, "right": False}
            if target:
                dx = target["x"] - p["x"]
                dy = target["y"] - p["y"]
                dist = math.hypot(dx, dy)
                if dist > 1.5:
                    inp["right"] = dx > 0.3
                    inp["left"] = dx < -0.3
                    inp["down"] = dy > 0.3
                    inp["up"] = dy < -0.3
                else:
                    p["dir"] = (("right" if dx > 0 else "left") if abs(dx) > abs(dy)
                                else ("down" if dy > 0 else "up"))
                    if p["atk_t"] <= 0:
                        was = target["alive"]
                        game.attack()
                        kills += 1 if was and not target["alive"] else 0
                    if p["hotbar"] and p["mp"] > 10 and i % 90 == 0:
                        game.cast(i % len(p["hotbar"]))
            if p["hp"] < game.stats()["hp_max"] * 0.4:
                for idx, slot in enumerate(p["inventory"]):
                    if slot["id"] in ("potion", "potion_big", "elixir", "meat", "herb"):
                        game.use_slot(idx)
                        break
            game.update(dt, inp)
            renderer.draw(screen)
    except Exception:  # noqa: BLE001 — surfacing crashes is the point
        import traceback
        traceback.print_exc()
        print(f"PLAYTEST FAILED at frame {i}")
        pygame.quit()
        return 1

    p = game.player
    print(f"playtest: {frames} frames rendered | kills {kills} | level {p['level']} | "
          f"gold {gold_start} -> {p['gold']} | sold {sold} trades | "
          f"harvested {harvested} nodes | quests {quests_taken} taken, {quests_done} done | "
          f"skills {learned_start} -> {len(p['learned'])}/{len(SK.SKILLS)} | "
          f"mobs alive {sum(1 for m in game.mobs if m['alive'])} | "
          f"regions {len(game.visited)}/{len(game.world.regions)} | hp "
          f"{p['hp']:.0f}/{game.stats()['hp_max']:.0f}")
    if quests_done < 1:
        print("PLAYTEST WARNING: no quest was completed")
    print("PLAYTEST OK")
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3000))
