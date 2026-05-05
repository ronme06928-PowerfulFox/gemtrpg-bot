from manager.game_logic import process_skill_effects
from manager.utils import apply_buff, get_stack_resource_count


def _build_char(char_id: str, team: str):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": 73,
        "max_hp": 100,
        "mp": 10,
        "states": [{"name": "HP", "value": 73}],
        "special_buffs": [],
        "SPassive": [],
    }


def _apply_changes(changes):
    for target, change_type, name, value in changes:
        if change_type != "APPLY_BUFF":
            continue
        apply_buff(
            target,
            name,
            value.get("lasting", 0),
            value.get("delay", 0),
            data=value.get("data"),
            count=value.get("count"),
        )


def test_apply_buff_per_n_uses_lost_hp_as_source_param():
    actor = _build_char("actor", "ally")
    target = _build_char("target", "enemy")
    context = {"characters": [actor, target]}

    effects = [
        {
            "timing": "PRE_MATCH",
            "type": "APPLY_BUFF_PER_N",
            "target": "self",
            "source": "self",
            "source_param": "lost_hp",
            "per_N": 10,
            "value": 1,
            "buff_id": "Bu-31",
            "max_count": 99,
        }
    ]

    _, _, changes = process_skill_effects(
        effects, "PRE_MATCH", actor, target, None, context=context, base_damage=0
    )
    _apply_changes(changes)

    # lost_hp = 100 - 73 = 27, per_N=10 => floor(27/10)=2 stacks
    assert get_stack_resource_count(actor, "gyoma") == 2
