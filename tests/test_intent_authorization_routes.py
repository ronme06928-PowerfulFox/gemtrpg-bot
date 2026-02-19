from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import importlib.util

import pytest


def _load_battle_common_routes_module():
    root = Path(__file__).resolve().parents[1]
    route_path = root / "events" / "battle" / "common_routes.py"
    spec = importlib.util.spec_from_file_location("battle_common_routes_auth_test", route_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _base_battle_state():
    return {
        "phase": "select",
        "slots": {
            "S1": {"slot_id": "S1", "actor_id": "A1", "initiative": 10, "disabled": False},
            "S2": {"slot_id": "S2", "actor_id": "B1", "initiative": 8, "disabled": False},
        },
        "intents": {
            "S1": {
                "slot_id": "S1",
                "actor_id": "A1",
                "skill_id": "old_skill",
                "target": {"type": "single_slot", "slot_id": "S2"},
                "tags": {"instant": False, "mass_type": None, "no_redirect": False},
                "committed": True,
                "committed_at": 1,
                "committed_by": "owner_a",
            }
        },
        "resolve": {"trace": []},
    }


def _patch_common(monkeypatch, routes, state, user_info, authorized, emit_calls):
    monkeypatch.setattr(routes, "request", SimpleNamespace(sid="sid-test"))
    monkeypatch.setattr(routes, "_log_battle_recv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        routes,
        "emit",
        lambda event, payload=None, to=None: emit_calls.append((event, payload or {}, to)),
    )
    monkeypatch.setattr(
        routes,
        "get_or_create_select_resolve_state",
        lambda room_id, battle_id=None: state,
    )
    monkeypatch.setattr(routes, "_emit_battle_state_updated", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "_recalculate_redirect_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "_refresh_resolve_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "_maybe_advance_phase_to_resolve_mass", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "get_user_info_from_sid", lambda sid: user_info)
    monkeypatch.setattr(
        routes,
        "is_authorized_for_character",
        lambda room_id, actor_id, username, attribute: authorized,
    )
    monkeypatch.setattr(
        routes,
        "_validate_and_normalize_target",
        lambda target, state_obj, allow_none=False: (
            {"type": "single_slot", "slot_id": "S2"},
            None,
        ),
    )
    monkeypatch.setattr(
        routes,
        "_normalize_target_by_skill",
        lambda skill_id, target, allow_none=False: (target, None),
    )
    monkeypatch.setattr(
        routes,
        "_build_tags",
        lambda skill_id, target: {"instant": False, "mass_type": None, "no_redirect": False},
    )
    monkeypatch.setattr(
        routes,
        "_default_intent_tags",
        lambda tags=None: {"instant": False, "mass_type": None, "no_redirect": False},
    )


@pytest.mark.parametrize(
    "handler_name,payload",
    [
        ("on_battle_intent_preview", {"room_id": "room_t", "battle_id": "battle_t", "slot_id": "S1", "skill_id": "p1", "target": {"type": "single_slot", "slot_id": "S2"}}),
        ("on_battle_intent_commit", {"room_id": "room_t", "battle_id": "battle_t", "slot_id": "S1", "skill_id": "c1", "target": {"type": "single_slot", "slot_id": "S2"}}),
        ("on_battle_intent_uncommit", {"room_id": "room_t", "battle_id": "battle_t", "slot_id": "S1"}),
    ],
)
def test_intent_events_reject_unauthorized_user(monkeypatch, handler_name, payload):
    routes = _load_battle_common_routes_module()
    state = _base_battle_state()
    before = deepcopy(state["intents"])
    emit_calls = []
    _patch_common(
        monkeypatch,
        routes,
        state,
        user_info={"username": "intruder", "attribute": "Player"},
        authorized=False,
        emit_calls=emit_calls,
    )

    getattr(routes, handler_name)(payload)

    assert state["intents"] == before
    battle_errors = [row for row in emit_calls if row[0] == "battle_error"]
    assert battle_errors, f"battle_error must be emitted for {handler_name}"
    assert "permission denied" in str(battle_errors[-1][1].get("message", ""))


@pytest.mark.parametrize(
    "handler_name,payload,expected_committed,expected_skill",
    [
        ("on_battle_intent_preview", {"room_id": "room_t", "battle_id": "battle_t", "slot_id": "S1", "skill_id": "preview_skill", "target": {"type": "single_slot", "slot_id": "S2"}}, False, "preview_skill"),
        ("on_battle_intent_commit", {"room_id": "room_t", "battle_id": "battle_t", "slot_id": "S1", "skill_id": "commit_skill", "target": {"type": "single_slot", "slot_id": "S2"}}, True, "commit_skill"),
        ("on_battle_intent_uncommit", {"room_id": "room_t", "battle_id": "battle_t", "slot_id": "S1"}, False, "old_skill"),
    ],
)
def test_intent_events_allow_gm(monkeypatch, handler_name, payload, expected_committed, expected_skill):
    routes = _load_battle_common_routes_module()
    state = _base_battle_state()
    emit_calls = []
    _patch_common(
        monkeypatch,
        routes,
        state,
        user_info={"username": "gm", "attribute": "GM"},
        authorized=True,
        emit_calls=emit_calls,
    )

    getattr(routes, handler_name)(payload)

    intent = state["intents"]["S1"]
    assert intent["committed"] is expected_committed
    assert intent["skill_id"] == expected_skill
    assert all(row[0] != "battle_error" for row in emit_calls)


@pytest.mark.parametrize(
    "handler_name,payload",
    [
        ("on_battle_intent_preview", {"room_id": "room_t", "battle_id": "battle_t", "slot_id": "UNKNOWN", "skill_id": "p1", "target": {"type": "single_slot", "slot_id": "S2"}}),
        ("on_battle_intent_commit", {"room_id": "room_t", "battle_id": "battle_t", "slot_id": "UNKNOWN", "skill_id": "c1", "target": {"type": "single_slot", "slot_id": "S2"}}),
        ("on_battle_intent_uncommit", {"room_id": "room_t", "battle_id": "battle_t", "slot_id": "UNKNOWN"}),
    ],
)
def test_intent_events_reject_unknown_slot(monkeypatch, handler_name, payload):
    routes = _load_battle_common_routes_module()
    state = _base_battle_state()
    before = deepcopy(state["intents"])
    emit_calls = []
    _patch_common(
        monkeypatch,
        routes,
        state,
        user_info={"username": "gm", "attribute": "GM"},
        authorized=True,
        emit_calls=emit_calls,
    )

    getattr(routes, handler_name)(payload)

    assert state["intents"] == before
    battle_errors = [row for row in emit_calls if row[0] == "battle_error"]
    assert battle_errors, f"battle_error must be emitted for {handler_name}"
    assert "unknown slot_id" in str(battle_errors[-1][1].get("message", ""))
