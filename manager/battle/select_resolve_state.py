import time

from manager.dice_roller import roll_dice
from manager.logs import setup_logger
from manager.game_logic import get_status_value
import manager.room_manager as room_manager
import manager.utils as _utils_mod
from manager.battle.pve_intent_planner import (
    _apply_pve_auto_enemy_intents,
    _broadcast_pve_round_start_preview_log,
)


logger = setup_logger(__name__)

get_room_state = getattr(room_manager, "get_room_state", lambda *_args, **_kwargs: None)
save_specific_room_state = getattr(room_manager, "save_specific_room_state", lambda *_args, **_kwargs: None)
broadcast_log = getattr(room_manager, "broadcast_log", lambda *_args, **_kwargs: None)
clear_newly_applied_flags = getattr(_utils_mod, 'clear_newly_applied_flags', lambda *_args, **_kwargs: 0)
clear_round_limited_flags = getattr(_utils_mod, 'clear_round_limited_flags', lambda *_args, **_kwargs: 0)

def _build_select_resolve_slots_from_timeline(room_state):
    slots = {}
    timeline = room_state.get('timeline', [])
    characters = room_state.get('characters', [])
    char_map = {c.get('id'): c for c in characters if isinstance(c, dict)}
    actor_slot_count = {}

    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        slot_id = entry.get('id')
        actor_id = entry.get('char_id')
        if not slot_id or not actor_id:
            continue

        char = char_map.get(actor_id, {})
        index_in_actor = actor_slot_count.get(actor_id, 0)
        actor_slot_count[actor_id] = index_in_actor + 1

        slots[slot_id] = {
            'slot_id': slot_id,
            'actor_id': actor_id,
            'team': char.get('type', 'unknown'),
            'index_in_actor': index_in_actor,
            'initiative': entry.get('speed', 0),
            'disabled': False,
            'locked_target': False,
            'status': 'ready' if char.get('hp', 0) > 0 else 'down',
            'is_alive': bool(char.get('hp', 0) > 0)
        }

    return slots

def _build_select_resolve_timeline_from_room(room_state, slots):
    slots = slots if isinstance(slots, dict) else {}
    if not slots:
        return []

    slot_ids = set(slots.keys())
    room_timeline = room_state.get('timeline', []) if isinstance(room_state, dict) else []
    ordered = []

    if isinstance(room_timeline, list) and room_timeline:
        first = room_timeline[0]
        if isinstance(first, dict):
            for entry in room_timeline:
                if not isinstance(entry, dict):
                    continue
                slot_id = entry.get('id')
                if slot_id in slot_ids:
                    ordered.append(slot_id)
        elif isinstance(first, str):
            for slot_id in room_timeline:
                if slot_id in slot_ids:
                    ordered.append(slot_id)

    if not ordered:
        return sorted(
            slots.keys(),
            key=lambda sid: (-int(slots.get(sid, {}).get('initiative', 0)), str(sid))
        )

    seen = set(ordered)
    missing = [sid for sid in slots.keys() if sid not in seen]
    if missing:
        missing.sort(key=lambda sid: (-int(slots.get(sid, {}).get('initiative', 0)), str(sid)))
        ordered.extend(missing)

    return ordered

def ensure_battle_state_vNext(room_state, battle_id=None, round_value=None, rebuild_slots=False):
    if not isinstance(room_state, dict):
        return None

    migrated = room_state.get('select_resolve_battle_state')
    battle_state = room_state.get('battle_state')
    if not isinstance(battle_state, dict):
        battle_state = migrated if isinstance(migrated, dict) else {}

    battle_state['battle_id'] = battle_id or battle_state.get('battle_id') or 'battle_main'
    battle_state['round'] = round_value if isinstance(round_value, int) else battle_state.get('round', room_state.get('round', 0))
    battle_state['phase'] = battle_state.get('phase', 'select')
    battle_state['slots'] = battle_state.get('slots', {})
    battle_state['timeline'] = battle_state.get('timeline', [])
    battle_state['tiebreak'] = battle_state.get('tiebreak', [])
    battle_state['intents'] = battle_state.get('intents', {})
    battle_state['resolve_snapshot_intents'] = battle_state.get('resolve_snapshot_intents', {})
    battle_state['resolve_snapshot_at'] = battle_state.get('resolve_snapshot_at')
    battle_state['behavior_runtime'] = battle_state.get('behavior_runtime', {})
    battle_state['redirects'] = battle_state.get('redirects', [])
    battle_state['resolve_ready'] = bool(battle_state.get('resolve_ready', False))
    battle_state['resolve_ready_info'] = battle_state.get('resolve_ready_info', {})
    battle_state['resolve'] = battle_state.get('resolve', {})
    battle_state['resolve']['mass_queue'] = battle_state['resolve'].get('mass_queue', [])
    battle_state['resolve']['single_queue'] = battle_state['resolve'].get('single_queue', [])
    battle_state['resolve']['resolved_slots'] = battle_state['resolve'].get('resolved_slots', [])
    battle_state['resolve']['trace'] = battle_state['resolve'].get('trace', [])
    battle_state['resolve']['auto_defense_charges'] = battle_state['resolve'].get('auto_defense_charges', {})

    if rebuild_slots or not battle_state['slots']:
        battle_state['slots'] = _build_select_resolve_slots_from_timeline(room_state)

    slots = battle_state.get('slots', {})
    slot_ids = set(slots.keys()) if isinstance(slots, dict) else set()

    current_timeline = battle_state.get('timeline', [])
    if not isinstance(current_timeline, list):
        current_timeline = []
    current_timeline = [sid for sid in current_timeline if sid in slot_ids]
    current_set = set(current_timeline)
    desired_timeline = _build_select_resolve_timeline_from_room(room_state, slots)



    if rebuild_slots or current_set != slot_ids:
        battle_state['timeline'] = desired_timeline
    else:
        battle_state['timeline'] = current_timeline

    if isinstance(battle_state.get('intents'), dict):
        battle_state['intents'] = {
            sid: intent for sid, intent in battle_state.get('intents', {}).items()
            if sid in slot_ids
        }
    if isinstance(battle_state.get('resolve_snapshot_intents'), dict):
        battle_state['resolve_snapshot_intents'] = {
            sid: intent for sid, intent in battle_state.get('resolve_snapshot_intents', {}).items()
            if sid in slot_ids
        }
    if isinstance(battle_state.get('behavior_runtime'), dict):
        actor_ids = {
            str((slot or {}).get('actor_id'))
            for slot in (slots.values() if isinstance(slots, dict) else [])
            if isinstance(slot, dict) and slot.get('actor_id')
        }
        battle_state['behavior_runtime'] = {
            str(actor_id): runtime
            for actor_id, runtime in battle_state.get('behavior_runtime', {}).items()
            if str(actor_id) in actor_ids and isinstance(runtime, dict)
        }

    resolved_slots = battle_state['resolve'].get('resolved_slots', [])
    if not isinstance(resolved_slots, list):
        resolved_slots = []
    battle_state['resolve']['resolved_slots'] = [sid for sid in resolved_slots if sid in slot_ids]

    for queue_key in ['mass_queue', 'single_queue']:
        queue = battle_state['resolve'].get(queue_key, [])
        if not isinstance(queue, list):
            queue = []
        battle_state['resolve'][queue_key] = [sid for sid in queue if sid in slot_ids]

    room_state['battle_state'] = battle_state
    if 'select_resolve_battle_state' in room_state:
        room_state.pop('select_resolve_battle_state', None)

    try:
        phase_sig = battle_state.get('phase')
        slots_sig = len(battle_state.get('slots', {}))
        intents_sig = len(battle_state.get('intents', {}))
        sig = (phase_sig, slots_sig, intents_sig)
        now = time.time()
        last_sig = getattr(ensure_battle_state_vNext, '_last_ensure_sig', None)
        last_ts = float(getattr(ensure_battle_state_vNext, '_last_ensure_ts', 0.0) or 0.0)
        if sig != last_sig or (now - last_ts) >= 5.0:
            logger.debug(
                "[battle_state.ensure] phase=%s slots=%s intents=%s",
                phase_sig,
                slots_sig,
                intents_sig
            )
            setattr(ensure_battle_state_vNext, '_last_ensure_sig', sig)
            setattr(ensure_battle_state_vNext, '_last_ensure_ts', now)
    except Exception:
        logger.debug("[battle_state.ensure] phase=%s", battle_state.get('phase'))
    return battle_state

def get_or_create_select_resolve_state(room, battle_id=None, round_value=None, rebuild_slots=False):
    room_state = get_room_state(room)
    if not room_state:
        return None
    return ensure_battle_state_vNext(
        room_state,
        battle_id=battle_id,
        round_value=round_value,
        rebuild_slots=rebuild_slots
    )

def build_select_resolve_state_payload(room, battle_id=None):
    battle_state = get_or_create_select_resolve_state(room, battle_id=battle_id)
    if not battle_state:
        return None
    return {
        'room_id': room,
        'battle_id': battle_state.get('battle_id'),
        'round': battle_state.get('round', 0),
        'phase': battle_state.get('phase', 'select'),
        'timeline': battle_state.get('timeline', []),
        'tiebreak': battle_state.get('tiebreak', []),
        'slots': battle_state.get('slots', {}),
        'intents': battle_state.get('intents', {}),
        'redirects': battle_state.get('redirects', []),
        'resolve_ready': bool(battle_state.get('resolve_ready', False)),
        'resolve_ready_info': battle_state.get('resolve_ready_info', {})
    }

def process_select_resolve_round_start(room, battle_id, round_value):
    state = get_room_state(room)
    if not state:
        return None
    clear_newly_applied_flags(state)
    clear_round_limited_flags(state)

    def _roll_1d6():
        result = roll_dice("1d6")
        try:
            return int(result.get('total', 1))
        except Exception:
            return 1

    battle_state = ensure_battle_state_vNext(
        state,
        battle_id=battle_id,
        round_value=round_value,
        rebuild_slots=False
    )
    if not battle_state:
        return None

    characters = state.get('characters', [])
    slot_entries = []
    legacy_timeline_entries = []
    from plugins.buffs.speed_mod import SpeedModBuff

    for char in characters:
        try:
            hp = int(char.get('hp', 0))
            x_val = float(char.get('x', -1))
            escaped = bool(char.get('is_escaped', False))
        except (ValueError, TypeError):
            continue

        if hp <= 0 or escaped or x_val < 0:
            continue
        can_act_from_round = int(char.get('can_act_from_round', 0) or 0)
        if bool(char.get('is_summoned', False)) and can_act_from_round > int(round_value):
            continue

        actor_id = char.get('id')
        if not actor_id:
            continue

        try:
            action_count = int(get_status_value(char, "行動回数"))
        except Exception:
            action_count = 0
        if action_count <= 0:
            try:
                action_count = int(get_status_value(char, '行動回数'))
            except Exception:
                action_count = 1
        action_count = max(1, action_count)

        char['totalSpeed'] = None

        try:
            speed_val = int(get_status_value(char, "速度"))
        except Exception:
            speed_val = 0
        if speed_val <= 0:
            try:
                speed_val = int(get_status_value(char, '速度'))
            except Exception:
                speed_val = 0
        speed_modifier = SpeedModBuff.get_speed_modifier(char)
        base_initiative = (speed_val // 6) + speed_modifier

        if speed_modifier != 0:
            mod_text = f"+{speed_modifier}" if speed_modifier > 0 else str(speed_modifier)
            broadcast_log(room, f"{char.get('name', actor_id)} の速度補正: {mod_text} (基礎速度に加算)", 'info')

        for i in range(action_count):
            slot_id = f"{actor_id}:r{round_value}:s{i}"
            roll = _roll_1d6()
            initiative = max(1, base_initiative + roll)
            slot_entries.append({
                'slot_id': slot_id,
                'actor_id': actor_id,
                'team': char.get('type', 'unknown'),
                'index_in_actor': i,
                'initiative': initiative,
                'speed_stat': speed_val,
                'speed_base': base_initiative,
                'speed_modifier': speed_modifier,
                'speed_roll': roll,
                'disabled': False,
                'locked_target': False,
                'status': 'ready',
                'is_alive': True,
                '_tie_roll': None
            })
            legacy_timeline_entries.append({
                'id': slot_id,
                'char_id': actor_id,
                'speed': initiative,
                'stat_speed': base_initiative,
                'roll': roll,
                'acted': False,
                'is_extra': (i > 0)
            })
            if i == 0:
                char['speedRoll'] = roll
                char['totalSpeed'] = initiative

        char['hasActed'] = False

    grouped_by_init = {}
    for entry in slot_entries:
        grouped_by_init.setdefault(entry['initiative'], []).append(entry)

    tiebreak_payload = []
    for initiative, group in grouped_by_init.items():
        if len(group) <= 1:
            continue
        rolls = {}
        for slot in group:
            tie_roll = _roll_1d6()
            slot['_tie_roll'] = tie_roll
            rolls[slot['slot_id']] = tie_roll
        tiebreak_payload.append({
            'initiative': initiative,
            'group': sorted([slot['slot_id'] for slot in group]),
            'rolls': rolls
        })

    slot_entries.sort(
        key=lambda x: (
            -x['initiative'],
            -(x['_tie_roll'] if x['_tie_roll'] is not None else -1),
            x['slot_id']
        )
    )

    slots_dict = {}
    timeline = []
    legacy_by_slot_id = {
        str(entry.get('id')): entry for entry in legacy_timeline_entries if isinstance(entry, dict)
    }
    legacy_timeline_sorted = []
    for slot in slot_entries:
        slot_id = slot['slot_id']
        slots_dict[slot_id] = {
            'slot_id': slot_id,
            'actor_id': slot['actor_id'],
            'team': slot['team'],
            'index_in_actor': slot['index_in_actor'],
            'initiative': slot['initiative'],
            'speed_stat': slot['speed_stat'],
            'speed_base': slot['speed_base'],
            'speed_modifier': slot['speed_modifier'],
            'speed_roll': slot['speed_roll'],
            'disabled': slot['disabled'],
            'locked_target': slot['locked_target'],
            'status': slot['status'],
            'is_alive': slot['is_alive']
        }
        timeline.append(slot_id)
        legacy_entry = legacy_by_slot_id.get(slot_id)
        if isinstance(legacy_entry, dict):
            legacy_timeline_sorted.append(legacy_entry)

    battle_state['round'] = round_value
    battle_state['phase'] = 'select'
    battle_state['slots'] = slots_dict
    battle_state['timeline'] = timeline
    battle_state['tiebreak'] = tiebreak_payload
    battle_state['intents'] = {}
    battle_state['resolve_snapshot_intents'] = {}
    battle_state['resolve_snapshot_at'] = None
    battle_state['redirects'] = []
    battle_state['resolve_ready'] = False
    battle_state['resolve_ready_info'] = {}
    battle_state['resolve']['mass_queue'] = []
    battle_state['resolve']['single_queue'] = []
    battle_state['resolve']['resolved_slots'] = []
    battle_state['resolve']['trace'] = []
    pve_auto_result = _apply_pve_auto_enemy_intents(state, battle_state, room)
    _broadcast_pve_round_start_preview_log(
        state,
        room,
        pve_auto_result.get('preview_rows', []) if isinstance(pve_auto_result, dict) else [],
        round_value=battle_state.get('round')
    )
    state['timeline'] = legacy_timeline_sorted

    save_specific_room_state(room)

    logger.info(
        "[battle_round_start] room=%s battle_id=%s round=%s slots=%s timeline_head=%s tiebreak_groups=%s",
        room,
        battle_id,
        round_value,
        len(slots_dict),
        timeline[:5],
        len(tiebreak_payload)
    )

    return {
        'room_id': room,
        'battle_id': battle_id,
        'round': round_value,
        'phase': 'select',
        'slots': slots_dict,
        'timeline': timeline,
        'tiebreak': tiebreak_payload
    }

