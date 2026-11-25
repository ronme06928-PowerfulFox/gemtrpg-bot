"""ログイン中の本人の図鑑に必要な出会いと敵ユニットを返す。"""
from datetime import timezone

from flask import Blueprint, g, jsonify, request

from manager.utils import session_required
from manager.catalog.kinds import MARK_LABELS
from manager.encyclopedia import can_view_hollow, hollow_reward_entries, unit_entries
from manager.units.repository import entry_json
from manager.room_access import GM_ROLES, resolve_room_role
from models import CatalogEncounter, CatalogEntry

encyclopedia_bp = Blueprint("encyclopedia", __name__)


def _utc(value):
    """SQLite は時差なし、PostgreSQL は時差付きで返すので、どちらも UTC にそろえる。"""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@encyclopedia_bp.get("/api/encyclopedia")
@session_required
def get_encyclopedia():
    user = g.authenticated_user
    room = request.args.get("room", "").strip()
    from manager.practice_rooms import is_practice
    from manager.battle.hidden_passives import redact_hidden_passives

    room_gm = bool(room and not is_practice(room) and resolve_room_role(user.id, room) in GM_ROLES)
    can_view_all = bool(user.is_catalog_author or user.is_app_admin or room_gm)
    encounters = CatalogEncounter.query.filter_by(user_id=user.id).order_by(
        CatalogEncounter.kind, CatalogEncounter.entry_id).all()
    if not can_view_hollow(user):
        encounters = [row for row in encounters if not row.entry_id.startswith(("HBu-", "HI-"))]
        seen_units = {row.entry_id for row in encounters if row.kind == "unit"}
        if seen_units:
            hidden = {entry_id for (entry_id,) in CatalogEntry.query.with_entities(CatalogEntry.entry_id).filter(
                CatalogEntry.kind == "unit", CatalogEntry.payload["domain"].as_string() == "hollow",
                CatalogEntry.entry_id.in_(seen_units),
            )}
            encounters = [row for row in encounters if row.kind != "unit" or row.entry_id not in hidden]
    units = [entry_json(row) for row, _ in unit_entries(user, full=can_view_all)]
    if not can_view_all:
        for unit in units:
            unit["payload"] = redact_hidden_passives(unit["payload"])
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
        hollow_buffs=[entry_json(row) for row in hollow_reward_entries(user, "hollow_buff")],
        hollow_items=[entry_json(row) for row in hollow_reward_entries(user, "hollow_item")],
    )
