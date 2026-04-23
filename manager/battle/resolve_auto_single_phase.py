def _sync_from_core():
    from manager.battle import core as core_mod
    g = globals()
    # Mirror symbols from core so monkeypatches in tests remain effective.
    for name, value in core_mod.__dict__.items():
        if name.startswith("__"):
            continue
        g[name] = value


from manager.battle.system_skills import (
    consume_auto_defense_charge,
    get_system_skill,
    grant_auto_defense_charge,
    is_auto_defense_skill_data,
    queue_selected_power_recovery_from_snapshot,
)


def run_single_phase(room, battle_id, state, battle_state, resolve_intents, characters_by_id):
    _sync_from_core()
    from manager.battle.common_manager import (
        build_select_resolve_state_payload,
        select_evade_insert_slot,
        select_hard_followup_evade_slot,
    )

    if battle_state.get('phase') == 'resolve_single':
        intents = resolve_intents
        slots = battle_state.get('slots', {})
        processed_slots = set()
        single_queue = battle_state['resolve'].get('single_queue', []) or []

        # Contention rule:
        # if multiple attackers target the same defender slot, keep one
        # reciprocal clash candidate and downgrade the rest to one-sided.
        contention = _compute_single_contention(intents, single_queue)
        contention_winner_by_target = dict(contention.get('contention_winner_by_target', {}) or {})
        contested_losers = set(contention.get('contested_losers', set()) or set())

        if contested_losers:
            logger.info(
                "[resolve_single_contention] losers=%s winners=%s",
                sorted(contested_losers),
                contention_winner_by_target
            )

        queue_kind_counts = {'clash': 0, 'one_sided': 0, 'fizzle': 0}
        queue_pairs = []
        for q_slot_id in single_queue:
            q_intent_a = intents.get(q_slot_id, {})
            q_skill_id = q_intent_a.get('skill_id')
            q_target = q_intent_a.get('target', {})
            q_target_slot = q_target.get('slot_id')
            q_kind = 'one_sided'

            if not q_intent_a or not q_skill_id:
                q_kind = 'fizzle'
            elif q_target.get('type') != 'single_slot' or not q_target_slot:
                q_kind = 'fizzle'
            else:
                q_target_actor_id = slots.get(q_target_slot, {}).get('actor_id')
                if not q_target_actor_id or not _is_actor_placed(state, q_target_actor_id):
                    q_kind = 'fizzle'
                else:
                    q_intent_b = intents.get(q_target_slot, {})
                    q_def_skill_id = q_intent_b.get('skill_id') if isinstance(q_intent_b, dict) else None
                    q_def_skill_data = all_skill_data.get(q_def_skill_id, {}) if q_def_skill_id else None
                    non_clashable_ally_support = _is_non_clashable_ally_support_pair(
                        slots,
                        q_slot_id,
                        q_target_slot,
                        all_skill_data.get(q_skill_id, {}) if q_skill_id else None,
                        q_def_skill_data,
                    )
                    if (
                        q_slot_id not in contested_losers
                        and
                        q_intent_b.get('target', {}).get('type') == 'single_slot'
                        and q_intent_b.get('target', {}).get('slot_id') == q_slot_id
                        and (not non_clashable_ally_support)
                    ):
                        q_kind = 'clash'

            queue_kind_counts[q_kind] = int(queue_kind_counts.get(q_kind, 0)) + 1
            if len(queue_pairs) < 8:
                queue_pairs.append(f"{q_slot_id}->{q_target_slot or 'none'}")

        logger.info(
            "[resolve_single_queue] total=%d clash=%d one_sided=%d fizzle=%d pairs=%s",
            len(single_queue),
            queue_kind_counts.get('clash', 0),
            queue_kind_counts.get('one_sided', 0),
            queue_kind_counts.get('fizzle', 0),
            queue_pairs
        )

        def _mark_processed(slot_key, cancelled_without_use=False):
            if not slot_key:
                return
            if slot_key in processed_slots:
                if cancelled_without_use:
                    _mark_slot_cancelled_without_use(battle_state, slot_key)
                return
            processed_slots.add(slot_key)
            slot_data = slots.get(slot_key)
            if isinstance(slot_data, dict):
                slot_data['disabled'] = True
                slot_data['status'] = 'consumed'
                if cancelled_without_use:
                    slot_data['cancelled_without_use'] = True
            resolved_slots = battle_state['resolve'].get('resolved_slots', [])
            if slot_key not in resolved_slots:
                resolved_slots.append(slot_key)
                battle_state['resolve']['resolved_slots'] = resolved_slots
            if cancelled_without_use:
                _mark_slot_cancelled_without_use(battle_state, slot_key)

        def _actor_name_from_slot(slot_key):
            actor_id = slots.get(slot_key, {}).get('actor_id') if slot_key else None
            return _resolve_actor_name(characters_by_id, actor_id), actor_id

        def _resolve_reuse_display_label(slot_key):
            intent = intents.get(slot_key, {}) if slot_key else {}
            if not isinstance(intent, dict):
                return None
            if not intent.get('reuse_virtual', False):
                return None
            origin_label = str(intent.get('reuse_origin_label') or '').strip()
            depth = _safe_int(intent.get('reuse_depth', 0), 0)
            if depth <= 0:
                depth = 1
            suffix = 'EX' if depth == 1 else f'EX{depth}'
            if origin_label:
                return f"{origin_label}-{suffix}"
            return suffix

        def _collect_reuse_policy(delegate_summary):
            if not isinstance(delegate_summary, dict):
                return {'enabled': False, 'max_reuses': 0, 'consume_cost': False, 'reuse_cost': []}
            requests = delegate_summary.get('reuse_requests', [])
            if not isinstance(requests, list):
                return {'enabled': False, 'max_reuses': 0, 'consume_cost': False, 'reuse_cost': []}

            max_reuses = 0
            consume_cost = False
            reuse_cost = []
            for req in requests:
                if not isinstance(req, dict):
                    continue
                req_max = _safe_int(req.get('max_reuses', 1), 1)
                if req_max > max_reuses:
                    max_reuses = req_max
                consume_cost = consume_cost or bool(req.get('consume_cost', False))
                if (not reuse_cost) and isinstance(req.get('reuse_cost'), list):
                    normalized = []
                    for entry in req.get('reuse_cost', []):
                        if not isinstance(entry, dict):
                            continue
                        c_type = str(entry.get('type', '')).strip()
                        c_val = _safe_int(entry.get('value', 0), 0)
                        if not c_type or c_val <= 0:
                            continue
                        normalized.append({'type': c_type, 'value': c_val})
                    if normalized:
                        reuse_cost = normalized

            if max_reuses <= 0:
                return {'enabled': False, 'max_reuses': 0, 'consume_cost': consume_cost, 'reuse_cost': reuse_cost}
            return {
                'enabled': True,
                'max_reuses': min(int(max_reuses), int(MAX_USE_SKILL_AGAIN_CHAIN_HARD_CAP)),
                'consume_cost': bool(consume_cost),
                'reuse_cost': reuse_cost,
            }

        def _extract_reuse_requests_from_changes(changes):
            requests = []
            for row in (changes or []):
                if not isinstance(row, (list, tuple)) or len(row) < 4:
                    continue
                target_obj, effect_type, _name, payload = row
                if effect_type not in {'USE_SKILL_AGAIN', 'APPLY_SKILL_DAMAGE_AGAIN'}:
                    continue
                value = payload if isinstance(payload, dict) else {}
                default_reuses = 1
                if effect_type == 'APPLY_SKILL_DAMAGE_AGAIN':
                    # Backward-compat: old tag is treated as single re-use request in select/resolve.
                    default_reuses = 1
                req = {
                    'max_reuses': max(1, _safe_int(value.get('max_reuses', default_reuses), default_reuses)),
                    'consume_cost': bool(value.get('consume_cost', False)),
                }
                raw_reuse_cost = value.get('reuse_cost', [])
                if isinstance(raw_reuse_cost, dict):
                    raw_reuse_cost = [raw_reuse_cost]
                if isinstance(raw_reuse_cost, list):
                    normalized = []
                    for entry in raw_reuse_cost:
                        if not isinstance(entry, dict):
                            continue
                        c_type = str(entry.get('type', '')).strip()
                        c_val = _safe_int(entry.get('value', 0), 0)
                        if not c_type or c_val <= 0:
                            continue
                        normalized.append({'type': c_type, 'value': c_val})
                    if normalized:
                        req['reuse_cost'] = normalized
                if isinstance(target_obj, dict) and target_obj.get('id'):
                    req['target_id'] = target_obj.get('id')
                requests.append(req)
            return requests

        def _schedule_single_reuse_slot(current_slot_id, queue_index, intent_obj, policy, origin_label):
            if not isinstance(intent_obj, dict):
                return None
            if not isinstance(policy, dict) or not policy.get('enabled', False):
                return None

            max_reuses = _safe_int(policy.get('max_reuses', 0), 0)
            if max_reuses <= 0:
                return None

            origin_slot = str(intent_obj.get('reuse_origin_slot') or current_slot_id)
            carried_origin_label = str(intent_obj.get('reuse_origin_label') or origin_label or '').strip()
            current_depth = _safe_int(intent_obj.get('reuse_depth', 0), 0)
            existing_limit = _safe_int(intent_obj.get('reuse_chain_limit', 0), 0)
            chain_limit = min(
                int(MAX_USE_SKILL_AGAIN_CHAIN_HARD_CAP),
                max(int(max_reuses), int(existing_limit))
            )
            next_depth = current_depth + 1
            if next_depth > chain_limit:
                return None

            target = intent_obj.get('target', {}) if isinstance(intent_obj.get('target'), dict) else {}
            target_type = target.get('type')
            target_slot_id = target.get('slot_id')
            if target_type != 'single_slot' or not target_slot_id:
                return None

            base_slot = slots.get(current_slot_id, {}) if isinstance(slots, dict) else {}
            if not isinstance(base_slot, dict):
                return None

            # Optional per-reuse cost: if unaffordable, skip scheduling this reuse.
            raw_reuse_cost = policy.get('reuse_cost', [])
            if isinstance(raw_reuse_cost, dict):
                raw_reuse_cost = [raw_reuse_cost]
            reuse_cost = []
            if isinstance(raw_reuse_cost, list):
                for entry in raw_reuse_cost:
                    if not isinstance(entry, dict):
                        continue
                    c_type = str(entry.get('type', '')).strip()
                    c_val = _safe_int(entry.get('value', 0), 0)
                    if not c_type or c_val <= 0:
                        continue
                    reuse_cost.append({'type': c_type, 'value': c_val})

            if reuse_cost:
                actor_id = intent_obj.get('actor_id') or base_slot.get('actor_id')
                actor = characters_by_id.get(actor_id) if actor_id else None
                if not isinstance(actor, dict):
                    return None
                affordable = True
                for c in reuse_cost:
                    current_val = _safe_int(get_status_value(actor, c.get('type')), 0)
                    if current_val < _safe_int(c.get('value', 0), 0):
                        affordable = False
                        break
                if not affordable:
                    logger.info(
                        "[reuse_schedule_skip] slot=%s actor=%s reason=insufficient_reuse_cost required=%s",
                        current_slot_id,
                        actor_id,
                        reuse_cost
                    )
                    return None
                for c in reuse_cost:
                    c_type = str(c.get('type'))
                    spend = _safe_int(c.get('value', 0), 0)
                    current_val = _safe_int(get_status_value(actor, c_type), 0)
                    _update_char_stat(
                        room,
                        actor,
                        c_type,
                        max(0, int(current_val) - int(spend)),
                        username="[蜀堺ｽｿ逕ｨ繧ｳ繧ｹ繝・"
                    )

            base_id = f"{origin_slot}__EX{next_depth}"
            next_slot_id = base_id
            suffix = 2
            while next_slot_id in slots:
                next_slot_id = f"{base_id}_{suffix}"
                suffix += 1

            next_slot = dict(base_slot)
            next_slot['slot_id'] = next_slot_id
            next_slot['disabled'] = False
            next_slot['status'] = 'queued_reuse'
            next_slot['virtual_reuse'] = True
            next_slot['reuse_origin_slot'] = origin_slot
            next_slot['reuse_depth'] = next_depth
            slots[next_slot_id] = next_slot

            next_intent = {
                'slot_id': next_slot_id,
                'actor_id': intent_obj.get('actor_id'),
                'skill_id': intent_obj.get('skill_id'),
                'target': {'type': 'single_slot', 'slot_id': target_slot_id},
                'tags': dict(intent_obj.get('tags', {}) if isinstance(intent_obj.get('tags'), dict) else {}),
                'committed': True,
                'committed_at': _resolve_server_ts(),
                'intent_rev': _safe_int(intent_obj.get('intent_rev', 0), 0) + 1,
                'reuse_virtual': True,
                'reuse_origin_slot': origin_slot,
                'reuse_depth': next_depth,
                'reuse_chain_limit': chain_limit,
                'reuse_origin_label': carried_origin_label,
                'apply_cost_on_execute': bool(policy.get('consume_cost', False)),
            }
            intents[next_slot_id] = next_intent

            queue_ref = battle_state.get('resolve', {}).get('single_queue', [])
            if not isinstance(queue_ref, list):
                queue_ref = []
                battle_state.setdefault('resolve', {})['single_queue'] = queue_ref
            # Insert directly after the current slot so chained reuses
            # execute deterministically within the same resolve window.
            insert_at = min(len(queue_ref), int(queue_index) + 1)
            queue_ref.insert(insert_at, next_slot_id)
            return next_slot_id

        def _emit_fizzle_with_log(attacker_slot, notes, target_actor_id=None):
            attacker_name, attacker_actor_id = _actor_name_from_slot(attacker_slot)
            skill_id_local = intents.get(attacker_slot, {}).get('skill_id')
            display_label = _resolve_reuse_display_label(attacker_slot)
            _ = attacker_name  # keep local extraction for stable actor_id resolution
            outcome_payload = {
                'attacker_id': attacker_actor_id,
                'target_id': target_actor_id,
                'skill_id': skill_id_local,
                'delegate_summary': {'rolls': {}, 'logs': []}
            }
            legacy_input = to_legacy_duel_log_input(
                outcome_payload=outcome_payload,
                state=state,
                intents=intents,
                attacker_slot=attacker_slot,
                defender_slot=None,
                applied={'damage': [], 'statuses': [], 'cost': {'hp': 0, 'mp': 0, 'fp': 0}},
                kind='fizzle',
                outcome='no_effect',
                notes=notes
            )
            log_lines = format_duel_result_lines(
                legacy_input['actor_name_a'],
                legacy_input['skill_display_a'],
                legacy_input['total_a'],
                legacy_input['actor_name_d'],
                legacy_input['skill_display_d'],
                legacy_input['total_d'],
                legacy_input['winner_message'],
                damage_report=legacy_input['damage_report'],
                extra_lines=legacy_input.get('extra_lines')
            )
            _log_match_result(log_lines)
            _append_trace(
                room, battle_id, battle_state, 'fizzle', attacker_slot,
                target_actor_id=target_actor_id,
                outcome='no_effect',
                notes=notes,
                extra_fields={
                    'display_label': display_label,
                    'lines': log_lines,
                    'log_lines': log_lines,
                    'outcome_payload': dict(outcome_payload, log_lines=log_lines)
                }
            )

        def _emit_cancelled_clash_with_log(attacker_slot, defender_slot, notes, target_actor_id=None):
            attacker_name, attacker_actor_id = _actor_name_from_slot(attacker_slot)
            skill_id_local = intents.get(attacker_slot, {}).get('skill_id')
            display_label = _resolve_reuse_display_label(attacker_slot)
            _ = attacker_name
            outcome_payload = {
                'attacker_id': attacker_actor_id,
                'target_id': target_actor_id,
                'skill_id': skill_id_local,
                'delegate_summary': {'rolls': {}, 'logs': []}
            }
            legacy_input = to_legacy_duel_log_input(
                outcome_payload=outcome_payload,
                state=state,
                intents=intents,
                attacker_slot=attacker_slot,
                defender_slot=defender_slot,
                applied={'damage': [], 'statuses': [], 'cost': {'hp': 0, 'mp': 0, 'fp': 0}},
                kind='clash',
                outcome='no_effect',
                notes=notes
            )
            legacy_input['winner_message'] = "<strong> 竊・荳咲匱</strong>"
            log_lines = format_duel_result_lines(
                legacy_input['actor_name_a'],
                legacy_input['skill_display_a'],
                legacy_input['total_a'],
                legacy_input['actor_name_d'],
                legacy_input['skill_display_d'],
                legacy_input['total_d'],
                legacy_input['winner_message'],
                damage_report=legacy_input['damage_report'],
                extra_lines=legacy_input.get('extra_lines')
            )
            _log_match_result(log_lines)
            _append_trace(
                room,
                battle_id,
                battle_state,
                'fizzle',
                attacker_slot,
                defender_slot=defender_slot,
                target_actor_id=target_actor_id,
                outcome='no_effect',
                notes=notes,
                extra_fields={
                    'display_label': display_label,
                    'resolution_kind': 'cancelled_clash',
                    'lines': log_lines,
                    'log_lines': log_lines,
                    'outcome_payload': dict(outcome_payload, log_lines=log_lines)
                }
            )

        queue_index = 0
        while True:
            single_queue_runtime = battle_state.get('resolve', {}).get('single_queue', [])
            if not isinstance(single_queue_runtime, list):
                single_queue_runtime = []
                battle_state.setdefault('resolve', {})['single_queue'] = single_queue_runtime
            if queue_index >= len(single_queue_runtime):
                break
            slot_id = single_queue_runtime[queue_index]
            clear_newly_applied_flags(state)
            if slot_id in processed_slots:
                logger.debug("[resolve_single] skip slot=%s reason=processed", slot_id)
                queue_index += 1
                continue

            attacker_actor_id = slots.get(slot_id, {}).get('actor_id')
            if not attacker_actor_id or not _is_actor_placed(state, attacker_actor_id):
                _emit_fizzle_with_log(slot_id, 'attacker_unplaced', target_actor_id=attacker_actor_id)
                _mark_processed(slot_id, cancelled_without_use=True)
                queue_index += 1
                continue

            attacker_is_contested_loser = slot_id in contested_losers

            intent_a = intents.get(slot_id, {})
            skill_id = intent_a.get('skill_id')
            if not intent_a or not skill_id:
                _emit_fizzle_with_log(slot_id, 'no_intent')
                _mark_processed(slot_id, cancelled_without_use=True)
                queue_index += 1
                continue
            skill_data = all_skill_data.get(skill_id, {}) if skill_id else {}
            trace_display_label = _resolve_reuse_display_label(slot_id)

            target = intent_a.get('target', {})
            target_slot = target.get('slot_id')
            if target.get('type') != 'single_slot' or not target_slot:
                _emit_fizzle_with_log(slot_id, 'invalid_target')
                _mark_processed(slot_id, cancelled_without_use=True)
                queue_index += 1
                continue

            target_actor_id = slots.get(target_slot, {}).get('actor_id')
            if not target_actor_id or not _is_actor_placed(state, target_actor_id):
                _emit_fizzle_with_log(slot_id, 'target_unplaced', target_actor_id=target_actor_id)
                _mark_processed(slot_id, cancelled_without_use=True)
                queue_index += 1
                continue

            if str(target_slot) == str(slot_id) and is_auto_defense_skill_data(skill_data):
                actor_char = characters_by_id.get(attacker_actor_id)
                if actor_char:
                    auto_defense = skill_data.get('auto_defense')
                    if not isinstance(auto_defense, dict):
                        auto_defense = (skill_data.get('rule_data') or {}).get('auto_defense', {})
                    grant_auto_defense_charge(
                        battle_state,
                        attacker_actor_id,
                        skill_id,
                        count=int((auto_defense or {}).get('count_per_use', 1) or 1)
                    )
                _mark_processed(slot_id)
                queue_index += 1
                continue

            intent_b = intents.get(target_slot, {})
            defender_skill_id_for_pair = intent_b.get('skill_id') if isinstance(intent_b, dict) else None
            defender_skill_data_for_pair = all_skill_data.get(defender_skill_id_for_pair, {}) if defender_skill_id_for_pair else None
            non_clashable_ally_support = _is_non_clashable_ally_support_pair(
                slots,
                slot_id,
                target_slot,
                skill_data,
                defender_skill_data_for_pair,
            )
            same_team_pair = _is_same_team_slot_pair(slots, slot_id, target_slot)
            is_clash = (
                not attacker_is_contested_loser
                and
                intent_b.get('target', {}).get('type') == 'single_slot'
                and intent_b.get('target', {}).get('slot_id') == slot_id
                and (not non_clashable_ally_support)
            )
            clash_defender_slot = target_slot if is_clash else None
            if (not is_clash) and target_actor_id and (not same_team_pair):
                evade_slot, evade_reason = select_evade_insert_slot(
                    state, battle_state, target_actor_id, slot_id
                )
                if evade_slot:
                    logger.info(
                        "[evade_insert] attacker_slot=%s defender_actor=%s defender_slot=%s reason=%s",
                        slot_id, target_actor_id, evade_slot, evade_reason
                    )
                    _append_trace(
                        room,
                        battle_id,
                        battle_state,
                        'evade_insert',
                        slot_id,
                        defender_slot=evade_slot,
                        target_actor_id=target_actor_id,
                        notes=f"dodge_lock insert ({evade_reason})",
                        outcome='no_effect'
                    )
                    is_clash = True
                    clash_defender_slot = evade_slot

            if is_clash:
                defender_actor_id = slots.get(clash_defender_slot, {}).get('actor_id') if clash_defender_slot else target_actor_id
                attacker_char = characters_by_id.get(attacker_actor_id)
                defender_char = characters_by_id.get(defender_actor_id)
                clash_intent = intents.get(clash_defender_slot, {}) if clash_defender_slot else {}
                defender_skill_id = clash_intent.get('skill_id')
                defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id else None
                cancelled_clash_reason = _get_inherent_skill_cancel_reason(skill_data, defender_skill_data)
                if cancelled_clash_reason:
                    _emit_cancelled_clash_with_log(
                        slot_id,
                        clash_defender_slot,
                        cancelled_clash_reason,
                        target_actor_id=defender_actor_id
                    )
                    _mark_processed(slot_id, cancelled_without_use=True)
                    _mark_processed(clash_defender_slot, cancelled_without_use=True)
                    queue_index += 1
                    continue

                clash_delegated = _resolve_clash_by_existing_logic(
                    room=room,
                    state=state,
                    attacker_char=attacker_char,
                    defender_char=defender_char,
                    attacker_skill_data=skill_data,
                    defender_skill_data=defender_skill_data
                )
                clash_ok = bool((clash_delegated or {}).get('ok', False))
                clash_summary = clash_delegated.get('summary', {}) if clash_ok else {}
                clash_outcome = clash_delegated.get('outcome', 'no_effect') if clash_ok else 'no_effect'
                clash_rolls = clash_summary.get('rolls', {}) if isinstance(clash_summary, dict) else {}
                clash_notes = None if clash_ok else (clash_delegated.get('reason') if isinstance(clash_delegated, dict) else 'delegate_failed')

                clash_reuse_slot = None
                clash_reuse_intent = None
                clash_reuse_policy = {'enabled': False, 'max_reuses': 0, 'consume_cost': False}
                clash_reuse_origin_label = trace_display_label
                hard_followup_plan = None
                hard_followup_block_reason = None
                hard_followup_block_log = None

                if clash_ok and clash_outcome in {'attacker_win', 'defender_win'}:
                    winner_is_attacker = clash_outcome == 'attacker_win'
                    winner_slot = slot_id if winner_is_attacker else clash_defender_slot
                    winner_intent = intent_a if winner_is_attacker else clash_intent
                    winner_char = attacker_char if winner_is_attacker else defender_char
                    loser_char = defender_char if winner_is_attacker else attacker_char
                    winner_skill_data = skill_data if winner_is_attacker else defender_skill_data
                    loser_skill_data = defender_skill_data if winner_is_attacker else skill_data

                    if _should_grant_clash_win_fp(skill_data, defender_skill_data, clash_outcome):
                        fp_status = _ensure_clash_winner_fp_gain(
                            room,
                            winner_char,
                            clash_summary,
                            winner_skill_data=winner_skill_data
                        )
                        if isinstance(fp_status, dict):
                            if not isinstance(clash_summary, dict):
                                clash_summary = {}
                            statuses = clash_summary.get('statuses', [])
                            if not isinstance(statuses, list):
                                statuses = []
                            statuses.append(fp_status)
                            clash_summary['statuses'] = statuses

                    clash_reuse_slot = winner_slot
                    clash_reuse_intent = winner_intent if isinstance(winner_intent, dict) else None

                    loser_slot = clash_defender_slot if winner_is_attacker else slot_id
                    loser_intent = clash_intent if winner_is_attacker else intent_a
                    if (
                        _is_hard_skill(loser_skill_data)
                        and (_is_normal_skill(winner_skill_data) or _is_feint_skill(winner_skill_data))
                    ):
                        if _is_feint_skill(winner_skill_data):
                            hard_followup_block_reason = 'feint_blocked'
                            winner_name = str((winner_char or {}).get('name') or '荳肴・')
                            loser_name = str((loser_char or {}).get('name') or '荳肴・')
                            hard_followup_block_log = f"[牽制] {winner_name} の牽制により {loser_name} の強硬攻撃は不発"
                        elif _resolve_skill_role(winner_skill_data) == 'evade':
                            hard_followup_block_reason = 'hard_evaded'
                            winner_name = str((winner_char or {}).get('name') or '荳肴・')
                            loser_name = str((loser_char or {}).get('name') or '荳肴・')
                            hard_followup_block_log = f"[回避] {winner_name} の回避成功により {loser_name} の強硬攻撃は不発"
                        else:
                            hard_followup_plan = {
                                'attacker_slot': loser_slot,
                                'attacker_intent': loser_intent if isinstance(loser_intent, dict) else {},
                                'attacker_char': loser_char,
                                'attacker_skill_data': loser_skill_data,
                                'defender_slot': None,
                                'defender_char': winner_char,
                            }

                    # Preferred source: delegate summary (one-sided path uses this today).
                    clash_reuse_policy = _collect_reuse_policy(clash_summary)

                    # Clash delegate uses legacy duel internals and may not expose re-use intents.
                    # Fallback: evaluate HIT timing on winner skill and extract USE_SKILL_AGAIN changes.
                    if (
                        (not clash_reuse_policy.get('enabled', False))
                        and isinstance(winner_char, dict)
                        and isinstance(loser_char, dict)
                        and isinstance(winner_skill_data, dict)
                    ):
                        winner_rule = _extract_rule_data_from_skill(winner_skill_data)
                        winner_effects = winner_rule.get('effects', []) if isinstance(winner_rule, dict) else []
                        reuse_context = {
                            'timeline': state.get('timeline', []),
                            'characters': state.get('characters', []),
                            'room': room,
                            'battle_state': state.get('battle_state'),
                            'room_state': state
                        }
                        _tmp_dmg, _tmp_logs, winner_changes = process_skill_effects(
                            winner_effects,
                            "HIT",
                            winner_char,
                            loser_char,
                            loser_skill_data,
                            context=reuse_context,
                            base_damage=0
                        )
                        winner_reuse_requests = _extract_reuse_requests_from_changes(winner_changes)
                        clash_reuse_policy = _collect_reuse_policy({'reuse_requests': winner_reuse_requests})
                if hard_followup_block_reason:
                    if clash_notes:
                        clash_notes = f"{clash_notes} / {hard_followup_block_reason}"
                    else:
                        clash_notes = hard_followup_block_reason
                if hard_followup_block_log:
                    broadcast_log(room, hard_followup_block_log, 'info')

                clash_outcome_payload = {
                    'attacker_id': attacker_actor_id,
                    'target_id': defender_actor_id,
                    'skill_id': skill_id,
                    'skill': skill_data,
                    'apply_cost': False,  # clash cost is handled by delegated existing duel logic
                    'cost_policy': COST_CONSUME_POLICY,
                    'delegate_applied': clash_ok,
                    'delegate_summary': clash_summary if clash_ok else {}
                }
                clash_applied = _apply_outcome_to_state(clash_outcome_payload, characters_by_id)
                if clash_ok:
                    _emit_stat_updates_from_applied(
                        room,
                        clash_applied,
                        characters_by_id,
                        source='resolve_single_clash'
                    )
                attacker_name = _resolve_actor_name(characters_by_id, attacker_actor_id)
                defender_name = _resolve_actor_name(characters_by_id, defender_actor_id)
                attacker_skill_name = _resolve_skill_name(skill_id, skill_data)
                defender_skill_name = _resolve_skill_name(defender_skill_id, defender_skill_data)
                clash_rolls_norm = {
                    'power_a': clash_rolls.get('power_a'),
                    'power_b': clash_rolls.get('power_b'),
                    'tie_break': clash_rolls.get('tie_break')
                }
                clash_legacy_input = to_legacy_duel_log_input(
                    outcome_payload=clash_outcome_payload,
                    state=state,
                    intents=intents,
                    attacker_slot=slot_id,
                    defender_slot=clash_defender_slot,
                    applied=clash_applied,
                    kind='clash',
                    outcome=clash_outcome,
                    notes=clash_notes
                )
                clash_legacy_lines = format_duel_result_lines(
                    clash_legacy_input['actor_name_a'],
                    clash_legacy_input['skill_display_a'],
                    clash_legacy_input['total_a'],
                    clash_legacy_input['actor_name_d'],
                    clash_legacy_input['skill_display_d'],
                    clash_legacy_input['total_d'],
                    clash_legacy_input['winner_message'],
                    damage_report=clash_legacy_input['damage_report'],
                    extra_lines=clash_legacy_input.get('extra_lines')
                )
                clash_outcome_payload['log_lines'] = clash_legacy_lines
                clash_outcome_payload['lines'] = clash_legacy_lines
                clash_applied['log_lines'] = clash_legacy_lines
                clash_applied['lines'] = clash_legacy_lines
                _log_match_result(clash_legacy_lines)
                logger.info(
                    "[clash_outcome] slot=%s vs=%s outcome=%s cost=%s damage_events=%d status_events=%d",
                    slot_id,
                    clash_defender_slot,
                    clash_outcome,
                    clash_applied.get('cost', {}),
                    len(clash_applied.get('damage', []) or []),
                    len(clash_applied.get('statuses', []) or []),
                )
                trace_cost = {
                    'mp': int(clash_applied.get('cost', {}).get('mp', 0)),
                    'hp': int(clash_applied.get('cost', {}).get('hp', 0)),
                    'fp': int(clash_applied.get('cost', {}).get('fp', 0))
                }

                clash_trace_entry = _append_trace(
                    room, battle_id, battle_state, 'clash', slot_id,
                    defender_slot=clash_defender_slot,
                    target_actor_id=target_actor_id,
                    notes=clash_notes,
                    outcome=clash_outcome,
                    cost=trace_cost,
                    rolls=clash_rolls,
                    extra_fields={
                        'display_label': trace_display_label,
                        'outcome_payload': clash_outcome_payload,
                        'applied': clash_applied,
                        'lines': clash_legacy_lines,
                        'log_lines': clash_legacy_lines
                    }
                )
                attacker_self_destructed = _apply_self_destruct_if_needed(room, attacker_char, skill_data)
                defender_self_destructed = _apply_self_destruct_if_needed(room, defender_char, defender_skill_data)
                if (
                    clash_ok
                    and clash_reuse_slot
                    and isinstance(clash_reuse_intent, dict)
                    and clash_reuse_policy.get('enabled', False)
                ):
                    if clash_reuse_slot == slot_id and attacker_self_destructed:
                        clash_reuse_slot = None
                    if clash_reuse_slot == clash_defender_slot and defender_self_destructed:
                        clash_reuse_slot = None
                if (
                    clash_ok
                    and clash_reuse_slot
                    and isinstance(clash_reuse_intent, dict)
                    and clash_reuse_policy.get('enabled', False)
                ):
                    if not clash_reuse_origin_label and isinstance(clash_trace_entry, dict):
                        clash_reuse_origin_label = str(clash_trace_entry.get('step') or '')
                    _schedule_single_reuse_slot(
                        current_slot_id=clash_reuse_slot,
                        queue_index=queue_index,
                        intent_obj=clash_reuse_intent,
                        policy=clash_reuse_policy,
                        origin_label=clash_reuse_origin_label
                    )

                if clash_ok and isinstance(hard_followup_plan, dict):
                    hf_attacker_slot = hard_followup_plan.get('attacker_slot')
                    hf_attacker_char = hard_followup_plan.get('attacker_char')
                    hf_attacker_skill_data = hard_followup_plan.get('attacker_skill_data')
                    hf_defender_char = hard_followup_plan.get('defender_char')
                    hf_defender_slot = hard_followup_plan.get('defender_slot')
                    hf_defender_actor_id = (hf_defender_char or {}).get('id')
                    hf_evade_slot = None
                    hf_evade_reason = None
                    hf_defender_skill_data = None

                    if hf_defender_actor_id and hf_attacker_slot:
                        hf_evade_slot, hf_evade_reason = select_hard_followup_evade_slot(
                            state, battle_state, hf_defender_actor_id, hf_attacker_slot
                        )
                    if hf_evade_slot:
                        hf_defender_slot = hf_evade_slot
                        hf_evade_intent = intents.get(hf_evade_slot, {})
                        hf_evade_skill_id = hf_evade_intent.get('skill_id')
                        hf_defender_skill_data = all_skill_data.get(hf_evade_skill_id, {}) if hf_evade_skill_id else None

                    hard_res = _resolve_hard_attack_followup(
                        room=room,
                        state=state,
                        attacker_char=hf_attacker_char,
                        defender_char=hf_defender_char,
                        attacker_skill_data=hf_attacker_skill_data,
                        defender_skill_data=hf_defender_skill_data,
                    )
                    hard_ok = bool((hard_res or {}).get('ok', False))
                    hard_summary = hard_res.get('summary', {}) if hard_ok else {}
                    hard_outcome = hard_res.get('outcome', 'no_effect') if hard_ok else 'no_effect'
                    hard_notes = hf_evade_reason if hf_evade_reason else None
                    if not hard_ok:
                        hard_notes = hard_res.get('reason', 'hard_followup_failed')

                    hf_skill_id = _extract_skill_id_from_data(hf_attacker_skill_data)
                    hard_payload = {
                        'attacker_id': (hf_attacker_char or {}).get('id'),
                        'target_id': (hf_defender_char or {}).get('id'),
                        'skill_id': hf_skill_id,
                        'skill': hf_attacker_skill_data,
                        'apply_cost': False,
                        'cost_policy': COST_CONSUME_POLICY,
                        'delegate_applied': hard_ok,
                        'delegate_summary': hard_summary if hard_ok else {},
                    }
                    hard_applied = _apply_outcome_to_state(hard_payload, characters_by_id)
                    if hard_ok:
                        _emit_stat_updates_from_applied(
                            room,
                            hard_applied,
                            characters_by_id,
                            source='resolve_single_hard_attack'
                        )

                    hard_legacy_input = to_legacy_duel_log_input(
                        outcome_payload=hard_payload,
                        state=state,
                        intents=intents,
                        attacker_slot=hf_attacker_slot,
                        defender_slot=hf_defender_slot,
                        applied=hard_applied,
                        kind='one_sided',
                        outcome=hard_outcome,
                        notes=hard_notes
                    )
                    hard_lines = format_duel_result_lines(
                        hard_legacy_input['actor_name_a'],
                        hard_legacy_input['skill_display_a'],
                        hard_legacy_input['total_a'],
                        hard_legacy_input['actor_name_d'],
                        hard_legacy_input['skill_display_d'],
                        hard_legacy_input['total_d'],
                        hard_legacy_input['winner_message'],
                        damage_report=hard_legacy_input['damage_report'],
                        extra_lines=hard_legacy_input.get('extra_lines')
                    )
                    hard_payload['log_lines'] = hard_lines
                    hard_payload['lines'] = hard_lines
                    hard_applied['log_lines'] = hard_lines
                    hard_applied['lines'] = hard_lines
                    _log_match_result(hard_lines)
                    _append_trace(
                        room, battle_id, battle_state, 'hard_attack', hf_attacker_slot,
                        defender_slot=hf_defender_slot,
                        target_actor_id=hf_defender_actor_id,
                        notes=hard_notes,
                        outcome=hard_outcome,
                        cost={
                            'mp': int(hard_applied.get('cost', {}).get('mp', 0)),
                            'hp': int(hard_applied.get('cost', {}).get('hp', 0)),
                            'fp': int(hard_applied.get('cost', {}).get('fp', 0)),
                        },
                        rolls=hard_summary.get('rolls', {}) if isinstance(hard_summary, dict) else {},
                        extra_fields={
                            'display_label': _resolve_reuse_display_label(hf_attacker_slot),
                            'outcome_payload': hard_payload,
                            'applied': hard_applied,
                            'lines': hard_lines,
                            'log_lines': hard_lines,
                            'hard_followup': True,
                        }
                    )
                    if hf_evade_slot:
                        _mark_processed(hf_evade_slot)
                _mark_processed(slot_id)
                _mark_processed(clash_defender_slot)
            else:
                attacker_char = characters_by_id.get(attacker_actor_id)
                defender_char = characters_by_id.get(target_actor_id)
                intent_b = intents.get(target_slot, {}) if target_slot else {}
                defender_skill_id = intent_b.get('skill_id')
                defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id else None
                auto_defense_charge = consume_auto_defense_charge(battle_state, target_actor_id)

                if auto_defense_charge and isinstance(defender_char, dict):
                    charged_skill_id = str((auto_defense_charge or {}).get('skill_id') or '').strip()
                    charged_skill_data = get_system_skill(charged_skill_id)
                    delegated = _resolve_clash_by_existing_logic(
                        room=room,
                        state=state,
                        attacker_char=attacker_char,
                        defender_char=defender_char,
                        attacker_skill_data=skill_data,
                        defender_skill_data=charged_skill_data
                    )
                    clash_ok = bool((delegated or {}).get('ok', False))
                    clash_summary = delegated.get('summary', {}) if clash_ok else {}
                    clash_outcome = delegated.get('outcome', 'no_effect') if clash_ok else 'no_effect'
                    clash_notes = None if clash_ok else (delegated.get('reason') if isinstance(delegated, dict) else 'delegate_failed')

                    if clash_ok:
                        queue_selected_power_recovery_from_snapshot(
                            defender_char,
                            ((clash_summary.get('rolls', {}) or {}).get('power_snapshot_b', {}))
                        )

                    clash_outcome_payload = {
                        'attacker_id': attacker_actor_id,
                        'target_id': target_actor_id,
                        'skill_id': skill_id,
                        'skill': skill_data,
                        'apply_cost': False,
                        'cost_policy': COST_CONSUME_POLICY,
                        'delegate_applied': clash_ok,
                        'delegate_summary': clash_summary if clash_ok else {}
                    }
                    clash_applied = _apply_outcome_to_state(clash_outcome_payload, characters_by_id)
                    if clash_ok:
                        _emit_stat_updates_from_applied(
                            room,
                            clash_applied,
                            characters_by_id,
                            source='resolve_single_auto_defense_clash'
                        )
                    clash_legacy_input = to_legacy_duel_log_input(
                        outcome_payload=clash_outcome_payload,
                        state=state,
                        intents=intents,
                        attacker_slot=slot_id,
                        defender_slot=target_slot,
                        applied=clash_applied,
                        kind='clash',
                        outcome=clash_outcome,
                        notes=clash_notes
                    )
                    clash_log_lines = format_duel_result_lines(
                        clash_legacy_input['actor_name_a'],
                        clash_legacy_input['skill_display_a'],
                        clash_legacy_input['total_a'],
                        clash_legacy_input['actor_name_d'],
                        clash_legacy_input['skill_display_d'],
                        clash_legacy_input['total_d'],
                        clash_legacy_input['winner_message'],
                        damage_report=clash_legacy_input['damage_report'],
                        extra_lines=clash_legacy_input.get('extra_lines')
                    )
                    clash_outcome_payload['log_lines'] = clash_log_lines
                    clash_outcome_payload['lines'] = clash_log_lines
                    clash_applied['log_lines'] = clash_log_lines
                    clash_applied['lines'] = clash_log_lines
                    _log_match_result(clash_log_lines)
                    _append_trace(
                        room, battle_id, battle_state, 'clash', slot_id,
                        defender_slot=target_slot,
                        target_actor_id=target_actor_id,
                        notes=clash_notes,
                        outcome=clash_outcome,
                        cost={
                            'mp': int(clash_applied.get('cost', {}).get('mp', 0)),
                            'hp': int(clash_applied.get('cost', {}).get('hp', 0)),
                            'fp': int(clash_applied.get('cost', {}).get('fp', 0))
                        },
                        rolls=clash_summary.get('rolls', {}) if isinstance(clash_summary, dict) else {},
                        extra_fields={
                            'display_label': trace_display_label,
                            'outcome_payload': clash_outcome_payload,
                            'applied': clash_applied,
                            'lines': clash_log_lines,
                            'log_lines': clash_log_lines,
                            'auto_defense': True
                        }
                    )
                    _mark_processed(slot_id)
                    queue_index += 1
                    continue

                delegated = _resolve_one_sided_by_existing_logic(
                    room=room,
                    state=state,
                    attacker_char=attacker_char,
                    defender_char=defender_char,
                    attacker_skill_data=skill_data,
                    defender_skill_data=defender_skill_data
                )
                delegate_ok = bool((delegated or {}).get('ok', False))
                delegate_summary = delegated.get('summary', {}) if delegate_ok else {}
                outcome_payload = {
                    'attacker_id': attacker_actor_id,
                    'target_id': target_actor_id,
                    'skill_id': skill_id,
                    'skill': skill_data,
                    'apply_cost': bool(intent_a.get('apply_cost_on_execute', True)),
                    'cost_policy': COST_CONSUME_POLICY,
                    'delegate_applied': delegate_ok,
                    'delegate_summary': delegate_summary if delegate_ok else {}
                }
                applied = _apply_outcome_to_state(outcome_payload, characters_by_id)
                attacker_name = _resolve_actor_name(characters_by_id, attacker_actor_id)
                defender_name = _resolve_actor_name(characters_by_id, target_actor_id)
                attacker_skill_name = _resolve_skill_name(skill_id, skill_data)
                one_sided_rolls = delegate_summary.get('rolls', {}) if isinstance(delegate_summary, dict) else {}
                one_sided_rolls_norm = {
                    'power_a': one_sided_rolls.get('total_damage', one_sided_rolls.get('final_damage', one_sided_rolls.get('base_damage'))),
                    'power_b': '-',
                    'tie_break': 'one_sided'
                }
                one_sided_notes = None if delegate_ok else (delegated.get('reason') if isinstance(delegated, dict) else 'delegate_failed')
                one_sided_legacy_input = to_legacy_duel_log_input(
                    outcome_payload=outcome_payload,
                    state=state,
                    intents=intents,
                    attacker_slot=slot_id,
                    defender_slot=target_slot,
                    applied=applied,
                    kind='one_sided',
                    outcome=('attacker_win' if delegate_ok else 'no_effect'),
                    notes=one_sided_notes
                )
                one_sided_log_lines = format_duel_result_lines(
                    one_sided_legacy_input['actor_name_a'],
                    one_sided_legacy_input['skill_display_a'],
                    one_sided_legacy_input['total_a'],
                    one_sided_legacy_input['actor_name_d'],
                    one_sided_legacy_input['skill_display_d'],
                    one_sided_legacy_input['total_d'],
                    one_sided_legacy_input['winner_message'],
                    damage_report=one_sided_legacy_input['damage_report'],
                    extra_lines=one_sided_legacy_input.get('extra_lines')
                )
                outcome_payload['log_lines'] = one_sided_log_lines
                outcome_payload['lines'] = one_sided_log_lines
                applied['log_lines'] = one_sided_log_lines
                applied['lines'] = one_sided_log_lines
                _log_match_result(one_sided_log_lines)
                logger.info(
                    "[one_sided_outcome] slot=%s attacker=%s target=%s cost=%s damage_events=%d status_events=%d",
                    slot_id,
                    attacker_actor_id,
                    target_actor_id,
                    applied.get('cost', {}),
                    len(applied.get('damage', []) or []),
                    len(applied.get('statuses', []) or []),
                )
                trace_cost = {
                    'mp': int(applied.get('cost', {}).get('mp', 0)),
                    'hp': int(applied.get('cost', {}).get('hp', 0)),
                    'fp': int(applied.get('cost', {}).get('fp', 0))
                }
                trace_outcome = 'attacker_win' if delegate_ok else 'no_effect'
                trace_notes = one_sided_notes
                trace_rolls = delegate_summary.get('rolls', {}) if isinstance(delegate_summary, dict) else {}

                trace_entry = _append_trace(
                    room, battle_id, battle_state, 'one_sided', slot_id,
                    defender_slot=target_slot,
                    target_actor_id=target_actor_id,
                    notes=trace_notes,
                    outcome=trace_outcome,
                    cost=trace_cost,
                    rolls=trace_rolls,
                    extra_fields={
                        'display_label': trace_display_label,
                        'outcome_payload': outcome_payload,
                        'applied': applied,
                        'lines': one_sided_log_lines,
                        'log_lines': one_sided_log_lines
                    }
                )
                attacker_self_destructed = _apply_self_destruct_if_needed(room, attacker_char, skill_data)
                if delegate_ok:
                    reuse_policy = _collect_reuse_policy(delegate_summary)
                    current_label = trace_display_label
                    if not current_label and isinstance(trace_entry, dict):
                        current_label = str(trace_entry.get('step') or '')
                    if not attacker_self_destructed:
                        _schedule_single_reuse_slot(
                            current_slot_id=slot_id,
                            queue_index=queue_index,
                            intent_obj=intent_a,
                            policy=reuse_policy,
                            origin_label=current_label
                        )
                _mark_processed(slot_id)

            queue_index += 1

        remaining_slots = sum(
            1 for slot in (slots or {}).values()
            if isinstance(slot, dict) and not slot.get('disabled', False)
        )
        committed_intents = sum(
            1 for intent in (intents or {}).values()
            if isinstance(intent, dict) and bool(intent.get('committed', False))
        )
        logger.info(
            "[round_end_summary] room=%s battle=%s remaining_slots=%d committed_intents=%d",
            room, battle_id, remaining_slots, committed_intents
        )

        timeline_before = _snapshot_legacy_timeline_state(state)
        resolved_slots = battle_state.get('resolve', {}).get('resolved_slots', []) or []
        sync_slot_ids = [sid for sid in resolved_slots if sid in slots] or list(processed_slots)
        processed_actor_ids = [
            slots.get(sid, {}).get('actor_id')
            for sid in sync_slot_ids
            if slots.get(sid, {}).get('actor_id')
        ]
        consumed_entries = _consume_legacy_timeline_entries_for_slots(state, slots, sync_slot_ids)
        synced_has_acted = _sync_legacy_has_acted_flags_from_timeline(
            state,
            actor_ids=processed_actor_ids
        )
        logger.info(
            "[resolve_single_turn_sync] room=%s battle=%s processed_slots=%d sync_slots=%d actors=%d consumed_entries=%d has_acted_synced=%d",
            room,
            battle_id,
            len(processed_slots),
            len(sync_slot_ids),
            len(set(processed_actor_ids)),
            consumed_entries,
            synced_has_acted
        )
        try:
            proceed_next_turn(room, suppress_logs=True, suppress_state_emit=True)
        except Exception as e:
            logger.warning("[resolve_single_turn_sync] proceed_next_turn failed room=%s battle=%s error=%s", room, battle_id, e)
        timeline_after = _snapshot_legacy_timeline_state(state)
        logger.info(
            "[resolve_single_turn_snapshot] room=%s battle=%s before(total=%d acted=%d turn=%s/%s head=%s) after(total=%d acted=%d turn=%s/%s head=%s)",
            room,
            battle_id,
            int(timeline_before.get('total', 0)),
            int(timeline_before.get('acted', 0)),
            timeline_before.get('current_entry_id'),
            timeline_before.get('current_char_id'),
            timeline_before.get('head'),
            int(timeline_after.get('total', 0)),
            int(timeline_after.get('acted', 0)),
            timeline_after.get('current_entry_id'),
            timeline_after.get('current_char_id'),
            timeline_after.get('head')
        )

        try:
            _apply_phase_timing_for_committed_intents(
                room=room,
                state=state,
                battle_state=battle_state,
                characters_by_id=characters_by_id,
                timing='RESOLVE_END',
                intents_override=resolve_intents
            )
        except Exception as e:
            logger.warning("[timing_effect] RESOLVE_END failed room=%s battle=%s error=%s", room, battle_id, e)

        battle_state['phase'] = 'round_end'
        battle_state['intents'] = {}
        battle_state['resolve_snapshot_intents'] = {}
        battle_state['resolve_snapshot_at'] = None
        battle_state.setdefault('resolve', {})['timing_marks'] = {}
        battle_state.setdefault('resolve', {})['auto_defense_charges'] = {}

        # Stop legacy sequential turn flow after select/resolve round is finished.
        state['turn_char_id'] = None
        state['turn_entry_id'] = None
        for entry in state.get('timeline', []) or []:
            if isinstance(entry, dict):
                entry['acted'] = True
        _sync_legacy_has_acted_flags_from_timeline(state)

        round_finished_payload = {
            'room_id': room,
            'battle_id': battle_id,
            'round': battle_state.get('round', 0),
            'phase': battle_state.get('phase', 'round_end'),
            'timeline': battle_state.get('timeline', []),
            'slots': battle_state.get('slots', {}),
            'intents': battle_state.get('intents', {})
        }
        _log_battle_emit('battle_round_finished', room, battle_id, round_finished_payload)
        socketio.emit('battle_round_finished', round_finished_payload, to=room)
        payload = build_select_resolve_state_payload(room, battle_id=battle_id)
        if payload:
            _log_battle_emit('battle_state_updated', room, battle_id, payload)
            socketio.emit('battle_state_updated', payload, to=room)
        # Do not auto-advance immediately here.
        # In battle_only mode, round-end/start should happen after clients finish
        # resolve-flow playback and explicitly trigger request_end_round.


def _try_auto_advance_battle_only_round(room, state):
    if not isinstance(state, dict):
        return
    play_mode = str(state.get('play_mode') or 'normal').strip().lower()
    if play_mode != 'battle_only':
        return
    bo = state.get('battle_only') if isinstance(state.get('battle_only'), dict) else {}
    bo_status = str(bo.get('status') or '').strip().lower()
    if bo_status and bo_status != 'in_battle':
        return
    if state.get('is_round_ended', False):
        return

    from manager.battle.common_manager import process_full_round_end, process_round_start

    actor = '戦闘専用モード'
    process_full_round_end(room, actor)
    refreshed = get_room_state(room)
    if not isinstance(refreshed, dict):
        return
    if not refreshed.get('is_round_ended', False):
        return
    process_round_start(room, actor)


