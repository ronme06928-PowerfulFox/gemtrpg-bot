from manager.battle.combat_session import (
    is_combat_progression_allowed,
    record_combat_damage,
)


def test_combat_progression_keeps_legacy_and_battle_only_rooms_active():
    assert is_combat_progression_allowed({}) is True
    assert is_combat_progression_allowed({"play_mode": "battle_only", "combat_phase": "ready"}) is True


def test_combat_progression_rejects_normal_room_while_ready():
    assert is_combat_progression_allowed({"play_mode": "normal", "combat_phase": "ready"}) is False
    assert is_combat_progression_allowed({"combat_phase": "active"}) is True


def test_record_combat_damage_tracks_actual_loss_and_actor_attribution():
    actor = {"id": "actor-1"}
    target = {"id": "target-1"}
    state = {"combat_phase": "active", "combat_session": {"participants": {}}}

    assert record_combat_damage(state, target, 8, 0, {"actor": actor}) is True
    assert state["combat_session"]["participants"] == {
        "actor-1": {"damage_dealt": 8, "damage_taken": 0},
        "target-1": {"damage_dealt": 0, "damage_taken": 8},
    }


def test_record_combat_damage_ignores_healing_missing_session_and_unknown_actor():
    target = {"id": "target-1"}
    state = {"combat_phase": "active", "combat_session": {"participants": {}}}

    assert record_combat_damage(state, target, 3, 5, {}) is False
    assert record_combat_damage({}, target, 5, 0, {}) is False
    assert record_combat_damage(state, target, 5, 2, {}) is True
    assert state["combat_session"]["participants"] == {
        "target-1": {"damage_dealt": 0, "damage_taken": 3},
    }
