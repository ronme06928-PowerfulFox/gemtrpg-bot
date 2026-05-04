from manager.game_logic import check_condition


def _make_char(states):
    return {"id": "T1", "type": "enemy", "states": states}


def test_condition_status_stack_sum_default_five_states():
    actor = {"id": "A1", "type": "ally", "states": []}
    target = _make_char(
        [
            {"name": "出血", "value": 2},
            {"name": "破裂", "value": 3},
            {"name": "亀裂", "value": 4},
            {"name": "戦慄", "value": 1},
            {"name": "荊棘", "value": 5},
            {"name": "毒", "value": 99},
        ]
    )

    cond = {
        "source": "target",
        "param": "状態異常スタック合計:出血,破裂,亀裂,戦慄,荊棘",
        "operator": "EQUALS",
        "value": 15,
    }
    assert check_condition(cond, actor, target) is True


def test_condition_status_stack_sum_subset_with_comma():
    actor = {"id": "A1", "type": "ally", "states": []}
    target = _make_char(
        [
            {"name": "出血", "value": 2},
            {"name": "破裂", "value": 3},
            {"name": "亀裂", "value": 4},
            {"name": "戦慄", "value": 1},
            {"name": "荊棘", "value": 5},
        ]
    )

    cond = {"source": "target", "param": "状態異常スタック合計:出血,破裂", "operator": "EQUALS", "value": 5}
    assert check_condition(cond, actor, target) is True


def test_condition_status_stack_sum_subset_with_japanese_comma():
    actor = {"id": "A1", "type": "ally", "states": []}
    target = _make_char(
        [
            {"name": "出血", "value": 2},
            {"name": "破裂", "value": 3},
            {"name": "亀裂", "value": 4},
            {"name": "戦慄", "value": 1},
            {"name": "荊棘", "value": 5},
        ]
    )

    cond = {
        "source": "target",
        "param": "状態異常スタック合計:出血、亀裂、戦慄",
        "operator": "EQUALS",
        "value": 7,
    }
    assert check_condition(cond, actor, target) is True


def test_condition_status_stack_sum_requires_explicit_state_list():
    actor = {"id": "A1", "type": "ally", "states": []}
    target = _make_char(
        [
            {"name": "出血", "value": 2},
            {"name": "破裂", "value": 3},
            {"name": "亀裂", "value": 4},
            {"name": "戦慄", "value": 1},
            {"name": "荊棘", "value": 5},
        ]
    )

    cond = {"source": "target", "param": "状態異常スタック合計", "operator": "GTE", "value": 1}
    assert check_condition(cond, actor, target) is False
