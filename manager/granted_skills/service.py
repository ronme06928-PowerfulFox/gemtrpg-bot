from __future__ import annotations

import re

from extensions import all_skill_data


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _parse_bool(value, default=False):
    if value in (None, ""):
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "ok"}:
        return True
    if text in {"0", "false", "no", "n", "off", "ng"}:
        return False
    return bool(default)


def _normalize_grant_mode(raw_value):
    text = str(raw_value or "permanent").strip().lower()
    if text in {"permanent", "duration_rounds", "usage_count"}:
        return text
    return "permanent"


def _split_command_lines(commands_text):
    return [line.strip() for line in str(commands_text or "").splitlines() if str(line or "").strip()]


def _join_command_lines(lines):
    return "\n".join([str(line or "").strip() for line in (lines or []) if str(line or "").strip()])


def _extract_skill_id_from_line(command_line):
    line = str(command_line or "").strip()
    if not line:
        return None
    m = re.search(r"[【\[]\s*([^\s\]】]+)", line)
    if not m:
        return None
    return str(m.group(1) or "").strip() or None


def _commands_has_skill(commands_text, skill_id):
    sid = str(skill_id or "").strip()
    if not sid:
        return False
    for line in _split_command_lines(commands_text):
        if _extract_skill_id_from_line(line) == sid:
            return True
    return False


def _remove_skill_command_lines(commands_text, skill_id):
    sid = str(skill_id or "").strip()
    kept = []
    for line in _split_command_lines(commands_text):
        if _extract_skill_id_from_line(line) == sid:
            continue
        kept.append(line)
    return _join_command_lines(kept)


def _build_skill_command_line(skill_id, custom_name=None):
    sid = str(skill_id or "").strip()
    if not sid:
        return ""

    skill_data = all_skill_data.get(sid, {}) if isinstance(all_skill_data, dict) else {}
    palette = str(skill_data.get("チャットパレット", "") or "").strip()
    custom = str(custom_name or "").strip()

    if custom:
        if palette:
            return re.sub(r"[【\[].*?[】\]]", f"【{sid} {custom}】", palette, count=1)
        return f"【{sid} {custom}】"

    if palette:
        return palette

    base_name = (
        skill_data.get("デフォルト名称")
        or skill_data.get("name")
        or skill_data.get("名称")
        or sid
    )
    return f"【{sid} {base_name}】"


def _upsert_granted_entry(granted_skills, entry):
    sid = str(entry.get("skill_id", "") or "").strip()
    if not sid:
        return granted_skills

    out = []
    replaced = False
    for row in granted_skills:
        if not isinstance(row, dict):
            continue
        if str(row.get("skill_id", "") or "").strip() == sid:
            if not replaced:
                out.append(dict(entry))
                replaced = True
            continue
        out.append(row)
    if not replaced:
        out.append(dict(entry))
    return out


def apply_grant_skill_change(room, state, source_char, target_char, payload):
    """
    GRANT_SKILL change を適用する。
    Returns:
        dict: {'ok': bool, 'message': str, 'changed': bool}
    """
    _ = room
    if not isinstance(payload, dict):
        return {"ok": False, "message": "invalid grant payload", "changed": False}
    if not isinstance(target_char, dict):
        return {"ok": False, "message": "target character is missing", "changed": False}

    skill_id = str(payload.get("skill_id", payload.get("grant_skill_id", "")) or "").strip()
    if not skill_id:
        return {"ok": False, "message": "skill_id is required", "changed": False}
    if not (isinstance(all_skill_data, dict) and isinstance(all_skill_data.get(skill_id), dict)):
        return {"ok": False, "message": f"unknown skill_id: {skill_id}", "changed": False}

    grant_mode = _normalize_grant_mode(payload.get("grant_mode", "permanent"))
    duration = _safe_int(payload.get("duration", payload.get("rounds", 0)), 0)
    uses = _safe_int(payload.get("uses", payload.get("count", 0)), 0)
    overwrite = _parse_bool(payload.get("overwrite", True), default=True)
    custom_name = str(payload.get("custom_name", "") or "").strip() or None

    if grant_mode == "duration_rounds" and duration <= 0:
        return {"ok": False, "message": "duration_rounds requires duration >= 1", "changed": False}
    if grant_mode == "usage_count" and uses <= 0:
        return {"ok": False, "message": "usage_count requires uses >= 1", "changed": False}

    granted_skills = target_char.get("granted_skills", [])
    if not isinstance(granted_skills, list):
        granted_skills = []

    existing = next(
        (
            row for row in granted_skills
            if isinstance(row, dict) and str(row.get("skill_id", "") or "").strip() == skill_id
        ),
        None
    )
    if existing and not overwrite:
        return {"ok": True, "message": f"{target_char.get('name', 'target')} は既に {skill_id} を付与済み。", "changed": False}

    current_commands = str(target_char.get("commands", "") or "")
    had_skill_before = _commands_has_skill(current_commands, skill_id)
    injected = bool(existing.get("injected", False)) if isinstance(existing, dict) else False

    if not had_skill_before:
        command_line = _build_skill_command_line(skill_id, custom_name=custom_name)
        command_lines = _split_command_lines(current_commands)
        if command_line:
            command_lines.append(command_line)
            target_char["commands"] = _join_command_lines(command_lines)
            injected = True

    round_value = 0
    if isinstance(state, dict):
        round_value = _safe_int(state.get("round", 0), 0)

    entry = {
        "skill_id": skill_id,
        "mode": grant_mode,
        "remaining_rounds": (duration if grant_mode == "duration_rounds" else None),
        "remaining_uses": (uses if grant_mode == "usage_count" else None),
        "source_actor_id": (source_char.get("id") if isinstance(source_char, dict) else None),
        "source_skill_id": payload.get("source_skill_id"),
        "granted_at_round": round_value,
        "custom_name": custom_name,
        "injected": bool(injected),
    }
    target_char["granted_skills"] = _upsert_granted_entry(granted_skills, entry)
    return {"ok": True, "message": f"{target_char.get('name', 'target')} に {skill_id} を付与。", "changed": True}


def consume_granted_skill_use(char_obj, used_skill_id):
    """
    usage_count モードの付与スキル消費を処理する。
    Returns:
        list[dict]: expired entries
    """
    if not isinstance(char_obj, dict):
        return []
    skill_id = str(used_skill_id or "").strip()
    if not skill_id:
        return []
    rows = char_obj.get("granted_skills", [])
    if not isinstance(rows, list) or not rows:
        return []

    expired = []
    kept = []
    commands = str(char_obj.get("commands", "") or "")

    for row in rows:
        if not isinstance(row, dict):
            continue
        row_skill_id = str(row.get("skill_id", "") or "").strip()
        if row_skill_id != skill_id:
            kept.append(row)
            continue

        mode = _normalize_grant_mode(row.get("mode", "permanent"))
        if mode != "usage_count":
            kept.append(row)
            continue

        remaining = _safe_int(row.get("remaining_uses", 0), 0) - 1
        if remaining > 0:
            row["remaining_uses"] = remaining
            kept.append(row)
            continue

        if _parse_bool(row.get("injected", False), default=False):
            commands = _remove_skill_command_lines(commands, row_skill_id)
        expired.append({"skill_id": row_skill_id, "reason": "usage_exhausted", "char_id": char_obj.get("id")})

    char_obj["granted_skills"] = kept
    char_obj["commands"] = commands
    return expired


def process_granted_skill_round_end(state, room=None):
    """
    duration_rounds モードの付与スキルをラウンド終了時に減衰させる。
    Returns:
        list[dict]: expired entries
    """
    _ = room
    if not isinstance(state, dict):
        return []
    chars = state.get("characters", [])
    if not isinstance(chars, list):
        return []

    expired = []
    for char in chars:
        if not isinstance(char, dict):
            continue
        rows = char.get("granted_skills", [])
        if not isinstance(rows, list) or not rows:
            continue

        kept = []
        commands = str(char.get("commands", "") or "")
        for row in rows:
            if not isinstance(row, dict):
                continue
            mode = _normalize_grant_mode(row.get("mode", "permanent"))
            if mode != "duration_rounds":
                kept.append(row)
                continue

            remaining = _safe_int(row.get("remaining_rounds", 0), 0) - 1
            if remaining > 0:
                row["remaining_rounds"] = remaining
                kept.append(row)
                continue

            if _parse_bool(row.get("injected", False), default=False):
                commands = _remove_skill_command_lines(commands, row.get("skill_id"))
            expired.append(
                {
                    "skill_id": row.get("skill_id"),
                    "reason": "duration_expired",
                    "char_id": char.get("id"),
                    "char_name": char.get("name"),
                }
            )

        char["granted_skills"] = kept
        char["commands"] = commands
    return expired

