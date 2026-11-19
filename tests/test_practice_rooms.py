import copy
import os
os.environ['GEMTRPG_SKIP_IMPORT_STARTUP']='1'

import pytest
from flask import request
from app import create_app
from extensions import db, active_room_states, user_sids
from models import User, OwnedCharacter, Room, RoomMember, CatalogEncounter, CatalogEntry
from manager import practice_rooms as practice
from manager.room_manager import get_room_state, save_specific_room_state, flush_room_state_now
from manager.room_access import resolve_room_role


@pytest.fixture
def app(monkeypatch):
    import manager.room_manager as rooms
    monkeypatch.setattr(rooms,'_dirty_rooms',set())
    monkeypatch.setattr(rooms,'_save_retry_counts',{})
    monkeypatch.setattr(rooms,'_app_ref',None)
    monkeypatch.setattr(rooms,'_schedule_flush',lambda:None)
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite://','SQLALCHEMY_ENGINE_OPTIONS':{}},
                   run_startup=False,register_sockets=False)
    tasks=[]
    app.extensions['practice_tasks']=tasks
    monkeypatch.setattr(practice.socketio,'start_background_task',lambda *args,**kwargs:tasks.append(args[0]))
    monkeypatch.setattr(practice,'_reaper_running',False)
    def start(name):
        active_room_states[name].update(round=1)
        active_room_states[name].setdefault('battle_state',{})['phase']='select'
    monkeypatch.setattr(practice,'start_round',start)
    with app.app_context():
        db.create_all()
        db.session.add_all([User(id='me',name='me'),User(id='other',name='other'),User(id='admin',name='admin',is_app_admin=True)])
        db.session.add(OwnedCharacter(id='mine',user_id='me',name='hero',data={
            'name':'hero','status':[{'label':'HP','value':20,'max':20}], 'commands':'','params':[]}))
        db.session.add(CatalogEntry(kind='unit',entry_id='U-001',visibility='public',payload={
            'name':'known','allow_enemy':True,'marks':['known'],'hp':30,'mp':10,'skills':[]}))
        db.session.add(CatalogEntry(kind='unit',entry_id='U-002',visibility='staff',payload={
            'name':'secret','allow_enemy':True,'hp':30,'skills':[]}))
        db.session.commit()
        yield app
        for name in list(practice.registry): practice.drop(name)
        db.session.remove(); db.drop_all()


def client(app,user='me'):
    c=app.test_client()
    with c.session_transaction() as session: session.update(user_id=user,username=user,auth_version=1)
    return c


def create(app,**extra):
    return client(app).post('/api/drill/practice',json={
        'actor':{'source':'owned','id':'mine'},'target':{'source':'unit','id':'U-001'},**extra})


def test_private_memory_only_and_rebuilds_characters(app):
    response=create(app)
    assert response.status_code==201,response.json
    name=response.json['room_name']
    state=get_room_state(name)
    assert state['characters'][0]['hp']==20
    assert state['characters'][1]['hp']==30
    assert resolve_room_role('me',name)=='gm'
    assert resolve_room_role('other',name) is None
    assert resolve_room_role('admin',name,app_admin=True) is None
    assert client(app).post('/api/enter_room',json={'room_name':name}).status_code==200
    assert client(app,'other').post('/api/enter_room',json={'room_name':name}).status_code==403
    for who in ('me','other','admin'):
        assert not any(row.get('name')==name for row in client(app,who).get('/list_rooms').json['rooms'])
    assert save_specific_room_state(name) is False
    assert flush_room_state_now(name) is True
    from manager.data_manager import save_room_to_db
    assert save_room_to_db(name,state) is False
    from manager.encounters import record
    record(name,[('skill','E-00')])
    assert Room.query.count()==RoomMember.query.count()==CatalogEncounter.query.count()==0


def test_authorization_rejects_other_owned_and_unreadable_unit(app):
    assert create(app,actor={'source':'owned','id':'not-mine'}).status_code==404
    assert create(app,target={'source':'unit','id':'U-002'}).status_code==404
    assert create(app,actor={'source':'owned','id':'mine','character':{'hp':9999}}).status_code==422
    assert Room.query.count()==0


def test_one_per_person_cleanup_and_reconnect_deadline(app,monkeypatch):
    name=create(app).json['room_name']
    for _ in range(10):
        assert create(app).json['room_name']==name
        assert len(practice.registry)==1
    assert len(app.extensions['practice_tasks'])==1
    monkeypatch.setitem(user_sids,'one',{'room':name,'user_id':'me','attribute':'GM'})
    practice.joined(name)
    practice.expire(now=10**12)
    assert name in active_room_states
    user_sids['one']['room']=None
    practice.detached(name,now=100)
    practice.expire(now=159)
    assert name in active_room_states
    practice.joined(name)
    practice.expire(now=161)
    assert name in active_room_states
    practice.detached(name,now=200)
    practice.expire(now=260)
    assert name not in active_room_states and name not in practice.registry
    assert get_room_state(name) is None


def test_reset_and_mode_keep_initial_copy_private(app):
    name=create(app).json['room_name']
    before=copy.deepcopy(practice.registry[name]['initial'])
    active_room_states[name]['characters'][0]['hp']=1
    practice.control(name,'reset')
    assert active_room_states[name]['characters'][0]['hp']==20
    assert practice.registry[name]['initial']==before
    practice.control(name,'mode',mode='auto')
    assert active_room_states[name]['battle_mode']=='pve'
    practice.control(name,'mode',mode='manual')
    assert active_room_states[name]['battle_mode']=='pvp'


def test_socket_join_leave_disconnect_and_both_sides_control(app):
    from extensions import socketio
    from events import socket_main
    from events.battle.practice_routes import practice_control
    for event,handler in [('connect',socket_main.handle_connect),('disconnect',socket_main.handle_disconnect),
                          ('join_room',socket_main.handle_join_room),('leave_room',socket_main.handle_leave_room),
                          ('practice_control',practice_control)]:
        socketio.on_event(event,handler)
    from manager.room_manager import is_authorized_for_character
    name=create(app).json['room_name']
    mine=socketio.test_client(app,flask_test_client=client(app))
    other=socketio.test_client(app,flask_test_client=client(app,'other'))
    try:
        other.emit('join_room',{'room':name,'role':'GM'})
        assert any(row['name']=='join_room_error' for row in other.get_received())
        mine.emit('join_room',{'room':name,'role':'Player'})
        assert any(row['name']=='state_updated' for row in mine.get_received())
        for char in active_room_states[name]['characters']:
            assert is_authorized_for_character(name,char['id'],'me','GM')
        assert mine.emit('practice_control',{'room':name,'action':'reset'},callback=True)=={'ok':True}
        mine.disconnect()
        assert name in active_room_states
        assert practice.registry[name]['expires_at'] is not None
        again=socketio.test_client(app,flask_test_client=client(app))
        again.emit('join_room',{'room':name})
        assert practice.registry[name]['expires_at'] is None
        assert again.emit('leave_room',{},callback=True)['ok']
        assert name not in active_room_states and name not in practice.registry
        again.disconnect()
    finally:
        if mine.is_connected(): mine.disconnect()
        other.disconnect()


def test_auto_round_uses_existing_end_then_start_only_for_practice(app,monkeypatch):
    from events.battle import common_routes
    name=create(app).json['room_name']
    active_room_states[name]['round']=3
    calls=[]
    monkeypatch.setattr(common_routes,'process_full_round_end',lambda room,who:calls.append(('end',room)) or True)
    monkeypatch.setattr(common_routes,'process_round_start',lambda room,who:calls.append(('start',room)) or True)
    monkeypatch.setattr(common_routes,'flush_room_state_now',lambda room:True)
    assert common_routes._complete_round_after_resolve(name,'me',3)
    assert calls==[('end',name),('start',name)]
    assert not common_routes._complete_round_after_resolve(name,'me',2)


def test_reserved_names_and_whole_room_overwrite_are_rejected(app):
    name=create(app).json['room_name']
    c=client(app)
    assert c.post('/create_room',json={'room_name':name,'gm_pin':'1234'}).status_code==400
    assert c.post('/save_room',json={'room_name':name,'state':{}}).status_code==403
    with c.session_transaction() as session: session['entered_rooms']=[name]
    stranger=client(app,'other')
    with stranger.session_transaction() as session: session['entered_rooms']=[name]
    assert stranger.get('/load_room',query_string={'name':name}).status_code==403
    assert c.get('/load_room',query_string={'name':name}).status_code==200


def test_log_limit_never_archives_and_placement_stays_fixed(app,monkeypatch):
    from manager.room_manager import trim_room_logs_with_archive
    from manager.battle.common_manager import move_token_logic
    from manager.log_archive import get_archived_room_logs
    from models import RoomLogArchive
    name=create(app).json['room_name']
    state=active_room_states[name]
    state['logs']=[{'message':str(index)} for index in range(600)]
    assert trim_room_logs_with_archive(name,state)
    assert len(state['logs'])==500
    assert get_archived_room_logs(name)==[]
    assert RoomLogArchive.query.count()==0
    before=copy.deepcopy(state['characters'])
    move_token_logic(name,'practice_0',8,8,'me','GM')
    assert state['characters']==before


def test_explicit_switch_to_normal_room_deletes_practice(app):
    from extensions import socketio
    from events import socket_main
    for event,handler in [('connect',socket_main.handle_connect),('disconnect',socket_main.handle_disconnect),
                          ('join_room',socket_main.handle_join_room),('leave_room',socket_main.handle_leave_room)]:
        socketio.on_event(event,handler)
    c=client(app)
    name=create(app).json['room_name']
    normal=c.post('/create_room',json={'room_name':'normal-practice-test','gm_pin':'1234'})
    assert normal.status_code==201
    sock=socketio.test_client(app,flask_test_client=c)
    try:
        sock.emit('join_room',{'room':name})
        sock.emit('join_room',{'room':'normal-practice-test'})
        assert name not in practice.registry and name not in active_room_states
        assert any(info.get('room')=='normal-practice-test' for info in user_sids.values())
    finally:
        sock.disconnect()
        from manager.room_manager import discard_pending_save
        discard_pending_save('normal-practice-test')
        active_room_states.pop('normal-practice-test',None)
