import copy
import random

BEHAVIOR_TARGET_POLICY_DEFAULT = "target_enemy_random"
BEHAVIOR_TARGET_POLICIES = {
    "target_enemy_random",
    "target_enemy_fastest",
    "target_enemy_slowest",
    "target_ally_random",
    "target_ally_fastest",
    "target_ally_slowest",
    "target_self",
}
BEHAVIOR_TARGET_POLICY_ALIASES = {
    "enemy_random": "target_enemy_random",
    "random_enemy": "target_enemy_random",
    "enemy_fastest": "target_enemy_fastest",
    "enemy_highest_speed": "target_enemy_fastest",
    "enemy_slowest": "target_enemy_slowest",
    "enemy_lowest_speed": "target_enemy_slowest",
    "ally_random": "target_ally_random",
    "random_ally": "target_ally_random",
    "ally_fastest": "target_ally_fastest",
    "ally_highest_speed": "target_ally_fastest",
    "ally_slowest": "target_ally_slowest",
    "ally_lowest_speed": "target_ally_slowest",
    "self": "target_self",
}


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _normalize_operator(op):
    return str(op or "EQUALS").strip().upper()


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, str):
        txt = value.strip().lower()
        if txt in {"1", "true", "yes", "on"}:
            return True
        if txt in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _read_actor_status(actor_char, param_name):
    if not isinstance(actor_char, dict):
        return 0
    key = str(param_name or "")
    if key in {"HP", "hp"}:
        return _safe_int(actor_char.get("hp", 0), 0)
    if key in {"MP", "mp"}:
        return _safe_int(actor_char.get("mp", 0), 0)

    states = actor_char.get("states", [])
    if isinstance(states, list):
        hit = next((s for s in states if isinstance(s, dict) and s.get("name") == key), None)
        if isinstance(hit, dict):
            return _safe_int(hit.get("value", 0), 0)

    params = actor_char.get("params", [])
    if isinstance(params, list):
        hit = next((p for p in params if isinstance(p, dict) and p.get("label") == key), None)
        if isinstance(hit, dict):
            return _safe_int(hit.get("value", 0), 0)
    return _safe_int(actor_char.get(key, 0), 0)


def _evaluate_simple_condition(condition, actor_char=None, state=None, battle_state=None):
    if not isinstance(condition, dict):
        return False
    source = str(condition.get("source", "")).strip().lower()
    param = str(condition.get("param", "")).strip()
    op = _normalize_operator(condition.get("operator"))
    expected = condition.get("value")
    if not source or not param:
        return False

    if source == "self":
        current = _read_actor_status(actor_char, param)
    elif source == "battle":
        if param == "round":
            current = _safe_int(
                (battle_state or {}).get("round", (state or {}).get("round", 0)),
                0,
            )
        elif param == "phase":
            current = str((battle_state or {}).get("phase", ""))
        else:
            current = (battle_state or {}).get(param, (state or {}).get(param))
    else:
        return False

    if op == "CONTAINS":
        if isinstance(current, (list, tuple, set)):
            return expected in current
        return str(expected or "") in str(current or "")

    if isinstance(current, str) and isinstance(expected, str):
        if op == "EQUALS":
            return current == expected
        return False

    cur_num = _safe_float(current, 0.0)
    exp_num = _safe_float(expected, 0.0)
    if op == "GTE":
        return cur_num >= exp_num
    if op == "LTE":
        return cur_num <= exp_num
    if op == "GT":
        return cur_num > exp_num
    if op == "LT":
        return cur_num < exp_num
    if op == "EQUALS":
        return cur_num == exp_num
    return False


def _coerce_actions(raw_actions):
    if isinstance(raw_actions, list):
        out = []
        for item in raw_actions:
            if item is None:
                out.append(None)
            else:
                txt = str(item).strip()
                out.append(txt if txt else None)
        return out
    if raw_actions is None:
        return []
    txt = str(raw_actions).strip()
    return [txt] if txt else []


def _coerce_target_policy(raw_policy):
    text = str(raw_policy or "").strip().lower()
    if not text:
        return BEHAVIOR_TARGET_POLICY_DEFAULT
    text = BEHAVIOR_TARGET_POLICY_ALIASES.get(text, text)
    if text in BEHAVIOR_TARGET_POLICIES:
        return text
    return BEHAVIOR_TARGET_POLICY_DEFAULT


def _coerce_targets(raw_targets):
    if isinstance(raw_targets, list):
        return [_coerce_target_policy(item) for item in raw_targets]
    if raw_targets is None:
        return []
    return [_coerce_target_policy(raw_targets)]


def _coerce_step_actions_and_targets(raw_actions, raw_targets):
    actions = []
    inline_targets = []

    if isinstance(raw_actions, list):
        for item in raw_actions:
            if isinstance(item, dict):
                skill_raw = item.get("skill_id", item.get("skill", item.get("id")))
                target_raw = item.get("target_policy", item.get("target", item.get("target_selector")))
                skill_txt = str(skill_raw or "").strip()
                actions.append(skill_txt if skill_txt else None)
                inline_targets.append(_coerce_target_policy(target_raw))
            elif item is None:
                actions.append(None)
                inline_targets.append(BEHAVIOR_TARGET_POLICY_DEFAULT)
            else:
                skill_txt = str(item).strip()
                actions.append(skill_txt if skill_txt else None)
                inline_targets.append(BEHAVIOR_TARGET_POLICY_DEFAULT)
    elif raw_actions is None:
        actions = []
    else:
        skill_txt = str(raw_actions).strip()
        actions = [skill_txt] if skill_txt else []
        inline_targets = [BEHAVIOR_TARGET_POLICY_DEFAULT for _ in actions]

    explicit_targets = _coerce_targets(raw_targets)
    base_targets = explicit_targets if explicit_targets else inline_targets
    targets = []
    for idx in range(len(actions)):
        if idx < len(base_targets):
            targets.append(_coerce_target_policy(base_targets[idx]))
        else:
            targets.append(BEHAVIOR_TARGET_POLICY_DEFAULT)
    return actions, targets


def normalize_behavior_profile(raw_profile):
    profile = raw_profile if isinstance(raw_profile, dict) else {}
    loops_raw = profile.get("loops", {})
    loops = {}
    if isinstance(loops_raw, dict):
        for loop_id_raw, loop_data in loops_raw.items():
            loop_id = str(loop_id_raw or "").strip()
            if not loop_id:
                continue
            loop_obj = loop_data if isinstance(loop_data, dict) else {}

            steps_out = []
            raw_steps = loop_obj.get("steps", [])
            if isinstance(raw_steps, list):
                for step in raw_steps:
                    step_obj = step if isinstance(step, dict) else {}
                    actions, targets = _coerce_step_actions_and_targets(
                        step_obj.get("actions", []),
                        step_obj.get("targets", []),
                    )
                    next_loop_id = str(
                        step_obj.get("next_loop_id", step_obj.get("after_step_to_loop_id", "")) or ""
                    ).strip() or None
                    next_reset_step_index = _to_bool(
                        step_obj.get("next_reset_step_index", step_obj.get("after_step_reset_step_index", True)),
                        True
                    )
                    steps_out.append({
                        "actions": actions,
                        "targets": targets,
                        "next_loop_id": next_loop_id,
                        "next_reset_step_index": next_reset_step_index,
                    })

            transitions_out = []
            raw_transitions = loop_obj.get("transitions", [])
            if isinstance(raw_transitions, list):
                for tr in raw_transitions:
                    tr_obj = tr if isinstance(tr, dict) else {}
                    to_loop_id = str(tr_obj.get("to_loop_id", "") or "").strip()
                    if not to_loop_id:
                        continue
                    conds = tr_obj.get("when_all", [])
                    if not isinstance(conds, list):
                        conds = []
                    transitions_out.append({
                        "priority": _safe_int(tr_obj.get("priority", 0), 0),
                        "to_loop_id": to_loop_id,
                        "reset_step_index": _to_bool(tr_obj.get("reset_step_index", True), True),
                        "when_all": [c for c in conds if isinstance(c, dict)],
                    })
            transitions_out.sort(key=lambda row: int(row.get("priority", 0)), reverse=True)

            loops[loop_id] = {
                "repeat": _to_bool(loop_obj.get("repeat", True), True),
                "steps": steps_out,
                "transitions": transitions_out,
            }

    normalized = {
        "enabled": _to_bool(profile.get("enabled", False), False),
        "version": 1,
        "initial_loop_id": str(profile.get("initial_loop_id", "") or "").strip() or None,
        "loops": loops,
    }

    if normalized["initial_loop_id"] not in loops:
        normalized["initial_loop_id"] = next(iter(loops.keys()), None)
    if not loops:
        normalized["enabled"] = False
    return normalized


def initialize_behavior_runtime_entry(profile, runtime_entry=None, round_value=None):
    prof = normalize_behavior_profile(profile)
    current = runtime_entry if isinstance(runtime_entry, dict) else {}
    active_loop_id = str(current.get("active_loop_id", "") or "").strip() or prof.get("initial_loop_id")
    if active_loop_id not in prof.get("loops", {}):
        active_loop_id = prof.get("initial_loop_id")

    runtime = {
        "active_loop_id": active_loop_id,
        "step_index": max(0, _safe_int(current.get("step_index", 0), 0)),
        "last_round": _safe_int(current.get("last_round", round_value if round_value is not None else 0), 0),
        "last_skill_ids": list(current.get("last_skill_ids", [])) if isinstance(current.get("last_skill_ids"), list) else [],
    }
    return runtime


def evaluate_transitions(profile, runtime_entry, actor_char=None, state=None, battle_state=None):
    prof = normalize_behavior_profile(profile)
    runtime = initialize_behavior_runtime_entry(
        prof,
        runtime_entry=runtime_entry,
        round_value=_safe_int((battle_state or {}).get("round", (state or {}).get("round", 0)), 0),
    )
    active_loop_id = runtime.get("active_loop_id")
    loops = prof.get("loops", {})
    loop = loops.get(active_loop_id, {})
    transitions = loop.get("transitions", []) if isinstance(loop, dict) else []
    changed = False

    for tr in transitions:
        conds = tr.get("when_all", []) if isinstance(tr, dict) else []
        if conds and not all(
            _evaluate_simple_condition(c, actor_char=actor_char, state=state, battle_state=battle_state)
            for c in conds
        ):
            continue
        next_loop_id = str(tr.get("to_loop_id", "") or "").strip()
        if not next_loop_id or next_loop_id not in loops:
            continue
        if next_loop_id != active_loop_id:
            changed = True
            runtime["active_loop_id"] = next_loop_id
        if _to_bool(tr.get("reset_step_index", True), True):
            runtime["step_index"] = 0
            changed = True
        break

    return {
        "runtime": runtime,
        "changed": changed,
    }


def pick_step_actions(profile, runtime_entry):
    prof = normalize_behavior_profile(profile)
    runtime = initialize_behavior_runtime_entry(prof, runtime_entry=runtime_entry)
    loops = prof.get("loops", {})
    loop_id = runtime.get("active_loop_id")
    loop = loops.get(loop_id, {})
    steps = loop.get("steps", []) if isinstance(loop, dict) else []
    if not steps:
        return {"actions": [], "targets": [], "plans": [], "runtime": runtime}

    idx = _safe_int(runtime.get("step_index", 0), 0)
    if idx < 0:
        idx = 0
    if idx >= len(steps):
        if _to_bool(loop.get("repeat", True), True):
            idx = idx % len(steps)
        else:
            idx = len(steps) - 1
    runtime["step_index"] = idx
    step = steps[idx] if isinstance(steps[idx], dict) else {}
    actions, targets = _coerce_step_actions_and_targets(
        step.get("actions", []),
        step.get("targets", []),
    )
    step_transition = None
    next_loop_id = str(step.get("next_loop_id", "") or "").strip()
    if next_loop_id and next_loop_id in loops:
        step_transition = {
            "to_loop_id": next_loop_id,
            "reset_step_index": _to_bool(step.get("next_reset_step_index", True), True),
        }
    plans = []
    for i, skill_id in enumerate(actions):
        plans.append({
            "skill_id": skill_id,
            "target_policy": targets[i] if i < len(targets) else BEHAVIOR_TARGET_POLICY_DEFAULT,
        })
    return {
        "actions": actions,
        "targets": targets,
        "plans": plans,
        "runtime": runtime,
        "step_transition": step_transition,
    }


def advance_step_pointer(profile, runtime_entry, step_transition=None):
    prof = normalize_behavior_profile(profile)
    runtime = initialize_behavior_runtime_entry(prof, runtime_entry=runtime_entry)
    loop_id = runtime.get("active_loop_id")
    loop = prof.get("loops", {}).get(loop_id, {})
    steps = loop.get("steps", []) if isinstance(loop, dict) else []
    if not steps:
        runtime["step_index"] = 0
        return runtime

    if isinstance(step_transition, dict):
        to_loop_id = str(step_transition.get("to_loop_id", "") or "").strip()
        loops = prof.get("loops", {})
        if to_loop_id and to_loop_id in loops:
            runtime["active_loop_id"] = to_loop_id
            if _to_bool(step_transition.get("reset_step_index", True), True):
                runtime["step_index"] = 0
            else:
                next_loop = loops.get(to_loop_id, {})
                next_steps = next_loop.get("steps", []) if isinstance(next_loop, dict) else []
                if not next_steps:
                    runtime["step_index"] = 0
                else:
                    current_idx = _safe_int(runtime.get("step_index", 0), 0)
                    runtime["step_index"] = min(max(0, current_idx), len(next_steps) - 1)
            return runtime

    idx = _safe_int(runtime.get("step_index", 0), 0) + 1
    if _to_bool(loop.get("repeat", True), True):
        idx = idx % len(steps)
    else:
        idx = min(len(steps) - 1, idx)
    runtime["step_index"] = idx
    return runtime


def choose_actions_for_slot_count(actions, slot_count):
    action_plans = [{"skill_id": action, "target_policy": BEHAVIOR_TARGET_POLICY_DEFAULT} for action in actions or []]
    picked = choose_action_plans_for_slot_count(action_plans, slot_count)
    return [row.get("skill_id") for row in picked]


def choose_action_plans_for_slot_count(action_plans, slot_count):
    count = max(0, _safe_int(slot_count, 0))
    if count <= 0:
        return []

    normalized = []
    for row in action_plans or []:
        if isinstance(row, dict):
            skill_raw = row.get("skill_id", row.get("skill", row.get("id")))
            policy_raw = row.get("target_policy", row.get("target"))
        else:
            skill_raw = row
            policy_raw = None
        skill_txt = str(skill_raw or "").strip() if skill_raw is not None else ""
        normalized.append({
            "skill_id": (skill_txt if skill_txt else None),
            "target_policy": _coerce_target_policy(policy_raw),
        })

    if not normalized:
        return [{
            "skill_id": None,
            "target_policy": BEHAVIOR_TARGET_POLICY_DEFAULT,
        } for _ in range(count)]

    if len(normalized) > count:
        return [dict(row) for row in random.sample(normalized, count)]

    out = []
    for idx in range(count):
        if idx < len(normalized):
            out.append(dict(normalized[idx]))
        else:
            # Do not duplicate the last action automatically.
            # Missing slots are treated as "no action".
            out.append({
                "skill_id": None,
                "target_policy": BEHAVIOR_TARGET_POLICY_DEFAULT,
            })
    return out


def clone_behavior_runtime_map(runtime_map):
    if not isinstance(runtime_map, dict):
        return {}
    return copy.deepcopy(runtime_map)
