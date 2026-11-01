"""Commit publishes one cleaned snapshot before a possible ready notification."""

import copy
from types import SimpleNamespace

import pytest

from events.battle import common_routes as routes


@pytest.fixture
def commit_runtime(monkeypatch):
    room = {"battle_mode": "pvp", "characters": [
        {"id": actor, "type": "ally", "hp": 30, "x": 0, "y": 0,
         "special_buffs": [], "flags": {}} for actor in ("A", "B")
    ]}
    battle = {"phase": "select", "round": 1, "resolve_ready": False,
              "resolve_ready_info": {"required_count": 2, "committed_count": 0,
                                     "waiting_slots": ["A", "B"]},
              "slots": {actor: {"actor_id": actor, "team": "ally"} for actor in ("A", "B")},
              "intents": {actor: {"skill_id": "probe", "committed": False,
                                  "tags": {"instant": False}} for actor in ("A", "B")}}
    room["battle_state"] = battle
    events = []
    monkeypatch.setattr(routes, "request", SimpleNamespace(sid="synthetic"))
    monkeypatch.setattr(routes, "_ensure_battle_payload", lambda *_a, **_k: ("room", "battle", "A"))
    monkeypatch.setattr(routes, "get_room_state", lambda _room: room)
    monkeypatch.setattr(routes, "get_or_create_select_resolve_state", lambda *_a, **_k: battle)
    monkeypatch.setattr(routes, "_authorize_intent_slot_control", lambda *_a, **_k: True)
    monkeypatch.setattr(routes, "get_user_info_from_sid", lambda _sid: {"username": "GM"})
    monkeypatch.setattr(routes, "_validate_and_normalize_target", lambda target, *_a, **_k: (target, None))
    monkeypatch.setattr(routes, "_normalize_target_by_skill_compat", lambda _skill, target, **_k: (target, None))
    monkeypatch.setattr(routes, "evaluate_skill_access", lambda *_a, **_k: {"usable": True, "effective_cost": []})
    monkeypatch.setattr(routes, "_build_tags", lambda *_a: {"instant": False})
    monkeypatch.setattr(routes, "_recalculate_redirect_state", lambda *_a: None)
    monkeypatch.setattr(routes, "_log_battle_recv", lambda *_a: None)
    monkeypatch.setattr(routes, "_log_battle_emit", lambda *_a: None)
    monkeypatch.setattr(routes, "build_select_resolve_state_payload", lambda *_a, **_k: copy.deepcopy(battle))
    monkeypatch.setattr(routes.socketio, "emit", lambda name, payload, **kwargs:
                        events.append((name, copy.deepcopy(payload), kwargs.get("to"))))
    monkeypatch.setattr(routes, "save_specific_room_state", lambda *_a: pytest.fail("unexpected save"))
    data = {"room_id": "room", "battle_id": "battle", "slot_id": "A", "skill_id": "probe",
            "target": {"type": "single_slot", "slot_id": "B"}}
    return room, battle, events, data


@pytest.mark.parametrize("other_committed", [False, True])
def test_commit_publishes_one_current_snapshot_before_ready(commit_runtime, other_committed):
    _, battle, events, data = commit_runtime
    battle["intents"]["B"]["committed"] = other_committed
    routes.on_battle_intent_commit(data)
    expected = ["battle_state_updated"] + (["battle_resolve_ready"] if other_committed else [])
    assert [row[0] for row in events] == expected
    payload = events[0][1]
    assert payload["resolve_ready"] is other_committed
    assert payload["resolve_ready_info"] == {
        "required_count": 2, "committed_count": 1 + int(other_committed),
        "waiting_slots": [] if other_committed else ["B"],
    }
    assert payload["intents"]["A"]["committed"]
    assert all(row[2] == "room" for row in events)
    assert battle["phase"] == "select"


def test_already_ready_does_not_notify_ready_again(commit_runtime):
    _, battle, events, data = commit_runtime
    battle["resolve_ready"] = True
    battle["intents"]["B"]["committed"] = True
    routes.on_battle_intent_commit(data)
    assert [row[0] for row in events] == ["battle_state_updated"]
    assert events[0][1]["resolve_ready"] is True


def test_inactive_intent_is_removed_before_publication(commit_runtime):
    room, _, events, data = commit_runtime
    room["characters"][1]["hp"] = 0
    routes.on_battle_intent_commit(data)
    assert [row[0] for row in events] == ["battle_state_updated", "battle_resolve_ready"]
    assert set(events[0][1]["intents"]) == {"A"}
    assert events[0][1]["resolve_ready_info"]["required_count"] == 1


def test_no_required_slots_publishes_not_ready(commit_runtime):
    room, _, events, data = commit_runtime
    for actor in room["characters"]:
        actor["hp"] = 0
    routes.on_battle_intent_commit(data)
    assert [row[0] for row in events] == ["battle_state_updated"]
    assert events[0][1]["resolve_ready"] is False
    assert events[0][1]["intents"] == {}


def test_ready_check_exception_does_not_publish_success(commit_runtime, monkeypatch):
    _, battle, events, data = commit_runtime

    def fail(*_args):
        raise RuntimeError("synthetic ready check failure")

    monkeypatch.setattr(routes, "_refresh_resolve_ready", fail)
    with pytest.raises(RuntimeError, match="synthetic ready check failure"):
        routes.on_battle_intent_commit(data)
    assert events == []
    assert battle["intents"]["A"]["committed"] is True


def test_unauthorized_commit_does_not_publish_or_mutate(commit_runtime, monkeypatch):
    _, battle, events, data = commit_runtime
    before = copy.deepcopy(battle)
    monkeypatch.setattr(routes, "_authorize_intent_slot_control", lambda *_a: False)
    routes.on_battle_intent_commit(data)
    assert events == []
    assert battle == before


@pytest.mark.parametrize("mode,instant,skill,required,ready", [
    ("pvp", False, None, 2, False),
    ("pve", False, None, 1, True),
    ("pve", False, "probe", 2, False),
    ("pvp", True, "probe", 1, True),
])
def test_pve_and_instant_filters_are_applied_before_publication(
    commit_runtime, mode, instant, skill, required, ready
):
    room, battle, events, data = commit_runtime
    room["battle_mode"] = mode
    room["characters"][1]["type"] = "enemy"
    battle["slots"]["B"]["team"] = "enemy"
    battle["intents"]["B"].update(skill_id=skill, committed=instant, tags={"instant": instant})
    routes.on_battle_intent_commit(data)
    assert [row[0] for row in events] == ["battle_state_updated"] + (["battle_resolve_ready"] if ready else [])
    assert events[0][1]["resolve_ready_info"]["required_count"] == required
    assert events[0][1]["resolve_ready"] is ready
    assert "B" in events[0][1]["intents"]


def test_measured_commit_tracks_single_publication_without_persisting_id(commit_runtime):
    _, battle, events, data = commit_runtime
    battle["intents"]["B"]["committed"] = True
    data["_intent_perf_id"] = "synthetic-commit-0123456789"
    ack = routes.on_battle_intent_commit(data)["intent_perf"]
    assert ack["state_emitted"] is True
    assert ack["stages_ms"]["delivery_ms"] >= 0
    assert ack["stages_ms"]["ready_ms"] >= 0
    assert [row[0] for row in events] == ["battle_state_updated", "battle_resolve_ready"]
    assert events[0][1]["_intent_perf"] == {"id": data["_intent_perf_id"]}
    assert "_intent_perf" not in battle
    assert data["_intent_perf_id"] not in repr(battle)


def test_phase_changed_during_commit_still_publishes_latest_state(commit_runtime, monkeypatch):
    _, battle, events, data = commit_runtime

    def change_phase(*_args):
        battle["phase"] = "resolve_mass"

    monkeypatch.setattr(routes, "_recalculate_redirect_state", change_phase)
    monkeypatch.setattr(routes, "_refresh_resolve_ready", lambda *_a: pytest.fail("ready outside select"))
    routes.on_battle_intent_commit(data)
    assert [row[0] for row in events] == ["battle_state_updated"]
    assert events[0][1]["phase"] == "resolve_mass"
