from pathlib import Path
import importlib.util


def _load_battle_common_routes_module():
    root = Path(__file__).resolve().parents[1]
    route_path = root / "events" / "battle" / "common_routes.py"
    spec = importlib.util.spec_from_file_location("battle_common_routes_pve_target_test", route_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _base_state():
    return {
        "phase": "select",
        "slots": {
            "S_E": {"slot_id": "S_E", "actor_id": "E1", "team": "enemy", "initiative": 9, "disabled": False},
            "S_A1": {"slot_id": "S_A1", "actor_id": "A1", "team": "ally", "initiative": 8, "disabled": False},
            "S_A2": {"slot_id": "S_A2", "actor_id": "A2", "team": "ally", "initiative": 7, "disabled": False},
        },
        "intents": {},
        "redirects": [],
    }


def _room_state(auto_skill=False, show_planned=False):
    return {
        "battle_mode": "pve",
        "characters": [
            {
                "id": "E1",
                "type": "enemy",
                "hp": 100,
                "x": 1,
                "y": 1,
                "is_escaped": False,
                "flags": {
                    "auto_target_select": True,
                    "auto_skill_select": auto_skill,
                    "show_planned_skill": show_planned,
                },
            },
            {"id": "A1", "type": "ally", "hp": 100, "x": 1, "y": 1, "is_escaped": False, "flags": {}},
            {"id": "A2", "type": "ally", "hp": 100, "x": 1, "y": 1, "is_escaped": False, "flags": {}},
        ],
    }


def test_pve_enemy_target_is_restored_when_request_wants_none(monkeypatch):
    routes = _load_battle_common_routes_module()
    state = _base_state()
    room_state = _room_state(auto_skill=False)
    monkeypatch.setattr(routes, "get_room_state", lambda _room: room_state)

    intent_before = {
        "slot_id": "S_E",
        "actor_id": "E1",
        "skill_id": None,
        "target": {"type": "single_slot", "slot_id": "S_A1"},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": False,
    }
    intent_now = {
        "slot_id": "S_E",
        "actor_id": "E1",
        "skill_id": None,
        "target": {"type": "none", "slot_id": None},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": False,
    }

    result = routes._apply_pve_enemy_intent_defaults(
        "room_t",
        state,
        "S_E",
        intent_now,
        intent_before=intent_before,
        requested_skill_id=None,
        requested_target={"type": "none", "slot_id": None},
    )

    assert result["target"]["type"] == "single_slot"
    assert result["target"]["slot_id"] == "S_A1"


def test_pve_enemy_explicit_target_request_is_respected(monkeypatch):
    routes = _load_battle_common_routes_module()
    state = _base_state()
    room_state = _room_state(auto_skill=False)
    monkeypatch.setattr(routes, "get_room_state", lambda _room: room_state)

    intent_now = {
        "slot_id": "S_E",
        "actor_id": "E1",
        "skill_id": None,
        "target": {"type": "none", "slot_id": None},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": False,
    }

    result = routes._apply_pve_enemy_intent_defaults(
        "room_t",
        state,
        "S_E",
        intent_now,
        intent_before={},
        requested_skill_id=None,
        requested_target={"type": "single_slot", "slot_id": "S_A2"},
    )

    assert result["target"]["type"] == "single_slot"
    assert result["target"]["slot_id"] == "S_A2"


def test_pve_enemy_auto_skill_is_filled_when_missing(monkeypatch):
    routes = _load_battle_common_routes_module()
    state = _base_state()
    room_state = _room_state(auto_skill=True)
    monkeypatch.setattr(routes, "get_room_state", lambda _room: room_state)

    from manager.battle import battle_ai
    monkeypatch.setattr(battle_ai, "ai_suggest_skill", lambda _char: "S-AUTO")

    intent_now = {
        "slot_id": "S_E",
        "actor_id": "E1",
        "skill_id": None,
        "target": {"type": "none", "slot_id": None},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": False,
    }

    result = routes._apply_pve_enemy_intent_defaults(
        "room_t",
        state,
        "S_E",
        intent_now,
        intent_before={},
        requested_skill_id=None,
        requested_target={"type": "none", "slot_id": None},
    )

    assert result["skill_id"] == "S-AUTO"
    assert result["target"]["type"] == "single_slot"


def test_pve_enemy_show_planned_also_enables_auto_skill_fill(monkeypatch):
    routes = _load_battle_common_routes_module()
    state = _base_state()
    room_state = _room_state(auto_skill=False, show_planned=True)
    monkeypatch.setattr(routes, "get_room_state", lambda _room: room_state)

    from manager.battle import battle_ai
    monkeypatch.setattr(battle_ai, "ai_suggest_skill", lambda _char: "S-PLAN")

    intent_now = {
        "slot_id": "S_E",
        "actor_id": "E1",
        "skill_id": None,
        "target": {"type": "none", "slot_id": None},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": False,
    }

    result = routes._apply_pve_enemy_intent_defaults(
        "room_t",
        state,
        "S_E",
        intent_now,
        intent_before={},
        requested_skill_id=None,
        requested_target={"type": "none", "slot_id": None},
    )

    assert result["skill_id"] == "S-PLAN"


def test_required_slots_excludes_pve_enemy_without_skill(monkeypatch):
    routes = _load_battle_common_routes_module()
    state = _base_state()
    state["intents"] = {
        "S_E": {
            "slot_id": "S_E",
            "actor_id": "E1",
            "skill_id": None,
            "target": {"type": "single_slot", "slot_id": "S_A1"},
            "committed": False,
            "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        },
        "S_A1": {
            "slot_id": "S_A1",
            "actor_id": "A1",
            "skill_id": None,
            "target": {"type": "single_slot", "slot_id": "S_E"},
            "committed": False,
            "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        },
    }
    monkeypatch.setattr(routes, "get_room_state", lambda _room: _room_state(auto_skill=False))

    required = routes._required_slots("room_t", state)

    assert "S_E" not in required
    assert "S_A1" in required


def test_required_slots_keeps_pve_enemy_with_skill(monkeypatch):
    routes = _load_battle_common_routes_module()
    state = _base_state()
    state["intents"] = {
        "S_E": {
            "slot_id": "S_E",
            "actor_id": "E1",
            "skill_id": "S-ENEMY",
            "target": {"type": "single_slot", "slot_id": "S_A1"},
            "committed": False,
            "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        }
    }
    monkeypatch.setattr(routes, "get_room_state", lambda _room: _room_state(auto_skill=False))

    required = routes._required_slots("room_t", state)

    assert "S_E" in required
