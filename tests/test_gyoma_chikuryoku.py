from manager.game_logic import process_skill_effects
from manager.utils import apply_buff, get_status_value, remove_buff, set_status_value


def _build_char():
    return {
        "id": "char-1",
        "name": "Tester",
        "type": "ally",
        "hp": 100,
        "mp": 10,
        "params": [
            {"label": "物理補正", "value": 0},
            {"label": "魔法補正", "value": 0},
        ],
        "states": [
            {"name": "FP", "value": 0},
            {"name": "MP", "value": 10},
        ],
        "special_buffs": [],
        "SPassive": [],
    }


def _apply_changes(char, changes):
    for target, change_type, name, value in changes:
        assert target is char
        if change_type == "APPLY_STATE":
            current = get_status_value(char, name)
            set_status_value(char, name, current + int(value))
        elif change_type == "REMOVE_BUFF":
            remove_buff(char, name)
        elif change_type == "APPLY_BUFF":
            apply_buff(
                char,
                name,
                value.get("lasting", 0),
                value.get("delay", 0),
                data=value.get("data"),
                count=value.get("count"),
            )


def test_apply_buff_gyoma_and_chikuryoku_stack_as_permanent():
    char = _build_char()

    apply_buff(char, "凝魔", 1, 0, data={"buff_id": "Bu-Gyoma"}, count=3)
    apply_buff(char, "凝魔", 1, 0, data={"buff_id": "Bu-Gyoma"}, count=2)
    apply_buff(char, "蓄力", 1, 0, data={"buff_id": "Bu-Chikuryoku"}, count=11)

    gyoma = next(b for b in char["special_buffs"] if b.get("name") == "凝魔")
    chikuryoku = next(b for b in char["special_buffs"] if b.get("name") == "蓄力")

    assert gyoma.get("count") == 5
    assert gyoma.get("lasting") == -1
    assert gyoma.get("is_permanent") is True
    assert chikuryoku.get("count") == 11
    assert chikuryoku.get("lasting") == -1
    assert chikuryoku.get("is_permanent") is True


def test_stack_bonus_floor_per_10_for_magic_and_physical():
    char = _build_char()
    apply_buff(char, "凝魔", -1, 0, data={"buff_id": "Bu-Gyoma"}, count=29)
    apply_buff(char, "蓄力", -1, 0, data={"buff_id": "Bu-Chikuryoku"}, count=9)

    assert get_status_value(char, "魔法補正") == 2
    assert get_status_value(char, "物理補正") == 0

    apply_buff(char, "蓄力", -1, 0, data={"buff_id": "Bu-Chikuryoku"}, count=11)
    assert get_status_value(char, "物理補正") == 2


def test_consume_buff_count_for_gain_success_and_insufficient():
    char = _build_char()
    apply_buff(char, "凝魔", -1, 0, data={"buff_id": "Bu-Gyoma"}, count=4)

    effects = [
        {
            "timing": "IMMEDIATE",
            "type": "CONSUME_BUFF_COUNT_FOR_GAIN",
            "target": "self",
            "buff_name": "凝魔",
            "consume_required": 3,
            "gains": [{"type": "FP", "value": 2}],
        }
    ]
    _, logs, changes = process_skill_effects(effects, "IMMEDIATE", char, None, context={"characters": [char]})
    _apply_changes(char, changes)

    gyoma = next(b for b in char["special_buffs"] if b.get("name") == "凝魔")
    assert gyoma.get("count") == 1
    assert get_status_value(char, "FP") == 2
    assert any("凝魔 3消費" in line for line in logs)

    effects_fail = [
        {
            "timing": "IMMEDIATE",
            "type": "CONSUME_BUFF_COUNT_FOR_GAIN",
            "target": "self",
            "buff_name": "凝魔",
            "consume_required": 3,
            "gains": [{"type": "FP", "value": 5}],
        }
    ]
    _, logs_fail, changes_fail = process_skill_effects(
        effects_fail, "IMMEDIATE", char, None, context={"characters": [char]}
    )
    _apply_changes(char, changes_fail)

    gyoma_after = next(b for b in char["special_buffs"] if b.get("name") == "凝魔")
    assert gyoma_after.get("count") == 1
    assert get_status_value(char, "FP") == 2
    assert any("凝魔不足" in line for line in logs_fail)


def test_consume_buff_count_for_power_uses_up_to_max_and_adds_final_power():
    char = _build_char()
    apply_buff(char, "凝魔", -1, 0, data={"buff_id": "Bu-Gyoma"}, count=7)

    effects = [
        {
            "timing": "PRE_MATCH",
            "type": "CONSUME_BUFF_COUNT_FOR_POWER",
            "target": "self",
            "buff_name": "凝魔",
            "consume_max": 5,
            "value_per_stack": 1,
            "apply_to": "final",
        }
    ]
    _, logs, changes = process_skill_effects(effects, "PRE_MATCH", char, None, context={"characters": [char]})
    _apply_changes(char, changes)

    final_power_changes = [c for c in changes if c[1] == "MODIFY_FINAL_POWER"]
    assert len(final_power_changes) == 1
    assert int(final_power_changes[0][3]) == 5

    gyoma = next(b for b in char["special_buffs"] if b.get("name") == "凝魔")
    assert gyoma.get("count") == 2
    assert any("最終威力+5" in line for line in logs)

    effects_fail = [
        {
            "timing": "PRE_MATCH",
            "type": "CONSUME_BUFF_COUNT_FOR_POWER",
            "target": "self",
            "buff_name": "凝魔",
            "consume_max": 5,
            "value_per_stack": 1,
            "apply_to": "final",
            "min_consume": 3,
        }
    ]
    _, logs_fail, changes_fail = process_skill_effects(
        effects_fail, "PRE_MATCH", char, None, context={"characters": [char]}
    )
    _apply_changes(char, changes_fail)

    assert not [c for c in changes_fail if c[1] == "MODIFY_FINAL_POWER"]
    gyoma_after = next(b for b in char["special_buffs"] if b.get("name") == "凝魔")
    assert gyoma_after.get("count") == 2
    assert any("凝魔不足" in line for line in logs_fail)
