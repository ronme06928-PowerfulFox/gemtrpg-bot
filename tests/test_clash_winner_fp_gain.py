from manager.battle import core as battle_core


def _char_with_fp(char_id, fp):
    return {
        "id": char_id,
        "name": char_id,
        "hp": 100,
        "mp": 10,
        "states": [{"name": "FP", "value": int(fp)}],
    }


def test_no_duplicate_when_summary_already_has_match_win_like_fp_and_skill_is_end_round_only():
    winner = _char_with_fp("W1", 8)
    summary = {
        "statuses": [
            {"target_id": "W1", "name": "FP", "before": 6, "after": 7, "delta": 1},
        ]
    }
    winner_skill = {
        "rule_data": {
            "effects": [
                {"timing": "END_ROUND", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 2}
            ]
        }
    }

    row = battle_core._ensure_clash_winner_fp_gain("room_t", winner, summary, winner_skill_data=winner_skill)
    assert row is None
    assert int(battle_core.get_status_value(winner, "FP")) == 8


def test_no_duplicate_when_direct_fp_gain_plus_match_win_already_observed():
    winner = _char_with_fp("W2", 9)
    summary = {
        "statuses": [
            {"target_id": "W2", "name": "FP", "before": 7, "after": 9, "delta": 2},
        ]
    }
    winner_skill = {
        "rule_data": {
            "effects": [
                {"timing": "WIN", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1}
            ]
        }
    }

    row = battle_core._ensure_clash_winner_fp_gain("room_t", winner, summary, winner_skill_data=winner_skill)
    assert row is None
    assert int(battle_core.get_status_value(winner, "FP")) == 9


def test_add_match_win_when_only_direct_fp_gain_is_observed():
    winner = _char_with_fp("W3", 10)
    summary = {
        "statuses": [
            {"target_id": "W3", "name": "FP", "before": 9, "after": 10, "delta": 1},
        ]
    }
    winner_skill = {
        "rule_data": {
            "effects": [
                {"timing": "WIN", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1}
            ]
        }
    }

    row = battle_core._ensure_clash_winner_fp_gain("room_t", winner, summary, winner_skill_data=winner_skill)
    assert isinstance(row, dict)
    assert row.get("source") == "match_win_fp"
    assert int(battle_core.get_status_value(winner, "FP")) == 11

