"""Master data access for special passives used as hidden content."""
from flask import request, session

import extensions
from extensions import active_room_states, db
from manager.room_access import resolve_room_role, role_can_gm
from models import CatalogEncounter, CatalogEntry, User


def request_catalog_reader():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    if user is None or session.get("auth_version") != user.auth_version:
        return None, False, None
    room = request.args.get("room", "").strip()
    from manager.practice_rooms import is_practice
    role = resolve_room_role(user.id, room) if room else None
    full = user.is_catalog_author or user.is_app_admin or (role_can_gm(room, role) and not is_practice(room))
    return user, full, room if role else None


def undiscovered_passive_ids(user, room=None):
    units = CatalogEntry.query.filter_by(kind="unit", deprecated=False)
    configured = [row.payload for row in units]
    configured.extend(extensions.all_summon_template_data.copy().values())
    hidden = {row["passive_id"] for item in configured for row in item.get("hidden_passives", [])}
    if not user or not hidden:
        return hidden
    seen = CatalogEncounter.query.filter_by(user_id=user.id, kind="passive").filter(
        CatalogEncounter.entry_id.in_(hidden)
    )
    hidden.difference_update(row.entry_id for row in seen)
    if room:
        state = active_room_states.get(room, {})
        hidden.difference_update(key for char in state.get("characters", []) for key in char.get("SPassive", []))
    return hidden
