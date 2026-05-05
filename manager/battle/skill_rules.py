import json
from manager.json_rule_v2 import extract_and_normalize_skill_rule_data, JsonRuleV2Error


def _extract_rule_data_from_skill(skill_data, *, raise_on_error=False, strict=True):
    try:
        skill_id = ""
        if isinstance(skill_data, dict):
            skill_id = str(skill_data.get("id", "") or "").strip()
        return extract_and_normalize_skill_rule_data(
            skill_data,
            skill_id=skill_id,
            strict=strict,
        )
    except JsonRuleV2Error:
        if raise_on_error:
            raise
        return {}
    except Exception:
        if raise_on_error:
            raise
        return {}


def _extract_skill_cost_entries(skill_data):
    if not isinstance(skill_data, dict):
        return []
    direct = skill_data.get('cost')
    if isinstance(direct, list):
        return direct
    rule_data = _extract_rule_data_from_skill(skill_data)
    rule_cost = rule_data.get('cost', [])
    if isinstance(rule_cost, list):
        return rule_cost
    return []

def _has_skill_tag(skill_data, tag_name):
    if not isinstance(skill_data, dict):
        return False
    tag = str(tag_name or "").strip()
    if not tag:
        return False

    tags = []
    rule_data = _extract_rule_data_from_skill(skill_data)
    if isinstance(rule_data, dict):
        raw_tags = rule_data.get('tags')
        if isinstance(raw_tags, list):
            tags.extend([str(v).strip() for v in raw_tags if str(v).strip()])

    skill_tags = skill_data.get('tags', [])
    if isinstance(skill_tags, list):
        tags.extend([str(v).strip() for v in skill_tags if str(v).strip()])

    return tag in tags


def _skill_deals_damage(skill_data):
    if not isinstance(skill_data, dict):
        return True
    direct = skill_data.get('deals_damage')
    if isinstance(direct, bool):
        return direct
    # Defense/evade-like skills are treated as non-damaging by default.
    try:
        resolved_role = _resolve_skill_role(skill_data)
    except Exception:
        resolved_role = None
    if resolved_role in {'defense', 'evade'}:
        return False

    rule_data = _extract_rule_data_from_skill(skill_data)
    if isinstance(rule_data, dict) and isinstance(rule_data.get('deals_damage'), bool):
        return bool(rule_data.get('deals_damage'))

    # role/category based fallback
    role_tokens = {'defense', 'evade'}
    role_values = []
    for key in ('category',):
        val = skill_data.get(key)
        if isinstance(val, str) and val.strip():
            role_values.append(val.strip())
        if isinstance(rule_data, dict):
            rule_val = rule_data.get(key)
            if isinstance(rule_val, str) and rule_val.strip():
                role_values.append(rule_val.strip())
    role_norm = {str(v).strip().lower() for v in role_values if str(v).strip()}
    if any(str(token).strip().lower() in role_norm for token in role_tokens):
        return False

    no_damage_tags = {
        '髱槭ム繝｡繝ｼ繧ｸ', '髱槭ム繝｡繝ｼ繧ｸ繧ｹ繧ｭ繝ｫ', 'no_damage', 'non_damage'
    }
    tags = []
    if isinstance(skill_data.get('tags'), list):
        tags.extend([str(v).strip() for v in skill_data.get('tags', []) if str(v).strip()])
    if isinstance(rule_data, dict) and isinstance(rule_data.get('tags'), list):
        tags.extend([str(v).strip() for v in rule_data.get('tags', []) if str(v).strip()])
    normalized = {str(v or '').strip().lower() for v in tags}
    if any(str(tag).strip().lower() in normalized for tag in no_damage_tags):
        return False
    return True


def _is_hard_skill(skill_data):
    for tag in ['蠑ｷ遑ｬ', '蠑ｷ遑ｬ繧ｹ繧ｭ繝ｫ', 'hard_skill']:
        if _has_skill_tag(skill_data, tag):
            return True
    return False


def _is_feint_skill(skill_data):
    for tag in ['迚ｽ蛻ｶ', '迚ｽ蛻ｶ繧ｹ繧ｭ繝ｫ', 'feint_skill']:
        if _has_skill_tag(skill_data, tag):
            return True
    return False


def _is_normal_skill(skill_data):
    return (not _is_hard_skill(skill_data)) and (not _is_feint_skill(skill_data))


def _collect_skill_tags(skill_data):
    tags = []
    if not isinstance(skill_data, dict):
        return tags
    direct_tags = skill_data.get('tags', [])
    if isinstance(direct_tags, list):
        tags.extend([str(v).strip() for v in direct_tags if str(v).strip()])
    rule_data = _extract_rule_data_from_skill(skill_data)
    if isinstance(rule_data, dict):
        rule_tags = rule_data.get('tags', [])
        if isinstance(rule_tags, list):
            tags.extend([str(v).strip() for v in rule_tags if str(v).strip()])
    return tags


def _resolve_skill_category(skill_data):
    if not isinstance(skill_data, dict):
        return ''
    for key in ('category',):
        value = skill_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    rule_data = _extract_rule_data_from_skill(skill_data)
    if isinstance(rule_data, dict):
        for key in ('category',):
            value = rule_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ''


def _normalize_target_scope(raw_value, default='enemy'):
    text = str(raw_value or '').strip().lower()
    if text in ['', 'default', 'auto']:
        return str(default or 'enemy')
    if text in ['self', 'self_only', 'caster', '自分', '自分対象', '自身', '自己対象']:
        return 'self'
    if text in [
        'enemy', 'enemies', 'foe', 'opponent', 'opponents',
        'opposing_team',
    ]:
        return 'enemy'
    if text in [
        'ally', 'allies', 'friend', 'friends',
        'same_team',
    ]:
        return 'ally'
    if text in ['any', 'all', 'both', 'all_targets']:
        return 'any'
    return str(default or 'enemy')


def _infer_target_scope_from_skill_data(skill_data):
    if not isinstance(skill_data, dict):
        return 'enemy'
    rule_data = _extract_rule_data_from_skill(skill_data)
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

    normalized_tags = {str(v or '').strip().lower() for v in _collect_skill_tags(skill_data)}
    self_tags = {'self_target', 'target_self', '自分対象', '自身対象', '自己対象'}
    ally_tags = {'ally_target', 'target_ally'}
    any_tags = {'any_target', 'target_any'}
    enemy_tags = {'enemy_target', 'target_enemy'}
    if any(tag.lower() in normalized_tags for tag in any_tags):
        return 'any'
    if any(tag.lower() in normalized_tags for tag in self_tags):
        return 'self'
    if any(tag.lower() in normalized_tags for tag in ally_tags):
        return 'ally'
    if any(tag.lower() in normalized_tags for tag in enemy_tags):
        return 'enemy'
    return 'enemy'


def _is_ally_target_skill_data(skill_data):
    return _infer_target_scope_from_skill_data(skill_data) == 'ally'


def _canonical_slot_team(team_value):
    text = str(team_value or '').strip().lower()
    if text in ['ally', 'player', 'friend', 'friends']:
        return 'ally'
    if text in ['enemy', 'foe', 'opponent', 'boss', 'npc']:
        return 'enemy'
    return None


def _is_same_team_slot_pair(slots, slot_a, slot_b):
    if not isinstance(slots, dict):
        return False
    team_a = _canonical_slot_team((slots.get(slot_a) or {}).get('team'))
    team_b = _canonical_slot_team((slots.get(slot_b) or {}).get('team'))
    return bool(team_a and team_b and team_a == team_b)


def _is_non_clashable_ally_support_pair(slots, slot_a, slot_b, skill_data_a=None, skill_data_b=None):
    if not _is_same_team_slot_pair(slots, slot_a, slot_b):
        return False
    if _is_ally_target_skill_data(skill_data_a):
        return True
    if _is_ally_target_skill_data(skill_data_b):
        return True
    return False


def _resolve_skill_role(skill_data):
    category = _resolve_skill_category(skill_data)
    tags = _collect_skill_tags(skill_data)
    lower_tags = [str(v or '').strip().lower() for v in tags]

    if category == '蝗樣∩':
        return 'evade'
    if any(('蝗樣∩' in t) for t in tags):
        return 'evade'
    if any(('evade' in t) for t in lower_tags):
        return 'evade'

    if category == '髦ｲ蠕｡':
        return 'defense'
    if any(('髦ｲ蠕｡' in t or '螳亥ｙ' in t) for t in tags):
        return 'defense'
    if any(('defense' in t) for t in lower_tags):
        return 'defense'

    return 'attack'


def _get_forced_clash_no_effect_reason(attacker_skill_data, defender_skill_data):
    attacker_role = _resolve_skill_role(attacker_skill_data)
    defender_role = _resolve_skill_role(defender_skill_data)
    roles = {attacker_role, defender_role}
    if roles == {'defense', 'evade'}:
        return 'defense_evade_no_match'
    if attacker_role == 'evade' and defender_role == 'evade':
        return 'evade_evade_no_match'
    return None


def _get_inherent_skill_cancel_reason(attacker_skill_data, defender_skill_data):
    attacker_role = _resolve_skill_role(attacker_skill_data)
    defender_role = _resolve_skill_role(defender_skill_data)
    roles = {attacker_role, defender_role}
    if roles == {'defense', 'evade'}:
        return 'defense_evade_fizzle'
    if attacker_role == 'evade' and defender_role == 'evade':
        return 'evade_evade_fizzle'
    return None

def _normalize_effect_timing(value):
    return str(value or '').strip().upper()


def _effect_targets_self(effect):
    if not isinstance(effect, dict):
        return False
    target = str(effect.get('target') or '').strip().lower()
    if target in ['', 'self', 'source', 'actor', 'caster', 'owner']:
        return True
    return False


def _estimate_immediate_self_fp_gain(skill_data):
    """
    Estimate immediate self FP gain that can occur during clash execution.
    This intentionally ignores END_ROUND style delayed effects.
    """
    rule_data = _extract_rule_data_from_skill(skill_data)
    if not isinstance(rule_data, dict):
        return 0
    effects = rule_data.get('effects', [])
    if not isinstance(effects, list):
        return 0

    # Timings that can contribute FP before/within duel resolution.
    immediate_timings = {'PRE_MATCH', 'WIN', 'HIT', 'UNOPPOSED'}
    total = 0
    for effect in effects:
        if not isinstance(effect, dict):
            continue
        if str(effect.get('type') or '').strip().upper() != 'APPLY_STATE':
            continue
        state_name = str(effect.get('state_name') or effect.get('name') or '').strip().upper()
        if state_name != 'FP':
            continue
        if not _effect_targets_self(effect):
            continue
        if _normalize_effect_timing(effect.get('timing')) not in immediate_timings:
            continue
        try:
            value = int(effect.get('value', 0))
        except Exception:
            value = 0
        if value > 0:
            total += value
    return total


def _skill_has_direct_fp_gain(skill_data):
    return _estimate_immediate_self_fp_gain(skill_data) > 0


