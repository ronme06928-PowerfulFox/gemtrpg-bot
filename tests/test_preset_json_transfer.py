import json
from types import SimpleNamespace

from events import socket_char


def _base_state():
    return {
        "characters": [],
        "presets": {
            "LegacyPreset": [
                {"id": "E1", "name": "Enemy1", "type": "enemy", "flags": {}},
            ]
        },
        "battle_state": {"behavior_runtime": {}},
    }


def _patch_common(monkeypatch, state):
    emits = []
    monkeypatch.setattr(socket_char, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(socket_char, "get_room_state", lambda _room: state)
    monkeypatch.setattr(socket_char, "save_specific_room_state", lambda _room: True)
    monkeypatch.setattr(socket_char, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(socket_char, "broadcast_state_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        socket_char,
        "get_user_info_from_sid",
        lambda _sid: {"username": "gm", "attribute": "GM"},
    )
    monkeypatch.setattr(
        socket_char.socketio,
        "emit",
        lambda event, payload=None, to=None: emits.append((event, payload or {}, to)),
    )
    return emits


def test_export_normalizes_legacy_preset(monkeypatch):
    state = _base_state()
    emits = _patch_common(monkeypatch, state)

    socket_char.handle_export_preset_json({"room": "room_t", "name": "LegacyPreset"})

    exported = [row for row in emits if row[0] == "preset_json_exported"]
    assert exported
    payload = exported[-1][1]
    parsed = json.loads(payload["json"])
    assert parsed["schema"] == "gem_dicebot_enemy_preset.v1"
    assert parsed["payload"]["version"] == 2
    assert isinstance(parsed["payload"]["enemies"], list)
    assert state["presets"]["LegacyPreset"]["version"] == 2


def test_import_rejects_duplicate_without_overwrite_and_accepts_with_overwrite(monkeypatch):
    state = _base_state()
    emits = _patch_common(monkeypatch, state)
    incoming = {
        "schema": "gem_dicebot_enemy_preset.v1",
        "preset_name": "LegacyPreset",
        "payload": {
            "version": 2,
            "enemies": [{"id": "E2", "name": "Enemy2", "type": "enemy", "flags": {}}],
        },
    }

    socket_char.handle_import_preset_json({"room": "room_t", "json": json.dumps(incoming)})
    assert any(row[0] == "preset_import_error" for row in emits)

    emits.clear()
    socket_char.handle_import_preset_json({"room": "room_t", "json": json.dumps(incoming), "overwrite": True})
    assert any(row[0] == "preset_imported" for row in emits)
    assert state["presets"]["LegacyPreset"]["version"] == 2
    assert state["presets"]["LegacyPreset"]["enemies"][0]["name"] == "Enemy2"
