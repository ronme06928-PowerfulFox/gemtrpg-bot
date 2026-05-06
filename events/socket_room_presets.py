# events/socket_room_presets.py
import copy

from flask import request

from extensions import socketio, user_sids
from manager.room_manager import (
    broadcast_log,
    broadcast_state_update,
    get_room_state,
    get_user_info_from_sid,
    save_specific_room_state,
)
from manager.room_preset_apply import (
    RoomPresetError,
    apply_enemy_formation_to_room_state,
    apply_enemy_preset_to_room_state,
    apply_stage_preset_to_room_state,
    build_room_preset_catalog,
)


def _emit_error(code, message, event_name="room_preset_error", extra=None):
    payload = {"error": str(code or "room_preset_error"), "message": str(message or "")}
    if isinstance(extra, dict):
        payload.update(extra)
    socketio.emit(event_name, payload, to=request.sid)


def _is_gm(user_info):
    return str((user_info or {}).get("attribute", "")).strip().upper() == "GM"


def _require_room_participant(room, event_name="room_preset_error"):
    target_room = str(room or "").strip()
    if not target_room:
        _emit_error("missing_room", "room is required", event_name=event_name)
        return False, get_user_info_from_sid(request.sid)

    user_info = get_user_info_from_sid(request.sid)
    sid_entry = user_sids.get(request.sid) if isinstance(user_sids, dict) else None
    sid_room = str((sid_entry or {}).get("room", "")).strip() if isinstance(sid_entry, dict) else ""
    if sid_room and sid_room == target_room:
        return True, user_info

    _emit_error("permission_denied", "you are not in this room", event_name=event_name)
    return False, user_info


def _require_room_gm(room, event_name="room_preset_error"):
    allowed, user_info = _require_room_participant(room, event_name=event_name)
    if not allowed:
        return False, user_info
    if not _is_gm(user_info):
        _emit_error("permission_denied", "GM permission is required", event_name=event_name)
        return False, user_info
    return True, user_info


def _normal_room_state(room, event_name="room_preset_error"):
    state = get_room_state(room)
    if not isinstance(state, dict):
        _emit_error("not_found", "room state not found", event_name=event_name)
        return None
    play_mode = str(state.get("play_mode", "normal") or "normal").strip().lower()
    if play_mode == "battle_only":
        _emit_error("invalid_room_mode", "normal room preset API cannot be used in battle-only mode", event_name=event_name)
        return None
    return state


def _finish_apply(room, summary):
    save_specific_room_state(room)
    broadcast_state_update(room)
    socketio.emit("room_preset_applied", copy.deepcopy(summary), to=room)


@socketio.on("request_room_preset_catalog")
def handle_room_preset_catalog(data):
    src = data if isinstance(data, dict) else {}
    room = str(src.get("room", "")).strip()
    if room:
        allowed, user_info = _require_room_participant(room, event_name="room_preset_error")
        if not allowed:
            return
    else:
        user_info = get_user_info_from_sid(request.sid)

    payload = build_room_preset_catalog(user_info=user_info)
    socketio.emit("receive_room_preset_catalog", payload, to=request.sid)


@socketio.on("request_room_apply_enemy_preset")
def handle_room_apply_enemy_preset(data):
    src = data if isinstance(data, dict) else {}
    room = str(src.get("room", "")).strip()
    allowed, user_info = _require_room_gm(room, event_name="room_preset_error")
    if not allowed:
        return
    state = _normal_room_state(room)
    if state is None:
        return

    preset_id = str(src.get("preset_id", "")).strip()
    count = src.get("count", 1)
    mode = str(src.get("mode", "append") or "append").strip().lower()
    anchor = src.get("anchor") if isinstance(src.get("anchor"), dict) else None
    try:
        summary = apply_enemy_preset_to_room_state(
            state,
            preset_id,
            count=count,
            user_info=user_info,
            mode=mode,
            room=room,
            anchor=anchor,
        )
    except RoomPresetError as ex:
        _emit_error(ex.code, ex.message, event_name="room_preset_error")
        return

    _finish_apply(room, summary)
    broadcast_log(room, f"[Preset] enemy preset applied: {preset_id}", "info")


@socketio.on("request_room_apply_enemy_formation")
def handle_room_apply_enemy_formation(data):
    src = data if isinstance(data, dict) else {}
    room = str(src.get("room", "")).strip()
    allowed, user_info = _require_room_gm(room, event_name="room_preset_error")
    if not allowed:
        return
    state = _normal_room_state(room)
    if state is None:
        return

    formation_id = str(src.get("formation_id", "")).strip()
    mode = str(src.get("mode", "replace") or "replace").strip().lower()
    anchor = src.get("anchor") if isinstance(src.get("anchor"), dict) else None
    try:
        summary = apply_enemy_formation_to_room_state(
            state,
            formation_id,
            user_info=user_info,
            mode=mode,
            room=room,
            anchor=anchor,
        )
    except RoomPresetError as ex:
        _emit_error(ex.code, ex.message, event_name="room_preset_error")
        return

    _finish_apply(room, summary)
    broadcast_log(room, f"[Preset] enemy formation applied: {formation_id}", "info")


@socketio.on("request_room_apply_stage_preset")
def handle_room_apply_stage_preset(data):
    src = data if isinstance(data, dict) else {}
    room = str(src.get("room", "")).strip()
    allowed, user_info = _require_room_gm(room, event_name="room_preset_error")
    if not allowed:
        return
    state = _normal_room_state(room)
    if state is None:
        return

    stage_id = str(src.get("stage_id", "")).strip()
    apply_options = src.get("apply") if isinstance(src.get("apply"), dict) else {}
    enemy_apply_mode = str(src.get("enemy_apply_mode", "replace") or "replace").strip().lower()
    anchor = src.get("anchor") if isinstance(src.get("anchor"), dict) else None
    try:
        summary = apply_stage_preset_to_room_state(
            state,
            stage_id,
            apply_options=apply_options,
            user_info=user_info,
            enemy_apply_mode=enemy_apply_mode,
            room=room,
            anchor=anchor,
        )
    except RoomPresetError as ex:
        _emit_error(ex.code, ex.message, event_name="room_preset_error")
        return

    _finish_apply(room, summary)
    broadcast_log(room, f"[Preset] stage preset applied: {stage_id}", "info")
