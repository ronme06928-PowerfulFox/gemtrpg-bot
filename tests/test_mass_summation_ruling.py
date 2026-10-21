import pytest

from manager.battle import core
from tests.test_cost_payment_order import _setup, _skill
from tests.test_select_resolve_smoke import _state_value, _add_slot, _set_intent


def _summation(monkeypatch, attack_power=40, participants=2, category="物理"):
    state, routes = _setup(monkeypatch, participants=participants)
    bs = state["battle_state"]
    bs["intents"]["A"]["tags"]["mass_type"] = "mass_summation"
    bs["intents"]["A"]["target"]["type"] = "mass_summation"
    catalog = core.all_skill_data
    catalog["COST_A"] = _skill("COST_A", attack_power, fp=2, mp=3)
    catalog["COST_B"].update({"分類": category, "tags": ["攻撃"] if category == "物理" else ["守備", category]})
    rows = routes._consume_mass_costs_on_resolve_start("room_t", bs, set(bs["slots"]))
    assert rows[0]["spent"] == {"hp": 0, "mp": 3, "fp": 2}
    assert routes._consume_mass_costs_on_resolve_start("room_t", bs, set(bs["slots"])) == []
    bs["phase"] = "resolve_mass"
    return state, routes


@pytest.mark.parametrize("attack_power,outcome", [(40, "attacker_win"), (10, "defender_win"), (30, "draw")])
@pytest.mark.parametrize("category", ["物理", "防御", "回避"])
def test_mass_summation_pays_each_participant_and_grants_collective_win_fp(monkeypatch, attack_power, outcome, category):
    state, _ = _summation(monkeypatch, attack_power=attack_power, category=category)
    core.run_select_resolve_auto("room_t", "battle_test")
    a, b1, b2, observer = state["characters"]
    assert (a["mp"], _state_value(a, "FP")) == (47, 18 + (outcome == "attacker_win"))
    for participant in [b1, b2]:
        assert participant["mp"] == 48
        assert _state_value(participant, "FP") == 19 + (outcome == "defender_win")
    assert (observer["mp"], _state_value(observer, "FP")) == (50, 20)
    traces = [t for t in state["battle_state"]["resolve"]["trace"] if t["kind"] == "mass_summation"]
    assert len(traces) == 1
    assert traces[0]["outcome"] == outcome
    assert traces[0]["participants"] == ["B1", "B2"]
    assert traces[0]["cost"] == {"hp": 0, "mp": 4, "fp": 2}
    before = [(c["hp"], c["mp"], _state_value(c, "FP")) for c in state["characters"]]
    core.run_select_resolve_auto("room_t", "battle_test")
    assert [(c["hp"], c["mp"], _state_value(c, "FP")) for c in state["characters"]] == before


def test_mass_summation_only_selected_slot_pays_and_paid_before_power_roll(monkeypatch):
    state, _ = _summation(monkeypatch)
    _add_slot(state, "B1_slow", "B1", "enemy", 1)
    _set_intent(state, "B1_slow", "B1", "COST_B", "single_slot", "A")
    observed = []
    original_roll = core._roll_power_for_slot

    def roll(bs, slot_id, **kwargs):
        if slot_id in ["B1", "B2"]:
            actor = next(c for c in state["characters"] if c["id"] == slot_id)
            observed.append((slot_id, actor["mp"], _state_value(actor, "FP")))
        return original_roll(bs, slot_id, **kwargs)

    monkeypatch.setattr(core, "_roll_power_for_slot", roll)
    # Inspect mass phase before the unselected slot can execute its later single action.
    from manager.battle.resolve_auto_mass_phase import run_mass_phase
    bs = state["battle_state"]
    bs["resolve"]["mass_queue"] = ["A"]
    bs["__room_name"] = "room_t"
    run_mass_phase("room_t", "battle_test", state, bs, bs["intents"], {c["id"]: c for c in state["characters"]})
    assert observed == [("B1", 48, 19), ("B2", 48, 19)]
    assert "B1_slow" not in bs["resolve"]["resolved_slots"]


@pytest.mark.parametrize("reason", ["unplaced", "incapacitated"])
def test_mass_fizzle_after_prepayment_does_not_refund(monkeypatch, reason):
    state, _ = _summation(monkeypatch)
    a = state["characters"][0]
    if reason == "unplaced":
        a["x"] = -1
    else:
        a["hp"] = 0
    core.run_select_resolve_auto("room_t", "battle_test")
    assert (a["mp"], _state_value(a, "FP")) == (47, 18)
    assert any(t["kind"] == "fizzle" and t["attacker_slot"] == "A"
               for t in state["battle_state"]["resolve"]["trace"])


@pytest.mark.parametrize("payment", ["free_cost", "prepaid", "hp"])
def test_mass_summation_uses_single_clash_payment_rules(monkeypatch, payment):
    state, _ = _summation(monkeypatch, attack_power=30)
    bs = state["battle_state"]
    skill = core.all_skill_data["COST_B"]
    if payment == "free_cost":
        skill["tags"].append("free_cost")
    elif payment == "prepaid":
        for slot in ["B1", "B2"]:
            bs["intents"][slot]["cost_consumed_at_resolve_start"] = True
    else:
        skill["rule_data"]["cost"] = [{"type": "HP", "value": 3}]
    core.run_select_resolve_auto("room_t", "battle_test")
    for participant in state["characters"][1:3]:
        assert participant["hp"] == (97 if payment == "hp" else 100)
        assert participant["mp"] == 50
        assert _state_value(participant, "FP") == 20
    trace = next(t for t in bs["resolve"]["trace"] if t["kind"] == "mass_summation")
    assert trace["cost"] == {"hp": 6 if payment == "hp" else 0, "mp": 0, "fp": 0}


def test_mass_summation_win_effect_fp_is_separate_from_victory_fp(monkeypatch):
    import json
    state, _ = _summation(monkeypatch, attack_power=10)
    skill = core.all_skill_data["COST_B"]
    skill["rule_data"]["effects"] = [
        {"timing": "WIN", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 2}
    ]
    skill["特記処理"] = json.dumps(skill["rule_data"])
    core.run_select_resolve_auto("room_t", "battle_test")
    assert [_state_value(c, "FP") for c in state["characters"][1:3]] == [22, 22]
