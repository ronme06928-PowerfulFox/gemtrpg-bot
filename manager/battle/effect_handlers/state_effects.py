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


SCHEMAS = {
    "APPLY_FISSURE_BUFFED": {
        "label": "期限付き亀裂を付与",
        "description": "付与者の補正を加えた亀裂をラウンド制バフで付与する。受け手側補正は加えない。",
        "internal": True,
        "fields": {
            "value": {"type": "int", "required": True, "label": "亀裂量", "description": "正の整数。"},
            "rounds": {"type": "int", "required": True, "label": "継続ラウンド", "description": "正の整数。"},
            "source": {"type": "string", "required": False, "label": "付与元", "description": "省略時skill。"},
        },
        "summary": "{target}に亀裂を{value}付与（{rounds}ラウンド）",
        "example": {
            "timing": "HIT",
            "type": "APPLY_FISSURE_BUFFED",
            "target": "target",
            "value": 3,
            "rounds": 2,
        },
    },
    "APPLY_STATE": {
        "label": "状態を付与",
        "description": "状態値を加減する。正の付与量には付与者・受け手の補正が入る。",
        "internal": False,
        "fields": {
            "state_name": {"type": "state_ref", "required": True, "label": "状態", "description": "nameでも指定可能。HP・MP・FPも使用可能。"},
            "value": {"type": "int", "required": True, "label": "量", "description": "負数は減少。省略時0で不発。"},
            "rounds": {"type": "int", "required": False, "label": "亀裂の継続ラウンド", "visible_when": {"state_name": "亀裂"}, "description": "亀裂の正の付与時だけ使用。正数なら期限付き。"},
            "source": {"type": "string", "required": False, "label": "付与元", "visible_when": {"state_name": "亀裂"}, "description": "期限付き亀裂の付与元。省略時skill。"},
        },
        "summary": "{target}に{state_name}を{value}付与",
        "example": {
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "出血",
            "value": 3,
        },
    },
    "APPLY_STATE_PER_N": {
        "label": "参照値ごとに状態を付与",
        "description": "参照値をper_Nで整数除算しvalueを掛け、正の量だけ状態を付与する。上限処理後に付与補正が入る。",
        "internal": False,
        "fields": {
            "source": {"type": "string", "required": False, "label": "参照元", "description": "省略時self。self以外は対象を参照。"},
            "source_param": {"type": "string", "required": True, "label": "参照項目"},
            "per_N": {"type": "int", "required": False, "label": "区切り", "description": "省略時1。0以下なら不発。"},
            "value": {"type": "int", "required": False, "label": "区切りごとの量", "description": "省略時1。"},
            "max_value": {"type": "int", "required": False, "label": "補正前の付与上限"},
            "state_name": {"type": "state_ref", "required": True, "label": "付与する状態"},
            "rounds": {"type": "int", "required": False, "label": "亀裂の継続ラウンド", "description": "亀裂の正の付与でのみ使用。"},
        },
        "summary": "{target}に{source_param}の{per_N}ごとに{state_name}を{value}付与",
        "example": {
            "timing": "HIT",
            "type": "APPLY_STATE_PER_N",
            "target": "target",
            "source_param": "出血",
            "per_N": 3,
            "state_name": "破裂",
            "value": 1,
        },
    },
    "MULTIPLY_STATE": {
        "label": "状態を乗算",
        "description": "現在値×倍率に0.5を加えて整数化し、差分を適用する。",
        "internal": False,
        "fields": {
            "state_name": {"type": "state_ref", "required": True, "label": "状態"},
            "value": {"type": "number", "required": False, "label": "倍率", "description": "省略時1.0。"},
        },
        "summary": "{target}の{state_name}を{value}倍",
        "example": {
            "timing": "HIT",
            "type": "MULTIPLY_STATE",
            "target": "target",
            "state_name": "出血",
            "value": 2,
        },
    },
}
