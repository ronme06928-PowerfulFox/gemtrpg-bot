import pytest

from manager.battle.battle_result import estimate_battle_result


@pytest.mark.parametrize(("ally_hp", "enemy_hp", "result"), [
    (1, 0, "ally_win"),
    (0, 1, "enemy_win"),
    (0, 0, "draw"),
    (1, 1, "in_progress"),
])
def test_estimate_battle_result(ally_hp, enemy_hp, result):
    assert estimate_battle_result({"characters": [
        {"type": "ally", "hp": ally_hp},
        {"team": "enemy", "hp": enemy_hp},
    ]}) == result
