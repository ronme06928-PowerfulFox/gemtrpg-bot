from manager.battle import common_manager


def test_existing_token_move_emits_position_only_update(monkeypatch):
    state = {
        "play_mode": "battle_only",
        "characters": [{"id": "c1", "x": 1, "y": 2, "last_move_ts": 10}],
    }
    emitted = []
    broadcasts = []
    saves = []

    monkeypatch.setattr(common_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_manager, "save_specific_room_state", lambda room: saves.append(room))
    monkeypatch.setattr(common_manager, "broadcast_state_update", lambda room: broadcasts.append(room))
    monkeypatch.setattr(common_manager, "_safe_emit", lambda event, payload, **kwargs: emitted.append((event, payload, kwargs)))

    common_manager.move_token_logic("room_a", "c1", 4, 5, "gm", "GM", move_ts=20)

    assert broadcasts == []
    assert saves == ["room_a"]
    assert state["characters"][0]["x"] == 4
    assert state["characters"][0]["y"] == 5
    assert emitted == [(
        "character_moved",
        {"character_id": "c1", "x": 4.0, "y": 5.0, "last_move_ts": 20.0},
        {"to": "room_a"},
    )]


def test_first_placement_keeps_full_state_update(monkeypatch):
    state = {
        "play_mode": "battle_only",
        "characters": [{"id": "c1", "x": -1, "y": -1}],
    }
    emitted = []
    broadcasts = []

    monkeypatch.setattr(common_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_manager, "save_specific_room_state", lambda _room: None)
    monkeypatch.setattr(common_manager, "broadcast_state_update", lambda room: broadcasts.append(room))
    monkeypatch.setattr(common_manager, "_safe_emit", lambda *args, **kwargs: emitted.append((args, kwargs)))

    common_manager.move_token_logic("room_a", "c1", 2, 3, "gm", "GM", move_ts=20)

    assert broadcasts == ["room_a"]
    assert emitted == []
