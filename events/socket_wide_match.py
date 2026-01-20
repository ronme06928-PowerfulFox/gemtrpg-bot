"""
広域マッチ処理モジュール
"""
import re
import json
import random
import copy
from flask import request
from flask_socketio import emit

from extensions import socketio, all_skill_data
from manager.room_manager import (
    get_room_state, save_specific_room_state,
    broadcast_state_update, broadcast_log, get_user_info_from_sid,
    _update_char_stat, is_authorized_for_character  # ★追加
)
from manager.game_logic import get_status_value, process_skill_effects, apply_buff, remove_buff
from manager.utils import resolve_placeholders  # ★追加
from manager.dice_roller import roll_dice  # ★追加

# _process_end_round_logicもsocket_battleから使用するためインポート（循環回避のため注意）
# NOTE: この関数は後でmanagerモジュールに移動することを推奨
from events.socket_battle import _process_end_round_logic  # ★追加


# ★ 相手スキルを考慮した威力補正計算（socket_battleから複製）
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

    # 防御者リストを構築（フィールドに配置されているキャラのみ）
    defenders = []
    for def_id in defender_ids:
        def_char = next((c for c in state["characters"] if c.get('id') == def_id), None)
        # ★ 配置チェック: タイムラインと同様に x, y >= 0 のキャラのみを対象
        if not def_char:
            continue

        # タイムラインのロジック (c.get('x', -1) >= 0) に準拠
        x_val = def_char.get('x', -1)
        y_val = def_char.get('y', -1)

        # None対策 (getのデフォルト値だけではNoneを防げないため念のため)
        if x_val is None: x_val = -1
        if y_val is None: y_val = -1

        try:
            is_placed = int(x_val) >= 0 and int(y_val) >= 0
        except (ValueError, TypeError):
            is_placed = False

        if def_char.get('hp', 0) > 0 and is_placed:
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

            # ★ サーバー側で統一ロジックを用いて再計算
            # これにより、亀裂などの対抗補正や詳細な内訳を正確に保存する

            # ターゲット（攻撃者）の特定
            attacker_id = active_match.get('attacker_id')
            attacker_char = next((c for c in state['characters'] if c.get('id') == attacker_id), None)

            # calculate_skill_preview のインポート
            from manager.game_logic import calculate_skill_preview

            # プレビュー計算
            # 攻撃者からの外部補正(base_power_mod)を考慮する必要がある
            # Attacker Declaration時に保存されたdefender['power_breakdown']['base_power_mod']を使う
            external_mod = 0
            if 'power_breakdown' in defender and defender['power_breakdown']:
                external_mod = defender['power_breakdown'].get('base_power_mod', 0)

            preview = calculate_skill_preview(
                def_char, attacker_char, skill_data,
                external_base_power_mod=external_mod,
                senritsu_max_apply=3
            )

            # 結果の保存
            defender['final_command'] = preview['final_command']
            defender['min'] = preview['min_damage']
            defender['max'] = preview['max_damage']
            defender['declared'] = True
            defender['declared_by'] = username

            # 詳細データの保存 (wide_match_synced.jsでの表示に使用)
            defender['damage_range_text'] = preview['damage_range_text']
            defender['correction_details'] = preview['correction_details']
            defender['senritsu_dice_reduction'] = preview['senritsu_dice_reduction']
            defender['power_breakdown'] = preview['power_breakdown']

            # dataフィールドにも念のため保存（フロントエンドの参照先が混在している可能性があるため）
            defender['data'] = {
                'skill_id': skill_id,
                'final_command': preview['final_command'],
                'min_damage': preview['min_damage'],
                'max_damage': preview['max_damage'],
                'damage_range_text': preview['damage_range_text'],
                'correction_details': preview['correction_details'],
                'senritsu_dice_reduction': preview['senritsu_dice_reduction'],
                'skill_details': preview['skill_details'],
                'power_breakdown': preview['power_breakdown']
            }

            print(f"[WIDE_MATCH] Defender {defender['name']} declared skill {skill_id} with full preview data")
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

    # ★ Attacker Preview Calculation
    # ターゲットは便宜上、最初のディフェンダーか自分自身とする（計算上ターゲット必須のため）
    target_char = active_match.get('defenders', [None])[0]
    if target_char:
        target_char = next((c for c in state['characters'] if c.get('id') == target_char.get('id')), None)
    if not target_char: target_char = attacker_char # Fallback

    from manager.game_logic import calculate_skill_preview
    att_preview = calculate_skill_preview(
        attacker_char, target_char, skill_data,
        senritsu_max_apply=3
    )

    active_match['attacker_data'] = {
        'skill_id': skill_id,
        'command': command,
        'final_command': att_preview['final_command'],
        'min_damage': att_preview['min_damage'],
        'max_damage': att_preview['max_damage'],
        # 'min': data.get('min'), # クライアント計算値は使わずサーバー計算値を使う
        # 'max': data.get('max'),
        'damage_range_text': att_preview['damage_range_text'],
        'correction_details': att_preview['correction_details'],
        'senritsu_dice_reduction': att_preview['senritsu_dice_reduction'],
        'skill_details': att_preview['skill_details'],
        'power_breakdown': att_preview['power_breakdown']
    }
    active_match['attacker_declared'] = True

    # ★ スキルの距離フィールドからモードを自動判定して更新
    distance_field = skill_data.get('距離', '')
    if '広域-合算' in distance_field:
        active_match['mode'] = 'combined'
        print(f"[WIDE_MATCH] Mode set to 'combined' based on skill 距離 field: {distance_field}")
    elif '広域-個別' in distance_field:
        active_match['mode'] = 'individual'
        print(f"[WIDE_MATCH] Mode set to 'individual' based on skill 距離 field: {distance_field}")

    # ★ Update modifiers for all defenders (Base Mod, etc.)
    print(f"[WIDE_MATCH] Attacker declared. Updating modifiers for all defenders...")
    for defender in active_match.get('defenders', []):
        d_id = defender.get('id')
        d_char = next((c for c in state['characters'] if c.get('id') == d_id), None)

        # If no skill declared yet, skip calculation
        d_skill_id = defender.get('skill_id')
        d_skill_data = all_skill_data.get(d_skill_id)

        if d_char and d_skill_data:
            mods = calculate_opponent_skill_modifiers(
                attacker_char, d_char, skill_data, d_skill_data, all_skill_data
            )
            base_mod = mods.get('base_power_mod', 0)

            # Update power_breakdown at root level (for backward compat or easy access)
            if 'power_breakdown' not in defender: defender['power_breakdown'] = {}
            defender['power_breakdown']['base_power_mod'] = base_mod
            # defender['power_breakdown']['base_power'] = int(skill_data.get('基礎威力', 0)) # skill_data is attacker's! Fixed below

            # プレビュー計算 (共通関数)
            preview = calculate_skill_preview(
                d_char, attacker_char, d_skill_data,
                external_base_power_mod=base_mod,
                senritsu_max_apply=3
            )

            # 結果の更新
            defender['final_command'] = preview['final_command']
            defender['min'] = preview['min_damage']
            defender['max'] = preview['max_damage']

            # 詳細データの保存
            defender['data'] = {
                'skill_id': d_skill_id,
                'final_command': preview['final_command'],
                'min_damage': preview['min_damage'],
                'max_damage': preview['max_damage'],
                'damage_range_text': preview['damage_range_text'],
                'correction_details': preview['correction_details'],
                'senritsu_dice_reduction': preview['senritsu_dice_reduction'],
                'skill_details': preview['skill_details'],
                'power_breakdown': preview['power_breakdown']
            }
            # base_mod の再設定 (calculate_skill_preview 内部で加算されているが、内訳として補強)
            if base_mod != 0:
                 # preview['power_breakdown'] には自分のバフ等は入っているが、相手からの補正(external)は入っていないかもしれない？
                 # calculate_skill_preview の返り値の power_breakdown は、base_power_buff_mod と additional_power のみ。
                 # 外部補正は base_power に足し込まれている。
                 pass

            print(f"[WIDE_MATCH DEBUG] Updated Defender {d_id} Mod: {base_mod}")

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
    attacker_command = attacker_data.get('final_command') or attacker_data.get('command')

    attacker_char = next((c for c in state['characters'] if c.get('id') == attacker_id), None)
    if not attacker_char:
        return

    attacker_skill_data = all_skill_data.get(attacker_skill_id)
    mode = active_match.get('mode', 'individual')

    # ★ Helper: Pre-Match Effects (copied from handle_match for Wide Match consistency)
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
                    if 'flags' not in char: char['flags'] = {}
                    char['flags'][name] = value
                elif type == "MODIFY_BASE_POWER":
                    # 基礎威力ボーナスを一時保存（荊棘処理で参照）
                    char['_base_power_bonus'] = char.get('_base_power_bonus', 0) + value
                    broadcast_log(room, f"[{char['name']}] 基礎威力 {value:+}", 'state-change')
        except json.JSONDecodeError: pass

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

    # Execute match
    broadcast_log(room, f"⚔️ === 広域マッチ開始 ({mode}モード) ===", 'match-start')
    broadcast_log(room, f"🗡️ 攻撃者: {attacker_char['name']} [{attacker_skill_id}]", 'info')

    attacker_roll = roll_dice(attacker_command)
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
            def_roll_result = roll_dice(def_command)

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
            def_skill_data = all_skill_data.get(def_skill_id)

            # --- Wide Match Thorns & Modifiers Logic ---
            # Reset temporary bonus
            attacker_char['_base_power_bonus'] = 0
            if def_char: def_char['_base_power_bonus'] = 0

            # Apply modifiers
            apply_pre_match_effects(attacker_char, def_char, attacker_skill_data, def_skill_data)
            if def_char and def_skill_data:
                apply_pre_match_effects(def_char, attacker_char, def_skill_data, attacker_skill_data)

            # Thorns (荊棘) Processing - Defender Self-Reduction
            thorn_val = get_status_value(def_char, "荊棘")
            if thorn_val > 0 and def_skill_data:
                 tags = def_skill_data.get('tags', [])
                 cat = def_skill_data.get('分類', '')
                 if cat == '防御' or '防御' in tags or '守備' in tags:
                      bp = int(def_skill_data.get('基礎威力', 0))
                      bp += def_char.get('_base_power_bonus', 0)
                      if bp > 0:
                          _update_char_stat(room, def_char, "荊棘", max(0, thorn_val - bp), username=f"[{def_skill_id}:荊棘詳細]")
            using_precalc = False
            def_command = def_data.get('command', '2d6')
            if def_data.get('data') and def_data['data'].get('final_command'):
                def_command = def_data['data']['final_command']
                using_precalc = True

            # ★ Apply dynamic base power modifiers to command
            bp_mod = def_char.get('_base_power_bonus', 0)
            if bp_mod != 0 and not using_precalc:
                def_command = f"{def_command}+{bp_mod}"
                print(f"[WIDE_MATCH EXEC] Applied BaseMod {bp_mod} -> {def_command}")

            def_roll = roll_dice(def_command)

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

    # ★ 広域マッチ終了時に全員のパネルを閉じる
    socketio.emit('match_modal_closed', {}, to=room)

    # ★ 広域マッチ終了後にactive_matchをクリア
    if 'active_match' in state:
        del state['active_match']
        save_specific_room_state(room)

    print(f"[WIDE_MATCH] Executed wide match: {len(results)} defenders processed")

    # ★ ラウンド終了タグがあった場合、通常の保存・ブロードキャスト後にラウンド終了処理を実行
    if round_end_requested:
        _process_end_round_logic(state, room)


@socketio.on('request_wide_match')
def handle_wide_match(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    state = get_room_state(room)

    # ★ 重複実行防止: マッチIDをチェック
    match_id = data.get('match_id')
    active_match = state.get('active_match', {})

    # active_matchが存在する場合のみIDチェック
    if active_match.get('is_active') and active_match.get('match_type') == 'wide':
        # マッチIDが未生成なら生成
        if 'match_id' not in active_match:
            import uuid
            active_match['match_id'] = str(uuid.uuid4())
            state['active_match'] = active_match
            print(f"[WIDE_MATCH] Generated match ID: {active_match['match_id']}")

        expected_match_id = active_match.get('match_id')
        if match_id and match_id != expected_match_id:
            print(f"[WIDE_MATCH] Match ID mismatch: {match_id} != {expected_match_id}, skipping")
            return

        # すでに実行済みかチェック
        if active_match.get('executed'):
            print(f"[WIDE_MATCH] Match {match_id} already executed, skipping")
            return

        # 実行済みフラグを立てる
        state['active_match']['executed'] = True
        save_specific_room_state(room)
        print(f"[WIDE_MATCH] Executing match {match_id}")

    actor_id = data.get('actorId'); skill_id = data.get('skillId'); mode = data.get('mode'); command_actor = data.get('commandActor'); defenders_data = data.get('defenders', [])
    actor_char = next((c for c in state["characters"] if c.get('id') == actor_id), None)
    if not actor_char: return
    actor_name = actor_char['name']
    skill_data_actor = all_skill_data.get(skill_id)

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

        # ★ 戦慄によるダイス面減少（最大3まで、1d1未満にはならない）
        senritsu = get_status_value(def_char, '戦慄')
        senritsu_max = min(senritsu, 3) if senritsu > 0 else 0
        dice_reduction = 0

        # ダイス威力からダイス面数を取得して減少を計算
        dice_str = d_skill_data.get('ダイス威力', '')
        dice_m = re.search(r'([+-]?)(\d+)d(\d+)', dice_str)
        if dice_m and senritsu_max > 0:
            orig_faces = int(dice_m.group(3))
            if orig_faces > 1:
                max_red = orig_faces - 1
                dice_reduction = min(senritsu_max, max_red)

        if dice_reduction > 0:
            _update_char_stat(room, def_char, '戦慄', max(0, senritsu - dice_reduction), username=f"[{def_char['name']}:戦慄消費(ダイス-{dice_reduction})]")

        total_mod = power_bonus  # 戦慄はダイス面減少として適用済み
        phys = get_status_value(def_char, '物理補正'); mag = get_status_value(def_char, '魔法補正')
        final_cmd = resolved_cmd
        if '{物理補正}' in final_cmd: final_cmd = final_cmd.replace('{物理補正}', str(phys))
        elif '{魔法補正}' in final_cmd: final_cmd = final_cmd.replace('{魔法補正}', str(mag))

        # ★ ダイス面減少をコマンドに適用（例: 1d6 → 1d3）
        if dice_reduction > 0:
            def reduce_dice_faces(m):
                sign = m.group(1) or ''
                num = m.group(2)
                faces = int(m.group(3))
                new_faces = max(1, faces - dice_reduction)
                return f"{sign}{num}d{new_faces}"
            # 最初のダイスのみ置換（基礎威力直後のダイス威力）
            final_cmd = re.sub(r'([+-]?)(\d+)d(\d+)', reduce_dice_faces, final_cmd, count=1)

        if total_mod > 0:
            if ' 【' in final_cmd: final_cmd = final_cmd.replace(' 【', f"+{total_mod} 【")
            else: final_cmd += f"+{total_mod}"
        elif total_mod < 0:
            if ' 【' in final_cmd: final_cmd = final_cmd.replace(' 【', f"{total_mod} 【")
            else: final_cmd += f"{total_mod}"
        return final_cmd, d_skill_data


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
    result_actor = roll_dice(command_actor)
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
            result_target = roll_dice(d_cmd); target_power = result_target['total']
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

                bonus, logs = apply_skill_effects_bidirectional(room, state, username, 'attacker', actor_char, target_char, skill_data_actor, skill_data_target, base_dmg)
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

                bonus, logs = apply_skill_effects_bidirectional(room, state, username, 'defender', actor_char, target_char, skill_data_actor, skill_data_target, base_dmg)
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
            res = roll_dice(d_cmd); total_def_power += res['total']
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
                    room, state, username, 'attacker', actor_char, target_char, skill_data_actor, entry['skill_data'], diff_dmg,
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
                    room, state, username, 'defender', actor_char, target_char, skill_data_actor, entry['skill_data'], 0,
                    suppress_actor_self_effect=should_suppress
                )
                if logs: broadcast_log(room, f"➡ {target_char['name']}の効果: {' '.join(logs)}", 'match')

    broadcast_state_update(room)
    save_specific_room_state(room)
