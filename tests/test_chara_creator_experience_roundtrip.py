import json
import subprocess

import pytest

from events import socket_char
from extensions import db
from models import OwnedCharacter
from routes import owned_characters as oc
from tests.test_owned_character_lifecycle import (
    app_ctx, client, patch_skill_data, _login, _sample_creation_payload, _patch_socket_char,
)


def _reedit(character, confirm_save=True):
    result = subprocess.run(["node", "tests/support/chara_creator_account_runner.cjs"],
                            input=json.dumps({"character": character, "confirmSave": confirm_save}),
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("origin", [0, 7])
@pytest.mark.parametrize("legacy_spent", [0, 1])
def test_creation_reflection_reedit_save_keeps_experience_and_budget(client, app_ctx, monkeypatch, origin, legacy_spent):
    _login(client, "owner")
    payload = _sample_creation_payload()
    payload["data"]["params"].append({"label": "出身", "value": str(origin)})
    response = client.post("/api/owned_characters", json=payload)
    assert response.status_code == 201
    char_id = response.get_json()["character"]["id"]
    with app_ctx.app_context():
        owned = db.session.get(OwnedCharacter, char_id)
        if legacy_spent:
            owned.growth_log = [{"kind": "growth", "param_increases": {"筋力": legacy_spent}}]
            db.session.commit()
        char = {"id": "room_char", "name": "Test", "owner_id": "owner", "owned_character_id": char_id, "flags": {}}
        _patch_socket_char(monkeypatch, {"characters": [char], "presets": {}, "play_mode": "normal"}, "owner")
        socket_char.handle_reflect_session_results({"room": "room", "char_id": "room_char", "exp_gain": 2})
    # Skill growth and character editing must use the same cumulative budget.
    assert client.post(f"/api/owned_characters/{char_id}/growth", json={"add_skill_ids": ["Ps-01"]}).status_code == 200
    before = client.get(f"/api/owned_characters/{char_id}").get_json()["character"]
    edited = _reedit(before)
    assert edited["base"] == 6
    assert edited["scenario"] == 4 - legacy_spent
    assert edited["confirmations"] == []
    assert len(edited["requests"]) == 1
    request = edited["requests"][0]
    assert request["method"] == "PUT"
    response = client.put(request["url"], json=request["payload"])
    assert response.status_code == 200
    after = response.get_json()["character"]
    assert after["exp_total"] == before["exp_total"]
    assert after["skill_exp_budget"] == before["skill_exp_budget"]
    assert after["remaining_exp"] == before["remaining_exp"]
    assert oc.compute_exp_limit(after["data"]) == before["skill_exp_budget"]
    assert oc._get_param_value(after["data"], "経験") == 6
    assert oc._get_param_value(after["data"], "シナリオ経験") == 4 - legacy_spent


@pytest.mark.parametrize("confirm_save", [False, True])
def test_negative_scenario_experience_is_visible_and_requires_save_confirmation(confirm_save):
    character = {"id": "legacy", "name": "Legacy", "exp_total": 5, "skill_exp_budget": 5, "remaining_exp": 5,
                 "data": {"name": "Legacy", "params": [{"label": "経験", "value": "6"},
                                                            {"label": "シナリオ経験", "value": "0"}]}}
    result = _reedit(character, confirm_save)
    assert result["base"] == 6 and result["scenario"] == -1
    assert "警告" in result["loadMessage"]
    assert len(result["confirmations"]) == 1
    assert len(result["requests"]) == int(confirm_save)
