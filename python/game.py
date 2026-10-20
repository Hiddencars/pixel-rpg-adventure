#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pixel patch 2.8 — Python / pygame-ce.

Version 2.1 adds the living island: music, fifty quests, harvesting and a
rebuilt look.  Version 2.0 was the content pass:
  * map 250x128 tiles (5x the area) with biomes, nine regions and landmarks
  * 16 monster species + 3 farm animals, all with 64x64 shaded sprites
  * 50 items, per-species loot tables and a merchant who buys and sells
  * a skill tree of 121 nodes growing on one great oak (5 limbs)
  * 35 procedurally synthesised sound effects
  * 32x32 pre-rendered terrain art with shaded tiles and outlined objects

Run:        python game.py [--res 1920x1080] [--fullscreen]
Self-test:  python game.py --selftest
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
from pathlib import Path

import pygame

import art
import items as IT
import music as MUS
import quests as QST
import skills as SK
import sounds as SFX
import sprites as SP
import world as W
from world import MAP_H, MAP_W, SPAWN_TILE, VILLAGE_CENTER, World

TILE = art.TILE
SPRITE = SP.SPRITE
FPS = 60
BASE_UI_WIDTH = 1248
INV_SLOTS = 24
HOTBAR_KEYS = 9
MAP_CELL = 32            # размер клетки тумана войны на карте мира, в тайлах
# the oak screen: zoomed in enough that neighbouring nodes never touch
TREE_ZOOM_MIN = 1.0
TREE_ZOOM_DEFAULT = 2.0
TREE_ZOOM_MAX = 2.8
TREE_ZOOM_STEP = 0.15

# ------------------------------------------------------- the living island
# What can be harvested in the world: decor kind -> (quest stat, drops, verb).
# Drops are (item_id, count); the second entry is a bonus with its own chance.
HARVEST: dict[str, tuple] = {
    "bush":       ("gather", [("leaf", 2), ("herb", 1)], 0.45, "Собрано"),
    "berry_bush": ("gather", [("berry", 2), ("leaf", 1)], 0.35, "Собрано"),
    "flower":     ("gather", [("flower", 1), ("herb", 1)], 0.30, "Собрано"),
    "rock_small": ("mine",   [("stone", 2), ("ore_iron", 1)], 0.35, "Добыто"),
    "stump":      ("chop",   [("wood", 1)], 0.0, "Срублено"),
}
TREE_KINDS = ("oak", "pine", "birch", "tree")
HARVEST_RANGE = 1.9                 # tiles you can reach a bush or a tree from
REGROW = {"tree": 110.0, "bush": 55.0, "berry_bush": 70.0,
          "flower": 60.0, "rock_small": 95.0, "stump": 0.0}

MUSIC_VOLUME = 0.42                 # noticeable, but well under the effects
REGION_TRACK = {
    "village": "village", "meadow": "forest", "forest": "forest",
    "swamp": "swamp", "highlands": "highlands", "ruins": "ruins",
    "graveyard": "graveyard", "camp": "forest", "shore": "village",
}
EVENT_INTERVAL = (70.0, 150.0)      # секунд между случайными событиями
COMBAT_RANGE = 7.0                  # hostiles this close start the battle theme
COMBAT_HOLD = 6.0                   # seconds of calm before the region theme returns
SITE_NPC_INFO = {
    "scout": ("Разведчик", [
        "Дозор держу с тех пор, как руины начали шевелиться.",
        "Дальше на восток лучше не ходить в одиночку.",
        "Принеси вести с границ — заплачу."]),
    "hunter": ("Охотник", [
        "Зверь тут крупный, но шкура дорогая.",
        "Следы волков видел у самой воды.",
        "Приноси трофеи — не пропадать же добру."]),
    "miner": ("Рудокоп", [
        "Порода твёрдая, зато жила богатая.",
        "В забое кто-то воет по ночам. Не ходи туда один.",
        "Нужна руда — приноси, я знаю цену."]),
    "fisher": ("Рыбак", [
        "Рыба здесь клюёт только на рассвете.",
        "В омуте что-то крупное. Сети рвёт.",
        "Принеси мне трав на приманку — отдам улов."]),
    "pilgrim": ("Паломник", [
        "Свет в этой чаше не гаснет уже сотню лет.",
        "Кто зажигает огонь — тот и хранит дорогу.",
        "Помоги святилищу, и оно поможет тебе."]),
    "hermit": ("Отшельник", [
        "Я живу здесь, потому что здесь тихо.",
        "Мёртвые не любят, когда их тревожат.",
        "Принеси кости — я скажу, чьи они."]),
    "nomad": ("Кочевник", [
        "Мы не задерживаемся на одном месте.",
        "Торгую тем, что нашёл по дороге.",
        "Хочешь — идём вместе до следующего табора."]),
}

GIVER_NAMES = {"peasant": "Крестьянину", "farmer": "Фермеру", "smith": "Кузнецу",
               "merchant": "Торговцу", "elder": "Старейшине", "guard": "Стражнику",
               "healer": "Знахарке", "scout": "Разведчику", "hunter": "Охотнику",
               "miner": "Рудокопу", "fisher": "Рыбаку", "pilgrim": "Паломнику",
               "hermit": "Отшельнику", "nomad": "Кочевнику"}

RESOLUTIONS = [(960, 540, 1), (1280, 720, 2), (1366, 768, 2),
               (1600, 900, 2), (1920, 1080, 2)]
DEFAULT_RES_INDEX = len(RESOLUTIONS) - 1

# --------------------------------------------------------------- settings
# Everything a player can tune. Stored in the config file next to the resolution.
DEFAULT_SETTINGS: dict = {
    "sfx_volume": 0.8,          # 0..1
    "music_volume": 0.42,
    "muted": False,
    "difficulty": 1,            # 0 easy, 1 normal, 2 harsh
    "damage_numbers": True,
    "screen_shake": True,
    "minimap": True,
    "hints": True,
    "autosave": True,
    "atmosphere": True,          # свет и время суток
}
DIFFICULTY_NAMES = ("Лёгкая", "Обычная", "Суровая")
DIFFICULTY_DAMAGE = (0.65, 1.0, 1.5)     # incoming damage multiplier

# Rebindeable actions. Movement also always answers to the arrow keys.
KEY_ACTIONS = [
    ("up", "Вверх", "K_w"),
    ("down", "Вниз", "K_s"),
    ("left", "Влево", "K_a"),
    ("right", "Вправо", "K_d"),
    ("attack", "Атака", "K_SPACE"),
    ("interact", "Действие / говорить", "K_e"),
    ("inventory", "Сумка", "K_i"),
    ("skills", "Дуб навыков", "K_k"),
    ("quests", "Задания", "K_q"),
    ("potion", "Выпить зелье", "K_h"),
    ("music", "Музыка вкл/выкл", "K_F7"),
    ("next_track", "Следующая мелодия", "K_n"),
    ("map", "Карта мира", "K_m"),
]
DEFAULT_KEYS = {name: getattr(pygame, code) for name, _label, code in KEY_ACTIONS}

KEY_NAMES = {pygame.K_SPACE: "ПРОБЕЛ", pygame.K_RETURN: "ENTER", pygame.K_TAB: "TAB",
             pygame.K_ESCAPE: "ESC", pygame.K_LSHIFT: "SHIFT", pygame.K_LCTRL: "CTRL",
             pygame.K_UP: "↑", pygame.K_DOWN: "↓", pygame.K_LEFT: "←",
             pygame.K_RIGHT: "→", pygame.K_BACKSPACE: "BACKSPACE"}


def key_label(code: int) -> str:
    if code in KEY_NAMES:
        return KEY_NAMES[code]
    name = pygame.key.name(code)
    return name.upper() if name else "?"

SAVE_PATH = Path.home() / ".pixel_rpg_adventure_save.json"
CONFIG_PATH = Path.home() / ".pixel_rpg_adventure_config.json"

# ------------------------------------------------------------------ monsters
# hp, atk, speed (tiles/s), xp, aggro range (tiles), attack range, gold
MOBS: dict[str, dict] = {
    "goblin":   {"name": "Гоблин", "hp": 18, "atk": 4, "speed": 3.0, "xp": 9, "aggro": 8.0, "reach": 1.2, "scale": 0.95},
    "brute":    {"name": "Гоблин-здоровяк", "hp": 38, "atk": 8, "speed": 2.4, "xp": 20, "aggro": 8.5, "reach": 1.3, "scale": 1.15},
    "orc":      {"name": "Орк", "hp": 55, "atk": 11, "speed": 2.6, "xp": 30, "aggro": 9.0, "reach": 1.35, "scale": 1.2},
    "bandit":   {"name": "Разбойник", "hp": 34, "atk": 9, "speed": 3.3, "xp": 22, "aggro": 10.0, "reach": 1.3, "scale": 1.0},
    "skeleton": {"name": "Скелет", "hp": 30, "atk": 8, "speed": 2.7, "xp": 20, "aggro": 8.0, "reach": 1.25, "scale": 1.0},
    "wraith":   {"name": "Призрак", "hp": 42, "atk": 13, "speed": 3.1, "xp": 34, "aggro": 11.0, "reach": 1.4, "scale": 1.05},
    "troll":    {"name": "Тролль", "hp": 95, "atk": 17, "speed": 2.2, "xp": 55, "aggro": 8.0, "reach": 1.5, "scale": 1.42},
    "imp":      {"name": "Бес", "hp": 20, "atk": 7, "speed": 3.6, "xp": 16, "aggro": 9.0, "reach": 1.15, "scale": 0.72},
    "golem":    {"name": "Голем", "hp": 120, "atk": 15, "speed": 1.9, "xp": 62, "aggro": 7.5, "reach": 1.5, "scale": 1.2},
    "spider":   {"name": "Паук", "hp": 16, "atk": 5, "speed": 3.4, "xp": 11, "aggro": 8.0, "reach": 1.2, "scale": 0.95},
    "slime":    {"name": "Слизень", "hp": 14, "atk": 3, "speed": 1.7, "xp": 7, "aggro": 6.0, "reach": 1.15, "scale": 0.9},
    "bat":      {"name": "Летучая мышь", "hp": 12, "atk": 4, "speed": 4.0, "xp": 9, "aggro": 10.0, "reach": 1.1, "scale": 0.8},
    "snake":    {"name": "Змея", "hp": 15, "atk": 6, "speed": 2.9, "xp": 10, "aggro": 7.0, "reach": 1.2, "scale": 0.9},
    "wolf":     {"name": "Волк", "hp": 28, "atk": 8, "speed": 3.9, "xp": 18, "aggro": 11.0, "reach": 1.25, "scale": 1.0},
    "boar":     {"name": "Кабан", "hp": 32, "atk": 9, "speed": 3.2, "xp": 17, "aggro": 8.0, "reach": 1.25, "scale": 1.02},
    "bear":     {"name": "Медведь", "hp": 70, "atk": 14, "speed": 3.0, "xp": 40, "aggro": 9.0, "reach": 1.4, "scale": 1.22},
    "cow":      {"name": "Корова", "hp": 22, "atk": 0, "speed": 1.4, "xp": 5, "aggro": 0.0, "reach": 1.2, "scale": 1.05, "passive": True},
    "sheep":    {"name": "Овца", "hp": 18, "atk": 0, "speed": 1.6, "xp": 4, "aggro": 0.0, "reach": 1.2, "scale": 0.92, "passive": True},
    "chicken":  {"name": "Курица", "hp": 8, "atk": 0, "speed": 1.8, "xp": 2, "aggro": 0.0, "reach": 1.1, "scale": 0.8, "passive": True},
}

# ------------------------------------------------------------------ abilities
# kind: aoe | single | heal | buff | summon | move | stealth
ABILITIES: dict[str, dict] = {
    "whirlwind":       {"name": "Круговой удар", "kind": "aoe", "mana": 6, "cd": 5.0, "radius": 3.0, "mult": 1.0, "color": (255, 214, 140)},
    "power_strike":    {"name": "Мощный удар", "kind": "single", "mana": 8, "cd": 6.0, "mult": 3.0, "color": (255, 180, 120)},
    "blade_storm":     {"name": "Вихрь стали", "kind": "aoe", "mana": 14, "cd": 9.0, "radius": 4.0, "mult": 1.6, "color": (255, 230, 180)},
    "execute":         {"name": "Казнь", "kind": "single", "mana": 12, "cd": 8.0, "mult": 2.0, "color": (230, 90, 90), "execute": True},
    "world_cleave":    {"name": "Рассечение мира", "kind": "aoe", "mana": 30, "cd": 20.0, "radius": 9.0, "mult": 3.0, "color": (255, 240, 200)},
    "shield_block":    {"name": "Блок", "kind": "buff", "mana": 5, "cd": 12.0, "stat": "def_pct", "value": 1.0, "time": 4.0, "color": (150, 190, 240)},
    "shield_bash":     {"name": "Удар щитом", "kind": "single", "mana": 7, "cd": 7.0, "mult": 1.4, "stun": 1.6, "color": (170, 200, 250)},
    "taunt":           {"name": "Провокация", "kind": "aoe", "mana": 6, "cd": 15.0, "radius": 7.0, "mult": 0.0, "color": (240, 170, 120)},
    "stoneskin":       {"name": "Каменная кожа", "kind": "buff", "mana": 12, "cd": 22.0, "stat": "def_pct", "value": 1.0, "time": 6.0, "color": (170, 170, 160)},
    "earthquake":      {"name": "Землетрясение", "kind": "aoe", "mana": 18, "cd": 12.0, "radius": 5.0, "mult": 1.5, "stun": 2.0, "color": (200, 170, 120)},
    "fortress":        {"name": "Непоколебимый дух", "kind": "buff", "mana": 25, "cd": 40.0, "stat": "def_pct", "value": 4.0, "time": 6.0, "color": (200, 220, 255)},
    "fireball":        {"name": "Огненный шар", "kind": "single", "mana": 7, "cd": 3.5, "mult": 2.2, "element": "fire", "color": (250, 150, 70)},
    "frost_bolt":      {"name": "Ледяная стрела", "kind": "single", "mana": 6, "cd": 3.0, "mult": 1.8, "slow": 3.0, "element": "frost", "color": (140, 200, 250)},
    "frost_nova":      {"name": "Ледяная новая", "kind": "aoe", "mana": 14, "cd": 9.0, "radius": 4.0, "mult": 1.5, "slow": 3.0, "element": "frost", "color": (150, 210, 255)},
    "lightning":       {"name": "Разряд", "kind": "aoe", "mana": 16, "cd": 8.0, "radius": 3.5, "mult": 2.0, "element": "fire", "color": (200, 220, 255)},
    "fire_wall":       {"name": "Огненная стена", "kind": "aoe", "mana": 20, "cd": 14.0, "radius": 3.0, "mult": 1.2, "element": "fire", "color": (250, 120, 60)},
    "blink":           {"name": "Телепорт", "kind": "move", "mana": 8, "cd": 6.0, "distance": 6.0, "color": (190, 160, 250)},
    "meteor":          {"name": "Метеор", "kind": "aoe", "mana": 28, "cd": 18.0, "radius": 6.0, "mult": 2.8, "element": "fire", "color": (255, 130, 60)},
    "armageddon":      {"name": "Армагеддон", "kind": "aoe", "mana": 45, "cd": 35.0, "radius": 12.0, "mult": 4.0, "element": "fire", "color": (255, 90, 40)},
    "poison_cloud":    {"name": "Облако яда", "kind": "aoe", "mana": 9, "cd": 7.0, "radius": 3.5, "mult": 0.8, "element": "poison", "color": (150, 210, 110)},
    "dash":            {"name": "Рывок", "kind": "move", "mana": 4, "cd": 4.0, "distance": 4.0, "color": (200, 240, 180)},
    "arrow_volley":    {"name": "Залп стрел", "kind": "aoe", "mana": 11, "cd": 6.0, "radius": 5.0, "mult": 1.3, "color": (220, 200, 160)},
    "summon_wolf":     {"name": "Волк-спутник", "kind": "summon", "mana": 15, "cd": 25.0, "count": 1, "time": 30.0, "color": (170, 170, 190)},
    "summon_pack":     {"name": "Стая", "kind": "summon", "mana": 26, "cd": 35.0, "count": 2, "time": 35.0, "color": (170, 170, 190)},
    "invisibility":    {"name": "Невидимость", "kind": "stealth", "mana": 12, "cd": 20.0, "time": 6.0, "color": (200, 200, 230)},
    "nature_wrath":    {"name": "Ярость природы", "kind": "aoe", "mana": 17, "cd": 11.0, "radius": 4.5, "mult": 1.7, "element": "poison", "color": (140, 210, 120)},
    "heal":            {"name": "Свет", "kind": "heal", "mana": 8, "cd": 6.0, "amount": 25, "color": (250, 230, 150)},
    "holy_light":      {"name": "Благословение", "kind": "heal", "mana": 14, "cd": 12.0, "amount": 45, "radius": 4.0, "color": (255, 240, 180)},
    "smite":           {"name": "Освящённый удар", "kind": "single", "mana": 9, "cd": 5.0, "mult": 1.9, "heal": 8, "color": (255, 240, 190)},
    "life_drain":      {"name": "Похищение жизни", "kind": "single", "mana": 12, "cd": 8.0, "mult": 1.6, "drain": 0.6, "color": (180, 120, 200)},
    "totem":           {"name": "Тотем жизни", "kind": "buff", "mana": 16, "cd": 30.0, "stat": "regen", "value": 8.0, "time": 15.0, "color": (170, 210, 150)},
    "healing_circle":  {"name": "Круг исцеления", "kind": "heal", "mana": 22, "cd": 20.0, "amount": 90, "radius": 3.0, "color": (200, 250, 190)},
    "revive":          {"name": "Воскрешение", "kind": "heal", "mana": 30, "cd": 60.0, "amount": 999, "color": (255, 250, 200)},
    "miracle":         {"name": "Чудо", "kind": "heal", "mana": 40, "cd": 70.0, "amount": 999, "mana_restore": 999, "color": (255, 255, 220)},
}

STAT_KEYS = ("atk_flat", "atk_pct", "def_flat", "def_pct", "hp_max", "mp_max",
             "crit_chance", "crit_mult", "speed_pct", "dodge", "atk_speed",
             "lifesteal", "thorns", "regen", "mp_regen", "potion_power",
             "gold_find", "loot_chance", "xp_gain", "magic_power", "aoe_radius",
             "armor_pen", "knockback", "heal_power", "fire_damage",
             "frost_damage", "poison_damage")


class Game:
    def __init__(self, seed: int | None = None, sound: bool = True, progress=None):
        self.rng = random.Random(seed)
        self.seed = seed
        self.world = World(self.rng.randrange(1 << 30) if seed is None else seed,
                           progress=progress)
        self.frame = 0
        self.time = 0.0
        self.sfx = SFX.build_bank(sound)

        self.music_on = sound
        self.music = MUS.build_player(sound)
        cfg = load_config()
        self.settings = dict(DEFAULT_SETTINGS)
        for k, v in (cfg.get("settings") or {}).items():
            if k in self.settings:
                self.settings[k] = v
        self.keys = dict(DEFAULT_KEYS)
        for action, code in (cfg.get("keys") or {}).items():
            if action in self.keys and isinstance(code, int):
                self.keys[action] = code
        self.music.set_volume(self.settings["music_volume"])
        self.music.prewarm()          # synthesise every track in the background
        self.music_track: str | None = None
        self.apply_settings()

        self.reset_progress()

    def reset_progress(self) -> None:
        """Сбросить прогресс, не трогая сгенерированный мир.

        Мир детерминирован сидом и стоит ~4 секунды генерации, поэтому «Новая
        игра» из меню должна переиспользовать его, а не строить карту заново.
        Вызывается и из __init__ — тогда она же и создаёт стартовое состояние.
        """
        self.frame = 0
        self.time = 0.0
        self.player = {
            "x": float(SPAWN_TILE[0]) + 0.5, "y": float(SPAWN_TILE[1]) + 0.5,
            "dir": "down", "moving": False, "anim_t": 0.0, "frame": 0,
            "hp": 60.0, "mp": 30.0, "level": 1, "xp": 0, "xp_next": 40, "gold": 25,
            "atk_t": 0.0, "atk_anim": 0.0, "hurt_t": 0.0, "invuln": 0.0,
            "inventory": [], "equip": {"weapon": None, "armor": None, "ring": None,
                                       "amulet": None},
            "learned": set(), "hotbar": [], "cooldowns": {}, "buffs": {},
            "stealth": 0.0, "revived": False,
        }
        self.skill_points = 3
        self.mobs = []
        self.allies = []
        self.npcs = []
        self.drops = []
        self.particles = []
        self.floaters = []
        self.corpses = []
        self.toasts = []
        self.dialog = None
        self.overlay = None        # inventory | skilltree | shop | quests | map
        self.inv_cursor = 0
        self.shop_tab = "sell"                 # sell | buy
        self.shop_cursor = 0
        self.tree_cursor = "root"
        self.tree_zoom = TREE_ZOOM_DEFAULT
        self.tree_cam = [0.5, 0.5]
        self.tree_offset = (0.0, 0.0)
        self.quests = []          # accepted quests, with live progress
        self.quest_log = []        # accepted ids, in order
        self.quest_done = set()
        self.quest_ready = set()
        self.quest_stats = {"kill": {}, "chop": 0, "mine": 0, "gather": 0, "sold": 0}
        self.harvest_done = {}   # node -> ready time
        self.nodes = None
        self.merchant_stock = dict(IT.SHOP_STOCK)
        self.reach = set()
        self.kills = {}
        self.deaths = 0
        self.visited = set()
        self.explored = set()
        self.combat_t = 0.0
        self.battle_track = False
        self.shake = 0.0
        self.music_track = None
        self.event_timer = 55.0
        self.active_events = []

        self.spawn_npcs()
        self.spawn_mobs()
        self.init_quests()
        self.learn("root")                     # the trunk is always unlocked
        for item_id, count in (("potion", 3), ("herb", 3), ("mana_potion", 1)):
            self.add_item(item_id, count)
        self.mark_explored()
        cells = f"{W.MAP_W * W.MAP_H:,}".replace(",", " ")
        self.toast(f"Новая игра: мир {W.MAP_W}×{W.MAP_H} — {cells} клеток", "#ffe066")

    # ------------------------------------------------------------- sound
    def sound(self, name: str, volume: float = 1.0) -> None:
        if self.settings.get("muted"):
            return
        self.sfx.play(name, volume * float(self.settings.get("sfx_volume", 0.8)))

    # ---------------------------------------------------------- settings
    def apply_settings(self) -> None:
        """Push the current settings into the sound and music systems."""
        vol = 0.0 if self.settings.get("muted") else float(self.settings["music_volume"])
        self.music.set_volume(vol)
        self.music_on = (not self.settings.get("muted")) and self.music_on
        if self.settings.get("muted"):
            self.music.stop(200)
            self.music_track = None

    def set_setting(self, key: str, value) -> None:
        if key not in self.settings:
            return
        self.settings[key] = value
        self.apply_settings()
        self.save_settings()

    def cycle_setting(self, key: str, step: int = 1) -> None:
        """Step a numeric or boolean setting; used by the settings screen."""
        cur = self.settings.get(key)
        if isinstance(cur, bool):
            self.set_setting(key, not cur)
        elif key == "difficulty":
            self.set_setting(key, max(0, min(len(DIFFICULTY_NAMES) - 1, int(cur) + step)))
        else:
            self.set_setting(key, max(0.0, min(1.0, round(float(cur) + step * 0.1, 2))))

    def bind_key(self, action: str, code: int) -> str:
        if action not in self.keys:
            return ""
        for other, other_code in self.keys.items():
            if other != action and other_code == code:
                self.keys[other] = self.keys[action]     # swap, never duplicate
                break
        self.keys[action] = code
        self.save_settings()
        return f"{action}: {key_label(code)}"

    def save_settings(self) -> None:
        cfg = load_config()
        cfg["settings"] = self.settings
        cfg["keys"] = self.keys
        save_config(cfg)

    def incoming_damage(self, dmg: float) -> float:
        return dmg * DIFFICULTY_DAMAGE[int(self.settings.get("difficulty", 1))]

    # ------------------------------------------------- the settings screen
    SETTINGS_TABS = (("screen", "Экран"), ("sound", "Звук"),
                     ("controls", "Управление"), ("game", "Игра"))

    def settings_rows(self, tab: str, res_index: int = DEFAULT_RES_INDEX,
                      fullscreen: bool = False) -> list[tuple[str, str, str]]:
        """Rows for one settings tab: (action key, label, value text)."""
        st = self.settings
        rows: list[tuple[str, str, str]] = []
        if tab == "screen":
            for i, (w, h, z) in enumerate(RESOLUTIONS):
                mark = "  •  выбрано" if i == res_index else ""
                hd = "  (Full HD)" if (w, h) == (1920, 1080) else ""
                rows.append((f"res:{i}", f"{w} × {h}{hd}", f"масштаб ×{z}{mark}"))
            rows.append(("fullscreen", "Полный экран",
                         "включён" if fullscreen else "выключен"))
        elif tab == "sound":
            rows.append(("sfx_volume", "Громкость эффектов",
                         f"{int(round(st['sfx_volume'] * 100))}%"))
            rows.append(("music_volume", "Громкость музыки",
                         f"{int(round(st['music_volume'] * 100))}%"))
            rows.append(("muted", "Выключить весь звук",
                         "да" if st["muted"] else "нет"))
        elif tab == "controls":
            for action, label, _code in KEY_ACTIONS:
                rows.append((f"key:{action}", label, key_label(self.keys[action])))
            rows.append(("reset_keys", "Вернуть управление по умолчанию", ""))
        else:
            rows.append(("difficulty", "Сложность",
                         DIFFICULTY_NAMES[int(st["difficulty"])]))
            rows.append(("damage_numbers", "Показывать цифры урона",
                         "да" if st["damage_numbers"] else "нет"))
            rows.append(("screen_shake", "Тряска экрана при ударах",
                         "да" if st["screen_shake"] else "нет"))
            rows.append(("minimap", "Миникарта", "да" if st["minimap"] else "нет"))
            rows.append(("hints", "Подсказки на экране", "да" if st["hints"] else "нет"))
            rows.append(("autosave", "Автосохранение", "да" if st["autosave"] else "нет"))
            rows.append(("atmosphere", "Свет и время суток",
                         "да" if st["atmosphere"] else "нет"))
        return rows

    def change_setting(self, action: str, step: int = 1) -> str:
        """Left/right on a settings row. Returns a short note for the screen."""
        if action in self.settings:
            self.cycle_setting(action, step)
            label = next((lbl for key, lbl, _c in KEY_ACTIONS if key == action), action)
            if action == "difficulty":
                return f"Сложность: {DIFFICULTY_NAMES[int(self.settings['difficulty'])]}"
            if isinstance(self.settings[action], bool):
                return f"{label}: {'да' if self.settings[action] else 'нет'}"
            return f"{label}: {int(round(float(self.settings[action]) * 100))}%"
        if action == "reset_keys":
            self.keys = dict(DEFAULT_KEYS)
            self.save_settings()
            return "Управление сброшено"
        return ""

    # ------------------------------------------------------- stats & skills
    def stats(self) -> dict:
        p = self.player
        st = {k: 0.0 for k in STAT_KEYS}
        st["atk"] = 5.0 + p["level"] * 1.4
        st["def"] = 0.0
        for slot, item_id in p["equip"].items():
            if not item_id:
                continue
            data = IT.ITEMS.get(item_id)
            if not data:
                continue
            st["atk"] += data.get("atk", 0)
            st["def"] += data.get("def", 0)
            st["hp_max"] += data.get("hp", 0)
            st["mp_max"] += data.get("mp", 0)
            st["crit_chance"] += data.get("crit", 0)
            st["magic_power"] += data.get("magic", 0)
            st["fire_damage"] += data.get("fire", 0)
        totals = SK.effect_totals(p["learned"])
        for k, v in totals.items():
            if k in st:
                st[k] += v
        for k, buff in p["buffs"].items():
            if k in st:
                st[k] += buff["value"]
        st["hp_max"] = 60 + p["level"] * 8 + st["hp_max"]
        st["mp_max"] = 30 + p["level"] * 5 + st["mp_max"]
        st["atk"] *= (1.0 + st["atk_pct"] / 100.0)
        st["def"] = max(0.0, (st["def"] + st["def_flat"]) * (1.0 + st["def_pct"] / 100.0))
        st["speed"] = 4.6 * (1.0 + st["speed_pct"] / 100.0)
        st["crit_chance"] = min(75.0, st["crit_chance"])
        st["crit_mult"] = 1.6 + st["crit_mult"] / 100.0
        st["atk_cd"] = 0.34 / (1.0 + st["atk_speed"] / 100.0)
        st["heal_power"] = 1.0 + st["heal_power"] / 100.0
        st["potion_power"] = 1.0 + st["potion_power"] / 100.0
        st["gold_find"] = 1.0 + st["gold_find"] / 100.0
        st["loot_chance"] = 1.0 + st["loot_chance"] / 100.0
        st["xp_gain"] = 1.0 + st["xp_gain"] / 100.0
        st["aoe"] = 1.0 + st["aoe_radius"] / 100.0
        return st

    def hp_max(self) -> float:
        return self.stats()["hp_max"]

    def mp_max(self) -> float:
        return self.stats()["mp_max"]

    def can_learn(self, sid: str) -> bool:
        skill = SK.by_id(sid)
        if not skill:
            return False
        return SK.can_learn(self.player["learned"], skill, self.skill_points)

    def learn(self, sid: str) -> bool:
        skill = SK.by_id(sid)
        if not skill:
            return False
        if sid in self.player["learned"]:
            return False
        if sid != "root" and not self.can_learn(sid):
            self.sound("error")
            return False
        self.skill_points -= skill["cost"]
        self.player["learned"].add(sid)
        if skill["kind"] == "active":
            key = skill["effect"]["key"]
            if key not in self.player["hotbar"] and len(self.player["hotbar"]) < HOTBAR_KEYS:
                self.player["hotbar"].append(key)
        self.sound("skill_learn")
        self.toast("Изучено: " + skill["name"], "#9ad7ff")
        if skill["effect"]["key"] == "hp_max":
            self.player["hp"] = min(self.hp_max(), self.player["hp"] + skill["effect"]["value"])
        self.refresh_quests()
        return True

    def tree_nodes(self) -> list[dict]:
        return SK.SKILLS

    def tree_zoom_by(self, step: float) -> None:
        """Zoom the oak view (the camera follows the cursor, so this is all a player needs)."""
        self.tree_zoom = max(TREE_ZOOM_MIN, min(TREE_ZOOM_MAX, self.tree_zoom + step))

    def tree_show_all(self) -> None:
        self.tree_zoom = TREE_ZOOM_MIN
        node = SK.by_id(self.tree_cursor) or SK.ROOT
        self.tree_cam = [0.5, 0.5]
        self.sound("menu_select", 0.4)

    def tree_move(self, dx: int, dy: int) -> None:
        """Move the skill-tree cursor to the nearest node in that direction."""
        cur = SK.by_id(self.tree_cursor) or SK.ROOT
        cx, cy = SK.position_of(cur)
        best, best_score = None, 1e9
        for node in SK.SKILLS:
            if node["id"] == cur["id"]:
                continue
            nx, ny = SK.position_of(node)
            vx, vy = nx - cx, ny - cy
            dot = vx * dx + vy * dy
            if dot <= 0.012:
                continue
            perp = abs(vx * dy - vy * dx)
            score = perp * 2.4 + math.hypot(vx, vy) * 0.35
            if score < best_score:
                best, best_score = node, score
        if best:
            self.tree_cursor = best["id"]
            self.sound("menu_move", 0.5)

    def cast(self, slot: int) -> bool:
        """Cast hotbar ability `slot` (0-based)."""
        p = self.player
        hotbar = p["hotbar"]
        if not (0 <= slot < len(hotbar)):
            return False
        key = hotbar[slot]
        ab = ABILITIES.get(key)
        if not ab:
            return False
        if p["cooldowns"].get(key, 0.0) > 0:
            self.sound("error", 0.5)
            self.toast(f"{ab['name']}: перезарядка {p['cooldowns'][key]:.1f} с", "#c8c8d0")
            return False
        if p["mp"] < ab["mana"]:
            self.sound("error", 0.5)
            self.toast("Недостаточно маны", "#9ab0ff")
            return False
        st = self.stats()
        p["mp"] -= ab["mana"]
        p["cooldowns"][key] = ab["cd"]
        kind = ab["kind"]
        fx, fy = self.face_dir()
        px, py = p["x"], p["y"]

        if kind in ("aoe", "single"):
            targets = []
            for m in self.mobs:
                if not m["alive"]:
                    continue
                d = math.hypot(m["x"] - px, m["y"] - py)
                if kind == "single":
                    if d <= 9.0:
                        targets.append((d, m))
                elif d <= ab.get("radius", 3.0) * st["aoe"]:
                    targets.append((d, m))
            if kind == "single":
                targets.sort(key=lambda t: t[0])
                targets = targets[:1]
            for (_d, m) in targets:
                dmg = st["atk"] * ab.get("mult", 1.0)
                if ab.get("execute") and m["hp"] < m["hp_max"] * 0.35:
                    dmg *= 2.0
                dmg += st["fire_damage"] if ab.get("element") == "fire" else 0
                dmg += st["frost_damage"] if ab.get("element") == "frost" else 0
                dmg += st["poison_damage"] if ab.get("element") == "poison" else 0
                if ab.get("element"):
                    dmg *= 1.0 + st["magic_power"] / 100.0
                self.hurt_mob(m, max(1, int(dmg)), ability=key)
                if ab.get("slow"):
                    m["slow"] = ab["slow"]
                if ab.get("stun"):
                    m["stun"] = ab["stun"]
                if ab.get("heal"):
                    p["hp"] = min(self.hp_max(), p["hp"] + ab["heal"] * st["heal_power"])
                if ab.get("drain"):
                    p["hp"] = min(self.hp_max(), p["hp"] + dmg * ab["drain"] * 0.5)
            if not targets and kind == "single":
                self.toast("Нет цели в поле зрения", "#c8c8d0")
            self.sound("spell" if ab.get("element") else "swing")
        elif kind == "heal":
            heal = ab.get("amount", 20) * st["heal_power"]
            p["hp"] = min(self.hp_max(), p["hp"] + heal)
            if ab.get("mana_restore"):
                p["mp"] = min(self.mp_max(), p["mp"] + ab["mana_restore"])
            self.add_floater(px, py - 1.0, f"+{int(heal)}", "#9cff9c")
            self.sound("heal")
        elif kind == "buff":
            p["buffs"][ab["stat"]] = {"value": ab["value"], "t": ab.get("time", 5.0)}
            self.toast(f"{ab['name']} активен", "#ffe066")
            self.sound("heal", 0.7)
        elif kind == "summon":
            for _ in range(ab.get("count", 1)):
                ang = self.rng.random() * math.tau
                self.allies.append({
                    "x": px + math.cos(ang) * 1.6, "y": py + math.sin(ang) * 1.6,
                    "kind": "wolf", "hp": 30.0, "hp_max": 30.0, "atk": st["atk"] * 0.5,
                    "speed": 3.6, "t": ab.get("time", 30.0), "anim_t": 0.0, "frame": 0,
                    "dir": "down", "atk_t": 0.0, "moving": False,
                })
            self.toast("Призваны союзники", "#c8d0ff")
            self.sound("spell")
        elif kind == "move":
            dist = ab.get("distance", 4.0)
            steps = int(dist * 4)
            for _ in range(steps):
                nx, ny = p["x"] + fx * dist / steps, p["y"] + fy * dist / steps
                if self.world.blocked_rect(nx, ny, 0.3):
                    break
                p["x"], p["y"] = nx, ny
            self.sound("dodge" if "dodge" in self.sfx.names() else "menu_select", 0.6)
        elif kind == "stealth":
            p["stealth"] = ab.get("time", 6.0)
            self.toast("Ты растворился в тенях", "#c8d0ff")
            self.sound("ghost" if "ghost" in self.sfx.names() else "spell", 0.7)
        return True

    # ------------------------------------------------------------ inventory
    def add_item(self, item_id: str, count: int = 1) -> bool:
        if item_id not in IT.ITEMS or count <= 0:
            return False
        stack = IT.ITEMS[item_id].get("stack", 1)
        inv = self.player["inventory"]
        if stack > 1:
            for slot in inv:
                if slot["id"] == item_id and slot["count"] < stack:
                    put = min(stack - slot["count"], count)
                    slot["count"] += put
                    count -= put
                    if count <= 0:
                        return True
        while count > 0 and len(inv) < INV_SLOTS:
            put = min(count, stack)
            inv.append({"id": item_id, "count": put})
            count -= put
        return count <= 0

    def remove_item(self, item_id: str, count: int = 1) -> bool:
        inv = self.player["inventory"]
        have = sum(s["count"] for s in inv if s["id"] == item_id)
        if have < count:
            return False
        for slot in list(inv):
            if slot["id"] != item_id:
                continue
            take = min(slot["count"], count)
            slot["count"] -= take
            count -= take
            if slot["count"] <= 0:
                inv.remove(slot)
            if count <= 0:
                break
        return True

    def count_item(self, item_id: str) -> int:
        return sum(s["count"] for s in self.player["inventory"] if s["id"] == item_id)

    def equip_slot(self, slot_key: str) -> str:
        return {"weapon": "Оружие", "armor": "Броня", "ring": "Кольцо",
                "amulet": "Амулет"}.get(slot_key, slot_key)

    def use_slot(self, index: int) -> str:
        inv = self.player["inventory"]
        if not (0 <= index < len(inv)):
            return ""
        slot = inv[index]
        item_id = slot["id"]
        data = IT.ITEMS.get(item_id)
        if not data:
            return ""
        kind = data["kind"]
        p = self.player
        if kind == "consumable":
            st = self.stats()
            if "heal" in data and p["hp"] < self.hp_max():
                heal = data["heal"] * st["potion_power"]
                p["hp"] = min(self.hp_max(), p["hp"] + heal)
                self.add_floater(p["x"], p["y"] - 1.0, f"+{int(heal)}", "#9cff9c")
                self.sound("potion")
                self.consume(index)
                return f"{data['name']}: +{int(heal)} HP"
            if "mp" in data and p["mp"] < self.mp_max():
                mp = data["mp"] * st["potion_power"]
                p["mp"] = min(self.mp_max(), p["mp"] + mp)
                self.sound("potion")
                self.consume(index)
                return f"{data['name']}: +{int(mp)} MP"
            if "speed" in data:
                p["buffs"]["speed_pct"] = {"value": data["speed"] * 100, "t": 10.0}
                self.sound("potion")
                self.consume(index)
                return f"{data['name']}: ускорение"
            return "Уже полон сил"
        if kind in ("weapon", "armor", "ring"):
            slot_key = data.get("slot", "weapon")
            old = p["equip"].get(slot_key)
            p["equip"][slot_key] = item_id
            inv.pop(index)
            if old:
                self.add_item(old, 1)
            self.sound("menu_select")
            return f"Экипировано: {data['name']}"
        if kind == "material":
            return f"{data['name']}: можно продать за {IT.sell_price(item_id)} золота"
        return f"{data['name']}: квестовый предмет"

    def consume(self, index: int) -> None:
        inv = self.player["inventory"]
        if 0 <= index < len(inv):
            inv[index]["count"] -= 1
            if inv[index]["count"] <= 0:
                inv.pop(index)

    def drop_item(self, index: int) -> None:
        inv = self.player["inventory"]
        if 0 <= index < len(inv):
            inv.pop(index)
            self.sound("menu_move")

    # ------------------------------------------------------------- merchant
    def shop_lines(self) -> list[tuple[str, int, int]]:
        """(item_id, unit_price, available_count) for the current tab."""
        if self.shop_tab == "buy":
            return [(i, IT.buy_price(i), n) for i, n in self.merchant_stock.items() if n > 0]
        seen: dict[str, int] = {}
        for slot in self.player["inventory"]:
            item_id = slot["id"]
            if IT.ITEMS[item_id]["kind"] == "quest":
                continue
            seen[item_id] = seen.get(item_id, 0) + slot["count"]
        return [(i, IT.sell_price(i), n) for i, n in sorted(seen.items(),
                                                           key=lambda kv: -IT.sell_price(kv[0]))]

    def shop_action(self) -> str:
        lines = self.shop_lines()
        if not lines:
            self.sound("error", 0.5)
            return "Нечего продавать"
        self.shop_cursor = max(0, min(self.shop_cursor, len(lines) - 1))
        item_id, price, count = lines[self.shop_cursor]
        data = IT.ITEMS[item_id]
        if self.shop_tab == "buy":
            if self.merchant_stock.get(item_id, 0) <= 0:
                self.sound("error", 0.5)
                return "Товар закончился"
            if self.player["gold"] < price:
                self.sound("error", 0.5)
                return "Не хватает золота"
            if not self.add_item(item_id, 1):
                self.sound("error", 0.5)
                return "Сумка полна"
            self.player["gold"] -= price
            self.merchant_stock[item_id] -= 1
            self.sound("buy")
            return f"Куплено: {data['name']} за {price}"
        if data["kind"] == "quest":
            self.sound("error", 0.5)
            return "Квестовые предметы не продаются"
        if not self.remove_item(item_id, 1):
            return "Предмета нет"
        self.player["gold"] += price
        self.sound("sell")
        self.quest_stats["sold"] = self.quest_stats.get("sold", 0) + 1
        self.refresh_quests()
        return f"Продано: {data['name']} за {price} золота"

    def sell_all_junk(self) -> str:
        total = 0
        sold = 0
        for slot in list(self.player["inventory"]):
            item_id = slot["id"]
            data = IT.ITEMS[item_id]
            if data["kind"] != "material":
                continue
            price = IT.sell_price(item_id)
            total += price * slot["count"]
            sold += slot["count"]
            self.remove_item(item_id, slot["count"])
        if sold == 0:
            self.sound("error", 0.5)
            return "Нет материалов на продажу"
        self.player["gold"] += total
        self.sound("sell")
        self.quest_stats["sold"] = self.quest_stats.get("sold", 0) + sold
        self.refresh_quests()
        return f"Продано {sold} материалов за {total} золота"

    # ----------------------------------------------------------------- setup
    # ------------------------------------------------------------- quests
    # The fifty quests live in quests.py, each owned by one villager. Progress is
    # derived from world statistics, so nothing has to be counted twice.
    def init_quests(self) -> None:
        self.quest_log = []
        self.quest_done = set()
        self.quest_ready = set()
        self.quest_stats = {"kill": {}, "chop": 0, "mine": 0, "gather": 0, "sold": 0}
        self.quests = []
        self.visited: set[str] = set()
        # туман войны: множество открытых ячеек 32×32 тайла для карты мира
        self.explored: set[tuple[int, int]] = set()

    def quest_current(self, q: dict) -> int:
        kind, target = q["kind"], q["target"]
        if kind in ("kill", "boss"):
            return self.quest_stats["kill"].get(target, 0)
        if kind in ("collect", "deliver"):
            return self.count_item(target)
        if kind == "sell":
            return self.quest_stats.get("sold", 0)
        if kind in ("chop", "mine", "gather"):
            return self.quest_stats.get(kind, 0)
        if kind == "learn":
            return len(self.player["learned"])
        if kind == "visit":
            return 1 if target in self.visited else 0
        if kind == "explore":
            return len(self.visited)
        return 0

    def quest_state(self, q: dict) -> str:
        if q["id"] in self.quest_done:
            return "done"
        if self.quest_current(q) >= q["count"]:
            return "ready"
        return "active"

    def refresh_quests(self) -> None:
        """Rebuild the journal from the accepted ids and the live world statistics."""
        self.quests = []
        for qid in self.quest_log:
            q = QST.by_id(qid)
            if not q:
                continue
            cur = self.quest_current(q)
            self.quests.append({**q, "goal": q["count"], "progress": min(cur, q["count"]),
                                "done": False, "ready": cur >= q["count"],
                                "state": "ready" if cur >= q["count"] else "active"})
        self.quests.sort(key=lambda q: (not q["ready"], -q["progress"] / max(1, q["goal"])))

    def accept_quest(self, qid: str) -> bool:
        q = QST.by_id(qid)
        if not q or qid in self.quest_log or qid in self.quest_done:
            return False
        self.quest_log.append(qid)
        self.refresh_quests()
        self.sound("menu_select")
        self.toast(f"Взято задание: {q['title']}", "#ffe066")
        return True

    def turn_in_quest(self, qid: str) -> str:
        q = QST.by_id(qid)
        if not q or qid not in self.quest_log:
            return "Это задание не взято"
        if self.quest_current(q) < q["count"]:
            return "Задание ещё не выполнено"
        if q["kind"] in ("collect", "deliver") and q["target"]:
            self.remove_item(q["target"], q["count"])
        xp = int(q["xp"] * self.stats()["xp_gain"])
        self.player["xp"] += xp
        self.player["gold"] += q["gold"]
        if q.get("reward"):
            self.add_item(q["reward"], 1)
        self.quest_done.add(qid)
        self.quest_ready.discard(qid)
        self.quest_log.remove(qid)
        self.refresh_quests()
        self.sound("quest_done")
        self.check_level()
        extra = ""
        if q.get("reward") and IT.ITEMS.get(q["reward"]):
            extra = f", {IT.ITEMS[q['reward']]['name']}"
        return f"Задание сдано: {q['title']} (+{xp} XP, +{q['gold']} золота{extra})"

    def available_quests(self, giver: str) -> list[dict]:
        done = set(self.quest_done) | set(self.quest_log)
        return QST.available(giver, done)

    def ready_quests(self, giver: str) -> list[dict]:
        out = []
        for qid in self.quest_log:
            q = QST.by_id(qid)
            if q and q["giver"] == giver and self.quest_current(q) >= q["count"]:
                out.append(q)
        return out

    def update_quests(self) -> None:
        region = self.region_at(self.player["x"], self.player["y"])
        if region and region["id"] not in self.visited:
            self.visited.add(region["id"])
            self.toast("Новая область: " + region["name"], "#b6e3a0")
        for qid in list(self.quest_log):
            q = QST.by_id(qid)
            if not q or qid in self.quest_ready:
                continue
            if self.quest_current(q) >= q["count"]:
                self.quest_ready.add(qid)
                npc = GIVER_NAMES.get(q["giver"], "жителя деревни")
                self.toast(f"Задание готово: {q['title']} — вернись к {npc}", "#b6e3a0")
                self.sound("menu_select", 0.6)
        self.refresh_quests()

    # ------------------------------------------------- harvesting the island
    def harvest_nodes(self) -> dict[tuple[int, int], dict]:
        """Every bush, flower, rock and tree you can interact with, keyed by tile."""
        if self.nodes is not None:
            return self.nodes
        nodes: dict[tuple[int, int], dict] = {}
        for d in self.world.decor:
            if d["kind"] in HARVEST:
                nodes[(d["x"], d["y"])] = {"x": d["x"], "y": d["y"], "kind": d["kind"],
                                           "ref": d}
        for o in self.world.objects:
            if o["kind"].startswith(TREE_KINDS):
                nodes[(o["x"], o["y"])] = {"x": o["x"], "y": o["y"], "kind": "tree",
                                           "ref": o}
        self.nodes = nodes
        return nodes

    def nearest_node(self, max_dist: float = HARVEST_RANGE) -> dict | None:
        """Closest harvestable tile. Looks only at the tiles around the player —
        scanning all ~4000 nodes every frame cost about 1.4 s per 300 frames."""
        nodes = self.harvest_nodes()
        px, py = self.player["x"], self.player["y"]
        cx, cy = int(px), int(py)
        span = int(math.ceil(max_dist)) + 1
        best, best_d = None, max_dist
        for ty in range(cy - span, cy + span + 1):
            for tx in range(cx - span, cx + span + 1):
                node = nodes.get((tx, ty))
                if node is None:
                    continue
                if self.harvest_done.get((tx, ty), 0.0) > self.time:
                    continue
                d = math.hypot(tx + 0.5 - px, ty + 0.5 - py)
                if d < best_d:
                    best, best_d = node, d
        return best

    def harvest(self, node: dict) -> str:
        """Chop a tree, mine a rock, pick a bush: the island answers back."""
        kind = node["kind"]
        stat, drops, chance, verb = HARVEST.get(kind, (None, [], 0.0, "Собрано"))
        if kind == "tree":
            stat, drops, chance, verb = "chop", [("wood", 2), ("leaf", 1)], 0.35, "Срублено"
        if stat is None:
            return ""
        gained: list[str] = []
        for i, (item_id, count) in enumerate(drops):
            if i and self.rng.random() > chance:
                continue
            n = count + (1 if i == 0 and self.rng.random() < 0.3 else 0)
            if self.add_item(item_id, n):
                gained.append(f"{IT.ITEMS[item_id]['name']} x{n}")
        self.quest_stats[stat] = self.quest_stats.get(stat, 0) + 1
        key = (node["x"], node["y"])
        self.harvest_done[key] = self.time + REGROW.get(kind, 60.0)
        ref = node["ref"]
        if kind == "tree":
            self.world.solid.discard(key)          # the tile opens up
            ref["kind"] = "stump"
            node["kind"] = "stump"
            node["ref"] = ref
            self.sound("hit_metal", 0.7)
            self.add_particle(node["x"] + 0.5, node["y"] + 0.5, (150, 176, 96), 10, 2.6)
        elif kind == "rock_small":
            self.sound("hit_metal", 0.8)
            self.add_particle(node["x"] + 0.5, node["y"] + 0.5, (168, 168, 176), 8, 2.4)
        else:
            self.sound("pickup", 0.7)
            self.add_particle(node["x"] + 0.5, node["y"] + 0.5, (120, 190, 96), 7, 2.0)
        self.sound("hit", 0.5)
        text = f"{verb}: " + (", ".join(gained) if gained else "пусто")
        self.toast(text, "#b6e3a0")
        self.refresh_quests()
        return text

    def update_harvest(self) -> None:
        """Bring back whatever was picked after its regrowth time."""
        for key, ready in list(self.harvest_done.items()):
            if ready > self.time:
                continue
            node = self.harvest_nodes().get(key)
            del self.harvest_done[key]
            if not node:
                continue
            ref = node["ref"]
            if node["kind"] == "stump":             # the stump becomes a tree again
                ref["kind"] = self.rng.choice(("oak", "pine", "birch"))
                self.world.solid.add(key)
                node["kind"] = "tree"

    # ---------------------------------------------------------------- music
    def current_track(self) -> str:
        if self.battle_track:
            return "battle"
        region = self.region_at(self.player["x"], self.player["y"])
        return REGION_TRACK.get(region["id"] if region else "", "forest")

    def update_music(self, dt: float, in_combat: bool) -> None:
        if not self.music_on:
            return
        self.music.update()           # start a track that was still being synthesised
        if in_combat:
            self.combat_t = COMBAT_HOLD
        else:
            self.combat_t = max(0.0, self.combat_t - dt)
        self.battle_track = self.combat_t > 0.0
        track = self.current_track()
        if track != self.music_track:
            self.music.play(track, 900)
            self.music_track = track

    def toggle_music(self) -> str:
        self.music_on = not self.music_on
        if self.music_on:
            self.music.set_volume(MUSIC_VOLUME)
            self.music_track = None
            self.music.play(self.current_track(), 400)
            return "Музыка включена"
        self.music.stop(400)
        self.music_track = None
        return "Музыка выключена"

    def next_track(self) -> str:
        """Cycle the soundtrack, so the player can hear all of it."""
        names = self.music.names()
        if not names:
            return "Музыки нет"
        try:
            i = (names.index(self.music_track) + 1) % len(names)
        except ValueError:
            i = 0
        self.music_on = True
        self.music.set_volume(MUSIC_VOLUME)
        self.music.play(names[i], 300)
        self.music_track = names[i]
        self.battle_track = False
        self.combat_t = 0.0
        title = MUS.TRACKS.get(names[i], {}).get("title", names[i])
        return f"Мелодия: {title}"

    # ---------------------------------------------------------------- combat

    def spawn_npcs(self) -> None:
        vx, vy = VILLAGE_CENTER
        self.npcs = [
            {"x": vx - 4.0, "y": vy - 3.0, "kind": "peasant", "name": "Крестьянин",
             "dir": "down", "met": False, "anim_t": 0.0,
             "lines": ["Добро пожаловать в Дубраву, путник!",
                       "Остров стал куда больше — и опаснее.",
                       "На юге топь, на северо-востоке руины. Не ходи один."]},
            {"x": vx + 4.0, "y": vy - 3.0, "kind": "farmer", "name": "Фермер",
             "dir": "down", "met": False, "anim_t": 0.0,
             "lines": ["Пшеница в этом году богатая!",
                       "На лугах пасутся коровы и овцы — их можно и подоить, и съесть."]},
            {"x": vx - 6.5, "y": vy + 3.0, "kind": "smith", "name": "Кузнец",
             "dir": "up", "met": False, "anim_t": 0.0, "gift": True,
             "lines": ["Сталь куётся в огне, а герой — в бою.",
                       "Держи зелья — и не благодари.",
                       "Приноси руду: из мифрила выйдет славный клинок."]},
            {"x": vx + 1.0, "y": vy + 4.0, "kind": "merchant", "name": "Торговец",
             "dir": "up", "met": False, "anim_t": 0.0, "shop": True,
             "lines": ["Покупаю всё, что падает с монстров!",
                       "Нажми E — и я покажу товар."]},
            {"x": vx, "y": vy - 5.0, "kind": "elder", "name": "Старейшина",
             "dir": "down", "met": False, "anim_t": 0.0,
             "lines": ["Я чувствую в тебе силу, странник.",
                       "На большом дубе растёт больше сотни умений — выбирай свою ветвь.",
                       "Три ветви ведут к войне, две — к мудрости."]},
            {"x": vx + 7.5, "y": vy + 3.0, "kind": "guard", "name": "Стражник",
             "dir": "left", "met": False, "anim_t": 0.0,
             "lines": ["За воротами держи оружие наготове.",
                       "Големов бей только с хорошей бронёй."]},
            {"x": vx - 14.0, "y": vy + 4.0, "kind": "healer", "name": "Знахарка",
             "dir": "right", "met": False, "anim_t": 0.0,
             "lines": ["Раны затянутся, было бы чем платить.",
                       "Травы и зелья спасают чаще, чем меч."]},
        ]
        # обитатели стоянок по всей карте: без них 4.8 млн клеток пустуют
        for site in getattr(self.world, "sites", ()):
            kind = site.get("npc")
            info = SITE_NPC_INFO.get(kind)
            if not info:
                continue
            name, lines = info
            spot = self.world.nearest_walkable(site["x"], site["y"] + 3) \
                or (site["x"], site["y"] + 3)
            self.npcs.append({
                "x": float(spot[0]) + 0.5, "y": float(spot[1]) + 0.5,
                "kind": kind, "name": name, "dir": "down", "met": False,
                "anim_t": 0.0, "lines": list(lines), "site": site["id"],
                "site_name": site["name"],
            })

    def spawn_mobs(self) -> None:
        rng = self.rng
        for region in self.world.regions:
            kinds = region.get("mobs") or []
            if not kinds:
                continue
            x0, y0, x1, y1 = region["rect"]
            area = max(1, (x1 - x0) * (y1 - y0))
            count = max(6, min(240, area // 700))
            level = region.get("level", 1)
            for _ in range(count):
                spot = self.world.random_walkable_in((x0, y0, x1, y1), rng, tries=40)
                if not spot:
                    continue
                kind = rng.choice(kinds)
                if rng.random() < 0.12:
                    kind = rng.choice([k for k in kinds if MOBS[k]["hp"] > 40] or kinds)
                self.mobs.append(self.make_mob(spot[0] + 0.5, spot[1] + 0.5, kind, level))

        # 18% суши лежит вне прямоугольников областей — там раньше не было ни
        # мобов, ни стоянок, и целые страны стояли пустыми. Добиваем россыпью:
        # бродячий зверь на каждые ~700 клеток такой земли.
        outside_target = 900
        placed = tries = 0
        while placed < outside_target and tries < outside_target * 40:
            tries += 1
            x = rng.randrange(4, MAP_W - 4)
            y = rng.randrange(4, MAP_H - 4)
            if not self.world.walkable(x, y):
                continue
            if self.region_at(x + 0.5, y + 0.5) is not None:
                continue
            kind = rng.choice(("wolf", "boar", "goblin", "spider", "slime", "bat"))
            self.mobs.append(self.make_mob(x + 0.5, y + 0.5, kind,
                                           1 + rng.randrange(3)))
            placed += 1

    def make_mob(self, x: float, y: float, kind: str, level: int = 1) -> dict:
        base = MOBS[kind]
        scale = 1.0 + (level - 1) * 0.18
        hp = base["hp"] * scale
        return {
            "x": x, "y": y, "kind": kind, "name": base["name"],
            "hp": hp, "hp_max": hp, "atk": base["atk"] * (1.0 + (level - 1) * 0.12),
            "speed": base["speed"], "xp": int(base["xp"] * scale),
            "aggro": base["aggro"], "reach": base["reach"], "scale": base.get("scale", 1.0),
            "passive": base.get("passive", False), "level": level,
            "dir": "down", "moving": False, "anim_t": 0.0, "frame": 0,
            "timer": 1 + self.rng.random() * 2, "attack_cd": 0.0, "hurt_t": 0.0,
            "atk_t": 0.0, "stun": 0.0, "slow": 0.0, "alive": True, "flee": 0.0,
            "wander": {"x": x, "y": y},
        }

    def ensure_reachable(self) -> None:
        self.reach = self.world.reachable_from(SPAWN_TILE)
        moved = 0
        for ent in list(self.npcs):
            tile = (int(ent["x"]), int(ent["y"]))
            if tile in self.reach:
                continue
            target = self.world.nearest_walkable(*tile)
            if target:
                ent["x"], ent["y"] = target[0] + 0.5, target[1] + 0.5
                moved += 1
        self.mobs = [m for m in self.mobs
                     if (int(m["x"]), int(m["y"])) in self.reach]
        self.npcs_moved = moved

    # --------------------------------------------------------------- helpers
    def toast(self, text: str, color: str = "#ffffff") -> None:
        self.toasts.append({"text": text, "color": color, "t": 0.0, "life": 3.4})

    def add_floater(self, x, y, text, color) -> None:
        self.floaters.append({"x": x, "y": y, "text": text, "color": color,
                              "t": 0.0, "life": 1.1})

    def add_particle(self, x, y, color, count: int = 1, speed: float = 3.0) -> None:
        for _ in range(count):
            a = self.rng.random() * math.tau
            s = speed * (0.5 + self.rng.random())
            self.particles.append({"x": x, "y": y, "vx": math.cos(a) * s,
                                   "vy": math.sin(a) * s, "t": 0.0,
                                   "life": 0.35 + self.rng.random() * 0.4,
                                   "color": color})

    def face_dir(self) -> tuple[int, int]:
        d = self.player["dir"]
        return {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[d]

    def nearest_npc(self, max_dist: float = 2.2) -> dict | None:
        p = self.player
        best, best_d = None, max_dist
        for n in self.npcs:
            d = math.hypot(n["x"] - p["x"], n["y"] - p["y"])
            if d <= best_d:
                best, best_d = n, d
        return best

    def region_at(self, x: float, y: float) -> dict | None:
        for region in self.world.regions:
            x0, y0, x1, y1 = region["rect"]
            if x0 <= x <= x1 and y0 <= y <= y1:
                return region
        return None

    # -------------------------------------------------------------- movement
    def try_move(self, ent: dict, mx: float, my: float) -> None:
        r = 0.30
        w = self.world
        nx, ny = ent["x"] + mx, ent["y"] + my
        if not w.blocked_rect(nx, ent["y"], r):
            ent["x"] = nx
        if not w.blocked_rect(ent["x"], ny, r):
            ent["y"] = ny

    # ---------------------------------------------------------------- update
    def in_combat(self) -> bool:
        """True while a hostile is close enough to matter (drives the battle theme)."""
        px, py = self.player["x"], self.player["y"]
        for m in self.mobs:
            if not m["alive"] or m.get("friendly"):
                continue
            if math.hypot(m["x"] - px, m["y"] - py) <= COMBAT_RANGE:
                return True
        return self.player["atk_t"] > 0

    def update(self, dt: float, inp: dict) -> None:
        self.frame += 1
        self.time += dt
        self.update_player(dt, inp)
        self.update_mobs(dt)
        self.update_allies(dt)
        self.update_npcs(dt)
        self.update_effects(dt)
        self.update_quests()
        self.update_harvest()
        self.mark_explored()
        self.update_events(dt)
        self.update_music(dt, self.in_combat())
        if self.shake > 0:
            self.shake = max(0.0, self.shake - dt * 1.6)

    # -------------------------------------------------------------- события
    def update_events(self, dt: float) -> None:
        """Случайные события вокруг игрока: караван, налёт, клад, звезда, странник.

        Без них мир читается как декорация: идёшь сорок минут, ничего не
        происходит. Событие всегда случается рядом (10–22 тайла), чтобы игрок
        успел его увидеть, и живёт ограниченное время.
        """
        for ev in list(self.active_events):
            ev["t"] += dt
            if ev["t"] >= ev["life"]:
                self._end_event(ev)
                self.active_events.remove(ev)
        self.event_timer -= dt
        if self.event_timer > 0:
            return
        self.event_timer = self.rng.uniform(*EVENT_INTERVAL)
        self._start_event()

    def _event_spot(self, near: float = 16.0):
        """Проходимая клетка в 10–22 тайлах от игрока."""
        p = self.player
        for _ in range(40):
            ang = self.rng.random() * math.tau
            dist = near + self.rng.random() * 6
            x = int(p["x"] + math.cos(ang) * dist)
            y = int(p["y"] + math.sin(ang) * dist)
            if self.world.walkable(x, y):
                return x, y
        return None

    def _start_event(self) -> None:
        rng = self.rng
        kind = rng.choices(
            ("raid", "cache", "meteor", "caravan", "wanderer", "beast"),
            weights=(30, 22, 14, 16, 12, 6), k=1)[0]
        spot = self._event_spot(18.0 if kind == "raid" else 13.0)
        if spot is None:
            return
        x, y = spot[0] + 0.5, spot[1] + 0.5
        ev = {"kind": kind, "x": x, "y": y, "t": 0.0, "life": 120.0, "ids": []}

        if kind == "raid":
            region = self.region_at(x, y)
            kinds = (region or {}).get("mobs") or ["goblin", "wolf", "bandit"]
            level = (region or {}).get("level", 1)
            pack = rng.randrange(4, 7)
            for i in range(pack):
                k = rng.choice(kinds)
                m = self.make_mob(x + rng.uniform(-2, 2), y + rng.uniform(-2, 2), k, level)
                m["aggro"] = max(m["aggro"], 16.0)      # налёт сам идёт на игрока
                m["event"] = True
                self.mobs.append(m)
                ev["ids"].append(id(m))
            self.toast("Налёт! Кто-то идёт по твоему следу", "#ff8a7a")
            self.sound("enemy_hit", 0.6)
            ev["life"] = 150.0

        elif kind == "cache":
            self.world._place(int(x), int(y), "crate", solid=True)
            for item_id in rng.sample(("potion", "ore_iron", "gem_ruby", "cloth", "herb"), 3):
                self.drops.append({"x": x + rng.uniform(-0.4, 0.4),
                                   "y": y + rng.uniform(0.2, 0.6),
                                   "t": 0.0, "kind": item_id, "count": 1})
            gold = rng.randrange(15, 45)
            self.drops.append({"x": x, "y": y + 0.4, "t": 0.0, "kind": "gold",
                               "count": gold})
            self.toast("Рядом брошенный ящик — внутри что-то есть", "#ffe066")
            ev["life"] = 40.0

        elif kind == "meteor":
            self.add_particle(x, y, "#fff2b0", 30, 5.0)
            self.sound("levelup", 0.5)
            for item_id in rng.sample(("ore_mithril", "gem_emerald", "gem_sapphire",
                                       "ore_gold"), 2):
                self.drops.append({"x": x + rng.uniform(-0.5, 0.5),
                                   "y": y + rng.uniform(-0.5, 0.5),
                                   "t": 0.0, "kind": item_id, "count": 1})
            self.toast("С неба упала звезда — на месте падения что-то блестит", "#9ad7ff")
            ev["life"] = 45.0

        elif kind == "caravan":
            npc = {"x": x, "y": y, "kind": "merchant", "name": "Караванщик",
                   "dir": "down", "met": False, "anim_t": 0.0, "shop": True,
                   "event": True,
                   "lines": ["Караван идёт дальше через минуту.",
                             "Бери, пока не свернулся: цены честные."]}
            self.npcs.append(npc)
            ev["npc"] = npc
            self.toast("Караван встал неподалёку — торговля открыта", "#9ad7ff")
            ev["life"] = 110.0

        elif kind == "wanderer":
            npc = {"x": x, "y": y, "kind": "pilgrim", "name": "Странник",
                   "dir": "down", "met": False, "anim_t": 0.0, "event": True,
                   "gift_gold": self.rng.randrange(12, 30),
                   "lines": ["Иду с севера. Там, в кряже, кто-то жжёт огни по ночам.",
                             "Держи монету — мне всё равно тяжело нести."]}
            self.npcs.append(npc)
            ev["npc"] = npc
            self.toast("На дороге странник — у него есть, что рассказать", "#b6e3a0")
            ev["life"] = 90.0

        else:  # beast
            region = self.region_at(x, y)
            level = (region or {}).get("level", 1) + 2
            kind_mob = rng.choice(("bear", "troll", "golem", "wraith"))
            m = self.make_mob(x, y, kind_mob, level)
            m["hp"] = m["hp_max"] = m["hp_max"] * 2.2
            m["atk"] *= 1.4
            m["xp"] = int(m["xp"] * 2.5)
            m["event"] = True
            self.mobs.append(m)
            ev["ids"].append(id(m))
            self.toast(f"Поблизости объявился {m['name']} — крупный и злой", "#ffb0a0")
            ev["life"] = 180.0

        self.active_events.append(ev)

    def _end_event(self, ev: dict) -> None:
        """Убрать временных участников события, чтобы мир не засорялся."""
        if ev.get("npc") is not None:
            npc = ev["npc"]
            if npc in self.npcs:
                self.npcs.remove(npc)
            if self.dialog and self.dialog.get("name") == npc["name"]:
                self.dialog = None
        ids = set(ev.get("ids") or ())
        if ids:
            self.mobs = [m for m in self.mobs if id(m) not in ids or not m.get("event")]

    def mark_explored(self) -> None:
        """Открыть клетки карты вокруг игрока — туман войны для карты мира.

        13 ячеек на кадр: дёшево и без заметных дыр по краям экрана, потому что
        клетка — 32×32 тайла, то есть экран целиком.
        """
        cx = int(self.player["x"]) // MAP_CELL
        cy = int(self.player["y"]) // MAP_CELL
        ex = self.explored
        for dy in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                if abs(dx) + abs(dy) <= 2:
                    ex.add((cx + dx, cy + dy))

    def update_player(self, dt: float, inp: dict) -> None:
        p = self.player
        st = self.stats()
        dx = (1 if inp.get("right") else 0) - (1 if inp.get("left") else 0)
        dy = (1 if inp.get("down") else 0) - (1 if inp.get("up") else 0)
        p["moving"] = (dx != 0 or dy != 0) and p["atk_t"] <= 0
        if p["moving"]:
            ln = math.hypot(dx, dy) or 1
            nx, ny = dx / ln, dy / ln
            self.try_move(p, nx * st["speed"] * dt, ny * st["speed"] * dt)
            if abs(nx) > abs(ny):
                p["dir"] = "right" if nx > 0 else "left"
            elif ny != 0:
                p["dir"] = "down" if ny > 0 else "up"
            p["anim_t"] += dt
            if p["anim_t"] > 0.16:
                p["anim_t"] = 0.0
                p["frame"] = 1 - p["frame"]
                if self.frame % 6 == 0:
                    self.sound("footstep", 0.25)
        else:
            p["frame"] = 0
            p["anim_t"] = 0.0
        p["atk_t"] = max(0.0, p["atk_t"] - dt)
        p["atk_anim"] = max(0.0, p["atk_anim"] - dt)
        p["hurt_t"] = max(0.0, p["hurt_t"] - dt)
        p["invuln"] = max(0.0, p["invuln"] - dt)
        p["stealth"] = max(0.0, p["stealth"] - dt)
        for key in list(p["cooldowns"]):
            p["cooldowns"][key] = max(0.0, p["cooldowns"][key] - dt)
        for stat in list(p["buffs"]):
            p["buffs"][stat]["t"] -= dt
            if p["buffs"][stat]["t"] <= 0:
                del p["buffs"][stat]
        hp_max, mp_max = st["hp_max"], st["mp_max"]
        p["hp"] = min(hp_max, p["hp"] + (st["regen"] + 0.4) * dt)
        p["mp"] = min(mp_max, p["mp"] + (st["mp_regen"] + 0.6) * dt)

    def update_mobs(self, dt: float) -> None:
        p = self.player
        st = self.stats()
        px, py = p["x"], p["y"]
        far = 30.0                     # mobs further away than this are asleep
        for m in self.mobs:
            if not m["alive"]:
                continue
            m["hurt_t"] = max(0.0, m["hurt_t"] - dt)
            m["attack_cd"] = max(0.0, m["attack_cd"] - dt)
            m["atk_t"] = max(0.0, m["atk_t"] - dt)
            m["stun"] = max(0.0, m["stun"] - dt)
            m["slow"] = max(0.0, m["slow"] - dt)
            if m["stun"] > 0:
                continue
            dist = math.hypot(px - m["x"], py - m["y"])
            if dist > far and m["flee"] <= 0:
                continue               # nothing can see or reach you from that far
            speed = m["speed"] * (0.55 if m["slow"] > 0 else 1.0)
            stealth = p["stealth"] > 0
            if m["flee"] > 0:                      # animals run away when hurt
                m["flee"] -= dt
                ux = (m["x"] - p["x"]) / (dist or 1)
                uy = (m["y"] - p["y"]) / (dist or 1)
                self.try_move(m, ux * speed * dt, uy * speed * dt)
                m["moving"] = True
                m["dir"] = "right" if ux > 0 else "left"
            elif (not m["passive"] or m["hurt_t"] > 0) and dist < m["aggro"] \
                    and p["hp"] > 0 and not stealth:
                ux = (p["x"] - m["x"]) / (dist or 1)
                uy = (p["y"] - m["y"]) / (dist or 1)
                if dist > m["reach"]:
                    self.try_move(m, ux * speed * dt, uy * speed * dt)
                    m["moving"] = True
                elif m["attack_cd"] <= 0:
                    m["atk_t"] = 0.35
                    m["attack_cd"] = 1.2
                    if dist < m["reach"] + 0.3:
                        raw = max(1.0, m["atk"] + self.rng.randrange(3) - 1)
                        if self.rng.random() < st["dodge"] / 100.0:
                            self.add_floater(p["x"], p["y"] - 1.0, "мимо", "#bcd6ff")
                            self.sound("dodge", 0.6)
                        else:
                            dmg = max(1, raw - st["def"] * 0.6)
                            if p["invuln"] > 0:
                                dmg *= 0.2
                            dmg = self.incoming_damage(dmg)
                            p["hp"] -= dmg
                            p["hurt_t"] = 0.25
                            p["invuln"] = 0.25
                            if self.settings.get("damage_numbers"):
                                self.add_floater(p["x"], p["y"] - 1.0, f"-{int(dmg)}", "#ff7070")
                            if self.settings.get("screen_shake"):
                                self.shake = min(0.5, self.shake + 0.22)
                            self.add_particle(p["x"], p["y"], "#ff6b6b", 8)
                            self.sound("player_hurt", 0.8)
                            if st["thorns"] > 0:
                                self.hurt_mob(m, int(st["thorns"]), silent=True)
                            if p["hp"] <= 0:
                                self.player_died()
                if abs(ux) > abs(uy):
                    m["dir"] = "right" if ux > 0 else "left"
                else:
                    m["dir"] = "down" if uy > 0 else "up"
            else:
                m["timer"] -= dt
                if m["timer"] <= 0:
                    m["timer"] = 2 + self.rng.random() * 4
                    a = self.rng.random() * math.tau
                    m["wander"]["x"] = m["x"] + math.cos(a) * 4.0
                    m["wander"]["y"] = m["y"] + math.sin(a) * 4.0
                ln = math.hypot(m["wander"]["x"] - m["x"], m["wander"]["y"] - m["y"])
                if ln > 0.4:
                    ux = (m["wander"]["x"] - m["x"]) / ln
                    uy = (m["wander"]["y"] - m["y"]) / ln
                    self.try_move(m, ux * speed * 0.4 * dt, uy * speed * 0.4 * dt)
                    m["moving"] = True
                    if abs(ux) > abs(uy):
                        m["dir"] = "right" if ux > 0 else "left"
                    else:
                        m["dir"] = "down" if uy > 0 else "up"
                else:
                    m["moving"] = False
            m["anim_t"] += dt
            if m["anim_t"] > 0.2:
                m["anim_t"] = 0.0
                m["frame"] = 1 - m["frame"]
        # keep monsters from stacking — через пространственные корзины.
        # Наивный двойной цикл был O(n²): при 91 мобе это 4 тыс. пар, при 554 —
        # уже 153 тыс. пар на кадр, и один этот блок съедал 60% кадра.
        cell = 2.0
        grid: dict[tuple[int, int], list[dict]] = {}
        for m in self.mobs:
            if m["alive"]:
                grid.setdefault((int(m["x"] // cell), int(m["y"] // cell)), []).append(m)
        # соседние ячейки: только «вперёд», чтобы каждая пара считалась один раз
        NEIGH = ((0, 1), (1, -1), (1, 0), (1, 1))
        for (gx, gy), bucket in grid.items():
            for i in range(len(bucket)):
                a = bucket[i]
                for b in bucket[i + 1:]:
                    self._separate(a, b)
            for (ox, oy) in NEIGH:
                other = grid.get((gx + ox, gy + oy))
                if not other:
                    continue
                for a in bucket:
                    for b in other:
                        self._separate(a, b)

    def _separate(self, a: dict, b: dict) -> None:
        dx, dy = a["x"] - b["x"], a["y"] - b["y"]
        d2 = dx * dx + dy * dy
        if d2 <= 0.0 or d2 >= 0.49:        # 0.7²
            return
        d = math.sqrt(d2)
        push = (0.7 - d) / 2
        ux, uy = dx / d, dy / d
        self.try_move(a, ux * push, uy * push)
        self.try_move(b, -ux * push, -uy * push)

    def update_allies(self, dt: float) -> None:
        for a in list(self.allies):
            a["t"] -= dt
            if a["t"] <= 0 or a["hp"] <= 0:
                self.allies.remove(a)
                self.add_particle(a["x"], a["y"], "#c8d0ff", 10)
                continue
            a["atk_t"] = max(0.0, a["atk_t"] - dt)
            target, best = None, 9.0
            for m in self.mobs:
                if not m["alive"]:
                    continue
                d = math.hypot(m["x"] - a["x"], m["y"] - a["y"])
                if d < best:
                    target, best = m, d
            if target:
                ux = (target["x"] - a["x"]) / (best or 1)
                uy = (target["y"] - a["y"]) / (best or 1)
                if best > 1.1:
                    self.try_move(a, ux * a["speed"] * dt, uy * a["speed"] * dt)
                    a["moving"] = True
                elif a["atk_t"] <= 0:
                    a["atk_t"] = 0.7
                    self.hurt_mob(target, max(1, int(a["atk"])), silent=True)
                a["dir"] = "right" if ux > 0 else "left"
            a["anim_t"] += dt
            if a["anim_t"] > 0.2:
                a["anim_t"] = 0.0
                a["frame"] = 1 - a["frame"]

    def update_npcs(self, dt: float) -> None:
        for n in self.npcs:
            n["anim_t"] = (n["anim_t"] + dt) % 0.8

    def update_effects(self, dt: float) -> None:
        for p in self.particles:
            p["t"] += dt
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["vx"] *= 0.9
            p["vy"] *= 0.9
        self.particles = [p for p in self.particles if p["t"] < p["life"]]
        for f in self.floaters:
            f["t"] += dt
            f["y"] -= dt * 0.8
        self.floaters = [f for f in self.floaters if f["t"] < f["life"]]
        for c in self.corpses:
            c["t"] += dt
        self.corpses = [c for c in self.corpses if c["t"] < 1.8]
        pl = self.player
        for d in self.drops:
            d["t"] += dt
            if d["t"] > 0.4 and not d.get("taken") and \
                    math.hypot(d["x"] - pl["x"], d["y"] - pl["y"]) < 1.1:
                d["taken"] = True
                if d["kind"] == "gold":
                    pl["gold"] += d["count"]
                    self.add_floater(d["x"], d["y"], f"+{d['count']} золота", "#ffd166")
                    self.sound("coin", 0.6)
                else:
                    if self.add_item(d["kind"], d["count"]):
                        self.add_floater(d["x"], d["y"],
                                         f"+{d['count']} {IT.item_name(d['kind'])}", "#9ad7ff")
                        self.sound("pickup", 0.5)
                    else:
                        d["taken"] = False
                        d["t"] = 0.0
                        self.toast("Сумка полна!", "#ffb0b0")
        self.drops = [d for d in self.drops if not d.get("taken") and d["t"] < 120]
        for t in self.toasts:
            t["t"] += dt
        self.toasts = [t for t in self.toasts if t["t"] < t["life"]]

    def update_quests(self) -> None:
        region = self.region_at(self.player["x"], self.player["y"])
        if region and region["id"] not in self.visited:
            self.visited.add(region["id"])
            self.toast("Новая область: " + region["name"], "#b6e3a0")

    # ---------------------------------------------------------------- combat
    def attack(self) -> None:
        p = self.player
        if p["atk_t"] > 0:
            return
        st = self.stats()
        p["atk_t"] = st["atk_cd"]
        p["atk_anim"] = 0.3
        fx, fy = self.face_dir()
        self.sound("swing", 0.8)
        hits = 0
        sweep = st["aoe"]
        for m in self.mobs:
            if not m["alive"]:
                continue
            dist = math.hypot(m["x"] - p["x"], m["y"] - p["y"])
            if dist > 1.75 * sweep:
                continue
            dot = ((m["x"] - p["x"]) * fx + (m["y"] - p["y"]) * fy) / (dist or 1)
            if sweep < 1.15 and dot < 0.3:
                continue
            dmg = st["atk"] + self.rng.randrange(3)
            if self.rng.random() < st["crit_chance"] / 100.0:
                dmg *= st["crit_mult"]
                self.add_floater(m["x"], m["y"] - 1.0, "крит!", "#ff9a5a")
            for elem in ("fire_damage", "frost_damage", "poison_damage"):
                dmg += st[elem]
            dmg = max(1, int(dmg - m["level"] * 0.6))
            self.hurt_mob(m, dmg)
            if st["lifesteal"]:
                p["hp"] = min(self.hp_max(), p["hp"] + dmg * st["lifesteal"] / 100.0)
            kb = 0.35 + st["knockback"] / 200.0
            self.try_move(m, -fx * kb, -fy * kb)
            hits += 1
        if hits == 0:
            for _ in range(6):
                self.add_particle(p["x"] + fx * 0.9, p["y"] + fy * 0.9, "#cfd6ff")
            if not any(m["alive"] and math.hypot(m["x"] - p["x"], m["y"] - p["y"]) < 2.5
                       for m in self.mobs):
                pass
        else:
            self.sound("hit", 0.7)

    def hurt_mob(self, m: dict, dmg: int, ability: str | None = None,
                 silent: bool = False) -> None:
        if not m["alive"] or dmg <= 0:
            return
        m["hp"] -= dmg
        m["hurt_t"] = 0.3
        if m["passive"]:
            m["flee"] = 6.0
        color = "#ffd166" if dmg > 12 else "#ffe066"
        self.add_floater(m["x"], m["y"] - 1.0, f"-{dmg}", color)
        if self.settings.get("screen_shake") and dmg >= 12:
            self.shake = min(0.4, self.shake + 0.1)
        self.add_particle(m["x"], m["y"], "#ffd166" if not ability else "#c8b0ff", 10)
        if not silent:
            self.sound("hit_metal" if m["kind"] in ("skeleton", "golem") else "hit", 0.7)
        if m["hp"] <= 0:
            self.kill_mob(m)

    def kill_mob(self, m: dict) -> None:
        m["alive"] = False
        p = self.player
        st = self.stats()
        xp = int(m["xp"] * st["xp_gain"])
        p["xp"] += xp
        gold = int(IT.gold_drop(m["kind"], self.rng) * st["gold_find"])
        p["gold"] += gold
        self.kills[m["kind"]] = self.kills.get(m["kind"], 0) + 1
        self.toast(f"Побеждён: {m['name']} (+{xp} XP, +{gold} золота)", "#ffe066")
        self.sound("boss_die" if m["hp_max"] > 70 else "enemy_die", 0.8)
        self.drops.append({"x": m["x"], "y": m["y"], "t": 0.0, "kind": "gold",
                           "count": gold})
        loot = IT.roll_loot(m["kind"], self.rng)
        if st["loot_chance"] > 1.0 and self.rng.random() < (st["loot_chance"] - 1.0):
            extra = IT.roll_loot(m["kind"], self.rng)
            loot.extend(extra)
        for item_id in loot:
            self.drops.append({"x": m["x"] + self.rng.uniform(-0.5, 0.5),
                               "y": m["y"] + self.rng.uniform(-0.5, 0.5),
                               "t": 0.0, "kind": item_id, "count": 1})
        self.corpses.append({"x": m["x"], "y": m["y"], "kind": m["kind"], "t": 0.0})
        self.add_particle(m["x"], m["y"], "#88ff88", 16, 4.0)
        self.check_level()
        kills = self.quest_stats.setdefault("kill", {})
        kills[m["kind"]] = kills.get(m["kind"], 0) + 1
        self.refresh_quests()
        self.respawn_mob(m["kind"])

    def respawn_mob(self, kind: str) -> None:
        """Keep the world populated: respawn the same species in its region."""
        region = next((r for r in self.world.regions if kind in (r.get("mobs") or [])),
                      None)
        if not region:
            return
        spot = self.world.random_walkable_in(region["rect"], self.rng, tries=30)
        if not spot:
            return
        p = self.player
        if math.hypot(spot[0] - p["x"], spot[1] - p["y"]) < 14:
            return
        self.mobs.append(self.make_mob(spot[0] + 0.5, spot[1] + 0.5, kind,
                                       region.get("level", 1)))

    def check_level(self) -> None:
        p = self.player
        while p["xp"] >= p["xp_next"]:
            p["xp"] -= p["xp_next"]
            p["level"] += 1
            p["xp_next"] = int(p["xp_next"] * 1.45)
            p["hp"] = self.hp_max()
            p["mp"] = self.mp_max()
            self.skill_points += 1
            self.sound("level_up")
            self.toast(f"Уровень {p['level']}! +1 очко навыка (K)", "#9ad7ff")
            if self.settings.get("autosave"):
                self.save()

    def player_died(self) -> None:
        p = self.player
        self.deaths += 1
        p["hp"] = self.hp_max()
        p["mp"] = self.mp_max()
        p["x"], p["y"] = float(SPAWN_TILE[0]) + 0.5, float(SPAWN_TILE[1]) + 0.5
        p["stealth"] = 2.0
        p["invuln"] = 3.0
        for m in self.mobs:
            m["wander"] = {"x": m["x"], "y": m["y"]}
        self.sound("player_die")
        self.toast("Ты потерял сознание... и очнулся в деревне.", "#ffb0b0")

    # ------------------------------------------------------------ interaction
    def interact(self) -> None:
        if self.dialog:
            self.dialog = None
            return
        n = self.nearest_npc()
        if n:
            n["dir"] = "left" if self.player["x"] > n["x"] else "right"
            giver = n.get("kind", "")
            offers = self.available_quests(giver) if giver else []
            turns = self.ready_quests(giver) if giver else []
            self.dialog = {"name": n["name"], "line": self.rng.choice(n["lines"]),
                           "shop": bool(n.get("shop")), "giver": giver,
                           "site": n.get("site_name", ""),
                           "offers": [q["id"] for q in offers[:3]],
                           "turns": [q["id"] for q in turns[:3]]}
            self.sound("dialog")
            if n.get("gift_gold") and not n.get("gave"):
                n["gave"] = True
                self.player["gold"] += int(n["gift_gold"])
                self.toast(f"Странник дал {n['gift_gold']} золота", "#ffe066")
            if n.get("gift") and not n.get("gave"):
                n["gave"] = True
                self.add_item("potion", 3)
                self.add_item("mana_potion", 1)
                self.toast("Кузнец дал 3 зелья и зелье маны", "#ffe066")
            if not n["met"]:
                n["met"] = True
            return
        for m in self.mobs:
            if m["alive"] and math.hypot(m["x"] - self.player["x"],
                                         m["y"] - self.player["y"]) < 1.6:
                self.attack()
                return
        node = self.nearest_node()
        if node:
            self.harvest(node)
            return
        self.toast("Рядом никого и ничего нет.", "#c8c8d0")

    def dialog_take_quest(self, index: int) -> str:
        """Accept the index-th quest the current villager is offering."""
        if not self.dialog:
            return ""
        offers = self.dialog.get("offers", [])
        if not 0 <= index < len(offers):
            return ""
        qid = offers[index]
        q = QST.by_id(qid)
        if not self.accept_quest(qid):
            return "Это задание уже взято"
        self.dialog["offers"] = [o for o in offers if o != qid]
        return f"Задание: {q['title']} — {q['desc']}"

    def dialog_turn_in(self) -> str:
        """Hand in the first finished quest this villager is waiting for."""
        if not self.dialog:
            return ""
        turns = self.dialog.get("turns", [])
        if not turns:
            return ""
        msg = self.turn_in_quest(turns[0])
        self.dialog["turns"] = turns[1:]
        return msg

    def open_shop(self) -> None:
        self.overlay = "shop"
        self.shop_tab = "sell"
        self.shop_cursor = 0
        self.sound("menu_select")

    def use_potion_hotkey(self) -> None:
        for i, slot in enumerate(self.player["inventory"]):
            if slot["id"] in ("potion", "potion_big", "elixir") and \
                    self.player["hp"] < self.hp_max():
                self.toast(self.use_slot(i), "#8ee08e")
                return
        self.toast("Зелий нет или здоровье полное", "#c8c8d0")

    # -------------------------------------------------------------- save/load
    def save(self, path: Path = SAVE_PATH) -> bool:
        try:
            p = dict(self.player)
            p["learned"] = sorted(p["learned"])
            data = {"version": 5, "player": p, "skill_points": self.skill_points,
                    "quest_log": self.quest_log, "quest_done": sorted(self.quest_done),
                    "quest_stats": {**self.quest_stats,
                                    "kill": dict(self.quest_stats.get("kill", {}))},
                    "harvest": [[k[0], k[1], round(v, 1)] for k, v in self.harvest_done.items()],
                    "music_on": self.music_on,
                    "merchant": self.merchant_stock,
                    "visited": sorted(self.visited), "kills": self.kills,
                    "explored": sorted(self.explored),
                    "npcs_met": {n["name"]: n["met"] for n in self.npcs}}
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            self.toast("Игра сохранена", "#9ad7ff")
            self.sound("menu_select")
            return True
        except OSError as exc:
            self.toast(f"Не удалось сохранить: {exc}", "#ff9a9a")
            return False

    def load(self, path: Path = SAVE_PATH) -> bool:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.toast("Сохранение не найдено", "#ff9a9a")
            self.sound("error")
            return False
        p = self.player
        for k, v in data.get("player", {}).items():
            if k in ("inventory", "equip", "learned", "hotbar", "cooldowns", "buffs"):
                continue
            if k in p:
                p[k] = v
        p["learned"] = {s for s in data.get("player", {}).get("learned", [])
                        if SK.by_id(s)}
        p["learned"].add("root")
        hotbar = [a for a in data.get("player", {}).get("hotbar", [])
                  if a in ABILITIES][:HOTBAR_KEYS]
        for sid in SK.active_abilities(p["learned"]):
            if sid not in hotbar and len(hotbar) < HOTBAR_KEYS:
                hotbar.append(sid)
        p["hotbar"] = hotbar
        p["cooldowns"] = {}
        p["buffs"] = {}
        inv = data.get("player", {}).get("inventory")
        if isinstance(inv, list):
            p["inventory"] = [s for s in inv
                              if isinstance(s, dict) and s.get("id") in IT.ITEMS][:INV_SLOTS]
        equip = data.get("player", {}).get("equip")
        if isinstance(equip, dict):
            p["equip"] = {k: (v if v in IT.ITEMS else None)
                          for k, v in equip.items() if k in p["equip"]}
        self.skill_points = int(data.get("skill_points", self.skill_points))
        self.quest_log = [q for q in data.get("quest_log", []) if QST.by_id(q)]
        self.quest_done = {q for q in data.get("quest_done", []) if QST.by_id(q)}
        stats = data.get("quest_stats")
        if isinstance(stats, dict):
            self.quest_stats = {"kill": {k: int(v) for k, v in stats.get("kill", {}).items()},
                                "chop": int(stats.get("chop", 0)),
                                "mine": int(stats.get("mine", 0)),
                                "gather": int(stats.get("gather", 0)),
                                "sold": int(stats.get("sold", 0))}
        self.harvest_done = {}
        for row in data.get("harvest", []):
            try:
                x, y, ready = int(row[0]), int(row[1]), float(row[2])
            except (TypeError, ValueError, IndexError):
                continue
            self.harvest_done[(x, y)] = ready
        if "music_on" in data:
            self.music_on = bool(data["music_on"])
        self.refresh_quests()
        stock = data.get("merchant")
        if isinstance(stock, dict):
            self.merchant_stock = {k: int(v) for k, v in stock.items()
                                   if k in IT.ITEMS}
        self.visited = set(data.get("visited", []))
        self.explored = {(int(c[0]), int(c[1])) for c in data.get("explored", [])
                         if isinstance(c, (list, tuple)) and len(c) == 2}
        self.kills = dict(data.get("kills", {}))
        met = data.get("npcs_met", {})
        for n in self.npcs:
            n["met"] = bool(met.get(n["name"], n["met"]))
        self.toast("Игра загружена", "#9ad7ff")
        self.sound("menu_select")
        return True


# ----------------------------------------------------------------------------
# Config helpers
# ----------------------------------------------------------------------------
def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    except OSError:
        pass


def parse_res_arg(argv: list[str]) -> int | None:
    for i, a in enumerate(argv):
        if a == "--res" and i + 1 < len(argv):
            try:
                w, h = argv[i + 1].lower().split("x")
                w, h = int(w), int(h)
            except ValueError:
                return None
            return min(range(len(RESOLUTIONS)),
                       key=lambda i: abs(RESOLUTIONS[i][0] - w) + abs(RESOLUTIONS[i][1] - h))
    return None


def best_res_index_for_desktop() -> int:
    try:
        dw, dh = pygame.display.get_desktop_sizes()[0]
    except Exception:
        return DEFAULT_RES_INDEX
    for i in range(len(RESOLUTIONS) - 1, -1, -1):
        if RESOLUTIONS[i][0] <= dw and RESOLUTIONS[i][1] <= dh:
            return i
    return 0


def apply_display(res_index: int, fullscreen: bool):
    w, h, zoom = RESOLUTIONS[res_index]
    if fullscreen:
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except Exception:
            dw, dh = w, h
        screen = pygame.display.set_mode((dw, dh), pygame.FULLSCREEN)
        best = 1
        for z in (1, 2, 3, 4):
            if dw // z >= 480 and dh // z >= 270:
                best = z
        return screen, dw, dh, best
    return pygame.display.set_mode((w, h)), w, h, zoom


KEYMAP = {
    pygame.K_w: "up", pygame.K_UP: "up",
    pygame.K_s: "down", pygame.K_DOWN: "down",
    pygame.K_a: "left", pygame.K_LEFT: "left",
    pygame.K_d: "right", pygame.K_RIGHT: "right",
}


def gather_input(keys, keymap: dict | None = None) -> dict:
    """Movement input from the pressed-key table, honouring the player's bindings.
    The arrow keys always work as well, so a rebound layout never locks anyone out."""
    keymap = keymap or DEFAULT_KEYS
    inp = {"up": False, "down": False, "left": False, "right": False}
    pairs = (("up", pygame.K_UP), ("down", pygame.K_DOWN),
             ("left", pygame.K_LEFT), ("right", pygame.K_RIGHT))
    for name, arrow in pairs:
        code = keymap.get(name, arrow)
        if (0 <= code < len(keys) and keys[code]) or (0 <= arrow < len(keys) and keys[arrow]):
            inp[name] = True
    return inp


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        # у exe нет консоли (--noconsole): отчёт пишем файлом, чтобы сборка
        # могла проверить бинарник, а не только исходники
        import selftest
        code = selftest.main()
        out = Path(os.environ.get("TEMP", ".")) / "pixelrpg_selftest_exit.txt"
        try:
            out.write_text(f"{code}\n", encoding="utf-8")
        except OSError:
            pass
        raise SystemExit(code)
    import render
    raise SystemExit(render.run())
