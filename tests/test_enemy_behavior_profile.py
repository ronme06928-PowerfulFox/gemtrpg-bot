import manager.battle.enemy_behavior as behavior_module
from manager.battle.enemy_behavior import (
    normalize_behavior_profile,
    initialize_behavior_runtime_entry,
    evaluate_transitions,
    pick_step_actions,
    advance_step_pointer,
    choose_actions_for_slot_count,
    choose_action_plans_for_slot_count,
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


def test_choose_actions_for_slot_count_fills_missing_with_no_action():
    actions = choose_actions_for_slot_count(["S-A", "S-B"], 4)
    assert actions == ["S-A", "S-B", None, None]


def test_choose_actions_for_slot_count_single_action_does_not_duplicate():
    actions = choose_actions_for_slot_count(["S-A"], 2)
    assert actions == ["S-A", None]


def test_choose_actions_for_slot_count_random_when_overflow(monkeypatch):
    monkeypatch.setattr(behavior_module.random, "sample", lambda seq, k: [seq[3], seq[1]])
    actions = choose_actions_for_slot_count(["S-A", "S-B", "S-C", "S-D"], 2)
    assert actions == ["S-D", "S-B"]


def test_pick_step_actions_includes_target_policies():
    profile = normalize_behavior_profile({
        "enabled": True,
        "initial_loop_id": "loop_1",
        "loops": {
            "loop_1": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-A", "S-B"],
                    "targets": ["target_enemy_fastest", "target_ally_random"],
                }],
                "transitions": [],
            }
        },
    })
    runtime = initialize_behavior_runtime_entry(profile, runtime_entry={"active_loop_id": "loop_1", "step_index": 0})
    picked = pick_step_actions(profile, runtime)
    assert picked["actions"] == ["S-A", "S-B"]
    assert picked["targets"] == ["target_enemy_fastest", "target_ally_random"]
    assert picked["plans"][0]["target_policy"] == "target_enemy_fastest"
    assert picked["plans"][1]["target_policy"] == "target_ally_random"
    assert picked["step_transition"] is None


def test_pick_step_actions_exposes_step_transition():
    profile = normalize_behavior_profile({
        "enabled": True,
        "initial_loop_id": "loop_1",
        "loops": {
            "loop_1": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-A"],
                    "next_loop_id": "loop_2",
                    "next_reset_step_index": True,
                }],
                "transitions": [],
            },
            "loop_2": {
                "repeat": True,
                "steps": [{"actions": ["S-B"]}],
                "transitions": [],
            },
        },
    })
    runtime = initialize_behavior_runtime_entry(profile, runtime_entry={"active_loop_id": "loop_1", "step_index": 0})
    picked = pick_step_actions(profile, runtime)
    assert picked["actions"] == ["S-A"]
    assert picked["step_transition"] == {"to_loop_id": "loop_2", "reset_step_index": True}


def test_advance_step_pointer_applies_step_transition_before_normal_advance():
    profile = normalize_behavior_profile({
        "enabled": True,
        "initial_loop_id": "loop_1",
        "loops": {
            "loop_1": {
                "repeat": True,
                "steps": [{"actions": ["S-A"]}],
                "transitions": [],
            },
            "loop_2": {
                "repeat": True,
                "steps": [{"actions": ["S-B"]}, {"actions": ["S-C"]}],
                "transitions": [],
            },
        },
    })
    runtime = initialize_behavior_runtime_entry(profile, runtime_entry={"active_loop_id": "loop_1", "step_index": 0})
    advanced = advance_step_pointer(
        profile,
        runtime,
        step_transition={"to_loop_id": "loop_2", "reset_step_index": True},
    )
    assert advanced["active_loop_id"] == "loop_2"
    assert int(advanced["step_index"]) == 0


def test_choose_action_plans_for_slot_count_random_when_overflow(monkeypatch):
    source = [
        {"skill_id": "S-A", "target_policy": "target_enemy_random"},
        {"skill_id": "S-B", "target_policy": "target_enemy_fastest"},
        {"skill_id": "S-C", "target_policy": "target_ally_random"},
    ]
    monkeypatch.setattr(behavior_module.random, "sample", lambda seq, k: [seq[2], seq[0]])
    picked = choose_action_plans_for_slot_count(source, 2)
    assert [row["skill_id"] for row in picked] == ["S-C", "S-A"]
    assert [row["target_policy"] for row in picked] == ["target_ally_random", "target_enemy_random"]
