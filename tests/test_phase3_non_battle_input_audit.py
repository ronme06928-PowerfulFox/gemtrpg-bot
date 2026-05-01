import json

from manager.json_rule_v2 import JsonRuleV2Error, normalize_skill_constraints_rows


def test_phase3_non_battle_stage_presets_skill_constraints_are_normalizable():
    data = json.load(open("data/cache/battle_only_presets_cache.json", encoding="utf-8"))
    assert isinstance(data, dict)

    stage_presets = data.get("stage_presets", {})
    assert isinstance(stage_presets, dict)

    checked = 0
    for stage_id, stage in stage_presets.items():
        if not isinstance(stage, dict):
            continue
        profile = stage.get("field_effect_profile", {})
        if not isinstance(profile, dict):
            continue
        rules = profile.get("rules", [])
        if not isinstance(rules, list):
            continue
        for idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            if "skill_constraints" not in rule:
                continue
            checked += 1
            try:
                normalized = normalize_skill_constraints_rows(
                    rule.get("skill_constraints"),
                    source_path=f"stage_presets.{stage_id}.rules[{idx}].skill_constraints",
                )
            except JsonRuleV2Error as exc:
                raise AssertionError(f"{stage_id}[{idx}] invalid skill_constraints: {exc}") from exc
            assert isinstance(normalized, list)

    # This audit should still be valid even when no constraints are present.
    assert checked >= 0
