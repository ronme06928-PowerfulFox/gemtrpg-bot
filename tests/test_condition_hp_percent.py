"""条件の param「HP割合」：今のHP÷最大HP×100 で比べる（C01 §14）。"""
import pytest

from manager.battle import condition_eval
from manager.battle.buff_power import calculate_buff_power_bonus_parts


def _char(hp, max_hp=50, **extra):
    return {"id": "c1", "hp": hp, "maxHp": max_hp, "states": [], **extra}


def _below_20(param="HP割合"):
    return {"source": "self", "param": param, "operator": "LTE", "value": 20}


@pytest.mark.parametrize("hp, expected", [(10, True), (11, False), (0, True), (50, False)])
def test_hp_percent_compares_ratio_of_max_hp(hp, expected):
    actor = _char(hp)
    assert condition_eval.check_condition(_below_20(), actor, None) is expected


@pytest.mark.parametrize("alias", ["HP比率", "hp_percent", "hp_ratio"])
def test_hp_percent_aliases_match_behavior_chart(alias):
    assert condition_eval.check_condition(_below_20(alias), _char(10), None) is True


def test_hp_percent_keeps_fraction():
    # 最大HP 30 の 7 は 23.3…% なので 23 以下ではない
    condition = {"source": "self", "param": "HP割合", "operator": "LTE", "value": 23}
    assert condition_eval.check_condition(condition, _char(7, max_hp=30), None) is False


def test_hp_percent_reads_max_hp_from_params():
    actor = {"id": "c1", "hp": 4, "states": [], "params": [{"label": "最大HP", "value": 40}]}
    assert condition_eval.check_condition(_below_20(), actor, None) is True


def test_hp_percent_without_max_hp_is_false():
    actor = {"id": "c1", "hp": 1, "states": []}
    assert condition_eval.check_condition(_below_20(), actor, None) is False


def test_lost_hp_still_uses_max_hp():
    condition = {"source": "self", "param": "失ったHP", "operator": "EQUALS", "value": 40}
    assert condition_eval.check_condition(condition, _char(10), None) is True


def test_passive_style_power_bonus_with_hp_percent():
    rule = {"operation": "FIXED", "value": 1, "apply_to": "final", "condition": _below_20()}
    buff = {"name": "test", "source": "passive", "passive_id": "Pa-T", "delay": 0, "lasting": -1,
            "data": {"power_bonus": [rule]}}
    low = _char(10, special_buffs=[dict(buff)])
    high = _char(30, special_buffs=[dict(buff)])
    assert calculate_buff_power_bonus_parts(low, None, {})["final"] == 1
    assert calculate_buff_power_bonus_parts(high, None, {})["final"] == 0
