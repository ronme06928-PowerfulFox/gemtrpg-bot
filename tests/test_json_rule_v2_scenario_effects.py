import pytest

from manager.json_rule_v2 import JsonRuleV2Error, normalize_skill_rule_object


def _rule(effect):
    return {
        "schema": "skill_json_rule_v2",
        "effects": [effect],
        "power_bonus": [],
    }


def test_schedule_effect_contract_is_normalized():
    normalized = normalize_skill_rule_object(
        _rule(
            {
                "timing": "RESOLVE_START",
                "type": "SCHEDULE_EFFECT",
                "target": "self",
                "round_offset": "1",
                "repeat_count": "2",
                "effect": {
                    "type": "summon_character",
                    "summon_template_id": "U-02",
                },
            }
        )
    )

    effect = normalized["effects"][0]
    assert effect["round_offset"] == 1
    assert effect["repeat_count"] == 2
    assert effect["effect"]["type"] == "SUMMON_CHARACTER"


@pytest.mark.parametrize(
    "effect",
    [
        {"timing": "RESOLVE_START", "type": "SCHEDULE_EFFECT"},
        {
            "timing": "RESOLVE_START",
            "type": "SCHEDULE_EFFECT",
            "effect": {"type": "SUMMON_CHARACTER"},
            "round_offset": 0,
        },
        {
            "timing": "RESOLVE_START",
            "type": "APPLY_BUFF_FROM_CHARACTER_COUNT",
            "buff_name": "吸収",
        },
        {
            "timing": "RESOLVE_START",
            "type": "CUSTOM_EFFECT",
            "target": "FILTERED_CHARACTERS",
            "value": "DEAL_TARGET_MAX_HP_DAMAGE",
        },
    ],
)
def test_scenario_effect_contract_rejects_incomplete_rows(effect):
    with pytest.raises(JsonRuleV2Error):
        normalize_skill_rule_object(_rule(effect))
