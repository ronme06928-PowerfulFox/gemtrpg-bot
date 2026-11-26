"""Party composition while the expedition is forming."""

from uuid import uuid4

from manager.hollow.host import can_manage_hollow

PARTY_SIZE = 6


def _ally_ids(state):
    return {char["id"] for char in state.get("characters", [])
            if isinstance(char, dict) and char.get("type") == "ally" and isinstance(char.get("id"), str)}


def prune_party(state):
    """Drop vanished or reclassified characters from the live roster."""
    if state.get("play_mode") != "hollow":
        return False
    order = state["party"]["order"]
    if not order:
        return False
    allies = _ally_ids(state)
    current = [char_id for char_id in order if char_id in allies]
    if current == order:
        return False
    state["party"]["order"] = current
    return True


def change_party(room_name, user_id, action, char_id, index=None):
    from manager.room_manager import get_room_state, save_specific_room_state

    if not can_manage_hollow(room_name, user_id):
        raise PermissionError("ホストかオーナーだけが編成を変更できます")
    state = get_room_state(room_name)
    if state["hollow"]["run"]["status"] != "forming":
        raise ValueError("パーティの並びは固定されています")
    if not isinstance(char_id, str):
        raise ValueError("キャラを選んでください")

    order = state["party"]["order"]
    if action == "remove" and char_id in order:
        order.remove(char_id)
        state["characters"] = [char for char in state["characters"] if char.get("id") != char_id]
        state.get("character_owners", {}).pop(char_id, None)
    elif action == "move" and char_id in order and type(index) is int and 0 <= index < len(order):
        order.remove(char_id)
        order.insert(index, char_id)
    else:
        raise ValueError("編成の操作が正しくありません")
    save_specific_room_state(room_name)


def add_owned_party(room_name, user_id, owned_ids, *, username):
    from manager.battle.common_manager import _get_round_transition_lock
    from manager.character_runtime import build_owned_character_for_play
    from manager.hollow.rooms import is_hollow_room
    from manager.room_access import get_membership_role
    from manager.room_manager import get_room_state, save_specific_room_state
    from models import OwnedCharacter

    with _get_round_transition_lock(room_name):
        if not is_hollow_room(room_name) or not get_membership_role(user_id, room_name):
            raise PermissionError("ホロウの部屋の参加者だけが追加できます")
        state = get_room_state(room_name)
        if state["hollow"]["run"]["status"] != "forming":
            raise ValueError("パーティの並びは固定されています")
        if not isinstance(owned_ids, list) or not 1 <= len(owned_ids) <= PARTY_SIZE or any(
            not isinstance(key, str) or not key or len(key) > 36 for key in owned_ids
        ):
            raise ValueError("追加する持ちキャラを1〜6人選んでください")
        order = state["party"]["order"]
        if len(order) + len(owned_ids) > PARTY_SIZE:
            raise ValueError("パーティは6体までです")
        added = {char.get("owned_character_id") for char in state["characters"]}
        if len(set(owned_ids)) != len(owned_ids) or added.intersection(owned_ids):
            raise ValueError("同じ持ちキャラは一度だけ追加できます")
        rows = {row.id: row for row in OwnedCharacter.query.filter_by(user_id=user_id, deleted_at=None)
                .filter(OwnedCharacter.id.in_(owned_ids)).all()}
        if len(rows) != len(owned_ids):
            raise ValueError("自分の持ちキャラだけを追加できます")

        additions = []
        for key in owned_ids:
            row = rows[key]
            char = build_owned_character_for_play(row.data, "ally")
            char.update(id=f"char_h_{uuid4().hex}", owned_character_id=key,
                        baseName=row.name, name=row.name, owner_id=user_id, owner=username, x=-1, y=-1)
            char.pop("source_unit_id", None)
            additions.append(char)
        state["characters"].extend(additions)
        order.extend(char["id"] for char in additions)
        state.setdefault("character_owners", {}).update({char["id"]: username for char in additions})
        save_specific_room_state(room_name)
