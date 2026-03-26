from extensions import all_skill_data as _default_all_skill_data
from manager.battle.duel_log_utils import (
    _extract_damage_parts_from_legacy_lines,
    _is_dice_damage_source,
)
from manager.battle.runtime_actions import (
    format_skill_name_for_log,
    format_skill_display_from_command,
)

all_skill_data = _default_all_skill_data
SOURCE_DICE_DAMAGE = "ダイスダメージ"
SOURCE_EFFECT_DAMAGE = "効果ダメージ"
SOURCE_GENERIC_DAMAGE = "ダメージ"

_LEGACY_DICE_ALIASES = {
    "繝繧､繧ｹ",
    "繝繧､繧ｹ繝繝｡繝ｼ繧ｸ",
    "繝繝｡繝ｼ繧ｸ",
}
_LEGACY_EFFECT_ALIASES = {
    "繧ｭ繝ｼ繝ｯ繝ｼ繝牙柑譫懊ム繝｡繝ｼ繧ｸ",
}


def _humanize_resolve_reason(notes):
    return str(notes or "").strip()


def _normalize_damage_source_label(source_name):
    src = str(source_name or "").strip()
    if not src:
        return SOURCE_GENERIC_DAMAGE
    s = src.lower()

    if src in _LEGACY_DICE_ALIASES:
        return SOURCE_DICE_DAMAGE
    if src in _LEGACY_EFFECT_ALIASES:
        return SOURCE_EFFECT_DAMAGE
    if s in {"dice", "base_damage", "power_roll", "mass_summation_delta"}:
        return SOURCE_DICE_DAMAGE
    if s in {"on_hit", "on_damage", "custom_damage", "keyword_damage", "one_sided_delegate"}:
        return SOURCE_EFFECT_DAMAGE
    if src == "一方攻撃":
        return SOURCE_EFFECT_DAMAGE
    return src


def _extract_power_with_snapshot_fallback(rolls, primary_key, fallback_keys):
    if not isinstance(rolls, dict):
        return None

    value = rolls.get(primary_key)
    if value is not None:
        return value

    for key in fallback_keys:
        value = rolls.get(key)
        if value is not None:
            return value

    return None


def to_legacy_duel_log_input(
    outcome_payload,
    state,
    intents,
    attacker_slot,
    defender_slot,
    applied=None,
    kind="one_sided",
    outcome="no_effect",
    notes=None,
):
    outcome_payload = outcome_payload if isinstance(outcome_payload, dict) else {}
    applied = applied if isinstance(applied, dict) else {}
    intents = intents if isinstance(intents, dict) else {}

    battle_state = state.get("battle_state", {}) if isinstance(state, dict) else {}
    slots = battle_state.get("slots", {}) if isinstance(battle_state, dict) else {}
    chars = state.get("characters", []) if isinstance(state, dict) else []
    chars_by_id = {
        c.get("id"): c
        for c in chars
        if isinstance(c, dict) and c.get("id")
    }

    attacker_actor_id = slots.get(attacker_slot, {}).get("actor_id")
    defender_actor_id = slots.get(defender_slot, {}).get("actor_id") if defender_slot else outcome_payload.get("target_id")

    attacker_char = chars_by_id.get(attacker_actor_id, {})
    defender_char = chars_by_id.get(defender_actor_id, {})

    attacker_name = attacker_char.get("name") or f"slot:{attacker_slot}"
    defender_name = defender_char.get("name") or (f"slot:{defender_slot}" if defender_slot else "対象なし")

    attacker_intent = intents.get(attacker_slot, {})
    defender_intent = intents.get(defender_slot, {}) if defender_slot else {}
    attacker_skill_id = outcome_payload.get("skill_id") or attacker_intent.get("skill_id")
    defender_skill_id = defender_intent.get("skill_id")
    attacker_skill_data = all_skill_data.get(attacker_skill_id, {}) if attacker_skill_id else {}
    defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id else {}

    delegate_summary = outcome_payload.get("delegate_summary", {})
    delegate_legacy_lines = (
        delegate_summary.get("legacy_log_lines", [])
        if isinstance(delegate_summary, dict)
        else []
    )
    rolls = delegate_summary.get("rolls", {}) if isinstance(delegate_summary, dict) else {}
    command_a = rolls.get("command") or "0"
    command_b = rolls.get("command_b") or "0"

    skill_display_a = format_skill_display_from_command(command_a, attacker_skill_id, attacker_skill_data, attacker_char)
    if not skill_display_a:
        skill_display_a = f"[{format_skill_name_for_log(attacker_skill_id, attacker_skill_data, attacker_char)}]"

    if defender_skill_id:
        skill_display_d = format_skill_display_from_command(command_b, defender_skill_id, defender_skill_data, defender_char)
        if not skill_display_d:
            skill_display_d = f"[{format_skill_name_for_log(defender_skill_id, defender_skill_data, defender_char)}]"
    else:
        skill_display_d = "-"

    power_a = _extract_power_with_snapshot_fallback(
        rolls,
        "power_a",
        ["total_damage", "final_damage", "base_damage"],
    )
    if power_a is None:
        snap_a = rolls.get("power_snapshot_a") if isinstance(rolls.get("power_snapshot_a"), dict) else rolls.get("power_snapshot")
        if isinstance(snap_a, dict):
            power_a = snap_a.get("final_power")

    power_b = _extract_power_with_snapshot_fallback(rolls, "power_b", [])
    if power_b is None:
        snap_b = rolls.get("power_snapshot_b")
        if isinstance(snap_b, dict):
            power_b = snap_b.get("final_power")
    if power_b is None:
        power_b = 0

    # One-sided / fizzle does not have an opposed defender power.
    if kind in ["one_sided", "fizzle"]:
        skill_display_d = "-"
        power_b = "-"
        if rolls.get("base_damage") is not None:
            power_a = rolls.get("base_damage")

    if kind == "fizzle":
        winner_message = "<strong>不発</strong>"
    elif kind == "one_sided":
        winner_message = (
            f"<strong>{attacker_name} の一方攻撃</strong>"
            if outcome == "attacker_win"
            else "<strong>一方攻撃（不成立）</strong>"
        )
    else:
        if outcome == "attacker_win":
            winner_message = f"<strong>{attacker_name} の勝利</strong>"
        elif outcome == "defender_win":
            winner_message = f"<strong>{defender_name} の勝利</strong>"
        elif outcome == "draw":
            winner_message = "<strong>引き分け</strong> (ダメージなし)"
        else:
            winner_message = "<strong>効果なし</strong>"

    damage_report = {"A": [], "D": []}
    source_alias = {
        "one_sided_delegate": "一方攻撃",
    }
    per_side_total = {"A": 0, "D": 0}
    for dmg in applied.get("damage", []) or []:
        if not isinstance(dmg, dict):
            continue
        target_id = dmg.get("target_id")
        try:
            amount = int(dmg.get("hp", dmg.get("amount", 0)))
        except (TypeError, ValueError):
            amount = 0
        if amount <= 0:
            continue
        if target_id == attacker_actor_id:
            per_side_total["A"] += amount
        elif target_id == defender_actor_id:
            per_side_total["D"] += amount

    delegate_legacy_parts = _extract_damage_parts_from_legacy_lines(
        delegate_legacy_lines,
        attacker_name,
        defender_name,
    )

    def _append_split(side_key, total_value, dice_value):
        total_value = int(total_value or 0)
        if total_value <= 0:
            return
        dice_part = min(max(int(dice_value or 0), 0), total_value)
        effect_part = max(0, total_value - dice_part)
        if dice_part > 0:
            damage_report[side_key].append({"source": SOURCE_DICE_DAMAGE, "value": dice_part})
        if effect_part > 0:
            damage_report[side_key].append({"source": SOURCE_EFFECT_DAMAGE, "value": effect_part})
        if dice_part <= 0 and effect_part <= 0:
            damage_report[side_key].append({"source": SOURCE_GENERIC_DAMAGE, "value": total_value})

    def _append_legacy_parts_with_cap(side_key, total_value):
        total_value = int(total_value or 0)
        if total_value <= 0:
            return {"used_total": 0, "used_dice": 0}
        remaining = total_value
        used_total = 0
        used_dice = 0
        for item in delegate_legacy_parts.get(side_key, []) or []:
            if not isinstance(item, dict):
                continue
            source = _normalize_damage_source_label(item.get("source"))
            if not source:
                continue
            try:
                value = int(item.get("value", 0))
            except (TypeError, ValueError):
                value = 0
            if value <= 0 or remaining <= 0:
                continue
            take = min(value, remaining)
            damage_report[side_key].append({"source": source, "value": take})
            used_total += take
            if _is_dice_damage_source(source):
                used_dice += take
            remaining -= take
            if remaining <= 0:
                break
        return {"used_total": used_total, "used_dice": used_dice}

    if kind in ["one_sided", "fizzle"]:
        try:
            base_roll_damage = int(rolls.get("base_damage", 0) or 0)
        except (TypeError, ValueError):
            base_roll_damage = 0
        _append_split("D", per_side_total.get("D", 0), base_roll_damage)
        if int(per_side_total.get("A", 0) or 0) > 0:
            damage_report["A"].append({"source": SOURCE_EFFECT_DAMAGE, "value": int(per_side_total.get("A", 0) or 0)})
    elif kind == "clash":
        try:
            clash_power_a = int(rolls.get("power_a", 0) or 0)
        except (TypeError, ValueError):
            clash_power_a = 0
        try:
            clash_power_b = int(rolls.get("power_b", 0) or 0)
        except (TypeError, ValueError):
            clash_power_b = 0
        if outcome == "attacker_win":
            d_total = int(per_side_total.get("D", 0) or 0)
            d_used = _append_legacy_parts_with_cap("D", d_total)
            d_remain = max(0, d_total - int(d_used.get("used_total", 0)))
            d_dice_remain = max(0, int(clash_power_a or 0) - int(d_used.get("used_dice", 0)))
            _append_split("D", d_remain, d_dice_remain)
            if int(per_side_total.get("A", 0) or 0) > 0:
                a_total = int(per_side_total.get("A", 0) or 0)
                a_used = _append_legacy_parts_with_cap("A", a_total)
                a_remain = max(0, a_total - int(a_used.get("used_total", 0)))
                if a_remain > 0:
                    damage_report["A"].append({"source": SOURCE_EFFECT_DAMAGE, "value": a_remain})
        elif outcome == "defender_win":
            a_total = int(per_side_total.get("A", 0) or 0)
            a_used = _append_legacy_parts_with_cap("A", a_total)
            a_remain = max(0, a_total - int(a_used.get("used_total", 0)))
            a_dice_remain = max(0, int(clash_power_b or 0) - int(a_used.get("used_dice", 0)))
            _append_split("A", a_remain, a_dice_remain)
            if int(per_side_total.get("D", 0) or 0) > 0:
                d_total = int(per_side_total.get("D", 0) or 0)
                d_used = _append_legacy_parts_with_cap("D", d_total)
                d_remain = max(0, d_total - int(d_used.get("used_total", 0)))
                if d_remain > 0:
                    damage_report["D"].append({"source": SOURCE_EFFECT_DAMAGE, "value": d_remain})
        else:
            if int(per_side_total.get("A", 0) or 0) > 0:
                a_total = int(per_side_total.get("A", 0) or 0)
                a_used = _append_legacy_parts_with_cap("A", a_total)
                a_remain = max(0, a_total - int(a_used.get("used_total", 0)))
                if a_remain > 0:
                    damage_report["A"].append({"source": SOURCE_EFFECT_DAMAGE, "value": a_remain})
            if int(per_side_total.get("D", 0) or 0) > 0:
                d_total = int(per_side_total.get("D", 0) or 0)
                d_used = _append_legacy_parts_with_cap("D", d_total)
                d_remain = max(0, d_total - int(d_used.get("used_total", 0)))
                if d_remain > 0:
                    damage_report["D"].append({"source": SOURCE_EFFECT_DAMAGE, "value": d_remain})
    else:
        for dmg in applied.get("damage", []) or []:
            if not isinstance(dmg, dict):
                continue
            target_id = dmg.get("target_id")
            try:
                amount = int(dmg.get("hp", dmg.get("amount", 0)))
            except (TypeError, ValueError):
                amount = 0
            if amount <= 0:
                continue
            source_raw = str(dmg.get("source") or SOURCE_DICE_DAMAGE)
            source = _normalize_damage_source_label(source_alias.get(source_raw, source_raw))
            if target_id == attacker_actor_id:
                damage_report["A"].append({"source": source, "value": amount})
            elif target_id == defender_actor_id:
                damage_report["D"].append({"source": source, "value": amount})

    extra_lines = []
    tie_break = rolls.get("tie_break")
    if tie_break:
        extra_lines.append(f"tie_break: {tie_break}")
    if notes:
        reason_text = _humanize_resolve_reason(notes)
        extra_lines.append(f"reason: {reason_text or notes}")

    for dmg in applied.get("damage", []) or []:
        if not isinstance(dmg, dict):
            continue
        t_id = dmg.get("target_id")
        if not t_id:
            continue
        try:
            amount = int(dmg.get("hp", dmg.get("amount", 0)))
        except (TypeError, ValueError):
            amount = 0
        if amount <= 0:
            continue
        t_name = chars_by_id.get(t_id, {}).get("name", str(t_id))
        after_hp = int(chars_by_id.get(t_id, {}).get("hp", 0) or 0)
        before_hp = after_hp + amount
        extra_lines.append(f"[結果] {t_name} HP: {before_hp} -> {after_hp}")

    for st in applied.get("statuses", []) or []:
        if not isinstance(st, dict):
            continue
        t_id = st.get("target_id")
        t_name = chars_by_id.get(t_id, {}).get("name", str(t_id))
        name = st.get("name") or st.get("type") or "status"
        before = st.get("before")
        after = st.get("after")
        if before is not None and after is not None:
            extra_lines.append(f"[結果] {t_name} {name}: {before} -> {after}")
        else:
            extra_lines.append(f"[結果] {t_name} {name}")

    cost = applied.get("cost", {})
    if isinstance(cost, dict):
        hp = int(cost.get("hp", 0))
        mp = int(cost.get("mp", 0))
        fp = int(cost.get("fp", 0))
        if hp or mp or fp:
            extra_lines.append(f"[コスト] HP:{hp} MP:{mp} FP:{fp}")

    match_log_line = str(delegate_summary.get("match_log") or "").strip() if isinstance(delegate_summary, dict) else ""
    for line in (delegate_legacy_lines if isinstance(delegate_legacy_lines, list) else []):
        if line is None:
            continue
        line_str = str(line).strip()
        if not line_str:
            continue
        if match_log_line and line_str == match_log_line:
            continue
        # Rebuild damage detail lines from structured damage_report only.
        if ("内訳:" in line_str) or ("蜀・ｨｳ:" in line_str):
            continue
        if ("ダメージ" in line_str) and ("<strong>" in line_str):
            continue
        # Keep buff/debuff apply/remove announcement lines.
        if ("付与されました" in line_str) or ("解除されました" in line_str) or ("適用" in line_str) or ("解除" in line_str):
            extra_lines.append(line_str)

    for line in (delegate_summary.get("logs", []) if isinstance(delegate_summary, dict) else []):
        if line:
            extra_lines.append(str(line))

    return {
        "actor_name_a": attacker_name,
        "skill_display_a": skill_display_a,
        "total_a": power_a,
        "actor_name_d": defender_name,
        "skill_display_d": skill_display_d,
        "total_d": power_b,
        "winner_message": winner_message,
        "damage_report": damage_report,
        "extra_lines": extra_lines,
    }
