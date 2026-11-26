"""Exercise PR35-12 in a normal room on a disposable copy of the app DB."""

import argparse
import json
import os
import sqlite3
from contextlib import closing
from urllib.parse import urlencode
from uuid import uuid4

from scripts.hollow_data_proto.check_app import BASE, DB, DB_DIR, api, launch_and_verify, register
from scripts.hollow_run_check import socket_call, wait_for


def state_effect(timing, state, value, target, **fields):
    return {"timing": timing, "type": "APPLY_STATE", "state_name": state,
            "value": value, "target": target, **fields}


BLEEDING = {"source": "target", "param": "出血", "operator": "GT", "value": 0}
DEFEATED_WHILE_BLEEDING = {**BLEEDING, "source": "trigger_target"}
BUFFS = {
    "止血帯の切れ端": [state_effect("START_ROUND", "出血", -2, "self")],
    "獣の爪飾り": [state_effect("HIT", "出血", 1, "target", condition={
        "source": "skill", "param": "属性", "operator": "EQUALS", "value": "斬撃",
    })],
    "裂け目の縫い針": [state_effect("WIN", "出血", 3, "target")],
    "群れ狩りの角笛": [{
        "timing": "END_ROUND", "type": "APPLY_BUFF_FROM_CHARACTER_COUNT", "target": "self",
        "buff_id": "Bu-30", "buff_name": "蓄力", "value_per_character": 2, "apply_to": "stack",
        "lasting": -1, "character_filter": {"team": "enemy", "alive": True, "condition": BLEEDING},
    }],
    "血河の舟": [
        state_effect("ON_KILL", "出血", 3, "FILTERED_CHARACTERS", condition=DEFEATED_WHILE_BLEEDING,
                     character_filter={"team": "enemy", "alive": True, "condition": BLEEDING}),
        state_effect("ON_KILL", "HP", 5, "ALL_ALLIES", condition=DEFEATED_WHILE_BLEEDING),
    ],
}
BUFF_IDS = dict(zip(BUFFS, (f"Bu-{number}" for number in range(901, 906)), strict=True))


def seed_buffs():
    assert "GEMTRPG_CHECK_DB" in os.environ and DB.is_relative_to(DB_DIR) and DB.is_file()
    with closing(sqlite3.connect(DB)) as conn, conn:
        for name, rows in BUFFS.items():
            payload = {"name": name, "default_duration": -1, "effect": {"effects": rows}}
            conn.execute(
                "INSERT INTO catalog_entries (kind, entry_id, payload, visibility, revision, deprecated, updated_at)"
                " VALUES ('buff', ?, ?, 'public', 1, 0, CURRENT_TIMESTAMP)",
                (BUFF_IDS[name], json.dumps(payload, ensure_ascii=False)),
            )


def fighter(key, side, skill, hp, x):
    return {
        "id": key, "name": key, "type": side, "x": x, "y": 0, "size": 1,
        "hp": hp, "maxHp": hp + 20, "mp": 50, "maxMp": 50, "maxFp": 50,
        "params": [{"label": "物理補正", "value": 30 if side == "ally" else 1}],
        "states": [{"name": "FP", "value": 40}],
        "commands": skill["チャットパレット"],
    }


def resolve_round(page, get_state, room, number):
    def battle_state():
        return get_state().get("battle_state") or {}

    socket_call(page, "request_new_round", {"room": room})
    battle = wait_for(battle_state, lambda b: b.get("round") == number and b.get("phase") == "select")
    active = {slot["team"]: slot["slot_id"] for slot in battle["slots"].values()
              if not slot.get("target_only") and not slot.get("disabled") and slot.get("status") == "ready"}
    for team, opposing, skill in (("ally", "enemy", "Ps-01"), ("enemy", "ally", "E-00")):
        socket_call(page, "battle_intent_commit", {
            "room_id": room, "battle_id": battle["battle_id"], "slot_id": active[team],
            "skill_id": skill, "target": {"type": "single_slot", "slot_id": active[opposing]},
        })
    wait_for(battle_state, lambda b: all(b["intents"].get(slot_id, {}).get("committed")
                                        for slot_id in active.values()))
    socket_call(page, "battle_resolve_start", {"room_id": room})
    for _ in range(24):
        battle = wait_for(battle_state, lambda b: b["resolve"].get("presentation", {}).get("status")
                          in {"playing", "completed"})
        presentation = battle["resolve"]["presentation"]
        if presentation["status"] == "completed":
            break
        socket_call(page, "battle_resolve_flow_advance_request", {
            "room_id": room, "battle_id": battle["battle_id"], "round": number,
            "expected_step_index": presentation["current_step_index"],
            "expected_revision": presentation["revision"],
        })
    else:
        raise AssertionError("解決表示が完了しません")
    records = [effect for step in battle["resolve"]["trace"]
               for effect in step.get("fired_effects", (step.get("applied") or {}).get("fired_effects", []))]
    if not get_state().get("is_round_ended"):
        socket_call(page, "request_end_round", {"room": room, "expected_round": number})
    state = wait_for(get_state, lambda snapshot: snapshot.get("is_round_ended"))
    return state, records


def exercise(browser):
    token = uuid4().hex[:8]
    room = f"PR3512-{token}"
    page = register(browser, f"PR3512GM{token}")
    api(page, "POST", "/create_room", room_name=room, gm_pin="1234")
    skills = api(page, "GET", "/api/get_skill_data")
    catalog = api(page, "GET", "/api/get_buff_data")
    for name, buff_id in BUFF_IDS.items():
        assert catalog.get(buff_id, {}).get("effect", {}).get("effects") == BUFFS[name], buff_id
    chars = [fighter("owner", "ally", skills["Ps-01"], 200, 0),
             fighter("enemy", "enemy", skills["E-00"], 150, 1),
             {**fighter("observer", "enemy", skills["E-00"], 300, 2), "action_slot_mode": "none"}]
    api(page, "POST", "/save_room", room_name=room, state={
        "characters": chars, "combat_phase": "ready", "round": 0, "timeline": [], "logs": [],
    })
    page.goto(BASE + "/#sessions")
    page.wait_for_function("typeof joinRoom === 'function' && socket?.connected")
    page.evaluate("room => joinRoom(room, null, {role: 'GM', gmPin: '1234'})", room)
    page.wait_for_function("window.currentUserAttribute === 'GM'")

    def get_state():
        return api(page, "GET", "/load_room?" + urlencode({"name": room}))

    socket_call(page, "request_combat_enter", {"room": room})
    wait_for(get_state, lambda state: state["combat_phase"] != "ready")
    for buff_id in BUFF_IDS.values():
        socket_call(page, "request_gm_apply_buff", {
            "room": room, "target_id": "owner", "buff_id": buff_id, "lasting": -1,
        })
    for key in ("owner", "enemy", "observer"):
        socket_call(page, "request_gm_apply_state", {
            "room": room, "target_id": key, "state_name": "出血", "amount": 8,
        })
    fired = {}
    for number in range(1, 4):
        if number == 3:
            # Keep the last blow attributable to the skill, even with variable dice.
            enemy = next(char for char in state["characters"] if char["id"] == "enemy")
            socket_call(page, "request_gm_apply_state", {
                "room": room, "target_id": "enemy", "state_name": "HP", "amount": 3 - enemy["hp"],
            })
        state, records = resolve_round(page, get_state, room, number)
        for record in records:
            if record["name"] in BUFFS:
                fired.setdefault(record["name"], []).append(record["results"])
        enemy_hp = next(char["hp"] for char in state["characters"] if char["id"] == "enemy")
        print(f"R{number}: enemy HP {enemy_hp}")
        assert (enemy_hp <= 0) == (number == 3)
    logs = json.dumps(state["logs"], ensure_ascii=False)
    missing = [name for name in BUFFS if f"[{name}]" not in logs]
    assert not missing, (missing, fired, [log["message"] for log in state["logs"]])
    for name in BUFFS:
        print(f"{name}: ログあり, 解決表示 {fired.get(name, [])}")
    assert {"獣の爪飾り", "裂け目の縫い針", "血河の舟"} <= fired.keys(), fired
    assert [{"name": "出血", "delta": 3}] in fired["血河の舟"]
    assert [{"name": "HP", "delta": 5}] in fired["血河の舟"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", required=True)
    args = parser.parse_args()
    seed_buffs()
    launch_and_verify(args.app_python, exercise)
