#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Items, loot tables, prices and shop stock for Pixel RPG.

Item fields
    name    Russian display name
    kind    consumable | weapon | armor | ring | material | quest
    slot    weapon | armor | ring | amulet  (for equippable kinds)
    icon    key into sprites.ICON_BUILDERS
    desc    short description
    value   base price in gold (selling gives SELL_RATE of it)
    stack   max per inventory slot (1 = no stacking)
    atk/def/heal/mp/speed/crit  stat bonuses

Public API
    ITEMS, SHOP_STOCK, MOB_GOLD, LOOT_TABLES
    item_name(item_id), item_icon(item_id), item_value(item_id)
    sell_price(item_id), buy_price(item_id)
    roll_loot(mob_kind, rng) -> list[item_id]
    gold_drop(mob_kind, rng) -> int
    validate() -> list[str]
"""

from __future__ import annotations

import random

SELL_RATE = 0.45           # what a merchant pays for your loot
BUY_MARKUP = 1.6           # what the merchant charges


def _it(name, kind, icon, desc, value, **kw) -> dict:
    if "dfn" in kw:                    # `def` is a keyword, so the kwarg is `dfn`
        kw["def"] = kw.pop("dfn")
    data = {"name": name, "kind": kind, "icon": icon, "desc": desc, "value": value,
            "stack": kw.pop("stack", 1 if kind in ("weapon", "armor", "ring") else 9)}
    data.update(kw)
    return data


ITEMS: dict[str, dict] = {
    # ---------------------------------------------------------- consumables
    "potion": _it("Зелье здоровья", "consumable", "potion_red",
                  "Восстанавливает 25 HP.", 18, heal=25, stack=9),
    "potion_big": _it("Большое зелье здоровья", "consumable", "potion_red",
                      "Восстанавливает 70 HP.", 52, heal=70, stack=5),
    "mana_potion": _it("Зелье маны", "consumable", "potion_blue",
                       "Восстанавливает 30 маны.", 22, mp=30, stack=9),
    "elixir": _it("Эликсир силы", "consumable", "potion_gold",
                  "Полностью восстанавливает здоровье и ману.", 140,
                  heal=999, mp=999, stack=3),
    "antidote": _it("Противоядие", "consumable", "potion_green",
                    "Снимает отравление и даёт 10 HP.", 16, heal=10, stack=9),
    "herb": _it("Целебная трава", "consumable", "herb",
                "Восстанавливает 8 HP.", 6, heal=8, stack=9),
    "mushroom": _it("Лесной гриб", "consumable", "mushroom",
                    "Восстанавливает 12 HP, но немного кружит голову.", 9,
                    heal=12, stack=9),
    "honey": _it("Дикий мёд", "consumable", "honey",
                 "Восстанавливает 20 HP и ускоряет на 10 секунд.", 28,
                 heal=20, speed=0.15, stack=5),
    "meat": _it("Жареное мясо", "consumable", "meat",
                "Восстанавливает 35 HP.", 26, heal=35, stack=5),
    # -------------------------------------------------------------- weapons
    "sword_rusty": _it("Ржавый меч", "weapon", "sword_rusty",
                       "Старый меч, но всё лучше кулаков.", 15, slot="weapon", atk=3),
    "sword_iron": _it("Железный меч", "weapon", "sword_iron",
                      "Надёжная сталь кузнеца.", 65, slot="weapon", atk=7),
    "sword_steel": _it("Стальной меч", "weapon", "sword_steel",
                       "Острый и лёгкий клинок.", 180, slot="weapon", atk=13, crit=4),
    "sword_dragon": _it("Драконий клинок", "weapon", "sword_dragon",
                        "Пылает жаром драконьей чешуи.", 620, slot="weapon", atk=22,
                        crit=8, fire=6),
    "axe_goblin": _it("Топор гоблина", "weapon", "axe_goblin",
                      "Грубый, но тяжёлый.", 24, slot="weapon", atk=5),
    "axe_steel": _it("Стальной топор", "weapon", "axe_steel",
                     "Рассекает и щит, и кость.", 210, slot="weapon", atk=16),
    "dagger_shadow": _it("Кинжал тени", "weapon", "sword_rusty",
                         "Быстрый кинжал охотника.", 120, slot="weapon", atk=8,
                         crit=10, speed=0.05),
    "staff_arcane": _it("Посох чар", "weapon", "scroll",
                        "Усиливает магию и заклинания.", 240, slot="weapon", atk=6,
                        magic=25),
    # ---------------------------------------------------------------- armor
    "armor_leather": _it("Кожаная куртка", "armor", "armor_leather",
                         "Лёгкая защита охотника.", 40, slot="armor", dfn=2),
    "armor_iron": _it("Железная броня", "armor", "armor_iron",
                      "Тяжёлая, зато надёжная.", 130, slot="armor", dfn=5),
    "armor_steel": _it("Стальная броня", "armor", "armor_steel",
                       "Кольчуга с наплечниками.", 320, slot="armor", dfn=9, hp=10),
    "armor_mage": _it("Мантия чародея", "armor", "armor_mage",
                      "Ткань, ткущая защиту из маны.", 280, slot="armor", dfn=6,
                      mp=20, magic=15),
    "shield_wood": _it("Деревянный щит", "armor", "shield_wood",
                       "Дубовые доски, обитые кожей.", 35, slot="armor", dfn=2),
    "shield_iron": _it("Железный щит", "armor", "shield_iron",
                       "Надёжно держит удар.", 150, slot="armor", dfn=6),
    # ---------------------------------------------------------------- rings
    "ring_gold": _it("Золотое кольцо", "ring", "ring_gold",
                     "Блестит, греет душу.", 90, slot="ring", hp=8),
    "ring_ruby": _it("Кольцо с рубином", "ring", "ring_ruby",
                     "Придаёт ярости в бою.", 210, slot="ring", atk=4, crit=5),
    "ring_sapphire": _it("Кольцо с сапфиром", "ring", "ring_sapphire",
                         "Хранит ману.", 210, slot="ring", mp=25),
    "amulet": _it("Амулет духа", "amulet", "amulet",
                  "Хранит жизнь владельца.", 260, slot="amulet", hp=20, dfn=2),
    # ------------------------------------------------------------- materials
    "ear": _it("Ухо гоблина", "material", "ear",
               "Трофей, который охотно купят.", 5, stack=20),
    "fang": _it("Клык", "material", "fang", "Острый трофей.", 8, stack=20),
    "tusk": _it("Клык орка", "material", "tusk", "Из него делают рукояти.", 14, stack=20),
    "claw": _it("Коготь", "material", "claw", "Крепкий и цепкий.", 10, stack=20),
    "pelt": _it("Шкура", "material", "pelt", "Тёплая выделанная шкура.", 16, stack=20),
    "silk": _it("Паутина", "material", "silk", "Тонкая и прочная нить.", 12, stack=20),
    "feather": _it("Перо", "material", "feather", "Легче воздуха.", 6, stack=20),
    "venom": _it("Пузырёк яда", "material", "venom", "Осторожно, едко.", 18, stack=20),
    "bone": _it("Кость", "material", "bone", "Из неё варят клей и супы.", 7, stack=20),
    "skull": _it("Череп", "material", "skull", "Мрачный трофей.", 22, stack=20),
    "ore_iron": _it("Железная руда", "material", "ore_iron", "Кузнец расплавит.", 12, stack=20),
    "ore_gold": _it("Золотая руда", "material", "ore_gold", "Блестящие крупинки.", 30, stack=20),
    "ore_mithril": _it("Мифриловая руда", "material", "ore_mithril",
                       "Редкий светлый металл.", 75, stack=20),
    "gem_emerald": _it("Изумруд", "material", "gem_emerald", "Зелёный самоцвет.", 60, stack=10),
    "gem_ruby": _it("Рубин", "material", "gem_ruby", "Алый самоцвет.", 70, stack=10),
    "gem_sapphire": _it("Сапфир", "material", "gem_sapphire", "Синий самоцвет.", 70, stack=10),
    "soul": _it("Осколок души", "material", "soul", "Холодный на ощупь.", 45, stack=10),
    "cloth": _it("Обрывок ткани", "material", "cloth", "Годится на бинты.", 4, stack=20),
    "wood": _it("Древесина", "material", "wood", "Плотное полено.", 5, stack=20),
    "leaf": _it("Лист дуба", "material", "leaf", "Пахнет смолой и летом.", 2, stack=20),
    "berry": _it("Лесные ягоды", "consumable", "berry", "Сладкие ягоды: +12 здоровья.", 6,
                 stack=20, heal=12),
    "flower": _it("Полевой цветок", "material", "flower", "Знахарка платит за такие.", 8,
                  stack=20),
    "stone": _it("Камень", "material", "stone", "Серый булыжник.", 3, stack=20),
    "scroll": _it("Свиток чар", "material", "scroll", "Непонятные письмена.", 55, stack=10),
    # ---------------------------------------------------------------- quests
    "key": _it("Ключ от подвала", "quest", "key", "Открывает что-то важное.", 0),
    "crown_shard": _it("Осколок короны", "quest", "gem_sapphire",
                       "Часть древней короны Дубравы.", 0),
}

# gold ranges per mob kind
MOB_GOLD: dict[str, tuple[int, int]] = {
    "goblin": (2, 7), "brute": (6, 14), "orc": (9, 20), "bandit": (8, 18),
    "skeleton": (5, 12), "wraith": (10, 22), "troll": (14, 30), "imp": (4, 10),
    "golem": (16, 34), "spider": (3, 9), "slime": (2, 6), "bat": (2, 6),
    "snake": (3, 8), "wolf": (4, 10), "boar": (5, 11), "bear": (7, 15),
    "cow": (1, 3), "sheep": (1, 3), "chicken": (1, 2),
}

# (item_id, chance, min_count, max_count)
LOOT_TABLES: dict[str, list[tuple[str, float, int, int]]] = {
    "goblin": [("ear", 0.75, 1, 2), ("herb", 0.25, 1, 1), ("cloth", 0.30, 1, 2),
               ("axe_goblin", 0.06, 1, 1), ("potion", 0.12, 1, 1), ("wood", 0.2, 1, 2)],
    "brute": [("ear", 0.9, 1, 3), ("fang", 0.45, 1, 2), ("pelt", 0.3, 1, 1),
              ("sword_iron", 0.07, 1, 1), ("armor_leather", 0.06, 1, 1),
              ("potion", 0.2, 1, 1), ("ore_iron", 0.18, 1, 2)],
    "orc": [("tusk", 0.6, 1, 2), ("cloth", 0.35, 1, 2), ("pelt", 0.3, 1, 1),
            ("axe_steel", 0.05, 1, 1), ("armor_iron", 0.06, 1, 1),
            ("potion_big", 0.14, 1, 1), ("ore_iron", 0.25, 1, 3)],
    "bandit": [("cloth", 0.5, 1, 3), ("key", 0.08, 1, 1), ("dagger_shadow", 0.06, 1, 1),
               ("potion", 0.3, 1, 2), ("armor_leather", 0.08, 1, 1)],
    "skeleton": [("bone", 0.7, 1, 3), ("skull", 0.18, 1, 1), ("scroll", 0.12, 1, 1),
                 ("sword_rusty", 0.1, 1, 1), ("shield_wood", 0.08, 1, 1),
                 ("bone", 0.2, 1, 1)],
    "wraith": [("soul", 0.6, 1, 2), ("cloth", 0.4, 1, 2), ("scroll", 0.25, 1, 1),
               ("ring_sapphire", 0.05, 1, 1), ("mana_potion", 0.3, 1, 2)],
    "troll": [("pelt", 0.7, 1, 2), ("bone", 0.5, 1, 3), ("stone", 0.5, 1, 3),
              ("ring_gold", 0.08, 1, 1), ("armor_steel", 0.05, 1, 1),
              ("potion_big", 0.25, 1, 2)],
    "imp": [("venom", 0.5, 1, 2), ("soul", 0.2, 1, 1), ("gem_ruby", 0.07, 1, 1),
            ("potion", 0.2, 1, 1)],
    "golem": [("stone", 0.8, 1, 3), ("ore_iron", 0.5, 1, 2), ("ore_mithril", 0.12, 1, 1),
              ("gem_emerald", 0.12, 1, 1), ("armor_iron", 0.1, 1, 1)],
    "spider": [("silk", 0.7, 1, 3), ("venom", 0.35, 1, 2), ("fang", 0.3, 1, 2),
               ("ring_ruby", 0.04, 1, 1)],
    "slime": [("venom", 0.35, 1, 1), ("herb", 0.3, 1, 2), ("stone", 0.2, 1, 1)],
    "bat": [("feather", 0.5, 1, 2), ("cloth", 0.25, 1, 1), ("fang", 0.2, 1, 1)],
    "snake": [("venom", 0.6, 1, 2), ("pelt", 0.3, 1, 1), ("antidote", 0.15, 1, 1)],
    "wolf": [("pelt", 0.65, 1, 2), ("fang", 0.45, 1, 2), ("meat", 0.3, 1, 1),
             ("armor_leather", 0.05, 1, 1)],
    "boar": [("meat", 0.6, 1, 2), ("tusk", 0.4, 1, 2), ("pelt", 0.3, 1, 1)],
    "bear": [("pelt", 0.8, 1, 2), ("meat", 0.5, 1, 2), ("claw", 0.5, 1, 2),
             ("ring_gold", 0.05, 1, 1)],
    "cow": [("meat", 0.7, 1, 2), ("pelt", 0.4, 1, 1), ("cloth", 0.2, 1, 1)],
    "sheep": [("cloth", 0.7, 1, 2), ("meat", 0.4, 1, 1)],
    "chicken": [("feather", 0.8, 1, 3), ("meat", 0.3, 1, 1)],
}

# what the merchant sells (id -> how many he keeps in stock)
SHOP_STOCK: dict[str, int] = {
    "potion": 12, "potion_big": 5, "mana_potion": 8, "antidote": 6, "elixir": 2,
    "herb": 15, "meat": 6,
    "sword_iron": 2, "axe_steel": 1, "sword_steel": 1, "dagger_shadow": 2,
    "armor_leather": 3, "armor_iron": 2, "shield_iron": 2, "shield_wood": 3,
    "ring_gold": 2, "ring_sapphire": 1,
}


def item_name(item_id: str | None) -> str:
    if not item_id:
        return "—"
    item = ITEMS.get(item_id)
    return item["name"] if item else item_id


def item_icon(item_id: str | None) -> str:
    item = ITEMS.get(item_id) if item_id else None
    return item["icon"] if item else "default"


def item_value(item_id: str) -> int:
    item = ITEMS.get(item_id)
    return int(item["value"]) if item else 0


def sell_price(item_id: str) -> int:
    """Gold the merchant pays for one unit (quest items are not for sale)."""
    item = ITEMS.get(item_id)
    if not item or item["kind"] == "quest":
        return 0
    return max(1, int(item["value"] * SELL_RATE))


def buy_price(item_id: str) -> int:
    item = ITEMS.get(item_id)
    if not item:
        return 0
    return max(1, int(item["value"] * BUY_MARKUP))


def roll_loot(mob_kind: str, rng: random.Random) -> list[str]:
    out: list[str] = []
    for (item_id, chance, lo, hi) in LOOT_TABLES.get(mob_kind, []):
        if item_id not in ITEMS or chance <= 0:
            continue
        if rng.random() < chance:
            for _ in range(rng.randint(lo, max(lo, hi))):
                out.append(item_id)
    return out


def gold_drop(mob_kind: str, rng: random.Random) -> int:
    lo, hi = MOB_GOLD.get(mob_kind, (1, 4))
    return rng.randint(lo, hi)


def validate() -> list[str]:
    problems: list[str] = []
    for item_id, item in ITEMS.items():
        for field in ("name", "kind", "icon", "desc", "value", "stack"):
            if field not in item:
                problems.append(f"{item_id} missing {field}")
        if item["kind"] in ("weapon", "armor", "ring") and "slot" not in item:
            problems.append(f"{item_id} is equippable but has no slot")
        if item["kind"] == "consumable" and not any(
                k in item for k in ("heal", "mp", "speed")):
            problems.append(f"{item_id} is a consumable with no effect")
    for mob, table in LOOT_TABLES.items():
        if mob not in MOB_GOLD:
            problems.append(f"loot table for {mob} has no gold range")
        for (item_id, chance, lo, hi) in table:
            if item_id not in ITEMS:
                problems.append(f"{mob} drops unknown item {item_id}")
            if not 0.0 <= chance <= 1.0:
                problems.append(f"{mob}/{item_id} chance {chance} out of range")
            if lo > hi:
                problems.append(f"{mob}/{item_id} count range {lo}-{hi} inverted")
    for item_id in SHOP_STOCK:
        if item_id not in ITEMS:
            problems.append(f"shop sells unknown item {item_id}")
    if len(ITEMS) < 40:
        problems.append(f"only {len(ITEMS)} items defined")
    return problems


if __name__ == "__main__":
    issues = validate()
    print(f"items: {len(ITEMS)} | loot tables: {len(LOOT_TABLES)} | shop lines: {len(SHOP_STOCK)}")
    kinds: dict[str, int] = {}
    for it in ITEMS.values():
        kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
    print("by kind:", kinds)
    rng = random.Random(7)
    for mob in ("goblin", "orc", "troll", "wraith"):
        sample: dict[str, int] = {}
        for _ in range(300):
            for i in roll_loot(mob, rng):
                sample[i] = sample.get(i, 0) + 1
        print(f"  {mob}: {dict(sorted(sample.items()))}")
    print("problems:", len(issues))
    for p in issues:
        print("  -", p)
    if not issues:
        print("ITEMS OK")
