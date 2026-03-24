# manager/room_manager.py
import time
import re

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

_MOJIBAKE_TEXT_REPLACEMENTS = {
    "蜃ｺ陦": "出血",
    "遐ｴ陬・": "亀裂",
    "莠陬・": "破裂",
    "謌ｦ諷・": "戦慄",
    "闕頑｣・": "荊棘",
    "豺ｷ荵ｱ": "混乱",
    "騾溷ｺｦ": "速度",
    "陦悟虚": "行動",
    "邨ゆｺ・凾": "終了時",
    "驍ｨ繧・ｽｺ繝ｻ蜃ｾ": "終了時",
    "繝ｩ繧ｦ繝ｳ繝臥ｵゆｺ・・繝ｼ繝翫せ": "ラウンド終了ボーナス",
}


def _normalize_log_text(text):
    value = str(text or "")
    for src, dst in _MOJIBAKE_TEXT_REPLACEMENTS.items():
        value = value.replace(src, dst)
    value = value.replace("陦悟虚鬆・′豎ｺ縺ｾ繧翫∪縺励◆:", "行動順が決まりました:")
    value = re.sub(
        r"---\s*(.+?)\s*縺・Round\s*(\d+)\s*繧帝幕蟋九＠縺ｾ縺励◆\s*---",
        r"--- \1 が Round \2 を開始しました ---",
        value,
    )
    value = re.sub(
        r"---\s*(.+?)\s*縺・Round\s*(\d+)\s*縺ｮ邨ゆｺ・・逅・ｒ螳溯｡後＠縺ｾ縺励◆\s*---",
        r"--- \1 が Round \2 の終了処理を実行しました ---",
        value,
    )
    value = re.sub(r"\[(\d+)R(?:終了時|邨ゆｺ・凾|驍ｨ繧・ｽｺ繝ｻ蜃ｾ)\]", r"[\1R終了時]", value)
    return value


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


            # 笘・霑ｽ蜉: 繝輔ぅ繝ｼ繝ｫ繝芽｣懷ｮ・
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
                # 笘・霑ｽ蜉: 繝槭ャ繝苓ｨｭ螳壹ョ繝ｼ繧ｿ
                "map_data": {
                    "width": 20,
                    "height": 15,
                    "gridSize": 64,
                    "backgroundImage": None
                },
                # 笘・霑ｽ蜉: 繧ｭ繝｣繝ｩ繧ｯ繧ｿ繝ｼ謇譛画ｨｩ繝槭ャ繝・
                "character_owners": {},
                # 笘・霑ｽ蜉: 繝槭ャ繝∫憾諷狗ｮ｡逅・
                "active_match": {
                    "is_active": False,
                    "match_type": None,
                    "attacker_id": None,
                    "defender_id": None,
                    "targets": [],
                    "attacker_data": {},
                    "defender_data": {},
                },
                # 笘・霑ｽ蜉: 謗｢邏｢繝｢繝ｼ繝臥憾諷・
                "mode": "battle",
                "exploration": {
                    "backgroundImage": None,
                    "tachie_locations": {}
                },
                # 笘・霑ｽ蜉: PvE繝｢繝ｼ繝・
                "battle_mode": 'pvp',
                "ai_target_arrows": []
            }
            active_room_states[room_name] = state

    # 笘・霑ｽ蜉: 譌｢蟄倥Ν繝ｼ繝縺ｧ character_owners 繧・active_match 縺後↑縺・ｴ蜷医・蛻晄悄蛹・
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
    # 笘・霑ｽ蜉: PvE繝｢繝ｼ繝牙・譛溷喧
    if 'battle_mode' not in state:
        state['battle_mode'] = 'pvp'
    if 'ai_target_arrows' not in state:
        state['ai_target_arrows'] = []
    # 笘・霑ｽ蜉: 謗｢邏｢繝｢繝ｼ繝臥憾諷九・蛻晄悄蛹・
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


    try:
        room_db = Room.query.filter_by(name=room_name).first()
        if room_db:
            state['owner_id'] = room_db.owner_id
    except Exception as e:
        logger.error(f"Error fetching owner_id: {e}")

    # 笘・Phase 13: 讓ｩ髯舌メ繧ｧ繝・け謨ｴ蜷域ｧ縺ｮ縺溘ａ縲｛wner_id 繧呈ｳｨ蜈･
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
        # 笘・Phase 13: 讓ｩ髯舌メ繧ｧ繝・け縺ｮ縺溘ａ縺ｫ owner_id 繧偵く繝｣繝ｩ繧ｯ繧ｿ繝・・繧ｿ縺ｫ豕ｨ蜈･
        # (豕ｨ: get_room_state蜀・〒繧よｳｨ蜈･縺輔ｌ繧九′縲∝ｿｵ縺ｮ縺溘ａ莠碁㍾繝√ぉ繝・け)
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

# 笆ｼ笆ｼ笆ｼ 菫ｮ豁｣邂・園: secret 蠑墓焚蟇ｾ蠢懃沿縺ｮ縺ｿ縺ｫ縺吶ｋ 笆ｼ笆ｼ笆ｼ
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
                "username": info.get('username', '荳肴・'),
                "attribute": info.get('attribute', 'Player'),
                "user_id": info.get('user_id')
            })
    user_list.sort(key=lambda x: x['username'])
    _safe_emit('user_list_updated', user_list, to=room_name)

def get_user_info_from_sid(sid):
    return user_sids.get(sid, {"username": "System", "attribute": "System"})

def is_authorized_for_character(room_name, char_id, username, attribute):
    """Return whether a user can control a character in the given room."""
    # GM縺ｯ蟶ｸ縺ｫ讓ｩ髯舌≠繧・
    if attribute == 'GM':
        return True

    # 謇譛芽・メ繧ｧ繝・け
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
        # 笘・HP縺・縺ｫ縺ｪ縺｣縺溘ｉ閾ｪ蜍慕噪縺ｫ譛ｪ驟咲ｽｮ・域姶髣倅ｸ崎・・峨↓縺吶ｋ
        if char['hp'] <= 0:
            char['x'] = -1; char['y'] = -1
            log_message += " [戦闘不能/未配置へ移動]"
            # 笘・霑ｽ蜉: 豁ｻ莠｡譎ゅう繝吶Φ繝医ヵ繝・け
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
        # 笘・霑ｽ蜉: 逕ｻ蜒酋RL譖ｴ譁ｰ
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
        # 笘・霑ｽ蜉: 繧ｹ繧ｭ繝ｫ陦ｨ遉ｺ險ｭ螳壽峩譁ｰ
        # new_value 縺ｯ繝ｪ繧ｹ繝医∪縺溘・迚ｹ螳壹・謫堺ｽ懃畑霎樊嶌繧呈Φ螳・
        # 繧ｷ繝ｳ繝励Ν縺ｫ繝ｪ繧ｹ繝亥・鄂ｮ謠帙〒蟇ｾ蠢・
        char['hidden_skills'] = new_value
        log_message = "" # 鬆ｻ郢√↑蛻・ｊ譖ｿ縺医〒繝ｭ繧ｰ縺悟沂縺ｾ繧九・繧帝亟縺舌◆繧√√≠縺医※繝ｭ繧ｰ縺ｯ蜃ｺ縺輔↑縺・°縲√ョ繝舌ャ繧ｰ縺ｮ縺ｿ縺ｫ縺吶ｋ
        # log_message = f"{username}: {char['name']}: 繧ｹ繧ｭ繝ｫ陦ｨ遉ｺ險ｭ螳壹ｒ譖ｴ譁ｰ"
    elif stat_name == 'flags':
        # 笘・霑ｽ蜉: 豎守畑繝輔Λ繧ｰ譖ｴ譁ｰ
        char['flags'] = new_value
        log_message = "" # 繝ｭ繧ｰ荳崎ｦ・
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
        # 笘・霑ｽ蜉: params縺ｫ繧ょｭ伜惠縺吶ｋ蝣ｴ蜷医√◎縺｡繧峨ｒ蜆ｪ蜈医☆繧・(get/set_status_value縺ｮ謖吝虚縺ｫ蜷医ｏ縺帙ｋ)
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

    # 笘・蟾ｮ蛻・峩譁ｰ繧､繝吶Φ繝磯∽ｿ｡・・P/MP/迥ｶ諷句､縺ｮ縺ｿ縲∫判蜒上ｄ濶ｲ縺ｯ髯､螟厄ｼ・
    if str(old_value) != str(new_value):
        # 逕ｻ蜒上ｄ濶ｲ縺ｮ螟画峩譎ゅ・繝輔Ο繝ｼ繝・ぅ繝ｳ繧ｰ繝・く繧ｹ繝医ｒ陦ｨ遉ｺ縺励↑縺・◆繧√√う繝吶Φ繝磯∽ｿ｡繧偵せ繧ｭ繝・・
        should_emit_stat_update = stat_name in ['HP', 'MP'] or (stat_name not in ['image', 'imageOriginal', 'color', 'gmOnly'])

        if should_emit_stat_update:
            # max_value繧貞叙蠕暦ｼ・P/MP縺ｮ蝣ｴ蜷茨ｼ・
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
                'source': source  # 笘・霑ｽ蜉: 繝繝｡繝ｼ繧ｸ逋ｺ逕滓ｺ・
            }, to=room_name)

    if log_message and (str(old_value) != str(new_value) or is_new or is_delete):
        broadcast_log(room_name, _normalize_log_text(log_message), 'state-change', save=save)


