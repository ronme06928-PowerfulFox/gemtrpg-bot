"""待機列とプリセット配置のSocketイベント。"""

from __future__ import annotations

import copy
import logging
from threading import RLock
from uuid import uuid4
from collections import OrderedDict

from flask import request

from extensions import socketio, user_sids
from events.preset_deployment_access import catalog_request_context
from manager.room_access import GM_ROLES
from manager.battle.common_manager import _get_round_transition_lock
from manager.units.runtime import deployment_store
from manager.preset_deployment import (
    PresetDeploymentError,
    apply_deployment,
    build_deployment_catalog,
    normalize_deployment_request,
    preview_deployment,
)
from manager.room_manager import (
    broadcast_log,
    broadcast_state_update,
    get_room_state,
    save_specific_room_state,
)


_APPLIED_OPERATION_LIMIT = 64
_applied_operations = {}
_mutation_lock = RLock()
logger = logging.getLogger(__name__)


def _emit_error(code, message, *, refresh_required=False, request_version=None):
    payload = {
        "code": str(code or "deployment_error"),
        "message": str(message or "配置に失敗しました。"),
        "refresh_required": bool(refresh_required),
    }
    if request_version is not None:
        payload["request_version"] = request_version
    socketio.emit(
        "preset_deployment_error",
        payload,
        to=request.sid,
    )


def _room_users(room):
    rows = []
    seen = set()
    for info in user_sids.values() if isinstance(user_sids, dict) else []:
        if not isinstance(info, dict) or str(info.get("room") or "") != room:
            continue
        user_id = str(info.get("user_id") or "").strip()
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        rows.append({
            "user_id": user_id,
            "username": str(info.get("username") or ""),
            "attribute": str(info.get("attribute") or ""),
        })
    rows.sort(key=lambda row: (row["username"].lower(), row["user_id"]))
    return rows


def _active_user_map(room):
    return {
        row["user_id"]: row["username"]
        for row in _room_users(room)
        if row.get("user_id")
    }


def _require_context(data):
    src = data if isinstance(data, dict) else {}
    room = str(src.get("room") or "").strip()
    if not room:
        _emit_error("missing_room", "ルームが指定されていません。")
        return None
    context = catalog_request_context(src)
    sid_info = user_sids.get(request.sid) if isinstance(user_sids, dict) else None
    if not isinstance(sid_info, dict) or str(sid_info.get("room") or "") != room:
        _emit_error("permission_denied", "このルームへ入室してから操作してください。")
        return None
    if context.get("room_role") not in GM_ROLES:
        _emit_error("permission_denied", "待機列の操作にはGM権限が必要です。")
        return None
    state = get_room_state(room)
    if not isinstance(state, dict):
        _emit_error("not_found", "ルーム状態が見つかりません。", refresh_required=True)
        return None
    return {
        **context,
        "room": room,
        "state": state,
        "users": _room_users(room),
    }


def _queue(state):
    return state.get("encounter_queue") or []


def _emit_queue(context, *, summary=None):
    socketio.emit("encounter_queue", {
        "room": context["room"], "entries": _queue(context["state"]), "summary": summary,
    }, to=request.sid)


def _encounter(context, encounter_id):
    row = next((row for row in _queue(context["state"]) if row["id"] == encounter_id), None)
    if row is None:
        raise PresetDeploymentError("not_found", "遭遇が見つかりません。", refresh_required=True)
    return row


def _deployment_payload(context, src):
    encounter_id = src.get("encounter_id")
    if not encounter_id:
        payload = src.get("deployment") if isinstance(src.get("deployment"), dict) else src
        return payload
    row = _encounter(context, encounter_id)
    return {**row["deployment"], "center": src.get("center")}


@socketio.on("request_encounter_queue")
def handle_encounter_queue(data):
    context = _require_context(data)
    if context is not None:
        _emit_queue(context)


@socketio.on("request_encounter_save")
def handle_encounter_save(data):
    context = _require_context(data)
    if context is None:
        return
    name = str(data.get("name") or "").strip()
    if not name or len(name) > 120:
        _emit_error("invalid_name", "遭遇名は1〜120文字で指定してください。")
        return
    with _mutation_lock:
        try:
            payload = _deployment_payload(context, {"deployment": data.get("deployment") or {}})
            deployment = normalize_deployment_request({**payload, "center": None})
            summary = preview_deployment(context["state"], deployment, deployment_store(), **_manager_context(context))
            encounter_id = data.get("encounter_id")
            row = _encounter(context, encounter_id) if encounter_id else None
        except PresetDeploymentError as ex:
            _emit_error(ex.code, ex.message, refresh_required=ex.refresh_required)
            return
        if data.get("check_only"):
            socketio.emit("encounter_checked", {"room": context["room"], "summary": summary}, to=request.sid)
            return
        updated = {
            "id": row["id"] if row else uuid4().hex,
            "name": name,
            "memo": str(data.get("memo") or "").strip()[:2000],
            "deployment": deployment,
            "done": bool(row and row.get("done")),
        }
        entries = _queue(context["state"])
        context["state"]["encounter_queue"] = [updated if item is row else item for item in entries] if row else [*entries, updated]
        save_specific_room_state(context["room"])
        _emit_queue(context, summary=summary)


@socketio.on("request_encounter_delete")
def handle_encounter_delete(data):
    context = _require_context(data)
    if context is None:
        return
    with _mutation_lock:
        entries = _queue(context["state"])
        remaining = [row for row in entries if row["id"] != data.get("encounter_id")]
        if len(remaining) != len(entries):
            context["state"]["encounter_queue"] = remaining
            save_specific_room_state(context["room"])
        _emit_queue(context)


def _manager_context(context):
    return {
        "user_id": context.get("user_id"),
        "is_author": context.get("is_author", False),
        "room_role": context.get("room_role"),
        "gm_user": context.get("user_info") or {},
        "active_users": _active_user_map(context["room"]),
    }


def _remember_operation(room, operation_id, payload, state=None):
    cache = _applied_operations.setdefault(room, OrderedDict())
    cache[operation_id] = copy.deepcopy(payload)
    cache.move_to_end(operation_id)
    while len(cache) > _APPLIED_OPERATION_LIMIT:
        cache.popitem(last=False)
    if isinstance(state, dict):
        rows = state.get("preset_deployment_operations")
        rows = rows if isinstance(rows, list) else []
        rows = [
            row for row in rows
            if isinstance(row, dict) and str(row.get("operation_id") or "") != operation_id
        ]
        rows.append(copy.deepcopy(payload))
        state["preset_deployment_operations"] = rows[-_APPLIED_OPERATION_LIMIT:]


def _cached_operation(room, operation_id, state=None):
    cache = _applied_operations.get(room)
    if isinstance(cache, OrderedDict):
        payload = cache.get(operation_id)
        if payload is not None:
            cache.move_to_end(operation_id)
            return copy.deepcopy(payload) if isinstance(payload, dict) else None
    rows = state.get("preset_deployment_operations") if isinstance(state, dict) else []
    for row in reversed(rows if isinstance(rows, list) else []):
        if isinstance(row, dict) and str(row.get("operation_id") or "") == operation_id:
            return copy.deepcopy(row)
    return None


@socketio.on("request_preset_deployment_catalog")
def handle_preset_deployment_catalog(data):
    context = _require_context(data)
    if context is None:
        return
    store = deployment_store()
    catalog = build_deployment_catalog(
        store,
        user_id=context.get("user_id"),
        is_author=context.get("is_author", False),
        room_role=context.get("room_role"),
        users=context["users"],
    )
    catalog["room"] = context["room"]
    socketio.emit("preset_deployment_catalog", catalog, to=request.sid)


@socketio.on("request_preset_deployment_preview")
def handle_preset_deployment_preview(data):
    context = _require_context(data)
    if context is None:
        return
    src = data if isinstance(data, dict) else {}
    request_version = src.get("request_version")
    try:
        payload = _deployment_payload(context, src)
        summary = preview_deployment(
            context["state"],
            payload,
            deployment_store(),
            **_manager_context(context),
        )
    except PresetDeploymentError as ex:
        _emit_error(
            ex.code,
            ex.message,
            refresh_required=ex.refresh_required,
            request_version=request_version,
        )
        return
    except Exception:
        logger.exception("preset deployment preview failed: room=%s", context["room"])
        _emit_error(
            "preview_failed",
            "配置内容を確認できませんでした。",
            request_version=request_version,
        )
        return
    socketio.emit(
        "preset_deployment_preview",
        {
            "room": context["room"],
            "summary": summary,
            "request_version": request_version,
        },
        to=request.sid,
    )


@socketio.on("request_preset_deployment_apply")
def handle_preset_deployment_apply(data):
    context = _require_context(data)
    if context is None:
        return
    with _get_round_transition_lock(context["room"]), _mutation_lock:
        _apply(context, data)


def _apply(context, src):
    operation_id = str(src.get("operation_id") or "").strip()
    if not operation_id or len(operation_id) > 128:
        _emit_error("invalid_operation_id", "配置操作IDが不正です。")
        return
    cached = _cached_operation(context["room"], operation_id, context["state"])
    if cached is not None:
        cached["duplicate"] = True
        socketio.emit("preset_deployment_applied", cached, to=request.sid)
        return
    try:
        payload = _deployment_payload(context, src)
        expected_unplaced = src.get("expected_unplaced")
        summary, logs = apply_deployment(
            context["state"],
            payload,
            deployment_store(),
            expected_unplaced=expected_unplaced if type(expected_unplaced) is int else None,
            room=context["room"],
            **_manager_context(context),
        )
    except PresetDeploymentError as ex:
        _emit_error(ex.code, ex.message, refresh_required=ex.refresh_required)
        return
    except Exception:
        logger.exception("preset deployment apply failed: room=%s", context["room"])
        _emit_error("apply_failed", "配置を確定できませんでした。")
        return

    if src.get("encounter_id"):
        _encounter(context, src["encounter_id"])["done"] = True
    response = {
        "room": context["room"],
        "operation_id": operation_id,
        "summary": summary,
        "duplicate": False,
    }
    _remember_operation(context["room"], operation_id, response, context["state"])
    save_specific_room_state(context["room"])
    broadcast_state_update(context["room"])
    for message in logs:
        broadcast_log(context["room"], message, "state-change")
    broadcast_log(
        context["room"],
        f"登場：味方{summary['added']['ally']}体・敵{summary['added']['enemy']}体",
        "info",
    )
    _emit_queue(context)
    socketio.emit("preset_deployment_applied", response, to=request.sid)
