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
