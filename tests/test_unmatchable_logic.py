import manager.battle.duel_solver as duel_solver
import manager.battle.wide_solver as wide_solver


def test_duel_unmatchable_tag_is_recognized_without_name_matching():
    assert duel_solver._is_unmatchable_skill({"tags": ["マッチ不可"], "name": "攻撃"})
    assert duel_solver._is_unmatchable_skill({"tags": ["unmatchable"], "name": "攻撃"})
    assert not duel_solver._is_unmatchable_skill({"tags": ["防御"], "name": "通常攻撃"})


def test_wide_unmatchable_tag_is_recognized_without_name_matching():
    assert wide_solver._is_unmatchable_skill({"tags": ["マッチ不可"], "name": "攻撃"})
    assert wide_solver._is_unmatchable_skill({"tags": ["unmatchable"], "name": "攻撃"})
    assert not wide_solver._is_unmatchable_skill({"tags": ["防御"], "name": "通常攻撃"})
