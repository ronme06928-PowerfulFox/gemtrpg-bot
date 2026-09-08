from manager.battle.combat_session import (
    conclude_combat_session,
    ensure_combat_session_defaults,
    record_combat_damage,
    start_combat_session,
)


def _character(char_id, name, **extra):
    char = {
        "id": char_id,
        "name": name,
        "hp": 23,
        "mp": 7,
        "FP": 4,
        "x": 2,
        "y": 3,
        "states": [{"name": "FP", "value": 4}, {"name": "出血", "value": 3}],
        "special_buffs": [{"name": "temporary", "lasting": 2}],
        "initial_state": {"special_buffs": [{"name": "permanent", "is_permanent": True}]},
        "commands": "【S-1 テスト】\n【BASE】",
        "granted_skills": [{"skill_id": "S-1", "injected": True}],
        "hasActed": True,
    }
    char.update(extra)
    return char


def test_new_and_legacy_room_defaults_are_compatible():
    new_state = {"characters": []}
    ensure_combat_session_defaults(new_state, new_room=True)
    assert new_state["combat_phase"] == "ready"
    assert new_state["combat_session"] is None

    legacy_state = {"characters": []}
    ensure_combat_session_defaults(legacy_state)
    assert legacy_state["combat_phase"] == "active"
    assert legacy_state["combat_session"]["legacy_migrated"] is True


def test_start_and_conclusion_archive_record_and_clear_only_combat_state():
    actor = _character("actor", "Actor")
    target = _character("target", "Target")
    state = {"combat_phase": "ready", "combat_history": [], "characters": [actor, target], "battle_state": {"resolve": {}}}

    session = start_combat_session(state, "GM")
    assert session and state["combat_phase"] == "active"
    assert set(session["participants"]) == {"actor", "target"}
    assert actor["hp"] == 23 and actor["mp"] == 7 and actor["FP"] == 4
    assert actor["states"][1]["value"] == 0
    assert actor["special_buffs"] == [{"name": "permanent", "is_permanent": True}]
    assert actor["granted_skills"] == []
    assert actor["commands"] == "【BASE】"

    assert record_combat_damage(state, target, 23, 15, {"actor": actor}) is True
    record = conclude_combat_session(state, "GM", "VICTORY")
    assert record["participants"]["actor"]["damage_dealt"] == 8
    assert state["combat_phase"] == "ready"
    assert state["combat_session"] is None
    assert state["combat_history"] == [record]
    assert target["hp"] == 23 and target["mp"] == 7 and target["FP"] == 4


def test_summons_are_aggregated_without_participant_rows():
    owner = _character("owner", "Owner")
    summon = _character("summon", "Summon", is_summoned=True, summoner_id="owner")
    target = _character("target", "Target")
    state = {"combat_phase": "ready", "combat_history": [], "characters": [owner, summon, target]}
    session = start_combat_session(state, "GM")

    assert "summon" not in session["participants"]
    record_combat_damage(state, target, 23, 18, {"actor": summon})
    record_combat_damage(state, summon, 23, 19, {"actor": target})
    owner_row = session["participants"]["owner"]
    assert owner_row["damage_dealt"] == 5
    assert owner_row["summon_damage_dealt"] == 5
    assert owner_row["summon_damage_taken"] == 4


def test_unplaced_characters_are_not_initial_combat_participants():
    deployed = _character("deployed", "Deployed")
    unplaced = _character("unplaced", "Unplaced", x=-1, y=-1)
    state = {"combat_phase": "ready", "combat_history": [], "characters": [deployed, unplaced]}

    session = start_combat_session(state, "GM")

    assert session is not None
    assert set(session["participants"]) == {"deployed"}
