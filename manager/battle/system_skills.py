import copy

from extensions import all_skill_data


SYS_STRUGGLE_ID = "SYS-STRUGGLE"


SYSTEM_SKILLS = {
    SYS_STRUGGLE_ID: {
        "id": SYS_STRUGGLE_ID,
        "name": "どうにかもがく",
        "display_name": "どうにかもがく",
        "分類": "防御",
        "カテゴリ": "防御",
        "基礎威力": 0,
        "ダイス威力": "0",
        "target_scope": "self",
        "tags": [
            "system_skill",
            "system_fallback",
            "auto_defense",
            "自分対象",
            "防御",
        ],
        "特記": "物理補正もしくは魔法補正のうち、より高い方の値をこのスキルの威力として扱う。",
        "発動時効果": "(ラウンド終了時):物理補正を参照したなら、FPを1得る。魔法補正を参照したなら、MPを1得る。",
        "description": "物理補正もしくは魔法補正のうち、より高い方の値をこのスキルの威力として扱う。 (ラウンド終了時):物理補正を参照したなら、FPを1得る。魔法補正を参照したなら、MPを1得る。",
        "power_stat_choice": {
            "mode": "max",
            "params": ["物理補正", "魔法補正"],
            "tie_breaker": "物理補正",
            "apply_as": "final_power",
        },
        "auto_defense": {
            "enabled": True,
            "count_per_use": 1,
        },
        "rule_data": {
            "target_scope": "self",
            "tags": [
                "system_skill",
                "system_fallback",
                "auto_defense",
                "自分対象",
                "防御",
            ],
            "power_stat_choice": {
                "mode": "max",
                "params": ["物理補正", "魔法補正"],
                "tie_breaker": "物理補正",
                "apply_as": "final_power",
            },
            "auto_defense": {
                "enabled": True,
                "count_per_use": 1,
            },
            "effects": [],
            "cost": [],
        },
    }
}


def ensure_system_skills_registered():
    if not isinstance(all_skill_data, dict):
        return
    for skill_id, skill_data in SYSTEM_SKILLS.items():
        current = all_skill_data.get(skill_id)
        if isinstance(current, dict) and current.get("_system_skill_registered"):
            continue
        merged = copy.deepcopy(skill_data)
        merged["_system_skill_registered"] = True
        all_skill_data[skill_id] = merged


def get_system_skill(skill_id):
    ensure_system_skills_registered()
    if skill_id in SYSTEM_SKILLS:
        return all_skill_data.get(skill_id)
    return all_skill_data.get(skill_id)


def is_system_skill_id(skill_id):
    return str(skill_id or "").strip() in SYSTEM_SKILLS


def is_auto_defense_skill_data(skill_data):
    if not isinstance(skill_data, dict):
        return False
    auto_defense = skill_data.get("auto_defense")
    if isinstance(auto_defense, dict):
        return bool(auto_defense.get("enabled", False))
    rule_data = skill_data.get("rule_data")
    if isinstance(rule_data, dict):
        auto_defense = rule_data.get("auto_defense")
        if isinstance(auto_defense, dict):
            return bool(auto_defense.get("enabled", False))
    return False


def grant_auto_defense_charge(battle_state, actor_id, skill_id, count=1):
    if not isinstance(battle_state, dict) or not actor_id:
        return 0
    resolve = battle_state.setdefault("resolve", {})
    charges = resolve.get("auto_defense_charges")
    if not isinstance(charges, dict):
        charges = {}
        resolve["auto_defense_charges"] = charges
    actor_key = str(actor_id)
    actor_charges = charges.get(actor_key)
    if not isinstance(actor_charges, list):
        actor_charges = []
        charges[actor_key] = actor_charges
    granted = 0
    for _ in range(max(0, int(count or 0))):
        actor_charges.append({"skill_id": str(skill_id or "").strip()})
        granted += 1
    return granted


def consume_auto_defense_charge(battle_state, actor_id):
    if not isinstance(battle_state, dict) or not actor_id:
        return None
    charges = (battle_state.get("resolve") or {}).get("auto_defense_charges")
    if not isinstance(charges, dict):
        return None
    actor_charges = charges.get(str(actor_id))
    if not isinstance(actor_charges, list) or not actor_charges:
        return None
    return actor_charges.pop(0)


def queue_selected_power_recovery(actor, selected_param):
    if not isinstance(actor, dict):
        return False
    param = str(selected_param or "").strip()
    if param == "物理補正":
        state_name = "FP"
    elif param == "魔法補正":
        state_name = "MP"
    else:
        return False
    rows = actor.get("_pending_selected_power_recoveries")
    if not isinstance(rows, list):
        rows = []
        actor["_pending_selected_power_recoveries"] = rows
    rows.append(state_name)
    return True


def queue_selected_power_recovery_from_snapshot(actor, power_snapshot):
    if not isinstance(power_snapshot, dict):
        return False
    selected_param = power_snapshot.get("selected_power_param")
    if not selected_param:
        raw = power_snapshot.get("raw")
        if isinstance(raw, dict):
            preview = raw.get("preview")
            if isinstance(preview, dict):
                breakdown = preview.get("power_breakdown")
                if isinstance(breakdown, dict):
                    selected_param = breakdown.get("selected_power_param")
    return queue_selected_power_recovery(actor, selected_param)


def pop_pending_selected_power_recoveries(actor):
    if not isinstance(actor, dict):
        return []
    rows = actor.get("_pending_selected_power_recoveries")
    if not isinstance(rows, list):
        return []
    actor["_pending_selected_power_recoveries"] = []
    return list(rows)


ensure_system_skills_registered()
