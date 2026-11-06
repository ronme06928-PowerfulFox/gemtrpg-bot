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


def handle_schedule_effect(effect, target_obj, sim_target, session):
    context = session.context if isinstance(session.context, dict) else {}
    nested_effect = effect.get("effect")
    if not isinstance(nested_effect, dict):
        return
    try:
        round_offset = max(1, int(effect.get("round_offset", 1) or 1))
    except (TypeError, ValueError):
        round_offset = 1
    try:
        repeat_count = max(1, int(effect.get("repeat_count", 1) or 1))
    except (TypeError, ValueError):
        repeat_count = 1

    room_state = context.get("room_state")
    battle_state = context.get("battle_state")
    current_round = context.get("round")
    if current_round is None and isinstance(battle_state, dict):
        current_round = battle_state.get("round")
    if current_round is None and isinstance(room_state, dict):
        current_round = room_state.get("round")
    try:
        current_round = int(current_round or 0)
    except (TypeError, ValueError):
        current_round = 0
    if current_round <= 0:
        return

    source_skill = context.get("actor_skill_data")
    source_skill_id = None
    if isinstance(source_skill, dict):
        for key in ("id", "skill_id", "スキルID", "ID"):
            if source_skill.get(key):
                source_skill_id = source_skill.get(key)
                break
    source_skill_id = str(source_skill_id or effect.get("source_skill_id") or "").strip()
    source_slot_id = str(context.get("source_slot_id") or "").strip()
    nested_type = str(nested_effect.get("type") or "").strip().upper()
    nested_id = str(
        nested_effect.get("summon_template_id")
        or nested_effect.get("buff_id")
        or nested_effect.get("value")
        or nested_type
    )
    schedule_key = str(effect.get("schedule_key") or nested_id).strip()
    unique_key = (
        f"{source_slot_id or session.actor.get('id')}:{source_skill_id}:"
        f"{current_round}:{nested_type}:{schedule_key}"
    )
    payload = {
        "unique_key": unique_key,
        "source_actor_id": session.actor.get("id"),
        "source_skill_id": source_skill_id,
        "source_slot_id": source_slot_id,
        "execute_round": current_round + round_offset,
        "repeat_count": repeat_count,
        "effect": copy.deepcopy(nested_effect),
    }
    session.changes_to_apply.append(
        (session.actor, "SCHEDULE_EFFECT", source_skill_id, payload)
    )
    session.log_snippets.append(
        f"[予約 {nested_type} Round {payload['execute_round']} x{repeat_count}]"
    )


HANDLERS = {
    "GRANT_SKILL": handle_grant_skill,
    "USE_SKILL_AGAIN": handle_use_skill_again,
    "SUMMON_CHARACTER": handle_summon_character,
    "SCHEDULE_EFFECT": handle_schedule_effect,
}


SCHEMAS = {
    "GRANT_SKILL": {
        "label": "スキルを付与",
        "description": "スキル付与要求を作る。期間・回数は付与モードに合わせて指定する。",
        "internal": False,
        "fields": {
            "skill_id": {"type": "skill_ref", "required": True, "label": "スキルID", "description": "grant_skill_idでも指定可能。"},
            "grant_mode": {"type": "string", "required": False, "label": "付与モード", "description": "省略時permanent。"},
            "duration": {"type": "int", "required": False, "label": "期間", "description": "roundsでも指定可能。"},
            "uses": {"type": "int", "required": False, "label": "使用回数", "description": "countでも指定可能。"},
            "custom_name": {"type": "string", "required": False, "label": "表示名"},
            "overwrite": {"type": "bool", "required": False, "label": "上書き", "description": "省略時True。"},
            "source_skill_id": {"type": "skill_ref", "required": False, "label": "付与元スキルID"},
        },
        "summary": "{target}にスキル{skill_id}を付与",
        "example": {
            "timing": "PRE_MATCH",
            "type": "GRANT_SKILL",
            "target": "self",
            "skill_id": "E-01",
        },
    },
    "USE_SKILL_AGAIN": {
        "label": "スキルを再使用",
        "description": "同じスロット対象に同じスキルを再使用する要求を作る。",
        "internal": False,
        "fields": {
            "max_reuses": {"type": "int", "required": False, "label": "再使用上限", "description": "省略時1、最小1。max_reuse_count・valueでも指定可能。"},
            "consume_cost": {"type": "bool", "required": False, "label": "元のコストを消費", "description": "省略時False。"},
            "reuse_cost": {"type": "json", "required": False, "label": "再使用コスト", "description": "type・valueを持つ配列または1件。reuse_costsでも指定可能。"},
            "stack_reuse_cost": {"type": "json", "required": False, "label": "再使用スタックコスト", "description": "buff_name・valueを持つ配列または1件。stack_reuse_costsでも指定可能。"},
        },
        "summary": "{target}へスキルを最大{max_reuses}回再使用",
        "example": {
            "timing": "HIT",
            "type": "USE_SKILL_AGAIN",
            "target": "target",
            "max_reuses": 1,
        },
    },
    "SUMMON_CHARACTER": {
        "label": "キャラクターを召喚",
        "description": "テンプレートを元に召喚する要求を作る。対象が自分以外で座標未指定なら対象座標を使う。",
        "internal": False,
        "fields": {
            "summon_template_id": {"type": "summon_ref", "required": True, "label": "召喚テンプレート", "description": "template_id・summon_idでも指定可能。"},
            "summon_duration_mode": {"type": "string", "required": False, "label": "継続方式", "description": "duration_modeでも指定可能。"},
            "summon_duration": {"type": "int", "required": False, "label": "継続期間", "description": "durationでも指定可能。"},
            "summon_type": {"type": "string", "required": False, "label": "召喚陣営", "description": "summon_teamでも指定可能。"},
            "name": {"type": "string", "required": False, "label": "名前"},
            "base_name": {"type": "string", "required": False, "label": "基本名"},
            "x": {"type": "int", "required": False, "label": "X座標"},
            "y": {"type": "int", "required": False, "label": "Y座標"},
            "offset_x": {"type": "int", "required": False, "label": "X座標差"},
            "offset_y": {"type": "int", "required": False, "label": "Y座標差"},
            "commands": {"type": "string", "required": False, "label": "コマンド"},
            "initial_skill_ids": {"type": "json", "required": False, "label": "初期スキルID配列"},
            "custom_skill_names": {"type": "json", "required": False, "label": "スキル表示名"},
            "SPassive": {"type": "json", "required": False, "label": "特殊パッシブ"},
            "special_buffs": {"type": "json", "required": False, "label": "特殊バフ"},
            "radiance_skills": {"type": "json", "required": False, "label": "輝化スキル"},
            "params": {"type": "json", "required": False, "label": "能力値"},
            "states": {"type": "json", "required": False, "label": "状態値"},
            "hp": {"type": "int", "required": False, "label": "HP"},
            "maxHp": {"type": "int", "required": False, "label": "最大HP"},
            "mp": {"type": "int", "required": False, "label": "MP"},
            "maxMp": {"type": "int", "required": False, "label": "最大MP"},
        },
        "summary": "{target}の位置に{summon_template_id}を召喚",
        "example": {
            "timing": "RESOLVE_START",
            "type": "SUMMON_CHARACTER",
            "target": "self",
            "summon_template_id": "U-02",
        },
    },
    "SCHEDULE_EFFECT": {
        "label": "効果を予約",
        "description": "将来ラウンドの開始に実行する効果を予約する。現在の内側効果はSUMMON_CHARACTERのみ。",
        "internal": False,
        "fields": {
            "effect": {"type": "json", "required": True, "label": "予約する効果", "description": "typeを持つオブジェクト。"},
            "round_offset": {"type": "int", "required": False, "label": "何ラウンド後", "description": "省略時1、最小1。"},
            "repeat_count": {"type": "int", "required": False, "label": "予約効果の実行回数", "description": "省略時1、最小1。"},
            "schedule_key": {"type": "string", "required": False, "label": "重複防止キー", "description": "省略時は内側のテンプレートID・バフID・value・typeから決定。"},
            "source_skill_id": {"type": "skill_ref", "required": False, "label": "発生元スキルID", "description": "コンテキストにIDがないとき使用。"},
        },
        "summary": "{target}の効果を{round_offset}ラウンド後に予約",
        "example": {
            "timing": "RESOLVE_START",
            "type": "SCHEDULE_EFFECT",
            "target": "self",
            "round_offset": 1,
            "repeat_count": 2,
            "effect": {
                "type": "SUMMON_CHARACTER",
                "summon_template_id": "U-02",
            },
        },
    },
}
