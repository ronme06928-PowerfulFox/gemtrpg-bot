from __future__ import annotations

import copy
import re
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Callable, Literal

from manager.battle import common_manager as battle_common
from manager.battle import core as battle_core
from manager.battle import duel_solver
from manager.battle import resolve_auto_runtime
from manager.battle import wide_solver
from manager.battle.battle_ai import ai_suggest_skill
from manager.sim.reporting import (
    BattleReport,
    battle_summary_from_characters,
    committed_intent_count,
    round_summary,
    safe_int,
    snapshot_characters,
    stall_reason,
    total_hp_for_progress,
)
import manager.room_manager as room_manager


IntentProvider = Callable[[dict, dict], None]
RollMode = Literal["random", "low", "median", "high"]
AllyTargetPolicy = Literal["first_alive_enemy", "lowest_hp_enemy"]


def _resolve_term_sign(expr, start_index):
    i = int(start_index) - 1
    while i >= 0 and expr[i].isspace():
        i -= 1
    if i >= 0 and expr[i] == "-":
        return -1
    return 1


def _median_die_value(faces: int) -> int:
    if faces <= 1:
        return max(0, faces)
    return (faces + 2) // 2


def _rolls_for_mode(num_dice: int, faces: int, roll_mode: RollMode) -> list[int]:
    if num_dice <= 0:
        return []
    if faces < 1:
        return [0] * num_dice
    if roll_mode == "low":
        return [1] * num_dice
    if roll_mode == "median":
        return [_median_die_value(faces)] * num_dice
    if roll_mode == "high":
        return [faces] * num_dice
    raise ValueError(f"unsupported deterministic roll mode: {roll_mode}")


def build_deterministic_roll_dice(roll_mode: RollMode):
    if roll_mode not in {"low", "median", "high"}:
        raise ValueError("roll_mode must be one of: low, median, high")

    def _roll_dice(cmd_str):
        raw_cmd = str(cmd_str or "").strip()
        calc_str = raw_cmd.split()[0] if raw_cmd else ""
        details_str = calc_str
        original_calc = calc_str

        dice_total = 0
        dice_terms = []
        matches = list(re.finditer(r"(\d+)d(\d+)", original_calc))

        for match in reversed(matches):
            num_dice = int(match.group(1))
            num_faces = int(match.group(2))
            sign = _resolve_term_sign(original_calc, match.start())
            rolls = _rolls_for_mode(num_dice, num_faces, roll_mode)
            roll_sum = sum(rolls)
            roll_details = f"({'+'.join(map(str, rolls))})"

            start, end = match.start(), match.end()
            details_str = details_str[:start] + roll_details + details_str[end:]
            calc_str = calc_str[:start] + str(roll_sum) + calc_str[end:]
            dice_total += sign * int(roll_sum)
            dice_terms.append({
                "sign": sign,
                "num": num_dice,
                "faces": num_faces,
                "rolls": rolls,
                "sum": int(roll_sum),
                "raw": match.group(0),
            })

        sanitized = re.sub(r"[^-\d()/*+.]", "", calc_str)
        try:
            total = eval(sanitized)
        except Exception:
            total = 0

        constant_total = 0
        constant_terms = []
        for token in re.finditer(r"([+-]?)(\d+d\d+|\d+)", original_calc.replace(" ", "")):
            sign_raw = token.group(1)
            raw_value = token.group(2)
            sign = -1 if sign_raw == "-" else 1
            if "d" in raw_value:
                continue
            try:
                value = sign * int(raw_value)
            except Exception:
                continue
            constant_total += value
            constant_terms.append({"raw": f"{sign_raw}{raw_value}", "value": value})

        return {
            "total": total,
            "details": details_str,
            "breakdown": {
                "expression": original_calc,
                "sanitized_expression": sanitized,
                "dice_total": int(dice_total),
                "constant_total": int(constant_total),
                "final_total": int(total),
                "dice_terms": list(reversed(dice_terms)),
                "constant_terms": constant_terms,
                "roll_mode": roll_mode,
            },
        }

    return _roll_dice


def _is_active_char(char: dict) -> bool:
    if not isinstance(char, dict):
        return False
    if safe_int(char.get("hp"), 0) <= 0:
        return False
    if bool(char.get("is_escaped", False)):
        return False
    try:
        return float(char.get("x", -1)) >= 0
    except Exception:
        return False


def _mark_round_ready_to_end(state: dict) -> None:
    for char in state.get("characters", []) or []:
        if isinstance(char, dict) and _is_active_char(char):
            char["hasActed"] = True


def _characters_by_id(state: dict) -> dict[str, dict]:
    result = {}
    for char in state.get("characters", []) or []:
        if isinstance(char, dict) and char.get("id"):
            result[str(char.get("id"))] = char
    return result


def _candidate_enemy_slots(state: dict, battle_state: dict) -> list[tuple[str, dict, dict]]:
    chars_by_id = _characters_by_id(state)
    slots = battle_state.get("slots", {}) if isinstance(battle_state.get("slots"), dict) else {}
    timeline = battle_state.get("timeline", []) if isinstance(battle_state.get("timeline"), list) else []
    timeline_index = {str(slot_id): idx for idx, slot_id in enumerate(timeline)}

    candidates = []
    for slot_id, slot in slots.items():
        if not isinstance(slot, dict):
            continue
        if str(slot.get("team") or "").strip().lower() != "enemy":
            continue
        actor_id = str(slot.get("actor_id") or "")
        char = chars_by_id.get(actor_id)
        if not _is_active_char(char):
            continue
        candidates.append((str(slot_id), slot, char))

    candidates.sort(key=lambda row: timeline_index.get(row[0], 999999))
    return candidates


def _select_ally_target_slot(state: dict, battle_state: dict, target_policy: AllyTargetPolicy) -> str | None:
    candidates = _candidate_enemy_slots(state, battle_state)
    if not candidates:
        return None
    if target_policy == "first_alive_enemy":
        return candidates[0][0]
    if target_policy == "lowest_hp_enemy":
        return min(candidates, key=lambda row: (safe_int(row[2].get("hp"), 0), row[0]))[0]
    raise ValueError("target_policy must be one of: first_alive_enemy, lowest_hp_enemy")


def auto_commit_ally_intents(
    state: dict,
    battle_state: dict,
    *,
    target_policy: AllyTargetPolicy = "first_alive_enemy",
) -> int:
    chars_by_id = _characters_by_id(state)
    slots = battle_state.get("slots", {}) if isinstance(battle_state.get("slots"), dict) else {}
    timeline = battle_state.get("timeline", []) if isinstance(battle_state.get("timeline"), list) else list(slots.keys())
    intents = battle_state.setdefault("intents", {})
    committed = 0

    for slot_id in timeline:
        slot_id = str(slot_id)
        slot = slots.get(slot_id)
        if not isinstance(slot, dict):
            continue
        if str(slot.get("team") or "").strip().lower() != "ally":
            continue
        if slot_id in intents:
            continue

        actor_id = str(slot.get("actor_id") or "")
        actor = chars_by_id.get(actor_id)
        if not _is_active_char(actor):
            continue

        skill_id = ai_suggest_skill(actor)
        if not skill_id:
            continue

        target_slot_id = _select_ally_target_slot(state, battle_state, target_policy)
        if not target_slot_id:
            continue

        intents[slot_id] = {
            "slot_id": slot_id,
            "actor_id": actor_id,
            "skill_id": skill_id,
            "target": {"type": "single_slot", "slot_id": target_slot_id},
            "tags": {"instant": False, "mass_type": None, "no_redirect": False},
            "committed": True,
            "committed_at": 1,
            "committed_by": "AI:SIM_ALLY",
        }
        committed += 1

    return committed


def _noop(*_args, **_kwargs):
    return None


def _silent_update_char_stat(room, char, stat_name, new_value, *args, **kwargs):
    kwargs["save"] = False
    kwargs["suppress_log"] = True
    return room_manager._update_char_stat(room, char, stat_name, new_value, *args, **kwargs)


@contextmanager
def _patched_headless_runtime(room: str, state: dict, roll_mode: RollMode):
    emit_calls = []

    def _emit(event, payload=None, to=None, **kwargs):
        emit_calls.append((event, payload, to, kwargs))

    original_attrs = []

    def set_attr(module, name, value):
        original_attrs.append((module, name, getattr(module, name)))
        setattr(module, name, value)

    socket_stub = SimpleNamespace(emit=_emit)
    deterministic_roll_dice = None
    if roll_mode != "random":
        deterministic_roll_dice = build_deterministic_roll_dice(roll_mode)

    try:
        for module in (battle_core, battle_common):
            set_attr(module, "get_room_state", lambda target_room: state if target_room == room else None)
            set_attr(module, "save_specific_room_state", lambda *_args, **_kwargs: True)
            set_attr(module, "broadcast_log", _noop)
            set_attr(module, "socketio", socket_stub)
            set_attr(module, "_update_char_stat", _silent_update_char_stat)
            if deterministic_roll_dice is not None:
                set_attr(module, "roll_dice", deterministic_roll_dice)

        if deterministic_roll_dice is not None:
            for module in (duel_solver, wide_solver):
                set_attr(module, "roll_dice", deterministic_roll_dice)

        set_attr(room_manager, "save_specific_room_state", lambda *_args, **_kwargs: True)
        set_attr(room_manager, "broadcast_log", _noop)
        set_attr(room_manager, "socketio", socket_stub)

        yield emit_calls
    finally:
        for module, name, value in reversed(original_attrs):
            setattr(module, name, value)


def _current_battle_id(state: dict, fallback: str = "sim_battle") -> str:
    battle_state = state.setdefault("battle_state", {})
    battle_id = str(battle_state.get("battle_id") or fallback)
    battle_state["battle_id"] = battle_id
    return battle_id


def _prepare_round_state(state: dict, battle_id: str, round_value: int) -> None:
    state["round"] = round_value
    state["is_round_ended"] = False
    battle_state = state.setdefault("battle_state", {})
    battle_state["battle_id"] = battle_id
    battle_state["round"] = round_value


def run_battle(
    room_state: dict,
    *,
    room: str = "sim_room",
    max_rounds: int = 10,
    intent_provider: IntentProvider | None = None,
    roll_mode: RollMode = "random",
    auto_ally_intents: bool = False,
    ally_target_policy: AllyTargetPolicy = "first_alive_enemy",
    copy_state: bool = True,
) -> BattleReport:
    """Run a headless Select/Resolve battle with optional injected or ally-AI intents."""

    if not isinstance(room_state, dict):
        raise TypeError("room_state must be a dict")
    if max_rounds <= 0:
        raise ValueError("max_rounds must be positive")
    if roll_mode not in {"random", "low", "median", "high"}:
        raise ValueError("roll_mode must be one of: random, low, median, high")
    if ally_target_policy not in {"first_alive_enemy", "lowest_hp_enemy"}:
        raise ValueError("ally_target_policy must be one of: first_alive_enemy, lowest_hp_enemy")

    state = copy.deepcopy(room_state) if copy_state else room_state
    battle_id = _current_battle_id(state)
    result = resolve_auto_runtime._bo_estimate_battle_result(state)
    rounds = safe_int(state.get("round"), 0)
    rounds_detail = []

    with _patched_headless_runtime(room, state, roll_mode):
        for round_value in range(1, max_rounds + 1):
            result = resolve_auto_runtime._bo_estimate_battle_result(state)
            if result != "in_progress":
                break

            rounds = round_value
            _prepare_round_state(state, battle_id, round_value)
            payload = battle_common.process_select_resolve_round_start(room, battle_id, round_value)
            if not payload:
                snapshots = snapshot_characters(state)
                return BattleReport(
                    result="invalid_state",
                    rounds=round_value - 1,
                    stalled=True,
                    max_rounds=max_rounds,
                    characters=snapshots,
                    summary=battle_summary_from_characters(snapshots),
                    stall_reason="invalid_battle_state",
                    rounds_detail=rounds_detail,
                )

            battle_state = state.setdefault("battle_state", {})
            if intent_provider is not None:
                intent_provider(state, battle_state)
            if auto_ally_intents:
                auto_commit_ally_intents(state, battle_state, target_policy=ally_target_policy)

            committed_intents = committed_intent_count(battle_state)
            hp_before = total_hp_for_progress(state)
            battle_state["phase"] = "resolve_mass"
            battle_core.run_select_resolve_auto(room, battle_id)

            _mark_round_ready_to_end(state)
            battle_common.process_full_round_end(room, "simulator")
            round_result = resolve_auto_runtime._bo_estimate_battle_result(state)
            rounds_detail.append(round_summary(state, round_value, round_result, committed_intents, hp_before))

        result = resolve_auto_runtime._bo_estimate_battle_result(state)

    snapshots = snapshot_characters(state)
    return BattleReport(
        result=result,
        rounds=rounds,
        stalled=result == "in_progress",
        max_rounds=max_rounds,
        characters=snapshots,
        summary=battle_summary_from_characters(snapshots),
        stall_reason=stall_reason(result, rounds, max_rounds, rounds_detail),
        rounds_detail=rounds_detail,
    )
