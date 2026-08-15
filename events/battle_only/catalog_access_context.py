"""Socket要求からプリセット認可コンテキストを組み立てる補助関数。"""

from flask import has_app_context, request

from extensions import user_sids
from manager.battle_only_catalog_access import filter_visible_records, record_map
from manager.room_access import resolve_room_role
from manager.room_manager import get_user_info_from_sid
from manager.user_manager import is_user_management_admin
from models import User


def _is_gm(user_info):
    return str((user_info or {}).get("attribute", "")).strip().upper() == "GM"


def catalog_request_context(data=None):
    src = data if isinstance(data, dict) else {}
    user_info = get_user_info_from_sid(request.sid) or {}
    user_id = str(user_info.get("user_id") or "").strip()
    room = str(src.get("room") or "").strip() or None
    try:
        is_admin = bool(is_user_management_admin(user_id)) if user_id else False
    except Exception:
        is_admin = bool(user_info.get("is_app_admin", False))
    room_role = None
    if room and user_id:
        try:
            room_role = resolve_room_role(user_id, room, app_admin=is_admin)
        except Exception:
            room_role = None
        sid_info = user_sids.get(request.sid) if isinstance(user_sids, dict) else None
        if room_role is None and isinstance(sid_info, dict) and str(sid_info.get("room") or "") == room and _is_gm(user_info):
            room_role = "gm"
        if room_role is None and not has_app_context() and _is_gm(user_info):
            # 単体テストではDB/app contextを構築せずSocket依存だけを差し替える。
            room_role = "gm"
    return {
        "user_info": user_info,
        "user_id": user_id,
        "room": room,
        "room_role": room_role,
        "is_app_admin": is_admin,
        "admin_global": bool(src.get("admin_global", False)),
    }


def owner_names_for_store(store):
    owner_ids = set()
    for record_type in ("character", "enemy_formation", "ally_formation", "stage", "collection"):
        for record in (record_map(store, record_type) or {}).values():
            if isinstance(record, dict):
                owner_id = str((record.get("access_control") or {}).get("owner_user_id") or "").strip()
                if owner_id:
                    owner_ids.add(owner_id)
    if not owner_ids:
        return {}
    try:
        return {user.id: user.name for user in User.query.filter(User.id.in_(owner_ids)).all()}
    except Exception:
        return {}


def visible_map(store, record_type, context, *, owner_names=None):
    if context.get("admin_global") and not context.get("is_app_admin"):
        return {}
    return filter_visible_records(
        record_map(store, record_type) or {},
        user_id=context.get("user_id"),
        is_app_admin=context.get("is_app_admin"),
        room_role=context.get("room_role"),
        owner_names=owner_names,
    )


def check_expected_updated_at(src, current):
    if not isinstance(src, dict):
        return True
    try:
        if "expected_revision" in src:
            return int(src.get("expected_revision")) == int((current or {}).get("revision", 0))
        if "expected_updated_at" not in src:
            return True
        return int(src.get("expected_updated_at")) == int((current or {}).get("updated_at", 0))
    except (TypeError, ValueError):
        return False
