"""Hollow host authority and membership order."""

from extensions import db, socketio, user_sids
from manager.battle.common_manager import _get_round_transition_lock
from manager.hollow.rooms import is_hollow_room
from models import Room, RoomMember, User


def active_members(room_name):
    return (db.session.query(RoomMember, User.name)
            .join(Room, Room.id == RoomMember.room_id)
            .join(User, User.id == RoomMember.user_id)
            .filter(Room.name == room_name, RoomMember.revoked_at.is_(None))
            .order_by(RoomMember.joined_at.asc().nulls_last(), RoomMember.id).all())


def member_rows(room_name):
    return [{"id": member.user_id, "name": name, "role": member.role}
            for member, name in active_members(room_name)]


def can_manage_hollow(room_name, user_id):
    """The current host and any current owner may operate the expedition."""
    if not user_id or not is_hollow_room(room_name):
        return False
    from manager.room_access import OWNER, get_membership_role
    from manager.room_manager import get_room_state

    role = get_membership_role(user_id, room_name)
    return bool(role and (role == OWNER or get_room_state(room_name)["hollow"]["host_user_id"] == user_id))


def transfer_host(room_name, actor_id, target_id):
    from manager.room_access import get_membership_role
    from manager.room_manager import get_room_state, save_specific_room_state

    with _get_round_transition_lock(room_name):
        if not can_manage_hollow(room_name, actor_id):
            raise PermissionError("ホストかオーナーだけが譲渡できます")
        if not isinstance(target_id, str) or target_id == actor_id or not get_membership_role(target_id, room_name):
            raise ValueError("譲渡先の参加者を選んでください")
        get_room_state(room_name)["hollow"]["host_user_id"] = target_id
        save_specific_room_state(room_name)


def member_departed(room_name, user_id):
    """Apply a committed membership revocation to the live room."""
    from manager.room_manager import broadcast_state_update, broadcast_user_list, get_room_state, save_specific_room_state

    with _get_round_transition_lock(room_name):
        state = get_room_state(room_name)
        if state["hollow"]["host_user_id"] == user_id:
            members = active_members(room_name)
            state["hollow"]["host_user_id"] = members[0][0].user_id if members else None
            save_specific_room_state(room_name)
    if socketio.server:
        for sid, info in user_sids.copy().items():
            if info.get("room") == room_name and info.get("user_id") == user_id:
                socketio.server.leave_room(sid, room_name, namespace="/")
                info["room"] = None
                socketio.emit("hollow_membership_revoked", {"room": room_name}, to=sid)
    from manager.hollow.rooms import cleanup_finished_room
    if not cleanup_finished_room(room_name):
        broadcast_state_update(room_name)
        broadcast_user_list(room_name)
