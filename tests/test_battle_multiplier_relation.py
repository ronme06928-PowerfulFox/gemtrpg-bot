from manager.game_logic import compute_damage_multipliers, check_condition


def test_compute_damage_multipliers_combines_outgoing_and_incoming():
    attacker = {
        "special_buffs": [
            {"name": "Out", "outgoing_damage_multiplier": 1.2}
        ]
    }
    defender = {
        "special_buffs": [
            {"name": "In", "damage_multiplier": 0.5},
            {"name": "混乱"},
        ]
    }
    result = compute_damage_multipliers(attacker, defender)
    assert round(float(result["outgoing"]), 4) == 1.2
    assert round(float(result["incoming"]), 4) == 0.75
    assert round(float(result["final"]), 4) == 0.9
    assert "Out" in result["outgoing_logs"]
    assert "In" in result["incoming_logs"]


def test_relation_condition_supports_ally_enemy_checks():
    actor = {"id": "A", "type": "ally"}
    ally_target = {"id": "B", "type": "ally"}
    enemy_target = {"id": "E", "type": "enemy"}

    cond_ally = {"source": "relation", "param": "target_is_ally", "operator": "EQUALS", "value": 1}
    cond_enemy = {"source": "relation", "param": "target_is_enemy", "operator": "EQUALS", "value": 1}
    cond_same = {"source": "relation", "param": "same_team", "operator": "EQUALS", "value": 1}

    assert check_condition(cond_ally, actor, ally_target) is True
    assert check_condition(cond_enemy, actor, ally_target) is False
    assert check_condition(cond_same, actor, ally_target) is True

    assert check_condition(cond_ally, actor, enemy_target) is False
    assert check_condition(cond_enemy, actor, enemy_target) is True
    assert check_condition(cond_same, actor, enemy_target) is False


def test_compute_damage_multipliers_honors_outgoing_condition():
    attacker = {
        "type": "ally",
        "special_buffs": [
            {
                "name": "氷断ち",
                "outgoing_damage_multiplier": 1.2,
                "condition": {
                    "source": "target",
                    "param": "buff_count:減速",
                    "operator": "GTE",
                    "value": 1,
                },
            }
        ],
    }
    defender_with_slow = {
        "type": "enemy",
        "special_buffs": [
            {"name": "減速", "count": 1, "delay": 0},
        ],
    }
    defender_without_slow = {"type": "enemy", "special_buffs": []}

    result_hit = compute_damage_multipliers(attacker, defender_with_slow)
    assert round(float(result_hit["outgoing"]), 4) == 1.2
    assert round(float(result_hit["final"]), 4) == 1.2

    result_miss = compute_damage_multipliers(attacker, defender_without_slow)
    assert round(float(result_miss["outgoing"]), 4) == 1.0
    assert round(float(result_miss["final"]), 4) == 1.0
