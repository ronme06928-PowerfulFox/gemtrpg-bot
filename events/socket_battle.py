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

    if not actor_id or not skill_id:
        return

    state = get_room_state(room)

    # 実データの取得
    original_actor_char = next((c for c in state["characters"] if c.get('id') == actor_id), None)
    skill_data = all_skill_data.get(skill_id)

    original_target_char = None
    if target_id:
        original_target_char = next((c for c in state["characters"] if c.get('id') == target_id), None)

    if not original_actor_char or not skill_data:
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
        print(f"❌ 特記処理(宣言)のJSONパースエラー: {e} (スキルID: {skill_id})")
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
        "使用時効果": skill_data.get("使用時効果", ""),
        "発動時効果": skill_data.get("発動時効果", ""),
        "特記": skill_data.get("特記", "")
    }

    # =========================================================
    #  ★ パターンA: 即時発動スキル (宝石の加護など)
    # =========================================================
    if is_immediate_skill:
        if is_commit:
            # --- 確定実行 (Declareボタン押下時) ---
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
                    socketio.emit('request_end_round', {"room": room})
                    broadcast_log(room, f"[{skill_id}] の効果でラウンドが強制終了します。", 'round')

            # 3. 使用記録
            if 'used_skills_this_round' not in original_actor_char:
                original_actor_char['used_skills_this_round'] = []
            original_actor_char['used_skills_this_round'].append(skill_id)

            # 4. 保存
            broadcast_state_update(room)
            save_specific_room_state(room)

            # 5. クライアントへ応答 (リセット指示)
            socketio.emit('skill_declaration_result', {
                "prefix": data.get('prefix'),
                "final_command": "--- (効果発動完了) ---",
                "is_one_sided_attack": False,
                "min_damage": 0,
                "max_damage": 0,
                "is_instant_action": True, # クライアント側で欄をリセットさせる
                "is_immediate_skill": True,
                "skill_details": skill_details_payload,
                "senritsu_penalty": 0
            }, to=request.sid)

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
    socketio.emit('skill_declaration_result', {
        "prefix": data.get('prefix'),
        "final_command": final_command,
        "is_one_sided_attack": is_one_sided_attack,
        "min_damage": min_damage,
        "max_damage": max_damage,
        "is_instant_action": False,
        "is_immediate_skill": False,
        "skill_details": skill_details_payload,
        "senritsu_penalty": senritsu_penalty
    }, to=request.sid)


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

    # ★ PRE_MATCH 適用関数 (REMOVE_BUFF対応)
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
                elif type == "REMOVE_BUFF": # ★対応追加
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
    if actor_d_char: actor_d_char['hasActed'] = True
    bonus_damage = 0; log_snippets = []; changes = []
    is_one_sided = command_d.strip() == "【一方攻撃（行動済）】" or command_a.strip() == "【一方攻撃（行動済）】"

    try:
        def apply_changes(changes_list, actor_skill_id, defender_skill_id, base_damage=0):
            extra_damage_from_effects = 0
            regain_action = False
            actor_skill_name = "スキル"
            if actor_skill_id and all_skill_data.get(actor_skill_id):
                actor_skill_name = all_skill_data[actor_skill_id].get('デフォルト名称', actor_skill_id)
            elif defender_skill_id and all_skill_data.get(defender_skill_id):
                 actor_skill_name = all_skill_data[defender_skill_id].get('デフォルト名称', defender_skill_id)

            for (char, type, name, value) in changes_list:
                if type == "APPLY_STATE":
                    curr = get_status_value(char, name)
                    _update_char_stat(room, char, name, curr + value, username=f"[{actor_skill_name}]")
                elif type == "SET_STATUS":
                    _update_char_stat(room, char, name, value, username=f"[{actor_skill_name}]")
                elif type == "CUSTOM_DAMAGE":
                    extra_damage_from_effects += value
                elif type == "APPLY_BUFF":
                    apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                    broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
                elif type == "REMOVE_BUFF": # ★★★ ここが重要: バフ消費時の削除処理 ★★★
                    remove_buff(char, name)
                elif type == "APPLY_SKILL_DAMAGE_AGAIN":
                    extra_damage_from_effects += base_damage
                elif type == "APPLY_STATE_TO_ALL_OTHERS":
                    orig_target_id = char.get("id")
                    for other_char in state["characters"]:
                        if other_char.get("type") == char.get("type") and other_char.get("id") != orig_target_id:
                            curr = get_status_value(other_char, name)
                            _update_char_stat(room, other_char, name, curr + value, username=f"[{actor_skill_name}]")
                elif type == "REGAIN_ACTION":
                    regain_action = True
            return extra_damage_from_effects, regain_action

        def grant_win_fp(char):
            if not char: return
            curr = get_status_value(char, 'FP')
            _update_char_stat(room, char, 'FP', curr + 1, username="[マッチ勝利]")

        damage = 0; final_damage = 0; extra_skill_damage = 0
        attacker_tags = skill_data_a.get("tags", []) if skill_data_a else []
        defender_tags = skill_data_d.get("tags", []) if skill_data_d else []
        attacker_category = skill_data_a.get("分類", "") if skill_data_a else ""
        defender_category = skill_data_d.get("分類", "") if skill_data_d else ""

        # 荊棘
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
                    bd_un, log_un, chg_un = process_skill_effects(effects_array_a, "UNOPPOSED", actor_a_char, actor_d_char, skill_data_d)
                    bd_hit, log_hit, chg_hit = process_skill_effects(effects_array_a, "HIT", actor_a_char, actor_d_char, skill_data_d)
                    bonus_damage = bd_un + bd_hit; log_snippets.extend(log_un + log_hit); changes = chg_un + chg_hit
                    extra_skill_damage, _ = apply_changes(changes, skill_id_a, skill_id_d, damage)
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
                bd_win, log_win, chg_win = process_skill_effects(effects_array_a, "WIN", actor_a_char, actor_d_char, skill_data_d)
                bd_hit, log_hit, chg_hit = process_skill_effects(effects_array_a, "HIT", actor_a_char, actor_d_char, skill_data_d)
                bd_lose, log_lose, chg_lose = process_skill_effects(effects_array_d, "LOSE", actor_d_char, actor_a_char, skill_data_a)
                bonus_damage = bd_win + bd_hit + bd_lose; log_snippets.extend(log_win + log_hit + log_lose); changes = chg_win + chg_hit + chg_lose
                extra_skill_damage, _ = apply_changes(changes, skill_id_a, skill_id_d, result_a['total'])
                final_damage = damage + kiretsu + bonus_damage + extra_skill_damage
                if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_a} の勝利！</strong> (ダメージ軽減)"
                damage_message += f"(差分 {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + (f"+ [追加攻撃 {extra_skill_damage}] " if extra_skill_damage > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
            else:
                grant_win_fp(actor_d_char)
                winner_message = f"<strong> → {actor_name_d} の勝利！</strong> (防御成功)"
                bd_lose, log_lose, chg_lose = process_skill_effects(effects_array_a, "LOSE", actor_a_char, actor_d_char, skill_data_d)
                bd_win, log_win, chg_win = process_skill_effects(effects_array_d, "WIN", actor_d_char, actor_a_char, skill_data_a)
                changes = chg_lose + chg_win; apply_changes(changes, skill_id_a, skill_id_d)
                log_snippets.extend(log_lose + log_win); damage_message = "(ダメージ 0)"
                if log_snippets: damage_message += f" ({' '.join(log_snippets)})"
        elif "守備" in defender_tags and defender_category == "回避":
            if result_a['total'] > result_d['total']:
                grant_win_fp(actor_a_char)
                damage = result_a['total']
                kiretsu = get_status_value(actor_d_char, '亀裂')
                bd_hit, log_hit, chg_hit = process_skill_effects(effects_array_a, "HIT", actor_a_char, actor_d_char, skill_data_d)
                bd_lose, log_lose, chg_lose = process_skill_effects(effects_array_d, "LOSE", actor_d_char, actor_a_char, skill_data_a)
                bonus_damage = bd_hit + bd_lose; log_snippets.extend(log_hit + log_lose); changes = chg_hit + chg_lose
                extra_skill_damage, _ = apply_changes(changes, skill_id_a, skill_id_d, damage)
                final_damage = damage + kiretsu + bonus_damage + extra_skill_damage
                if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_a} の勝利！</strong> (回避失敗)"
                damage_message += f"({actor_d_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + (f"+ [追加攻撃 {extra_skill_damage}] " if extra_skill_damage > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
            else:
                grant_win_fp(actor_d_char)
                bd_lose, log_lose, chg_lose = process_skill_effects(effects_array_a, "LOSE", actor_a_char, actor_d_char, skill_data_d)
                bd_win, log_win, chg_win = process_skill_effects(effects_array_d, "WIN", actor_d_char, actor_a_char, skill_data_a)
                changes = chg_lose + chg_win
                _, regain = apply_changes(changes, skill_id_a, skill_id_d)
                if actor_d_char:
                    log_snippets.append("[再回避可能！]")
                    apply_buff(actor_d_char, "再回避ロック", 1, 0, data={"skill_id": skill_id_d})
                log_snippets.extend(log_lose + log_win); winner_message = f"<strong> → {actor_name_d} の勝利！</strong> (回避成功)"; damage_message = "(ダメージ 0)"
                if log_snippets: damage_message += f" ({' '.join(log_snippets)})"
        elif result_a['total'] > result_d['total']:
            grant_win_fp(actor_a_char)
            damage = result_a['total']
            if actor_d_char:
                kiretsu = get_status_value(actor_d_char, '亀裂')
                bd_win, log_win, chg_win = process_skill_effects(effects_array_a, "WIN", actor_a_char, actor_d_char, skill_data_d)
                bd_hit, log_hit, chg_hit = process_skill_effects(effects_array_a, "HIT", actor_a_char, actor_d_char, skill_data_d)
                bd_lose, log_lose, chg_lose = process_skill_effects(effects_array_d, "LOSE", actor_d_char, actor_a_char, skill_data_a)
                bonus_damage = bd_win + bd_hit + bd_lose; log_snippets.extend(log_win + log_hit + log_lose); changes = chg_win + chg_hit + chg_lose
                extra_skill_damage, _ = apply_changes(changes, skill_id_a, skill_id_d, damage)
                final_damage = damage + kiretsu + bonus_damage + extra_skill_damage
                if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_a} の勝利！</strong>"
                damage_message += f"({actor_d_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + (f"+ [追加攻撃 {extra_skill_damage}] " if extra_skill_damage > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
        elif result_d['total'] > result_a['total']:
            grant_win_fp(actor_d_char)
            damage = result_d['total']
            if actor_a_char:
                kiretsu = get_status_value(actor_a_char, '亀裂')
                bd_win, log_win, chg_win = process_skill_effects(effects_array_d, "WIN", actor_d_char, actor_a_char, skill_data_a)
                bd_hit, log_hit, chg_hit = process_skill_effects(effects_array_d, "HIT", actor_d_char, actor_a_char, skill_data_a)
                bd_lose, log_lose, chg_lose = process_skill_effects(effects_array_a, "LOSE", actor_a_char, actor_d_char, skill_data_d)
                bonus_damage = bd_win + bd_hit + bd_lose; log_snippets.extend(log_win + log_hit + log_lose); changes = chg_win + chg_hit + chg_lose
                extra_skill_damage, _ = apply_changes(changes, skill_id_a, skill_id_d, damage)
                final_damage = damage + kiretsu + bonus_damage + extra_skill_damage
                if any(b.get('name') == "混乱" for b in actor_a_char.get('special_buffs', [])):
                    final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                _update_char_stat(room, actor_a_char, 'HP', actor_a_char['hp'] - final_damage, username=username)
                winner_message = f"<strong> → {actor_name_d} の勝利！</strong>"
                damage_message += f"({actor_a_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + (f"+ [追加攻撃 {extra_skill_damage}] " if extra_skill_damage > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
        else:
            winner_message = '<strong> → 引き分け！</strong> (ダメージなし)'
            bd_end_a, log_end_a, chg_end_a = process_skill_effects(effects_array_a, "END_MATCH", actor_a_char, actor_d_char, skill_data_d)
            bd_end_d, log_end_d, chg_end_d = process_skill_effects(effects_array_d, "END_MATCH", actor_d_char, actor_a_char, skill_data_a)
            changes = chg_end_a + chg_end_d; apply_changes(changes, skill_id_a, skill_id_d); log_snippets.extend(log_end_a + log_end_d)
            if log_snippets: winner_message += f" ({' '.join(log_snippets)})"

    except TypeError as e:
        print("--- ▼▼▼ エラーをキャッチしました ▼▼▼ ---", flush=True)
        print(f"エラー内容: {e}", flush=True)
        raise e

    # cleanup_one_time_buffs の呼び出しは削除

    skill_display_a = format_skill_display_from_command(command_a, skill_id_a, skill_data_a)
    skill_display_d = format_skill_display_from_command(command_d, skill_id_d, skill_data_d)
    match_log = f"<strong>{actor_name_a}</strong> {skill_display_a} (<span class='dice-result-total'>{result_a['total']}</span>) vs <strong>{actor_name_d}</strong> {skill_display_d} (<span class='dice-result-total'>{result_d['total']}</span>) | {winner_message} {damage_message}"
    broadcast_log(room, match_log, 'match')
    broadcast_state_update(room)
    save_specific_room_state(room)


#ラウンドの開始処理
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
        # === ▼▼▼ 修正点 (フェーズ4c) ▼▼▼ ===

        char['isWideUser'] = False

        # 1. (既存) 行動済みフラグをリセット
        char['hasActed'] = False

        # 2. (既存) 「使用済みスキル」リストをリセット
        char['used_skills_this_round'] = []

        # 3. (新規) 「再回避ロック」 バフを削除
        if 'special_buffs' in char:
            remove_buff(char, "再回避ロック")

        # === ▲▲▲ 修正ここまで ▲▲▲ ===

        base_speed = get_speed_stat(char)
        roll = random.randint(1, 6)
        stat_bonus = base_speed // 6
        char['speedRoll'] = roll + stat_bonus
        log_detail = f"{char['name']}: 1d6({roll}) + {stat_bonus} = <span class='dice-result-total'>{char['speedRoll']}</span>"
        broadcast_log(room, log_detail, 'dice')

    def sort_key(char):
        speed_roll = char['speedRoll']
        is_enemy = 1 if char['type'] == 'enemy' else 2
        speed_stat = get_speed_stat(char)
        random_tiebreak = random.random()
        return (-speed_roll, is_enemy, -speed_stat, random_tiebreak)

    state['characters'].sort(key=sort_key)
    state['timeline'] = [c['id'] for c in state['characters']]

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

        broadcast_log(room, f"--- {username} が全キャラクターの状態をリセットしました ---", 'round')

    broadcast_state_update(room)
    save_specific_room_state(room)

# === ▼▼▼ 追加: 広域スキル使用者宣言処理 ▼▼▼
@socketio.on('request_declare_wide_skill_users')
def handle_declare_wide_skill_users(data):
    room = data.get('room')
    wide_user_ids = data.get('wideUserIds', []) # 広域を使用するキャラIDのリスト

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
        broadcast_log(room, f"⚡ 広域スキル使用宣言: {', '.join(wide_user_names)}", 'info')
    else:
        broadcast_log(room, f"広域スキル使用者は居ません。通常の速度順で開始します。", 'info')

    # 2. タイムラインの再ソート
    # 優先順位:
    # 1. isWideUser (Trueが先)
    # 2. speedRoll (高い順)
    # 3. is_enemy (敵が先 ※既存ロジック踏襲)
    # 4. speed_stat (高い順)

    def get_speed_stat(char):
        param = next((p for p in char['params'] if p.get('label') == '速度'), None)
        return int(param.get('value')) if param else 0

    def sort_key(char):
        is_wide = 0 if char.get('isWideUser') else 1 # 0(True) < 1(False) なので昇順ソートならこれでOK
        speed_roll = char['speedRoll']
        is_enemy = 1 if char['type'] == 'enemy' else 2
        speed_stat = get_speed_stat(char)
        # ランダム要素は再計算せず、既存の順序を維持したいが簡易的に再生成
        random_tiebreak = random.random()

        # 降順にしたい項目はマイナスをつける
        return (is_wide, -speed_roll, is_enemy, -speed_stat, random_tiebreak)

    state['characters'].sort(key=sort_key)
    state['timeline'] = [c['id'] for c in state['characters']]

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
                    curr = get_status_value(char, name)
                    _update_char_stat(room, char, name, curr + value, username=f"[{skill_data.get('デフォルト名称', 'スキル')}]")
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

    def apply_skill_effects_bidirectional(winner_side, a_char, d_char, a_skill, d_skill, damage_val=0):
        effects_a = []; effects_d = []
        if a_skill:
            try: effects_a = json.loads(a_skill.get('特記処理', '{}')).get("effects", [])
            except: pass
        if d_skill:
            try: effects_d = json.loads(d_skill.get('特記処理', '{}')).get("effects", [])
            except: pass
        total_bonus_dmg = 0; all_logs = []; all_changes = []
        def run_proc(effs, timing, actor, target, skill):
            d, l, c = process_skill_effects(effs, timing, actor, target, skill)
            nonlocal total_bonus_dmg
            total_bonus_dmg += d
            all_logs.extend(l)
            all_changes.extend(c)
        if winner_side == 'attacker':
            run_proc(effects_a, "HIT", a_char, d_char, d_skill)
            run_proc(effects_a, "WIN", a_char, d_char, d_skill)
            run_proc(effects_d, "LOSE", d_char, a_char, a_skill)
        else:
            run_proc(effects_a, "LOSE", a_char, d_char, d_skill)
            run_proc(effects_d, "HIT", d_char, a_char, a_skill)
            run_proc(effects_d, "WIN", d_char, a_char, a_skill)
        extra_dmg_val = 0
        for (char, type, name, value) in all_changes:
            if type == "APPLY_STATE":
                curr = get_status_value(char, name)
                _update_char_stat(room, char, name, curr + value, username=f"[{name}]")
            elif type == "SET_STATUS":
                _update_char_stat(room, char, name, value, username=f"[{name}]")
            elif type == "CUSTOM_DAMAGE":
                extra_dmg_val += value
            elif type == "APPLY_BUFF":
                apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
            elif type == "REMOVE_BUFF": # ★ここでもREMOVE_BUFF対応
                remove_buff(char, name)
        return total_bonus_dmg + extra_dmg_val, all_logs

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
    if 'used_skills_this_round' not in actor_char: actor_char['used_skills_this_round'] = []
    actor_char['used_skills_this_round'].append(skill_id)
    mode_text = "広域-個別" if mode == 'individual' else "広域-合算"
    skill_display_actor = format_skill_display_from_command(command_actor, skill_id, skill_data_actor)
    broadcast_log(room, f"⚔️ <strong>{actor_name}</strong> {skill_display_actor} の【{mode_text}】攻撃！ (出目: {actor_power})", 'match')

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
            for entry in valid_targets:
                target_char = entry['char']
                bonus, logs = apply_skill_effects_bidirectional('attacker', actor_char, target_char, skill_data_actor, entry['skill_data'], diff_dmg)
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
            for entry in valid_targets:
                target_char = entry['char']; grant_win_fp(target_char)
                _, logs = apply_skill_effects_bidirectional('defender', actor_char, target_char, skill_data_actor, entry['skill_data'], 0)
                if logs: broadcast_log(room, f"➡ {target_char['name']}の効果: {' '.join(logs)}", 'match')

    # cleanup_one_time_buffs の呼び出しは削除

    broadcast_state_update(room)
    save_specific_room_state(room)