from __future__ import annotations

import copy

from manager.logs import setup_logger


logger = setup_logger(__name__)
SCHEDULED_EFFECTS_KEY = "scheduled_effects"
EXECUTED_KEYS_KEY = "executed_scheduled_effect_keys"


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def apply_schedule_change(state, source_actor, payload):
    if not isinstance(state, dict) or not isinstance(payload, dict):
        return False
    unique_key = str(payload.get("unique_key") or "").strip()
    execute_round = _safe_int(payload.get("execute_round"), 0)
    effect = payload.get("effect")
    if not unique_key or execute_round <= 0 or not isinstance(effect, dict):
        return False

    executed = {
        str(key)
        for key in state.get(EXECUTED_KEYS_KEY, []) or []
        if str(key or "").strip()
    }
    if unique_key in executed:
        return False

    queue = state.setdefault(SCHEDULED_EFFECTS_KEY, [])
    if not isinstance(queue, list):
        queue = []
        state[SCHEDULED_EFFECTS_KEY] = queue
    if any(
        isinstance(row, dict) and str(row.get("unique_key") or "") == unique_key
        for row in queue
    ):
        return False

    entry = copy.deepcopy(payload)
    if isinstance(source_actor, dict):
        entry.setdefault("source_actor_id", source_actor.get("id"))
        entry.setdefault(
            "source_actor_snapshot",
            {
                key: copy.deepcopy(source_actor.get(key))
                for key in ["id", "name", "type", "x", "y", "owner", "owner_id"]
                if key in source_actor
            },
        )
    queue.append(entry)
    return True


def execute_scheduled_effects(state, round_value, room=None):
    if not isinstance(state, dict):
        return {"executed": 0, "summoned": 0, "failed": 0}
    current_round = _safe_int(round_value, 0)
    queue = state.get(SCHEDULED_EFFECTS_KEY, [])
    if not isinstance(queue, list) or not queue:
        return {"executed": 0, "summoned": 0, "failed": 0}

    executed_keys = [
        str(key)
        for key in state.get(EXECUTED_KEYS_KEY, []) or []
        if str(key or "").strip()
    ]
    executed_set = set(executed_keys)
    remaining = []
    result = {"executed": 0, "summoned": 0, "failed": 0}

    characters = state.get("characters", [])
    for entry in queue:
        if not isinstance(entry, dict):
            continue
        if _safe_int(entry.get("execute_round"), 0) > current_round:
            remaining.append(entry)
            continue

        unique_key = str(entry.get("unique_key") or "").strip()
        if not unique_key or unique_key in executed_set:
            continue

        # Persist the idempotency mark before applying the effect. A repeated
        # RoundStart therefore cannot execute the same reservation twice.
        executed_set.add(unique_key)
        executed_keys.append(unique_key)
        result["executed"] += 1

        source_actor_id = str(entry.get("source_actor_id") or "")
        source_actor = next(
            (
                char for char in characters
                if isinstance(char, dict) and str(char.get("id") or "") == source_actor_id
            ),
            None,
        )
        if not isinstance(source_actor, dict):
            source_actor = copy.deepcopy(entry.get("source_actor_snapshot") or {})

        effect = entry.get("effect") if isinstance(entry.get("effect"), dict) else {}
        effect_type = str(effect.get("type") or "").strip().upper()
        repeat_count = max(1, _safe_int(entry.get("repeat_count"), 1))
        if effect_type == "SUMMON_CHARACTER":
            from manager.summons.service import apply_summon_change

            summon_payload = copy.deepcopy(effect)
            summon_payload.pop("type", None)
            for _ in range(repeat_count):
                applied = apply_summon_change(room, state, source_actor, summon_payload)
                if applied.get("ok"):
                    result["summoned"] += 1
                else:
                    result["failed"] += 1
                    logger.warning(
                        "scheduled summon failed key=%s: %s",
                        unique_key,
                        applied.get("message"),
                    )
        else:
            result["failed"] += 1
            logger.warning(
                "scheduled effect type is not supported key=%s type=%s",
                unique_key,
                effect_type,
            )

    state[SCHEDULED_EFFECTS_KEY] = remaining
    state[EXECUTED_KEYS_KEY] = executed_keys[-500:]
    return result
