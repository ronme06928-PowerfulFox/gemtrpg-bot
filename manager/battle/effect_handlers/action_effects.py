# manager/battle/effect_handlers/action_effects.py
# 行動系 effect ハンドラ（計画書29 Phase 4 で game_logic.process_skill_effects から移設）。
# ロジック・ログ文字列・changes_to_apply の形式は移設前と同一。
import copy


def handle_grant_skill(effect, target_obj, sim_target, session):
    grant_skill_id = str(effect.get("skill_id", effect.get("grant_skill_id", "")) or "").strip()
    if not grant_skill_id:
        return
    grant_payload = {
        "skill_id": grant_skill_id,
        "grant_mode": effect.get("grant_mode", "permanent"),
        "duration": effect.get("duration", effect.get("rounds")),
        "uses": effect.get("uses", effect.get("count")),
        "custom_name": effect.get("custom_name"),
        "overwrite": effect.get("overwrite", True),
        "source_skill_id": effect.get("source_skill_id"),
    }
    session.changes_to_apply.append((target_obj, "GRANT_SKILL", grant_skill_id, grant_payload))
    session.log_snippets.append(f"[スキル付与 {grant_skill_id}]")


def handle_use_skill_again(effect, target_obj, sim_target, session):
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
    session.changes_to_apply.append((target_obj, "USE_SKILL_AGAIN", "None", request_payload))
    session.log_snippets.append(f"[スキル再使用 x{max_reuses}]")


def handle_summon_character(effect, target_obj, sim_target, session):
    actor = session.actor

    summon_template_id = (
        effect.get("summon_template_id")
        or effect.get("template_id")
        or effect.get("summon_id")
    )
    if not summon_template_id:
        return
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

    session.changes_to_apply.append((actor, "SUMMON_CHARACTER", str(summon_template_id), summon_payload))
    session.log_snippets.append(f"[召喚 {summon_template_id}]")


HANDLERS = {
    "GRANT_SKILL": handle_grant_skill,
    "USE_SKILL_AGAIN": handle_use_skill_again,
    "SUMMON_CHARACTER": handle_summon_character,
}
