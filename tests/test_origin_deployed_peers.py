import pytest

from manager import utils


def _char(char_id, origin, team, position):
    return {"id": char_id, "type": team, "hp": 100, "x": position[0], "y": position[1],
            "totalSpeed": 6, "params": [{"label": "出身", "value": str(origin)}, {"label": "速度値", "value": "6"}]}


@pytest.mark.parametrize("position,deployed", [((None, None), False), ((-1, -1), False), ((0, 0), True), ((2, 5), True)])
def test_emrida_and_same_speed_helper_count_only_deployed_peers(position, deployed):
    actor = _char("A", 17, "ally", (0, 0))
    peer = _char("B", 0, "enemy", position)
    context = {"characters": [actor, peer]}
    result = utils.compute_origin_skill_modifiers(actor, peer, {"分類": "物理"}, context=context)
    assert result["base_power_bonus"] == int(deployed)
    assert utils.has_same_speed_peer(actor, context=context) is deployed


@pytest.mark.parametrize("position,deployed", [((None, None), False), ((-1, -1), False), ((0, 0), True), ((2, 5), True)])
def test_flodias_counts_only_deployed_enemy_valwaire(position, deployed):
    actor = _char("A", 14, "ally", (0, 0))
    peer = _char("B", 13, "enemy", position)
    result = utils.compute_origin_skill_modifiers(actor, peer, {"分類": "回避"}, context={"characters": [actor, peer]})
    assert result["dice_power_bonus"] == 1 + int(deployed)
