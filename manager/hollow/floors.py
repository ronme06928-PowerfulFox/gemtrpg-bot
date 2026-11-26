"""Load expedition data and prepare the next battle on an isolated state."""

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from random import Random

from manager.battle.action_slot_mode import is_character_deployed
from manager.battle.combat_session import mark_combat_arrival, start_combat_session
from manager.hollow.map import build_map, weighted_choice
from manager.units.repository import entries
from manager.units.runtime import deployment_store


def floor_resources():
    resources = entries(domain="hollow", include_deprecated=False)
    tiers = {row["payload"]["tier"]: row["payload"] for (kind, _), row in resources.items() if kind == "tier"}
    fixed = {}
    for (kind, _), row in resources.items():
        if kind == "fixed_floor":
            payload = row["payload"]
            if payload["floor"] not in fixed or payload["type"] == "boss":
                fixed[payload["floor"]] = payload
    return tiers, fixed, deployment_store(resources, domain="hollow")


def _encounters(tier, kind, store):
    result = []
    for row in tier["encounters"].get(kind, []):
        if row["weight"] <= 0:
            continue
        formation = store["enemy_formations"].get(row["formation_id"])
        if not formation or not formation.get("members"):
            raise ValueError(f"Tier {tier['tier']} の遭遇表に使えない敵編成があります: {row['formation_id']}")
        result.append((row["formation_id"], row["weight"]))
    if not result:
        raise ValueError(f"Tier {tier['tier']} の{ '通常' if kind == 'normal' else '精鋭' }遭遇表が空です")
    return result


def new_map(number, seed, resources):
    tiers, fixed, store = resources
    tier = tiers.get(number)
    if tier is None:
        raise ValueError(f"Tier {number} がありません")
    kinds = [kind for kind in ("normal", "elite") if tier["event_weights"].get(kind, 0) > 0]
    if not kinds:
        raise ValueError(f"Tier {number} に通常・精鋭戦闘の重みがありません")
    for kind in kinds:
        _encounters(tier, kind, store)
    return build_map(tier, fixed, seed)


def encounter_for(run, node, resources):
    tiers, fixed, store = resources
    tier_number = run["map"]["tier"]
    tier = tiers.get(tier_number)
    if tier is None:
        raise ValueError(f"Tier {tier_number} がありません")
    if node["type"] == "boss":
        row = fixed.get(node["floor"], {})
        if row.get("type") != "boss" or not row.get("formation_id") or not row.get("stage_id"):
            raise ValueError(f"{node['floor']}F のボスの編成・ステージを設定してください")
        formation = store["enemy_formations"].get(row["formation_id"])
        if not formation or not formation.get("members"):
            raise ValueError(f"{node['floor']}F のボス編成が空です")
        return tier, row["formation_id"], row["stage_id"]
    kind = "normal" if node["type"] == "battle" else "elite"
    rng = Random(f"{run['map']['seed']}:{node['id']}")
    return tier, weighted_choice(_encounters(tier, kind, store), rng), None


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
    summary, logs = apply_deployment(state, request, resources[2], room_role="owner")
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
    # Combat entry effects use the scaled enemy HP.
    logs += process_battle_start(None, [char for char in state["characters"]
                                       if alive(char) and is_character_deployed(char)], state=state)
    return {"formation_id": formation_id, "stage_id": stage_id, **scaling}, logs, enemies
