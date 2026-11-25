"""Party composition while the expedition is forming."""

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
    if action == "add":
        if char_id not in _ally_ids(state) or char_id in order:
            raise ValueError("部屋にいる未編成の味方を選んでください")
        if len(order) >= PARTY_SIZE:
            raise ValueError("パーティは6体までです")
        order.append(char_id)
    elif action == "remove" and char_id in order:
        order.remove(char_id)
    elif action == "move" and char_id in order and type(index) is int and 0 <= index < len(order):
        order.remove(char_id)
        order.insert(index, char_id)
    else:
        raise ValueError("編成の操作が正しくありません")
    save_specific_room_state(room_name)
