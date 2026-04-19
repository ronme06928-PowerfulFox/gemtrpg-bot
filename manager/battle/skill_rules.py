import json


def _extract_rule_data_from_skill(skill_data):
    if not isinstance(skill_data, dict):
        return {}

    for key in ['rule_data', 'rule_json', 'rule', '特記処理']:
        raw = skill_data.get(key)
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            text = raw.strip()
            if not text.startswith('{'):
                continue
            try:
                parsed = json.loads(text)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed

    direct = skill_data.get('rule_data')
    if isinstance(direct, dict):
        return direct

    for raw in skill_data.values():
        if not isinstance(raw, str):
            continue
        raw = raw.strip()
        if not raw.startswith('{'):
            continue
        if (
            ('"effects"' not in raw)
            and ('"cost"' not in raw)
            and ('"tags"' not in raw)
            and ('"deals_damage"' not in raw)
            and ('"target_scope"' not in raw)
            and ('"target_team"' not in raw)
        ):
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
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
    # 防御/回避スキルは一方攻撃でもダメージを発生させない。
    try:
        resolved_role = _resolve_skill_role(skill_data)
    except Exception:
        resolved_role = None
    if resolved_role in {'defense', 'evade'}:
        return False

    rule_data = _extract_rule_data_from_skill(skill_data)
    if isinstance(rule_data, dict) and isinstance(rule_data.get('deals_damage'), bool):
        return bool(rule_data.get('deals_damage'))

    # 分類フィールドの揺れ（日本語/英語）をフォールバックで吸収
    role_tokens = {'defense', 'evade', '防御', '回避', '守備'}
    role_values = []
    for key in ('category', '分類'):
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
        '非ダメージ', '非ダメージスキル', 'no_damage', 'non_damage'
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
    for tag in ['強硬', '強硬スキル', 'hard_skill']:
        if _has_skill_tag(skill_data, tag):
            return True
    return False


def _is_feint_skill(skill_data):
    for tag in ['牽制', '牽制スキル', 'feint_skill']:
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
    for key in ('分類', 'category'):
        value = skill_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    rule_data = _extract_rule_data_from_skill(skill_data)
    if isinstance(rule_data, dict):
        for key in ('分類', 'category'):
            value = rule_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ''


def _normalize_target_scope(raw_value, default='enemy'):
    text = str(raw_value or '').strip().lower()
    if text in ['', 'default', 'auto']:
        return str(default or 'enemy')
    if text in [
        'enemy', 'enemies', 'foe', 'opponent', 'opponents',
        '敵', '敵対象', 'opposing_team', '相手陣営', '相手陣営対象', '相手陣営指定'
    ]:
        return 'enemy'
    if text in [
        'ally', 'allies', 'friend', 'friends',
        '味方', '味方対象', '味方指定', '同陣営', '同陣営対象', '同陣営指定', 'same_team'
    ]:
        return 'ally'
    if text in ['any', 'all', 'both', '任意', '対象自由', 'all_targets']:
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
    ally_tags = {'ally_target', 'target_ally', '味方対象', '味方指定', '同陣営', '同陣営対象', '同陣営指定'}
    any_tags = {'any_target', 'target_any', '任意対象', '対象自由'}
    enemy_tags = {'enemy_target', 'target_enemy', '敵対象', '相手陣営対象', '相手陣営指定'}
    if any(tag.lower() in normalized_tags for tag in any_tags):
        return 'any'
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

    if category == '回避':
        return 'evade'
    if any(('回避' in t) for t in tags):
        return 'evade'
    if any(('evade' in t) for t in lower_tags):
        return 'evade'

    if category == '防御':
        return 'defense'
    if any(('防御' in t or '守備' in t) for t in tags):
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

