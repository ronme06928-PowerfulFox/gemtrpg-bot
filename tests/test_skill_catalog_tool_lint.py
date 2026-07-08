from scripts.skill_catalog_tool import lint_catalog, load_skills


def test_lint_catalog_passes_on_real_skills_cache():
    """計画書31 Phase1 完了条件: 現行キャッシュ全件でERROR 0件。"""
    skills = load_skills()
    assert skills, "skills_cache.json が空、またはロードに失敗している"
    errors = lint_catalog(skills)
    assert errors == []


def test_lint_catalog_detects_invalid_json_rule():
    skills = {
        "S-BROKEN": {
            "特記処理": '{"schema":"skill_json_rule_v2","effects":[{"timing":"HIT"'  # 閉じ括弧欠落
        }
    }
    errors = lint_catalog(skills)
    assert len(errors) == 1
    assert errors[0]["skill_id"] == "S-BROKEN"
    assert "invalid JSON" in errors[0]["error"]


def test_lint_catalog_detects_missing_schema_in_strict_mode():
    skills = {
        "S-NOSCHEMA": {
            "特記処理": '{"effects":[{"timing":"HIT","type":"DAMAGE_BONUS","value":1}]}'
        }
    }
    errors = lint_catalog(skills)
    assert len(errors) == 1
    assert errors[0]["skill_id"] == "S-NOSCHEMA"
    assert "schema" in errors[0]["error"]


def test_lint_catalog_detects_unresolvable_buff_id():
    skills = {
        "S-BADBUFF": {
            "特記処理": (
                '{"schema":"skill_json_rule_v2","effects":['
                '{"timing":"HIT","type":"APPLY_BUFF","target":"target",'
                '"buff_id":"Bu-NOT-EXIST","lasting":1}]}'
            )
        }
    }
    errors = lint_catalog(skills)
    assert len(errors) == 1
    assert errors[0]["skill_id"] == "S-BADBUFF"
    assert "buff_id" in errors[0]["error"]


def test_lint_catalog_detects_broken_embedded_skill_constraints():
    skills = {
        "S-BADCONSTRAINT": {
            "特記処理": (
                '{"schema":"skill_json_rule_v2","effects":['
                '{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target",'
                '"buff_id":"Bu-00","lasting":1,'
                '"data":{"skill_constraints":[{"mode":"invalid_mode"}]}}]}'
            )
        }
    }
    errors = lint_catalog(skills)
    assert len(errors) == 1
    assert errors[0]["skill_id"] == "S-BADCONSTRAINT"
    assert "mode" in errors[0]["error"]


def test_lint_catalog_ignores_skills_without_rule_json():
    skills = {"S-EMPTY": {"スキルID": "S-EMPTY", "デフォルト名称": "空技"}}
    assert lint_catalog(skills) == []
