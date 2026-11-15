from events import socket_preset_deployment as deployment_socket


def test_operation_cache_is_persisted_in_room_state_and_bounded():
    room = "deployment-cache-test"
    state = {}
    deployment_socket._applied_operations.pop(room, None)

    for index in range(deployment_socket._APPLIED_OPERATION_LIMIT + 3):
        operation_id = f"op-{index}"
        deployment_socket._remember_operation(
            room,
            operation_id,
            {"operation_id": operation_id, "summary": {"added": index}},
            state,
        )

    rows = state["preset_deployment_operations"]
    assert len(rows) == deployment_socket._APPLIED_OPERATION_LIMIT
    assert rows[0]["operation_id"] == "op-3"
    assert deployment_socket._cached_operation(room, "op-0", state) is None
    assert deployment_socket._cached_operation(room, "op-3", state)["summary"]["added"] == 3


def test_operation_cache_survives_runtime_cache_loss():
    room = "deployment-cache-reload-test"
    state = {}
    payload = {"operation_id": "same-request", "duplicate": False}
    deployment_socket._remember_operation(room, "same-request", payload, state)

    deployment_socket._applied_operations.pop(room, None)

    assert deployment_socket._cached_operation(room, "same-request", state) == payload


def test_queue_and_operation_history_are_excluded_from_participant_state():
    from manager.room_manager import build_participant_state

    state = {"encounter_queue": [{"name": "secret"}],
             "preset_deployment_operations": [{"summary": {"name": "secret"}}],
             "characters": []}
    assert build_participant_state(state) == {"characters": []}
    assert state["encounter_queue"][0]["name"] == "secret"


def test_queue_events_validate_update_and_reject_players(monkeypatch):
    from types import SimpleNamespace
    from tests.test_preset_deployment import _normal_state, _store

    state = _normal_state()
    sent = []
    role = {"room_role": "gm"}
    monkeypatch.setattr(deployment_socket, "request", SimpleNamespace(sid="gm"))
    monkeypatch.setattr(deployment_socket, "user_sids", {"gm": {"room": "r"}})
    monkeypatch.setattr(deployment_socket, "catalog_request_context", lambda _: role)
    monkeypatch.setattr(deployment_socket, "get_room_state", lambda _: state)
    monkeypatch.setattr(deployment_socket, "deployment_store", _store)
    monkeypatch.setattr(deployment_socket, "save_specific_room_state", lambda _: None)
    monkeypatch.setattr(deployment_socket, "broadcast_state_update", lambda _: None)
    monkeypatch.setattr(deployment_socket, "broadcast_log", lambda *_: None)
    monkeypatch.setattr(deployment_socket.socketio, "emit", lambda *args, **kw: sent.append((*args, kw)))
    save = {"room": "r", "name": "test", "deployment": {"stage": {"id": "st_1"}}}
    deployment_socket.handle_encounter_save({**save, "deployment": {"stage": {"id": "missing"}}})
    assert sent[-1][0] == "preset_deployment_error"
    assert not state.get("encounter_queue")
    deployment_socket.handle_encounter_save(save)
    row, = state["encounter_queue"]
    assert row["deployment"]["stage"]["record_id"] == "st_1"
    assert "record" not in row["deployment"]["stage"]
    assert sent[-1][2] == {"to": "gm"}

    role["room_role"] = "player"
    deployment_socket.handle_preset_deployment_catalog({"room": "r"})
    assert sent[-1][0] == "preset_deployment_error"
    role["room_role"] = "gm"
    payload = {"room": "r", "encounter_id": row["id"], "operation_id": "queue-test"}
    deployment_socket.handle_preset_deployment_apply(payload)
    deployment_socket.handle_preset_deployment_apply(payload)
    assert sent[-1][1]["duplicate"] is True
    assert state["encounter_queue"][0]["done"] is True
    assert len(state["characters"]) == 3
    deployment_socket.handle_encounter_delete({"room": "r", "encounter_id": row["id"]})
    assert state["encounter_queue"] == []

    state["play_mode"] = "battle_only"
    deployment_socket.handle_encounter_save({
        **save, "deployment": {"stage": {"id": "st_1", "apply": {"ally_formation": False}}}
    })
    row, = state["encounter_queue"]
    deployment_socket.handle_preset_deployment_apply({
        "room": "r", "encounter_id": row["id"], "operation_id": "battle-draft-test"
    })
    assert sent[-1][1]["summary"]["ready"] is False
    assert state["battle_only"]["enemy_entries"][0]["count"] == 2
    assert state["encounter_queue"][0]["done"] is True


def test_retired_socket_handlers_are_unregistered():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    removed = ("request_room_apply_", "request_bo_bookmark_", "request_save_preset",
               "request_load_preset", "request_get_presets", "request_delete_preset",
               "request_export_preset_json", "request_import_preset_json")
    for path in [*(root / "events").rglob("*.py"), *(root / "static/js").rglob("*.js")]:
        source = path.read_text(encoding="utf-8")
        assert not any(event in source for event in removed), str(path)
