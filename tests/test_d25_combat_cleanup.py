import pytest

from manager.battle.combat_session import start_combat_session, conclude_combat_session
from tests.test_combat_session_phase1 import _character


@pytest.mark.parametrize("transition", ["start", "conclude"])
def test_combat_boundary_removes_summons_and_entangle_without_touching_resources(transition):
    actor = _character("owner", "Owner")
    actor["states"].append({"name": "荊棘重絡", "value": 3})
    summons = [_character("summon1", "S1", is_summoned=True, summon_duration_mode="permanent"),
               _character("summon2", "S2", is_summoned=True, summon_duration_mode="duration_rounds")]
    state = {"characters": [actor, *summons], "combat_phase": "ready" if transition == "start" else "active",
             "character_owners": {"owner": "User", "summon1": "User", "summon2": "User"},
             "battle_state": {"slots": {"old": {}}, "resolve": {}}, "timeline": [{"char_id": "summon1"}]}
    before = {key: actor[key] for key in ("hp", "mp", "FP", "x", "y")}
    result = start_combat_session(state, "GM") if transition == "start" else conclude_combat_session(state, "GM", "VICTORY")
    assert result
    assert [c["id"] for c in state["characters"]] == ["owner"]
    assert state["character_owners"] == {"owner": "User"}
    assert next(s["value"] for s in actor["states"] if s["name"] == "荊棘重絡") == 0
    assert {key: actor[key] for key in before} == before
    assert actor["special_buffs"] == actor["initial_state"]["special_buffs"]
    assert actor["granted_skills"] == []
    assert actor["commands"] == "【BASE】"
    assert state["timeline"] == [] and state["battle_state"]["slots"] == {}


def test_conclusion_archives_summon_contribution_before_removal():
    from manager.battle.combat_session import record_combat_damage
    owner = _character("owner", "Owner")
    target = _character("target", "Target")
    state = {"characters": [owner, target], "combat_phase": "ready"}
    start_combat_session(state, "GM")
    summon = _character("summon", "Summon", is_summoned=True, summoner_id="owner")
    state["characters"].append(summon)
    record_combat_damage(state, target, 23, 18, {"actor": summon})
    record = conclude_combat_session(state, "GM", "VICTORY")
    assert record["participants"]["owner"]["summon_damage_dealt"] == 5
    assert summon not in state["characters"]
