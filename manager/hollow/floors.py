"""Load expedition data and prepare the next battle on an isolated state."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from random import Random

from manager.battle.action_slot_mode import is_character_deployed
from manager.battle.combat_session import mark_combat_arrival, start_combat_session
from manager.hollow.map import build_map, weighted_choice
from manager.hollow.resources import DRAW_CATEGORIES
from manager.units.repository import entries
from manager.units.runtime import deployment_store, get_record, valid_deployment_target


@dataclass
class FloorResources:
    tiers: dict
    maps: dict
    fixed: dict
    store: dict


def floor_resources():
    resources = entries(domain="hollow", include_deprecated=False)
    tiers, maps, fixed = {}, {}, {}
    for (kind, key), row in resources.items():
        payload = row["payload"]
        if kind == "tier":
            tiers[payload["tier"]] = payload
        elif kind == "hollow_map":
            maps[key] = payload
        elif kind == "fixed_floor":
            fixed.setdefault(payload["floor"], payload)
    return FloorResources(tiers, maps, fixed, deployment_store(resources, domain="hollow"))


def map_candidates(number, seed, resources):
    if number not in resources.tiers:
        raise ValueError(f"Tier {number} がありません")
    pool = sorted(key for key, payload in resources.maps.items() if payload["tier"] == number)
    if not pool:
        raise ValueError(f"Tier {number} にマップがありません")
    keys = Random(f"{seed}:{number}:candidates").sample(pool, min(3, len(pool)))
    return {"tier": number, "maps": [_candidate_card(key, resources.maps[key]) for key in keys]}


def _candidate_card(key, area):
    weights = area.get("category_weights", {})
    ranked = sorted((category for category in DRAW_CATEGORIES if weights.get(category, 0) > 0),
                    key=weights.__getitem__, reverse=True)
    return {"map_id": key, "name": area["name"], "description": area["description"],
            "image": area.get("image", ""), "categories": ranked[:3]}


def _formation_usable(store, key):
    formation = get_record(store, "enemy_formation", key)
    return bool(formation and formation.get("members")
                and valid_deployment_target(store, "enemy_formation", formation))


def _encounters(area, kind, store):
    result = []
    for row in area["encounters"].get(kind, []):
        if row["weight"] <= 0:
            continue
        if not _formation_usable(store, row["formation_id"]):
            raise ValueError(f"{area['name']} の遭遇表に使えない敵編成があります: {row['formation_id']}")
        result.append((row["formation_id"], row["weight"]))
    if not result:
        raise ValueError(f"{area['name']} の{'通常' if kind == 'normal' else '精鋭'}遭遇表が空です")
    return result


def _selected_map(number, map_id, resources):
    tier = resources.tiers.get(number)
    area = resources.maps.get(map_id)
    if tier is None:
        raise ValueError(f"Tier {number} がありません")
    if area is None or area["tier"] != number:
        raise ValueError(f"Tier {number} で使えないマップです: {map_id}")
    return tier, area


def _boss(area, store):
    formation_id, stage_id = area["boss_formation_id"], area["boss_stage_id"]
    if not _formation_usable(store, formation_id):
        raise ValueError(f"{area['name']} に使えないボス編成があります: {formation_id}")
    stage = get_record(store, "stage", stage_id)
    if not stage or not valid_deployment_target(store, "stage", stage):
        raise ValueError(f"{area['name']} に使えないボスステージがあります: {stage_id}")
    return formation_id, stage_id


def new_map(number, map_id, seed, resources):
    tier, area = _selected_map(number, map_id, resources)
    kinds = [kind for kind in ("normal", "elite") if area["event_weights"].get(kind, 0) > 0]
    if not any(area["event_weights"].values()):
        raise ValueError(f"{area['name']} にマスの重みがありません")
    for kind in kinds:
        _encounters(area, kind, resources.store)
    _boss(area, resources.store)
    return {**build_map(tier, area, resources.fixed, seed), "map_id": map_id}


def encounter_for(run, node, resources):
    layout = run["map"]
    tier, area = _selected_map(layout["tier"], layout["map_id"], resources)
    if node["type"] == "boss":
        return tier, *_boss(area, resources.store)
    kind = "normal" if node["type"] == "battle" else "elite"
    rng = Random(f"{layout['seed']}:{node['id']}")
    return tier, weighted_choice(_encounters(area, kind, resources.store), rng), None


def _roster(state):
    return {char["id"]: char for char in state["characters"] if char.get("type") == "ally"}


def alive(char):
    return char is not None and char.get("hp", 0) > 0


def _board(state):
    board = state.get("map_data") or {}
    return (max(1, min(100, int(board.get("width") or 20))),
            max(1, min(100, int(board.get("height") or 15))))


def line_up(chars, width, height, side):
    """Every other cell, centred vertically, so the badges above and names below never overlap."""
    usable = max(1, height - 2)
    per_column = (usable + 1) // 2
    ally_x = width // 2 - 4
    for column in range(0, len(chars), per_column):
        group = chars[column:column + per_column]
        x = ally_x - column // per_column * 2
        if side == "enemy":
            x = width - 1 - x
        if not 0 <= x < width:
            raise ValueError("戦闘のキャラを配置する場所が足りません")
        top = 1 + (usable - (2 * len(group) - 1)) // 2
        for index, char in enumerate(group):
            char.update(x=x, y=top + 2 * index)


def place_party(state, active):
    roster = _roster(state)
    for char in roster.values():
        char.update(x=-1, y=-1)
    line_up([roster[char_id] for char_id in active if char_id in roster], *_board(state), "ally")


def _reserve_order(run):
    return (char_id for char_id in run["party_order"] if char_id not in run["active"])


def replace_fallen(state, run):
    roster = _roster(state)
    reserves = iter([roster[char_id] for char_id in _reserve_order(run) if alive(roster.get(char_id))])
    replacements = []
    for index, char_id in enumerate(run["active"]):
        char = roster.get(char_id)
        if alive(char):
            continue
        position = ([char["x"], char["y"]] if is_character_deployed(char)
                    else run["positions"].get(char_id))
        if position is None:
            continue
        reserve = next(reserves, None)
        if reserve is None:
            break
        reserve.update(x=position[0], y=position[1])
        if char is not None:
            char.update(x=-1, y=-1)
        run["active"][index] = reserve["id"]
        run["positions"].pop(char_id, None)
        run["positions"][reserve["id"]] = position
        mark_combat_arrival(state, reserve)
        replacements.append(reserve)
    return replacements


def promote_survivors(state, run):
    roster = _roster(state)
    active = [key for key in (*run["active"], *_reserve_order(run)) if alive(roster.get(key))]
    run["active"] = active[:4]
    place_party(state, [])
    run["positions"] = {}


def battle_outcome(state, run):
    from manager.battle.battle_result import estimate_battle_result

    participants = set(run["party_order"])
    characters = [c for c in state["characters"]
                  if c["id"] in participants or (c.get("type") == "enemy" and is_character_deployed(c))]
    estimated = estimate_battle_result({"characters": characters})
    return {"ally_win": "VICTORY", "enemy_win": "DEFEAT", "draw": "DEFEAT"}.get(estimated)


def scale_enemies(enemies, tier, party_size):
    reserve_factor = 1 + Decimal("0.15") * max(0, party_size - 4)
    hp_factor = Decimal(str(tier["hp_multiplier"])) * reserve_factor
    attack = max(0, int(((Decimal(str(tier["attack_multiplier"])) - 1) * 100).to_integral_value(rounding=ROUND_HALF_UP)))
    for enemy in enemies:
        for field in ("hp", "maxHp"):
            enemy[field] = int((enemy[field] * hp_factor).to_integral_value(rounding=ROUND_CEILING))
        if attack:
            from manager.buff_apply import apply_buff
            apply_buff(enemy, "ホロウの攻撃補正", -1, 0, data={"buff_id": "Bu-45", "value": attack})
    return {"hp_multiplier": float(hp_factor), "attack_percent": attack}


def prepare_battle(state, run, node, resources, username):
    from manager.battle.common_manager import _clear_stage_runtime_state
    from manager.game_logic import process_battle_start
    from manager.preset_deployment import apply_deployment

    tier, formation_id, stage_id = encounter_for(run, node, resources)
    place_party(state, run["active"])
    _clear_stage_runtime_state(state)
    state.pop("room_preset_state", None)
    request = {"formations": {"enemy": {"id": formation_id, "mode": "replace"}}}
    if stage_id:
        request["stage"] = {"id": stage_id, "apply": {"enemy_formation": False}}
    summary, logs = apply_deployment(state, request, resources.store, room_role="owner")
    if summary["placement"]["unplaced"]:
        raise ValueError("敵を配置する場所が足りません")
    line_up([char for char in state["characters"] if char.get("type") == "enemy" and is_character_deployed(char)],
            *_board(state), "enemy")
    if not start_combat_session(state, username):
        raise ValueError("戦闘を開始できません")
    # Deployment replaces the room's nested state with its own candidate.
    run = state["hollow"]["run"]
    run["positions"] = {char["id"]: [char["x"], char["y"]] for char in state["characters"]
                        if char["id"] in run["active"] and is_character_deployed(char)}
    replace_fallen(state, run)
    enemies = [char for char in state["characters"] if char.get("type") == "enemy"]
    scaling = scale_enemies(enemies, tier, len(run["party_order"]))
    from manager.hollow.relic_buffs import sync_expedition_buffs

    sync_expedition_buffs(state, run)
    # Combat entry effects use the scaled enemy HP.
    logs += process_battle_start(None, [char for char in state["characters"]
                                       if alive(char) and is_character_deployed(char)], state=state)
    encounter = {"formation_id": formation_id, "stage_id": stage_id, **scaling}
    if node["type"] == "boss":
        encounter["boss_name"] = get_record(resources.store, "enemy_formation", formation_id)["name"]
    return encounter, logs, enemies
