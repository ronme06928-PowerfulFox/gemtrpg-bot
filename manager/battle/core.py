import re
import json
from extensions import all_skill_data

from manager.game_logic import (
    process_skill_effects, apply_buff, remove_buff, get_status_value
)
from manager.utils import get_effective_origin_id
from models import Room
from manager.buff_catalog import get_buff_effect
from manager.room_manager import (
    get_room_state, broadcast_log, broadcast_state_update,
    save_specific_room_state, _update_char_stat
)
from manager.logs import setup_logger

logger = setup_logger(__name__)

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
        logger.error(f"calculate_opponent_skill_modifiers: {e}")

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
    total_applied_damage = 0
    if damage_val <= 0: return 0

    for b in char.get('special_buffs', []):
        # ★追加: 今回のアクションで適用されたばかりのバフは除外
        if b.get('newly_applied'):
            continue
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
            if s_name == 'HP':
                total_applied_damage += s_val

    return total_applied_damage

def process_on_hit_buffs(actor, target, damage_val, log_snippets):
    """
    攻撃ヒット時トリガーバフの処理 (例: 爆縮)
    Returns: extra_damage (int)
    """
    from plugins.buffs.registry import buff_registry

    total_extra_damage = 0
    if not actor or 'special_buffs' not in actor:
        return 0

    logger.info(f"[process_on_hit_buffs] Checking buffs for {actor.get('name')}. Count: {len(actor['special_buffs'])}")

    # スナップショットをとって回す（副作用でリストが変わる可能性があるため）
    for buff_entry in list(actor['special_buffs']):
        buff_id = buff_entry.get('buff_id')
        handler_cls = buff_registry.get_handler(buff_id)

        if handler_cls and hasattr(handler_cls, 'on_hit_damage_calculation'):
            logger.info(f"[process_on_hit_buffs] Executing {handler_cls.__name__} for {buff_id}")
            # クラスメソッドとして呼び出し
            new_damage, logs = handler_cls.on_hit_damage_calculation(actor, target, damage_val + total_extra_damage)

            diff = new_damage - (damage_val + total_extra_damage)
            if diff != 0:
                logger.info(f"[process_on_hit_buffs] {handler_cls.__name__} added {diff} damage")
                total_extra_damage += diff

            if logs:
                log_snippets.extend(logs)
        else:
            logger.info(f"[process_on_hit_buffs] No handler or hook for {buff_id} ({buff_entry.get('name')}). Has Handler: {bool(handler_cls)}")

    return total_extra_damage

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
    # 0. ターン終了時処理 (前のキャラクター)
    # マホロバ (ID: 5) ボーナス: ターン終了時 HP+3 -> ラウンド終了時一括処理に変更

    current_idx = -1
    if current_id in timeline:
        current_idx = timeline.index(current_id)

    next_id = None

    # 現在位置の「次」から末尾に向かって、未行動のキャラを探す
    from plugins.buffs.confusion import ConfusionBuff
    from plugins.buffs.immobilize import ImmobilizeBuff

    for i in range(current_idx + 1, len(timeline)):
        cid = timeline[i]
        # キャラデータ取得
        char = next((c for c in state['characters'] if c['id'] == cid), None)

        # 生存していて、かつ「行動済み(hasActed)」でない
        if char and char.get('hp', 0) > 0 and not char.get('hasActed', False):
            # 行動不能チェック (混乱)
            if ConfusionBuff.is_incapacitated(char):
                logger.info(f"Skipping {char['name']} due to incapacitation (Confusion)")
                continue

            # 行動不能チェック (Immobilize/Bu-04)
            can_act, reason = ImmobilizeBuff.can_act(char, {})
            if not can_act:
                logger.info(f"[TurnSkip] Skipping {char['name']} due to Immobilize: {reason}")
                continue

            next_id = cid
            break

    if next_id:
        state['turn_char_id'] = next_id
        next_char = next((c for c in state['characters'] if c['id'] == next_id), None)
        logger.info(f"[proceed_next_turn] Next turn: {next_char['name']} (ID: {next_id})")

        # ラティウム (ID: 3) ボーナス: ターン開始時 FP+1 -> ラウンド開始時一括処理に変更

        broadcast_log(room, f"--- {next_char['name']} の手番です ---", 'turn-change')
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
    logger.debug("===== process_simple_round_end 開始 =====")

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

    # ★ 追加: マホロバ (ID: 5) ラウンド終了時一括処理
    mahoroba_targets = []
    for char in state.get('characters', []):
        if char.get('hp', 0) <= 0: continue

        # Origin Check
        if get_effective_origin_id(char) == 5:
            _update_char_stat(room, char, 'HP', char['hp'] + 3, username="[マホロバ恩恵]")
            mahoroba_targets.append(char['name'])

    if mahoroba_targets:
        broadcast_log(room, f"[マホロバ恩恵] {', '.join(mahoroba_targets)} のHPが3回復しました。", 'info')

    logger.debug("===== process_simple_round_end 完了 =====")
