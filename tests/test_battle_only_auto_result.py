import manager.battle.resolve_auto_runtime as runtime


def test_finalize_battle_only_result_when_enemy_wiped(monkeypatch):
    monkeypatch.setattr(runtime, '_now_iso_fallback', lambda: '2026-04-18T00:00:00+09:00')
    state = {
        'play_mode': 'battle_only',
        'battle_only': {
            'status': 'in_battle',
            'active_record_id': 'bor_1',
            'records': [
                {
                    'id': 'bor_1',
                    'status': 'in_battle',
                    'result': None,
                    'ended_at': None,
                }
            ],
        },
        'characters': [
            {'id': 'a1', 'type': 'ally', 'hp': 12},
            {'id': 'e1', 'type': 'enemy', 'hp': 0},
        ],
    }

    row = runtime._maybe_finalize_battle_only_result('room_t', state)

    assert isinstance(row, dict)
    assert row.get('result') == 'ally_win'
    assert row.get('record_id') == 'bor_1'
    assert state['battle_only']['status'] == 'draft'
    assert state['battle_only']['active_record_id'] is None
    assert state['battle_only']['pending_auto_reset'] is True

    rec = state['battle_only']['records'][0]
    assert rec.get('status') == 'finished'
    assert rec.get('result') == 'ally_win'
    assert rec.get('ended_at') == '2026-04-18T00:00:00+09:00'


def test_finalize_battle_only_result_keeps_in_progress_when_both_alive():
    state = {
        'play_mode': 'battle_only',
        'battle_only': {
            'status': 'in_battle',
            'active_record_id': 'bor_1',
            'records': [
                {
                    'id': 'bor_1',
                    'status': 'in_battle',
                    'result': None,
                    'ended_at': None,
                }
            ],
        },
        'characters': [
            {'id': 'a1', 'type': 'ally', 'hp': 12},
            {'id': 'e1', 'type': 'enemy', 'hp': 8},
        ],
    }

    row = runtime._maybe_finalize_battle_only_result('room_t', state)

    assert row is None
    assert state['battle_only']['status'] == 'in_battle'
    assert state['battle_only']['active_record_id'] == 'bor_1'
    rec = state['battle_only']['records'][0]
    assert rec.get('status') == 'in_battle'
    assert rec.get('result') is None
