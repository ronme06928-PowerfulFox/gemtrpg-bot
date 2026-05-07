from manager.battle import common_manager


def _resolve_state():
    return {
        "resolve": {
            "mass_queue": [],
            "single_queue": [],
            "resolved_slots": [],
            "trace": [],
        }
    }


def test_status_reset_removes_summoned_characters(monkeypatch):
    state = {
        "round": 3,
        "is_round_ended": False,
        "timeline": [],
        "active_match": {"dummy": True},
        "characters": [
            {
                "id": "ally_1",
                "name": "Ally",
                "hp": 20,
                "maxHp": 20,
                "mp": 5,
                "maxMp": 5,
                "x": 0,
                "y": 0,
                "is_escaped": False,
                "hasActed": False,
                "states": [],
                "special_buffs": [],
            },
            {
                "id": "sm_1",
                "name": "Summon",
                "hp": 10,
                "maxHp": 10,
                "mp": 0,
                "maxMp": 0,
                "x": 1,
                "y": 0,
                "is_escaped": False,
                "hasActed": False,
                "is_summoned": True,
                "states": [],
                "special_buffs": [],
            },
        ],
        "character_owners": {"ally_1": "alice", "sm_1": "alice"},
        "battle_state": {"resolve": {}},
    }

    monkeypatch.setattr(common_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_manager, "save_specific_room_state", lambda _room: None)
    monkeypatch.setattr(common_manager, "broadcast_state_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "emit_select_resolve_events", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "ensure_battle_state_vNext", lambda *_args, **_kwargs: _resolve_state())

    common_manager.reset_battle_logic(
        "room_t",
        "status",
        "tester",
        reset_options={
            "hp": False,
            "mp": False,
            "fp": False,
            "states": False,
            "bad_states": False,
            "buffs": False,
            "timeline": True,
        },
    )

    assert state["round"] == 0
    assert len(state["characters"]) == 1
    assert state["characters"][0]["id"] == "ally_1"
    assert "sm_1" not in state.get("character_owners", {})


def test_status_reset_clears_stage_runtime_effects(monkeypatch):
    state = {
        "play_mode": "normal",
        "round": 2,
        "is_round_ended": False,
        "timeline": [{"char_id": "c1"}],
        "characters": [],
        "field_effects": [{"field_id": "fog", "source_type": "stage_preset"}],
        "stage_field_effect_profile": {"version": 1, "rules": [{"rule_id": "fog", "type": "SPEED_ROLL_MOD"}]},
        "stage_field_effect_enabled": True,
        "stage_avatar_profile": {"enabled": True, "name": "Stage Avatar", "icon": "S"},
        "stage_avatar_enabled": True,
        "battle_state": {"resolve": {}},
    }

    monkeypatch.setattr(common_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_manager, "save_specific_room_state", lambda _room: None)
    monkeypatch.setattr(common_manager, "broadcast_state_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "emit_select_resolve_events", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "ensure_battle_state_vNext", lambda *_args, **_kwargs: _resolve_state())

    common_manager.reset_battle_logic(
        "room_t",
        "status",
        "tester",
        reset_options={
            "hp": False,
            "mp": False,
            "fp": False,
            "states": False,
            "bad_states": False,
            "buffs": False,
            "timeline": True,
        },
    )

    assert state["field_effects"] == []
    assert state["stage_field_effect_profile"] == {}
    assert state["stage_field_effect_enabled"] is False
    assert state["stage_avatar_profile"] == {}
    assert state["stage_avatar_enabled"] is False


def test_full_reset_hides_battle_only_stage_effect_card_state(monkeypatch):
    state = {
        "play_mode": "battle_only",
        "round": 3,
        "is_round_ended": False,
        "timeline": [{"char_id": "c1"}],
        "characters": [{"id": "c1", "type": "ally"}],
        "field_effects": [{"field_id": "fog", "source_type": "stage_preset"}],
        "stage_field_effect_profile": {"version": 1, "rules": [{"rule_id": "fog", "type": "SPEED_ROLL_MOD"}]},
        "stage_field_effect_enabled": True,
        "stage_avatar_profile": {"enabled": True, "name": "Stage Avatar", "icon": "S"},
        "stage_avatar_enabled": True,
        "battle_only": {
            "status": "in_battle",
            "active_record_id": "bor_1",
            "pending_auto_reset": True,
            "pending_auto_reset_round": 3,
            "selected_stage_id": "stage_1",
            "stage_field_effect_profile": {"version": 1, "rules": [{"rule_id": "fog", "type": "SPEED_ROLL_MOD"}]},
            "stage_avatar_profile": {"enabled": True, "name": "Stage Avatar", "icon": "S"},
            "stage_avatar_enabled": True,
        },
        "battle_state": {"resolve": {}},
    }

    monkeypatch.setattr(common_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_manager, "save_specific_room_state", lambda _room: None)
    monkeypatch.setattr(common_manager, "broadcast_state_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "emit_select_resolve_events", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "ensure_battle_state_vNext", lambda *_args, **_kwargs: _resolve_state())

    common_manager.reset_battle_logic("room_t", "full", "tester")

    assert state["field_effects"] == []
    assert state["stage_field_effect_profile"] == {}
    assert state["stage_field_effect_enabled"] is False
    assert state["stage_avatar_profile"] == {}
    assert state["stage_avatar_enabled"] is False
    assert state["battle_only"]["status"] == "draft"
    assert state["battle_only"]["active_record_id"] is None
    assert state["battle_only"]["pending_auto_reset"] is False
