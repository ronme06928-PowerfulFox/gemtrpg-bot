from manager.constants import DamageSource, THORNS_DAMAGE_CATS
from manager.battle.damage_context import build_damage_context
from manager.battle.skill_rules import _resolve_skill_category
from manager.room_manager import _handle_character_death_transition


def _sync_from_core():
    from manager.battle import core as core_mod
    g = globals()
    # Pull symbols from core at runtime to preserve test monkeypatch behavior.
    for name, value in core_mod.__dict__.items():
        if name.startswith("__"):
            continue
        g[name] = value


def run_mass_phase(room, battle_id, state, battle_state, resolve_intents, characters_by_id):
    _sync_from_core()
    from manager.battle.common_manager import build_select_resolve_state_payload

    if battle_state.get('phase') == 'resolve_mass':
        intents = resolve_intents
        slots = battle_state.get('slots', {})

        def _enemy_actor_ids_for_team(attacker_team):
            enemy_actors = []
            for actor in state.get('characters', []):
                actor_id = actor.get('id')
                if not actor_id:
                    continue
                if actor.get('type') == attacker_team:
                    continue
                if not _is_actor_placed(state, actor_id):
                    continue
                enemy_actors.append(actor_id)
            return enemy_actors

        def _emit_hp_diff(char_obj, old_hp, new_hp, source='mass-summation'):
            if not isinstance(char_obj, dict):
                return
            if int(old_hp) == int(new_hp):
                return
            socketio.emit('char_stat_updated', {
                'room': room,
                'char_id': char_obj.get('id'),
                'stat': 'HP',
                'new_value': int(new_hp),
                'old_value': int(old_hp),
                'max_value': int(char_obj.get('maxHp', 0) or 0),
                'log_message': f"[{source}] {char_obj.get('name', char_obj.get('id'))}: HP ({int(old_hp)}) -> ({int(new_hp)})",
                'source': source
            }, to=room)

        def _apply_mass_summation_delta_damage(
            target_actor_ids,
            delta_value,
            source_actor=None,
            source_skill=None,
        ):
            damage_events = []
            delta_int = int(max(0, delta_value))
            if delta_int <= 0:
                return damage_events

            for actor_id in (target_actor_ids or []):
                defender_char = characters_by_id.get(actor_id)
                if not isinstance(defender_char, dict):
                    continue
                try:
                    fissure = int(get_status_value(defender_char, '亀裂') or 0)
                except Exception:
                    fissure = 0
                total_damage = max(0, delta_int + fissure)
                if total_damage <= 0:
                    continue
                before_hp = int(defender_char.get('hp', 0))
                after_hp = max(0, before_hp - total_damage)
                if after_hp == before_hp:
                    continue
                defender_char['hp'] = after_hp
                _handle_character_death_transition(
                    room,
                    defender_char,
                    before_hp,
                    after_hp,
                    username="[mass-summation]",
                    damage_context=build_damage_context(
                        actor=source_actor,
                        skill_data=source_skill,
                        damage_type="mass-summation",
                    ),
                )
                _emit_hp_diff(defender_char, before_hp, after_hp, source='mass-summation')
                damage_events.append({
                    'target_id': actor_id,
                    'hp': int(before_hp - after_hp),
                    'damage_type': '合計ダメージ',
                    'base_delta': delta_int,
                    'fissure': fissure,
                })
            return damage_events

        def _mass_target_char(actor_ids):
            for actor_id in actor_ids or []:
                char = characters_by_id.get(actor_id)
                if isinstance(char, dict):
                    return char
            return None

        def _trigger_mass_summation_timing(timing, actor_char, target_char, skill_data, target_skill_data=None, base_damage=0):
            if not isinstance(actor_char, dict) or not isinstance(skill_data, dict):
                return
            _trigger_skill_timing_effects(
                room=room,
                state=state,
                characters_by_id=characters_by_id,
                timing=timing,
                actor_char=actor_char,
                target_char=target_char,
                skill_data=skill_data,
                target_skill_data=target_skill_data,
                base_damage=int(base_damage or 0),
                emit_source='mass_summation_timing'
            )

        def _apply_mass_summation_thorns(actor_char, skill_data):
            if not isinstance(actor_char, dict):
                return
            thorn_val = int(get_status_value(actor_char, "荊棘") or 0)
            if thorn_val <= 0:
                return

            category = _resolve_skill_category(skill_data)
            if category in THORNS_DAMAGE_CATS:
                current_hp = int(actor_char.get('hp', 0) or 0)
                _update_char_stat(
                    room,
                    actor_char,
                    "HP",
                    max(0, current_hp - thorn_val),
                    username="[荊棘自傷]",
                    source=DamageSource.THORNS,
                    damage_context=build_damage_context(
                        actor=actor_char,
                        skill_data=skill_data,
                        damage_type=DamageSource.THORNS,
                    ),
                )

            entangle_val = int(get_status_value(actor_char, "荊棘重絡") or 0)
            if entangle_val > 0:
                _update_char_stat(room, actor_char, "荊棘重絡", entangle_val - 1, username="[荊棘重絡消費]")
            else:
                _update_char_stat(room, actor_char, "荊棘", 0, username="[荊棘消滅]")

        # Resolve every mass slot first, then hand over to single-phase resolution.
        for slot_id in battle_state['resolve'].get('mass_queue', []):
            clear_newly_applied_flags(state)
            intent = intents.get(slot_id, {})
            tags = intent.get('tags', {})
            mass_type = tags.get('mass_type')
            attacker_skill_id = intent.get('skill_id')
            attacker_skill_data = all_skill_data.get(attacker_skill_id, {}) if attacker_skill_id else {}
            attacker_slot_data = slots.get(slot_id, {})
            attacker_actor_id = attacker_slot_data.get('actor_id')
            attacker_team = attacker_slot_data.get('team')
            attacker_char = characters_by_id.get(attacker_actor_id)

            if not attacker_actor_id or not attacker_char or not _is_actor_placed(state, attacker_actor_id):
                _append_trace(
                    room,
                    battle_id,
                    battle_state,
                    'fizzle',
                    slot_id,
                    notes='attacker_unplaced',
                    extra_fields={'lines': ['reason: attacker_unplaced'], 'log_lines': ['reason: attacker_unplaced']},
                )
                _consume_resolve_slot(battle_state, slot_id)
                continue

            # Mass attacker skill is resolved in this phase and should count for END_ROUND effects.
            _record_used_skill_for_actor(attacker_char, attacker_skill_id)

            def _emit_mass_one_sided(defender_actor_id, defender_slot=None, trace_kind='mass_individual', trace_notes=None):
                defender_char = characters_by_id.get(defender_actor_id)
                if not isinstance(defender_char, dict):
                    _append_trace(
                        room,
                        battle_id,
                        battle_state,
                        'fizzle',
                        slot_id,
                        defender_slot=defender_slot,
                        target_actor_id=defender_actor_id,
                        notes='target_unplaced',
                        extra_fields={'lines': ['reason: target_unplaced'], 'log_lines': ['reason: target_unplaced']},
                    )
                    return

                defender_intent = intents.get(defender_slot, {}) if defender_slot else {}
                defender_skill_id = defender_intent.get('skill_id')
                defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id else None

                delegated = _resolve_one_sided_by_existing_logic(
                    room=room,
                    state=state,
                    attacker_char=attacker_char,
                    defender_char=defender_char,
                    attacker_skill_data=attacker_skill_data,
                    defender_skill_data=defender_skill_data
                )
                delegate_ok = bool((delegated or {}).get('ok', False))
                delegate_summary = delegated.get('summary', {}) if delegate_ok else {}

                outcome_payload = {
                    'attacker_id': attacker_actor_id,
                    'target_id': defender_actor_id,
                    'skill_id': attacker_skill_id,
                    'skill': attacker_skill_data,
                    'apply_cost': False,
                    'cost_policy': COST_CONSUME_POLICY,
                    'delegate_applied': delegate_ok,
                    'delegate_summary': delegate_summary if delegate_ok else {}
                }
                applied = _apply_outcome_to_state(outcome_payload, characters_by_id)

                one_sided_notes = None if delegate_ok else (delegated.get('reason') if isinstance(delegated, dict) else 'delegate_failed')
                legacy_input = to_legacy_duel_log_input(
                    outcome_payload=outcome_payload,
                    state=state,
                    intents=intents,
                    attacker_slot=slot_id,
                    defender_slot=defender_slot,
                    applied=applied,
                    kind='one_sided',
                    outcome=('attacker_win' if delegate_ok else 'no_effect'),
                    notes=(trace_notes or one_sided_notes)
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

                outcome_payload['log_lines'] = log_lines
                outcome_payload['lines'] = log_lines
                applied['log_lines'] = log_lines
                applied['lines'] = log_lines

                _append_trace(
                    room,
                    battle_id,
                    battle_state,
                    trace_kind,
                    slot_id,
                    defender_slot=defender_slot,
                    target_actor_id=defender_actor_id,
                    notes=(trace_notes or one_sided_notes),
                    outcome=('attacker_win' if delegate_ok else 'no_effect'),
                    cost={
                        'mp': int(applied.get('cost', {}).get('mp', 0)),
                        'hp': int(applied.get('cost', {}).get('hp', 0)),
                        'fp': int(applied.get('cost', {}).get('fp', 0)),
                    },
                    rolls=(delegate_summary.get('rolls', {}) if isinstance(delegate_summary, dict) else {}),
                    extra_fields={
                        'resolution_kind': 'one_sided',
                        'outcome_payload': outcome_payload,
                        'applied': applied,
                        'lines': log_lines,
                        'log_lines': log_lines
                    }
                )

            # summation/mass_summation uses one aggregate clash against all
            # participants that targeted this mass slot.
            if mass_type in ['summation', 'mass_summation']:
                participant_slots = _gather_slots_targeting_slot_s(
                    state,
                    battle_state,
                    slot_id,
                    attacker_team=attacker_team,
                    intents_override=intents
                )

                attacker_power = _roll_power_for_slot(battle_state, slot_id)
                defender_powers = {}
                participant_entries = []
                for p_slot in participant_slots:
                    participant_actor_id = slots.get(p_slot, {}).get('actor_id')
                    participant_char = characters_by_id.get(participant_actor_id)
                    participant_skill_id = (intents.get(p_slot, {}) or {}).get('skill_id')
                    participant_skill_data = all_skill_data.get(participant_skill_id, {}) if participant_skill_id else {}
                    _record_used_skill_for_actor(participant_char, participant_skill_id)
                    defender_powers[p_slot] = _roll_power_for_slot(battle_state, p_slot)
                    if isinstance(participant_char, dict):
                        participant_entries.append({
                            'slot_id': p_slot,
                            'actor_id': participant_actor_id,
                            'char': participant_char,
                            'skill_id': participant_skill_id,
                            'skill_data': participant_skill_data,
                        })
                defender_sum = sum(defender_powers.values())
                outcome = _compare_outcome(attacker_power, defender_sum)
                delta = abs(int(attacker_power) - int(defender_sum))
                attacker_name = _resolve_actor_name(characters_by_id, attacker_actor_id)
                skill_name = _resolve_skill_name(attacker_skill_id, attacker_skill_data)
                defender_actor_ids = _enemy_actor_ids_for_team(attacker_team)
                primary_defender_char = _mass_target_char(defender_actor_ids)
                primary_participant = participant_entries[0] if participant_entries else None
                primary_participant_char = primary_participant.get('char') if isinstance(primary_participant, dict) else None
                primary_participant_skill = primary_participant.get('skill_data') if isinstance(primary_participant, dict) else None
                logger.info(
                    "[resolve_mass] type=広域-合算 slot=%s 参加人数=%d attacker_power=%s defender_sum=%s outcome=%s 総和差分=%s",
                    slot_id, len(participant_slots), attacker_power, defender_sum, outcome, delta
                )

                if outcome == 'attacker_win':
                    _trigger_mass_summation_timing(
                        'END_MATCH',
                        attacker_char,
                        primary_defender_char,
                        attacker_skill_data,
                        target_skill_data=primary_participant_skill,
                        base_damage=delta,
                    )
                    for entry in participant_entries:
                        _trigger_mass_summation_timing(
                            'END_MATCH',
                            entry.get('char'),
                            attacker_char,
                            entry.get('skill_data'),
                            target_skill_data=attacker_skill_data,
                            base_damage=delta,
                        )
                    _trigger_mass_summation_timing(
                        'WIN',
                        attacker_char,
                        primary_defender_char,
                        attacker_skill_data,
                        target_skill_data=primary_participant_skill,
                        base_damage=delta,
                    )
                    for entry in participant_entries:
                        _trigger_mass_summation_timing(
                            'LOSE',
                            entry.get('char'),
                            attacker_char,
                            entry.get('skill_data'),
                            target_skill_data=attacker_skill_data,
                            base_damage=delta,
                        )
                elif outcome == 'defender_win':
                    _trigger_mass_summation_timing(
                        'END_MATCH',
                        attacker_char,
                        primary_participant_char,
                        attacker_skill_data,
                        target_skill_data=primary_participant_skill,
                        base_damage=delta,
                    )
                    for entry in participant_entries:
                        _trigger_mass_summation_timing(
                            'END_MATCH',
                            entry.get('char'),
                            attacker_char,
                            entry.get('skill_data'),
                            target_skill_data=attacker_skill_data,
                            base_damage=delta,
                        )
                    for entry in participant_entries:
                        _trigger_mass_summation_timing(
                            'WIN',
                            entry.get('char'),
                            attacker_char,
                            entry.get('skill_data'),
                            target_skill_data=attacker_skill_data,
                            base_damage=delta,
                        )
                    _trigger_mass_summation_timing(
                        'LOSE',
                        attacker_char,
                        primary_participant_char,
                        attacker_skill_data,
                        target_skill_data=primary_participant_skill,
                        base_damage=delta,
                    )
                else:
                    _trigger_mass_summation_timing(
                        'END_MATCH',
                        attacker_char,
                        primary_participant_char,
                        attacker_skill_data,
                        target_skill_data=primary_participant_skill,
                        base_damage=0,
                    )
                    for entry in participant_entries:
                        _trigger_mass_summation_timing(
                            'END_MATCH',
                            entry.get('char'),
                            attacker_char,
                            entry.get('skill_data'),
                            target_skill_data=attacker_skill_data,
                            base_damage=0,
                        )

                _apply_mass_summation_thorns(attacker_char, attacker_skill_data)
                for entry in participant_entries:
                    _apply_mass_summation_thorns(entry.get('char'), entry.get('skill_data'))

                damage_events = []
                if outcome == 'attacker_win' and delta > 0:
                    damage_events = _apply_mass_summation_delta_damage(
                        defender_actor_ids,
                        delta,
                        source_actor=attacker_char,
                        source_skill=attacker_skill_data,
                    )
                elif outcome == 'defender_win' and delta > 0:
                    damage_events = _apply_mass_summation_delta_damage(
                        [attacker_actor_id],
                        delta,
                        source_actor=primary_participant_char,
                        source_skill=primary_participant_skill,
                    )
                if outcome == 'attacker_win':
                    for evt in damage_events:
                        target_for_timing = characters_by_id.get(evt.get('target_id'))
                        _trigger_skill_timing_effects(
                            room=room,
                            state=state,
                            characters_by_id=characters_by_id,
                            timing='AFTER_DAMAGE_APPLY',
                            actor_char=attacker_char,
                            target_char=target_for_timing,
                            skill_data=attacker_skill_data,
                            target_skill_data=primary_participant_skill,
                            base_damage=int(evt.get('hp') or 0),
                            emit_source='after_damage_apply'
                        )
                elif outcome == 'defender_win':
                    actual_damage = int((damage_events[0] if damage_events else {}).get('hp') or 0)
                    for entry in participant_entries:
                        _trigger_skill_timing_effects(
                            room=room,
                            state=state,
                            characters_by_id=characters_by_id,
                            timing='AFTER_DAMAGE_APPLY',
                            actor_char=entry.get('char'),
                            target_char=attacker_char,
                            skill_data=entry.get('skill_data'),
                            target_skill_data=attacker_skill_data,
                            base_damage=actual_damage,
                            emit_source='after_damage_apply'
                        )

                if outcome == 'attacker_win':
                    winner_message = '攻撃側の勝利'
                elif outcome == 'defender_win':
                    winner_message = '防御側の勝利'
                else:
                    winner_message = '引き分け'

                summary_lines = [
                    (
                        f"<strong>{attacker_name}</strong> "
                        f"<span style='color: #d63384; font-weight: bold;'>[{skill_name}]</span> "
                        f"(<span class='dice-result-total'>{attacker_power}</span>) vs "
                        f"<strong>防御側合計</strong> "
                        f"(<span class='dice-result-total'>{defender_sum}</span>) | "
                        f"<strong> → {winner_message}</strong>"
                    ),
                    f"[mass-summation] 参加人数={len(participant_slots)} 総和差分={delta}",
                ]
                for e in damage_events:
                    target_name = _resolve_actor_name(characters_by_id, e.get('target_id'))
                    dmg_val = int(e.get('hp', 0) or 0)
                    if dmg_val > 0:
                        summary_lines.append(
                            f"<strong>{target_name}</strong> に <strong>{dmg_val}</strong> ダメージ"
                            f"<br><span style='font-size:0.9em; color:#888;'>内訳: [合計ダメージ {dmg_val}]</span>"
                        )
                _log_match_result(summary_lines)

                _append_trace(
                    room,
                    battle_id,
                    battle_state,
                    'mass_summation',
                    slot_id,
                    rolls={
                        'attacker_power': attacker_power,
                        'defender_powers': defender_powers,
                        'defender_sum': defender_sum,
                        'delta': delta
                    },
                    outcome=outcome,
                    target_actor_id=attacker_actor_id,
                    extra_fields={
                        'participants': participant_slots,
                        'damage_events': damage_events,
                        'lines': summary_lines,
                        'log_lines': summary_lines
                    }
                )

                for p_slot in participant_slots:
                    _consume_resolve_slot(battle_state, p_slot)
            else:
                participant_slots = _gather_slots_targeting_slot_s(
                    state,
                    battle_state,
                    slot_id,
                    attacker_team=attacker_team,
                    intents_override=intents
                )
                participant_by_actor = {}
                for p_slot in participant_slots:
                    actor_id = slots.get(p_slot, {}).get('actor_id')
                    if actor_id:
                        participant_by_actor[actor_id] = p_slot

                for defender_actor_id in _enemy_actor_ids_for_team(attacker_team):
                    defender_slot = participant_by_actor.get(defender_actor_id)
                    defender_intent = intents.get(defender_slot, {}) if defender_slot else {}
                    defender_skill_id = defender_intent.get('skill_id')

                    if defender_slot and defender_skill_id:
                        defender_char = characters_by_id.get(defender_actor_id)
                        defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id else None
                        clash_delegated = _resolve_clash_by_existing_logic(
                            room=room,
                            state=state,
                            attacker_char=attacker_char,
                            defender_char=defender_char,
                            attacker_skill_data=attacker_skill_data,
                            defender_skill_data=defender_skill_data
                        )
                        clash_ok = bool((clash_delegated or {}).get('ok', False))
                        clash_summary = clash_delegated.get('summary', {}) if clash_ok else {}
                        clash_outcome = clash_delegated.get('outcome', 'no_effect') if clash_ok else 'no_effect'
                        clash_notes = None if clash_ok else (
                            clash_delegated.get('reason') if isinstance(clash_delegated, dict) else 'delegate_failed'
                        )
                        forced_no_match_reason = None
                        if clash_ok:
                            forced_no_match_reason = _get_forced_clash_no_effect_reason(attacker_skill_data, defender_skill_data)
                        if forced_no_match_reason:
                            clash_summary = _sanitize_forced_no_match_clash_summary(clash_summary)
                            clash_outcome = 'no_effect'
                            clash_notes = forced_no_match_reason
                        elif clash_ok and _should_grant_clash_win_fp(attacker_skill_data, defender_skill_data, clash_outcome):
                            winner_char = attacker_char if clash_outcome == 'attacker_win' else defender_char
                            winner_skill_data = attacker_skill_data if clash_outcome == 'attacker_win' else defender_skill_data
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

                        clash_payload = {
                            'attacker_id': attacker_actor_id,
                            'target_id': defender_actor_id,
                            'skill_id': attacker_skill_id,
                            'skill': attacker_skill_data,
                            'apply_cost': False,
                            'cost_policy': COST_CONSUME_POLICY,
                            'delegate_applied': clash_ok,
                            'delegate_summary': clash_summary if clash_ok else {}
                        }
                        clash_applied = _apply_outcome_to_state(clash_payload, characters_by_id)
                        if clash_ok:
                            _emit_stat_updates_from_applied(
                                room,
                                clash_applied,
                                characters_by_id,
                                source='resolve_mass_clash'
                            )
                        legacy_input = to_legacy_duel_log_input(
                            outcome_payload=clash_payload,
                            state=state,
                            intents=intents,
                            attacker_slot=slot_id,
                            defender_slot=defender_slot,
                            applied=clash_applied,
                            kind='clash',
                            outcome=clash_outcome,
                            notes=clash_notes
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
                            room,
                            battle_id,
                            battle_state,
                            'mass_individual',
                            slot_id,
                            defender_slot=defender_slot,
                            target_actor_id=defender_actor_id,
                            notes=clash_notes,
                            outcome=clash_outcome,
                            rolls=(clash_summary.get('rolls', {}) if isinstance(clash_summary, dict) else {}),
                            cost={
                                'mp': int(clash_applied.get('cost', {}).get('mp', 0)),
                                'hp': int(clash_applied.get('cost', {}).get('hp', 0)),
                                'fp': int(clash_applied.get('cost', {}).get('fp', 0)),
                            },
                            extra_fields={
                                'resolution_kind': 'clash',
                                'outcome_payload': clash_payload,
                                'applied': clash_applied,
                                'lines': log_lines,
                                'log_lines': log_lines
                            }
                        )
                        _consume_resolve_slot(battle_state, defender_slot)
                    else:
                        _emit_mass_one_sided(
                            defender_actor_id=defender_actor_id,
                            defender_slot=defender_slot,
                            trace_kind='mass_individual'
                        )

            _consume_resolve_slot(battle_state, slot_id)

        battle_state['phase'] = 'resolve_single'
        resolve_random_intents(state, battle_state, intents)
        _build_resolve_queues(battle_state, intents_override=intents)
        phase_payload = {
            'room_id': room,
            'battle_id': battle_id,
            'round': battle_state.get('round', 0),
            'from': 'resolve_mass',
            'to': 'resolve_single'
        }
        _log_battle_emit('battle_phase_changed', room, battle_id, phase_payload)
        socketio.emit('battle_phase_changed', phase_payload, to=room)
        payload = build_select_resolve_state_payload(room, battle_id=battle_id)
        if payload:
            _log_battle_emit('battle_state_updated', room, battle_id, payload)
            socketio.emit('battle_state_updated', payload, to=room)
