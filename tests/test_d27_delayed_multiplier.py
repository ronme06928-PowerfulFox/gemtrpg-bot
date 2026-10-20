import pytest

from manager.game_logic import compute_damage_multipliers


@pytest.mark.parametrize("buff,side,active", [
    ({"name": "混乱"}, "incoming", 1.5),
    ({"name": "被ダメ増加", "buff_id": "Bu-43", "data": {"value": 20}}, "incoming", 1.2),
    ({"name": "与ダメ増加", "buff_id": "Bu-45", "data": {"value": 30}}, "outgoing", 1.3),
    ({"name": "被ダメ減少", "buff_id": "Bu-44", "data": {"value": 50}}, "incoming", 0.5),
    ({"name": "与ダメ減少", "buff_id": "Bu-46", "data": {"value": 50}}, "outgoing", 0.5),
])
@pytest.mark.parametrize("delay", [1, 0, None])
def test_only_active_buffs_contribute_to_multiplier_and_logs(buff, side, active, delay):
    entry = dict(buff)
    if delay is not None:
        entry["delay"] = delay
    char = {"special_buffs": [entry]}
    result = compute_damage_multipliers(char if side == "outgoing" else {}, char if side == "incoming" else {})
    assert result["final"] == pytest.approx(1.0 if delay else active)
    assert result[side + "_logs"] == ([] if delay else [entry["name"]])
