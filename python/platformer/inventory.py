"""Cosmetic catalogue and validated transactions; no graphics dependencies."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    slot: str
    price: int
    color: str
    shape: str


ITEMS = (
    Item("hat_leaf", "새싹 모자", "hat", 100, "#6acc74", "leaf"),
    Item("hat_crown", "황금 왕관", "hat", 240, "#ffcc52", "crown"),
    Item("color_sky", "하늘색", "color", 80, "#79c9ed", "color"),
    Item("color_rose", "장미색", "color", 80, "#ee8cad", "color"),
    Item("color_mint", "민트색", "color", 80, "#7ed6b3", "color"),
    Item("back_wings", "숲의 날개", "back", 180, "#bedfa1", "wings"),
)
CATALOG = {item.id: item for item in ITEMS}


def purchase(profile, item_id):
    item = CATALOG.get(item_id)
    if item is None:
        return False, "없는 아이템입니다."
    if item_id in profile["owned"]:
        return False, "이미 보유하고 있습니다."
    if profile["meso"] < item.price:
        return False, "메소가 부족합니다."
    profile["meso"] -= item.price
    profile["owned"].append(item_id)
    return True, f"{item.name} 구매 완료!"


def toggle_equip(profile, item_id):
    if item_id not in CATALOG or item_id not in profile["owned"]:
        return False, "먼저 구매해 주세요."
    item = CATALOG[item_id]
    if profile["equipped"].get(item.slot) == item_id:
        profile["equipped"].pop(item.slot)
        return True, "장착을 해제했습니다."
    profile["equipped"][item.slot] = item_id
    return True, f"{item.name} 장착 완료!"
