import sys

from manager.battle import condition_eval as _condition_eval
from manager.buff_catalog import resolve_runtime_buff_effect


def _utils_module():
    return sys.modules.get('manager.utils')

def _calculate_bonus_from_rules(rules, actor, target, actor_skill_data=None, context=None, get_status_value_fn=None):
    total = 0
    for rule in rules:
        condition = rule.get('condition')
        if condition:
            if not _condition_eval.check_condition(condition, actor, target, actor_skill_data=actor_skill_data, context=context, get_status_value_fn=get_status_value_fn):
                continue

        bonus = 0
        operation = str(rule.get('operation', rule.get('operator', 'FIXED')) or 'FIXED').strip().upper()

        if operation == 'FIXED':
            bonus = int(rule.get('value', 0))

        elif operation in ['MULTIPLY', 'FIXED_IF_EXISTS', 'PER_N_BONUS']:
            src_type = rule.get('source', 'self')
            src_obj = target if src_type == 'target' else actor
            p_name = rule.get('param')
            val = _condition_eval._get_value_for_condition(
                src_obj,
                p_name,
                context=context,
                actor=actor,
                target=target,
                source_type=src_type,
                get_status_value_fn=get_status_value_fn,
            )
            if val is None:
                val = 0

            if operation == 'MULTIPLY':
                bonus = int(val * float(rule.get('value_per_param', 0)))
            elif operation == 'FIXED_IF_EXISTS':
                threshold = int(rule.get('threshold', 1))
                if val >= threshold:
                    bonus = int(rule.get('value', 0))
            elif operation == 'PER_N_BONUS':
                N = int(rule.get('per_N', 1))
                if N > 0:
                    bonus = (val // N) * int(rule.get('value', 0))

        if 'max_bonus' in rule:
            bonus = min(bonus, int(rule['max_bonus']))
        if 'min_bonus' in rule:
            bonus = max(bonus, int(rule['min_bonus']))

        total += bonus
    return total


def _split_power_bonus_rules(rules):
    """Split power_bonus rules by apply target. If apply_to is missing, treat it as base."""
    buckets = {"base": [], "dice": [], "final": []}
    for rule in (rules or []):
        if not isinstance(rule, dict):
            continue
        apply_to = str(rule.get("apply_to", "base") or "base").lower()
        if apply_to == "dice":
            buckets["dice"].append(rule)
        elif apply_to == "final":
            buckets["final"].append(rule)
        else:
            buckets["base"].append(rule)
    return buckets


def _resolve_runtime_buff_effect_data(buff_row):
    """
    Resolve buff effect for runtime calculation.
    Shared resolver:
    1) Catalog/static effect by buff name
    2) Merge/override with buff instance data
    3) Fixed value-driven implementation for Bu-32..Bu-47
    """
    return resolve_runtime_buff_effect(buff_row)


def calculate_buff_power_bonus_parts(actor, target, actor_skill_data, context=None, get_status_value_fn=None):
    """Return buff-derived power bonus parts. Returns: {"base": int, "dice": int, "final": int}."""
    parts = {"base": 0, "dice": 0, "final": 0}
    if not actor or 'special_buffs' not in actor:
        return parts

    for buff in actor['special_buffs']:
        effect_data = _resolve_runtime_buff_effect_data(buff)
        if not effect_data:
            continue

        if buff.get('delay', 0) > 0:
            continue

        buckets = _split_power_bonus_rules(effect_data.get('power_bonus', []))
        parts["base"] += _calculate_bonus_from_rules(
            buckets["base"], actor, target, actor_skill_data, context=context, get_status_value_fn=get_status_value_fn
        )
        parts["dice"] += _calculate_bonus_from_rules(
            buckets["dice"], actor, target, actor_skill_data, context=context, get_status_value_fn=get_status_value_fn
        )
        parts["final"] += _calculate_bonus_from_rules(
            buckets["final"], actor, target, actor_skill_data, context=context, get_status_value_fn=get_status_value_fn
        )

    return parts


def calculate_buff_power_bonus(actor, target, actor_skill_data, context=None, get_status_value_fn=None):
    parts = calculate_buff_power_bonus_parts(actor, target, actor_skill_data, context=context, get_status_value_fn=get_status_value_fn)
    return int(parts.get("base", 0)) + int(parts.get("final", 0))

def calculate_state_apply_bonus(actor, target, stat_name, context=None, get_status_value_fn=None):
    total_bonus = 0
    buffs_to_remove = []

    if not actor or 'special_buffs' not in actor:
        return 0, [] # 笘・

    for buff in actor['special_buffs']:
        buff_name = buff.get('name')
        effect_data = _resolve_runtime_buff_effect_data(buff)
        if not effect_data:
            continue

        if buff.get('delay', 0) > 0:
            continue

        state_bonuses = effect_data.get('state_bonus', [])
        matching_rules = [r for r in state_bonuses if r.get('stat') == stat_name]

        bonus = _calculate_bonus_from_rules(matching_rules, actor, target, None, context=context, get_status_value_fn=get_status_value_fn)

        if bonus > 0:
            total_bonus += bonus
            for rule in matching_rules:
                if rule.get('consume'):
                    buffs_to_remove.append(buff_name)
                    break

    normalized_stat = _condition_eval._normalize_condition_status_name(stat_name)
    is_other_target = (
        isinstance(actor, dict)
        and isinstance(target, dict)
        and str(actor.get("id", "")) != str(target.get("id", ""))
    )
    if normalized_stat == "出血" and is_other_target:
        mod = _utils_module()
        bonus_fn = getattr(mod, "get_stack_variant_bleed_apply_bonus", None) if mod else None
        if callable(bonus_fn):
            try:
                total_bonus += int(bonus_fn(actor) or 0)
            except Exception:
                pass

    return total_bonus, buffs_to_remove

def calculate_state_receive_bonus(receiver, source, stat_name, context=None, get_status_value_fn=None):
    total_bonus = 0
    buffs_to_remove = []

    if not receiver or 'special_buffs' not in receiver:
        return 0, []

    def _resolve_stack_count(buff):
        """Resolve stack count from buff row. Default to 1 when unspecified."""
        if not isinstance(buff, dict):
            return 1
        raw_count = buff.get('count')
        if raw_count is None:
            data = buff.get('data')
            if isinstance(data, dict):
                raw_count = data.get('count')
        if raw_count is None:
            return 1
        try:
            return max(0, int(raw_count))
        except Exception:
            return 1

    for buff in receiver['special_buffs']:
        buff_name = buff.get('name')
        effect_data = _resolve_runtime_buff_effect_data(buff)
        if not effect_data:
            continue

        if not isinstance(effect_data, dict):
            effect_data = {}
        if not effect_data.get('state_receive_bonus'):
            try:
                from manager.buff_catalog import get_buff_by_id
                buff_id = str(
                    buff.get('buff_id')
                    or (buff.get('data') or {}).get('buff_id')
                    or ''
                ).strip()
                if buff_id:
                    buff_data = get_buff_by_id(buff_id)
                    if isinstance(buff_data, dict):
                        catalog_effect = buff_data.get('effect')
                        if isinstance(catalog_effect, dict) and catalog_effect.get('state_receive_bonus'):
                            merged = dict(catalog_effect)
                            merged.update(effect_data)
                            effect_data = merged
            except Exception:
                pass

        if buff.get('delay', 0) > 0:
            continue

        receive_rules = effect_data.get('state_receive_bonus', [])
        matching_rules = [r for r in receive_rules if r.get('stat') == stat_name]
        if not matching_rules:
            continue

        stack_count = _resolve_stack_count(buff)
        if stack_count <= 0:
            continue

        bonus_per_stack = _calculate_bonus_from_rules(matching_rules, receiver, source, None, context=context, get_status_value_fn=get_status_value_fn)
        bonus = bonus_per_stack * stack_count

        if bonus > 0:
            total_bonus += bonus
            for rule in matching_rules:
                if rule.get('consume'):
                    buffs_to_remove.append(buff_name)
                    break

    return total_bonus, buffs_to_remove
