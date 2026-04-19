import copy
import time

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


def _bo_canonical_side(raw):
    text = str(raw or '').strip().lower()
    if text in {'ally', 'player', 'friend', 'friends'}:
        return 'ally'
    if text in {'enemy', 'foe', 'opponent', 'boss', 'npc'}:
        return 'enemy'
    return None


def _bo_safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _bo_estimate_battle_result(state):
    allies_alive = False
    enemies_alive = False
    for char in (state.get('characters') or []):
        if not isinstance(char, dict):
            continue
        side = (
            _bo_canonical_side(char.get('type'))
            or _bo_canonical_side(char.get('team'))
            or _bo_canonical_side(char.get('side'))
            or _bo_canonical_side(char.get('faction'))
        )
        hp = _bo_safe_int(char.get('hp'), 0)
        if side == 'ally' and hp > 0:
            allies_alive = True
        elif side == 'enemy' and hp > 0:
            enemies_alive = True
    if allies_alive and not enemies_alive:
        return 'ally_win'
    if enemies_alive and not allies_alive:
        return 'enemy_win'
    if not allies_alive and not enemies_alive:
        return 'draw'
    return 'in_progress'


def _bo_find_active_record(bo):
    if not isinstance(bo, dict):
        return None, None
    records = bo.get('records')
    if not isinstance(records, list):
        return None, None

    target_id = str(bo.get('active_record_id') or '').strip()
    if target_id:
        for rec in records:
            if not isinstance(rec, dict):
                continue
            if str(rec.get('id') or '').strip() == target_id:
                return rec, target_id

    for rec in reversed(records):
        if not isinstance(rec, dict):
            continue
        if str(rec.get('status') or '').strip().lower() == 'in_battle':
            return rec, str(rec.get('id') or '').strip() or None
    return None, None


def _now_iso_fallback():
    now_iso = globals().get('_now_iso')
    if callable(now_iso):
        try:
            return str(now_iso())
        except Exception:
            pass
    return str(int(time.time()))


def _maybe_finalize_battle_only_result(room, state):
    if not isinstance(state, dict):
        return None
    if str(state.get('play_mode') or 'normal').strip().lower() != 'battle_only':
        return None

    bo = state.get('battle_only')
    if not isinstance(bo, dict):
        return None

    bo_status = str(bo.get('status') or '').strip().lower()
    if bo_status and bo_status != 'in_battle':
        return None

    result = _bo_estimate_battle_result(state)
    if result == 'in_progress':
        return None

    rec, rec_id = _bo_find_active_record(bo)
    if isinstance(rec, dict):
        rec['status'] = 'finished'
        rec['result'] = result
        rec['ended_at'] = _now_iso_fallback()
        rec.setdefault('end_reason', 'auto_annihilation')
    bo['active_record_id'] = None
    bo['status'] = 'draft'
    # Defer field reset until clients finish resolve-flow playback.
    bo['pending_auto_reset'] = True
    bo['pending_auto_reset_round'] = int(state.get('round', 0) or 0)

    record_id = str((rec or {}).get('id') or '').strip() or rec_id or None
    return {
        'room': room,
        'result': result,
        'record_id': record_id,
        'record': copy.deepcopy(rec) if isinstance(rec, dict) else None,
    }


def _auto_reset_battle_only_field(room):
    try:
        from manager.battle.common_manager import reset_battle_logic
        reset_battle_logic(room, 'full', '戦闘専用モード(自動リセット)')
        return True
    except Exception:
        return False


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

    bo_result = _maybe_finalize_battle_only_result(room, state)
    save_specific_room_state(room)

    if isinstance(bo_result, dict):
        result = str(bo_result.get('result') or 'unknown')
        result_label = {
            'ally_win': 'ally_win',
            'enemy_win': 'enemy_win',
            'draw': 'draw',
        }.get(result, result)
        try:
            broadcast_log(room, f"[BattleOnly] Auto result: {result_label} (annihilation)", 'info')
        except Exception:
            pass
        try:
            socketio.emit(
                'bo_record_updated',
                {
                    'record_id': bo_result.get('record_id'),
                    'record': bo_result.get('record'),
                    'active_record_id': None,
                },
                to=room
            )
        except Exception:
            pass
        try:
            socketio.emit(
                'bo_battle_finished',
                {
                    'result': result,
                    'record_id': bo_result.get('record_id'),
                },
                to=room
            )
        except Exception:
            pass
        try:
            broadcast_log(room, "[BattleOnly] 勝敗確定。解決表示完了後に自動リセットします。", 'info')
        except Exception:
            pass
        try:
            broadcast_state_update(room)
        except Exception:
            pass
