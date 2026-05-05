from manager.game_logic import process_skill_effects
from manager.utils import (
    GYOMA_BUFF_NAME,
    GYOMA_BUFF_ID,
    STACK_RESOURCE_VARIANT_BLOOD_PLASMA,
    apply_buff,
    get_stack_resource_variant,
    get_status_value,
    remove_buff,
    set_status_value,
)


def _build_char(char_id="char-1", team="ally"):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": 100,
        "mp": 10,
        "params": [
            {"label": "物理補正", "value": 0},
            {"label": "魔法補正", "value": 0},
        ],
        "states": [
            {"name": "FP", "value": 0},
            {"name": "MP", "value": 10},
            {"name": "出血", "value": 0},
        ],
        "special_buffs": [],
        "SPassive": [],
    }


def _apply_changes(changes):
    for target, change_type, name, value in changes:
        if change_type == "APPLY_STATE":
            current = get_status_value(target, name)
            set_status_value(target, name, current + int(value))
        elif change_type == "REMOVE_BUFF":
            remove_buff(target, name)
        elif change_type == "APPLY_BUFF":
            apply_buff(
                target,
                name,
                value.get("lasting", 0),
                value.get("delay", 0),
                data=value.get("data"),
                count=value.get("count"),
            )


def _find_gyoma(char_obj):
    for buff in char_obj.get("special_buffs", []):
        if buff.get("name") == GYOMA_BUFF_NAME:
            return buff
    return None


def test_convert_stack_resource_variant_requires_existing_stack():
    actor = _build_char("actor")
    effects = [
        {
            "timing": "PRE_MATCH",
            "type": "CONVERT_STACK_RESOURCE_VARIANT",
            "target": "self",
            "resource_name": "gyoma",
            "to_variant": STACK_RESOURCE_VARIANT_BLOOD_PLASMA,
            "require_count_gte": 1,
        }
    ]
    _, _logs, changes = process_skill_effects(effects, "PRE_MATCH", actor, None, context={"characters": [actor]})
    _apply_changes(changes)

    assert _find_gyoma(actor) is None
    assert get_stack_resource_variant(actor, "gyoma") == "normal"


def test_convert_stack_resource_variant_preserves_count_and_overwrites_variant():
    actor = _build_char("actor")
    apply_buff(actor, GYOMA_BUFF_NAME, -1, 0, data={"buff_id": GYOMA_BUFF_ID, "variant": "foo"}, count=23)

    effects = [
        {
            "timing": "PRE_MATCH",
            "type": "CONVERT_STACK_RESOURCE_VARIANT",
            "target": "self",
            "resource_name": "gyoma",
            "to_variant": STACK_RESOURCE_VARIANT_BLOOD_PLASMA,
            "require_count_gte": 1,
        }
    ]
    _, _logs, changes = process_skill_effects(effects, "PRE_MATCH", actor, None, context={"characters": [actor]})
    _apply_changes(changes)

    gyoma = _find_gyoma(actor)
    assert gyoma is not None
    assert int(gyoma.get("count", 0)) == 23
    assert get_stack_resource_variant(actor, "gyoma") == STACK_RESOURCE_VARIANT_BLOOD_PLASMA


def test_blood_plasma_disables_magic_stat_bonus_and_persists_on_gain_and_consume():
    actor = _build_char("actor")
    apply_buff(actor, GYOMA_BUFF_NAME, -1, 0, data={"buff_id": GYOMA_BUFF_ID, "variant": STACK_RESOURCE_VARIANT_BLOOD_PLASMA}, count=20)
    assert get_status_value(actor, "魔法補正") == 0

    apply_buff(actor, GYOMA_BUFF_NAME, -1, 0, data={"buff_id": GYOMA_BUFF_ID}, count=5)
    assert get_stack_resource_variant(actor, "gyoma") == STACK_RESOURCE_VARIANT_BLOOD_PLASMA
    assert get_status_value(actor, "魔法補正") == 0

    consume_effects = [
        {
            "timing": "PRE_MATCH",
            "type": "CONSUME_BUFF_COUNT_FOR_POWER",
            "target": "self",
            "buff_name": GYOMA_BUFF_NAME,
            "consume_max": 3,
            "value_per_stack": 1,
            "apply_to": "final",
        }
    ]
    _, _logs, changes = process_skill_effects(consume_effects, "PRE_MATCH", actor, None, context={"characters": [actor]})
    _apply_changes(changes)
    assert get_stack_resource_variant(actor, "gyoma") == STACK_RESOURCE_VARIANT_BLOOD_PLASMA


def test_blood_plasma_adds_bleed_apply_bonus_only_for_other_target():
    actor = _build_char("actor")
    target = _build_char("target", team="enemy")
    apply_buff(actor, GYOMA_BUFF_NAME, -1, 0, data={"buff_id": GYOMA_BUFF_ID, "variant": STACK_RESOURCE_VARIANT_BLOOD_PLASMA}, count=21)

    effects = [
        {"timing": "HIT", "type": "APPLY_STATE", "target": "target", "state_name": "出血", "value": 2},
        {"timing": "HIT", "type": "APPLY_STATE", "target": "self", "state_name": "出血", "value": 2},
    ]
    _, _logs, changes = process_skill_effects(effects, "HIT", actor, target, context={"characters": [actor, target]})
    _apply_changes(changes)

    assert get_status_value(target, "出血") == 4
    assert get_status_value(actor, "出血") == 2


def test_blood_plasma_is_included_in_self_bleed_reference_param():
    actor = _build_char("actor")
    target = _build_char("target", team="enemy")
    set_status_value(actor, "出血", 3)
    apply_buff(actor, GYOMA_BUFF_NAME, -1, 0, data={"buff_id": GYOMA_BUFF_ID, "variant": STACK_RESOURCE_VARIANT_BLOOD_PLASMA}, count=12)

    effects = [
        {
            "timing": "HIT",
            "type": "APPLY_STATE_PER_N",
            "target": "target",
            "source": "self",
            "source_param": "出血",
            "per_N": 1,
            "state_name": "出血",
            "value": 1,
        }
    ]
    _, _logs, changes = process_skill_effects(effects, "HIT", actor, target, context={"characters": [actor, target]})
    _apply_changes(changes)

    # source_param 出血 = 3 + 血漿スタック12。さらに血漿の出血付与ボーナス floor(12/10)=1 を加算。
    assert get_status_value(target, "出血") == 16

