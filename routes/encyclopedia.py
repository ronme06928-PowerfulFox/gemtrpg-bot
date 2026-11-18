"""ログイン中の本人の図鑑に必要な出会いと敵ユニットを返す。"""
from datetime import timezone

from flask import Blueprint, g, jsonify, request

from manager.utils import session_required
from manager.catalog.kinds import MARK_LABELS
from manager.units.repository import entry_json
from manager.room_access import GM_ROLES, resolve_room_role
from models import CatalogEncounter

encyclopedia_bp = Blueprint("encyclopedia", __name__)


def _utc(value):
    """SQLite は時差なし、PostgreSQL は時差付きで返すので、どちらも UTC にそろえる。"""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@encyclopedia_bp.get("/api/encyclopedia")
@session_required
def get_encyclopedia():
    user = g.authenticated_user
    room = request.args.get("room", "").strip()
    room_gm = bool(room and resolve_room_role(user.id, room) in GM_ROLES)
    can_view_all = bool(user.is_catalog_author or user.is_app_admin or room_gm)
    encounters = CatalogEncounter.query.filter_by(user_id=user.id).order_by(
        CatalogEncounter.kind, CatalogEncounter.entry_id).all()
    from manager.encyclopedia import unit_entries
    units = [entry_json(row) for row, _ in unit_entries(user,full=can_view_all)]
    return jsonify(
        can_view_all=can_view_all,
        is_catalog_author=bool(user.is_catalog_author),
        can_preview_own=bool(user.is_catalog_author or room_gm),
        mark_labels=MARK_LABELS,
        encounters=[{
            "kind": row.kind, "entry_id": row.entry_id,
            "first_seen_at": _utc(row.first_seen_at).isoformat().replace("+00:00", "Z"),
        } for row in encounters],
        units=units,
    )
