from manager.game_logic import process_skill_effects
from manager.utils import get_status_value


def _build_actor():
    return {
        "id": "a1",
        "name": "Actor",
        "type": "ally",
        "hp": 100,
        "maxHp": 100,
        "mp": 30,
        "maxMp": 30,
        "states": [{"name": "FP", "value": 0}],
        "special_buffs": [],
        "params": [],
        "x": 0,
        "y": 0,
    }


def _build_target(rupture, buffs=None):
    return {
        "id": "t1",
        "name": "Target",
        "type": "enemy",
        "hp": 120,
        "maxHp": 120,
        "mp": 20,
        "maxMp": 20,
        "states": [{"name": "破裂", "value": int(rupture)}],
        "special_buffs": list(buffs or []),
        "params": [],
        "x": 1,
        "y": 0,
    }


def test_burst_emits_set_status_change_for_consumption():
    actor = _build_actor()
    target = _build_target(rupture=10)
    effects = [
        {"timing": "HIT", "type": "CUSTOM_EFFECT", "target": "target", "value": "破裂爆発", "rupture_remainder_ratio": 0.5},
        {"timing": "HIT", "type": "CUSTOM_EFFECT", "target": "target", "value": "破裂爆発"},
    ]
    context = {"characters": [actor, target], "timeline": [], "room": "unit"}

    _, _, changes = process_skill_effects(effects, "HIT", actor, target, context=context)

    set_status_events = [c for c in changes if c[1] == "SET_STATUS" and c[2] == "破裂"]
    damage_events = [c for c in changes if c[1] == "CUSTOM_DAMAGE" and c[2] == "破裂爆発"]

    assert [int(c[3]) for c in set_status_events] == [5, 0]
    assert [int(c[3]) for c in damage_events] == [10, 5]
    assert get_status_value(target, "破裂") == 10


def test_burst_no_consume_buff_skips_set_status():
    actor = _build_actor()
    target = _build_target(
        rupture=7,
        buffs=[{"name": "破裂威力減少無効", "buff_id": "Bu-06", "delay": 0, "lasting": 1}],
    )
    effects = [{"timing": "HIT", "type": "CUSTOM_EFFECT", "target": "target", "value": "破裂爆発"}]
    context = {"characters": [actor, target], "timeline": [], "room": "unit"}

    _, _, changes = process_skill_effects(effects, "HIT", actor, target, context=context)

    set_status_events = [c for c in changes if c[1] == "SET_STATUS" and c[2] == "破裂"]
    damage_events = [c for c in changes if c[1] == "CUSTOM_DAMAGE" and c[2] == "破裂爆発"]

    assert not set_status_events
    assert [int(c[3]) for c in damage_events] == [7]
