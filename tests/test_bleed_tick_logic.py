from manager.bleed_logic import (
    resolve_bleed_tick,
    get_bleed_maintenance_count,
)
from manager.utils import get_status_value
from manager.game_logic import process_skill_effects
from plugins.standard import BleedOverflowEffect


def _build_char(bleed=0, buffs=None):
    return {
        "id": "c1",
        "name": "Target",
        "hp": 100,
        "mp": 50,
        "states": [{"name": "出血", "value": int(bleed)}],
        "special_buffs": list(buffs or []),
        "params": [],
    }


def test_resolve_bleed_tick_without_maintenance_halves_bleed():
    char = _build_char(bleed=5)
    tick = resolve_bleed_tick(char, consume_maintenance=True)

    assert tick["damage"] == 5
    assert tick["bleed_before"] == 5
    assert tick["bleed_after"] == 2
    assert tick["bleed_delta"] == -3
    assert tick["maintenance_consumed"] == 0


def test_resolve_bleed_tick_with_maintenance_consumes_one_stack():
    char = _build_char(
        bleed=5,
        buffs=[{"name": "出血遷延", "buff_id": "Bu-08", "delay": 0, "count": 2, "lasting": -1, "is_permanent": True}],
    )
    tick = resolve_bleed_tick(char, consume_maintenance=True)

    assert tick["damage"] == 5
    assert tick["bleed_after"] == 5
    assert tick["maintenance_consumed"] == 1
    assert tick["maintenance_remaining"] == 1
    assert get_bleed_maintenance_count(char) == 1


def test_resolve_bleed_tick_legacy_maintenance_without_count_is_compatible():
    char = _build_char(
        bleed=4,
        buffs=[{"name": "出血遷延", "buff_id": "Bu-08", "delay": 0, "lasting": 3}],
    )
    tick = resolve_bleed_tick(char, consume_maintenance=True)

    assert tick["damage"] == 4
    assert tick["bleed_after"] == 4
    assert tick["maintenance_consumed"] == 1
    assert get_bleed_maintenance_count(char) == 0


def test_bleed_overflow_effect_applies_immediate_bleed_tick():
    actor = {"id": "a1", "name": "Actor", "states": [], "special_buffs": [], "params": []}
    target = _build_char(bleed=5)
    effect = BleedOverflowEffect()

    changes, logs = effect.apply(actor, target, {}, {})

    assert any(c[1] == "CUSTOM_DAMAGE" and c[3] == 5 for c in changes)
    assert any(c[1] == "APPLY_STATE" and c[2] == "出血" and c[3] == -3 for c in changes)
    assert any("出血氾濫" in line for line in logs)
    assert get_status_value(target, "出血") == 5  # apply() returns changes; 実反映は呼び出し側


def test_custom_effect_uses_simulated_target_state_in_same_effect_chain():
    actor = {
        "id": "a1",
        "name": "Actor",
        "type": "ally",
        "hp": 100,
        "mp": 50,
        "states": [{"name": "FP", "value": 10}],
        "special_buffs": [],
        "params": [],
    }
    target = _build_char(bleed=11)
    target["type"] = "enemy"
    target["x"] = 1
    target["y"] = 0
    actor["x"] = 0
    actor["y"] = 0

    effects = [
        {"timing": "HIT", "type": "APPLY_STATE", "target": "target", "state_name": "出血", "value": 8},
        {"timing": "HIT", "type": "CUSTOM_EFFECT", "target": "target", "value": "出血氾濫"},
    ]
    context = {"characters": [actor, target], "timeline": [], "room": "unit"}

    _, _, changes = process_skill_effects(effects, "HIT", actor, target, context=context)
    damage_events = [c for c in changes if c[1] == "CUSTOM_DAMAGE" and c[2] == "出血氾濫"]
    bleed_state_events = [c for c in changes if c[1] == "APPLY_STATE" and c[2] == "出血"]

    assert damage_events, "出血氾濫のCUSTOM_DAMAGEが生成されること"
    assert damage_events[0][3] == 19, "先行する出血+8を反映した値で出血氾濫が計算されること"
    assert any(ev[3] == -10 for ev in bleed_state_events), "19 -> 9 の減衰差分(-10)が含まれること"


def test_bleed_overflow_emits_maintenance_consume_change():
    actor = {
        "id": "a1",
        "name": "Actor",
        "type": "ally",
        "hp": 100,
        "mp": 50,
        "states": [{"name": "FP", "value": 10}],
        "special_buffs": [],
        "params": [],
    }
    target = _build_char(
        bleed=11,
        buffs=[{"name": "出血遷延", "buff_id": "Bu-08", "delay": 0, "count": 1, "lasting": -1, "is_permanent": True}],
    )
    target["type"] = "enemy"
    target["x"] = 1
    target["y"] = 0
    actor["x"] = 0
    actor["y"] = 0

    effects = [{"timing": "HIT", "type": "CUSTOM_EFFECT", "target": "target", "value": "出血氾濫"}]
    context = {"characters": [actor, target], "timeline": [], "room": "unit"}

    _, _, changes = process_skill_effects(effects, "HIT", actor, target, context=context)
    consume_events = [c for c in changes if c[1] == "CONSUME_BLEED_MAINTENANCE"]
    assert consume_events and int(consume_events[0][3]) == 1
