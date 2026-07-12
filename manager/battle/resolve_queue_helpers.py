import random as _random_module

from extensions import all_skill_data
from manager.battle.timeline_helpers import _is_actor_placed
from manager.battle.skill_rules import _is_non_clashable_ally_support_pair


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default

def resolve_random_intents(state, battle_state, intents):
    """
    target.type == 'random_single' のインテントに対して、ランダムにターゲットスロットを選び
    type を 'single_slot' に書き換える。_build_resolve_queues の直前に呼ぶこと。

    - random_target_scope == 'enemy'  : 攻撃側と反対チームの生存済み配置スロットから選ぶ
    - random_target_scope == 'ally'   : 攻撃側と同チームの生存済み配置スロットから選ぶ
    - random_target_scope == 'any'    : チーム不問で生存済み配置スロットから選ぶ（自スロット除く）
    """
    if not isinstance(intents, dict):
        return
    slots = battle_state.get('slots', {}) if isinstance(battle_state, dict) else {}
    characters = state.get('characters', []) if isinstance(state, dict) else []

    # actor_id → character オブジェクトの辞書を作る
    char_by_id = {str(c.get('id')): c for c in characters if isinstance(c, dict) and c.get('id')}

    for slot_id, intent in intents.items():
        if not isinstance(intent, dict):
            continue
        target = intent.get('target', {}) or {}
        if not isinstance(target, dict):
            continue
        if target.get('type') != 'random_single':
            continue

        scope = str(target.get('random_target_scope') or 'enemy').strip()
        attacker_slot_data = slots.get(slot_id) or {}
        attacker_actor_id = str(attacker_slot_data.get('actor_id') or '')
        attacker_team = str(attacker_slot_data.get('team') or '')

        # 候補スロット: 配置済み・生存中のスロット
        candidate_slot_ids = []
        for sid, sdata in slots.items():
            if not isinstance(sdata, dict):
                continue
            if sdata.get('disabled', False):
                continue
            candidate_actor_id = str(sdata.get('actor_id') or '')
            if not candidate_actor_id:
                continue
            # 自スロットは除外
            if sid == slot_id:
                continue
            # 生存・配置チェック
            if not _is_actor_placed(state, candidate_actor_id):
                continue
            candidate_team = str(sdata.get('team') or '')
            # スコープでフィルタ
            if scope == 'enemy':
                if attacker_team and candidate_team == attacker_team:
                    continue
            elif scope == 'ally':
                if attacker_team and candidate_team != attacker_team:
                    continue
            # 'any' はフィルタなし
            candidate_slot_ids.append(sid)

        if not candidate_slot_ids:
            # 候補なし → ターゲットなしに変更
            intent['target'] = {'type': 'none', 'slot_id': None}
            continue

        chosen_slot = _random_module.choice(candidate_slot_ids)
        intent['target'] = {'type': 'single_slot', 'slot_id': chosen_slot}


def _build_resolve_queues(battle_state, intents_override=None):
    timeline = battle_state.get('timeline', [])
    slots = battle_state.get('slots', {})
    intents = intents_override if isinstance(intents_override, dict) else battle_state.get('intents', {})
    ordered_slots = []
    seen_slots = set()
    if isinstance(timeline, list):
        for slot_id in timeline:
            if slot_id in slots and slot_id not in seen_slots:
                ordered_slots.append(slot_id)
                seen_slots.add(slot_id)

    # Fallback for stale/missing timeline entries: append remaining slots by initiative desc.
    remaining_slots = [sid for sid in slots.keys() if sid not in seen_slots]
    remaining_slots.sort(
        key=lambda sid: (
            -int((slots.get(sid) or {}).get('initiative', 0)),
            str(sid)
        )
    )
    ordered_slots.extend(remaining_slots)

    mass_slots = []
    for slot_id in ordered_slots:
        slot = slots.get(slot_id) or {}
        if slot.get('disabled', False):
            continue
        intent = intents.get(slot_id, {})
        tags = intent.get('tags', {})
        mass_type = tags.get('mass_type')
        if mass_type in ['individual', 'summation', 'mass_individual', 'mass_summation']:
            mass_slots.append(slot_id)

    single_slots = []
    for slot_id in ordered_slots:
        slot = slots.get(slot_id) or {}
        if slot.get('disabled', False):
            continue
        intent = intents.get(slot_id, {})
        tags = intent.get('tags', {})
        mass_type = tags.get('mass_type')
        is_mass = mass_type in ['individual', 'summation', 'mass_individual', 'mass_summation']
        if is_mass:
            continue
        if tags.get('instant', False):
            continue
        single_slots.append(slot_id)

    battle_state['resolve']['mass_queue'] = mass_slots
    battle_state['resolve']['single_queue'] = single_slots

def _enemy_actor_ids_for_team(state, attacker_team):
    enemies = []
    for actor in state.get('characters', []):
        actor_id = actor.get('id')
        if not actor_id:
            continue
        if attacker_team and actor.get('type') == attacker_team:
            continue
        if not _is_actor_placed(state, actor_id):
            continue
        enemies.append(actor_id)
    return enemies

def _estimate_mass_trace_steps(state, battle_state, intents):
    resolve = battle_state.get('resolve', {}) if isinstance(battle_state, dict) else {}
    slots = battle_state.get('slots', {}) if isinstance(battle_state, dict) else {}
    mass_queue = resolve.get('mass_queue', []) or []
    total = 0
    for slot_id in mass_queue:
        slot_data = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
        attacker_actor_id = slot_data.get('actor_id')
        if not attacker_actor_id or not _is_actor_placed(state, attacker_actor_id):
            total += 1
            continue
        intent = intents.get(slot_id, {}) if isinstance(intents, dict) else {}
        tags = intent.get('tags', {}) if isinstance(intent, dict) else {}
        mass_type = tags.get('mass_type')
        if mass_type in ['summation', 'mass_summation']:
            total += 1
            continue
        attacker_team = slot_data.get('team')
        total += len(_enemy_actor_ids_for_team(state, attacker_team))
    return int(max(0, total))

def _intent_single_target_slot(intent):
    if not isinstance(intent, dict):
        return None
    target = intent.get('target', {}) or {}
    if target.get('type') != 'single_slot':
        return None
    slot_id = target.get('slot_id')
    return str(slot_id) if slot_id else None

def _compute_single_contention(intents, single_queue):
    target_claims = {}
    for slot_id in single_queue:
        intent = intents.get(slot_id, {}) if isinstance(intents, dict) else {}
        if not isinstance(intent, dict):
            continue
        target_slot = _intent_single_target_slot(intent)
        if not target_slot:
            continue
        if not intent.get('committed', False):
            continue
        if not intent.get('skill_id'):
            continue
        target_claims.setdefault(target_slot, []).append((
            slot_id,
            _safe_int(intent.get('committed_at'), 0),
            _safe_int(intent.get('intent_rev'), 0),
        ))

    contention_winner_by_target = {}
    contested_losers = set()
    for target_slot, claims in target_claims.items():
        if not claims:
            continue
        target_intent = intents.get(target_slot, {}) if isinstance(intents, dict) else {}
        if (
            isinstance(target_intent, dict)
            and target_intent.get('committed', False)
            and target_intent.get('skill_id')
        ):
            reciprocal_slot = _intent_single_target_slot(target_intent)
        else:
            reciprocal_slot = None
        preferred_claims = [claim for claim in claims if claim[0] == reciprocal_slot]
        candidate_claims = preferred_claims if preferred_claims else claims
        winner = max(candidate_claims, key=lambda row: (row[1], row[2], str(row[0])))
        contention_winner_by_target[target_slot] = winner[0]
        if len(claims) > 1:
            for claim in claims:
                if claim[0] != winner[0]:
                    contested_losers.add(claim[0])

    return {
        'target_claims': target_claims,
        'contention_winner_by_target': contention_winner_by_target,
        'contested_losers': contested_losers,
    }

def _estimate_single_trace_steps(state, battle_state, intents):
    resolve = battle_state.get('resolve', {}) if isinstance(battle_state, dict) else {}
    slots = battle_state.get('slots', {}) if isinstance(battle_state, dict) else {}
    single_queue = resolve.get('single_queue', []) or []
    processed = set()
    total = 0

    contention = _compute_single_contention(intents, single_queue)
    contested_losers = set(contention.get('contested_losers', set()) or set())

    for slot_id in single_queue:
        if slot_id in processed:
            continue
        intent_a = intents.get(slot_id, {}) if isinstance(intents, dict) else {}
        skill_id = intent_a.get('skill_id') if isinstance(intent_a, dict) else None
        if not intent_a or not skill_id:
            total += 1
            processed.add(slot_id)
            continue

        target = intent_a.get('target', {}) if isinstance(intent_a, dict) else {}
        target_slot = target.get('slot_id') if isinstance(target, dict) else None
        if target.get('type') != 'single_slot' or not target_slot:
            total += 1
            processed.add(slot_id)
            continue

        target_actor_id = (slots.get(target_slot, {}) or {}).get('actor_id') if isinstance(slots, dict) else None
        if not target_actor_id or not _is_actor_placed(state, target_actor_id):
            total += 1
            processed.add(slot_id)
            continue

        attacker_is_contested_loser = slot_id in contested_losers
        intent_b = intents.get(target_slot, {}) if isinstance(intents, dict) else {}
        defender_skill_id = intent_b.get('skill_id') if isinstance(intent_b, dict) else None
        defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id else None
        non_clashable_ally_support = _is_non_clashable_ally_support_pair(
            slots,
            slot_id,
            target_slot,
            all_skill_data.get(skill_id, {}) if skill_id else None,
            defender_skill_data,
        )
        is_clash = (
            not attacker_is_contested_loser
            and isinstance(intent_b, dict)
            and intent_b.get('committed', False)
            and defender_skill_id
            and intent_b.get('target', {}).get('type') == 'single_slot'
            and intent_b.get('target', {}).get('slot_id') == slot_id
            and target_slot not in processed
            and (not non_clashable_ally_support)
        )
        if is_clash:
            total += 1
            processed.add(slot_id)
            processed.add(target_slot)
        else:
            total += 1
            processed.add(slot_id)

    return int(max(0, total))

def _consume_resolve_slot(battle_state, slot_id):
    if not isinstance(battle_state, dict) or not slot_id:
        return
    slots = battle_state.get('slots', {})
    slot_data = slots.get(slot_id)
    if isinstance(slot_data, dict):
        slot_data['disabled'] = True
        slot_data['status'] = 'consumed'
    resolve = battle_state.setdefault('resolve', {})
    resolved_slots = resolve.get('resolved_slots', [])
    if slot_id not in resolved_slots:
        resolved_slots.append(slot_id)
        resolve['resolved_slots'] = resolved_slots

def _compare_outcome(attacker_power, defender_power):
    if attacker_power > defender_power:
        return 'attacker_win'
    if attacker_power < defender_power:
        return 'defender_win'
    return 'draw'

def _gather_slots_targeting_slot_s(state, battle_state, slot_s, attacker_team=None, intents_override=None):
    intents = intents_override if isinstance(intents_override, dict) else battle_state.get('intents', {})
    slots = battle_state.get('slots', {})
    candidates = []

    for slot_id, intent in intents.items():
        if not intent.get('committed', False):
            continue
        if intent.get('tags', {}).get('instant', False):
            continue
        target = intent.get('target', {})
        if target.get('type') != 'single_slot':
            continue
        if target.get('slot_id') != slot_s:
            continue
        slot_data = slots.get(slot_id)
        if not slot_data:
            continue
        if attacker_team and slot_data.get('team') == attacker_team:
            continue
        actor_id = slot_data.get('actor_id')
        if not actor_id:
            continue
        if not _is_actor_placed(state, actor_id):
            continue
        candidates.append((slot_id, actor_id, int(slot_data.get('initiative', 0))))

    best_by_actor = {}
    for slot_id, actor_id, initiative in candidates:
        prev = best_by_actor.get(actor_id)
        if (
            prev is None
            or initiative > prev[2]
            or (initiative == prev[2] and slot_id < prev[0])
        ):
            best_by_actor[actor_id] = (slot_id, actor_id, initiative)

    return [v[0] for v in best_by_actor.values()]

