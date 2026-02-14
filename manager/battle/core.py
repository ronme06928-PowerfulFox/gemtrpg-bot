import re
import json
import time
from extensions import all_skill_data
from extensions import socketio
from manager.dice_roller import roll_dice

from manager.game_logic import (
    process_skill_effects, apply_buff, remove_buff, get_status_value
)
from manager.utils import get_effective_origin_id
from models import Room
from manager.buff_catalog import get_buff_effect
from manager.room_manager import (
    get_room_state, broadcast_log, broadcast_state_update,
    save_specific_room_state, _update_char_stat
)
from manager.logs import setup_logger

logger = setup_logger(__name__)


def _resolve_server_ts():
    return int(time.time())


def _log_battle_emit(event_name, room_id, battle_id, payload):
    payload = payload or {}
    timeline_len = len(payload.get('timeline', []) or [])
    slots_len = len(payload.get('slots', {}) or {})
    intents_len = len(payload.get('intents', {}) or {})
    trace_len = len(payload.get('trace', []) or [])
    phase = payload.get('phase') or payload.get('to') or payload.get('from')
    logger.info(
        "[EMIT] %s room=%s battle=%s phase=%s timeline=%d slots=%d intents=%d trace=%d",
        event_name, room_id, battle_id, phase, timeline_len, slots_len, intents_len, trace_len
    )


def _emit_battle_trace(room, battle_id, battle_state, trace_entry):
    payload = {
        'room_id': room,
        'battle_id': battle_id,
        'round': battle_state.get('round', 0),
        'phase': battle_state.get('phase', 'resolve_mass'),
        'trace': [trace_entry]
    }
    _log_battle_emit('battle_resolve_trace_appended', room, battle_id, payload)
    socketio.emit('battle_resolve_trace_appended', payload, to=room)


def _append_trace(
    room,
    battle_id,
    battle_state,
    kind,
    attacker_slot,
    defender_slot=None,
    target_actor_id=None,
    notes=None,
    outcome='no_effect',
    cost=None,
    rolls=None,
    extra_fields=None
):
    trace = battle_state.get('resolve', {}).get('trace', [])
    entry = {
        'step': len(trace) + 1,
        'kind': kind,
        'attacker_slot': attacker_slot,
        'defender_slot': defender_slot,
        'target_actor_id': target_actor_id,
        'rolls': rolls or {},
        'outcome': outcome,
        'cost': cost or {'mp': 0, 'hp': 0},
        'notes': notes
    }
    if extra_fields:
        entry.update(extra_fields)
    trace.append(entry)
    battle_state['resolve']['trace'] = trace
    logger.info("[resolve_trace] kind=%s attacker_slot=%s", kind, attacker_slot)
    _emit_battle_trace(room, battle_id, battle_state, entry)


def _is_actor_placed(state, actor_id):
    actor = next((c for c in state.get('characters', []) if c.get('id') == actor_id), None)
    if not actor:
        return False
    try:
        x_val = float(actor.get('x', -1))
    except (ValueError, TypeError):
        x_val = -1
    if x_val < 0:
        return False
    if actor.get('hp', 0) <= 0:
        return False
    if actor.get('is_escaped', False):
        return False
    return True


def _build_resolve_queues(battle_state):
    timeline = battle_state.get('timeline', [])
    slots = battle_state.get('slots', {})
    intents = battle_state.get('intents', {})
    index_map = {slot_id: idx for idx, slot_id in enumerate(timeline)}

    mass_slots = []
    for slot_id in timeline:
        intent = intents.get(slot_id, {})
        tags = intent.get('tags', {})
        mass_type = tags.get('mass_type')
        if mass_type in ['individual', 'summation', 'mass_individual', 'mass_summation']:
            mass_slots.append(slot_id)

    mass_slots.sort(key=lambda s: index_map.get(s, 10**9))

    single_slots = []
    for slot_id in timeline:
        intent = intents.get(slot_id, {})
        tags = intent.get('tags', {})
        mass_type = tags.get('mass_type')
        is_mass = mass_type in ['individual', 'summation', 'mass_individual', 'mass_summation']
        if is_mass:
            continue
        if tags.get('instant', False):
            continue
        single_slots.append(slot_id)

    battle_state['resolve']['mass_queue'] = mass_slots
    battle_state['resolve']['single_queue'] = single_slots


def _compare_outcome(attacker_power, defender_power):
    if attacker_power > defender_power:
        return 'attacker_win'
    if attacker_power < defender_power:
        return 'defender_win'
    return 'draw'


def _roll_power_for_slot(battle_state, slot_id):
    intents = battle_state.get('intents', {})
    intent = intents.get(slot_id, {})
    skill_id = intent.get('skill_id')

    # Prefer deterministic+visible debug values: 1d20 + optional static bonus from skill data.
    base_roll = int(roll_dice("1d20").get('total', 1))
    bonus = 0
    if skill_id:
        skill_data = all_skill_data.get(skill_id, {})
        for key in ['基礎威力補正', 'ダイス補正']:
            try:
                bonus += int(skill_data.get(key, 0))
            except Exception:
                pass
    return max(0, base_roll + bonus)


def _gather_slots_targeting_slot_s(state, battle_state, slot_s):
    intents = battle_state.get('intents', {})
    slots = battle_state.get('slots', {})
    candidates = []

    for slot_id, intent in intents.items():
        if not intent.get('committed', False):
            continue
        if intent.get('tags', {}).get('instant', False):
            continue
        target = intent.get('target', {})
        if target.get('type') != 'single_slot':
            continue
        if target.get('slot_id') != slot_s:
            continue
        slot_data = slots.get(slot_id)
        if not slot_data:
            continue
        actor_id = slot_data.get('actor_id')
        if not actor_id:
            continue
        if not _is_actor_placed(state, actor_id):
            continue
        candidates.append((slot_id, actor_id, int(slot_data.get('initiative', 0))))

    best_by_actor = {}
    for slot_id, actor_id, initiative in candidates:
        prev = best_by_actor.get(actor_id)
        if (
            prev is None
            or initiative > prev[2]
            or (initiative == prev[2] and slot_id < prev[0])
        ):
            best_by_actor[actor_id] = (slot_id, actor_id, initiative)

    return [v[0] for v in best_by_actor.values()]


def run_select_resolve_auto(room, battle_id):
    state = get_room_state(room)
    if not state:
        return

    from manager.battle.common_manager import (
        ensure_battle_state_vNext,
        build_select_resolve_state_payload,
        select_evade_insert_slot
    )
    battle_state = ensure_battle_state_vNext(state, battle_id=battle_id, round_value=state.get('round', 0))
    if not battle_state:
        return

    if battle_state.get('phase') not in ['resolve_mass', 'resolve_single']:
        return

    _build_resolve_queues(battle_state)

    if battle_state.get('phase') == 'resolve_mass':
        for slot_id in battle_state['resolve'].get('mass_queue', []):
            intent = battle_state.get('intents', {}).get(slot_id, {})
            tags = intent.get('tags', {})
            mass_type = tags.get('mass_type')
            attacker_slot_data = battle_state.get('slots', {}).get(slot_id, {})
            attacker_actor_id = attacker_slot_data.get('actor_id')
            attacker_team = attacker_slot_data.get('team')
            if not attacker_actor_id or not _is_actor_placed(state, attacker_actor_id):
                _append_trace(room, battle_id, battle_state, 'fizzle', slot_id, notes='attacker_unplaced')
                battle_state['resolve']['resolved_slots'].append(slot_id)
                continue

            if mass_type in ['summation', 'mass_summation']:
                participant_slots = _gather_slots_targeting_slot_s(state, battle_state, slot_id)
                attacker_power = _roll_power_for_slot(battle_state, slot_id)
                defender_powers = {}
                for p_slot in participant_slots:
                    defender_powers[p_slot] = _roll_power_for_slot(battle_state, p_slot)
                defender_sum = sum(defender_powers.values())
                outcome = _compare_outcome(attacker_power, defender_sum)
                _append_trace(
                    room,
                    battle_id,
                    battle_state,
                    'mass_summation',
                    slot_id,
                    rolls={
                        'attacker_power': attacker_power,
                        'defender_powers': defender_powers,
                        'defender_sum': defender_sum
                    },
                    outcome=outcome,
                    extra_fields={'participants': participant_slots}
                )
            else:
                participant_slots = _gather_slots_targeting_slot_s(state, battle_state, slot_id)
                participant_by_actor = {}
                for p_slot in participant_slots:
                    actor_id = battle_state.get('slots', {}).get(p_slot, {}).get('actor_id')
                    if actor_id:
                        participant_by_actor[actor_id] = p_slot

                enemy_actors = []
                for actor in state.get('characters', []):
                    actor_id = actor.get('id')
                    if not actor_id:
                        continue
                    if actor.get('type') == attacker_team:
                        continue
                    if not _is_actor_placed(state, actor_id):
                        continue
                    enemy_actors.append(actor_id)

                for defender_actor_id in enemy_actors:
                    defender_slot = participant_by_actor.get(defender_actor_id)
                    attacker_power = _roll_power_for_slot(battle_state, slot_id)
                    if defender_slot:
                        defender_power = _roll_power_for_slot(battle_state, defender_slot)
                        outcome = _compare_outcome(attacker_power, defender_power)
                    else:
                        defender_power = 0
                        outcome = 'attacker_win'

                    _append_trace(
                        room,
                        battle_id,
                        battle_state,
                        'mass_individual',
                        slot_id,
                        defender_slot=defender_slot,
                        target_actor_id=defender_actor_id,
                        rolls={
                            'attacker_power': attacker_power,
                            'defender_power': defender_power
                        },
                        outcome=outcome
                    )

            battle_state['resolve']['resolved_slots'].append(slot_id)

        battle_state['phase'] = 'resolve_single'
        phase_payload = {
            'room_id': room,
            'battle_id': battle_id,
            'round': battle_state.get('round', 0),
            'from': 'resolve_mass',
            'to': 'resolve_single'
        }
        _log_battle_emit('battle_phase_changed', room, battle_id, phase_payload)
        socketio.emit('battle_phase_changed', phase_payload, to=room)
        payload = build_select_resolve_state_payload(room, battle_id=battle_id)
        if payload:
            _log_battle_emit('battle_state_updated', room, battle_id, payload)
            socketio.emit('battle_state_updated', payload, to=room)

    if battle_state.get('phase') == 'resolve_single':
        intents = battle_state.get('intents', {})
        slots = battle_state.get('slots', {})
        processed_slots = set()

        def _mark_processed(slot_key):
            if not slot_key:
                return
            if slot_key in processed_slots:
                return
            processed_slots.add(slot_key)
            resolved_slots = battle_state['resolve'].get('resolved_slots', [])
            if slot_key not in resolved_slots:
                resolved_slots.append(slot_key)
                battle_state['resolve']['resolved_slots'] = resolved_slots

        for slot_id in battle_state['resolve'].get('single_queue', []):
            if slot_id in processed_slots:
                logger.debug("[resolve_single] skip slot=%s reason=processed", slot_id)
                continue

            intent_a = intents.get(slot_id, {})
            skill_id = intent_a.get('skill_id')
            if not intent_a or not skill_id:
                _append_trace(room, battle_id, battle_state, 'fizzle', slot_id, notes='no_intent')
                _mark_processed(slot_id)
                continue

            target = intent_a.get('target', {})
            target_slot = target.get('slot_id')
            if target.get('type') != 'single_slot' or not target_slot:
                _append_trace(room, battle_id, battle_state, 'fizzle', slot_id, notes='invalid_target')
                _mark_processed(slot_id)
                continue

            target_actor_id = slots.get(target_slot, {}).get('actor_id')
            if not target_actor_id or not _is_actor_placed(state, target_actor_id):
                _append_trace(room, battle_id, battle_state, 'fizzle', slot_id, target_actor_id=target_actor_id, notes='target_unplaced')
                _mark_processed(slot_id)
                continue

            intent_b = intents.get(target_slot, {})
            is_clash = (
                intent_b.get('target', {}).get('type') == 'single_slot'
                and intent_b.get('target', {}).get('slot_id') == slot_id
            )
            clash_defender_slot = target_slot if is_clash else None
            if (not is_clash) and target_actor_id:
                evade_slot, evade_reason = select_evade_insert_slot(
                    state, battle_state, target_actor_id, slot_id
                )
                if evade_slot:
                    logger.info(
                        "[evade_insert] attacker_slot=%s defender_actor=%s defender_slot=%s reason=%s",
                        slot_id, target_actor_id, evade_slot, evade_reason
                    )
                    _append_trace(
                        room,
                        battle_id,
                        battle_state,
                        'evade_insert',
                        slot_id,
                        defender_slot=evade_slot,
                        target_actor_id=target_actor_id,
                        notes=f"dodge_lock insert ({evade_reason})",
                        outcome='no_effect'
                    )
                    is_clash = True
                    clash_defender_slot = evade_slot

            if is_clash:
                _append_trace(
                    room, battle_id, battle_state, 'clash', slot_id,
                    defender_slot=clash_defender_slot, target_actor_id=target_actor_id
                )
                _mark_processed(slot_id)
                _mark_processed(clash_defender_slot)
            else:
                _append_trace(
                    room, battle_id, battle_state, 'one_sided', slot_id,
                    target_actor_id=target_actor_id
                )
                _mark_processed(slot_id)

        battle_state['phase'] = 'round_end'
        round_finished_payload = {
            'room_id': room,
            'battle_id': battle_id,
            'round': battle_state.get('round', 0)
        }
        _log_battle_emit('battle_round_finished', room, battle_id, round_finished_payload)
        socketio.emit('battle_round_finished', round_finished_payload, to=room)
        payload = build_select_resolve_state_payload(room, battle_id=battle_id)
        if payload:
            _log_battle_emit('battle_state_updated', room, battle_id, payload)
            socketio.emit('battle_state_updated', payload, to=room)

    save_specific_room_state(room)

def calculate_opponent_skill_modifiers(actor_char, target_char, actor_skill_data, target_skill_data, all_skill_data_ref):
    """
    相手スキルを考慮したPRE_MATCHエフェクトを評価し、各種補正値を返す。
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
        logger.error(f"calculate_opponent_skill_modifiers: {e}")

    return modifiers

def extract_cost_from_text(text):
    """
    使用時効果テキストからコスト記述を抽出する
    """
    if not text:
        return "なし"
    match = re.search(r'\[使用時\]:?([^\n]+)', text)
    if match:
        return match.group(1).strip()
    return "なし"

def extract_custom_skill_name(character, skill_id):
    """
    キャラクターのcommandsからスキルIDに対応するカスタム名を抽出

    Args:
        character (dict): キャラクターデータ
        skill_id (str): スキルID (例: "Pp-01")

    Returns:
        str: カスタムスキル名またはNone
    """
    if not character or not skill_id:
        return None

    commands = character.get('commands', '')
    if not commands:
        return None

    # 【Pp-01 刺し込むA】や【Pp-01: 刺し込むA】のようなパターンを検索
    # スペースまたはコロン（全角・半角）で区切られた名前を抽出
    pattern = rf'【{re.escape(skill_id)}[\s:：]+(.*?)】'
    match = re.search(pattern, commands)

    if match:
        return match.group(1).strip()

    return None

def format_skill_name_for_log(skill_id, skill_data, character=None):
    """
    ログ用のスキル名をフォーマットする
    キャラクター情報が提供されている場合はカスタム名を優先、
    なければデフォルト名を使用

    Args:
        skill_id (str): スキルID (例: "Pp-01")
        skill_data (dict): スキルデータ
        character (dict): キャラクターデータ（オプション）

    Returns:
        str: フォーマットされたスキル名 (例: "Pp-01: 刺し込むA")
    """
    if not skill_id:
        return "不明"

    # カスタム名を取得
    custom_name = None
    if character:
        custom_name = extract_custom_skill_name(character, skill_id)

    # カスタム名があればそれを使用、なければデフォルト名
    if custom_name:
        return f"{skill_id}: {custom_name}"
    elif skill_data:
        default_name = skill_data.get('デフォルト名称', '')
        if default_name:
            return f"{skill_id}: {default_name}"

    # フォールバック: スキルIDのみ
    return skill_id

def format_skill_display_from_command(command_str, skill_id, skill_data, character=None):
    """
    コマンド文字列に含まれる【ID 名称】を抽出して目立つ色で表示する。
    キャラクター情報が提供されている場合、カスタムスキル名を優先的に使用する。
    """
    # まずキャラクターのカスタム名を試みる
    custom_name = None
    if character and skill_id:
        custom_name = extract_custom_skill_name(character, skill_id)

    text = ""
    if custom_name:
        text = f"【{skill_id}: {custom_name}】"
    else:
        # 既存のロジック：コマンド文字列から抽出
        match = re.search(r'【(.*?)】', command_str)
        if match:
            text = f"【{match.group(1)}】"
        elif skill_id and skill_data:
            name = skill_data.get('デフォルト名称', '不明')
            text = f"【{skill_id}: {name}】"
        else:
            return ""

    return f"<span style='color: #d63384; font-weight: bold;'>{text}</span>"

def verify_skill_cost(char, skill_d):
    """
    スキル使用に必要なコストが足りているかチェックする
    """
    if not skill_d: return True, None

    rule_json_str = skill_d.get('特記処理', '{}')
    try:
        rule_data = json.loads(rule_json_str)
        tags = rule_data.get('tags', skill_d.get('tags', []))
        if "即時発動" in tags:
             # ★ 追加: 宝石の加護スキルの回数制限 (1戦闘に1回)
             if "宝石の加護スキル" in tags:
                 if char.get('used_gem_protect_this_battle', False):
                     return False, "宝石の加護は1戦闘に1回しか使用できません。"

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

def process_on_damage_buffs(room, char, damage_val, username, log_snippets):
    """
    被弾時トリガーバフの処理
    """
    total_applied_damage = 0
    if damage_val <= 0: return 0

    for b in char.get('special_buffs', []):
        # ★追加: 今回のアクションで適用されたばかりのバフは除外
        if b.get('newly_applied'):
            continue
        # Resolve full effect data (dynamic or static)
        effect_data = get_buff_effect(b.get('name'))
        if not effect_data: continue

        conf = effect_data.get('on_damage_state')
        # print(f"[DEBUG] Checking buff {b.get('name')}: on_damage_state={conf}")
        if not conf: continue

        s_name = conf.get('stat')
        s_val = conf.get('value', 0)


        if s_name and s_val > 0:
            curr = get_status_value(char, s_name)
            # print(f"[DEBUG] Triggering on_damage_state: {s_name} {curr} -> {curr + s_val}")
            _update_char_stat(room, char, s_name, curr + s_val, username=f"[{b.get('name')}]")
            log_snippets.append(f"[{b.get('name')}→{s_name}+{s_val}]")
            if s_name == 'HP':
                total_applied_damage += s_val

    return total_applied_damage

def process_on_hit_buffs(actor, target, damage_val, log_snippets):
    """
    攻撃ヒット時トリガーバフの処理 (例: 爆縮)
    Returns: extra_damage (int)
    """
    from plugins.buffs.registry import buff_registry

    total_extra_damage = 0
    if not actor or 'special_buffs' not in actor:
        return 0

    logger.info(f"[process_on_hit_buffs] Checking buffs for {actor.get('name')}. Count: {len(actor['special_buffs'])}")

    # スナップショットをとって回す（副作用でリストが変わる可能性があるため）
    for buff_entry in list(actor['special_buffs']):
        buff_id = buff_entry.get('buff_id')
        handler_cls = buff_registry.get_handler(buff_id)

        if handler_cls and hasattr(handler_cls, 'on_hit_damage_calculation'):
            logger.info(f"[process_on_hit_buffs] Executing {handler_cls.__name__} for {buff_id}")
            # クラスメソッドとして呼び出し
            new_damage, logs = handler_cls.on_hit_damage_calculation(actor, target, damage_val + total_extra_damage)

            diff = new_damage - (damage_val + total_extra_damage)
            if diff != 0:
                logger.info(f"[process_on_hit_buffs] {handler_cls.__name__} added {diff} damage")
                total_extra_damage += diff

            if logs:
                log_snippets.extend(logs)
        else:
            logger.info(f"[process_on_hit_buffs] No handler or hook for {buff_id} ({buff_entry.get('name')}). Has Handler: {bool(handler_cls)}")

    return total_extra_damage

def execute_pre_match_effects(room, actor, target, skill_data, target_skill_data=None):
    """
    Match実行時のPRE_MATCH効果適用
    """
    if not skill_data or not actor: return

    # スキルIDを取得（actor['used_skills_this_round']から最後に使用したスキルを取得）
    skill_id = None
    if 'used_skills_this_round' in actor and actor['used_skills_this_round']:
        skill_id = actor['used_skills_this_round'][-1]

    try:
        rule_json_str = skill_data.get('特記処理', '{}')
        rule_data = json.loads(rule_json_str)
        effects_array = rule_data.get("effects", [])

        # Room state for context
        state = get_room_state(room)
        context = {
            "characters": state['characters'],
            "timeline": state.get('timeline', [])
        } if state else None

        _, logs, changes = process_skill_effects(effects_array, "PRE_MATCH", actor, target, target_skill_data, context=context)

        for (char, type, name, value) in changes:
            if type == "APPLY_STATE":
                current_val = get_status_value(char, name)
                _update_char_stat(room, char, name, current_val + value, username=f"[{format_skill_name_for_log(skill_id, skill_data, actor)}]")
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

def proceed_next_turn(room):
    """
    ターン進行ロジック
    """
    state = get_room_state(room)
    if not state: return
    try:
        from manager.battle.common_manager import ensure_battle_state_vNext
        ensure_battle_state_vNext(state, round_value=state.get('round', 0))
    except Exception as e:
        logger.error(f"battle_state ensure failed in proceed_next_turn room={room}: {e}")

    timeline = state.get('timeline', [])
    current_entry_id = state.get('turn_entry_id')
    current_char_id = state.get('turn_char_id') # Maintain for compatibility

    if not timeline:
        return

    # 現在の手番エントリIDがタイムラインのどこにあるか探す
    current_idx = -1
    if current_entry_id:
        # Find index by entry ID
        for idx, entry in enumerate(timeline):
            if entry['id'] == current_entry_id:
                current_idx = idx
                break

    next_entry = None

    # 現在位置の「次」から末尾に向かって、未行動のエントリを探す
    from plugins.buffs.confusion import ConfusionBuff
    from plugins.buffs.immobilize import ImmobilizeBuff

    for i in range(current_idx + 1, len(timeline)):
        entry = timeline[i]

        # 行動済みチェック (Entry flag)
        if entry.get('acted', False):
            continue

        cid = entry['char_id']
        # キャラデータ取得
        char = next((c for c in state['characters'] if c['id'] == cid), None)

        # 生存しているか
        if char and char.get('hp', 0) > 0:
            # 行動不能チェック (混乱)
            if ConfusionBuff.is_incapacitated(char):
                logger.info(f"Skipping {char['name']} due to incapacitation (Confusion)")
                # entry is skipped but not consumed? Or consumed?
                # Usually incapacitation consumes the turn.
                entry['acted'] = True
                continue

            # 行動不能チェック (Immobilize/Bu-04)
            can_act, reason = ImmobilizeBuff.can_act(char, {})
            if not can_act:
                logger.info(f"[TurnSkip] Skipping {char['name']} due to Immobilize: {reason}")
                entry['acted'] = True
                continue

            next_entry = entry
            break

    if next_entry:
        state['turn_entry_id'] = next_entry['id']
        state['turn_char_id'] = next_entry['char_id'] # Sync for frontend 'currentTurnId'

        next_char = next((c for c in state['characters'] if c['id'] == next_entry['char_id']), None)
        logger.info(f"[proceed_next_turn] Next turn: {next_char['name']} (EntryID: {next_entry['id']})")

        broadcast_log(room, f"--- {next_char['name']} の手番です ---", 'turn-change')
    else:
        state['turn_char_id'] = None
        state['turn_entry_id'] = None
        broadcast_log(room, "全ての行動可能キャラクターが終了しました。ラウンド終了処理を行ってください。", 'info')

    broadcast_state_update(room)
    save_specific_room_state(room)

def process_simple_round_end(state, room):
    """
    ラウンド終了時の共通処理（バフ減少、アイテムリセットなど）
    広域マッチからも呼び出される
    """
    logger.debug("===== process_simple_round_end 開始 =====")

    for char in state.get("characters", []):
        # バフタイマーの処理
        if "special_buffs" in char:
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
                    active_buffs.append(buff)

            char['special_buffs'] = active_buffs

        # アイテム使用制限をリセット
        if 'round_item_usage' in char:
            char['round_item_usage'] = {}

        # スキル使用履歴をリセット
        if 'used_immediate_skills_this_round' in char:
            char['used_immediate_skills_this_round'] = []
        if 'used_gem_protect_this_round' in char:
            char['used_gem_protect_this_round'] = False
        if 'used_skills_this_round' in char:
            char['used_skills_this_round'] = []

    # ★ 追加: マホロバ (ID: 5) ラウンド終了時一括処理
    mahoroba_targets = []
    for char in state.get('characters', []):
        if char.get('hp', 0) <= 0: continue

        # Origin Check
        if get_effective_origin_id(char) == 5:
            _update_char_stat(room, char, 'HP', char['hp'] + 3, username="[マホロバ恩恵]")
            mahoroba_targets.append(char['name'])

    if mahoroba_targets:
        broadcast_log(room, f"[マホロバ恩恵] {', '.join(mahoroba_targets)} のHPが3回復しました。", 'info')

    logger.debug("===== process_simple_round_end 完了 =====")
