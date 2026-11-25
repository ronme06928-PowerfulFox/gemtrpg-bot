"""Resolve the authenticated account and the room attached to this socket."""
from flask import request

from extensions import user_sids
from manager.room_access import PLAYER, resolve_room_role, role_can_gm
from manager.room_manager import get_user_info_from_sid
from manager.user_manager import is_catalog_author


def catalog_request_context(data):
    info = get_user_info_from_sid(request.sid) or {}
    user_id = info.get("user_id")
    room = str((data or {}).get("room") or "").strip()
    sid_room = user_sids.get(request.sid, {}).get("room")
    role = resolve_room_role(user_id, room, app_admin=bool(info.get('is_app_admin'))) if user_id and room and room == sid_room else None
    if role and not role_can_gm(room, role):
        role = PLAYER
    return {"user_info": info, "user_id": user_id, "room": room,
            "room_role": role, "is_author": bool(user_id and is_catalog_author(user_id))}
