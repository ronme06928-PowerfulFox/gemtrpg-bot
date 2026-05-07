from types import SimpleNamespace

from manager import data_manager, room_manager


def test_bo_defaults_normalize_invalid_values():
    state = {
        "play_mode": "something_else",
        "battle_only": {
            "status": "bad",
            "ally_entries": {},
            "enemy_entries": "bad",
            "records": {},
        },
    }

    room_manager._ensure_battle_only_defaults(state)

    assert state["play_mode"] == "normal"
    assert state["battle_only"]["status"] == "lobby"
    assert isinstance(state["battle_only"]["ally_entries"], list)
    assert isinstance(state["battle_only"]["enemy_entries"], list)
    assert isinstance(state["battle_only"]["records"], list)
    assert "active_record_id" in state["battle_only"]


def test_bo_defaults_clear_stale_runtime_stage_state_when_not_in_battle():
    state = {
        "play_mode": "battle_only",
        "field_effects": [{"field_id": "fog", "source_type": "stage_preset"}],
        "stage_field_effect_profile": {"version": 1, "rules": [{"rule_id": "fog", "type": "SPEED_ROLL_MOD"}]},
        "stage_field_effect_enabled": True,
        "stage_avatar_profile": {"enabled": True, "name": "Stage Avatar", "icon": "S"},
        "stage_avatar_enabled": True,
        "battle_only": {
            "status": "draft",
            "selected_stage_id": "stage_1",
            "stage_field_effect_profile": {"version": 1, "rules": [{"rule_id": "fog", "type": "SPEED_ROLL_MOD"}]},
            "stage_field_effect_enabled": True,
            "stage_avatar_profile": {"enabled": True, "name": "Stage Avatar", "icon": "S"},
            "stage_avatar_enabled": True,
        },
    }

    room_manager._ensure_battle_only_defaults(state)

    assert state["field_effects"] == []
    assert state["stage_field_effect_profile"] == {}
    assert state["stage_field_effect_enabled"] is False
    assert state["stage_avatar_profile"] == {}
    assert state["stage_avatar_enabled"] is False
    assert state["battle_only"]["selected_stage_id"] == "stage_1"
    assert state["battle_only"]["stage_field_effect_profile"]["rules"][0]["rule_id"] == "fog"
    assert state["battle_only"]["stage_field_effect_enabled"] is True
    assert state["battle_only"]["stage_avatar_profile"]["name"] == "Stage Avatar"
    assert state["battle_only"]["stage_avatar_enabled"] is True


def test_bo_defaults_keep_runtime_stage_state_during_active_battle():
    state = {
        "play_mode": "battle_only",
        "field_effects": [{"field_id": "fog", "source_type": "stage_preset"}],
        "stage_field_effect_profile": {"version": 1, "rules": [{"rule_id": "fog", "type": "SPEED_ROLL_MOD"}]},
        "stage_field_effect_enabled": True,
        "stage_avatar_profile": {"enabled": True, "name": "Stage Avatar", "icon": "S"},
        "stage_avatar_enabled": True,
        "battle_only": {
            "status": "in_battle",
            "stage_field_effect_profile": {"version": 1, "rules": [{"rule_id": "fog", "type": "SPEED_ROLL_MOD"}]},
            "stage_avatar_profile": {"enabled": True, "name": "Stage Avatar", "icon": "S"},
        },
    }

    room_manager._ensure_battle_only_defaults(state)

    assert state["field_effects"][0]["field_id"] == "fog"
    assert state["stage_field_effect_profile"]["rules"][0]["rule_id"] == "fog"
    assert state["stage_field_effect_enabled"] is True
    assert state["stage_avatar_profile"]["name"] == "Stage Avatar"
    assert state["stage_avatar_enabled"] is True


def test_read_saved_rooms_with_owners_includes_battle_only_metadata(monkeypatch):
    fake_rooms = [
        SimpleNamespace(
            name="normal_room",
            owner_id="user_1",
            data={"play_mode": "normal"},
        ),
        SimpleNamespace(
            name="bo_room",
            owner_id="user_2",
            data={"play_mode": "battle_only", "battle_only": {"status": "draft"}},
        ),
        SimpleNamespace(
            name="legacy_room",
            owner_id="user_3",
            data={},
        ),
    ]

    monkeypatch.setattr(
        data_manager,
        "Room",
        SimpleNamespace(query=SimpleNamespace(all=lambda: fake_rooms)),
    )

    rooms = data_manager.read_saved_rooms_with_owners()
    by_name = {row["name"]: row for row in rooms}

    assert by_name["normal_room"]["play_mode"] == "normal"
    assert by_name["normal_room"]["battle_only_stage_id"] is None

    assert by_name["bo_room"]["play_mode"] == "battle_only"
    assert by_name["bo_room"]["battle_only_stage_id"] is None

    assert by_name["legacy_room"]["play_mode"] == "normal"
    assert by_name["legacy_room"]["battle_only_stage_id"] is None
