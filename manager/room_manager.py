# manager/room_manager.py
import atexit
import copy
import json
import os
import time

from flask import current_app

# パフォーマンス計測（PERF_LOG=1 のときのみ state_updated のペイロードサイズを出力）
_PERF_LOG = os.environ.get('PERF_LOG') == '1'

from extensions import socketio, active_room_states, user_sids
from manager.data_manager import read_saved_room, save_room_to_db
from manager.utils import (
    set_status_value, get_status_value, apply_buff, remove_buff,
    normalize_status_name, normalize_character_labels,
)
from models import Room
from manager.game_logic import process_on_death
from manager.logs import setup_logger

try:
    from manager.utils import get_effective_origin_id
except Exception:
    def get_effective_origin_id(_char):
        return 0

logger = setup_logger(__name__)


def _default_battle_only_state():
    return {
        "status": "lobby",
        "ally_entries": [],
        "enemy_entries": [],
        "records": [],
        "active_record_id": None,
        "pending_auto_reset": False,
        "pending_auto_reset_round": None,
    }

def _ensure_battle_only_defaults(state):
    if not isinstance(state, dict):
        return

    play_mode = str(state.get('play_mode', 'normal') or 'normal').strip().lower()
    if play_mode not in ('normal', 'battle_only'):
        play_mode = 'normal'
    state['play_mode'] = play_mode

    bo_default = _default_battle_only_state()
    battle_only = state.get('battle_only')
    if not isinstance(battle_only, dict):
        battle_only = {}
        state['battle_only'] = battle_only

    for k, v in bo_default.items():
        if k not in battle_only:
            battle_only[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v

    battle_only['status'] = str(battle_only.get('status', 'lobby') or 'lobby').strip().lower()
    if battle_only['status'] not in ('lobby', 'draft', 'in_battle'):
        battle_only['status'] = 'lobby'

    if not isinstance(battle_only.get('ally_entries'), list):
        battle_only['ally_entries'] = []
    if not isinstance(battle_only.get('enemy_entries'), list):
        battle_only['enemy_entries'] = []
    if not isinstance(battle_only.get('records'), list):
        battle_only['records'] = []

    if 'stage_field_effect_enabled' not in battle_only:
        battle_only['stage_field_effect_enabled'] = True
    if 'stage_avatar_enabled' not in battle_only:
        battle_only['stage_avatar_enabled'] = True
    if not isinstance(battle_only.get('stage_field_effect_profile'), dict):
        battle_only['stage_field_effect_profile'] = {}
    if not isinstance(battle_only.get('stage_avatar_profile'), dict):
        battle_only['stage_avatar_profile'] = {}

    # Top-level stage fields are runtime-only. If a battle-only room is restored
    # outside an active battle, remove stale runtime data so cards/effects do not
    # resurrect after reset, reconnect, or page reload.
    if play_mode == 'battle_only' and battle_only['status'] != 'in_battle':
        state['field_effects'] = []
        state['stage_field_effect_profile'] = {}
        state['stage_field_effect_enabled'] = False
        state['stage_avatar_profile'] = {}
        state['stage_avatar_enabled'] = False


def _normalize_log_text(text):
    return str(text or "")


def _is_bleed_state_change_log(text):
    msg = str(text or "")
    if not msg.startswith("["):
        return False
    return "\u51fa\u8840 (" in msg


def _safe_emit(event_name, payload, **kwargs):
    emit_fn = getattr(socketio, "emit", None)
    if callable(emit_fn):
        try:
            emit_fn(event_name, payload, **kwargs)
        except Exception:
            return


def _log_battle_emit(event_name, room_id, battle_id, payload):
    payload = payload or {}
    timeline_len = len(payload.get('timeline', []) or [])
    slots_len = len(payload.get('slots', {}) or {})
    intents_len = len(payload.get('intents', {}) or {})
    trace_len = len(payload.get('trace', []) or [])
    phase = payload.get('phase') or payload.get('to') or payload.get('from')
    logger.debug(
        "[EMIT] %s room=%s battle=%s phase=%s timeline=%d slots=%d intents=%d trace=%d",
        event_name, room_id, battle_id, phase, timeline_len, slots_len, intents_len, trace_len
    )


def emit_select_resolve_events(room_name, to_sid=None, include_round_started=False):
    """
    Emit select/resolve snapshot events to the same namespace/room path as state_updated.
    This is additive and keeps legacy state_updated flow intact.
    """
    state = get_room_state(room_name)
    if not state:
        return

    try:
        from manager.battle.common_manager import ensure_battle_state_vNext, build_select_resolve_state_payload
    except Exception as e:
        logger.error(f"emit_select_resolve_events import failed room={room_name}: {e}")
        return

    battle_id = f"battle_{room_name}"
    battle_state = ensure_battle_state_vNext(
        state,
        battle_id=battle_id,
        round_value=state.get('round', 0)
    )
    if not battle_state:
        return

    battle_id = battle_state.get('battle_id') or battle_id
    target = to_sid if to_sid else room_name

    timeline = battle_state.get('timeline', []) or []
    if not timeline:
        room_timeline = state.get('timeline', [])
        if room_timeline and isinstance(room_timeline[0], dict):
            timeline = [
                e.get('id') for e in room_timeline
                if e.get('id') in battle_state.get('slots', {})
            ]
        elif room_timeline and isinstance(room_timeline[0], str):
            timeline = [sid for sid in room_timeline if sid in battle_state.get('slots', {})]
    if not timeline:
        slots = battle_state.get('slots', {})
        timeline = sorted(
            slots.keys(),
            key=lambda sid: (-int(slots.get(sid, {}).get('initiative', 0)), str(sid))
        )
    battle_state['timeline'] = timeline

    if include_round_started:
        round_started_payload = {
            'room_id': room_name,
            'battle_id': battle_id,
            'round': battle_state.get('round', state.get('round', 0)),
            'phase': battle_state.get('phase', 'select'),
            'slots': battle_state.get('slots', {}),
            'timeline': timeline,
            'tiebreak': battle_state.get('tiebreak', [])
        }
        _log_battle_emit('battle_round_started', room_name, battle_id, round_started_payload)
        _safe_emit('battle_round_started', round_started_payload, to=target)

    payload = build_select_resolve_state_payload(room_name, battle_id=battle_id)
    if not payload:
        return

    # Add timeline/tiebreak for easier client-side synchronization/debug.
    payload['timeline'] = timeline
    payload['tiebreak'] = battle_state.get('tiebreak', [])

    _log_battle_emit('battle_state_updated', room_name, battle_id, payload)
    _safe_emit('battle_state_updated', payload, to=target)


def get_room_state(room_name):
    if room_name in active_room_states:
        state = active_room_states[room_name]
    else:
        room_data = read_saved_room(room_name)
        if isinstance(room_data, dict):
            state = room_data
            if 'logs' not in state:
                state['logs'] = []
            if '_log_seq' not in state:
                state['_log_seq'] = len(state['logs'])


            if 'active_match' not in state:
                state['active_match'] = {
                    "is_active": False,
                    "match_type": None,
                    "attacker_id": None, "defender_id": None,
                    "targets": [],
                    "attacker_data": {}, "defender_data": {}
                }
            if 'character_owners' not in state:
                state['character_owners'] = {}

            active_room_states[room_name] = state
        else:
            state = {
                "characters": [],
                "timeline": [],
                "round": 0,
                "logs": [],
                "_log_seq": 0,
                "battle_state": {},
                "map_data": {
                    "width": 20,
                    "height": 15,
                    "gridSize": 64,
                    "backgroundImage": None
                },
                "character_owners": {},
                "active_match": {
                    "is_active": False,
                    "match_type": None,
                    "attacker_id": None,
                    "defender_id": None,
                    "targets": [],
                    "attacker_data": {},
                    "defender_data": {},
                },
                "mode": "battle",
                "exploration": {
                    "backgroundImage": None,
                    "tachie_locations": {}
                },
                "battle_mode": 'pvp',
                "ai_target_arrows": []
            }
            active_room_states[room_name] = state

    if 'character_owners' not in state:
        state['character_owners'] = {}
    if 'active_match' not in state:
        state['active_match'] = {
            "is_active": False,
            "match_type": None,
            "attacker_id": None,
            "defender_id": None,
            "targets": [],
            "attacker_data": {},
            "defender_data": {},
        }
    if 'battle_mode' not in state:
        state['battle_mode'] = 'pvp'
    if 'ai_target_arrows' not in state:
        state['ai_target_arrows'] = []
    if 'mode' not in state:
        state['mode'] = 'battle'  # default is battle
    if 'exploration' not in state:
        state['exploration'] = {
            'backgroundImage': None,
            'tachie_locations': {}  # char_id -> {x, y, scale}
        }
    if 'battle_state' not in state:
        state['battle_state'] = {}
    if '_log_seq' not in state:
        state['_log_seq'] = len(state.get('logs', []))

    _ensure_battle_only_defaults(state)


    try:
        room_db = Room.query.filter_by(name=room_name).first()
        if room_db:
            state['owner_id'] = room_db.owner_id
    except Exception as e:
        logger.error(f"Error fetching owner_id: {e}")

    if 'character_owners' in state and 'characters' in state:
        owners = state['character_owners']
        for char in state['characters']:
            if char['id'] in owners:
                char['owner_id'] = owners[char['id']]

    try:
        from manager.battle.common_manager import ensure_battle_state_vNext
        ensure_battle_state_vNext(state, round_value=state.get('round', 0))
    except Exception as e:
        logger.error(f"battle_state ensure failed for room={room_name}: {e}")

    # Normalize legacy mojibake labels in-memory so clients receive canonical names.
    for char in state.get('characters', []):
        normalize_character_labels(char)
    return state

# === ▼▼▼ DB保存のデバウンス（ライトビハインド） ▼▼▼ ===
# アクション毎にルーム全状態をDBへ同期コミットすると、eventlet単一ワーカー上で
# 書込のたびに他リクエストが待たされる。短い間隔で発生する保存要求をまとめ、
# 1回のコミットに集約する。in-memoryの active_room_states が常に真実なので、
# 永続化が数秒遅れても読み取り(get_room_state)の整合性は保たれる。
_SAVE_DEBOUNCE_SECONDS = 2.0
_dirty_rooms = set()
_flush_scheduled = False
_app_ref = None


def _resolve_app():
    """DB操作に使うFlaskアプリを返す。確保できなければNone。"""
    if _app_ref is not None:
        return _app_ref
    try:
        return current_app._get_current_object()
    except RuntimeError:
        return None


def discard_pending_save(room_name):
    """保留中の保存要求を破棄する（ルーム削除時など）。

    削除後にフラッシュが走って save_room_to_db でルームを復活させるのを防ぐ。
    """
    _dirty_rooms.discard(room_name)


def _flush_dirty_rooms_once():
    """現在ダーティなルームをまとめてDBへ書き込む（要app_context）。"""
    rooms = list(_dirty_rooms)
    _dirty_rooms.difference_update(rooms)
    for room_name in rooms:
        state = active_room_states.get(room_name)
        if state is None:
            # 削除済み等。復活させない。
            continue
        # update_only=True: 存在しないルームは作らない（削除直後の復活防止）。
        # 失敗時に再登録すると存在しないルームで無限ループするため再登録しない
        # （次のユーザー操作で再度ダーティになるので取りこぼしは実害が小さい）。
        if not save_room_to_db(room_name, state, update_only=True):
            logger.error(f"[ERROR] Auto-save skipped/failed: {room_name}")


def _flush_within_context():
    """app_contextを確保してフラッシュする。確保できなければスキップ。"""
    app = _resolve_app()
    if app is None:
        # アプリコンテキストが無い環境（テスト/シャットダウン後など）では
        # 永続化できないため安全にスキップする。本番のソケット/HTTP処理は
        # 常にコンテキスト内で save を呼ぶため _app_ref は捕捉済み。
        return False
    with app.app_context():
        _flush_dirty_rooms_once()
    return True


def _flush_worker():
    global _flush_scheduled
    try:
        socketio.sleep(_SAVE_DEBOUNCE_SECONDS)
        _flush_within_context()
    except Exception as e:
        logger.error(f"[ERROR] debounced flush worker failed: {e}")
    finally:
        _flush_scheduled = False
    # フラッシュ中(yield中)に積まれた新たな保存要求があれば再スケジュール
    if _dirty_rooms:
        _schedule_flush()


def _schedule_flush():
    global _flush_scheduled
    if _flush_scheduled:
        return
    _flush_scheduled = True
    try:
        socketio.start_background_task(_flush_worker)
    except Exception as e:
        # バックグラウンド起動に失敗した場合は同期保存にフォールバック
        _flush_scheduled = False
        logger.error(f"[ERROR] could not schedule flush, saving inline: {e}")
        _flush_within_context()


def flush_pending_saves():
    """保留中の保存を即時に同期フラッシュする（シャットダウン時等）。"""
    if not _dirty_rooms:
        return
    try:
        _flush_within_context()
    except Exception:
        # シャットダウン中はロギングのストリームが閉じている場合があるため握り潰す
        pass


atexit.register(flush_pending_saves)


def save_specific_room_state(room_name):
    """ルーム状態の永続化を要求する（デバウンスして後でまとめて保存）。"""
    global _app_ref
    state = active_room_states.get(room_name)
    if not state:
        return False
    if _app_ref is None:
        try:
            _app_ref = current_app._get_current_object()
        except RuntimeError:
            _app_ref = None
    _dirty_rooms.add(room_name)
    _schedule_flush()
    return True
# === ▲▲▲ DB保存のデバウンスここまで ▲▲▲ ===

def broadcast_state_update(room_name):
    state = get_room_state(room_name)
    if state:
        if 'character_owners' in state and 'characters' in state:
            owners = state['character_owners']
            for char in state['characters']:
                if char['id'] in owners:
                    char['owner_id'] = owners[char['id']]

        if _PERF_LOG:
            try:
                size = len(json.dumps(state, ensure_ascii=False, default=str))
                logger.info(
                    "[PERF] state_updated room=%s size=%dB logs=%d chars=%d",
                    room_name, size, len(state.get('logs', [])), len(state.get('characters', [])),
                )
            except Exception:
                pass

        _safe_emit('state_updated', state, to=room_name)

        # Additive emit for new Select->Resolve flow (same room path as legacy state_updated).
        try:
            emit_select_resolve_events(room_name, include_round_started=False)
        except Exception as e:
            logger.error(f"emit_select_resolve_events failed room={room_name}: {e}")

def broadcast_log(room_name, message, type='info', user=None, secret=False, save=True):
    """Append and broadcast a log entry for the room."""
    state = get_room_state(room_name)
    if 'logs' not in state:
        state['logs'] = []
    if '_log_seq' not in state:
        state['_log_seq'] = len(state['logs'])

    normalized_message = _normalize_log_text(message)
    if type == 'state-change' and _is_bleed_state_change_log(normalized_message):
        last = state['logs'][-1] if state['logs'] else None
        if isinstance(last, dict):
            if str(last.get('type') or '') == 'state-change' and str(last.get('message') or '') == normalized_message:
                return

    state['_log_seq'] += 1
    log_data = {
        "log_id": state['_log_seq'],
        "timestamp": int(time.time() * 1000),
        "message": normalized_message,
        "type": type,
        "secret": secret
    }
    if user:
        log_data["user"] = _normalize_log_text(user)

    state['logs'].append(log_data)

    if len(state['logs']) > 500:
        state['logs'] = state['logs'][-500:]

    _safe_emit('new_log', log_data, to=room_name)

    if save:
        save_specific_room_state(room_name)

def broadcast_user_list(room_name):
    if not room_name: return
    user_list = []
    for sid, info in user_sids.items():
        if info.get('room') == room_name:
            user_list.append({
                "username": info.get('username', '不明'),
                "attribute": info.get('attribute', 'Player'),
                "user_id": info.get('user_id')
            })
    user_list.sort(key=lambda x: x['username'])
    _safe_emit('user_list_updated', user_list, to=room_name)

def get_user_info_from_sid(sid):
    info = user_sids.get(sid)
    if not info:
        return {"username": "System", "attribute": "System"}
    # Phase 5 cutover: 権限の正本は membership。GM相当(attribute='GM')かどうかを
    # 毎回 membership から再解決して上書きする（キャッシュのドリフトを防ぐ）。
    # membership が無い場合（移行期・GM PIN直後の作成失敗等）はキャッシュ値を保つ
    # ＝降格しない。これが全socketイベントのGM判定の単一チョークポイント。
    from manager.room_access import get_membership_role, GM_ROLES
    room = info.get('room')
    uid = info.get('user_id')
    if room and uid:
        role = get_membership_role(uid, room)
        if role is not None:
            info['attribute'] = 'GM' if role in GM_ROLES else 'Player'
    return info

def is_authorized_for_character(room_name, char_id, username, attribute):
    """Return whether a user can control a character in the given room."""
    if attribute == 'GM':
        return True

    state = get_room_state(room_name)
    owners = state.get('character_owners', {})
    return owners.get(char_id) == username

def set_character_owner(room_name, char_id, username):
    """Set ownership of a character."""
    state = get_room_state(room_name)
    if 'character_owners' not in state:
        state['character_owners'] = {}
    state['character_owners'][char_id] = username
    save_specific_room_state(room_name)


def get_users_in_room(room_name):
    """Return active users currently in the specified room."""
    room_users = {}
    for sid, info in user_sids.items():
        if info.get('room') == room_name:
            room_users[sid] = info
    return room_users



def _update_char_stat(room_name, char, stat_name, new_value, is_new=False, is_delete=False, username="System", source=None, save=True, suppress_log=False):
    stat_name = normalize_status_name(stat_name)
    normalize_character_labels(char)
    username = _normalize_log_text(username)
    old_value = None
    log_message = ""

    if stat_name == 'HP':
        old_value = char['hp']
        try:
            numeric_new = int(float(new_value))
        except Exception:
            numeric_new = 0
        max_hp = int(char.get('maxHp', 0) or 0)
        clamped_hp = max(0, numeric_new)
        if max_hp > 0:
            clamped_hp = min(clamped_hp, max_hp)
        char['hp'] = clamped_hp
        new_value = char['hp']
        log_message = f"{username}: {char['name']}: HP ({old_value}) -> ({char['hp']})"
        if char['hp'] <= 0:
            char['x'] = -1; char['y'] = -1
            log_message += " [戦闘不能/未配置へ移動]"
            try:
                process_on_death(room_name, char, username)
            except Exception as e:
                logger.error(f"[ERROR] process_on_death failed: {e}")
    elif stat_name == 'MP':
        old_value = char['mp']
        try:
            numeric_new = int(float(new_value))
        except Exception:
            numeric_new = 0
        max_mp = int(char.get('maxMp', 0) or 0)
        clamped_mp = max(0, numeric_new)
        if max_mp > 0:
            clamped_mp = min(clamped_mp, max_mp)
        char['mp'] = clamped_mp
        new_value = char['mp']
        log_message = f"{username}: {char['name']}: MP ({old_value}) -> ({char['mp']})"
    elif stat_name == 'gmOnly':
        old_value = char.get('gmOnly', False)
        char['gmOnly'] = new_value
        new_status_str = "GMのみ" if new_value else "全員"
        log_message = f"{username}: {char['name']}: 公開設定 -> ({new_status_str})"
    elif stat_name == 'color':
        char['color'] = new_value
    elif stat_name == 'image':
        old_value = char.get('image')
        char['image'] = new_value
        old_value = char.get('image')
        char['image'] = new_value
        log_message = f"{username}: {char['name']}: 立ち絵画像を更新しました"
    elif stat_name == 'imageOriginal':
        old_value = char.get('imageOriginal')
        char['imageOriginal'] = new_value
        log_message = f"{username}: {char['name']}: 元画像を更新しました"
    elif stat_name == 'hidden_skills':
        char['hidden_skills'] = new_value
        log_message = ""
    elif stat_name == 'flags':
        char['flags'] = new_value
        log_message = ""
    elif is_new:
        char['states'].append({"name": stat_name, "value": new_value})
        log_message = f"{username}: {char['name']}: {stat_name} (なし) -> ({new_value})"
    elif is_delete:
        state = next((s for s in char['states'] if s.get('name') == stat_name), None)
        if state:
            old_value = state['value']
            char['states'] = [s for s in char['states'] if s.get('name') != stat_name]
            log_message = f"{username}: {char['name']}: {stat_name} ({old_value}) -> (削除)"
    else:
        state = next((s for s in char['states'] if s.get('name') == stat_name), None)
        param = next((p for p in char.get('params', []) if p.get('label') == stat_name), None)

        if param:
             try: old_value = int(param.get('value', 0))
             except: old_value = param.get('value')
             set_status_value(char, stat_name, new_value)
             new_val_from_logic = get_status_value(char, stat_name)
             log_message = f"{username}: {char['name']}: {stat_name} ({old_value}) -> ({new_val_from_logic})"
        elif state:
            old_value = state['value']
            set_status_value(char, stat_name, new_value)
            new_val_from_logic = get_status_value(char, stat_name)
            log_message = f"{username}: {char['name']}: {stat_name} ({old_value}) -> ({new_val_from_logic})"
        elif not state and stat_name not in ['HP', 'MP']:
            set_status_value(char, stat_name, new_value)
            log_message = f"{username}: {char['name']}: {stat_name} (なし) -> ({new_value})"

    if str(old_value) != str(new_value):
        should_emit_stat_update = stat_name in ['HP', 'MP'] or (stat_name not in ['image', 'imageOriginal', 'color', 'gmOnly'])

        if should_emit_stat_update:
            max_value = None
            if stat_name == 'HP':
                max_value = char.get('maxHp', 0)
            elif stat_name == 'MP':
                max_value = char.get('maxMp', 0)

            _safe_emit('char_stat_updated', {
                'room': room_name,
                'char_id': char['id'],
                'stat': stat_name,
                'new_value': new_value,
                'old_value': old_value,
                'max_value': max_value,
                'log_message': None if suppress_log else log_message,
                'source': source
            }, to=room_name)

    if (not suppress_log) and log_message and (str(old_value) != str(new_value) or is_new or is_delete):
        broadcast_log(room_name, _normalize_log_text(log_message), 'state-change', save=save)


