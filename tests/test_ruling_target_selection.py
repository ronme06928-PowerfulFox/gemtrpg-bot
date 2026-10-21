import pytest

from manager.battle import core
from tests.test_cost_payment_order import _setup
from tests.test_select_resolve_smoke import _add_slot, _set_intent


@pytest.mark.parametrize("same_team", [False, True])
def test_re_evasion_covers_other_attackers_but_excludes_same_team(monkeypatch, same_team):
    state, _ = _setup(monkeypatch, mass=False)
    bs = state["battle_state"]
    defender = state["characters"][1]
    defender["special_buffs"] = [
        {"name": "再回避ロック", "buff_id": "Bu-05", "skill_id": "COST_B", "lasting": 1, "delay": 0}
    ]
    core.all_skill_data["COST_B"].update({"分類": "回避", "tags": ["守備", "回避"]})
    from manager.battle import common_manager
    monkeypatch.setattr(common_manager, "all_skill_data", core.all_skill_data)
    # The evasion declaration points at B2, rather than the incoming attacker A.
    bs["intents"]["B1"]["target"] = {"type": "single_slot", "slot_id": "B2"}
    if same_team:
        defender["type"] = "ally"
        bs["slots"]["B1"]["team"] = "ally"
    bs["phase"] = "resolve_single"
    core.run_select_resolve_auto("room_t", "battle_test")
    inserted = [t for t in bs["resolve"]["trace"]
                if t["kind"] == "evade_insert" and t["attacker_slot"] == "A"]
    assert bool(inserted) is (not same_team)
    if inserted:
        assert inserted[0]["defender_slot"] == "B1"


@pytest.mark.parametrize("second_initiative,expected", [(8, "B1"), (12, "B1_2")])
def test_mass_individual_candidate_uses_initiative_then_smaller_slot_id(monkeypatch, second_initiative, expected):
    state, _ = _setup(monkeypatch)
    _add_slot(state, "B1_2", "B1", "enemy", second_initiative)
    _set_intent(state, "B1_2", "B1", "COST_B", "single_slot", "A")
    bs = state["battle_state"]
    # Reverse declaration insertion order to ensure it cannot choose the winner.
    bs["intents"] = dict(reversed(list(bs["intents"].items())))
    bs["phase"] = "resolve_mass"
    core.run_select_resolve_auto("room_t", "battle_test")
    trace = next(t for t in bs["resolve"]["trace"]
                 if t["kind"] == "mass_individual" and t.get("target_actor_id") == "B1")
    assert trace["defender_slot"] == expected
