from flask import request, session
from extensions import socketio
from manager import practice_rooms
from manager.room_access import is_sid_in_room


@socketio.on('practice_control')
def practice_control(data):
    if not isinstance(data,dict):
        return {'error':'不正な操作です。'}
    room=data.get('room')
    if (not isinstance(room,str) or not practice_rooms.is_practice(room)
            or practice_rooms.owner(room)!=session.get('user_id') or not is_sid_in_room(request.sid,room)):
        return {'error':'在室の所有者だけが操作できます。'}
    try:
        practice_rooms.control(room,data.get('action'),data.get('mode'))
        return {'ok':True}
    except ValueError as error:
        return {'error':str(error)}
