from types import SimpleNamespace

from events import socket_char


def _base_state():
    return {
        "characters": [
            {"id": "A1", "name": "Ally", "type": "ally", "flags": {}},
            {"id": "E1", "name": "Enemy", "type": "enemy", "flags": {}},
        ],
        "presets": {},
        "battle_state": {"behavior_runtime": {}},
    }


def _patch_common(monkeypatch, state, user_info):
    emits = []
    monkeypatch.setattr(socket_char, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(socket_char, "get_room_state", lambda _room: state)
    monkeypatch.setattr(socket_char, "save_specific_room_state", lambda _room: True)
    monkeypatch.setattr(socket_char, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(socket_char, "broadcast_state_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(socket_char, "get_user_info_from_sid", lambda _sid: user_info)
    monkeypatch.setattr(
        socket_char.socketio,
        "emit",
        lambda event, payload=None, to=None: emits.append((event, payload or {}, to)),
    )
    return emits


def test_preset_save_rejected_for_non_gm(monkeypatch):
    state = _base_state()
    emits = _patch_common(monkeypatch, state, {"username": "player", "attribute": "Player"})

    socket_char.handle_save_preset({"room": "room_t", "name": "PresetA"})

    assert state.get("presets", {}) == {}
    assert any(row[0] == "preset_error" for row in emits)
    assert any(row[0] == "preset_save_error" for row in emits)


def test_preset_save_stores_v2_and_is_deepcopied(monkeypatch):
    state = _base_state()
    emits = _patch_common(monkeypatch, state, {"username": "gm", "attribute": "GM"})

    socket_char.handle_save_preset({"room": "room_t", "name": "PresetA"})

    assert "PresetA" in state["presets"]
    payload = state["presets"]["PresetA"]
    assert isinstance(payload, dict)
    assert payload.get("version") == 2
    assert isinstance(payload.get("enemies"), list)
    assert len(payload["enemies"]) == 1
    assert payload["enemies"][0]["id"] == "E1"

    # 保存後に元データを書き換えてもプリセット側に波及しない
    state["characters"][1]["name"] = "EnemyChanged"
    assert payload["enemies"][0]["name"] == "Enemy"
    assert any(row[0] == "preset_saved" for row in emits)
