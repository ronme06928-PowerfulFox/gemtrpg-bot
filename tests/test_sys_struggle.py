from manager.battle.skill_access import list_usable_skill_ids
from manager.battle.system_skills import (
    SYS_STRUGGLE_ID,
    queue_selected_power_recovery_from_snapshot,
    pop_pending_selected_power_recoveries,
)
from manager.game_logic import calculate_skill_preview
from events.battle.common_routes import _normalize_target_by_skill_compat


def _char(commands="", fp=0, mp=0, physical=0, magical=0):
    return {
        "id": "C-1",
        "name": "Tester",
        "commands": commands,
        "hp": 10,
        "mp": mp,
        "states": [
            {"name": "FP", "value": fp},
            {"name": "物理補正", "value": physical},
            {"name": "魔法補正", "value": magical},
        ],
    }


def test_sys_struggle_fallback_only_when_no_regular_skill():
    actor = _char(commands="")
    assert list_usable_skill_ids(actor) == [SYS_STRUGGLE_ID]


def test_sys_struggle_preview_uses_higher_power_stat_and_physical_tiebreak():
    actor = _char(physical=4, magical=7)
    skill_data = {
        "id": SYS_STRUGGLE_ID,
        "基礎威力": 0,
        "ダイス威力": "0",
        "power_stat_choice": {
            "mode": "max",
            "params": ["物理補正", "魔法補正"],
            "tie_breaker": "物理補正",
            "apply_as": "final_power",
        },
    }
    preview = calculate_skill_preview(actor, None, skill_data, rule_data={})
    assert preview["final_command"] == "0+7"
    assert preview["power_breakdown"]["selected_power_param"] == "魔法補正"
    assert preview["power_breakdown"]["selected_power_value"] == 7

    tie_actor = _char(physical=5, magical=5)
    tie_preview = calculate_skill_preview(tie_actor, None, skill_data, rule_data={})
    assert tie_preview["power_breakdown"]["selected_power_param"] == "物理補正"
    assert tie_preview["power_breakdown"]["selected_power_value"] == 5


def test_sys_struggle_self_target_normalization():
    target, error = _normalize_target_by_skill_compat(
        SYS_STRUGGLE_ID,
        {"type": "none", "slot_id": None},
        state={"slots": {"S-1": {"actor_id": "C-1"}}},
        source_slot_id="S-1",
        allow_none=False,
    )
    assert error is None
    assert target == {"type": "single_slot", "slot_id": "S-1"}


def test_selected_power_recovery_queue_uses_fp_or_mp():
    actor = _char()
    assert queue_selected_power_recovery_from_snapshot(actor, {"selected_power_param": "物理補正"})
    assert queue_selected_power_recovery_from_snapshot(actor, {"selected_power_param": "魔法補正"})
    assert pop_pending_selected_power_recoveries(actor) == ["FP", "MP"]
