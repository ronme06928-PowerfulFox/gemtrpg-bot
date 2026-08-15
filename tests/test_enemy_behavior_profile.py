import manager.battle.enemy_behavior as behavior_module
from manager.battle.enemy_behavior import (
    normalize_behavior_profile,
    initialize_behavior_runtime_entry,
    evaluate_transitions,
    pick_step_actions,
    advance_step_pointer,
    choose_actions_for_slot_count,
    choose_action_plans_for_slot_count,
    normalize_target_candidates,
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
    assert normalized["slot_generation_mode"] == "character_action_count"
    assert normalized["loops"]["L1"]["steps"][0]["on_no_target"] == ["cancel"]


def test_normalize_behavior_profile_preserves_step_action_mode_and_aligns_no_target():
    normalized = normalize_behavior_profile({
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "loops": {
            "L1": {
                "steps": [{
                    "actions": ["S1", "S2"],
                    "on_no_target": ["cancel", "unknown"],
                }],
            },
        },
    })

    assert normalized["slot_generation_mode"] == "step_actions"
    step = normalized["loops"]["L1"]["steps"][0]
    assert step["on_no_target"] == ["cancel", "cancel"]
    picked = pick_step_actions(
        normalized,
        {"active_loop_id": "L1", "step_index": 0},
    )
    assert [row["on_no_target"] for row in picked["plans"]] == ["cancel", "cancel"]


def test_pick_step_actions_preserves_explicit_no_action_token():
    normalized = normalize_behavior_profile({
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "loops": {"L1": {"steps": [{"actions": ["S1", "__NO_ACTION__", "S2"]}]}},
    })

    picked = pick_step_actions(normalized, {"active_loop_id": "L1", "step_index": 0})

    assert [row["action_type"] for row in picked["plans"]] == ["skill", "no_action", "skill"]
    assert picked["plans"][1]["skill_id"] is None


def test_evaluate_transitions_moves_loop_when_condition_matches():
    prof = normalize_behavior_profile(_profile())
    runtime = initialize_behavior_runtime_entry(prof, runtime_entry={"active_loop_id": "phase_1", "step_index": 1}, round_value=2)
    actor = {"id": "E1", "type": "enemy", "hp": 40, "states": [], "params": []}
    result = evaluate_transitions(prof, runtime, actor_char=actor, state={"round": 2}, battle_state={"round": 2})
    next_runtime = result["runtime"]
    assert result["changed"] is True
    assert next_runtime["active_loop_id"] == "phase_2"
    assert int(next_runtime["step_index"]) == 0


def _hp_percent_profile(operator="LTE", value=40):
    profile = _profile()
    profile["loops"]["phase_1"]["transitions"][0]["when_all"] = [
        {"source": "self", "param": "HP割合", "operator": operator, "value": value}
    ]
    return normalize_behavior_profile(profile)


def test_behavior_transition_can_compare_current_hp_percentage():
    actor = {"id": "E1", "type": "enemy", "hp": 40, "maxHp": 100, "states": [], "params": []}
    runtime = {"active_loop_id": "phase_1", "step_index": 0}

    at_boundary = evaluate_transitions(
        _hp_percent_profile("LTE", 40), runtime, actor_char=actor, battle_state={"round": 1}
    )
    below_boundary = evaluate_transitions(
        _hp_percent_profile("LT", 40), runtime, actor_char=actor, battle_state={"round": 1}
    )

    assert at_boundary["runtime"]["active_loop_id"] == "phase_2"
    assert below_boundary["runtime"]["active_loop_id"] == "phase_1"


def test_behavior_hp_percentage_condition_requires_positive_max_hp():
    profile = _hp_percent_profile("LTE", 40)
    runtime = {"active_loop_id": "phase_1", "step_index": 0}

    for actor in (
        {"hp": 0},
        {"hp": 0, "maxHp": 0},
        {"hp": 0, "maxHp": "invalid"},
    ):
        result = evaluate_transitions(
            profile, runtime, actor_char=actor, battle_state={"round": 1}
        )
        assert result["runtime"]["active_loop_id"] == "phase_1"


def test_behavior_hp_percentage_condition_accepts_legacy_alias():
    actor = {"hp": 25, "max_hp": 100}
    runtime = {"active_loop_id": "phase_1", "step_index": 0}
    profile = _profile()
    profile["loops"]["phase_1"]["transitions"][0]["when_all"] = [
        {"source": "self", "param": "hp_percent", "operator": "LTE", "value": 25}
    ]

    result = evaluate_transitions(
        normalize_behavior_profile(profile), runtime, actor_char=actor, battle_state={"round": 1}
    )
    assert result["runtime"]["active_loop_id"] == "phase_2"


def _speed_condition_profile(param_name):
    return {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{"actions": ["S-A"]}],
                "transitions": [
                    {
                        "priority": 10,
                        "when_all": [
                            {"source": "self", "param": param_name, "operator": "GTE", "value": 8}
                        ],
                        "to_loop_id": "phase_2",
                        "reset_step_index": True,
                    }
                ],
            },
            "phase_2": {"repeat": True, "steps": [{"actions": ["S-Z"]}], "transitions": []},
        },
    }


def _fires_on_agility_param(condition_param, stored_label):
    prof = normalize_behavior_profile(_speed_condition_profile(condition_param))
    runtime = initialize_behavior_runtime_entry(
        prof, runtime_entry={"active_loop_id": "phase_1", "step_index": 0}, round_value=1
    )
    actor = {
        "id": "E1",
        "type": "enemy",
        "hp": 100,
        "states": [],
        "params": [{"label": stored_label, "value": 9}],
    }
    result = evaluate_transitions(
        prof, runtime, actor_char=actor, state={"round": 1}, battle_state={"round": 1}
    )
    return result["runtime"]["active_loop_id"] == "phase_2"


def test_behavior_condition_matches_agility_param_across_legacy_names():
    """行動チャートの条件キーと params のラベルが新旧どちらでも噛み合うこと。"""
    # 新旧の組み合わせ4通りすべてで条件が成立する。
    assert _fires_on_agility_param("敏捷", "敏捷") is True
    assert _fires_on_agility_param("速度", "敏捷") is True
    assert _fires_on_agility_param("敏捷", "速度") is True
    assert _fires_on_agility_param("速度", "速度") is True


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


def test_normalize_behavior_profile_preserves_legacy_and_normalizes_ordered_candidates():
    profile = normalize_behavior_profile({
        "enabled": True,
        "loops": {
            "loop_1": {
                "steps": [{
                    "actions": ["S-OLD", "S-NEW"],
                    "targets": [
                        "target_enemy_fastest",
                        [
                            {
                                "team": "same_team",
                                "required_tag_ids": [" 瓦礫 ", "瓦礫", "機械"],
                                "selection": "slowest",
                            },
                            {
                                "team": "opposing_team",
                                "required_tag_ids": [],
                                "selection": "random",
                            },
                        ],
                    ],
                }],
            },
        },
    })

    targets = profile["loops"]["loop_1"]["steps"][0]["targets"]
    assert targets[0] == "target_enemy_fastest"
    assert targets[1] == [
        {
            "team": "same_team",
            "required_tag_ids": ["瓦礫", "機械"],
            "selection": "slowest",
        },
        {
            "team": "opposing_team",
            "required_tag_ids": [],
            "selection": "random",
        },
    ]

    picked = pick_step_actions(profile, {"active_loop_id": "loop_1", "step_index": 0})
    assert picked["plans"][0]["target_is_legacy"] is True
    assert picked["plans"][1]["target_is_legacy"] is False
    assert picked["plans"][1]["target_candidates"] == targets[1]


def test_normalize_target_candidates_accepts_wrapper_and_policy_aliases():
    assert normalize_target_candidates({
        "candidates": [
            {"team": "ally", "required_tags": ["機械"], "method": "fastest"},
            "target_enemy_slowest",
        ]
    }) == [
        {
            "team": "same_team",
            "required_tag_ids": ["機械"],
            "selection": "fastest",
        },
        {
            "team": "opposing_team",
            "required_tag_ids": [],
            "selection": "slowest",
        },
    ]
