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




# ★ Phase 7: Cost extraction helper
def extract_cost_from_text(text):
    """
    使用時効果テキストからコスト記述を抽出する（'[使用時]:MPを5消費。' -> 'MPを5消費'）
    """
    if not text:
        return "なし"
    match = re.search(r'\[使用時\]:?([^\n。]+)', text)
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
    この関数はサーバー側で呼び出され、クライアント側での二重実行を防ぐ。
    """
    active_match = state.get('active_match')
    if not active_match or not active_match.get('is_active'):
        return

    attacker_id = active_match.get('attacker_id')
    defender_id = active_match.get('defender_id')
    attacker_data = active_match.get('attacker_data', {})
    defender_data = active_match.get('defender_data', {})

    command_a = attacker_data.get('final_command', '---')
    command_d = defender_data.get('final_command', '---')
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

    # request_match と同じデータ形式で内部的に処理
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

    # handle_match 内のロジックを直接呼び出す代わりに、
    # request_match イベントをサーバー内部で発火させる
    # ★ 二重実行防止: 既にマッチ実行中なら何もしない
    if active_match.get('match_executing'):
        print(f"[MATCH] Match already executing in room {room}, skipping")
        return

    # 実行中フラグを立てる
    state['active_match']['match_executing'] = True
    save_specific_room_state(room)

    # 最初に受信したクライアントだけが実行するよう、
    # イベント送信前に active_match をクリア (完了したので削除)
    if 'active_match' in state:
        del state['active_match']

    save_specific_room_state(room)
    broadcast_state_update(room)

    # マッチ実行イベントを送信（クライアントが一人だけ処理するよう指示）
    socketio.emit('match_auto_execute', match_data, to=room)
    print(f"[MATCH] Auto-executed match in room {room}")

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
        is_confused = any(b.get('name') == "混乱" for b in actor_char['special_buffs'])
        if is_confused:
            socketio.emit('skill_declaration_result', {
                "prefix": data.get('prefix'),
                "final_command": "混乱により行動できません",
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

    # --- 戦慄ペナルティ計算 ---
    current_senritsu = get_status_value(actor_char, '戦慄')
    senritsu_penalty = min(current_senritsu, 3) if current_senritsu > 0 else 0

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

    total_modifier = power_bonus - senritsu_penalty

    final_command = resolved_command
    # (既存のダメージ計算ロジック)
    base_power = 0
    try:
        base_power = int(skill_data.get('基礎威力', 0))
    except ValueError: base_power = 0
    dice_roll_str = skill_data.get('ダイス威力', "")
    dice_min = 0; dice_max = 0
    dice_match = re.search(r'(\d+)d(\d+)', dice_roll_str)
    if dice_match:
        try:
            num_dice = int(dice_match.group(1))
            num_faces = int(dice_match.group(2))
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

    if total_modifier > 0:
        if ' 【' in final_command: final_command = final_command.replace(' 【', f"+{total_modifier} 【")
        else: final_command += f"+{total_modifier}"
    elif total_modifier < 0:
        if ' 【' in final_command: final_command = final_command.replace(' 【', f"{total_modifier} 【")
        else: final_command += f"{total_modifier}"

    is_one_sided_attack = False
    has_re_evasion = False
    if target_char and 'special_buffs' in target_char:
        for buff in target_char['special_buffs']:
            if buff.get('name') == "再回避ロック":
                has_re_evasion = True
                break

    if (target_char.get('hasActed', False) and not has_re_evasion) or force_unopposed:
        is_one_sided_attack = True

    # --- 結果送信 (通常スキルなので即時発動フラグはFalse) ---
    result_payload = {
        "prefix": data.get('prefix'),
        "final_command": final_command,
        "is_one_sided_attack": is_one_sided_attack,
        "min_damage": min_damage,
        "max_damage": max_damage,
        "is_instant_action": False,
        "is_immediate_skill": False,
        "skill_details": skill_details_payload,
        "senritsu_penalty": senritsu_penalty
    }
    socketio.emit('skill_declaration_result', result_payload, to=request.sid)

    # ★ リファクタリング: active_match に計算結果を保存し、state_updated で同期
    side = 'attacker' if 'attacker' in data.get('prefix', '') else 'defender' if 'defender' in data.get('prefix', '') else None

    if side and state.get('active_match') and state['active_match'].get('is_active'):
        # active_match に計算結果を保存
        side_data_key = f'{side}_data'
        state['active_match'][side_data_key] = {
            'skill_id': skill_id,
            'final_command': final_command,
            'min_damage': min_damage,
            'max_damage': max_damage,
            'is_immediate': False,
            'skill_details': skill_details_payload,
            'senritsu_penalty': senritsu_penalty
        }

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
                has_re_evasion = False
                if 'special_buffs' in defender_char:
                    for buff in defender_char['special_buffs']:
                        if buff.get('name') == "再回避ロック":
                            has_re_evasion = True
                            break

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

        print(f"[MATCH DEBUG] Saved {side} data: {state['active_match'][side_data_key]}")
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


@socketio.on('request_match')
def handle_match(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    state = get_room_state(room)
    command_a = data.get('commandA')
    command_d = data.get('commandD')
    actor_id_a = data.get('actorIdA')
    actor_id_d = data.get('actorIdD')
    actor_name_a = data.get('actorNameA')
    actor_name_d = data.get('actorNameD')

    senritsu_penalty_a = int(data.get('senritsuPenaltyA', 0))
    senritsu_penalty_d = int(data.get('senritsuPenaltyD', 0))

    def roll(cmd_str):
        calc_str = re.sub(r'【.*?】', '', cmd_str).strip()
        details_str = calc_str
        dice_regex = r'(\d+)d(\d+)'
        matches = list(re.finditer(dice_regex, calc_str))
        for match in reversed(matches):
            num_dice = int(match.group(1)); num_faces = int(match.group(2))
            rolls = [random.randint(1, num_faces) for _ in range(num_dice)]
            roll_sum = sum(rolls)
            roll_details = f"({'+'.join(map(str, rolls))})"
            start, end = match.start(), match.end()
            details_str = details_str[:start] + roll_details + details_str[end:]
            calc_str = calc_str[:start] + str(roll_sum) + calc_str[end:]
        try: total = eval(re.sub(r'[^-()\d/*+.]', '', calc_str))
        except: total = 0
        return {"total": total, "details": details_str}

    global all_skill_data
    actor_a_char = next((c for c in state["characters"] if c.get('id') == actor_id_a), None)
    actor_d_char = next((c for c in state["characters"] if c.get('id') == actor_id_d), None)

    # PRE_MATCH 適用関数
    def apply_pre_match_effects(actor, target, skill_data):
        if not skill_data or not actor: return
        try:
            rule_json_str = skill_data.get('特記処理', '{}')
            rule_data = json.loads(rule_json_str)
            effects_array = rule_data.get("effects", [])
            _, logs, changes = process_skill_effects(effects_array, "PRE_MATCH", actor, target, None)

            for (char, type, name, value) in changes:
                if type == "APPLY_STATE":
                    current_val = get_status_value(char, name)
                    _update_char_stat(room, char, name, current_val + value, username=f"[{skill_data.get('デフォルト名称', 'スキル')}]")
                elif type == "APPLY_BUFF":
                    apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                    broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
                elif type == "REMOVE_BUFF":
                    remove_buff(char, name)
        except json.JSONDecodeError: pass

    if actor_a_char and senritsu_penalty_a > 0:
        curr = get_status_value(actor_a_char, '戦慄')
        _update_char_stat(room, actor_a_char, '戦慄', max(0, curr - senritsu_penalty_a), username=f"[{actor_name_a}:戦慄消費]")
    if actor_d_char and senritsu_penalty_d > 0:
        curr = get_status_value(actor_d_char, '戦慄')
        _update_char_stat(room, actor_d_char, '戦慄', max(0, curr - senritsu_penalty_d), username=f"[{actor_name_d}:戦慄消費]")

    skill_id_a = None; skill_data_a = None; effects_array_a = []
    skill_id_d = None; skill_data_d = None; effects_array_d = []
    match_a = re.search(r'【(.*?)\s', command_a)
    match_d = re.search(r'【(.*?)\s', command_d)

    if match_a and actor_a_char:
        skill_id_a = match_a.group(1)
        skill_data_a = all_skill_data.get(skill_id_a)
        if skill_data_a:
            apply_pre_match_effects(actor_a_char, actor_d_char, skill_data_a)
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
            apply_pre_match_effects(actor_d_char, actor_a_char, skill_data_d)
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

    result_a = roll(command_a)
    result_d = roll(command_d)
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

        # ★修正: 効果適用ロジック (即時適用 & 重複防止対応)
        def apply_skill_effects_bidirectional(winner_side, a_char, d_char, a_skill, d_skill, damage_val=0, suppress_actor_self_effect=False):
            effects_a = []; effects_d = []
            if a_skill:
                try: effects_a = json.loads(a_skill.get('特記処理', '{}')).get("effects", [])
                except: pass
            if d_skill:
                try: effects_d = json.loads(d_skill.get('特記処理', '{}')).get("effects", [])
                except: pass

            total_bonus_dmg = 0; all_logs = []

            # 内部関数: 変更内容の即時適用
            def apply_local_changes(changes):
                extra_dmg = 0
                for (char, type, name, value) in changes:
                    if type == "APPLY_STATE":
                        curr = get_status_value(char, name)
                        _update_char_stat(room, char, name, curr + value, username=f"[{name}]")
                    elif type == "SET_STATUS":
                        _update_char_stat(room, char, name, value, username=f"[{name}]")
                    elif type == "CUSTOM_DAMAGE":
                        extra_dmg += value
                    elif type == "APPLY_BUFF":
                        apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                        broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
                    elif type == "REMOVE_BUFF":
                        remove_buff(char, name)
                    elif type == "APPLY_SKILL_DAMAGE_AGAIN":
                        extra_dmg += damage_val
                    elif type == "APPLY_STATE_TO_ALL_OTHERS":
                        orig_target_id = char.get("id")
                        orig_target_type = char.get("type")
                        for other_char in state["characters"]:
                            # ★修正: 敵側（異なるタイプ）のキャラクターに適用
                            if other_char.get("type") != orig_target_type and other_char.get("id") != orig_target_id:
                                curr = get_status_value(other_char, name)
                                _update_char_stat(room, other_char, name, curr + value, username=f"[{name}]")
                    # REGAIN_ACTION はここではハンドルせず、呼び出し元でやるのが一般的だが今回は省略
                return extra_dmg

            # 内部関数: 処理実行と適用
            def run_proc_and_apply(effs, timing, actor, target, skill):
                d, l, c = process_skill_effects(effs, timing, actor, target, skill)

                # ★重複防止: 攻撃者の自己バフ抑制フラグがONの場合、ターゲットが攻撃者自身である変更を除外
                final_changes = []
                if suppress_actor_self_effect and timing in ["WIN", "HIT", "LOSE", "UNOPPOSED"]:
                    # 防御側スキル起因の場合は抑制しない（攻撃者のスキル効果のみ抑制対象とすべきだが、簡易的に攻撃者への変更をカット）
                    # 厳密には「攻撃者のスキル効果による自己バフ」を消すべき。
                    # ここでは a_char (攻撃者) への変更を全てスキップする実装とする
                    for change in c:
                        change_target = change[0]
                        if change_target.get('id') == a_char.get('id'):
                            continue
                        final_changes.append(change)
                else:
                    final_changes = c

                nonlocal total_bonus_dmg
                total_bonus_dmg += d
                all_logs.extend(l)

                # 即時適用
                dmg_val = apply_local_changes(final_changes)
                total_bonus_dmg += dmg_val

            if winner_side == 'attacker':
                # ★順序変更: WIN -> HIT (勝利ボーナスをHITに乗せるため)
                run_proc_and_apply(effects_a, "WIN", a_char, d_char, d_skill)
                run_proc_and_apply(effects_a, "HIT", a_char, d_char, d_skill)
                run_proc_and_apply(effects_d, "LOSE", d_char, a_char, a_skill)
            else:
                run_proc_and_apply(effects_a, "LOSE", a_char, d_char, d_skill)
                # 防御側も WIN -> HIT に統一
                run_proc_and_apply(effects_d, "WIN", d_char, a_char, a_skill)
                run_proc_and_apply(effects_d, "HIT", d_char, a_char, a_skill)

            return total_bonus_dmg, all_logs

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
                        _update_char_stat(room, actor_a_char, "荊棘", max(0, at - bp), username=f"[{skill_data_a.get('デフォルト名称')}]")
                    except ValueError: pass
        if actor_d_char:
            dt = get_status_value(actor_d_char, "荊棘")
            if dt > 0:
                if defender_category in ["物理", "魔法"]:
                    _update_char_stat(room, actor_d_char, "HP", actor_d_char['hp'] - dt, username="[荊棘の自傷]")
                elif defender_category == "防御" and skill_data_d:
                    try:
                        bp = int(skill_data_d.get('基礎威力', 0))
                        _update_char_stat(room, actor_d_char, "荊棘", max(0, dt - bp), username=f"[{skill_data_d.get('デフォルト名称')}]")
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
                bonus_damage, logs = apply_skill_effects_bidirectional('attacker', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
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
                _, logs = apply_skill_effects_bidirectional('defender', actor_a_char, actor_d_char, skill_data_a, skill_data_d)
                log_snippets.extend(logs)
                damage_message = "(ダメージ 0)"
                if log_snippets: damage_message += f" ({' '.join(log_snippets)})"
        elif "守備" in defender_tags and defender_category == "回避":
            if result_a['total'] > result_d['total']:
                grant_win_fp(actor_a_char)
                damage = result_a['total']
                kiretsu = get_status_value(actor_d_char, '亀裂')
                bonus_damage, logs = apply_skill_effects_bidirectional('attacker', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
                log_snippets.extend(logs)
                final_damage = damage + kiretsu + bonus_damage
                if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_a} の勝利！</strong> (回避失敗)"
                damage_message += f"({actor_d_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
            else:
                grant_win_fp(actor_d_char)
                _, logs = apply_skill_effects_bidirectional('defender', actor_a_char, actor_d_char, skill_data_a, skill_data_d)
                if actor_d_char:
                    log_snippets.append("[再回避可能！]")
                    apply_buff(actor_d_char, "再回避ロック", 1, 0, data={"skill_id": skill_id_d})
                log_snippets.extend(logs)
                winner_message = f"<strong> → {actor_name_d} の勝利！</strong> (回避成功)"; damage_message = "(ダメージ 0)"
                if log_snippets: damage_message += f" ({' '.join(log_snippets)})"
        elif result_a['total'] > result_d['total']:
            grant_win_fp(actor_a_char)
            damage = result_a['total']
            if actor_d_char:
                kiretsu = get_status_value(actor_d_char, '亀裂')
                bonus_damage, logs = apply_skill_effects_bidirectional('attacker', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
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
                bonus_damage, logs = apply_skill_effects_bidirectional('defender', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
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
        has_re_evasion = any(b.get('name') == "再回避ロック" for b in actor_a_char.get('special_buffs', []))
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

    _process_end_round_logic(room, username)


def _process_end_round_logic(room, username):
    """
    ラウンド終了時の共通処理（ログ出力、EndRound効果、バフ減少、フラグ更新）
    """
    state = get_room_state(room)

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
        if 'special_buffs' in char and char['special_buffs']:
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

            char['special_buffs'] = active_buffs

    state['is_round_ended'] = True
    state['turn_char_id'] = None  # ★ 手番キャラをクリア（青い光やボタンを消すため）

    # ★ 追加: ラウンド終了時にアクティブマッチも強制終了
    state['active_match'] = None

    broadcast_state_update(room)
    save_specific_room_state(room)

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

            # バフ・フラグ削除
            char['special_buffs'] = []
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
    broadcast_log(room, f"⚠️ GM {username} がマッチを強制終了しました。", 'match-end')

@socketio.on('request_declare_wide_skill_users')
def handle_declare_wide_skill_users(data):
    room = data.get('room')
    wide_user_ids = data.get('wideUserIds', [])

    if not room: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    state = get_room_state(room)

    # 1. フラグの更新
    wide_user_names = []
    for char in state['characters']:
        if char['id'] in wide_user_ids:
            char['isWideUser'] = True
            wide_user_names.append(char['name'])
        else:
            char['isWideUser'] = False

    if wide_user_names:
        broadcast_log(room, f"⚡ 広域スキル使用予約: {', '.join(wide_user_names)}", 'info')
    else:
        broadcast_log(room, f"広域スキル使用者は居ません。通常の速度順で開始します。", 'info')

    # 2. タイムラインの再ソート
    def get_speed_stat(char):
        param = next((p for p in char['params'] if p.get('label') == '速度'), None)
        return int(param.get('value')) if param else 0

    def sort_key(char):
        is_wide = 0 if char.get('isWideUser') else 1
        speed_roll = char.get('speedRoll', 0) # ★ 修正: speedRollがない場合は0
        is_enemy = 1 if char['type'] == 'enemy' else 2
        speed_stat = get_speed_stat(char)
        random_tiebreak = random.random()
        return (is_wide, -speed_roll, is_enemy, -speed_stat, random_tiebreak)

    state['characters'].sort(key=sort_key)
    # ★ 修正: 未配置キャラはタイムラインから除外
    state['timeline'] = [c['id'] for c in state['characters'] if c.get('x', -1) >= 0 and c.get('y', -1) >= 0]

    # ★追加: ここで改めてタイムラインの先頭を手番として確定させる
    if state['timeline']:
        first_id = state['timeline'][0]
        state['turn_char_id'] = first_id
        first_char = next((c for c in state['characters'] if c['id'] == first_id), None)
        first_name = first_char['name'] if first_char else "不明"
        broadcast_log(room, f"Round {state['round']} 開始: 最初の手番は {first_name} です。", 'info')
    else:
        state['turn_char_id'] = None

    broadcast_state_update(room)
    save_specific_room_state(room)

@socketio.on('request_wide_match')
def handle_wide_match(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    state = get_room_state(room)
    actor_id = data.get('actorId'); skill_id = data.get('skillId'); mode = data.get('mode'); command_actor = data.get('commandActor'); defenders_data = data.get('defenders', [])
    actor_char = next((c for c in state["characters"] if c.get('id') == actor_id), None)
    if not actor_char: return
    actor_name = actor_char['name']
    skill_data_actor = all_skill_data.get(skill_id)

    def roll(cmd_str):
        calc_str = re.sub(r'【.*?】', '', cmd_str).strip()
        details_str = calc_str
        dice_regex = r'(\d+)d(\d+)'
        matches = list(re.finditer(dice_regex, calc_str))
        for match in reversed(matches):
            num_dice = int(match.group(1)); num_faces = int(match.group(2))
            rolls = [random.randint(1, num_faces) for _ in range(num_dice)]
            roll_sum = sum(rolls)
            roll_details = f"({'+'.join(map(str, rolls))})"
            start, end = match.start(), match.end()
            details_str = details_str[:start] + roll_details + details_str[end:]
            calc_str = calc_str[:start] + str(roll_sum) + calc_str[end:]
        try: total = eval(re.sub(r'[^-()\d/*+.]', '', calc_str))
        except: total = 0
        return {"total": total, "details": details_str}

    def grant_win_fp(char):
        if not char: return
        curr = get_status_value(char, 'FP')
        _update_char_stat(room, char, 'FP', curr + 1, username="[マッチ勝利]")

    def apply_pre_match_effects(actor, target, skill_data):
        if not skill_data or not actor: return
        try:
            rule_json_str = skill_data.get('特記処理', '{}')
            rule_data = json.loads(rule_json_str)
            effects_array = rule_data.get("effects", [])
            _, logs, changes = process_skill_effects(effects_array, "PRE_MATCH", actor, target, None)
            for (char, type, name, value) in changes:
                if type == "APPLY_STATE":
                    current_val = get_status_value(char, name)
                    _update_char_stat(room, char, name, current_val + value, username=f"[{skill_data.get('デフォルト名称', 'スキル')}]")
                elif type == "APPLY_BUFF":
                    apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                    broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
                elif type == "REMOVE_BUFF":
                    remove_buff(char, name)
        except json.JSONDecodeError: pass

    def resolve_defender_action(def_char, d_skill_id):
        d_skill_data = all_skill_data.get(d_skill_id)
        if not d_skill_data: return "2d6", None
        base_cmd = d_skill_data.get('チャットパレット', '')
        resolved_cmd = resolve_placeholders(base_cmd, def_char.get('params', []))
        power_bonus = 0
        rule_json = d_skill_data.get('特記処理', '{}')
        try:
            rd = json.loads(rule_json)
            power_bonus = calculate_power_bonus(def_char, actor_char, rd)
        except: pass
        buff_bonus = calculate_buff_power_bonus(def_char, actor_char, d_skill_data)
        power_bonus += buff_bonus
        senritsu = get_status_value(def_char, '戦慄')
        penalty = min(senritsu, 3) if senritsu > 0 else 0
        if penalty > 0:
             _update_char_stat(room, def_char, '戦慄', max(0, senritsu - penalty), username=f"[{def_char['name']}:戦慄消費]")
        total_mod = power_bonus - penalty
        phys = get_status_value(def_char, '物理補正'); mag = get_status_value(def_char, '魔法補正')
        final_cmd = resolved_cmd
        if '{物理補正}' in final_cmd: final_cmd = final_cmd.replace('{物理補正}', str(phys))
        elif '{魔法補正}' in final_cmd: final_cmd = final_cmd.replace('{魔法補正}', str(mag))
        if total_mod > 0:
            if ' 【' in final_cmd: final_cmd = final_cmd.replace(' 【', f"+{total_mod} 【")
            else: final_cmd += f"+{total_mod}"
        elif total_mod < 0:
            if ' 【' in final_cmd: final_cmd = final_cmd.replace(' 【', f"{total_mod} 【")
            else: final_cmd += f"{total_mod}"
        return final_cmd, d_skill_data

    # ★修正: 効果適用ロジック (extra_dmg_val を削除)
    def apply_skill_effects_bidirectional(winner_side, a_char, d_char, a_skill, d_skill, damage_val=0, suppress_actor_self_effect=False):
        effects_a = []; effects_d = []
        if a_skill:
            try: effects_a = json.loads(a_skill.get('特記処理', '{}')).get("effects", [])
            except: pass
        if d_skill:
            try: effects_d = json.loads(d_skill.get('特記処理', '{}')).get("effects", [])
            except: pass

        total_bonus_dmg = 0; all_logs = []

        # 内部関数: 変更内容の即時適用
        def apply_local_changes(changes):
            extra_dmg = 0
            for (char, type, name, value) in changes:
                if type == "APPLY_STATE":
                    curr = get_status_value(char, name)
                    _update_char_stat(room, char, name, curr + value, username=f"[{name}]")
                elif type == "SET_STATUS":
                    _update_char_stat(room, char, name, value, username=f"[{name}]")
                elif type == "CUSTOM_DAMAGE":
                    extra_dmg += value
                elif type == "APPLY_BUFF":
                    apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                    broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
                elif type == "REMOVE_BUFF":
                    remove_buff(char, name)
                # 広域での特殊効果対応が必要ならここに追加
            return extra_dmg

        # 内部関数: 処理実行と適用
        def run_proc_and_apply(effs, timing, actor, target, skill):
            d, l, c = process_skill_effects(effs, timing, actor, target, skill)

            # 重複防止: 攻撃者の自己バフ抑制フラグがONの場合、ターゲットが攻撃者自身である変更を除外
            final_changes = []
            if suppress_actor_self_effect and timing in ["WIN", "HIT", "LOSE", "UNOPPOSED"]:
                for change in c:
                    change_target = change[0]
                    # 攻撃者(a_char)への変更をスキップ
                    if change_target.get('id') == a_char.get('id'):
                        continue
                    final_changes.append(change)
            else:
                final_changes = c

            nonlocal total_bonus_dmg
            total_bonus_dmg += d
            all_logs.extend(l)

            # 即時適用
            dmg_val = apply_local_changes(final_changes)
            total_bonus_dmg += dmg_val

        if winner_side == 'attacker':
            # WIN -> HIT
            run_proc_and_apply(effects_a, "WIN", a_char, d_char, d_skill)
            run_proc_and_apply(effects_a, "HIT", a_char, d_char, d_skill)
            run_proc_and_apply(effects_d, "LOSE", d_char, a_char, a_skill)
        else:
            run_proc_and_apply(effects_a, "LOSE", a_char, d_char, d_skill)
            # WIN -> HIT
            run_proc_and_apply(effects_d, "WIN", d_char, a_char, a_skill)
            run_proc_and_apply(effects_d, "HIT", d_char, a_char, a_skill)

        # ★修正: total_bonus_dmg にはすでに extra_dmg 分も含まれているため単独で返す
        return total_bonus_dmg, all_logs

    def process_thorns(char, skill_data):
        if not char or not skill_data: return
        thorns = get_status_value(char, "荊棘")
        if thorns <= 0: return
        cat = skill_data.get("分類", "")
        if cat in ["物理", "魔法"]:
            _update_char_stat(room, char, "HP", get_status_value(char, "HP") - thorns, username="[荊棘の自傷]")
        elif cat == "防御":
            try:
                base_power = int(skill_data.get('基礎威力', 0))
                _update_char_stat(room, char, "荊棘", max(0, thorns - base_power), username=f"[{skill_data.get('デフォルト名称')}]")
            except ValueError: pass

    if skill_data_actor:
        apply_pre_match_effects(actor_char, None, skill_data_actor)
    result_actor = roll(command_actor)
    actor_power = result_actor['total']
    if skill_data_actor:
        try:
            rd = json.loads(skill_data_actor.get('特記処理', '{}'))
            if "即時発動" not in skill_data_actor.get("tags", []):
                for cost in rd.get("cost", []):
                    c_val = int(cost.get("value", 0))
                    if c_val > 0:
                        curr = get_status_value(actor_char, cost.get("type"))
                        _update_char_stat(room, actor_char, cost.get("type"), curr - c_val, username=f"[{skill_data_actor.get('デフォルト名称')}]")
        except: pass
    process_thorns(actor_char, skill_data_actor)
    actor_char['hasActed'] = True

    # ★追加: 広域攻撃実行後はフラグを下ろす
    actor_char['isWideUser'] = False

    if 'used_skills_this_round' not in actor_char: actor_char['used_skills_this_round'] = []
    actor_char['used_skills_this_round'].append(skill_id)
    mode_text = "広域-個別" if mode == 'individual' else "広域-合算"
    skill_display_actor = format_skill_display_from_command(command_actor, skill_id, skill_data_actor)
    broadcast_log(room, f"⚔️ <strong>{actor_name}</strong> {skill_display_actor} の【{mode_text}】攻撃！ (出目: {actor_power})", 'match')

    # === 広域-個別 (Individual) ===
    if mode == 'individual':
        for defender_info in defenders_data:
            if actor_char['hp'] <= 0:
                broadcast_log(room, f"⛔ {actor_name} は倒れたため、攻撃は中断されました。", 'info'); break
            target_id = defender_info.get('id')
            target_char = next((c for c in state["characters"] if c.get('id') == target_id), None)
            if not target_char or target_char['hp'] <= 0: continue
            target_char['hasActed'] = True
            d_skill_id = defender_info.get('skillId')
            d_cmd_from_client = defender_info.get('command')
            if d_cmd_from_client:
                d_cmd = d_cmd_from_client; skill_data_target = all_skill_data.get(d_skill_id)
            else:
                d_cmd, skill_data_target = resolve_defender_action(target_char, d_skill_id)
            if skill_data_target: apply_pre_match_effects(target_char, actor_char, skill_data_target)
            result_target = roll(d_cmd); target_power = result_target['total']
            if skill_data_target:
                try:
                    rd = json.loads(skill_data_target.get('特記処理', '{}'))
                    for cost in rd.get("cost", []):
                        c_val = int(cost.get("value", 0))
                        if c_val > 0:
                            curr = get_status_value(target_char, cost.get("type"))
                            _update_char_stat(room, target_char, cost.get("type"), curr - c_val)
                except: pass
            process_thorns(target_char, skill_data_target)
            if 'used_skills_this_round' not in target_char: target_char['used_skills_this_round'] = []
            if d_skill_id: target_char['used_skills_this_round'].append(d_skill_id)
            msg = ""; d_tags = skill_data_target.get("tags", []) if skill_data_target else []; d_cat = skill_data_target.get("分類", "") if skill_data_target else ""
            skill_display_target = format_skill_display_from_command(d_cmd, d_skill_id, skill_data_target)

            if actor_power > target_power:
                grant_win_fp(actor_char); base_dmg = actor_power
                if "守備" in d_tags and d_cat == "防御": base_dmg = actor_power - target_power; msg = "(軽減)"
                elif "守備" in d_tags and d_cat == "回避": base_dmg = actor_power; msg = "(回避失敗)"

                bonus, logs = apply_skill_effects_bidirectional('attacker', actor_char, target_char, skill_data_actor, skill_data_target, base_dmg)
                final_dmg = base_dmg + bonus

                if any(b.get('name') == "混乱" for b in target_char.get('special_buffs', [])): final_dmg = int(final_dmg * 1.5); msg += " (混乱x1.5)"
                _update_char_stat(room, target_char, 'HP', target_char['hp'] - final_dmg, username=username)
                broadcast_log(room, f"➡ vs {target_char['name']} {skill_display_target} ({target_power}): 命中！ {final_dmg}ダメージ {msg} {' '.join(logs)}", 'match')
            else:
                grant_win_fp(target_char); base_dmg = 0; msg = ""
                if "守備" in d_tags:
                    base_dmg = 0; msg = "(回避成功)" if ("守備" in d_tags and d_cat == "回避") else "(防いだ)"
                else:
                    base_dmg = target_power; msg = "(反撃)"

                bonus, logs = apply_skill_effects_bidirectional('defender', actor_char, target_char, skill_data_actor, skill_data_target, base_dmg)
                final_dmg = base_dmg + bonus

                if any(b.get('name') == "混乱" for b in target_char.get('special_buffs', [])): final_dmg = int(final_dmg * 1.5); msg += "(混乱x1.5)"
                if final_dmg > 0: _update_char_stat(room, actor_char, 'HP', actor_char['hp'] - final_dmg, username="[反撃]"); msg += f" {final_dmg}ダメージ"
                else: msg += " (ダメージなし)"
                broadcast_log(room, f"➡ vs {target_char['name']} {skill_display_target} ({target_power}): {msg} {' '.join(logs)}", 'match')

    # === 広域-合算 (Combined) ===
    elif mode == 'combined':
        total_def_power = 0; defenders_results = []; valid_targets = []
        for defender_info in defenders_data:
            target_id = defender_info.get('id')
            target_char = next((c for c in state["characters"] if c.get('id') == target_id), None)
            if not target_char or target_char['hp'] <= 0: continue
            valid_targets.append({'char': target_char, 'skill_id': defender_info.get('skillId'), 'skill_data': None})
            target_char['hasActed'] = True
            d_skill_id = defender_info.get('skillId'); d_cmd_from_client = defender_info.get('command')
            if d_cmd_from_client: d_cmd = d_cmd_from_client; skill_data_target = all_skill_data.get(d_skill_id)
            else: d_cmd, skill_data_target = resolve_defender_action(target_char, d_skill_id)
            valid_targets[-1]['skill_data'] = skill_data_target
            if skill_data_target: apply_pre_match_effects(target_char, actor_char, skill_data_target)
            if skill_data_target:
                try:
                    rd = json.loads(skill_data_target.get('特記処理', '{}'))
                    for cost in rd.get("cost", []):
                        c_val = int(cost.get("value", 0))
                        if c_val > 0:
                            curr = get_status_value(target_char, cost.get("type"))
                            _update_char_stat(room, target_char, cost.get("type"), curr - c_val)
                except: pass
            process_thorns(target_char, skill_data_target)
            if 'used_skills_this_round' not in target_char: target_char['used_skills_this_round'] = []
            if d_skill_id: target_char['used_skills_this_round'].append(d_skill_id)
            res = roll(d_cmd); total_def_power += res['total']
            skill_display_target = format_skill_display_from_command(d_cmd, d_skill_id, skill_data_target)
            defenders_results.append(f"{target_char['name']}{skill_display_target}({res['total']})")
        broadcast_log(room, f"🛡️ 防御側合計: {total_def_power} [{', '.join(defenders_results)}]", 'info')

        if actor_power > total_def_power:
            grant_win_fp(actor_char); diff_dmg = actor_power - total_def_power
            broadcast_log(room, f"💥 攻撃成功！ 差分ダメージ: {diff_dmg} を全員に与えます。", 'match')

            for i, entry in enumerate(valid_targets):
                target_char = entry['char']
                # 合算モード: 2人目以降は攻撃者自身の自己バフをスキップ
                should_suppress = (i > 0)

                bonus, logs = apply_skill_effects_bidirectional(
                    'attacker', actor_char, target_char, skill_data_actor, entry['skill_data'], diff_dmg,
                    suppress_actor_self_effect=should_suppress
                )

                final_dmg = diff_dmg + bonus; msg = ""
                if logs: msg = f"({' '.join(logs)})"
                if any(b.get('name') == "混乱" for b in target_char.get('special_buffs', [])): final_dmg = int(final_dmg * 1.5); msg += " (混乱)"
                _update_char_stat(room, target_char, 'HP', target_char['hp'] - final_dmg, username=username)
                if msg: broadcast_log(room, f"➡ {target_char['name']}に追加効果: {msg}", 'match')
        else:
            diff_dmg = total_def_power - actor_power; msg = f"🛡️ 防御成功！ (攻撃 {actor_power} vs 防御 {total_def_power})"
            if diff_dmg > 0:
                _update_char_stat(room, actor_char, 'HP', actor_char['hp'] - diff_dmg, username="[カウンター]"); msg += f" ➡ 攻撃者に {diff_dmg} の反撃ダメージ！"
            broadcast_log(room, msg, 'match')

            for i, entry in enumerate(valid_targets):
                target_char = entry['char']; grant_win_fp(target_char)
                should_suppress = (i > 0)

                _, logs = apply_skill_effects_bidirectional(
                    'defender', actor_char, target_char, skill_data_actor, entry['skill_data'], 0,
                    suppress_actor_self_effect=should_suppress
                )
                if logs: broadcast_log(room, f"➡ {target_char['name']}の効果: {' '.join(logs)}", 'match')

    broadcast_state_update(room)
    save_specific_room_state(room)

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

@socketio.on('open_wide_match_modal')
def handle_open_wide_match_modal(data):
    """
    広域攻撃マッチモーダルを開催し、全員に通知
    """
    room = data.get('room')
    if not room:
        return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")

    attacker_id = data.get('attacker_id')
    defender_ids = data.get('defender_ids', [])  # 複数の防御者ID
    mode = data.get('mode', 'individual')  # 'individual' or 'combined'

    state = get_room_state(room)

    # 攻撃者情報取得
    attacker_char = next((c for c in state["characters"] if c.get('id') == attacker_id), None)
    if not attacker_char:
        return

    # 防御者リストを構築
    defenders = []
    for def_id in defender_ids:
        def_char = next((c for c in state["characters"] if c.get('id') == def_id), None)
        if def_char and def_char.get('hp', 0) > 0:
            defenders.append({
                'id': def_id,
                'name': def_char.get('name'),
                'owner': def_char.get('owner'),
                'owner_id': def_char.get('owner_id'),
                'skill_id': None,
                'command': None,
                'declared': False,
                'snapshot': copy.deepcopy(def_char)
            })

    # active_match に広域マッチ状態を設定
    state['active_match'] = {
        'is_active': True,
        'match_type': 'wide',
        'attacker_id': attacker_id,
        'attacker_data': {},
        'attacker_declared': False,
        'attacker_snapshot': copy.deepcopy(attacker_char),
        'defenders': defenders,
        'mode': mode,
        'opened_by': username
    }

    save_specific_room_state(room)
    broadcast_state_update(room)

    print(f"[WIDE_MATCH] {username} opened wide match modal in room {room} with {len(defenders)} defenders")


# ★ コスト精査ヘルパー
def verify_skill_cost(char, skill_d):
    """
    スキル使用に必要なコストが足りているかチェックする
    足りていればTrue, 不足していればFalseと不足情報を返す
    """
    if not skill_d: return True, None

    rule_json_str = skill_d.get('特記処理', '{}')
    try:
        rule_data = json.loads(rule_json_str)
        tags = rule_data.get('tags', skill_d.get('tags', []))
        if "即時発動" in tags:
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


@socketio.on('wide_declare_skill')
def handle_wide_declare_skill(data):
    """
    広域マッチで防御者がスキルを宣言
    """
    room = data.get('room')
    if not room:
        return

    defender_id = data.get('defender_id')
    skill_id = data.get('skill_id')
    command = data.get('command')

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    state = get_room_state(room)
    active_match = state.get('active_match')

    if not active_match or not active_match.get('is_active') or active_match.get('match_type') != 'wide':
        return

    # 権限チェック: GMまたはキャラクター所有者のみ
    from manager.room_manager import is_authorized_for_character
    if not is_authorized_for_character(room, defender_id, username, attribute):
        print(f"[WIDE_MATCH] Unauthorized declaration attempt by {username} for {defender_id}")
        return

    # 対象の防御者を更新
    for defender in active_match.get('defenders', []):
        if defender['id'] == defender_id:
            # ★ コストチェック
            def_char = next((c for c in state['characters'] if c.get('id') == defender_id), None)
            skill_data = all_skill_data.get(skill_id)
            ok, msg = verify_skill_cost(def_char, skill_data)
            if not ok:
                 broadcast_log(room, f"⚠️ コスト不足により {defender['name']} の宣言を拒否: {msg}", 'error')
                 return

            defender['skill_id'] = skill_id
            defender['command'] = command
            # ★ レンジ情報の保存
            defender['min'] = data.get('min')
            defender['max'] = data.get('max')
            defender['declared'] = True
            defender['declared_by'] = username
            print(f"[WIDE_MATCH] Defender {defender['name']} declared skill {skill_id}")
            break

    save_specific_room_state(room)
    broadcast_state_update(room)


@socketio.on('wide_attacker_declare')
def handle_wide_attacker_declare(data):
    """
    広域マッチで攻撃者がスキルと計算結果を宣言
    """
    room = data.get('room')
    if not room:
        return

    skill_id = data.get('skill_id')
    command = data.get('command')

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    state = get_room_state(room)
    active_match = state.get('active_match')

    if not active_match or not active_match.get('is_active') or active_match.get('match_type') != 'wide':
        return

    attacker_id = active_match.get('attacker_id')

    # 権限チェック
    from manager.room_manager import is_authorized_for_character
    if not is_authorized_for_character(room, attacker_id, username, attribute):
        print(f"[WIDE_MATCH] Unauthorized declaration attempt by {username} for attacker")
        return

    # ★ コストチェック
    attacker_char = next((c for c in state['characters'] if c.get('id') == attacker_id), None)
    skill_data = all_skill_data.get(skill_id, {})
    ok, msg = verify_skill_cost(attacker_char, skill_data)
    if not ok:
         broadcast_log(room, f"⚠️ コスト不足により攻撃者の宣言を拒否: {msg}", 'error')
         return

    active_match['attacker_data'] = {
        'skill_id': skill_id,
        'command': command,
        'min': data.get('min'),
        'max': data.get('max')
    }
    active_match['attacker_declared'] = True

    # ★ マッチ不可タグのチェックと強制宣言処理
    skill_data = all_skill_data.get(skill_id, {})
    tags = skill_data.get('tags', [])

    if "マッチ不可" in tags:
        print(f"[WIDE_MATCH] Match Disabled tag detected. Forcing defenders to declare.")
        for defender in active_match.get('defenders', []):
            # 既に宣言済みの人でも上書きするか、未宣言のみにするか。
            # 「強制的に行動不可」なので、未宣言の人を強制完了させるのが自然。
            if not defender.get('declared'):
                defender['skill_id'] = "（対抗不可）"
                defender['command'] = "0"
                defender['declared'] = True
                defender['declared_by'] = "System (Match Disabled)"

        broadcast_log(room, "🚫 [マッチ不可] スキルのため、防御側は行動できません。", 'info')

    print(f"[WIDE_MATCH] Attacker declared skill {skill_id}")

    save_specific_room_state(room)
    broadcast_state_update(room)


@socketio.on('execute_synced_wide_match')
def handle_execute_synced_wide_match(data):
    """
    同期パネルからの広域マッチ実行
    active_matchに保存された宣言データを使用してマッチを実行
    """
    room = data.get('room')
    if not room:
        return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")

    state = get_room_state(room)
    active_match = state.get('active_match')

    if not active_match or not active_match.get('is_active') or active_match.get('match_type') != 'wide':
        print(f"[WIDE_MATCH] No active wide match to execute")
        return

    # Check if all participants have declared
    if not active_match.get('attacker_declared'):
        broadcast_log(room, "⚠️ 攻撃者がまだ宣言していません", 'error')
        return

    defenders = active_match.get('defenders', [])
    undeclared = [d for d in defenders if not d.get('declared')]
    if undeclared:
        broadcast_log(room, f"⚠️ 防御者 {len(undeclared)}人 がまだ宣言していません", 'error')
        return

    # Get attacker data
    attacker_id = active_match.get('attacker_id')
    attacker_data = active_match.get('attacker_data', {})
    attacker_skill_id = attacker_data.get('skill_id')
    attacker_command = attacker_data.get('command')

    attacker_char = next((c for c in state['characters'] if c.get('id') == attacker_id), None)
    if not attacker_char:
        return

    attacker_skill_data = all_skill_data.get(attacker_skill_id)
    mode = active_match.get('mode', 'individual')

    # ★ コスト消費処理ヘルパー
    def consume_skill_cost(char, skill_d, skill_id_log):
        if not skill_d: return
        rule_json_str = skill_d.get('特記処理', '{}')
        try:
            rule_data = json.loads(rule_json_str)
            tags = rule_data.get('tags', skill_d.get('tags', []))
            if "即時発動" not in tags:
                for cost in rule_data.get("cost", []):
                    c_type = cost.get("type")
                    c_val = int(cost.get("value", 0))
                    if c_val > 0 and c_type:
                        curr = get_status_value(char, c_type)
                        # デバッグログ
                        print(f"[DEBUG_COST] {char['name']} {c_type} val:{c_val} curr:{curr} -> new:{max(0, curr - c_val)}")

                        if curr == 0:
                             print(f"[DEBUG_DUMP] keys: {list(char.keys())}")
                             if c_type == 'MP':
                                 print(f"[DEBUG_DUMP] MP raw: {char.get('mp')}")
                             if 'states' in char:
                                 print(f"[DEBUG_DUMP] states: {[s.get('name') for s in char['states']]}")

                        new_val = max(0, curr - c_val)
                        _update_char_stat(room, char, c_type, new_val, username=f"[{skill_id_log}]")

                        # 明示的にチャットに通知（消費確認用）
                        broadcast_log(room, f"{char['name']} は {c_type}を{c_val}消費しました (残:{new_val})", 'system')

                        # 更新確認
                        check_val = get_status_value(char, c_type)
                        print(f"[DEBUG_CHECK] After update: {check_val}")

        except Exception as e:
            print(f"[COST] Error consuming cost for {char['name']}: {e}")
            import traceback
            traceback.print_exc()

    # 攻撃者のコスト消費
    consume_skill_cost(attacker_char, attacker_skill_data, attacker_skill_id)

    # 全防御者のコスト消費
    for def_data in defenders:
        def_id = def_data.get('id')
        def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
        if def_char:
             def_skill_id = def_data.get('skill_id')
             def_skill_data = all_skill_data.get(def_skill_id)
             consume_skill_cost(def_char, def_skill_data, def_skill_id)

    # 使用スキル記録
    if 'used_skills_this_round' not in attacker_char:
        attacker_char['used_skills_this_round'] = []
    attacker_char['used_skills_this_round'].append(attacker_skill_id)

    # Roll function
    def roll(cmd_str):
        calc_str = re.sub(r'【.*?】', '', cmd_str).strip()
        details_str = calc_str
        dice_regex = r'(\d+)d(\d+)'
        matches = list(re.finditer(dice_regex, calc_str))
        for match in reversed(matches):
            num_dice = int(match.group(1))
            num_faces = int(match.group(2))
            rolls = [random.randint(1, num_faces) for _ in range(num_dice)]
            roll_sum = sum(rolls)
            roll_details = f"({'+'.join(map(str, rolls))})"
            start, end = match.start(), match.end()
            details_str = details_str[:start] + roll_details + details_str[end:]
            calc_str = calc_str[:start] + str(roll_sum) + calc_str[end:]
        try:
            total = eval(re.sub(r'[^-()\d/*+.]', '', calc_str))
        except:
            total = 0
        return {"total": total, "details": details_str}

    # Execute match
    broadcast_log(room, f"⚔️ === 広域マッチ開始 ({mode}モード) ===", 'match-start')
    broadcast_log(room, f"🗡️ 攻撃者: {attacker_char['name']} [{attacker_skill_id}]", 'info')

    attacker_roll = roll(attacker_command)
    broadcast_log(room, f"   → ロール: {attacker_roll['details']} = {attacker_roll['total']}", 'dice')

    results = []

    # ★ 共通: 攻撃者スキル効果の準備
    attacker_effects = []
    if attacker_skill_data:
        rule_json = attacker_skill_data.get('特記処理', '{}')
        try:
            d = json.loads(rule_json)
            attacker_effects = d.get('effects', [])
        except: pass

    # ★ 共通: 効果適用ヘルパー関数
    def apply_local_changes(changes):
        extra = 0
        for (char, type, name, value) in changes:
            if type == "APPLY_STATE":
                curr = get_status_value(char, name)
                _update_char_stat(room, char, name, curr + value, username=f"[{attacker_skill_id}]")
            elif type == "APPLY_BUFF":
                apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
            elif type == "CUSTOM_DAMAGE":
                extra += value
            elif type == "APPLY_STATE_TO_ALL_OTHERS":
                orig_target_id = char.get("id")
                orig_target_type = char.get("type")
                for other_char in state["characters"]:
                    # 同じ陣営の他キャラクターに適用 (自分以外)
                    if other_char.get("type") == orig_target_type and other_char.get("id") != orig_target_id:
                        curr = get_status_value(other_char, name)
                        _update_char_stat(room, other_char, name, curr + value, username=f"[{name}]")
        return extra

    # ★ 合算モードの場合は別処理
    if mode == 'combined':
        # 全防御者のロールを先に実行
        defender_rolls = []
        valid_defenders = []
        total_defender_roll = 0

        for def_data in defenders:
            def_id = def_data.get('id')
            def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
            if not def_char:
                continue

            def_skill_id = def_data.get('skill_id')
            def_command = def_data.get('command', '2d6')
            def_roll_result = roll(def_command)

            defender_rolls.append({
                'char': def_char,
                'skill_id': def_skill_id,
                'roll': def_roll_result
            })
            valid_defenders.append(def_char)
            total_defender_roll += def_roll_result['total']

            broadcast_log(room, f"🛡️ {def_char['name']} [{def_skill_id}]: {def_roll_result['details']} = {def_roll_result['total']}", 'dice')

        broadcast_log(room, f"📊 防御者合計: {total_defender_roll} vs 攻撃者: {attacker_roll['total']}", 'info')

        # 勝敗判定
        if attacker_roll['total'] > total_defender_roll:
            # 攻撃者勝利: 差分を全防御者に均等ダメージ
            diff = attacker_roll['total'] - total_defender_roll
            broadcast_log(room, f"   → 🗡️ 攻撃者勝利! 差分: {diff}", 'match-result')

            for dr in defender_rolls:
                def_char = dr['char']
                results.append({'defender': def_char['name'], 'result': 'win', 'damage': diff})
                current_hp = get_status_value(def_char, 'HP')
                new_hp = max(0, current_hp - diff)
                _update_char_stat(room, def_char, 'HP', new_hp, username=f"[{attacker_skill_id}]")
                broadcast_log(room, f"   → {def_char['name']} に {diff} ダメージ", 'damage')

                # ★ 合算モードでもスキル効果を適用 (荊棘飛散など)
                if attacker_effects:
                    dmg_bonus, logs, changes = process_skill_effects(attacker_effects, "HIT", attacker_char, def_char, None)
                    for log_msg in logs:
                        broadcast_log(room, log_msg, 'skill-effect')
                    diff_bonus = apply_local_changes(changes)
                    if diff_bonus > 0:
                        # 追加ダメージがあればさらに適用
                        current_hp = get_status_value(def_char, 'HP') # 再取得
                        new_hp = max(0, current_hp - diff_bonus)
                        _update_char_stat(room, def_char, 'HP', new_hp, username=f"[{attacker_skill_id}追加]")
                        broadcast_log(room, f"   → {def_char['name']} に追加 {diff_bonus} ダメージ", 'damage')

        elif total_defender_roll > attacker_roll['total']:
            # 防御者勝利: 差分を攻撃者にダメージ
            diff = total_defender_roll - attacker_roll['total']
            broadcast_log(room, f"   → 🛡️ 防御者勝利! 差分: {diff}", 'match-result')

            current_hp = get_status_value(attacker_char, 'HP')
            new_hp = max(0, current_hp - diff)
            _update_char_stat(room, attacker_char, 'HP', new_hp, username="[防御者勝利]")
            broadcast_log(room, f"   → {attacker_char['name']} に {diff} ダメージ", 'damage')

            for dr in defender_rolls:
                results.append({'defender': dr['char']['name'], 'result': 'lose', 'damage': diff})
        else:
            # 引き分け
            broadcast_log(room, f"   → 引き分け", 'match-result')
            for dr in defender_rolls:
                results.append({'defender': dr['char']['name'], 'result': 'draw', 'damage': 0})

    else:
        # ★ 個別モード: 従来の処理
        for def_data in defenders:
            def_id = def_data.get('id')
            def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
            if not def_char:
                continue

            def_skill_id = def_data.get('skill_id')
            def_command = def_data.get('command', '2d6')

            def_roll = roll(def_command)

            # Determine winner
            attacker_total = attacker_roll['total']
            defender_total = def_roll['total']

            if attacker_total > defender_total:
                winner = 'attacker'
                # ★ 修正: 個別モードでは勝者のロール結果がそのままダメージ
                damage = attacker_total  # 攻撃者のロール結果がダメージ
                results.append({'defender': def_char['name'], 'result': 'win', 'damage': damage})
                broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']}", 'dice')
                broadcast_log(room, f"   → 🗡️ 攻撃者勝利! ダメージ: {damage}", 'match-result')

                # 攻撃者効果適用

                # 攻撃者効果適用
                if attacker_effects:
                    # HITタイミング
                    dmg_bonus, logs, changes = process_skill_effects(attacker_effects, "HIT", attacker_char, def_char, None)
                    # logs は文字列のリスト
                    for log_msg in logs:
                        broadcast_log(room, log_msg, 'skill-effect')
                    damage += apply_local_changes(changes) # 追加ダメージ加算

                # Apply damage
                current_hp = get_status_value(def_char, 'HP')
                new_hp = max(0, current_hp - damage)
                _update_char_stat(room, def_char, 'HP', new_hp, username=f"[{attacker_skill_id}]")

            elif defender_total > attacker_total:
                winner = 'defender'
                # ★ 修正: 個別モードでは勝者のロール結果がそのままダメージ
                damage = defender_total  # 防御者のロール結果がダメージ
                results.append({'defender': def_char['name'], 'result': 'lose', 'damage': damage})
                broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']}", 'dice')
                broadcast_log(room, f"   → 🛡️ 防御者勝利! ダメージ: {damage}", 'match-result')

                # Apply damage to attacker (only in individual mode)
                current_hp = get_status_value(attacker_char, 'HP')
                new_hp = max(0, current_hp - damage)
                _update_char_stat(room, attacker_char, 'HP', new_hp, username=f"[{def_skill_id}]")
            else:
                results.append({'defender': def_char['name'], 'result': 'draw', 'damage': 0})
                broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']}", 'dice')
                broadcast_log(room, f"   → 引き分け", 'match-result')

    broadcast_log(room, f"⚔️ === 広域マッチ終了 ===", 'match-end')

    # Update hasActed flags
    attacker_char['hasActed'] = True

    # ★ マッチ不可の場合、防御側は行動済みにならない
    no_defender_acted = False
    attacker_tags = attacker_skill_data.get('tags', []) if attacker_skill_data else []
    if 'マッチ不可' in attacker_tags:
        no_defender_acted = True
        print(f"[WIDE_MATCH] マッチ不可 tag detected - defender won't be marked as acted")

    for def_data in defenders:
        def_id = def_data.get('id')
        def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
        if def_char and not no_defender_acted:
            def_char['hasActed'] = True

    # Clear active match
    state['active_match'] = None

    # ★ ラウンド終了タグの処理（早期リターンせず通常フローを通る）
    round_end_requested = False
    if 'ラウンド終了' in attacker_tags:
        for c in state['characters']:
            c['hasActed'] = True
        broadcast_log(room, f"[{attacker_skill_id}] の効果でラウンドが強制終了します。", 'round')
        round_end_requested = True
        # ★ 早期リターンを削除し、通常の保存・ブロードキャストを通る

    # Advance to next turn directly
    timeline = state.get('timeline', [])
    current_id = state.get('turn_char_id')

    next_id = None
    if timeline:
        current_idx = -1
        if current_id in timeline:
            current_idx = timeline.index(current_id)

        # Search for next actor
        for i in range(current_idx + 1, len(timeline)):
            cid = timeline[i]
            char = next((c for c in state['characters'] if c['id'] == cid), None)
            if char and char.get('hp', 0) > 0 and not char.get('hasActed', False):
                next_id = cid
                break

    if next_id:
        state['turn_char_id'] = next_id
        next_char = next((c for c in state['characters'] if c['id'] == next_id), None)
        char_name = next_char['name'] if next_char else "不明"
        broadcast_log(room, f"手番が {char_name} に移りました。", 'info')
    else:
        state['turn_char_id'] = None
        broadcast_log(room, "全てのキャラクターが行動を終了しました。ラウンド終了処理を行ってください。", 'info')

    save_specific_room_state(room)
    broadcast_state_update(room)

    print(f"[WIDE_MATCH] Executed wide match: {len(results)} defenders processed")

    # ★ ラウンド終了タグがあった場合、通常の保存・ブロードキャスト後にラウンド終了処理を実行
    if round_end_requested:
        _process_end_round_logic(room, f"System [{attacker_skill_id}]")
