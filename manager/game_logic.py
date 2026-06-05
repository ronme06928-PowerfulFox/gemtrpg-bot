# manager/game_logic.py
import sys
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
    total_bonus_damage = 0
    log_snippets = []
    changes_to_apply = []

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
            total_bonus_damage += int(stage_damage_mod)
            log_snippets.append(f"[StageDamage {stage_damage_mod:+} source=stage]")
    if timing_to_check == "HIT" and isinstance(target, dict):
        for st_name, st_value, rule_id in get_stage_state_effects(stage_state, target):
            if st_value == 0:
                continue
            changes_to_apply.append((target, "APPLY_STATE", st_name, st_value))
            rid = f" rule={rule_id}" if rule_id else ""
            log_snippets.append(f"[StageState {st_name}{st_value:+} source=stage{rid}]")

    select_random_targets = _skill_effect_helpers.select_random_targets

    import copy

    simulated_chars = {}

    def get_simulated_char(real_char):
        if not real_char: return None
        cid = real_char.get('id')
        if cid not in simulated_chars:
            simulated_chars[cid] = copy.deepcopy(real_char)
        return simulated_chars[cid]

    # Original hit target (before per-effect target remapping like target=self).
    original_sim_target = get_simulated_char(target) if target else None

    _parse_positive_rounds = _skill_effect_helpers.parse_positive_rounds

    def _queue_fissure_round_buff(target_obj, sim_target, amount, rounds, source='skill'):
        amount = int(amount or 0)
        rounds = int(rounds or 0)
        if amount <= 0 or rounds <= 0:
            return

        current_val = _stable_get_status_value(sim_target, "亀裂")
        _stable_set_status_value(sim_target, "亀裂", current_val + amount)

        changes_to_apply.append((
            target_obj,
            "APPLY_BUFF",
            f"亀裂_R{rounds}",
            {
                "lasting": rounds,
                "delay": 0,
                "data": {
                    "buff_id": "Bu-Fissure",
                    "source": source,
                    "count": amount,
                    "fissure_count": amount,
                    "original_rounds": rounds
                }
            }
        ))

    _normalize_buff_name_local = _skill_effect_helpers.normalize_buff_name
    _resolve_buff_count_local = _skill_effect_helpers.resolve_buff_count
    _find_sim_buff = _skill_effect_helpers.find_sim_buff
    _find_sim_buff_by_id = _skill_effect_helpers.find_sim_buff_by_id
    _set_sim_buff_count = _skill_effect_helpers.set_sim_buff_count

    def _queue_remaining_buff(target_obj, sim_bucket, buff_name, remaining):
        changes_to_apply.append((target_obj, "REMOVE_BUFF", buff_name, 0))
        if remaining <= 0:
            return

        preserved_data = {}
        preserved_lasting = -1
        preserved_delay = 0
        explicit_lasting = False
        if isinstance(sim_bucket, dict):
            preserved_data = dict(sim_bucket.get("data") or {})
            try:
                preserved_lasting = int(sim_bucket.get("lasting", -1))
            except (TypeError, ValueError):
                preserved_lasting = -1
            try:
                preserved_delay = int(sim_bucket.get("delay", 0))
            except (TypeError, ValueError):
                preserved_delay = 0
            explicit_lasting = ("lasting" in sim_bucket)
            if sim_bucket.get("buff_id") and "buff_id" not in preserved_data:
                preserved_data["buff_id"] = sim_bucket.get("buff_id")
            if sim_bucket.get("description") and "description" not in preserved_data:
                preserved_data["description"] = sim_bucket.get("description")
            if sim_bucket.get("flavor") and "flavor" not in preserved_data:
                preserved_data["flavor"] = sim_bucket.get("flavor")

        preserved_data["count"] = remaining
        changes_to_apply.append((
            target_obj,
            "APPLY_BUFF",
            buff_name,
            {
                "lasting": preserved_lasting,
                "delay": preserved_delay,
                "count": remaining,
                "data": preserved_data,
                "explicit_lasting": explicit_lasting,
            }
        ))

    _simulate_apply_buff_stack = _skill_effect_helpers.simulate_apply_buff_stack
    _simulate_remove_buff_stack = _skill_effect_helpers.simulate_remove_buff_stack
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

            if effect_type == "APPLY_FISSURE_BUFFED":
                rounds = _parse_positive_rounds(effect.get("rounds"))
                value = int(effect.get("value", 0))
                if rounds <= 0 or value <= 0:
                    continue

                if not sim_target:
                    continue
                if 'flags' not in sim_target:
                    sim_target['flags'] = {}
                if sim_target['flags'].get('fissure_received_this_round', False):
                    log_snippets.append("[亀裂付与失敗: 同一ラウンド内で既に亀裂付与済み]")
                    continue

                bonus, buffs_to_remove = calculate_state_apply_bonus(sim_actor, sim_target, "亀裂", context=context)
                final_value = value + max(0, int(bonus or 0))
                if final_value <= 0:
                    continue

                for b_name in buffs_to_remove:
                    remove_buff(sim_actor, b_name)
                    changes_to_apply.append((actor, "REMOVE_BUFF", b_name, 0))
                    log_snippets.append(f"[{b_name} 消費]")

                _queue_fissure_round_buff(
                    target_obj=target_obj,
                    sim_target=sim_target,
                    amount=final_value,
                    rounds=rounds,
                    source=effect.get("source", "skill"),
                )
                sim_target['flags']['fissure_received_this_round'] = True
                changes_to_apply.append((target_obj, "SET_FLAG", "fissure_received_this_round", True))
                log_snippets.append(f"[亀裂 {final_value} ({rounds}R)]")
                continue

            elif effect_type == "APPLY_STATE":
                stat_name = effect.get("state_name") or effect.get("name")
                value = int(effect.get("value", 0))
                fissure_rounds = _parse_positive_rounds(effect.get("rounds"))

                if stat_name == "亀裂" and value > 0 and sim_target:
                    if 'flags' not in sim_target:
                        sim_target['flags'] = {}
                    if sim_target['flags'].get('fissure_received_this_round', False):
                        log_snippets.append("[亀裂付与失敗: 同一ラウンド内で既に亀裂付与済み]")
                        continue

                if value > 0:
                    if sim_actor:
                        source_bonus, source_buffs_to_remove = calculate_state_apply_bonus(
                            sim_actor, sim_target, stat_name, context=context
                        )
                        if source_bonus > 0:
                            value += source_bonus
                        for b_name in source_buffs_to_remove:
                            remove_buff(sim_actor, b_name)
                            changes_to_apply.append((actor, "REMOVE_BUFF", b_name, 0))
                            log_snippets.append(f"[{b_name} 消費]")

                    if sim_target:
                        receive_bonus, receive_buffs_to_remove = calculate_state_receive_bonus(
                            sim_target, sim_actor, stat_name, context=context
                        )
                        if receive_bonus > 0:
                            value += receive_bonus
                        for b_name in receive_buffs_to_remove:
                            remove_buff(sim_target, b_name)
                            changes_to_apply.append((target_obj, "REMOVE_BUFF", b_name, 0))
                            log_snippets.append(f"[{b_name} 消費]")

                if stat_name and value != 0:
                    if stat_name == "亀裂" and value > 0 and fissure_rounds > 0:
                        _queue_fissure_round_buff(
                            target_obj=target_obj,
                            sim_target=sim_target,
                            amount=value,
                            rounds=fissure_rounds,
                            source=effect.get("source", "skill"),
                        )
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        sim_target['flags']['fissure_received_this_round'] = True
                        changes_to_apply.append((target_obj, "SET_FLAG", "fissure_received_this_round", True))
                        log_snippets.append(f"[亀裂 {value} ({fissure_rounds}R)]")
                        continue

                    current_val = _stable_get_status_value(sim_target, stat_name)
                    _stable_set_status_value(sim_target, stat_name, current_val + value)

                    changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, value))

                    if stat_name == "亀裂" and value > 0:
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        sim_target['flags']['fissure_received_this_round'] = True
                        changes_to_apply.append((target_obj, "SET_FLAG", "fissure_received_this_round", True))


            elif effect_type == "APPLY_STATE_PER_N":
                source_type = effect.get("source", "self")
                if source_type == "self":
                    source_obj = sim_actor
                else:
                    # source=target should still point to the original action target
                    # when this effect itself is applied to self.
                    source_obj = original_sim_target if effect.get("target") == "self" and original_sim_target else sim_target
                source_param = effect.get("source_param")
                fissure_rounds = _parse_positive_rounds(effect.get("rounds"))

                if not source_obj or not source_param:
                    continue

                source_param_value = _get_value_for_condition(
                    source_obj,
                    source_param,
                    context=context,
                    actor=sim_actor,
                    target=sim_target,
                    source_type=source_type,
                )
                if source_param_value is None:
                    source_param_value = 0

                per_N = int(effect.get("per_N", 1))
                value_per = int(effect.get("value", 1))
                calculated_value = (source_param_value // per_N) * value_per if per_N > 0 else 0

                if "max_value" in effect:
                    calculated_value = min(calculated_value, int(effect["max_value"]))

                stat_name = effect.get("state_name")
                if stat_name and calculated_value > 0:
                    if stat_name == "亀裂" and sim_target:
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        if sim_target['flags'].get('fissure_received_this_round', False):
                            log_snippets.append("[亀裂付与失敗: 同一ラウンド内で既に亀裂付与済み]")
                            continue

                    if sim_actor:
                        source_bonus, source_buffs_to_remove = calculate_state_apply_bonus(
                            sim_actor, sim_target, stat_name, context=context
                        )
                        if source_bonus > 0:
                            calculated_value += source_bonus
                        for b_name in source_buffs_to_remove:
                            remove_buff(sim_actor, b_name)
                            changes_to_apply.append((actor, "REMOVE_BUFF", b_name, 0))
                            log_snippets.append(f"[{b_name} 消費]")

                    if sim_target:
                        receive_bonus, receive_buffs_to_remove = calculate_state_receive_bonus(
                            sim_target, sim_actor, stat_name, context=context
                        )
                        if receive_bonus > 0:
                            calculated_value += receive_bonus
                        for b_name in receive_buffs_to_remove:
                            remove_buff(sim_target, b_name)
                            changes_to_apply.append((target_obj, "REMOVE_BUFF", b_name, 0))
                            log_snippets.append(f"[{b_name} 消費]")

                    if stat_name == "亀裂" and fissure_rounds > 0:
                        _queue_fissure_round_buff(
                            target_obj=target_obj,
                            sim_target=sim_target,
                            amount=calculated_value,
                            rounds=fissure_rounds,
                            source=effect.get("source", "skill"),
                        )
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        sim_target['flags']['fissure_received_this_round'] = True
                        changes_to_apply.append((target_obj, "SET_FLAG", "fissure_received_this_round", True))
                        log_snippets.append(f"[亀裂 {calculated_value} ({source_param}{source_param_value}/{fissure_rounds}R)]")
                        continue

                    current_val = _stable_get_status_value(sim_target, stat_name)
                    _stable_set_status_value(sim_target, stat_name, current_val + calculated_value)

                    changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, calculated_value))
                    log_snippets.append(f"[{stat_name} +{calculated_value} ({source_param}={source_param_value})]")

                    if stat_name == "亀裂":
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        sim_target['flags']['fissure_received_this_round'] = True
                        changes_to_apply.append((target_obj, "SET_FLAG", "fissure_received_this_round", True))


            elif effect_type == "MULTIPLY_STATE":
                stat_name = effect.get("state_name")
                multiplier = float(effect.get("value", 1.0))

                if stat_name and sim_target:
                    current_val = _stable_get_status_value(sim_target, stat_name)
                    new_val = int(current_val * multiplier + 0.5)
                    diff = new_val - current_val

                    if diff != 0:
                        _stable_set_status_value(sim_target, stat_name, new_val)

                        changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, diff))
                        log_snippets.append(f"[{stat_name} x{multiplier} ({current_val}->{new_val})]")


            elif effect_type == "APPLY_BUFF_PER_N":
                source_type = effect.get("source", "self")
                if source_type == "self":
                    source_obj = sim_actor
                else:
                    source_obj = original_sim_target if effect.get("target") == "self" and original_sim_target else sim_target
                source_param = effect.get("source_param")
                if not source_obj or not source_param:
                    continue

                try:
                    per_n = int(effect.get("per_N", 1))
                except (TypeError, ValueError):
                    per_n = 1
                if per_n <= 0:
                    continue

                try:
                    value_per_step = int(effect.get("value", 1))
                except (TypeError, ValueError):
                    value_per_step = 1
                if value_per_step <= 0:
                    continue

                source_value = _get_value_for_condition(
                    source_obj,
                    source_param,
                    context=context,
                    actor=sim_actor,
                    target=sim_target,
                    source_type=source_type,
                )
                if source_value is None:
                    source_value = 0
                apply_count = (source_value // per_n) * value_per_step
                try:
                    max_count = int(effect.get("max_count", 0))
                except (TypeError, ValueError):
                    max_count = 0
                if max_count > 0:
                    apply_count = min(apply_count, max_count)
                if apply_count <= 0:
                    continue

                buff_name = effect.get("buff_name")
                buff_id = effect.get("buff_id")
                if not buff_name and buff_id:
                    from manager.buff_catalog import get_buff_by_id
                    buff_data = get_buff_by_id(buff_id)
                    if buff_data:
                        buff_name = buff_data.get("name")
                if not buff_name:
                    continue

                effect_data = effect.get("data")
                if effect_data is None:
                    effect_data = {}
                elif isinstance(effect_data, dict):
                    effect_data = effect_data.copy()
                else:
                    effect_data = {}
                if buff_id:
                    effect_data["buff_id"] = buff_id
                effect_data["count"] = apply_count

                try:
                    parsed_lasting = int(effect.get("lasting", 1))
                except (TypeError, ValueError):
                    parsed_lasting = 1
                try:
                    parsed_delay = int(effect.get("delay", 0))
                except (TypeError, ValueError):
                    parsed_delay = 0
                buff_payload = {
                    "lasting": parsed_lasting,
                    "delay": parsed_delay,
                    "data": effect_data,
                    "explicit_lasting": ("lasting" in effect),
                    "count": apply_count,
                }
                changes_to_apply.append((target_obj, "APPLY_BUFF", buff_name, buff_payload))
                before_count, after_count, delta_count = _simulate_apply_buff_stack(sim_target, buff_name, buff_payload)
                log_snippets.append(f"[{buff_name} 付与]")
                if delta_count != 0:
                    log_snippets.append(f"[{buff_name} スタック +{delta_count} ({before_count}->{after_count})]")
                log_snippets.append(f"[{buff_name} 条件: {source_param}={source_value}, per={per_n}]")

            elif effect_type == "APPLY_BUFF":
                buff_name = effect.get("buff_name")
                buff_id = effect.get("buff_id")

                if not buff_name and buff_id:
                    from manager.buff_catalog import get_buff_by_id
                    buff_data = get_buff_by_id(buff_id)
                    if buff_data:
                        buff_name = buff_data.get("name")
                        logger.debug(f"Resolved buff_id '{buff_id}' to buff_name '{buff_name}'")
                    else:
                        logger.warning(f"buff_id '{buff_id}' not found in catalog")

                if buff_name:
                    effect_data = effect.get("data")
                    if effect_data is None:
                        effect_data = {}
                    else:
                        effect_data = effect_data.copy()

                    if buff_id:
                        effect_data["buff_id"] = buff_id

                        if 'buff_data' in locals() and buff_data:
                            if "description" not in effect_data:
                                effect_data["description"] = buff_data.get("description", "")
                            if "flavor" not in effect_data:
                                effect_data["flavor"] = buff_data.get("flavor", "")

                            catalog_effect = buff_data.get("effect", {})
                            if catalog_effect.get("type") == "stat_mod":
                                stat_name = catalog_effect.get("stat")
                                mod_value = catalog_effect.get("value")

                                if stat_name and mod_value is not None:
                                    if "stat_mods" not in effect_data:
                                        effect_data["stat_mods"] = {}
                                    effect_data["stat_mods"][stat_name] = mod_value
                                    # print(f"[APPLY_BUFF] Converted stat_mod for {buff_name}: {stat_name}={mod_value}")

                    from manager.buff_catalog import get_buff_effect
                    catalog_effect_data = get_buff_effect(buff_name)
                    if isinstance(catalog_effect_data, dict):
                        for k, v in catalog_effect_data.items():
                            if k not in effect_data:
                                effect_data[k] = v
                            elif k == "stat_mods" and isinstance(v, dict):
                                if "stat_mods" not in effect_data:
                                    effect_data["stat_mods"] = {}
                                for sk, sv in v.items():
                                    if sk not in effect_data["stat_mods"]:
                                        effect_data["stat_mods"][sk] = sv

                    if "flavor" in effect:
                        effect_data["flavor"] = effect["flavor"]

                    default_lasting = -1 if _normalize_buff_name_local(buff_name) in {"蓄力", "凝魔"} else 1
                    raw_lasting = effect.get("lasting", default_lasting)
                    try:
                        parsed_lasting = int(raw_lasting)
                    except (TypeError, ValueError):
                        parsed_lasting = default_lasting
                    try:
                        parsed_delay = int(effect.get("delay", 0))
                    except (TypeError, ValueError):
                        parsed_delay = 0
                    buff_payload = {
                        "lasting": parsed_lasting,
                        "delay": parsed_delay,
                        "data": effect_data,
                        "explicit_lasting": ("lasting" in effect),
                    }
                    if "count" in effect:
                        try:
                            parsed_count = int(effect.get("count"))
                        except (TypeError, ValueError):
                            parsed_count = 0
                        if parsed_count > 0:
                            buff_payload["count"] = parsed_count
                            if isinstance(effect_data, dict) and "count" not in effect_data:
                                effect_data["count"] = parsed_count
                    changes_to_apply.append((target_obj, "APPLY_BUFF", buff_name, buff_payload))
                    before_count, after_count, delta_count = _simulate_apply_buff_stack(sim_target, buff_name, buff_payload)
                    log_snippets.append(f"[{buff_name} 付与]")
                    if delta_count != 0:
                        log_snippets.append(f"[{buff_name} スタック +{delta_count} ({before_count}->{after_count})]")

            elif effect_type == "CONVERT_STACK_RESOURCE_VARIANT":
                resource_name = (
                    effect.get("resource_name")
                    or effect.get("resource")
                    or effect.get("buff_name")
                    or ""
                )
                to_variant = str(effect.get("to_variant") or effect.get("variant") or "").strip()
                if not resource_name or not to_variant:
                    continue

                try:
                    require_count = int(
                        effect.get("require_count_gte", effect.get("require_count", effect.get("min_count", 1)))
                    )
                except (TypeError, ValueError):
                    require_count = 1
                require_count = max(1, require_count)

                mod = _utils_module()
                resolve_name_fn = getattr(mod, "resolve_stack_resource_name", None) if mod else None
                canonical_resource_name = str(resource_name).strip()
                resource_key = canonical_resource_name.lower()
                preferred_buff_id = ""
                if ("gyoma" in resource_key) or ("凝魔" in canonical_resource_name):
                    preferred_buff_id = "Bu-31"
                elif ("chikuryoku" in resource_key) or ("蓄力" in canonical_resource_name):
                    preferred_buff_id = "Bu-30"

                sim_bucket = None
                if preferred_buff_id:
                    sim_bucket = _find_sim_buff_by_id(sim_target, preferred_buff_id)
                if not isinstance(sim_bucket, dict):
                    sim_bucket = _find_sim_buff(sim_target, canonical_resource_name)
                if not isinstance(sim_bucket, dict) and callable(resolve_name_fn):
                    try:
                        resolved = str(resolve_name_fn(resource_name) or "").strip()
                    except Exception:
                        resolved = ""
                    if resolved:
                        sim_bucket = _find_sim_buff(sim_target, resolved)
                if not isinstance(sim_bucket, dict):
                    # Last-resort fallback by known stack-resource buff IDs.
                    if preferred_buff_id:
                        sim_bucket = _find_sim_buff_by_id(sim_target, preferred_buff_id)
                    if not isinstance(sim_bucket, dict):
                        fallback_rows = [
                            _find_sim_buff_by_id(sim_target, "Bu-31"),
                            _find_sim_buff_by_id(sim_target, "Bu-30"),
                        ]
                        if preferred_buff_id == "Bu-30":
                            fallback_rows.reverse()
                        for row in fallback_rows:
                            if isinstance(row, dict) and _resolve_buff_count_local(row, default=0) > 0:
                                sim_bucket = row
                                break

                current_count = _resolve_buff_count_local(sim_bucket, default=0)
                if current_count < require_count:
                    log_snippets.append(f"[{canonical_resource_name} 不足 {current_count}/{require_count}]")
                    continue
                if not isinstance(sim_bucket, dict):
                    continue
                canonical_resource_name = str(sim_bucket.get("name") or canonical_resource_name).strip()

                if not isinstance(sim_bucket.get("data"), dict):
                    sim_bucket["data"] = {}
                sim_bucket["variant"] = to_variant
                sim_bucket["data"]["variant"] = to_variant

                # Avoid remove/re-apply on conversion to prevent accidental stack duplication.
                # Persist variant directly to the live target row as well.
                live_bucket = None
                if preferred_buff_id:
                    live_bucket = _find_sim_buff_by_id(target_obj, preferred_buff_id)
                if not isinstance(live_bucket, dict):
                    live_bucket = _find_sim_buff(target_obj, canonical_resource_name)
                if not isinstance(live_bucket, dict) and callable(resolve_name_fn):
                    try:
                        resolved_live = str(resolve_name_fn(resource_name) or "").strip()
                    except Exception:
                        resolved_live = ""
                    if resolved_live:
                        live_bucket = _find_sim_buff(target_obj, resolved_live)
                if isinstance(live_bucket, dict):
                    if not isinstance(live_bucket.get("data"), dict):
                        live_bucket["data"] = {}
                    live_bucket["variant"] = to_variant
                    live_bucket["data"]["variant"] = to_variant

                log_snippets.append(f"[{canonical_resource_name} 変換: {to_variant}]")

            elif effect_type == "CONSUME_BUFF_COUNT_FOR_GAIN":
                buff_name = effect.get("buff_name")
                if not buff_name:
                    continue
                try:
                    consume_required = int(effect.get("consume_required", 0))
                except (TypeError, ValueError):
                    consume_required = 0
                if consume_required <= 0:
                    continue

                sim_bucket = _find_sim_buff(sim_target, buff_name)
                current_count = _resolve_buff_count_local(sim_bucket, default=0)
                consumed_by_state = False
                if current_count < consume_required:
                    state_current = _stable_get_status_value(sim_target, buff_name)
                    try:
                        state_current = int(state_current or 0)
                    except Exception:
                        state_current = 0
                    if state_current < consume_required:
                        log_snippets.append(f"[{buff_name}不足 {current_count}/{consume_required}]")
                        continue
                    remaining = state_current - consume_required
                    _stable_set_status_value(sim_target, buff_name, remaining)
                    changes_to_apply.append((target_obj, "APPLY_STATE", buff_name, -consume_required))
                    current_count = state_current
                    consumed_by_state = True
                else:
                    remaining = current_count - consume_required
                    _set_sim_buff_count(sim_target, buff_name, remaining)
                    _queue_remaining_buff(target_obj, sim_bucket, buff_name, remaining)

                gains = effect.get("gains", [])
                if isinstance(gains, dict):
                    gains = [gains]
                gain_count = 0
                if isinstance(gains, list):
                    for gain in gains:
                        if not isinstance(gain, dict):
                            continue
                        gain_target_type = str(gain.get("target", effect.get("target", "self")) or "self").strip().lower()
                        if gain_target_type == "self":
                            gain_target_obj = actor
                        elif gain_target_type == "target":
                            gain_target_obj = target if effect.get("target") == "self" and target is not None else target_obj
                        else:
                            gain_target_obj = target_obj
                        sim_gain_target = get_simulated_char(gain_target_obj) if gain_target_obj else None
                        if sim_gain_target is None:
                            continue

                        gain_type = str(gain.get("type", "")).strip().upper()
                        if gain_type in {"FP", "MP", "HP"}:
                            try:
                                gain_value = int(gain.get("value", 0))
                            except (TypeError, ValueError):
                                gain_value = 0
                            if gain_value == 0:
                                continue
                            current_val = _stable_get_status_value(sim_gain_target, gain_type)
                            _stable_set_status_value(sim_gain_target, gain_type, current_val + gain_value)
                            changes_to_apply.append((gain_target_obj, "APPLY_STATE", gain_type, gain_value))
                            gain_count += 1
                        elif gain_type in {"STATE", "APPLY_STATE"}:
                            gain_state_name = str(gain.get("state_name", gain.get("name", "")) or "").strip()
                            if not gain_state_name:
                                continue
                            try:
                                gain_value = int(gain.get("value", 0))
                            except (TypeError, ValueError):
                                gain_value = 0
                            if gain_value == 0:
                                continue
                            try:
                                gain_rounds = int(gain.get("rounds", 0))
                            except (TypeError, ValueError):
                                gain_rounds = 0
                            if gain_state_name == "亀裂" and gain_value > 0:
                                if not gain_target_obj:
                                    continue
                                if gain_rounds > 0:
                                    changes_to_apply.append((
                                        gain_target_obj,
                                        "APPLY_BUFF",
                                        f"亀裂_R{gain_rounds}",
                                        {
                                            "lasting": gain_rounds,
                                            "delay": 0,
                                            "count": gain_value,
                                            "data": {
                                                "buff_id": "Bu-Fissure",
                                                "original_rounds": gain_rounds,
                                                "fissure_count": gain_value,
                                            },
                                        },
                                    ))
                                    _stable_set_status_value(
                                        sim_gain_target,
                                        gain_state_name,
                                        _stable_get_status_value(sim_gain_target, gain_state_name) + gain_value,
                                    )
                                    gain_count += 1
                                else:
                                    changes_to_apply.append((gain_target_obj, "APPLY_STATE", gain_state_name, gain_value))
                                    gain_count += 1
                            else:
                                _stable_set_status_value(
                                    sim_gain_target,
                                    gain_state_name,
                                    _stable_get_status_value(sim_gain_target, gain_state_name) + gain_value,
                                )
                                changes_to_apply.append((gain_target_obj, "APPLY_STATE", gain_state_name, gain_value))
                                gain_count += 1
                        elif gain_type in {"BUFF", "APPLY_BUFF"}:
                            gain_buff_name = gain.get("buff_name")
                            gain_buff_id = gain.get("buff_id")
                            if not gain_buff_name and gain_buff_id:
                                from manager.buff_catalog import get_buff_by_id
                                gain_buff_data = get_buff_by_id(gain_buff_id)
                                if gain_buff_data:
                                    gain_buff_name = gain_buff_data.get("name")
                            if not gain_buff_name:
                                continue
                            try:
                                gain_lasting = int(gain.get("lasting", 1))
                            except (TypeError, ValueError):
                                gain_lasting = 1
                            try:
                                gain_delay = int(gain.get("delay", 0))
                            except (TypeError, ValueError):
                                gain_delay = 0
                            gain_data = gain.get("data")
                            if gain_data is None:
                                gain_data = {}
                            elif isinstance(gain_data, dict):
                                gain_data = dict(gain_data)
                            else:
                                continue
                            if gain_buff_id:
                                gain_data["buff_id"] = gain_buff_id
                            gain_payload = {
                                "lasting": gain_lasting,
                                "delay": gain_delay,
                                "data": gain_data,
                                "explicit_lasting": ("lasting" in gain),
                            }
                            if "lasting" in gain and isinstance(gain_payload.get("data"), dict):
                                gain_payload["data"]["_explicit_lasting"] = True
                            if "count" in gain:
                                try:
                                    gain_payload["count"] = int(gain.get("count"))
                                except (TypeError, ValueError):
                                    pass
                            changes_to_apply.append((gain_target_obj, "APPLY_BUFF", gain_buff_name, gain_payload))
                            gain_count += 1

                log_snippets.append(f"[{buff_name} 消費]")
                if consumed_by_state:
                    log_snippets.append(f"[{buff_name} 状態値 -{consume_required} ({current_count}->{remaining})]")
                else:
                    log_snippets.append(f"[{buff_name} {consume_required}消費 ({current_count}->{remaining})]")
                if gain_count > 0:
                    log_snippets.append(f"[効果発動 {gain_count}件]")
            elif effect_type == "CONSUME_BUFF_COUNT_FOR_POWER":
                buff_name = effect.get("buff_name")
                if not buff_name:
                    continue

                try:
                    consume_max = int(effect.get("consume_max", 0))
                except (TypeError, ValueError):
                    consume_max = 0
                if consume_max <= 0:
                    continue

                try:
                    value_per_stack = int(effect.get("value_per_stack", 1))
                except (TypeError, ValueError):
                    value_per_stack = 1
                if value_per_stack == 0:
                    continue

                try:
                    min_consume = int(effect.get("min_consume", 1))
                except (TypeError, ValueError):
                    min_consume = 1
                if min_consume < 1:
                    min_consume = 1

                apply_to = str(effect.get("apply_to", "final") or "final").strip().lower()
                if apply_to not in {"base", "final"}:
                    apply_to = "final"

                sim_bucket = _find_sim_buff(sim_target, buff_name)
                current_count = _resolve_buff_count_local(sim_bucket, default=0)
                consumed_by_state = False
                if current_count <= 0:
                    state_current = _stable_get_status_value(sim_target, buff_name)
                    try:
                        state_current = int(state_current or 0)
                    except Exception:
                        state_current = 0
                    if state_current > 0:
                        current_count = state_current
                        consumed_by_state = True
                consume_amount = min(current_count, consume_max)
                if consume_amount < min_consume:
                    log_snippets.append(f"[{buff_name}不足 {current_count}/{min_consume}]")
                    continue

                remaining = current_count - consume_amount
                if consumed_by_state:
                    _stable_set_status_value(sim_target, buff_name, remaining)
                    changes_to_apply.append((target_obj, "APPLY_STATE", buff_name, -consume_amount))
                else:
                    _set_sim_buff_count(sim_target, buff_name, remaining)
                    _queue_remaining_buff(target_obj, sim_bucket, buff_name, remaining)

                power_delta = consume_amount * value_per_stack
                if power_delta != 0:
                    change_type = "MODIFY_BASE_POWER" if apply_to == "base" else "MODIFY_FINAL_POWER"
                    changes_to_apply.append((target_obj, change_type, None, power_delta))
                    bonus_label = "基礎威力" if apply_to == "base" else "最終威力"
                    log_snippets.append(f"[{buff_name} 消費]")
                    log_snippets.append(f"[{buff_name} {consume_amount}消費 ({current_count}->{remaining})]")
                    log_snippets.append(f"[{bonus_label}{power_delta:+}]")
                else:
                    log_snippets.append(f"[{buff_name} 消費]")
                    log_snippets.append(f"[{buff_name} {consume_amount}消費 ({current_count}->{remaining})]")
            elif effect_type == "GRANT_SKILL":
                grant_skill_id = str(effect.get("skill_id", effect.get("grant_skill_id", "")) or "").strip()
                if not grant_skill_id:
                    continue
                grant_payload = {
                    "skill_id": grant_skill_id,
                    "grant_mode": effect.get("grant_mode", "permanent"),
                    "duration": effect.get("duration", effect.get("rounds")),
                    "uses": effect.get("uses", effect.get("count")),
                    "custom_name": effect.get("custom_name"),
                    "overwrite": effect.get("overwrite", True),
                    "source_skill_id": effect.get("source_skill_id"),
                }
                changes_to_apply.append((target_obj, "GRANT_SKILL", grant_skill_id, grant_payload))
                log_snippets.append(f"[スキル付与 {grant_skill_id}]")
            elif effect_type == "REMOVE_BUFF":
                buff_name = effect.get("buff_name")
                if buff_name:
                    changes_to_apply.append((target_obj, "REMOVE_BUFF", buff_name, 0))
                    before_count, _after_count = _simulate_remove_buff_stack(sim_target, buff_name)
                    log_snippets.append(f"[{buff_name} 解除]")
                    if before_count > 0:
                        log_snippets.append(f"[{buff_name} スタック -{before_count} ({before_count}->0)]")
            elif effect_type == "DAMAGE_BONUS":
                damage = int(effect.get("value", 0))
                if damage > 0:
                    total_bonus_damage += damage
                    log_snippets.append(f"[追加ダメージ +{damage}]")
            elif effect_type == "MODIFY_ROLL":
                mod_value = int(effect.get("value", 0))
                if mod_value != 0:
                    total_bonus_damage += mod_value
                    log_snippets.append(f"[ロール補正 {mod_value:+}]")
            elif effect_type == "USE_SKILL_AGAIN":
                # Resolve-layer feature: request reusing the same skill against the same slot target.
                max_reuses = effect.get("max_reuses", effect.get("max_reuse_count", effect.get("value", 1)))
                try:
                    max_reuses = int(max_reuses)
                except (TypeError, ValueError):
                    max_reuses = 1
                max_reuses = max(1, max_reuses)

                consume_cost = bool(effect.get("consume_cost", False))
                raw_reuse_cost = effect.get("reuse_cost", effect.get("reuse_costs", []))
                if isinstance(raw_reuse_cost, dict):
                    raw_reuse_cost = [raw_reuse_cost]
                reuse_cost = []
                if isinstance(raw_reuse_cost, list):
                    for entry in raw_reuse_cost:
                        if not isinstance(entry, dict):
                            continue
                        c_type = str(entry.get("type", "")).strip()
                        if not c_type:
                            continue
                        try:
                            c_val = int(entry.get("value", 0))
                        except (TypeError, ValueError):
                            c_val = 0
                        if c_val <= 0:
                            continue
                        reuse_cost.append({"type": c_type, "value": c_val})
                request_payload = {
                    "max_reuses": max_reuses,
                    "consume_cost": consume_cost,
                }
                if reuse_cost:
                    request_payload["reuse_cost"] = reuse_cost
                raw_stack_reuse_cost = effect.get("stack_reuse_cost", effect.get("stack_reuse_costs", []))
                if isinstance(raw_stack_reuse_cost, dict):
                    raw_stack_reuse_cost = [raw_stack_reuse_cost]
                stack_reuse_cost = []
                if isinstance(raw_stack_reuse_cost, list):
                    for entry in raw_stack_reuse_cost:
                        if not isinstance(entry, dict):
                            continue
                        buff_name = str(entry.get("buff_name", entry.get("resource", entry.get("name", ""))) or "").strip()
                        if not buff_name:
                            continue
                        try:
                            c_val = int(entry.get("value", entry.get("count", entry.get("consume_required", 0))))
                        except (TypeError, ValueError):
                            c_val = 0
                        if c_val <= 0:
                            continue
                        stack_reuse_cost.append({"buff_name": buff_name, "value": c_val})
                if stack_reuse_cost:
                    request_payload["stack_reuse_cost"] = stack_reuse_cost
                changes_to_apply.append((target_obj, "USE_SKILL_AGAIN", "None", request_payload))
                log_snippets.append(f"[スキル再使用 x{max_reuses}]")
            elif effect_type == "CUSTOM_EFFECT":
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
            elif effect_type == "FORCE_UNOPPOSED":
                changes_to_apply.append((target_obj, "FORCE_UNOPPOSED", "None", 0))
            elif effect_type == "MODIFY_BASE_POWER":
                mod_value = int(effect.get("value", 0))
                if mod_value != 0:
                    changes_to_apply.append((target_obj, "MODIFY_BASE_POWER", None, mod_value))
                    log_snippets.append(f"[基礎威力 {mod_value:+}]")
            elif effect_type == "MODIFY_FINAL_POWER":
                mod_value = int(effect.get("value", 0))
                if mod_value != 0:
                    changes_to_apply.append((target_obj, "MODIFY_FINAL_POWER", None, mod_value))
                    log_snippets.append(f"[最終威力 {mod_value:+}]")
            elif effect_type == "DRAIN_HP":
                 if base_damage > 0:
                     rate = float(effect.get("value", 0))

                     calc_base = base_damage
                     if target:
                         target_current_hp = _stable_get_status_value(target, 'HP')
                         if target_current_hp < calc_base:
                             calc_base = target_current_hp

                     heal_val = int(calc_base * rate)
                     if heal_val > 0:
                         current_hp = _stable_get_status_value(sim_actor, 'HP')
                         _stable_set_status_value(sim_actor, 'HP', current_hp + heal_val)

                         changes_to_apply.append((actor, "APPLY_STATE", "HP", heal_val))
                         log_snippets.append(f"[吸収 +{heal_val}]")
            elif effect_type == "SUMMON_CHARACTER":
                summon_template_id = (
                    effect.get("summon_template_id")
                    or effect.get("template_id")
                    or effect.get("summon_id")
                )
                if not summon_template_id:
                    continue
                summon_payload = {
                    "summon_template_id": summon_template_id,
                }
                duration_mode_raw = effect.get("summon_duration_mode", effect.get("duration_mode"))
                if duration_mode_raw not in (None, ""):
                    summon_payload["summon_duration_mode"] = duration_mode_raw
                duration_raw = effect.get("summon_duration", effect.get("duration"))
                if duration_raw not in (None, ""):
                    summon_payload["summon_duration"] = duration_raw
                summon_team_raw = effect.get("summon_type", effect.get("summon_team"))
                if summon_team_raw not in (None, ""):
                    summon_payload["type"] = summon_team_raw
                for key in [
                    "name",
                    "base_name",
                    "x",
                    "y",
                    "offset_x",
                    "offset_y",
                    "commands",
                    "initial_skill_ids",
                    "custom_skill_names",
                    "SPassive",
                    "special_buffs",
                    "radiance_skills",
                    "params",
                    "states",
                    "hp",
                    "maxHp",
                    "mp",
                    "maxMp",
                ]:
                    if key in effect:
                        summon_payload[key] = copy.deepcopy(effect.get(key))

                if (
                    isinstance(target_obj, dict)
                    and target_obj.get("id") != actor.get("id")
                    and "x" not in summon_payload
                    and "y" not in summon_payload
                ):
                    summon_payload["x"] = target_obj.get("x")
                    summon_payload["y"] = target_obj.get("y")

                changes_to_apply.append((actor, "SUMMON_CHARACTER", str(summon_template_id), summon_payload))
                log_snippets.append(f"[召喚 {summon_template_id}]")


    return total_bonus_damage, log_snippets, changes_to_apply

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

