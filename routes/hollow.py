"""Dungeon lobby and creation of an expedition room."""
from flask import Blueprint, jsonify, request, session
from sqlalchemy.exc import IntegrityError

from extensions import active_room_states, db
from manager.battle.combat_session import ensure_combat_session_defaults
from manager.hollow.rooms import initial_state, is_hollow, lobby_cards
from manager.join_code import review_hollow_join_code, set_join_code
from manager.practice_rooms import is_practice
from manager.room_access import OWNER, VIS_LISTED, ensure_membership, get_membership_role, revoke_membership
from manager.utils import session_required
from models import Room

hollow_bp = Blueprint("hollow", __name__)


@hollow_bp.get("/api/hollow/rooms")
@session_required
def list_rooms():
    return jsonify(rooms=lobby_cards(session["user_id"]))


@hollow_bp.post("/api/hollow/rooms")
@session_required
def create_room():
    data = request.get_json(silent=True)
    name = data.get("room_name") if isinstance(data, dict) else None
    name = name.strip() if isinstance(name, str) else ""
    if not name or len(name) > 100:
        return jsonify(error="部屋名を100文字以内で入力してください。"), 400
    if is_practice(name):
        return jsonify(error="予約されたルーム名です。"), 400
    if Room.query.filter_by(name=name).first():
        return jsonify(error="その部屋名は既に使用されています。"), 409

    owner_id = session["user_id"]
    state = initial_state(owner_id)
    ensure_combat_session_defaults(state, new_room=True)
    room = Room(name=name, owner_id=owner_id, data=state, lobby_visibility=VIS_LISTED)
    try:
        db.session.add(room)
        db.session.flush()
        ensure_membership(room.id, owner_id, OWNER, granted_by=owner_id, commit=False)
        code = set_join_code(name, commit=False)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if Room.query.filter_by(name=name).first():
            return jsonify(error="その部屋名は既に使用されています。"), 409
        raise
    active_room_states[name] = state
    return jsonify(room_name=name, join_code=code), 201, {"Cache-Control": "no-store"}


def _requested_room():
    data = request.get_json(silent=True)
    name = data.get("room_name") if isinstance(data, dict) else None
    return Room.query.filter_by(name=name).first() if isinstance(name, str) else None


@hollow_bp.post("/api/hollow/join_code")
@session_required
def join_code():
    room = _requested_room()
    if not is_hollow(room) or get_membership_role(session["user_id"], room.name) != OWNER:
        return jsonify(error="オーナー権限が必要です"), 403
    code = review_hollow_join_code(room)
    if code is None:
        return jsonify(error="参加コードは失効しています"), 409
    return jsonify(room_name=room.name, join_code=code), 200, {"Cache-Control": "no-store"}


@hollow_bp.post("/api/hollow/leave")
@session_required
def leave_room():
    room = _requested_room()
    user_id = session["user_id"]
    if not is_hollow(room) or not get_membership_role(user_id, room.name):
        return jsonify(error="参加中の部屋が見つかりません"), 404
    try:
        revoke_membership(room.name, user_id)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(room_name=room.name)
