import pytest

from manager.battle.condition_eval import check_condition
from manager.catalog.kinds import inspect_buff_effect
from manager.game_logic import process_skill_effects


def fighter(key, side="ally", *, hp=20, x=0, effects=()):
    return {"id": key, "name": key, "type": side, "hp": hp, "maxHp": 20, "mp": 0,
            "maxMp": 20, "x": x, "y": 0, "states": [],
            "special_buffs": [{"name": "獣の爪飾り", "data": {"effects": list(effects)}}]}


def row(timing, **fields):
    return {"timing": timing, "type": "APPLY_STATE", "state_name": "出血", "value": 1, **fields}


def test_skill_fields_and_missing_value():
    slash = {"source": "skill", "param": "属性", "operator": "EQUALS", "value": "斬撃"}
    magic = {"source": "target_skill", "param": "分類", "operator": "EQUALS", "value": "魔法"}
    assert check_condition(slash, {}, {}, actor_skill_data={"属性": "斬撃"})
    assert check_condition(magic, {}, {}, target_skill_data={"分類": "魔法"})
    assert not check_condition(slash, {}, {}, actor_skill_data={"tags": ["斬撃"]})


def test_buff_power_condition_reads_classification():
    from manager.battle.buff_power import calculate_buff_power_bonus

    condition = {"source": "actor_skill", "param": "分類", "operator": "EQUALS", "value": "物理"}
    actor = fighter("actor")
    actor["special_buffs"][0]["data"]["power_bonus"] = [{"value": 3, "condition": condition}]
    assert calculate_buff_power_bonus(actor, fighter("target", "enemy"), {"分類": "物理"}) == 3
    assert calculate_buff_power_bonus(actor, fighter("target", "enemy"), {"分類": "魔法"}) == 0


@pytest.mark.parametrize("timing", ["PRE_MATCH", "HIT", "WIN", "LOSE", "UNOPPOSED", "END_MATCH"])
def test_skill_and_buff_rows_use_same_skill_and_order(timing):
    condition = {"source": "skill", "param": "属性", "operator": "EQUALS", "value": "斬撃"}
    attacker = fighter("actor", effects=[row(timing, condition=condition)])
    target = fighter("target", "enemy")
    effects = [row(timing, value=2, condition=condition)]
    shown = []
    context = {"actor_skill_data": {"属性": "斬撃"}, "fired_effects": shown}
    _, logs, changes = process_skill_effects(effects, timing, attacker, target, context=context)
    assert [change[-1] for change in changes] == [2, 1]
    assert any("[獣の爪飾り]" in log for log in logs)
    assert not any(log.endswith(timing) for log in logs)
    assert any(effect["name"] == "獣の爪飾り" for effect in shown)
    assert process_skill_effects([], timing, target, attacker, context=context)[-1] == []


@pytest.mark.parametrize("effects", [None, {}, [3], [{"type": "APPLY_STATE"}], [row("RESOLVE_END")],
                                     [{"timing": "HIT", "type": "UNDEFINED"}],
                                     [row("HIT", state_name=[])], [row("HIT", value=True)]])
def test_buff_effect_validation_rejects_unsupported_rows(effects):
    problems = []
    inspect_buff_effect({"effect": {"effects": effects}}, "Bu-99", "approve",
                        lambda path, message, *_: problems.append(path))
    assert problems and problems[0].startswith("effect.effects")


def test_round_owner_eligibility_and_entry_uses_real_application():
    from manager.battle.timed_buffs import run_timed_buffs
    from manager.game_logic import get_status_value, process_battle_start

    effects = [row("START_ROUND", value=-2), row("END_ROUND", state_name="FP", value=2),
               row("BATTLE_START", target="ALL_ENEMIES")]
    actor, reserve, down = fighter("actor", effects=effects), fighter("reserve", x=-1, effects=effects), fighter(
        "down", hp=0, effects=effects)
    enemy = fighter("enemy", "enemy")
    state = {"characters": [actor, reserve, down, enemy]}
    for char in (actor, reserve, down):
        char["states"] = [{"name": "出血", "value": 3}]
        run_timed_buffs(None, state, char, "START_ROUND")
        run_timed_buffs(None, state, char, "END_ROUND")
    assert [get_status_value(char, "出血") for char in (actor, reserve, down)] == [1, 3, 3]
    assert [get_status_value(char, "FP") for char in (actor, reserve, down)] == [2, 0, 0]
    logs = process_battle_start(None, [actor, reserve, down], state=state)
    assert get_status_value(enemy, "出血") == 1
    assert any("[獣の爪飾り]" in line for line in logs)


def test_kill_uses_defeated_target_and_honors_chain_budget(monkeypatch):
    from manager import room_manager
    from manager.battle import timed_buffs
    from manager.battle.damage_context import build_damage_context
    from manager.game_logic import get_status_value

    actor = fighter("actor", effects=[row("ON_KILL", target="self", state_name="FP",
                                         condition={"source": "trigger_target", "param": "出血",
                                                    "operator": "GT", "value": 0})])
    enemy = fighter("enemy", "enemy", hp=2)
    enemy["states"] = [{"name": "出血", "value": 2}]
    friend = fighter("friend")
    state = {"characters": [actor, enemy, friend]}
    monkeypatch.setattr(room_manager, "get_room_state", lambda _: state)
    monkeypatch.setattr(room_manager, "save_specific_room_state", lambda *_: None)
    monkeypatch.setattr(room_manager, "_safe_emit", lambda *_, **__: None)
    monkeypatch.setattr(room_manager, "broadcast_log", lambda *_, **__: None)
    skill = {"id": "Ps-01"}
    room_manager._update_char_stat("test-buff", enemy, "HP", 0,
                                  damage_context=build_damage_context(actor=friend, skill_data=skill))
    assert get_status_value(actor, "FP") == 0
    enemy["hp"] = 2
    room_manager._update_char_stat("test-buff", enemy, "HP", 0,
                                  damage_context=build_damage_context(actor=actor, skill_data=skill))
    assert get_status_value(actor, "FP") == 1

    observed = []
    cause = build_damage_context(actor=actor, skill_data=skill)

    def chain(*_args, **_kwargs):
        observed.append(1)
        timed_buffs.process_kill("test-buff", state, enemy, cause)

    monkeypatch.setattr(timed_buffs, "run_timed_buffs", chain)
    timed_buffs.process_kill("test-buff", state, enemy, cause)
    assert len(observed) == timed_buffs.MAX_KILL_TRIGGERS


def test_count_effect_applies_only_to_bleeding_opponents(monkeypatch):
    from manager.battle.timed_buffs import run_timed_buffs
    from manager.battle import effect_handlers
    from manager import buff_catalog

    charge = {"type": "APPLY_BUFF_FROM_CHARACTER_COUNT", "timing": "END_ROUND", "target": "self",
              "buff_id": "Bu-30", "buff_name": "蓄力", "value_per_character": 2, "apply_to": "stack",
              "lasting": -1,
              "character_filter": {"team": "enemy", "condition": {
                  "source": "target", "param": "出血", "operator": "GT", "value": 0}}}
    actor, enemy, unbled = fighter("actor", effects=[charge]), fighter("enemy", "enemy"), fighter("unbled", "enemy")
    enemy["states"] = [{"name": "出血", "value": 2}]
    assert "APPLY_BUFF_FROM_CHARACTER_COUNT" in effect_handlers.EFFECT_HANDLERS
    definition = {"name": "蓄力", "effect": {}}
    monkeypatch.setattr(buff_catalog, "get_buff_by_id", lambda _: definition)
    run_timed_buffs(None, {"characters": [actor, enemy, unbled]}, actor, "END_ROUND")
    assert next(buff for buff in actor["special_buffs"] if buff["name"] == "蓄力")["count"] == 2


@pytest.mark.parametrize("mode", ["single", "clash", "mass_individual", "mass_summation"])
def test_resolve_paths_run_buff_hit_and_present_it(monkeypatch, mode):
    from manager.battle import core
    from manager.battle.effect_presentation import step_effects_scope
    from manager import room_manager
    from tests.test_cost_payment_order import _skill, _update_stat
    from tests.test_select_resolve_smoke import (
        _make_actor, _base_state, _add_slot, _set_intent, _patch_room_and_socket, _state_value,
    )
    from tests.test_select_resolve_timing_normalization import _resolve_clash

    actor, enemy = _make_actor("A1", "ally"), _make_actor("B1", "enemy")
    actor["special_buffs"] = fighter("buff", effects=[row("HIT")])["special_buffs"]
    messages = []
    monkeypatch.setattr(room_manager, "broadcast_log", lambda room, text, *args: messages.append(text))
    attack = _skill("atk", 10)
    defense = _skill("def", 1)
    if mode == "clash":
        with step_effects_scope():
            result = _resolve_clash(monkeypatch, actor, enemy, attack, defense)
        assert result["ok"]
        effects = result["summary"]["fired_effects"]
    else:
        state = _base_state([actor, enemy])
        state["battle_state"]["phase"] = "resolve_single" if mode == "single" else "resolve_mass"
        _add_slot(state, "a", "A1", "ally", 10)
        _add_slot(state, "b", "B1", "enemy", 5)
        _set_intent(state, "a", "A1", "atk", "single_slot" if mode == "single" else mode,
                    "b" if mode == "single" else None, mass_type=None if mode == "single" else mode)
        _patch_room_and_socket(monkeypatch, state)
        monkeypatch.setattr(core, "all_skill_data", {"atk": attack})
        monkeypatch.setattr(core, "_update_char_stat", _update_stat)
        core.run_select_resolve_auto("room_t", "battle_test")
        effects = [effect for step in state["battle_state"]["resolve"]["trace"]
                   for effect in (step.get("fired_effects") or (step.get("applied") or {}).get("fired_effects") or [])]
    assert _state_value(enemy, "出血") == 1
    assert any(effect["name"] == "獣の爪飾り" for effect in effects)
    assert any(line.startswith("[獣の爪飾り]") for line in messages)


def test_simulator_applies_round_end_buffs_without_declarations():
    from scripts.simulate_battle import run_battle
    from tests.sim.test_simulate_battle import _base_state

    state = _base_state()
    actor = state["characters"][0]
    actor["hp"] = 10
    actor["action_slot_mode"] = "none"
    actor["special_buffs"] = [{"name": "回復", "lasting": -1, "is_permanent": True,
                               "data": {"effects": [row("END_ROUND", state_name="HP", value=2)]}}]
    report = run_battle(state, max_rounds=2, copy_state=False)
    assert report.rounds == 2
    assert actor["hp"] == 14


def test_drill_marks_timed_buff_as_excluded():
    from manager.drill.exclusions import excluded_effects

    actor = fighter("actor", effects=[row("PRE_MATCH")])
    reasons = excluded_effects(actor, fighter("target", "enemy"), None, None)
    assert any(reason["code"] == "buff_reaction" and "獣の爪飾り" in reason["reason"] for reason in reasons)
