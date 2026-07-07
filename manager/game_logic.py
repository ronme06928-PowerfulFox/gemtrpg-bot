# manager/game_logic.py
import copy
import sys
from manager.battle.effect_handlers import EFFECT_HANDLERS, EffectSession
from manager.battle.system_skills import ensure_system_skills_registered
from manager.battle import condition_eval as _condition_eval
from manager.battle import buff_power as _buff_power
from manager.battle import skill_effect_helpers as _skill_effect_helpers
from manager.battle import power_preview as _power_preview
from manager.battle import damage_multiplier as _damage_multiplier
from manager.battle import lifecycle_effects as _lifecycle_effects
from manager.buff_catalog import get_buff_effect, resolve_runtime_buff_effect
from manager.field_effects import (
    get_state_from_context,
    get_stage_damage_dealt_mod,
    get_stage_state_effects,
)
from manager.logs import setup_logger

logger = setup_logger(__name__)
ensure_system_skills_registered()


def _utils_module():
    return sys.modules.get('manager.utils')


def _effect_registry():
    plugins_mod = sys.modules.get("plugins")
    if plugins_mod is None:
        try:
            import plugins as plugins_mod  # type: ignore
        except Exception:
            return {}
    registry = getattr(plugins_mod, "EFFECT_REGISTRY", None)
    return registry if isinstance(registry, dict) else {}


def _fallback_get_status_value(char_obj, status_name):
    if not isinstance(char_obj, dict):
        return 0
    if status_name in ("HP", "hp"):
        return int(char_obj.get("hp", 0) or 0)
    if status_name in ("MP", "mp"):
        return int(char_obj.get("mp", 0) or 0)
    states = char_obj.get("states", [])
    if isinstance(states, list):
        hit = next((s for s in states if isinstance(s, dict) and s.get("name") == status_name), None)
        if isinstance(hit, dict):
            try:
                return int(hit.get("value", 0))
            except Exception:
                return 0
    return int(char_obj.get(status_name, 0) or 0)


def _stable_get_status_value(char_obj, status_name):
    state_stack_sum = _condition_eval._resolve_state_stack_sum_value(char_obj, status_name)
    if state_stack_sum is not None:
        return state_stack_sum

    mod = _utils_module()
    fn = getattr(mod, "get_status_value", None) if mod else None
    if callable(fn):
        try:
            primary = fn(char_obj, status_name)
        except Exception:
            primary = None
        fallback = _fallback_get_status_value(char_obj, status_name)
        try:
            primary_int = int(primary)
        except Exception:
            primary_int = primary
        # Prefer fallback only when the injected helper misses existing state/param values.
        if primary is None:
            return fallback
        if isinstance(primary_int, int) and primary_int == 0 and fallback != 0:
            return fallback
        return primary_int
    return _fallback_get_status_value(char_obj, status_name)


def get_status_value(char_obj, status_name):
    return _stable_get_status_value(char_obj, status_name)


def _stable_set_status_value(char_obj, status_name, value):
    mod = _utils_module()
    fn = getattr(mod, "set_status_value", None) if mod else None
    if callable(fn):
        try:
            result = fn(char_obj, status_name, value)
        except Exception:
            result = None
        if status_name in ("HP", "hp"):
            char_obj["hp"] = int(value or 0)
            return result
        if status_name in ("MP", "mp"):
            char_obj["mp"] = int(value or 0)
            return result

        expected = int(value or 0)
        states = char_obj.get("states", [])
        if not isinstance(states, list):
            states = []
            char_obj["states"] = states
        hit = next((s for s in states if isinstance(s, dict) and s.get("name") == status_name), None)
        if hit is None:
            states.append({"name": status_name, "value": expected})
        else:
            try:
                current = int(hit.get("value", 0) or 0)
            except Exception:
                current = None
            if current != expected:
                hit["value"] = expected
        return result
    if not isinstance(char_obj, dict):
        return None
    if status_name in ("HP", "hp"):
        char_obj["hp"] = int(value or 0)
        return None
    if status_name in ("MP", "mp"):
        char_obj["mp"] = int(value or 0)
        return None
    states = char_obj.setdefault("states", [])
    if not isinstance(states, list):
        states = []
        char_obj["states"] = states
    hit = next((s for s in states if isinstance(s, dict) and s.get("name") == status_name), None)
    if hit is None:
        states.append({"name": status_name, "value": int(value or 0)})
    else:
        hit["value"] = int(value or 0)
    return None


def set_status_value(char_obj, status_name, value):
    return _stable_set_status_value(char_obj, status_name, value)


def apply_buff(*args, **kwargs):
    mod = _utils_module()
    fn = getattr(mod, "apply_buff", None) if mod else None
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def remove_buff(*args, **kwargs):
    mod = _utils_module()
    fn = getattr(mod, "remove_buff", None) if mod else None
    if callable(fn):
        return fn(*args, **kwargs)
    try:
        char_obj = args[0] if len(args) >= 1 else kwargs.get("char_obj")
        buff_name = args[1] if len(args) >= 2 else kwargs.get("buff_name")
        if not isinstance(char_obj, dict):
            return None
        buffs = char_obj.get("special_buffs")
        if not isinstance(buffs, list):
            return None
        normalized_name = str(buff_name or "").strip()
        char_obj["special_buffs"] = [
            b for b in buffs
            if str((b or {}).get("name", "")).strip() != normalized_name
        ]
    except Exception:
        return None
    return None


def get_buff_stat_mod(char_obj, stat_name):
    mod = _utils_module()
    fn = getattr(mod, "get_buff_stat_mod", None) if mod else None
    if callable(fn):
        return fn(char_obj, stat_name)
    return 0


def get_buff_stat_mod_details(char_obj, stat_name):
    mod = _utils_module()
    fn = getattr(mod, "get_buff_stat_mod_details", None) if mod else None
    if callable(fn):
        return fn(char_obj, stat_name)
    return []


def resolve_placeholders(text, char_obj):
    mod = _utils_module()
    fn = getattr(mod, "resolve_placeholders", None) if mod else None
    if callable(fn):
        return fn(text, char_obj)
    return text


def get_effective_origin_id(char_obj):
    mod = _utils_module()
    fn = getattr(mod, "get_effective_origin_id", None) if mod else None
    if callable(fn):
        return fn(char_obj)
    return 0


def compute_origin_skill_modifiers(actor_char, target_char, skill_data, state=None, context=None):
    mod = _utils_module()
    fn = getattr(mod, "compute_origin_skill_modifiers", None) if mod else None
    if callable(fn):
        return fn(actor_char, target_char, skill_data, state=state, context=context)
    return {}


def build_origin_hit_changes(actor_char, target_char, context=None):
    mod = _utils_module()
    fn = getattr(mod, "build_origin_hit_changes", None) if mod else None
    if callable(fn):
        return fn(actor_char, target_char, context=context)
    return [], []

def _get_value_for_condition(source_obj, param_name, context=None, actor=None, target=None, source_type=None):
    return _condition_eval._get_value_for_condition(
        source_obj,
        param_name,
        context=context,
        actor=actor,
        target=target,
        source_type=source_type,
        get_status_value_fn=get_status_value,
    )


def check_condition(condition_obj, actor, target, target_skill_data=None, actor_skill_data=None, context=None):
    return _condition_eval.check_condition(
        condition_obj,
        actor,
        target,
        target_skill_data=target_skill_data,
        actor_skill_data=actor_skill_data,
        context=context,
        get_status_value_fn=get_status_value,
    )

def _calculate_bonus_from_rules(rules, actor, target, actor_skill_data=None, context=None):
    return _buff_power._calculate_bonus_from_rules(
        rules,
        actor,
        target,
        actor_skill_data=actor_skill_data,
        context=context,
        get_status_value_fn=get_status_value,
    )


def calculate_buff_power_bonus_parts(actor, target, actor_skill_data, context=None):
    return _buff_power.calculate_buff_power_bonus_parts(
        actor,
        target,
        actor_skill_data,
        context=context,
        get_status_value_fn=get_status_value,
    )


def calculate_buff_power_bonus(actor, target, actor_skill_data, context=None):
    return _buff_power.calculate_buff_power_bonus(
        actor,
        target,
        actor_skill_data,
        context=context,
        get_status_value_fn=get_status_value,
    )


def calculate_state_apply_bonus(actor, target, stat_name, context=None):
    return _buff_power.calculate_state_apply_bonus(
        actor,
        target,
        stat_name,
        context=context,
        get_status_value_fn=get_status_value,
    )


def calculate_state_receive_bonus(receiver, source, stat_name, context=None):
    return _buff_power.calculate_state_receive_bonus(
        receiver,
        source,
        stat_name,
        context=context,
        get_status_value_fn=get_status_value,
    )

def execute_custom_effect(effect, actor, target, context=None):
    """Execute a registered CUSTOM_EFFECT handler."""
    effect_name = effect.get("value")
    registry = _effect_registry()
    handler = registry.get(effect_name)

    if not handler:
        logger.debug(f"Unknown CUSTOM_EFFECT '{effect_name}'")
        return [], []

    try:
        plugin_context = {
            "registry": registry
        }
        if isinstance(context, dict):
            plugin_context.update(context)
            plugin_context["registry"] = registry
        return handler.apply(actor, target, effect, plugin_context)
    except Exception as e:
        logger.error(f"Plugin Error ({effect_name}): {e}")
        return [], []

def process_skill_effects(effects_array, timing_to_check, actor, target, target_skill_data=None, context=None, base_damage=0):
    session = EffectSession(
        actor=actor,
        target=target,
        timing=timing_to_check,
        context=context,
        base_damage=base_damage,
        get_status_value_fn=_stable_get_status_value,
        set_status_value_fn=_stable_set_status_value,
    )
    log_snippets = session.log_snippets
    changes_to_apply = session.changes_to_apply

    if not actor:
        return 0, [], []
    if not effects_array and timing_to_check != "HIT":
        return 0, [], []

    if timing_to_check == "HIT":
        origin_logs, origin_changes = build_origin_hit_changes(actor, target, context=context)
        if origin_logs:
            log_snippets.extend(origin_logs)
        if origin_changes:
            changes_to_apply.extend(origin_changes)

    stage_state = get_state_from_context(context)
    if timing_to_check in ("PRE_MATCH", "BEFORE_POWER_ROLL", "HIT", "UNOPPOSED"):
        stage_damage_mod = get_stage_damage_dealt_mod(stage_state, actor)
        if stage_damage_mod != 0:
            session.total_bonus_damage += int(stage_damage_mod)
            log_snippets.append(f"[StageDamage {stage_damage_mod:+} source=stage]")
    if timing_to_check == "HIT" and isinstance(target, dict):
        for st_name, st_value, rule_id in get_stage_state_effects(stage_state, target):
            if st_value == 0:
                continue
            changes_to_apply.append((target, "APPLY_STATE", st_name, st_value))
            rid = f" rule={rule_id}" if rule_id else ""
            log_snippets.append(f"[StageState {st_name}{st_value:+} source=stage{rid}]")

    select_random_targets = _skill_effect_helpers.select_random_targets

    get_simulated_char = session.get_simulated_char

    # Original hit target (before per-effect target remapping like target=self).
    original_sim_target = get_simulated_char(target) if target else None
    session.original_sim_target = original_sim_target

    _resolve_buff_count_local = _skill_effect_helpers.resolve_buff_count
    _find_sim_buff = _skill_effect_helpers.find_sim_buff
    _find_sim_buff_by_id = _skill_effect_helpers.find_sim_buff_by_id
    _set_sim_buff_count = _skill_effect_helpers.set_sim_buff_count
    _queue_remaining_buff = session.queue_remaining_buff
    _read_stack_variant_local = _skill_effect_helpers.read_stack_variant
    _is_chikuryoku_burst_guidance_variant = _skill_effect_helpers.is_chikuryoku_burst_guidance_variant

    def _apply_chikuryoku_burst_guidance_on_hit():
        if timing_to_check != "HIT":
            return
        if not isinstance(actor, dict) or not isinstance(target, dict):
            return
        actor_team = str(actor.get("type") or "").strip().lower()
        target_team = str(target.get("type") or "").strip().lower()
        if not actor_team or not target_team or actor_team == target_team:
            return

        sim_actor = get_simulated_char(actor)
        sim_target = original_sim_target if isinstance(original_sim_target, dict) else get_simulated_char(target)
        if not isinstance(sim_actor, dict) or not isinstance(sim_target, dict):
            return

        rupture = _stable_get_status_value(sim_target, "破裂")
        try:
            rupture = int(rupture or 0)
        except Exception:
            rupture = 0
        if rupture < 1:
            return

        sim_bucket = _find_sim_buff_by_id(sim_actor, "Bu-30")
        if not isinstance(sim_bucket, dict):
            sim_bucket = _find_sim_buff(sim_actor, "蓄力")
        if not isinstance(sim_bucket, dict):
            return

        variant = _read_stack_variant_local(sim_bucket)
        if not _is_chikuryoku_burst_guidance_variant(variant):
            return

        current_count = _resolve_buff_count_local(sim_bucket, default=0)
        if current_count < 10:
            return
        remaining = current_count - 10

        bucket_name = str(sim_bucket.get("name") or "蓄力")
        _set_sim_buff_count(sim_actor, bucket_name, remaining)
        _queue_remaining_buff(actor, sim_bucket, bucket_name, remaining)

        burst_effect = {
            "value": "破裂爆発",
            "rupture_remainder_ratio": 1.0,
            "no_rupture_consume": True,
        }
        custom_changes, custom_logs = execute_custom_effect(burst_effect, sim_actor, sim_target, context=context)
        remapped_changes = []
        for c, t, n, v in custom_changes:
            mapped_char = c
            if c is sim_actor:
                mapped_char = actor
            elif c is sim_target:
                mapped_char = target
            remapped_changes.append((mapped_char, t, n, v))
        changes_to_apply.extend(remapped_changes)
        log_snippets.append(f"[蓄力-誘爆 10消費 ({current_count}->{remaining})]")
        log_snippets.extend(custom_logs)

    _apply_chikuryoku_burst_guidance_on_hit()

    _expand_repeated_effects = _skill_effect_helpers.expand_repeated_effects

    effects_array = _expand_repeated_effects(effects_array)

    for effect in effects_array:
        if effect.get("timing") != timing_to_check: continue

        effect_type = effect.get("type")
        targets_list = []

        # Target Resolution
        t_select = effect.get("target_select") # NORMAL (default), RANDOM

        if t_select == "RANDOM":
            if context and "characters" in context:
                targets_list = select_random_targets(actor, effect, context["characters"])
                if not targets_list:
                    log_snippets.append("(対象なし)")
            else:
                 pass
        else:
            # Standard targeting
            t_str = effect.get("target")
            if not t_str: t_str = "target" # Default to target if not specified

            if t_str == "self": targets_list = [actor]
            elif t_str == "target": targets_list = [target] if target else []
            elif t_str == "ALL_ENEMIES" and context and "characters" in context:
                actor_type = actor.get("type", "ally")
                target_type = "enemy" if actor_type == "ally" else "ally"
                targets_list = [c for c in context["characters"] if c.get("type") == target_type and c.get('hp', 0) > 0]
            elif t_str == "ALL_ALLIES" and context and "characters" in context:
                actor_type = actor.get("type", "ally")
                targets_list = [c for c in context["characters"] if c.get("type") == actor_type and c.get('hp', 0) > 0]
            elif t_str == "ALL_OTHER_ALLIES" and context and "characters" in context:
                actor_type = actor.get("type", "ally")
                actor_id = actor.get("id")
                targets_list = [
                    c for c in context["characters"]
                    if c.get("type") == actor_type
                    and c.get('hp', 0) > 0
                    and str(c.get("id")) != str(actor_id)
                ]
            elif t_str == "ALL" and context and "characters" in context:
                 targets_list = [c for c in context["characters"] if c.get('hp', 0) > 0]
            # 笘・眠讖溯・: NEXT_ALLY
            elif t_str == "NEXT_ALLY" and context and "characters" in context and context.get("room"):
                from manager.room_manager import get_room_state
                room_name = context.get("room")
                if room_name:
                    state = get_room_state(room_name)
                    timeline = state.get('timeline', [])

                    if timeline and actor:
                        my_id = actor.get('id')
                        my_type = actor.get('type', 'ally')
                        start_idx = -1
                        try:
                            start_idx = timeline.index(my_id)
                        except ValueError:
                            pass
                        target_id = None
                        search_indices = list(range(start_idx + 1, len(timeline))) + list(range(0, start_idx))
                        for idx in search_indices:
                            tid = timeline[idx]
                            t_char = next((c for c in state['characters'] if c['id'] == tid), None)
                            if t_char and t_char.get('type') == my_type and t_char.get('hp', 0) > 0:
                                target_id = tid
                                break
                        if target_id:
                            found = next((c for c in state['characters'] if c['id'] == target_id), None)
                            if found: targets_list = [found]

        if not targets_list: continue

        for target_obj in targets_list:
            sim_actor = get_simulated_char(actor)
            sim_target = get_simulated_char(target_obj)

            if not check_condition(effect.get("condition"), sim_actor, sim_target, target_skill_data, context=context):
                continue

            handler = EFFECT_HANDLERS.get(effect_type)
            if handler is not None:
                handler(effect, target_obj, sim_target, session)
                continue

            if effect_type == "CUSTOM_EFFECT":
                custom_target_sim = sim_actor if effect.get("target") == "self" else sim_target
                custom_changes, custom_logs = execute_custom_effect(effect, sim_actor, custom_target_sim, context=context)

                remapped_changes = []
                for c, t, n, v in custom_changes:
                    mapped_char = c
                    if c is sim_actor:
                        mapped_char = actor
                    elif c is sim_target:
                        mapped_char = target_obj
                    remapped_changes.append((mapped_char, t, n, v))

                changes_to_apply.extend(remapped_changes)
                log_snippets.extend(custom_logs)
    return session.total_bonus_damage, session.log_snippets, session.changes_to_apply

def calculate_power_bonus(actor, target, power_bonus_data, context=None):
    return _power_preview.calculate_power_bonus(
        actor,
        target,
        power_bonus_data,
        context=context,
        get_value_for_condition_fn=_get_value_for_condition,
    )


def calculate_skill_preview(
    actor_char,
    target_char,
    skill_data,
    rule_data=None,
    custom_skill_name=None,
    senritsu_max_apply=0,
    external_base_power_mod=0,
    external_final_power_mod=0,
    context=None
):
    return _power_preview.calculate_skill_preview(
        actor_char,
        target_char,
        skill_data,
        rule_data=rule_data,
        custom_skill_name=custom_skill_name,
        senritsu_max_apply=senritsu_max_apply,
        external_base_power_mod=external_base_power_mod,
        external_final_power_mod=external_final_power_mod,
        context=context,
        deps={
            'compute_origin_skill_modifiers': compute_origin_skill_modifiers,
            'get_buff_stat_mod': get_buff_stat_mod,
            'get_status_value': get_status_value,
            'calculate_buff_power_bonus_parts': calculate_buff_power_bonus_parts,
            'get_effective_origin_id': get_effective_origin_id,
            'resolve_placeholders': resolve_placeholders,
        },
    )

def build_power_result_snapshot(preview_data, roll_result):
    return _power_preview.build_power_result_snapshot(preview_data, roll_result)

def compute_damage_multipliers(attacker, defender, context=None):
    return _damage_multiplier.compute_damage_multipliers(
        attacker,
        defender,
        context=context,
        check_condition_fn=check_condition,
    )


def calculate_damage_multiplier(character):
    return _damage_multiplier.calculate_damage_multiplier(
        character,
        check_condition_fn=check_condition,
    )

def _lifecycle_effect_context():
    return {
        'apply_buff': apply_buff,
        'get_buff_effect': get_buff_effect,
        'get_status_value': get_status_value,
        'logger': logger,
        'process_skill_effects': process_skill_effects,
    }


def process_on_death(room, char, username):
    return _lifecycle_effects.process_on_death(
        room,
        char,
        username,
        _lifecycle_effect_context(),
    )


def process_battle_start(room, char):
    return _lifecycle_effects.process_battle_start(
        room,
        char,
        _lifecycle_effect_context(),
    )

