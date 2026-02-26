import manager.battle.enemy_behavior as behavior_module
from manager.battle.enemy_behavior import (
    normalize_behavior_profile,
    initialize_behavior_runtime_entry,
    evaluate_transitions,
    pick_step_actions,
    advance_step_pointer,
    choose_actions_for_slot_count,
)


def _profile():
    return {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [
                    {"actions": ["S-A"]},
                    {"actions": ["S-B", "S-C"]},
                ],
                "transitions": [
                    {
                        "priority": 10,
                        "when_all": [
                            {"source": "self", "param": "HP", "operator": "LTE", "value": 50}
                        ],
                        "to_loop_id": "phase_2",
                        "reset_step_index": True,
                    }
                ],
            },
            "phase_2": {
                "repeat": True,
                "steps": [{"actions": ["S-Z"]}],
                "transitions": [],
            },
        },
    }


def test_normalize_behavior_profile_min_shape():
    normalized = normalize_behavior_profile({"enabled": True, "loops": {"L1": {"steps": [{"actions": "S1"}]}}})
    assert normalized["enabled"] is True
    assert normalized["version"] == 1
    assert normalized["initial_loop_id"] == "L1"
    assert normalized["loops"]["L1"]["steps"][0]["actions"] == ["S1"]


def test_evaluate_transitions_moves_loop_when_condition_matches():
    prof = normalize_behavior_profile(_profile())
    runtime = initialize_behavior_runtime_entry(prof, runtime_entry={"active_loop_id": "phase_1", "step_index": 1}, round_value=2)
    actor = {"id": "E1", "type": "enemy", "hp": 40, "states": [], "params": []}
    result = evaluate_transitions(prof, runtime, actor_char=actor, state={"round": 2}, battle_state={"round": 2})
    next_runtime = result["runtime"]
    assert result["changed"] is True
    assert next_runtime["active_loop_id"] == "phase_2"
    assert int(next_runtime["step_index"]) == 0


def test_pick_and_advance_step_pointer_repeat():
    prof = normalize_behavior_profile(_profile())
    runtime = initialize_behavior_runtime_entry(prof, runtime_entry={"active_loop_id": "phase_1", "step_index": 0})
    picked_1 = pick_step_actions(prof, runtime)
    assert picked_1["actions"] == ["S-A"]

    runtime_2 = advance_step_pointer(prof, picked_1["runtime"])
    picked_2 = pick_step_actions(prof, runtime_2)
    assert picked_2["actions"] == ["S-B", "S-C"]

    runtime_3 = advance_step_pointer(prof, picked_2["runtime"])
    picked_3 = pick_step_actions(prof, runtime_3)
    assert picked_3["actions"] == ["S-A"]


def test_choose_actions_for_slot_count_reuses_last():
    actions = choose_actions_for_slot_count(["S-A", "S-B"], 4)
    assert actions == ["S-A", "S-B", "S-B", "S-B"]


def test_choose_actions_for_slot_count_random_when_overflow(monkeypatch):
    monkeypatch.setattr(behavior_module.random, "sample", lambda seq, k: ["S-D", "S-B"])
    actions = choose_actions_for_slot_count(["S-A", "S-B", "S-C", "S-D"], 2)
    assert actions == ["S-D", "S-B"]
