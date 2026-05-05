from manager.game_logic import calculate_skill_preview, process_skill_effects
from manager.utils import get_status_value, set_status_value


def _mk_char(cid, team):
    return {
        "id": cid,
        "name": cid,
        "type": team,
        "hp": 100,
        "max_hp": 100,
        "mp": 10,
        "states": [
            {"name": "HP", "value": 100},
            {"name": "MP", "value": 10},
            {"name": "戦慄", "value": 4},
        ],
        "special_buffs": [],
        "SPassive": [],
    }


def _apply_state_changes(changes):
    for target, change_type, name, value in changes:
        if change_type != "APPLY_STATE":
            continue
        cur = int(get_status_value(target, name) or 0)
        set_status_value(target, name, cur + int(value))


def test_senritsu_dice_reduction_uses_palette_dice_expression():
    actor = _mk_char("a", "ally")
    target = _mk_char("t", "enemy")
    skill_data = {
        "基礎威力": 0,
        "チャットパレット": "/roll 0+2d6",
        "分類": "戦慄",
    }

    out = calculate_skill_preview(actor, target, skill_data, senritsu_max_apply=3)
    assert int(out.get("senritsu_dice_reduction", 0)) == 3
    assert "2d3" in str(out.get("final_command", ""))


def test_consume_buff_count_for_gain_falls_back_to_status_value():
    actor = _mk_char("a", "ally")
    target = _mk_char("t", "enemy")
    ctx = {"characters": [actor, target]}
    effects = [
        {
            "timing": "HIT",
            "type": "CONSUME_BUFF_COUNT_FOR_GAIN",
            "target": "self",
            "buff_name": "戦慄",
            "consume_required": 3,
            "gains": [{"type": "MP", "value": 2}],
        }
    ]

    _, _logs, changes = process_skill_effects(effects, "HIT", actor, target, None, context=ctx, base_damage=0)
    _apply_state_changes(changes)

    assert int(get_status_value(actor, "戦慄")) == 1
    assert int(get_status_value(actor, "MP")) == 12
