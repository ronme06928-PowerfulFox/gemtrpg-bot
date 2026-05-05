from manager.game_logic import process_skill_effects
from manager.utils import apply_buff, get_status_value, remove_buff, set_status_value


def _build_char(name):
    return {
        "id": name,
        "name": name,
        "type": "ally",
        "hp": 100,
        "mp": 10,
        "states": [{"name": "FP", "value": 0}, {"name": "MP", "value": 10}],
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


def test_consume_gain_apply_buff_by_buff_id_ms13_path():
    actor = _build_char("actor")
    target = _build_char("target")
    apply_buff(actor, "凝魔", -1, 0, data={"buff_id": "Bu-31"}, count=10)

    effects = [
        {
            "timing": "HIT",
            "type": "CONSUME_BUFF_COUNT_FOR_GAIN",
            "target": "self",
            "buff_name": "凝魔",
            "consume_required": 10,
            "gains": [{"type": "APPLY_BUFF", "target": "target", "buff_id": "Bu-08", "lasting": 3}],
        }
    ]

    _, _, changes = process_skill_effects(effects, "HIT", actor, target, context={"characters": [actor, target]})

    target_changes = [c for c in changes if c[0] is target and c[1] == "APPLY_BUFF"]
    assert target_changes, "target should receive APPLY_BUFF from gains buff_id"
    _, _, applied_name, payload = target_changes[0]
    assert applied_name == "出血遷延"
    assert int(payload.get("lasting", 0)) == 3
    assert (payload.get("data") or {}).get("buff_id") == "Bu-08"

    _apply_changes(target, target_changes)
    applied = next((b for b in target.get("special_buffs", []) if b.get("buff_id") == "Bu-08"), None)
    assert applied is not None
    assert int(applied.get("count", 0)) == 3
