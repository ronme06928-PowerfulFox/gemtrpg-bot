import re
import json
from extensions import all_skill_data, socketio
from manager.room_manager import (
    get_room_state, save_specific_room_state, broadcast_log,
    broadcast_state_update, _update_char_stat
)
from manager.game_logic import (
    get_status_value, remove_buff, apply_buff, process_skill_effects,
    calculate_power_bonus, calculate_buff_power_bonus, calculate_damage_multiplier
)
from manager.skill_effects import apply_skill_effects_bidirectional
from manager.dice_roller import roll_dice
from manager.battle.core import (
    format_skill_display_from_command, execute_pre_match_effects,
    process_simple_round_end, proceed_next_turn,
    calculate_opponent_skill_modifiers, process_on_hit_buffs
)
from manager.summons.service import apply_summon_change
from manager.utils import resolve_placeholders, get_effective_origin_id
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
                'damage_range_text': data.get('damage_range_text'), # If client sends it
                'senritsu_penalty': data.get('senritsu_penalty', 0)
            }
            updated = True
            break

    if updated:
        save_specific_room_state(room)
        # broadcast_state_update(room) # ★ 修正: 全データ送信を停止 (差分更新イベントのみ送信)

        # 部分更新通知
        socketio.emit('wide_defender_updated', {
            'defender_id': defender_id,
            'declared': True,
            'data': d['data'] # ★ 追加: 描画に必要な詳細データ
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
    # broadcast_state_update(room) # ★ 修正: 全データ送信を停止

    socketio.emit('wide_attacker_updated', {
        'declared': True,
        'attacker_id': data.get('attacker_id'),
        'data': active_match['attacker_data'] # ★ 追加
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
    attacker_char['_base_power_bonus'] = 0
    attacker_char['_final_power_bonus'] = 0

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
             if 'used_skills_this_round' not in def_char:
                 def_char['used_skills_this_round'] = []
             def_char['used_skills_this_round'].append(def_skill_id)

    if 'used_skills_this_round' not in attacker_char:
        attacker_char['used_skills_this_round'] = []
    attacker_char['used_skills_this_round'].append(attacker_skill_id)

    # Execute match
    broadcast_log(room, f"⚔️ === 広域マッチ開始 ({mode}モード) ===", 'match-start')
    broadcast_log(room, f"🗡️ 攻撃者: {attacker_char['name']} [{attacker_skill_id}]", 'info')

    attacker_roll = roll_dice(attacker_command)
    broadcast_log(room, f"   → ロール: {attacker_roll['details']} = {attacker_roll['total']}", 'dice')

    attacker_total = attacker_roll['total']

    # --- Senritsu (Terror) Penalty: Attacker ---
    attacker_senritsu_penalty = int(attacker_data.get('senritsu_penalty', 0))
    if attacker_senritsu_penalty > 0:
        attacker_total = max(0, attacker_total - attacker_senritsu_penalty)
        # Consume Senritsu
        curr_senritsu = get_status_value(attacker_char, '戦慄')
        _update_char_stat(room, attacker_char, '戦慄', max(0, curr_senritsu - attacker_senritsu_penalty), username=f"[{attacker_char['name']}:戦慄消費(ダイス-{attacker_senritsu_penalty})]")
        broadcast_log(room, f"   → 戦慄ペナルティ: -{attacker_senritsu_penalty} (最終: {attacker_total})", 'dice')

    # --- Wadatsumi (ID: 9) Bonus: Slash Power +1 ---
    attacker_origin = get_effective_origin_id(attacker_char)
    if attacker_origin == 9 and attacker_skill_data.get('属性') == '斬撃':
         attacker_total += 1
         broadcast_log(room, f"[綿津見恩恵] 斬撃威力+1 → {attacker_total}", 'info')

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
    def apply_local_changes(changes, primary_target=None):
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
            elif type == "MODIFY_BASE_POWER":
                char['_base_power_bonus'] = int(char.get('_base_power_bonus', 0) or 0) + int(value or 0)
            elif type == "MODIFY_FINAL_POWER":
                char['_final_power_bonus'] = int(char.get('_final_power_bonus', 0) or 0) + int(value or 0)
            elif type == "CUSTOM_DAMAGE":
                # ★修正: 攻撃対象へのダメージのみを加算し、それ以外（自傷など）は直接適用する
                if primary_target and char.get('id') == primary_target.get('id'):
                    extra += value
                else:
                    curr = get_status_value(char, 'HP')
                    _update_char_stat(room, char, 'HP', max(0, curr - value), username=f"[{name}]", source=DamageSource.SKILL_EFFECT)

            elif type == "APPLY_STATE_TO_ALL_OTHERS":
                orig_target_id = char.get("id")
                orig_target_type = char.get("type")
                for other_char in state["characters"]:
                    if other_char.get("type") == orig_target_type and other_char.get("id") != orig_target_id:
                        curr = get_status_value(other_char, name)
                        _update_char_stat(room, other_char, name, curr + value, username=f"[{name}]")
            elif type == "SUMMON_CHARACTER":
                res = apply_summon_change(room, state, char, value)
                if res.get("ok"):
                    broadcast_log(room, res.get("message", "召喚が発生した。"), "state-change")
                else:
                    logger.warning("[wide summon failed] %s", res.get("message"))
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


            # ★ 1. ダメージ計算 (Unmatchableでも攻撃側の値は既に計算済み: attacker_total)
            damage = attacker_total

            # Attacker's HIT & UNOPPOSED effects
            # Pre-calc effects from attacker_effects

            # process_skill_effects expects 'attacker' or 'defender' logic?
            # It primarily processes the effects list.

            total_damage = damage
            log_snippets = []

            # Apply UNOPPOSED effects
            unop_bonus, unop_logs, unop_changes = process_skill_effects(attacker_effects, "UNOPPOSED", attacker_char, def_char, None, context={'timeline': state.get('timeline', []), 'characters': state['characters'], 'room': room})
            log_snippets.extend(unop_logs)
            apply_local_changes(unop_changes, def_char)
            total_damage += unop_bonus

            # Apply HIT effects (order is aligned with select/resolve one-sided chain)
            hit_bonus, hit_logs, hit_changes = process_skill_effects(attacker_effects, "HIT", attacker_char, def_char, None, context={'timeline': state.get('timeline', []), 'characters': state['characters'], 'room': room})
            log_snippets.extend(hit_logs)
            apply_local_changes(hit_changes, def_char)
            total_damage += hit_bonus

            # Apply Damage to Defender
            # Defense multiplier (def_char might have generic defense mods, but no roll here)
            d_mult, d_logs = calculate_damage_multiplier(def_char)
            final_damage = int(total_damage * d_mult)

            if d_logs:
                 log_snippets.append(f"(防:{'/'.join(d_logs)} x{d_mult:.2f})")

            # Apply damage
            if final_damage > 0:
                 current_hp = get_status_value(def_char, 'HP')
                 _update_char_stat(room, def_char, 'HP', current_hp - final_damage, username=f"[{attacker_skill_id}]")
                 broadcast_log(room, f"{def_char['name']} に {final_damage} ダメージ {' '.join(log_snippets)}", 'damage')
            else:
                 if log_snippets:
                     broadcast_log(room, f"{def_char['name']} に効果適用: {' '.join(log_snippets)}", 'info')

            # ★ 追加: 防御側の PRE_MATCH 効果を適用 (自己バフなど)
            for def_data in defenders:
                def_id = def_data.get('id')
                def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
                if not def_char: continue

                def_skill_id = def_data.get('skill_id')
                def_skill_data = all_skill_data.get(def_skill_id)

                # PRE_MATCH実行
                if def_skill_data:
                    execute_pre_match_effects(room, def_char, attacker_char, def_skill_data, attacker_skill_data)

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

            # --- Senritsu (Terror) Penalty: Defender ---
            def_senritsu_penalty = int(def_data.get('data', {}).get('senritsu_penalty', 0))
            if def_senritsu_penalty > 0:
                def_roll_result['total'] = max(0, def_roll_result['total'] - def_senritsu_penalty)
                # Consume Senritsu
                curr_senritsu = get_status_value(def_char, '戦慄')
                _update_char_stat(room, def_char, '戦慄', max(0, curr_senritsu - def_senritsu_penalty), username=f"[{def_char['name']}:戦慄消費(ダイス-{def_senritsu_penalty})]")
                def_roll_result['details'] += f" -戦慄({def_senritsu_penalty})"

            defender_rolls.append({
                'char': def_char,
                'skill_id': def_skill_id,
                'roll': def_roll_result
            })
            valid_defenders.append(def_char)
            total_defender_roll += def_roll_result['total']

            broadcast_log(room, f"🛡️ {def_char['name']} [{def_skill_id}]: {def_roll_result['details']} = {def_roll_result['total']}", 'dice')

            broadcast_log(room, f"🛡️ {def_char['name']} [{def_skill_id}]: {def_roll_result['details']} = {def_roll_result['total']}", 'dice')

        # --- Walwaire (ID: 13) Logic (Combined) ---
        # 1. Attacker is Walwaire -> Defender Total -1 ?
        # Rule: "マッチ相手の最終威力を-1"
        # In Combined, opponent is the group. Logic: reduce total by 1? Or each roll?
        # Typically wide rules apply normally. Let's assume total -1.
        if attacker_origin == 13:
             if total_defender_roll > 2:
                 total_defender_roll -= 1
                 broadcast_log(room, f"[ヴァルヴァイレ恩恵] 防御側合計 -1", 'info')

        # 2. Any Defender is Walwaire -> Attacker -1 (Non-stacking)
        has_walwaire_defender = any(get_effective_origin_id(d) == 13 for d in valid_defenders)
        if has_walwaire_defender:
             if attacker_total > 2:
                 attacker_total -= 1
                 broadcast_log(room, f"[ヴァルヴァイレ恩恵] 攻撃側値 -1", 'info')

        broadcast_log(room, f"📊 防御者合計: {total_defender_roll} vs 攻撃者: {attacker_total}", 'info')

        if attacker_total > total_defender_roll:
            diff = attacker_total - total_defender_roll

            # ★ 修正: 攻撃側が防御/回避スキルの場合はダメージ0
            attacker_params = all_skill_data.get(attacker_skill_id, {})
            att_cat = attacker_params.get('分類', '')
            att_tags = attacker_params.get('tags', [])

            if att_cat == '防御' or att_cat == '回避' or '防御' in att_tags or '回避' in att_tags:
                broadcast_log(room, f"   → 🛡️ 攻撃側勝利 ({att_cat})! (ダメージなし)", 'match-result')
                # ダメージ処理スキップ、ただし効果処理は必要なら呼ぶ（今回は簡易的にスキップ）
            else:
                broadcast_log(room, f"   → 🗡️ 攻撃者勝利! 差分: {diff}", 'match-result')

                for dr in defender_rolls:
                    def_char = dr['char']
                    results.append({'defender': def_char['name'], 'result': 'win', 'damage': diff})
                    current_hp = get_status_value(def_char, 'HP')
                    extra_dmg = process_on_hit_buffs(attacker_char, def_char, diff, [])
                    if extra_dmg > 0:
                         broadcast_log(room, f"[{attacker_char['name']}] 追加ダメージ +{extra_dmg}", 'buff')
                    new_hp = max(0, current_hp - (diff + extra_dmg))
                    _update_char_stat(room, def_char, 'HP', new_hp, username=f"[{attacker_skill_id}]")
                    broadcast_log(room, f"   → {def_char['name']} に {diff} ダメージ", 'damage')

                    if attacker_effects:
                        dmg_bonus, logs, changes = process_skill_effects(attacker_effects, "HIT", attacker_char, def_char, None, context={'timeline': state.get('timeline', []), 'characters': state['characters'], 'room': room})
                        for log_msg in logs:
                            broadcast_log(room, log_msg, 'skill-effect')
                        diff_bonus = apply_local_changes(changes, def_char)
                        if diff_bonus > 0:
                            current_hp = get_status_value(def_char, 'HP')
                            new_hp = max(0, current_hp - diff_bonus)
                            _update_char_stat(room, def_char, 'HP', new_hp, username=f"[{attacker_skill_id}追加]")
                            broadcast_log(room, f"   → {def_char['name']} に追加 {diff_bonus} ダメージ", 'damage')

        elif total_defender_roll > attacker_total:
            diff = total_defender_roll - attacker_total
            broadcast_log(room, f"   → 🛡️ 防御者勝利! 差分: {diff}", 'match-result')

            current_hp = get_status_value(attacker_char, 'HP')
            new_hp = max(0, current_hp - diff)
            _update_char_stat(room, attacker_char, 'HP', new_hp, username="[防御者勝利]", save=False)
            broadcast_log(room, f"   → {attacker_char['name']} に {diff} ダメージ", 'damage', save=False)
            for dr in defender_rolls:
                results.append({'defender': dr['char']['name'], 'result': 'lose', 'damage': diff})

            # --- Gyan Barth (ID: 8) Reflect Logic (Combined) ---
            # 防御側勝利時、余剰ダメージを反射
            # 条件: Gyan Barth出身者がおり、かつそのキャラクターが「防御スキル」を使用していること

            # 1. バルフ出身かつ防御スキルの使用者がいるかチェック
            reflector = None
            for dr in defender_rolls:
                char = dr['char']
                if get_effective_origin_id(char) == 8:
                    # Check skill type
                    sid = dr.get('skill_id')
                    sdata = all_skill_data.get(sid)
                    if sdata:
                        cat = sdata.get('分類', '')
                        tags = sdata.get('tags', [])
                        if cat == '防御' or '防御' in tags or '守備' in tags:
                            reflector = char
                            break

            if reflector:
                if diff > 0:
                     curr_hp = get_status_value(attacker_char, 'HP')
                     _update_char_stat(room, attacker_char, 'HP', curr_hp - diff, username="[反射ダメージ]", save=False)
                     broadcast_log(room, f"[ギァン・バルフ恩恵] {reflector['name']}が余剰 {diff} ダメージを攻撃者に反射！", 'info', save=False)

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
            attacker_char['_final_power_bonus'] = 0
            def_char['_base_power_bonus'] = 0
            def_char['_final_power_bonus'] = 0

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
                          _update_char_stat(room, def_char, "荊棘", max(0, thorn_val - bp), username=f"[{def_skill_id}:荊棘詳細]", save=False)

            using_precalc = False
            def_command = def_data.get('command', '2d6')
            if def_data.get('data') and def_data['data'].get('final_command'):
                def_command = def_data['data']['final_command']
                using_precalc = True

            # Dynamic power mod logic
            # PRE_MATCH はロール直前に適用されるため、precalcコマンドにも追記する。
            bp_mod = int(def_char.get('_base_power_bonus', 0) or 0)
            fp_mod = int(def_char.get('_final_power_bonus', 0) or 0)
            total_power_mod = bp_mod + fp_mod
            if total_power_mod != 0:
                def_command = f"{def_command}{'+' if total_power_mod > 0 else ''}{total_power_mod}"
                logger.debug(f"Applied PowerMod base={bp_mod} final={fp_mod} -> {def_command} (precalc={using_precalc})")

            def_roll = roll_dice(def_command)
            defender_total = def_roll['total']

            # --- Senritsu (Terror) Penalty: Defender ---
            def_senritsu_penalty = int(def_data.get('data', {}).get('senritsu_penalty', 0))
            if def_senritsu_penalty > 0:
                defender_total = max(0, defender_total - def_senritsu_penalty)
                def_roll['total'] = defender_total
                # Consume Senritsu
                curr_senritsu = get_status_value(def_char, '戦慄')
                _update_char_stat(room, def_char, '戦慄', max(0, curr_senritsu - def_senritsu_penalty), username=f"[{def_char['name']}:戦慄消費(ダイス-{def_senritsu_penalty})]")
                def_roll['details'] += f" -戦慄({def_senritsu_penalty})"

            # --- Walwaire (ID: 13) Logic (Individual) ---

            # 1. Attacker is Walwaire -> Defender -1
            if attacker_origin == 13:
                 if defender_total > 2:
                     defender_total -= 1
                     # 個別ログはうるさいので省略、または詳細に含める

            # 2. Defender is Walwaire -> Attacker -1
            # Note: Attacker total effectively reduced for THIS match only
            effective_attacker_total = attacker_total
            if get_effective_origin_id(def_char) == 13:
                 if effective_attacker_total > 2:
                     effective_attacker_total -= 1

            # Display modified totals if changed
            if defender_total != def_roll['total'] or effective_attacker_total != attacker_total:
                 broadcast_log(room, f"   (補正後判定: 攻{effective_attacker_total} vs 防{defender_total})", 'info')


            if effective_attacker_total > defender_total:
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
                    damage = max(0, effective_attacker_total - defender_total)

                    # ★ 修正: 攻撃者が防御/回避スキルならダメージ0
                    att_params = all_skill_data.get(attacker_skill_id, {})
                    if att_params.get('分類') == '防御' or att_params.get('分類') == '回避' or '防御' in att_params.get('tags', []) or '回避' in att_params.get('tags', []):
                         damage = 0
                         broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (攻撃側も防御/回避のためダメージなし)", 'dice', save=False)
                    else:
                        broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (防御)", 'dice', save=False)
                        broadcast_log(room, f"   → 🗡️ 攻撃命中 (軽減): {damage} ダメージ", 'match-result', save=False)
                elif is_evasion_skill:
                    # 回避スキル: 回避失敗なら直撃
                    damage = effective_attacker_total
                    broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (回避失敗)", 'dice', save=False)
                    broadcast_log(room, f"   → 🗡️ 攻撃命中 (直撃): {damage} ダメージ", 'match-result', save=False)

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
                    damage = effective_attacker_total

                    # ★ 修正: 攻撃者が防御/回避スキルならダメージ0
                    att_params = all_skill_data.get(attacker_skill_id, {})
                    if att_params.get('分類') == '防御' or att_params.get('分類') == '回避' or '防御' in att_params.get('tags', []) or '回避' in att_params.get('tags', []):
                         damage = 0
                         broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (攻撃側も防御/回避のためダメージなし)", 'dice', save=False)
                    else:
                        broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']}", 'dice', save=False)
                        broadcast_log(room, f"   → 🗡️ 攻撃命中: {damage} ダメージ", 'match-result', save=False)

                results.append({'defender': def_char['name'], 'result': 'win', 'damage': damage}) # Attacker win in terms of dmg

                if attacker_effects:
                    dmg_bonus, logs, changes = process_skill_effects(attacker_effects, "HIT", attacker_char, def_char, None, context={'characters': state['characters']})
                    for log_msg in logs:
                        broadcast_log(room, log_msg, 'skill-effect')
                    damage += apply_local_changes(changes, def_char)
                    extra_dmg = process_on_hit_buffs(attacker_char, def_char, damage, [])
                    if extra_dmg > 0:
                         broadcast_log(room, f"[{attacker_char['name']}] 追加ダメージ +{extra_dmg}", 'buff')
                    damage += extra_dmg

                current_hp = get_status_value(def_char, 'HP')
                new_hp = max(0, current_hp - damage)
                _update_char_stat(room, def_char, 'HP', new_hp, username=f"[{attacker_skill_id}]", save=False)

            elif defender_total > effective_attacker_total:
                # 防御側勝利
                is_defense_skill = False
                if def_skill_data:
                    cat = def_skill_data.get('分類', '')
                    tags = def_skill_data.get('tags', [])
                    if cat == '防御' or '防御' in tags or '守備' in tags:
                        is_defense_skill = True

                if is_defense_skill:
                    # 防御スキルでの勝利: ダメージ0 (反撃なし)
                    # ★ 修正: 防御勝利時にFP+1を付与
                    curr_fp = get_status_value(def_char, 'FP')
                    _update_char_stat(room, def_char, 'FP', curr_fp + 1, username="[マッチ勝利]", save=False)
                    damage = 0
                    results.append({'defender': def_char['name'], 'result': 'lose', 'damage': 0}) # Attacker lose, but 0 dmg
                    broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (防御成功)", 'dice')
                    broadcast_log(room, f"   → 🛡️ 防御成功! (ダメージなし)", 'match-result')

                    # --- Gyan Barth (ID: 8) Reflect Logic (Individual) ---
                    if get_effective_origin_id(def_char) == 8:
                         diff = defender_total - effective_attacker_total
                         if diff > 0:
                             curr_hp = get_status_value(attacker_char, 'HP')
                             _update_char_stat(room, attacker_char, 'HP', curr_hp - diff, username="[反射ダメージ]", save=False)
                             broadcast_log(room, f"[ギァン・バルフ恩恵] {def_char['name']}が余剰 {diff} ダメージを反射！", 'info', save=False)
                else:
                    # 回避スキルや攻撃スキルでの勝利: 反撃ダメージ発生
                    damage = defender_total
                    if "回避" in (def_skill_data.get('tags', []) if def_skill_data else []):
                         # 回避成功: ダメージ0
                         # ★ 修正: 回避勝利時にFP+1を付与
                         curr_fp = get_status_value(def_char, 'FP')
                         _update_char_stat(room, def_char, 'FP', curr_fp + 1, username="[マッチ勝利]", save=False)
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
                        broadcast_log(room, f"   → 🛡️ 防御者勝利! (カウンター): {damage}", 'match-result', save=False)

                        current_hp = get_status_value(attacker_char, 'HP')
                        new_hp = max(0, current_hp - damage)
                        _update_char_stat(room, attacker_char, 'HP', new_hp, username=f"[{def_skill_id}]", save=False)

            else:
                # 引き分け
                results.append({'defender': def_char['name'], 'result': 'draw', 'damage': 0})
                broadcast_log(room, f"🛡️ vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']}", 'dice')
                broadcast_log(room, f"   → 引き分け", 'match-result')

    broadcast_log(room, f"⚔️ === 広域マッチ終了 ===", 'match-end')

    # helper to consume action
    def consume_action(char_obj):
        if not char_obj: return
        timeline = state.get('timeline', [])
        current_entry_id = state.get('turn_entry_id')
        consumed = False

        # Priority: Current Turn
        if current_entry_id:
            for entry in timeline:
                if entry['id'] == current_entry_id and entry['char_id'] == char_obj['id']:
                    entry['acted'] = True
                    consumed = True
                    break

        # Fallback: First Available
        # Strict ID comparison
        if not consumed:
            for entry in timeline:
                if str(entry['char_id']) == str(char_obj['id']) and not entry.get('acted', False):
                    entry['acted'] = True
                    consumed = True
                    break

        remaining = any(str(e['char_id']) == str(char_obj['id']) and not e.get('acted', False) for e in timeline)
        char_obj['hasActed'] = not remaining
        logger.debug(f"[ActStatus(Wide)] {char_obj['name']}: remaining={remaining}, hasActed={char_obj['hasActed']}")

    consume_action(attacker_char)

    # ★ 修正: マッチ不可であっても防御側は行動済みとする (コスト消費や効果発動があるため)
    for def_data in defenders:
        def_id = def_data.get('id')
        def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
        if def_char:
            consume_action(def_char)

    # ★ 追加: END_MATCH 効果処理
    def execute_end_match(actor, target, skill_d, target_skill_d):
        if not skill_d: return
        try:
            d = json.loads(skill_d.get('特記処理', '{}'))
            effs = d.get('effects', [])
            _, logs, changes = process_skill_effects(effs, "END_MATCH", actor, target, target_skill_d, context={'timeline': state.get('timeline', []), 'characters': state['characters'], 'room': room})
            for log_msg in logs:
                broadcast_log(room, log_msg, 'skill-effect')
            apply_local_changes(changes, target) # Re-use local helper
        except: pass

    # Attacker END_MATCH
    execute_end_match(attacker_char, None, attacker_skill_data, None)

    # Defenders END_MATCH
    for def_data in defenders:
        def_id = def_data.get('id')
        def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
        if def_char:
            def_skill_id = def_data.get('skill_id')
            def_skill_data = all_skill_data.get(def_skill_id)
            execute_end_match(def_char, attacker_char, def_skill_data, attacker_skill_data)

    state['active_match'] = None

    round_end_requested = False
    round_end_requested = False
    if 'ラウンド終了' in attacker_tags:
        # Mark ALL timeline entries as acted
        for entry in state.get('timeline', []):
            entry['acted'] = True

        for c in state['characters']:
            # Force act all
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
