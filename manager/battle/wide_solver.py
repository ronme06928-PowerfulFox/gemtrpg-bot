import re
import json
from extensions import all_skill_data, socketio
from manager.room_manager import (
    get_room_state, save_specific_room_state, broadcast_log,
    broadcast_state_update, _update_char_stat
)
from manager.game_logic import (
    get_status_value, remove_buff, apply_buff, process_skill_effects,
    calculate_power_bonus, calculate_buff_power_bonus
)
from manager.skill_effects import apply_skill_effects_bidirectional
from manager.dice_roller import roll_dice
from manager.battle.core import (
    format_skill_display_from_command, execute_pre_match_effects,
    process_simple_round_end, proceed_next_turn,
    calculate_opponent_skill_modifiers
)
from manager.utils import resolve_placeholders
from manager.logs import setup_logger

logger = setup_logger(__name__)

def setup_wide_match_declaration(room, data, username):
    state = get_room_state(room)
    if not state: return

    targets_data = data.get('targets', [])
    defender_ids = data.get('defender_ids', [])
    attacker_id = data.get('attacker_id')
    mode = data.get('mode', 'individual')

    # active_match 初期化
    defenders = []

    # 速度統計ヘルパー
    def get_speed_stat(char):
        curr = get_status_value(char, '速度')
        return curr

    # Normalize targets from simple IDs if needed
    if not targets_data and defender_ids:
        targets_data = [{'id': did} for did in defender_ids]

    # ターゲットを展開してソート（速度順など）
    for t in targets_data:
        tid = t.get('id')
        char = next((c for c in state['characters'] if c.get('id') == tid), None)
        if char:
            defenders.append({
                'id': tid,
                'name': char['name'],
                'speed': get_speed_stat(char),
                'declared': False,
                'skill_id': None,
                'command': None
            })

    # Sort by speed (descending)
    defenders.sort(key=lambda x: x['speed'], reverse=True)

    state['active_match'] = {
        'is_active': True,
        'match_type': 'wide',
        'mode': mode,
        'attacker_id': attacker_id,
        'attacker_declared': False,
        'defenders': defenders,
        'match_id': data.get('match_id', 'new_wide_match'),
        'opened_by': username
    }

    save_specific_room_state(room)
    broadcast_state_update(room) # Ensure client receives active_match
    broadcast_log(room, f"⚔️ 広域マッチ宣言フェーズを開始します (対象: {len(defenders)}体)", 'info')

    socketio.emit('wide_skill_users_declared', {
        'attacker_id': attacker_id,
        'defenders': defenders,
        'mode': mode
    }, to=room)

def update_defender_declaration(room, data):
    state = get_room_state(room)
    if not state: return
    active_match = state.get('active_match')
    if not active_match or not active_match.get('is_active'): return

    defender_id = data.get('defender_id')
    skill_id = data.get('skill_id')
    command = data.get('command')
    # status_corrections = data.get('status_corrections') # 必要なら保存

    # Update state
    updated = False
    for d in active_match.get('defenders', []):
        if d.get('id') == defender_id:
            d['declared'] = True
            d['skill_id'] = skill_id
            d['command'] = command
            # d['data'] = data # 全データを保存しておくと後で便利かも
            # commandはfinal扱いとする。min/max/range_textも保存して表示用に使用
            d['data'] = {
                'final_command': command,
                'min': data.get('min'),
                'max': data.get('max'),
                'damage_range_text': data.get('damage_range_text') # If client sends it
            }
            updated = True
            break

    if updated:
        save_specific_room_state(room)
        broadcast_state_update(room) # Force full UI refresh
        # 部分更新通知 (Keep for specific animations if any)
        socketio.emit('wide_defender_updated', {
            'defender_id': defender_id,
            'declared': True
        }, to=room)

def update_attacker_declaration(room, data):
    state = get_room_state(room)
    if not state: return
    active_match = state.get('active_match')
    if not active_match or not active_match.get('is_active'): return

    # attacker_id check?
    # data contains {attacker_id, skill_id, command, ...}

    active_match['attacker_declared'] = True
    active_match['attacker_data'] = data

    save_specific_room_state(room)
    broadcast_state_update(room) # Force full UI refresh
    socketio.emit('wide_attacker_updated', {
        'declared': True
    }, to=room)


def execute_wide_match(room, username):
    state = get_room_state(room)
    if not state: return

    active_match = state.get('active_match')
    if not active_match or not active_match.get('is_active') or active_match.get('match_type') != 'wide':
        logger.warning("No active wide match to execute")
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

    # コスト消費処理
    def consume_skill_cost(char, skill_d, skill_id_log):
        if not skill_d: return
        try:
            rule_json_str = skill_d.get('特記処理', '{}')
            rule_data = json.loads(rule_json_str)
            tags = rule_data.get('tags', skill_d.get('tags', []))
            if "即時発動" not in tags:
                for cost in rule_data.get("cost", []):
                    c_type = cost.get("type")
                    c_val = int(cost.get("value", 0))
                    if c_val > 0 and c_type:
                        curr = get_status_value(char, c_type)
                        new_val = max(0, curr - c_val)
                        _update_char_stat(room, char, c_type, new_val, username=f"[{skill_id_log}]")
                        broadcast_log(room, f"{char['name']} は {c_type}を{c_val}消費しました (残:{new_val})", 'system')
        except: pass

    consume_skill_cost(attacker_char, attacker_skill_data, attacker_skill_id)

    for def_data in defenders:
        def_id = def_data.get('id')
        def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
        if def_char:
             def_skill_id = def_data.get('skill_id')
             def_skill_data = all_skill_data.get(def_skill_id)
             consume_skill_cost(def_char, def_skill_data, def_skill_id)

    if 'used_skills_this_round' not in attacker_char:
        attacker_char['used_skills_this_round'] = []
    attacker_char['used_skills_this_round'].append(attacker_skill_id)

    # Execute match
    broadcast_log(room, f"⚔️ === 広域マッチ開始 ({mode}モード) ===", 'match-start')
    broadcast_log(room, f"🗡️ 攻撃者: {attacker_char['name']} [{attacker_skill_id}]", 'info')

    attacker_roll = roll_dice(attacker_command)
    broadcast_log(room, f"   → ロール: {attacker_roll['details']} = {attacker_roll['total']}", 'dice')

    results = []
    attacker_effects = []
    if attacker_skill_data:
        try:
            d = json.loads(attacker_skill_data.get('特記処理', '{}'))
            attacker_effects = d.get('effects', [])
        except: pass

    attacker_effects = []
    if attacker_skill_data:
        try:
            d = json.loads(attacker_skill_data.get('特記処理', '{}'))
            attacker_effects = d.get('effects', [])
        except: pass

    # Apply Local Changes Helper
    def apply_local_changes(changes):
        extra = 0
        for (char, type, name, value) in changes:
            if type == "APPLY_STATE":
                curr = get_status_value(char, name)
                _update_char_stat(room, char, name, curr + value, username=f"[{attacker_skill_id}]")
            elif type == "APPLY_BUFF":
                apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
            elif type == "REMOVE_BUFF":
                remove_buff(char, name)
            elif type == "CUSTOM_DAMAGE":
                extra += value
            elif type == "APPLY_STATE_TO_ALL_OTHERS":
                orig_target_id = char.get("id")
                orig_target_type = char.get("type")
                for other_char in state["characters"]:
                    if other_char.get("type") == orig_target_type and other_char.get("id") != orig_target_id:
                        curr = get_status_value(other_char, name)
                        _update_char_stat(room, other_char, name, curr + value, username=f"[{name}]")
        return extra

    # ★ 追加: マッチ不可 (Unmatchable) の処理
    # ダイス勝負を行わず、一方的に効果 (HIT) を適用する
    attacker_tags = attacker_skill_data.get('tags', []) if attacker_skill_data else []
    if "マッチ不可" in attacker_tags:
        broadcast_log(room, f"⚠️ [マッチ不可] のため、ダイス勝負をスキップして効果を適用します。", 'info')

        for def_data in defenders:
            def_id = def_data.get('id')
            def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
            if not def_char: continue

            # ダメージは発生しない前提だが、effectsの処理を行う
            # タイミングは HIT として扱う
            if attacker_effects:
                dmg_bonus, logs, changes = process_skill_effects(attacker_effects, "HIT", attacker_char, def_char, None, context={'characters': state['characters']})
                for log_msg in logs:
                    broadcast_log(room, log_msg, 'skill-effect')

                # apply_local_changes で状態異常等を適用
                apply_local_changes(changes)

    elif mode == 'combined':
        # Combined Mode
        defender_rolls = []
        valid_defenders = []
        total_defender_roll = 0

        for def_data in defenders:
            def_id = def_data.get('id')
            def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
            if not def_char: continue

            def_skill_id = def_data.get('skill_id')
            def_command = def_data.get('command')
            # If using pre-calc command stored in data
            if def_data.get('data') and def_data['data'].get('final_command'):
                 def_command = def_data['data']['final_command']

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

        if attacker_roll['total'] > total_defender_roll:
            diff = attacker_roll['total'] - total_defender_roll
            broadcast_log(room, f"   → 🗡️ 攻撃者勝利! 差分: {diff}", 'match-result')

            for dr in defender_rolls:
                def_char = dr['char']
                results.append({'defender': def_char['name'], 'result': 'win', 'damage': diff})
                current_hp = get_status_value(def_char, 'HP')
                new_hp = max(0, current_hp - diff)
                _update_char_stat(room, def_char, 'HP', new_hp, username=f"[{attacker_skill_id}]")
                broadcast_log(room, f"   → {def_char['name']} に {diff} ダメージ", 'damage')

                if attacker_effects:
                    dmg_bonus, logs, changes = process_skill_effects(attacker_effects, "HIT", attacker_char, def_char, None, context={'characters': state['characters']})
                    for log_msg in logs:
                        broadcast_log(room, log_msg, 'skill-effect')
                    diff_bonus = apply_local_changes(changes)
                    if diff_bonus > 0:
                        current_hp = get_status_value(def_char, 'HP')
                        new_hp = max(0, current_hp - diff_bonus)
                        _update_char_stat(room, def_char, 'HP', new_hp, username=f"[{attacker_skill_id}追加]")
                        broadcast_log(room, f"   → {def_char['name']} に追加 {diff_bonus} ダメージ", 'damage')

        elif total_defender_roll > attacker_roll['total']:
            diff = total_defender_roll - attacker_roll['total']
            broadcast_log(room, f"   → 🛡️ 防御者勝利! 差分: {diff}", 'match-result')

            current_hp = get_status_value(attacker_char, 'HP')
            new_hp = max(0, current_hp - diff)
            _update_char_stat(room, attacker_char, 'HP', new_hp, username="[防御者勝利]")
            broadcast_log(room, f"   → {attacker_char['name']} に {diff} ダメージ", 'damage')
            for dr in defender_rolls:
                results.append({'defender': dr['char']['name'], 'result': 'lose', 'damage': diff})
        else:
            broadcast_log(room, f"   → 引き分け", 'match-result')
            for dr in defender_rolls:
                results.append({'defender': dr['char']['name'], 'result': 'draw', 'damage': 0})

    else:
        # Individual Mode
        for def_data in defenders:
            def_id = def_data.get('id')
            def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
            if not def_char: continue

            def_skill_id = def_data.get('skill_id')
            def_skill_data = all_skill_data.get(def_skill_id)

            # Reset temp bonus
            attacker_char['_base_power_bonus'] = 0
            def_char['_base_power_bonus'] = 0

            # Apply Pre-Match
            execute_pre_match_effects(room, attacker_char, def_char, attacker_skill_data, def_skill_data)
            if def_skill_data:
                execute_pre_match_effects(room, def_char, attacker_char, def_skill_data, attacker_skill_data)

            # Thorns (Simplified inline)
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

            # Dynamic base power mod logic (replicated from socket_wide_match)
            bp_mod = def_char.get('_base_power_bonus', 0)
            if bp_mod != 0 and not using_precalc:
                def_command = f"{def_command}+{bp_mod}"
                logger.debug(f"Applied BaseMod {bp_mod} -> {def_command}")

            def_roll = roll_dice(def_command)

            attacker_total = attacker_roll['total']
            defender_total = def_roll['total']

            if attacker_total > defender_total:
                # 攻撃成功
                is_defense_skill = False
                is_evasion_skill = False
                if def_skill_data:
                    cat = def_skill_data.get('分類', '')
                    tags = def_skill_data.get('tags', [])
                    if cat == '防御' or '防御' in tags or '守備' in tags:
                        is_defense_skill = True
                    if cat == '回避' or '回避' in tags:
                        is_evasion_skill = True

                damage = 0
                result_type = 'win' # Attacker win

                if is_defense_skill:
                    # 防御スキル: ダメージ軽減 (攻撃 - 防御)
                    damage = max(0, attacker_total - defender_total)
                    broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (防御)", 'dice')
                    broadcast_log(room, f"   → 🗡️ 攻撃命中 (軽減): {damage} ダメージ", 'match-result')
                elif is_evasion_skill:
                    # 回避スキル: 回避失敗なら直撃
                    damage = attacker_total
                    broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (回避失敗)", 'dice')
                    broadcast_log(room, f"   → 🗡️ 攻撃命中 (直撃): {damage} ダメージ", 'match-result')

                    # 再回避ロック解除 check
                    from plugins.buffs.dodge_lock import DodgeLockBuff
                    if DodgeLockBuff.has_re_evasion(def_char):
                         remove_buff(def_char, "再回避ロック")
                         broadcast_log(room, f"[再回避失敗！(ロック解除)]", 'info')

                else:
                    # 通常(攻撃スキル等で反撃失敗): 直撃扱い (Duel仕様に準拠)
                    # または カウンター合戦なら差分？ -> USER要望「回避スキルの場合は攻撃者のダメージがそのまま入る」
                    # 通常の攻撃スキルでの応戦負けは一般的に「相殺」か「一方的」か？
                    # Duel Solver Check: result_a > result_d -> damage = result_a (Full Damage) if not Defense.
                    # 攻撃vs攻撃で負けた場合もFull Damage (Duel Solver Line 520)
                    damage = attacker_total
                    broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']}", 'dice')
                    broadcast_log(room, f"   → 🗡️ 攻撃命中: {damage} ダメージ", 'match-result')

                results.append({'defender': def_char['name'], 'result': 'win', 'damage': damage}) # Attacker win in terms of dmg

                if attacker_effects:
                    dmg_bonus, logs, changes = process_skill_effects(attacker_effects, "HIT", attacker_char, def_char, None, context={'characters': state['characters']})
                    for log_msg in logs:
                        broadcast_log(room, log_msg, 'skill-effect')
                    damage += apply_local_changes(changes)

                current_hp = get_status_value(def_char, 'HP')
                new_hp = max(0, current_hp - damage)
                _update_char_stat(room, def_char, 'HP', new_hp, username=f"[{attacker_skill_id}]")

            elif defender_total > attacker_total:
                # 防御側勝利
                is_defense_skill = False
                if def_skill_data:
                    cat = def_skill_data.get('分類', '')
                    tags = def_skill_data.get('tags', [])
                    if cat == '防御' or '防御' in tags or '守備' in tags:
                        is_defense_skill = True

                if is_defense_skill:
                    # 防御スキルでの勝利: ダメージ0 (反撃なし)
                    damage = 0
                    results.append({'defender': def_char['name'], 'result': 'lose', 'damage': 0}) # Attacker lose, but 0 dmg
                    broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (防御成功)", 'dice')
                    broadcast_log(room, f"   → 🛡️ 防御成功! (ダメージなし)", 'match-result')
                else:
                    # 回避スキルや攻撃スキルでの勝利: 反撃ダメージ発生
                    damage = defender_total
                    if "回避" in (def_skill_data.get('tags', []) if def_skill_data else []):
                         # 回避成功: ダメージ0
                         # 再回避ロック処理
                         damage = 0
                         results.append({'defender': def_char['name'], 'result': 'lose', 'damage': 0})
                         broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (回避成功)", 'dice')
                         broadcast_log(room, f"   → 🛡️ 回避成功!", 'match-result')

                         broadcast_log(room, "[再回避可能！]", 'info')
                         apply_buff(def_char, "再回避ロック", 1, 0, data={"skill_id": def_skill_id, "buff_id": "Bu-05"})

                    else:
                        # 攻撃スキルでの勝利 (カウンター)
                        results.append({'defender': def_char['name'], 'result': 'lose', 'damage': damage})
                        broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']}", 'dice')
                        broadcast_log(room, f"   → 🛡️ 防御者勝利! (カウンター): {damage}", 'match-result')

                        current_hp = get_status_value(attacker_char, 'HP')
                        new_hp = max(0, current_hp - damage)
                        _update_char_stat(room, attacker_char, 'HP', new_hp, username=f"[{def_skill_id}]")

            else:
                # 引き分け
                results.append({'defender': def_char['name'], 'result': 'draw', 'damage': 0})
                broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']}", 'dice')
                broadcast_log(room, f"   → 引き分け", 'match-result')

    broadcast_log(room, f"⚔️ === 広域マッチ終了 ===", 'match-end')

    attacker_char['hasActed'] = True
    no_defender_acted = False
    attacker_tags = attacker_skill_data.get('tags', []) if attacker_skill_data else []
    if 'マッチ不可' in attacker_tags:
        no_defender_acted = True

    for def_data in defenders:
        def_id = def_data.get('id')
        def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
        if def_char and not no_defender_acted:
            def_char['hasActed'] = True

    state['active_match'] = None

    round_end_requested = False
    if 'ラウンド終了' in attacker_tags:
        for c in state['characters']:
            c['hasActed'] = True
        broadcast_log(room, f"[{attacker_skill_id}] の効果でラウンドが強制終了します。", 'round')
        round_end_requested = True

    proceed_next_turn(room)

    socketio.emit('match_modal_closed', {}, to=room)
    if 'active_match' in state:
        del state['active_match']
        save_specific_room_state(room)

    if round_end_requested:
        process_simple_round_end(state, room)
