from scripts.migrate_skill_json_rule_v2 import migrate_skills


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
        "migrated": {"skills": 0, "buff_catalog": 0},
        "failed": {"skills": 0, "buff_catalog": 0},
        "errors": [],
    }

    out = migrate_skills(skills, buffs, report)
    rule = out["S-1"]["rule_data"]
    eff = rule["effects"][0]
    assert rule.get("schema") == "skill_json_rule_v2"
    assert eff.get("buff_id") == "Bu-32"
    assert eff.get("data", {}).get("value") == 5
    assert not report["errors"]
