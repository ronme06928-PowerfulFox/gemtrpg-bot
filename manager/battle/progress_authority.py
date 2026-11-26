"""Authority for battle progress, character operations, and playback handoff."""

from manager.hollow.rooms import is_hollow_room


def can_progress_battle(room, user, *, normalize_gm=False):
    if is_hollow_room(room):
        from manager.hollow.host import can_manage_hollow
        return can_manage_hollow(room, user.get("user_id"))
    attribute = user.get("attribute")
    if normalize_gm:
        attribute = str(attribute or "").strip().upper()
    return attribute == "GM"


def can_control_character(room, char_id, username, attribute, *, user_id=None):
    from manager.room_manager import get_room_state

    if user_id is not None and is_hollow_room(room):
        if can_progress_battle(room, {"user_id": user_id}):
            return True
        state = get_room_state(room)
        char = next((c for c in state.get("characters", []) if c.get("id") == char_id), None)
        if not char:
            return False
        if char.get("owner_id"):
            return char["owner_id"] == user_id
        return (char.get("owner") or state.get("character_owners", {}).get(char_id)) == username

    if attribute == "GM":
        return True
    return get_room_state(room).get("character_owners", {}).get(char_id) == username


def resolve_claim_candidates(room, controller_id):
    """Connected Hollow members in the highest available handoff tier."""
    from manager.hollow.host import active_members
    from manager.room_manager import get_users_in_room

    connected = {info.get("user_id") for info in get_users_in_room(room).values()}
    if controller_id and controller_id in connected:
        return set()
    members = {member.user_id for member, _ in active_members(room) if member.user_id in connected}
    leaders = {user_id for user_id in members if can_progress_battle(room, {"user_id": user_id})}
    return leaders or members


def can_claim_resolve(room, user, presentation):
    user_id = str(user.get("user_id") or "").strip()
    if not user_id:
        return False
    controller_id = presentation.get("controller_user_id")
    if is_hollow_room(room):
        return presentation.get("status") == "playing" and user_id in resolve_claim_candidates(room, controller_id)
    return user_id == str(controller_id or "").strip() or can_progress_battle(room, user, normalize_gm=True)


def add_resolve_presence(room, presentation):
    from manager.room_access import is_user_in_room

    controller_id = presentation.get("controller_user_id")
    presentation["controller_present"] = bool(controller_id and is_user_in_room(controller_id, room))
    if is_hollow_room(room):
        candidates = set()
        if presentation.get("status") == "playing" and not presentation["controller_present"]:
            candidates = resolve_claim_candidates(room, controller_id)
        presentation["claim_user_ids"] = sorted(candidates)
    return presentation
