import copy
import json
import uuid
from flask_socketio import emit
from extensions import socketio, all_skill_data
from plugins.buffs.registry import buff_registry
from manager.room_manager import (
    get_room_state, save_specific_room_state, broadcast_log,
    broadcast_state_update, _update_char_stat, is_authorized_for_character,
    get_users_in_room
)
from manager.constants import DamageSource
from manager.battle.core import proceed_next_turn
from manager.logs import setup_logger

logger = setup_logger(__name__)


from manager.game_logic import (
    get_status_value, process_skill_effects, apply_buff, remove_buff, process_battle_start
)
from manager.utils import get_effective_origin_id
import random


def process_full_round_end(room, username):
    state = get_room_state(room)
    if not state: return

    if state.get('is_round_ended', False):
        emit('new_log', {"message": "⚠️ 既にラウンド終了処理は完了しています。", "type": "error"})
        return

    broadcast_log(room, f"--- {username} が Round {state.get('round', 0)} の終了処理を実行しました ---", 'info')
    characters_to_process = state.get('characters', [])

    # 全員行動済みかチェック
    from plugins.buffs.confusion import ConfusionBuff
    not_acted_chars = []
    for c in characters_to_process:
        is_dead = c.get('hp', 0) <= 0
        is_escaped = c.get('is_escaped', False)
        is_incapacitated = ConfusionBuff.is_incapacitated(c)
        should_act = not is_dead and not is_escaped and not is_incapacitated

        if should_act and not c.get('hasActed', False):
            not_acted_chars.append(c.get('name', 'Unknown'))

    if not_acted_chars:
        msg = f"⚠️ まだ行動していないキャラクターがいます: {', '.join(not_acted_chars)}"
        emit('new_log', {"message": msg, "type": "error"})
        return

    # 1. END_ROUND Effects
    for char in characters_to_process:
        used_skill_ids = char.get('used_skills_this_round', [])
        all_changes = []

        for skill_id in set(used_skill_ids):
            skill_data = all_skill_data.get(skill_id)
            if not skill_data: continue

            try:
                rule_json_str = skill_data.get('特記処理', '{}')
                rule_data = json.loads(rule_json_str)
                effects_array = rule_data.get("effects", [])
                if effects_array:
                    _, logs, changes = process_skill_effects(effects_array, "END_ROUND", char, char, None, context={'timeline': state.get('timeline', []), 'characters': state['characters'], 'room': room})
                    all_changes.extend(changes)
            except: pass

        for (c, type, name, value) in all_changes:
            if type == "APPLY_STATE":
                current_val = get_status_value(c, name)
                _update_char_stat(room, c, name, current_val + value, username=f"[{state.get('round')}R終了時]")
            elif type == "APPLY_BUFF":
                apply_buff(c, name, value["lasting"], value["delay"], data=value.get("data"))
                broadcast_log(room, f"[{name}] が {c['name']} に付与されました。", 'state-change')

        # 1c. Bleed
        bleed_value = get_status_value(char, '出血')
        if bleed_value > 0:
            _update_char_stat(room, char, 'HP', char['hp'] - bleed_value, username="[出血]", source=DamageSource.BLEED)

            # 出血維持バフチェック
            from plugins.buffs.bleed_maintenance import BleedMaintenanceBuff
            if BleedMaintenanceBuff.has_bleed_maintenance(char):
                 # 維持する場合、減少処理をスキップ (値は変わらない)
                 pass
            else:
                 # 通常: 半減
                _update_char_stat(room, char, '出血', bleed_value // 2, username="[出血]")

        # 1d. Thorns
        thorns_value = get_status_value(char, '荊棘')
        if thorns_value > 0:
            _update_char_stat(room, char, '荊棘', thorns_value - 1, username="[荊棘]")

        # 2. Buff Timers
        if "special_buffs" in char:
            active_buffs = []
            buffs_to_remove = []

            for buff in char['special_buffs']:
                buff_name = buff.get("name")
                delay = buff.get("delay", 0)
                lasting = buff.get("lasting", 0)

                if delay > 0:
                    buff["delay"] = delay - 1
                    if buff["delay"] == 0:
                        broadcast_log(room, f"[{buff_name}] の効果が {char['name']} で発動可能になった。", 'state-change')

                        # Hook
                        BuffClass = buff_registry.get_handler(buff.get('buff_id'))
                        if BuffClass:
                            plugin = BuffClass(buff)
                            if hasattr(plugin, 'on_delay_zero'):
                                res = plugin.on_delay_zero(char, {'room': room})
                                for log in res.get('logs', []):
                                    broadcast_log(room, log.get('message', ''), log.get('type', 'info'))
                                for change in res.get('changes', []):
                                    if len(change) >= 4:
                                        c_target, c_type, c_name, c_val = change
                                        if c_type == "CUSTOM_DAMAGE":
                                            curr = c_target.get('hp', 0)
                                            _update_char_stat(room, c_target, 'HP', curr - c_val, username=f"[{c_name}]")

                        if lasting > 0: active_buffs.append(buff)
                        else: buffs_to_remove.append(buff_name)
                    else:
                        active_buffs.append(buff)
                elif lasting > 0:
                    buff["lasting"] = lasting - 1
                    if buff["lasting"] > 0:
                        active_buffs.append(buff)
                    else:
                        broadcast_log(room, f"[{buff_name}] の効果が {char['name']} から切れた。", 'state-change')
                        buffs_to_remove.append(buff_name)
                        if buff_name == "混乱":
                            _update_char_stat(room, char, 'MP', int(char.get('maxMp', 0)), username="[混乱解除]")
                            broadcast_log(room, f"{char['name']} は意識を取り戻した！ (MP全回復)", 'state-change')
                elif buff.get('is_permanent', False):
                    active_buffs.append(buff)

            char['special_buffs'] = active_buffs

        # Reset limits
        if 'round_item_usage' in char: char['round_item_usage'] = {}
        if 'used_immediate_skills_this_round' in char: char['used_immediate_skills_this_round'] = []
        if 'used_skills_this_round' in char: char['used_skills_this_round'] = []

    # ★ 追加: マホロバ (ID: 5) ラウンド終了時一括処理
    mahoroba_targets = []
    for char in characters_to_process:
        if char.get('hp', 0) <= 0: continue
        if get_effective_origin_id(char) == 5:
             # HP回復
             _update_char_stat(room, char, 'HP', char['hp'] + 3, username="[マホロバ恩恵]")
             mahoroba_targets.append(char['name'])

    if mahoroba_targets:
        broadcast_log(room, f"[マホロバ恩恵] {', '.join(mahoroba_targets)} のHPが3回復しました。", 'info')

    state['is_round_ended'] = True
    state['turn_char_id'] = None
    state['active_match'] = None

    broadcast_state_update(room)
    save_specific_room_state(room)

def reset_battle_logic(room, mode, username, reset_options=None):
    state = get_room_state(room)
    if not state: return

    # Default options if None (Full reset behavior)
    if reset_options is None:
        reset_options = {
            'hp': True,
            'mp': True,
            'fp': True,
            'states': True, # 出血等
            'bad_states': True, # 状態異常 (麻痺など)
            'buffs': True,
            'timeline': True # Force timeline reset for status mode too based on user request
        }

    log_msg = f"\n--- {username} が戦闘をリセットしました (Mode: {mode}) ---\n"
    # log_msg += f"Opt: {json.dumps(reset_options, ensure_ascii=False)}"
    broadcast_log(room, log_msg, 'round')

    # ★ 追加: 矢印は常にリセット
    state['ai_target_arrows'] = []

    if mode == 'full':
        state['characters'] = []
        state['timeline'] = []
        state['round'] = 0
        state['is_round_ended'] = False
    elif mode == 'status':
        # ラウンド数はリセットしない要望もあるかもしれないが、一旦デフォルトは0に戻す
        # (Status only reset usually implies starting over but keeping chars)
        state['round'] = 0
        state['is_round_ended'] = False

        if reset_options.get('timeline'):
            state['timeline'] = []

        for char in state.get('characters', []):
            initial = char.get('initial_state', {})

            # ★ 修正: 未配置(x<0)かつ生存(hp>0)の場合はリセット対象外
            # (戦闘不能キャラは未配置でもリセットして復帰させる)
            is_unplaced = char.get('x', -1) < 0
            is_dead = char.get('hp', 0) <= 0

            if is_unplaced and not is_dead:
                # リセットしない
                continue

            # --- HP ---
            if reset_options.get('hp'):
                max_hp = int(initial.get('maxHp', char.get('maxHp', 0)))
                # 初期値があればそれ、なければ現在のMax
                char['maxHp'] = max_hp
                char['hp'] = max_hp

            # --- MP ---
            if reset_options.get('mp'):
                max_mp = int(initial.get('maxMp', char.get('maxMp', 0)))
                char['maxMp'] = max_mp
                char['mp'] = max_mp

            # --- FP & Stackable States (出血, 破裂 etc) ---
            if reset_options.get('fp') or reset_options.get('states'):
                # これらは 'states' 配列に入っている
                # FPは独立して管理されることも多いが、ここでは states リスト内のもので判断

                # まず既存の states を維持しつつ、対象のものだけリセット
                # ただし、構造上 states はリストなので、全部作り直したほうが安全

                new_states = []
                # デフォルトのステータス定義
                default_states = {
                    "FP": 0, "出血": 0, "破裂": 0, "亀裂": 0, "戦慄": 0, "荊棘": 0
                }

                # 既存の状態を取得
                current_states = {s['name']: s['value'] for s in char.get('states', [])}

                for s_name, def_val in default_states.items():
                    # FP
                    if s_name == 'FP':
                        if reset_options.get('fp'):
                            # 初期FPは 0 ではなく process_battle_start で入るかもしれないが、
                            # ベースとしては 0 (または maxFp?)
                            # 実装では FP = maxFp (初期値) としている箇所が見当たる
                            # ここでは 0 にしてから process_battle_start に任せるか、maxFpにするか
                            # 既存ロジック: char['FP'] = char.get('maxFp', 0)
                            char['FP'] = char.get('maxFp', 0)
                            new_states.append({"name": "FP", "value": 0}) # 表示用?
                        else:
                            # 維持
                            val = current_states.get(s_name, def_val)
                            new_states.append({"name": s_name, "value": val})

                    # 他の蓄積値
                    else:
                        if reset_options.get('states'):
                            new_states.append({"name": s_name, "value": 0})
                        else:
                            val = current_states.get(s_name, def_val)
                            new_states.append({"name": s_name, "value": val})

                char['states'] = new_states

            # --- Status Effects (麻痺, 毒 etc - char['状態異常'] list) ---
            if reset_options.get('bad_states'):
                char['状態異常'] = []

            # --- Buffs ---
            if reset_options.get('buffs'):
                # 初期バフ（パッシブ由来やキャラ作成時バフ）は initial_state にある
                # initial_state の special_buffs を復元
                raw_initial_buffs = initial.get('special_buffs', [])
                char['special_buffs'] = [dict(b) for b in raw_initial_buffs]

            # --- Common Reset (Always) ---
            # これらは「戦闘状態」なのでリセット必須
            if 'round_item_usage' in char: char['round_item_usage'] = {}
            if 'used_immediate_skills_this_round' in char: char['used_immediate_skills_this_round'] = []
            if 'used_gem_protect_this_battle' in char: char['used_gem_protect_this_battle'] = False
            if 'used_skills_this_round' in char: char['used_skills_this_round'] = []

            char['hasActed'] = False
            char['speedRoll'] = 0
            char['isWideUser'] = False

            # ★ 追加: 戦闘開始時効果の再適用 (FPリセットなどが有効な場合のみ)
            # リセットオプションにかかわらず、戦闘開始時処理は走らせるべきか？
            # 例えば「FPリセット」を選んだ場合のみ、初期FP付与などの処理を再度適用したい。
            # しかし process_battle_start は副作用があるかもしれない。
            # ここではシンプルに、「HP/MP/FPのいずれかがリセットされた場合」は再適用する、とする
            if reset_options.get('hp') or reset_options.get('mp') or reset_options.get('fp'):
                 try:
                     process_battle_start(room, char)
                 except Exception as e:
                     logger.error(f"process_battle_start in reset failed: {e}")

            # ★ 追加: 爆縮リセット (バフリセット時のみ)
            if reset_options.get('buffs'):
                origin_id = get_effective_origin_id(char)
                if origin_id == 10:
                    apply_buff(char, "爆縮", -1, 0, count=8)

        state['turn_char_id'] = None

    state['active_match'] = None
    broadcast_state_update(room)
    save_specific_room_state(room)

def force_end_match_logic(room, username):
    state = get_room_state(room)
    if not state: return

    if not state.get('active_match') and not state.get('pending_wide_ids'):
        emit('new_log', {"message": "現在アクティブなマッチまたは広域予約はありません。", "type": "error"})
        return

    # リセット処理
    state['active_match'] = None
    state['pending_wide_ids'] = []  # 広域マッチの予約もクリア

    save_specific_room_state(room)
    broadcast_state_update(room)

    # モーダル閉じるイベントを送信 (広域用とDuel用)
    socketio.emit('match_modal_closed', {}, to=room)
    socketio.emit('force_close_wide_modal', {}, to=room) # 必要であればクライアント側で受ける

    broadcast_log(room, f"⚠️ GM {username} がマッチを強制終了しました。", 'match-end')

def move_token_logic(room, char_id, x, y, username, attribute):
    state = get_room_state(room)
    if not state: return

    target_char = next((c for c in state["characters"] if c.get('id') == char_id), None)
    if not target_char: return

    if not is_authorized_for_character(room, char_id, username, attribute):
        emit('move_denied', {'message': '権限がありません。'})
        return

    target_char["x"] = float(x)
    target_char["y"] = float(y)

    save_specific_room_state(room)
    broadcast_state_update(room)

def open_match_modal_logic(room, data, username):
    state = get_room_state(room)
    if not state: return

    match_type = data.get('match_type')
    attacker_id = data.get('attacker_id')
    defender_id = data.get('defender_id')
    targets = data.get('targets', [])

    # Provoke Check
    if match_type == 'duel':
        attacker_char = next((c for c in state["characters"] if c.get('id') == attacker_id), None)
        if attacker_char:
            attacker_type = attacker_char.get('type', 'ally')
            provoking_enemies = []
            for c in state["characters"]:
                if c.get('type') != attacker_type and c.get('hp', 0) > 0:
                    for buff in c.get('special_buffs', []):
                         if (buff.get('name') in ['挑発中', '挑発'] or buff.get('buff_id') in ['Bu-Provoke', 'Bu-01']) and buff.get('delay', 0) == 0:
                             provoking_enemies.append(c['id'])
                             break

            if provoking_enemies and defender_id not in provoking_enemies:
                emit('match_error', {'error': '挑発中の敵がいるため、他のキャラクターを攻撃できません。'}, to=request.sid)
                return

    # Resume Check
    current_match = state.get('active_match')
    is_resume = False

    if current_match and \
       current_match.get('attacker_id') == attacker_id and \
       current_match.get('defender_id') == defender_id and \
       current_match.get('match_type') == match_type:
           state['active_match']['is_active'] = True
           state['active_match']['opened_by'] = username
           is_resume = True
    else:
        # New Match
        defender_char = next((c for c in state["characters"] if c.get('id') == defender_id), None)
        is_one_sided = False
        if defender_char:
            from plugins.buffs.dodge_lock import DodgeLockBuff
            if defender_char.get('hasActed', False) and not DodgeLockBuff.has_re_evasion(defender_char):
                is_one_sided = True

        attacker_char = next((c for c in state["characters"] if c.get('id') == attacker_id), None)

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
            'is_one_sided_attack': is_one_sided,
            'attacker_snapshot': copy.deepcopy(attacker_char),
            'defender_snapshot': copy.deepcopy(defender_char),
            'match_id': str(uuid.uuid4())
        }

    save_specific_room_state(room)
    socketio.emit('match_modal_opened', {
        'match_type': match_type,
        'attacker_id': attacker_id,
        'defender_id': defender_id,
        'targets': targets,
        'is_resume': is_resume
    }, to=room)
    broadcast_state_update(room)

def close_match_modal_logic(room):
    state = get_room_state(room)
    if not state: return

    if 'active_match' in state:
        state['active_match']['is_active'] = False

    save_specific_room_state(room)
    socketio.emit('match_modal_closed', {}, to=room)
    broadcast_state_update(room)

def sync_match_data_logic(room, side, data, username, attribute):
    state = get_room_state(room)
    if not state: return
    active_match = state.get('active_match', {})

    if not active_match.get('is_active') or active_match.get('match_type') != 'duel':
        return

    # ★ 権限チェック: GM または そのキャラクターの所有者のみ許可
    target_char_id = None
    if side == 'attacker':
        target_char_id = active_match.get('attacker_id')
    elif side == 'defender':
        target_char_id = active_match.get('defender_id')

    # 所有者確認
    allowed = False
    if attribute == 'GM':
        allowed = True
    elif target_char_id:
        owners = state.get('character_owners', {})
        if owners.get(target_char_id) == username:
            allowed = True

    if not allowed:
        # 権限がない場合は無視（ログに出しても良いが、頻繁な同期なのでサイレントに無視するか、デバッグログのみ）
        logger.warning(f"Unauthorized sync attempt by {username} for side {side} (CharID: {target_char_id})")
        return

    if side == 'attacker':
        state['active_match']['attacker_data'] = data
    elif side == 'defender':
        state['active_match']['defender_data'] = data

    save_specific_room_state(room)
    socketio.emit('match_data_updated', {'side': side, 'data': data}, to=room)

def process_round_start(room, username):
    logger.debug(f"process_round_start called for room: {room} by {username}")
    state = get_room_state(room)
    if not state:
        logger.debug(f"Room state not found for {room}")
        return

    # Check previous round end flag
    if state.get('round', 0) > 0 and not state.get('is_round_ended', False):
        emit('new_log', {'message': 'ラウンド終了処理が完了していません。「ラウンド終了」ボタンを押してください。', 'type': 'error'}, room=room)
        return

    # increment round
    state['round'] = state.get('round', 0) + 1
    state['is_round_ended'] = False

    broadcast_log(room, f"--- {username} が Round {state['round']} を開始しました ---", 'round')

    # Update Speed and Create Timeline
    timeline_unsorted = []
    import uuid

    # Debug: Log start of timeline generation
    logger.info(f"[Timeline] Starting generation for Round {state.get('round')}. Total chars: {len(state.get('characters', []))}")

    for char in state.get('characters', []):
        # Type-safe checks
        try:
            hp = int(char.get('hp', 0))
            x_val = float(char.get('x', -1))
            escaped = bool(char.get('is_escaped', False))
        except (ValueError, TypeError):
            logger.warning(f"[Timeline] Type mismatch for char {char.get('name', 'Unknown')}. Skipping.")
            continue

        if hp <= 0:
            logger.debug(f"[Timeline] Skip {char.get('name')} (HP<=0)")
            continue
        if escaped:
             logger.debug(f"[Timeline] Skip {char.get('name')} (Escaped)")
             continue
        if x_val < 0:
             logger.debug(f"[Timeline] Skip {char.get('name')} (Unplaced x={x_val})")
             continue

        # Calculate Speed (1d6 + Speed/6)
        # Clear previous totalSpeed
        char['totalSpeed'] = None

        speed_val = 0
        try:
            speed_val = int(get_status_value(char, '速度'))
        except:
            speed_val = 0

        # ★ 加速・減速による速度補正
        from plugins.buffs.speed_mod import SpeedModBuff
        speed_modifier = SpeedModBuff.get_speed_modifier(char)

        initiative = (speed_val // 6) + speed_modifier

        if speed_modifier != 0:
            mod_text = f"+{speed_modifier}" if speed_modifier > 0 else str(speed_modifier)
            broadcast_log(room, f"{char['name']} の速度補正: {mod_text} (加速/減速)", 'info')

        # 速度ロール後に加速・減速をクリア
        SpeedModBuff.clear_speed_modifiers(char)

        # 行動回数を取得 (デフォルト1)
        try:
             action_count = int(get_status_value(char, '行動回数'))
        except:
             action_count = 1
        action_count = max(1, action_count)

        logger.debug(f"[SPEED ROLL] {char['name']}: speed={speed_val} (init={initiative}), count={action_count}")

        for i in range(action_count):
            roll = random.randint(1, 6)
            total_speed = initiative + roll

            # ★ 追加: 速度値の下限は1
            total_speed = max(1, total_speed)

            entry_id = str(uuid.uuid4())
            timeline_unsorted.append({
                'id': entry_id,          # UNIQUE ID for this action
                'char_id': char['id'],   # Link to Character
                'speed': total_speed,
                'stat_speed': initiative,
                'roll': roll,
                'acted': False,
                'is_extra': (i > 0)
            })

            # For backward compatibility / display on char token
            if i == 0:
                char['speedRoll'] = roll
                char['totalSpeed'] = total_speed

        # Reset Turn State
        char['hasActed'] = False

    # Sort Timeline (Speed Descending)
    timeline_unsorted.sort(key=lambda x: x['speed'], reverse=True)

    # Store full objects
    state['timeline'] = timeline_unsorted
    logger.info(f"[Timeline] Generated {len(timeline_unsorted)} entries.")

    state['turn_char_id'] = None
    state['turn_entry_id'] = None

    # Broadcast Timeline Info
    log_msg = "行動順が決まりました:<br>"
    for idx, item in enumerate(timeline_unsorted):
        char = next((c for c in state['characters'] if c['id'] == item['char_id']), None)
        if char:
            roll = item.get('roll', 0)
            stat = item.get('stat_speed', 0)
            total = item.get('speed', 0)
            sign = "+" if stat >= 0 else ""

            # ユーザー要望: 1d6(X)+Y の形式で内訳表示
            breakdown = f"1d6({roll}){sign}{stat} = {total}"

            log_msg += f"{idx+1}. {char['name']} ({breakdown})<br>"

    broadcast_log(room, log_msg, 'info')

    # ★ 追加: ラティウム (ID: 3) ラウンド開始時一括処理
    # 全員のFPを+1する
    latium_targets = []
    for char in state.get('characters', []):
        if char.get('hp', 0) <= 0: continue
        if get_effective_origin_id(char) == 3:
            current_fp = get_status_value(char, 'FP')
            _update_char_stat(room, char, 'FP', current_fp + 1, username="[ラティウム恩恵]")
            latium_targets.append(char['name'])

    if latium_targets:
        broadcast_log(room, f"[ラティウム恩恵] {', '.join(latium_targets)} のFPが1増加しました。", 'info')

    broadcast_state_update(room)
    save_specific_room_state(room)

    # ★ 追加: PvEモードならターゲット抽選
    if state.get('battle_mode') == 'pve':
        from manager.battle.battle_ai import ai_select_targets
        ai_select_targets(state, room)
        logger.info(f"PvE AI Targets updated for Round {state['round']}")

    # Reset Wide Modal Logic State
    state['wide_modal_confirms'] = []
    state['pending_wide_ids'] = []

    # Open Wide Declaration Modal (Wait for response)
    socketio.emit('open_wide_declaration_modal', {}, to=room)

def process_wide_declarations(room, wide_user_ids):
    state = get_room_state(room)
    if not state: return

    # Reset wide flags for everyone first (safety)
    for char in state.get('characters', []):
        char['isWideUser'] = False

    # Set new flags
    names = []
    logger.debug(f"[DEBUG] process_wide_declarations ids: {wide_user_ids}")
    for uid in wide_user_ids:
        char = next((c for c in state['characters'] if str(c['id']) == str(uid)), None)
        if char:
            char['isWideUser'] = True
            names.append(char['name'])
            logger.debug(f"[DEBUG] Set isWideUser=True for {char['name']} ({char['id']})")
        else:
            logger.debug(f"[DEBUG] Character not found for uid: {uid}")

    if names:
        broadcast_log(room, f"広域攻撃予約: {', '.join(names)}", 'info')
        # Reorder timeline: Move wide users to the front
        current_timeline = state.get('timeline', [])

        # New Logic for Object Timeline
        valid_wide_char_ids = [str(uid) for uid in wide_user_ids if any(str(c['id']) == str(uid) for c in state['characters'])]

        wide_entries = [entry for entry in current_timeline if str(entry['char_id']) in valid_wide_char_ids]
        remaining_entries = [entry for entry in current_timeline if str(entry['char_id']) not in valid_wide_char_ids]

        # New timeline: [Wide Entries] + [Remaining Entries]
        state['timeline'] = wide_entries + remaining_entries
        logger.debug(f"[DEBUG] New timeline len: {len(state['timeline'])}")
    else:
        broadcast_log(room, "広域攻撃予約: なし", 'info')

    save_specific_room_state(room)
    broadcast_state_update(room)

    # 状態保存後に少し待機してからターン進行（念のため）
    # proceed_next_turn(room)

    # ★修正: Latium (ID: 3) などのターン開始時効果を確実にするため
    # proceed_next_turn を呼び出し、その結果を確認する
    proceed_next_turn(room)

def process_wide_modal_confirm(room, user_id, attribute, wide_ids):
    state = get_room_state(room)
    if not state: return

    # Init container if missing
    if 'wide_modal_confirms' not in state: state['wide_modal_confirms'] = []
    if 'pending_wide_ids' not in state: state['pending_wide_ids'] = []

    # Merge Wide IDs (from this user)
    # Note: Even if already confirmed, we merge incase they updated selection (though UI locks).
    for wid in wide_ids:
        if wid not in state['pending_wide_ids']:
            state['pending_wide_ids'].append(wid)

    # 1. GM Force Confirm (Overrides waiting)
    if attribute == 'GM':
        logger.info(f"[WideModal] GM {user_id} Forced Confirm. IDs: {wide_ids}")

        # Execute Wide Declarations immediately
        process_wide_declarations(room, state['pending_wide_ids'])

        # Close Modal for everyone
        socketio.emit('close_wide_declaration_modal', {}, to=room)

        broadcast_log(room, f"GMにより広域攻撃予約が確定されました。", 'info')
        return

    # 2. Normal Player Confirm
    if user_id not in state['wide_modal_confirms']:
        state['wide_modal_confirms'].append(user_id)
        broadcast_log(room, f"{user_id} が広域予約を確認しました。", 'info')

    # Check coverage (All non-GM users in room)
    # Check coverage (All non-GM users in room)
    current_room_users = get_users_in_room(room)

    # Filter for active non-GM users
    non_gm_users = set()
    for sid, u_info in current_room_users.items():
        if u_info.get('attribute') != 'GM':
            non_gm_users.add(u_info.get('username'))

    # Check if all non-GM users have confirmed
    confirmed_users = set(state['wide_modal_confirms'])

    # Logic: If there are non-GM users and all of them confirmed, proceed.
    # If there are NO non-GM users (only GM in room), GM confirm handled above.

    all_confirmed = False
    if len(non_gm_users) > 0:
        if non_gm_users.issubset(confirmed_users):
            all_confirmed = True

    if all_confirmed:
        logger.info("[WideModal] All players confirmed. Executing.")
        process_wide_declarations(room, state['pending_wide_ids'])
        socketio.emit('close_wide_declaration_modal', {}, to=room)
    else:
        # Wait
        logger.info(f"Player {user_id} confirmed. Waiting... ({len(confirmed_users)}/{len(non_gm_users)})")
        save_specific_room_state(room)



def update_battle_background_logic(room, image_url, scale, offset_x, offset_y, username, attribute):
    """
    戦闘画面の背景画像を更新するロジック
    """
    if attribute != 'GM':
        emit('new_log', {'message': '背景設定はGMのみ可能です。', 'type': 'error'})
        return

    state = get_room_state(room)
    if not state: return

    # データ構造の初期化
    if 'battle_map_data' not in state:
        state['battle_map_data'] = {}

    # 値の更新
    state['battle_map_data']['background_image'] = image_url
    if scale is not None:
        state['battle_map_data']['background_scale'] = scale
    if offset_x is not None:
        state['battle_map_data']['background_offset_x'] = offset_x
    if offset_y is not None:
        state['battle_map_data']['background_offset_y'] = offset_y

    broadcast_state_update(room)
    broadcast_log(room, f"戦闘マップの背景が変更されました。", 'system')

# ★ 追加: PvEモード切替ロジック
def process_switch_battle_mode(room, mode, username):
    state = get_room_state(room)
    if not state: return

    old_mode = state.get('battle_mode', 'pvp')
    if old_mode == mode:
        return

    state['battle_mode'] = mode
    broadcast_log(room, f"戦闘モードが変更されました: {old_mode.upper()} → {mode.upper()}", 'system')

    # PvEになったらターゲット再抽選
    if mode == 'pve':
        from manager.battle.battle_ai import ai_select_targets
        ai_select_targets(state)
        # ログは ai_select_targets 内では出ないのでここで出すか、AIロジック側で出すか
        # とりあえずAI側でdebugログ出してるが、ユーザーに見えるログも少し出す
        broadcast_log(room, "AIがターゲットを選定しました。", 'info', secret=True)

    save_specific_room_state(room)
    broadcast_state_update(room)

# ★ 追加: AIスキル提案API (Socket経由で呼ばれる想定だが、routesで実装してもいい。ここではロジックのみ)
def process_ai_suggest_skill(room, char_id):
    # これは戻り値を返すタイプなので、Socketのコールバックで返すのが一般的
    # common_managerにおく必要性は薄いかもしれないが、一応
    state = get_room_state(room)
    if not state: return None

    char = next((c for c in state['characters'] if c['id'] == char_id), None)
    if not char: return None

    from manager.battle.battle_ai import ai_suggest_skill
    return ai_suggest_skill(char)

