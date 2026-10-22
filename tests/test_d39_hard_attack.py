import pytest

from manager.battle import core
from tests.test_cost_payment_order import _setup, _skill
from tests.test_select_resolve_smoke import _add_slot, _set_intent


@pytest.mark.parametrize("winner_side", ["A", "B1"])
@pytest.mark.parametrize("winner_kind", ["hard_skill", "normal", "feint_skill", "evade"])
def test_hard_attack_after_loss_depends_on_winner_kind_not_slot_side(monkeypatch, winner_side, winner_kind):
    state, _ = _setup(monkeypatch, mass=False)
    catalog = core.all_skill_data
    winner_skill = "COST_A" if winner_side == "A" else "COST_B"
    loser_skill = "COST_B" if winner_side == "A" else "COST_A"
    catalog[winner_skill] = _skill(winner_skill, 20)
    catalog[loser_skill] = _skill(loser_skill, 5)
    catalog[loser_skill]["tags"] = ["攻撃", "hard_skill"]
    if winner_kind != "normal":
        catalog[winner_skill]["tags"].append(winner_kind)
    if winner_kind == "evade":
        catalog[winner_skill].update({"分類": "回避", "tags": ["守備", "回避"]})
    state["battle_state"]["phase"] = "resolve_single"
    core.run_select_resolve_auto("room_t", "battle_test")
    attacks = [t for t in state["battle_state"]["resolve"]["trace"] if t["kind"] == "hard_attack"]
    expected = winner_kind in {"hard_skill", "normal"}
    assert len(attacks) == int(expected)
    winner = state["characters"][0 if winner_side == "A" else 1]
    assert winner["hp"] == (95 if expected else 100)
    if attacks:
        assert "追撃" not in str(attacks)


def test_hard_skills_draw_does_not_trigger_hard_attack(monkeypatch):
    state, _ = _setup(monkeypatch, mass=False)
    for sid in ["COST_A", "COST_B"]:
        core.all_skill_data[sid] = {**_skill(sid, 10), "tags": ["攻撃", "hard_skill"]}
    state["battle_state"]["phase"] = "resolve_single"
    core.run_select_resolve_auto("room_t", "battle_test")
    assert not any(t["kind"] == "hard_attack" for t in state["battle_state"]["resolve"]["trace"])
    assert [c["hp"] for c in state["characters"][:2]] == [100, 100]


def test_hard_vs_hard_winner_can_evade_the_hard_attack(monkeypatch):
    state, _ = _setup(monkeypatch, mass=False)
    for sid, power in [("COST_A", 20), ("COST_B", 5)]:
        core.all_skill_data[sid] = {**_skill(sid, power), "tags": ["攻撃", "hard_skill"]}
    core.all_skill_data["DODGE"] = {**_skill("DODGE", 5), "分類": "回避", "tags": ["守備", "回避"]}
    from manager.battle import common_manager
    monkeypatch.setattr(common_manager, "all_skill_data", core.all_skill_data)
    _add_slot(state, "A_evade", "A1", "ally", 1)
    _set_intent(state, "A_evade", "A1", "DODGE", "single_slot", "B1")
    state["battle_state"]["phase"] = "resolve_single"
    core.run_select_resolve_auto("room_t", "battle_test")
    attacks = [t for t in state["battle_state"]["resolve"]["trace"] if t["kind"] == "hard_attack"]
    assert len(attacks) == 1
    assert state["characters"][0]["hp"] == 100
