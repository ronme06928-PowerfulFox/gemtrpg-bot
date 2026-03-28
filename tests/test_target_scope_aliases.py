from events.battle import common_routes
from manager.battle import pve_intent_planner
from manager.battle import skill_rules


def _state_for_scope_check():
    return {
        "slots": {
            "S_ALLY": {"slot_id": "S_ALLY", "actor_id": "A1", "team": "ally"},
            "S_ENEMY": {"slot_id": "S_ENEMY", "actor_id": "E1", "team": "enemy"},
        },
        "characters": [
            {"id": "A1", "type": "ally"},
            {"id": "E1", "type": "enemy"},
        ],
    }


def test_common_routes_infers_same_team_target_scope(monkeypatch):
    monkeypatch.setattr(common_routes, "all_skill_data", {"S1": {"target_scope": "same_team"}})
    assert common_routes._infer_target_scope_from_skill("S1") == "ally"


def test_common_routes_infers_opposing_team_target_scope(monkeypatch):
    monkeypatch.setattr(common_routes, "all_skill_data", {"S1": {"target_scope": "opposing_team"}})
    assert common_routes._infer_target_scope_from_skill("S1") == "enemy"


def test_common_routes_scope_validation_accepts_opposing_team(monkeypatch):
    monkeypatch.setattr(common_routes, "all_skill_data", {"S1": {"target_scope": "opposing_team"}})
    state = _state_for_scope_check()
    target, err = common_routes._normalize_target_by_skill(
        "S1",
        {"type": "single_slot", "slot_id": "S_ALLY"},
        state=state,
        source_slot_id="S_ENEMY",
        allow_none=False,
    )
    assert err is None
    assert target == {"type": "single_slot", "slot_id": "S_ALLY"}


def test_common_routes_scope_validation_blocks_cross_team_for_same_team(monkeypatch):
    monkeypatch.setattr(common_routes, "all_skill_data", {"S1": {"target_scope": "same_team"}})
    state = _state_for_scope_check()
    target, err = common_routes._normalize_target_by_skill(
        "S1",
        {"type": "single_slot", "slot_id": "S_ALLY"},
        state=state,
        source_slot_id="S_ENEMY",
        allow_none=False,
    )
    assert target is None
    assert "target_scope=ally" in str(err)


def test_skill_rules_normalize_target_scope_supports_new_aliases():
    assert skill_rules._normalize_target_scope("same_team") == "ally"
    assert skill_rules._normalize_target_scope("opposing_team") == "enemy"


def test_pve_intent_planner_normalize_target_scope_supports_new_aliases():
    assert pve_intent_planner._normalize_target_scope("same_team") == "ally"
    assert pve_intent_planner._normalize_target_scope("opposing_team") == "enemy"
