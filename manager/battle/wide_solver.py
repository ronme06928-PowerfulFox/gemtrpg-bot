import re
import json
from extensions import all_skill_data, socketio
from manager.room_manager import (
    get_room_state, save_specific_room_state, broadcast_log,
    broadcast_state_update, _update_char_stat
)
from manager.game_logic import (
    get_status_value, remove_buff, apply_buff, process_skill_effects,
    calculate_power_bonus, calculate_buff_power_bonus, compute_damage_multipliers
)
from manager.skill_effects import apply_skill_effects_bidirectional
from manager.dice_roller import roll_dice
from manager.battle.core import (
    format_skill_display_from_command, execute_pre_match_effects,
    process_simple_round_end, proceed_next_turn,
    calculate_opponent_skill_modifiers, process_on_hit_buffs
)
from manager.summons.service import apply_summon_change
from manager.granted_skills.service import apply_grant_skill_change, consume_granted_skill_use
try:
    import manager.utils as _utils_mod
except Exception:
    _utils_mod = None

resolve_placeholders = getattr(_utils_mod, "resolve_placeholders", lambda text, *_args, **_kwargs: text)
get_effective_origin_id = getattr(_utils_mod, "get_effective_origin_id", lambda *_args, **_kwargs: 0)
compute_origin_skill_modifiers = getattr(_utils_mod, "compute_origin_skill_modifiers", lambda *_args, **_kwargs: {})
apply_dice_power_bonus_to_command = getattr(
    _utils_mod, "apply_dice_power_bonus_to_command", lambda command, *_args, **_kwargs: command
)
get_target_coloration_attack_bonus = getattr(
    _utils_mod, "get_target_coloration_attack_bonus", lambda *_args, **_kwargs: 0
)
from manager.logs import setup_logger

logger = setup_logger(__name__)

_room_save_specific_room_state = save_specific_room_state


def save_specific_room_state(room_name):
    try:
        return _room_save_specific_room_state(room_name)
    except Exception as exc:
        logger.error(f"save_specific_room_state failed room={room_name}: {exc}")
        return False


def _safe_emit(event, payload, to=None):
    emit_fn = getattr(socketio, "emit", None)
    if callable(emit_fn):
        try:
            if to is None:
                emit_fn(event, payload)
            else:
                emit_fn(event, payload, to=to)
        except Exception:

            return


def _apply_temp_power_bonus_to_command(command, actor):
    if not isinstance(actor, dict):
        return command
    total_bonus = int(actor.get('_base_power_bonus', 0) or 0) + int(actor.get('_final_power_bonus', 0) or 0)
    if total_bonus == 0:
        return command
    return f"{command}{'+' if total_bonus > 0 else ''}{total_bonus}"


def _is_unmatchable_skill(skill_data):
    if not isinstance(skill_data, dict):
        return False
    tags = [str(v).strip() for v in (skill_data.get("tags") or []) if str(v).strip()]
    joined = " ".join(tags)
    name = str(skill_data.get("name") or "").lower()
    return (
        ("unmatchable" in joined.lower())
        or ("マッチ不可" in joined)
        or ("マッチ不" in joined)
        or ("unmatchable" in name)
    )

def setup_wide_match_declaration(room, data, username):
    state = get_room_state(room)
    if not state: return

    targets_data = data.get('targets', [])
    defender_ids = data.get('defender_ids', [])
    attacker_id = data.get('attacker_id')
    mode = data.get('mode', 'individual')


    defenders = []


    def get_speed_stat(char):
        curr = get_status_value(char, '速度')
        return curr


    if not targets_data and defender_ids:
        targets_data = [{'id': did} for did in defender_ids]


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
    broadcast_state_update(room)
    broadcast_log(room, f"▶ 広域マッチの宣言フェーズを開始しました (対象: {len(defenders)}名)", 'info')

    _safe_emit('wide_skill_users_declared', {
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



    updated = False
    for d in active_match.get('defenders', []):
        if d.get('id') == defender_id:
            d['declared'] = True
            d['skill_id'] = skill_id
            d['command'] = command


            d['data'] = {
                'final_command': command,
                'min': data.get('min'),
                'max': data.get('max'),
                'damage_range_text': data.get('damage_range_text'),
                'senritsu_penalty': data.get('senritsu_penalty', 0)
            }
            updated = True
            break

    if updated:
        save_specific_room_state(room)



        _safe_emit('wide_defender_updated', {
            'defender_id': defender_id,
            'declared': True,
            'data': d['data']
        }, to=room)

def update_attacker_declaration(room, data):
    state = get_room_state(room)
    if not state: return
    active_match = state.get('active_match')
    if not active_match or not active_match.get('is_active'): return




    active_match['attacker_declared'] = True
    active_match['attacker_data'] = data

    save_specific_room_state(room)


    _safe_emit('wide_attacker_updated', {
        'declared': True,
        'attacker_id': data.get('attacker_id'),
        'data': active_match['attacker_data']
    }, to=room)


def execute_wide_match(room, username):
    state = get_room_state(room)
    if not state: return

    active_match = state.get('active_match')
    if not active_match or not active_match.get('is_active') or active_match.get('match_type') != 'wide':
        logger.warning("No active wide match to execute")
        return


    if not active_match.get('attacker_declared'):
        broadcast_log(room, "攻撃側がまだ宣言していません", 'error')
        return

    defenders = active_match.get('defenders', [])
    undeclared = [d for d in defenders if not d.get('declared')]
    if undeclared:
        broadcast_log(room, f"防御側 {len(undeclared)} 名がまだ宣言していません", 'error')
        return


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


    def consume_skill_cost(char, skill_d, skill_id_log):
        if not skill_d:
            return
        try:
            rule_json_str = (
                skill_d.get("rule_data_json")
                or skill_d.get("special_rule")
                or skill_d.get("特記処理")
                or "{}"
            )
            rule_data = rule_json_str if isinstance(rule_json_str, dict) else json.loads(str(rule_json_str))
            tags = rule_data.get("tags", skill_d.get("tags", []))
            if "free_cost" not in tags:
                for cost in rule_data.get("cost", []):
                    c_type = cost.get("type")
                    c_val = int(cost.get("value", 0))
                    if c_val > 0 and c_type:
                        curr = get_status_value(char, c_type)
                        new_val = max(0, curr - c_val)
                        _update_char_stat(room, char, c_type, new_val, username=f"[{skill_id_log}]")
                        broadcast_log(room, f"{char['name']} は {c_type}を{c_val}消費しました (残: {new_val})", "system")
        except Exception:
            pass

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
             consume_granted_skill_use(def_char, def_skill_id)

    if 'used_skills_this_round' not in attacker_char:
        attacker_char['used_skills_this_round'] = []
    attacker_char['used_skills_this_round'].append(attacker_skill_id)
    consume_granted_skill_use(attacker_char, attacker_skill_id)


    broadcast_log(room, f"▶ === 広域マッチ開始 ({mode}モード) ===", 'match-start')
    broadcast_log(room, f"▶ 攻撃側: {attacker_char['name']} [{attacker_skill_id}]", 'info')

    attacker_origin_mods = compute_origin_skill_modifiers(attacker_char, None, attacker_skill_data, state=state)
    attacker_char['_base_power_bonus'] = int(attacker_char.get('_base_power_bonus', 0) or 0) + int(attacker_origin_mods.get('base_power_bonus', 0) or 0)
    attacker_char['_final_power_bonus'] = int(attacker_char.get('_final_power_bonus', 0) or 0) + int(attacker_origin_mods.get('final_power_bonus', 0) or 0)
    attacker_command = apply_dice_power_bonus_to_command(attacker_command, attacker_origin_mods.get('dice_power_bonus', 0))
    attacker_command = _apply_temp_power_bonus_to_command(attacker_command, attacker_char)

    attacker_roll = roll_dice(attacker_command)
    broadcast_log(room, f"   →ロール: {attacker_roll['details']} = {attacker_roll['total']}", 'dice')

    attacker_total = attacker_roll['total']


    attacker_senritsu_penalty = int(attacker_data.get('senritsu_penalty', 0))
    if attacker_senritsu_penalty > 0:
        attacker_total = max(0, attacker_total - attacker_senritsu_penalty)

        curr_senritsu = get_status_value(attacker_char, "戦慄")
        _update_char_stat(
            room,
            attacker_char,
            "戦慄",
            max(0, curr_senritsu - attacker_senritsu_penalty),
            username=f"[{attacker_char['name']}:戦慄 cost -{attacker_senritsu_penalty}]",
        )
        broadcast_log(room, f"   [senritsu penalty] -{attacker_senritsu_penalty} (total {attacker_total})", "dice")


    attacker_origin = get_effective_origin_id(attacker_char)
    skill_attr = str((attacker_skill_data or {}).get("属性") or (attacker_skill_data or {}).get("属性") or "")
    if attacker_origin == 9 and skill_attr in {"slash", "斬撃"}:
        attacker_total += 1
        broadcast_log(room, f"[Wadatsumi] Slash power +1 => {attacker_total}", "info")

    results = []
    attacker_effects = []
    if attacker_skill_data:
        try:
            raw_rule = (
                attacker_skill_data.get("rule_data_json")
                or attacker_skill_data.get("special_rule")
                or attacker_skill_data.get("特記処理")
                or "{}"
            )
            parsed_rule = raw_rule if isinstance(raw_rule, dict) else json.loads(str(raw_rule))
            attacker_effects = parsed_rule.get("effects", [])
        except Exception:
            attacker_effects = []


    def apply_local_changes(changes, primary_target=None):
        extra = 0
        for (char, type, name, value) in changes:
            if type == "APPLY_STATE":
                curr = get_status_value(char, name)
                _update_char_stat(room, char, name, curr + value, username=f"[{attacker_skill_id}]")
            elif type == "APPLY_BUFF":
                apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                broadcast_log(room, f"[{name}] applied to {char['name']}", "state-change")
            elif type == "REMOVE_BUFF":
                remove_buff(char, name)
            elif type == "MODIFY_BASE_POWER":
                char["_base_power_bonus"] = int(char.get("_base_power_bonus", 0) or 0) + int(value or 0)
            elif type == "MODIFY_FINAL_POWER":
                char["_final_power_bonus"] = int(char.get("_final_power_bonus", 0) or 0) + int(value or 0)
            elif type == "CUSTOM_DAMAGE":
                if primary_target and char.get("id") == primary_target.get("id"):
                    extra += value
                else:
                    curr = get_status_value(char, "HP")
                    _update_char_stat(room, char, "HP", max(0, curr - value), username=f"[{name}]", source=DamageSource.SKILL_EFFECT)
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
                    broadcast_log(room, res.get("message", "Summon applied"), "state-change")
                else:
                    logger.warning("[wide summon failed] %s", res.get("message"))
            elif type == "GRANT_SKILL":
                grant_payload = dict(value) if isinstance(value, dict) else {}
                if "skill_id" not in grant_payload:
                    grant_payload["skill_id"] = name
                res = apply_grant_skill_change(room, state, attacker_char, char, grant_payload)
                if res.get("ok"):
                    broadcast_log(room, res.get("message", "Grant skill applied"), "state-change")
                else:
                    logger.warning("[wide grant_skill failed] %s", res.get("message"))
        return extra

    attacker_tags = attacker_skill_data.get("tags", []) if attacker_skill_data else []
    if _is_unmatchable_skill(attacker_skill_data):
        broadcast_log(room, "[Unmatchable] Skip dice roll and apply HIT effects.", "info")

        for def_data in defenders:
            def_id = def_data.get('id')
            def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
            if not def_char: continue



            damage = attacker_total







            total_damage = damage
            log_snippets = []


            unop_bonus, unop_logs, unop_changes = process_skill_effects(attacker_effects, "UNOPPOSED", attacker_char, def_char, None, context={'timeline': state.get('timeline', []), 'characters': state['characters'], 'room': room})
            log_snippets.extend(unop_logs)
            apply_local_changes(unop_changes, def_char)
            total_damage += unop_bonus


            hit_bonus, hit_logs, hit_changes = process_skill_effects(attacker_effects, "HIT", attacker_char, def_char, None, context={'timeline': state.get('timeline', []), 'characters': state['characters'], 'room': room})
            log_snippets.extend(hit_logs)
            apply_local_changes(hit_changes, def_char)
            total_damage += hit_bonus



            mult_info = compute_damage_multipliers(attacker_char, def_char)
            final_damage = int(total_damage * float(mult_info.get('final', 1.0) or 1.0))
            d_logs = mult_info.get('incoming_logs', []) or []
            a_logs = mult_info.get('outgoing_logs', []) or []

            if d_logs:
                 log_snippets.append(f"(防:{'/'.join(d_logs)} x{float(mult_info.get('incoming', 1.0) or 1.0):.2f})")
            if a_logs:
                 log_snippets.append(f"(攻:{'/'.join(a_logs)} x{float(mult_info.get('outgoing', 1.0) or 1.0):.2f})")


            if final_damage > 0:
                 current_hp = get_status_value(def_char, 'HP')
                 _update_char_stat(room, def_char, 'HP', current_hp - final_damage, username=f"[{attacker_skill_id}]")
                 broadcast_log(room, f"{def_char['name']} に {final_damage} ダメージ {' '.join(log_snippets)}", 'damage')
            else:
                 if log_snippets:
                     broadcast_log(room, f"{def_char['name']} に効果適用: {' '.join(log_snippets)}", 'info')


            for def_data in defenders:
                def_id = def_data.get('id')
                def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
                if not def_char: continue

                def_skill_id = def_data.get('skill_id')
                def_skill_data = all_skill_data.get(def_skill_id)


                if def_skill_data:
                    execute_pre_match_effects(room, def_char, attacker_char, def_skill_data, attacker_skill_data)

    elif mode == 'combined':

        defender_rolls = []
        valid_defenders = []
        total_defender_roll = 0

        for def_data in defenders:
            def_id = def_data.get('id')
            def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
            if not def_char: continue

            def_skill_id = def_data.get('skill_id')
            def_command = def_data.get('command')

            if def_data.get('data') and def_data['data'].get('final_command'):
                 def_command = def_data['data']['final_command']

            def_skill_data = all_skill_data.get(def_skill_id)
            origin_mods = compute_origin_skill_modifiers(def_char, attacker_char, def_skill_data, state=state)
            def_char['_base_power_bonus'] = int(def_char.get('_base_power_bonus', 0) or 0) + int(origin_mods.get('base_power_bonus', 0) or 0)
            def_char['_final_power_bonus'] = int(def_char.get('_final_power_bonus', 0) or 0) + int(origin_mods.get('final_power_bonus', 0) or 0)
            def_command = apply_dice_power_bonus_to_command(def_command, origin_mods.get('dice_power_bonus', 0))
            def_command = _apply_temp_power_bonus_to_command(def_command, def_char)

            def_roll_result = roll_dice(def_command)


            def_senritsu_penalty = int(def_data.get('data', {}).get('senritsu_penalty', 0))
            if def_senritsu_penalty > 0:
                def_roll_result['total'] = max(0, def_roll_result['total'] - def_senritsu_penalty)

                curr_senritsu = get_status_value(def_char, "戦慄")
                _update_char_stat(
                    room,
                    def_char,
                    "戦慄",
                    max(0, curr_senritsu - def_senritsu_penalty),
                    username=f"[{def_char['name']}:戦慄 cost -{def_senritsu_penalty}]",
                )
                def_roll_result['details'] += f" -senritsu({def_senritsu_penalty})"

            defender_rolls.append({
                'char': def_char,
                'skill_id': def_skill_id,
                'roll': def_roll_result
            })
            valid_defenders.append(def_char)
            total_defender_roll += def_roll_result['total']

            broadcast_log(room, f"   ←{def_char['name']} [{def_skill_id}]: {def_roll_result['details']} = {def_roll_result['total']}", 'dice')






        if attacker_origin == 13:
             if total_defender_roll > 2:
                 total_defender_roll -= 1
                 broadcast_log(room, f"[ヴァルヴァイレ恩恵] 防御側合計 -1", 'info')


        has_walwaire_defender = any(get_effective_origin_id(d) == 13 for d in valid_defenders)
        if has_walwaire_defender:
             if attacker_total > 2:
                 attacker_total -= 1
                 broadcast_log(room, f"[ヴァルヴァイレ恩恵] 攻撃側合計 -1", 'info')

        if any(get_target_coloration_attack_bonus(attacker_char, defender_char, attacker_skill_data) > 0 for defender_char in valid_defenders):
             attacker_total += 1

        broadcast_log(room, f"📊 防御側合計 {total_defender_roll} vs 攻撃側 {attacker_total}", 'info')

        if attacker_total > total_defender_roll:
            diff = attacker_total - total_defender_roll


            attacker_params = all_skill_data.get(attacker_skill_id, {})
            att_cat = str(attacker_params.get("分類") or attacker_params.get("attribute") or "")
            att_tags = attacker_params.get('tags', [])

            if att_cat == '防御' or att_cat == '回避' or '防御' in att_tags or '回避' in att_tags:
                broadcast_log(room, f"   → 攻撃側勝利 ({att_cat})! (ダメージなし)", 'match-result')

            else:
                broadcast_log(room, f"   → 攻撃側勝利! 差分 {diff}", 'match-result')

                for dr in defender_rolls:
                    def_char = dr['char']
                    results.append({'defender': def_char['name'], 'result': 'win', 'damage': diff})
                    current_hp = get_status_value(def_char, 'HP')
                    extra_dmg = process_on_hit_buffs(attacker_char, def_char, diff, [])
                    if extra_dmg > 0:
                         broadcast_log(room, f"[{attacker_char['name']}] 追加ダメージ +{extra_dmg}", 'buff')
                    new_hp = max(0, current_hp - (diff + extra_dmg))
                    _update_char_stat(room, def_char, 'HP', new_hp, username=f"[{attacker_skill_id}]")
                    broadcast_log(room, f"   →{def_char['name']} に {diff} ダメージ", 'damage')

                    if attacker_effects:
                        dmg_bonus, logs, changes = process_skill_effects(attacker_effects, "HIT", attacker_char, def_char, None, context={'timeline': state.get('timeline', []), 'characters': state['characters'], 'room': room})
                        for log_msg in logs:
                            broadcast_log(room, log_msg, 'skill-effect')
                        diff_bonus = apply_local_changes(changes, def_char)
                        if diff_bonus > 0:
                            current_hp = get_status_value(def_char, 'HP')
                            new_hp = max(0, current_hp - diff_bonus)
                            _update_char_stat(room, def_char, 'HP', new_hp, username=f"[{attacker_skill_id}追加]")
                            broadcast_log(room, f"   →{def_char['name']} に追加 {diff_bonus} ダメージ", 'damage')

        elif total_defender_roll > attacker_total:
            diff = total_defender_roll - attacker_total
            broadcast_log(room, f"   → 防御側勝利! 差分 {diff}", 'match-result')

            current_hp = get_status_value(attacker_char, 'HP')
            new_hp = max(0, current_hp - diff)
            _update_char_stat(room, attacker_char, 'HP', new_hp, username="[防御側勝利]", save=False)
            broadcast_log(room, f"   →{attacker_char['name']} に {diff} ダメージ", 'damage', save=False)
            for dr in defender_rolls:
                results.append({'defender': dr['char']['name'], 'result': 'lose', 'damage': diff})






            reflector = None
            for dr in defender_rolls:
                char = dr['char']
                if get_effective_origin_id(char) == 8:

                    sid = dr.get('skill_id')
                    sdata = all_skill_data.get(sid)
                    if sdata:
                        cat = str(sdata.get("分類") or sdata.get("attribute") or "")
                        tags = sdata.get('tags', [])
                        if cat == '防御' or '防御' in tags or '守備' in tags:
                            reflector = char
                            break

            if reflector:
                if diff > 0:
                     curr_hp = get_status_value(attacker_char, 'HP')
                     _update_char_stat(room, attacker_char, 'HP', curr_hp - diff, username="[反射ダメージ]", save=False)
                     broadcast_log(room, f"[鏡面反射] {reflector['name']} reflected {diff} damage.", "info", save=False)

        else:
            broadcast_log(room, "   → 引き分け", 'match-result')
            for dr in defender_rolls:
                results.append({'defender': dr['char']['name'], 'result': 'draw', 'damage': 0})

    else:

        for def_data in defenders:
            def_id = def_data.get('id')
            def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
            if not def_char: continue

            def_skill_id = def_data.get('skill_id')
            def_skill_data = all_skill_data.get(def_skill_id)


            attacker_char['_base_power_bonus'] = 0
            attacker_char['_final_power_bonus'] = 0
            def_char['_base_power_bonus'] = 0
            def_char['_final_power_bonus'] = 0


            execute_pre_match_effects(room, attacker_char, def_char, attacker_skill_data, def_skill_data)
            if def_skill_data:
                execute_pre_match_effects(room, def_char, attacker_char, def_skill_data, attacker_skill_data)


            thorn_val = get_status_value(def_char, "荊棘")
            if thorn_val > 0 and def_skill_data:
                 tags = def_skill_data.get('tags', [])
                 cat = str(def_skill_data.get("分類") or def_skill_data.get("attribute") or "")
                 if cat == '防御' or '防御' in tags or '守備' in tags:
                      bp = int(def_skill_data.get('基礎威力', 0))
                      bp += def_char.get('_base_power_bonus', 0)
                      if bp > 0:
                          _update_char_stat(room, def_char, "荊棘", max(0, thorn_val - bp), username=f"[{def_skill_id}:荊棘削減]", save=False)

            using_precalc = False
            def_command = def_data.get('command', '2d6')
            if def_data.get('data') and def_data['data'].get('final_command'):
                def_command = def_data['data']['final_command']
                using_precalc = True

            origin_mods = compute_origin_skill_modifiers(def_char, attacker_char, def_skill_data, state=state)
            def_char['_base_power_bonus'] = int(def_char.get('_base_power_bonus', 0) or 0) + int(origin_mods.get('base_power_bonus', 0) or 0)
            def_char['_final_power_bonus'] = int(def_char.get('_final_power_bonus', 0) or 0) + int(origin_mods.get('final_power_bonus', 0) or 0)
            def_command = apply_dice_power_bonus_to_command(def_command, origin_mods.get('dice_power_bonus', 0))



            bp_mod = int(def_char.get('_base_power_bonus', 0) or 0)
            fp_mod = int(def_char.get('_final_power_bonus', 0) or 0)
            total_power_mod = bp_mod + fp_mod
            if total_power_mod != 0:
                def_command = f"{def_command}{'+' if total_power_mod > 0 else ''}{total_power_mod}"
                logger.debug(f"Applied PowerMod base={bp_mod} final={fp_mod} -> {def_command} (precalc={using_precalc})")

            def_roll = roll_dice(def_command)
            defender_total = def_roll['total']


            def_senritsu_penalty = int(def_data.get('data', {}).get('senritsu_penalty', 0))
            if def_senritsu_penalty > 0:
                defender_total = max(0, defender_total - def_senritsu_penalty)
                def_roll['total'] = defender_total

                curr_senritsu = get_status_value(def_char, "戦慄")
                _update_char_stat(
                    room,
                    def_char,
                    "戦慄",
                    max(0, curr_senritsu - def_senritsu_penalty),
                    username=f"[{def_char['name']}:戦慄 cost -{def_senritsu_penalty}]",
                )
                def_roll['details'] += f" -senritsu({def_senritsu_penalty})"




            if attacker_origin == 13:
                 if defender_total > 2:
                     defender_total -= 1




            effective_attacker_total = attacker_total
            if get_effective_origin_id(def_char) == 13:
                 if effective_attacker_total > 2:
                     effective_attacker_total -= 1

            effective_attacker_total += get_target_coloration_attack_bonus(attacker_char, def_char, attacker_skill_data)


            if defender_total != def_roll['total'] or effective_attacker_total != attacker_total:
                 broadcast_log(room, f"   (補正後判定 攻{effective_attacker_total} vs 防{defender_total})", 'info')


            if effective_attacker_total > defender_total:

                is_defense_skill = False
                is_evasion_skill = False
                if def_skill_data:
                    cat = str(def_skill_data.get("分類") or def_skill_data.get("attribute") or "")
                    tags = def_skill_data.get('tags', [])
                    if cat == '防御' or '防御' in tags or '守備' in tags:
                        is_defense_skill = True
                    if cat == '回避' or '回避' in tags:
                        is_evasion_skill = True

                damage = 0
                result_type = 'win'

                if is_defense_skill:

                    damage = max(0, effective_attacker_total - defender_total)


                    att_params = all_skill_data.get(attacker_skill_id, {})
                    att_cat = str(att_params.get("分類") or att_params.get("attribute") or "")
                    att_tags = att_params.get("tags", [])
                    if att_cat in {"防御", "回避"} or "防御" in att_tags or "回避" in att_tags:
                        damage = 0
                        broadcast_log(
                            room,
                            f"[{def_char['name']}:{def_skill_id}] {def_roll['details']} = {def_roll['total']} (attacker used defense/evasion; no damage)",
                            "dice",
                            save=False,
                        )
                    else:
                        broadcast_log(room, f"[{def_char['name']}:{def_skill_id}] {def_roll['details']} = {def_roll['total']} (defense)", "dice", save=False)
                        broadcast_log(room, f"   [result] attacker hit (damage: {damage})", "match-result", save=False)
                elif is_evasion_skill:

                    damage = effective_attacker_total
                    broadcast_log(room, f"   ←vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (回避失敗)", 'dice', save=False)
                    broadcast_log(room, f"   → 攻撃側命中 (ダメージ: {damage})", 'match-result', save=False)


                    from plugins.buffs.dodge_lock import DodgeLockBuff
                    if DodgeLockBuff.has_re_evasion(def_char):
                         remove_buff(def_char, "再回避ロック")
                         broadcast_log(room, f"[再回避失敗！ロック解除]", 'info')

                else:





                    damage = effective_attacker_total


                    att_params = all_skill_data.get(attacker_skill_id, {})
                    att_cat = str(att_params.get("分類") or att_params.get("attribute") or "")
                    att_tags = att_params.get("tags", [])
                    if att_cat in {"防御", "回避"} or "防御" in att_tags or "回避" in att_tags:
                        damage = 0
                        broadcast_log(
                            room,
                            f"[{def_char['name']}:{def_skill_id}] {def_roll['details']} = {def_roll['total']} (attacker used defense/evasion; no damage)",
                            "dice",
                            save=False,
                        )
                    else:
                        broadcast_log(room, f"[{def_char['name']}:{def_skill_id}] {def_roll['details']} = {def_roll['total']}", "dice", save=False)
                        broadcast_log(room, f"   [result] attacker hit: {damage} damage", "match-result", save=False)

                results.append({'defender': def_char['name'], 'result': 'win', 'damage': damage})

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

                is_defense_skill = False
                if def_skill_data:
                    cat = str(def_skill_data.get("分類") or def_skill_data.get("attribute") or "")
                    tags = def_skill_data.get('tags', [])
                    if cat == '防御' or '防御' in tags or '守備' in tags:
                        is_defense_skill = True

                if is_defense_skill:


                    curr_fp = get_status_value(def_char, 'FP')
                    _update_char_stat(room, def_char, 'FP', curr_fp + 1, username="[マッチ勝利]", save=False)
                    damage = 0
                    results.append({'defender': def_char['name'], 'result': 'lose', 'damage': 0})
                    broadcast_log(room, f"   ←vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (防御成功)", 'dice')
                    broadcast_log(room, f"   → 防御成功! (ダメージ 0)", 'match-result')


                    if get_effective_origin_id(def_char) == 8:
                         diff = defender_total - effective_attacker_total
                         if diff > 0:
                             curr_hp = get_status_value(attacker_char, 'HP')
                             _update_char_stat(room, attacker_char, 'HP', curr_hp - diff, username="[反射ダメージ]", save=False)
                             broadcast_log(room, f"[鏡面反射] {def_char['name']} reflected {diff} damage.", "info", save=False)
                else:

                    damage = defender_total
                    if "回避" in (def_skill_data.get('tags', []) if def_skill_data else []):


                         curr_fp = get_status_value(def_char, 'FP')
                         _update_char_stat(room, def_char, 'FP', curr_fp + 1, username="[マッチ勝利]", save=False)

                         damage = 0
                         results.append({'defender': def_char['name'], 'result': 'lose', 'damage': 0})
                         broadcast_log(room, f"   ←vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']} (回避成功)", 'dice')
                         broadcast_log(room, f"   → 回避成功!", 'match-result')

                         broadcast_log(room, "[再回避可能]", 'info')
                         apply_buff(def_char, "再回避ロック", 1, 0, data={"skill_id": def_skill_id, "buff_id": "Bu-05"})

                    else:

                        results.append({'defender': def_char['name'], 'result': 'lose', 'damage': damage})
                        broadcast_log(room, f"   ←vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']}", 'dice')
                        broadcast_log(room, f"   → 防御側勝利! (反撃ダメージ): {damage}", 'match-result', save=False)

                        current_hp = get_status_value(attacker_char, 'HP')
                        new_hp = max(0, current_hp - damage)
                        _update_char_stat(room, attacker_char, 'HP', new_hp, username=f"[{def_skill_id}]", save=False)

            else:

                results.append({'defender': def_char['name'], 'result': 'draw', 'damage': 0})
                broadcast_log(room, f"   ←vs {def_char['name']} [{def_skill_id}]: {def_roll['details']} = {def_roll['total']}", 'dice')
                broadcast_log(room, "   → 相殺", 'match-result')

    broadcast_log(room, "▶ === 広域マッチ終了 ===", 'match-end')


    def consume_action(char_obj):
        if not char_obj: return
        timeline = state.get('timeline', [])
        current_entry_id = state.get('turn_entry_id')
        consumed = False


        if current_entry_id:
            for entry in timeline:
                if entry['id'] == current_entry_id and entry['char_id'] == char_obj['id']:
                    entry['acted'] = True
                    consumed = True
                    break



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


    for def_data in defenders:
        def_id = def_data.get('id')
        def_char = next((c for c in state['characters'] if c.get('id') == def_id), None)
        if def_char:
            consume_action(def_char)


    def execute_end_match(actor, target, skill_d, target_skill_d):
        if not skill_d: return
        try:
            raw_rule = (
                skill_d.get("rule_data_json")
                or skill_d.get("special_rule")
                or skill_d.get("特記処理")
                or "{}"
            )
            d = raw_rule if isinstance(raw_rule, dict) else json.loads(str(raw_rule))
            effs = d.get('effects', [])
            _, logs, changes = process_skill_effects(effs, "END_MATCH", actor, target, target_skill_d, context={'timeline': state.get('timeline', []), 'characters': state['characters'], 'room': room})
            for log_msg in logs:
                broadcast_log(room, log_msg, 'skill-effect')
            apply_local_changes(changes, target)
        except Exception:
            pass


    execute_end_match(attacker_char, None, attacker_skill_data, None)


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

        for entry in state.get('timeline', []):
            entry['acted'] = True

        for c in state['characters']:

            c['hasActed'] = True

        broadcast_log(room, f"[{attacker_skill_id}] requested immediate round end.", "round")
        round_end_requested = True

    proceed_next_turn(room)

    _safe_emit('match_modal_closed', {}, to=room)
    if 'active_match' in state:
        del state['active_match']
        save_specific_room_state(room)

    if round_end_requested:
        process_simple_round_end(state, room)



