import pytest

from manager.battle import core
from plugins.buffs.dodge_lock import DodgeLockBuff
from tests.test_select_resolve_smoke import _state_value
from tests.test_select_resolve_timing_normalization import (
    _clash_skill, _make_char, _patch_deterministic_clash,
)


def _resolve(monkeypatch, category_a, category_d, power_a=10, power_d=10, origin=0):
    actors = [_make_char("A1", "ally"), _make_char("B1", "enemy")]
    skills = []
    for i, category in enumerate([category_a, category_d]):
        skill = _clash_skill(f"S{i}", [])
        skill.update({"分類": category, "category": category,
                      "tags": ["攻撃"] if category == "物理" else ["守備", category]})
        skills.append(skill)
        if category == "防御":
            actors[i]["params"].append({"label": "出身", "value": str(origin)})
    duel = _patch_deterministic_clash(monkeypatch, power_a, power_d)
    state = {"characters": actors, "timeline": []}
    monkeypatch.setattr(duel, "all_skill_data", {s["id"]: s for s in skills})
    monkeypatch.setattr(duel, "get_room_state", lambda _: state)
    result = core._resolve_clash_by_existing_logic("room_t", state, *actors, *skills)
    assert result["ok"] is True
    return result, actors


@pytest.mark.parametrize("category", ["防御", "回避"])
@pytest.mark.parametrize("guard_side", [0, 1], ids=["attacker", "defender"])
def test_equal_power_defensive_win_is_independent_of_processing_side(monkeypatch, category, guard_side):
    categories = ["物理", "物理"]
    categories[guard_side] = category
    result, actors = _resolve(monkeypatch, *categories)
    assert result["outcome"] == ("attacker_win" if guard_side == 0 else "defender_win")
    assert [_state_value(c, "FP") for c in actors] == ([1, 0] if guard_side == 0 else [0, 1])
    assert [c["hp"] for c in actors] == [100, 100]
    assert DodgeLockBuff.has_re_evasion(actors[guard_side]) is (category == "回避")


@pytest.mark.parametrize("guard_side", [0, 1])
def test_gian_balf_equal_power_win_has_no_counter_damage(monkeypatch, guard_side):
    categories = ["物理", "物理"]
    categories[guard_side] = "防御"
    result, actors = _resolve(monkeypatch, *categories, origin=8)
    assert result["outcome"] == ("attacker_win" if guard_side == 0 else "defender_win")
    assert [c["hp"] for c in actors] == [100, 100]
    assert "反撃ダメージ" not in str(result)


@pytest.mark.parametrize("category", ["物理", "防御"])
def test_same_category_tie_stays_draw_without_win_fp(monkeypatch, category):
    result, actors = _resolve(monkeypatch, category, category)
    assert result["outcome"] == "draw"
    assert [_state_value(c, "FP") for c in actors] == [0, 0]
    assert [c["hp"] for c in actors] == [100, 100]


@pytest.mark.parametrize("category", ["防御", "回避"])
@pytest.mark.parametrize("guard_side", [0, 1])
@pytest.mark.parametrize("guard_wins", [False, True])
def test_strict_power_win_fp_conditions_stay_unchanged(monkeypatch, category, guard_side, guard_wins):
    categories = ["物理", "物理"]
    categories[guard_side] = category
    powers = [10, 10]
    powers[guard_side] = 12 if guard_wins else 8
    result, actors = _resolve(monkeypatch, *categories, *powers)
    expected = [0, 0]
    if guard_wins:
        expected[guard_side] = 1
    assert [_state_value(c, "FP") for c in actors] == expected
    assert result["outcome"] == ("attacker_win" if (guard_side == 0) == guard_wins else "defender_win")
