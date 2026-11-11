# manager/battle/effect_handlers/power_effects.py
# 威力修飾系 effect ハンドラ（計画書29 Phase 4 で game_logic.process_skill_effects から移設）。
# ロジック・ログ文字列・changes_to_apply の形式は移設前と同一。


def handle_damage_bonus(effect, target_obj, sim_target, session):
    damage = int(effect.get("value", 0))
    if damage > 0:
        session.total_bonus_damage += damage
        session.log_snippets.append(f"[追加ダメージ +{damage}]")


def handle_modify_roll(effect, target_obj, sim_target, session):
    mod_value = int(effect.get("value", 0))
    if mod_value != 0:
        session.total_bonus_damage += mod_value
        session.log_snippets.append(f"[ロール補正 {mod_value:+}]")


def handle_force_unopposed(effect, target_obj, sim_target, session):
    session.changes_to_apply.append((target_obj, "FORCE_UNOPPOSED", "None", 0))


def handle_modify_base_power(effect, target_obj, sim_target, session):
    mod_value = int(effect.get("value", 0))
    if mod_value != 0:
        session.changes_to_apply.append((target_obj, "MODIFY_BASE_POWER", None, mod_value))
        session.log_snippets.append(f"[基礎威力 {mod_value:+}]")


def handle_modify_final_power(effect, target_obj, sim_target, session):
    mod_value = int(effect.get("value", 0))
    if mod_value != 0:
        session.changes_to_apply.append((target_obj, "MODIFY_FINAL_POWER", None, mod_value))
        session.log_snippets.append(f"[最終威力 {mod_value:+}]")


def handle_drain_hp(effect, target_obj, sim_target, session):
    if session.base_damage > 0:
        rate = float(effect.get("value", 0))

        calc_base = session.base_damage
        if session.target:
            target_current_hp = session.get_status_value(session.target, 'HP')
            if target_current_hp < calc_base:
                calc_base = target_current_hp

        heal_val = int(calc_base * rate)
        if heal_val > 0:
            sim_actor = session.get_simulated_char(session.actor)
            current_hp = session.get_status_value(sim_actor, 'HP')
            session.set_status_value(sim_actor, 'HP', current_hp + heal_val)

            session.changes_to_apply.append((session.actor, "APPLY_STATE", "HP", heal_val))
            session.log_snippets.append(f"[吸収 +{heal_val}]")


HANDLERS = {
    "DAMAGE_BONUS": handle_damage_bonus,
    "MODIFY_ROLL": handle_modify_roll,
    "FORCE_UNOPPOSED": handle_force_unopposed,
    "MODIFY_BASE_POWER": handle_modify_base_power,
    "MODIFY_FINAL_POWER": handle_modify_final_power,
    "DRAIN_HP": handle_drain_hp,
}


SCHEMAS = {
    "DAMAGE_BONUS": {
        "group": "ダメージ・回復",
        "label": "追加ダメージ",
        "description": "正のvalueを追加ダメージへ加算する。0以下は不発。",
        "internal": False,
        "fields": {
            "value": {"type": "int", "required": True, "label": "補正量", "description": "省略時0。"},
        },
        "summary": "{target}に追加ダメージ{value}",
        "example": {
            "timing": "HIT",
            "type": "DAMAGE_BONUS",
            "target": "target",
            "value": 2,
        },
    },
    "MODIFY_ROLL": {
        "group": "威力・ロール",
        "label": "ロール補正",
        "description": "valueを追加ダメージの合計へ加算する。負数も使用可能。",
        "internal": False,
        "fields": {
            "value": {"type": "int", "required": True, "label": "補正量", "description": "省略時0。"},
        },
        "summary": "{target}にロール補正{value}",
        "example": {
            "timing": "PRE_MATCH",
            "type": "MODIFY_ROLL",
            "target": "target",
            "value": 2,
        },
    },
    "MODIFY_BASE_POWER": {
        "group": "威力・ロール",
        "label": "基礎威力補正",
        "description": "基礎威力にvalueを加減する要求を作る。",
        "internal": False,
        "fields": {
            "value": {"type": "int", "required": True, "label": "補正量", "description": "省略時0。"},
        },
        "summary": "{target}に基礎威力補正{value}",
        "example": {
            "timing": "PRE_MATCH",
            "type": "MODIFY_BASE_POWER",
            "target": "target",
            "value": 2,
        },
    },
    "MODIFY_FINAL_POWER": {
        "group": "威力・ロール",
        "label": "最終威力補正",
        "description": "最終威力にvalueを加減する要求を作る。",
        "internal": False,
        "fields": {
            "value": {"type": "int", "required": True, "label": "補正量", "description": "省略時0。"},
        },
        "summary": "{target}に最終威力補正{value}",
        "example": {
            "timing": "PRE_MATCH",
            "type": "MODIFY_FINAL_POWER",
            "target": "target",
            "value": 2,
        },
    },
    "DRAIN_HP": {
        "group": "ダメージ・回復",
        "label": "HP吸収",
        "description": "与えた基礎ダメージと対象の現在HPの小さい方にvalueを掛け、整数化した量を自分のHPへ加える。",
        "internal": False,
        "fields": {
            "value": {"type": "number", "required": True, "label": "吸収率", "description": "省略時0。"},
        },
        "summary": "自分のHPをダメージの{value}倍回復",
        "example": {
            "timing": "HIT",
            "type": "DRAIN_HP",
            "target": "target",
            "value": 0.5,
        },
    },
    "FORCE_UNOPPOSED": {
        "group": "行動・進行",
        "label": "一方攻撃を強制",
        "description": "一方攻撃への変更要求を作る。",
        "internal": True,
        "fields": {},
        "summary": "{target}への一方攻撃を強制",
        "example": {
            "timing": "PRE_MATCH",
            "type": "FORCE_UNOPPOSED",
            "target": "target",
        },
    },
}
