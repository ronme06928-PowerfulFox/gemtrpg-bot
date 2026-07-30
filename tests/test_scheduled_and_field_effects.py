from manager.battle import scheduled_effects
from manager.game_logic import process_skill_effects


def _char(char_id, team, *, tags=None, hp=30, x=0):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": hp,
        "maxHp": 30,
        "x": x,
        "y": 0,
        "tag_ids": list(tags or []),
        "states": [],
        "params": [],
        "special_buffs": [],
    }


def test_schedule_effect_is_idempotent_and_executes_when_source_is_dead(monkeypatch):
    actor = _char("boss", "enemy")
    schedule = {
        "timing": "RESOLVE_START",
        "type": "SCHEDULE_EFFECT",
        "target": "self",
        "round_offset": 1,
        "repeat_count": 2,
        "effect": {
            "type": "SUMMON_CHARACTER",
            "summon_template_id": "U-02",
        },
    }
    context = {
        "characters": [actor],
        "room_state": {"round": 1, "characters": [actor]},
        "battle_state": {"round": 1},
        "round": 1,
        "source_slot_id": "boss:r1:s0",
        "actor_skill_data": {"id": "E-34"},
    }

    _, _, changes = process_skill_effects(
        [schedule],
        "RESOLVE_START",
        actor,
        actor,
        context=context,
    )

    assert len(changes) == 1
    assert changes[0][1] == "SCHEDULE_EFFECT"
    state = context["room_state"]
    assert scheduled_effects.apply_schedule_change(state, actor, changes[0][3]) is True
    assert scheduled_effects.apply_schedule_change(state, actor, changes[0][3]) is False

    calls = []

    def _fake_summon(_room, _state, source, payload):
        calls.append((source.get("id"), payload.get("summon_template_id")))
        return {"ok": True}

    monkeypatch.setattr(
        "manager.summons.service.apply_summon_change",
        _fake_summon,
    )
    actor["hp"] = 0

    first = scheduled_effects.execute_scheduled_effects(state, 2, room="room")
    second = scheduled_effects.execute_scheduled_effects(state, 2, room="room")

    assert first == {"executed": 1, "summoned": 2, "failed": 0}
    assert second == {"executed": 0, "summoned": 0, "failed": 0}
    assert calls == [("boss", "U-02"), ("boss", "U-02")]


def test_filtered_character_damage_and_count_buff_share_pre_damage_snapshot():
    actor = _char("boss", "enemy")
    rubble_a = _char("rubble-a", "enemy", tags=["瓦礫"])
    rubble_b = _char("rubble-b", "enemy", tags=["瓦礫"])
    other_team = _char("other-team", "ally", tags=["瓦礫"])
    disabled_tag = _char("disabled-tag", "enemy", tags=["瓦礫"])
    disabled_tag["disabled_tag_ids"] = ["瓦礫"]
    filter_data = {
        "team": "same_team",
        "required_tag_ids": ["瓦礫"],
        "alive": True,
        "placed": True,
    }
    effects = [
        {
            "timing": "RESOLVE_START",
            "type": "CUSTOM_EFFECT",
            "target": "FILTERED_CHARACTERS",
            "value": "DEAL_TARGET_MAX_HP_DAMAGE",
            "character_filter": filter_data,
        },
        {
            "timing": "RESOLVE_START",
            "type": "APPLY_BUFF_FROM_CHARACTER_COUNT",
            "target": "self",
            "buff_name": "瓦礫吸収",
            "lasting": 1,
            "delay": 0,
            "value_per_character": 1,
            "character_filter": filter_data,
        },
    ]
    characters = [actor, rubble_a, rubble_b, other_team, disabled_tag]

    _, _, changes = process_skill_effects(
        effects,
        "RESOLVE_START",
        actor,
        None,
        context={"characters": characters, "actor_skill_data": {"id": "E-33"}},
    )

    damage = [change for change in changes if change[1] == "CUSTOM_DAMAGE"]
    buffs = [change for change in changes if change[1] == "APPLY_BUFF"]
    assert {change[0]["id"] for change in damage} == {"rubble-a", "rubble-b"}
    assert [change[3] for change in damage] == [30, 30]
    assert len(buffs) == 1
    assert buffs[0][0]["id"] == "boss"
    assert buffs[0][3]["lasting"] == 1
    assert buffs[0][3]["delay"] == 0
    assert buffs[0][3]["data"]["power_bonus"][0]["value"] == 2


def test_filtered_character_count_zero_does_not_apply_buff():
    actor = _char("boss", "enemy")
    effect = {
        "timing": "RESOLVE_START",
        "type": "APPLY_BUFF_FROM_CHARACTER_COUNT",
        "target": "self",
        "buff_name": "瓦礫吸収",
        "character_filter": {
            "team": "same_team",
            "required_tag_ids": ["瓦礫"],
        },
    }

    _, _, changes = process_skill_effects(
        [effect],
        "RESOLVE_START",
        actor,
        actor,
        context={"characters": [actor]},
    )

    assert changes == []
