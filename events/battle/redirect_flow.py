# events/battle/redirect_flow.py
# リダイレクト（対象すり替え）処理の実体。計画書34 Phase 1 で
# events/battle/common_routes.py から移設。ロジック・ログは移設前と同一。
#
# events/battle/phase_flow.py 等の既存サブモジュールと同じ方針で、
# common_routes.py 側の関数（_ensure_intent_for_slot 等）は関数注入で受け取る
# （本モジュールは common_routes を import しない。循環回避）。


def clear_redirect_state(state):
    if not isinstance(state, dict):
        return
    slots = state.get('slots', {})
    if isinstance(slots, dict):
        for slot in slots.values():
            if not isinstance(slot, dict):
                continue
            slot['locked_target'] = False
            slot.pop('locked_by_slot', None)
            slot.pop('locked_by_initiative', None)
            slot.pop('locked_by_intent_rev', None)
            slot.pop('locked_by_committed_at', None)
    state['redirects'] = []


def append_redirect_record(state, record):
    state.setdefault('redirects', [])
    state['redirects'].append(record)
    trace = state.get('resolve', {}).get('trace', [])
    trace.append({
        'step': len(trace) + 1,
        'kind': record.get('kind', 'redirect'),
        'attacker_slot': record.get('by_slot'),
        'defender_slot': record.get('from_slot'),
        'target_actor_id': None,
        'rolls': {},
        'outcome': 'no_effect',
        'cost': {'mp': 0, 'hp': 0},
        'notes': None
    })
    state['resolve']['trace'] = trace


def cancel_redirect_by_no_redirect(
    room_id, battle_id, state, slot_id, reset_target=False,
    *, ensure_intent_for_slot_fn, server_ts_fn,
):
    slot = state.get('slots', {}).get(slot_id, {})
    if not slot:
        return

    intent = ensure_intent_for_slot_fn(state, slot_id)
    was_locked = bool(slot.get('locked_target', False))
    old_target_slot = intent.get('target', {}).get('slot_id')
    if not was_locked:
        return

    slot['locked_target'] = False
    if 'locked_by_slot' in slot:
        slot.pop('locked_by_slot', None)
    if 'locked_by_initiative' in slot:
        slot.pop('locked_by_initiative', None)
    if 'locked_by_intent_rev' in slot:
        slot.pop('locked_by_intent_rev', None)
    if 'locked_by_committed_at' in slot:
        slot.pop('locked_by_committed_at', None)
    if reset_target:
        intent['target'] = {'type': 'none', 'slot_id': None}

    cancel_record = {
        'ts': server_ts_fn(),
        'kind': 'redirect_cancelled_by_no_redirect',
        'by_slot': slot_id,
        'from_slot': slot_id,
        'old_target_slot': old_target_slot,
        'new_target_slot': None
    }
    append_redirect_record(state, cancel_record)
    print(f"unlock target for {slot_id} due to no_redirect")


def try_apply_redirect(
    room_id, battle_id, state, slot_a,
    *, ensure_intent_for_slot_fn, infer_target_scope_fn, server_ts_fn,
):
    slot_a_data = state.get('slots', {}).get(slot_a, {})
    intent_a = ensure_intent_for_slot_fn(state, slot_a)
    target = intent_a.get('target', {})

    if target.get('type') != 'single_slot':
        return
    slot_b = target.get('slot_id')
    if not slot_b or slot_b not in state.get('slots', {}):
        return
    if slot_b == slot_a:
        return

    intent_b = ensure_intent_for_slot_fn(state, slot_b)
    slot_b_data = state['slots'][slot_b]
    scope_a = infer_target_scope_fn(intent_a.get('skill_id'))
    scope_b = infer_target_scope_fn(intent_b.get('skill_id'))
    # Ally-target skills are excluded from redirect in this route.
    if scope_a == 'ally' or scope_b == 'ally':
        return

    # If slot_b is currently aiming at a mass skill slot, keep that pairing stable.
    # This prevents higher-initiative third parties from stealing the clash target.
    slot_b_target = (intent_b.get('target') or {})
    slot_b_target_slot = slot_b_target.get('slot_id') if slot_b_target.get('type') == 'single_slot' else None
    if slot_b_target_slot:
        intent_targeted_by_b = ensure_intent_for_slot_fn(state, slot_b_target_slot)
        target_mass_type = ((intent_targeted_by_b.get('tags') or {}).get('mass_type'))
        if target_mass_type in ['mass_individual', 'mass_summation', 'individual', 'summation']:
            return

    init_a = int(slot_a_data.get('initiative', 0))
    init_b = int(slot_b_data.get('initiative', 0))
    if init_a <= init_b:
        return

    if intent_a.get('tags', {}).get('no_redirect', False):
        return
    if intent_b.get('tags', {}).get('no_redirect', False):
        return

    # Redirect contention rule:
    # among faster-than-B candidates, the most recently committed declaration wins.
    intent_rev_a = int(intent_a.get('intent_rev', 0) or 0)
    committed_at_a = int(intent_a.get('committed_at', 0) or 0)
    current_locked_by_rev = int(slot_b_data.get('locked_by_intent_rev', -999999))
    current_locked_by_ts = int(slot_b_data.get('locked_by_committed_at', -999999))
    if slot_b_data.get('locked_target', False):
        if intent_rev_a < current_locked_by_rev:
            return
        if intent_rev_a == current_locked_by_rev and committed_at_a < current_locked_by_ts:
            return

    old_target_slot = intent_b.get('target', {}).get('slot_id')
    intent_b['target'] = {'type': 'single_slot', 'slot_id': slot_a}
    slot_b_data['locked_target'] = True
    slot_b_data['locked_by_slot'] = slot_a
    slot_b_data['locked_by_initiative'] = init_a
    slot_b_data['locked_by_intent_rev'] = intent_rev_a
    slot_b_data['locked_by_committed_at'] = committed_at_a

    redirect_record = {
        'ts': server_ts_fn(),
        'kind': 'redirect',
        'by_slot': slot_a,
        'from_slot': slot_b,
        'old_target_slot': old_target_slot,
        'new_target_slot': slot_a
    }
    append_redirect_record(state, redirect_record)
    print(
        f"redirect {slot_b} -> {slot_a} by {slot_a}"
        f"(init={init_a} > {init_b}, rev={intent_rev_a}, ts={committed_at_a})"
    )


def recalculate_redirect_state(
    room_id, battle_id, state,
    *, ensure_intent_for_slot_fn, infer_target_scope_fn, server_ts_fn,
):
    if not isinstance(state, dict):
        return
    clear_redirect_state(state)
    slots = state.get('slots', {}) or {}
    intents = state.get('intents', {}) or {}
    if not isinstance(slots, dict) or not isinstance(intents, dict):
        return

    def _redirect_sort_key(slot_id):
        intent = intents.get(slot_id, {}) if isinstance(intents, dict) else {}
        slot = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
        # Lower values first so later declarations are processed later and can overwrite.
        intent_rev = int(intent.get('intent_rev', 0) or 0)
        committed_at = int(intent.get('committed_at', 0) or 0)
        initiative = int(slot.get('initiative', 0) or 0)
        return (intent_rev, committed_at, initiative, str(slot_id))

    ordered_slot_ids = sorted([sid for sid in slots.keys()], key=_redirect_sort_key)

    for slot_id in ordered_slot_ids:
        intent = ensure_intent_for_slot_fn(state, slot_id)
        if not intent.get('committed', False):
            continue
        target = intent.get('target', {}) or {}
        if target.get('type') != 'single_slot':
            continue
        if not intent.get('skill_id'):
            continue
        if intent.get('tags', {}).get('no_redirect', False):
            cancel_redirect_by_no_redirect(
                room_id, battle_id, state, slot_id, reset_target=False,
                ensure_intent_for_slot_fn=ensure_intent_for_slot_fn,
                server_ts_fn=server_ts_fn,
            )
            continue
        try_apply_redirect(
            room_id, battle_id, state, slot_id,
            ensure_intent_for_slot_fn=ensure_intent_for_slot_fn,
            infer_target_scope_fn=infer_target_scope_fn,
            server_ts_fn=server_ts_fn,
        )
