"""Recommendation pins on the choices the Hollow host decides."""

from manager.battle.common_manager import _get_round_transition_lock
from manager.hollow.map import next_nodes


def pin_scene(state, run):
    """Return the pending decision as (scene key, pinnable options), or None."""
    if run.get("status") != "in_progress" or state.get("combat_phase") == "active" or run.get("fusion"):
        return None
    if reward := run.get("reward"):
        return f"reward:{reward['floor']}", [*reward["relic_ids"], "skip"]
    if candidates := run.get("map_candidates"):
        return f"maps:{candidates['tier']}", [row["map_id"] for row in candidates["maps"]]
    event = run.get("current_event") or {}
    if event.get("type") in ("miasma", "chest") and not event.get("resolved"):
        options = [str(index) for index in range(len(event["choices"]))] if event["type"] == "miasma" else ["take", "skip"]
        return f"{event['type']}:{run['floor']}", options
    layout = run.get("map")
    if layout and not run.get("next_tier_error"):
        return f"node:{layout['tier']}:{layout['current']}", [*next_nodes(layout), "retreat"]
    return None


def set_pin(room, user_id, scene, option):
    from manager.hollow.host import can_manage_hollow
    from manager.hollow.rooms import is_hollow_room
    from manager.room_access import get_membership_role
    from manager.room_manager import get_room_state, save_specific_room_state

    with _get_round_transition_lock(room):
        if not is_hollow_room(room) or not get_membership_role(user_id, room):
            raise PermissionError("部屋の参加者だけがピンを立てられます")
        if can_manage_hollow(room, user_id):
            raise PermissionError("ホストとオーナーは札を選んで決めます")
        state = get_room_state(room)
        run = state["hollow"]["run"]
        current = pin_scene(state, run)
        if current is None or current[0] != scene:
            raise ValueError("この場面ではピンを立てられません")
        if option not in current[1]:
            raise ValueError("選べる札にピンを立ててください")
        pins = run.get("pins")
        if not pins or pins["scene"] != scene:
            pins = run["pins"] = {"scene": scene, "by_user": {}}
        by_user = pins["by_user"]
        if by_user.get(user_id) == option:
            del by_user[user_id]
        else:
            by_user[user_id] = option
        save_specific_room_state(room)


def project_pins(state, run):
    """Keep only the live scene's pins, minus the current host's, in a participant copy."""
    current = pin_scene(state, run)
    pins = run.get("pins") or {}
    host = state["hollow"].get("host_user_id")
    live = current and pins.get("scene") == current[0]
    run["pins"] = {"scene": current and current[0],
                   "by_user": {user: option for user, option in pins["by_user"].items() if user != host} if live else {}}


def drop_member_pin(state, user_id):
    (state["hollow"].get("run", {}).get("pins") or {}).get("by_user", {}).pop(user_id, None)
