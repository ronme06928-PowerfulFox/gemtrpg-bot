import pytest

from routes import owned_characters as oc
from tests.test_chara_creator_experience_roundtrip import _reedit
from tests.test_owned_character_lifecycle import (
    app_ctx, client, patch_skill_data, _login, _sample_creation_payload,
)


@pytest.mark.parametrize("origin,bonus", [(o, b) for o in (1, 2, 12) for b in (6, 7)] + [(6, 0), (7, 0)])
def test_selected_origin_budget_matches_creator_through_save_reedit_and_growth(client, monkeypatch, origin, bonus):
    _login(client, "owner")
    monkeypatch.setitem(oc.all_skill_data, "Ms-01", {"取得コスト": "2"})
    payload = _sample_creation_payload()
    payload["data"]["params"] += [{"label": "出身", "value": str(origin)}, {"label": "ボーナス", "value": str(bonus)}]
    payload["data"]["commands"] = "0+0 【Ms-01 magic】"
    effective = bonus or origin
    # CharaCreator: base 6 + scenario 2, origin 7 grants one budget point;
    # origin 6 covers one point of the total magic acquisition cost.
    limit = 9 if effective == 7 else 8
    used = 1 if effective == 6 else 2
    assert oc.compute_exp_limit(payload["data"]) == limit
    assert oc.compute_used_exp(payload["data"]) == used
    response = client.post("/api/owned_characters", json=payload)
    assert response.status_code == 201
    before = response.get_json()["character"]
    edited = _reedit(before)
    assert edited["base"] == 6 and edited["scenario"] == 2
    saved = edited["requests"][0]
    response = client.put(saved["url"], json=saved["payload"])
    assert response.status_code == 200
    after = response.get_json()["character"]
    assert after["exp_total"] == limit
    assert after["used_exp"] == used
    assert after["remaining_exp"] == limit - used
    assert client.post(f'/api/owned_characters/{after["id"]}/growth', json={"add_skill_ids": ["Ps-01"]}).status_code == 200
