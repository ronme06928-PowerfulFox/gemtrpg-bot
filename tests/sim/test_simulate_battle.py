import json

import scripts.simulate_battle as simulate_battle
from scripts.simulate_battle import (
    auto_commit_ally_intents,
    build_deterministic_roll_dice,
    build_room_state_from_presets,
    format_report,
    run_battle,
)


def _make_char(char_id, team, hp=20):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": hp,
        "maxHp": hp,
        "mp": 10,
        "maxMp": 10,
        "x": 0,
        "y": 0,
        "is_escaped": False,
        "states": [],
        "special_buffs": [],
        "params": [
            {"label": "速度", "value": 6},
            {"label": "行動回数", "value": 1},
        ],
    }


def _base_state(extra_enemies=None):
    characters = [
        _make_char("A1", "ally", hp=20),
        _make_char("E1", "enemy", hp=20),
    ]
    if extra_enemies:
        characters.extend(extra_enemies)
    return {
        "round": 0,
        "characters": characters,
        "timeline": [],
        "battle_state": {
            "battle_id": "sim_test",
            "round": 0,
            "phase": "round_end",
            "slots": {},
            "timeline": [],
            "tiebreak": [],
            "intents": {},
            "redirects": [],
            "resolve": {
                "mass_queue": [],
                "single_queue": [],
                "resolved_slots": [],
                "trace": [],
            },
        },
    }


def _slot_for_actor(battle_state, actor_id):
    for slot_id, slot in (battle_state.get("slots") or {}).items():
        if isinstance(slot, dict) and slot.get("actor_id") == actor_id:
            return slot_id
    raise AssertionError(f"slot not found for {actor_id}")


def _commit_ally_attack(state, battle_state):
    ally_slot = _slot_for_actor(battle_state, "A1")
    enemy_slot = _slot_for_actor(battle_state, "E1")
    battle_state.setdefault("intents", {})[ally_slot] = {
        "slot_id": ally_slot,
        "actor_id": "A1",
        "skill_id": "SIM_ATK",
        "target": {"type": "single_slot", "slot_id": enemy_slot},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": True,
        "committed_at": 1,
    }


def _commit_ally_attack_against_uncommitted_enemy_target(state, battle_state):
    ally_slot = _slot_for_actor(battle_state, "A1")
    enemy_slot = _slot_for_actor(battle_state, "E1")
    battle_state.setdefault("intents", {})[enemy_slot] = {
        "slot_id": enemy_slot,
        "actor_id": "E1",
        "skill_id": None,
        "target": {"type": "single_slot", "slot_id": ally_slot},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": False,
        "committed_at": None,
    }
    battle_state["intents"][ally_slot] = {
        "slot_id": ally_slot,
        "actor_id": "A1",
        "skill_id": "SIM_ATK",
        "target": {"type": "single_slot", "slot_id": enemy_slot},
        "tags": {"instant": False, "mass_type": None, "no_redirect": False},
        "committed": True,
        "committed_at": 1,
    }


def _preset_record(preset_id, name, side):
    data = _make_char(f"{preset_id}_template", side, hp=20)
    data["name"] = name
    data["status"] = [
        {"label": "HP", "value": 20, "max": 20},
        {"label": "MP", "value": 10, "max": 10},
        {"label": "FP", "value": 0, "max": 0},
    ]
    return {
        "id": preset_id,
        "name": name,
        "allow_ally": True,
        "allow_enemy": True,
        "character_json": {"kind": "character", "data": data},
    }


def _preset_store():
    return {
        "version": 2,
        "character_presets": {
            "ALLY_1": _preset_record("ALLY_1", "Ally Preset", "ally"),
            "ENEMY_1": _preset_record("ENEMY_1", "Enemy Preset", "enemy"),
        },
        "ally_formations": {
            "ALLY_FORM": {"id": "ALLY_FORM", "members": [{"preset_id": "ALLY_1"}]},
        },
        "enemy_formations": {
            "ENEMY_FORM": {"id": "ENEMY_FORM", "members": [{"preset_id": "ENEMY_1", "count": 2}]},
        },
        "stage_presets": {
            "STAGE_1": {
                "id": "STAGE_1",
                "ally_formation_id": "ALLY_FORM",
                "enemy_formation_id": "ENEMY_FORM",
                "field_effect_profile": {"enabled": True, "id": "field_test"},
            },
        },
    }


def test_run_battle_returns_report_when_fixed_intent_wins(monkeypatch):
    from manager.battle import core as battle_core

    state = _base_state()
    monkeypatch.setitem(
        battle_core.all_skill_data,
        "SIM_ATK",
        {"base_power": 1, "dice_power": "1d1", "rule_data": {"effects": []}},
    )

    def _stub_one_sided(**kwargs):
        defender = kwargs["defender_char"]
        defender["hp"] = 0
        defender["x"] = -1
        defender["y"] = -1
        return {
            "ok": True,
            "summary": {
                "damage": [{"target_id": defender.get("id"), "amount": 20, "before": 20, "after": 0}],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "rolls": {"total_damage": 20},
            },
        }

    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)

    report = run_battle(state, max_rounds=3, intent_provider=_commit_ally_attack)

    assert report.result == "ally_win"
    assert report.rounds == 1
    assert report.stalled is False
    assert report.stall_reason is None
    assert report.summary.ally.alive_count == 1
    assert report.summary.enemy.alive_count == 0
    assert report.summary.enemy.hp == 0
    assert report.rounds_detail[0].committed_intents == 1
    assert report.rounds_detail[0].hp_delta == 20
    assert any(c.id == "E1" and c.hp == 0 for c in report.characters)
    assert "summary: ally 1/1 HP 20/20" in format_report(report)
    assert "result: ally_win" in format_report(report)


def test_run_battle_reports_stall_at_max_rounds_without_intents():
    report = run_battle(_base_state(), max_rounds=2)

    assert report.result == "in_progress"
    assert report.rounds == 2
    assert report.stalled is True
    assert report.stall_reason == "no_committed_intents"
    assert report.summary.ally.hp_rate == 1.0
    assert report.summary.enemy.hp_rate == 1.0
    assert [row.committed_intents for row in report.rounds_detail] == [0, 0]


def test_run_battle_reports_no_damage_progress_when_intents_do_not_change_hp(monkeypatch):
    from manager.battle import core as battle_core

    state = _base_state()
    monkeypatch.setitem(
        battle_core.all_skill_data,
        "SIM_ATK",
        {"base_power": 1, "dice_power": "1d1", "rule_data": {"effects": []}},
    )

    def _stub_one_sided(**_kwargs):
        return {
            "ok": True,
            "summary": {
                "damage": [],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "rolls": {"total_damage": 0},
            },
        }

    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)

    report = run_battle(state, max_rounds=2, intent_provider=_commit_ally_attack)

    assert report.result == "in_progress"
    assert report.stalled is True
    assert report.stall_reason == "no_damage_progress"
    assert [row.committed_intents for row in report.rounds_detail] == [1, 1]
    assert [row.hp_delta for row in report.rounds_detail] == [0, 0]


def test_deterministic_roll_dice_modes_preserve_breakdown_shape():
    low = build_deterministic_roll_dice("low")("2d6+3-1d4 【test】")
    median = build_deterministic_roll_dice("median")("2d6+3-1d4 【test】")
    high = build_deterministic_roll_dice("high")("2d6+3-1d4 【test】")

    assert low["total"] == 4
    assert low["details"] == "(1+1)+3-(1)"
    assert low["breakdown"]["dice_terms"][0]["rolls"] == [1, 1]
    assert low["breakdown"]["dice_terms"][1]["sign"] == -1
    assert low["breakdown"]["roll_mode"] == "low"

    assert median["total"] == 8
    assert median["breakdown"]["dice_terms"][0]["rolls"] == [4, 4]
    assert median["breakdown"]["dice_terms"][1]["rolls"] == [3]

    assert high["total"] == 11
    assert high["breakdown"]["dice_terms"][0]["rolls"] == [6, 6]
    assert high["breakdown"]["dice_terms"][1]["rolls"] == [4]


def test_run_battle_roll_mode_controls_round_start_initiative():
    seen = {}

    def _capture(mode):
        def _provider(_state, battle_state):
            slot = next(
                slot
                for slot in (battle_state.get("slots") or {}).values()
                if isinstance(slot, dict) and slot.get("actor_id") == "A1"
            )
            seen[mode] = {
                "speed_roll": slot.get("speed_roll"),
                "initiative": slot.get("initiative"),
            }

        run_battle(_base_state(), max_rounds=1, roll_mode=mode, intent_provider=_provider)

    _capture("low")
    _capture("median")
    _capture("high")

    assert seen["low"] == {"speed_roll": 1, "initiative": 2}
    assert seen["median"] == {"speed_roll": 4, "initiative": 5}
    assert seen["high"] == {"speed_roll": 6, "initiative": 7}


def test_auto_commit_ally_intents_selects_lowest_hp_enemy_and_preserves_existing(monkeypatch):
    state = _base_state(extra_enemies=[_make_char("E2", "enemy", hp=5)])
    battle_state = state["battle_state"]
    battle_state["slots"] = {
        "A1:s0": {"slot_id": "A1:s0", "actor_id": "A1", "team": "ally"},
        "A1:s1": {"slot_id": "A1:s1", "actor_id": "A1", "team": "ally"},
        "E1:s0": {"slot_id": "E1:s0", "actor_id": "E1", "team": "enemy"},
        "E2:s0": {"slot_id": "E2:s0", "actor_id": "E2", "team": "enemy"},
    }
    battle_state["timeline"] = ["A1:s0", "A1:s1", "E1:s0", "E2:s0"]
    battle_state["intents"] = {
        "A1:s0": {
            "slot_id": "A1:s0",
            "actor_id": "A1",
            "skill_id": "MANUAL",
            "target": {"type": "none", "slot_id": None},
            "committed": True,
        }
    }
    monkeypatch.setattr(simulate_battle.battle_runner, "ai_suggest_skill", lambda _char: "SIM_ATK")

    committed = auto_commit_ally_intents(state, battle_state, target_policy="lowest_hp_enemy")

    assert committed == 1
    assert battle_state["intents"]["A1:s0"]["skill_id"] == "MANUAL"
    auto_intent = battle_state["intents"]["A1:s1"]
    assert auto_intent["skill_id"] == "SIM_ATK"
    assert auto_intent["target"] == {"type": "single_slot", "slot_id": "E2:s0"}
    assert auto_intent["committed_by"] == "AI:SIM_ALLY"


def test_run_battle_can_use_auto_ally_intents(monkeypatch):
    from manager.battle import core as battle_core

    monkeypatch.setattr(simulate_battle.battle_runner, "ai_suggest_skill", lambda _char: "SIM_ATK")
    monkeypatch.setitem(
        battle_core.all_skill_data,
        "SIM_ATK",
        {"base_power": 1, "dice_power": "1d1", "rule_data": {"effects": []}},
    )

    def _stub_one_sided(**kwargs):
        defender = kwargs["defender_char"]
        defender["hp"] = 0
        defender["x"] = -1
        defender["y"] = -1
        return {
            "ok": True,
            "summary": {
                "damage": [{"target_id": defender.get("id"), "amount": 20, "before": 20, "after": 0}],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "rolls": {"total_damage": 20},
            },
        }

    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)

    report = run_battle(_base_state(), max_rounds=3, roll_mode="median", auto_ally_intents=True)

    assert report.result == "ally_win"
    assert report.rounds == 1
    assert report.stalled is False


def test_uncommitted_reciprocal_target_does_not_force_clash(monkeypatch):
    from manager.battle import core as battle_core

    monkeypatch.setitem(
        battle_core.all_skill_data,
        "SIM_ATK",
        {"base_power": 1, "dice_power": "1d1", "rule_data": {"effects": []}},
    )

    def _stub_clash(**_kwargs):
        raise AssertionError("uncommitted reciprocal target should not form clash")

    def _stub_one_sided(**kwargs):
        defender = kwargs["defender_char"]
        defender["hp"] = 0
        defender["x"] = -1
        defender["y"] = -1
        return {
            "ok": True,
            "summary": {
                "damage": [{"target_id": defender.get("id"), "amount": 20, "before": 20, "after": 0}],
                "statuses": [],
                "flags": [],
                "cost": {"mp": 0, "hp": 0, "fp": 0},
                "logs": [],
                "rolls": {"total_damage": 20},
            },
        }

    monkeypatch.setattr(battle_core, "_resolve_clash_by_existing_logic", _stub_clash)
    monkeypatch.setattr(battle_core, "_resolve_one_sided_by_existing_logic", _stub_one_sided)

    report = run_battle(
        _base_state(),
        max_rounds=3,
        roll_mode="median",
        intent_provider=_commit_ally_attack_against_uncommitted_enemy_target,
    )

    assert report.result == "ally_win"
    assert report.rounds == 1
    assert report.rounds_detail[0].hp_delta == 20


def test_build_room_state_from_presets_uses_stage_formations_and_positions():
    state = build_room_state_from_presets(store=_preset_store(), stage_id="STAGE_1")

    allies = [char for char in state["characters"] if char.get("type") == "ally"]
    enemies = [char for char in state["characters"] if char.get("type") == "enemy"]
    assert len(allies) == 1
    assert len(enemies) == 2
    assert state["play_mode"] == "battle_only"
    assert state["battle_only"]["selected_stage_id"] == "STAGE_1"
    assert state["battle_only"]["field_effect_profile"]["id"] == "field_test"
    assert all(char["x"] >= 0 and char["y"] >= 0 for char in state["characters"])


def test_build_room_state_from_presets_accepts_direct_preset_ids():
    state = build_room_state_from_presets(
        store=_preset_store(),
        ally_preset_ids=["ALLY_1"],
        enemy_preset_ids=["ENEMY_1"],
    )

    assert [char["type"] for char in state["characters"]] == ["ally", "enemy"]
    assert {char["name"] for char in state["characters"]} == {"Ally Preset", "Enemy Preset"}


def test_cli_outputs_console_report(tmp_path, capsys):
    input_path = tmp_path / "room_state.json"
    input_path.write_text(json.dumps(_base_state(), ensure_ascii=False), encoding="utf-8")

    rc = simulate_battle.main(["--input", str(input_path), "--roll-mode", "median", "--max-rounds", "1"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "roll_mode: median" in captured.out
    assert "result: in_progress" in captured.out
    assert "stalled: true" in captured.out
    assert "stall_reason: no_committed_intents" in captured.out
    assert "rounds_detail:" in captured.out


def test_cli_outputs_json_for_all_roll_modes(tmp_path, capsys):
    input_path = tmp_path / "room_state.json"
    input_path.write_text(json.dumps(_base_state(), ensure_ascii=False), encoding="utf-8")

    rc = simulate_battle.main(["--input", str(input_path), "--roll-mode", "all", "--max-rounds", "1", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0
    assert [row["roll_mode"] for row in payload] == ["low", "median", "high"]
    assert all(row["result"] == "in_progress" for row in payload)
    assert all(row["stall_reason"] == "no_committed_intents" for row in payload)
    assert all("summary" in row and "rounds_detail" in row for row in payload)


def test_cli_outputs_aggregate_json_for_multiple_runs(tmp_path, capsys):
    input_path = tmp_path / "room_state.json"
    input_path.write_text(json.dumps(_base_state(), ensure_ascii=False), encoding="utf-8")

    rc = simulate_battle.main(
        [
            "--input",
            str(input_path),
            "--roll-mode",
            "median",
            "--max-rounds",
            "1",
            "--runs",
            "3",
            "--seed",
            "42",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0
    assert payload["roll_mode"] == "median"
    assert payload["aggregate"]["runs"] == 3
    assert payload["aggregate"]["result_counts"] == {"in_progress": 3}
    assert payload["aggregate"]["stall_reason_counts"] == {"no_committed_intents": 3}
    assert payload["aggregate"]["stall_rate"] == 1.0
    assert [row["run_index"] for row in payload["runs"]] == [1, 2, 3]


def test_cli_lists_preset_catalog_without_room_input(tmp_path, capsys):
    store_path = tmp_path / "battle_only_presets_cache.json"
    store_path.write_text(json.dumps(_preset_store(), ensure_ascii=False), encoding="utf-8")

    rc = simulate_battle.main(["--preset-store", str(store_path), "--list-stages"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "stage_presets:" in captured.out
    assert "STAGE_1" in captured.out
    assert "ally_formation_id=ALLY_FORM" in captured.out


def test_cli_lists_preset_catalog_as_json(tmp_path, capsys):
    store_path = tmp_path / "battle_only_presets_cache.json"
    store_path.write_text(json.dumps(_preset_store(), ensure_ascii=False), encoding="utf-8")

    rc = simulate_battle.main(["--preset-store", str(store_path), "--list-presets", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0
    assert [row["id"] for row in payload["character_presets"]] == ["ALLY_1", "ENEMY_1"]


def test_cli_can_build_room_state_from_stage_preset(tmp_path, capsys):
    store_path = tmp_path / "battle_only_presets_cache.json"
    store_path.write_text(json.dumps(_preset_store(), ensure_ascii=False), encoding="utf-8")

    rc = simulate_battle.main(
        [
            "--preset-store",
            str(store_path),
            "--stage-id",
            "STAGE_1",
            "--roll-mode",
            "median",
            "--max-rounds",
            "1",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0
    assert payload["roll_mode"] == "median"
    assert payload["result"] == "in_progress"
    assert len(payload["characters"]) == 3
    assert payload["summary"]["ally"]["total_count"] == 1
    assert payload["summary"]["enemy"]["total_count"] == 2
    assert payload["rounds_detail"][0]["round"] == 1
