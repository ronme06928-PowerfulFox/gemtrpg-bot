from scripts.skill_catalog_tool import load_skills, warn_catalog


def _rule(effects=None, cost=None, power_bonus=None):
    payload = {"schema": "skill_json_rule_v2"}
    if power_bonus is not None:
        payload["power_bonus"] = power_bonus
    if cost is not None:
        payload["cost"] = cost
    if effects is not None:
        payload["effects"] = effects
    import json
    return json.dumps(payload, ensure_ascii=False)


def test_warn_catalog_is_quiet_on_real_cache_except_known_findings():
    """現行133件に対する既知の妥当な逸脱のみが残ること（回帰）。

    F02の主要確定調整レコード（Mp-08/Ps-13）はallowlistで抑制済み、
    Ms-09はF02記載の既知例外として抑制済み、power_bonus/条件付き加算を持つ
    スキル（Pb-10/Ms-06）は判定対象外。Ms-04の出血8のみ未レビューの実逸脱として残る。
    """
    skills = load_skills()
    warnings = warn_catalog(skills)
    ids = {w["skill_id"] for w in warnings}
    assert "Mp-08" not in ids, "Mp-08 はF02承認済み調整のためallowlistで抑制されるはず"
    assert "Ps-13" not in ids, "Ps-13 はF02承認済み調整のためallowlistで抑制されるはず"
    assert "Ms-09" not in ids, "Ms-09 はF02記載の既知例外のためallowlistで抑制されるはず"
    assert "Pb-10" not in ids, "power_bonusを持つスキルはpower_stage判定対象外のはず"
    assert "Ms-06" not in ids, "条件付きDAMAGE_BONUSを持つスキルはpower_stage判定対象外のはず"
    assert any(w["skill_id"] == "Ms-04" for w in warnings), "Ms-04 の出血8は未レビューの実逸脱として残るはず"


def test_warn_power_stage_detects_deviation():
    skills = {
        "Ps-99": {
            "スキルID": "Ps-99",
            "取得コスト": "1",
            "基礎威力": "30",
            "ダイス威力": "+0",
            "特記処理": _rule(effects=[]),
        }
    }
    warnings = warn_catalog(skills)
    assert len(warnings) == 1
    assert warnings[0]["category"] == "power_stage"
    assert warnings[0]["skill_id"] == "Ps-99"


def test_warn_power_stage_skips_conditional_power_bonus_skills():
    skills = {
        "Ps-98": {
            "スキルID": "Ps-98",
            "取得コスト": "1",
            "基礎威力": "0",
            "ダイス威力": "+1d2",
            "特記処理": _rule(
                effects=[],
                power_bonus=[{"source": "target", "param": "亀裂", "operator": "PER_N_BONUS", "per_N": 1, "value": 1}],
            ),
        }
    }
    assert warn_catalog(skills) == []


def test_warn_cost_detects_deviation():
    skills = {
        "Mp-98": {
            "スキルID": "Mp-98",
            "取得コスト": "1",
            "基礎威力": "8",
            "ダイス威力": "+0",
            "特記処理": _rule(effects=[], cost=[{"type": "MP", "value": 10}]),
        }
    }
    warnings = warn_catalog(skills)
    assert any(w["category"] == "cost" and w["skill_id"] == "Mp-98" for w in warnings)


def test_warn_state_value_only_checks_hit_timing():
    skills = {
        "Ps-97": {
            "スキルID": "Ps-97",
            "取得コスト": "1",
            "基礎威力": "8",
            "ダイス威力": "+0",
            "特記処理": _rule(effects=[
                {"timing": "WIN", "type": "APPLY_STATE", "target": "target", "state_name": "出血", "value": 20},
            ]),
        }
    }
    # WIN タイミングは対象外なので WARN は出ない
    assert warn_catalog(skills) == []


def test_warn_state_value_flags_hit_deviation():
    skills = {
        "Ps-96": {
            "スキルID": "Ps-96",
            "取得コスト": "1",
            "基礎威力": "8",
            "ダイス威力": "+0",
            "特記処理": _rule(effects=[
                {"timing": "HIT", "type": "APPLY_STATE", "target": "target", "state_name": "出血", "value": 20},
            ]),
        }
    }
    warnings = warn_catalog(skills)
    assert any(w["category"] == "state_value" and w["skill_id"] == "Ps-96" for w in warnings)


def test_warn_acquire_high_flags_unapproved_skill():
    skills = {
        "Ps-95": {
            "スキルID": "Ps-95",
            "取得コスト": "3",
            "基礎威力": "15",
            "ダイス威力": "+0",
            "特記処理": _rule(effects=[]),
        }
    }
    warnings = warn_catalog(skills)
    assert any(w["category"] == "acquire_cost" and w["skill_id"] == "Ps-95" for w in warnings)


def test_warn_action_economy_flags_unapproved_holder():
    skills = {
        "Ps-94": {
            "スキルID": "Ps-94",
            "取得コスト": "1",
            "基礎威力": "8",
            "ダイス威力": "+0",
            "特記処理": _rule(effects=[
                {"timing": "HIT", "type": "USE_SKILL_AGAIN", "max_reuses": 1},
            ]),
        }
    }
    warnings = warn_catalog(skills)
    assert any(w["category"] == "action_economy" and w["skill_id"] == "Ps-94" for w in warnings)


def test_warn_action_economy_allows_approved_holder():
    skills = {
        "Ps-04": {
            "スキルID": "Ps-04",
            "取得コスト": "1",
            "基礎威力": "8",
            "ダイス威力": "+0",
            "特記処理": _rule(effects=[
                {"timing": "HIT", "type": "USE_SKILL_AGAIN", "max_reuses": 1},
            ]),
        }
    }
    warnings = warn_catalog(skills)
    assert not any(w["category"] == "action_economy" for w in warnings)
