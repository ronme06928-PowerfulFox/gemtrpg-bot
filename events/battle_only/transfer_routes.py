"""Socket routes for environment-neutral preset package export and import."""

import time

from flask import current_app, request

from extensions import db, socketio
from events.battle_only.catalog_access_context import catalog_request_context
from manager.battle_only_catalog_access import capabilities
from manager.battle_only_presets import load_store, mutate_store
from manager.preset_transfer import (
    PresetPackageError,
    apply_package,
    build_collection_package,
    package_json,
    preview_package,
)
from models import User


def _emit_error(code, message, *, details=None):
    payload = {"error": str(code), "message": str(message)}
    if details is not None:
        payload["details"] = details
    socketio.emit("bo_preset_package_error", payload, to=request.sid)


def _caps(context, record):
    return capabilities(
        record,
        user_id=context.get("user_id"),
        is_app_admin=context.get("is_app_admin", False),
        room_role=context.get("room_role"),
    )


def _resolve_owner(context, requested_owner_id=None):
    actor_id = str(context.get("user_id") or "").strip()
    if not actor_id:
        raise PresetPackageError("login_required", "プリセットの取込みにはログインが必要です。")
    requested = str(requested_owner_id or "").strip()
    if requested and requested != actor_id and not context.get("is_app_admin"):
        raise PresetPackageError("permission_denied", "別ユーザーを所有者に指定できるのは管理者だけです。")
    owner_id = requested if requested and context.get("is_app_admin") else actor_id
    owner = db.session.get(User, owner_id)
    if owner is None:
        raise PresetPackageError("owner_not_found", "指定した所有者が見つかりません。")
    return owner


@socketio.on("request_bo_collection_package_export")
def handle_bo_collection_package_export(data):
    src = data if isinstance(data, dict) else {}
    context = catalog_request_context(src)
    store = load_store()
    try:
        package = build_collection_package(
            store,
            src.get("collection_id"),
            can_view=lambda _resource_type, record: _caps(context, record).get("can_view", False),
        )
    except PresetPackageError as exc:
        _emit_error(exc.code, exc.message, details=exc.details)
        return
    except Exception:
        current_app.logger.exception("Failed to export preset collection package")
        _emit_error("persistence_error", "プリセットDBから移送JSONを作成できませんでした。")
        return
    collection_id = str(src.get("collection_id") or "collection").strip()
    socketio.emit(
        "bo_collection_package_exported",
        {
            "filename": f"preset_package_{collection_id}_{int(time.time())}.json",
            "content": package_json(package),
            "resource_count": len(package["resources"]),
        },
        to=request.sid,
    )


@socketio.on("request_bo_preset_package_preview")
def handle_bo_preset_package_preview(data):
    src = data if isinstance(data, dict) else {}
    context = catalog_request_context(src)
    try:
        owner = _resolve_owner(context, src.get("owner_user_id"))
        store = load_store()
        preview = preview_package(
            src.get("content"),
            store,
            can_update=lambda _resource_type, record: _caps(context, record).get("can_edit", False),
            can_use_existing=lambda _resource_type, record: _caps(context, record).get("can_use", False),
        )
        preview["owner"] = {"id": owner.id, "name": owner.name}
        socketio.emit("bo_preset_package_preview", preview, to=request.sid)
    except PresetPackageError as exc:
        _emit_error(exc.code, exc.message, details=exc.details)
    except Exception:
        current_app.logger.exception("Failed to preview preset package")
        _emit_error("persistence_error", "移送JSONの確認中にプリセットDBの操作に失敗しました。")


@socketio.on("request_bo_preset_package_import")
def handle_bo_preset_package_import(data):
    src = data if isinstance(data, dict) else {}
    context = catalog_request_context(src)
    result = {}
    try:
        owner = _resolve_owner(context, src.get("owner_user_id"))

        def _mutator(store):
            result.update(apply_package(
                src.get("content"),
                store,
                owner_user_id=owner.id,
                owner_name=owner.name,
                actions=src.get("actions"),
                expected_revisions=src.get("expected_revisions"),
                can_update=lambda _resource_type, record: _caps(context, record).get("can_edit", False),
                can_use_existing=lambda _resource_type, record: _caps(context, record).get("can_use", False),
            ))

        mutate_store(_mutator)
        socketio.emit("bo_preset_package_imported", result, to=request.sid)
    except PresetPackageError as exc:
        _emit_error(exc.code, exc.message, details=exc.details)
    except ValueError as exc:
        _emit_error("invalid_package", str(exc))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to import preset package")
        _emit_error("persistence_error", "移送JSONをプリセットDBへ登録できませんでした。")
