from scripts.migrate_skill_json_rule_v2 import migrate_skills, migrate_stage_presets


def test_migrate_skills_converts_dynamic_buff_name_to_buff_id():
    skills = {
        "S-1": {
            "特記処理": '{"effects":[{"type":"APPLY_BUFF","target":"self","buff_name":"Power_Atk5","lasting":2}]}'
        }
    }
    buffs = {
        "Bu-32": {"id": "Bu-32", "name": "攻撃威力アップ", "effect": {}},
    }
    report = {
        "migrated": {"skills": 0, "buff_catalog": 0, "field_effects": 0},
        "failed": {"skills": 0, "buff_catalog": 0, "field_effects": 0},
        "errors": [],
    }

    out = migrate_skills(skills, buffs, report)
    rule = out["S-1"]["rule_data"]
    eff = rule["effects"][0]
    assert rule.get("schema") == "skill_json_rule_v2"
    assert eff.get("buff_id") == "Bu-32"
    assert eff.get("data", {}).get("value") == 5
    assert not report["errors"]


def test_migrate_stage_presets_normalizes_skill_constraints():
    stage = {
        "stage_presets": {
            "ST-1": {
                "id": "ST-1",
                "field_effect_profile": {
                    "version": 1,
                    "rules": [
                        {
                            "rule_id": "r1",
                            "type": "SPEED_ROLL_MOD",
                            "scope": "ALL",
                            "value": -1,
                            "skill_constraints": {"mode": "block", "match": {"skill_id": "P-01"}},
                        }
                    ],
                },
            }
        }
    }
    report = {
        "migrated": {"skills": 0, "buff_catalog": 0, "field_effects": 0},
        "failed": {"skills": 0, "buff_catalog": 0, "field_effects": 0},
        "errors": [],
    }
    out = migrate_stage_presets(stage, report)
    rules = out["stage_presets"]["ST-1"]["field_effect_profile"]["rules"]
    assert isinstance(rules[0].get("skill_constraints"), list)
    assert rules[0]["skill_constraints"][0]["mode"] == "block"
    assert report["migrated"]["field_effects"] == 1
