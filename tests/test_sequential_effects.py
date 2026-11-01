"""Sequential effects evaluate pending changes without mutating real characters."""

import copy

import pytest

from manager.game_logic import get_status_value, process_skill_effects


@pytest.mark.parametrize("state_format", ["states", "flat"])
@pytest.mark.parametrize(
    ("initial", "expected_changes", "expected_final"),
    [(3, 2, 13), (2, 1, 7), (8, 2, 18)],
)
def test_sequential_condition_uses_pending_state_changes(
    state_format, initial, expected_changes, expected_final
):
    actor = {"id": "actor", "name": "Attacker"}
    target = {"id": "target", "name": "Target"}
    if state_format == "states":
        target["states"] = [{"name": "破裂", "value": initial}]
    else:
        target["破裂"] = initial
    before = copy.deepcopy(target)
    effects = [
        {
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "破裂",
            "value": 5,
        },
        {
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "破裂",
            "value": 5,
            "condition": {
                "source": "target",
                "param": "破裂",
                "operator": "GTE",
                "value": 8,
            },
        },
    ]

    bonus_damage, _logs, changes = process_skill_effects(
        effects, "HIT", actor, target
    )

    assert bonus_damage == 0
    assert len(changes) == expected_changes
    for character, operation, name, value in changes:
        assert character is target
        assert (operation, name, value) == ("APPLY_STATE", "破裂", 5)
    assert initial + sum(change[3] for change in changes) == expected_final
    assert target == before
    assert get_status_value(target, "破裂") == initial
