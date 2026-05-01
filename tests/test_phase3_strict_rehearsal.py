import json

from manager.cache_paths import SKILLS_CACHE_FILE, load_json_cache
from manager.json_rule_v2 import extract_and_normalize_skill_rule_data


def test_phase3_strict_rehearsal_all_cached_skills_are_valid_v2():
    catalog = load_json_cache(SKILLS_CACHE_FILE)
    assert isinstance(catalog, dict) and catalog

    checked = 0
    for skill_id, skill_data in catalog.items():
        if not isinstance(skill_data, dict):
            continue
        checked += 1
        rule = extract_and_normalize_skill_rule_data(
            skill_data,
            skill_id=str(skill_id),
            strict=True,
        )
        assert rule.get("schema") == "skill_json_rule_v2"
        effects = rule.get("effects", [])
        assert isinstance(effects, list)
        for effect in effects:
            if not isinstance(effect, dict):
                continue
            effect_type = str(effect.get("type", "")).strip().upper()
            if effect_type in {"APPLY_BUFF", "REMOVE_BUFF"}:
                assert str(effect.get("buff_id", "") or "").strip(), f"{skill_id}: {effect_type} missing buff_id"

    assert checked > 0
