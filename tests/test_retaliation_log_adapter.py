from manager.battle.resolve_legacy_log_adapter import to_legacy_duel_log_input
from manager.battle.resolve_snapshot_utils import _extract_step_aux_log_lines


def test_legacy_adapter_keeps_retaliation_line_from_delegate_legacy_logs():
    line = "[\u88ab\u5f3e\u53cd\u5fdc] \u9632\u5fa1\u8005\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067\u653b\u6483\u8005\u306b\u51fa\u88402\u3092\u4ed8\u4e0e\u3002"
    state = {
        "battle_state": {
            "slots": {
                "a": {"actor_id": "A"},
                "d": {"actor_id": "D"},
            }
        },
        "characters": [
            {"id": "A", "name": "\u653b\u6483\u8005", "hp": 20},
            {"id": "D", "name": "\u9632\u5fa1\u8005", "hp": 12},
        ],
    }
    payload = {
        "skill_id": "S-01",
        "delegate_summary": {
            "rolls": {"power_a": 12, "power_b": 7, "command": "2d6", "command_b": "1d6"},
            "legacy_log_lines": [line],
        },
    }

    legacy = to_legacy_duel_log_input(
        payload,
        state,
        intents={},
        attacker_slot="a",
        defender_slot="d",
        applied={"damage": [], "statuses": [], "cost": {}},
        kind="clash",
        outcome="attacker_win",
    )

    assert line in legacy["extra_lines"]


def test_legacy_adapter_dedupes_retaliation_line_from_legacy_and_logs():
    line = "[\u88ab\u5f3e\u53cd\u5fdc] \u9632\u5fa1\u8005\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067\u653b\u6483\u8005\u306b2\u30c0\u30e1\u30fc\u30b8\u3002"
    state = {
        "battle_state": {
            "slots": {
                "a": {"actor_id": "A"},
                "d": {"actor_id": "D"},
            }
        },
        "characters": [
            {"id": "A", "name": "\u653b\u6483\u8005", "hp": 18},
            {"id": "D", "name": "\u9632\u5fa1\u8005", "hp": 12},
        ],
    }
    payload = {
        "skill_id": "S-01",
        "delegate_summary": {
            "rolls": {"power_a": 12, "power_b": 7, "command": "2d6", "command_b": "1d6"},
            "legacy_log_lines": [line],
            "logs": [line],
        },
    }

    legacy = to_legacy_duel_log_input(
        payload,
        state,
        intents={},
        attacker_slot="a",
        defender_slot="d",
        applied={"damage": [], "statuses": [], "cost": {}},
        kind="clash",
        outcome="attacker_win",
    )

    assert legacy["extra_lines"].count(line) == 1


def test_extract_step_aux_log_lines_keeps_retaliation_lines():
    trace_entry = {
        "lines": [
            "<strong>\u653b\u6483\u8005</strong> [S-01] (<span class='dice-result-total'>9</span>) vs <strong>\u9632\u5fa1\u8005</strong> - (<span class='dice-result-total'>-</span>) | <strong>\u653b\u6483\u5074\u52dd\u5229</strong>",
            "[\u88ab\u5f3e\u53cd\u5fdc] \u9632\u5fa1\u8005\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067\u653b\u6483\u8005\u306b\u51fa\u88402\u3092\u4ed8\u4e0e\u3002",
            "[\u7d50\u679c] \u653b\u6483\u8005 \u51fa\u8840: 0 -> 2",
        ]
    }

    lines = _extract_step_aux_log_lines(trace_entry)

    assert "[\u88ab\u5f3e\u53cd\u5fdc] \u9632\u5fa1\u8005\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067\u653b\u6483\u8005\u306b\u51fa\u88402\u3092\u4ed8\u4e0e\u3002" in lines
