from events.battle.intent_targets import _normalize_target_slot_id, _resolve_slot_team


def _canonical_team(raw_value):
    text = str(raw_value or '').strip().lower()
    if text in ['ally', 'player', 'friend', 'friends']:
        return 'ally'
    if text in ['enemy', 'foe', 'opponent', 'boss', 'npc']:
        return 'enemy'
    return None


def _is_actor_actionable(room_id, actor_id, *, get_room_state_fn, confusion_buff_cls, immobilize_buff_cls):
    room_state = get_room_state_fn(room_id)
    if not room_state:
        return False
    actor = next((c for c in room_state.get('characters', []) if c.get('id') == actor_id), None)
    if not actor:
        return False
    if actor.get('hp', 0) <= 0:
        return False
    if actor.get('is_escaped', False):
        return False
    try:
        x_val = float(actor.get('x', -1))
    except (TypeError, ValueError):
        x_val = -1
    if x_val < 0:
        return False
    if confusion_buff_cls.is_incapacitated(actor):
        return False
    can_act, _ = immobilize_buff_cls.can_act(actor, {})
    if not can_act:
        return False
    return True


def _is_actor_targetable(room_id, actor_id, *, get_room_state_fn):
    room_state = get_room_state_fn(room_id)
    if not room_state:
        return False
    actor = next((c for c in room_state.get('characters', []) if c.get('id') == actor_id), None)
    if not actor:
        return False
    if actor.get('hp', 0) <= 0:
        return False
    if actor.get('is_escaped', False):
        return False
    try:
        x_val = float(actor.get('x', -1))
    except (TypeError, ValueError):
        x_val = -1
    return x_val >= 0


def _is_valid_single_target_slot_for_pve_enemy(room_id, state, source_slot_id, target_slot_id, *, get_room_state_fn):
    slots = state.get('slots', {}) or {}
    source_slot = slots.get(source_slot_id, {}) if isinstance(slots, dict) else {}
    target_slot = slots.get(target_slot_id, {}) if isinstance(slots, dict) else {}
    if not isinstance(source_slot, dict) or not isinstance(target_slot, dict):
        return False
    if bool(target_slot.get('disabled', False)):
        return False

    source_team = _canonical_team(source_slot.get('team'))
    target_team = _canonical_team(target_slot.get('team'))
    if source_team and target_team and source_team == target_team:
        return False
    if target_team and target_team != 'ally':
        return False

    target_actor_id = target_slot.get('actor_id')
    if not target_actor_id:
        return False
    if not _is_actor_targetable(room_id, target_actor_id, get_room_state_fn=get_room_state_fn):
        return False
    return True


def _pick_default_pve_enemy_target_slot(room_id, state, source_slot_id, preferred_slot_id=None, *, get_room_state_fn):
    slots = state.get('slots', {}) or {}
    if not isinstance(slots, dict):
        return None

    if preferred_slot_id and _is_valid_single_target_slot_for_pve_enemy(
        room_id, state, source_slot_id, preferred_slot_id, get_room_state_fn=get_room_state_fn
    ):
        return preferred_slot_id

    candidates = []
    for slot_id, slot in slots.items():
        if not _is_valid_single_target_slot_for_pve_enemy(
            room_id, state, source_slot_id, slot_id, get_room_state_fn=get_room_state_fn
        ):
            continue
        candidates.append((int(slot.get('initiative', 0) or 0), str(slot_id)))

    if not candidates:
        return None
    candidates.sort(key=lambda row: (-row[0], row[1]))
    return candidates[0][1]


def _is_pve_enemy_auto_target_slot(room_id, state, slot_id, *, get_room_state_fn):
    room_state = get_room_state_fn(room_id) or {}
    if room_state.get('battle_mode', 'pvp') != 'pve':
        return False

    slots = state.get('slots', {}) or {}
    slot = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
    if not isinstance(slot, dict):
        return False

    slot_team = _canonical_team(slot.get('team'))
    if slot_team and slot_team != 'enemy':
        return False

    actor_id = slot.get('actor_id')
    if not actor_id:
        return False

    actor = next((c for c in room_state.get('characters', []) if c.get('id') == actor_id), None)
    if not actor:
        return False

    actor_team = _canonical_team(actor.get('type'))
    if actor_team and actor_team != 'enemy':
        return False

    flags = actor.get('flags', {}) if isinstance(actor.get('flags'), dict) else {}
    return bool(flags.get('auto_target_select', True))


def _apply_pve_enemy_intent_defaults(
    room_id,
    state,
    slot_id,
    intent,
    intent_before=None,
    requested_skill_id=None,
    requested_target=None,
    *,
    get_room_state_fn,
    normalize_target_by_skill_compat_fn,
    default_intent_tags_fn,
    build_tags_fn,
    ai_suggest_skill_fn,
):
    if not _is_pve_enemy_auto_target_slot(room_id, state, slot_id, get_room_state_fn=get_room_state_fn):
        return intent
    if not isinstance(intent, dict):
        return intent

    prev = intent_before if isinstance(intent_before, dict) else {}
    req_target = requested_target if isinstance(requested_target, dict) else {}
    explicit_target_slot = None
    if req_target.get('type') == 'single_slot':
        explicit_target_slot = _normalize_target_slot_id(req_target.get('slot_id'))

    target = intent.get('target', {}) if isinstance(intent.get('target'), dict) else {}
    curr_target_slot = _normalize_target_slot_id(target.get('slot_id')) if target.get('type') == 'single_slot' else None
    prev_target = (prev.get('target') or {}) if isinstance(prev.get('target'), dict) else {}
    prev_target_slot = _normalize_target_slot_id(prev_target.get('slot_id')) if prev_target.get('type') == 'single_slot' else None

    if explicit_target_slot:
        intent['target'] = {'type': 'single_slot', 'slot_id': explicit_target_slot}
    else:
        chosen_target = None
        if curr_target_slot and _is_valid_single_target_slot_for_pve_enemy(
            room_id, state, slot_id, curr_target_slot, get_room_state_fn=get_room_state_fn
        ):
            chosen_target = curr_target_slot
        if not chosen_target and prev_target_slot and _is_valid_single_target_slot_for_pve_enemy(
            room_id, state, slot_id, prev_target_slot, get_room_state_fn=get_room_state_fn
        ):
            chosen_target = prev_target_slot
        if not chosen_target:
            chosen_target = _pick_default_pve_enemy_target_slot(
                room_id,
                state,
                slot_id,
                preferred_slot_id=prev_target_slot,
                get_room_state_fn=get_room_state_fn,
            )
        if chosen_target:
            intent['target'] = {'type': 'single_slot', 'slot_id': chosen_target}

    room_state = get_room_state_fn(room_id) or {}
    slots = state.get('slots', {}) or {}
    actor_id = (slots.get(slot_id) or {}).get('actor_id') if isinstance(slots, dict) else None
    actor = next((c for c in room_state.get('characters', []) if c.get('id') == actor_id), None)
    flags = actor.get('flags', {}) if isinstance(actor, dict) and isinstance(actor.get('flags'), dict) else {}
    auto_skill_select = bool(
        flags.get('auto_skill_select', False)
        or flags.get('show_planned_skill', False)
    )
    explicit_skill = requested_skill_id not in [None, '']

    if auto_skill_select and not explicit_skill and not intent.get('skill_id'):
        suggested = ai_suggest_skill_fn(actor)
        if suggested:
            intent['skill_id'] = suggested

    normalized_target, target_error = normalize_target_by_skill_compat_fn(
        intent.get('skill_id'),
        intent.get('target'),
        state=state,
        source_slot_id=slot_id,
        allow_none=True
    )
    if not target_error:
        intent['target'] = normalized_target
    intent['tags'] = default_intent_tags_fn(build_tags_fn(intent.get('skill_id'), intent.get('target')))
    return intent


def _required_slots(room_id, state, *, get_room_state_fn, is_actor_actionable_fn):
    required = set()
    room_state = get_room_state_fn(room_id) or {}
    is_pve_mode = str(room_state.get('battle_mode', 'pvp') or 'pvp').strip().lower() == 'pve'
    for slot_id, slot in state.get('slots', {}).items():
        if slot.get('disabled', False):
            continue
        actor_id = slot.get('actor_id')
        if not is_actor_actionable_fn(room_id, actor_id):
            continue

        intent = state.get('intents', {}).get(slot_id, {})
        is_committed_instant = bool(intent.get('committed') and intent.get('tags', {}).get('instant'))
        if is_committed_instant:
            continue
        if is_pve_mode and _resolve_slot_team(state, slot_id) == 'enemy':
            skill_id = str(intent.get('skill_id', '') or '').strip()
            if not skill_id:
                continue
        required.add(slot_id)
    return required
