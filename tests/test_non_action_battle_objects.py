from events.battle import pve_intents
from manager.battle import resolve_queue_helpers
from manager.battle import select_resolve_state
from manager.battle.action_slot_mode import (
    build_target_only_slot,
    get_action_unavailable_reason,
    get_action_slot_mode,
)
from manager.game_logic import process_skill_effects


def _character(char_id, team, *, passive_data=None, summoned=False):
    char = {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": 30,
        "maxHp": 30,
        "x": 0,
        "y": 0,
        "states": [],
        "params": [],
        "special_buffs": [],
        "flags": {},
    }
    if passive_data:
        char["special_buffs"].append(
            {"name": "passive", "lasting": -1, "delay": 0, "data": passive_data}
        )
    if summoned:
        char.update({"is_summoned": True, "can_act_from_round": 2})
    return char


def test_action_slot_mode_is_read_from_passive_effect_data():
    rubble = _character("rubble", "ally", passive_data={"action_slot_mode": "none"})

    assert get_action_slot_mode(rubble) == "none"
    anchor = build_target_only_slot(rubble, 1)
    assert anchor["target_only"] is True
    assert anchor["source_disabled"] is True
    assert anchor["initiative"] is None


def test_confusion_is_reported_as_action_unavailable_without_losing_targetability():
    actor = _character("actor", "ally")
    actor["special_buffs"].append({"buff_id": "Bu-02", "lasting": 1, "delay": 0})

    assert get_action_unavailable_reason(actor) == "confusion"


def test_round_start_creates_target_anchor_without_action_slot(monkeypatch):
    actor = _character("actor", "ally")
    rubble = _character(
        "rubble",
        "ally",
        passive_data={"action_slot_mode": "none"},
        summoned=True,
    )
    room_state = {
        "round": 1,
        "battle_mode": "pvp",
        "characters": [actor, rubble],
        "timeline": [],
    }
    monkeypatch.setattr(select_resolve_state, "get_room_state", lambda _room: room_state)
    monkeypatch.setattr(select_resolve_state, "save_specific_room_state", lambda _room: None)
    monkeypatch.setattr(select_resolve_state, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(select_resolve_state, "roll_dice", lambda _expr: {"total": 3})

    result = select_resolve_state.process_select_resolve_round_start("room", "battle", 1)

    action_slots = [slot for slot in result["slots"].values() if not slot.get("target_only")]
    target_slots = [slot for slot in result["slots"].values() if slot.get("target_only")]
    assert [slot["actor_id"] for slot in action_slots] == ["actor"]
    assert [slot["actor_id"] for slot in target_slots] == ["rubble"]
    assert result["timeline"] == [action_slots[0]["slot_id"]]

    battle_state = room_state["battle_state"]
    battle_state["intents"] = {
        action_slots[0]["slot_id"]: {"tags": {"mass_type": None, "instant": False}}
    }
    resolve_queue_helpers._build_resolve_queues(battle_state)
    assert battle_state["resolve"]["single_queue"] == [action_slots[0]["slot_id"]]

    required = pve_intents._required_slots(
        "room",
        battle_state,
        get_room_state_fn=lambda _room: room_state,
        is_actor_actionable_fn=lambda _room, _actor: True,
    )
    assert required == {action_slots[0]["slot_id"]}


def test_pve_default_target_can_select_target_only_anchor():
    enemy = _character("enemy", "enemy")
    rubble = _character("rubble", "ally", passive_data={"action_slot_mode": "none"})
    enemy_slot = {
        "slot_id": "enemy:r1:s0",
        "actor_id": "enemy",
        "team": "enemy",
        "initiative": 8,
    }
    anchor = build_target_only_slot(rubble, 1)
    battle_state = {
        "slots": {enemy_slot["slot_id"]: enemy_slot, anchor["slot_id"]: anchor},
        "characters": [enemy, rubble],
    }
    room_state = {"characters": [enemy, rubble]}

    selected = pve_intents._pick_default_pve_enemy_target_slot(
        "room",
        battle_state,
        enemy_slot["slot_id"],
        get_room_state_fn=lambda _room: room_state,
    )

    assert selected == anchor["slot_id"]


def test_death_context_targets_killer_or_living_killer_team():
    rubble = _character("rubble", "enemy")
    rubble["hp"] = 0
    killer = _character("killer", "ally")
    ally = _character("ally", "ally")
    unplaced = _character("unplaced", "ally")
    unplaced["x"] = -1
    enemy = _character("enemy", "enemy")
    effects = [
        {
            "timing": "IMMEDIATE",
            "type": "APPLY_BUFF",
            "target": "KILLER_TEAM",
            "buff_id": "Bu-51",
            "lasting": 2,
            "delay": 1,
            "condition": {
                "source": "death_context",
                "param": "killer_team",
                "operator": "EQUALS",
                "value": "ally",
            },
        },
        {
            "timing": "IMMEDIATE",
            "type": "APPLY_BUFF",
            "target": "KILLER",
            "buff_id": "Bu-52",
            "lasting": 3,
            "delay": 1,
            "condition": {
                "source": "death_context",
                "param": "killer_team",
                "operator": "EQUALS",
                "value": "enemy",
            },
        },
    ]
    context = {
        "characters": [rubble, killer, ally, unplaced, enemy],
        "death_context": {"actor": killer, "skill_id": "SKILL-1"},
    }

    _, _, changes = process_skill_effects(
        effects,
        "IMMEDIATE",
        rubble,
        killer,
        context=context,
    )

    buff_changes = [change for change in changes if change[1] == "APPLY_BUFF"]
    assert {change[0]["id"] for change in buff_changes} == {"killer", "ally"}
    assert {change[2] for change in buff_changes} == {"鉄の恩恵"}
    assert all(change[3]["lasting"] == 2 and change[3]["delay"] == 1 for change in buff_changes)


def test_death_context_without_skill_does_not_trigger_killer_branch():
    rubble = _character("rubble", "ally")
    killer = _character("killer", "enemy")
    effect = {
        "timing": "IMMEDIATE",
        "type": "APPLY_BUFF",
        "target": "KILLER",
        "buff_id": "Bu-52",
        "lasting": 3,
        "delay": 1,
        "condition": {
            "source": "death_context",
            "param": "killer_team",
            "operator": "EQUALS",
            "value": "enemy",
        },
    }

    _, _, changes = process_skill_effects(
        [effect],
        "IMMEDIATE",
        rubble,
        killer,
        context={
            "characters": [rubble, killer],
            "death_context": {"actor": killer},
        },
    )

    assert changes == []
