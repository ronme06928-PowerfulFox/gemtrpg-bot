"""Draw and resolve Hollow events, and recover the expedition party."""

from copy import deepcopy
from random import Random

from manager.exploration_roll import roll_check, roll_log, skill_level
from manager.hollow import relics
from manager.hollow.floors import _roster, alive, promote_survivors
from manager.hollow.map import weighted_choice
from manager.hollow.resources import EVENT_TABLES
from manager.hollow.runtime import available, get_reward, relic_card
from manager.items.loader import item_loader
from manager.items.usage_manager import item_usage_manager
from manager.buff_catalog import get_buff_by_id


def _loot_card(kind, key):
    if kind == "item":
        item = item_loader.get_item(key)
        return {"kind": kind, "id": key, "name": item.get("name") or key} if item else None
    relic = get_reward("relic", key)
    return {"kind": kind, **relic_card(relic)} if relic else None


def draw_event(run, node, area):
    kind = node["type"]
    field, id_field, resource = EVENT_TABLES[kind]
    rng = Random(f"{run['map']['seed']}:{node['id']}:event")
    definitions = available(resource)
    options = [(row[id_field], row["weight"]) for row in area[field] if row[id_field] in definitions]
    if not any(weight > 0 for _, weight in options):
        raise ValueError(f"{area['name']} に使える{('魔素だまり' if kind == 'miasma' else '宝箱')}がありません")
    item = definitions[weighted_choice(options, rng)]
    event = {"type": kind, "resolved": False, "name": item["name"], "text": item["text"]}
    if kind == "miasma":
        if not item["choices"]:
            raise ValueError("魔素だまりに選択肢がありません")
        event["choices"] = deepcopy(item["choices"])
    else:
        table = available("drop_table").get(item["drop_table_id"], {})
        cards = [(_loot_card(row["kind"], row["id"]), row["weight"])
                 for row in table.get("rows", []) if row["weight"] > 0]
        options = [(card, weight) for card, weight in cards if card]
        if not options:
            raise ValueError(f"{item['name']} に使えるドロップがありません")
        event["loot"] = weighted_choice(options, rng)
    return event


def _party_member(state, run, char_id, *, allow_down):
    char = _roster(state).get(char_id) if isinstance(char_id, str) and char_id in run["party_order"] else None
    if char is None or (not allow_down and not alive(char)):
        raise ValueError("受け取る、または判定するパーティのキャラを選んでください")
    return char


def _gain_loot(run, card, char):
    key = card["id"]
    if card["kind"] == "item":
        item_usage_manager.grant_item(char, key)
        return {"kind": "item", "id": key, "name": card["name"], "char_id": char["id"]}
    return {"kind": "relic", "id": key, "name": card["name"], **relics.acquire(run, key, card)}


def _apply_choice(state, run, choice, field, target, char):
    effect = choice.get(field)
    if not effect:
        return None
    kind, key = effect["kind"], effect["id"]
    if kind == "buff":
        definition = get_buff_by_id(key)
        if definition is None:
            raise ValueError(f"効果に使えるバフがありません: {key}")
        roster = _roster(state)
        char_ids = ([char["id"]] if choice[target] == "selected" else
                    [char_id for char_id in run["party_order"] if char_id in roster])
        duration = effect["battles"]
        run["temp_buffs"].extend({"char_id": char_id, "buff_id": key, "battles_left": duration}
                                for char_id in char_ids)
        name = definition.get("display_name") or definition.get("name") or key
        return {"kind": kind, "id": key, "name": name, "battles_left": duration, "char_ids": char_ids}
    card = _loot_card(kind, key)
    if card is None:
        raise ValueError(f"効果に使える報酬がありません: {key}")
    return _gain_loot(run, card, char)


def resolve_miasma(state, run, event, index, char_id):
    choices = event["choices"]
    if type(index) is not int or not 0 <= index < len(choices):
        raise ValueError("魔素だまりの選択肢を指定してください")
    choice = choices[index]
    needs_member = "difficulty" in choice or any(
        choice.get(field, {}).get("kind") == "item" or choice.get(target) == "selected"
        for field, target in (("effect", "target"), ("failure_effect", "failure_target"))
    )
    char = _party_member(state, run, char_id, allow_down=False) if needs_member or char_id is not None else None
    result = {"choice_index": index, "success": True}
    if char is not None:
        result["char_id"] = char["id"]
    message = None
    if "difficulty" in choice:
        skill, difficulty = choice["skill"], choice["difficulty"]
        check = roll_check(skill_level(char, skill), difficulty)
        message = roll_log(char["name"], skill, check, difficulty, show_difficulty=True)
        result.update(check, difficulty=difficulty, skill=skill)
    fields = ("effect", "target") if result["success"] else ("failure_effect", "failure_target")
    result["gain"] = _apply_choice(state, run, choice, *fields, char)
    return result, message


def resolve_chest(state, run, event, take, char_id):
    if type(take) is not bool:
        raise ValueError("宝箱を受け取るか見送るかを指定してください")
    result = {"taken": take, "gain": None}
    if take:
        card = event["loot"]
        char = _party_member(state, run, char_id, allow_down=True) if card["kind"] == "item" else None
        result["gain"] = _gain_loot(run, card, char)
    return result, None


def recover_party(state, run, hp_percent, mp_percent, *, revive=False):
    roster = _roster(state)
    changes = []
    for char_id in run["party_order"]:
        char = roster.get(char_id)
        if char is None or (not revive and not alive(char)):
            continue
        changes_for_char = {"char_id": char_id}
        for stat, maximum, percent in (("hp", "maxHp", hp_percent), ("mp", "maxMp", mp_percent)):
            cap = char.get(maximum, 0)
            before = char.get(stat, 0)
            amount = int(cap * percent // 100)
            base = before
            if stat == "hp" and revive and not alive(char):
                base = 0
                amount = max(1, amount)
            after = cap if percent == 100 else min(cap, base + amount)
            char[stat] = after
            changes_for_char[stat] = after - before
        changes.append(changes_for_char)
    return changes


def fixed_recovery(state, run, fixed, *, boss_name=None):
    kind = fixed["type"]
    percent = 100 if kind == "town" else 50
    recovery = recover_party(state, run, percent, percent, revive=True)
    promote_survivors(state, run)
    event = {"type": kind, "name": fixed["name"], "text": fixed["text"], "resolved": True, "recovery": recovery}
    if boss_name:
        event["boss_name"] = boss_name
    return event
