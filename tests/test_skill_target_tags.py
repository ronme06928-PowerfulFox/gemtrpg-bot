from events.battle import common_routes
from types import SimpleNamespace

from manager.battle import core as battle_core
from manager.battle import duel_solver


def _state_for_scope_check():
    return {
        "slots": {
            "S_ALLY": {"slot_id": "S_ALLY", "actor_id": "A1", "team": "ally"},
            "S_ENEMY": {"slot_id": "S_ENEMY", "actor_id": "E1", "team": "enemy"},
        },
        "characters": [
            {"id": "A1", "type": "ally"},
            {"id": "E1", "type": "enemy"},
        ],
    }


def test_skill_deals_damage_false_by_tag():
    skill = {"tags": ["攻撃", "非ダメージ"]}
    assert battle_core._skill_deals_damage(skill) is False


def test_skill_deals_damage_false_by_rule_tag():
    skill = {"rule_data": {"tags": ["no_damage"]}}
    assert battle_core._skill_deals_damage(skill) is False


def test_target_scope_blocks_ally_without_ally_tag(monkeypatch):
    monkeypatch.setattr(common_routes, "all_skill_data", {"S1": {"tags": ["攻撃"]}})
    state = _state_for_scope_check()
    target, err = common_routes._normalize_target_by_skill(
        "S1",
        {"type": "single_slot", "slot_id": "S_ENEMY"},
        state=state,
        source_slot_id="S_ENEMY",
        allow_none=False,
    )
    assert target is None
    assert "味方スロット" in str(err)


def test_target_scope_allows_ally_with_tag(monkeypatch):
    monkeypatch.setattr(common_routes, "all_skill_data", {"S1": {"tags": ["攻撃", "ally_target"]}})
    state = _state_for_scope_check()
    target, err = common_routes._normalize_target_by_skill(
        "S1",
        {"type": "single_slot", "slot_id": "S_ENEMY"},
        state=state,
        source_slot_id="S_ENEMY",
        allow_none=False,
    )
    assert err is None
    assert target == {"type": "single_slot", "slot_id": "S_ENEMY"}


def test_clash_win_fp_granted_for_defense_winning_against_attack():
    attacker = {"分類": "攻撃"}
    defender = {"分類": "防御"}
    assert battle_core._should_grant_clash_win_fp(attacker, defender, "defender_win") is True
    assert battle_core._should_grant_clash_win_fp(attacker, defender, "attacker_win") is False


def test_clash_win_fp_granted_for_evade_winning_against_attack():
    attacker = {"分類": "攻撃"}
    defender = {"分類": "回避"}
    assert battle_core._should_grant_clash_win_fp(attacker, defender, "defender_win") is True
    assert battle_core._should_grant_clash_win_fp(attacker, defender, "attacker_win") is False


def test_defense_loss_damage_uses_difference():
    damage, source = duel_solver._compute_match_damage_from_rolls(
        winner_total=10,
        loser_total=8,
        loser_skill_data={"tags": ["defense"]},
    )
    assert damage == 2
    assert source == "差分ダメージ"


def test_attack_loss_damage_remains_full_power():
    damage, source = duel_solver._compute_match_damage_from_rolls(
        winner_total=10,
        loser_total=8,
        loser_skill_data={"tags": ["attack"]},
    )
    assert damage == 10
    assert source == "ダイスダメージ"


def test_diff_snapshot_detects_fp_change_outside_states():
    diff = battle_core._diff_snapshot(
        {
            "id": "A1",
            "hp": 100,
            "mp": 50,
            "fp": 5,
            "states": {},
            "bad_states": {},
            "buffs": {},
            "flags": {},
        },
        {
            "id": "A1",
            "hp": 100,
            "mp": 50,
            "fp": 6,
            "states": {},
            "bad_states": {},
            "buffs": {},
            "flags": {},
        },
    )
    assert {"target_id": "A1", "name": "FP", "before": 5, "after": 6, "delta": 1} in diff["statuses"]


def test_summary_has_positive_fp_gain_handles_id_type_mismatch():
    summary = {
        "statuses": [
            {"target_id": "42", "name": "FP", "before": 1, "after": 2, "delta": 1}
        ]
    }
    assert battle_core._summary_has_positive_fp_gain(summary, 42) is True
    assert battle_core._summary_has_match_win_fp_gain(
        {"statuses": [{"target_id": "42", "name": "FP", "before": 1, "after": 2, "delta": 1, "source": "match_win_fp"}]},
        42,
    ) is True


def test_delegate_mode_does_not_reapply_coloration_bonus_to_command(monkeypatch):
    state = {
        "__select_resolve_delegate__": True,
        "timeline": [],
        "turn_entry_id": None,
        "characters": [
            {
                "id": "A1",
                "name": "Attacker",
                "type": "ally",
                "hp": 100,
                "maxHp": 100,
                "mp": 50,
                "maxMp": 50,
                "x": 0,
                "y": 0,
                "is_escaped": False,
                "states": [],
                "params": [{"label": "出身", "value": "0"}],
                "special_buffs": [],
            },
            {
                "id": "B1",
                "name": "Defender",
                "type": "enemy",
                "hp": 100,
                "maxHp": 100,
                "mp": 50,
                "maxMp": 50,
                "x": 1,
                "y": 0,
                "is_escaped": False,
                "states": [],
                "params": [{"label": "出身", "value": "0"}],
                "special_buffs": [{"name": "色彩", "lasting": 2}],
            },
        ],
    }
    monkeypatch.setattr(duel_solver, "get_room_state", lambda _room: state)
    monkeypatch.setattr(duel_solver, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(duel_solver, "broadcast_state_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(duel_solver, "save_specific_room_state", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(duel_solver, "proceed_next_turn", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(duel_solver, "socketio", SimpleNamespace(emit=lambda *_args, **_kwargs: None))

    def _stub_update_char_stat(_room, char, stat, value, **_kwargs):
        if str(stat).upper() == "HP":
            char["hp"] = int(value)
            return
        if str(stat).upper() == "MP":
            char["mp"] = int(value)
            return
        states = char.setdefault("states", [])
        hit = next((s for s in states if str(s.get("name", "")) == str(stat)), None)
        if hit is None:
            states.append({"name": str(stat), "value": int(value)})
        else:
            hit["value"] = int(value)

    monkeypatch.setattr(duel_solver, "_update_char_stat", _stub_update_char_stat)
    monkeypatch.setitem(duel_solver.all_skill_data, "ATK", {"category": "attack", "属性": "打撃", "tags": ["attack"]})
    monkeypatch.setitem(duel_solver.all_skill_data, "DEF", {"category": "attack", "属性": "打撃", "tags": ["attack"]})

    rolled_commands = []

    def _stub_roll(command):
        rolled_commands.append(str(command))
        return {"total": 10, "detail": "stub"}

    monkeypatch.setattr(duel_solver, "roll_dice", _stub_roll)

    duel_solver.execute_duel_match(
        "room_t",
        {
            "room": "room_t",
            "match_id": "m1",
            "actorIdA": "A1",
            "actorIdD": "B1",
            "actorNameA": "Attacker",
            "actorNameD": "Defender",
            "commandA": "10+1",
            "commandD": "8",
            "skillIdA": "ATK",
            "skillIdD": "DEF",
            "senritsuPenaltyA": 0,
            "senritsuPenaltyD": 0,
        },
        "[probe]",
    )

    assert len(rolled_commands) >= 2
    assert rolled_commands[0] == "10+1"


def test_to_legacy_duel_log_input_includes_hp_transition_from_damage():
    state = {
        "characters": [
            {"id": "A1", "name": "Attacker", "hp": 100},
            {"id": "B1", "name": "Defender", "hp": 91},
        ],
        "battle_state": {
            "slots": {
                "A_slot": {"slot_id": "A_slot", "actor_id": "A1"},
                "B_slot": {"slot_id": "B_slot", "actor_id": "B1"},
            }
        },
    }
    result = battle_core.to_legacy_duel_log_input(
        outcome_payload={"skill_id": "ATK", "delegate_summary": {"rolls": {"power_a": 9, "power_b": 5}}},
        state=state,
        intents={},
        attacker_slot="A_slot",
        defender_slot="B_slot",
        applied={
            "damage": [{"target_id": "B1", "hp": 9, "source": "ダイスダメージ"}],
            "statuses": [],
            "cost": {"hp": 0, "mp": 0, "fp": 0},
        },
        kind="clash",
        outcome="attacker_win",
    )
    extra_lines = result.get("extra_lines", [])
    assert any("Defender HP: 100 -> 91" in str(line) for line in extra_lines)


def test_to_legacy_duel_log_input_includes_buff_apply_line_from_delegate_legacy_logs():
    state = {
        "characters": [
            {"id": "A1", "name": "Attacker", "hp": 100},
            {"id": "B1", "name": "Defender", "hp": 100},
        ],
        "battle_state": {
            "slots": {
                "A_slot": {"slot_id": "A_slot", "actor_id": "A1"},
                "B_slot": {"slot_id": "B_slot", "actor_id": "B1"},
            }
        },
    }
    result = battle_core.to_legacy_duel_log_input(
        outcome_payload={
            "skill_id": "ATK",
            "delegate_summary": {
                "rolls": {"power_a": 8, "power_b": 6},
                "match_log": "<strong>Attacker</strong> ...",
                "legacy_log_lines": [
                    "<strong>Attacker</strong> ...",
                    "[色彩] が Defender に付与されました。",
                ],
            },
        },
        state=state,
        intents={},
        attacker_slot="A_slot",
        defender_slot="B_slot",
        applied={
            "damage": [],
            "statuses": [],
            "cost": {"hp": 0, "mp": 0, "fp": 0},
        },
        kind="clash",
        outcome="attacker_win",
    )
    extra_lines = [str(line) for line in (result.get("extra_lines", []) or [])]
    assert any("付与されました" in line for line in extra_lines)


def test_summary_logs_has_match_win_fp_gain_detects_legacy_fp_line():
    summary = {
        "legacy_log_lines": [
            "[マッチ勝利]: Attacker: FP (2) → (3)",
        ]
    }
    assert battle_core._summary_logs_has_match_win_fp_gain(summary, actor_name="Attacker") is True


def test_snapshot_for_outcome_prefers_state_fp_over_param_fp():
    actor = {
        "id": "A1",
        "hp": 100,
        "mp": 50,
        "states": [{"name": "FP", "value": 3}],
        "params": [{"label": "FP", "value": 1}],
        "special_buffs": [],
        "bad_states": [],
    }
    snap = battle_core._snapshot_for_outcome(actor)
    assert int(snap.get("fp", 0)) == 3


def test_handle_skill_declaration_passes_preview_context(monkeypatch):
    state = {
        "characters": [
            {"id": "A1", "name": "Attacker", "type": "ally", "hp": 100, "mp": 10, "states": [], "special_buffs": []},
            {"id": "B1", "name": "Defender", "type": "enemy", "hp": 100, "mp": 10, "states": [], "special_buffs": []},
        ],
        "timeline": [{"id": "t1", "char_id": "A1", "speed": 7, "acted": False}],
        "battle_state": {"slots": {"A_slot": {"actor_id": "A1", "initiative": 7}}},
    }
    emitted = []
    seen = {"context": None}

    monkeypatch.setattr(duel_solver, "get_room_state", lambda _room: state)
    monkeypatch.setattr(duel_solver, "socketio", SimpleNamespace(emit=lambda event, payload=None, to=None: emitted.append((event, payload, to))))
    monkeypatch.setitem(duel_solver.all_skill_data, "ATK", {"name": "Test"})

    import manager.game_logic as game_logic_mod

    def _stub_preview(actor_char, target_char, skill_data, **kwargs):
        seen["context"] = kwargs.get("context")
        return {
            "final_command": "1d6+1",
            "min_damage": 2,
            "max_damage": 7,
            "skill_details": {},
            "correction_details": [],
            "senritsu_dice_reduction": 0,
            "power_breakdown": {},
        }

    monkeypatch.setattr(game_logic_mod, "calculate_skill_preview", _stub_preview)

    duel_solver.handle_skill_declaration(
        "room_t",
        {
            "actor_id": "A1",
            "target_id": "B1",
            "skill_id": "ATK",
            "commit": False,
            "prefix": "declare_panel_A_slot",
        },
        "tester",
    )

    ctx = seen.get("context") or {}
    assert isinstance(ctx.get("characters"), list)
    assert isinstance(ctx.get("battle_state"), dict)
    assert any(ev == "skill_declaration_result" for ev, _payload, _to in emitted)


def test_apply_effect_changes_like_duel_records_buff_apply_and_remove_logs():
    attacker = {
        "id": "A1",
        "name": "Attacker",
        "type": "ally",
        "hp": 100,
        "mp": 20,
        "states": [],
        "special_buffs": [],
        "flags": {},
    }
    target = {
        "id": "B1",
        "name": "Defender",
        "type": "enemy",
        "hp": 100,
        "mp": 20,
        "states": [],
        "special_buffs": [],
        "flags": {},
    }
    log_snippets = []
    changes = [
        (
            target,
            "APPLY_BUFF",
            "色彩",
            {"lasting": 2, "delay": 0, "data": {"buff_id": "Bu-28"}},
        ),
        (
            target,
            "REMOVE_BUFF",
            "色彩",
            0,
        ),
    ]

    battle_core._apply_effect_changes_like_duel(
        room="room_t",
        state={"characters": [attacker, target]},
        changes=changes,
        attacker_char=attacker,
        defender_char=target,
        base_damage=0,
        log_snippets=log_snippets,
        reuse_requests=[],
    )

    assert any("付与されました" in str(line) for line in log_snippets)
    assert any("解除されました" in str(line) for line in log_snippets)


def test_emit_battle_trace_persists_lines_once_per_trace(monkeypatch):
    room_state = {"logs": []}
    monkeypatch.setattr(battle_core, "get_room_state", lambda _room: room_state)
    monkeypatch.setattr(battle_core, "socketio", SimpleNamespace(emit=lambda *_args, **_kwargs: None))
    monkeypatch.setattr(battle_core, "save_specific_room_state", lambda *_args, **_kwargs: True)

    battle_state = {
        "round": 2,
        "phase": "resolve_single",
        "resolve": {},
    }
    trace_entry = {
        "step": 1,
        "step_index": 0,
        "timestamp": 1234567,
        "kind": "clash",
        "attacker_slot_id": "A_slot",
        "defender_slot_id": "B_slot",
        "lines": ["line-1", "line-2"],
    }

    battle_core._emit_battle_trace("room_t", "battle_t", battle_state, trace_entry)
    assert len(room_state["logs"]) == 1
    assert "[マッチ]" in str(room_state["logs"][0].get("message", ""))
    detail = room_state["logs"][0].get("resolve_trace_detail", {})
    assert isinstance(detail, dict)
    assert detail.get("kind") == "clash"
    assert len((battle_state.get("resolve") or {}).get("persisted_trace_log_keys", [])) == 1

    # Same trace key must not be persisted twice.
    battle_core._emit_battle_trace("room_t", "battle_t", battle_state, trace_entry)
    assert len(room_state["logs"]) == 1


def test_clash_delegate_captures_core_broadcast_log_lines(monkeypatch):
    attacker = {
        "id": "A1",
        "name": "Attacker",
        "type": "ally",
        "hp": 100,
        "maxHp": 100,
        "mp": 20,
        "maxMp": 20,
        "states": [],
        "params": [],
        "special_buffs": [],
        "flags": {},
    }
    defender = {
        "id": "B1",
        "name": "Defender",
        "type": "enemy",
        "hp": 100,
        "maxHp": 100,
        "mp": 20,
        "maxMp": 20,
        "states": [],
        "params": [],
        "special_buffs": [],
        "flags": {},
    }
    state = {
        "timeline": [],
        "characters": [attacker, defender],
    }

    monkeypatch.setattr(
        battle_core,
        "calculate_skill_preview",
        lambda *_args, **_kwargs: {"final_command": "1d6", "min_damage": 1, "max_damage": 6, "power_breakdown": {}},
    )

    from manager.battle import duel_solver as duel_solver_mod

    def _fake_execute_duel_match(room, _exec_data, _username):
        defender["hp"] = 99
        battle_core.broadcast_log(room, "[色彩] が Defender に付与されました。", "state-change")

    monkeypatch.setattr(duel_solver_mod, "execute_duel_match", _fake_execute_duel_match)

    result = battle_core._resolve_clash_by_existing_logic(
        room="room_t",
        state=state,
        attacker_char=attacker,
        defender_char=defender,
        attacker_skill_data={"id": "ATK", "category": "attack", "tags": ["attack"]},
        defender_skill_data={"id": "DEF", "category": "attack", "tags": ["attack"]},
    )

    assert result.get("ok") is True
    legacy_lines = (result.get("summary") or {}).get("legacy_log_lines", [])
    assert any("付与されました" in str(line) for line in legacy_lines)
