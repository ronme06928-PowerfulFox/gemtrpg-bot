import json
from types import SimpleNamespace

from events import socket_battle_only
from manager.units.characters import read_character


SAMPLE_CHAR_JSON = {
    "kind": "character",
    "data": {
        "name": "テストユニット",
        "status": [
            {"label": "HP", "value": 20, "max": 20},
            {"label": "MP", "value": 8, "max": 8},
            {"label": "FP", "value": 0, "max": 0},
            {"label": "出血", "value": 0, "max": 0},
        ],
        "commands": "1d6 【テスト】",
        "params": [{"label": "敏捷", "value": "5"}],
    },
}


def _base_state():
    return {
        "play_mode": "battle_only",
        "characters": [],
        "timeline": [],
        "round": 0,
        "map_data": {"width": 20, "height": 15, "gridSize": 64},
        "battle_only": {
            "status": "draft",
            "ally_entries": [],
            "enemy_entries": [],
            "records": [],
            "active_record_id": None,
        },
    }


def _patch_common(monkeypatch, state, store, user_info=None, room='room_t'):
    emits = []

    monkeypatch.setattr(socket_battle_only, 'request', SimpleNamespace(sid='sid_test'))
    monkeypatch.setattr(socket_battle_only, 'get_room_state', lambda _room: state)
    monkeypatch.setattr(socket_battle_only, 'save_specific_room_state', lambda _room: True)
    monkeypatch.setattr(socket_battle_only, 'broadcast_state_update', lambda _room: None)
    monkeypatch.setattr(socket_battle_only, 'broadcast_log', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(socket_battle_only, 'set_character_owner', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(socket_battle_only, 'process_battle_start', lambda *_args, **_kwargs: None)
    def _fake_start_round(_room, _user_info):
        state['round'] = int(state.get('round', 0) or 0) + 1
        if not isinstance(state.get('timeline'), list) or len(state.get('timeline')) <= 0:
            chars = [c for c in (state.get('characters') or []) if isinstance(c, dict)]
            state['timeline'] = [{'id': f'tl_{idx}', 'char_id': str(c.get('id', '')), 'speed': 1, 'acted': False} for idx, c in enumerate(chars)]
    monkeypatch.setattr(socket_battle_only, '_start_battle_only_round', _fake_start_round)
    monkeypatch.setattr(
        socket_battle_only,
        'get_user_info_from_sid',
        lambda _sid: user_info or {"username": "gm", "attribute": "GM", "user_id": "u_gm"},
    )
    monkeypatch.setattr(
        socket_battle_only.socketio,
        'emit',
        lambda event, payload=None, to=None: emits.append((event, payload or {}, to)),
    )

    for unit in store.get("character_presets", {}).values():
        if "character_json" in unit:
            fields, _ = read_character(unit)
            unit.update(fields)
    for key in ("ally_formations", "enemy_formations"):
        for formation in store.get(key, {}).values():
            for member in formation.get("members", []):
                member["unit_id"] = member.pop("preset_id")
    info = user_info or {"username": "gm", "attribute": "GM", "user_id": "u_gm"}
    monkeypatch.setattr(socket_battle_only, "deployment_store", lambda: store)
    monkeypatch.setattr(socket_battle_only, "_catalog_request_context", lambda data: {
        "user_info": info, "user_id": info.get("user_id"), "room": data.get("room"),
        "room_role": "gm" if info["attribute"] == "GM" else "player", "is_author": False,
    })
    monkeypatch.setattr(
        socket_battle_only,
        'user_sids',
        {
            'sid_gm': {'room': room, 'user_id': 'u_gm', 'username': 'GM', 'attribute': 'GM'},
            'sid_p1': {'room': room, 'user_id': 'u_1', 'username': 'Alice', 'attribute': 'Player'},
        },
    )

    return emits


def _find_event(emits, event_name):
    return [row for row in emits if row[0] == event_name]


def test_bo_draft_update_and_start_battle(monkeypatch):
    from manager import room_manager
    from manager.game_logic import process_battle_start
    from manager.utils import get_status_value

    state = _base_state()
    store = {
        'character_presets': {
            'ally_1': {
                'id': 'ally_1',
                'name': '味方A',
                'visibility': 'public',
                'allow_ally': True,
                'allow_enemy': False,
                'character_json': SAMPLE_CHAR_JSON,
            },
            'enemy_1': {
                'id': 'enemy_1',
                'name': '敵A',
                'visibility': 'public',
                'allow_ally': False,
                'allow_enemy': True,
                'character_json': SAMPLE_CHAR_JSON,
            },
        }
    }
    owner_calls = []
    start_calls = []

    emits = _patch_common(monkeypatch, state, store)
    monkeypatch.setattr(socket_battle_only, 'set_character_owner', lambda room, char_id, username: owner_calls.append((room, char_id, username)))
    buff = {"name": "TestInitFP", "data": {"battle_start_effect": [
        {"type": "APPLY_STATE", "state_name": "FP", "value": 1},
    ]}}
    for unit in store["character_presets"].values():
        unit["special_buffs"] = [buff]
    monkeypatch.setattr(room_manager, "get_room_state", lambda *_: state)
    for fn in ("broadcast_log", "broadcast_state_update", "save_specific_room_state"):
        monkeypatch.setattr(room_manager, fn, lambda *args, **kwargs: None)

    def track_battle_start(room, char):
        start_calls.append((room, char["id"]))
        process_battle_start(room, char)

    monkeypatch.setattr(socket_battle_only, "process_battle_start", track_battle_start)

    socket_battle_only.handle_bo_draft_update(
        {
            'room': 'room_t',
            'payload': {
                'ally_entries': [{'preset_id': 'ally_1', 'user_id': 'u_1'}],
                'enemy_entries': [{'preset_id': 'enemy_1', 'count': 2}],
            },
        }
    )

    bo = state['battle_only']
    assert bo['ally_entries'][0]['preset_id'] == 'ally_1'
    assert bo['enemy_entries'][0]['count'] == 2
    assert bo['status'] == 'draft'

    socket_battle_only.handle_bo_start_battle({'room': 'room_t'})

    assert state.get('play_mode') == 'battle_only'
    assert state.get('battle_only', {}).get('status') == 'in_battle'
    chars = state.get('characters', [])
    assert len(chars) == 3
    allies = [c for c in chars if c.get('type') == 'ally']
    enemies = [c for c in chars if c.get('type') == 'enemy']
    assert len(allies) == 1
    assert len(enemies) == 2
    assert allies[0].get('owner') == 'Alice'
    assert owner_calls
    assert len(start_calls) == 3
    assert [get_status_value(char, 'FP') for char in chars] == [1, 1, 1]
    assert int(state.get('round', 0) or 0) == 1
    assert isinstance(state.get('timeline'), list)
    assert len(state.get('timeline')) >= 1
    round_start_errors = [row for row in emits if row[0] == 'bo_draft_error' and str((row[1] or {}).get('error', '')) == 'round_start_failed']
    assert not round_start_errors

    started = _find_event(emits, 'bo_battle_started')
    assert started
    assert started[-1][1].get('ally_count') == 1
    assert started[-1][1].get('enemy_count') == 2


def test_bo_start_battle_closes_orphaned_in_progress_record(monkeypatch):
    state = _base_state()
    state['battle_only'].update({
        'status': 'draft',
        'active_record_id': None,
        'records': [{'id': 'orphan', 'status': 'in_battle', 'result': None}],
        'ally_entries': [{'preset_id': 'ally_1', 'user_id': 'u_1'}],
        'enemy_entries': [{'preset_id': 'enemy_1', 'count': 1}],
    })
    store = {
        'character_presets': {
            'ally_1': {
                'id': 'ally_1', 'name': 'Ally', 'visibility': 'public',
                'allow_ally': True, 'allow_enemy': False, 'character_json': SAMPLE_CHAR_JSON,
            },
            'enemy_1': {
                'id': 'enemy_1', 'name': 'Enemy', 'visibility': 'public',
                'allow_ally': False, 'allow_enemy': True, 'character_json': SAMPLE_CHAR_JSON,
            },
        },
    }
    _patch_common(monkeypatch, state, store)

    socket_battle_only.handle_bo_start_battle({'room': 'room_t'})

    orphan = next(rec for rec in state['battle_only']['records'] if rec.get('id') == 'orphan')
    assert orphan['status'] == 'finished'
    assert orphan['result'] == 'aborted'
    assert orphan['end_reason'] == 'orphaned_state_recovery'
    assert state['battle_only']['active_record_id'] != 'orphan'
    assert state['battle_only']['status'] == 'in_battle'


def test_bo_record_mark_result(monkeypatch):
    state = _base_state()
    state['battle_only'] = {
        'status': 'in_battle',
        'ally_entries': [{'preset_id': 'ally_1', 'user_id': 'u_1'}],
        'enemy_entries': [{'preset_id': 'enemy_1', 'count': 1}],
        'records': [
            {
                'id': 'bor_1',
                'status': 'in_battle',
                'result': None,
                'started_at': '2026-01-01T00:00:00+00:00',
                'ended_at': None,
            }
        ],
        'active_record_id': 'bor_1',
    }
    state['characters'] = [
        {'id': 'a1', 'type': 'ally', 'hp': 10},
        {'id': 'e1', 'type': 'enemy', 'hp': 0},
    ]
    store = {'character_presets': {}}
    emits = _patch_common(monkeypatch, state, store)

    socket_battle_only.handle_bo_record_mark_result({'room': 'room_t', 'record_id': 'bor_1', 'result': 'auto', 'note': 'test'})

    rec = state['battle_only']['records'][0]
    assert rec.get('status') == 'finished'
    assert rec.get('result') == 'ally_win'
    assert rec.get('ended_at')
    assert rec.get('note') == 'test'
    assert state['battle_only'].get('active_record_id') is None
    assert state['battle_only'].get('status') == 'draft'

    updated = _find_event(emits, 'bo_record_updated')
    assert updated

    emits.clear()
    socket_battle_only.handle_bo_record_export({'room': 'room_t'})
    exported = _find_event(emits, 'bo_record_export')
    assert exported
    payload = exported[-1][1]
    assert payload.get('filename', '').endswith('.json')
    assert '"records"' in payload.get('content', '')


def test_bo_start_battle_auto_places_characters_with_spacing(monkeypatch):
    state = _base_state()
    state["map_data"] = {"width": 20, "height": 15, "gridSize": 64}
    store = {
        "character_presets": {
            "ally_1": {
                "id": "ally_1",
                "name": "味方A",
                "visibility": "public",
                "allow_ally": True,
                "allow_enemy": False,
                "character_json": SAMPLE_CHAR_JSON,
            },
            "ally_2": {
                "id": "ally_2",
                "name": "味方B",
                "visibility": "public",
                "allow_ally": True,
                "allow_enemy": False,
                "character_json": SAMPLE_CHAR_JSON,
            },
            "enemy_1": {
                "id": "enemy_1",
                "name": "敵A",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_CHAR_JSON,
            },
            "enemy_2": {
                "id": "enemy_2",
                "name": "敵B",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_CHAR_JSON,
            },
        }
    }
    _patch_common(monkeypatch, state, store)

    socket_battle_only.handle_bo_draft_update(
        {
            "room": "room_t",
            "payload": {
                "ally_entries": [
                    {"preset_id": "ally_1", "user_id": "u_1"},
                    {"preset_id": "ally_2", "user_id": "u_gm"},
                ],
                "enemy_entries": [
                    {"preset_id": "enemy_1", "count": 1},
                    {"preset_id": "enemy_2", "count": 1},
                ],
            },
        }
    )
    socket_battle_only.handle_bo_start_battle({"room": "room_t"})

    chars = state.get("characters", [])
    allies = [c for c in chars if c.get("type") == "ally"]
    enemies = [c for c in chars if c.get("type") == "enemy"]
    assert len(allies) == 2
    assert len(enemies) == 2

    for c in chars:
        assert int(c.get("x", -1)) >= 0
        assert int(c.get("y", -1)) >= 0

    ally_xs = [int(c.get("x", 0)) for c in allies]
    enemy_xs = [int(c.get("x", 0)) for c in enemies]
    assert max(ally_xs) < min(enemy_xs)


def test_bo_start_battle_forces_team_fields_by_side(monkeypatch):
    state = _base_state()
    store = {
        "character_presets": {
            "ally_bad": {
                "id": "ally_bad",
                "name": "味方(入力汚染)",
                "visibility": "public",
                "allow_ally": True,
                "allow_enemy": False,
                "character_json": {
                    "kind": "character",
                    "data": {
                        "name": "汚染味方",
                        "type": "enemy",
                        "team": "enemy",
                        "side": "enemy",
                        "faction": "enemy",
                        "status": [{"label": "HP", "value": 10, "max": 10}],
                    },
                },
            },
            "enemy_bad": {
                "id": "enemy_bad",
                "name": "敵(入力汚染)",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": {
                    "kind": "character",
                    "data": {
                        "name": "汚染敵",
                        "type": "ally",
                        "team": "ally",
                        "side": "ally",
                        "faction": "ally",
                        "status": [{"label": "HP", "value": 10, "max": 10}],
                    },
                },
            },
        }
    }
    _patch_common(monkeypatch, state, store)
    socket_battle_only.handle_bo_draft_update(
        {
            "room": "room_t",
            "payload": {
                "ally_entries": [{"preset_id": "ally_bad", "user_id": "u_1"}],
                "enemy_entries": [{"preset_id": "enemy_bad", "count": 1}],
            },
        }
    )
    socket_battle_only.handle_bo_start_battle({"room": "room_t"})

    chars = state.get("characters", [])
    allies = [c for c in chars if c.get("type") == "ally"]
    enemies = [c for c in chars if c.get("type") == "enemy"]
    assert len(allies) == 1
    assert len(enemies) == 1
    a = allies[0]
    e = enemies[0]
    assert a.get("team") == "ally"
    assert a.get("side") == "ally"
    assert a.get("faction") == "ally"
    assert bool(a.get("is_ally")) is True
    assert bool(a.get("is_enemy")) is False
    assert a.get("color") == "#007bff"
    assert e.get("team") == "enemy"
    assert e.get("side") == "enemy"
    assert e.get("faction") == "enemy"
    assert bool(e.get("is_ally")) is False
    assert bool(e.get("is_enemy")) is True
    assert e.get("color") == "#dc3545"


def test_bo_start_battle_uses_operator_anchor_center(monkeypatch):
    state = _base_state()
    state["map_data"] = {"width": 24, "height": 16, "gridSize": 64}
    store = {
        "character_presets": {
            "ally_1": {
                "id": "ally_1",
                "name": "味方A",
                "visibility": "public",
                "allow_ally": True,
                "allow_enemy": False,
                "character_json": SAMPLE_CHAR_JSON,
            },
            "enemy_1": {
                "id": "enemy_1",
                "name": "敵A",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_CHAR_JSON,
            },
        }
    }
    _patch_common(monkeypatch, state, store)
    socket_battle_only.handle_bo_draft_update(
        {
            "room": "room_t",
            "payload": {
                "ally_entries": [{"preset_id": "ally_1", "user_id": "u_1"}],
                "enemy_entries": [{"preset_id": "enemy_1", "count": 1}],
            },
        }
    )

    socket_battle_only.handle_bo_start_battle({"room": "room_t", "anchor": {"x": 15.2, "y": 10.1}})

    chars = state.get("characters", [])
    allies = [c for c in chars if c.get("type") == "ally"]
    enemies = [c for c in chars if c.get("type") == "enemy"]
    assert len(allies) == 1
    assert len(enemies) == 1
    ally = allies[0]
    enemy = enemies[0]

    assert int(ally.get("x", -1)) < int(enemy.get("x", -1))
    # アンカー周辺（x=15, y=10付近）を基準に配置されること
    assert int(ally.get("x", -1)) >= 12
    assert int(enemy.get("x", -1)) <= 18
    assert abs(int(ally.get("y", -1)) - 10) <= 1
    assert abs(int(enemy.get("y", -1)) - 10) <= 1


def test_bo_select_enemy_formation_overwrites_required_ally_count(monkeypatch):
    state = _base_state()
    state["battle_only"]["required_ally_count"] = 5
    store = {
        "character_presets": {
            "ally_1": {
                "id": "ally_1",
                "name": "AllyA",
                "visibility": "public",
                "allow_ally": True,
                "allow_enemy": False,
                "character_json": SAMPLE_CHAR_JSON,
            },
            "enemy_1": {
                "id": "enemy_1",
                "name": "敵A",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_CHAR_JSON,
            }
        },
        "enemy_formations": {
            "fm_1": {
                "id": "fm_1",
                "name": "編成1",
                "visibility": "public",
                "recommended_ally_count": 2,
                "members": [{"preset_id": "enemy_1", "count": 1}],
            }
        },
    }
    emits = _patch_common(monkeypatch, state, store)

    socket_battle_only.handle_bo_select_enemy_formation({"room": "room_t", "formation_id": "fm_1"})
    selected = _find_event(emits, 'bo_enemy_formation_selected')
    assert selected
    assert state["battle_only"]["required_ally_count"] == 2


def test_bo_start_battle_room_existing_mode_uses_placed_allies(monkeypatch):
    state = _base_state()
    state["characters"] = [
        {
            "id": "ally_room_1",
            "name": "配置済み味方",
            "type": "ally",
            "team": "ally",
            "side": "ally",
            "faction": "ally",
            "hp": 10,
            "maxHp": 10,
            "mp": 5,
            "maxMp": 5,
            "x": 4,
            "y": 6,
            "owner": "Alice",
            "owner_id": "u_1",
        }
    ]
    state["battle_only"]["ally_mode"] = "room_existing"
    state["battle_only"]["required_ally_count"] = 1
    state["battle_only"]["enemy_entries"] = [{"preset_id": "enemy_1", "count": 1}]
    store = {
        "character_presets": {
            "enemy_1": {
                "id": "enemy_1",
                "name": "敵A",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_CHAR_JSON,
            }
        }
    }
    _patch_common(
        monkeypatch,
        state,
        store,
        user_info={"username": "gm", "attribute": "GM", "user_id": "u_gm"},
    )

    socket_battle_only.handle_bo_start_battle({
        "room": "room_t",
        "anchor": {"x": 12.0, "y": 8.0},
        "draft_payload": {
            "ally_mode": "room_existing",
            "required_ally_count": 1,
            "selected_stage_id": None,
            "enemy_formation_id": None,
            "ally_formation_id": None,
            "ally_entries": [],
            "enemy_entries": [{"preset_id": "enemy_1", "count": 1}],
        },
    })

    assert state.get("battle_mode") == "pve"
    assert state.get("battle_only", {}).get("status") == "in_battle"
    assert state["battle_only"]["selected_stage_id"] is None
    assert state["battle_only"]["ally_formation_id"] is None
    chars = state.get("characters", [])
    allies = [c for c in chars if c.get("type") == "ally"]
    enemies = [c for c in chars if c.get("type") == "enemy"]
    assert len(allies) == 1
    assert len(enemies) == 1
    ally = allies[0]
    assert ally.get("id") == "ally_room_1"
    assert int(ally.get("x", -1)) == 4
    assert int(ally.get("y", -1)) == 6
    assert ally.get("color") == "#007bff"
    assert enemies[0].get("color") == "#dc3545"


def test_bo_start_battle_uses_inline_draft_before_stale_room_state(monkeypatch):
    state = _base_state()
    state["battle_state"] = {
        "round": 1,
        "behavior_round_plan": {
            "round": 1,
            "actors": {"old_enemy": {"plans": [{"skill_id": "OLD"}]}},
        },
    }
    state["battle_only"]["ally_entries"] = [{"preset_id": "ally_1", "user_id": "u_1"}]
    state["battle_only"]["enemy_entries"] = [{
        "preset_id": "enemy_1",
        "count": 1,
    }]
    store = {
        "character_presets": {
            "ally_1": {
                "id": "ally_1",
                "name": "味方A",
                "visibility": "public",
                "allow_ally": True,
                "allow_enemy": False,
                "character_json": SAMPLE_CHAR_JSON,
            },
            "enemy_1": {
                "id": "enemy_1",
                "name": "敵A",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_CHAR_JSON,
            },
        }
    }
    _patch_common(monkeypatch, state, store)
    profile = {
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "initial_loop_id": "loop_1",
        "loops": {
            "loop_1": {
                "repeat": True,
                "steps": [{"actions": ["E-31", "E-31", "E-34"]}],
                "transitions": [],
            }
        },
    }

    store["character_presets"]["enemy_1"]["patterns"] = [
        {"id": "BP-1", "profile": {"enabled": False}},
        {"id": "BP-2", "profile": profile},
    ]
    store["character_presets"]["enemy_1"]["default_pattern_id"] = "BP-1"
    socket_battle_only.handle_bo_start_battle({
        "room": "room_t",
        "draft_payload": {
            "ally_mode": "preset",
            "required_ally_count": 1,
            "ally_entries": [{"preset_id": "ally_1", "user_id": "u_1"}],
            "enemy_entries": [{
                "preset_id": "enemy_1",
                "count": 1,
                "pattern_id": "BP-2",
            }],
        },
    })

    enemies = [c for c in state.get("characters", []) if c.get("type") == "enemy"]
    assert len(enemies) == 1
    assert "battle_state" not in state
    behavior = enemies[0]["flags"]["behavior_profile"]
    assert behavior["enabled"] is True
    assert behavior["slot_generation_mode"] == "step_actions"
    assert behavior["loops"]["loop_1"]["steps"][0]["actions"] == ["E-31", "E-31", "E-34"]


def test_bo_validate_entry_ready_in_room_existing_mode(monkeypatch):
    state = _base_state()
    state["characters"] = [
        {
            "id": "ally_room_1",
            "name": "味方A",
            "type": "ally",
            "hp": 10,
            "maxHp": 10,
            "x": 2,
            "y": 2,
        }
    ]
    state["battle_only"]["ally_mode"] = "room_existing"
    state["battle_only"]["required_ally_count"] = 1
    state["battle_only"]["enemy_entries"] = [{"preset_id": "enemy_1", "count": 1}]
    store = {
        "character_presets": {
            "enemy_1": {
                "id": "enemy_1",
                "name": "敵A",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_CHAR_JSON,
            }
        }
    }
    emits = _patch_common(
        monkeypatch,
        state,
        store,
        user_info={"username": "gm", "attribute": "GM", "user_id": "u_gm"},
    )

    socket_battle_only.handle_bo_validate_entry({"room": "room_t"})
    rows = _find_event(emits, "bo_entry_validated")
    assert rows
    payload = rows[-1][1]
    assert payload.get("ready") is True
    assert payload.get("issues") == []
    assert int(payload.get("room_ally_count", -1)) == 1
    assert int(payload.get("enemy_entry_count", -1)) == 1


def test_bo_validate_entry_reports_missing_enemy_and_count_mismatch(monkeypatch):
    state = _base_state()
    state["characters"] = [
        {
            "id": "ally_room_1",
            "name": "味方A",
            "type": "ally",
            "hp": 10,
            "maxHp": 10,
            "x": 2,
            "y": 2,
        }
    ]
    state["battle_only"]["ally_mode"] = "room_existing"
    state["battle_only"]["required_ally_count"] = 2
    state["battle_only"]["enemy_entries"] = []
    store = {"character_presets": {}}
    emits = _patch_common(
        monkeypatch,
        state,
        store,
        user_info={"username": "gm", "attribute": "GM", "user_id": "u_gm"},
    )

    socket_battle_only.handle_bo_validate_entry({"room": "room_t"})
    rows = _find_event(emits, "bo_entry_validated")
    assert rows
    payload = rows[-1][1]
    assert payload.get("ready") is False
    issues = [str(x) for x in payload.get("issues", [])]
    assert any("敵編成が空" in x for x in issues)
    assert any("味方人数が不一致" in x for x in issues)


def test_bo_ally_formation_and_stage_select(monkeypatch):
    state = _base_state()
    store = {
        "character_presets": {
            "ally_1": {
                "id": "ally_1",
                "name": "味方A",
                "visibility": "public",
                "allow_ally": True,
                "allow_enemy": False,
                "character_json": SAMPLE_CHAR_JSON,
            },
            "enemy_1": {
                "id": "enemy_1",
                "name": "敵A",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_CHAR_JSON,
            },
        },
        "enemy_formations": {
            "ef_1": {
                "id": "ef_1",
                "name": "敵編成A",
                "visibility": "public",
                "recommended_ally_count": 2,
                "members": [{"preset_id": "enemy_1", "count": 1}],
            }
        },
        "ally_formations": {},
        "stage_presets": {},
    }
    emits = _patch_common(monkeypatch, state, store)

    ally_formation_id = "F-002"
    stage_id = "ST-001"
    store["ally_formations"][ally_formation_id] = {
        "members": [{"unit_id": "ally_1", "count": 2}],
    }
    store["stage_presets"][stage_id] = {
        "enemy_formation_id": "ef_1", "ally_formation_id": ally_formation_id,
        "required_ally_count": 2,
    }
    socket_battle_only.handle_bo_select_stage_preset({"room": "room_t", "stage_id": stage_id})
    selected = _find_event(emits, "bo_stage_preset_selected")
    assert selected
    bo = state.get("battle_only", {})
    assert bo.get("selected_stage_id") == stage_id
    assert bo.get("enemy_formation_id") == "ef_1"
    assert bo.get("ally_formation_id") == ally_formation_id
    assert bo.get("ally_mode") == "preset"
    assert bo.get("required_ally_count") == 2
    assert isinstance(bo.get("enemy_entries"), list) and bo.get("enemy_entries")
    assert isinstance(bo.get("ally_entries"), list) and bo.get("ally_entries")
    assert isinstance(bo.get("stage_field_effect_profile"), dict)
    assert isinstance(bo.get("stage_avatar_profile"), dict)
    assert bo.get("stage_field_effect_enabled") is True


def test_bo_stage_field_effect_toggle_disables_injection(monkeypatch):
    state = _base_state()
    state["battle_only"]["stage_field_effect_profile"] = {
        "version": 1,
        "rules": [{"rule_id": "r1", "type": "SPEED_ROLL_MOD", "scope": "ALL", "value": -1}],
    }
    state["battle_only"]["stage_field_effect_enabled"] = True
    state["battle_only"]["ally_entries"] = [{"preset_id": "ally_1", "user_id": "u_1"}]
    state["battle_only"]["enemy_entries"] = [{"preset_id": "enemy_1", "count": 1}]
    store = {
        "character_presets": {
            "ally_1": {
                "id": "ally_1",
                "name": "AllyA",
                "visibility": "public",
                "allow_ally": True,
                "allow_enemy": False,
                "character_json": SAMPLE_CHAR_JSON,
            },
            "enemy_1": {
                "id": "enemy_1",
                "name": "EnemyA",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_CHAR_JSON,
            },
        }
    }
    emits = _patch_common(monkeypatch, state, store)

    socket_battle_only.handle_bo_set_stage_field_effect_enabled({"room": "room_t", "enabled": False})
    assert state["battle_only"]["stage_field_effect_enabled"] is False
    updated = _find_event(emits, "bo_stage_field_effect_updated")
    assert updated

    emits.clear()
    socket_battle_only.handle_bo_start_battle({"room": "room_t"})
    assert state.get("field_effects") == []


def test_bo_stage_avatar_toggle_updates_state(monkeypatch):
    state = _base_state()
    state["battle_only"]["stage_avatar_profile"] = {"enabled": True, "name": "Avatar", "description": "desc", "icon": "icon"}
    state["battle_only"]["stage_avatar_enabled"] = True
    state["battle_only"]["ally_entries"] = [{"preset_id": "ally_1", "user_id": "u_1"}]
    state["battle_only"]["enemy_entries"] = [{"preset_id": "enemy_1", "count": 1}]
    store = {
        "character_presets": {
            "ally_1": {
                "id": "ally_1",
                "name": "AllyA",
                "visibility": "public",
                "allow_ally": True,
                "allow_enemy": False,
                "character_json": SAMPLE_CHAR_JSON,
            },
            "enemy_1": {
                "id": "enemy_1",
                "name": "EnemyA",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_CHAR_JSON,
            },
        }
    }
    emits = _patch_common(monkeypatch, state, store)

    socket_battle_only.handle_bo_set_stage_avatar_enabled({"room": "room_t", "enabled": False})
    assert state["battle_only"]["stage_avatar_enabled"] is False
    updated = _find_event(emits, "bo_stage_avatar_updated")
    assert updated

    emits.clear()
    socket_battle_only.handle_bo_start_battle({"room": "room_t"})
    assert state["stage_avatar_enabled"] is False
    assert state["stage_avatar_profile"]["name"] == "Avatar"


def test_bo_stage_selection_uses_stage_avatar_enabled_default(monkeypatch):
    state = _base_state()
    store = {
        "character_presets": {
            "ally_1": {
                "id": "ally_1",
                "name": "AllyA",
                "visibility": "public",
                "allow_ally": True,
                "allow_enemy": False,
                "character_json": SAMPLE_CHAR_JSON,
            },
            "enemy_1": {
                "id": "enemy_1",
                "name": "EnemyA",
                "visibility": "public",
                "allow_ally": False,
                "allow_enemy": True,
                "character_json": SAMPLE_CHAR_JSON,
            },
        },
        "enemy_formations": {
            "ef_1": {
                "id": "ef_1",
                "name": "EnemyFormation",
                "visibility": "public",
                "recommended_ally_count": 0,
                "members": [{"preset_id": "enemy_1", "count": 1}],
            }
        },
        "ally_formations": {},
        "stage_presets": {
            "stage_no_avatar": {
                "id": "stage_no_avatar",
                "name": "No Avatar Stage",
                "visibility": "public",
                "enemy_formation_id": "ef_1",
                "required_ally_count": 0,
                "field_effect_profile": {"version": 1, "rules": []},
                "stage_avatar": {"enabled": False, "name": "Hidden Avatar", "description": "hidden", "icon": "hide"},
            }
        },
    }
    emits = _patch_common(monkeypatch, state, store)

    socket_battle_only.handle_bo_select_stage_preset({"room": "room_t", "stage_id": "stage_no_avatar"})
    bo = state["battle_only"]
    assert bo["stage_avatar_profile"]["name"] == "Hidden Avatar"
    assert bo["stage_avatar_enabled"] is False
    bo["ally_entries"] = [{"preset_id": "ally_1", "user_id": "u_1"}]

    emits.clear()
    socket_battle_only.handle_bo_start_battle({"room": "room_t"})
    assert state["stage_avatar_profile"]["name"] == "Hidden Avatar"
    assert state["stage_avatar_enabled"] is False
