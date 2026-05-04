from manager.game_logic import process_skill_effects, _calculate_bonus_from_rules
from manager.json_rule_v2 import parse_status_stack_sum_param
from manager.utils import apply_buff


def _mk_char(cid, team):
    return {
        "id": cid,
        "name": cid,
        "type": team,
        "hp": 100,
        "mp": 10,
        "states": [],
        "special_buffs": [],
    }


def test_parse_status_stack_sum_param_accepts_japanese_key():
    parsed = parse_status_stack_sum_param("状態異常スタック合計:破裂,出血")
    assert isinstance(parsed, dict)
    assert parsed.get("is_stack_sum") is True
    assert parsed.get("error") == ""
    assert parsed.get("names") == ["破裂", "出血"]


def test_apply_buff_per_n_and_buff_count_power_bonus_flow():
    actor = _mk_char("A", "ally")
    target = _mk_char("T", "enemy")
    target["states"] = [{"name": "破裂", "value": 5}, {"name": "出血", "value": 4}]
    ctx = {"characters": [actor, target], "timeline": []}

    effects = [
        {
            "timing": "HIT",
            "type": "APPLY_BUFF_PER_N",
            "target": "self",
            "source": "target",
            "source_param": "状態異常スタック合計:破裂,出血",
            "buff_id": "Bu-30",
            "value": 1,
            "per_N": 3,
            "max_count": 7,
        }
    ]

    _dmg, logs, changes = process_skill_effects(
        effects, "HIT", actor, target, None, context=ctx, base_damage=0
    )

    buff_changes = [row for row in changes if row[1] == "APPLY_BUFF"]
    assert buff_changes, "APPLY_BUFF change should be produced from APPLY_BUFF_PER_N"
    _, _, buff_name, payload = buff_changes[0]
    assert buff_name == "蓄力"
    assert int(payload.get("count", 0)) == 3
    assert any("蓄力 付与" in line for line in logs)
    assert any("蓄力 スタック +3" in line for line in logs)

    apply_buff(
        actor,
        buff_name,
        int(payload.get("lasting", -1)),
        int(payload.get("delay", 0)),
        data=payload.get("data"),
        count=payload.get("count"),
    )

    bonus_rules = [
        {
            "operation": "PER_N_BONUS",
            "source": "self",
            "param": "蓄力_count",
            "value": 1,
            "per_N": 3,
            "max_bonus": 7,
        }
    ]
    bonus = _calculate_bonus_from_rules(bonus_rules, actor, target, None, context=ctx)
    assert bonus == 1
