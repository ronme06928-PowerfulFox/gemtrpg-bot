# manager/game_logic.py
import sys
from manager.utils import get_status_value, set_status_value, apply_buff, remove_buff
from manager.buff_catalog import BUFF_EFFECTS

# プラグインシステム (pluginsフォルダはルートにあるのでそのままでOK)
from plugins import EFFECT_REGISTRY

def _get_value_for_condition(source_obj, param_name):
    if not source_obj: return None
    if param_name == "tags": return source_obj.get("tags", [])
    return get_status_value(source_obj, param_name)

def check_condition(condition_obj, actor, target, target_skill_data=None, actor_skill_data=None):
    if not condition_obj: return True
    source_str = condition_obj.get("source")
    param_name = condition_obj.get("param")
    op = condition_obj.get("operator")
    check_value = condition_obj.get("value")

    if not source_str or not param_name or not op or check_value is None: return False

    source_obj = None
    if source_str == "self": source_obj = actor
    elif source_str == "target": source_obj = target
    elif source_str == "target_skill": source_obj = target_skill_data
    elif source_str == "skill" or source_str == "actor_skill": source_obj = actor_skill_data

    current_value = _get_value_for_condition(source_obj, param_name)
    if current_value is None: return False

    try:
        if op == "CONTAINS": return check_value in current_value
        current_value = int(current_value)
        check_value = int(check_value)
        if op == "GTE": return current_value >= check_value
        elif op == "LTE": return current_value <= check_value
        elif op == "GT": return current_value > check_value
        elif op == "LT": return current_value < check_value
        elif op == "EQUALS": return current_value == check_value
    except Exception:
        return False
    return False

def calculate_buff_power_bonus(actor, target, actor_skill_data):
    """
    キャラクターが所持するバフに基づき、威力ボーナスを計算する
    """
    total_buff_bonus = 0

    if not actor or 'special_buffs' not in actor:
        return 0

    # キャラクターが持っているバフを1つずつチェック
    for buff in actor['special_buffs']:
        buff_name = buff.get('name')

        # 定義ファイルにデータがあるか確認
        effect_data = BUFF_EFFECTS.get(buff_name)
        if not effect_data:
            continue

        # power_bonus 定義がある場合
        power_bonuses = effect_data.get('power_bonus', [])

        # 既存の calculate_power_bonus の内部ロジック(_get_bonus)を再利用したいが、
        # condition判定が必要なため、ここでループ処理する
        for rule in power_bonuses:
            # 1. 適用条件(condition)のチェック
            condition = rule.get('condition')
            if condition:
                # 自分のスキル情報(actor_skill_data)も渡して判定
                if not check_condition(condition, actor, target, actor_skill_data=actor_skill_data):
                    continue

            # 2. ボーナス値の計算 (既存関数のロジックを流用または再実装)
            # ここではシンプルに再実装します
            bonus = 0
            operation = rule.get('operation', 'FIXED')

            if operation == 'FIXED':
                bonus = int(rule.get('value', 0))

            elif operation in ['MULTIPLY', 'FIXED_IF_EXISTS', 'PER_N_BONUS']:
                # 参照先を取得
                src_type = rule.get('source', 'self')
                src_obj = target if src_type == 'target' else actor
                p_name = rule.get('param')
                val = get_status_value(src_obj, p_name)

                if operation == 'MULTIPLY':
                    bonus = int(val * float(rule.get('value_per_param', 0)))
                elif operation == 'FIXED_IF_EXISTS':
                    if val >= int(rule.get('threshold', 1)): # thresholdがなければ1以上
                        bonus = int(rule.get('value', 0))
                elif operation == 'PER_N_BONUS':
                    N = int(rule.get('per_N', 1))
                    if N > 0:
                        bonus = (val // N) * int(rule.get('value', 0))

            # 上限適用
            if 'max_bonus' in rule:
                bonus = min(bonus, int(rule['max_bonus']))

            total_buff_bonus += bonus

    return total_buff_bonus

def execute_custom_effect(effect, actor, target):
    """
    プラグイン化されたカスタム効果を実行する
    """
    effect_name = effect.get("value")
    handler = EFFECT_REGISTRY.get(effect_name)

    if not handler:
        print(f"DEBUG: Unknown CUSTOM_EFFECT '{effect_name}'")
        return [], []

    try:
        # コンテキストとしてレジストリを渡す（亀裂崩壊などで再帰的に使うため）
        context = {
            "registry": EFFECT_REGISTRY
        }
        return handler.apply(actor, target, effect, context)
    except Exception as e:
        print(f"❌ Plugin Error ({effect_name}): {e}", file=sys.stderr)
        return [], []

def process_skill_effects(effects_array, timing_to_check, actor, target, target_skill_data=None):
    total_bonus_damage = 0
    log_snippets = []
    changes_to_apply = []

    if not actor or not effects_array:
        return 0, [], []

    for effect in effects_array:
        if effect.get("timing") != timing_to_check: continue
        if not check_condition(effect.get("condition"), actor, target, target_skill_data): continue

        effect_type = effect.get("type")
        target_obj = None
        if effect.get("target") == "self": target_obj = actor
        elif effect.get("target") == "target": target_obj = target

        if not target_obj and effect.get("target") == "target": continue

        if effect_type == "APPLY_STATE":
            stat_name = effect.get("state_name")
            value = int(effect.get("value", 0))
            if stat_name and value != 0:
                changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, value))

        elif effect_type == "APPLY_BUFF":
            buff_name = effect.get("buff_name")
            lasting = int(effect.get("lasting", 1))
            delay = int(effect.get("delay", 0))
            if buff_name:
                changes_to_apply.append((target_obj, "APPLY_BUFF", buff_name, {"lasting": lasting, "delay": delay, "data": effect.get("data")}))
                log_snippets.append(f"[{buff_name} 付与]")

        elif effect_type == "REMOVE_BUFF":
            buff_name = effect.get("buff_name")
            if buff_name:
                changes_to_apply.append((target_obj, "REMOVE_BUFF", buff_name, 0))
                log_snippets.append(f"[{buff_name} 解除]")

        elif effect_type == "DAMAGE_BONUS":
            damage = int(effect.get("value", 0))
            if damage > 0:
                total_bonus_damage += damage
                log_snippets.append(f"+ [追加ダメージ {damage}]")

        elif effect_type == "MODIFY_ROLL":
            mod_value = int(effect.get("value", 0))
            if mod_value != 0:
                total_bonus_damage += mod_value
                log_snippets.append(f"[ロール修正 {mod_value:+,}]")

        elif effect_type == "CUSTOM_EFFECT":
            # ★ プラグイン呼び出し
            custom_changes, custom_logs = execute_custom_effect(effect, actor, target)
            changes_to_apply.extend(custom_changes)
            log_snippets.extend(custom_logs)

        elif effect_type == "FORCE_UNOPPOSED":
            changes_to_apply.append((target_obj, "FORCE_UNOPPOSED", "None", 0))

    return total_bonus_damage, log_snippets, changes_to_apply

def calculate_power_bonus(actor, target, power_bonus_data):
    # (この関数は変更なし、ロジックそのまま)
    def _get_bonus(rule, s, t):
        if not rule: return 0
        src = s if rule.get('source') != 'target' else t
        if not src: return 0
        p_name = rule.get('param')
        val = get_status_value(src, p_name)
        bonus = 0
        op = rule.get('operation')
        if op == 'MULTIPLY':
            bonus = int(val * float(rule.get('value_per_param', 0)))
        elif op == 'FIXED_IF_EXISTS':
            if val >= 1: bonus = int(rule.get('value', 0))
        elif op == 'PER_N_BONUS':
            N = int(rule.get('per_N', 1))
            if N > 0: bonus = (val // N) * int(rule.get('value', 0))
        if 'max_bonus' in rule:
            bonus = min(bonus, int(rule['max_bonus']))
        return bonus

    total = 0
    if isinstance(power_bonus_data, list):
        for rule in power_bonus_data: total += _get_bonus(rule, actor, target)
    elif isinstance(power_bonus_data, dict):
        rule = power_bonus_data.get("power_bonus", power_bonus_data)
        total = _get_bonus(rule, actor, target)
    return total