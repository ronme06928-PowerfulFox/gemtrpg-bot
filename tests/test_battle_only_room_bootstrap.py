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
