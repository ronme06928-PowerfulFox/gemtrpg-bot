"""戦闘専用プリセット群と戦績のJSON出力ルート。"""

import copy
import json
import time
from datetime import datetime, timezone

from flask import request

from extensions import socketio
from events.battle_only.catalog_access_context import catalog_request_context, visible_map
from events.battle_only.catalog_state import _ensure_bo_state, _get_records, _sort_named_ids, _sort_stage_ids
from manager.battle_only_presets import load_store
from manager.room_manager import get_room_state


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _dependencies():
    """Use registered dependencies normally and the legacy direct-call seam in tests."""
    try:
        request.sid
        return request, load_store, get_room_state, catalog_request_context
    except RuntimeError:
        from events import socket_battle_only
        return (
            socket_battle_only.request,
            socket_battle_only.load_bo_preset_store,
            socket_battle_only.get_room_state,
            socket_battle_only._catalog_request_context,
        )


def _emit_store_export(event_name, filename_prefix, rows, sorted_ids):
    request_obj, _, _, _ = _dependencies()
    sanitized = copy.deepcopy(rows if isinstance(rows, dict) else {})
    for record in sanitized.values():
        if not isinstance(record, dict):
            continue
        for key in ("access_control", "capabilities", "owner_display_name", "shared_via"):
            record.pop(key, None)
    content = json.dumps(
        {
            "version": 3,
            "exported_at": _now_iso(),
            "count": len(sanitized),
            "sorted_ids": sorted_ids if isinstance(sorted_ids, list) else [],
            "items": sanitized,
        },
        ensure_ascii=False,
        indent=2,
    )
    socketio.emit(
        event_name,
        {"filename": f"{filename_prefix}_{int(time.time())}.json", "content": content},
        to=request_obj.sid,
    )


def _export_rows(data, record_type, event_name, filename_prefix, sorter):
    _, load_fn, _, context_fn = _dependencies()
    context = context_fn(data)
    store = load_fn()
    rows = visible_map(store, record_type, context)
    _emit_store_export(event_name, filename_prefix, rows, sorter(rows))


@socketio.on("request_bo_export_enemy_formations_json")
def handle_bo_export_enemy_formations_json(data):
    _export_rows(data, "enemy_formation", "bo_export_enemy_formations_json", "bo_enemy_formations", _sort_named_ids)


@socketio.on("request_bo_export_ally_formations_json")
def handle_bo_export_ally_formations_json(data):
    _export_rows(data, "ally_formation", "bo_export_ally_formations_json", "bo_ally_formations", _sort_named_ids)


@socketio.on("request_bo_export_stage_presets_json")
def handle_bo_export_stage_presets_json(data):
    _export_rows(data, "stage", "bo_export_stage_presets_json", "bo_stage_presets", _sort_stage_ids)


@socketio.on("request_bo_record_export")
def handle_bo_record_export(data):
    request_obj, _, get_room_fn, context_fn = _dependencies()
    context = context_fn(data)
    room = context.get("room")
    if not room or not context.get("room_role"):
        socketio.emit(
            "bo_draft_error",
            {"error": "permission_denied", "message": "対象ルームの参加者だけが出力できます。"},
            to=request_obj.sid,
        )
        return
    state = get_room_fn(room)
    bo = _ensure_bo_state(state)
    records = copy.deepcopy(_get_records(bo))
    payload = {
        "room": room,
        "play_mode": str(state.get("play_mode", "normal")),
        "exported_at": _now_iso(),
        "battle_only": {
            "status": bo.get("status"),
            "active_record_id": bo.get("active_record_id"),
            "selected_stage_id": bo.get("selected_stage_id"),
            "ally_formation_id": bo.get("ally_formation_id"),
            "enemy_formation_id": bo.get("enemy_formation_id"),
            "required_ally_count": bo.get("required_ally_count"),
            "ally_entries": copy.deepcopy(bo.get("ally_entries", [])),
            "enemy_entries": copy.deepcopy(bo.get("enemy_entries", [])),
        },
        "records": records,
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    socketio.emit(
        "bo_record_export",
        {
            "filename": f"battle_only_records_{room.replace(' ', '_')}_{int(time.time())}.json",
            "content": content,
            "record_count": len(records),
        },
        to=request_obj.sid,
    )
