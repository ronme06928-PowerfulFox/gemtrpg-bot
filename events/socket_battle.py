# events/socket_battle.py
import re
import json
import random
import copy
from flask import request, session
from flask_socketio import emit

# 拡張機能とマネージャーからのインポート
from extensions import socketio, all_skill_data
from manager.room_manager import (
    get_room_state, save_specific_room_state, broadcast_state_update,
    broadcast_log, get_user_info_from_sid, _update_char_stat
)
from manager.game_logic import (
    get_status_value, set_status_value, process_skill_effects,
    calculate_power_bonus, calculate_buff_power_bonus, # ★追加
    apply_buff, remove_buff
)
from manager.utils import resolve_placeholders
from manager.dice_roller import roll_dice
from manager.skill_effects import apply_skill_effects_bidirectional  # ★追加




# ★ Phase 2: 相手スキルを考慮した威力補正計算
def calculate_opponent_skill_modifiers(actor_char, target_char, actor_skill_data, target_skill_data, all_skill_data_ref):
    """
    相手スキルを考慮したPRE_MATCHエフェクトを評価し、各種補正値を返す。

    Returns:
        dict: {
            "base_power_mod": int,     # 基礎威力補正
            "dice_power_mod": int,     # ダイス威力補正（将来拡張用）
            "stat_correction_mod": int, # 物理/魔法補正（将来拡張用）
            "additional_power": int     # 追加威力（将来拡張用）
        }
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

# ★ Phase 7: Cost extraction helper
def extract_cost_from_text(text):
    """
    使用時効果テキストからコスト記述を抽出する（'[使用時]:MPを5消費。' -> 'MPを5消費。'）
    """
    if not text:
        return "なし"
    # 修正: 句点「。」で切れずに、行末まで取得するように変更
    match = re.search(r'\[使用時\]:?([^\n]+)', text)
    if match:
        return match.group(1).strip()
    return "なし"

# --- ヘルパー関数: スキル名表示用のHTML生成 (コマンドから抽出版) ---
def format_skill_display_from_command(command_str, skill_id, skill_data):
    """
    コマンド文字列に含まれる【ID 名称】を抽出して目立つ色で表示する。
    コマンド内に見つからない場合はマスタデータから生成する。
    """
    # コマンド内の 【...】 を探す
    match = re.search(r'【(.*?)】', command_str)
    text = ""

    if match:
        # コマンド内の表記をそのまま使う (カスタム名が含まれている)
        text = f"【{match.group(1)}】"
    elif skill_id and skill_data:
        # マスタデータから補完
        name = skill_data.get('デフォルト名称', '不明')
        text = f"【{skill_id}: {name}】"
    else:
        return ""

    # 視認性が高い色（濃いピンク/マゼンタ系）で太字にする
    return f"<span style='color: #d63384; font-weight: bold;'>{text}</span>"

# --- ヘルパー関数: active_match データからマッチを実行 ---
def execute_match_from_active_state(room, state, username):
    """
    両側が宣言済みの場合に、active_match の保存データを使ってマッチを実行する。
    ★ 修正: クライアント経由ではなく、サーバー側で直接マッチ処理を実行する。
    """
    active_match = state.get('active_match')
    if not active_match or not active_match.get('is_active'):
        return

    # ★ 重複実行防止: 既にマッチ実行中または実行済みなら何もしない
    if active_match.get('match_executing') or active_match.get('executed'):
        print(f"[MATCH] Match already executing/executed in room {room}, skipping")
        return

    attacker_id = active_match.get('attacker_id')
    defender_id = active_match.get('defender_id')
    attacker_data = active_match.get('attacker_data', {})
    defender_data = active_match.get('defender_data', {})

    command_a = attacker_data.get('final_command', '---')
    command_d = defender_data.get('final_command', '---')

    # ★ 一方攻撃フラグがある場合、防御側コマンドを強制的に一方攻撃専用文字列にする
    # (handle_match で is_one_sided として判定させるため)
    if active_match.get('is_one_sided_attack'):
        command_d = "【一方攻撃(行動済)】"
    senritsu_a = attacker_data.get('senritsu_penalty', 0)
    senritsu_d = defender_data.get('senritsu_penalty', 0)

    attacker_char = next((c for c in state["characters"] if c.get('id') == attacker_id), None)
    defender_char = next((c for c in state["characters"] if c.get('id') == defender_id), None)

    if not attacker_char or not defender_char:
        print(f"[MATCH ERROR] Characters not found: {attacker_id}, {defender_id}")
        return

    # ★ Phase 12.2: 攻撃者のスキルが防御/回避属性かチェック
    attacker_skill_id = attacker_data.get('skill_id')
    if attacker_skill_id and attacker_skill_id in all_skill_data:
        attacker_skill = all_skill_data[attacker_skill_id]
        skill_category = attacker_skill.get('分類', '')

        # 防御/回避スキルの場合はダメージ0のマッチを実行（手番を終了させるため）
        if skill_category in ['防御', '回避']:
            print(f"[MATCH] Defensive skill ({skill_category}) - executing match with 0 damage")
            command_a = "---"
            command_d = "---"
            broadcast_log(room, f"[{attacker_char.get('name')}] が {skill_category}スキルを使用したため、ダメージは発生しません。", 'match')

    # 実行中フラグを立てる
    state['active_match']['match_executing'] = True
    state['active_match']['executed'] = True
    save_specific_room_state(room)

    # active_match をクリア (完了したので削除)
    if 'active_match' in state:
        del state['active_match']

    save_specific_room_state(room)
    broadcast_state_update(room)

    # ★ マッチ終了時に全員のパネルを閉じる
    socketio.emit('match_modal_closed', {}, to=room)

    # ★ 修正: クライアント経由ではなく、サーバー側で直接handle_matchを呼び出す
    # match_data を構築してhandle_matchに渡す
    match_data = {
        'room': room,
        'commandA': command_a,
        'commandD': command_d,
        'actorIdA': attacker_id,
        'actorIdD': defender_id,
        'actorNameA': attacker_char.get('name', 'Unknown'),
        'actorNameD': defender_char.get('name', 'Unknown'),
        'senritsuPenaltyA': senritsu_a,
        'senritsuPenaltyD': senritsu_d
    }

    # ★ 修正: クライアント経由ではなく、サーバー側で直接handle_matchを呼び出す
    # match_dataを構築してhandle_matchを直接実行
    # handle_matchは@socketio.onデコレータがついているが、関数本体は普通に呼び出せる
    handle_match(match_data)

    print(f"[MATCH] Match executed directly on server in room {room}")


@socketio.on('request_skill_declaration')
def handle_skill_declaration(data):
    """
    スキル宣言処理
    - preview/commitフラグにより挙動を制御
    """
    room = data.get('room')
    if not room: return

    # ★追加: コミット（確定）フラグ。デフォルトはFalse（プレビュー）
    is_commit = data.get('commit', False)

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")

    # --- 1. データ取得 ---
    actor_id = data.get('actor_id')
    target_id = data.get('target_id')
    skill_id = data.get('skill_id')
    custom_skill_name = data.get('custom_skill_name')

    # 【修正】ID不足時にエラーを返す
    if not actor_id or not skill_id:
        socketio.emit('skill_declaration_result', {
            "prefix": data.get('prefix'),
            "final_command": "エラー: ID不足 (Actor or Skill)",
            "min_damage": 0, "max_damage": 0, "error": True
        }, to=request.sid)
        return

    state = get_room_state(room)

    # 実データの取得
    original_actor_char = next((c for c in state["characters"] if c.get('id') == actor_id), None)
    skill_data = all_skill_data.get(skill_id)

    original_target_char = None
    if target_id:
        original_target_char = next((c for c in state["characters"] if c.get('id') == target_id), None)

    # 【修正】データが見つからない場合にエラーを返す
    if not original_actor_char or not skill_data:
        error_msg = "エラー: データが見つかりません"
        if not original_actor_char: error_msg += f" (ActorID: {actor_id})"
        if not skill_data: error_msg += f" (SkillID: {skill_id})"

        socketio.emit('skill_declaration_result', {
            "prefix": data.get('prefix'),
            "final_command": error_msg,
            "min_damage": 0, "max_damage": 0, "error": True
        }, to=request.sid)
        return

    # ★ 追加: 権限チェック - GMまたは所有者のみがスキル宣言可能
    from manager.room_manager import is_authorized_for_character
    if not is_authorized_for_character(room, actor_id, username, user_info.get("attribute", "Player")):
        print(f"⚠️ Security: Player {username} tried to declare skill for character {original_actor_char['name']} without permission.")
        socketio.emit('skill_declaration_result', {
            "prefix": data.get('prefix'),
            "final_command": "エラー: このキャラクターのスキルを使用する権限がありません",
            "min_damage": 0, "max_damage": 0, "error": True
        }, to=request.sid)
        return


    # ★重要: 計算はすべて「複製データ(Sim)」で行う
    actor_char = copy.deepcopy(original_actor_char)
    target_char = copy.deepcopy(original_target_char) if original_target_char else None

    # === 混乱チェック ===
    if 'special_buffs' in actor_char:
        # プラグイン経由で混乱チェック
        from plugins.buffs.confusion import ConfusionBuff
        can_act, reason = ConfusionBuff.can_act(actor_char, {})

        if not can_act:
            socketio.emit('skill_declaration_result', {
                "prefix": data.get('prefix'),
                "final_command": reason,
                "min_damage": 0, "max_damage": 0, "error": True
            }, to=request.sid)
            return

    # --- 特記処理読み込み ---
    rule_json_str = skill_data.get('特記処理', '{}')
    try:
        rule_data = json.loads(rule_json_str) if rule_json_str else {}
    except json.JSONDecodeError as e:
        print(f"[ERROR] 特記処理(宣言)のJSONパースエラー: {e} (スキルID: {skill_id})")
        rule_data = {}

    effects_array = rule_data.get("effects", [])
    cost_array = rule_data.get("cost", [])

    # --- コストチェック (シミュレーション) ---
    for cost in cost_array:
        cost_type = cost.get("type")
        cost_value = int(cost.get("value", 0))
        if cost_value > 0:
            current_resource = get_status_value(actor_char, cost_type)
            if current_resource < cost_value:
                socketio.emit('skill_declaration_result', {
                    "prefix": data.get('prefix'),
                    "final_command": f"{cost_type}が {cost_value - current_resource} 不足しています",
                    "min_damage": 0, "max_damage": 0, "error": True
                }, to=request.sid)
                return

    # --- PRE_MATCH 効果のシミュレーション ---
    pre_match_bonus_damage, pre_match_logs, pre_match_changes = process_skill_effects(
        effects_array, "PRE_MATCH", actor_char, target_char, skill_data
    )

    # 変更を複製データに適用
    is_force_end_round = False
    force_unopposed = False

    for (char, type, name, value) in pre_match_changes:
        if type == "APPLY_STATE":
            current_val = get_status_value(char, name)
            set_status_value(char, name, current_val + value)
        elif type == "APPLY_BUFF":
            apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
        elif type == "FORCE_UNOPPOSED":
            force_unopposed = True
        elif type == "CUSTOM_EFFECT" and name == "END_ROUND_IMMEDIATELY":
            is_force_end_round = True

    # --- 戦慄によるダイス面減少計算 ---
    current_senritsu = get_status_value(actor_char, '戦慄')
    senritsu_max_apply = min(current_senritsu, 3) if current_senritsu > 0 else 0  # 最大3まで適用
    senritsu_dice_reduction = 0  # 実際にダイス面を減らした量（後で計算）

    # --- 即時発動かどうか ---
    is_immediate_skill = "即時発動" in skill_data.get("tags", []) or is_force_end_round

    skill_details_payload = {
        "分類": skill_data.get("分類", "---"),
        "距離": skill_data.get("距離", "---"),
        "属性": skill_data.get("属性", "---"),
        "特記": skill_data.get("特記", "") or "なし",
        # ★ Phase 7: Additional details for client display (Mapped from available data)
        "タイミング": skill_data.get("分類", "---"), # Substitute Category for Timing
        "判定": skill_data.get("判定", "---"),
        "対象": skill_data.get("対象", "---"),
        "射程": skill_data.get("距離", "---"), # Map 距離 to 射程
        "コスト": extract_cost_from_text(skill_data.get("使用時効果", "")), # Extract cost from text
        # ★ Phase 12.4: 【効果】は発動時効果のみ（使用時効果は【コスト】に表示済み）
        "効果": skill_data.get("発動時効果", "").strip() or "なし"
    }

    # =========================================================
    #  ★ パターンA: 即時発動スキル (宝石の加護など)
    # =========================================================
    if is_immediate_skill:
        if is_commit:
            # --- 確定実行 (Declareボタン押下時) ---

            # ★ バリデーション: 使用済みフラグチェック
            if 'flags' not in original_actor_char:
                original_actor_char['flags'] = {}

            skill_tags = skill_data.get("tags", [])

            # ★ 再回避ロックチェック
            from plugins.buffs.dodge_lock import DodgeLockBuff
            locked_skill_id = DodgeLockBuff.get_locked_skill_id(original_actor_char)

            # [DEBUG] 再回避ロックの状態を確認
            if locked_skill_id or any(b.get('name') == '再回避ロック' for b in original_actor_char.get('special_buffs', [])):
                print(f"[DEBUG_LOCK] Char: {original_actor_char['name']}, LockedID: {locked_skill_id}, Declaring: {skill_id}")

            if locked_skill_id:
                if skill_id != locked_skill_id:
                    print(f"[DEBUG_LOCK] BLOCKED violation: {skill_id} != {locked_skill_id}")
                    socketio.emit('skill_declaration_result', {
                        "prefix": data.get('prefix'),
                        "final_command": f"エラー: 再回避ロック中は指定されたスキル({locked_skill_id})のみ使用可能です",
                        "min_damage": 0, "max_damage": 0, "error": True
                    }, to=request.sid)
                    return

            is_gem_skill = "宝石の加護スキル" in skill_tags

            # 宝石の加護スキル: カテゴリ全体で1ラウンド1回
            if is_gem_skill:
                if original_actor_char['flags'].get('gem_skill_used', False):
                    socketio.emit('skill_declaration_result', {
                        "prefix": data.get('prefix'),
                        "final_command": "エラー: 今ラウンドは既に宝石の加護スキルを使用済みです",
                        "min_damage": 0, "max_damage": 0, "error": True
                    }, to=request.sid)
                    return
            else:
                # 即時発動スキル: 同一スキルIDは1ラウンド1回
                used_skills = original_actor_char['flags'].get('used_immediate_skills', [])
                if skill_id in used_skills:
                    socketio.emit('skill_declaration_result', {
                        "prefix": data.get('prefix'),
                        "final_command": f"エラー: 今ラウンドは既に {skill_id} を使用済みです",
                        "min_damage": 0, "max_damage": 0, "error": True
                    }, to=request.sid)
                    return

            # 1. 実データでコスト消費
            # 再回避ロック中の指定スキル使用ならコスト消費なし
            should_consume_cost = True
            if locked_skill_id and skill_id == locked_skill_id:
                should_consume_cost = False

            if should_consume_cost:
                for cost in cost_array:
                    cost_type = cost.get("type")
                    cost_value = int(cost.get("value", 0))
                if cost_value > 0:
                    curr = get_status_value(original_actor_char, cost_type)
                    _update_char_stat(room, original_actor_char, cost_type, curr - cost_value, username=f"[{skill_id}]")

            # 2. 実データで PRE_MATCH 効果適用
            _, _, real_changes = process_skill_effects(effects_array, "PRE_MATCH", original_actor_char, original_target_char, skill_data)

            for (char, type, name, value) in real_changes:
                if type == "APPLY_STATE":
                    current_val = get_status_value(char, name)
                    _update_char_stat(room, char, name, current_val + value, username=f"[{skill_id}]")
                elif type == "APPLY_BUFF":
                    apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                    broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
                elif type == "SET_FLAG":
                    if 'flags' not in char:
                        char['flags'] = {}
                    char['flags'][name] = value
                elif type == "CUSTOM_EFFECT" and name == "END_ROUND_IMMEDIATELY":
                    # 全キャラを行動済みに
                    for c in state['characters']:
                        c['hasActed'] = True
                    broadcast_log(room, f"[{skill_id}] の効果でラウンドが強制終了します。", 'round')
                    # ラウンド終了処理をトリガー
                    socketio.emit('request_end_round', {"room": room})

            # ★ タグベースのラウンド終了処理
            if "ラウンド終了" in skill_tags:
                for c in state['characters']:
                    c['hasActed'] = True
                broadcast_log(room, f"[{skill_id}] の効果でラウンドが強制終了します。", 'round')
                socketio.emit('request_end_round', {"room": room})

            # 3. 使用済みフラグを設定
            if is_gem_skill:
                original_actor_char['flags']['gem_skill_used'] = True
            else:
                if 'used_immediate_skills' not in original_actor_char['flags']:
                    original_actor_char['flags']['used_immediate_skills'] = []
                if skill_id not in original_actor_char['flags']['used_immediate_skills']:
                    original_actor_char['flags']['used_immediate_skills'].append(skill_id)

            # 4. 使用記録
            if 'used_skills_this_round' not in original_actor_char:
                original_actor_char['used_skills_this_round'] = []
            original_actor_char['used_skills_this_round'].append(skill_id)

            # 5. 保存
            broadcast_state_update(room)
            save_specific_room_state(room)

            # 6. クライアントへ応答 (リセット指示)
            result_payload = {
                "prefix": data.get('prefix'),
                "final_command": "--- (効果発動完了) ---",
                "is_one_sided_attack": False,
                "min_damage": 0,
                "max_damage": 0,
                "is_instant_action": True, # クライアント側で欄をリセットさせる
                "is_immediate_skill": True,
                "skill_details": skill_details_payload,
                "senritsu_penalty": 0
            }
            socketio.emit('skill_declaration_result', result_payload, to=request.sid)

            # ★ 追加: 即時発動の結果も同期
            side = 'attacker' if 'attacker' in data.get('prefix', '') else 'defender' if 'defender' in data.get('prefix', '') else None
            if side:
                sync_payload = {
                    'skill_id': skill_id,
                    'final_command': "--- (効果発動完了) ---",
                    'min_damage': 0, 'max_damage': 0,
                    'is_immediate': True,
                    'skill_details': skill_details_payload
                }
                socketio.emit('match_data_updated', {
                    'side': side,
                    'data': sync_payload
                }, to=room)

        else:
            # --- プレビューのみ (Calculateボタン押下時) ---
            socketio.emit('skill_declaration_result', {
                "prefix": data.get('prefix'),
                "final_command": "--- (即時発動: 宣言待機) ---",
                "is_one_sided_attack": False,
                "min_damage": 0,
                "max_damage": 0,
                "is_instant_action": False, # まだリセットしない
                "is_immediate_skill": True, # クライアントに「これは即時スキルだよ」と伝える
                "skill_details": skill_details_payload,
                "senritsu_penalty": 0
            }, to=request.sid)

        return

    # =========================================================
    #  ★ パターンB: 通常攻撃/自己バフ攻撃など
    # =========================================================

    if not target_char:
        # 広域攻撃の威力計算リクエスト等、ターゲットIDが自身または指定なしの場合があるため
        # ここでの厳密なエラーチェックは行わず、ターゲットなしとして計算を進めるケースを許容する場合があるが、
        # 基本的にはマッチには対象が必要。ただし、self-targetingなどのケースも考慮し、
        # ここではエラーを返すが、クライアント側で target_id = actor_id を送ることで回避可能とする。

        # もし「ターゲットなし」を許容するならここを修正するが、
        # 現状の仕様では target_id 必須としているためエラーを返す
        socketio.emit('skill_declaration_result', {
            "prefix": data.get('prefix'),
            "final_command": "エラー: マッチには「対象」が必要です",
            "min_damage": 0, "max_damage": 0, "error": True
        }, to=request.sid)
        return

    # 威力計算等は複製データで行う（変更なし）
    power_bonus = 0
    if isinstance(rule_data, dict):
        if 'power_bonus' in rule_data:
            power_bonus_data = rule_data.get('power_bonus')
        else:
            power_bonus_data = rule_data
        power_bonus = calculate_power_bonus(actor_char, target_char, power_bonus_data)

    base_command = skill_data.get('チャットパレット', '')
    actor_params = actor_char.get('params', [])
    resolved_command = resolve_placeholders(base_command, actor_params)
    if custom_skill_name:
        resolved_command = re.sub(r'【.*?】', f'【{skill_id} {custom_skill_name}】', resolved_command)

    buff_bonus = calculate_buff_power_bonus(actor_char, target_char, skill_data)
    power_bonus += buff_bonus

    total_modifier = power_bonus  # 戦慄はダイス面減少として適用済み

    # (既存のダメージ計算ロジック)
    base_power = 0
    try:
        base_power = int(skill_data.get('基礎威力', 0))
    except ValueError: base_power = 0

    # ★追加: バフからの基礎威力補正を取得
    from manager.utils import get_buff_stat_mod
    base_power_buff_mod = get_buff_stat_mod(actor_char, '基礎威力')
    base_power += base_power_buff_mod


    dice_roll_str = skill_data.get('ダイス威力', "")
    dice_min = 0; dice_max = 0
    original_num_faces = 0  # 元のダイス面数（戦慄減少表示用）
    dice_match = re.search(r'([+-]?)(\d+)d(\d+)', dice_roll_str)
    if dice_match:
        try:
            sign = dice_match.group(1)
            is_negative_dice = (sign == '-')
            num_dice = int(dice_match.group(2))
            original_num_faces = int(dice_match.group(3))
            num_faces = original_num_faces

            # 戦慄によるダイス面減少を適用（1d1未満にはならない）
            if senritsu_max_apply > 0 and num_faces > 1:
                max_reduction = num_faces - 1  # 1d1が最小
                senritsu_dice_reduction = min(senritsu_max_apply, max_reduction)
                num_faces = num_faces - senritsu_dice_reduction

            if is_negative_dice:
                # マイナスダイス: 最大出目が最小威力、最小出目が最大威力
                dice_min = -(num_dice * num_faces)
                dice_max = -num_dice
            else:
                dice_min = num_dice
                dice_max = num_dice * num_faces
        except Exception: pass

    phys_correction = get_status_value(actor_char, '物理補正')
    mag_correction = get_status_value(actor_char, '魔法補正')
    correction_min = 0; correction_max = 0
    if '{物理補正}' in base_command:
        correction_max = phys_correction
        if phys_correction >= 1: correction_min = 1
    elif '{魔法補正}' in base_command:
        correction_max = mag_correction
        if mag_correction >= 1: correction_min = 1

    min_damage = base_power + dice_min + correction_min + total_modifier
    max_damage = base_power + dice_max + correction_max + total_modifier

    # ★ コマンド文字列の構築
    final_command = resolved_command

    # ★ 基礎威力補正をコマンド文字列に反映
    if base_power_buff_mod != 0:
        # 基礎威力の数値を置換（例: "5+1d6" → "6+1d6"）
        try:
            original_base = int(skill_data.get('基礎威力', 0))
            if original_base > 0 and f"{original_base}+" in final_command:
                final_command = final_command.replace(f"{original_base}+", f"{base_power}+", 1)
            elif base_power > 0 and original_base == 0:
                # 元が0の場合は先頭に追加
                final_command = f"{base_power}+" + final_command
        except Exception as e:
            print(f"[WARNING] 基礎威力補正の反映に失敗: {e}")

    # ★ 戦慄によるダイス減少をコマンド文字列にも反映
    if senritsu_dice_reduction > 0 and original_num_faces > 0:
        reduced_faces = original_num_faces - senritsu_dice_reduction
        # 最初のダイス（基礎威力直後）を減少後の値に置換
        def replace_first_dice(m):
            return f"{m.group(1)}{m.group(2)}d{reduced_faces}"
        final_command = re.sub(r'([+-]?)(\d+)d' + str(original_num_faces), replace_first_dice, final_command, count=1)

    if total_modifier > 0:
        if ' 【' in final_command: final_command = final_command.replace(' 【', f"+{total_modifier} 【")
        else: final_command += f"+{total_modifier}"
    elif total_modifier < 0:
        if ' 【' in final_command: final_command = final_command.replace(' 【', f"{total_modifier} 【")
        else: final_command += f"{total_modifier}"

    is_one_sided_attack = False
    has_re_evasion = False
    if target_char and 'special_buffs' in target_char:
        # プラグイン経由で再回避ロックチェック
        from plugins.buffs.dodge_lock import DodgeLockBuff
        has_re_evasion = DodgeLockBuff.has_re_evasion(target_char)

    if (target_char.get('hasActed', False) and not has_re_evasion) or force_unopposed:
        is_one_sided_attack = True

    # --- 結果送信 (通常スキルなので即時発動フラグはFalse) ---
    # ★ 基礎威力補正をスキル詳細に追加
    skill_details_payload['base_power_mod'] = base_power_buff_mod

    result_payload = {
        "prefix": data.get('prefix'),
        "final_command": final_command,
        "is_one_sided_attack": is_one_sided_attack,
        "min_damage": min_damage,
        "max_damage": max_damage,
        "is_instant_action": False,
        "is_immediate_skill": False,
        "skill_details": skill_details_payload,
        "senritsu_penalty": senritsu_dice_reduction,  # ★ 互換性維持: 戦慄によるダイス減少量
        "senritsu_dice_reduction": senritsu_dice_reduction,  # ★ 新規: ダイス減少量
        "original_dice_faces": original_num_faces,  # ★ 新規: 元のダイス面数
        "reduced_dice_faces": original_num_faces - senritsu_dice_reduction if original_num_faces > 0 else 0  # ★ 減少後
    }
    socketio.emit('skill_declaration_result', result_payload, to=request.sid)

    # ★ リファクタリング: active_match に計算結果を保存し、state_updated で同期
    prefix = data.get('prefix', '')
    is_wide_match = prefix.startswith('wide_')
    side = 'attacker' if 'attacker' in prefix else 'defender' if 'defender' in prefix else None

    if side and state.get('active_match') and state['active_match'].get('is_active'):
        match_type = state['active_match'].get('match_type', 'duel')
        if is_wide_match: match_type = 'wide'

        # ★ マッチIDが未生成なら生成（重複実行防止用）
        if 'match_id' not in state['active_match']:
            import uuid
            state['active_match']['match_id'] = str(uuid.uuid4())
            print(f"[MATCH] Generated match ID: {state['active_match']['match_id']}")

        # 補正内訳データを共通で生成
        power_breakdown_data = {
            'base_power': base_power,
            'base_power_mod': 0,
            'dice_power_mod': 0,
            'stat_correction_mod': 0,
            'additional_power': power_bonus
        }

        if match_type == 'wide':
            # ★ 広域マッチ用の処理
            if side == 'attacker':
                # 攻撃者の場合: 攻撃者から防御者への補正を計算（将来の拡張用）
                state['active_match']['attacker_data'] = {
                    'skill_id': skill_id,
                    'final_command': final_command,
                    'min_damage': min_damage,
                    'max_damage': max_damage,
                    'is_immediate': False,
                    'skill_details': skill_details_payload,
                    'senritsu_penalty': senritsu_dice_reduction,
                    'power_breakdown': power_breakdown_data
                }

                # ★ 重要: 攻撃者が宣言/変更した場合、全防御者の補正を再計算して更新する
                skill_id_attacker = skill_id
                attacker_skill_data = all_skill_data.get(skill_id_attacker)
                attacker_char_obj = actor_char # 宣言しているのは攻撃者自身

                print(f"[WIDE_MATCH] Attacker declared. Updating modifiers for all defenders...")

                for defender in state['active_match'].get('defenders', []):
                    d_data = defender.get('data')
                    if d_data and d_data.get('skill_id'):
                        def_id = defender['id']
                        # ID比較は文字列で行う
                        def_char = next((c for c in state["characters"] if str(c.get('id')) == str(def_id)), None)
                        def_skill_id = d_data['skill_id']
                        def_skill_data = all_skill_data.get(def_skill_id)

                        if def_char and def_skill_data and attacker_skill_data:
                            # 攻撃者スキル -> 防御者への補正 (Actor=Attacker, Target=Defender)
                            mods = calculate_opponent_skill_modifiers(
                                attacker_char_obj, def_char, attacker_skill_data, def_skill_data, all_skill_data
                            )
                            base_mod = mods.get('base_power_mod', 0)

                            # コマンド再計算
                            def_base = int(def_skill_data.get('基礎威力', 0))
                            new_base = def_base + base_mod
                            def_dice = def_skill_data.get('ダイス威力', '2d6')
                            # Get full dice from chat palette (more reliable than ダイス威力)
                            palette = def_skill_data.get('チャットパレット', '')
                            cmd_part = re.sub(r'【.*?】', '', palette).strip()
                            if '+' in cmd_part:
                                dice_part = cmd_part.split('+', 1)[1]  # Everything after base power
                            else:
                                dice_part = def_dice

                            # 変数ダイスの解決
                            phys = get_status_value(def_char, '物理補正')
                            mag = get_status_value(def_char, '魔法補正')
                            processed_dice = dice_part.replace('{物理補正}', str(phys)).replace('{魔法補正}', str(mag))

                            new_command = f"{new_base}+{processed_dice}"

                            # 威力レンジ再計算
                            dice_min = 0; dice_max = 0
                            matches = re.findall(r'(\d+)d(\d+)', processed_dice)
                            for num_str, sides_str in matches:
                                num = int(num_str); sides = int(sides_str)
                                dice_min += num
                                dice_max += num * sides

                            new_min = new_base + dice_min
                            new_max = new_base + dice_max

                            # 更新
                            d_data['final_command'] = new_command
                            d_data['min_damage'] = new_min
                            d_data['max_damage'] = new_max

                            if 'power_breakdown' not in d_data: d_data['power_breakdown'] = {}
                            d_data['power_breakdown']['base_power_mod'] = base_mod
                            d_data['power_breakdown']['base_power'] = def_base

                            print(f"[WIDE_MATCH DEBUG] Updated Defender {def_id} Command: {new_command} (Mod: {base_mod})")
            else:
                # 防御者の場合: defenders配列から対象を探して更新
                attacker_data = state['active_match'].get('attacker_data', {})
                attacker_skill_id = attacker_data.get('skill_id')
                attacker_skill_data = all_skill_data.get(attacker_skill_id) if attacker_skill_id else None

                # 攻撃者スキルから防御者への補正を計算
                # actor = 攻撃者, target = 防御者, actor_skill = 攻撃者スキル, target_skill = 防御者スキル
                if attacker_skill_data:
                    # 攻撃者キャラを取得
                    attacker_id = state['active_match'].get('attacker_id')
                    attacker_char = next((c for c in state["characters"] if str(c.get('id')) == str(attacker_id)), None)
                    if not attacker_char:
                        print(f"[WIDE_MATCH ERROR] Attacker char not found for ID: {attacker_id} (Side: Defender Declaring)")

                    modifiers = calculate_opponent_skill_modifiers(
                        attacker_char, actor_char, attacker_skill_data, skill_data, all_skill_data
                    )
                    power_breakdown_data['base_power_mod'] = modifiers.get('base_power_mod', 0)
                    print(f"[WIDE_MATCH DEBUG] Defender {actor_id} base_power_mod: {modifiers.get('base_power_mod', 0)}")

                # defenders配列内の対象を更新
                updated = False
                for defender in state['active_match'].get('defenders', []):
                    if str(defender['id']) == str(actor_id):
                        defender['data'] = {
                            'skill_id': skill_id,
                            'final_command': final_command,
                            'min_damage': min_damage,
                            'max_damage': max_damage,
                            'skill_details': skill_details_payload,
                            'senritsu_penalty': senritsu_dice_reduction,
                            'power_breakdown': power_breakdown_data
                        }
                        updated = True
                        break
                if not updated:
                    print(f"[WIDE_MATCH ERROR] Defender {actor_id} not found in defenders list for update!")
        else:
            # ★ 通常デュエルマッチ用の処理（既存ロジック）
            opponent_side = 'defender' if side == 'attacker' else 'attacker'
            opponent_data = state['active_match'].get(f'{opponent_side}_data', {})
            opponent_skill_id = opponent_data.get('skill_id')
            opponent_skill_data = all_skill_data.get(opponent_skill_id) if opponent_skill_id else None

            # 相手スキルを考慮した補正計算
            opponent_modifiers = calculate_opponent_skill_modifiers(
                actor_char, target_char, skill_data, opponent_skill_data, all_skill_data
            )
            power_breakdown_data['base_power_mod'] = opponent_modifiers.get('base_power_mod', 0)

            # active_match に計算結果を保存
            side_data_key = f'{side}_data'
            state['active_match'][side_data_key] = {
                'skill_id': skill_id,
                'final_command': final_command,
                'min_damage': min_damage,
                'max_damage': max_damage,
                'is_immediate': False,
                'skill_details': skill_details_payload,
                'senritsu_penalty': senritsu_dice_reduction,
                'power_breakdown': power_breakdown_data
            }

        # ★ 以下はデュエルマッチ専用の処理（広域マッチはスキップ）
        if match_type != 'wide':
            # ★ 一方攻撃フラグを保存（攻撃者側の計算時に再判定）
            if side == 'attacker':
                # 防御者データを取得して再判定
                defender_id = state['active_match'].get('defender_id')
                defender_char = next((c for c in state["characters"] if c.get('id') == defender_id), None)

                # 一方攻撃かどうかを判定
                is_one_sided = False
                no_defender_acted = False

                # ★ マッチ不可タグのチェック
                attacker_skill_tags = [] # スキルデータからタグを取得
                if skill_data:
                    attacker_skill_tags = skill_data.get('tags', [])

                if 'マッチ不可' in attacker_skill_tags:
                    is_one_sided = True
                    no_defender_acted = True  # 防御側は行動済みにならない
                    print(f"[MATCH] マッチ不可 tag detected - forced one-sided, defender won't be marked as acted")
                elif defender_char:
                    # プラグイン経由で再回避ロックチェック
                    from plugins.buffs.dodge_lock import DodgeLockBuff
                    has_re_evasion = DodgeLockBuff.has_re_evasion(defender_char)
                    print(f"[MATCH] One-sided check: defender={defender_char.get('name')}, hasActed={defender_char.get('hasActed')}, has_re_evasion={has_re_evasion}")

                    if defender_char.get('hasActed', False) and not has_re_evasion:
                        is_one_sided = True

                if is_one_sided:
                    state['active_match']['is_one_sided_attack'] = True
                    if no_defender_acted:
                        state['active_match']['no_defender_acted'] = True
                    print(f"[MATCH] One-sided attack detected for room {room}")
                else:
                    # 通常マッチの場合はフラグを削除（以前の一方攻撃が残らないように）
                    state['active_match'].pop('is_one_sided_attack', None)
                    state['active_match'].pop('no_defender_acted', None)

            # コミット（宣言）の場合は declared フラグを立てる
            if is_commit:
                state['active_match'][f'{side}_declared'] = True
                print(f"[MATCH] {side} declared in room {room}")

            side_data_key = f'{side}_data'
            print(f"[MATCH DEBUG] Saved {side} data: {state['active_match'].get(side_data_key, {})}")
            save_specific_room_state(room)

            # ★ Phase 2: 相手が既に宣言済みなら、相手の補正も再計算
            if opponent_skill_data:
                # 相手側から見た補正を計算（自分のスキルが相手に与える補正）
                reverse_modifiers = calculate_opponent_skill_modifiers(
                    target_char, actor_char, opponent_skill_data, skill_data, all_skill_data
                )

                # 相手の power_breakdown を更新
                if opponent_data:
                    if 'power_breakdown' not in opponent_data:
                        opponent_data['power_breakdown'] = {}
                    opponent_data['power_breakdown']['base_power_mod'] = reverse_modifiers.get('base_power_mod', 0)
                    state['active_match'][f'{opponent_side}_data'] = opponent_data
                    print(f"[MATCH DEBUG] Updated {opponent_side} base_power_mod: {reverse_modifiers.get('base_power_mod', 0)}")
                    save_specific_room_state(room)

            # ★ 変更: match_data_updated ではなく state_updated を全員に送信
            broadcast_state_update(room)

            # 両側が宣言済みかチェック
            attacker_declared = state['active_match'].get('attacker_declared', False)
            defender_declared = state['active_match'].get('defender_declared', False)
            is_one_sided = state['active_match'].get('is_one_sided_attack', False)

            # ★ 一方攻撃の場合は攻撃者のみの宣言で実行
            # 通常マッチは両側が宣言したら実行
            should_execute = False
            if is_one_sided and attacker_declared:
                should_execute = True
                print(f"[MATCH] One-sided attack: attacker declared in room {room}, executing match...")
            elif attacker_declared and defender_declared:
                should_execute = True
                print(f"[MATCH] Both sides declared in room {room}, executing match...")

            if should_execute:
                # ★ 変更: クライアントに通知する代わりにサーバーで直接実行
                execute_match_from_active_state(room, state, user_info.get("username", "System"))
        else:
            # ★ 広域マッチの場合は状態保存と同期のみ
            save_specific_room_state(room)
            broadcast_state_update(room)


@socketio.on('request_match')
def handle_match(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    state = get_room_state(room)

    # ★ 重複実行防止: マッチIDをチェック
    match_id = data.get('match_id')
    active_match = state.get('active_match', {})

    # active_matchが存在する場合のみIDチェック（通常の手動実行では存在しない）
    if active_match.get('is_active'):
        expected_match_id = active_match.get('match_id')
        if match_id and match_id != expected_match_id:
            print(f"[MATCH] Match ID mismatch: {match_id} != {expected_match_id}, skipping")
            return

        # すでに実行済みかチェック
        if active_match.get('executed'):
            print(f"[MATCH] Match {match_id} already executed, skipping")
            return

        # 実行済みフラグを立てる
        state['active_match']['executed'] = True
        save_specific_room_state(room)
        print(f"[MATCH] Executing match {match_id}")

    command_a = data.get('commandA')
    command_d = data.get('commandD')
    actor_id_a = data.get('actorIdA')
    actor_id_d = data.get('actorIdD')
    actor_name_a = data.get('actorNameA')
    actor_name_d = data.get('actorNameD')

    senritsu_penalty_a = int(data.get('senritsuPenaltyA', 0))
    senritsu_penalty_d = int(data.get('senritsuPenaltyD', 0))

    global all_skill_data
    actor_a_char = next((c for c in state["characters"] if c.get('id') == actor_id_a), None)
    actor_d_char = next((c for c in state["characters"] if c.get('id') == actor_id_d), None)

    # PRE_MATCH 適用関数
    def apply_pre_match_effects(actor, target, skill_data, target_skill_data=None):
        if not skill_data or not actor: return
        try:
            rule_json_str = skill_data.get('特記処理', '{}')
            rule_data = json.loads(rule_json_str)
            effects_array = rule_data.get("effects", [])
            _, logs, changes = process_skill_effects(effects_array, "PRE_MATCH", actor, target, target_skill_data)

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

    if actor_a_char and senritsu_penalty_a > 0:
        curr = get_status_value(actor_a_char, '戦慄')
        _update_char_stat(room, actor_a_char, '戦慄', max(0, curr - senritsu_penalty_a), username=f"[{actor_name_a}:戦慄消費(ダイス-{senritsu_penalty_a})]")
    if actor_d_char and senritsu_penalty_d > 0:
        curr = get_status_value(actor_d_char, '戦慄')
        _update_char_stat(room, actor_d_char, '戦慄', max(0, curr - senritsu_penalty_d), username=f"[{actor_name_d}:戦慄消費(ダイス-{senritsu_penalty_d})]")

    skill_id_a = None; skill_data_a = None; effects_array_a = []
    skill_id_d = None; skill_data_d = None; effects_array_d = []
    match_a = re.search(r'【(.*?)\s', command_a)
    match_d = re.search(r'【(.*?)\s', command_d)

    if match_a and actor_a_char:
        skill_id_a = match_a.group(1)
        skill_data_a = all_skill_data.get(skill_id_a)
        if skill_data_a:
            # ★ 相手スキルデータを渡して条件評価を可能にする
            apply_pre_match_effects(actor_a_char, actor_d_char, skill_data_a, skill_data_d)
            rule_json_str_a = skill_data_a.get('特記処理')
            if rule_json_str_a:
                try:
                    rd = json.loads(rule_json_str_a)
                    effects_array_a = rd.get("effects", [])
                    if "即時発動" not in skill_data_a.get("tags", []):
                        for cost in rd.get("cost", []):
                            c_val = int(cost.get("value", 0))
                            if c_val > 0:
                                curr = get_status_value(actor_a_char, cost.get("type"))
                                _update_char_stat(room, actor_a_char, cost.get("type"), curr - c_val, username=f"[{skill_data_a.get('デフォルト名称')}]")
                except: pass
        if 'used_skills_this_round' not in actor_a_char: actor_a_char['used_skills_this_round'] = []
        actor_a_char['used_skills_this_round'].append(skill_id_a)

    if match_d and actor_d_char:
        skill_id_d = match_d.group(1)
        skill_data_d = all_skill_data.get(skill_id_d)
        if skill_data_d:
            # ★ 相手スキルデータを渡して条件評価を可能にする
            apply_pre_match_effects(actor_d_char, actor_a_char, skill_data_d, skill_data_a)
            rule_json_str_d = skill_data_d.get('特記処理')
            if rule_json_str_d:
                try:
                    rd = json.loads(rule_json_str_d)
                    effects_array_d = rd.get("effects", [])
                    if "即時発動" not in skill_data_d.get("tags", []):
                        for cost in rd.get("cost", []):
                            c_val = int(cost.get("value", 0))
                            if c_val > 0:
                                curr = get_status_value(actor_d_char, cost.get("type"))
                                _update_char_stat(room, actor_d_char, cost.get("type"), curr - c_val, username=f"[{skill_data_d.get('デフォルト名称')}]")
                except: pass
        if 'used_skills_this_round' not in actor_d_char: actor_d_char['used_skills_this_round'] = []
        actor_d_char['used_skills_this_round'].append(skill_id_d)

    result_a = roll_dice(command_a)
    result_d = roll_dice(command_d)
    winner_message = ''; damage_message = ''
    if actor_a_char: actor_a_char['hasActed'] = True
    # ★ マッチ不可の場合、防御側は行動済みにならない
    no_defender_acted = state.get('active_match', {}).get('no_defender_acted', False)
    if actor_d_char and not no_defender_acted:
        actor_d_char['hasActed'] = True
    bonus_damage = 0; log_snippets = []; changes = []
    is_one_sided = command_d.strip() == "【一方攻撃（行動済）】" or command_a.strip() == "【一方攻撃（行動済）】"

    try:
        def grant_win_fp(char):
            if not char: return
            curr = get_status_value(char, 'FP')
            _update_char_stat(room, char, 'FP', curr + 1, username="[マッチ勝利]")

        damage = 0; final_damage = 0; extra_skill_damage = 0
        attacker_tags = skill_data_a.get("tags", []) if skill_data_a else []
        defender_tags = skill_data_d.get("tags", []) if skill_data_d else []
        attacker_category = skill_data_a.get("分類", "") if skill_data_a else ""
        defender_category = skill_data_d.get("分類", "") if skill_data_d else ""

        # 荊棘処理
        if actor_a_char:
            at = get_status_value(actor_a_char, "荊棘")
            if at > 0:
                if attacker_category in ["物理", "魔法"]:
                    _update_char_stat(room, actor_a_char, "HP", actor_a_char['hp'] - at, username="[荊棘の自傷]")
                elif attacker_category == "防御" and skill_data_a:
                    try:
                        bp = int(skill_data_a.get('基礎威力', 0))
                        # ★ 基礎威力ボーナスを加算（MODIFY_BASE_POWERから）
                        bp += actor_a_char.get('_base_power_bonus', 0)
                        _update_char_stat(room, actor_a_char, "荊棘", max(0, at - bp), username=f"[{skill_data_a.get('デフォルト名称')}]")
                        # ★ ボーナスをリセット
                        actor_a_char.pop('_base_power_bonus', None)
                    except ValueError: pass
        if actor_d_char:
            dt = get_status_value(actor_d_char, "荊棘")
            if dt > 0:
                if defender_category in ["物理", "魔法"]:
                    _update_char_stat(room, actor_d_char, "HP", actor_d_char['hp'] - dt, username="[荊棘の自傷]")
                elif defender_category == "防御" and skill_data_d:
                    try:
                        bp = int(skill_data_d.get('基礎威力', 0))
                        # ★ 基礎威力ボーナスを加算（MODIFY_BASE_POWERから）
                        bp += actor_d_char.get('_base_power_bonus', 0)
                        _update_char_stat(room, actor_d_char, "荊棘", max(0, dt - bp), username=f"[{skill_data_d.get('デフォルト名称')}]")
                        # ★ ボーナスをリセット
                        actor_d_char.pop('_base_power_bonus', None)
                    except ValueError: pass

        if "即時発動" in attacker_tags or "即時発動" in defender_tags:
            winner_message = '<strong> → スキル効果の適用のみ</strong>'; damage_message = '(ダメージなし)'
        elif is_one_sided:
            if "守備" in attacker_tags:
                winner_message = f"<strong> → {actor_name_a} の一方攻撃！</strong> (守備スキルのためダメージなし)"; damage_message = "(ダメージ 0)"
            else:
                damage = result_a['total']
                if actor_d_char:
                    kiretsu = get_status_value(actor_d_char, '亀裂')
                    # 一方攻撃: UNOPPOSED -> HIT (HIT処理時にバフが乗るかはUNOPPOSED次第)
                    bd_un, log_un, chg_un = process_skill_effects(effects_array_a, "UNOPPOSED", actor_a_char, actor_d_char, skill_data_d)

                    # ここは既存構造的に一括処理が残っているが、apply_skill_effects_bidirectional 相当の即時適用ロジックが必要
                    # 簡易的に bidirectional 関数を流用できないため、ここだけ手動で即時適用に書き換える
                    def local_apply(clist):
                        ex = 0
                        for (c, t, n, v) in clist:
                            if t == "APPLY_STATE": _update_char_stat(room, c, n, get_status_value(c, n)+v, username=f"[{n}]")
                            elif t == "APPLY_BUFF": apply_buff(c, n, v["lasting"], v["delay"], data=v.get("data"))
                            elif t == "REMOVE_BUFF": remove_buff(c, n)
                            elif t == "CUSTOM_DAMAGE": ex += v
                            elif t == "SET_FLAG":
                                if 'flags' not in c:
                                    c['flags'] = {}
                                c['flags'][n] = v
                        return ex

                    # UNOPPOSED適用
                    local_apply(chg_un)

                    # HIT適用 (UNOPPOSEDでバフがついていれば乗る)
                    bd_hit, log_hit, chg_hit = process_skill_effects(effects_array_a, "HIT", actor_a_char, actor_d_char, skill_data_d)
                    extra_skill_damage = local_apply(chg_hit)

                    log_snippets.extend(log_un + log_hit)
                    bonus_damage = bd_un + bd_hit

                    final_damage = damage + kiretsu + bonus_damage + extra_skill_damage
                    if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                        final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                    _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                    winner_message = f"<strong> → {actor_name_a} の一方攻撃！</strong>"
                    damage_message += f"({actor_d_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + (f"+ [追加攻撃 {extra_skill_damage}] " if extra_skill_damage > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
        elif attacker_category == "防御" and defender_category == "防御":
            winner_message = "<strong> → 両者防御のため、ダメージなし</strong>"; damage_message = "(相殺)"
        elif (attacker_category == "防御" and defender_category == "回避") or (attacker_category == "回避" and defender_category == "防御"):
            winner_message = "<strong> → 防御と回避のため、マッチ不成立</strong>"; damage_message = "(効果処理なし)"
        elif "守備" in defender_tags and defender_category == "防御":
            if result_a['total'] > result_d['total']:
                grant_win_fp(actor_a_char)
                damage = result_a['total'] - result_d['total']
                kiretsu = get_status_value(actor_d_char, '亀裂')
                # ★修正: 即時適用関数を利用
                bonus_damage, logs = apply_skill_effects_bidirectional(room, state, username, 'attacker', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
                log_snippets.extend(logs)
                final_damage = damage + kiretsu + bonus_damage # extra_skill_damageはbonus_damageに含まれる
                if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_a} の勝利！</strong> (ダメージ軽減)"
                damage_message += f"(差分 {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
            else:
                grant_win_fp(actor_d_char)
                winner_message = f"<strong> → {actor_name_d} の勝利！</strong> (防御成功)"
                _, logs = apply_skill_effects_bidirectional(room, state, username, 'defender', actor_a_char, actor_d_char, skill_data_a, skill_data_d)
                log_snippets.extend(logs)
                damage_message = "(ダメージ 0)"
                if log_snippets: damage_message += f" ({' '.join(log_snippets)})"
        elif "守備" in defender_tags and defender_category == "回避":
            if result_a['total'] > result_d['total']:
                grant_win_fp(actor_a_char)
                damage = result_a['total']
                kiretsu = get_status_value(actor_d_char, '亀裂')
                bonus_damage, logs = apply_skill_effects_bidirectional(room, state, username, 'attacker', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
                log_snippets.extend(logs)
                final_damage = damage + kiretsu + bonus_damage
                if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_a} の勝利！</strong> (回避失敗)"
                damage_message += f"({actor_d_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
            else:
                grant_win_fp(actor_d_char)
                _, logs = apply_skill_effects_bidirectional(room, state, username, 'defender', actor_a_char, actor_d_char, skill_data_a, skill_data_d)
                if actor_d_char:
                    log_snippets.append("[再回避可能！]")
                    # ★修正: dataにbuff_idを含めることでプラグイン判定を有効にする
                    apply_buff(actor_d_char, "再回避ロック", 1, 0, data={"skill_id": skill_id_d, "buff_id": "Bu-05"})
                log_snippets.extend(logs)
                winner_message = f"<strong> → {actor_name_d} の勝利！</strong> (回避成功)"; damage_message = "(ダメージ 0)"
                if log_snippets: damage_message += f" ({' '.join(log_snippets)})"
        elif result_a['total'] > result_d['total']:
            grant_win_fp(actor_a_char)
            damage = result_a['total']
            if actor_d_char:
                kiretsu = get_status_value(actor_d_char, '亀裂')
                bonus_damage, logs = apply_skill_effects_bidirectional(room, state, username, 'attacker', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
                log_snippets.extend(logs)
                final_damage = damage + kiretsu + bonus_damage
                if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_a} の勝利！</strong>"
                damage_message += f"({actor_d_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
        elif result_d['total'] > result_a['total']:
            grant_win_fp(actor_d_char)
            damage = result_d['total']
            if actor_a_char:
                kiretsu = get_status_value(actor_a_char, '亀裂')
                bonus_damage, logs = apply_skill_effects_bidirectional(room, state, username, 'defender', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
                log_snippets.extend(logs)
                final_damage = damage + kiretsu + bonus_damage
                if any(b.get('name') == "混乱" for b in actor_a_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                _update_char_stat(room, actor_a_char, 'HP', actor_a_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_d} の勝利！</strong>"
                damage_message += f"({actor_a_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
        else:
            winner_message = '<strong> → 引き分け！</strong> (ダメージなし)'
            # 引き分け処理も即時適用ロジックに合わせる
            def run_end_match(effs, actor, target, skill):
                d, l, c = process_skill_effects(effs, "END_MATCH", actor, target, skill)
                all_logs = l
                # 簡易適用
                for (char, type, name, value) in c:
                    if type == "APPLY_STATE": _update_char_stat(room, char, name, get_status_value(char, name)+value, username=f"[{name}]")
                    elif type == "APPLY_BUFF": apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                    elif type == "REMOVE_BUFF": remove_buff(char, name)
                    elif type == "SET_FLAG":
                        if 'flags' not in char:
                            char['flags'] = {}
                        char['flags'][name] = value
                return all_logs

            log_a = run_end_match(effects_array_a, actor_a_char, actor_d_char, skill_data_d)
            log_d = run_end_match(effects_array_d, actor_d_char, actor_a_char, skill_data_a)
            log_snippets.extend(log_a + log_d)
            if log_snippets: winner_message += f" ({' '.join(log_snippets)})"

    except TypeError as e:
        print("--- ▼▼▼ エラーをキャッチしました ▼▼▼ ---", flush=True)
        print(f"エラー内容: {e}", flush=True)
        raise e

    skill_display_a = format_skill_display_from_command(command_a, skill_id_a, skill_data_a)
    skill_display_d = format_skill_display_from_command(command_d, skill_id_d, skill_data_d)
    match_log = f"<strong>{actor_name_a}</strong> {skill_display_a} (<span class='dice-result-total'>{result_a['total']}</span>) vs <strong>{actor_name_d}</strong> {skill_display_d} (<span class='dice-result-total'>{result_d['total']}</span>) | {winner_message} {damage_message}"
    broadcast_log(room, match_log, 'match')
    broadcast_state_update(room)
    save_specific_room_state(room)

    # --- 手番更新処理 ---
    if actor_a_char:
        # プラグイン経由で再回避ロックチェック
        from plugins.buffs.dodge_lock import DodgeLockBuff
        has_re_evasion = DodgeLockBuff.has_re_evasion(actor_a_char)

        if not has_re_evasion:
             actor_a_char['hasActed'] = True
             save_specific_room_state(room)

    # 次のターンへ
    handle_next_turn({'room': room})


@socketio.on('request_new_round')
def handle_new_round(data):
    room = data.get('room')
    if not room: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        print(f"⚠️ Security: Player {username} tried to start new round. Denied.")
        return

    state = get_room_state(room)
    if state['round'] > 0 and not state.get('is_round_ended', False):
        socketio.emit('new_log', {"message": "⚠️ ラウンド終了処理が行われていません。", "type": "error"}, to=request.sid)
        return

    # 新しいラウンドを開始するのでフラグを下ろす
    state['is_round_ended'] = False

    state['round'] += 1

    broadcast_log(room, f"--- {username} が Round {state['round']} を開始しました ---", 'round')

    def get_speed_stat(char):
        param = next((p for p in char['params'] if p.get('label') == '速度'), None)
        return int(param.get('value')) if param else 0

    for char in state['characters']:
        # ★ 未配置キャラクター（座標が負）は速度ロール・ラウンド参加から除外
        if char.get('x', -1) < 0 or char.get('y', -1) < 0:
            continue

        # === フラグのリセット ===
        char['isWideUser'] = False # 広域使用フラグのリセット
        char['hasActed'] = False   # 行動済みフラグのリセット
        char['used_skills_this_round'] = [] # 使用済みスキルリストのリセット

        # === 即時発動フラグのリセット ===
        if 'flags' not in char:
            char['flags'] = {}
        char['flags']['gem_skill_used'] = False
        char['flags']['used_immediate_skills'] = []
        char['flags']['fissure_received_this_round'] = False  # ★亀裂付与制限のリセット

        # 再回避ロックの解除
        if 'special_buffs' in char:
            remove_buff(char, "再回避ロック")

        # === 速度ロール ===
        base_speed = get_speed_stat(char)
        roll = random.randint(1, 6)
        stat_bonus = base_speed // 6
        char['speedRoll'] = roll + stat_bonus
        log_detail = f"{char['name']}: 1d6({roll}) + {stat_bonus} = <span class='dice-result-total'>{char['speedRoll']}</span>"
        broadcast_log(room, log_detail, 'dice')

    def sort_key(char):
        speed_roll = char.get('speedRoll', 0)
        is_enemy = 1 if char['type'] == 'enemy' else 2
        speed_stat = get_speed_stat(char)
        random_tiebreak = random.random()
        return (-speed_roll, is_enemy, -speed_stat, random_tiebreak)

    state['characters'].sort(key=sort_key)
    # ★ 速度ロールがあり、かつ配置されているキャラクターのみをタイムラインに追加
    state['timeline'] = [c['id'] for c in state['characters'] if c.get('speedRoll', 0) > 0 and c.get('x', -1) >= 0 and c.get('y', -1) >= 0]

    # ★修正点: ここでは手番を決定せず、Noneに設定する
    # 手番決定は「広域攻撃予約」の後に行う
    state['turn_char_id'] = None

    broadcast_state_update(room)
    save_specific_room_state(room)

    # ★追加: GMのクライアントに対して「広域攻撃予約モーダル」を開くよう指示
    socketio.emit('open_wide_declaration_modal', {'room': room}, to=request.sid)


@socketio.on('request_next_turn')
def handle_next_turn(data):
    room = data.get('room')
    if not room: return

    state = get_room_state(room)
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
    for i in range(current_idx + 1, len(timeline)):
        cid = timeline[i]
        # キャラデータ取得
        char = next((c for c in state['characters'] if c['id'] == cid), None)
        # 生存していて、かつ「行動済み(hasActed)」でないなら、その人を次の手番にする
        if char and char.get('hp', 0) > 0 and not char.get('hasActed', False):
            next_id = cid
            break

    # もし見つからなかった場合（全員行動済み、または現在の人が最後）
    # ループせず「手番なし」状態にする（ラウンド終了待ち）

    if next_id:
        state['turn_char_id'] = next_id
        next_char = next((c for c in state['characters'] if c['id'] == next_id), None)
        char_name = next_char['name'] if next_char else "不明"
        broadcast_log(room, f"手番が {char_name} に移りました。", 'info')
    else:
        state['turn_char_id'] = None
        broadcast_log(room, "全てのキャラクターが行動を終了しました。ラウンド終了処理を行ってください。", 'info')

    broadcast_state_update(room)
    save_specific_room_state(room)


# ▼▼▼ ラウンド終了処理 ▼▼▼
@socketio.on('request_end_round')
def handle_end_round(data):
    room = data.get('room')
    if not room: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        print(f"⚠️ Security: Player {username} tried to end round. Denied.")
        return

    state = get_room_state(room)

    if state.get('is_round_ended', False):
        socketio.emit('new_log', {"message": "⚠️ 既にラウンド終了処理は完了しています。", "type": "error"}, to=request.sid)
        return

    broadcast_log(room, f"--- {username} が Round {state['round']} の終了処理を実行しました ---", 'info')
    characters_to_process = state.get('characters', [])

    global all_skill_data

    for char in characters_to_process:

        # --- 1. "END_ROUND" 効果 (アクティブ) の処理 ---
        used_skill_ids = char.get('used_skills_this_round', [])

        all_end_round_changes = []
        all_end_round_logs = []

        for skill_id in set(used_skill_ids):
            skill_data = all_skill_data.get(skill_id)
            if not skill_data:
                continue

            rule_json_str = skill_data.get('特記処理', '{}')
            effects_array = []
            if rule_json_str:
                try:
                    rule_data = json.loads(rule_json_str)
                    effects_array = rule_data.get("effects", [])
                except json.JSONDecodeError:
                    pass

            if not effects_array:
                continue

            bonus_dmg, logs, changes = process_skill_effects(
                effects_array, "END_ROUND", char, char, None
            )
            all_end_round_changes.extend(changes)
            all_end_round_logs.extend(logs)

        for (c, type, name, value) in all_end_round_changes:
            if type == "APPLY_STATE":
                current_val = get_status_value(c, name)
                _update_char_stat(room, c, name, current_val + value, username=f"[{state['round']}R終了時]")
            elif type == "APPLY_BUFF":
                apply_buff(c, name, value["lasting"], value["delay"])
                broadcast_log(room, f"[{name}] が {c['name']} に付与されました。", 'state-change')

        # --- 1c. (旧) 出血処理 ---
        bleed_value = get_status_value(char, '出血')
        if bleed_value > 0:
            damage = bleed_value
            _update_char_stat(room, char, 'HP', char['hp'] - damage, username="[出血]")
            new_bleed_value = bleed_value // 2
            _update_char_stat(room, char, '出血', new_bleed_value, username="[出血]")

        # --- 1d. (旧) 荊棘処理 ---
        thorns_value = get_status_value(char, '荊棘')
        if thorns_value > 0:
            _update_char_stat(room, char, '荊棘', thorns_value - 1, username="[荊棘]")

        # --- 2. バフタイマーの処理 ---
        # === Phase 1.1: バフのディレイとlastingを減らす ===
        if "special_buffs" in char:
            print(f"[DEBUG] {char.get('name', 'Unknown')}: バフ数={len(char.get('special_buffs', []))}")
            active_buffs = []
            buffs_to_remove = []

            for buff in char['special_buffs']:
                buff_name = buff.get("name")
                delay = buff.get("delay", 0)
                lasting = buff.get("lasting", 0)

                if delay > 0:
                    buff["delay"] = delay - 1
                    active_buffs.append(buff)
                    if buff["delay"] == 0:
                        broadcast_log(room, f"[{buff_name}] の効果が {char['name']} で発動可能になった。", 'state-change')

                elif lasting > 0:
                    buff["lasting"] = lasting - 1
                    if buff["lasting"] > 0:
                        active_buffs.append(buff)
                    else:
                        broadcast_log(room, f"[{buff_name}] の効果が {char['name']} から切れた。", 'state-change')
                        buffs_to_remove.append(buff_name)

                        # === ▼▼▼ 修正点 (混乱解除時のMP回復) ▼▼▼ ===
                        if buff_name == "混乱":
                            max_mp = int(char.get('maxMp', 0))
                            _update_char_stat(room, char, 'MP', max_mp, username="[混乱解除]")
                            broadcast_log(room, f"{char['name']} は意識を取り戻した！ (MP全回復)", 'state-change')
                        # === ▲▲▲ 修正ここまで ▲▲▲ ===

                elif buff.get('is_permanent', False):
                    # ★ 永続バフ（輝化スキルなど）is_permanentフラグがTrueなら保持
                    print(f"[DEBUG] 永続バフ保持: {buff.get('name')} (source={buff.get('source')})")
                    active_buffs.append(buff)

            char['special_buffs'] = active_buffs

        # ★ アイテム使用制限をリセット（全キャラ対象、バフの有無に関わらず）
        print(f"[DEBUG] {char.get('name', 'Unknown')}: round_item_usage存在チェック: {'round_item_usage' in char}")
        if 'round_item_usage' in char:
            print(f"[DEBUG] {char.get('name', 'Unknown')} のアイテム使用制限をリセット: {char['round_item_usage']}")
            char['round_item_usage'] = {}
        else:
            print(f"[DEBUG] {char.get('name', 'Unknown')}: round_item_usageフィールドが存在しません")

        # ★ スキル使用履歴をリセット（全キャラ対象）
        if 'used_immediate_skills_this_round' in char:
            char['used_immediate_skills_this_round'] = []
        if 'used_gem_protect_this_round' in char:
            char['used_gem_protect_this_round'] = False
        if 'used_skills_this_round' in char:
            char['used_skills_this_round'] = []

    print(f"[DEBUG] ===== ラウンド終了処理完了 =====")
    state['is_round_ended'] = True
    state['turn_char_id'] = None  # ★ 手番キャラをクリア（青い光やボタンを消すため）

    # ★ 追加: ラウンド終了時にアクティブマッチも強制終了
    state['active_match'] = None

    broadcast_state_update(room)
    save_specific_room_state(room)


def _process_end_round_logic(state, room):
    """
    ラウンド終了時の共通処理（バフ減少、アイテムリセットなど）
    広域マッチからも呼び出される
    """
    print(f"[DEBUG] ===== _process_end_round_logic 開始 =====")

    for char in state.get("characters", []):
        # バフタイマーの処理
        if "special_buffs" in char:
            print(f"[DEBUG] {char.get('name', 'Unknown')}: バフ数={len(char.get('special_buffs', []))}")
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
                    print(f"[DEBUG] 永続バフ保持: {buff.get('name')} (source={buff.get('source')})")
                    active_buffs.append(buff)

            char['special_buffs'] = active_buffs

        # アイテム使用制限をリセット
        if 'round_item_usage' in char:
            print(f"[DEBUG] {char.get('name', 'Unknown')} のアイテム使用制限をリセット: {char['round_item_usage']}")
            char['round_item_usage'] = {}

        # スキル使用履歴をリセット
        if 'used_immediate_skills_this_round' in char:
            char['used_immediate_skills_this_round'] = []
        if 'used_gem_protect_this_round' in char:
            char['used_gem_protect_this_round'] = False
        if 'used_skills_this_round' in char:
            char['used_skills_this_round'] = []

    print(f"[DEBUG] ===== _process_end_round_logic 完了 =====")



@socketio.on('request_reset_battle')
def handle_reset_battle(data):
    room = data.get('room')
    if not room: return

    # モード取得 (デフォルトは full)
    mode = data.get('mode', 'full')

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    state = get_room_state(room)

    print(f"Battle reset ({mode}) for room '{room}' by {username}.")

    if mode == 'full':
        # === A. 完全リセット (既存) ===
        state["characters"] = []
        state["timeline"] = []
        state["round"] = 0
        state["is_round_ended"] = False # フラグもリセット
        broadcast_log(room, f"--- {username} が戦闘を完全リセットしました ---", 'round')

    elif mode == 'status':
        # === B. ステータスリセット (新規) ===
        state["round"] = 0
        state["timeline"] = []
        state["is_round_ended"] = False

        for char in state["characters"]:
            # HP/MP を最大値に
            char['hp'] = int(char.get('maxHp', 0))
            char['mp'] = int(char.get('maxMp', 0))

            # 状態異常・FP をリセット (初期状態に戻す)
            # ※ FP=0, 他の状態異常=0 のリストを再生成
            initial_states = [
                { "name": "FP", "value": 0 },
                { "name": "出血", "value": 0 },
                { "name": "破裂", "value": 0 },
                { "name": "亀裂", "value": 0 },
                { "name": "戦慄", "value": 0 },
                { "name": "荊棘", "value": 0 }
            ]
            char['states'] = initial_states
            char['状態異常'] = []
            char['FP'] = char.get('maxFp', 0)

            # ★ アイテム使用制限もリセット
            if 'round_item_usage' in char:
                char['round_item_usage'] = {}

            # スキル使用履歴もリセット
            if 'used_immediate_skills_this_round' in char:
                char['used_immediate_skills_this_round'] = []
            if 'used_gem_protect_this_round' in char:
                char['used_gem_protect_this_round'] = False
            if 'used_skills_this_round' in char:
                char['used_skills_this_round'] = []

            # ★ initial_stateからバフとアイテムを復元
            if 'initial_state' in char:
                # アイテムを初期状態に復元
                char['inventory'] = dict(char['initial_state'].get('inventory', {}))
                # バフを初期状態に復元（輝化スキル由来のバフを含む）
                char['special_buffs'] = [dict(b) for b in char['initial_state'].get('special_buffs', [])]
                # maxHp/maxMpを初期状態に復元（輝化スキルによる増加を反映）
                char['maxHp'] = int(char['initial_state'].get('maxHp', char.get('maxHp', 0)))
                char['maxMp'] = int(char['initial_state'].get('maxMp', char.get('maxMp', 0)))
            else:
                # initial_stateがない場合は空にする
                char['special_buffs'] = []
                if 'inventory' not in char:
                    char['inventory'] = {}
            # === ▲▲▲ Phase 6 ここまで ▲▲▲

            # HP/MP を最大値に（復元されたmaxHp/maxMpを使用）
            char['hp'] = int(char.get('maxHp', 0))
            char['mp'] = int(char.get('maxMp', 0))

            # フラグ削除
            char['hasActed'] = False
            char['speedRoll'] = 0
            char['used_skills_this_round'] = []
            # ★追加: 広域攻撃フラグもリセット（広域攻撃ボタンを非表示にするため）
            char['isWideUser'] = False

        # ★追加: 手番キャラをクリア（発光表示を消すため）
        state['turn_char_id'] = None

        broadcast_log(room, f"--- {username} が全キャラクターの状態をリセットしました ---", 'round')

    # ★追加: リセット時にアクティブマッチも強制終了
    state['active_match'] = None

    broadcast_state_update(room)
    save_specific_room_state(room)

@socketio.on('request_force_end_match')
def handle_force_end_match(data):
    room = data.get('room')
    if not room: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        print(f"⚠️ Security: Player {username} tried to force end match. Denied.")
        return

    state = get_room_state(room)
    if not state.get('active_match') or not state['active_match'].get('is_active'):
        socketio.emit('new_log', {"message": "現在アクティブなマッチはありません。", "type": "error"}, to=request.sid)
        return

    state['active_match'] = None
    save_specific_room_state(room)
    broadcast_state_update(room)

    # ★ 全クライアントにマッチパネルを閉じるよう通知
    socketio.emit('match_modal_closed', {}, to=room)

    broadcast_log(room, f"⚠️ GM {username} がマッチを強制終了しました。", 'match-end')



@socketio.on('request_move_token')
def handle_move_token(data):
    """キャラクタートークンを移動させる（ピクセル座標で管理）"""
    room_name = data.get('room')
    char_id = data.get('charId')
    target_x = data.get('x')
    target_y = data.get('y')

    # ★ 追加: 権限チェック
    from flask import request
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    # ルームデータの取得
    state = get_room_state(room_name)
    if not state:
        return

    # キャラクター検索
    target_char = next((c for c in state["characters"] if c.get('id') == char_id), None)

    if target_char:
        # ★ 追加: 権限チェック - GMまたは所有者のみ移動可能
        from manager.room_manager import is_authorized_for_character
        if not is_authorized_for_character(room_name, char_id, username, attribute):
            print(f"⚠️ Security: Player {username} tried to move character {target_char['name']} without permission.")
            socketio.emit('move_denied', {
                'message': 'このキャラクターを移動する権限がありません。'
            }, to=request.sid)
            return

        # 座標更新 (データがなければ新規作成される)
        target_char["x"] = int(target_x)
        target_char["y"] = int(target_y)

        # ログ出力 (デバッグ用)
        print(f"[MOVE] Room:{room_name}, Char:{target_char['name']} -> ({target_x}, {target_y}) by {username}")

        # 保存
        save_specific_room_state(room_name)

        # 全員に更新を通知
        broadcast_state_update(room_name)

# ============================================================
# マッチモーダル同期機能
# ============================================================

@socketio.on('open_match_modal')
def handle_open_match_modal(data):
    """
    マッチモーダルを開催し、全員に通知
    """
    room = data.get('room')
    if not room:
        return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    match_type = data.get('match_type')  # 'duel' or 'wide'
    attacker_id = data.get('attacker_id')
    defender_id = data.get('defender_id')  # duelの場合のみ
    targets = data.get('targets', [])  # wideの場合のみ

    state = get_room_state(room)

    # ★ 挑発チェック (duelの場合のみ)
    if match_type == 'duel':
        attacker_char = next((c for c in state["characters"] if c.get('id') == attacker_id), None)
        if attacker_char:
            attacker_type = attacker_char.get('type', 'ally')

            # 敵側で「挑発中」バフを持つキャラを検索
            provoking_enemies = []
            for c in state["characters"]:
                if c.get('type') != attacker_type and c.get('hp', 0) > 0:
                    if 'special_buffs' in c:
                        for buff in c['special_buffs']:
                            if buff.get('name') == '挑発中':
                                # ★修正: ディレイ中は効果を発揮しない
                                if buff.get('delay', 0) > 0:
                                    continue
                                provoking_enemies.append(c['id'])
                                break

            # 挑発持ちがいて、対象がその中にない場合はエラー
            if provoking_enemies and defender_id not in provoking_enemies:
                socketio.emit('match_error', {
                    'error': '挑発中の敵がいるため、他のキャラクターを攻撃できません。'
                }, room=request.sid)
                return  # ★ ここで終了し、絶対に下に通さない

    # ★ Phase 9: Resume Logic
    # 既存のactive_matchがあり、かつ同じアクター/ターゲットなら再開する
    current_match = state.get('active_match')
    is_resume = False

    if current_match and \
       current_match.get('attacker_id') == attacker_id and \
       current_match.get('defender_id') == defender_id and \
       current_match.get('match_type') == match_type:
           # 再開 (Resume)
           state['active_match']['is_active'] = True
           # opened_by だけ更新
           state['active_match']['opened_by'] = username
           is_resume = True
           print(f"[MATCH] Resuming existing match for {attacker_id} vs {defender_id}")
    else:
        # 新規作成 (New)
        # ★ Phase 12.1: 防御者が行動済みかチェック
        defender_char = next((c for c in state["characters"] if c.get('id') == defender_id), None)
        is_one_sided = False
        if defender_char:
            has_re_evasion = False
            if 'special_buffs' in defender_char:
                for buff in defender_char['special_buffs']:
                    if buff.get('name') == "再回避ロック":
                        has_re_evasion = True
                        break

            if defender_char.get('hasActed', False) and not has_re_evasion:
                is_one_sided = True

        state['active_match'] = {
            'is_active': True,
            'match_type': match_type,
            'attacker_id': attacker_id,
            'defender_id': defender_id,
            'targets': targets,
            'attacker_data': {},
            'defender_data': {},
            'opened_by': username,
            'attacker_declared': False,
            'defender_declared': False,
            # ★ Phase 12.1: 一方攻撃フラグを初期化
            'is_one_sided_attack': is_one_sided,
            # ★ Phase 7: Snapshot
            'attacker_snapshot': copy.deepcopy(next((c for c in state["characters"] if c.get('id') == attacker_id), None)),
            'defender_snapshot': copy.deepcopy(defender_char)
        }
        if is_one_sided:
            print(f"[MATCH] One-sided attack detected at match start for room {room}")

    save_specific_room_state(room)

    # 全員にマッチモーダル開催を通知
    socketio.emit('match_modal_opened', {
        'match_type': match_type,
        'attacker_id': attacker_id,
        'defender_id': defender_id,
        'targets': targets,
        'is_resume': is_resume
    }, to=room)

    # ★ 追加: 状態更新もブロードキャストして、クライアントのbattleStateを即時同期させる
    broadcast_state_update(room)

    print(f"[MATCH] {username} opened {match_type} match modal in room {room}")

@socketio.on('sync_match_data')
def handle_sync_match_data(data):
    """
    マッチデータを同期（スキル選択、計算結果など）
    """
    room = data.get('room')
    if not room:
        return

    side = data.get('side')  # 'attacker' or 'defender'
    match_data = data.get('data')

    state = get_room_state(room)

    active_match = state.get('active_match', {})
    if not active_match.get('is_active'):
        return

    # ★ ガード: Duel以外の場合は無視 (Wide Matchのデータを破壊しないように)
    if active_match.get('match_type') != 'duel':
        return

    # データを更新
    if side == 'attacker':
        state['active_match']['attacker_data'] = match_data
    elif side == 'defender':
        state['active_match']['defender_data'] = match_data

    save_specific_room_state(room)

    # 全員にデータ同期を通知
    socketio.emit('match_data_updated', {
        'side': side,
        'data': match_data
    }, to=room)

@socketio.on('close_match_modal')
def handle_close_match_modal(data):
    """
    マッチモーダルを終了（マッチ完了時）
    """
    room = data.get('room')
    if not room:
        return

    state = get_room_state(room)

    # マッチ状態をリセット -> ★ Phase 9: リセットせず一時停止にする（復元可能にするため）
    if 'active_match' in state:
        state['active_match']['is_active'] = False
        # データは保持する
        # state['active_match'] = { ... } # 削除

    save_specific_room_state(room)

    # 全員にモーダル終了を通知
    socketio.emit('match_modal_closed', {}, to=room)

    # ★ 状態更新もブロードキャスト
    broadcast_state_update(room)

    save_specific_room_state(room)

    # 全員にモーダル終了を通知
    socketio.emit('match_modal_closed', {}, to=room)

    print(f"[MATCH] Match modal closed in room {room}")

# ============================================================
# 広域マッチ パネル同期機能
# ============================================================


