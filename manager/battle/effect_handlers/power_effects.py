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
