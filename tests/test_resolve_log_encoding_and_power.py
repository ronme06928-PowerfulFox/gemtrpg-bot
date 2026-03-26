from manager.battle.duel_log_utils import (
    _extract_damage_parts_from_legacy_lines,
    format_duel_result_lines,
)
from manager.battle.resolve_legacy_log_adapter import to_legacy_duel_log_input
from manager.battle.resolve_snapshot_utils import _extract_power_pair_from_match_log


def test_extract_power_pair_from_match_log_parses_positive_totals():
    match_log = (
        "<strong>A</strong> [S] (<span class='dice-result-total'>15</span>) vs "
        "<strong>D</strong> [T] (<span class='dice-result-total'>9</span>) | <strong>A の勝利</strong>"
    )
    assert _extract_power_pair_from_match_log(match_log) == (15, 9)


def test_extract_damage_parts_accepts_positive_breakdown_values():
    line = (
        "<strong>D</strong> に <strong>11</strong> ダメージ"
        "<br><span style='font-size:0.9em; color:#888;'>内訳: [ダイス 5] + [効果ダメージ 6]</span>"
    )
    out = _extract_damage_parts_from_legacy_lines([line], attacker_name="A", defender_name="D")
    assert out["D"] == [{"source": "ダイス", "value": 5}, {"source": "効果ダメージ", "value": 6}]


def test_format_duel_result_lines_emits_clean_damage_labels():
    lines = format_duel_result_lines(
        "A",
        "[S-01] テスト",
        10,
        "D",
        "[S-02] テスト",
        8,
        "<strong>A の勝利</strong>",
        damage_report={"D": [{"source": "ダイスダメージ", "value": 10}]},
        extra_lines=[],
    )
    assert any("内訳: [ダイス 10]" in line for line in lines)
    # Regression guard: historically mojibake labels leaked to output.
    assert all("繧" not in line for line in lines)


def test_legacy_adapter_normalizes_damage_sources_and_uses_numeric_power():
    state = {
        "battle_state": {
            "slots": {
                "a": {"actor_id": "A"},
                "d": {"actor_id": "D"},
            }
        },
        "characters": [
            {"id": "A", "name": "味方A", "hp": 20},
            {"id": "D", "name": "敵D", "hp": 9},
        ],
    }
    intents = {
        "a": {"skill_id": "S-01"},
        "d": {"skill_id": "S-02"},
    }
    payload = {
        "skill_id": "S-01",
        "delegate_summary": {
            "rolls": {
                "power_snapshot_a": {"final_power": 12},
                "power_snapshot_b": {"final_power": 7},
                "command": "2d6",
                "command_b": "1d6",
            },
            "legacy_log_lines": [],
        },
    }
    applied = {
        "damage": [
            {"target_id": "D", "hp": 12, "source": "on_damage"},
        ],
        "statuses": [],
        "cost": {},
    }

    legacy = to_legacy_duel_log_input(
        payload,
        state,
        intents,
        "a",
        "d",
        applied=applied,
        kind="clash",
        outcome="attacker_win",
    )
    assert legacy["total_a"] == 12
    assert legacy["total_d"] == 7
    assert legacy["damage_report"]["D"][0]["source"] == "効果ダメージ"
