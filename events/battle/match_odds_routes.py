"""Private Socket acknowledgements for battle forecasts; never create state."""
from flask import request
from extensions import socketio, active_room_states
from manager.room_access import is_sid_in_room
from manager.drill.room_odds import calculate_room_odds


@socketio.on('battle_match_odds')
def battle_match_odds(data):
    if not isinstance(data,dict):
        return {'error':'不正な要求です。'}
    keys=('room_id','battle_id','slot_id','target_slot_id')
    if any(not isinstance(data.get(key),str) or not 0<len(data[key])<=200 for key in keys):
        return {'error':'ルーム・戦闘・スロットを確認してください。'}
    room_id=data['room_id']
    if not is_sid_in_room(request.sid,room_id):
        return {'error':'在室していません。'}
    room=active_room_states.get(room_id)
    battle=(room or {}).get('battle_state',{})
    if battle.get('battle_id')!=data['battle_id'] or battle.get('phase')!='select':
        return {'error':'宣言の段階ではありません。'}
    slots=battle.get('slots',{})
    if data['slot_id'] not in slots or data['target_slot_id'] not in slots:
        return {'error':'スロットがありません。'}
    candidates=data.get('skill_ids')
    if (not isinstance(candidates,list) or len(candidates)>100
            or any(not isinstance(key,str) or not 0<len(key)<=80 for key in candidates)):
        return {'error':'候補は100件までのスキルIDで指定してください。'}
    return {'odds':calculate_room_odds(room,data['slot_id'],data['target_slot_id'],candidates,
                                       yield_work=lambda:socketio.sleep(0))}
