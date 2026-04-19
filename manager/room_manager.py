# manager/room_manager.py
import copy
import time

from extensions import socketio, active_room_states, user_sids
from manager.data_manager import read_saved_rooms, save_room_to_db
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


def _normalize_log_text(text):
    return str(text or "")


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
        all_rooms = read_saved_rooms()
        if room_name in all_rooms:
            state = all_rooms[room_name]
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

def save_specific_room_state(room_name):
    state = active_room_states.get(room_name)
    if not state: return False
    if save_room_to_db(room_name, state):
        return True
    else:
        logger.error(f"[ERROR] Auto-save failed: {room_name}")
        return False

def broadcast_state_update(room_name):
    state = get_room_state(room_name)
    if state:
        if 'character_owners' in state and 'characters' in state:
            owners = state['character_owners']
            for char in state['characters']:
                if char['id'] in owners:
                    char['owner_id'] = owners[char['id']]

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

    state['_log_seq'] += 1
    normalized_message = _normalize_log_text(message)
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
    return user_sids.get(sid, {"username": "System", "attribute": "System"})

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



def _update_char_stat(room_name, char, stat_name, new_value, is_new=False, is_delete=False, username="System", source=None, save=True):
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
                'log_message': log_message,
                'source': source
            }, to=room_name)

    if log_message and (str(old_value) != str(new_value) or is_new or is_delete):
        broadcast_log(room_name, _normalize_log_text(log_message), 'state-change', save=save)


