import json
from types import SimpleNamespace

from manager.battle import core as battle_core


def _make_char(char_id, team):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": 100,
        "maxHp": 100,
        "mp": 50,
        "maxMp": 50,
        "params": [],
        "states": [
            {"name": "FP", "value": 0},
            {"name": "亀裂", "value": 0},
            {"name": "荊棘", "value": 0},
            {"name": "荊棘重絡", "value": 0},
        ],
        "special_buffs": [],
        "flags": {},
    }


def _state_value(char, name):
    row = next((s for s in char.get("states", []) if s.get("name") == name), None)
    return int((row or {}).get("value", 0) or 0)


def _patch_deterministic_one_sided(monkeypatch, roll_total=10):
    monkeypatch.setattr(battle_core, "socketio", SimpleNamespace(emit=lambda *_args, **_kwargs: None))
    monkeypatch.setattr(
        battle_core,
        "calculate_skill_preview",
        lambda *_args, **_kwargs: {
            "final_command": str(roll_total),
            "min_damage": roll_total,
            "max_damage": roll_total,
            "power_breakdown": {},
        },
    )
    monkeypatch.setattr(
        battle_core,
        "roll_dice",
        lambda _cmd: {"total": roll_total, "details": str(roll_total), "breakdown": {}},
    )
    monkeypatch.setattr(
        battle_core,
        "compute_damage_multipliers",
        lambda *_args, **_kwargs: {
            "final": 1.0,
            "incoming": 1.0,
            "outgoing": 1.0,
            "incoming_logs": [],
            "outgoing_logs": [],
        },
    )
    monkeypatch.setattr(battle_core, "process_on_hit_buffs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(battle_core, "process_on_damage_buffs", lambda *_args, **_kwargs: 0)

    def _stub_update_char_stat(_room, char, name, value, **_kwargs):
        if name == "HP":
            char["hp"] = int(value)
            return
        if name == "MP":
            char["mp"] = int(value)
            return
        states = char.setdefault("states", [])
        hit = next((s for s in states if s.get("name") == name), None)
        if hit is None:
            states.append({"name": name, "value": int(value)})
        else:
            hit["value"] = int(value)

    monkeypatch.setattr(battle_core, "_update_char_stat", _stub_update_char_stat)


def _resolve_one_sided(attacker, defender, skill):
    return battle_core._resolve_one_sided_by_existing_logic(
        room="room_t",
        state={"characters": [attacker, defender], "timeline": []},
        attacker_char=attacker,
        defender_char=defender,
        attacker_skill_data=skill,
        defender_skill_data=None,
    )


def _patch_deterministic_clash(monkeypatch, attacker_total=10, defender_total=5):
    from manager.battle import duel_solver as duel_solver_mod

    monkeypatch.setattr(battle_core, "socketio", SimpleNamespace(emit=lambda *_args, **_kwargs: None))

    def _preview(actor, *_args, **_kwargs):
        total = attacker_total if actor.get("id") == "A1" else defender_total
        return {
            "final_command": str(total),
            "min_damage": total,
            "max_damage": total,
            "power_breakdown": {},
        }

    monkeypatch.setattr(battle_core, "calculate_skill_preview", _preview)
    monkeypatch.setattr(
        duel_solver_mod,
        "compute_damage_multipliers",
        lambda *_args, **_kwargs: {
            "final": 1.0,
            "incoming": 1.0,
            "outgoing": 1.0,
            "incoming_logs": [],
            "outgoing_logs": [],
        },
    )
    monkeypatch.setattr(duel_solver_mod, "process_on_hit_buffs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(duel_solver_mod, "process_on_damage_buffs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(duel_solver_mod, "socketio", SimpleNamespace(emit=lambda *_args, **_kwargs: None))

    def _stub_update_char_stat(_room, char, name, value, **_kwargs):
        if name == "HP":
            char["hp"] = int(value)
            return
        if name == "MP":
            char["mp"] = int(value)
            return
        states = char.setdefault("states", [])
        hit = next((s for s in states if s.get("name") == name), None)
        if hit is None:
            states.append({"name": name, "value": int(value)})
        else:
            hit["value"] = int(value)

    monkeypatch.setattr(duel_solver_mod, "_update_char_stat", _stub_update_char_stat)
    monkeypatch.setattr(battle_core, "_update_char_stat", _stub_update_char_stat)
    return duel_solver_mod


def _clash_skill(skill_id, effects):
    rule = {"effects": effects}
    return {
        "id": skill_id,
        "スキルID": skill_id,
        "category": "物理",
        "分類": "物理",
        "tags": ["攻撃"],
        "rule_data": rule,
        "rule_data_json": rule,
        "特記処理": json.dumps(rule, ensure_ascii=False),
    }


def _resolve_clash(monkeypatch, attacker, defender, attacker_skill, defender_skill=None):
    duel_solver_mod = _patch_deterministic_clash(monkeypatch)
    defender_skill = defender_skill or _clash_skill("DEF", [])
    state = {"characters": [attacker, defender], "timeline": []}
    catalog = {
        attacker_skill["id"]: attacker_skill,
        defender_skill["id"]: defender_skill,
    }
    monkeypatch.setattr(duel_solver_mod, "all_skill_data", catalog)
    monkeypatch.setattr(duel_solver_mod, "get_room_state", lambda _room: state)
    return battle_core._resolve_clash_by_existing_logic(
        room="room_t",
        state=state,
        attacker_char=attacker,
        defender_char=defender,
        attacker_skill_data=attacker_skill,
        defender_skill_data=defender_skill,
    )


def test_one_sided_end_match_fissure_contributes_before_hit_fissure(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    _patch_deterministic_one_sided(monkeypatch, roll_total=10)

    skill = {
        "category": "物理",
        "rule_data": {
            "effects": [
                {"timing": "END_MATCH", "type": "APPLY_STATE", "target": "target", "state_name": "亀裂", "value": 3},
                {"timing": "HIT", "type": "APPLY_STATE", "target": "target", "state_name": "亀裂", "value": 5},
            ]
        },
    }

    result = _resolve_one_sided(attacker, defender, skill)

    assert result["ok"] is True
    assert result["summary"]["rolls"]["kiretsu"] == 3
    assert result["summary"]["rolls"]["final_damage"] == 13
    assert defender["hp"] == 87
    assert _state_value(defender, "亀裂") == 8


def test_one_sided_win_fissure_contributes_to_same_damage(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    _patch_deterministic_one_sided(monkeypatch, roll_total=10)

    skill = {
        "category": "物理",
        "rule_data": {
            "effects": [
                {"timing": "WIN", "type": "APPLY_STATE", "target": "target", "state_name": "亀裂", "value": 4},
            ]
        },
    }

    result = _resolve_one_sided(attacker, defender, skill)

    assert result["ok"] is True
    assert result["summary"]["rolls"]["kiretsu"] == 4
    assert result["summary"]["rolls"]["final_damage"] == 14
    assert defender["hp"] == 86


def test_one_sided_hit_entangle_does_not_protect_current_thorns(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    attacker["states"] = [
        {"name": "FP", "value": 0},
        {"name": "亀裂", "value": 0},
        {"name": "荊棘", "value": 4},
        {"name": "荊棘重絡", "value": 0},
    ]
    _patch_deterministic_one_sided(monkeypatch, roll_total=10)

    skill = {
        "category": "物理",
        "rule_data": {
            "effects": [
                {"timing": "HIT", "type": "APPLY_STATE", "target": "self", "state_name": "荊棘重絡", "value": 1},
            ]
        },
    }

    result = _resolve_one_sided(attacker, defender, skill)

    assert result["ok"] is True
    assert attacker["hp"] == 96
    assert _state_value(attacker, "荊棘") == 0
    assert _state_value(attacker, "荊棘重絡") == 1


def test_one_sided_end_match_entangle_protects_current_thorns_decay(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    attacker["states"] = [
        {"name": "FP", "value": 0},
        {"name": "亀裂", "value": 0},
        {"name": "荊棘", "value": 4},
        {"name": "荊棘重絡", "value": 0},
    ]
    _patch_deterministic_one_sided(monkeypatch, roll_total=10)

    skill = {
        "category": "物理",
        "rule_data": {
            "effects": [
                {"timing": "END_MATCH", "type": "APPLY_STATE", "target": "self", "state_name": "荊棘重絡", "value": 1},
            ]
        },
    }

    result = _resolve_one_sided(attacker, defender, skill)

    assert result["ok"] is True
    assert attacker["hp"] == 96
    assert _state_value(attacker, "荊棘") == 4
    assert _state_value(attacker, "荊棘重絡") == 0


def test_clash_end_match_fissure_contributes_before_hit_fissure(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    skill = _clash_skill(
        "ATK",
        [
            {"timing": "END_MATCH", "type": "APPLY_STATE", "target": "target", "state_name": "亀裂", "value": 3},
            {"timing": "HIT", "type": "APPLY_STATE", "target": "target", "state_name": "亀裂", "value": 5},
        ],
    )

    result = _resolve_clash(monkeypatch, attacker, defender, skill)

    assert result["ok"] is True
    assert defender["hp"] == 87
    assert _state_value(defender, "亀裂") == 8


def test_clash_win_fissure_contributes_to_same_damage(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    skill = _clash_skill(
        "ATK",
        [
            {"timing": "WIN", "type": "APPLY_STATE", "target": "target", "state_name": "亀裂", "value": 4},
        ],
    )

    result = _resolve_clash(monkeypatch, attacker, defender, skill)

    assert result["ok"] is True
    assert defender["hp"] == 86
    assert _state_value(defender, "亀裂") == 4


def test_clash_defender_win_result_timing_order_is_end_match_win_lose(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    attacker_skill = _clash_skill("ATK", [])
    defender_skill = _clash_skill("DEF", [])
    duel_solver_mod = _patch_deterministic_clash(monkeypatch, attacker_total=5, defender_total=10)
    state = {"characters": [attacker, defender], "timeline": []}
    monkeypatch.setattr(duel_solver_mod, "all_skill_data", {"ATK": attacker_skill, "DEF": defender_skill})
    monkeypatch.setattr(duel_solver_mod, "get_room_state", lambda _room: state)

    seen = []

    def _record_process_skill_effects(effects_array, timing_to_check, actor, target, target_skill_data=None, context=None, base_damage=0):
        timing = str(timing_to_check)
        if timing in {"END_MATCH", "WIN", "LOSE"}:
            seen.append((timing, actor.get("id")))
        return 0, [], []

    monkeypatch.setattr(duel_solver_mod, "process_skill_effects", _record_process_skill_effects)

    result = battle_core._resolve_clash_by_existing_logic(
        room="room_t",
        state=state,
        attacker_char=attacker,
        defender_char=defender,
        attacker_skill_data=attacker_skill,
        defender_skill_data=defender_skill,
    )

    assert result["ok"] is True
    assert seen[:4] == [
        ("END_MATCH", "A1"),
        ("END_MATCH", "B1"),
        ("WIN", "B1"),
        ("LOSE", "A1"),
    ]


def test_clash_draw_end_match_runs_before_thorns_without_win_lose(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    attacker["states"] = [
        {"name": "FP", "value": 0},
        {"name": "亀裂", "value": 0},
        {"name": "荊棘", "value": 4},
        {"name": "荊棘重絡", "value": 0},
    ]
    attacker_skill = _clash_skill(
        "ATK",
        [
            {"timing": "END_MATCH", "type": "APPLY_STATE", "target": "self", "state_name": "荊棘重絡", "value": 1},
            {"timing": "WIN", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 99},
            {"timing": "LOSE", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 99},
        ],
    )
    defender_skill = _clash_skill("DEF", [])
    duel_solver_mod = _patch_deterministic_clash(monkeypatch, attacker_total=10, defender_total=10)
    state = {"characters": [attacker, defender], "timeline": []}
    monkeypatch.setattr(duel_solver_mod, "all_skill_data", {"ATK": attacker_skill, "DEF": defender_skill})
    monkeypatch.setattr(duel_solver_mod, "get_room_state", lambda _room: state)

    result = battle_core._resolve_clash_by_existing_logic(
        room="room_t",
        state=state,
        attacker_char=attacker,
        defender_char=defender,
        attacker_skill_data=attacker_skill,
        defender_skill_data=defender_skill,
    )

    assert result["ok"] is True
    assert result["outcome"] == "draw"
    assert attacker["hp"] == 96
    assert _state_value(attacker, "荊棘") == 4
    assert _state_value(attacker, "荊棘重絡") == 0
    assert _state_value(attacker, "FP") == 0


def test_clash_hit_entangle_does_not_protect_current_thorns(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    attacker["states"] = [
        {"name": "FP", "value": 0},
        {"name": "亀裂", "value": 0},
        {"name": "荊棘", "value": 4},
        {"name": "荊棘重絡", "value": 0},
    ]
    skill = _clash_skill(
        "ATK",
        [
            {"timing": "HIT", "type": "APPLY_STATE", "target": "self", "state_name": "荊棘重絡", "value": 1},
        ],
    )

    result = _resolve_clash(monkeypatch, attacker, defender, skill)

    assert result["ok"] is True
    assert attacker["hp"] == 96
    assert _state_value(attacker, "荊棘") == 0
    assert _state_value(attacker, "荊棘重絡") == 1


def test_clash_end_match_entangle_protects_current_thorns_decay(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    attacker["states"] = [
        {"name": "FP", "value": 0},
        {"name": "亀裂", "value": 0},
        {"name": "荊棘", "value": 4},
        {"name": "荊棘重絡", "value": 0},
    ]
    skill = _clash_skill(
        "ATK",
        [
            {"timing": "END_MATCH", "type": "APPLY_STATE", "target": "self", "state_name": "荊棘重絡", "value": 1},
        ],
    )

    result = _resolve_clash(monkeypatch, attacker, defender, skill)

    assert result["ok"] is True
    assert attacker["hp"] == 96
    assert _state_value(attacker, "荊棘") == 4
    assert _state_value(attacker, "荊棘重絡") == 0


def test_clash_after_damage_apply_receives_actual_damage(monkeypatch):
    attacker = _make_char("A1", "ally")
    defender = _make_char("B1", "enemy")
    skill = _clash_skill(
        "ATK",
        [
            {"timing": "AFTER_DAMAGE_APPLY", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1},
        ],
    )
    defender_skill = _clash_skill(
        "DEF",
        [
            {"timing": "AFTER_DAMAGE_APPLY", "type": "APPLY_STATE", "target": "self", "state_name": "FP", "value": 1},
        ],
    )
    seen = []

    def _record_process_skill_effects(effects_array, timing_to_check, actor, target, target_skill_data=None, context=None, base_damage=0):
        if str(timing_to_check) == "AFTER_DAMAGE_APPLY":
            seen.append((actor.get("id"), int(base_damage or 0)))
        return 0, [], []

    monkeypatch.setattr(battle_core, "process_skill_effects", _record_process_skill_effects)

    result = _resolve_clash(monkeypatch, attacker, defender, skill, defender_skill=defender_skill)

    assert result["ok"] is True
    assert defender["hp"] == 90
    assert ("A1", 10) in seen
    assert ("B1", 0) in seen
