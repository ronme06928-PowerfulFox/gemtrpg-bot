from manager.battle import common_manager


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
    monkeypatch.setattr(common_manager, "ensure_battle_state_vNext", lambda *_args, **_kwargs: {"resolve": {}})

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
