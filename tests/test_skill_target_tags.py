from events.battle import common_routes
from manager.battle import core as battle_core


def _state_for_scope_check():
    return {
        "slots": {
            "S_ALLY": {"slot_id": "S_ALLY", "actor_id": "A1", "team": "ally"},
            "S_ENEMY": {"slot_id": "S_ENEMY", "actor_id": "E1", "team": "enemy"},
        },
        "characters": [
            {"id": "A1", "type": "ally"},
            {"id": "E1", "type": "enemy"},
        ],
    }


def test_skill_deals_damage_false_by_tag():
    skill = {"tags": ["攻撃", "非ダメージ"]}
    assert battle_core._skill_deals_damage(skill) is False


def test_skill_deals_damage_false_by_rule_tag():
    skill = {"rule_data": {"tags": ["no_damage"]}}
    assert battle_core._skill_deals_damage(skill) is False


def test_target_scope_blocks_ally_without_ally_tag(monkeypatch):
    monkeypatch.setattr(common_routes, "all_skill_data", {"S1": {"tags": ["攻撃"]}})
    state = _state_for_scope_check()
    target, err = common_routes._normalize_target_by_skill(
        "S1",
        {"type": "single_slot", "slot_id": "S_ENEMY"},
        state=state,
        source_slot_id="S_ENEMY",
        allow_none=False,
    )
    assert target is None
    assert "味方スロット" in str(err)


def test_target_scope_allows_ally_with_tag(monkeypatch):
    monkeypatch.setattr(common_routes, "all_skill_data", {"S1": {"tags": ["攻撃", "ally_target"]}})
    state = _state_for_scope_check()
    target, err = common_routes._normalize_target_by_skill(
        "S1",
        {"type": "single_slot", "slot_id": "S_ENEMY"},
        state=state,
        source_slot_id="S_ENEMY",
        allow_none=False,
    )
    assert err is None
    assert target == {"type": "single_slot", "slot_id": "S_ENEMY"}


def test_clash_win_fp_granted_for_defense_winning_against_attack():
    attacker = {"分類": "攻撃"}
    defender = {"分類": "防御"}
    assert battle_core._should_grant_clash_win_fp(attacker, defender, "defender_win") is True
    assert battle_core._should_grant_clash_win_fp(attacker, defender, "attacker_win") is False


def test_clash_win_fp_granted_for_evade_winning_against_attack():
    attacker = {"分類": "攻撃"}
    defender = {"分類": "回避"}
    assert battle_core._should_grant_clash_win_fp(attacker, defender, "defender_win") is True
    assert battle_core._should_grant_clash_win_fp(attacker, defender, "attacker_win") is False
