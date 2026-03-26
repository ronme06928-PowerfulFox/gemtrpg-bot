import manager.battle.resolve_auto_mass_phase as _resolve_auto_mass_phase_mod
import manager.battle.resolve_auto_single_phase as _resolve_auto_single_phase_mod

def _sync_from_core():
    from manager.battle import core as core_mod
    g = globals()
    # Keep this runtime module behavior-identical to core by mirroring
    # current function bindings (including test monkeypatch targets).
    for name, value in core_mod.__dict__.items():
        if name in {"run_select_resolve_auto", "_sync_from_core"}:
            continue
        if name.startswith("__"):
            continue
        g[name] = value


def run_select_resolve_auto(room, battle_id):
    _sync_from_core()
    state = get_room_state(room)
    if not state:
        return

    from manager.battle.common_manager import ensure_battle_state_vNext
    battle_state = ensure_battle_state_vNext(state, battle_id=battle_id, round_value=state.get('round', 0))
    if not battle_state:
        return
    characters_by_id = {
        c.get('id'): c for c in state.get('characters', [])
        if isinstance(c, dict) and c.get('id')
    }

    if battle_state.get('phase') not in ['resolve_mass', 'resolve_single']:
        return

    # Ephemeral context for resolve-time power roll helpers.
    # Keep only room name to avoid serializing circular references into room state.
    battle_state['__room_name'] = room

    resolve_intents = battle_state.get('resolve_snapshot_intents')
    if not isinstance(resolve_intents, dict) or len(resolve_intents) == 0:
        resolve_intents = battle_state.get('intents', {})
    battle_state['__resolve_intents_override'] = resolve_intents

    _build_resolve_queues(battle_state, intents_override=resolve_intents)
    resolve_ctx = battle_state.setdefault('resolve', {})
    mass_steps_est = _estimate_mass_trace_steps(state, battle_state, resolve_intents)
    single_steps_est = _estimate_single_trace_steps(state, battle_state, resolve_intents)
    step_total_est = int(max(0, mass_steps_est + single_steps_est))
    trace_len = len(resolve_ctx.get('trace', []) or [])
    existing_total = _safe_int(resolve_ctx.get('step_total'), 0)
    # If trace is freshly reset, stale step_total from a previous round must not survive.
    if trace_len <= 0:
        existing_total = 0
    resolve_ctx['step_total'] = int(max(existing_total, step_total_est, trace_len))
    resolve_ctx['step_estimate'] = {
        'mass': int(mass_steps_est),
        'single': int(single_steps_est),
        'total': int(resolve_ctx['step_total']),
    }
    try:
        _apply_phase_timing_for_committed_intents(
            room=room,
            state=state,
            battle_state=battle_state,
            characters_by_id=characters_by_id,
            timing='RESOLVE_START',
            intents_override=resolve_intents
        )
    except Exception as e:
        logger.warning("[timing_effect] RESOLVE_START failed room=%s battle=%s error=%s", room, battle_id, e)

    # Phase handlers are split to keep responsibilities clear while
    # preserving the original call order and side effects.
    _resolve_auto_mass_phase_mod.run_mass_phase(
        room=room,
        battle_id=battle_id,
        state=state,
        battle_state=battle_state,
        resolve_intents=resolve_intents,
        characters_by_id=characters_by_id,
    )
    _resolve_auto_single_phase_mod.run_single_phase(
        room=room,
        battle_id=battle_id,
        state=state,
        battle_state=battle_state,
        resolve_intents=resolve_intents,
        characters_by_id=characters_by_id,
    )
    battle_state.pop('__room_state_ref__', None)
    battle_state.pop('__room_name', None)
    battle_state.pop('__resolve_intents_override', None)
    save_specific_room_state(room)



















