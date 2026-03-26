from extensions import all_skill_data

def _get_character_by_id(state, actor_id):
    if not state or not actor_id:
        return None
    return next((c for c in state.get('characters', []) if c.get('id') == actor_id), None)

def is_dodge_lock_active(state, actor_id):
    actor = _get_character_by_id(state, actor_id)
    if not actor:
        return False
    try:
        from plugins.buffs.dodge_lock import DodgeLockBuff
        return DodgeLockBuff.has_re_evasion(actor)
    except Exception:
        return False

def get_dodge_lock_skill_id(state, actor_id):
    actor = _get_character_by_id(state, actor_id)
    if not actor:
        return None
    try:
        from plugins.buffs.dodge_lock import DodgeLockBuff
        return DodgeLockBuff.get_locked_skill_id(actor)
    except Exception:
        return None

def _is_evade_skill(skill_id):
    if not skill_id:
        return False
    skill_data = all_skill_data.get(skill_id, {})
    category = str(
        skill_data.get('分類')
        or skill_data.get('attribute')
        or ''
    )
    if category in ['回避', '回避']:
        return True
    for tag in skill_data.get('tags', []) or []:
        if isinstance(tag, str) and ('回避' in tag or '回避' in tag):
            return True
    if '回避' in str(skill_data.get('name') or ''):
        return True
    return False

def _choose_highest_initiative_slot(slot_ids, slots):
    if not slot_ids:
        return None
    return max(
        slot_ids,
        key=lambda s: (int(slots.get(s, {}).get('initiative', 0)), str(s))
    )

def select_evade_insert_slot(state, battle_state, defender_actor_id, attacker_slot):
    if not defender_actor_id or not attacker_slot:
        return None, None
    if not is_dodge_lock_active(state, defender_actor_id):
        return None, None

    slots = battle_state.get('slots', {})
    intents = battle_state.get('intents', {})
    locked_skill_id = get_dodge_lock_skill_id(state, defender_actor_id)

    actor_slot_ids = [
        slot_id
        for slot_id, slot in slots.items()
        if slot.get('actor_id') == defender_actor_id
    ]
    if not actor_slot_ids:
        return None, None

    def _is_locked_skill_match(skill_id):
        if not locked_skill_id:
            return True
        return skill_id == locked_skill_id

    direct_candidates = []
    for slot_id in actor_slot_ids:
        slot_data = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
        if isinstance(slot_data, dict) and slot_data.get('cancelled_without_use'):
            continue
        intent = intents.get(slot_id, {})
        skill_id = intent.get('skill_id')
        if not intent.get('committed', False):
            continue
        if not _is_evade_skill(skill_id):
            continue
        if not _is_locked_skill_match(skill_id):
            continue
        target = intent.get('target', {})
        if target.get('type') == 'single_slot' and target.get('slot_id') == attacker_slot:
            direct_candidates.append(slot_id)
    picked = _choose_highest_initiative_slot(direct_candidates, slots)
    if picked:
        return picked, 'targeted_evade'

    evade_candidates = []
    for slot_id in actor_slot_ids:
        slot_data = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
        if isinstance(slot_data, dict) and slot_data.get('cancelled_without_use'):
            continue
        intent = intents.get(slot_id, {})
        skill_id = intent.get('skill_id')
        if not intent.get('committed', False):
            continue
        if not _is_evade_skill(skill_id):
            continue
        if not _is_locked_skill_match(skill_id):
            continue
        evade_candidates.append(slot_id)
    picked = _choose_highest_initiative_slot(evade_candidates, slots)
    if picked:
        return picked, 'evade_slot_reuse'

    resolved_slots = battle_state.get('resolve', {}).get('resolved_slots', [])
    reusable = [
        slot_id for slot_id in resolved_slots
        if slots.get(slot_id, {}).get('actor_id') == defender_actor_id
        and not slots.get(slot_id, {}).get('cancelled_without_use')
    ]
    picked = _choose_highest_initiative_slot(reusable, slots)
    if picked:
        return picked, 'resolved_slot_reuse'

    return None, None

def select_hard_followup_evade_slot(state, battle_state, defender_actor_id, attacker_slot):
    """
    強硬追撃時に、防御側が使用する再回避スロットを選択する。
      1) 強硬追撃の target を直接指定している未解決回避
      2) 未解決の回避スロット
      3) 再回避ロックがない場合、解決済み回避の再利用
    """
    if not defender_actor_id or not attacker_slot:
        return None, None

    slots = battle_state.get('slots', {})
    intents = battle_state.get('intents', {})
    resolved_slots = battle_state.get('resolve', {}).get('resolved_slots', [])
    resolved_set = set(resolved_slots if isinstance(resolved_slots, list) else [])

    actor_slot_ids = [
        slot_id
        for slot_id, slot in slots.items()
        if isinstance(slot, dict) and slot.get('actor_id') == defender_actor_id
    ]
    if not actor_slot_ids:
        return None, None

    def _is_unresolved(slot_id):
        return str(slot_id) not in resolved_set

    def _is_committed_evade(slot_id):
        slot_data = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
        if isinstance(slot_data, dict) and slot_data.get('cancelled_without_use'):
            return False
        intent = intents.get(slot_id, {}) if isinstance(intents, dict) else {}
        skill_id = intent.get('skill_id')
        if not intent.get('committed', False):
            return False
        return _is_evade_skill(skill_id)


    direct_targeted = []
    for slot_id in actor_slot_ids:
        if not _is_unresolved(slot_id):
            continue
        if not _is_committed_evade(slot_id):
            continue
        target = intents.get(slot_id, {}).get('target', {})
        if target.get('type') == 'single_slot' and target.get('slot_id') == attacker_slot:
            direct_targeted.append(slot_id)
    picked = _choose_highest_initiative_slot(direct_targeted, slots)
    if picked:
        return picked, 'targeted_evade'


    unresolved_evade = [
        slot_id for slot_id in actor_slot_ids
        if _is_unresolved(slot_id) and _is_committed_evade(slot_id)
    ]
    picked = _choose_highest_initiative_slot(unresolved_evade, slots)
    if picked:
        return picked, 'unresolved_evade'


    if is_dodge_lock_active(state, defender_actor_id):
        reusable = [
            slot_id for slot_id in actor_slot_ids
            if str(slot_id) in resolved_set and not slots.get(slot_id, {}).get('cancelled_without_use')
        ]
        picked = _choose_highest_initiative_slot(reusable, slots)
        if picked:
            return picked, 're_evasion_reuse'

    return None, None

