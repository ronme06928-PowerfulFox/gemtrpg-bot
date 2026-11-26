"""Socket operations for the Hollow party and host."""

from flask import request, session

from extensions import socketio, user_sids
from manager.battle.common_manager import _get_round_transition_lock
from manager.hollow.host import transfer_host
from manager.hollow.party import change_party
from manager.hollow.run import choose_map, retreat, select_node, start_run, swap_party
from manager.room_manager import broadcast_state_update


def _perform(operation, *args, **kwargs):
    info = user_sids.get(request.sid, {})
    room = info.get("room")
    user_id = session.get("user_id")
    if not room or not user_id or info.get("user_id") != user_id:
        return {"ok": False, "error": "部屋に入室してください"}
    try:
        operation(room, user_id, *args, **kwargs)
    except (ValueError, PermissionError) as exc:
        return {"ok": False, "error": str(exc)}
    broadcast_state_update(room)
    return {"ok": True}


@socketio.on("hollow_party_change")
def handle_party_change(data):
    payload = data if isinstance(data, dict) else {}
    return _perform(_change_party, payload.get("action"), payload.get("char_id"), payload.get("index"))


def _change_party(room, user_id, action, char_id, index):
    with _get_round_transition_lock(room):
        change_party(room, user_id, action, char_id, index)


@socketio.on("hollow_transfer_host")
def handle_transfer_host(data):
    payload = data if isinstance(data, dict) else {}
    return _perform(transfer_host, payload.get("user_id"))


@socketio.on("hollow_run_start")
def handle_run_start(_data=None):
    return _perform(start_run)


@socketio.on("hollow_choose_map")
def handle_choose_map(data):
    payload = data if isinstance(data, dict) else {}
    return _perform(choose_map, payload.get("map_id"), payload.get("tier"))


@socketio.on("hollow_select_node")
def handle_select_node(data):
    payload = data if isinstance(data, dict) else {}
    username = user_sids.get(request.sid, {}).get("username")
    return _perform(select_node, payload.get("node_id"), payload.get("tier"), username=username)


@socketio.on("hollow_swap_party")
def handle_swap_party(data):
    payload = data if isinstance(data, dict) else {}
    return _perform(swap_party, payload.get("active_id"), payload.get("reserve_id"))


@socketio.on("hollow_retreat")
def handle_retreat(_data=None):
    return _perform(retreat)
