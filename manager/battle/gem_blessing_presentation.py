"""Presentation records only; skill access and cost processing remain the callers' responsibility."""
import copy


def presentation_battle_state(room, get_room_state):
    # Cost helpers can also run without a loaded room (unit tests / legacy duel).
    try:
        return (get_room_state(room) or {}).get('battle_state') if room else None
    except RuntimeError as exc:
        if str(exc) == 'Initial room loading requires an app context':
            return None
        raise


def queue_immediate_gem(state, actor, skill_id, skill, skill_name):
    from manager.battle.skill_access import is_gem_protect_skill
    if isinstance(state, dict) and is_gem_protect_skill(skill):
        state.setdefault('pending_gem_blessings', []).append({
            'actor_id': actor.get('id'), 'skill_id': skill_id,
            'skill_name': skill_name, 'round': state.get('round', 0),
        })


def take_gem_prelude(state, timestamp):
    rows = state.pop('pending_gem_blessings', [])
    state['pending_gem_blessings'] = []
    if not rows:
        return None
    return {'kind': 'gem_blessing_prelude', 'step': 1, 'step_index': 0,
            'timestamp': timestamp, 'gem_blessings': copy.deepcopy(rows)}


def record_resolve_gem(state, actor, skill, slot_id=None):
    from manager.battle.skill_access import is_gem_protect_skill
    if not isinstance(state, dict) or not is_gem_protect_skill(skill):
        return
    skill_id = skill.get('id') or skill.get('スキルID')
    intents = state.get('__resolve_intents_override') or state.get('resolve_snapshot_intents') or state.get('intents', {})
    slots = [slot_id] if slot_id else [sid for sid, slot in state.get('slots', {}).items()
        if str(slot.get('actor_id')) == str(actor.get('id'))
        and intents.get(sid, {}).get('skill_id') == skill_id]
    pending = state.setdefault('resolve', {}).setdefault('pending_gem_uses', [])
    for sid in slots:
        row = {'actor_id': actor.get('id'), 'slot_id': sid}
        if row not in pending:
            pending.append(row)


def take_resolve_gem_users(state, entry):
    sides = {entry.get('attacker_slot_id'): 'attacker', entry.get('defender_slot_id'): 'defender'}
    sides.update({sid: 'defender' for sid in entry.get('participants', [])})
    pending = state.setdefault('resolve', {}).get('pending_gem_uses', [])
    used = [{ 'side': sides[row['slot_id']], **row} for row in pending if row['slot_id'] in sides]
    state['resolve']['pending_gem_uses'] = [row for row in pending if row['slot_id'] not in sides]
    return used
