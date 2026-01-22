import re
import json
from extensions import all_skill_data

from manager.game_logic import (
    process_skill_effects, get_status_value, apply_buff, remove_buff
)
from manager.buff_catalog import get_buff_effect
from manager.room_manager import (
    get_room_state, broadcast_log, broadcast_state_update,
    save_specific_room_state, _update_char_stat
)

def calculate_opponent_skill_modifiers(actor_char, target_char, actor_skill_data, target_skill_data, all_skill_data_ref):
    """
    相手スキルを考慮したPRE_MATCHエフェクトを評価し、各種補正値を返す。
    """
    modifiers = {
        "base_power_mod": 0,
        "dice_power_mod": 0,
        "stat_correction_mod": 0,
        "additional_power": 0
    }

    if not actor_skill_data:
        return modifiers

    try:
        rule_json_str = actor_skill_data.get('特記処理', '{}')
        rule_data = json.loads(rule_json_str) if rule_json_str else {}
        effects_array = rule_data.get("effects", [])

        # PRE_MATCHタイミングのエフェクトを評価
        _, logs, changes = process_skill_effects(
            effects_array, "PRE_MATCH", actor_char, target_char, target_skill_data
        )

        for (char, effect_type, name, value) in changes:
            if effect_type == "MODIFY_BASE_POWER":
                # ターゲットへの基礎威力補正
                if char and target_char and char.get('id') == target_char.get('id'):
                    modifiers["base_power_mod"] += value
    except Exception as e:
        print(f"[ERROR] calculate_opponent_skill_modifiers: {e}")

    return modifiers

def extract_cost_from_text(text):
    """
    使用時効果テキストからコスト記述を抽出する
    """
    if not text:
        return "なし"
    match = re.search(r'\[使用時\]:?([^\n]+)', text)
    if match:
        return match.group(1).strip()
    return "なし"

def format_skill_display_from_command(command_str, skill_id, skill_data):
    """
    コマンド文字列に含まれる【ID 名称】を抽出して目立つ色で表示する。
    """
    match = re.search(r'【(.*?)】', command_str)
    text = ""

    if match:
        text = f"【{match.group(1)}】"
    elif skill_id and skill_data:
        name = skill_data.get('デフォルト名称', '不明')
        text = f"【{skill_id}: {name}】"
    else:
        return ""

    return f"<span style='color: #d63384; font-weight: bold;'>{text}</span>"

def verify_skill_cost(char, skill_d):
    """
    スキル使用に必要なコストが足りているかチェックする
    """
    if not skill_d: return True, None

    rule_json_str = skill_d.get('特記処理', '{}')
    try:
        rule_data = json.loads(rule_json_str)
        tags = rule_data.get('tags', skill_d.get('tags', []))
        if "即時発動" in tags:
             # ★ 追加: 宝石の加護スキルの回数制限 (1戦闘に1回)
             if "宝石の加護スキル" in tags:
                 if char.get('used_gem_protect_this_battle', False):
                     return False, "宝石の加護は1戦闘に1回しか使用できません。"

             return True, None

        for cost in rule_data.get("cost", []):
            c_type = cost.get("type")
            c_val = int(cost.get("value", 0))
            if c_val > 0 and c_type:
                curr = get_status_value(char, c_type)
                if curr < c_val:
                    return False, f"{c_type}不足 (必要:{c_val}, 現在:{curr})"
    except:
        pass

    return True, None

def process_on_damage_buffs(room, char, damage_val, username, log_snippets):
    """
    被弾時トリガーバフの処理
    """
    if damage_val <= 0: return

    for b in char.get('special_buffs', []):
        # Resolve full effect data (dynamic or static)
        effect_data = get_buff_effect(b.get('name'))
        if not effect_data: continue

        conf = effect_data.get('on_damage_state')
        # print(f"[DEBUG] Checking buff {b.get('name')}: on_damage_state={conf}")
        if not conf: continue

        s_name = conf.get('stat')
        s_val = conf.get('value', 0)


        if s_name and s_val > 0:
            curr = get_status_value(char, s_name)
            # print(f"[DEBUG] Triggering on_damage_state: {s_name} {curr} -> {curr + s_val}")
            _update_char_stat(room, char, s_name, curr + s_val, username=f"[{b.get('name')}]")
            log_snippets.append(f"[{b.get('name')}→{s_name}+{s_val}]")

def execute_pre_match_effects(room, actor, target, skill_data, target_skill_data=None):
    """
    Match実行時のPRE_MATCH効果適用
    """
    if not skill_data or not actor: return
    try:
        rule_json_str = skill_data.get('特記処理', '{}')
        rule_data = json.loads(rule_json_str)
        effects_array = rule_data.get("effects", [])

        # Room state for context
        state = get_room_state(room)
        context = {"characters": state['characters']} if state else None

        _, logs, changes = process_skill_effects(effects_array, "PRE_MATCH", actor, target, target_skill_data, context=context)

        for (char, type, name, value) in changes:
            if type == "APPLY_STATE":
                current_val = get_status_value(char, name)
                _update_char_stat(room, char, name, current_val + value, username=f"[{skill_data.get('デフォルト名称', 'スキル')}]")
            elif type == "APPLY_BUFF":
                apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
            elif type == "REMOVE_BUFF":
                remove_buff(char, name)
            elif type == "SET_FLAG":
                if 'flags' not in char:
                    char['flags'] = {}
                char['flags'][name] = value
            elif type == "MODIFY_BASE_POWER":
                # 基礎威力ボーナスを一時保存（荊棘処理で参照）
                char['_base_power_bonus'] = char.get('_base_power_bonus', 0) + value
                broadcast_log(room, f"[{char['name']}] 基礎威力 {value:+}", 'state-change')
    except json.JSONDecodeError: pass

def proceed_next_turn(room):
    """
    ターン進行ロジック
    """
    state = get_room_state(room)
    if not state: return
    timeline = state.get('timeline', [])
    current_id = state.get('turn_char_id')

    if not timeline:
        return

    # 現在の手番IDがタイムラインのどこにあるか探す
    current_idx = -1
    if current_id in timeline:
        current_idx = timeline.index(current_id)

    next_id = None

    # 現在位置の「次」から末尾に向かって、未行動のキャラを探す
    from plugins.buffs.confusion import ConfusionBuff

    for i in range(current_idx + 1, len(timeline)):
        cid = timeline[i]
        # キャラデータ取得
        char = next((c for c in state['characters'] if c['id'] == cid), None)

        # 生存していて、かつ「行動済み(hasActed)」でない
        if char and char.get('hp', 0) > 0 and not char.get('hasActed', False):
            # 行動不能チェック
            if ConfusionBuff.is_incapacitated(char):
                print(f"[TurnSkip] Skipping {char['name']} due to incapacitation (Confusion)")
                # ここではスキップして次へ
                continue

            next_id = cid
            break

    if next_id:
        state['turn_char_id'] = next_id
        next_char = next((c for c in state['characters'] if c['id'] == next_id), None)
        char_name = next_char['name'] if next_char else "不明"
        broadcast_log(room, f"手番が {char_name} に移りました。", 'info')
    else:
        state['turn_char_id'] = None
        broadcast_log(room, "全ての行動可能キャラクターが終了しました。ラウンド終了処理を行ってください。", 'info')

    broadcast_state_update(room)
    save_specific_room_state(room)

def process_simple_round_end(state, room):
    """
    ラウンド終了時の共通処理（バフ減少、アイテムリセットなど）
    広域マッチからも呼び出される
    """
    print(f"[DEBUG] ===== process_simple_round_end 開始 =====")

    for char in state.get("characters", []):
        # バフタイマーの処理
        if "special_buffs" in char:
            active_buffs = []
            for buff in char['special_buffs']:
                delay = buff.get("delay", 0)
                lasting = buff.get("lasting", 0)

                if delay > 0:
                    buff["delay"] = delay - 1
                    active_buffs.append(buff)
                elif lasting > 0:
                    buff["lasting"] = lasting - 1
                    if buff["lasting"] > 0:
                        active_buffs.append(buff)
                elif buff.get('is_permanent', False):
                    active_buffs.append(buff)

            char['special_buffs'] = active_buffs

        # アイテム使用制限をリセット
        if 'round_item_usage' in char:
            char['round_item_usage'] = {}

        # スキル使用履歴をリセット
        if 'used_immediate_skills_this_round' in char:
            char['used_immediate_skills_this_round'] = []
        if 'used_gem_protect_this_round' in char:
            char['used_gem_protect_this_round'] = False
        if 'used_skills_this_round' in char:
            char['used_skills_this_round'] = []

    print(f"[DEBUG] ===== process_simple_round_end 完了 =====")
