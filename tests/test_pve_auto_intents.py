from manager.battle import common_manager as battle_common


def _make_char(char_id, team, flags=None, speed=6, action_count=1):
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
            {"label": "速度", "value": int(speed)},
            {"label": "行動回数", "value": int(action_count)},
        ],
        "states": [],
        "special_buffs": [],
        "flags": dict(flags or {}),
        "commands": "",
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
