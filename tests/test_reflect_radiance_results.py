from copy import deepcopy

import pytest

from events import socket_char
from extensions import db
from models import OwnedCharacter
from routes import owned_characters as oc
from tests.test_reflect_session_results import app_ctx, _room_char, _state_with_char, _patch_char
from tests.test_owned_character_growth import _login


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("exp_gain,radiance_gain", [(0, 2), (3, 2), (0, 0)])
def test_reflection_adds_separate_radiance_budget_once(app_ctx, monkeypatch, existing, exp_gain, radiance_gain):
    owned = db.session.get(OwnedCharacter, "owned_1")
    if existing:
        owned.data = {**owned.data, "params": [{"label": "通過点", "value": "1"}]}
        db.session.commit()
    char = _room_char()
    emits = _patch_char(monkeypatch, _state_with_char(char), "owner")
    payload = {"room": "r1", "char_id": "char_1", "exp_gain": exp_gain, "radiance_gain": radiance_gain}
    socket_char.handle_reflect_session_results(payload)
    socket_char.handle_reflect_session_results({**payload, "radiance_gain": 99})
    db.session.expire_all()
    owned = db.session.get(OwnedCharacter, "owned_1")
    assert owned.exp_total == 10 + exp_gain
    assert oc.compute_radiance_limit(owned.data) == int(existing) + radiance_gain
    assert owned.data["inventory"] == {"item-heal": 1}
    assert len(owned.growth_log) == 1
    assert owned.growth_log[0]["radiance_gain"] == radiance_gain
    assert char["flags"]["results_reflected"]
    results = [p for event, p, _ in emits if event == "reflect_session_results_result"]
    assert results[0]["radiance_gain"] == radiance_gain
    assert results[1]["reason"] == "already_reflected"


def test_gm_can_reflect_radiance_for_owner(app_ctx, monkeypatch):
    char = _room_char()
    emits = _patch_char(monkeypatch, _state_with_char(char), "gm_user", attribute="GM")
    socket_char.handle_reflect_session_results({"room": "r1", "char_id": "char_1", "radiance_gain": 3})
    assert oc.compute_radiance_limit(db.session.get(OwnedCharacter, "owned_1").data) == 3
    assert any(event == "reflect_session_results_result" and not p["skipped"] for event, p, _ in emits)


@pytest.mark.parametrize("gain", [-1, -0.5, "-2", 1.5, "oops", None])
def test_invalid_radiance_gain_does_not_change_any_state(app_ctx, monkeypatch, gain):
    owned = db.session.get(OwnedCharacter, "owned_1")
    before = deepcopy(owned.data)
    char = _room_char()
    emits = _patch_char(monkeypatch, _state_with_char(char), "owner")
    side_effects = []
    monkeypatch.setattr(socket_char, "save_specific_room_state", lambda *_a: side_effects.append("save"))
    monkeypatch.setattr(socket_char, "broadcast_state_update", lambda *_a: side_effects.append("broadcast"))
    socket_char.handle_reflect_session_results({"room": "r1", "char_id": "char_1", "exp_gain": 4,
                                               "items": {"item-heal": 3}, "radiance_gain": gain})
    db.session.expire_all()
    owned = db.session.get(OwnedCharacter, "owned_1")
    assert (owned.exp_total, owned.data, owned.growth_log) == (10, before, [])
    assert char["flags"] == {} and side_effects == []
    result = next(p for event, p, _ in emits if event == "reflect_session_results_result")
    assert result["skipped"] and result["reason"] == "invalid_radiance_gain"


@pytest.mark.parametrize("mode", ["hollow", "battle_only"])
def test_radiance_addition_is_limited_to_normal_rooms(app_ctx, monkeypatch, mode):
    char = _room_char()
    _patch_char(monkeypatch, _state_with_char(char, play_mode=mode), "owner")
    socket_char.handle_reflect_session_results({"room": "r1", "char_id": "char_1", "exp_gain": 2, "radiance_gain": 9})
    owned = db.session.get(OwnedCharacter, "owned_1")
    assert owned.exp_total == 12
    assert oc.compute_radiance_limit(owned.data) == 0


def test_reflected_points_can_buy_radiance_without_spending_exp(app_ctx, monkeypatch):
    char = _room_char()
    _patch_char(monkeypatch, _state_with_char(char), "owner")
    socket_char.handle_reflect_session_results({"room": "r1", "char_id": "char_1", "radiance_gain": 3})
    monkeypatch.setattr(oc.radiance_loader, "load_skills", lambda: {"R-01": {"id": "R-01", "name": "Test", "cost": 2}})
    client = app_ctx.test_client()
    _login(client, "owner")
    response = client.post("/api/owned_characters/owned_1/growth", json={"add_radiance_ids": ["R-01"]})
    assert response.status_code == 200, response.get_json()
    body = response.get_json()["character"]
    assert body["radiance_limit"] == 3 and body["radiance_remaining"] == 1
    assert body["remaining_exp"] == 10
