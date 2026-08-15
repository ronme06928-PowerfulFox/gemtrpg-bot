from manager.battle import common_manager as battle_common
from manager.battle import pve_intent_planner


def _make_char(
    char_id,
    team,
    flags=None,
    speed=6,
    action_count=1,
    tag_ids=None,
    disabled_tag_ids=None,
):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": 100,
        "maxHp": 100,
        "mp": 50,
        "maxMp": 50,
        "x": 1,
        "y": 1,
        "is_escaped": False,
        "params": [
            {"label": "敏捷", "value": int(speed)},
            {"label": "行動回数", "value": int(action_count)},
        ],
        "states": [],
        "special_buffs": [],
        "flags": dict(flags or {}),
        "commands": "",
        "tag_ids": list(tag_ids or []),
        "disabled_tag_ids": list(disabled_tag_ids or []),
    }


def _base_state(mode="pve", enemy_flags=None):
    ally = _make_char("A1", "ally")
    enemy = _make_char("E1", "enemy", flags=enemy_flags)
    return {
        "round": 0,
        "battle_mode": mode,
        "characters": [ally, enemy],
        "timeline": [],
        "ai_target_arrows": [],
        "battle_state": {
            "battle_id": "battle_room_t",
            "round": 0,
            "phase": "round_end",
            "slots": {},
            "timeline": [],
            "tiebreak": [],
            "intents": {},
            "resolve_snapshot_intents": {},
            "resolve_snapshot_at": None,
            "redirects": [],
            "resolve_ready": False,
            "resolve_ready_info": {},
            "resolve": {
                "mass_queue": [],
                "single_queue": [],
                "resolved_slots": [],
                "trace": [],
            },
        },
    }


def _slot_id_for_actor(state, actor_id):
    for slot_id, slot in (state.get("battle_state", {}).get("slots", {}) or {}).items():
        if str(slot.get("actor_id")) == str(actor_id):
            return slot_id
    return None


def _slot_ids_for_actor(state, actor_id):
    rows = []
    for slot_id, slot in (state.get("battle_state", {}).get("slots", {}) or {}).items():
        if str(slot.get("actor_id")) != str(actor_id):
            continue
        if slot.get("target_only", False):
            continue
        rows.append((
            int(slot.get("index_in_actor", 0) or 0),
            slot_id,
        ))
    rows.sort()
    return [slot_id for _, slot_id in rows]


def _patch_step_skill_catalog(monkeypatch, catalog):
    monkeypatch.setattr(battle_common, "all_skill_data", catalog)
    monkeypatch.setattr(
        battle_common,
        "list_usable_skill_ids",
        lambda _char, allow_instant=False: list(catalog),
    )


def test_select_resolve_round_start_pve_auto_commits_enemy_when_auto_skill_enabled(monkeypatch):
    state = _base_state(mode="pve", enemy_flags={"auto_skill_select": True})
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AUTO")

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    ally_slot_id = _slot_id_for_actor(state, "A1")
    assert enemy_slot_id
    assert ally_slot_id

    enemy_intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert enemy_intent.get("skill_id") == "S-AUTO"
    assert enemy_intent.get("committed") is True
    assert enemy_intent.get("committed_by") == "AI:PVE"
    assert enemy_intent.get("target", {}).get("type") == "single_slot"
    assert enemy_intent.get("target", {}).get("slot_id") == ally_slot_id

    arrows = state.get("ai_target_arrows", [])
    assert len(arrows) == 1
    assert arrows[0].get("from_id") == "E1"
    assert arrows[0].get("to_id") == "A1"


def test_select_resolve_round_start_pve_auto_commits_enemy_when_show_planned_enabled(monkeypatch):
    state = _base_state(mode="pve", enemy_flags={"show_planned_skill": True})
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-PLAN")

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    assert enemy_slot_id
    enemy_intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert enemy_intent.get("skill_id") == "S-PLAN"
    assert enemy_intent.get("committed") is True
    assert enemy_intent.get("committed_by") == "AI:PVE"


def test_select_resolve_round_start_pve_logs_target_and_planned_skill(monkeypatch):
    state = _base_state(mode="pve", enemy_flags={"show_planned_skill": True})
    logs = []

    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(
        battle_common,
        "broadcast_log",
        lambda room, message, log_type="info": logs.append((room, message, log_type)),
    )
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-PLAN")
    monkeypatch.setattr(
        battle_common,
        "all_skill_data",
        {"S-PLAN": {"name": "プラン技能"}},
    )

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    preview_logs = [entry for entry in logs if "[PvE行動予告]" in entry[1]]
    assert len(preview_logs) == 1
    assert "E1#1" in preview_logs[0][1]
    assert "A1#1" in preview_logs[0][1]
    assert "[S-PLAN] プラン技能" in preview_logs[0][1]
    assert state.get("_pve_preview_log_round") == 1


def test_select_resolve_round_start_pve_preview_log_is_not_duplicated_in_same_round(monkeypatch):
    state = _base_state(mode="pve", enemy_flags={"show_planned_skill": True})
    logs = []

    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(
        battle_common,
        "broadcast_log",
        lambda room, message, log_type="info": logs.append((room, message, log_type)),
    )
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-PLAN")

    first = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )
    second = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert first is not None
    assert second is not None
    preview_logs = [entry for entry in logs if "[PvE行動予告]" in entry[1]]
    assert len(preview_logs) == 1


def test_select_resolve_round_start_pve_sets_enemy_target_without_commit_when_auto_skill_disabled(monkeypatch):
    state = _base_state(mode="pve", enemy_flags={})
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(
        battle_common,
        "ai_suggest_skill",
        lambda _char: (_ for _ in ()).throw(AssertionError("ai_suggest_skill should not be called")),
    )

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    ally_slot_id = _slot_id_for_actor(state, "A1")
    assert enemy_slot_id
    assert ally_slot_id

    enemy_intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert enemy_intent.get("skill_id") is None
    assert enemy_intent.get("committed") is False
    assert enemy_intent.get("target", {}).get("type") == "single_slot"
    assert enemy_intent.get("target", {}).get("slot_id") == ally_slot_id

    arrows = state.get("ai_target_arrows", [])
    assert len(arrows) == 1
    assert arrows[0].get("from_id") == "E1"
    assert arrows[0].get("to_id") == "A1"


def test_select_resolve_round_start_pve_respects_auto_target_disable(monkeypatch):
    state = _base_state(mode="pve", enemy_flags={"auto_target_select": False, "auto_skill_select": True})
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AUTO")

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    assert enemy_slot_id
    assert enemy_slot_id not in state["battle_state"]["intents"]
    assert state.get("ai_target_arrows", []) == []


def test_select_resolve_round_start_pvp_does_not_apply_pve_auto_intents(monkeypatch):
    state = _base_state(mode="pvp", enemy_flags={"auto_skill_select": True})
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AUTO")

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    assert state["battle_state"]["intents"] == {}
    assert state.get("ai_target_arrows", []) == []


def test_select_resolve_round_start_behavior_profile_is_prioritized(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{"actions": ["S-BHV"]}],
                "transitions": [],
            }
        },
    }
    state = _base_state(mode="pve", enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile})
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AI")
    monkeypatch.setattr(battle_common, "all_skill_data", {"S-BHV": {"name": "BehaviorSkill"}})

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert intent.get("skill_id") == "S-BHV"
    assert intent.get("committed") is True

    runtime = state["battle_state"].get("behavior_runtime", {}).get("E1", {})
    assert runtime.get("active_loop_id") == "phase_1"
    assert runtime.get("last_skill_ids") == ["S-BHV"]


def test_select_resolve_round_start_behavior_profile_step_next_loop_transition(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-P1"],
                    "next_loop_id": "phase_2",
                }],
                "transitions": [],
            },
            "phase_2": {
                "repeat": True,
                "steps": [{"actions": ["S-P2"]}],
                "transitions": [],
            },
        },
    }
    state = _base_state(mode="pve", enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile})
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(
        battle_common,
        "all_skill_data",
        {
            "S-P1": {"name": "Phase1Skill"},
            "S-P2": {"name": "Phase2Skill"},
        },
    )

    first = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )
    assert first is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    first_intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert first_intent.get("skill_id") == "S-P1"

    runtime_after_first = state["battle_state"].get("behavior_runtime", {}).get("E1", {})
    assert runtime_after_first.get("active_loop_id") == "phase_2"
    assert int(runtime_after_first.get("step_index", -1)) == 0

    second = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=2,
    )
    assert second is not None
    enemy_slot_id_round2 = _slot_id_for_actor(state, "E1")
    second_intent = state["battle_state"]["intents"].get(enemy_slot_id_round2, {})
    assert second_intent.get("skill_id") == "S-P2"


def test_select_resolve_round_start_behavior_profile_fallbacks_to_ai(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{"actions": ["UNKNOWN_SKILL"]}],
                "transitions": [],
            }
        },
    }
    state = _base_state(mode="pve", enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile})
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AI")
    monkeypatch.setattr(battle_common, "all_skill_data", {"S-AI": {"name": "AutoSkill"}})

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert intent.get("skill_id") == "S-AI"
    assert intent.get("committed") is True


def test_step_actions_generates_one_slot_per_nonempty_action(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "initial_loop_id": "main",
        "loops": {
            "main": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-ONE", "", "S-TWO"],
                    "targets": ["target_enemy_random", "target_enemy_random", "target_enemy_random"],
                }],
                "transitions": [],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )
    state["characters"][1]["params"][1]["value"] = 1
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    _patch_step_skill_catalog(
        monkeypatch,
        {"S-ONE": {"name": "One"}, "S-TWO": {"name": "Two"}},
    )

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    enemy_slots = _slot_ids_for_actor(state, "E1")
    assert len(enemy_slots) == 2
    assert [
        state["battle_state"]["intents"][slot_id]["skill_id"]
        for slot_id in enemy_slots
    ] == ["S-ONE", "S-TWO"]


def test_normal_round_start_uses_step_action_count(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "initial_loop_id": "main",
        "loops": {
            "main": {
                "repeat": True,
                "steps": [{
                    "actions": ["E-31", "E-31", "E-34"],
                    "targets": ["target_enemy_random", "target_enemy_random", "target_enemy_random"],
                }],
                "transitions": [],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )
    monkeypatch.setattr(battle_common, "get_room_state", lambda _room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda _room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(battle_common, "broadcast_state_update", lambda _room: None)
    monkeypatch.setattr(battle_common, "emit_select_resolve_events", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(battle_common.random, "randint", lambda _a, _b: 1)
    _patch_step_skill_catalog(
        monkeypatch,
        {"E-31": {"name": "鉄根掌"}, "E-34": {"name": "暴れ回る"}},
    )

    assert battle_common.process_round_start("room_t", "GM") is True

    enemy_slots = [
        slot for slot in state["battle_state"]["slots"].values()
        if slot.get("actor_id") == "E1" and not slot.get("target_only", False)
    ]
    assert len(enemy_slots) == 3
    enemy_slots.sort(key=lambda slot: int(slot.get("behavior_plan_index", -1)))
    assert [
        state["battle_state"]["intents"][slot["slot_id"]]["skill_id"]
        for slot in enemy_slots
    ] == ["E-31", "E-31", "E-34"]


def test_step_actions_ignores_character_action_count_and_creates_zero_action_anchor(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "initial_loop_id": "main",
        "loops": {
            "main": {
                "repeat": True,
                "steps": [
                    {"actions": []},
                    {"actions": ["S-NEXT"]},
                ],
                "transitions": [],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )
    state["characters"][1]["params"][1]["value"] = 3
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    _patch_step_skill_catalog(monkeypatch, {"S-NEXT": {"name": "Next"}})

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )
    assert _slot_ids_for_actor(state, "E1") == []
    idle_slot = state["battle_state"]["slots"]["E1:r1:idle"]
    assert idle_slot["target_only"] is True
    assert idle_slot["inactive_reason"] == "behavior_no_action"
    assert "E1:r1:idle" not in state["battle_state"]["timeline"]
    runtime = state["battle_state"]["behavior_runtime"]["E1"]
    assert runtime["step_index"] == 1

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=2,
    )
    assert len(_slot_ids_for_actor(state, "E1")) == 1


def test_step_actions_no_action_keeps_plan_alignment(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "initial_loop_id": "main",
        "loops": {
            "main": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-ONE", "__NO_ACTION__", "S-TWO"],
                    "targets": ["target_enemy_random"] * 3,
                }],
                "transitions": [],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    _patch_step_skill_catalog(
        monkeypatch,
        {"S-ONE": {"name": "One"}, "S-TWO": {"name": "Two"}},
    )

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    actor_slots = _slot_ids_for_actor(state, "E1")
    assert actor_slots == ["E1:r1:s0", "E1:r1:s2"]
    wait_slot = state["battle_state"]["slots"]["E1:r1:wait1"]
    assert wait_slot["target_only"] is True
    assert wait_slot["behavior_plan_index"] == 1
    assert state["battle_state"]["intents"]["E1:r1:s0"]["skill_id"] == "S-ONE"
    assert state["battle_state"]["intents"]["E1:r1:s2"]["skill_id"] == "S-TWO"


def test_step_actions_reuses_same_round_snapshot_without_advancing_twice(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "initial_loop_id": "main",
        "loops": {
            "main": {
                "repeat": True,
                "steps": [
                    {"actions": ["S-ONE"]},
                    {"actions": ["S-TWO"]},
                    {"actions": ["S-THREE"]},
                ],
                "transitions": [],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    _patch_step_skill_catalog(
        monkeypatch,
        {
            "S-ONE": {"name": "One"},
            "S-TWO": {"name": "Two"},
            "S-THREE": {"name": "Three"},
        },
    )

    for _ in range(2):
        battle_common.process_select_resolve_round_start(
            room="room_t",
            battle_id="battle_room_t",
            round_value=1,
        )

    runtime = state["battle_state"]["behavior_runtime"]["E1"]
    assert runtime["step_index"] == 1
    enemy_slot = _slot_ids_for_actor(state, "E1")[0]
    assert state["battle_state"]["intents"][enemy_slot]["skill_id"] == "S-ONE"


def test_step_actions_reuses_resolved_random_skill_and_target_in_same_round(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "initial_loop_id": "main",
        "loops": {
            "main": {
                "repeat": True,
                "steps": [{
                    "actions": ["__RANDOM_USABLE__"],
                    "targets": ["target_enemy_random"],
                }],
                "transitions": [],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )
    state["characters"].append(_make_char("A2", "ally"))
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    _patch_step_skill_catalog(
        monkeypatch,
        {"S-ONE": {"name": "One"}, "S-TWO": {"name": "Two"}},
    )
    monkeypatch.setattr(pve_intent_planner.random, "choice", lambda rows: rows[0])

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )
    enemy_slot = _slot_ids_for_actor(state, "E1")[0]
    first_intent = dict(state["battle_state"]["intents"][enemy_slot])
    first_target = dict(first_intent["target"])

    monkeypatch.setattr(pve_intent_planner.random, "choice", lambda rows: rows[-1])
    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )
    enemy_slot = _slot_ids_for_actor(state, "E1")[0]
    second_intent = state["battle_state"]["intents"][enemy_slot]

    assert first_intent["skill_id"] == "S-ONE"
    assert second_intent["skill_id"] == "S-ONE"
    assert second_intent["target"] == first_target


def test_step_actions_targets_non_action_rubble_anchor(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "initial_loop_id": "main",
        "loops": {
            "main": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-RUBBLE"],
                    "targets": [[{
                        "team": "same_team",
                        "required_tag_ids": ["瓦礫"],
                        "selection": "random",
                    }]],
                }],
                "transitions": [],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )
    rubble = _make_char(
        "R1",
        "enemy",
        flags={"action_slot_mode": "none", "auto_target_select": False},
        tag_ids=["瓦礫"],
    )
    state["characters"].append(rubble)
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    _patch_step_skill_catalog(
        monkeypatch,
        {"S-RUBBLE": {"name": "Rubble", "target_scope": "any"}},
    )

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    enemy_slot = _slot_ids_for_actor(state, "E1")[0]
    target_slot = state["battle_state"]["intents"][enemy_slot]["target"]["slot_id"]
    assert target_slot == "R1:r1:target"
    assert state["battle_state"]["slots"][target_slot]["target_only"] is True


def test_step_actions_no_target_marks_only_that_slot_cancelled(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "initial_loop_id": "main",
        "loops": {
            "main": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-NORMAL", "S-RUBBLE"],
                    "targets": [
                        "target_enemy_random",
                        [{
                            "team": "same_team",
                            "required_tag_ids": ["瓦礫"],
                            "selection": "random",
                        }],
                    ],
                    "on_no_target": ["cancel", "cancel"],
                }],
                "transitions": [],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    _patch_step_skill_catalog(
        monkeypatch,
        {
            "S-NORMAL": {"name": "Normal"},
            "S-RUBBLE": {"name": "Rubble", "target_scope": "any"},
        },
    )

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    first_slot, second_slot = _slot_ids_for_actor(state, "E1")
    assert state["battle_state"]["slots"][first_slot]["disabled"] is False
    assert state["battle_state"]["intents"][first_slot]["cancelled"] is False

    cancelled_slot = state["battle_state"]["slots"][second_slot]
    cancelled_intent = state["battle_state"]["intents"][second_slot]
    assert cancelled_slot["disabled"] is True
    assert cancelled_slot["status"] == "cancelled"
    assert cancelled_slot["cancelled_without_use"] is True
    assert cancelled_intent["skill_id"] == "S-RUBBLE"
    assert cancelled_intent["committed"] is True
    assert cancelled_intent["cancelled"] is True
    assert cancelled_intent["cancel_reason"] == "no_target"
    assert cancelled_intent["target"]["slot_id"] is None
    assert state["battle_state"]["resolve"]["cancelled_slots"] == [second_slot]


def test_step_actions_unknown_skill_cancels_without_ai_fallback(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "initial_loop_id": "main",
        "loops": {
            "main": {
                "repeat": True,
                "steps": [{"actions": ["UNKNOWN_SKILL"]}],
                "transitions": [],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(
        battle_common,
        "ai_suggest_skill",
        lambda _char: (_ for _ in ()).throw(AssertionError("AI fallback must not run")),
    )
    monkeypatch.setattr(battle_common, "all_skill_data", {})

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    enemy_slot = _slot_ids_for_actor(state, "E1")[0]
    intent = state["battle_state"]["intents"][enemy_slot]
    assert intent["skill_id"] == "UNKNOWN_SKILL"
    assert intent["cancelled"] is True
    assert intent["cancel_reason"] == "skill_unavailable"


def test_step_actions_known_but_unusable_skill_is_cancelled(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "slot_generation_mode": "step_actions",
        "initial_loop_id": "main",
        "loops": {
            "main": {
                "repeat": True,
                "steps": [{"actions": ["S-SEALED"]}],
                "transitions": [],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(
        battle_common,
        "ai_suggest_skill",
        lambda _char: (_ for _ in ()).throw(AssertionError("AI fallback must not run")),
    )
    monkeypatch.setattr(
        battle_common,
        "all_skill_data",
        {"S-SEALED": {"name": "Sealed"}},
    )
    monkeypatch.setattr(
        battle_common,
        "list_usable_skill_ids",
        lambda _char, allow_instant=False: [],
    )

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    enemy_slot = _slot_ids_for_actor(state, "E1")[0]
    intent = state["battle_state"]["intents"][enemy_slot]
    assert intent["skill_id"] == "S-SEALED"
    assert intent["cancelled"] is True
    assert intent["cancel_reason"] == "skill_unavailable"


def test_select_resolve_round_start_behavior_profile_random_usable_token(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{"actions": ["__RANDOM_USABLE__"]}],
                "transitions": [],
            }
        },
    }
    state = _base_state(mode="pve", enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile})
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(
        battle_common,
        "ai_suggest_skill",
        lambda _char: (_ for _ in ()).throw(AssertionError("ai_suggest_skill should not be called")),
    )
    monkeypatch.setattr(battle_common, "list_usable_skill_ids", lambda _char, allow_instant=False: ["S-RND"])
    monkeypatch.setattr(battle_common, "all_skill_data", {"S-RND": {"name": "RandomUsable"}})

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert intent.get("skill_id") == "S-RND"
    assert intent.get("committed") is True

    runtime = state["battle_state"].get("behavior_runtime", {}).get("E1", {})
    assert runtime.get("last_skill_ids") == ["S-RND"]


def test_select_resolve_round_start_behavior_profile_random_usable_fallbacks_to_ai(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{"actions": ["__RANDOM_USABLE__"]}],
                "transitions": [],
            }
        },
    }
    state = _base_state(mode="pve", enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile})
    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "list_usable_skill_ids", lambda _char, allow_instant=False: [])
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AI")
    monkeypatch.setattr(battle_common, "all_skill_data", {"S-AI": {"name": "AutoSkill"}})

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert intent.get("skill_id") == "S-AI"
    assert intent.get("committed") is True


def test_select_resolve_round_start_behavior_profile_targets_enemy_fastest(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-BHV"],
                    "targets": ["target_enemy_fastest"],
                }],
                "transitions": [],
            }
        },
    }
    ally_fast = _make_char("A_FAST", "ally", speed=30)
    ally_slow = _make_char("A_SLOW", "ally", speed=6)
    enemy_main = _make_char("E1", "enemy", flags={"auto_skill_select": True, "behavior_profile": behavior_profile}, speed=12)
    enemy_side = _make_char("E2", "enemy", flags={"auto_target_select": False}, speed=8)
    state = _base_state(mode="pve", enemy_flags={})
    state["characters"] = [ally_fast, ally_slow, enemy_main, enemy_side]

    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AI")
    monkeypatch.setattr(battle_common, "all_skill_data", {"S-BHV": {"name": "BehaviorSkill"}})

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    ally_fast_slot_id = _slot_id_for_actor(state, "A_FAST")
    intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert intent.get("target", {}).get("type") == "single_slot"
    assert intent.get("target", {}).get("slot_id") == ally_fast_slot_id


def test_select_resolve_round_start_behavior_profile_targets_ally_fastest(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-BHV"],
                    "targets": ["target_ally_fastest"],
                }],
                "transitions": [],
            }
        },
    }
    ally_one = _make_char("A1", "ally", speed=10)
    enemy_main = _make_char("E1", "enemy", flags={"auto_skill_select": True, "behavior_profile": behavior_profile}, speed=12)
    enemy_fast = _make_char("E2", "enemy", flags={"auto_target_select": False}, speed=30)
    state = _base_state(mode="pve", enemy_flags={})
    state["characters"] = [ally_one, enemy_main, enemy_fast]

    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AI")
    monkeypatch.setattr(
        battle_common,
        "all_skill_data",
        {"S-BHV": {"name": "BehaviorSkill", "tags": ["ally_target"]}},
    )

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    enemy_fast_slot_id = _slot_id_for_actor(state, "E2")
    intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert intent.get("target", {}).get("type") == "single_slot"
    assert intent.get("target", {}).get("slot_id") == enemy_fast_slot_id


def test_select_resolve_round_start_behavior_profile_blocks_ally_target_without_tag(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-BHV"],
                    "targets": ["target_ally_fastest"],
                }],
                "transitions": [],
            }
        },
    }
    ally_one = _make_char("A1", "ally", speed=10)
    enemy_main = _make_char("E1", "enemy", flags={"auto_skill_select": True, "behavior_profile": behavior_profile}, speed=12)
    enemy_fast = _make_char("E2", "enemy", flags={"auto_target_select": False}, speed=30)
    state = _base_state(mode="pve", enemy_flags={})
    state["characters"] = [ally_one, enemy_main, enemy_fast]

    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AI")
    monkeypatch.setattr(battle_common, "all_skill_data", {"S-BHV": {"name": "BehaviorSkill"}})

    payload = battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    assert payload is not None
    enemy_slot_id = _slot_id_for_actor(state, "E1")
    ally_slot_id = _slot_id_for_actor(state, "A1")
    intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert intent.get("target", {}).get("type") == "single_slot"
    assert intent.get("target", {}).get("slot_id") == ally_slot_id


def test_behavior_profile_ordered_candidates_prefer_tagged_same_team(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-BHV"],
                    "targets": [[
                        {
                            "team": "same_team",
                            "required_tag_ids": ["瓦礫", "機械"],
                            "selection": "fastest",
                        },
                        {
                            "team": "opposing_team",
                            "required_tag_ids": [],
                            "selection": "random",
                        },
                    ]],
                }],
            },
        },
    }
    ally = _make_char("A1", "ally")
    enemy_main = _make_char(
        "E1",
        "enemy",
        flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
        speed=12,
    )
    tagged_enemy = _make_char(
        "E2",
        "enemy",
        flags={"auto_target_select": False},
        speed=30,
        tag_ids=["瓦礫", "機械"],
    )
    state = _base_state(mode="pve", enemy_flags={})
    state["characters"] = [ally, enemy_main, tagged_enemy]

    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AI")
    monkeypatch.setattr(
        battle_common,
        "all_skill_data",
        {"S-BHV": {"name": "BehaviorSkill", "target_scope": "any"}},
    )

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    enemy_slot_id = _slot_id_for_actor(state, "E1")
    tagged_slot_id = _slot_id_for_actor(state, "E2")
    intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert intent.get("skill_id") == "S-BHV"
    assert intent.get("target", {}).get("slot_id") == tagged_slot_id


def test_behavior_profile_ordered_candidates_skip_disabled_tag_and_fallback(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-BHV"],
                    "targets": [[
                        {
                            "team": "same_team",
                            "required_tag_ids": ["瓦礫"],
                            "selection": "random",
                        },
                        {
                            "team": "opposing_team",
                            "required_tag_ids": [],
                            "selection": "random",
                        },
                    ]],
                }],
            },
        },
    }
    ally = _make_char("A1", "ally")
    enemy_main = _make_char(
        "E1",
        "enemy",
        flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )
    disabled_rubble = _make_char(
        "E2",
        "enemy",
        flags={"auto_target_select": False},
        tag_ids=["瓦礫"],
        disabled_tag_ids=["瓦礫"],
    )
    state = _base_state(mode="pve", enemy_flags={})
    state["characters"] = [ally, enemy_main, disabled_rubble]

    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AI")
    monkeypatch.setattr(
        battle_common,
        "all_skill_data",
        {"S-BHV": {"name": "BehaviorSkill", "target_scope": "any"}},
    )

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    enemy_slot_id = _slot_id_for_actor(state, "E1")
    ally_slot_id = _slot_id_for_actor(state, "A1")
    intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert intent.get("skill_id") == "S-BHV"
    assert intent.get("target", {}).get("slot_id") == ally_slot_id


def test_behavior_profile_empty_ordered_candidates_fizzle_without_skill_substitution(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-BHV"],
                    "targets": [[{
                        "team": "same_team",
                        "required_tag_ids": ["存在しないタグ"],
                        "selection": "random",
                    }]],
                }],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )

    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AI")
    monkeypatch.setattr(
        battle_common,
        "all_skill_data",
        {"S-BHV": {"name": "BehaviorSkill", "target_scope": "any"}},
    )

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    enemy_slot_id = _slot_id_for_actor(state, "E1")
    intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert intent.get("skill_id") == "S-BHV"
    assert intent.get("committed") is True
    assert intent.get("target") == {"type": "single_slot", "slot_id": None}
    assert state.get("ai_target_arrows") == []


def test_behavior_profile_same_team_candidate_excludes_all_actor_slots(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-BHV", "S-BHV"],
                    "targets": [
                        [{"team": "same_team", "required_tag_ids": [], "selection": "random"}],
                        [{"team": "same_team", "required_tag_ids": [], "selection": "random"}],
                    ],
                }],
            },
        },
    }
    state = _base_state(mode="pve", enemy_flags={})
    state["characters"] = [
        _make_char("A1", "ally"),
        _make_char(
            "E1",
            "enemy",
            flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
            action_count=2,
        ),
    ]

    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AI")
    monkeypatch.setattr(
        battle_common,
        "all_skill_data",
        {"S-BHV": {"name": "BehaviorSkill", "target_scope": "same_team"}},
    )

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    enemy_intents = [
        intent
        for intent in state["battle_state"]["intents"].values()
        if intent.get("actor_id") == "E1"
    ]
    assert len(enemy_intents) == 2
    assert all(intent.get("target", {}).get("slot_id") is None for intent in enemy_intents)


def test_behavior_profile_self_candidate_can_target_current_actor_slot(monkeypatch):
    behavior_profile = {
        "enabled": True,
        "initial_loop_id": "phase_1",
        "loops": {
            "phase_1": {
                "repeat": True,
                "steps": [{
                    "actions": ["S-BHV"],
                    "targets": [[{
                        "team": "self",
                        "required_tag_ids": [],
                        "selection": "random",
                    }]],
                }],
            },
        },
    }
    state = _base_state(
        mode="pve",
        enemy_flags={"auto_skill_select": True, "behavior_profile": behavior_profile},
    )

    monkeypatch.setattr(battle_common, "get_room_state", lambda room: state)
    monkeypatch.setattr(battle_common, "save_specific_room_state", lambda room: True)
    monkeypatch.setattr(battle_common, "broadcast_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(battle_common, "roll_dice", lambda _cmd: {"total": 1})
    monkeypatch.setattr(battle_common, "ai_suggest_skill", lambda _char: "S-AI")
    monkeypatch.setattr(
        battle_common,
        "all_skill_data",
        {"S-BHV": {"name": "BehaviorSkill", "target_scope": "self"}},
    )

    battle_common.process_select_resolve_round_start(
        room="room_t",
        battle_id="battle_room_t",
        round_value=1,
    )

    enemy_slot_id = _slot_id_for_actor(state, "E1")
    intent = state["battle_state"]["intents"].get(enemy_slot_id, {})
    assert intent.get("skill_id") == "S-BHV"
    assert intent.get("target", {}).get("slot_id") == enemy_slot_id
