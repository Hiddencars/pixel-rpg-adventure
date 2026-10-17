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
NPC_KINDS = ("peasant", "farmer", "smith", "merchant", "elder", "guard", "healer")

# target vocabularies for the non-entity kinds
RESOURCE_TARGETS = {"chop": {"tree"}, "mine": {"rock"}, "gather": {"bush"}}
FREE_TARGET_KINDS = ("sell", "learn", "explore")     # target must be ""

# floors the data has to clear (checked by validate())
TOTAL_QUESTS = 50
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
    """Region ids from world.py, with the same fallback."""
    try:
        import world
        ids = {r["id"] for r in world.World(seed=2026).regions}
        if ids:
            return ids
    except Exception:
        pass
    src = (Path(__file__).with_name("world.py")).read_text(encoding="utf-8")
    return set(re.findall(r'\{"id": "([a-z_]+)",\s*"name"', src))


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
