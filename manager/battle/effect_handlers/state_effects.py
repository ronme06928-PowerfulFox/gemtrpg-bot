# manager/battle/effect_handlers/state_effects.py
# 状態異常系 effect ハンドラ（計画書29 Phase 3 で game_logic.process_skill_effects から移設）。
# ロジック・ログ文字列・changes_to_apply の形式は移設前と同一。
# game_logic のラッパ関数（calculate_state_apply_bonus 等）は循環import回避のため関数内で遅延importする。
from manager.battle import skill_effect_helpers as helpers


def handle_apply_fissure_buffed(effect, target_obj, sim_target, session):
    from manager.game_logic import calculate_state_apply_bonus, remove_buff

    actor = session.actor
    sim_actor = session.get_simulated_char(actor)
    changes_to_apply = session.changes_to_apply
    log_snippets = session.log_snippets

    rounds = helpers.parse_positive_rounds(effect.get("rounds"))
    value = int(effect.get("value", 0))
    if rounds <= 0 or value <= 0:
        return

    if not sim_target:
        return

    bonus, buffs_to_remove = calculate_state_apply_bonus(sim_actor, sim_target, "亀裂", context=session.context)
    final_value = value + max(0, int(bonus or 0))
    if final_value <= 0:
        return

    for b_name in buffs_to_remove:
        remove_buff(sim_actor, b_name)
        changes_to_apply.append((actor, "REMOVE_BUFF", b_name, 0))
        log_snippets.append(f"[{b_name} 消費]")

    session.queue_fissure_round_buff(
        target_obj=target_obj,
        sim_target=sim_target,
        amount=final_value,
        rounds=rounds,
        source=effect.get("source", "skill"),
    )
    log_snippets.append(f"[亀裂 {final_value} ({rounds}R)]")


def handle_apply_state(effect, target_obj, sim_target, session):
    from manager.game_logic import (
        calculate_state_apply_bonus,
        calculate_state_receive_bonus,
        remove_buff,
    )

    actor = session.actor
    context = session.context
    sim_actor = session.get_simulated_char(actor)
    changes_to_apply = session.changes_to_apply
    log_snippets = session.log_snippets

    stat_name = effect.get("state_name") or effect.get("name")
    value = int(effect.get("value", 0))
    fissure_rounds = helpers.parse_positive_rounds(effect.get("rounds"))

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
            session.queue_fissure_round_buff(
                target_obj=target_obj,
                sim_target=sim_target,
                amount=value,
                rounds=fissure_rounds,
                source=effect.get("source", "skill"),
            )
            log_snippets.append(f"[亀裂 {value} ({fissure_rounds}R)]")
            return

        current_val = session.get_status_value(sim_target, stat_name)
        session.set_status_value(sim_target, stat_name, current_val + value)

        changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, value))


def handle_apply_state_per_n(effect, target_obj, sim_target, session):
    from manager.game_logic import (
        _get_value_for_condition,
        calculate_state_apply_bonus,
        calculate_state_receive_bonus,
        remove_buff,
    )

    actor = session.actor
    context = session.context
    sim_actor = session.get_simulated_char(actor)
    original_sim_target = session.original_sim_target
    changes_to_apply = session.changes_to_apply
    log_snippets = session.log_snippets

    source_type = effect.get("source", "self")
    if source_type == "self":
        source_obj = sim_actor
    else:
        # source=target should still point to the original action target
        # when this effect itself is applied to self.
        source_obj = original_sim_target if effect.get("target") == "self" and original_sim_target else sim_target
    source_param = effect.get("source_param")
    fissure_rounds = helpers.parse_positive_rounds(effect.get("rounds"))

    if not source_obj or not source_param:
        return

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
            session.queue_fissure_round_buff(
                target_obj=target_obj,
                sim_target=sim_target,
                amount=calculated_value,
                rounds=fissure_rounds,
                source=effect.get("source", "skill"),
            )
            log_snippets.append(f"[亀裂 {calculated_value} ({source_param}{source_param_value}/{fissure_rounds}R)]")
            return

        current_val = session.get_status_value(sim_target, stat_name)
        session.set_status_value(sim_target, stat_name, current_val + calculated_value)

        changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, calculated_value))
        log_snippets.append(f"[{stat_name} +{calculated_value} ({source_param}={source_param_value})]")


def handle_multiply_state(effect, target_obj, sim_target, session):
    stat_name = effect.get("state_name")
    multiplier = float(effect.get("value", 1.0))

    if stat_name and sim_target:
        current_val = session.get_status_value(sim_target, stat_name)
        new_val = int(current_val * multiplier + 0.5)
        diff = new_val - current_val

        if diff != 0:
            session.set_status_value(sim_target, stat_name, new_val)

            session.changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, diff))
            session.log_snippets.append(f"[{stat_name} x{multiplier} ({current_val}->{new_val})]")


HANDLERS = {
    "APPLY_FISSURE_BUFFED": handle_apply_fissure_buffed,
    "APPLY_STATE": handle_apply_state,
    "APPLY_STATE_PER_N": handle_apply_state_per_n,
    "MULTIPLY_STATE": handle_multiply_state,
}
