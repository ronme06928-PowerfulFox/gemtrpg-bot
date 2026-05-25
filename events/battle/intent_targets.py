# events/battle/intent_targets.py
from extensions import all_skill_data
from manager.battle.skill_rules import _extract_rule_data_from_skill as _extract_rule_data_from_skill_v2


def _default_intent_tags(existing=None):
    tags = dict(existing or {})
    tags.setdefault('instant', False)
    tags.setdefault('mass_type', None)
    tags.setdefault('no_redirect', False)
    return tags

def _default_target(target):
    if isinstance(target, dict):
        target_type = target.get('type', 'none')
        if target_type not in ['single_slot', 'mass_individual', 'mass_summation', 'none', 'random_single']:
            target_type = 'none'
        return {
            'type': target_type,
            'slot_id': target.get('slot_id'),
            'random_target_scope': target.get('random_target_scope', 'enemy'),
        }
    return {'type': 'none', 'slot_id': None}

def _normalize_target_slot_id(value):
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    return str(value)

def _validate_and_normalize_target(target, state, allow_none=True):
    normalized = _default_target(target)
    target_type = normalized.get('type')
    slot_id = _normalize_target_slot_id(normalized.get('slot_id'))

    if target_type == 'none':
        if not allow_none:
            return None, 'target.type none is not allowed here'
        return {'type': 'none', 'slot_id': None}, None

    if target_type == 'single_slot':
        if not slot_id:
            return None, 'single_slot target requires slot_id'
        if slot_id not in (state.get('slots', {}) or {}):
            return None, 'target.slot_id is unknown'
        return {'type': 'single_slot', 'slot_id': slot_id}, None

    if target_type in ['mass_individual', 'mass_summation']:
        return {'type': target_type, 'slot_id': None}, None

    if target_type == 'random_single':
        # ターゲットはまだ決定されていない。resolve時に resolve_random_intents() で確定される
        scope = str(normalized.get('random_target_scope') or 'enemy').strip()
        if scope not in ('enemy', 'ally', 'any'):
            scope = 'enemy'
        return {'type': 'random_single', 'slot_id': None, 'random_target_scope': scope}, None

    return None, 'invalid target.type'

def _extract_skill_tags(skill_id):
    if not skill_id:
        return []
    skill_data = all_skill_data.get(skill_id, {})
    tags = list(skill_data.get('tags', []))
    rule_data = _extract_skill_rule_data(skill_data)
    for t in rule_data.get('tags', []) if isinstance(rule_data, dict) else []:
        if t not in tags:
            tags.append(t)
    return tags

def _extract_skill_rule_data(skill_data):
    return _extract_rule_data_from_skill_v2(skill_data, raise_on_error=False)

def _coerce_mass_type(raw_value):
    text = str(raw_value or '').strip().lower()
    if not text:
        return None
    if text in ['mass_summation', 'summation', 'sum']:
        return 'mass_summation'
    if text in ['mass_individual', 'individual']:
        return 'mass_individual'
    return None

def _infer_mass_type_from_text(text):
    merged = str(text or '').lower()
    if not merged:
        return None

    if (
        'mass_summation' in merged
        or 'summation' in merged
        or 'sum' in merged
        or '合算' in merged
        or '総和' in merged
    ):
        return 'mass_summation'

    if (
        'mass_individual' in merged
        or 'individual' in merged
        or '個別' in merged
        or '単体' in merged
    ):
        return 'mass_individual'

    if '広域' in merged:
        return 'mass_individual'
    return None

def _infer_mass_type_from_skill(skill_id):
    if not skill_id:
        return None
    skill_data = all_skill_data.get(skill_id, {})
    if not isinstance(skill_data, dict):
        return None

    rule_data = _extract_skill_rule_data(skill_data)

    direct_candidates = [
        skill_data.get('mass_type'),
        skill_data.get('target_type'),
        skill_data.get('targeting'),
        skill_data.get('targetType'),
        rule_data.get('mass_type') if isinstance(rule_data, dict) else None,
        rule_data.get('target_type') if isinstance(rule_data, dict) else None,
        rule_data.get('targeting') if isinstance(rule_data, dict) else None,
        rule_data.get('targetType') if isinstance(rule_data, dict) else None,
    ]
    for raw in direct_candidates:
        coerced = _coerce_mass_type(raw)
        if coerced:
            return coerced

    merged_parts = []
    merged_parts.extend(_extract_skill_tags(skill_id))
    if isinstance(rule_data, dict):
        rule_tags = rule_data.get('tags', [])
        if isinstance(rule_tags, list):
            merged_parts.extend(rule_tags)

    for key in [
        'category',
        'distance',
        '分類',
        'カテゴリ',
        '射程',
        '距離',
        '対象',
        'target_scope',
        'target',
        'target_type',
        'targeting',
        'mass_type',
    ]:
        if isinstance(skill_data.get(key), str):
            merged_parts.append(skill_data.get(key))
        if isinstance(rule_data, dict) and isinstance(rule_data.get(key), str):
            merged_parts.append(rule_data.get(key))

    merged = ' '.join(str(v or '').lower() for v in merged_parts)
    return _infer_mass_type_from_text(merged)

def _normalize_target_scope(raw_value, default='enemy'):
    text = str(raw_value or '').strip().lower()
    if text in ['', 'default', 'auto']:
        return str(default or 'enemy')
    if text in ['self', 'self_only', 'caster', '自分', '自分対象', '自身', '自己対象']:
        return 'self'
    if text in [
        'enemy', 'enemies', 'foe', 'opponent', 'opponents',
        '敵', '敵側', 'opposing_team', '相手チーム', '相手チーム対象', '相手チーム指定'
    ]:
        return 'enemy'
    if text in [
        'ally', 'allies', 'friend', 'friends',
        '味方', '味方全員', '同じチーム', '同じチーム対象', '同じチーム指定', 'same_team'
    ]:
        return 'ally'
    if text in ['any', 'all', 'both', '全体', 'all_targets']:
        return 'any'
    return str(default or 'enemy')

def _infer_target_scope_from_skill(skill_id):
    if not skill_id:
        return 'enemy'
    skill_data = all_skill_data.get(skill_id, {})
    if not isinstance(skill_data, dict):
        return 'enemy'
    rule_data = _extract_skill_rule_data(skill_data)
    candidates = [
        skill_data.get('target_scope'),
        skill_data.get('targetScope'),
        skill_data.get('target_team'),
        skill_data.get('targetTeam'),
        rule_data.get('target_scope') if isinstance(rule_data, dict) else None,
        rule_data.get('targetScope') if isinstance(rule_data, dict) else None,
        rule_data.get('target_team') if isinstance(rule_data, dict) else None,
        rule_data.get('targetTeam') if isinstance(rule_data, dict) else None,
    ]
    for raw in candidates:
        if raw not in [None, '']:
            return _normalize_target_scope(raw, default='enemy')

    tags = []
    for raw_tag in _extract_skill_tags(skill_id):
        text = str(raw_tag or '').strip()
        if text:
            tags.append(text)
    normalized = {str(v).strip().lower() for v in tags}
    self_tags = {'self_target', 'target_self', '自分対象', '自身対象', '自己対象'}
    ally_tags = {'ally_target', 'target_ally', '味方対象', '味方指定', '同じチーム対象', '同じチーム指定', '同陣営対象', '同陣営指定'}
    any_tags = {'any_target', 'target_any', '全体対象', '対象自由'}
    enemy_tags = {'enemy_target', 'target_enemy', '敵対象', '相手チーム対象', '相手チーム指定'}
    if any(str(t).lower() in normalized for t in any_tags):
        return 'any'
    if any(str(t).lower() in normalized for t in self_tags):
        return 'self'
    if any(str(t).lower() in normalized for t in ally_tags):
        return 'ally'
    if any(str(t).lower() in normalized for t in enemy_tags):
        return 'enemy'
    return 'enemy'

def _resolve_slot_team(state, slot_id):
    if not isinstance(state, dict) or not slot_id:
        return None
    slots = state.get('slots', {}) or {}
    slot = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
    team = str(slot.get('team', '') or '').strip().lower()
    if team in ['ally', 'enemy']:
        return team

    actor_id = slot.get('actor_id')
    chars = state.get('characters', []) if isinstance(state.get('characters'), list) else []
    actor = next((c for c in chars if str(c.get('id')) == str(actor_id)), None)
    actor_team = str((actor or {}).get('type', '') or '').strip().lower()
    if actor_team in ['ally', 'enemy']:
        return actor_team
    return None

def _validate_single_target_scope(state, source_slot_id, target_slot_id, target_scope):
    scope = _normalize_target_scope(target_scope, default='enemy')
    if scope == 'any':
        return None
    if scope == 'self':
        if str(source_slot_id or '') != str(target_slot_id or ''):
            return 'target_scope=self のため自分スロットのみ指定できます'
        return None
    source_team = _resolve_slot_team(state, source_slot_id)
    target_team = _resolve_slot_team(state, target_slot_id)
    if source_team not in ['ally', 'enemy'] or target_team not in ['ally', 'enemy']:
        return None
    if scope == 'enemy' and source_team == target_team:
        return 'target_scope=enemy のため味方スロットは指定できません'
    if scope == 'ally' and source_team != target_team:
        return 'target_scope=ally のため敵スロットは指定できません'
    return None

def _normalize_target_by_skill(skill_id, target, state=None, source_slot_id=None, allow_none=True):
    normalized = _default_target(target)
    inferred_mass = _infer_mass_type_from_skill(skill_id)
    if inferred_mass in ['mass_individual', 'mass_summation']:
        return {'type': inferred_mass, 'slot_id': None}, None

    target_scope = _infer_target_scope_from_skill(skill_id)
    if target_scope == 'self':
        if not source_slot_id:
            return None, 'self target requires source slot'
        return {'type': 'single_slot', 'slot_id': source_slot_id}, None

    if normalized.get('type') in ['mass_individual', 'mass_summation']:
        return None, 'this skill does not support mass target'
    if normalized.get('type') == 'none':
        if allow_none:
            return {'type': 'none', 'slot_id': None}, None
        return None, 'target.type none is not allowed here'
    if normalized.get('type') == 'single_slot':
        slot_id = _normalize_target_slot_id(normalized.get('slot_id'))
        if not slot_id:
            return None, 'single_slot target requires slot_id'
        if state and source_slot_id:
            target_scope = _infer_target_scope_from_skill(skill_id)
            scope_error = _validate_single_target_scope(state, source_slot_id, slot_id, target_scope)
            if scope_error:
                return None, scope_error
        return {'type': 'single_slot', 'slot_id': slot_id}, None
    return None, 'invalid target.type'

def _normalize_target_by_skill_compat(skill_id, target, state=None, source_slot_id=None, allow_none=True):
    """
    Backward-compat for tests/patches that monkeypatch _normalize_target_by_skill
    with older signatures.
    """
    try:
        return _normalize_target_by_skill(
            skill_id,
            target,
            state=state,
            source_slot_id=source_slot_id,
            allow_none=allow_none
        )
    except TypeError as e:
        msg = str(e)
        if 'unexpected keyword argument' in msg:
            try:
                return _normalize_target_by_skill(skill_id, target, allow_none=allow_none)
            except TypeError:
                return _normalize_target_by_skill(skill_id, target)
        raise

def _build_tags(skill_id, target):
    skill_tags = _extract_skill_tags(skill_id)
    target_type = (target or {}).get('type')
    target_scope = _infer_target_scope_from_skill(skill_id)
    inferred_mass = _infer_mass_type_from_skill(skill_id)
    if inferred_mass in ['mass_individual', 'mass_summation']:
        mass_type = inferred_mass
    elif target_type in ['mass_individual', 'mass_summation']:
        mass_type = target_type
    else:
        mass_type = None
    tags_text = ' '.join(str(t or '').lower() for t in skill_tags)
    return {
        'instant': (
            'instant' in skill_tags
            or '即時' in tags_text
            or '即時発動' in tags_text
        ),
        'mass_type': mass_type,
        'no_redirect': (
            'no_redirect' in skill_tags
            or '対象変更不可' in tags_text
            or target_scope in ['ally', 'self']
        )
    }

def _extract_skill_cost_entries(skill_data):
    if not isinstance(skill_data, dict):
        return []
    direct = skill_data.get('cost')
    if isinstance(direct, list):
        return direct

    rule_data = _extract_skill_rule_data(skill_data)
    if isinstance(rule_data, dict) and isinstance(rule_data.get('cost'), list):
        return rule_data.get('cost', [])
    return []

def _resolve_actor_for_slot(state, slot_id, room_id=None, get_room_state_fn=None):
    if not isinstance(state, dict) or not slot_id:
        return None
    slot = (state.get('slots', {}) or {}).get(slot_id)
    if not isinstance(slot, dict):
        return None
    actor_id = slot.get('actor_id')
    if not actor_id:
        return None
    chars = state.get('characters', []) if isinstance(state.get('characters'), list) else []
    actor = next((c for c in chars if str(c.get('id')) == str(actor_id)), None)
    if actor:
        return actor

    fallback_room_id = room_id
    if not fallback_room_id:
        fallback_room_id = str(state.get('room_id') or state.get('room') or '').strip()
    if not fallback_room_id:
        return None
    room_state = get_room_state_fn(fallback_room_id) if callable(get_room_state_fn) else {}
    room_state = room_state or {}
    room_chars = room_state.get('characters', []) if isinstance(room_state.get('characters'), list) else []
    return next((c for c in room_chars if str(c.get('id')) == str(actor_id)), None)
