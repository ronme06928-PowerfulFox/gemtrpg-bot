"""計画52 PR4: 判定を変えずに効果・適用後HP・自滅を記録する。"""
import copy
import json
from pathlib import Path

import pytest

import extensions
from manager.game_logic import process_skill_effects
from manager.utils import apply_buff, STACK_RESOURCE_VARIANT_BURST_GUIDANCE
from tests.test_stack_resource_variants import _build_char


@pytest.fixture(autouse=True)
def glossary(monkeypatch):
    catalog = json.loads((Path(__file__).resolve().parents[1] / "data/cache/glossary_catalog_cache.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(extensions, "all_glossary_data", catalog)


def test_fear_surge_records_glossary_name_and_per_effect_deltas_without_hp():
    actor, target = _build_char("a"), _build_char("d", "enemy")
    target["states"].append({"name": "戦慄", "value": 5})
    fired = []
    effects = [{"timing": "HIT", "type": "CUSTOM_EFFECT", "value": "戦慄殺到"}]
    untouched = copy.deepcopy((actor, target))
    plain = process_skill_effects(effects, "HIT", actor, target, context={})
    actor, target = copy.deepcopy(untouched)
    recorded = process_skill_effects(effects, "HIT", actor, target, context={"fired_effects": fired})
    assert recorded == plain
    assert len(fired) == 1
    assert fired[0] == {"term_id": "W-07", "name": "戦慄殺到", "actor_id": "a", "target_id": "d",
                        "results": [{"name": "MP", "delta": -5}, {"name": "戦慄", "delta": -5}]}


def test_burst_guidance_direct_call_records_rupture_explosion():
    actor, target = _build_char("a"), _build_char("d", "enemy")
    target["states"].append({"name": "破裂", "value": 7})
    apply_buff(actor, "蓄力", -1, 0, data={"buff_id": "Bu-30", "variant": STACK_RESOURCE_VARIANT_BURST_GUIDANCE}, count=10)
    fired = []
    process_skill_effects([], "HIT", actor, target, context={"fired_effects": fired})
    assert [row["term_id"] for row in fired] == ["W-03"]
    assert all(r["name"] != "HP" for row in fired for r in row["results"])


@pytest.mark.parametrize("resource,buff_id,term_id", [("凝魔", "Bu-31", "W-79"), ("蓄力", "Bu-30", "W-81")])
def test_resource_conversion_uses_the_resource_that_was_converted(resource, buff_id, term_id):
    actor = _build_char("a")
    apply_buff(actor, resource, -1, 0, data={"buff_id": buff_id}, count=10)
    fired = []
    effects = [{"timing": "PRE_MATCH", "type": "CONVERT_STACK_RESOURCE_VARIANT", "target": "self",
                "resource_name": resource, "to_variant": "converted"}]
    process_skill_effects(effects, "PRE_MATCH", actor, None, context={"fired_effects": fired})
    assert [r["term_id"] for r in fired] == [term_id]
    assert fired[0]["target_id"] == "a"
    assert fired[0]["actor_id"] == "a"


def test_reuse_and_unknown_or_missing_glossary_names(monkeypatch):
    actor, target = _build_char("a"), _build_char("d", "enemy")
    fired = []
    process_skill_effects([{"timing": "HIT", "type": "USE_SKILL_AGAIN", "target": "self"}], "HIT", actor, target,
                          context={"fired_effects": fired})
    assert [r["term_id"] for r in fired] == ["W-58"]
    for name in ["APPLY_SKILL_DAMAGE_AGAIN", "unknown"]:
        process_skill_effects([{"timing": "HIT", "type": "CUSTOM_EFFECT", "value": name}], "HIT", actor, target,
                              context={"fired_effects": fired})
    assert len(fired) == 1
    monkeypatch.setattr(extensions, "all_glossary_data", {})
    process_skill_effects([{"timing": "HIT", "type": "USE_SKILL_AGAIN"}], "HIT", actor, target,
                          context={"fired_effects": fired})
    assert len(fired) == 1


def test_snapshot_records_mp_and_post_damage_hp():
    from manager.battle.resolve_effect_runtime import _diff_snapshot, _apply_damage
    before = {"id": "d", "hp": 7, "mp": 10}
    after = {"id": "d", "hp": 0, "mp": 5}
    diff = _diff_snapshot(before, after)
    assert diff["damage"][0]["hp_after"] == 0
    assert {"target_id": "d", "name": "MP", "before": 10, "after": 5, "delta": -5} in diff["statuses"]
    assert _apply_damage({"id": "d", "hp": 7}, 10)["hp_after"] == 0
    assert _apply_damage({"id": "d", "hp": 7}, 0)["hp_after"] == 7


def test_self_destruct_is_in_the_sent_trace_before_hp_is_changed(monkeypatch):
    from manager.battle import core
    from tests.test_select_resolve_smoke import _make_actor, _base_state, _add_slot, _set_intent, _patch_room_and_socket
    actor, target = _make_actor("a", "ally"), _make_actor("d", "enemy")
    state = _base_state([actor, target])
    _add_slot(state, "sa", "a", "ally", 10)
    _add_slot(state, "sd", "d", "enemy", 8)
    _set_intent(state, "sa", "a", "self_destruct_test", "single_slot", "sd")
    _set_intent(state, "sd", "d", "idle", "none", committed=False)
    state["battle_state"]["phase"] = "resolve_single"
    _patch_room_and_socket(monkeypatch, state)
    from manager import room_manager
    monkeypatch.setattr(room_manager, 'get_room_state', lambda room: state)
    monkeypatch.setattr(room_manager, 'save_specific_room_state', lambda room: True)
    monkeypatch.setitem(core.all_skill_data, "self_destruct_test", {"tags": ["攻撃", "自滅"], "rule_data": {"tags": ["自滅"]}})
    monkeypatch.setattr(core, "_resolve_one_sided_by_existing_logic", lambda **kw: {"ok": True, "summary": {"fired_effects": [{"term_id": "W-58"}]}})
    moments = []
    def emit_trace(event, payload=None, **kw):
        if event == 'battle_resolve_trace_appended':
            moments.append(("trace", actor["hp"], copy.deepcopy(payload['trace'][0])))
    def update(_room, char, stat, value, **kw):
        if stat == "HP":
            moments.append(("hp", value))
            char["hp"] = int(value)
    monkeypatch.setattr(core.socketio, "emit", emit_trace)
    monkeypatch.setattr(core, "_apply_step_end_timing_from_trace", lambda *args: 0)
    monkeypatch.setattr(core, "_update_char_stat", update)
    core.run_select_resolve_auto("room_t", "battle_test")
    sent = next(row for row in moments if row[0] == "trace" and row[2]["kind"] == "one_sided")
    assert sent[1] == 100
    assert sent[2]["self_destructed"] == ["a"]
    assert sent[2]["applied"]["fired_effects"] == [{"term_id": "W-58"}]
    assert moments.index(sent) < next(i for i, row in enumerate(moments) if row == ("hp", 0))
    assert actor["hp"] == 0


@pytest.mark.parametrize('route', ['one_sided', 'clash', 'mass_individual', 'mass_summation'])
def test_real_resolution_paths_include_fired_effects_and_hp_after(monkeypatch, route):
    from manager.battle import core
    from tests.test_cost_payment_order import _setup
    state, _ = _setup(monkeypatch, mass=route.startswith('mass'))
    bs = state['battle_state']
    if route == 'one_sided':
        bs['intents']['B1']['skill_id'] = None
    if route == 'mass_summation':
        bs['intents']['A']['tags']['mass_type'] = 'mass_summation'
        bs['intents']['A']['target']['type'] = 'mass_summation'
    for target in state['characters'][1:]:
        target['states'].append({'name': '戦慄', 'value': 5})
    skill = core.all_skill_data['COST_A']
    rule = {**skill['rule_data'], 'effects': [{'timing': 'BEFORE_POWER_ROLL', 'type': 'CUSTOM_EFFECT', 'value': '戦慄殺到'}]}
    skill.update(rule_data=rule, rule_data_json=rule, 特記処理=json.dumps(rule, ensure_ascii=False))
    bs['phase'] = 'resolve_mass' if route.startswith('mass') else 'resolve_single'
    core.run_select_resolve_auto('room_t', 'battle_test')
    traces = [r for r in bs['resolve']['trace'] if r['kind'] == route]
    assert traces
    for trace in traces:
        fired = trace['applied']['fired_effects']
        assert any(row['term_id'] == 'W-07' for row in fired), trace
        assert any(row['name'] == 'MP' for row in trace['applied']['statuses'])
        for row in trace['applied'].get('damage', []) + trace.get('damage_events', []):
            assert 'hp_after' in row
        assert 'delegate_error' not in str(trace)


def test_hard_attack_collects_hit_effects_without_changing_its_damage(monkeypatch):
    from manager.battle import core
    from tests.test_select_resolve_timing_normalization import _patch_deterministic_one_sided, _make_char, _clash_skill
    _patch_deterministic_one_sided(monkeypatch)
    a, d = _make_char('A1', 'ally'), _make_char('D1', 'enemy')
    d['states'].append({'name': '戦慄', 'value': 5})
    skill = _clash_skill('TEST_HARD', [{'timing': 'HIT', 'type': 'CUSTOM_EFFECT', 'value': '戦慄殺到'}])
    result = core._resolve_hard_attack_followup('room_t', {'characters': [a, d], 'timeline': []}, a, d, skill)
    assert result['ok']
    assert [r['term_id'] for r in result['summary']['fired_effects']] == ['W-07']
    assert d['mp'] == 45


def test_custom_set_deltas_use_pre_effect_values_even_when_plugin_mutates_simulation():
    actor, target = _build_char('a'), _build_char('d', 'enemy')
    target['states'].append({'name': '破裂', 'value': 7})
    fired = []
    process_skill_effects([{'timing': 'HIT', 'type': 'CUSTOM_EFFECT', 'value': '破裂爆発'}], 'HIT', actor, target,
                          context={'fired_effects': fired})
    assert fired[0]['results'] == [{'name': '破裂', 'delta': -7}]


def test_power_capture_is_nested_and_does_not_leak_between_resolutions():
    from manager.battle.effect_presentation import capture_power_effects, power_effects_collector
    a, b = [], []
    assert power_effects_collector() is None
    with capture_power_effects(a):
        assert power_effects_collector() is a
        with capture_power_effects(b):
            assert power_effects_collector() is b
        assert power_effects_collector() is a
    assert power_effects_collector() is None


def test_bleed_flood_reports_maintenance_consumption_as_a_buff_result():
    actor, target = _build_char('a'), _build_char('d', 'enemy')
    next(row for row in target['states'] if row['name'] == '出血')['value'] = 4
    target['special_buffs'].append({'name': '出血遷延', 'buff_id': 'Bu-08', 'count': 2, 'delay': 0})
    fired = []
    process_skill_effects([{'timing': 'HIT', 'type': 'CUSTOM_EFFECT', 'value': '出血氾濫'}], 'HIT', actor, target,
                          context={'fired_effects': fired})
    assert {'name': 'buff:出血遷延', 'delta': -1} in fired[0]['results']


def test_unmapped_handler_with_object_value_keeps_the_original_result():
    actor = _build_char('a')
    effect = {'timing': 'HIT', 'type': 'APPLY_BUFF', 'target': 'self', 'buff_name': 'test',
              'value': {'count': 3}, 'lasting': 1}
    plain = process_skill_effects([effect], 'HIT', copy.deepcopy(actor), None, context={})
    fired = []
    recorded = process_skill_effects([effect], 'HIT', copy.deepcopy(actor), None, context={'fired_effects': fired})
    assert recorded == plain
    assert fired == []
