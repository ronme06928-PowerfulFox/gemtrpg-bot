"""ログイン中の本人の図鑑に必要な出会いと敵ユニットを返す。"""
from datetime import timezone

from flask import Blueprint, g, jsonify

from manager.utils import session_required
from manager.catalog.kinds import MARK_LABELS
from manager.units.repository import entry_json
from models import CatalogEncounter, CatalogEntry

encyclopedia_bp = Blueprint("encyclopedia", __name__)


def _utc(value):
    """SQLite は時差なし、PostgreSQL は時差付きで返すので、どちらも UTC にそろえる。"""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@encyclopedia_bp.get("/api/encyclopedia")
@session_required
def get_encyclopedia():
    user = g.authenticated_user
    can_view_all = bool(user.is_catalog_author or user.is_app_admin)
    encounters = CatalogEncounter.query.filter_by(user_id=user.id).order_by(
        CatalogEncounter.kind, CatalogEncounter.entry_id).all()
    seen_units = {row.entry_id for row in encounters if row.kind == "unit"}
    units = []
    for row in CatalogEntry.query.filter_by(kind="unit", deprecated=False).order_by(CatalogEntry.entry_id):
        if row.payload.get("allow_enemy", True) is False:
            continue
        if not can_view_all:
            if "hollow" in row.payload.get("marks", []):
                continue
            if row.visibility != "public" and row.entry_id not in seen_units:
                continue
        units.append(entry_json(row))
    return jsonify(
        can_view_all=can_view_all,
        is_catalog_author=bool(user.is_catalog_author),
        mark_labels=MARK_LABELS,
        encounters=[{
            "kind": row.kind, "entry_id": row.entry_id,
            "first_seen_at": _utc(row.first_seen_at).isoformat().replace("+00:00", "Z"),
        } for row in encounters],
        units=units,
    )
