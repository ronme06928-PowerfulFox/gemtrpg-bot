from manager.battle import core as battle_core
from manager.battle import duel_solver as duel_solver_mod
from manager.battle import runtime_actions
from manager.utils import apply_buff


def _build_char(char_id, team):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": 100,
        "maxHp": 100,
        "mp": 20,
        "maxMp": 20,
        "params": [
            {"label": "物理補正", "value": 0},
            {"label": "魔法補正", "value": 0},
        ],
        "states": [
            {"name": "FP", "value": 10},
            {"name": "MP", "value": 20},
            {"name": "出血", "value": 0},
            {"name": "破裂", "value": 0},
        ],
        "special_buffs": [],
        "SPassive": [],
        "flags": {},
    }


def test_clash_preview_breakdown_reflects_pre_match_consume_bonus(monkeypatch):
    attacker = _build_char("A1", "ally")
    defender = _build_char("B1", "enemy")
    apply_buff(attacker, "凝魔", -1, 0, data={"buff_id": "Bu-Gyoma"}, count=4)
    state = {"timeline": [], "characters": [attacker, defender]}

    attacker_skill = {
        "id": "T-MB13",
        "スキルID": "T-MB13",
        "分類": "魔法",
        "属性": "打撃",
        "基礎威力": "5",
        "ダイス威力": "1d1",
        "チャットパレット": "5+1d1 【T-MB13 テスト】",
        "tags": ["攻撃"],
        "rule_data": {
            "effects": [
                {
                    "timing": "PRE_MATCH",
                    "type": "CONSUME_BUFF_COUNT_FOR_POWER",
                    "target": "self",
                    "buff_name": "凝魔",
                    "consume_max": 5,
                    "value_per_stack": 1,
                    "apply_to": "final",
                    "min_consume": 1,
                }
            ]
        },
    }
    defender_skill = {
        "id": "T-DEF",
        "スキルID": "T-DEF",
        "分類": "物理",
        "属性": "打撃",
        "基礎威力": "1",
        "ダイス威力": "1d1",
        "チャットパレット": "1+1d1 【T-DEF テスト】",
        "tags": ["攻撃"],
        "rule_data": {"effects": []},
    }

    def _fake_execute_duel_match(room, exec_data, _username):
        res_a = duel_solver_mod.roll_dice(exec_data.get("commandA", "0"))
        res_d = duel_solver_mod.roll_dice(exec_data.get("commandD", "0"))
        duel_solver_mod.broadcast_log(
            room,
            (
                f"<div class='dice-result-total'>{int(res_a.get('total', 0))}</div>"
                f"<div class='dice-result-total'>{int(res_d.get('total', 0))}</div>"
            ),
            "match",
        )

    monkeypatch.setattr(duel_solver_mod, "execute_duel_match", _fake_execute_duel_match)

    result = battle_core._resolve_clash_by_existing_logic(
        room="room_t",
        state=state,
        attacker_char=attacker,
        defender_char=defender,
        attacker_skill_data=attacker_skill,
        defender_skill_data=defender_skill,
    )

    assert result.get("ok") is True
    rolls = (result.get("summary") or {}).get("rolls", {})
    pb_a = rolls.get("power_breakdown_a", {}) if isinstance(rolls.get("power_breakdown_a"), dict) else {}
    snap_a = rolls.get("power_snapshot_a", {}) if isinstance(rolls.get("power_snapshot_a"), dict) else {}

    assert int(pb_a.get("final_power_mod", 0)) == 4
    assert int(pb_a.get("total_flat_bonus", 0)) == 4
    assert int(snap_a.get("flat_power_bonus", 0)) == 4


def test_execute_pre_match_effects_skips_when_select_resolve_delegate(monkeypatch):
    actor = _build_char("A1", "ally")
    target = _build_char("B1", "enemy")
    state = {"__select_resolve_delegate__": True, "characters": [actor, target], "timeline": []}
    called = {"count": 0}

    skill_data = {
        "id": "T-PRE",
        "rule_data": {
            "effects": [
                {"timing": "PRE_MATCH", "type": "MODIFY_FINAL_POWER", "target": "self", "value": 3}
            ]
        },
    }

    def _stub_process_skill_effects(*_args, **_kwargs):
        called["count"] += 1
        return 0, [], [(actor, "MODIFY_FINAL_POWER", None, 3)]

    monkeypatch.setattr(runtime_actions, "get_room_state", lambda _room: state)
    monkeypatch.setattr(runtime_actions, "process_skill_effects", _stub_process_skill_effects)

    runtime_actions.execute_pre_match_effects("room_t", actor, target, skill_data, target_skill_data=None)

    assert called["count"] == 0
    assert int(actor.get("_final_power_bonus", 0) or 0) == 0
