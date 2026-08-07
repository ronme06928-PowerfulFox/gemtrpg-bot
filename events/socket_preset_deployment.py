"""通常ルーム／戦闘専用で共有するプリセット配置Socketイベント。"""

from __future__ import annotations

import copy
import logging
import time
from collections import OrderedDict

from flask import request

from extensions import socketio, user_sids
from events.battle_only.catalog_access_context import (
    catalog_request_context,
    owner_names_for_store,
)
from manager.battle_only_catalog_access import get_record
from manager.battle_only_presets import (
    load_store as load_bo_preset_store,
    mutate_store as mutate_bo_preset_store,
    normalize_catalog_meta,
)
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


def _bookmark_payload(state, catalog):
    bo = state.get("battle_only") if isinstance(state.get("battle_only"), dict) else {}
    rows = bo.get("preset_bookmarks") if isinstance(bo.get("preset_bookmarks"), list) else []
    records = catalog.get("records") if isinstance(catalog.get("records"), dict) else {}
    collections = catalog.get("catalog_collections") if isinstance(catalog.get("catalog_collections"), dict) else {}
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        target_type = str(row.get("target_type") or "").strip()
        target_id = str(row.get("target_id") or "").strip()
        if target_type == "collection":
            target = collections.get(target_id)
        else:
            target = (records.get(target_type) or {}).get(target_id)
        item = {
            "id": str(row.get("id") or f"bookmark:{target_type}:{target_id}"),
            "target_type": target_type,
            "target_id": target_id,
            "available": isinstance(target, dict),
            "label": str(row.get("label") or ((target or {}).get("name") if isinstance(target, dict) else target_id)),
            "collection_id": ((target or {}).get("catalog_meta") or {}).get("collection_id") if isinstance(target, dict) else None,
        }
        result.append(item)
    result.sort(key=lambda item: (str(item.get("label") or "").lower(), item["id"]))
    return result


def _validate_target_mode(state, payload):
    target_mode = str((payload or {}).get("target_mode") or "normal").strip().lower()
    current_mode = str(state.get("play_mode") or "normal").strip().lower()
    if target_mode == "battle_only" and current_mode != "battle_only":
        raise PresetDeploymentError("invalid_room_mode", "このルームは戦闘専用モードではありません。")
    if target_mode == "normal" and current_mode == "battle_only":
        raise PresetDeploymentError("invalid_room_mode", "戦闘専用ルームには通常配置できません。")


def _manager_context(context):
    return {
        "user_id": context.get("user_id"),
        "is_app_admin": context.get("is_app_admin", False),
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


def _touch_used_records(request_data):
    normalized = normalize_deployment_request(request_data)
    refs = set()
    if normalized.get("stage"):
        refs.add(("stage", normalized["stage"]["record_id"]))
    for side, record_type in (("ally", "ally_formation"), ("enemy", "enemy_formation")):
        row = normalized["formations"].get(side)
        if row:
            refs.add((record_type, row["record_id"]))
    for row in normalized["characters"]:
        refs.add(("character", row["record_id"]))
    now_ms = int(time.time() * 1000)

    def _mutate(store):
        for record_type, record_id in refs:
            record = get_record(store, record_type, record_id)
            if not isinstance(record, dict):
                continue
            meta = normalize_catalog_meta(record.get("catalog_meta"))
            meta["last_used_at"] = now_ms
            record["catalog_meta"] = meta

    mutate_bo_preset_store(_mutate)


@socketio.on("request_preset_deployment_catalog")
def handle_preset_deployment_catalog(data):
    context = _require_context(data)
    if context is None:
        return
    store = load_bo_preset_store()
    catalog = build_deployment_catalog(
        store,
        user_id=context.get("user_id"),
        is_app_admin=context.get("is_app_admin", False),
        room_role=context.get("room_role"),
        owner_names=owner_names_for_store(store),
        users=context["users"],
    )
    catalog["bookmarks"] = _bookmark_payload(context["state"], catalog)
    catalog["room"] = context["room"]
    socketio.emit("preset_deployment_catalog", catalog, to=request.sid)


@socketio.on("request_preset_deployment_preview")
def handle_preset_deployment_preview(data):
    context = _require_context(data)
    if context is None:
        return
    src = data if isinstance(data, dict) else {}
    request_version = src.get("request_version")
    payload = src.get("deployment") if isinstance(src.get("deployment"), dict) else data
    try:
        _validate_target_mode(context["state"], payload)
        summary = preview_deployment(
            context["state"],
            payload,
            load_bo_preset_store(),
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
    src = data if isinstance(data, dict) else {}
    operation_id = str(src.get("operation_id") or "").strip()
    if not operation_id or len(operation_id) > 128:
        _emit_error("invalid_operation_id", "配置操作IDが不正です。")
        return
    cached = _cached_operation(context["room"], operation_id, context["state"])
    if cached is not None:
        cached["duplicate"] = True
        socketio.emit("preset_deployment_applied", cached, to=request.sid)
        return
    payload = src.get("deployment") if isinstance(src.get("deployment"), dict) else src
    try:
        _validate_target_mode(context["state"], payload)
        summary, logs = apply_deployment(
            context["state"],
            payload,
            load_bo_preset_store(),
            **_manager_context(context),
        )
    except PresetDeploymentError as ex:
        _emit_error(ex.code, ex.message, refresh_required=ex.refresh_required)
        return
    except Exception:
        logger.exception("preset deployment apply failed: room=%s", context["room"])
        _emit_error("apply_failed", "配置を確定できませんでした。")
        return

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
        f"[Preset] 味方{summary['added']['ally']}体・敵{summary['added']['enemy']}体を配置しました。",
        "info",
    )
    try:
        _touch_used_records(payload)
    except Exception:
        # 配置済みルーム状態をlast_used_at更新失敗で巻き戻さない。
        logger.exception("preset last_used_at update failed: room=%s", context["room"])
    socketio.emit("preset_deployment_applied", response, to=request.sid)
