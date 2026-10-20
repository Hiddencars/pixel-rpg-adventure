#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quests for Pixel patch 2.0 — 50 jobs handed out by the seven peaceful NPCs.

Each quest is a plain dict: id, giver (peasant | farmer | smith | merchant |
elder | guard | healer), title, desc (one Russian sentence), kind, target,
count (goal), xp, gold, reward (item handed over, "" for none) and req (quest
ids that must be finished first).

kind picks what `target` means: kill/boss -> a monster kind from game.MOBS,
collect/deliver -> an item id from items.ITEMS, visit -> a region id from
world.World.regions, chop/mine/gather -> "tree"/"rock"/"bush", and
sell/learn/explore -> "".

Public API
    QUESTS, GIVERS, KINDS, by_id(qid), quests_for(giver),
    available(giver, finished), validate()

Run this file directly to print the whole table and the validation result.
"""

from __future__ import annotations

import re
from pathlib import Path

from items import ITEMS

# --------------------------------------------------------------------- tables
KINDS = ("kill", "boss", "collect", "deliver", "chop", "mine", "gather",
         "visit", "sell", "learn", "explore")

# the seven peaceful NPC kinds from game.spawn_npcs(), in menu order
NPC_KINDS = ("peasant", "farmer", "smith", "merchant", "elder", "guard", "healer",
             "scout", "hunter", "miner", "fisher", "pilgrim", "hermit", "nomad")

# target vocabularies for the non-entity kinds
RESOURCE_TARGETS = {"chop": {"tree"}, "mine": {"rock"}, "gather": {"bush"}}
FREE_TARGET_KINDS = ("sell", "learn", "explore")     # target must be ""

# floors the data has to clear (checked by validate())
TOTAL_QUESTS = 106
MIN_PER_GIVER = 5
MIN_MOBS = 10          # distinct monster kinds in kill/boss quests
MIN_ITEMS = 10         # distinct item ids in collect/deliver quests
MIN_REGIONS = 5        # distinct region ids in visit quests

REQUIRED_KEYS = ("id", "giver", "title", "desc", "kind", "target", "count",
                 "xp", "gold", "reward", "req")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


# ------------------------------------------------- external data (items/world)
# game.py and world.py both import pygame, so they are loaded defensively: when
# pygame is missing the ids are read straight out of the source files instead.
def _load_mob_kinds() -> set[str]:
    """Monster ids from game.py. Falls back to parsing the source, so this module
    also imports cleanly when game.py is only half-way through loading."""
    try:
        import game
        kinds = set(getattr(game, "MOBS", {}) or {})
        if kinds:
            return kinds
    except Exception:
        pass
    src = (Path(__file__).with_name("game.py")).read_text(encoding="utf-8")
    block = re.search(r"^MOBS[^=]*=\s*\{(.*?)^\}", src, re.S | re.M)
    return (set(re.findall(r'^\s{4}"([a-z_]+)":\s*\{', block.group(1), re.M))
            if block else set())


def _load_region_ids() -> set[str]:
    """Region ids from world.py — из статической константы, без генерации мира."""
    try:
        from world import REGION_IDS
        if REGION_IDS:
            return set(REGION_IDS)
    except Exception:
        pass
    src = (Path(__file__).with_name("world.py")).read_text(encoding="utf-8")
    return set(re.findall(r'"id": "([a-z_]+)"', src))


MOB_KINDS: set[str] = _load_mob_kinds()
REGION_IDS: set[str] = _load_region_ids()


# ------------------------------------------------------------------- quests
QUESTS: list[dict] = [
    # ------------------------------------------------------------- peasant
    {"id": "p_ears", "giver": "peasant", "title": "Гоблиньи уши",
     "desc": "Собери восемь ушей гоблинов на лугах — деревня платит за них монетой.",
     "kind": "collect", "target": "ear", "count": 8, "xp": 60, "gold": 20,
     "reward": "herb", "req": []},
    {"id": "p_goblin", "giver": "peasant", "title": "Гоблины у околицы",
     "desc": "Отгони стаю гоблинов от деревенских огородов, убив пятерых.",
     "kind": "kill", "target": "goblin", "count": 5, "xp": 80, "gold": 25,
     "reward": "potion", "req": []},
    {"id": "p_wood", "giver": "peasant", "title": "Дрова на зиму",
     "desc": "Сруби восемь деревьев на опушке и принеси древесину в деревню.",
     "kind": "chop", "target": "tree", "count": 8, "xp": 70, "gold": 18,
     "reward": "cloth", "req": []},
    {"id": "p_fence", "giver": "peasant", "title": "Новый частокол",
     "desc": "Заготовь пятнадцать брёвен для нового частокола вокруг Дубравы.",
     "kind": "chop", "target": "tree", "count": 15, "xp": 110, "gold": 35,
     "reward": "shield_wood", "req": ["p_wood"]},
    {"id": "p_spider", "giver": "peasant", "title": "Паутина в амбаре",
     "desc": "Выведи пять пауков из старого амбара, пока они не расплодились.",
     "kind": "kill", "target": "spider", "count": 5, "xp": 90, "gold": 30,
     "reward": "silk", "req": ["p_goblin"]},
    {"id": "p_berries", "giver": "peasant", "title": "Ягоды на опушке",
     "desc": "Обери шесть ягодных кустов, пока их не склевали птицы.",
     "kind": "gather", "target": "bush", "count": 6, "xp": 55, "gold": 16,
     "reward": "honey", "req": []},
    {"id": "p_sell", "giver": "peasant", "title": "Хлам на продажу",
     "desc": "Продай торговцу восемь ненужных трофеев и пополни казну деревни.",
     "kind": "sell", "target": "", "count": 8, "xp": 75, "gold": 45,
     "reward": "", "req": []},
    # -------------------------------------------------------------- farmer
    {"id": "f_slime", "giver": "farmer", "title": "Слизни на грядках",
     "desc": "Убей шесть слизней, что объедают капусту на восточных полях.",
     "kind": "kill", "target": "slime", "count": 6, "xp": 75, "gold": 22,
     "reward": "meat", "req": []},
    {"id": "f_boar", "giver": "farmer", "title": "Кабаны в посевах",
     "desc": "Убей четыре кабана, что вытаптывают пшеницу у мельницы.",
     "kind": "kill", "target": "boar", "count": 4, "xp": 130, "gold": 45,
     "reward": "meat", "req": []},
    {"id": "f_mill", "giver": "farmer", "title": "Жернова для мельницы",
     "desc": "Наломай шесть камней в Кряже — старые жернова совсем стёрлись.",
     "kind": "mine", "target": "rock", "count": 6, "xp": 70, "gold": 24,
     "reward": "", "req": []},
    {"id": "f_herb", "giver": "farmer", "title": "Травы для скота",
     "desc": "Собери восемь пучков травы на лугах, чтобы было чем кормить скот.",
     "kind": "gather", "target": "bush", "count": 8, "xp": 65, "gold": 20,
     "reward": "herb", "req": []},
    {"id": "f_honey", "giver": "farmer", "title": "Мёд к ярмарке",
     "desc": "Принеси четыре горшочка дикого мёда к ярмарочному столу.",
     "kind": "deliver", "target": "honey", "count": 4, "xp": 85, "gold": 28,
     "reward": "mushroom", "req": ["f_herb"]},
    {"id": "f_scarecrow", "giver": "farmer", "title": "Пугало для поля",
     "desc": "Сруби шесть деревьев — из них выйдет новое пугало на поле.",
     "kind": "chop", "target": "tree", "count": 6, "xp": 60, "gold": 18,
     "reward": "cloth", "req": []},
    {"id": "f_bear", "giver": "farmer", "title": "Медведь-пасечник",
     "desc": "Убей медведя, что разоряет пасеку и ломает ульи каждую ночь.",
     "kind": "boss", "target": "bear", "count": 1, "xp": 310, "gold": 125,
     "reward": "pelt", "req": ["f_boar"]},
    # --------------------------------------------------------------- smith
    {"id": "s_ore", "giver": "smith", "title": "Руда для горна",
     "desc": "Принеси восемь кусков железной руды — горн стоит холодным.",
     "kind": "collect", "target": "ore_iron", "count": 8, "xp": 95, "gold": 32,
     "reward": "sword_rusty", "req": []},
    {"id": "s_brute", "giver": "smith", "title": "Громилы на дороге",
     "desc": "Убей четырёх громил, что грабят обозы с рудой у подножия Кряжа.",
     "kind": "kill", "target": "brute", "count": 4, "xp": 160, "gold": 55,
     "reward": "armor_leather", "req": []},
    {"id": "s_charcoal", "giver": "smith", "title": "Уголь для горна",
     "desc": "Сруби двенадцать деревьев и пережги древесину в уголь.",
     "kind": "chop", "target": "tree", "count": 12, "xp": 85, "gold": 26,
     "reward": "axe_goblin", "req": []},
    {"id": "s_mine_iron", "giver": "smith", "title": "Железная жила",
     "desc": "Добудь десять кусков руды прямо в скалах Кряжа.",
     "kind": "mine", "target": "rock", "count": 10, "xp": 100, "gold": 30,
     "reward": "ore_iron", "req": ["s_ore"]},
    {"id": "s_mine_mithril", "giver": "smith", "title": "Мифрил в глубине",
     "desc": "Набей двадцать пять кусков редкой руды в глубокой штольне.",
     "kind": "mine", "target": "rock", "count": 25, "xp": 220, "gold": 90,
     "reward": "ore_mithril", "req": ["s_mine_iron"]},
    {"id": "s_golem", "giver": "smith", "title": "Каменный страж",
     "desc": "Разбей каменного голема, что завалил вход в штольню.",
     "kind": "boss", "target": "golem", "count": 1, "xp": 320, "gold": 130,
     "reward": "armor_iron", "req": ["s_mine_mithril"]},
    {"id": "s_weapon", "giver": "smith", "title": "Урок кузнеца",
     "desc": "Пройди обучение у кузнеца и выкуй себе настоящий клинок.",
     "kind": "learn", "target": "", "count": 1, "xp": 120, "gold": 40,
     "reward": "sword_steel", "req": ["s_brute"]},
    # ------------------------------------------------------------ merchant
    {"id": "m_silk", "giver": "merchant", "title": "Паутина для ткачей",
     "desc": "Принеси шесть мотков паутины — ткачи в Дубраве ждут товар.",
     "kind": "collect", "target": "silk", "count": 6, "xp": 100, "gold": 35,
     "reward": "mana_potion", "req": []},
    {"id": "m_pelt", "giver": "merchant", "title": "Шкуры к ярмарке",
     "desc": "Добудь пять выделанных шкур для зимней ярмарки.",
     "kind": "collect", "target": "pelt", "count": 5, "xp": 120, "gold": 40,
     "reward": "ring_gold", "req": []},
    {"id": "m_gems", "giver": "merchant", "title": "Красный камень",
     "desc": "Найди три рубина в руинах Аргоса — за них дают щедрую цену.",
     "kind": "collect", "target": "gem_ruby", "count": 3, "xp": 200, "gold": 80,
     "reward": "ring_ruby", "req": ["m_silk"]},
    {"id": "m_bat", "giver": "merchant", "title": "Мыши под крышей",
     "desc": "Избавься от шести летучих мышей, что гнездятся под крышей склада.",
     "kind": "kill", "target": "bat", "count": 6, "xp": 85, "gold": 26,
     "reward": "potion", "req": []},
    {"id": "m_shore", "giver": "merchant", "title": "Товар с берега",
     "desc": "Дойди до западного берега и разузнай, чем торгуют рыбаки.",
     "kind": "visit", "target": "shore", "count": 1, "xp": 90, "gold": 30,
     "reward": "feather", "req": []},
    {"id": "m_scroll", "giver": "merchant", "title": "Свитки чар",
     "desc": "Принеси три свитка чар — за них торговец выручит хорошие деньги.",
     "kind": "deliver", "target": "scroll", "count": 3, "xp": 150, "gold": 55,
     "reward": "staff_arcane", "req": ["m_gems"]},
    {"id": "m_sell", "giver": "merchant", "title": "Большая распродажа",
     "desc": "Продай торговцу тридцать трофеев и освободи место в сумке.",
     "kind": "sell", "target": "", "count": 30, "xp": 110, "gold": 60,
     "reward": "", "req": ["m_silk"]},
    # --------------------------------------------------------------- elder
    {"id": "e_ruins", "giver": "elder", "title": "Тропа к руинам",
     "desc": "Дойди до руин Аргоса и осмотри древние колонны.",
     "kind": "visit", "target": "ruins", "count": 1, "xp": 130, "gold": 45,
     "reward": "scroll", "req": []},
    {"id": "e_skeleton", "giver": "elder", "title": "Кости из могил",
     "desc": "Уложи шесть скелетов, что поднимаются из могил на Погосте.",
     "kind": "kill", "target": "skeleton", "count": 6, "xp": 140, "gold": 50,
     "reward": "bone", "req": ["e_ruins"]},
    {"id": "e_wraith", "giver": "elder", "title": "Плакальщица",
     "desc": "Упокой призрака-плакальщицу, что бродит между могил по ночам.",
     "kind": "boss", "target": "wraith", "count": 1, "xp": 380, "gold": 150,
     "reward": "amulet", "req": ["e_skeleton"]},
    {"id": "e_gather", "giver": "elder", "title": "Травы для обряда",
     "desc": "Собери восемь пучков травы для древнего обряда у колодца.",
     "kind": "gather", "target": "bush", "count": 8, "xp": 75, "gold": 22,
     "reward": "herb", "req": ["e_ruins"]},
    {"id": "e_firewood", "giver": "elder", "title": "Погребальный костёр",
     "desc": "Принеси пятнадцать поленьев для поминального костра на Погосте.",
     "kind": "deliver", "target": "wood", "count": 15, "xp": 95, "gold": 30,
     "reward": "", "req": []},
    {"id": "e_explore", "giver": "elder", "title": "Тайный подвал",
     "desc": "Отыщи тайный ход в подземелье под руинами и исследуй его.",
     "kind": "explore", "target": "", "count": 1, "xp": 200, "gold": 70,
     "reward": "key", "req": ["e_ruins"]},
    {"id": "e_lore", "giver": "elder", "title": "Сказания древних",
     "desc": "Выслушай и запиши сказания старейшины о короне Дубравы.",
     "kind": "learn", "target": "", "count": 1, "xp": 180, "gold": 65,
     "reward": "crown_shard", "req": ["e_explore"]},
    # --------------------------------------------------------------- guard
    {"id": "g_wolf", "giver": "guard", "title": "Волки на тракте",
     "desc": "Отгони волчью стаю от тракта, убив четырёх волков.",
     "kind": "kill", "target": "wolf", "count": 4, "xp": 90, "gold": 30,
     "reward": "potion", "req": []},
    {"id": "g_bandit", "giver": "guard", "title": "Разбойники на дороге",
     "desc": "Очисти южный тракт от пятерых разбойников из лагеря.",
     "kind": "kill", "target": "bandit", "count": 5, "xp": 150, "gold": 55,
     "reward": "dagger_shadow", "req": ["g_wolf"]},
    {"id": "g_camp", "giver": "guard", "title": "Вылазка в логово",
     "desc": "Проберись к лагерю разбойников и разведай их силы.",
     "kind": "visit", "target": "camp", "count": 1, "xp": 120, "gold": 40,
     "reward": "key", "req": ["g_bandit"]},
    {"id": "g_orc", "giver": "guard", "title": "Вождь орков",
     "desc": "Сразись с вождём орков в горном проходе Кряжа.",
     "kind": "boss", "target": "orc", "count": 1, "xp": 450, "gold": 190,
     "reward": "axe_steel", "req": ["g_camp"]},
    {"id": "g_mine", "giver": "guard", "title": "Камень для стены",
     "desc": "Набей пятнадцать камней для новой стены у южных ворот.",
     "kind": "mine", "target": "rock", "count": 15, "xp": 110, "gold": 35,
     "reward": "shield_iron", "req": []},
    {"id": "g_highlands", "giver": "guard", "title": "Дозор в Кряже",
     "desc": "Поднимись в Кряж и осмотри перевал, не идут ли оттуда орки.",
     "kind": "visit", "target": "highlands", "count": 1, "xp": 140, "gold": 45,
     "reward": "armor_steel", "req": ["g_camp"]},
    {"id": "g_sell", "giver": "guard", "title": "Добыча для казны",
     "desc": "Продай пятнадцать трофеев — выручка пойдёт на жалованье страже.",
     "kind": "sell", "target": "", "count": 15, "xp": 120, "gold": 65,
     "reward": "", "req": ["g_bandit"]},
    # -------------------------------------------------------------- healer
    {"id": "h_herb", "giver": "healer", "title": "Целебная трава",
     "desc": "Собери десять пучков целебной травы для больных деревни.",
     "kind": "collect", "target": "herb", "count": 10, "xp": 85, "gold": 26,
     "reward": "potion", "req": []},
    {"id": "h_bone", "giver": "healer", "title": "Кости для отвара",
     "desc": "Принеси десять костей — из них варят укрепляющий отвар.",
     "kind": "collect", "target": "bone", "count": 10, "xp": 80, "gold": 24,
     "reward": "antidote", "req": []},
    {"id": "h_snake", "giver": "healer", "title": "Змеи в топях",
     "desc": "Убей пять болотных змей, что кусают детей у воды.",
     "kind": "kill", "target": "snake", "count": 5, "xp": 120, "gold": 40,
     "reward": "antidote", "req": []},
    {"id": "h_mushroom", "giver": "healer", "title": "Грибы для настоя",
     "desc": "Принеси восемь лесных грибов для лечебного настоя.",
     "kind": "deliver", "target": "mushroom", "count": 8, "xp": 95, "gold": 30,
     "reward": "potion_big", "req": ["h_herb"]},
    {"id": "h_swamp", "giver": "healer", "title": "Корешки из топи",
     "desc": "Дойди до Гнилой топи и найди там редкие болотные корешки.",
     "kind": "visit", "target": "swamp", "count": 1, "xp": 100, "gold": 32,
     "reward": "venom", "req": []},
    {"id": "h_roots", "giver": "healer", "title": "Кусты у ручья",
     "desc": "Обери пять кустов у ручья — их корни годятся для припарок.",
     "kind": "gather", "target": "bush", "count": 5, "xp": 70, "gold": 20,
     "reward": "herb", "req": []},
    {"id": "h_elixir", "giver": "healer", "title": "Уроки знахарки",
     "desc": "Выучись у знахарки варить эликсир силы из редких трав.",
     "kind": "learn", "target": "", "count": 1, "xp": 260, "gold": 90,
     "reward": "elixir", "req": ["h_mushroom"]},
    {"id": "h_explore", "giver": "healer", "title": "Дым над Погостом",
     "desc": "Исследуй Погост и выясни, отчего там стонут по ночам.",
     "kind": "explore", "target": "", "count": 1, "xp": 180, "gold": 60,
     "reward": "mana_potion", "req": ["h_swamp"]},

    # ==================================================== разведчик (стоянки)
    {"id": "s_borders", "giver": "scout", "title": "Границы Кряжа",
     "desc": "Пройди кряж с севера на юг и вернись живым — мне нужны свежие вести.",
     "kind": "visit", "target": "highlands", "count": 1, "xp": 90, "gold": 30,
     "reward": "potion", "req": []},
    {"id": "s_orcs", "giver": "scout", "title": "Орки у перевала",
     "desc": "Сними шесть орков с перевала, пока они не спустились к дороге.",
     "kind": "kill", "target": "orc", "count": 6, "xp": 110, "gold": 40,
     "reward": "armor_iron", "req": []},
    {"id": "s_towers", "giver": "scout", "title": "Все дозорные точки",
     "desc": "Обоиди все области острова и запомни дороги — карта у меня старая.",
     "kind": "explore", "target": "", "count": 1, "xp": 200, "gold": 80,
     "reward": "scroll", "req": ["s_borders"]},
    {"id": "s_ruins", "giver": "scout", "title": "Тропа в руины",
     "desc": "Дойди до руин Аргоса и посмотри, что там шевелится.",
     "kind": "visit", "target": "ruins", "count": 1, "xp": 100, "gold": 35,
     "reward": "herb", "req": []},
    {"id": "s_undead", "giver": "scout", "title": "Костяные патрули",
     "desc": "Скелеты ходят строем — значит, кто-то ими командует. Уложи восьмерых.",
     "kind": "kill", "target": "skeleton", "count": 8, "xp": 130, "gold": 45,
     "reward": "armor_steel", "req": ["s_ruins"]},
    {"id": "sc_golem", "giver": "scout", "title": "Голем на перевале",
     "desc": "Каменный голем перекрыл единственный проход. Убери его.",
     "kind": "boss", "target": "golem", "count": 1, "xp": 160, "gold": 60,
     "reward": "shield_iron", "req": ["s_orcs"]},
    {"id": "s_swamp", "giver": "scout", "title": "Тропа через топь",
     "desc": "Разведай гнилую топь: где твёрдо, где провал. Мне нужен безопасный путь.",
     "kind": "visit", "target": "swamp", "count": 1, "xp": 95, "gold": 32,
     "reward": "antidote", "req": []},
    {"id": "s_report", "giver": "scout", "title": "Донесение в Дубраву",
     "desc": "Отнеси моё донесение в деревню — свиток с печатью, не потеряй.",
     "kind": "deliver", "target": "scroll", "count": 1, "xp": 85, "gold": 28,
     "reward": "potion", "req": ["s_borders"]},

    # ===================================================== охотник (стоянки)
    {"id": "hu_wolves", "giver": "hunter", "title": "Волчья тропа",
     "desc": "Семь волков идут за стадом. Прореди стаю, пока она не поредела сама.",
     "kind": "kill", "target": "wolf", "count": 7, "xp": 105, "gold": 38,
     "reward": "meat", "req": []},
    {"id": "hu_pelts", "giver": "hunter", "title": "Шкуры на продажу",
     "desc": "Шесть целых шкур — и я заплачу как за хороший день.",
     "kind": "collect", "target": "pelt", "count": 6, "xp": 95, "gold": 34,
     "reward": "cloth", "req": []},
    {"id": "hu_bear", "giver": "hunter", "title": "Медведь-шатун",
     "desc": "Медведь не залёг на зиму и рвёт всё подряд. Это уже не охота, а долг.",
     "kind": "boss", "target": "bear", "count": 1, "xp": 150, "gold": 55,
     "reward": "armor_leather", "req": ["hu_wolves"]},
    {"id": "hu_tusk", "giver": "hunter", "title": "Кабаньи клыки",
     "desc": "Восемь клыков — из них выйдут рукояти получше стальных.",
     "kind": "collect", "target": "tusk", "count": 8, "xp": 100, "gold": 36,
     "reward": "dagger_shadow", "req": []},
    {"id": "hu_feathers", "giver": "hunter", "title": "Пёрышки",
     "desc": "Десять перьев для стрел. Птицы тут пуганые, но ты справишься.",
     "kind": "collect", "target": "feather", "count": 10, "xp": 90, "gold": 30,
     "reward": "potion", "req": []},
    {"id": "hu_meat", "giver": "hunter", "title": "Мясо для лагеря",
     "desc": "Восемь кусков мяса — зима близко, а у нас пустой ледник.",
     "kind": "collect", "target": "meat", "count": 8, "xp": 95, "gold": 33,
     "reward": "potion_big", "req": ["hu_tusk"]},
    {"id": "hu_forest", "giver": "hunter", "title": "Глухой бор",
     "desc": "Дойди до самой чащи и посмотри, где зверь уходит на водопой.",
     "kind": "visit", "target": "forest", "count": 1, "xp": 85, "gold": 28,
     "reward": "herb", "req": []},
    {"id": "hu_traps", "giver": "hunter", "title": "Силы на силки",
     "desc": "Десять деревьев на жерди и силки — лес большой, материала нужно много.",
     "kind": "chop", "target": "tree", "count": 10, "xp": 90, "gold": 30,
     "reward": "wood", "req": []},

    # ===================================================== рудокоп (стоянки)
    {"id": "mi_ore", "giver": "miner", "title": "Железная жила",
     "desc": "Двенадцать камней из забоя — жила пошла хорошая, но рук не хватает.",
     "kind": "mine", "target": "rock", "count": 12, "xp": 105, "gold": 36,
     "reward": "ore_iron", "req": []},
    {"id": "mi_iron", "giver": "miner", "title": "Руда на плавку",
     "desc": "Восемь кусков железной руды: печь уже разогрета.",
     "kind": "collect", "target": "ore_iron", "count": 8, "xp": 110, "gold": 40,
     "reward": "armor_iron", "req": ["mi_ore"]},
    {"id": "mi_golem", "giver": "miner", "title": "Голем в забое",
     "desc": "Три голема поднялись из породы. Пока они там, шахта стоит.",
     "kind": "kill", "target": "golem", "count": 3, "xp": 150, "gold": 55,
     "reward": "shield_iron", "req": []},
    {"id": "mi_gems", "giver": "miner", "title": "Самоцветы",
     "desc": "Два рубина из глубинных жил — такие попадаются раз в месяц.",
     "kind": "collect", "target": "gem_ruby", "count": 2, "xp": 140, "gold": 60,
     "reward": "ring_ruby", "req": ["mi_iron"]},
    {"id": "mi_mithril", "giver": "miner", "title": "Мифрил",
     "desc": "Три куска мифрила. Не спрашивай, зачем — просто найди.",
     "kind": "collect", "target": "ore_mithril", "count": 3, "xp": 190, "gold": 80,
     "reward": "sword_steel", "req": ["mi_gems"]},
    {"id": "mi_bats", "giver": "miner", "title": "Заваленный забой",
     "desc": "Летучие мыши облюбовали верхний ярус. Десять — и можно работать.",
     "kind": "kill", "target": "bat", "count": 10, "xp": 95, "gold": 32,
     "reward": "potion", "req": []},
    {"id": "mi_stone", "giver": "miner", "title": "Камень для кладки",
     "desc": "Двенадцать камней для крепи — без крепи забой осыпается.",
     "kind": "collect", "target": "stone", "count": 12, "xp": 100, "gold": 34,
     "reward": "wood", "req": []},
    {"id": "mi_deep", "giver": "miner", "title": "Глубина",
     "desc": "Двадцать камней с нижнего яруса. Там темно, но жила того стоит.",
     "kind": "mine", "target": "rock", "count": 20, "xp": 130, "gold": 48,
     "reward": "elixir", "req": ["mi_ore"]},

    # ====================================================== рыбак (стоянки)
    {"id": "fi_herbs", "giver": "fisher", "title": "Приманка",
     "desc": "Восемь кустов травы на приманку — без неё тут ничего не клюёт.",
     "kind": "gather", "target": "bush", "count": 8, "xp": 85, "gold": 28,
     "reward": "herb", "req": []},
    {"id": "fi_slime", "giver": "fisher", "title": "Слизни у воды",
     "desc": "Слизни облепили сети. Восемь штук — и я снова смогу ловить.",
     "kind": "kill", "target": "slime", "count": 8, "xp": 90, "gold": 30,
     "reward": "antidote", "req": []},
    {"id": "fi_floats", "giver": "fisher", "title": "Поплавки",
     "desc": "Шесть кусков дерева на поплавки — без них сети идут ко дну.",
     "kind": "collect", "target": "wood", "count": 6, "xp": 80, "gold": 26,
     "reward": "cloth", "req": []},
    {"id": "fi_snake", "giver": "fisher", "title": "Змеи в камышах",
     "desc": "Шесть змей в камышах — я туда больше не сунусь.",
     "kind": "kill", "target": "snake", "count": 6, "xp": 95, "gold": 32,
     "reward": "antidote", "req": ["fi_slime"]},
    {"id": "fi_shore", "giver": "fisher", "title": "Дальний берег",
     "desc": "Пройди вдоль берега до дальнего мыса и посмотри, где лучше ловить.",
     "kind": "visit", "target": "shore", "count": 1, "xp": 90, "gold": 30,
     "reward": "potion", "req": []},
    {"id": "fi_net", "giver": "fisher", "title": "Сеть порвалась",
     "desc": "Пять мотков паутины на починку — своей уже не осталось.",
     "kind": "collect", "target": "silk", "count": 5, "xp": 95, "gold": 34,
     "reward": "potion", "req": []},
    {"id": "fi_salt", "giver": "fisher", "title": "Соль и травы",
     "desc": "Десять пучков травы: солить улов нечем, а без травы он не держится.",
     "kind": "collect", "target": "herb", "count": 10, "xp": 100, "gold": 36,
     "reward": "honey", "req": ["fi_herbs"]},
    {"id": "fi_big", "giver": "fisher", "title": "Кто-то в омуте",
     "desc": "Что-то крупное живёт в омуте и рвёт сети. Тролль, не иначе.",
     "kind": "boss", "target": "troll", "count": 1, "xp": 160, "gold": 58,
     "reward": "potion_big", "req": ["fi_snake"]},

    # =================================================== паломник (стоянки)
    {"id": "pi_shrines", "giver": "pilgrim", "title": "Три святилища",
     "desc": "Дойди до лугов: там, говорят, стоит алтарь, который помнит старое.",
     "kind": "visit", "target": "meadow", "count": 1, "xp": 85, "gold": 28,
     "reward": "herb", "req": []},
    {"id": "pi_herbs", "giver": "pilgrim", "title": "Благовония",
     "desc": "Двенадцать пучков травы для благовоний — дым должен быть густым.",
     "kind": "collect", "target": "herb", "count": 12, "xp": 110, "gold": 38,
     "reward": "elixir", "req": []},
    {"id": "pi_light", "giver": "pilgrim", "title": "Огонь не гаснет",
     "desc": "Десять поленьев: чаша святилища не должна погаснуть ночью.",
     "kind": "collect", "target": "wood", "count": 10, "xp": 95, "gold": 32,
     "reward": "potion", "req": ["pi_shrines"]},
    {"id": "pi_graves", "giver": "pilgrim", "title": "Поминание",
     "desc": "Дойди до погоста и поклонись тем, кто ушёл раньше нас.",
     "kind": "visit", "target": "graveyard", "count": 1, "xp": 90, "gold": 30,
     "reward": "scroll", "req": []},
    {"id": "pi_learn", "giver": "pilgrim", "title": "Путь мудрости",
     "desc": "Изучи хоть одно умение на дубе — сила без понимания только губит.",
     "kind": "learn", "target": "", "count": 1, "xp": 120, "gold": 40,
     "reward": "staff_arcane", "req": []},
    {"id": "pi_flowers", "giver": "pilgrim", "title": "Цветы на алтарь",
     "desc": "Восемь цветов: у алтаря всегда должно быть свежее подношение.",
     "kind": "collect", "target": "flower", "count": 8, "xp": 90, "gold": 30,
     "reward": "honey", "req": []},
    {"id": "pi_wraith", "giver": "pilgrim", "title": "Тени у алтаря",
     "desc": "Пять призраков кружат у святилища и не дают молиться. Разгони их.",
     "kind": "kill", "target": "wraith", "count": 5, "xp": 130, "gold": 45,
     "reward": "amulet", "req": ["pi_graves"]},
    {"id": "pi_road", "giver": "pilgrim", "title": "Дорога к Кряжу",
     "desc": "Поднимись к кряжу: там, на высоте, ближе всего к небу.",
     "kind": "visit", "target": "highlands", "count": 1, "xp": 105, "gold": 35,
     "reward": "potion_big", "req": ["pi_learn"]},

    # =================================================== отшельник (стоянки)
    {"id": "he_bones", "giver": "hermit", "title": "Кости",
     "desc": "Десять костей: по ним я читаю, кто здесь ходил до тебя.",
     "kind": "collect", "target": "bone", "count": 10, "xp": 100, "gold": 34,
     "reward": "scroll", "req": []},
    {"id": "he_skulls", "giver": "hermit", "title": "Черепа",
     "desc": "Пять черепов — у каждого своя история, и мне она нужна.",
     "kind": "collect", "target": "skull", "count": 5, "xp": 115, "gold": 40,
     "reward": "amulet", "req": ["he_bones"]},
    {"id": "he_wraiths", "giver": "hermit", "title": "Тишина",
     "desc": "Шесть призраков нарушают мой покой. Сделай так, чтобы стало тихо.",
     "kind": "kill", "target": "wraith", "count": 6, "xp": 140, "gold": 48,
     "reward": "staff_arcane", "req": []},
    {"id": "he_graveyard", "giver": "hermit", "title": "Старый погост",
     "desc": "Дойди до погоста. Скажи им, что я ещё помню их имена.",
     "kind": "visit", "target": "graveyard", "count": 1, "xp": 90, "gold": 30,
     "reward": "herb", "req": []},
    {"id": "he_souls", "giver": "hermit", "title": "Души",
     "desc": "Четыре души в сосудах — не для зла, а чтобы понять, что их держит.",
     "kind": "collect", "target": "soul", "count": 4, "xp": 160, "gold": 55,
     "reward": "amulet", "req": ["he_skulls"]},
    {"id": "he_skeletons", "giver": "hermit", "title": "Скелеты поднялись",
     "desc": "Десять скелетов встали из земли. Это плохой знак, но их надо уложить.",
     "kind": "kill", "target": "skeleton", "count": 10, "xp": 145, "gold": 50,
     "reward": "armor_mage", "req": ["he_graveyard"]},
    {"id": "he_mushrooms", "giver": "hermit", "title": "Грибы на ужин",
     "desc": "Шесть кустов — грибы и ягоды. Я не ем мяса, если ты не заметил.",
     "kind": "gather", "target": "bush", "count": 6, "xp": 85, "gold": 28,
     "reward": "mushroom", "req": []},
    {"id": "he_quiet", "giver": "hermit", "title": "Ни звука",
     "desc": "Восемь бесов визжат по ночам. Убери их — и я наконец посплю.",
     "kind": "kill", "target": "imp", "count": 8, "xp": 125, "gold": 42,
     "reward": "potion_big", "req": []},

    # ==================================================== кочевник (стоянки)
    {"id": "no_sell", "giver": "nomad", "title": "Товар в путь",
     "desc": "Продай десять трофеев: каравану нужно золото, а не барахло.",
     "kind": "sell", "target": "", "count": 10, "xp": 95, "gold": 40,
     "reward": "potion", "req": []},
    {"id": "no_bandits", "giver": "nomad", "title": "Разбойники на дороге",
     "desc": "Семь разбойников держат дорогу. Караван не пройдёт, пока они там.",
     "kind": "kill", "target": "bandit", "count": 7, "xp": 115, "gold": 42,
     "reward": "sword_iron", "req": []},
    {"id": "no_deliver", "giver": "nomad", "title": "Посылка",
     "desc": "Три отреза ткани — заказ для табора, что стоит на другом конце острова.",
     "kind": "deliver", "target": "cloth", "count": 3, "xp": 90, "gold": 32,
     "reward": "ring_gold", "req": []},
    {"id": "no_explore", "giver": "nomad", "title": "Дорога кочевья",
     "desc": "Обоиди весь остров: кочевью нужны новые тропы, а не старые.",
     "kind": "explore", "target": "", "count": 1, "xp": 180, "gold": 70,
     "reward": "elixir", "req": ["no_deliver"]},
    {"id": "no_gold", "giver": "nomad", "title": "Долг табора",
     "desc": "Два изумруда — табор задолжал кузнецу, а платить нечем.",
     "kind": "collect", "target": "gem_emerald", "count": 2, "xp": 150, "gold": 60,
     "reward": "ring_sapphire", "req": []},
    {"id": "no_brute", "giver": "nomad", "title": "Здоровяки",
     "desc": "Пять гоблинов-здоровяков разнесли стоянку. Найди и ответь.",
     "kind": "kill", "target": "brute", "count": 5, "xp": 125, "gold": 45,
     "reward": "axe_steel", "req": ["no_bandits"]},
    {"id": "no_map", "giver": "nomad", "title": "Дальние земли",
     "desc": "Дойди до логова разбойников и посмотри, можно ли там встать табором.",
     "kind": "visit", "target": "camp", "count": 1, "xp": 100, "gold": 34,
     "reward": "potion", "req": []},
    {"id": "no_caravan", "giver": "nomad", "title": "Караван",
     "desc": "Двенадцать разбойников собрались в ватагу. Пока они вместе — дорога мертва.",
     "kind": "kill", "target": "bandit", "count": 12, "xp": 170, "gold": 65,
     "reward": "armor_steel", "req": ["no_bandits"]},
]

# npc kind -> ordered list of quest ids he offers (same order as QUESTS)
GIVERS: dict[str, list[str]] = {kind: [q["id"] for q in QUESTS if q["giver"] == kind]
                                for kind in NPC_KINDS}

_BY_ID: dict[str, dict] = {q["id"]: q for q in QUESTS}


# ------------------------------------------------------------------- lookups
def by_id(qid: str) -> dict | None:
    """The quest dict with this id, or None."""
    return _BY_ID.get(qid)


def quests_for(giver: str) -> list[dict]:
    """Every quest this npc kind offers, in menu order."""
    return [q for q in QUESTS if q["giver"] == giver]


def available(giver: str, finished: set[str]) -> list[dict]:
    """Quests from `giver` whose reqs are met and which are not finished yet."""
    done = set(finished)
    return [q for q in quests_for(giver)
            if q["id"] not in done and all(r in done for r in q["req"])]


# ---------------------------------------------------------------- validation
def _find_cycle() -> list[str] | None:
    """Return one cyclic req chain, or None when the graph is acyclic."""
    state: dict[str, int] = {}          # 0 = on stack, 1 = done
    for start in _BY_ID:
        stack = [(start, iter(_BY_ID[start]["req"]))]
        state[start] = 0
        path = [start]
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if child not in _BY_ID:
                    continue
                if state.get(child) == 0:
                    return path[path.index(child):] + [child]
                if state.get(child) is None:
                    state[child] = 0
                    stack.append((child, iter(_BY_ID[child]["req"])))
                    path.append(child)
                    advanced = True
                    break
            if not advanced:
                state[node] = 1
                stack.pop()
                path.pop()
    return None


def validate() -> list[str]:
    """Every inconsistency in the quest data, as a list of messages."""
    problems: list[str] = []
    if len(QUESTS) != TOTAL_QUESTS:
        problems.append(f"{len(QUESTS)} quests defined, expected {TOTAL_QUESTS}")

    seen_ids: set[str] = set()
    seen_titles: set[tuple[str, str]] = set()
    seen_desc: dict[str, str] = {}
    used_kinds: set[str] = set()
    used_mobs: set[str] = set()
    used_items: set[str] = set()
    used_regions: set[str] = set()

    for q in QUESTS:
        qid = q.get("id", "?")
        missing = [k for k in REQUIRED_KEYS if k not in q]
        extra = [k for k in q if k not in REQUIRED_KEYS]
        if missing or extra:
            problems.append(f"{qid}: keys missing {missing}, unexpected {extra}")
        if missing:
            continue

        if not _ID_RE.match(qid):
            problems.append(f"{qid}: id is not ascii snake_case")
        if qid in seen_ids:
            problems.append(f"{qid}: duplicate quest id")
        seen_ids.add(qid)

        if q["giver"] not in NPC_KINDS:
            problems.append(f"{qid}: unknown giver {q['giver']!r}")
        if q["kind"] not in KINDS:
            problems.append(f"{qid}: unknown kind {q['kind']!r}")
            continue
        used_kinds.add(q["kind"])

        key = (q["giver"], q["title"])
        if key in seen_titles:
            problems.append(f"{qid}: duplicate (giver, title) {key}")
        seen_titles.add(key)
        if not str(q["title"]).strip():
            problems.append(f"{qid}: empty title")
        if not str(q["desc"]).strip():
            problems.append(f"{qid}: empty desc")
        if q["desc"] in seen_desc:
            problems.append(f"{qid}: desc repeats {seen_desc[q['desc']]} verbatim")
        else:
            seen_desc[q["desc"]] = qid

        # target depends on the kind
        kind, target = q["kind"], q["target"]
        if kind in ("kill", "boss"):
            if target not in MOB_KINDS:
                problems.append(f"{qid}: unknown monster kind {target!r}")
            else:
                used_mobs.add(target)
        elif kind in ("collect", "deliver"):
            if target not in ITEMS:
                problems.append(f"{qid}: unknown item id {target!r}")
            else:
                used_items.add(target)
        elif kind == "visit":
            if target not in REGION_IDS:
                problems.append(f"{qid}: unknown region id {target!r}")
            else:
                used_regions.add(target)
        elif kind in RESOURCE_TARGETS:
            if target not in RESOURCE_TARGETS[kind]:
                problems.append(f"{qid}: {kind} target must be one of "
                                f"{sorted(RESOURCE_TARGETS[kind])}, got {target!r}")
        elif kind in FREE_TARGET_KINDS and target != "":
            problems.append(f"{qid}: {kind} target must be \"\", got {target!r}")

        if not isinstance(q["count"], int) or q["count"] <= 0:
            problems.append(f"{qid}: count {q['count']!r} is not a positive int")
        for field in ("xp", "gold"):
            if not isinstance(q[field], int) or q[field] < 0:
                problems.append(f"{qid}: {field} {q[field]!r} is not a non-negative int")
        if q["reward"] and q["reward"] not in ITEMS:
            problems.append(f"{qid}: unknown reward item {q['reward']!r}")

        if not isinstance(q["req"], list):
            problems.append(f"{qid}: req is not a list")
            continue
        for r in q["req"]:
            if r not in _BY_ID:
                problems.append(f"{qid}: req points at unknown quest {r!r}")
            elif r == qid:
                problems.append(f"{qid}: requires itself")

    cycle = _find_cycle()
    if cycle:
        problems.append("cyclic req chain: " + " -> ".join(cycle))

    # giver tables
    for kind in NPC_KINDS:
        offered = GIVERS.get(kind, [])
        if len(offered) < MIN_PER_GIVER:
            problems.append(f"giver {kind} offers only {len(offered)} quests "
                            f"(need {MIN_PER_GIVER})")
        if len(set(offered)) != len(offered):
            problems.append(f"giver {kind} lists a quest twice")
        for qid in offered:
            q = _BY_ID.get(qid)
            if q is None:
                problems.append(f"giver {kind} offers unknown quest {qid!r}")
            elif q["giver"] != kind:
                problems.append(f"giver {kind} offers {qid} which belongs to {q['giver']}")
    listed = {qid for ids in GIVERS.values() for qid in ids}
    for q in QUESTS:
        if q["id"] not in listed:
            problems.append(f"{q['id']}: not listed in GIVERS")

    # kinds and coverage floors
    for kind in KINDS:
        if kind not in used_kinds:
            problems.append(f"quest kind never used: {kind}")
    for label, used, universe, floor in (
            ("monster kinds", used_mobs, MOB_KINDS, MIN_MOBS),
            ("item ids", used_items, set(ITEMS), MIN_ITEMS),
            ("region ids", used_regions, REGION_IDS, MIN_REGIONS)):
        if len(used) < floor:
            missing = sorted(universe - used)
            problems.append(f"only {len(used)} distinct {label} used "
                            f"(need {floor}); never used: {missing[:6]}")
    return problems


# ------------------------------------------------------------------- report
def _chains() -> list[tuple[int, list[str]]]:
    """Every quest with the longest req chain ending at it, longest first."""
    depth: dict[str, int] = {}
    path: dict[str, list[str]] = {}

    def walk(qid: str) -> tuple[int, list[str]]:
        if qid in depth:
            return depth[qid], path[qid]
        best = (0, [])
        for r in _BY_ID[qid]["req"]:
            if r in _BY_ID:
                d, p = walk(r)
                if d > best[0]:
                    best = (d, p)
        depth[qid] = best[0] + 1
        path[qid] = best[1] + [qid]
        return depth[qid], path[qid]

    for qid in _BY_ID:
        walk(qid)
    return sorted(((depth[q], path[q]) for q in depth), key=lambda t: -t[0])


if __name__ == "__main__":
    print(f"quests: {len(QUESTS)}")
    print(f"monster kinds known: {len(MOB_KINDS)} | items known: {len(ITEMS)} "
          f"| regions known: {len(REGION_IDS)}")
    print("\nper kind:")
    for kind in KINDS:
        print(f"  {kind:<8} {sum(1 for q in QUESTS if q['kind'] == kind)}")
    print("\nper giver:")
    for kind in NPC_KINDS:
        print(f"  {kind:<9} {len(GIVERS[kind]):>2}  {', '.join(GIVERS[kind])}")
    print("\n5 longest req chains:")
    for d, p in _chains()[:5]:
        print(f"  depth {d}: {' -> '.join(p)}")
    problems = validate()
    print(f"\nvalidate(): {len(problems)} problems")
    for p in problems:
        print("  -", p)
    print("QUESTS OK" if not problems else "QUESTS FAILED")
