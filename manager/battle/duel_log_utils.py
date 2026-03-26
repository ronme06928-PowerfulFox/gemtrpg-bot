import re

from extensions import all_skill_data
from manager.logs import setup_logger

logger = setup_logger(__name__)

DAMAGE_LABEL_DICE = "ダイス"
DAMAGE_LABEL_EFFECT = "効果"
DAMAGE_LABEL_GENERIC = "ダメージ"

# Read-only compatibility aliases for previously persisted mojibake labels.
_LEGACY_DICE_ALIASES = {
    "繝繧､繧ｹ",
    "蟾ｮ蛻・ム繝｡繝ｼ繧ｸ",
    "蜷郁ｨ医ム繝｡繝ｼ繧ｸ",
}
_LEGACY_EFFECT_ALIASES = {
    "繧ｭ繝ｼ繝ｯ繝ｼ繝牙柑譫懊ム繝｡繝ｼ繧ｸ",
}


def _resolve_actor_name(characters_by_id, actor_id):
    if not actor_id:
        return "(none)"
    actor = characters_by_id.get(actor_id) if isinstance(characters_by_id, dict) else None
    if isinstance(actor, dict):
        return actor.get("name") or str(actor_id)
    return str(actor_id)


def _resolve_skill_name(skill_id, skill_data=None):
    skill_data = skill_data if isinstance(skill_data, dict) else {}
    if (not skill_data) and skill_id:
        skill_data = all_skill_data.get(skill_id, {}) if isinstance(all_skill_data, dict) else {}
    name = (
        skill_data.get("name")
        or skill_data.get("default_name")
        or skill_data.get("skill_name")
        or skill_data.get("繝・ヵ繧ｩ繝ｫ繝亥錐遘ｰ")
        or (str(skill_id) if skill_id else "(none)")
    )
    if skill_id:
        return f"{name} ({skill_id})"
    return str(name)


def _extract_skill_id_from_data(skill_data, fallback=None):
    if fallback:
        return str(fallback)
    if not isinstance(skill_data, dict):
        return None

    direct_keys = ["id", "skill_id", "skillID", "skillId", "スキルID", "繧ｹ繧ｭ繝ｫID"]
    for key in direct_keys:
        val = skill_data.get(key)
        if val:
            return str(val)

    for key, value in skill_data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if "id" not in key.lower():
            continue
        m = re.search(r"^\s*([A-Za-z]{1,4}-\d{2,3})\s*$", value)
        if m:
            return str(m.group(1))

    for value in skill_data.values():
        if not isinstance(value, str):
            continue
        m = re.search(r"\b([A-Za-z]{1,4}-\d{2,3})\b", value)
        if m:
            return str(m.group(1))

    try:
        for sid, sdata in (all_skill_data or {}).items():
            if sdata is skill_data:
                return str(sid)
    except Exception:
        pass
    return None


def _format_damage_lines(damage_events, characters_by_id):
    lines = []
    for row in damage_events or []:
        if not isinstance(row, dict):
            continue
        target_id = row.get("target_id")
        target_name = _resolve_actor_name(characters_by_id, target_id)
        dmg = row.get("hp", row.get("amount", 0))
        try:
            dmg = int(dmg)
        except (TypeError, ValueError):
            dmg = 0
        lines.append(f"damage: {target_name} -{dmg}")
    return lines


def _format_status_lines(status_events, characters_by_id):
    lines = []
    for row in status_events or []:
        if not isinstance(row, dict):
            continue
        target_name = _resolve_actor_name(characters_by_id, row.get("target_id"))
        name = row.get("name") or row.get("type") or "status"
        before = row.get("before")
        after = row.get("after")
        if before is not None and after is not None:
            lines.append(f"status: {target_name} {name} {before}->{after}")
            continue
        delta = row.get("delta")
        if delta is not None:
            lines.append(f"status: {target_name} {name} {delta:+}")
        else:
            lines.append(f"status: {target_name} {name}")
    return lines


def _build_match_log_lines(
    kind,
    attacker_name,
    defender_name,
    attacker_skill_name,
    defender_skill_name=None,
    outcome="no_effect",
    rolls=None,
    tie_break=None,
    damage_events=None,
    status_events=None,
    cost=None,
    reason=None,
    characters_by_id=None,
):
    rolls = rolls if isinstance(rolls, dict) else {}
    cost = cost if isinstance(cost, dict) else {"mp": 0, "hp": 0, "fp": 0}
    power_a = rolls.get("power_a")
    power_b = rolls.get("power_b")
    if power_a is None:
        power_a = rolls.get("total_damage", rolls.get("final_damage", rolls.get("base_damage")))
    if power_b is None and kind == "one_sided":
        power_b = "-"

    lines = [
        f"kind={kind}",
        f"attacker={attacker_name}",
        f"defender={defender_name}",
        f"skill_a={attacker_skill_name}",
    ]
    if defender_skill_name:
        lines.append(f"skill_b={defender_skill_name}")
    lines.append(f"power_a={power_a if power_a is not None else '-'}")
    lines.append(f"power_b={power_b if power_b is not None else '-'}")
    if tie_break not in [None, "", "draw"]:
        lines.append(f"tie_break={tie_break}")
    elif tie_break == "draw":
        lines.append("tie_break=draw")
    if reason:
        lines.append(f"reason={reason}")
    lines.append(f"outcome={outcome}")

    name_map = characters_by_id if isinstance(characters_by_id, dict) else {}
    lines.extend(_format_damage_lines(damage_events, name_map))
    lines.extend(_format_status_lines(status_events, name_map))
    lines.append(
        "cost: HP={hp} MP={mp} FP={fp}".format(
            hp=int(cost.get("hp", 0)),
            mp=int(cost.get("mp", 0)),
            fp=int(cost.get("fp", 0)),
        )
    )
    return lines


def _log_match_result(log_lines):
    if not isinstance(log_lines, list) or not log_lines:
        return
    for line in log_lines:
        logger.info("[match_result] %s", str(line))


def _is_dice_damage_source(source_name):
    src = str(source_name or "").strip()
    if not src:
        return False

    src_lower = src.lower()
    if src in _LEGACY_DICE_ALIASES:
        return True
    if src in {"ダイス", "ダイスダメージ", "合計ダメージ", "基礎ダメージ"}:
        return True
    if "ダイス" in src:
        return True
    if "dice" in src_lower:
        return True
    if "base_damage" in src_lower or "power_roll" in src_lower:
        return True
    if "mass_summation_delta" in src_lower:
        return True
    return False


def _split_damage_entries_for_display(entries):
    out = {
        "dice_total": 0,
        "effect_total": 0,
        "dice_parts": [],
        "effect_parts": [],
    }
    for item in entries or []:
        if not isinstance(item, dict):
            continue
        src = str(item.get("source", DAMAGE_LABEL_GENERIC) or DAMAGE_LABEL_GENERIC).strip()
        if src in _LEGACY_EFFECT_ALIASES:
            src = "効果ダメージ"
        elif src in _LEGACY_DICE_ALIASES:
            src = "ダイスダメージ"

        try:
            value = int(item.get("value", 0))
        except (TypeError, ValueError):
            value = 0
        if value <= 0:
            continue

        part_label = f"[{src} {value}]"
        if _is_dice_damage_source(src):
            out["dice_total"] += value
            out["dice_parts"].append(part_label)
        else:
            out["effect_total"] += value
            out["effect_parts"].append(part_label)
    return out


def _extract_damage_parts_from_legacy_lines(lines, attacker_name, defender_name):
    out = {"A": [], "D": []}
    if not isinstance(lines, list):
        return out

    for line in lines:
        if not isinstance(line, str) or "<strong>" not in line:
            continue
        if ("内訳" not in line) and ("蜀・ｨｳ" not in line):
            continue

        m_target = re.search(r"<strong>([^<]+)</strong>", line)
        if not m_target:
            continue

        target_name = str(m_target.group(1) or "").strip()
        side_key = "A" if target_name == attacker_name else ("D" if target_name == defender_name else None)
        if not side_key:
            continue

        if "内訳:" in line:
            details_text = line.split("内訳:", 1)[1]
        elif "蜀・ｨｳ:" in line:
            details_text = line.split("蜀・ｨｳ:", 1)[1]
        else:
            details_text = ""

        for src, raw_value in re.findall(r"\[([^\[\]]+)\s+(-?\d+)\]", details_text):
            source = str(src or "").strip()
            if not source:
                continue
            try:
                value = abs(int(raw_value))
            except (TypeError, ValueError):
                value = 0
            if value <= 0:
                continue
            out[side_key].append({"source": source, "value": value})
    return out


def format_duel_result_lines(
    actor_name_a,
    skill_display_a,
    total_a,
    actor_name_d,
    skill_display_d,
    total_d,
    winner_message,
    damage_report=None,
    extra_lines=None,
):
    lines = []
    match_log = (
        f"<strong>{actor_name_a}</strong> {skill_display_a} "
        f"(<span class='dice-result-total'>{total_a}</span>) vs "
        f"<strong>{actor_name_d}</strong> {skill_display_d} "
        f"(<span class='dice-result-total'>{total_d}</span>) | {winner_message}"
    )
    lines.append(match_log)

    report = damage_report if isinstance(damage_report, dict) else {}
    for target_key, char_name in [("D", actor_name_d), ("A", actor_name_a)]:
        entries = report.get(target_key, []) or []
        if not entries:
            continue
        split = _split_damage_entries_for_display(entries)
        dice_total = int(split.get("dice_total", 0))
        effect_total = int(split.get("effect_total", 0))
        total_dmg = dice_total + effect_total
        if total_dmg <= 0:
            continue

        details_parts = []
        if dice_total > 0:
            details_parts.append(f"[{DAMAGE_LABEL_DICE} {dice_total}]")
        if effect_total > 0:
            if split.get("effect_parts"):
                details_parts.extend(split.get("effect_parts"))
            else:
                details_parts.append(f"[{DAMAGE_LABEL_EFFECT} {effect_total}]")
        details = " + ".join(details_parts) if details_parts else "[内訳なし]"

        damage_line = (
            f"<strong>{char_name}</strong> に <strong>{total_dmg}</strong> ダメージ"
            f"<br><span style='font-size:0.9em; color:#888;'>内訳: {details}</span>"
        )
        lines.append(damage_line)

    if isinstance(extra_lines, list):
        seen_extra = set()
        for line in extra_lines:
            if line is None:
                continue
            line_str = str(line).strip()
            if line_str and (line_str not in seen_extra):
                seen_extra.add(line_str)
                lines.append(line_str)
    return lines
