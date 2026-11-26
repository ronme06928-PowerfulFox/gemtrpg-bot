"""Exercise PR35-8 via the real app's Socket.IO connection on a disposable DB."""

import argparse
import json
import sys
from time import monotonic, sleep
from urllib.parse import urlencode
from uuid import uuid4

from scripts.hollow_data_proto.check_app import BASE, api, launch_and_verify, register
from scripts.hollow_seed import PREFIX


def socket_call(page, event, data=None):
    return page.evaluate("""([event, payload]) => new Promise((resolve, reject) => {
      socket.timeout(7000).emit(event, payload, (error, result) => error ? reject(error) : resolve(result));
    })""", [event, data or {}])


def command(page, event, **data):
    result = socket_call(page, event, data)
    assert result and result["ok"], (event, result)


def wait_for(get, predicate, timeout=15):
    deadline = monotonic() + timeout
    while True:
        result = get()
        if predicate(result):
            return result
        if monotonic() >= deadline:
            raise AssertionError(json.dumps(result, ensure_ascii=False)[:3500])
        sleep(.08)


def library(author, suffix):
    def save(kind, **payload):
        return api(author, "POST", f"/api/units/{kind}",
                   payload={"domain": "hollow", **payload})["entry"]

    foes = []
    for name in ("坑道の鉄級シュラーカー", "坑道の銅級シュラーカー"):
        grade = "鉄級" if "鉄級" in name else "銅級"
        foes.append(save("unit", name=f"{name} {suffix}", hp=8, tags=[f"等級:{grade}"],
                         allow_ally=False, allow_enemy=True, skills=[{"id": "E-00"}],
                         params=[{"label": "物理補正", "value": 3}]))
    formations = [save("formation", name=f"確認編成 {i} {suffix}", type="enemy",
                       members=[{"unit_id": foe["entry_id"], "count": 1}]) for i, foe in enumerate(foes, 1)]
    normal, elite = [row["entry_id"] for row in formations]

    def upsert(kind, key, **fields):
        existing = api(author, "GET", f"/api/units/{kind}?domain=hollow")["entries"]
        entry = next((r for r in existing if r["payload"].get(key) == fields[key]
                      and not r["deprecated"]), None)
        if entry is None:
            return save(kind, **fields)
        return api(author, "PUT", f"/api/units/{kind}/{entry['entry_id']}",
                   visibility=entry["visibility"], base_revision=entry["revision"],
                   payload={**entry["payload"], **fields})["entry"]

    stage = save("stage", name=f"確認舞台 {suffix}", enemy_formation_id=elite)
    for number, hp, attack in ((1, 1.2, 1.25), (2, 1.4, 1.4)):
        upsert("tier", "tier", tier=number, name=f"確認 T{number}", hp_multiplier=hp, attack_multiplier=attack)
        for index in range(2 if number == 1 else 1):
            save("hollow_map", tier=number, name=f"確認マップ {number}-{index + 1} {suffix}",
                 event_weights={"normal": 3, "elite": 2},
                 encounters={"normal": [{"formation_id": [normal, elite][index], "weight": 1}],
                             "elite": [{"formation_id": elite, "weight": 1}]},
                 boss_formation_id=[elite, normal][index], boss_stage_id=stage["entry_id"])
    return foes


def expedition(page, title, count, hp, strength):
    api(page, "POST", "/api/hollow/rooms", room_name=title)
    user = api(page, "GET", "/api/get_session_user")
    command_line = api(page, "GET", "/api/get_skill_data")["Ps-01"]["チャットパレット"]
    actors = [{
        "id": f"ally-{i}", "name": f"冒険者{i + 1}", "type": "ally", "owner_id": user["user_id"],
        "hp": hp, "maxHp": hp, "mp": 50, "maxMp": 50, "x": -1, "y": -1,
        "states": [{"name": "FP", "value": 50}],
        "params": [{"label": "物理補正", "value": strength}], "commands": command_line,
    } for i in range(count)]
    api(page, "POST", "/save_room", room_name=title, state={
        "characters": actors, "combat_phase": "ready", "round": 0, "timeline": [], "logs": [],
    })
    page.goto(BASE + "/#dungeon")
    page.locator(".dungeon-room").filter(has_text=title).get_by_role("button", name="入る").click()
    page.wait_for_function("socket.connected && !!document.querySelector('#dock-hollow-party')")
    for actor in actors:
        command(page, "hollow_party_change", action="add", char_id=actor["id"])
    command(page, "hollow_run_start")
    return lambda: api(page, "GET", "/load_room?" + urlencode({"name": title}))


def choose_map(page, get_state, tier, expected_count, *, name=None):
    waiting = wait_for(get_state, lambda state: state["hollow"]["run"].get("map_candidates"))
    candidates = waiting["hollow"]["run"]["map_candidates"]
    assert candidates["tier"] == tier and len(candidates["maps"]) == expected_count, candidates
    selected = next(row for row in candidates["maps"] if name is None or row["name"] == name)
    command(page, "hollow_choose_map", map_id=selected["map_id"], tier=tier)
    layout = get_state()["hollow"]["run"]["map"]
    assert layout["tier"] == tier and layout["map_id"] == selected["map_id"]
    return selected


def choose(page, state, floor):
    layout = state["hollow"]["run"]["map"]
    paths = [node for row in layout["rows"] for node in row]
    current = next((n for n in paths if n["id"] == layout["current"]), None)
    node = next(n for n in paths if n["floor"] == floor and (not current or n["id"] in current["next"]))
    command(page, "hollow_select_node", node_id=node["id"], tier=layout["tier"])


def resolve_round(page, get_state, room):
    state = get_state()
    battle = state["battle_state"]
    round_number = state["round"]
    active = [slot for slot in battle["slots"].values()
              if not slot.get("target_only") and not slot.get("disabled") and slot.get("status") == "ready"]
    allies = [slot["slot_id"] for slot in active if slot["team"] == "ally"]
    enemies = [slot["slot_id"] for slot in active if slot["team"] == "enemy"]
    assert allies and enemies, (allies, enemies, round_number)
    targets = [(source, enemies[i % len(enemies)], "Ps-01") for i, source in enumerate(allies)]
    targets += [(source, allies[i % len(allies)], "E-00") for i, source in enumerate(enemies)]
    for source, target, skill in targets:
        socket_call(page, "battle_intent_commit", {
            "room_id": room, "battle_id": battle["battle_id"], "slot_id": source,
            "skill_id": skill, "target": {"type": "single_slot", "slot_id": target},
        })
    wait_for(get_state, lambda s: all(s["battle_state"]["intents"].get(slot_id, {}).get("committed")
                                      for slot_id, _, _ in targets))
    socket_call(page, "battle_resolve_start", {"room_id": room})

    def next_message(s):
        if s["round"] != round_number or s["combat_phase"] == "ready":
            return True
        return s["battle_state"]["resolve"].get("presentation", {}).get("status") == "playing"

    for _ in range(24):
        state = wait_for(get_state, next_message)
        if state["round"] != round_number or state["combat_phase"] == "ready":
            return state
        battle = state["battle_state"]
        presentation = battle["resolve"]["presentation"]
        socket_call(page, "battle_resolve_flow_advance_request", {
            "room_id": room, "battle_id": battle["battle_id"], "round": round_number,
            "expected_step_index": presentation["current_step_index"], "expected_revision": presentation["revision"],
        })
    raise AssertionError("解決表示が完了しません")


def verify(browser, *, seeded=False):
    suffix = uuid4().hex[:6]
    author = register(browser, "RunAuthor" + suffix, author=True)
    if seeded:
        foes = [row for row in api(author, "GET", "/api/units/unit?domain=hollow")["entries"]
                if row["payload"]["name"].startswith(PREFIX + " ")]
    else:
        foes = library(author, suffix)
    definitions = {row["entry_id"]: row["payload"] for row in api(author, "GET", "/api/units/hollow_map?domain=hollow")["entries"]}
    winner = register(browser, "RunWinner" + suffix)
    win_room = "階の確認 " + suffix
    get_win = expedition(winner, win_room, 5, 150, 100)
    selected = choose_map(winner, get_win, 1, 2, name=f"{PREFIX} 青晶洞" if seeded else None)
    maps = [selected]
    floors = []
    for floor in range(1, 12):
        choose(winner, get_win(), floor)
        battle_seed = get_win()
        assert battle_seed["round"] == 1 and battle_seed["combat_phase"] == "active"
        for _ in range(5):
            state = resolve_round(winner, get_win, win_room)
            if state["combat_phase"] == "ready":
                break
        run = state["hollow"]["run"]
        assert run["log"][-1]["outcome"] == "VICTORY", run["current_event"]
        assert run["map"]["tier"] == (1 if floor <= 10 else 2)
        floor_result = run["log"][-1]
        definition = definitions[selected["map_id"]]
        if floor == 10:
            assert floor_result["type"] == "boss"
            assert floor_result["formation_id"] == definition["boss_formation_id"]
            assert floor_result["stage_id"] == definition["boss_stage_id"]
        else:
            kind = "normal" if floor_result["type"] == "battle" else "elite"
            assert floor_result["formation_id"] in [row["formation_id"] for row in definition["encounters"][kind]]
        floors.append({"map_id": selected["map_id"], **{key: floor_result[key] for key in
                       ("floor", "type", "formation_id", "stage_id", "hp_multiplier", "attack_percent", "outcome")}})
        if floor == 10:
            selected = choose_map(winner, get_win, 2, 1)
            maps.append(selected)
    command(winner, "hollow_retreat")
    retreat = get_win()["hollow"]["run"]["result"]
    assert retreat == {"floor": 11, "outcome": "RETREAT"}
    assert not api(winner, "GET", "/api/hollow/rooms")["rooms"]

    if seeded:
        return {"maps": maps, "floors": floors, "retreat": retreat}

    for foe in foes:
        definition = dict(foe["payload"], hp=999, params=[{"label": "物理補正", "value": 100}])
        api(author, "PUT", f"/api/units/unit/{foe['entry_id']}", payload=definition, base_revision=foe["revision"])
    loser = register(browser, "RunLoser" + suffix)
    lose_room = "控えの確認 " + suffix
    get_lose = expedition(loser, lose_room, 6, 1, 0)
    choose(loser, get_lose(), 1)
    rotations = []
    for _ in range(12):
        before = get_lose()["hollow"]["run"]["active"]
        state = resolve_round(loser, get_lose, lose_room)
        run = state["hollow"]["run"]
        if run["status"] == "finished":
            break
        for outgoing, incoming in zip(before, run["active"]):
            if outgoing != incoming:
                rotations.append({"round": state["round"], "out": outgoing, "in": incoming})
    assert run["result"] == {"floor": 1, "outcome": "DEFEAT"}
    assert len(rotations) == 2 and not api(loser, "GET", "/api/hollow/rooms")["rooms"]
    return {"maps": maps, "floors": floors, "rotations": rotations, "defeat": run["result"], "retreat": retreat,
            "defeat_scaling": {k: run["current_event"][k] for k in ("type", "hp_multiplier", "attack_percent")}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-python", default=sys.executable)
    parser.add_argument("--seeded", action="store_true", help="Use the library created by hollow_seed.py")
    args = parser.parse_args()
    result = launch_and_verify(args.app_python, exercise=lambda browser: verify(browser, seeded=args.seeded))
    print(json.dumps(result, ensure_ascii=False, indent=2))
