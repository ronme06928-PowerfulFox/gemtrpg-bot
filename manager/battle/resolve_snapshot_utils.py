import copy
import re

from manager.game_logic import build_power_result_snapshot
from manager.battle.skill_rules import _extract_rule_data_from_skill, _extract_skill_cost_entries


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _extract_power_pair_from_match_log(match_log):
    if not isinstance(match_log, str):
        return None, None
    totals = re.findall(r"dice-result-total[^>]*>(-?\d+)<", match_log)
    if len(totals) < 2:
        return None, None
    try:
        return int(totals[0]), int(totals[1])
    except (TypeError, ValueError):
        return None, None


def _estimate_roll_breakdown_from_command_and_total(command_text, total_value, fallback_constant=0):
    expression = str(command_text or "").strip()
    expression = re.sub(r"[【】\[\]]", "", expression).strip()
    compact = expression.replace(" ", "")

    constant_total = 0
    saw_dice_term = False
    for token in re.finditer(r"([+-])(\d+d\d+|\d+)", compact):
        sign = -1 if token.group(1) == "-" else 1
        raw = token.group(2)
        if "d" in raw.lower():
            saw_dice_term = True
            continue
        try:
            constant_total += sign * int(raw)
        except Exception:
            continue

    if (not saw_dice_term) and constant_total == 0:
        constant_total = _safe_int(fallback_constant, 0)

    final_total = _safe_int(total_value, 0)
    dice_total = final_total - constant_total
    if dice_total < 0:
        dice_total = 0
        constant_total = final_total

    return {
        "expression": compact,
        "dice_total": int(dice_total),
        "constant_total": int(constant_total),
        "final_total": int(final_total),
    }


def _build_clash_power_snapshot(preview, command_text, total_value, roll_result=None):
    preview_data = preview if isinstance(preview, dict) else {}
    if isinstance(roll_result, dict):
        rr = copy.deepcopy(roll_result)
        rr_total = _safe_int(total_value, _safe_int(rr.get("total", 0), 0))
        rr["total"] = rr_total
        br = rr.get("breakdown", {})
        if isinstance(br, dict):
            final_total = _safe_int(br.get("final_total", rr_total), rr_total)
            diff = rr_total - final_total
            if diff != 0:
                br["constant_total"] = _safe_int(br.get("constant_total", 0), 0) + diff
                br["final_total"] = rr_total
            rr["breakdown"] = br
        return build_power_result_snapshot(preview_data, rr)

    power_breakdown = preview_data.get("power_breakdown") if isinstance(preview_data.get("power_breakdown"), dict) else {}
    fallback_constant = _safe_int(power_breakdown.get("final_base_power", 0), 0)
    roll_breakdown = _estimate_roll_breakdown_from_command_and_total(
        command_text,
        total_value,
        fallback_constant=fallback_constant,
    )
    return build_power_result_snapshot(
        preview_data,
        {"total": _safe_int(total_value, 0), "breakdown": roll_breakdown},
    )


def _extract_step_aux_log_lines(trace_entry):
    rows = trace_entry.get("lines")
    if not isinstance(rows, list):
        rows = trace_entry.get("log_lines")
    if not isinstance(rows, list):
        return []

    aux = []
    seen = set()
    for row in rows:
        if row is None:
            continue
        text_raw = str(row).strip()
        if not text_raw:
            continue
        text_plain = re.sub(r"<[^>]*>", " ", text_raw)
        text_plain = re.sub(r"\s+", " ", text_plain).strip()
        if not text_plain:
            continue

        is_match_headline = (" vs " in text_plain and "| " in text_plain)
        if is_match_headline:
            continue

        # Keep status/cost/damage detail style lines near each trace step.
        keep_line = (
            text_plain.startswith("[結果]")
            or text_plain.startswith("[コスト]")
            or text_plain.startswith("[出血]")
            or text_plain.startswith("内訳:")
            or ("内訳:" in text_plain)
            or ("ダメージ" in text_plain)
            or ("付与" in text_plain)
            or ("解除" in text_plain)
            # Backward compatibility for old persisted mojibake logs.
            or text_plain.startswith("[迥ｶ諷犠")
            or text_plain.startswith("[繧ｳ繧ｹ繝・")
            or ("蜀・ｨｳ:" in text_plain)
            or ("繝繝｡繝ｼ繧ｸ" in text_plain)
            or ("蜉ｹ譫懊′" in text_plain)
        )
        if not keep_line:
            continue
        if text_plain in seen:
            continue
        seen.add(text_plain)
        aux.append(text_plain)
    return aux


def _estimate_cost_for_skill_from_snapshot(before_snapshot, skill_data):
    cost = {"mp": 0, "hp": 0, "fp": 0}
    if not isinstance(before_snapshot, dict):
        return cost
    if not isinstance(skill_data, dict):
        return cost

    rule_data = _extract_rule_data_from_skill(skill_data)
    tags = rule_data.get("tags", skill_data.get("tags", [])) if isinstance(rule_data, dict) else skill_data.get("tags", [])
    no_cost_tags = {"消費不要", "コスト不要", "無消費", "no_cost", "free_cost", "蜊ｳ譎ら匱蜍・"}
    if isinstance(tags, list):
        normalized_tags = {str(tag).strip() for tag in tags}
        if normalized_tags.intersection(no_cost_tags):
            return cost

    for entry in _extract_skill_cost_entries(skill_data):
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

        key = c_type.upper()
        if key == "MP":
            current = int(before_snapshot.get("mp", 0))
            cost["mp"] += min(current, c_val)
        elif key == "HP":
            current = int(before_snapshot.get("hp", 0))
            cost["hp"] += min(current, c_val)
        elif key == "FP":
            current = int(before_snapshot.get("fp", 0))
            cost["fp"] += min(current, c_val)
    return cost
