import json
from pathlib import Path

from manager.utils import ORIGIN_BONUS_BUFFS, get_origin_bonus_buffs


def test_al_carmeil_boon_name_matches_runtime_reference_and_catalog(monkeypatch):
    expected = "砂海を流離う行人"
    assert ORIGIN_BONUS_BUFFS[15]["name"] == expected
    assert get_origin_bonus_buffs({"params": [{"label": "出身", "value": "15"}]})[0]["name"] == expected
    catalog = json.loads(Path("data/cache/buff_catalog_cache.json").read_text(encoding="utf-8"))
    assert catalog["Bu-25"]["name"] == expected
    from flask import Flask
    import app as app_module

    monkeypatch.setattr(app_module, "all_buff_data", catalog, raising=False)
    app = Flask(__name__)
    app_module.register_http_routes(app)
    reference = app.test_client().get("/api/get_buff_data").get_json()
    assert reference["Bu-25"]["name"] == expected
