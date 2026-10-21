import json
from pathlib import Path

from manager.utils import ORIGIN_BONUS_BUFFS, get_origin_bonus_buffs


def test_al_carmeil_boon_name_matches_runtime_reference_and_catalog():
    expected = "砂海を流離う行人"
    assert ORIGIN_BONUS_BUFFS[15]["name"] == expected
    assert get_origin_bonus_buffs({"params": [{"label": "出身", "value": "15"}]})[0]["name"] == expected
    source = Path("CharaCreator/json_builder_reference_data.js").read_text(encoding="utf-8")
    reference = json.loads(source.split("=", 1)[1].strip().removesuffix(";"))
    assert next(b for b in reference["buff_refs"] if b["id"] == "Bu-25")["name"] == expected
    catalog = json.loads(Path("data/cache/buff_catalog_cache.json").read_text(encoding="utf-8"))
    assert catalog["Bu-25"]["name"] == expected
