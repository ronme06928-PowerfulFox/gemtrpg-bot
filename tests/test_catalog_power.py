import copy
import json
from pathlib import Path

import pytest

from tests.test_catalog_skill import catalog, client
from manager.catalog.skills import from_cache

URL = "/api/catalog/skill/power_preview"
CACHE = json.loads((Path(__file__).resolve().parents[1] / "data/cache/skills_cache.json").read_text(encoding="utf-8"))


def preview(app, skill, params=None):
    payload = from_cache(CACHE[skill]) if isinstance(skill, str) else skill
    response = client(app, "reader").post(URL, json={"payload": payload, "params": params or {}})
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def numbers(result):
    return result["min"], result["avg"], result["max"], result["dice"]


def test_ranges_follow_the_battle_base_power_and_palette_dice(catalog):
    assert numbers(preview(catalog, "Ps-04")) == (8, 10.5, 13, "7+1d6")
    assert numbers(preview(catalog, "Ps-04", {"物理補正": 3})) == (9, 12.5, 16, "7+1d6+1d3")
    assert numbers(preview(catalog, "Ps-04", {"物理補正": 5})) == (9, 13.5, 18, "7+1d6+1d5")
    skill = from_cache(CACHE["Ps-04"])
    skill.update(基礎威力="99", ダイス威力="+2d6")
    # 戦闘と同じく、基礎威力は項目から、ダイスはパレットから読む（パレットだけのダイスが無ければダイス威力の項目）。
    assert numbers(preview(catalog, skill)) == (100, 102.5, 105, "99+1d6")
    skill["チャットパレット"] = "9+2d6+1d{物理補正} 【試験】"
    assert numbers(preview(catalog, skill)) == (101, 106, 111, "99+2d6")
    skill["チャットパレット"] = "9-1d-2+1d0"
    assert numbers(preview(catalog, skill)) == (99, 99, 99, "99")
    skill["チャットパレット"] = "9"
    assert numbers(preview(catalog, skill)) == (101, 106, 111, "99+2d6")


def test_bonus_text_and_baseline_without_target(catalog):
    ms = preview(catalog, "Ms-09")
    assert numbers(ms) == (9, 11.5, 14, "22-1d6-7")
    assert [rule["in_baseline"] for rule in ms["rules"]] == [False, True]
    assert not preview(catalog, "E-30")["rules"][0]["in_baseline"]
    expected = {
        "Mb-13": "相手の破裂4につき基礎威力+1（+3まで）",
        "Pb-14": "自分の蓄力3につき最終威力+1（+7まで）",
        "Pp-10": "相手の亀裂2につきダイスの面-1（-4まで）",
        "Pb-08": "相手の破裂が0なら基礎威力+2",
    }
    for key, line in expected.items():
        assert preview(catalog, key)["rules"][0]["text"] == line
    skill = from_cache(CACHE["Ps-04"])
    skill["特記処理"]["power_bonus"] = [{"operation": "UNKNOWN"}]
    assert preview(catalog, skill)["rules"][0]["text"] is None


def test_preview_is_read_only_and_accepts_all_published_skills(catalog, monkeypatch):
    from extensions import all_skill_data, active_room_states
    from manager.catalog import repository
    from models import CatalogEntry, CatalogDraft, CatalogHistory

    def forbidden(*args, **kwargs):
        pytest.fail("見込みの計算から保存や検査を呼んだ")

    monkeypatch.setattr(repository, "update_draft", forbidden)
    monkeypatch.setattr("routes.catalog.inspect_payload", forbidden)
    models = (CatalogEntry, CatalogDraft, CatalogHistory)
    counts = [model.query.count() for model in models]
    memory = copy.deepcopy(all_skill_data), copy.deepcopy(active_room_states)
    assert len(CACHE) == 138
    for key in CACHE:
        assert all(rule["text"] is not None for rule in preview(catalog, key)["rules"]), key
    assert [model.query.count() for model in models] == counts
    assert (all_skill_data, active_room_states) == memory


def test_bad_requests_and_authentication(catalog):
    assert catalog.test_client().post(URL, json={}).status_code in (401, 403)
    reader = client(catalog, "reader")
    for body in [
        [], {}, {"payload": []}, {"payload": {"チャットパレット": ""}},
        {"payload": {"チャットパレット": "7+1d6oops"}},
        {"payload": {"チャットパレット": "7+1d6", "特記処理": []}},
        {"payload": {"チャットパレット": "7+1d6"}, "params": {"物理補正": -1}},
    ]:
        response = reader.post(URL, json=body)
        assert response.status_code == 400
        assert response.get_json()["error"]
