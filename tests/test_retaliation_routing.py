from types import SimpleNamespace

from manager.battle import core as battle_core
from manager.battle import duel_solver
from manager.battle import wide_solver


def _char(char_id, team, hp=100):
    return {
        "id": char_id,
        "name": char_id,
        "type": team,
        "hp": hp,
        "maxHp": hp,
        "mp": 50,
        "maxMp": 50,
        "params": [],
        "states": [
            {"name": "FP", "value": 0},
            {"name": "亀裂", "value": 0},
            {"name": "戦慄", "value": 0},
            {"name": "荊棘", "value": 0},
        ],
        "special_buffs": [],
        "flags": {},
        "hasActed": False,
        "x": 0,
        "y": 0,
    }


def _stub_update_char_stat(_room, char, name, value, **_kwargs):
    if str(name).upper() == "HP":
        char["hp"] = int(value)
        return
    if str(name).upper() == "MP":
        char["mp"] = int(value)
        return
    states = char.setdefault("states", [])
    hit = next((s for s in states if s.get("name") == name), None)
    if hit is None:
        states.append({"name": name, "value": int(value)})
    else:
        hit["value"] = int(value)


def test_select_resolve_one_sided_passes_attacker_to_on_damage(monkeypatch):
    attacker = _char("A1", "ally")
    defender = _char("B1", "enemy")
    state = {"characters": [attacker, defender], "timeline": []}
    skill_a = {"base_power": 6, "dice_power": "1d1", "category": "attack", "tags": ["attack"]}

    captured = []

    monkeypatch.setattr(battle_core, "roll_dice", lambda _cmd: {"total": 6, "breakdown": {}})
    monkeypatch.setattr(battle_core, "process_on_hit_buffs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        battle_core,
        "compute_damage_multipliers",
        lambda *_args, **_kwargs: {"final": 1.0, "incoming": 1.0, "outgoing": 1.0, "incoming_logs": [], "outgoing_logs": []},
    )
    monkeypatch.setattr(battle_core, "_update_char_stat", _stub_update_char_stat)

    def _capture_on_damage(_room, target_char, _incoming_damage, _source, _logs, attacker_char=None, context=None):
        captured.append((target_char.get("id"), attacker_char.get("id") if attacker_char else None, dict(context or {})))
        return 0

    monkeypatch.setattr(battle_core, "process_on_damage_buffs", _capture_on_damage)

    result = battle_core._resolve_one_sided_by_existing_logic(
        room="room_t",
        state=state,
        attacker_char=attacker,
        defender_char=defender,
        attacker_skill_data=skill_a,
        defender_skill_data=None,
    )

    assert result["ok"] is True
    assert captured == [("B1", "A1", {"timeline": [], "characters": state["characters"], "room": "room_t"})]


def test_duel_match_passes_attacker_to_on_damage(monkeypatch):
    attacker = _char("ActorA", "ally", hp=20)
    defender = _char("ActorD", "enemy", hp=20)
    state = {
        "characters": [attacker, defender],
        "timeline": [],
        "active_match": {
            "is_active": True,
            "match_id": "m1",
            "executed": False,
            "attacker_data": {"skill_id": "S-Unmatchable"},
            "defender_data": {"skill_id": "S-Defense"},
        },
    }

    monkeypatch.setattr(duel_solver, "get_room_state", lambda _room: state)
    monkeypatch.setattr(duel_solver, "save_specific_room_state", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(duel_solver, "broadcast_state_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(duel_solver, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(duel_solver, "proceed_next_turn", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(duel_solver, "socketio", SimpleNamespace(emit=lambda *_args, **_kwargs: None))
    monkeypatch.setattr(duel_solver, "_update_char_stat", _stub_update_char_stat)
    monkeypatch.setattr(duel_solver, "execute_pre_match_effects", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(duel_solver, "apply_skill_effects_bidirectional", lambda *_args, **_kwargs: (0, [], 0, []))
    monkeypatch.setattr(duel_solver, "process_on_hit_buffs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        duel_solver,
        "compute_damage_multipliers",
        lambda *_args, **_kwargs: {"final": 1.0, "incoming": 1.0, "outgoing": 1.0, "incoming_logs": [], "outgoing_logs": []},
    )
    monkeypatch.setattr(
        duel_solver,
        "all_skill_data",
        {
            "S-Unmatchable": {"name": "Unmatchable", "分類": "物理", "tags": ["マッチ不可"]},
            "S-Defense": {"name": "Defense", "分類": "防御", "tags": ["defense"]},
        },
    )
    monkeypatch.setattr(
        duel_solver,
        "roll_dice",
        lambda command: {"total": 10 if str(command) == "10" else 5, "details": str(command), "text": str(command)},
    )

    captured = []

    def _capture_on_damage(_room, target_char, _incoming_damage, _source, _logs, attacker_char=None, context=None):
        captured.append((target_char.get("id"), attacker_char.get("id") if attacker_char else None))
        return 0

    monkeypatch.setattr(duel_solver, "process_on_damage_buffs", _capture_on_damage)

    duel_solver.execute_duel_match(
        "room_t",
        {
            "room": "room_t",
            "match_id": "m1",
            "actorIdA": "ActorA",
            "actorIdD": "ActorD",
            "actorNameA": "Attacker",
            "actorNameD": "Defender",
            "commandA": "10",
            "commandD": "5",
            "skillIdA": "S-Unmatchable",
            "skillIdD": "S-Defense",
        },
        "[probe]",
    )

    assert ("ActorD", "ActorA") in captured


def test_wide_match_passes_attacker_to_on_damage(monkeypatch):
    attacker = _char("ActorA", "ally", hp=20)
    defender = _char("ActorD", "enemy", hp=20)
    state = {
        "characters": [attacker, defender],
        "active_match": {
            "is_active": True,
            "match_type": "wide",
            "mode": "individual",
            "attacker_id": "ActorA",
            "attacker_declared": True,
            "attacker_data": {"skill_id": "S-Unmatchable", "final_command": "10"},
            "defenders": [
                {"id": "ActorD", "name": "Defender", "declared": True, "skill_id": "S-Defense", "command": "5"}
            ],
        },
    }

    monkeypatch.setattr(wide_solver, "get_room_state", lambda _room: state)
    monkeypatch.setattr(wide_solver, "save_specific_room_state", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(wide_solver, "broadcast_state_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wide_solver, "broadcast_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wide_solver, "_safe_emit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wide_solver, "_update_char_stat", _stub_update_char_stat)
    monkeypatch.setattr(wide_solver, "execute_pre_match_effects", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wide_solver, "process_on_hit_buffs", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(wide_solver, "process_skill_effects", lambda *_args, **_kwargs: (0, [], []))
    monkeypatch.setattr(
        wide_solver,
        "compute_damage_multipliers",
        lambda *_args, **_kwargs: {"final": 1.0, "incoming": 1.0, "outgoing": 1.0, "incoming_logs": [], "outgoing_logs": []},
    )
    monkeypatch.setattr(
        wide_solver,
        "all_skill_data",
        {
            "S-Unmatchable": {"name": "Unmatchable", "分類": "物理", "tags": ["マッチ不可"]},
            "S-Defense": {"name": "Defense", "分類": "防御", "tags": ["defense"]},
        },
    )
    monkeypatch.setattr(wide_solver, "roll_dice", lambda _cmd: {"total": 10, "details": "10"})

    captured = []

    def _capture_on_damage(_room, target_char, _incoming_damage, _source, _logs, attacker_char=None, context=None):
        captured.append((target_char.get("id"), attacker_char.get("id") if attacker_char else None))
        return 0

    monkeypatch.setattr(wide_solver, "process_on_damage_buffs", _capture_on_damage)

    wide_solver.execute_wide_match("room_t", "[probe]")

    assert captured == [("ActorD", "ActorA")]
