"""計画42で追加する分類・ACL・複製・ブックマークSocketルート。"""

import copy
import json
import time
import uuid

from flask import request

from extensions import db, socketio
from manager.battle_only_catalog_access import (
    capabilities,
    clear_collection_references,
    get_record,
    normalize_record_security,
    record_map,
)
from manager.battle_only_presets import (
    load_store,
    mutate_store,
    normalize_access_control,
    normalize_catalog_meta,
    normalize_collection_record,
)
from manager.room_access import GM_ROLES
from manager.room_manager import get_room_state, save_specific_room_state
from models import User
from events.battle_only.catalog_access_context import (
    catalog_request_context,
    check_expected_updated_at,
)


TYPE_PREFIXES = {
    "character": "bop",
    "enemy_formation": "bof",
    "ally_formation": "baf",
    "stage": "bos",
    "collection": "boc",
}


def _now_ms():
    return int(time.time() * 1000)


def _new_id(record_type):
    return f"{TYPE_PREFIXES.get(record_type, 'bor')}_{uuid.uuid4().hex[:12]}"


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _emit_error(event_name, code, message, **extra):
    payload = {"error": code, "message": message}
    payload.update(extra)
    socketio.emit(event_name, payload, to=request.sid)


def _require_room_manager(context, event_name):
    if context.get("room") and context.get("room_role") in GM_ROLES:
        return True
    _emit_error(event_name, "permission_denied", "対象ルームのowner・gm権限が必要です。")
    return False


def _record_caps(context, record):
    return capabilities(
        record,
        user_id=context.get("user_id"),
        is_app_admin=context.get("is_app_admin"),
        room_role=context.get("room_role"),
    )


def _validate_collection_meta(store, context, meta):
    normalized = normalize_catalog_meta(meta)
    collection_id = normalized.get("collection_id")
    if not collection_id:
        normalized["section_id"] = None
        return normalized
    collection = get_record(store, "collection", collection_id)
    if not isinstance(collection, dict) or not _record_caps(context, collection).get("can_view"):
        raise ValueError("指定したコレクションを利用できません。")
    section_id = normalized.get("section_id")
    if section_id:
        section_ids = {
            str(row.get("id") or "").strip()
            for row in collection.get("sections", [])
            if isinstance(row, dict)
        }
        if section_id not in section_ids:
            raise ValueError("指定したコレクション内区分が見つかりません。")
    return normalized


@socketio.on("request_bo_collection_save")
def handle_bo_collection_save(data):
    src = data if isinstance(data, dict) else {}
    payload = src.get("payload") if isinstance(src.get("payload"), dict) else src
    context = catalog_request_context(src)
    incoming_id = str(payload.get("id") or "").strip()
    current = get_record(load_store(), "collection", incoming_id) if incoming_id else None
    if current is None:
        if not context.get("user_id") or not (
            context.get("is_app_admin") or context.get("room_role") in GM_ROLES
        ):
            _emit_error("bo_collection_error", "permission_denied", "コレクションの作成権限がありません。")
            return
        allow_acl = True
    else:
        caps = _record_caps(context, current)
        if not caps.get("can_edit"):
            _emit_error("bo_collection_error", "permission_denied", "このコレクションを編集できません。")
            return
        if not check_expected_updated_at(src, current):
            _emit_error("bo_collection_error", "conflict", "他の利用者が先に更新しました。")
            return
        allow_acl = caps.get("can_manage_acl", False)

    saved = {}
    try:
        def _mutator(store):
            rows = record_map(store, "collection", create=True)
            existing = rows.get(incoming_id) if incoming_id else None
            if existing is not None and not check_expected_updated_at(src, existing):
                raise RuntimeError("conflict")
            work = copy.deepcopy(existing or {})
            work.update(copy.deepcopy(payload))
            work["id"] = incoming_id or _new_id("collection")
            work["updated_at"] = _now_ms()
            if not existing:
                work["created_at"] = work["updated_at"]
                work["created_by"] = str(context["user_info"].get("username") or "")
            if allow_acl and isinstance(work.get("access_control"), dict):
                requested_acl = normalize_access_control(
                    work.get("access_control"),
                    legacy_visibility=work.get("visibility", "restricted"),
                    owner_user_id=context.get("user_id"),
                )
                old_owner = str(((existing or {}).get("access_control") or {}).get("owner_user_id") or "")
                new_owner = str(requested_acl.get("owner_user_id") or "")
                if existing and new_owner and new_owner != old_owner:
                    if db.session.get(User, new_owner) is None:
                        raise ValueError("移譲先ユーザーが存在しません。")
                    if old_owner:
                        requested_acl["editor_user_ids"] = [old_owner, *requested_acl["editor_user_ids"]]
                work["access_control"] = requested_acl
            secured = normalize_record_security(
                work,
                creator_user_id=context.get("user_id"),
                existing=existing,
                allow_acl=allow_acl,
            )
            secured.pop("catalog_meta", None)
            normalized = normalize_collection_record(secured, fallback_id=work["id"])
            if not normalized or not str(normalized.get("name") or "").strip():
                raise ValueError("コレクション名は必須です。")
            old_sections = {
                str(row.get("id") or "") for row in (existing or {}).get("sections", [])
                if isinstance(row, dict)
            }
            new_sections = {
                str(row.get("id") or "") for row in normalized.get("sections", [])
                if isinstance(row, dict)
            }
            for removed_section in old_sections - new_sections:
                clear_collection_references(store, normalized["id"], section_id=removed_section)
            rows[normalized["id"]] = normalized
            saved.update(copy.deepcopy(normalized))

        mutate_store(_mutator)
        socketio.emit("bo_collection_saved", {"record": saved, "id": saved.get("id")}, to=request.sid)
    except RuntimeError as exc:
        if str(exc) == "conflict":
            _emit_error("bo_collection_error", "conflict", "他の利用者が先に更新しました。再読み込みしてください。")
        else:
            _emit_error("bo_collection_error", "save_failed", str(exc))
    except (TypeError, ValueError) as exc:
        _emit_error("bo_collection_error", "invalid_payload", str(exc))


@socketio.on("request_bo_collection_delete")
def handle_bo_collection_delete(data):
    context = catalog_request_context(data)
    collection_id = str((data or {}).get("id") or "").strip()
    try:
        changed = {"records": 0}

        def _mutator(store):
            rows = record_map(store, "collection", create=True)
            current = rows.get(collection_id)
            if not isinstance(current, dict):
                raise RuntimeError("not_found")
            if not _record_caps(context, current).get("can_delete"):
                raise RuntimeError("permission_denied")
            changed["records"] = clear_collection_references(store, collection_id)
            del rows[collection_id]

        mutate_store(_mutator)
        socketio.emit(
            "bo_collection_deleted",
            {"id": collection_id, "unclassified_records": changed["records"]},
            to=request.sid,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = "コレクションが見つかりません。" if code == "not_found" else "このコレクションを削除できません。"
        _emit_error("bo_collection_error", code, message)


@socketio.on("request_bo_record_metadata_save")
def handle_bo_record_metadata_save(data):
    src = data if isinstance(data, dict) else {}
    context = catalog_request_context(src)
    record_type = str(src.get("record_type") or "").strip()
    record_id = str(src.get("id") or "").strip()
    current = get_record(load_store(), record_type, record_id)
    if not isinstance(current, dict):
        _emit_error("bo_record_metadata_error", "not_found", "対象レコードが見つかりません。")
        return
    caps = _record_caps(context, current)
    if not caps.get("can_edit"):
        _emit_error("bo_record_metadata_error", "permission_denied", "このレコードを編集できません。")
        return
    if not check_expected_updated_at(src, current):
        _emit_error("bo_record_metadata_error", "conflict", "他の利用者が先に更新しました。")
        return

    saved = {}
    try:
        def _mutator(store):
            rows = record_map(store, record_type, create=True)
            record = rows.get(record_id)
            if not isinstance(record, dict):
                raise RuntimeError("not_found")
            if not check_expected_updated_at(src, record):
                raise RuntimeError("conflict")
            record["catalog_meta"] = _validate_collection_meta(store, context, src.get("catalog_meta"))
            if "access_control" in src:
                if not caps.get("can_manage_acl"):
                    raise RuntimeError("permission_denied")
                requested_acl = normalize_access_control(
                    src.get("access_control"),
                    legacy_visibility=record.get("visibility", "restricted"),
                    owner_user_id=(record.get("access_control") or {}).get("owner_user_id"),
                )
                old_owner = str((record.get("access_control") or {}).get("owner_user_id") or "")
                new_owner = str(requested_acl.get("owner_user_id") or "")
                if new_owner and new_owner != old_owner:
                    if db.session.get(User, new_owner) is None:
                        raise ValueError("移譲先ユーザーが存在しません。")
                    if old_owner:
                        requested_acl["editor_user_ids"] = [old_owner, *requested_acl["editor_user_ids"]]
                    requested_acl = normalize_access_control(requested_acl, legacy_visibility=requested_acl["viewer_mode"])
                record["access_control"] = requested_acl
                record["visibility"] = requested_acl["viewer_mode"]
            record["updated_at"] = _now_ms()
            record["updated_by"] = str(context["user_info"].get("username") or record.get("updated_by") or "")
            saved.update(copy.deepcopy(record))

        mutate_store(_mutator)
        socketio.emit(
            "bo_record_metadata_saved",
            {"record_type": record_type, "id": record_id, "record": saved},
            to=request.sid,
        )
    except RuntimeError as exc:
        code = str(exc)
        message = "他の利用者が先に更新しました。再読み込みしてください。" if code == "conflict" else "メタデータを保存できません。"
        _emit_error("bo_record_metadata_error", code, message)
    except (TypeError, ValueError) as exc:
        _emit_error("bo_record_metadata_error", "invalid_payload", str(exc))


def _validate_duplicate_references(store, context, record_type, record):
    refs = []
    if record_type in {"enemy_formation", "ally_formation"}:
        refs = [("character", row.get("preset_id")) for row in record.get("members", []) if isinstance(row, dict)]
    elif record_type == "stage":
        refs = [
            ("enemy_formation", record.get("enemy_formation_id")),
            ("ally_formation", record.get("ally_formation_id")),
        ]
    for ref_type, ref_id in refs:
        if not ref_id:
            continue
        child = get_record(store, ref_type, ref_id)
        if not isinstance(child, dict) or not _record_caps(context, child).get("can_use"):
            raise ValueError("利用できない参照があるため複製できません。")


@socketio.on("request_bo_record_duplicate")
def handle_bo_record_duplicate(data):
    src = data if isinstance(data, dict) else {}
    context = catalog_request_context(src)
    record_type = str(src.get("record_type") or "").strip()
    record_id = str(src.get("id") or "").strip()
    source_store = load_store()
    source = get_record(source_store, record_type, record_id)
    if not isinstance(source, dict) or not _record_caps(context, source).get("can_view"):
        _emit_error("bo_record_duplicate_error", "not_found", "複製元を利用できません。")
        return
    if not context.get("user_id"):
        _emit_error("bo_record_duplicate_error", "permission_denied", "ログインが必要です。")
        return
    try:
        _validate_duplicate_references(source_store, context, record_type, source)
        saved = {}

        def _mutator(store):
            rows = record_map(store, record_type, create=True)
            clone = copy.deepcopy(source)
            clone["id"] = _new_id(record_type)
            clone["name"] = f"{str(source.get('name') or record_id)} のコピー"
            clone["created_at"] = _now_ms()
            clone["updated_at"] = clone["created_at"]
            clone["created_by"] = str(context["user_info"].get("username") or "")
            clone["updated_by"] = clone["created_by"]
            clone["access_control"] = {
                "owner_user_id": context.get("user_id"),
                "editor_user_ids": [],
                "viewer_mode": "restricted",
                "viewer_user_ids": [],
            }
            clone["visibility"] = "restricted"
            clone.pop("capabilities", None)
            clone.pop("owner_display_name", None)
            clone.pop("shared_via", None)
            rows[clone["id"]] = clone
            saved.update(copy.deepcopy(clone))

        mutate_store(_mutator)
        socketio.emit(
            "bo_record_duplicated",
            {"record_type": record_type, "id": saved.get("id"), "record": saved},
            to=request.sid,
        )
    except ValueError as exc:
        _emit_error("bo_record_duplicate_error", "invalid_reference", str(exc))


def _normal_export_record(record, record_type):
    exported = copy.deepcopy(record)
    for key in ("access_control", "capabilities", "owner_display_name", "shared_via"):
        exported.pop(key, None)
    if record_type == "ally_formation":
        for member in exported.get("members", []):
            if isinstance(member, dict):
                member.pop("user_id", None)
    return exported


@socketio.on("request_bo_record_export_v3")
def handle_bo_record_export_v3(data):
    src = data if isinstance(data, dict) else {}
    context = catalog_request_context(src)
    record_type = str(src.get("record_type") or "").strip()
    record_id = str(src.get("id") or "").strip()
    full_backup = bool(src.get("full_backup", False))
    record = get_record(load_store(), record_type, record_id)
    if not isinstance(record, dict):
        _emit_error("bo_record_export_v3_error", "not_found", "対象レコードが見つかりません。")
        return
    caps = _record_caps(context, record)
    if not caps.get("can_view") or (full_backup and not caps.get("can_manage_acl")):
        _emit_error("bo_record_export_v3_error", "permission_denied", "この形式では出力できません。")
        return
    exported = copy.deepcopy(record) if full_backup else _normal_export_record(record, record_type)
    content = json.dumps(
        {"schema": "battle_only_record.v3", "record_type": record_type, "record": exported},
        ensure_ascii=False,
        indent=2,
    )
    socketio.emit(
        "bo_record_export_v3",
        {"filename": f"{record_type}_{record_id}.json", "content": content, "full_backup": full_backup},
        to=request.sid,
    )


def _bookmark_payload(room, context):
    state = get_room_state(room) or {}
    bo = state.get("battle_only") if isinstance(state.get("battle_only"), dict) else {}
    bookmarks = bo.get("preset_bookmarks") if isinstance(bo.get("preset_bookmarks"), list) else []
    store = load_store()
    result = []
    for bookmark in sorted(
        (row for row in bookmarks if isinstance(row, dict)),
        key=lambda row: (_safe_int(row.get("sort_order"), 2147483647), str(row.get("id") or "")),
    ):
        item = copy.deepcopy(bookmark)
        target = get_record(store, item.get("target_type"), item.get("target_id"))
        if isinstance(target, dict) and _record_caps(context, target).get("can_view"):
            item["available"] = True
            item["target_name"] = str(target.get("name") or item.get("target_id") or "")
            item["collection_id"] = (
                target.get("id") if item.get("target_type") == "collection"
                else (target.get("catalog_meta") or {}).get("collection_id")
            )
        else:
            item["available"] = False
            item["target_name"] = "利用できないブックマーク"
            item.pop("collection_id", None)
        result.append(item)
    return result


@socketio.on("request_bo_bookmark_list")
def handle_bo_bookmark_list(data):
    context = catalog_request_context(data)
    if not _require_room_manager(context, "bo_bookmark_error"):
        return
    socketio.emit(
        "bo_bookmark_list",
        {"room": context["room"], "bookmarks": _bookmark_payload(context["room"], context)},
        to=request.sid,
    )


@socketio.on("request_bo_bookmark_save")
def handle_bo_bookmark_save(data):
    src = data if isinstance(data, dict) else {}
    context = catalog_request_context(src)
    if not _require_room_manager(context, "bo_bookmark_error"):
        return
    target_type = str(src.get("target_type") or "").strip()
    target_id = str(src.get("target_id") or "").strip()
    if target_type not in TYPE_PREFIXES or not target_id:
        _emit_error("bo_bookmark_error", "invalid_payload", "ブックマーク対象が不正です。")
        return
    target = get_record(load_store(), target_type, target_id)
    if not isinstance(target, dict) or not _record_caps(context, target).get("can_view"):
        _emit_error("bo_bookmark_error", "not_found", "ブックマーク対象を利用できません。")
        return
    state = get_room_state(context["room"])
    bo = state.setdefault("battle_only", {})
    bookmarks = bo.setdefault("preset_bookmarks", [])
    if not isinstance(bookmarks, list):
        bookmarks = []
        bo["preset_bookmarks"] = bookmarks
    now = _now_ms()
    current = next((row for row in bookmarks if isinstance(row, dict) and row.get("target_type") == target_type and row.get("target_id") == target_id), None)
    if current is None:
        current = {
            "id": f"rbm_{uuid.uuid4().hex[:12]}",
            "target_type": target_type,
            "target_id": target_id,
            "created_by_user_id": context.get("user_id"),
            "created_at": now,
        }
        bookmarks.append(current)
    current.update({
        "label": str(src.get("label") or current.get("label") or target.get("name") or "").strip(),
        "note": str(src.get("note") or current.get("note") or "").strip(),
        "sort_order": int(src.get("sort_order", current.get("sort_order", len(bookmarks) * 10)) or 0),
        "collection_id": (
            target_id if target_type == "collection"
            else (target.get("catalog_meta") or {}).get("collection_id")
        ),
        "updated_at": now,
    })
    save_specific_room_state(context["room"])
    socketio.emit(
        "bo_bookmark_list",
        {"room": context["room"], "bookmarks": _bookmark_payload(context["room"], context)},
        to=request.sid,
    )


@socketio.on("request_bo_bookmark_delete")
def handle_bo_bookmark_delete(data):
    src = data if isinstance(data, dict) else {}
    context = catalog_request_context(src)
    if not _require_room_manager(context, "bo_bookmark_error"):
        return
    bookmark_id = str(src.get("id") or "").strip()
    state = get_room_state(context["room"])
    bo = state.setdefault("battle_only", {})
    bookmarks = bo.get("preset_bookmarks") if isinstance(bo.get("preset_bookmarks"), list) else []
    bo["preset_bookmarks"] = [
        row for row in bookmarks
        if not isinstance(row, dict) or str(row.get("id") or "") != bookmark_id
    ]
    save_specific_room_state(context["room"])
    socketio.emit(
        "bo_bookmark_list",
        {"room": context["room"], "bookmarks": _bookmark_payload(context["room"], context)},
        to=request.sid,
    )
