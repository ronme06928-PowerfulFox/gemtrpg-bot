from manager.battle import skill_access
from manager.battle.system_skills import SYS_STRUGGLE_ID


def _char(fp=3, commands=""):
    return {
        "id": "A1",
        "name": "Actor",
        "commands": commands,
        "states": [{"name": "FP", "value": int(fp)}],
        "special_buffs": [],
        "flags": {},
    }


def test_evaluate_skill_access_blocks_by_flag_constraint(monkeypatch):
    actor = _char(fp=5, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [
        {"id": "r1", "mode": "block", "match": {"cost_types": ["FP"]}, "reason": "FP cost blocked"}
    ]
    monkeypatch.setattr(
        skill_access,
        "all_skill_data",
        {"P-01": {"id": "P-01", "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]}}},
    )

    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    assert "FP cost blocked" in ev["blocked_reasons"]


def test_evaluate_skill_access_add_cost_causes_insufficient(monkeypatch):
    actor = _char(fp=1, commands="[P-01 Test]")
    actor["special_buffs"] = [
        {
            "name": "Pressure",
            "data": {
                "skill_constraints": [
                    {"id": "r2", "mode": "add_cost", "match": {"cost_types": ["FP"]}, "add_cost": [{"type": "FP", "value": 1}]}
                ]
            },
        }
    ]
    monkeypatch.setattr(
        skill_access,
        "all_skill_data",
        {"P-01": {"id": "P-01", "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]}}},
    )

    ev = skill_access.evaluate_skill_access(actor, "P-01")
    assert ev["usable"] is False
    assert any("FP" in r for r in ev["blocked_reasons"])
    assert ev["effective_cost"] == [{"type": "FP", "value": 2}]


def test_list_usable_skill_ids_falls_back_to_sys_struggle(monkeypatch):
    actor = _char(fp=0, commands="[P-01 Test]")
    actor["flags"]["skill_constraints"] = [{"mode": "block", "match": {"skill_id": "p-01"}, "reason": "blocked"}]
    monkeypatch.setattr(
        skill_access,
        "all_skill_data",
        {
            "P-01": {"id": "P-01", "rule_data": {"schema": "skill_json_rule_v2", "cost": [{"type": "FP", "value": 1}]}},
            SYS_STRUGGLE_ID: {"id": SYS_STRUGGLE_ID, "rule_data": {"schema": "skill_json_rule_v2", "cost": []}},
        },
    )

    usable = skill_access.list_usable_skill_ids(actor, allow_fallback=True)
    assert usable == [SYS_STRUGGLE_ID]
