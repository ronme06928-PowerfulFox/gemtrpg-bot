"""Room state and the member-only dungeon lobby projection."""
from flask import has_app_context

from extensions import active_room_states, db
from models import Room, RoomMember, User

MODE = "hollow"
OPEN_STATUSES = ("forming", "in_progress")


def entry_state(room):
    cached = active_room_states.get(room.name)
    return cached if isinstance(cached, dict) else room.data or {}


def is_hollow(room):
    return room is not None and entry_state(room).get("play_mode") == MODE


def is_hollow_room(name):
    cached = active_room_states.get(name)
    if isinstance(cached, dict):
        return cached.get("play_mode") == MODE
    return bool(name and has_app_context() and is_hollow(Room.query.filter_by(name=name).first()))


def is_open(room):
    run = entry_state(room).get("hollow", {}).get("run", {})
    return run.get("status") in OPEN_STATUSES


def room_accepts_entry(name):
    if not is_hollow_room(name):
        return True
    room = Room.query.filter_by(name=name).first()
    return room is not None and is_open(room)


def initial_state(owner_id):
    return {
        "play_mode": MODE,
        "owner_id": owner_id,
        "characters": [], "timeline": [], "round": 0, "logs": [],
        "hollow": {"host_user_id": owner_id, "run": {"status": "forming"}},
        "party": {"order": []},
    }


def lobby_cards(user_id):
    members = (db.session.query(Room, RoomMember.role)
               .join(RoomMember, RoomMember.room_id == Room.id)
               .filter(RoomMember.user_id == user_id, RoomMember.revoked_at.is_(None))
               .order_by(Room.name).all())
    rooms = [(room, role) for room, role in members if is_hollow(room) and is_open(room)]
    names = {user.id: user.name for user in User.query.filter(User.id.in_({
        user_id
        for room, _ in rooms
        for user_id in (room.owner_id, entry_state(room)["hollow"].get("host_user_id"))
        if user_id
    }))}
    cards = []
    for room, role in rooms:
        state = entry_state(room)
        hollow = state["hollow"]
        run = hollow["run"]
        in_progress = run["status"] == "in_progress"
        order = state.get("party", {}).get("order", [])
        if in_progress:
            order = run.get("party_order", order)
        characters = {character["id"]: character["name"] for character in state.get("characters", [])
                      if isinstance(character, dict) and isinstance(character.get("id"), str) and character.get("name")}
        summary = {"status": run["status"]}
        if in_progress and "floor" in run:
            summary["floor"] = run["floor"]
        cards.append({
            "name": room.name, "your_role": role,
            "owner_name": names.get(room.owner_id),
            "host_name": names.get(hollow.get("host_user_id")),
            "party_names": [characters[key] for key in order if key in characters][:6],
            "run": summary,
            "requires_code": bool(room.join_code_hash),
        })
    return cards
