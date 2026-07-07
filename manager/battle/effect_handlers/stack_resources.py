# manager/battle/effect_handlers/stack_resources.py
# スタック資源系 effect ハンドラ（計画書29 Phase 2 で game_logic.process_skill_effects から移設）。
# ロジック・ログ文字列・changes_to_apply の形式は移設前と同一。
import sys

from manager.battle import skill_effect_helpers as helpers


def _utils_module():
    return sys.modules.get('manager.utils')


def handle_convert_stack_resource_variant(effect, target_obj, sim_target, session):
    resource_name = (
        effect.get("resource_name")
        or effect.get("resource")
        or effect.get("buff_name")
        or ""
    )
    to_variant = str(effect.get("to_variant") or effect.get("variant") or "").strip()
    if not resource_name or not to_variant:
        return

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
        sim_bucket = helpers.find_sim_buff_by_id(sim_target, preferred_buff_id)
    if not isinstance(sim_bucket, dict):
        sim_bucket = helpers.find_sim_buff(sim_target, canonical_resource_name)
    if not isinstance(sim_bucket, dict) and callable(resolve_name_fn):
        try:
            resolved = str(resolve_name_fn(resource_name) or "").strip()
        except Exception:
            resolved = ""
        if resolved:
            sim_bucket = helpers.find_sim_buff(sim_target, resolved)
    if not isinstance(sim_bucket, dict):
        # Last-resort fallback by known stack-resource buff IDs.
        if preferred_buff_id:
            sim_bucket = helpers.find_sim_buff_by_id(sim_target, preferred_buff_id)
        if not isinstance(sim_bucket, dict):
            fallback_rows = [
                helpers.find_sim_buff_by_id(sim_target, "Bu-31"),
                helpers.find_sim_buff_by_id(sim_target, "Bu-30"),
            ]
            if preferred_buff_id == "Bu-30":
                fallback_rows.reverse()
            for row in fallback_rows:
                if isinstance(row, dict) and helpers.resolve_buff_count(row, default=0) > 0:
                    sim_bucket = row
                    break

    current_count = helpers.resolve_buff_count(sim_bucket, default=0)
    if current_count < require_count:
        session.log_snippets.append(f"[{canonical_resource_name} 不足 {current_count}/{require_count}]")
        return
    if not isinstance(sim_bucket, dict):
        return
    canonical_resource_name = str(sim_bucket.get("name") or canonical_resource_name).strip()

    if not isinstance(sim_bucket.get("data"), dict):
        sim_bucket["data"] = {}
    sim_bucket["variant"] = to_variant
    sim_bucket["data"]["variant"] = to_variant

    # Avoid remove/re-apply on conversion to prevent accidental stack duplication.
    # Persist variant directly to the live target row as well.
    live_bucket = None
    if preferred_buff_id:
        live_bucket = helpers.find_sim_buff_by_id(target_obj, preferred_buff_id)
    if not isinstance(live_bucket, dict):
        live_bucket = helpers.find_sim_buff(target_obj, canonical_resource_name)
    if not isinstance(live_bucket, dict) and callable(resolve_name_fn):
        try:
            resolved_live = str(resolve_name_fn(resource_name) or "").strip()
        except Exception:
            resolved_live = ""
        if resolved_live:
            live_bucket = helpers.find_sim_buff(target_obj, resolved_live)
    if isinstance(live_bucket, dict):
        if not isinstance(live_bucket.get("data"), dict):
            live_bucket["data"] = {}
        live_bucket["variant"] = to_variant
        live_bucket["data"]["variant"] = to_variant

    session.log_snippets.append(f"[{canonical_resource_name} 変換: {to_variant}]")


def handle_consume_buff_count_for_gain(effect, target_obj, sim_target, session):
    actor = session.actor
    target = session.target
    changes_to_apply = session.changes_to_apply
    log_snippets = session.log_snippets

    buff_name = effect.get("buff_name")
    if not buff_name:
        return
    try:
        consume_required = int(effect.get("consume_required", 0))
    except (TypeError, ValueError):
        consume_required = 0
    if consume_required <= 0:
        return

    sim_bucket = helpers.find_sim_buff(sim_target, buff_name)
    current_count = helpers.resolve_buff_count(sim_bucket, default=0)
    consumed_by_state = False
    if current_count < consume_required:
        state_current = session.get_status_value(sim_target, buff_name)
        try:
            state_current = int(state_current or 0)
        except Exception:
            state_current = 0
        if state_current < consume_required:
            log_snippets.append(f"[{buff_name}不足 {current_count}/{consume_required}]")
            return
        remaining = state_current - consume_required
        session.set_status_value(sim_target, buff_name, remaining)
        changes_to_apply.append((target_obj, "APPLY_STATE", buff_name, -consume_required))
        current_count = state_current
        consumed_by_state = True
    else:
        remaining = current_count - consume_required
        helpers.set_sim_buff_count(sim_target, buff_name, remaining)
        session.queue_remaining_buff(target_obj, sim_bucket, buff_name, remaining)

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
            sim_gain_target = session.get_simulated_char(gain_target_obj) if gain_target_obj else None
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
                current_val = session.get_status_value(sim_gain_target, gain_type)
                session.set_status_value(sim_gain_target, gain_type, current_val + gain_value)
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
                        session.set_status_value(
                            sim_gain_target,
                            gain_state_name,
                            session.get_status_value(sim_gain_target, gain_state_name) + gain_value,
                        )
                        gain_count += 1
                    else:
                        changes_to_apply.append((gain_target_obj, "APPLY_STATE", gain_state_name, gain_value))
                        gain_count += 1
                else:
                    session.set_status_value(
                        sim_gain_target,
                        gain_state_name,
                        session.get_status_value(sim_gain_target, gain_state_name) + gain_value,
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


def handle_consume_buff_count_for_power(effect, target_obj, sim_target, session):
    changes_to_apply = session.changes_to_apply
    log_snippets = session.log_snippets

    buff_name = effect.get("buff_name")
    if not buff_name:
        return

    try:
        consume_max = int(effect.get("consume_max", 0))
    except (TypeError, ValueError):
        consume_max = 0
    if consume_max <= 0:
        return

    try:
        value_per_stack = int(effect.get("value_per_stack", 1))
    except (TypeError, ValueError):
        value_per_stack = 1
    if value_per_stack == 0:
        return

    try:
        min_consume = int(effect.get("min_consume", 1))
    except (TypeError, ValueError):
        min_consume = 1
    if min_consume < 1:
        min_consume = 1

    apply_to = str(effect.get("apply_to", "final") or "final").strip().lower()
    if apply_to not in {"base", "final"}:
        apply_to = "final"

    sim_bucket = helpers.find_sim_buff(sim_target, buff_name)
    current_count = helpers.resolve_buff_count(sim_bucket, default=0)
    consumed_by_state = False
    if current_count <= 0:
        state_current = session.get_status_value(sim_target, buff_name)
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
        return

    remaining = current_count - consume_amount
    if consumed_by_state:
        session.set_status_value(sim_target, buff_name, remaining)
        changes_to_apply.append((target_obj, "APPLY_STATE", buff_name, -consume_amount))
    else:
        helpers.set_sim_buff_count(sim_target, buff_name, remaining)
        session.queue_remaining_buff(target_obj, sim_bucket, buff_name, remaining)

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


HANDLERS = {
    "CONVERT_STACK_RESOURCE_VARIANT": handle_convert_stack_resource_variant,
    "CONSUME_BUFF_COUNT_FOR_GAIN": handle_consume_buff_count_for_gain,
    "CONSUME_BUFF_COUNT_FOR_POWER": handle_consume_buff_count_for_power,
}
