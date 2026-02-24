import copy

from manager.battle import common_manager
from manager.game_logic import process_skill_effects
from manager.summons import service as summon_service


def test_process_skill_effects_emits_summon_change():
    actor = {"id": "A", "name": "Caster", "type": "ally", "hp": 20, "states": [], "params": []}
    target = {"id": "B", "name": "Target", "type": "enemy", "hp": 20, "states": [], "params": []}
    effects = [
        {
            "timing": "HIT",
            "type": "SUMMON_CHARACTER",
            "summon_template_id": "SMN-01",
            "summon_duration_mode": "duration_rounds",
            "summon_duration": 2,
        }
    ]

    _, _, changes = process_skill_effects(
        effects,
        "HIT",
        actor,
        target,
        context={"characters": [actor, target], "room": "room_test"},
    )

    summon_changes = [c for c in changes if c[1] == "SUMMON_CHARACTER"]
    assert len(summon_changes) == 1
    assert summon_changes[0][3]["summon_template_id"] == "SMN-01"
    assert int(summon_changes[0][3]["summon_duration"]) == 2


def test_process_skill_effects_summon_does_not_override_template_duration_when_unspecified():
    actor = {"id": "A", "name": "Caster", "type": "ally", "hp": 20, "states": [], "params": []}
    target = {"id": "B", "name": "Target", "type": "enemy", "hp": 20, "states": [], "params": []}
    effects = [
        {
            "timing": "HIT",
            "type": "SUMMON_CHARACTER",
            "summon_template_id": "SMN-01",
        }
    ]

    _, _, changes = process_skill_effects(
        effects,
        "HIT",
        actor,
        target,
        context={"characters": [actor, target], "room": "room_test"},
    )

    summon_changes = [c for c in changes if c[1] == "SUMMON_CHARACTER"]
    assert len(summon_changes) == 1
    payload = summon_changes[0][3]
    assert payload["summon_template_id"] == "SMN-01"
    assert "summon_duration_mode" not in payload
    assert "summon_duration" not in payload


def test_apply_summon_change_uses_template_skills_and_passives(monkeypatch):
    template = {
        "name": "Test Summon",
        "type": "enemy",
        "hp": 10,
        "maxHp": 10,
        "mp": 3,
        "maxMp": 3,
        "params": [{"label": "速度", "value": "6"}],
        "states": [{"name": "FP", "value": 0}],
        "initial_skill_ids": ["T-SUM-01"],
        "SPassive": ["PA-01"],
        "summon_duration_mode": "duration_rounds",
        "summon_duration": 2,
    }

    monkeypatch.setattr(summon_service, "get_summon_template", lambda _tid: copy.deepcopy(template))
    monkeypatch.setattr(summon_service, "_apply_radiance_if_needed", lambda c: c)
    monkeypatch.setattr(summon_service, "all_skill_data", {"T-SUM-01": {"チャットパレット": "【T-SUM-01 召喚攻撃】 1+1d6"}})
    monkeypatch.setattr(summon_service, "_get_room_state_fallback", lambda _room: None)

    room_state = {
        "round": 5,
        "characters": [
            {
                "id": "actor_1",
                "name": "Summoner",
                "type": "ally",
                "x": 4,
                "y": 7,
                "owner": "alice",
                "owner_id": "user_alice",
                "states": [],
                "params": [],
                "special_buffs": [],
            }
        ],
        "character_owners": {"actor_1": "alice"},
    }
    actor = room_state["characters"][0]

    res = summon_service.apply_summon_change(
        "room_t",
        room_state,
        actor,
        {"summon_template_id": "SMN-T"},
    )

    assert res["ok"] is True
    new_char = res["char"]
    assert new_char["is_summoned"] is True
    assert new_char["name"] == "Test Summon"
    assert new_char["type"] == "ally"
    assert new_char["can_act_from_round"] == 6
    assert new_char["summon_duration_mode"] == "duration_rounds"
    assert new_char["remaining_summon_rounds"] == 2
    assert new_char["SPassive"] == ["PA-01"]
    assert "T-SUM-01" in new_char["commands"]
    assert room_state["character_owners"][new_char["id"]] == "alice"


def test_apply_summon_change_ignores_empty_duration_override(monkeypatch):
    template = {
        "name": "Test Summon",
        "type": "enemy",
        "hp": 10,
        "maxHp": 10,
        "mp": 0,
        "maxMp": 0,
        "params": [{"label": "速度", "value": "3"}],
        "states": [{"name": "FP", "value": 0}],
        "summon_duration_mode": "duration_rounds",
        "summon_duration": 3,
    }

    monkeypatch.setattr(summon_service, "get_summon_template", lambda _tid: copy.deepcopy(template))
    monkeypatch.setattr(summon_service, "_apply_radiance_if_needed", lambda c: c)
    monkeypatch.setattr(summon_service, "_get_room_state_fallback", lambda _room: None)

    room_state = {
        "round": 1,
        "characters": [
            {
                "id": "actor_1",
                "name": "Summoner",
                "type": "ally",
                "x": 0,
                "y": 0,
                "owner": "alice",
                "owner_id": "user_alice",
                "states": [],
                "params": [],
                "special_buffs": [],
            }
        ],
        "character_owners": {"actor_1": "alice"},
    }
    actor = room_state["characters"][0]

    res = summon_service.apply_summon_change(
        "room_t",
        room_state,
        actor,
        {
            "summon_template_id": "SMN-T",
            "summon_duration_mode": None,
            "summon_duration": None,
        },
    )

    assert res["ok"] is True
    new_char = res["char"]
    assert new_char["summon_duration_mode"] == "duration_rounds"
    assert new_char["remaining_summon_rounds"] == 3


def test_apply_summon_change_rejects_same_team_duplicate_when_disallowed(monkeypatch):
    template = {
        "name": "Limited Summon",
        "type": "enemy",
        "hp": 10,
        "maxHp": 10,
        "mp": 0,
        "maxMp": 0,
        "params": [{"label": "速度", "value": "3"}],
        "states": [{"name": "FP", "value": 0}],
        "allow_duplicate_same_team": False,
        "summon_duration_mode": "permanent",
        "summon_duration": 0,
    }

    monkeypatch.setattr(summon_service, "get_summon_template", lambda _tid: copy.deepcopy(template))
    monkeypatch.setattr(summon_service, "_apply_radiance_if_needed", lambda c: c)
    monkeypatch.setattr(summon_service, "_get_room_state_fallback", lambda _room: None)

    room_state = {
        "round": 1,
        "characters": [
            {
                "id": "actor_1",
                "name": "Summoner",
                "type": "ally",
                "x": 0,
                "y": 0,
                "owner": "alice",
                "owner_id": "user_alice",
                "states": [],
                "params": [],
                "special_buffs": [],
            },
            {
                "id": "summon_existing",
                "name": "Limited Summon",
                "type": "ally",
                "hp": 5,
                "is_summoned": True,
                "summon_template_id": "SMN-T",
            },
        ],
        "character_owners": {"actor_1": "alice", "summon_existing": "alice"},
    }
    actor = room_state["characters"][0]

    res = summon_service.apply_summon_change(
        "room_t",
        room_state,
        actor,
        {"summon_template_id": "SMN-T"},
    )

    assert res["ok"] is False
    assert res["char"] is None


def test_process_summon_round_end_skips_summon_turn_and_expires_later():
    state = {
        "round": 3,
        "characters": [
            {
                "id": "sm_1",
                "name": "Summon",
                "is_summoned": True,
                "summoned_round": 3,
                "summon_duration_mode": "duration_rounds",
                "remaining_summon_rounds": 1,
            }
        ],
        "character_owners": {"sm_1": "alice"},
    }

    removed_now = summon_service.process_summon_round_end(state, room="room_t")
    assert removed_now == []
    assert state["characters"][0]["remaining_summon_rounds"] == 1

    state["round"] = 4
    removed_next = summon_service.process_summon_round_end(state, room="room_t")
    assert len(removed_next) == 1
    assert state["characters"] == []
    assert "sm_1" not in state["character_owners"]


def test_select_resolve_round_start_skips_summon_until_can_act(monkeypatch):
    state = {
        "round": 1,
        "characters": [
            {
                "id": "actor_alive",
                "name": "Alive",
                "type": "ally",
                "hp": 10,
                "x": 0,
                "y": 0,
                "params": [{"label": "速度", "value": 6}],
                "states": [{"name": "FP", "value": 0}],
                "special_buffs": [],
            },
            {
                "id": "actor_summon",
                "name": "Summon",
                "type": "ally",
                "hp": 10,
                "x": 1,
                "y": 0,
                "params": [{"label": "速度", "value": 6}],
                "states": [{"name": "FP", "value": 0}],
                "special_buffs": [],
                "is_summoned": True,
                "can_act_from_round": 2,
            },
        ],
        "battle_state": {},
    }

    monkeypatch.setattr(common_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_manager, "save_specific_room_state", lambda _room: None)
    monkeypatch.setattr(common_manager, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(common_manager, "roll_dice", lambda _expr: {"total": 3})

    payload = common_manager.process_select_resolve_round_start("room_t", "battle_room_t", round_value=1)
    slots = payload.get("slots", {})
    actor_ids = {s.get("actor_id") for s in slots.values()}
    assert "actor_alive" in actor_ids
    assert "actor_summon" not in actor_ids
