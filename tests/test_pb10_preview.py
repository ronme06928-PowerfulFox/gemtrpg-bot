import json

from manager.game_logic import calculate_skill_preview


def _char(char_id, team, rupture):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": 100,
        "maxHp": 100,
        "mp": 20,
        "maxMp": 20,
        "states": [
            {"name": "FP", "value": 0},
            {"name": "破裂", "value": int(rupture)},
        ],
        "params": [],
        "special_buffs": [],
    }


def test_pb10_preview_scales_with_target_rupture_from_rule_json():
    actor = _char("A1", "ally", 0)
    skill = {
        "スキルID": "Pb-10",
        "チャットパレット": "0+1d1 【Pb-10 右肩上がり】",
        "基礎威力": "0",
        "ダイス威力": "+1d1",
        "特記処理": json.dumps(
            {
                "power_bonus": [
                    {
                        "source": "target",
                        "param": "破裂",
                        "operator": "PER_N_BONUS",
                        "per_N": 1,
                        "value": 1,
                        "max_bonus": 30,
                    }
                ]
            },
            ensure_ascii=False,
        ),
    }

    for rupture, expected_bonus in [(0, 0), (1, 1), (5, 5), (30, 30), (31, 30)]:
        target = _char("E1", "enemy", rupture)
        preview = calculate_skill_preview(
            actor,
            target,
            skill,
            context={"characters": [actor, target]},
        )
        pb = preview.get("power_breakdown", {})
        assert int(pb.get("rule_power_bonus", 0)) == expected_bonus
        assert int(preview.get("min_damage", 0)) == 1 + expected_bonus
        assert int(preview.get("max_damage", 0)) == 1 + expected_bonus


def test_pb10_preview_uses_cached_skill_data_rule_operator():
    with open("data/cache/skills_cache.json", "r", encoding="utf-8") as f:
        skills = json.load(f)
    skill = skills["Pb-10"]
    actor = _char("A1", "ally", 0)
    target = _char("E1", "enemy", 12)

    preview = calculate_skill_preview(
        actor,
        target,
        skill,
        context={"characters": [actor, target]},
    )
    pb = preview.get("power_breakdown", {})
    assert int(pb.get("rule_power_bonus", 0)) == 12
    assert int(preview.get("min_damage", 0)) == 13
    assert int(preview.get("max_damage", 0)) == 13
