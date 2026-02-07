# manager/game_logic.py
import sys
import json
import re # Added for regex
from manager.utils import get_status_value, set_status_value, apply_buff, remove_buff, get_buff_stat_mod, get_buff_stat_mod_details, resolve_placeholders, get_effective_origin_id
from manager.buff_catalog import get_buff_effect
from manager.logs import setup_logger

# プラグインシステム (pluginsフォルダはルートにあるのでそのままでOK)
from plugins import EFFECT_REGISTRY

logger = setup_logger(__name__)

def _get_value_for_condition(source_obj, param_name, context=None):
    if not source_obj: return None
    if param_name == "tags": return source_obj.get("tags", [])

    # ★修正: 「速度値」(イニシアチブ)の参照ロジック
    # 戦闘中(contextにtimelineがある)かつ、targetがtimelineに含まれている場合、
    # そのキャラクターの全手番の中で最も高い速度値(イニシアチブ)を返す。
    # ユーザー指摘:「速度」はパラメータ、「速度値」はロール結果
    if param_name == "速度値" and context and 'timeline' in context:
        timeline = context['timeline']
        char_id = source_obj.get('id')

        # 該当キャラの全エントリを抽出 (行動済みかどうかに関わらず)
        my_entries = [t for t in timeline if t.get('char_id') == char_id]

        if my_entries:
            # 全エントリの中で最大の速度(speed)を返す
            max_speed = max(t.get('speed', 0) for t in my_entries)
            return max_speed
        else:
            # タイムラインに存在しない場合 (戦闘開始前など)
            # ユーザー要望に基づき 0 を返す (常に行動済み/参加不能扱い)
            return 0

    return get_status_value(source_obj, param_name)

def check_condition(condition_obj, actor, target, target_skill_data=None, actor_skill_data=None, context=None):
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

    # Contextを渡す
    current_value = _get_value_for_condition(source_obj, param_name, context=context)
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

# ★修正: 汎用ボーナス計算ロジック（内部用）
def _calculate_bonus_from_rules(rules, actor, target, actor_skill_data=None, context=None):
    total = 0
    for rule in rules:
        # 条件チェック
        condition = rule.get('condition')
        if condition:
            if not check_condition(condition, actor, target, actor_skill_data=actor_skill_data, context=context):
                continue

        # 加算値計算
        bonus = 0
        operation = rule.get('operation', 'FIXED')

        if operation == 'FIXED':
            bonus = int(rule.get('value', 0))

        elif operation in ['MULTIPLY', 'FIXED_IF_EXISTS', 'PER_N_BONUS']:
            src_type = rule.get('source', 'self')
            src_obj = target if src_type == 'target' else actor
            p_name = rule.get('param')
            # ここでも _get_value_for_condition を使うべきだが、
            # ボーナス値の基準にするパラメータ(param)は通常ステータス値(HP, MP, 筋力など)であり、
            # イニシアチブ値(速度)を基準に倍率を掛けることは稀。
            # しかし一貫性を保つため _get_value_for_condition を使うのが良いが、
            # 既存実装は get_status_value を直接呼んでいる。
            # ここでは安全のため既存通り get_status_value にしておく (イニシアチブ値で倍率計算するケースがあれば修正)
            val = get_status_value(src_obj, p_name)

            if operation == 'MULTIPLY':
                bonus = int(val * float(rule.get('value_per_param', 0)))
            elif operation == 'FIXED_IF_EXISTS':
                threshold = int(rule.get('threshold', 1))
                if val >= threshold:
                    bonus = int(rule.get('value', 0))
            elif operation == 'PER_N_BONUS':
                N = int(rule.get('per_N', 1))
                if N > 0:
                    bonus = (val // N) * int(rule.get('value', 0))

        if 'max_bonus' in rule:
            bonus = min(bonus, int(rule['max_bonus']))
        if 'min_bonus' in rule:
            bonus = max(bonus, int(rule['min_bonus']))

        total += bonus
    return total


# ★修正: バフによる威力ボーナス計算
def calculate_buff_power_bonus(actor, target, actor_skill_data, context=None):
    total_buff_bonus = 0
    if not actor or 'special_buffs' not in actor:
        return 0

    for buff in actor['special_buffs']:
        buff_name = buff.get('name')
        # ★ get_buff_effect を使用
        effect_data = get_buff_effect(buff_name)
        if not effect_data:
             if 'data' in buff: effect_data = buff['data']
             else: continue

        # ★追加: ディレイ中のバフは無効
        if buff.get('delay', 0) > 0:
            continue

        power_bonuses = effect_data.get('power_bonus', [])
        total_buff_bonus += _calculate_bonus_from_rules(power_bonuses, actor, target, actor_skill_data, context=context)

    return total_buff_bonus

def calculate_state_apply_bonus(actor, target, stat_name, context=None):
    total_bonus = 0
    buffs_to_remove = []  # ★削除リスト

    if not actor or 'special_buffs' not in actor:
        return 0, [] # ★

    for buff in actor['special_buffs']:
        buff_name = buff.get('name')
        effect_data = get_buff_effect(buff_name)
        if not effect_data:
             if 'data' in buff: effect_data = buff['data']
             else: continue

        # ★追加: ディレイ中のバフは無効
        if buff.get('delay', 0) > 0:
            continue

        state_bonuses = effect_data.get('state_bonus', [])
        matching_rules = [r for r in state_bonuses if r.get('stat') == stat_name]

        # ボーナス計算
        bonus = _calculate_bonus_from_rules(matching_rules, actor, target, None, context=context)

        if bonus > 0:
            total_bonus += bonus
            # ★ルールの中に "consume": True があれば削除リストに追加
            for rule in matching_rules:
                if rule.get('consume'):
                    buffs_to_remove.append(buff_name)
                    break # 1つのバフ定義内で複数ルールがあっても1回削除登録すれば十分

    return total_bonus, buffs_to_remove

def execute_custom_effect(effect, actor, target):
    """
    プラグイン化されたカスタム効果を実行する
    """
    effect_name = effect.get("value")
    handler = EFFECT_REGISTRY.get(effect_name)

    if not handler:
        logger.debug(f"Unknown CUSTOM_EFFECT '{effect_name}'")
        return [], []

    try:
        # コンテキストとしてレジストリを渡す（亀裂崩壊などで再帰的に使うため）
        context = {
            "registry": EFFECT_REGISTRY
        }
        return handler.apply(actor, target, effect, context)
    except Exception as e:
        logger.error(f"Plugin Error ({effect_name}): {e}")
        return [], []

def process_skill_effects(effects_array, timing_to_check, actor, target, target_skill_data=None, context=None, base_damage=0):
    total_bonus_damage = 0
    log_snippets = []
    changes_to_apply = []

    if not actor or not effects_array:
        return 0, [], []

    # Helper for random selection
    import random
    def select_random_targets(actor_obj, effect_def, all_chars):
        # Default settings
        tgt_type = effect_def.get("target_filter", "ENEMY") # ENEMY, ALLY, ALL
        count = int(effect_def.get("target_count", 1))
        include_self = effect_def.get("include_self", False)

        candidates = []
        actor_type = actor_obj.get("type", "ally")

        for c in all_chars:
            # Check placement (must have x, y coordinates to be considered "placed")
            if c.get("x") is None or c.get("y") is None:
                continue

            # Status Check
            if c.get("hp", 0) <= 0: continue
            if c.get("is_escaped"): continue

            # Faction Check
            c_type = c.get("type", "enemy")
            is_ally = (c_type == actor_type)

            if tgt_type == "ENEMY" and is_ally: continue
            if tgt_type == "ALLY" and not is_ally: continue
            # ALL accepts both (except self if excluded)

            # Self Check
            if c.get("id") == actor_obj.get("id") and not include_self:
                continue

            candidates.append(c)

        if not candidates:
            return []

        # Select distinct
        if count >= len(candidates):
            return candidates
        return random.sample(candidates, count)

    import copy # 追加

    # シミュレーション用キャッシュ (ID -> char_obj_copy)
    simulated_chars = {}

    def get_simulated_char(real_char):
        if not real_char: return None
        cid = real_char.get('id')
        if cid not in simulated_chars:
            simulated_chars[cid] = copy.deepcopy(real_char)
        return simulated_chars[cid]

    for effect in effects_array:
        if effect.get("timing") != timing_to_check: continue

        effect_type = effect.get("type")
        targets_list = []

        # Target Resolution
        t_select = effect.get("target_select") # NORMAL (default), RANDOM

        if t_select == "RANDOM":
            if context and "characters" in context:
                targets_list = select_random_targets(actor, effect, context["characters"])
                if not targets_list:
                    log_snippets.append(f"(対象不在)")
            else:
                 pass
        else:
            # Standard targeting
            t_str = effect.get("target")
            if not t_str: t_str = "target" # Default to target if not specified

            if t_str == "self": targets_list = [actor]
            elif t_str == "target": targets_list = [target] if target else []
            # ★ 追加: 全体対象サポート
            elif t_str == "ALL_ENEMIES" and context and "characters" in context:
                actor_type = actor.get("type", "ally")
                target_type = "enemy" if actor_type == "ally" else "ally"
                targets_list = [c for c in context["characters"] if c.get("type") == target_type and c.get('hp', 0) > 0]
            elif t_str == "ALL_ALLIES" and context and "characters" in context:
                actor_type = actor.get("type", "ally")
                targets_list = [c for c in context["characters"] if c.get("type") == actor_type and c.get('hp', 0) > 0]
            elif t_str == "ALL" and context and "characters" in context:
                 targets_list = [c for c in context["characters"] if c.get('hp', 0) > 0]
            # ★新機能: NEXT_ALLY
            elif t_str == "NEXT_ALLY" and context and "characters" in context and context.get("room"):
                from manager.room_manager import get_room_state
                room_name = context.get("room")
                if room_name:
                    state = get_room_state(room_name)
                    timeline = state.get('timeline', [])

                    if timeline and actor:
                        my_id = actor.get('id')
                        my_type = actor.get('type', 'ally')
                        start_idx = -1
                        try:
                            start_idx = timeline.index(my_id)
                        except ValueError:
                            pass
                        target_id = None
                        search_indices = list(range(start_idx + 1, len(timeline))) + list(range(0, start_idx))
                        for idx in search_indices:
                            tid = timeline[idx]
                            t_char = next((c for c in state['characters'] if c['id'] == tid), None)
                            if t_char and t_char.get('type') == my_type and t_char.get('hp', 0) > 0:
                                target_id = tid
                                break
                        if target_id:
                            found = next((c for c in state['characters'] if c['id'] == target_id), None)
                            if found: targets_list = [found]

        if not targets_list: continue

        for target_obj in targets_list:
            # ★重要: 副作用を防ぐため、判定や内部適用はシミュレーション用オブジェクトで行う
            sim_actor = get_simulated_char(actor)
            sim_target = get_simulated_char(target_obj)

            # 条件判定 (シミュレーション状態に基づく)
            if not check_condition(effect.get("condition"), sim_actor, sim_target, target_skill_data, context=context):
                continue

            if effect_type == "APPLY_STATE":
                # ★後方互換: "state_name"と"name"の両方に対応
                stat_name = effect.get("state_name") or effect.get("name")
                value = int(effect.get("value", 0))

                # ★亀裂の1ラウンド1回付与制限チェック
                if stat_name == "亀裂" and value > 0 and sim_target:
                    if 'flags' not in sim_target:
                        sim_target['flags'] = {}
                    if sim_target['flags'].get('fissure_received_this_round', False):
                        log_snippets.append(f"[亀裂付与失敗: 今ラウンド既に付与済み]")
                        continue  # この効果をスキップし、次の効果へ

                # ★修正: ボーナス計算と消費(削除)処理の適用
                # (状態付与値が正の数で、かつ実行者が存在する場合のみボーナスをチェック)
                if value > 0 and sim_actor:
                    # ボーナス値と、削除すべきバフリストを受け取る (シミュレーション状態を使用)
                    bonus, buffs_to_remove = calculate_state_apply_bonus(sim_actor, sim_target, stat_name, context=context)

                    if bonus > 0:
                        value += bonus
                        # 必要であればログにボーナス分を表示できますが、ここでは最終値のみ適用します

                    # ★消費型バフの削除アクションを追加
                    for b_name in buffs_to_remove:
                        # 自分(actor)のバフを削除する
                        # 変更リストには実体を登録、シミュレーションには即時適用
                        remove_buff(sim_actor, b_name)
                        changes_to_apply.append((actor, "REMOVE_BUFF", b_name, 0)) # 実体に対する変更予約
                        log_snippets.append(f"({b_name} 消費)")

                if stat_name and value != 0:
                    # ★即座に状態を更新（シミュレーション用オブジェクトに対してのみ）
                    current_val = get_status_value(sim_target, stat_name)
                    set_status_value(sim_target, stat_name, current_val + value)

                    # 変更ログとして記録（後続の処理で実体に適用される）
                    changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, value)) # 実体に対する変更予約

                    # ★亀裂の場合はフラグを立てる（付与成功時）
                    if stat_name == "亀裂" and value > 0:
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        sim_target['flags']['fissure_received_this_round'] = True


            elif effect_type == "APPLY_STATE_PER_N":
                source_type = effect.get("source", "self")
                source_obj = sim_actor if source_type == "self" else sim_target # シミュレーションを使用
                source_param = effect.get("source_param")

                if not source_obj or not source_param:
                    continue

                # 基準パラメータの値を取得
                source_param_value = get_status_value(source_obj, source_param)

                # N毎に計算
                per_N = int(effect.get("per_N", 1))
                value_per = int(effect.get("value", 1))
                calculated_value = (source_param_value // per_N) * value_per if per_N > 0 else 0

                # 最大値制限
                if "max_value" in effect:
                    calculated_value = min(calculated_value, int(effect["max_value"]))

                # 付与実行
                stat_name = effect.get("state_name")
                if stat_name and calculated_value > 0:
                    # 亀裂の1ラウンド1回付与制限チェック
                    if stat_name == "亀裂" and sim_target:
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        if sim_target['flags'].get('fissure_received_this_round', False):
                            log_snippets.append(f"[亀裂付与失敗: 今ラウンド既に付与済み]")
                            continue

                    # ★即座に状態を更新 (シミュレーション)
                    current_val = get_status_value(sim_target, stat_name)
                    set_status_value(sim_target, stat_name, current_val + calculated_value)

                    # 変更ログとして記録 (実体)
                    changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, calculated_value))
                    log_snippets.append(f"[{stat_name}+{calculated_value} ({source_param}{source_param_value}から)]")

                    # 亀裂の場合はフラグを立てる
                    if stat_name == "亀裂":
                        if 'flags' not in sim_target:
                            sim_target['flags'] = {}
                        sim_target['flags']['fissure_received_this_round'] = True


            elif effect_type == "MULTIPLY_STATE":
                stat_name = effect.get("state_name")
                multiplier = float(effect.get("value", 1.0))

                if stat_name and sim_target:
                    current_val = get_status_value(sim_target, stat_name)
                    new_val = int(current_val * multiplier + 0.5)
                    diff = new_val - current_val

                    if diff != 0:
                        # ★即座に状態を更新 (シミュレーション)
                        set_status_value(sim_target, stat_name, new_val)

                        # 変更ログとして記録 (実体)
                        changes_to_apply.append((target_obj, "APPLY_STATE", stat_name, diff))
                        log_snippets.append(f"[{stat_name} x{multiplier} ({current_val}→{new_val})]")


            elif effect_type == "APPLY_BUFF":
                buff_name = effect.get("buff_name")
                buff_id = effect.get("buff_id")

                # ★修正: buff_idが指定されている場合、buff_catalogから名前を取得
                if not buff_name and buff_id:
                    from manager.buff_catalog import get_buff_by_id
                    buff_data = get_buff_by_id(buff_id)
                    if buff_data:
                        buff_name = buff_data.get("name")
                        logger.debug(f"Resolved buff_id '{buff_id}' to buff_name '{buff_name}'")
                    else:
                        logger.warning(f"buff_id '{buff_id}' not found in catalog")

                if buff_name:
                    # ★修正: buff_idも一緒にdataに含める（プラグイン判定用）
                    # さらに description, flavor もカタログから引き継ぐ
                    effect_data = effect.get("data")
                    if effect_data is None:
                        effect_data = {}
                    else:
                        # 呼び出し元の副作用を防ぐためコピー
                        effect_data = effect_data.copy()

                    if buff_id:
                        effect_data["buff_id"] = buff_id

                        # カタログから詳細情報を取得してマージ
                        if 'buff_data' in locals() and buff_data:
                            if "description" not in effect_data:
                                effect_data["description"] = buff_data.get("description", "")
                            if "flavor" not in effect_data:
                                effect_data["flavor"] = buff_data.get("flavor", "")

                            # ★追加: stat_mod の継承 (Phase 10 後半)
                            # カタログ定義の effect: { type: "stat_mod", stat: "基礎威力", value: 1 }
                            # を、システムが解釈できる stat_mods: { "基礎威力": 1 } に変換する
                            catalog_effect = buff_data.get("effect", {})
                            if catalog_effect.get("type") == "stat_mod":
                                stat_name = catalog_effect.get("stat")
                                mod_value = catalog_effect.get("value")

                                if stat_name and mod_value is not None:
                                    if "stat_mods" not in effect_data:
                                        effect_data["stat_mods"] = {}
                                    effect_data["stat_mods"][stat_name] = mod_value
                                    # print(f"[APPLY_BUFF] Converted stat_mod for {buff_name}: {stat_name}={mod_value}")

                    # ★追加: 動的パターンや静的定義から得られる効果データをマージ
                    # (buff_idがなく、buff_nameのみの場合や、動的生成されたプロパティを取り込む)
                    from manager.buff_catalog import get_buff_effect
                    catalog_effect_data = get_buff_effect(buff_name)
                    if isinstance(catalog_effect_data, dict):
                        # 既存のeffect_dataにマージ
                        for k, v in catalog_effect_data.items():
                            if k not in effect_data:
                                effect_data[k] = v
                            elif k == "stat_mods" and isinstance(v, dict):
                                # stat_modsはマージ
                                if "stat_mods" not in effect_data:
                                    effect_data["stat_mods"] = {}
                                for sk, sv in v.items():
                                    if sk not in effect_data["stat_mods"]:
                                        effect_data["stat_mods"][sk] = sv

                    # ★追加: flavorテキストの継承
                    if "flavor" in effect:
                        effect_data["flavor"] = effect["flavor"]

                    changes_to_apply.append((target_obj, "APPLY_BUFF", buff_name, {"lasting": int(effect.get("lasting", 1)), "delay": int(effect.get("delay", 0)), "data": effect_data}))
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
                # ★修正: target="self" の場合は自分を対象にする
                target_obj = actor if effect.get("target") == "self" else target
                custom_changes, custom_logs = execute_custom_effect(effect, actor, target_obj)
                changes_to_apply.extend(custom_changes)
                log_snippets.extend(custom_logs)
            elif effect_type == "FORCE_UNOPPOSED":
                changes_to_apply.append((target_obj, "FORCE_UNOPPOSED", "None", 0))
            elif effect_type == "MODIFY_BASE_POWER":
                mod_value = int(effect.get("value", 0))
                if mod_value != 0:
                    changes_to_apply.append((target_obj, "MODIFY_BASE_POWER", None, mod_value))
                    log_snippets.append(f"[基礎威力 {mod_value:+}]")
            elif effect_type == "DRAIN_HP":
                 # ★追加: ダメージ吸収 (base_damageに基づく)
                 if base_damage > 0:
                     rate = float(effect.get("value", 0))

                     # ★ 追加: 対象(攻撃相手)のHPを上限にする
                     calc_base = base_damage
                     if target: # 攻撃対象が存在する場合
                         target_current_hp = get_status_value(target, 'HP')
                         if target_current_hp < calc_base:
                             calc_base = target_current_hp

                     heal_val = int(calc_base * rate)
                     if heal_val > 0:
                         # 即座に回復 (シミュレーション)
                         current_hp = get_status_value(sim_actor, 'HP')
                         set_status_value(sim_actor, 'HP', current_hp + heal_val)

                         # 変更予約 (実体)
                         changes_to_apply.append((actor, "APPLY_STATE", "HP", heal_val))
                         log_snippets.append(f"[吸収 {heal_val}]")


    return total_bonus_damage, log_snippets, changes_to_apply

def calculate_power_bonus(actor, target, power_bonus_data, context=None):
    # (この関数は変更なし、ロジックそのまま)
    def _get_bonus(rule, s, t):
        if not rule: return 0
        src = s if rule.get('source') != 'target' else t
        if not src: return 0
        p_name = rule.get('param')
        val = _get_value_for_condition(src, p_name, context=context) # ★修正: ここも context対応
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

def calculate_skill_preview(actor_char, target_char, skill_data, rule_data=None, custom_skill_name=None, senritsu_max_apply=0, external_base_power_mod=0, context=None):
    """
    スキルの威力、コマンド、補正情報のプレビューデータを計算する。
    Duel/Wide Matchの両方で共通して使用する。
            "correction_details": list,
            "senritsu_dice_reduction": int,
            "skill_details": dict,
            "power_breakdown": dict
        }
    """
    # 1. 基礎情報の取得
    base_power = int(skill_data.get('基礎威力', 0))

    # バフからの基礎威力補正
    base_power_buff_mod = get_buff_stat_mod(actor_char, '基礎威力')
    base_power += base_power_buff_mod

    # 外部からの基礎威力補正 (Wide MatchのAttackerからのデバフなど)
    base_power += external_base_power_mod

    skill_details = {
        'base_power': int(skill_data.get('基礎威力', 0)),
        'base_power_buff_mod': base_power_buff_mod,
        'external_mod': external_base_power_mod,
        '分類': skill_data.get('分類', skill_data.get('タイミング', '')),
        '距離': skill_data.get('距離', skill_data.get('射程', '')),
        '属性': skill_data.get('属性', ''),
        '使用時効果': skill_data.get('使用時効果', skill_data.get('コスト', '')),
        '発動時効果': skill_data.get('発動時効果', skill_data.get('効果', '')),
        '特記': skill_data.get('特記', ''),
    }

    # 2. 威力ボーナスの計算 (ルールおよびバフ)
    bonus_power = 0

    # ルールデータの自動パース (引数で渡されていない場合)
    if not rule_data and skill_data:
        try:
            rule_json_str = skill_data.get('特記処理', '{}')
            rule_data = json.loads(rule_json_str) if rule_json_str else {}
        except Exception:
            rule_data = {}

    # ルールベース (スキル特有の条件)
    dice_bonus_power = 0
    if rule_data:
        rules = rule_data.get('power_bonus', [])

        # ★追加: ダイス威力補正(apply_to='dice')と通常威力補正を分離
        base_rules = [r for r in rules if r.get('apply_to') != 'dice']
        dice_rules = [r for r in rules if r.get('apply_to') == 'dice']

        # 通常ボーナス
        bonus_from_rules = _calculate_bonus_from_rules(base_rules, actor_char, target_char, actor_skill_data=skill_data, context=context)
        bonus_power += bonus_from_rules

        # ★追加: ダイスボーナス
        dice_bonus_from_rules = _calculate_bonus_from_rules(dice_rules, actor_char, target_char, actor_skill_data=skill_data, context=context)
        dice_bonus_power += dice_bonus_from_rules

        # 戦慄の上限をルールから取得 (指定がなければ0)
        if senritsu_max_apply == 0:
            senritsu_max_apply = rule_data.get('senritsu_max', 0)

    # 戦慄の自動判定 (分類が物理/魔法を含むなら上限99として扱う)
    if senritsu_max_apply == 0:
        category = skill_data.get('分類', '')
        if category and ('物理' in category or '魔法' in category):
            senritsu_max_apply = 3 # ★修正: 最大-3まで

    # ★ 追加: ヴァルヴァイレ (ID: 13) 恩恵: 被対象時、相手の威力-1
    valvile_correction = 0
    if target_char:
        from manager.utils import get_effective_origin_id
        if get_effective_origin_id(target_char) == 13:
            valvile_correction = -1
            bonus_power += valvile_correction

    skill_details['senritsu_max_apply'] = senritsu_max_apply

    # バフベース (攻撃威力バフなど)
    buff_bonus = calculate_buff_power_bonus(actor_char, target_char, skill_data, context=context)
    bonus_power += buff_bonus

    # 綿津見 (ID: 9) ボーナス: 斬撃威力+1 (Preview用)
    try:
        from manager.utils import get_effective_origin_id
        if get_effective_origin_id(actor_char) == 9 and skill_data.get('属性') == '斬撃':
            bonus_power += 1
    except ImportError: pass

    skill_details['additional_power'] = bonus_power

    # 3. ダイス部分の解析
    palette = skill_data.get('チャットパレット', '')
    cmd_part = re.sub(r'【.*?】', '', palette).strip()

    # ★修正: 先頭の数値を基礎威力として除外し、残りをダイス部分とする
    # (22-1d6+... のようなケースで split('+') だと -1d6 が消えるため)
    match_base = re.match(r'^(\d+)(.*)$', cmd_part)
    if match_base:
        dice_part = match_base.group(2).strip()
        if not dice_part:
             # コマンドにダイス部分がない場合、JSONの定義を使う
             dice_part = skill_data.get('ダイス威力', '')
    else:
        # 数値で始まらない、または形式不明
        if '+' in cmd_part:
            dice_part = cmd_part.split('+', 1)[1]
        else:
            dice_part = skill_data.get('ダイス威力', '2d6')

    # 変数ダイスの解決
    resolved_dice = resolve_placeholders(dice_part, actor_char)

    # 4. 補正値のカテゴリ別集計 (Aggregated Correction Details)
    correction_details = []

    # (1) 基礎威力 (Base Power)
    total_base_mod = base_power_buff_mod + external_base_power_mod
    if total_base_mod != 0:
        correction_details.append({'source': '基礎威力', 'value': total_base_mod})

    # (2) 物理補正 (Physical Correction)
    phys_mod = get_status_value(actor_char, '物理補正')
    if '{物理補正}' in dice_part and phys_mod != 0:
        # 元の値 (initial_data) を取得して変動分(delta)のみを表示する
        base_phys = 0
        if 'initial_data' in actor_char and '物理補正' in actor_char['initial_data']:
             # initial_data は str だったり int だったりする可能性があるので安全にキャスト
             try:
                 base_phys = int(actor_char['initial_data']['物理補正'])
             except:
                 base_phys = 0

        delta_phys = phys_mod - base_phys
        if delta_phys != 0:
            correction_details.append({'source': '物理補正', 'value': delta_phys})

    # (3) 魔法補正 (Magical Correction)
    mag_mod = get_status_value(actor_char, '魔法補正')
    if '{魔法補正}' in dice_part and mag_mod != 0:
        # 元の値 (initial_data) を取得して変動分(delta)のみを表示する
        base_mag = 0
        if 'initial_data' in actor_char and '魔法補正' in actor_char['initial_data']:
             try:
                 base_mag = int(actor_char['initial_data']['魔法補正'])
             except:
                 base_mag = 0

        delta_mag = mag_mod - base_mag
        if delta_mag != 0:
            correction_details.append({'source': '魔法補正', 'value': delta_mag})

    # (4) ダイス威力 (Dice Power)
    dice_pow_mod = get_status_value(actor_char, 'ダイス威力')
    if '{ダイス威力}' in dice_part and dice_pow_mod != 0:
        # 元の値 (initial_data) を取得して変動分(delta)のみを表示する
        base_dice_pow = 0
        if 'initial_data' in actor_char and 'ダイス威力' in actor_char['initial_data']:
             try:
                 base_dice_pow = int(actor_char['initial_data']['ダイス威力'])
             except:
                 base_dice_pow = 0

        delta_dice_pow = dice_pow_mod - base_dice_pow
        if delta_dice_pow != 0:
            correction_details.append({'source': 'ダイス威力', 'value': delta_dice_pow})

    # (5) 威力補正 (Power Correction) - ヴァルヴァイレを除く
    # bonus_power にはヴァルヴァイレ補正が含まれているため、表示用に除外して計算
    display_bonus_power = bonus_power - valvile_correction
    if display_bonus_power != 0:
        correction_details.append({'source': '威力補正', 'value': display_bonus_power})

    # (6) ヴァルヴァイレ補正
    if valvile_correction != 0:
        correction_details.append({'source': 'ヴァルヴァイレ恩恵', 'value': valvile_correction})


    # 4. バフ・ダイスボーナスの適用 (Dice Face Modification)
    # dice_bonus_power (apply_to='dice') を面数に加算する
    # 例: -1d6 + (-2) -> -1d4 (faces decreased by 2)
    processed_dice = resolved_dice

    if dice_bonus_power != 0:
        def modify_dice_faces(m):
            sign = m.group(1) or ''
            num = m.group(2)
            faces = int(m.group(3))

            # 面数を変更 (最低1)
            # dice_bonus_power が -1 なら faces - 1
            new_faces = max(1, faces + dice_bonus_power)
            return f"{sign}{num}d{new_faces}"

        processed_dice = re.sub(r'([+-]?)(\d+)d(\d+)', modify_dice_faces, processed_dice, count=1)

        # ★追加: 内訳表示用にダイス威力補正を追加
        correction_details.append({'source': 'ダイス威力', 'value': dice_bonus_power})


    # 5. 戦慄(Senritsu)の適用
    senritsu_dice_reduction = 0

    if senritsu_max_apply > 0:
        current_senritsu = get_status_value(actor_char, '戦慄')
        apply_val = min(current_senritsu, senritsu_max_apply) if current_senritsu > 0 else 0

        dice_m = re.search(r'([+-]?)(\d+)d(\d+)', skill_data.get('ダイス威力', ''))
        if dice_m and apply_val > 0:
            orig_faces = int(dice_m.group(3))
            if orig_faces > 1:
                max_red = orig_faces - 1
                senritsu_dice_reduction = min(apply_val, max_red)

                # ダイス面数を減少させる置換関数
                def reduce_dice_faces(m):
                    sign = m.group(1) or ''
                    num = m.group(2)
                    faces = int(m.group(3))

                    new_faces = max(1, faces - senritsu_dice_reduction)
                    return f"{sign}{num}d{new_faces}"

                processed_dice = re.sub(r'([+-]?)(\d+)d(\d+)', reduce_dice_faces, processed_dice, count=1)
                skill_details['senritsu_dice_reduction'] = senritsu_dice_reduction

    # 5. 最終コマンド構築
    # ボーナスはここに追加すべきか、resolved_diceの一部として計算済みか？
    # 従来の logic: base + dice + bonus
    # resolved_dice は "2d6+5" (補正込み) のようになっている

    # ボーナス値をコマンド末尾に追加
    final_dice_part = processed_dice



    if bonus_power != 0:
        final_dice_part += f"{'+' if bonus_power > 0 else ''}{bonus_power}"

    # ★修正: base_power補正時の符号重複回避
    # final_dice_part が + または - で始まる場合はそのまま結合、そうでなければ + を挟む
    if final_dice_part.startswith('+') or final_dice_part.startswith('-'):
        final_command = f"{base_power}{final_dice_part}"
    else:
        final_command = f"{base_power}+{final_dice_part}"

    # 6. ダメージレンジの計算

    # final_command (例: "22-1d5+1d5") を解析して最小・最大を計算
    tokens = re.split(r'([+-])', final_command)

    range_min = 0
    range_max = 0
    current_sign = 1

    for token in tokens:
        token = token.strip()
        if not token:
            continue

        if token == '+':
            current_sign = 1
        elif token == '-':
            current_sign = -1
        else:
            # 数値またはダイス
            dice_match = re.match(r'^(\d+)d(\d+)$', token)
            if dice_match:
                num = int(dice_match.group(1))
                sides = int(dice_match.group(2))

                # ダイスの最小・最大
                d_min = num
                d_max = num * sides

                if current_sign == 1:
                    range_min += d_min
                    range_max += d_max
                else:
                    # マイナスの場合: 最小値には最大値を引き(最も減る)、最大値には最小値を引く(最も減らない)
                    range_min -= d_max
                    range_max -= d_min
            else:
                # 定数
                try:
                    val = int(token)
                    range_min += current_sign * val
                    range_max += current_sign * val
                except ValueError:
                    pass

    skill_details['range_min'] = range_min
    skill_details['range_max'] = range_max

    return {
        "final_command": final_command,
        "min_damage": range_min,
        "max_damage": range_max,
        "damage_range_text": f"{range_min} ~ {range_max}",
        "correction_details": correction_details,
        "senritsu_dice_reduction": senritsu_dice_reduction,
        "skill_details": skill_details,
        "power_breakdown": {
            "base_power_mod": base_power_buff_mod + external_base_power_mod,
            "additional_power": bonus_power,
             # Add other fields if needed by client
        }
    }


def calculate_damage_multiplier(character):
    """
    キャラクターのバフからダメージ倍率を計算する
    (混乱 + damage_multiplier)

    Args:
        character (dict): キャラクターデータ

    Returns:
        tuple: (final_multiplier, log_list)
            - final_multiplier (float): 最終的な倍率
            - log_list (list): 適用された効果の名前リスト
    """
    d_mult = 1.0
    logs = []

    for b in character.get('special_buffs', []):
        # 混乱: 1.5倍
        if b.get('name') == "混乱":
            d_mult *= 1.5
            logs.append("混乱")
        # dynamic pattern or plugin multiplier
        elif 'damage_multiplier' in b:
            try:
                v = float(b['damage_multiplier'])
                if v != 1.0:
                    d_mult *= v
                    logs.append(b['name'])
            except:
                pass

    return d_mult, logs

def process_on_death(room, char, username):
    """
    死亡時イベント(on_death)を処理する
    """
    if not char: return
    logs = []

    # special_buffs (またはパッシブ) に on_death があれば実行
    # パッシブは常時バフとして special_buffs に展開されている前提（ローダーの仕組み上そうなっている）

    for buff in char.get('special_buffs', []):
        effect_data = get_buff_effect(buff.get('name'))
        if not effect_data:
            if 'data' in buff: effect_data = buff['data']
            else: continue

        on_death_effects = effect_data.get('on_death', [])
        if on_death_effects:
            # 実行
            # 死んだ本人を actor として効果処理
            # ターゲットは効果定義内の target (ALL_ENEMIESなど) に依存

            # コンテキスト作成
            from manager.room_manager import get_room_state, broadcast_log, _update_char_stat
            state = get_room_state(room)
            context = {"characters": state['characters'], "room": room}

            _, l, changes = process_skill_effects(on_death_effects, "IMMEDIATE", char, None, None, context=context)

            if l:
                broadcast_log(room, f"【{char['name']} 死亡時効果】" + " ".join(l), 'state-change')

            for (c, type, name, value) in changes:
                if type == "APPLY_STATE":
                    current = get_status_value(c, name)
                    _update_char_stat(room, c, name, current + value, username=f"[{char['name']}:遺言]")
                elif type == "APPLY_BUFF":
                    apply_buff(c, name, value["lasting"], value["delay"], data=value.get("data"))
                    broadcast_log(room, f"[{name}] が {c['name']} に付与されました。", 'state-change')

    # 通常ログは呼び出し元で処理済み

def process_battle_start(room, char):
    """
    戦闘開始時(または参加時)イベント(battle_start_effect)を処理する
    初期FP付与などに使用
    """
    if not char: return

    # パッシブ/バフチェック
    executed = False

    for buff in char.get('special_buffs', []):
        buff_name = buff.get('name')
        effect_data = get_buff_effect(buff_name)

        # effect_data自体がない場合や、battle_start_effectがない場合はスキップ
        if not effect_data:
             # ★追加: 動的バフ（輝化スキルなど）で、dataプロパティに直接定義が入っている場合
             if 'data' in buff:
                 effect_data = buff['data']
             else:
                 continue

        start_effects = effect_data.get('battle_start_effect', [])
        if start_effects:
            # 実行 (タイミングチェックは不要だが、process_skill_effectsの仕様上タイミング指定が必要ならIMMEDIATE等で代用)
            # ここではタイミングフィルタを無視するか、データ側で指定させる
            # 既存関数再利用のため、タイミングは "BATTLE_START" と仮定するが、
            # process_skill_effectsはタイミング一致を見るので、データ側にも timing: BATTLE_START が必要。
            # しかし手入力の手間を省くため、ここでは強制的に通すか、process_skill_effectsを使わずに処理する。

            # 簡易実装: ここで処理ループを回す (process_skill_effectsは条件等が複雑なので再利用したい)
            # データ側に timing: BATTLE_START を付与して渡す

            # deepcopyしてtiming注入
            import copy
            effects_to_run = copy.deepcopy(start_effects)
            for eff in effects_to_run:
                eff['timing'] = 'BATTLE_START'
                if not eff.get('target'):
                    eff['target'] = 'self'

            from manager.room_manager import get_room_state, broadcast_log, _update_char_stat
            state = get_room_state(room)
            context = {"characters": state['characters'], "room": room}

            _, l, changes = process_skill_effects(effects_to_run, "BATTLE_START", char, None, None, context=context)

            if l:
                broadcast_log(room, f"【{char['name']} 開始時効果】" + " ".join(l), 'state-change')

            for (c, type, name, value) in changes:
                if type == "APPLY_STATE":
                    current = get_status_value(c, name)
                    _update_char_stat(room, c, name, current + value, username=f"[{buff_name}]")
                elif type == "APPLY_BUFF":
                     apply_buff(c, name, value["lasting"], value["delay"], data=value.get("data"))
                     broadcast_log(room, f"[{name}] が {c['name']} に付与されました。", 'state-change')

            executed = True

    if executed:
        from manager.room_manager import save_specific_room_state, broadcast_state_update
        save_specific_room_state(room)
        broadcast_state_update(room)
