from manager.game_logic import process_skill_effects
from plugins import EFFECT_REGISTRY


def test_pb05_rupture_bursts_use_the_current_value():
    actor = {"id": "actor1", "name": "Attacker", "states": [], "params": []}
    target = {
        "id": "target1",
        "name": "Target",
        "states": [{"name": "破裂", "value": 10}],
        "params": [],
    }
    effects = [
        {
            "timing": "HIT",
            "type": "CUSTOM_EFFECT",
            "value": "破裂爆発",
            "rupture_remainder_ratio": 0.5,
        },
        {"timing": "HIT", "type": "CUSTOM_EFFECT", "value": "破裂爆発"},
    ]

    _, _, changes = process_skill_effects(
        effects, "HIT", actor, target, context={"registry": EFFECT_REGISTRY}
    )

    damage_sum = sum(change[3] for change in changes if change[1] == "CUSTOM_DAMAGE")
    rupture_updates = [
        change[3]
        for change in changes
        if change[1] == "SET_STATUS" and change[2] == "破裂"
    ]
    assert damage_sum == 15
    assert rupture_updates == [5, 0]
