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
