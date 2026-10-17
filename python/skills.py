#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The skill tree of Pixel RPG — 120 nodes growing on one great oak.

Five limbs (branches) of the oak, eight tiers each, three nodes per tier:
    8 tiers x 3 nodes x 5 branches = 120 skills  (+ the trunk root "Искра")

Node positions are laid out along the limbs in normalised [0, 1] canvas
coordinates so the renderer can simply scale them to the panel.

Effects are split in two kinds:
    kind="passive"  -> {"key": <stat>, "value": <number>}   summed into stats
    kind="active"   -> {"key": <ability id>}                put on the hotbar

Public API
    BRANCHES, ROOT, SKILLS
    by_id(sid), children_of(sid), branch_skills(bid)
    position_of(skill) -> (x, y) normalised
    requirements_met(learned: set[str], skill) -> bool
    effect_totals(learned: set[str]) -> dict[str, float]
    active_abilities(learned: set[str]) -> list[str]
    validate() -> list[str]
"""

from __future__ import annotations

import math

# --------------------------------------------------------------- branches
BRANCHES = [
    {"id": "blade", "name": "Клинок", "color": (226, 96, 84), "angle": -45,
     "desc": "Сила оружия: урон, критические удары, размашистые атаки."},
    {"id": "guard", "name": "Оплот", "color": (150, 178, 226), "angle": -22.5,
     "desc": "Стойкость: броня, здоровье, отражение урона, блок."},
    {"id": "arcane", "name": "Чары", "color": (176, 140, 236), "angle": 0,
     "desc": "Магия: огонь, лёд, мана и заклинания по площади."},
    {"id": "wild", "name": "Чаща", "color": (128, 200, 122), "angle": 22.5,
     "desc": "Охота: скорость, ловкость, яды и звери-союзники."},
    {"id": "life", "name": "Исток", "color": (238, 196, 110), "angle": 45,
     "desc": "Жизнь: лечение, регенерация, золото и удача в добыче."},
]

ROOT = {
    "id": "root", "name": "Искра", "branch": "root", "tier": 0, "lane": 1,
    "cost": 0, "req": [], "kind": "passive",
    "effect": {"key": "hp_max", "value": 5},
    "desc": "Начало пути: +5 к здоровью.", "icon": "soul",
}

# tier tables: (name, kind, key, value, description) x 3 lanes x 8 tiers
_TIERS: dict[str, list[list[tuple]]] = {
    "blade": [
        [("Заточенный клинок", "passive", "atk_flat", 1, "Урон оружием +1."),
         ("Хватка", "passive", "atk_speed", 5, "Скорость атаки +5%."),
         ("Замах", "passive", "aoe_radius", 4, "Радиус удара +4%.")],
        [("Сильный удар", "passive", "atk_flat", 2, "Урон оружием +2."),
         ("Точность", "passive", "crit_chance", 3, "Шанс крита +3%."),
         ("Размашистый удар", "active", "whirlwind", 0, "Круговая атака по всем врагам рядом.")],
        [("Кованая сталь", "passive", "atk_flat", 3, "Урон оружием +3."),
         ("Жестокость", "passive", "crit_mult", 15, "Критический урон +15%."),
         ("Пронзание", "passive", "armor_pen", 2, "Пробитие брони +2.")],
        [("Мастер клинка", "passive", "atk_pct", 8, "Весь урон +8%."),
         ("Двойной разрез", "passive", "atk_speed", 8, "Скорость атаки +8%."),
         ("Мощный удар", "active", "power_strike", 0, "Удар с тройным уроном по одной цели.")],
        [("Остриё бури", "passive", "atk_pct", 10, "Весь урон +10%."),
         ("Кровавый след", "passive", "lifesteal", 5, "5% нанесённого урона возвращается как здоровье."),
         ("Отбрасывание", "passive", "knockback", 20, "Удары сильнее отбрасывают врагов.")],
        [("Танец стали", "passive", "atk_speed", 12, "Скорость атаки +12%."),
         ("Смертельный удар", "passive", "crit_chance", 8, "Шанс крита +8%."),
         ("Карусель", "active", "blade_storm", 0, "Вихрь стали: несколько атак по кругу.")],
        [("Ярость берсерка", "passive", "atk_pct", 14, "Весь урон +14%."),
         ("Палач", "passive", "crit_mult", 30, "Критический урон +30%."),
         ("Казнь", "active", "execute", 0, "Добивает раненого врага: урон растёт, когда у него мало здоровья.")],
        [("Легенда клинка", "passive", "atk_pct", 20, "Весь урон +20%."),
         ("Абсолютная точность", "passive", "crit_chance", 12, "Шанс крита +12%."),
         ("Рассечение мира", "active", "world_cleave", 0, "Мощнейший удар по всем врагам на экране.")],
    ],
    "guard": [
        [("Плотная кожа", "passive", "def_flat", 1, "Защита +1."),
         ("Выносливость", "passive", "hp_max", 8, "Здоровье +8."),
         ("Стойка", "passive", "dodge", 2, "Шанс уклонения +2%.")],
        [("Дубовый щит", "passive", "def_flat", 2, "Защита +2."),
         ("Каменная кожа", "passive", "hp_max", 12, "Здоровье +12."),
         ("Блок", "active", "shield_block", 0, "Поднять щит: урон снижается на 60% на 4 секунды.")],
        [("Кольчуга", "passive", "def_flat", 3, "Защита +3."),
         ("Толстая шкура", "passive", "def_pct", 8, "Защита +8%."),
         ("Шипы", "passive", "thorns", 3, "Отражает 3 урона атакующему.")],
        [("Стальной панцирь", "passive", "def_pct", 12, "Защита +12%."),
         ("Живучесть", "passive", "hp_max", 20, "Здоровье +20."),
         ("Таран", "active", "shield_bash", 0, "Удар щитом: отбрасывает и оглушает врага.")],
        [("Бастион", "passive", "def_flat", 5, "Защита +5."),
         ("Второе дыхание", "passive", "regen", 1, "Восстановление 1 HP в секунду."),
         ("Провокация", "active", "taunt", 0, "Все враги рядом переключаются на тебя и теряют боевой дух.")],
        [("Непробиваемый", "passive", "def_pct", 18, "Защита +18%."),
         ("Исполинское здоровье", "passive", "hp_max", 30, "Здоровье +30."),
         ("Каменная кожа", "active", "stoneskin", 0, "Кожа твердеет: защита удваивается на 6 секунд.")],
        [("Монолит", "passive", "def_pct", 24, "Защита +24%."),
         ("Отражение", "passive", "thorns", 8, "Отражает 8 урона атакующему."),
         ("Землетрясение", "active", "earthquake", 0, "Удар о землю: урон и оглушение всех врагов рядом.")],
        [("Незыблемость", "passive", "hp_max", 50, "Здоровье +50."),
         ("Неуязвимость", "passive", "dodge", 10, "Шанс уклонения +10%."),
         ("Непоколебимый дух", "active", "fortress", 0, "6 секунд почти полной неуязвимости.")],
    ],
    "arcane": [
        [("Искра маны", "passive", "mp_max", 8, "Мана +8."),
         ("Мудрость", "passive", "magic_power", 8, "Урон магии +8%."),
         ("Огненная искра", "active", "fireball", 0, "Огненный шар в ближайшего врага.")],
        [("Поток маны", "passive", "mp_regen", 1, "Восстановление 1 маны в секунду."),
         ("Пламя", "passive", "fire_damage", 3, "Оружие наносит +3 огненного урона."),
         ("Ледяная стрела", "active", "frost_bolt", 0, "Ледяная стрела замедляет врага.")],
        [("Глубина колодца", "passive", "mp_max", 15, "Мана +15."),
         ("Пепел", "passive", "magic_power", 14, "Урон магии +14%."),
         ("Ледяная новая", "active", "frost_nova", 0, "Волна холода вокруг: урон и замедление.")],
        [("Двойное плетение", "passive", "aoe_radius", 12, "Радиус заклинаний +12%."),
         ("Холод", "passive", "frost_damage", 4, "Оружие наносит +4 ледяного урона."),
         ("Разряд", "active", "lightning", 0, "Молния бьёт по цепи врагов.")],
        [("Щит маны", "passive", "def_flat", 3, "Защита +3 (магический барьер)."),
         ("Пламенный вихрь", "passive", "fire_damage", 6, "Оружие наносит +6 огненного урона."),
         ("Огненная стена", "active", "fire_wall", 0, "Стена огня поджигает врагов рядом.")],
        [("Архимаг", "passive", "magic_power", 22, "Урон магии +22%."),
         ("Хрустальный резерв", "passive", "mp_max", 25, "Мана +25."),
         ("Телепорт", "active", "blink", 0, "Мгновенный рывок в направлении взгляда.")],
        [("Стихийный резонанс", "passive", "magic_power", 28, "Урон магии +28%."),
         ("Абсолютный холод", "passive", "frost_damage", 9, "Оружие наносит +9 ледяного урона."),
         ("Метеор", "active", "meteor", 0, "Метеор падает на ближайших врагов.")],
        [("Владыка чар", "passive", "magic_power", 40, "Урон магии +40%."),
         ("Бездонная мана", "passive", "mp_regen", 4, "Восстановление 4 маны в секунду."),
         ("Армагеддон", "active", "armageddon", 0, "Огонь с небес: огромный урон по всем врагам.")],
    ],
    "wild": [
        [("Лёгкий шаг", "passive", "speed_pct", 6, "Скорость передвижения +6%."),
         ("Зоркий глаз", "passive", "loot_chance", 5, "Шанс выпадения лута +5%."),
         ("Укус змеи", "passive", "poison_damage", 2, "Оружие наносит +2 урона ядом.")],
        [("Охотник", "passive", "speed_pct", 10, "Скорость передвижения +10%."),
         ("Ловкость", "passive", "dodge", 4, "Шанс уклонения +4%."),
         ("Отравленный клинок", "active", "poison_cloud", 0, "Облако яда отравляет врагов рядом.")],
        [("Бегун", "passive", "speed_pct", 14, "Скорость передвижения +14%."),
         ("Чуткий слух", "passive", "xp_gain", 10, "Опыт +10%."),
         ("Рывок", "active", "dash", 0, "Быстрый рывок вперёд.")],
        [("Тень в лесу", "passive", "dodge", 7, "Шанс уклонения +7%."),
         ("Меткий выстрел", "passive", "crit_chance", 6, "Шанс крита +6%."),
         ("Залп стрел", "active", "arrow_volley", 0, "Залп по всем врагам перед собой.")],
        [("Звериная ярость", "passive", "atk_pct", 10, "Весь урон +10%."),
         ("Сильный яд", "passive", "poison_damage", 6, "Оружие наносит +6 урона ядом."),
         ("Волк-спутник", "active", "summon_wolf", 0, "Призвать волка, который сражается рядом.")],
        [("Следопыт", "passive", "loot_chance", 15, "Шанс выпадения лута +15%."),
         ("Вихрь", "passive", "atk_speed", 10, "Скорость атаки +10%."),
         ("Невидимость", "active", "invisibility", 0, "Враги теряют тебя из вида на 6 секунд.")],
        [("Хозяин чащи", "passive", "speed_pct", 20, "Скорость передвижения +20%."),
         ("Отрава", "passive", "poison_damage", 10, "Оружие наносит +10 урона ядом."),
         ("Стая", "active", "summon_pack", 0, "Призвать двух волков-союзников.")],
        [("Дух леса", "passive", "atk_pct", 18, "Весь урон +18%."),
         ("Удача охотника", "passive", "loot_chance", 25, "Шанс выпадения лута +25%."),
         ("Ярость природы", "active", "nature_wrath", 0, "Корни и шипы бьют всех врагов вокруг.")],
    ],
    "life": [
        [("Целебная трава", "passive", "potion_power", 10, "Зелья лечат на 10% сильнее."),
         ("Крепкое сердце", "passive", "hp_max", 10, "Здоровье +10."),
         ("Свет", "active", "heal", 0, "Лечение себя на 25 HP.")],
        [("Знаток трав", "passive", "potion_power", 20, "Зелья лечат на 20% сильнее."),
         ("Регенерация", "passive", "regen", 2, "Восстановление 2 HP в секунду."),
         ("Благословение", "active", "holy_light", 0, "Свет лечит и ослепляет врагов рядом.")],
        [("Жизненная сила", "passive", "hp_max", 18, "Здоровье +18."),
         ("Собиратель", "passive", "gold_find", 15, "Найденное золото +15%."),
         ("Освящённый удар", "active", "smite", 0, "Светящийся удар: урон плюс лечение.")],
        [("Дар жизни", "passive", "heal_power", 20, "Всё лечение +20%."),
         ("Чутьё на золото", "passive", "gold_find", 25, "Найденное золото +25%."),
         ("Похищение жизни", "active", "life_drain", 0, "Вытягивает здоровье из врага рядом.")],
        [("Второе сердце", "passive", "hp_max", 28, "Здоровье +28."),
         ("Мудрость веков", "passive", "xp_gain", 20, "Опыт +20%."),
         ("Тотем жизни", "active", "totem", 0, "Тотем лечит тебя, пока стоит.")],
        [("Источник", "passive", "regen", 4, "Восстановление 4 HP в секунду."),
         ("Щедрость земли", "passive", "loot_chance", 20, "Шанс выпадения лута +20%."),
         ("Круг исцеления", "active", "healing_circle", 0, "Круг на земле быстро лечит.")],
        [("Неугасимый дух", "passive", "hp_max", 45, "Здоровье +45."),
         ("Золотая жила", "passive", "gold_find", 40, "Найденное золото +40%."),
         ("Воскрешение", "active", "revive", 0, "Один раз за бой восстановить всё здоровье при смерти.")],
        [("Вечная жизнь", "passive", "regen", 7, "Восстановление 7 HP в секунду."),
         ("Дар богов", "passive", "heal_power", 45, "Всё лечение +45%."),
         ("Чудо", "active", "miracle", 0, "Полное восстановление здоровья и маны.")],
    ],
}

# icon per effect key (item icon ids from sprites.py)
_EFFECT_ICON = {
    "atk_flat": "sword_iron", "atk_pct": "sword_steel", "atk_speed": "axe_steel",
    "crit_chance": "sword_dragon", "crit_mult": "gem_ruby", "armor_pen": "claw",
    "aoe_radius": "gem_emerald", "lifesteal": "venom", "knockback": "stone",
    "def_flat": "shield_iron", "def_pct": "armor_steel", "hp_max": "armor_iron",
    "dodge": "feather", "thorns": "claw", "regen": "herb", "heal_power": "potion_red",
    "mp_max": "potion_blue", "mp_regen": "gem_sapphire", "magic_power": "scroll",
    "fire_damage": "gem_ruby", "frost_damage": "gem_sapphire", "poison_damage": "venom",
    "speed_pct": "feather", "loot_chance": "pelt", "xp_gain": "scroll",
    "potion_power": "potion_green", "gold_find": "gold",
}
_ABILITY_ICON = {
    "whirlwind": "axe_steel", "power_strike": "sword_steel", "execute": "skull",
    "world_cleave": "sword_dragon", "blade_storm": "axe_goblin",
    "shield_block": "shield_iron", "shield_bash": "shield_wood", "taunt": "meat",
    "stoneskin": "stone", "earthquake": "stone", "fortress": "armor_steel",
    "fireball": "gem_ruby", "frost_bolt": "gem_sapphire", "frost_nova": "gem_sapphire",
    "lightning": "scroll", "fire_wall": "gem_ruby", "blink": "feather",
    "meteor": "gem_ruby", "armageddon": "scroll",
    "poison_cloud": "venom", "dash": "feather", "arrow_volley": "feather",
    "summon_wolf": "pelt", "invisibility": "silk", "summon_pack": "pelt",
    "nature_wrath": "herb", "heal": "potion_red", "holy_light": "amulet",
    "smite": "amulet", "life_drain": "soul", "totem": "wood",
    "healing_circle": "herb", "revive": "ring_gold", "miracle": "potion_gold",
}

_TIER_COST = (1, 1, 2, 2, 3, 3, 4, 5)


def _build() -> list[dict]:
    skills: list[dict] = []
    for branch in BRANCHES:
        bid = branch["id"]
        tiers = _TIERS[bid]
        for ti, tier in enumerate(tiers):
            for lane, (name, kind, key, value, desc) in enumerate(tier):
                sid = f"{bid}_{ti + 1}_{lane}"
                req: list[str] = []
                if ti == 0:
                    req = ["root"]
                else:
                    req = [f"{bid}_{ti}_{lane}"]                 # same lane below
                    if lane != 1:
                        req.append(f"{bid}_{ti}_1")              # or the lane centre
                skills.append({
                    "id": sid, "name": name, "branch": bid, "tier": ti + 1,
                    "lane": lane, "cost": _TIER_COST[ti], "req": req, "kind": kind,
                    "effect": {"key": key, "value": value},
                    "desc": desc,
                    "icon": (_ABILITY_ICON.get(key, "scroll") if kind == "active"
                             else _EFFECT_ICON.get(key, "gem_emerald")),
                })
    return skills


SKILLS: list[dict] = [ROOT] + _build()
_BY_ID = {s["id"]: s for s in SKILLS}


def by_id(sid: str) -> dict | None:
    return _BY_ID.get(sid)


def branch_skills(bid: str) -> list[dict]:
    return [s for s in SKILLS if s["branch"] == bid]


def children_of(sid: str) -> list[dict]:
    return [s for s in SKILLS if sid in s["req"]]


_TIER_BASE = 0.44           # the trunk is bare: the first tier sits well above it
_TIER_STEP = 0.078          # distance between tiers (in tree units)
_LANE_ANGLE = 6.5           # degrees between the three lanes of a tier
_LANE_RADIAL = (-0.022, 0.0, 0.022)   # per-lane radial offset (inner, centre, outer)
_STAGGER = 0.030            # odd branches start further out, so neighbouring cones
                            # never line up radially
_MARGIN = 0.035

_BRANCH_INDEX = {b["id"]: i for i, b in enumerate(BRANCHES)}


def _raw_position(skill: dict) -> tuple[float, float]:
    if skill["branch"] == "root":
        return 0.5, 0.95
    branch = next(b for b in BRANCHES if b["id"] == skill["branch"])
    tier, lane = skill["tier"], skill["lane"]
    radius = (_TIER_BASE + _TIER_STEP * (tier - 1) + _LANE_RADIAL[lane]
              + (_STAGGER if _BRANCH_INDEX[branch["id"]] % 2 else 0.0))
    ang = math.radians(branch["angle"] + (lane - 1) * _LANE_ANGLE)
    return 0.5 + math.sin(ang) * radius, 0.95 - math.cos(ang) * radius


# Raw positions spread far past the unit square, so they are normalised once into
# it: that keeps the maximum possible distance between neighbouring nodes.
_RAW = {s["id"]: _raw_position(s) for s in SKILLS}
_XS = [p[0] for p in _RAW.values()]
_YS = [p[1] for p in _RAW.values()]
_MIN_X, _MAX_X = min(_XS), max(_XS)
_MIN_Y, _MAX_Y = min(_YS), max(_YS)


def position_of(skill: dict) -> tuple[float, float]:
    """Normalised position of a node on the oak canvas (0,0 = top-left, 1,1 = bottom-right)."""
    x, y = _RAW[skill["id"]]
    nx = _MARGIN + (x - _MIN_X) / (_MAX_X - _MIN_X) * (1 - _MARGIN * 2)
    ny = _MARGIN + (y - _MIN_Y) / (_MAX_Y - _MIN_Y) * (1 - _MARGIN * 2)
    return max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))


def min_node_gap() -> float:
    """Smallest distance between any two nodes — used to prove the tree is readable."""
    pts = [position_of(s) for s in SKILLS]
    best = 9.9
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            if d < best:
                best = d
    return best


def requirements_met(learned: set[str], skill: dict) -> bool:
    return all(r in learned for r in skill["req"])


def can_learn(learned: set[str], skill: dict, points: int) -> bool:
    return (skill["id"] not in learned and points >= skill["cost"]
            and requirements_met(learned, skill))


def effect_totals(learned: set[str]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for sid in learned:
        skill = _BY_ID.get(sid)
        if not skill or skill["kind"] != "passive":
            continue
        key = skill["effect"]["key"]
        totals[key] = totals.get(key, 0.0) + float(skill["effect"]["value"])
    return totals


def active_abilities(learned: set[str]) -> list[str]:
    out = []
    for sid in sorted(learned, key=lambda s: (_BY_ID[s]["branch"], _BY_ID[s]["tier"],
                                              _BY_ID[s]["lane"])):
        skill = _BY_ID.get(sid)
        if skill and skill["kind"] == "active":
            out.append(skill["effect"]["key"])
    return out


def validate() -> list[str]:
    problems: list[str] = []
    if len(SKILLS) < 120:
        problems.append(f"only {len(SKILLS)} skills (need 120+)")
    ids = [s["id"] for s in SKILLS]
    if len(set(ids)) != len(ids):
        problems.append("duplicate skill ids")
    for s in SKILLS:
        for r in s["req"]:
            if r not in _BY_ID:
                problems.append(f"{s['id']} requires missing {r}")
    # acyclicity + every node reachable from the root
    seen: set[str] = set()
    frontier = ["root"]
    while frontier:
        sid = frontier.pop()
        if sid in seen:
            continue
        seen.add(sid)
        frontier.extend(c["id"] for c in children_of(sid))
    unreachable = set(ids) - seen
    if unreachable:
        problems.append(f"{len(unreachable)} skills unreachable from the root: "
                        f"{sorted(unreachable)[:4]}")
    for bid in [b["id"] for b in BRANCHES]:
        if len(branch_skills(bid)) != 24:
            problems.append(f"branch {bid} has {len(branch_skills(bid))} skills, expected 24")
    for s in SKILLS:
        x, y = position_of(s)
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            problems.append(f"{s['id']} position {x:.2f},{y:.2f} outside the canvas")
    gap = min_node_gap()
    if gap < 0.034:
        problems.append(f"nodes are packed too tightly: closest pair is {gap:.3f} apart")
    return problems


if __name__ == "__main__":
    issues = validate()
    print(f"skills: {len(SKILLS)} | branches: {len(BRANCHES)}")
    print(f"  passive: {sum(1 for s in SKILLS if s['kind'] == 'passive')}, "
          f"active: {sum(1 for s in SKILLS if s['kind'] == 'active')}")
    print(f"  total cost of everything: {sum(s['cost'] for s in SKILLS)}")
    print(f"  closest node pair: {min_node_gap():.3f} of the canvas")
    xs = [position_of(s)[0] for s in SKILLS]
    ys = [position_of(s)[1] for s in SKILLS]
    print(f"  tree fills x {min(xs):.2f}..{max(xs):.2f}, y {min(ys):.2f}..{max(ys):.2f}")
    print("problems:", len(issues))
    for p in issues:
        print("  -", p)
    if not issues:
        print("SKILLS OK")
