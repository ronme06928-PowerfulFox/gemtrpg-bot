def _consume_legacy_timeline_entries_for_slots(state, slots, processed_slots):
    if not isinstance(state, dict):
        return 0
    timeline = state.get('timeline', [])
    if not isinstance(timeline, list) or not timeline:
        return 0

    consumed = 0
    slot_map = slots if isinstance(slots, dict) else {}
    actor_consume_counts = {}
    for sid in (processed_slots or []):
        slot_data = (slot_map.get(sid, {}) or {})
        if slot_data.get('virtual_reuse', False):
            # Virtual re-use slots are resolve-only steps and must not consume extra legacy turn entries.
            continue
        actor_id = slot_data.get('actor_id')
        if not actor_id:
            continue
        key = str(actor_id)
        actor_consume_counts[key] = int(actor_consume_counts.get(key, 0)) + 1

    if not actor_consume_counts:
        return 0

    for actor_id, need_count in actor_consume_counts.items():
        remain = int(max(0, need_count))
        if remain <= 0:
            continue
        for entry in timeline:
            if remain <= 0:
                break
            if not isinstance(entry, dict):
                continue
            if str(entry.get('char_id')) != actor_id:
                continue
            if entry.get('acted', False):
                continue
            entry['acted'] = True
            consumed += 1
            remain -= 1

        char = next((c for c in state.get('characters', []) if str(c.get('id')) == actor_id), None)
        if char:
            remaining = any(
                isinstance(e, dict)
                and str(e.get('char_id')) == actor_id
                and not e.get('acted', False)
                for e in timeline
            )
            char['hasActed'] = not remaining

    return consumed

def _sync_legacy_has_acted_flags_from_timeline(state, actor_ids=None):
    if not isinstance(state, dict):
        return 0

    timeline = state.get('timeline', [])
    characters = state.get('characters', [])
    if not isinstance(timeline, list) or not isinstance(characters, list):
        return 0

    actor_filter = None
    if actor_ids is not None:
        actor_filter = {str(aid) for aid in actor_ids if aid}

    remaining_by_actor = {}
    present_actor_ids = set()
    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        actor_id = entry.get('char_id')
        if not actor_id:
            continue
        actor_key = str(actor_id)
        if actor_filter is not None and actor_key not in actor_filter:
            continue
        present_actor_ids.add(actor_key)
        if not entry.get('acted', False):
            remaining_by_actor[actor_key] = True

    synced = 0
    for char in characters:
        actor_id = char.get('id')
        if not actor_id:
            continue
        actor_key = str(actor_id)
        if actor_filter is not None and actor_key not in actor_filter:
            continue
        if actor_key not in present_actor_ids:
            continue
        has_acted = not remaining_by_actor.get(actor_key, False)
        if char.get('hasActed') != has_acted:
            synced += 1
        char['hasActed'] = has_acted

    return synced

def _snapshot_legacy_timeline_state(state):
    if not isinstance(state, dict):
        return {'total': 0, 'acted': 0, 'current_entry_id': None, 'current_char_id': None, 'head': []}
    timeline = state.get('timeline', [])
    if not isinstance(timeline, list):
        timeline = []
    acted = 0
    head = []
    for idx, entry in enumerate(timeline):
        if not isinstance(entry, dict):
            continue
        is_acted = bool(entry.get('acted', False))
        if is_acted:
            acted += 1
        if len(head) < 6:
            head.append({
                'idx': idx,
                'id': entry.get('id'),
                'char_id': entry.get('char_id'),
                'acted': is_acted
            })
    return {
        'total': len(timeline),
        'acted': acted,
        'current_entry_id': state.get('turn_entry_id'),
        'current_char_id': state.get('turn_char_id'),
        'head': head
    }

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

