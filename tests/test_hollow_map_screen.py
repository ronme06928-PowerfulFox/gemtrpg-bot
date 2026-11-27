from collections import Counter

from extensions import socketio
from tests.test_hollow_run import ROOM, dungeon, expedition, room_clients, map_payload, tier  # noqa: F401


def test_map_has_prototype_widths_non_crossing_paths_and_shifts():
    from manager.hollow.map import build_map

    widths = Counter()
    for seed in range(500):
        layout = build_map(tier(1), map_payload(1), {}, seed)
        assert layout == build_map(tier(1), map_payload(1), {}, seed)
        rows = layout["rows"]
        assert rows[0] == [{"id": "n0s", "floor": 0, "type": "start", "shift": 0,
                            "next": [node["id"] for node in rows[1]]}]
        widths.update(map(len, rows[1:-1]))
        assert rows[-1][0]["shift"] == 0
        for row, following in zip(rows, rows[1:]):
            targets = {node["id"]: i for i, node in enumerate(following)}
            edges = [[targets[node_id] for node_id in node["next"]] for node in row]
            assert all(edges)
            assert all(max(a) <= min(b) for a, b in zip(edges, edges[1:]))
            assert {i for edge in edges for i in edge} == set(targets.values())
            assert all(-20 <= node["shift"] <= 20 for node in row)
    total = sum(widths.values())
    assert .04 < widths[1] / total < .08
    assert .41 < widths[2] / total < .47
    assert .47 < widths[3] / total < .53


def test_map_visibility_through_load_and_broadcast(dungeon, monkeypatch):
    from manager import room_manager
    from manager.hollow.run import choose_map, start_run

    _, clients, state, _ = dungeon
    from manager.units.repository import get, save

    area = get("hollow_map", "HM-01")
    save("hollow_map", "HM-01", {**area.payload, "image": "/static/images/cave.webp",
                                "category_weights": {"亀裂": 8, "出血": 9, "打撃": 2, "斬撃": 1, "破裂": 0}},
         base_revision=area.revision)
    start_run(ROOM, "owner", seed=34)
    pending = clients["guest"].get("/load_room", query_string={"name": ROOM}).json["hollow"]["run"]
    assert pending["map_candidates"]["maps"][0]["map_id"] == "HM-01" and "seed" not in pending
    assert "map" not in pending
    assert pending["map_candidates"]["maps"][0] == {
        "map_id": "HM-01", "name": "試験マップ1", "description": "",
        "image": "/static/images/cave.webp", "categories": ["出血", "亀裂", "打撃"],
    }
    choose_map(ROOM, "owner", "HM-01", 1)
    run = state["hollow"]["run"]
    layout = run["map"]
    sent = []
    monkeypatch.setattr(room_manager, "_safe_emit", lambda event, payload, **_: sent.append((event, payload)))
    for floor in (0, 4, 9):
        run["floor"] = floor
        layout["current"] = layout["rows"][floor][0]["id"]
        snapshot = clients["guest"].get("/load_room", query_string={"name": ROOM}).json
        room_manager.broadcast_participant_state(ROOM, state)
        assert sent[-1][0] == "state_updated"
        assert snapshot["hollow"]["run"] == sent[-1][1]["hollow"]["run"]
        public = snapshot["hollow"]["run"]["map"]
        assert "seed" not in public and public["last_floor"] == 10 and public["map_id"] == "HM-01"
        assert public["map_name"] == "試験マップ1"
        assert len(public["rows"]) == min(floor + 2, 10) + 1
        allowed = {node["id"] for row in public["rows"] for node in row}
        assert all(set(node["next"]) <= allowed for row in public["rows"] for node in row)
        assert len(layout["rows"]) == 11 and isinstance(layout["seed"], int)
    run.update(status="finished", result={"floor": 9, "outcome": "RETREAT"})
    room_manager.broadcast_participant_state(ROOM, state)
    assert "map" not in sent[-1][1]["hollow"]["run"]
    assert sent[-1][1]["hollow"]["run"]["result"]["floor"] == 9


def test_player_cannot_send_hollow_run_commands(dungeon):
    from events import socket_hollow, socket_main

    app, clients, _, _ = dungeon
    events = {
        "hollow_run_start": (socket_hollow.handle_run_start, {}),
        "hollow_choose_map": (socket_hollow.handle_choose_map, {"map_id": "HM-01", "tier": 1}),
        "hollow_select_node": (socket_hollow.handle_select_node, {"node_id": "n1a", "tier": 1}),
        "hollow_swap_party": (socket_hollow.handle_swap_party, {"active_id": "0", "reserve_id": "4"}),
        "hollow_retreat": (socket_hollow.handle_retreat, {}),
    }
    socketio.on_event("connect", socket_main.handle_connect)
    socketio.on_event("join_room", socket_main.handle_join_room)
    socketio.on_event("disconnect", socket_main.handle_disconnect)
    for event, (fn, _) in events.items():
        socketio.on_event(event, fn)
    client = socketio.test_client(app, flask_test_client=clients["guest"])
    try:
        client.emit("join_room", {"room": ROOM})
        for event, (_, payload) in events.items():
            result = client.emit(event, payload, callback=True)
            assert not result["ok"] and "ホストとオーナー" in result["error"]
    finally:
        client.disconnect()


def test_later_start_nodes_look_like_the_defeated_boss():
    # T2 以降のスタートマスは倒したボスのマスの札で描く（2026-11-26 試遊で「降り口」をやめた）。
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "static/js/hollow/map.js").read_text(encoding="utf-8")
    assert "降り口" not in source
    assert "node.type === 'start' && node.floor ? 'boss' : node.type" in source


def test_finish_screen_depth_fog_and_clear_transition():
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    script = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
let html = '';
const window = {HollowEvents:{types:{}}, CatalogWorkspaceParts:{h: String}, currentRoomRole:'owner'};
const context = {window, currentUserId:'owner', matchMedia: () => ({matches:false}), performance:{now:() => 0}};
vm.createContext(context);
for (const name of ['finish','party','map']) {
  vm.runInContext(fs.readFileSync('static/js/hollow/' + name + '.js','utf8'), context);
}
const finish = window.HollowFinish;
assert.equal(finish.revealedFloor({mapId:'HM-01', tier:1, visible:4}, {mapId:'HM-01', tier:1, visible:5}), 5);
for (const previous of [null,{mapId:'HM-02',tier:2,visible:4},{mapId:'HM-01',tier:1,visible:3}]) {
  assert.equal(finish.revealedFloor(previous,{mapId:'HM-01',tier:1,visible:5}), null);
}
const active = {status:'in_progress'};
assert.equal(finish.liveClear(active,{status:'finished',result:{floor:50,outcome:'CLEAR'}}), true);
for (const [before,floor,outcome] of [[null,50,'CLEAR'],[active,49,'CLEAR'],[active,50,'RETREAT'],
                                     [{status:'finished'},50,'CLEAR']]) {
  assert.equal(finish.liveClear(before,{status:'finished',result:{floor,outcome}}), false);
}
const state = {characters:[{id:'a',type:'ally'},{id:'b',type:'ally'}],
  party:{order:['a','b']}, hollow:{members:[{id:'owner',name:'試験ホスト',role:'owner'}],
  host_user_id:'owner',run:{status:'in_progress',floor:44,map:{tier:5,map_name:'淵の喉'},mana_load:18,
  load_stage:{level:3},log:[{floor:40,type:'boss',outcome:'VICTORY'}]}}};
const root = {set innerHTML(value) {html=value;}, querySelector:() => null};
window.HollowParty.renderRibbon(root,state);
for (const text of ['44F','T5 淵の喉','試験ホスト','魔力負荷','18','段階 3','2 / 6 人']) assert.ok(html.includes(text), text);
assert.equal((html.match(/class="hollow-depth-tier/g)||[]).length, 5);
assert.equal((html.match(/is-cleared/g)||[]).length, 4);
const map = fs.readFileSync('static/js/hollow/map.js','utf8');
assert.match(map,/row \? '' : ' is-fog'/);
const art = fs.readFileSync('static/js/hollow/finish.js','utf8');
assert.match(art,/querySelectorAll\('\.hollow-map-row\.is-fog, \.hollow-map-row\.is-revealing'\)/);
'''
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=root,
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
