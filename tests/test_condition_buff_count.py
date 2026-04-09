from manager.game_logic import check_condition


CHIKURYOKU_NAME = "\u84c4\u529b"


def _build_actor_with_buffs(buffs):
    return {
        "id": "A1",
        "name": "Tester",
        "type": "ally",
        "hp": 100,
        "params": [],
        "states": [],
        "special_buffs": buffs,
    }


def test_check_condition_supports_suffix_buff_count_param():
    actor = _build_actor_with_buffs(
        [
            {"name": CHIKURYOKU_NAME, "count": 4, "delay": 0},
        ]
    )

    cond_ok = {"source": "self", "param": "\u84c4\u529b_count", "operator": "GTE", "value": 4}
    cond_ng = {"source": "self", "param": "\u84c4\u529b_count", "operator": "GT", "value": 4}

    assert check_condition(cond_ok, actor, None) is True
    assert check_condition(cond_ng, actor, None) is False


def test_check_condition_supports_prefix_buff_count_param_and_ignores_delay():
    actor = _build_actor_with_buffs(
        [
            {"name": CHIKURYOKU_NAME, "count": 9, "delay": 1},
            {"name": CHIKURYOKU_NAME, "count": 3, "delay": 0},
        ]
    )

    cond = {"source": "self", "param": "buff_count:\u84c4\u529b", "operator": "EQUALS", "value": 3}
    assert check_condition(cond, actor, None) is True


def test_check_condition_buff_count_uses_one_when_count_is_missing():
    actor = _build_actor_with_buffs(
        [
            {"name": CHIKURYOKU_NAME, "delay": 0},
            {"name": CHIKURYOKU_NAME, "count": 2, "delay": 0},
        ]
    )

    cond = {"source": "self", "param": "\u84c4\u529b_count", "operator": "EQUALS", "value": 3}
    assert check_condition(cond, actor, None) is True
