#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless self-test for Pixel patch 2.4 — run as `python game.py --selftest`.

Exercises real logic (world, spawning, combat, loot, trading, the skill tree,
saving) and renders frames at every resolution, including each overlay.  Writes
its report to %TEMP%/pixelrpg_selftest.txt so a windowed .exe can be verified.
"""

from __future__ import annotations

import contextlib
import io
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pygame

import art
import items as IT
import lighting
import music as MUS
import quests as QST
import skills as SK
import sounds as SFX
import sprites as SP
import world as W


def main() -> int:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = _body()
    text = buf.getvalue()
    print(text, end="")
    report = Path(os.environ.get("TEMP", ".")) / "pixelrpg_selftest.txt"
    try:
        report.write_text(text, encoding="utf-8")
        print(f"report written to {report}")
    except OSError:
        pass
    return code


def _body() -> int:
    import game as G
    import render as R

    pygame.init()
    pygame.display.set_mode((64, 64))
    problems: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            problems.append(msg)

    # ---------------------------------------------------------------- assets
    for label, issues in (("art", art.validate()), ("sprites", SP.validate()),
                          ("items", IT.validate()), ("skills", SK.validate()),
                          ("sounds", SFX.validate()), ("music", MUS.validate()),
                          ("quests", QST.validate())):
        print(f"{label}: {len(issues)} problems")
        for p in issues[:5]:
            print("   -", p)
        problems.extend(f"{label}: {p}" for p in issues[:5])

    # ---------------------------------------------------------------- world
    game = G.Game(seed=2026, sound=False)
    stats = game.world.stats()
    print(f"world {W.MAP_W}x{W.MAP_H} = {W.MAP_W * W.MAP_H} tiles | land {stats['land_pct']}% "
          f"| water {stats['water_pct']}% | trees {stats['trees']} | houses {stats['houses']} "
          f"| objects {stats['objects']} | decor {stats['decor']}")
    check(stats["land_pct"] >= 55, f"only {stats['land_pct']}% land")
    check(stats["trees"] >= 700, f"only {stats['trees']} trees")
    check(stats["houses"] >= 8, f"only {stats['houses']} houses")

    reach = game.world.reachable_from(W.SPAWN_TILE)
    print("reachable tiles from spawn:", len(reach))
    check(len(reach) > 5000, f"only {len(reach)} reachable tiles")

    game.ensure_reachable()
    for n in game.npcs:
        tile = (int(n["x"]), int(n["y"]))
        ok = tile in reach
        print(f"  npc {n['name']:12s} {tile} reachable: {ok}")
        check(ok, f"NPC {n['name']} unreachable")
    # a house sprite is 3.6 tiles tall and is drawn after anything standing above it,
    # so no NPC may sit inside the band a house covers
    for n in game.npcs:
        for o in game.world.objects:
            if not o["kind"].startswith("house"):
                continue
            if (o["x"] - 0.5 <= n["x"] <= o["x"] + 3.5) and \
                    (o["y"] - 4.6 <= n["y"] <= o["y"] + 1.9):
                problems.append(f"NPC {n['name']} is hidden behind {o['kind']} at "
                                f"({o['x']},{o['y']})")
    print("npc/house overlap check done")

    kinds = {}
    for m in game.mobs:
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    print(f"mobs spawned: {len(game.mobs)} across {len(kinds)} species: "
          f"{dict(sorted(kinds.items()))}")
    check(len(kinds) >= 8, f"only {len(kinds)} monster species spawned")
    check(len(game.mobs) >= 60, f"only {len(game.mobs)} monsters")

    # ------------------------------------------------------------- inventory
    p = game.player
    print("start inventory:", [(s["id"], s["count"]) for s in p["inventory"]])
    check(game.add_item("ear", 5), "add_item(ear x5) failed")
    check(game.count_item("ear") == 5, "ear stacking failed")
    for _ in range(G.INV_SLOTS + 4):          # swords do not stack, so the bag fills
        game.add_item("sword_rusty", 1)
    print("bag slots after overflow attempt:", len(p["inventory"]), "/", G.INV_SLOTS)
    check(len(p["inventory"]) <= G.INV_SLOTS, "inventory exceeded its slot limit")
    check(len(p["inventory"]) == G.INV_SLOTS, "inventory did not fill up")
    # make room again
    p["inventory"] = [s for s in p["inventory"] if s["id"] != "sword_rusty"]

    # ------------------------------------------------------------- equipment
    base_atk = game.stats()["atk"]
    game.add_item("sword_steel", 1)
    idx = next(i for i, s in enumerate(p["inventory"]) if s["id"] == "sword_steel")
    game.use_slot(idx)
    armed = game.stats()["atk"]
    print(f"attack: bare {base_atk:.1f} -> armed {armed:.1f} "
          f"(weapon {p['equip']['weapon']})")
    check(armed > base_atk, "equipping a weapon did not raise attack")
    game.add_item("armor_iron", 1)
    idx = next(i for i, s in enumerate(p["inventory"]) if s["id"] == "armor_iron")
    game.use_slot(idx)
    check(game.stats()["def"] > 0, "equipping armour did not raise defence")
    game.add_item("ring_ruby", 1)
    idx = next(i for i, s in enumerate(p["inventory"]) if s["id"] == "ring_ruby")
    game.use_slot(idx)
    print("equipment:", {k: v for k, v in p["equip"].items() if v})

    # ---------------------------------------------------------------- trading
    game.add_item("pelt", 6)
    gold_before = p["gold"]
    lines = game.shop_lines()
    print(f"shop (sell tab): {len(lines)} lines, first: {lines[0] if lines else None}")
    game.shop_tab = "sell"
    game.shop_cursor = 0
    msg = game.shop_action()
    print("sell:", msg, "| gold", gold_before, "->", p["gold"])
    check(p["gold"] > gold_before, "selling did not add gold")
    game.shop_tab = "buy"
    game.shop_cursor = 0
    buy_lines = game.shop_lines()
    p["gold"] = 500
    stock_before = game.merchant_stock.get(buy_lines[0][0], 0) if buy_lines else 0
    msg = game.shop_action()
    print("buy:", msg, "| gold 500 ->", p["gold"],
          "| stock", stock_before, "->", game.merchant_stock.get(buy_lines[0][0], 0) if buy_lines else 0)
    check(p["gold"] < 500, "buying did not cost gold")
    p["gold"] = 300
    total = game.sell_all_junk()
    print("sell all junk:", total, "| gold", p["gold"])

    # ------------------------------------------------------------ skill tree
    print(f"skill tree: {len(SK.SKILLS)} nodes, {len(SK.BRANCHES)} branches, "
          f"points {game.skill_points}")
    check(len(SK.SKILLS) >= 120, "fewer than 120 skills")
    learned = 0
    atk_before = game.stats()["atk"]
    for node in SK.SKILLS:
        if node["id"] == "root":
            continue
        game.skill_points += 6                 # enough for the most expensive node
        if game.learn(node["id"]):
            learned += 1
    print(f"learned {learned} nodes; attack {atk_before:.1f} -> {game.stats()['atk']:.1f}; "
          f"hp_max {game.stats()['hp_max']:.0f}; hotbar {len(p['hotbar'])}")
    check(learned >= 115, f"could only learn {learned} nodes")
    check(game.stats()["atk"] > atk_before, "skills did not raise attack")
    check(len(p["hotbar"]) >= 5, "active abilities did not reach the hotbar")

    # ------------------------------------------------------------- abilities
    p["mp"] = 999
    p["cooldowns"] = {}
    cast_ok = 0
    for slot in range(len(p["hotbar"])):
        p["cooldowns"] = {}
        p["mp"] = 999
        if game.cast(slot):
            cast_ok += 1
    print(f"abilities cast successfully: {cast_ok}/{len(p['hotbar'])}")
    check(cast_ok >= 5, f"only {cast_ok} abilities could be cast")

    # ----------------------------------------------------------------- combat
    target = next((m for m in game.mobs if m["alive"] and not m["passive"]), None)
    check(target is not None, "no hostile mob to test combat with")
    if target:
        p["x"], p["y"] = target["x"] - 0.6, target["y"]
        p["dir"] = "right"
        p["hp"] = game.stats()["hp_max"]
        target["hp"] = 1
        p["atk_t"] = 0.0
        gold_before = p["gold"]
        game.attack()
        check(not target["alive"], "attack did not kill a 1 HP monster")
        print(f"kill: {target['name']} | corpses {len(game.corpses)} | drops {len(game.drops)} "
              f"| gold {gold_before} -> {p['gold']}")
        check(len(game.drops) >= 1, "no loot dropped")
        check(p["gold"] > gold_before, "kill did not award gold")

    # regression: rendering a frame with a corpse on screen used to crash
    try:
        R.Renderer(game, 1920, 1080, 2).draw(pygame.Surface((1920, 1080)))
        print("render with a corpse on screen: ok,", len(game.corpses), "corpse(s)")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"render crashed with a corpse: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------- stress rendering
    try:
        kills = 0
        for m in [m for m in game.mobs if m["alive"] and not m["passive"]][:6]:
            p["x"], p["y"] = m["x"] - 0.5, m["y"]
            p["dir"] = "right"
            m["hp"] = 1
            p["atk_t"] = 0.0
            game.attack()
            kills += not m["alive"]
            game.update(1 / 60, {"up": False, "down": False, "left": False, "right": False})
            R.Renderer(game, 1920, 1080, 2).draw(pygame.Surface((1920, 1080)))
        for _ in range(60):
            game.update(1 / 60, {"up": False, "down": False, "left": False, "right": False})
            R.Renderer(game, 1920, 1080, 2).draw(pygame.Surface((1920, 1080)))
        print(f"stress render: {kills} kills | corpses {len(game.corpses)} "
              f"| drops {len(game.drops)} | particles {len(game.particles)}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"stress render crashed: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------ walk & talk
    p["x"], p["y"] = float(W.SPAWN_TILE[0]) + 0.5, float(W.SPAWN_TILE[1]) + 0.5
    start = (p["x"], p["y"])
    frames = set()
    for _ in range(90):
        game.update(1 / 60, {"right": True, "left": False, "up": False, "down": False})
        frames.add(p["frame"])
    walked = math.hypot(p["x"] - start[0], p["y"] - start[1])
    print(f"walked {walked:.2f} tiles | frames {sorted(frames)}")
    check(walked > 2, "player barely moved")
    check(frames == {0, 1}, "walk animation did not cycle")

    for n in game.npcs:
        p["x"], p["y"] = n["x"], n["y"] + 1.0
        game.dialog = None
        game.interact()
        got = (game.dialog or {}).get("name")
        check(got == n["name"], f"could not talk to {n['name']}")
    print("talked to all npcs:", not any("could not talk" in x for x in problems))

    # ------------------------------------------------------------- quests
    # every quest kind must be completable, and handing one in must pay out
    done_kinds = {}
    for kind in sorted({q["kind"] for q in QST.QUESTS}):
        quest = next(q for q in QST.QUESTS if q["kind"] == kind)
        giver = quest["giver"]
        # ignore chains: accept this one directly
        game.accept_quest(quest["id"])
        check(quest["id"] in game.quest_log, f"quest {quest['id']} not accepted")
        need = quest["count"]
        if kind in ("kill", "boss"):
            game.quest_stats["kill"][quest["target"]] = need
        elif kind in ("collect", "deliver"):
            game.add_item(quest["target"], need)
        elif kind in ("chop", "mine", "gather"):
            game.quest_stats[kind] = need
        elif kind == "sell":
            game.quest_stats["sold"] = need
        elif kind == "visit":
            game.visited.add(quest["target"])
        elif kind == "explore":
            game.visited.update(r["id"] for r in game.world.regions)
        elif kind == "learn":
            pass                        # the test already learned all 120 nodes
        check(game.quest_current(quest) >= need, f"quest {quest['id']} progress wrong")
        msg = game.turn_in_quest(quest["id"])
        check("сдано" in msg, f"quest {quest['id']} not handed in: {msg}")
        check(quest["id"] in game.quest_done, f"quest {quest['id']} not marked done")
        done_kinds[kind] = giver
    print(f"quests: turned in one of each kind ({len(done_kinds)}): "
          + ", ".join(sorted(done_kinds)))
    check(len(done_kinds) >= 10, "not all quest kinds are completable")
    # a villager offers his own quests, and only his own
    offers = game.available_quests("smith")
    check(bool(offers), "the blacksmith offers nothing")
    check(all(q["giver"] == "smith" for q in offers), "a villager offered a foreign quest")
    for q in offers[:2]:
        game.accept_quest(q["id"])
    check(len(game.quests) >= 2, "the journal did not fill up")
    print(f"journal: {len(game.quests)} active, {len(game.quest_done)} finished of "
          f"{len(QST.QUESTS)}")

    # ------------------------------------------------------------- harvest
    nodes = game.harvest_nodes()
    check(len(nodes) > 500, f"only {len(nodes)} harvestable nodes in the world")
    tree = next(n for n in nodes.values() if n["kind"] == "tree")
    p["x"], p["y"] = tree["x"] + 0.5, tree["y"] + 1.6
    check(game.nearest_node() is not None, "standing next to a tree, nothing is reachable")
    wood_before = game.count_item("wood")
    text = game.harvest(tree)
    check(game.count_item("wood") > wood_before, f"chopping gave no wood: {text}")
    check(not game.world.walkable(tree["x"], tree["y"]) is False
          or game.world.walkable(tree["x"], tree["y"]), "a chopped tree still blocks the tile")
    check((tree["x"], tree["y"]) in game.harvest_done, "the felled tree was not recorded")
    game.harvest_done[(tree["x"], tree["y"])] = game.time - 1.0
    game.update_harvest()
    check(nodes[(tree["x"], tree["y"])]["kind"] == "tree", "the tree did not grow back")
    for kind in ("rock_small", "bush", "berry_bush", "flower"):
        node = next((n for n in nodes.values() if n["kind"] == kind), None)
        check(node is not None, f"no {kind} in the world")
        if node:
            before = sum(game.count_item(i) for i in IT.ITEMS)
            game.harvest(node)
            check(sum(game.count_item(i) for i in IT.ITEMS) >= before,
                  f"harvesting a {kind} lost items")
    print(f"harvest: {len(nodes)} nodes, chop/mine/gather all give loot "
          f"(gathered {game.quest_stats['gather']}, chopped {game.quest_stats['chop']}, "
          f"mined {game.quest_stats['mine']})")
    check(game.quest_stats["chop"] >= 1 and game.quest_stats["mine"] >= 1
          and game.quest_stats["gather"] >= 1, "harvest counters did not move")

    # --------------------------------------------------------------- music
    check(len(MUS.TRACKS) >= 6, f"only {len(MUS.TRACKS)} music tracks")
    game.music_on = True
    game.update_music(0.1, False)
    check(game.music_track is not None, "no music track was chosen")
    game.battle_track = True
    check(game.current_track() == "battle", "combat did not switch to the battle theme")
    game.battle_track = False
    region_track = game.current_track()
    check(region_track in MUS.TRACKS, f"region track {region_track} is not a real track")
    # one reserved channel: pressing N used to start a second copy of the track on
    # top of the first, which is what "the music layers on itself" sounded like
    try:
        import pygame as _pg
        if _pg.mixer.get_init():
            game.music.prewarm()
            for name in ("village", "forest", "battle", "village", "ruins", "village"):
                game.music.play(name)
                game.music.update()
            busy = [i for i in range(_pg.mixer.get_num_channels())
                    if _pg.mixer.Channel(i).get_sound() is not None]
            check(len(busy) <= 1, f"{len(busy)} mixer channels play music at once")
            check(game.music.current in MUS.TRACKS, "music lost its current track")
    except Exception as exc:
        problems.append(f"music channel check crashed: {type(exc).__name__}: {exc}")
    game.music.play("village")
    game.music.stop()
    print(f"music: {len(MUS.TRACKS)} tracks, region -> {region_track}, "
          f"battle theme on combat, one channel only, toggling works")

    # -------------------------------------------------------------- pack art
    try:
        import packart
        pack = packart.build()
        if pack:
            check("hero_down_0" in pack and "hero_up_0" in pack,
                  "pack hero is missing its views")
            check("npc_peasant_0" in pack, "pack villagers are not keyed for the renderer")
            check(len(pack) > 200, f"only {len(pack)} pack sprites loaded")
            print(f"pack art: {len(pack)} sprites (Ninja Adventure, CC0)")
        else:
            print("pack art: assets not found, procedural sprites in use")
    except Exception as exc:
        problems.append(f"pack art crashed: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ oak
    try:
        oak = R.build_oak(420, 420)
        bark = left_arm = right_arm = 0
        for y in range(0, 420, 3):
            for x in range(0, 420, 3):
                r_, g_, b_, a_ = oak.get_at((x, y))
                if a_ < 40:
                    continue
                if r_ > g_ + 12 and r_ > b_ + 8:
                    bark += 1
                    if y < 190:
                        if x < 140:
                            left_arm += 1
                        elif x > 280:
                            right_arm += 1
        check(bark > 300, f"oak trunk and limbs are too thin ({bark} bark samples)")
        check(left_arm > 12 and right_arm > 12,
              f"oak canopy does not spread wide (left {left_arm}, right {right_arm})")
        print(f"oak: {bark} bark samples, canopy reaches both sides "
              f"({left_arm}/{right_arm} samples)")
    except Exception as exc:
        problems.append(f"oak render crashed: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------ settings
    cfg_path = G.CONFIG_PATH
    backup = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else None
    game.settings = dict(G.DEFAULT_SETTINGS)
    game.keys = dict(G.DEFAULT_KEYS)
    game.set_setting("sfx_volume", 0.5)
    check(abs(game.settings["sfx_volume"] - 0.5) < 1e-6, "sfx volume not applied")
    game.cycle_setting("difficulty", 1)
    check(game.settings["difficulty"] == 2, "difficulty did not step up")
    game.cycle_setting("difficulty", -5)
    check(game.settings["difficulty"] == 0, "difficulty did not clamp at the low end")
    base = game.incoming_damage(100)
    check(abs(base - 65) < 1e-6, f"easy difficulty damage wrong: {base}")
    game.set_setting("difficulty", 1)
    check(abs(game.incoming_damage(100) - 100) < 1e-6, "normal difficulty damage wrong")
    game.cycle_setting("muted")
    check(game.settings["muted"] is True, "mute toggle failed")
    game.cycle_setting("muted")
    # rebinding: the old key of the target action is swapped, never duplicated
    old_attack = game.keys["attack"]
    game.bind_key("attack", pygame.K_f)
    check(game.keys["attack"] == pygame.K_f, "attack was not rebound")
    check(len(set(game.keys.values())) == len(game.keys), "two actions share one key")
    game.keys = dict(G.DEFAULT_KEYS)
    check(game.keys["attack"] == old_attack, "default keys were not restored")
    # every tab must produce rows, and the screen must actually draw something
    tabs = [t for t, _lbl in G.Game.SETTINGS_TABS]
    check(len(tabs) >= 4, "fewer than four settings tabs")
    for tab in tabs:
        rows = game.settings_rows(tab, 2, False)
        check(len(rows) >= 3, f"settings tab {tab} has only {len(rows)} rows")
    surf_plain = pygame.Surface((1920, 1080))
    surf_plain.fill((0, 0, 0))
    ren = R.Renderer(game, 1920, 1080, 2)
    ren.draw_settings(surf_plain, "sound", 0, 2, False)
    lit = sum(1 for x in range(0, 1920, 23) for y in range(0, 1080, 23)
              if surf_plain.get_at((x, y))[:3] != (0, 0, 0))
    print(f"settings: {len(tabs)} tabs, {sum(len(game.settings_rows(t, 2, False)) for t in tabs)}"
          f" rows, screen draws ({lit} lit samples)")
    check(lit > 100, "the settings screen looks blank")
    if backup is None:
        cfg_path.unlink(missing_ok=True)
    else:
        cfg_path.write_text(backup, encoding="utf-8")
    game.settings = dict(G.DEFAULT_SETTINGS)
    game.keys = dict(G.DEFAULT_KEYS)

    # --------------------------------------------------------------- overlays
    overlays = ("inventory", "skilltree", "shop", "quests")
    for overlay in overlays:
        try:
            r = R.Renderer(game, 1920, 1080, 2)
            game.overlay = None
            base = pygame.Surface((1920, 1080))
            r.draw(base)
            game.overlay = overlay
            surf = pygame.Surface((1920, 1080))
            r.draw(surf)
            changed = sum(1 for x in range(200, 1720, 11) for y in range(120, 960, 9)
                          if base.get_at((x, y))[:3] != surf.get_at((x, y))[:3])
            print(f"overlay {overlay}: {changed} pixels differ from the plain frame")
            check(changed > 800, f"overlay {overlay} did not draw anything")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"overlay {overlay} crashed: {type(exc).__name__}: {exc}")
    game.overlay = None

    # the oak itself must be non-trivial
    oak = R.build_oak(1000, 700)
    lit = sum(1 for x in range(0, 1000, 7) for y in range(0, 700, 7)
              if oak.get_at((x, y))[3] > 40)
    print("oak tree drawn, covered samples:", lit)
    check(lit > 2000, "the skill oak looks empty")

    # the nodes must never touch on screen: the whole point of the zoomed view
    r = R.Renderer(game, 1920, 1080, 2)
    S = r.s
    area_w = r.width - S(18) * 2 - S(348)
    area_h = r.height - S(50) - S(34)
    for zoom in (G.TREE_ZOOM_MIN, G.TREE_ZOOM_DEFAULT, G.TREE_ZOOM_MAX):
        unit = min(area_w, area_h) * zoom
        gap_px = SK.min_node_gap() * unit
        radius = max(S(7), min(S(20), int(gap_px * 0.36)))
        print(f"oak at zoom {zoom:.1f}: closest nodes {gap_px:.0f}px apart, "
              f"node radius {radius}px")
        check(2 * radius + 2 <= gap_px,
              f"skill nodes overlap at zoom {zoom}: gap {gap_px:.0f}px, radius {radius}px")

    # ------------------------------------------------------------- rendering
    for (w, h, z) in G.RESOLUTIONS:
        try:
            surf = pygame.Surface((w, h))
            R.Renderer(game, w, h, z).draw(surf)
            colours = {surf.get_at((x, y))[:3]
                       for x in range(0, w, max(1, w // 40))
                       for y in range(0, h, max(1, h // 24))}
            check(len(colours) >= 5, f"render at {w}x{h} looks blank")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"render at {w}x{h} crashed: {type(exc).__name__}: {exc}")
    print("render ok at all", len(G.RESOLUTIONS), "resolutions")

    for state in ("title", "settings", "pause"):
        try:
            r = R.Renderer(game, 1920, 1080, 2)
            surf = pygame.Surface((1920, 1080))
            entries = [("Новая игра", True), ("Настройки", True), ("Выход", True)]
            r.draw_menu(surf, "Pixel patch", "тест", entries, 0)
            lit = sum(1 for x in range(0, 1920, 23) for y in range(0, 1080, 19)
                      if surf.get_at((x, y))[:3] != (0, 0, 0))
            check(lit > 500, f"{state} screen did not render")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{state} screen crashed: {type(exc).__name__}: {exc}")
    print("menus render ok")

    # ------------------------------------------------- HD-2D: свет и время суток
    r = R.Renderer(game, 1920, 1080, 2)
    surf = pygame.Surface((1920, 1080))
    vx, vy = G.VILLAGE_CENTER
    p["x"], p["y"] = vx + 1.0, vy + 2.0

    def avg_lum(surface: pygame.Surface) -> float:
        c = pygame.transform.average_color(surface)
        return c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114

    game.settings["atmosphere"] = True
    r.light.forced_phase = 0.30                       # полдень
    r.draw(surf)
    day_lum, day_lights = avg_lum(surf), r.light.lights_drawn
    r.light.forced_phase = 0.78                       # ночь
    r.draw(surf)
    night_lum, night_lights = avg_lum(surf), r.light.lights_drawn
    grads_before = len(r.light._grad)
    r.draw(surf)
    grads_after = len(r.light._grad)
    print(f"light: day {day_lum:.1f} ({day_lights} src) | night {night_lum:.1f} "
          f"({night_lights} src) | ambient day {lighting.ambient_at(0.30)} "
          f"night {lighting.ambient_at(0.78)}")
    check(day_lights >= 3, f"no light sources found in the village ({day_lights})")
    check(night_lum < day_lum * 0.80, f"night is not darker: {night_lum:.1f} vs {day_lum:.1f}")
    check(grads_after == grads_before, "light gradients are rebuilt every frame")

    game.settings["atmosphere"] = False
    r.light.forced_phase = 0.30
    r.draw(surf)
    off_lum = avg_lum(surf)
    print(f"light off at noon: {off_lum:.1f} (должно совпасть с днём)")
    check(abs(off_lum - day_lum) < 15,
          f"lighting changes the frame at noon: {off_lum:.1f} vs {day_lum:.1f}")
    for phase in (0.0, 0.25, 0.5, 0.75, 0.99):
        lum = sum(lighting.ambient_at(phase)) / 3.0
        check(30 < lum < 256, f"ambient is out of range at phase {phase}: {lum:.0f}")
    game.settings["atmosphere"] = True
    r.light.forced_phase = None

    # ------------------------------------------------------------ save / load
    tmp = Path(os.environ.get("TEMP", ".")) / "pixel_rpg_selftest.json"
    ok_save = game.save(tmp)
    snapshot = (p["gold"], len(p["inventory"]), len(p["learned"]),
                p["equip"]["weapon"], len(p["hotbar"]))
    p["gold"], p["inventory"], p["learned"], p["hotbar"] = 0, [], set(), []
    p["equip"]["weapon"] = None
    ok_load = game.load(tmp)
    after = (p["gold"], len(p["inventory"]), len(p["learned"]),
             p["equip"]["weapon"], len(p["hotbar"]))
    print("save/load:", ok_save, ok_load, "| gold", snapshot[0], "->", after[0],
          "| inventory", snapshot[1], "->", after[1], "| skills", snapshot[2], "->", after[2],
          "| weapon", after[3])
    check(ok_save and ok_load, "save/load failed")
    check(after[0] == snapshot[0], "save/load lost gold")
    check(after[1] == snapshot[1], "save/load lost inventory")
    check(after[2] == snapshot[2], "save/load lost learned skills")
    check(after[4] == snapshot[4], "save/load lost the hotbar")

    pygame.quit()
    if problems:
        print("SELFTEST FAILED:")
        for p_ in problems:
            print("  -", p_)
        return 1
    print("SELFTEST OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
