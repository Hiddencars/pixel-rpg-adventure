#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Items, equipment and loot tables for Pixel RPG Adventure 1.3."""

from __future__ import annotations

# kind: consumable | weapon | armor | material | quest
ITEMS: dict[str, dict] = {
    "potion": {
        "name": "Зелье здоровья", "kind": "consumable", "icon": "potion",
        "desc": "Восстанавливает 15 HP.", "heal": 15, "value": 12, "stack": 9,
    },
    "herb": {
        "name": "Лесная трава", "kind": "consumable", "icon": "herb",
        "desc": "Восстанавливает 6 HP.", "heal": 6, "value": 4, "stack": 9,
    },
    "sword_rusty": {
        "name": "Ржавый меч", "kind": "weapon", "icon": "sword",
        "desc": "Старый, но всё ещё острый.", "atk": 3, "value": 15, "stack": 1,
    },
    "sword_iron": {
        "name": "Железный меч", "kind": "weapon", "icon": "sword",
        "desc": "Надёжная сталь кузнеца.", "atk": 7, "value": 60, "stack": 1,
    },
    "axe_goblin": {
        "name": "Гоблинский топор", "kind": "weapon", "icon": "axe",
        "desc": "Грубый, но тяжёлый.", "atk": 5, "value": 35, "stack": 1,
    },
    "armor_leather": {
        "name": "Кожаная куртка", "kind": "armor", "icon": "armor",
        "desc": "Мягкая защита странника.", "def": 2, "value": 25, "stack": 1,
    },
    "armor_iron": {
        "name": "Кольчуга", "kind": "armor", "icon": "armor",
        "desc": "Тяжёлая, зато держит удар.", "def": 5, "value": 80, "stack": 1,
    },
    "ear": {
        "name": "Ухо гоблина", "kind": "material", "icon": "ear",
        "desc": "Доказательство победы. Можно продать.", "value": 6, "stack": 9,
    },
    "key": {
        "name": "Ключ подземелья", "kind": "quest", "icon": "key",
        "desc": "Открывает что-то важное...", "value": 0, "stack": 1,
    },
}

# item id -> whether it can be used from the inventory
USABLE_KINDS = ("consumable", "weapon", "armor")

# (item_id, weight) — weight 0 means "never"
LOOT: dict[str, list[tuple[str, int]]] = {
    "goblin": [
        ("ear", 45), ("potion", 18), ("herb", 20),
        ("sword_rusty", 8), ("armor_leather", 6), ("axe_goblin", 5),
    ],
    "brute": [
        ("ear", 40), ("ear", 25), ("potion", 22), ("herb", 10),
        ("axe_goblin", 16), ("sword_iron", 8), ("armor_iron", 6),
    ],
}

GOLD_LOOT = {"goblin": (1, 6), "brute": (4, 12)}


def roll_loot(kind: str, rng) -> list[str]:
    """Return the item ids a defeated mob drops."""
    table = LOOT.get(kind, [])
    drops: list[str] = []
    for item_id, weight in table:
        if rng.randrange(100) < weight:
            drops.append(item_id)
    return drops


def item_name(item_id: str) -> str:
    return ITEMS.get(item_id, {}).get("name", item_id)


def item_icon(item_id: str) -> str:
    return ITEMS.get(item_id, {}).get("icon", "potion")
