from manager.battle.condition_eval import check_condition
from manager.battle import resolve_effect_runtime
from manager.game_logic import process_skill_effects


def test_string_equals_and_contains_use_character_names():
    actor = {"name": "ボス", "baseName": "鋼喰らい"}
    target = {"name": "瓦礫 [2]", "baseName": "前文明の瓦礫"}

    assert check_condition(
        {"source": "target", "param": "name", "operator": "EQUALS", "value": "瓦礫 [2]"},
        actor,
        target,
    )
    assert check_condition(
        {"source": "target", "param": "baseName", "operator": "CONTAINS", "value": "瓦礫"},
        actor,
        target,
    )
    assert not check_condition(
        {"source": "target", "param": "name", "operator": "EQUALS", "value": "瓦礫"},
        actor,
        target,
    )


def test_tag_contains_uses_only_effective_tags_and_exact_elements():
    target = {
        "tag_ids": ["種別:瓦礫", "機械"],
        "disabled_tag_ids": ["機械"],
    }

    assert check_condition(
        {"source": "target", "param": "tag_ids", "operator": "CONTAINS", "value": "種別:瓦礫"},
        {},
        target,
    )
    assert not check_condition(
        {"source": "target", "param": "tag_ids", "operator": "CONTAINS", "value": "瓦礫"},
        {},
        target,
    )
    assert not check_condition(
        {"source": "target", "param": "tag_ids", "operator": "CONTAINS", "value": "機械"},
        {},
        target,
    )


def test_numeric_conditions_keep_existing_comparison_behavior():
    target = {"HP": "05"}
    get_status = lambda char, name: char.get(name)

    assert check_condition(
        {"source": "target", "param": "HP", "operator": "EQUALS", "value": 5},
        {},
        target,
        get_status_value_fn=get_status,
    )
    assert check_condition(
        {"source": "target", "param": "HP", "operator": "GTE", "value": "4"},
        {},
        target,
        get_status_value_fn=get_status,
    )
    assert not check_condition(
        {"source": "target", "param": "HP", "operator": "CONTAINS", "value": 5},
        {},
        {"HP": 5},
        get_status_value_fn=get_status,
    )


def test_max_hp_damage_custom_effect_emits_full_max_hp_damage():
    actor = {"id": "boss", "name": "ボス"}
    target = {"id": "rubble", "name": "瓦礫", "hp": 12, "maxHp": 30}
    effects = [{
        "timing": "HIT",
        "type": "CUSTOM_EFFECT",
        "target": "target",
        "value": "DEAL_TARGET_MAX_HP_DAMAGE",
    }]

    _, logs, changes = process_skill_effects(effects, "HIT", actor, target)

    assert changes == [(target, "CUSTOM_DAMAGE", "DEAL_TARGET_MAX_HP_DAMAGE", 30)]
    assert any("瓦礫に30ダメージ" in line for line in logs)


def test_max_hp_damage_is_applied_immediately_without_primary_damage_multiplier(monkeypatch):
    actor = {"id": "boss", "name": "ボス"}
    target = {"id": "rubble", "name": "瓦礫", "hp": 12, "maxHp": 30}
    calls = []

    def fake_update(room, char, stat, new_value, **kwargs):
        calls.append((room, char, stat, new_value, kwargs))
        char["hp"] = max(0, int(new_value))

    monkeypatch.setattr(resolve_effect_runtime, "_update_char_stat", fake_update)
    changes = [(target, "CUSTOM_DAMAGE", "DEAL_TARGET_MAX_HP_DAMAGE", 30)]

    extra = resolve_effect_runtime._apply_effect_changes_like_duel(
        "room",
        {"characters": [actor, target]},
        changes,
        actor,
        target,
        10,
        [],
        attacker_skill_data={"id": "Boss-Absorb"},
    )

    assert extra == 0
    assert target["hp"] == 0
    assert calls[0][3] == 0
    context = calls[0][4]["damage_context"]
    assert context["actor"] is actor
    assert context["skill_id"] == "Boss-Absorb"
    assert context["damage_type"] == "skill_effect"


def test_max_hp_damage_safely_ignores_missing_or_invalid_max_hp():
    actor = {"id": "boss"}
    effects = [{
        "timing": "HIT",
        "type": "CUSTOM_EFFECT",
        "target": "target",
        "value": "DEAL_TARGET_MAX_HP_DAMAGE",
    }]

    for target in ({"id": "missing"}, {"id": "zero", "maxHp": 0}, {"id": "invalid", "maxHp": "x"}):
        _, logs, changes = process_skill_effects(effects, "HIT", actor, target)
        assert logs == []
        assert changes == []
