"""Private, memory-only rooms. Reserved names never fall through to persistence."""
from copy import deepcopy
from threading import RLock
from time import monotonic
from uuid import uuid4

from extensions import active_room_states, socketio, user_sids

PREFIX='__practice__:'
registry={}
_lock=RLock()
_reaper_running=False


def is_practice(name):
    return isinstance(name,str) and name.startswith(PREFIX)


def owner(name):
    return registry.get(name,{}).get('owner_id')


def drop(name):
    with _lock:
        record=registry.pop(name,None)
        if record is None:
            return
        from manager.room_manager import discard_pending_save
        from manager.battle.common_manager import _ROUND_TRANSITION_LOCKS, _ROUND_TRANSITION_LOCKS_GUARD
        discard_pending_save(name)
        active_room_states.pop(name,None)
        with _ROUND_TRANSITION_LOCKS_GUARD:
            _ROUND_TRANSITION_LOCKS.pop(name,None)
        for info in list(user_sids.values()):
            if info.get('room')==name:
                info.update(room=None,attribute='Player')
        if socketio.server is not None:
            socketio.close_room(name,namespace='/')


def expire(now=None):
    now=monotonic() if now is None else now
    with _lock:
        for name,record in list(registry.items()):
            if record.get('expires_at') is not None and now>=record['expires_at']:
                drop(name)


def _reap():
    global _reaper_running
    while True:
        socketio.sleep(5)
        expire()
        with _lock:
            if not registry:
                _reaper_running=False
                return


def detached(name,now=None):
    with _lock:
        if name in registry and not any(info.get('room')==name for info in list(user_sids.values())):
            registry[name]['expires_at']=(monotonic() if now is None else now)+60


def joined(name):
    with _lock:
        if name not in registry:
            raise ValueError('練習用のルームがありません。選び直してください。')
        registry[name]['expires_at']=None
    if active_room_states[name].get('round',0)==0:
        start_round(name)


def start_round(name):
    from manager.battle.common_manager import process_round_start
    state=active_room_states[name]
    if state.get('round',0)==0:
        from manager.game_logic import process_battle_start
        process_battle_start(name,[char for char in state['characters'] if char.get('hp',0)>0])
    return process_round_start(name,'演習場')


def _set_mode(state,mode):
    state['practice']['opponent_mode']=mode
    state['battle_mode']='pve' if mode=='auto' else 'pvp'
    for char in state['characters']:
        if char.get('type')=='enemy':
            char.setdefault('flags',{}).update(auto_target_select=mode=='auto',auto_skill_select=mode=='auto')


def create(user,selection,characters,mode='manual'):
    global _reaper_running
    name=PREFIX+user.id
    with _lock:
        drop(name)
        for index,char in enumerate(characters):
            char.update(id='practice_'+str(index),type='ally' if index==0 else 'enemy',
                        owner=user.name,owner_id=user.id,x=10 if index==0 else 14,y=12)
            # A selected enemy is operated by the same owner in manual mode.
            char.setdefault('flags',{})['auto_target_select']=False
        state={'characters':characters,'character_owners':{char['id']:user.name for char in characters},
               'owner_id':user.id,'timeline':[],'round':0,'logs':[],'mode':'battle','play_mode':'normal',
               'battle_mode':'pve' if mode=='auto' else 'pvp',
               'battle_map_data':{'background_image':'/static/images/backgrounds/暗い遺跡洞窟.png'},
               'practice':{'instance_id':uuid4().hex,'selection':deepcopy(selection),'opponent_mode':mode}}
        from manager.battle.combat_session import ensure_combat_session_defaults, start_combat_session
        _set_mode(state,mode)
        ensure_combat_session_defaults(state,new_room=True)
        start_combat_session(state,user.name)
        registry[name]={'owner_id':user.id,'initial':deepcopy(state),'expires_at':monotonic()+60}
        active_room_states[name]=state
        if not _reaper_running:
            _reaper_running=True
            socketio.start_background_task(_reap)
    return name,state


def control(name,action,mode=None):
    from manager.battle.common_manager import _get_round_transition_lock
    from manager.room_manager import broadcast_state_update, emit_select_resolve_events
    with _get_round_transition_lock(name):
        if name not in registry:
            raise ValueError('練習用のルームがありません。')
        state=active_room_states[name]
        if action=='reset':
            selected_mode=state['practice']['opponent_mode']
            state=deepcopy(registry[name]['initial'])
            _set_mode(state,selected_mode)
            active_room_states[name]=state
            start_round(name)
        elif action=='mode' and mode in ('manual','auto'):
            battle=state.get('battle_state',{})
            if battle.get('phase')!='select' and state.get('round',0)>0:
                raise ValueError('宣言の段階で切り替えてください。')
            _set_mode(state,mode)
            for slot_id,slot in battle.get('slots',{}).items():
                if slot.get('team')=='enemy':
                    battle.get('intents',{}).pop(slot_id,None)
            if mode=='auto' and battle:
                from manager.battle.common_manager import _apply_pve_auto_enemy_intents
                _apply_pve_auto_enemy_intents(state,battle,name)
            if battle:
                from events.battle.common_routes import _refresh_resolve_ready
                _refresh_resolve_ready(name,battle)
            emit_select_resolve_events(name,include_round_started=False)
            broadcast_state_update(name)
        else:
            raise ValueError('不正な操作です。')
        return state
