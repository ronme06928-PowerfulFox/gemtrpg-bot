import re

from manager.game_logic import get_status_value
from manager.battle.skill_rules import _resolve_skill_role, _estimate_immediate_self_fp_gain


def _sanitize_forced_no_match_clash_summary(summary):
    if not isinstance(summary, dict):
        return {}
    sanitized = dict(summary)
    sanitized['damage'] = []
    sanitized['statuses'] = []
    sanitized['flags'] = []
    return sanitized

def _should_grant_clash_win_fp(attacker_skill_data, defender_skill_data, clash_outcome):
    if clash_outcome not in {'attacker_win', 'defender_win'}:
        return False
    attacker_role = _resolve_skill_role(attacker_skill_data)
    defender_role = _resolve_skill_role(defender_skill_data)
    winner_role = attacker_role if clash_outcome == 'attacker_win' else defender_role
    if attacker_role == 'attack' and defender_role == 'attack':
        return True
    if attacker_role == 'defense' and defender_role == 'defense':
        return True
    if {attacker_role, defender_role} == {'attack', 'defense'} and winner_role == 'defense':
        return True
    if {attacker_role, defender_role} == {'attack', 'evade'} and winner_role == 'evade':
        return True
    return False

def _summary_has_positive_fp_gain(summary, target_id):
    if not isinstance(summary, dict):
        return False
    target_key = str(target_id)
    statuses = summary.get('statuses', [])
    if not isinstance(statuses, list):
        return False
    for row in statuses:
        if not isinstance(row, dict):
            continue
        if str(row.get('target_id')) != target_key:
            continue
        name = str(row.get('name') or '').strip().upper()
        if name != 'FP':
            continue
        before_v = row.get('before')
        after_v = row.get('after')
        delta_v = row.get('delta')
        try:
            delta = int(delta_v if delta_v is not None else (int(after_v or 0) - int(before_v or 0)))
        except Exception:
            delta = 0
        if delta > 0:
            return True
    return False

def _summary_fp_gain_total(summary, target_id):
    if not isinstance(summary, dict):
        return 0
    target_key = str(target_id)
    statuses = summary.get('statuses', [])
    if not isinstance(statuses, list):
        return 0
    total = 0
    for row in statuses:
        if not isinstance(row, dict):
            continue
        if str(row.get('target_id')) != target_key:
            continue
        name = str(row.get('name') or '').strip().upper()
        if name != 'FP':
            continue
        before_v = row.get('before')
        after_v = row.get('after')
        delta_v = row.get('delta')
        try:
            delta = int(delta_v if delta_v is not None else (int(after_v or 0) - int(before_v or 0)))
        except Exception:
            delta = 0
        if delta > 0:
            total += delta
    return total

def _summary_has_match_win_fp_gain(summary, target_id):
    if not isinstance(summary, dict):
        return False
    target_key = str(target_id)
    statuses = summary.get('statuses', [])
    if not isinstance(statuses, list):
        return False
    for row in statuses:
        if not isinstance(row, dict):
            continue
        if str(row.get('target_id')) != target_key:
            continue
        name = str(row.get('name') or '').strip().upper()
        if name != 'FP':
            continue
        source = str(row.get('source') or '').strip().lower()
        if source == 'match_win_fp':
            return True
    return False

def _iter_summary_log_lines(summary):
    if not isinstance(summary, dict):
        return []
    lines = []
    for key in ('legacy_log_lines', 'logs'):
        raw = summary.get(key, [])
        if not isinstance(raw, list):
            continue
        for row in raw:
            if row is None:
                continue
            text = str(row).strip()
            if text:
                lines.append(text)
    return lines

def _extract_fp_transition_delta_from_line(line, actor_name=None):
    if not isinstance(line, str):
        return None
    text = str(line).strip()
    if not text:
        return None
    if 'FP' not in text.upper():
        return None
    if actor_name:
        actor_text = str(actor_name).strip()
        if actor_text and (actor_text not in text):
            return None

    m = re.search(r"FP[^0-9\-]*(-?\d+)[^0-9\-]+(-?\d+)", text, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"FP\s*\((-?\d+)\)\D+\((-?\d+)\)", text, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        before = int(m.group(1))
        after = int(m.group(2))
    except Exception:
        return None
    return after - before

def _summary_logs_has_positive_fp_gain(summary, actor_name=None):
    for line in _iter_summary_log_lines(summary):
        delta = _extract_fp_transition_delta_from_line(line, actor_name=actor_name)
        if isinstance(delta, int) and delta > 0:
            return True
    return False

def _summary_logs_fp_gain_total(summary, actor_name=None):
    total = 0
    for line in _iter_summary_log_lines(summary):
        delta = _extract_fp_transition_delta_from_line(line, actor_name=actor_name)
        if isinstance(delta, int) and delta > 0:
            total += delta
    return total

def _summary_logs_has_match_win_fp_gain(summary, actor_name=None):
    for line in _iter_summary_log_lines(summary):
        if actor_name:
            actor_text = str(actor_name).strip()
            if actor_text and (actor_text not in line):
                continue
        lower = line.lower()
        delta = _extract_fp_transition_delta_from_line(line, actor_name=actor_name)
        if not (isinstance(delta, int) and delta > 0):
            continue
        # Legacy logs sometimes miss explicit "match_win" tokens but still
        # encode an FP transition line for the clash winner.
        if ('match_win' in lower) or ('マッチ勝利' in line) or ('match win' in lower):
            return True
        if ('fp (' in lower) and ('->' in lower):
            return True
    return False

def _set_actor_status_local(actor, stat_name, value):
    if not isinstance(actor, dict):
        return False
    name = str(stat_name or '').strip()
    if not name:
        return False
    ivalue = int(value or 0)
    upper = name.upper()
    if upper == 'HP':
        actor['hp'] = ivalue
        return True
    if upper == 'MP':
        actor['mp'] = ivalue
        return True

    states = actor.setdefault('states', [])
    if not isinstance(states, list):
        states = []
        actor['states'] = states
    for row in states:
        if not isinstance(row, dict):
            continue
        if str(row.get('name') or '') == name:
            row['value'] = ivalue
            return True
    states.append({'name': name, 'value': ivalue})
    return True

def _ensure_clash_winner_fp_gain(room, winner_char, clash_summary, winner_skill_data=None):
    if not isinstance(winner_char, dict):
        return None
    winner_id = winner_char.get('id')
    if not winner_id:
        return None
    winner_name = str(winner_char.get('name') or '').strip()
    if _summary_has_match_win_fp_gain(clash_summary, winner_id):
        return None
    if _summary_logs_has_match_win_fp_gain(clash_summary, actor_name=winner_name):
        return None

    observed_status_gain = _summary_fp_gain_total(clash_summary, winner_id)
    observed_log_gain = _summary_logs_fp_gain_total(clash_summary, actor_name=winner_name)
    observed_gain = max(int(observed_status_gain or 0), int(observed_log_gain or 0))
    expected_direct_gain = _estimate_immediate_self_fp_gain(winner_skill_data)

    # If observed gain already exceeds direct skill gain by at least +1,
    # the match-win FP has effectively been applied already.
    if observed_gain >= (expected_direct_gain + 1):
        return None

    before_fp = int(get_status_value(winner_char, 'FP') or 0)
    after_fp = before_fp + 1
    _set_actor_status_local(winner_char, 'FP', after_fp)
    return {
        'target_id': winner_id,
        'name': 'FP',
        'before': before_fp,
        'after': after_fp,
        'delta': 1,
        'source': 'match_win_fp',
    }

