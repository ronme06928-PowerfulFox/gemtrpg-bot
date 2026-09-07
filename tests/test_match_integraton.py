import pytest

import events.battle.duel_routes as duel_routes


@pytest.fixture
def active_duel(monkeypatch):
    state = {
        "combat_state": {"is_active": True},
        "active_match": {
            "is_active": True,
            "match_type": "duel",
            "attacker_id": "ActorA",
            "defender_id": "ActorD",
            "match_id": "test-match-uuid",
        },
    }
    declarations = []
    executions = []

    monkeypatch.setattr(duel_routes, "get_room_state", lambda _room: state)
    monkeypatch.setattr(duel_routes, "is_sid_in_room", lambda _sid, _room: True)
    monkeypatch.setattr(duel_routes, "_resolve_sid", lambda: None)
    monkeypatch.setattr(duel_routes, "_resolve_username", lambda: "Tester")
    monkeypatch.setattr(
        duel_routes,
        "update_duel_declaration",
        lambda room, data, username: declarations.append((room, data, username)),
    )
    monkeypatch.setattr(
        duel_routes,
        "execute_duel_match",
        lambda room, data, username: executions.append((room, data, username)),
    )
    return declarations, executions


def test_full_match_flow_delegates_committed_declarations_and_execution(active_duel):
    declarations, executions = active_duel
    room = "room1"

    duel_routes.on_declare_skill(
        {"room": room, "skill_id": "S-01", "prefix": "attacker", "commit": True}
    )
    duel_routes.on_declare_skill(
        {"room": room, "skill_id": "S-02", "prefix": "defender", "commit": True}
    )
    payload = {
        "room": room,
        "match_id": "test-match-uuid",
        "commandA": "10",
        "commandD": "10",
        "actorIdA": "ActorA",
        "actorIdD": "ActorD",
        "skillIdA": "S-01",
        "skillIdD": "S-02",
    }
    duel_routes.on_request_match(payload)

    assert [item[1]["skill_id"] for item in declarations] == ["S-01", "S-02"]
    assert executions == [(room, payload, "Tester")]
