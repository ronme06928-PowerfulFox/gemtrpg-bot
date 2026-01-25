import copy
import json
import uuid
from flask_socketio import emit
from extensions import socketio, all_skill_data
from plugins.buffs.registry import buff_registry
from manager.room_manager import (
    get_room_state, save_specific_room_state, broadcast_log,
    broadcast_state_update, _update_char_stat, is_authorized_for_character
)
from manager.constants import DamageSource
from manager.battle.core import proceed_next_turn
from manager.logs import setup_logger

logger = setup_logger(__name__)


from manager.game_logic import (
    get_status_value, process_skill_effects, apply_buff, remove_buff, process_battle_start
)
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
                    _, logs, changes = process_skill_effects(effects_array, "END_ROUND", char, char, None, context={'characters': state['characters']})
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

    state['is_round_ended'] = True
    state['turn_char_id'] = None
    state['active_match'] = None

    broadcast_state_update(room)
    save_specific_room_state(room)

def reset_battle_logic(room, mode, username):
    state = get_room_state(room)
    if not state: return

    broadcast_log(room, f"\n--- {username} が戦闘をリセットしました (Mode: {mode}) ---", 'round')

    if mode == 'full':
        state['characters'] = []
        state['timeline'] = []
        state['round'] = 0
        state['is_round_ended'] = False
    elif mode == 'status':
        state['round'] = 0
        state['timeline'] = []
        state['is_round_ended'] = False

        for char in state.get('characters', []):
            char['hp'] = int(char.get('maxHp', 0))
            char['mp'] = int(char.get('maxMp', 0))

            char['states'] = [
                { "name": "FP", "value": 0 },
                { "name": "出血", "value": 0 },
                { "name": "破裂", "value": 0 },
                { "name": "亀裂", "value": 0 },
                { "name": "戦慄", "value": 0 },
                { "name": "荊棘", "value": 0 }
            ]
            char['状態異常'] = []
            char['FP'] = char.get('maxFp', 0)

            if 'round_item_usage' in char: char['round_item_usage'] = {}
            if 'used_immediate_skills_this_round' in char: char['used_immediate_skills_this_round'] = []
            if 'used_gem_protect_this_battle' in char: char['used_gem_protect_this_battle'] = False
            if 'used_skills_this_round' in char: char['used_skills_this_round'] = []

            if 'initial_state' in char:
                char['inventory'] = dict(char['initial_state'].get('inventory', {}))
                char['special_buffs'] = [dict(b) for b in char['initial_state'].get('special_buffs', [])]
                char['maxHp'] = int(char['initial_state'].get('maxHp', char.get('maxHp', 0)))
                char['maxMp'] = int(char['initial_state'].get('maxMp', char.get('maxMp', 0)))
                char['hp'] = char['maxHp']
                char['mp'] = char['maxMp']
            else:
                 char['special_buffs'] = []
                 if 'inventory' not in char: char['inventory'] = {}

            char['hasActed'] = False
            char['speedRoll'] = 0
            char['isWideUser'] = False

            # ★ 追加: 戦闘開始時効果 (初期FP等) の再適用
            # リセット後に適用するため、初期FPパッシブがあればここでFPが入る
            try:
                process_battle_start(room, char)
            except Exception as e:
                logger.error(f"process_battle_start in reset failed: {e}")

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

    target_char["x"] = int(x)
    target_char["y"] = int(y)

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

def sync_match_data_logic(room, side, data):
    state = get_room_state(room)
    if not state: return
    active_match = state.get('active_match', {})

    if not active_match.get('is_active') or active_match.get('match_type') != 'duel':
        return

    if side == 'attacker':
        state['active_match']['attacker_data'] = data
    elif side == 'defender':
        state['active_match']['defender_data'] = data

    save_specific_room_state(room)
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

    for char in state.get('characters', []):
        if char.get('hp', 0) <= 0: continue
        if char.get('is_escaped', False): continue
        # 未配置チェック (x < 0)
        if char.get('x', -1) < 0: continue

        # Calculate Speed (1d6 + Speed/6)
        speed_param = get_status_value(char, '速度')
        initiative = speed_param // 6

        # 1d6
        roll = random.randint(1, 6)
        char['speedRoll'] = roll
        total_speed = initiative + roll
        char['totalSpeed'] = total_speed

        timeline_unsorted.append({
            'id': char['id'],
            'speed': total_speed,
            'stat_speed': initiative,
            'roll': roll
        })

        # Reset Turn State
        char['hasActed'] = False

    # Sort Timeline (Speed Descending)
    timeline_unsorted.sort(key=lambda x: x['speed'], reverse=True)

    state['timeline'] = [item['id'] for item in timeline_unsorted]
    state['turn_char_id'] = None

    # Broadcast Timeline Info
    log_msg = "行動順が決まりました:<br>"
    for idx, item in enumerate(timeline_unsorted):
        char = next((c for c in state['characters'] if c['id'] == item['id']), None)
        if char:
            log_msg += f"{idx+1}. {char['name']} (計{item['speed']})<br>"

    emit('new_log', {'message': log_msg, 'type': 'info'}, room=room)

    broadcast_state_update(room)
    save_specific_room_state(room)

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
        # Remove wide users from current positions
        remaining_timeline = [uid for uid in current_timeline if uid not in wide_user_ids]
        # Prepend wide users (filter valid ones)
        valid_wide_ids = [uid for uid in wide_user_ids if any(str(c['id']) == str(uid) for c in state['characters'])]

        # New timeline: [Wide Users] + [Remaining Users]
        state['timeline'] = valid_wide_ids + remaining_timeline
        logger.debug(f"[DEBUG] Valid wide IDs: {valid_wide_ids}")
        logger.debug(f"[DEBUG] New timeline: {state['timeline']}")
    else:
        broadcast_log(room, "広域攻撃予約: なし", 'info')

    save_specific_room_state(room)
    broadcast_state_update(room)

    # Proceed to first turn
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
    from manager.room_manager import ROOM_USERS
    current_room_users = ROOM_USERS.get(room, {})

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


