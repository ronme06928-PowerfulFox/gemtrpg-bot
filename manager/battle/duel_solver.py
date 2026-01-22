import re
import json
from extensions import all_skill_data, socketio

from manager.room_manager import (
    get_room_state, save_specific_room_state, broadcast_log,
    broadcast_state_update, _update_char_stat
)
from manager.game_logic import (
    get_status_value, calculate_damage_multiplier,
    remove_buff, apply_buff, process_skill_effects
)
from manager.skill_effects import apply_skill_effects_bidirectional
from manager.dice_roller import roll_dice

from manager.battle.core import (
    format_skill_display_from_command, process_on_damage_buffs,
    execute_pre_match_effects, proceed_next_turn
)
from plugins.buffs.dodge_lock import DodgeLockBuff

def update_duel_declaration(room, data, username):
    state = get_room_state(room)
    if not state: return
    active_match = state.get('active_match')
    if not active_match or not active_match.get('is_active'): return

    prefix = data.get('prefix') # 'attacker' or 'defender'
    commit = data.get('commit', False)

    updated = False
    skill_id = data.get('skill_id')

    if prefix == 'attacker':
        if commit is not None:
             active_match['attacker_declared'] = commit
             updated = True
        if skill_id:
             active_match['attacker_data'] = active_match.get('attacker_data', {})
             active_match['attacker_data']['skill_id'] = skill_id
    elif prefix == 'defender':
        if commit is not None:
             active_match['defender_declared'] = commit
             updated = True
        if skill_id:
             active_match['defender_data'] = active_match.get('defender_data', {})
             active_match['defender_data']['skill_id'] = skill_id

    if updated:
        save_specific_room_state(room)
        socketio.emit('match_data_updated', {
            'side': prefix,
            'declared': commit
        }, to=room)
        broadcast_state_update(room)


def handle_skill_declaration(room, data, username):
    state = get_room_state(room)
    if not state: return

    actor_id = data.get('actor_id')
    target_id = data.get('target_id')
    skill_id = data.get('skill_id')
    commit = data.get('commit', False)
    prefix = data.get('prefix') # visual_attacker, visual_defender

    actor = next((c for c in state['characters'] if str(c.get('id')) == str(actor_id)), None)
    target = next((c for c in state['characters'] if str(c.get('id')) == str(target_id)), None)

    if not actor: return

    skill_data = all_skill_data.get(skill_id)

    # Calculate Preview
    from manager.game_logic import calculate_skill_preview
    preview = calculate_skill_preview(actor, target, skill_data)

    # Return Result
    result_data = {
        'side': 'attacker' if 'attacker' in prefix else 'defender',
        'skill_id': skill_id,
        'final_command': preview['final_command'],
        'min_damage': preview['min_damage'],
        'max_damage': preview['max_damage'],
        'skill_details': preview['skill_details'],
        'correction_details': preview['correction_details'],
        'senritsu_dice_reduction': preview['senritsu_dice_reduction'],
        'senritsu_penalty': preview['senritsu_dice_reduction'],
        'power_breakdown': preview.get('power_breakdown', {}),
        'declared': commit,
        'prefix': prefix, # Required by client listener
        'enableButton': True
    }

    # If committing, update state
    if commit:
        # ★ 追加: 即時発動スキルの処理
        if prefix and prefix.startswith('immediate'):
             # ここで即座に実行する
             print(f"[Immediate] Executing {skill_id} for {actor['name']}")

             # コスト支払い
             rule_json_str = skill_data.get('特記処理', '{}')
             try:
                 rd = json.loads(rule_json_str)
                 effects_array = rd.get("effects", [])
                 # 即時発動なのでコストを支払う (verify_skill_costは通過済み想定だが、ここで消費処理)
                 for cost in rd.get("cost", []):
                     c_val = int(cost.get("value", 0))
                     c_type = cost.get("type")
                     if c_val > 0 and c_type:
                         curr = get_status_value(actor, c_type)
                         _update_char_stat(room, actor, c_type, curr - c_val, username=f"[{skill_data.get('デフォルト名称', '')}]")
             except:
                 effects_array = []
                 pass

             # 効果適用 (自分自身へ)
             # contextにroomを含めることで、get_room_stateなどが使えるようにする
             state = get_room_state(room) # 再取得
             context = {'room': room, 'characters': state['characters']}
             _, logs, changes = process_skill_effects(effects_array, "IMMEDIATE", actor, target, None, context=context)

             # 変更の適用
             for (c, type, name, value) in changes:
                 if type == "APPLY_STATE":
                     curr = get_status_value(c, name)
                     _update_char_stat(room, c, name, curr + value, username=f"[{skill_data.get('デフォルト名称', '')}]")
                 elif type == "APPLY_BUFF":
                     apply_buff(c, name, value["lasting"], value["delay"], data=value.get("data"))
                     broadcast_log(room, f"[{name}] が {c['name']} に付与されました。", 'state-change')
                 elif type == "REMOVE_BUFF":
                     remove_buff(c, name)
                 elif type == "SET_FLAG":
                     if 'flags' not in c: c['flags'] = {}
                     c['flags'][name] = value

             if 'flags' not in actor: actor['flags'] = {}
             actor['flags']['immediate_action_used'] = True

             # 宝石の加護フラグ設定
             skill_tags = skill_data.get('tags', [])
             if "宝石の加護スキル" in skill_tags:
                 actor['used_gem_protect_this_battle'] = True

             broadcast_log(room, f"{actor['name']} が 【{skill_data.get('デフォルト名称')}】 を即時発動しました！", 'info')
             broadcast_state_update(room)
             save_specific_room_state(room)

             # マッチ状態は更新しない
             return

        side_key = 'attacker' if 'attacker' in prefix else 'defender'
        active_match = state.get('active_match')
        if active_match:
            active_match[f'{side_key}_declared'] = True
            active_match[f'{side_key}_data'] = result_data # Store calc result
            save_specific_room_state(room)
            broadcast_state_update(room)

            # --- AUTO EXECUTE ---
            # --- AUTO EXECUTE ---
            attacker_id = active_match.get('attacker_id')
            defender_id = active_match.get('defender_id')
            attacker_char = next((c for c in state['characters'] if str(c.get('id')) == str(attacker_id)), None)
            defender_char = next((c for c in state['characters'] if str(c.get('id')) == str(defender_id)), None)

            # Check if defender has already acted (One-sided attack condition)
            is_one_sided = defender_char and defender_char.get('hasActed', False)

            # Condition 1: Both declared
            both_declared = active_match.get('attacker_declared') and active_match.get('defender_declared')

            # Condition 2: Attacker declared AND Defender is one-sided (cannot act)
            # In this case, we treat defender as "declared" (with empty/dummy command handled in execute_duel_match or here?)
            # Actually, execute_duel_match expects both commands.
            # If one-sided, defender command should be "0" or "No Guard".
            # Usually client handles this by sending "No Guard" if one-sided?
            # User says: "One-sided attack treated, only one side declaration needed."
            # Means defender might NOT declare anything.

            can_execute = False

            if both_declared:
                can_execute = True
            elif active_match.get('attacker_declared') and is_one_sided:
                print(f"[AUTO] One-sided Execution! {defender_char['name']} has already acted.")
                # We need to fill defender data so execute_duel_match doesn't crash or wait.
                if not active_match.get('defender_data'):
                     active_match['defender_data'] = {
                         'skill_id': 'No Guard',
                         'final_command': '0',
                         'min_damage': 0,
                         'max_damage': 0,
                         'skill_details': [],
                         'declared': True
                     }
                can_execute = True

            if can_execute:

                    exec_data = {
                        'room': room,
                        'actorIdA': attacker_id,
                        'actorIdD': defender_id,
                        'actorNameA': attacker_char['name'],
                        'actorNameD': defender_char['name'],
                        'commandA': active_match['attacker_data']['final_command'],
                        'commandD': active_match['defender_data']['final_command'],
                        'skillIdA': active_match['attacker_data']['skill_id'],
                        'skillIdD': active_match['defender_data']['skill_id'],
                        'senritsuPenaltyA': active_match['attacker_data'].get('senritsu_penalty', 0),
                        'senritsuPenaltyD': active_match['defender_data'].get('senritsu_penalty', 0),
                        'match_id': active_match.get('match_id')
                    }
                    print(f"[AUTO] Both sides declared in {room}. Executing Duel Match...")
                    execute_duel_match(room, exec_data, "System")
                    return # execute_duel_match handles emission/updates

    socketio.emit('skill_declaration_result', result_data, to=room)


def execute_duel_match(room, data, username):
    state = get_room_state(room)
    if not state: return

    # 重複実行防止: マッチIDをチェック
    match_id = data.get('match_id')
    active_match = state.get('active_match', {})

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

    # S-Confusion (行動不能) チェック
    active_match_data = state.get('active_match', {})
    attacker_data_s = active_match_data.get('attacker_data', {})
    defender_data_s = active_match_data.get('defender_data', {})

    skill_id_a_check = attacker_data_s.get('skill_id')
    skill_id_d_check = defender_data_s.get('skill_id')

    is_incap_a = (skill_id_a_check == 'S-Confusion') or ('S-Confusion' in (command_a or ''))
    is_incap_d = (skill_id_d_check == 'S-Confusion') or ('S-Confusion' in (command_d or ''))

    incap_logs = []

    if is_incap_a:
        incap_logs.append(f"{actor_name_a} は混乱により行動できない！ (Turn Skipped)")
        command_a = "0 【S-Confusion 混乱(行動不能)】"

    if is_incap_d:
        incap_logs.append(f"{actor_name_d} は混乱により行動できない！ (Turn Skipped)")
        command_d = "0 【S-Confusion 混乱(行動不能)】"

    actor_a_char = next((c for c in state["characters"] if c.get('id') == actor_id_a), None)
    actor_d_char = next((c for c in state["characters"] if c.get('id') == actor_id_d), None)

    # 戦慄消費
    if actor_a_char and senritsu_penalty_a > 0:
        curr = get_status_value(actor_a_char, '戦慄')
        _update_char_stat(room, actor_a_char, '戦慄', max(0, curr - senritsu_penalty_a), username=f"[{actor_name_a}:戦慄消費(ダイス-{senritsu_penalty_a})]")
    if actor_d_char and senritsu_penalty_d > 0:
        curr = get_status_value(actor_d_char, '戦慄')
        _update_char_stat(room, actor_d_char, '戦慄', max(0, curr - senritsu_penalty_d), username=f"[{actor_name_d}:戦慄消費(ダイス-{senritsu_penalty_d})]")

    # スキルデータ取得 & Pre-Match実行
    skill_data_a = None; effects_array_a = []
    skill_data_d = None; effects_array_d = []

    skill_id_a = data.get('skillIdA')
    skill_id_d = data.get('skillIdD')

    match_a = re.search(r'【(.*?)\s', command_a)
    match_d = re.search(r'【(.*?)\s', command_d)

    if (match_a or skill_id_a) and actor_a_char:
        if not skill_id_a and match_a:
            skill_id_a = match_a.group(1)
        skill_data_a = all_skill_data.get(skill_id_a)
        if skill_data_a:
            execute_pre_match_effects(room, actor_a_char, actor_d_char, skill_data_a, skill_data_d)
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

    if (match_d or skill_id_d) and actor_d_char:
        if not skill_id_d and match_d:
            skill_id_d = match_d.group(1)
        skill_data_d = all_skill_data.get(skill_id_d)
        if skill_data_d:
            execute_pre_match_effects(room, actor_d_char, actor_a_char, skill_data_d, skill_data_a)
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

    # ダイスロール
    result_a = roll_dice(command_a)
    result_d = roll_dice(command_d)

    winner_message = ''; damage_message = ''
    if actor_a_char: actor_a_char['hasActed'] = True
    no_defender_acted = state.get('active_match', {}).get('no_defender_acted', False)
    if actor_d_char and not no_defender_acted:
        actor_d_char['hasActed'] = True

    bonus_damage = 0; log_snippets = []; changes = []
    is_one_sided = False
    if command_d.strip() == "【一方攻撃（行動済）】" or command_a.strip() == "【一方攻撃（行動済）】":
        is_one_sided = True
    elif actor_d_char and actor_d_char.get('hasActed', False):
         # 明示的に行動済みフラグが立っている場合も一方攻撃として扱う
         is_one_sided = True
         # コマンドを上書きしてログの一貫性を保つ（オプション）
         command_d = "【一方攻撃（行動済）】"

    def grant_win_fp(char):
        if not char: return
        curr = get_status_value(char, 'FP')
        _update_char_stat(room, char, 'FP', curr + 1, username="[マッチ勝利]")

    try:
        damage = 0; final_damage = 0; extra_skill_damage = 0
        attacker_tags = skill_data_a.get("tags", []) if skill_data_a else []
        defender_tags = skill_data_d.get("tags", []) if skill_data_d else []
        attacker_category = skill_data_a.get("分類", "") if skill_data_a else ""
        defender_category = skill_data_d.get("分類", "") if skill_data_d else ""

        # 荊棘処理
        for (actor, cat, skill) in [(actor_a_char, attacker_category, skill_data_a), (actor_d_char, defender_category, skill_data_d)]:
            if actor:
                val = get_status_value(actor, "荊棘")
                if val > 0:
                    if cat in ["物理", "魔法"]:
                        _update_char_stat(room, actor, "HP", actor['hp'] - val, username="[荊棘の自傷]")
                    elif cat == "防御" and skill:
                        try:
                            bp = int(skill.get('基礎威力', 0))
                            bp += actor.get('_base_power_bonus', 0)
                            _update_char_stat(room, actor, "荊棘", max(0, val - bp), username=f"[{skill.get('デフォルト名称')}]")
                            actor.pop('_base_power_bonus', None)
                        except ValueError: pass

        if "即時発動" in attacker_tags or "即時発動" in defender_tags:
            winner_message = '<strong> → スキル効果の適用のみ</strong>'; damage_message = '(ダメージなし)'

        elif is_incap_a or is_incap_d:
            winner_message = ""; damage_message = ""
            if is_incap_a:
                damage = result_d['total']
                if actor_a_char:
                    kiretsu = get_status_value(actor_a_char, '亀裂')
                    bonus_damage, logs = apply_skill_effects_bidirectional(room, state, username, 'defender', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
                    log_snippets.extend(logs)
                    final_damage = damage + kiretsu + bonus_damage
                    if any(b.get('name') == "混乱" for b in actor_a_char.get('special_buffs', [])):
                         final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                    _update_char_stat(room, actor_a_char, 'HP', actor_a_char['hp'] - final_damage, username=username)
                    process_on_damage_buffs(room, actor_a_char, final_damage, username, log_snippets)
                    winner_message = f"<strong> → {actor_name_d} の一方的攻撃！</strong> (相手は行動不能)"
                    damage_message += f"({actor_a_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"

            elif is_incap_d:
                damage = result_a['total']
                if actor_d_char:
                    kiretsu = get_status_value(actor_d_char, '亀裂')
                    bonus_damage, logs = apply_skill_effects_bidirectional(room, state, username, 'attacker', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
                    log_snippets.extend(logs)
                    final_damage = damage + kiretsu + bonus_damage
                    if any(b.get('name') == "混乱" for b in actor_d_char.get('special_buffs', [])):
                        final_damage = int(final_damage * 1.5); damage_message = f"(混乱x1.5) "
                    _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                    process_on_damage_buffs(room, actor_d_char, final_damage, username, log_snippets)
                    winner_message = f"<strong> → {actor_name_a} の一方的攻撃！</strong> (相手は行動不能)"
                    damage_message += f"({actor_d_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"

        elif is_one_sided:
            if "守備" in attacker_tags:
                winner_message = f"<strong> → {actor_name_a} の一方攻撃！</strong> (守備スキルのためダメージなし)"; damage_message = "(ダメージ 0)"
            else:
                damage = result_a['total']
                if actor_d_char:
                    kiretsu = get_status_value(actor_d_char, '亀裂')
                    # 一方攻撃の特殊処理
                    bd_un, log_un, chg_un = process_skill_effects(effects_array_a, "UNOPPOSED", actor_a_char, actor_d_char, skill_data_d)

                    def local_apply(clist):
                        ex = 0
                        for (c, t, n, v) in clist:
                            if t == "APPLY_STATE": _update_char_stat(room, c, n, get_status_value(c, n)+v, username=f"[{n}]")
                            elif t == "APPLY_BUFF": apply_buff(c, n, v["lasting"], v["delay"], data=v.get("data"))
                            elif t == "REMOVE_BUFF": remove_buff(c, n)
                            elif t == "CUSTOM_DAMAGE": ex += v
                            elif t == "APPLY_SKILL_DAMAGE_AGAIN": ex += damage # Add original damage
                            elif t == "SET_FLAG":
                                if 'flags' not in c: c['flags'] = {}
                                c['flags'][n] = v
                        return ex

                    local_apply(chg_un)
                    bd_hit, log_hit, chg_hit = process_skill_effects(effects_array_a, "HIT", actor_a_char, actor_d_char, skill_data_d)
                    extra_skill_damage = local_apply(chg_hit)

                    log_snippets.extend(log_un + log_hit)
                    bonus_damage = bd_un + bd_hit
                    final_damage = damage + kiretsu + bonus_damage + extra_skill_damage
                    d_mult, logs = calculate_damage_multiplier(actor_d_char)
                    final_damage = int(final_damage * d_mult)
                    if logs: damage_message = f"({'/'.join(logs)} x{d_mult:.2f}) "
                    _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                    process_on_damage_buffs(room, actor_d_char, final_damage, username, log_snippets)
                    winner_message = f"<strong> → {actor_name_a} の一方攻撃！</strong>"
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
                bonus_damage, logs = apply_skill_effects_bidirectional(room, state, username, 'attacker', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
                log_snippets.extend(logs)
                final_damage = damage + kiretsu + bonus_damage
                d_mult, logs = calculate_damage_multiplier(actor_d_char)
                final_damage = int(final_damage * d_mult)
                if logs: damage_message = f"({'/'.join(logs)} x{d_mult:.2f}) "
                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                process_on_damage_buffs(room, actor_d_char, final_damage, username, log_snippets)
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
                d_mult, logs = calculate_damage_multiplier(actor_d_char)
                final_damage = int(final_damage * d_mult)
                if logs: damage_message = f"({'/'.join(logs)} x{d_mult:.2f}) "
                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                process_on_damage_buffs(room, actor_d_char, final_damage, username, log_snippets)

                if DodgeLockBuff.has_re_evasion(actor_d_char):
                     remove_buff(actor_d_char, "再回避ロック")
                     log_snippets.append("[再回避失敗！(ロック解除)]")

                winner_message = f"<strong> → {actor_name_a} の勝利！</strong> (回避失敗)"
                damage_message += f"({actor_d_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
            else:
                grant_win_fp(actor_d_char)
                _, logs = apply_skill_effects_bidirectional(room, state, username, 'defender', actor_a_char, actor_d_char, skill_data_a, skill_data_d)
                if actor_d_char:
                    log_snippets.append("[再回避可能！]")
                    apply_buff(actor_d_char, "再回避ロック", 1, 0, data={"skill_id": skill_id_d, "buff_id": "Bu-05"})
                log_snippets.extend(logs)
                winner_message = f"<strong> → {actor_name_d} の勝利！</strong> (回避成功)"; damage_message = "(ダメージ 0)"
                if log_snippets: damage_message += f" ({' '.join(log_snippets)})"

        elif attacker_category == "回避":
            if result_a['total'] > result_d['total']:
                grant_win_fp(actor_a_char)
                winner_message = f"<strong> → {actor_name_a} の勝利！</strong> (回避成功)"
                damage_message = "(ダメージなし)"
                if actor_a_char:
                    log_snippets.append("[再回避可能！]")
                    apply_buff(actor_a_char, "再回避ロック", 1, 0, data={"skill_id": skill_id_a, "buff_id": "Bu-05"})
                _, logs = apply_skill_effects_bidirectional(room, state, username, 'attacker', actor_a_char, actor_d_char, skill_data_a, skill_data_d, 0)
                if logs: damage_message += f" ({' '.join(logs)})"
            elif result_d['total'] > result_a['total']:
                grant_win_fp(actor_d_char)
                damage = result_d['total']
                if actor_a_char:
                    kiretsu = get_status_value(actor_a_char, '亀裂')
                    bonus_damage, logs = apply_skill_effects_bidirectional(room, state, username, 'defender', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
                    log_snippets.extend(logs)
                    final_damage = damage + kiretsu + bonus_damage
                    d_mult, logs = calculate_damage_multiplier(actor_a_char)
                    final_damage = int(final_damage * d_mult)
                    if logs: damage_message = f"({'/'.join(logs)} x{d_mult:.2f}) "
                    _update_char_stat(room, actor_a_char, 'HP', actor_a_char['hp'] - final_damage, username=username)
                    process_on_damage_buffs(room, actor_a_char, final_damage, username, log_snippets)
                    winner_message = f"<strong> → {actor_name_d} の勝利！</strong> (カウンター)"
                    damage_message += f"({actor_a_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
            else:
                winner_message = '<strong> → 引き分け！</strong> (ダメージなし)'
                # END_MATCH処理
                def local_end_match(effs, actor, target, skill):
                    d, l, c = process_skill_effects(effs, "END_MATCH", actor, target, skill)
                    for (char, type, name, value) in c:
                        if type == "APPLY_STATE": _update_char_stat(room, char, name, get_status_value(char, name)+value, username=f"[{name}]")
                        elif type == "APPLY_BUFF": apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                        elif type == "REMOVE_BUFF": remove_buff(char, name)
                    return l

                log_a = local_end_match(effects_array_a, actor_a_char, actor_d_char, skill_data_d)
                log_d = local_end_match(effects_array_d, actor_d_char, actor_a_char, skill_data_a)
                log_snippets.extend(log_a + log_d)
                if log_snippets: winner_message += f" ({' '.join(log_snippets)})"
                damage_message = "(相殺)"

        elif result_a['total'] > result_d['total']:
            grant_win_fp(actor_a_char)
            damage = result_a['total']
            if actor_d_char:
                kiretsu = get_status_value(actor_d_char, '亀裂')
                bonus_damage, logs = apply_skill_effects_bidirectional(room, state, username, 'attacker', actor_a_char, actor_d_char, skill_data_a, skill_data_d, damage)
                log_snippets.extend(logs)
                final_damage = damage + kiretsu + bonus_damage
                d_mult, logs = calculate_damage_multiplier(actor_d_char)
                final_damage = int(final_damage * d_mult)
                if logs: damage_message = f"({'/'.join(logs)} x{d_mult:.2f}) "
                _update_char_stat(room, actor_d_char, 'HP', actor_d_char['hp'] - final_damage, username=username)
                process_on_damage_buffs(room, actor_d_char, final_damage, username, log_snippets)

                # 再回避ロック中の回避失敗処理
                if actor_d_char and DodgeLockBuff.has_re_evasion(actor_d_char):
                     remove_buff(actor_d_char, "再回避ロック")
                     log_snippets.append("[再回避失敗！(ロック解除)]")

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
                d_mult, logs = calculate_damage_multiplier(actor_a_char)
                final_damage = int(final_damage * d_mult)
                if logs: damage_message = f"({'/'.join(logs)} x{d_mult:.2f}) "
                _update_char_stat(room, actor_a_char, 'HP', actor_a_char['hp'] - final_damage, username=username)
                process_on_damage_buffs(room, actor_a_char, final_damage, username, log_snippets)
                winner_message = f"<strong> → {actor_name_d} の勝利！</strong>"
                damage_message += f"({actor_a_char['name']} に {damage} " + (f"+ [亀裂 {kiretsu}] " if kiretsu > 0 else "") + "".join([f"{m} " for m in log_snippets]) + f"= {final_damage} ダメージ)"
        else:
            winner_message = '<strong> → 引き分け！</strong> (ダメージなし)'
            # END_MATCH Effect (Simplified for Draw)
            def run_end_match(effs, actor, target, skill):
                d, l, c = process_skill_effects(effs, "END_MATCH", actor, target, skill)
                for (char, type, name, value) in c:
                    if type == "APPLY_STATE": _update_char_stat(room, char, name, get_status_value(char, name)+value, username=f"[{name}]")
                    elif type == "APPLY_BUFF": apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                    elif type == "REMOVE_BUFF": remove_buff(char, name)
                    elif type == "SET_FLAG":
                        if 'flags' not in char: char['flags'] = {}
                        char['flags'][name] = value
                return l

            log_a = run_end_match(effects_array_a, actor_a_char, actor_d_char, skill_data_d)
            log_d = run_end_match(effects_array_d, actor_d_char, actor_a_char, skill_data_a)
            log_snippets.extend(log_a + log_d)
            if log_snippets: winner_message += f" ({' '.join(log_snippets)})"

    except Exception as e:
        print("--- ▼▼▼ エラーをキャッチしました ▼▼▼ ---", flush=True)
        print(f"エラー内容: {e}", flush=True)
        raise e

    skill_display_a = format_skill_display_from_command(command_a, skill_id_a, skill_data_a)
    skill_display_d = format_skill_display_from_command(command_d, skill_id_d, skill_data_d)

    if incap_logs:
        winner_message = f"{' '.join(incap_logs)}<br>{winner_message}"

    match_log = f"<strong>{actor_name_a}</strong> {skill_display_a} (<span class='dice-result-total'>{result_a['total']}</span>) vs <strong>{actor_name_d}</strong> {skill_display_d} (<span class='dice-result-total'>{result_d['total']}</span>) | {winner_message} {damage_message}"
    broadcast_log(room, match_log, 'match')
    broadcast_state_update(room)
    save_specific_room_state(room)

    # 手番更新
    if actor_a_char:
        has_re_evasion = DodgeLockBuff.has_re_evasion(actor_a_char)
        if not has_re_evasion:
             actor_a_char['hasActed'] = True
             save_specific_room_state(room)

    proceed_next_turn(room)

    # マッチ終了処理
    state['active_match'] = None
    if 'active_match' in state:
        del state['active_match']

    save_specific_room_state(room)
    broadcast_state_update(room)
    socketio.emit('match_modal_closed', {}, to=room)
