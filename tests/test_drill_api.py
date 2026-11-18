"""Authenticated, bounded and read-only drill endpoint."""
import os
os.environ['GEMTRPG_SKIP_IMPORT_STARTUP']='1'

import pytest
from app import create_app
from extensions import db, all_skill_data
from models import User
from tests.test_drill_match import skill, character


@pytest.fixture
def app(monkeypatch):
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite://',
                    'SQLALCHEMY_ENGINE_OPTIONS':{}},run_startup=False,register_sockets=False)
    with app.app_context():
        db.create_all()
        db.session.add(User(id='drill-reader',name='reader'))
        db.session.commit()
        monkeypatch.setitem(all_skill_data,'E-TEST',skill())
        yield app
        db.session.remove()
        db.drop_all()


def client(app):
    client=app.test_client()
    with client.session_transaction() as session:
        session.update(user_id='drill-reader',username='reader',auth_version=1)
    return client


def body():
    return {'actor':character(), 'target':character(id='target'), 'skill_id':'E-TEST'}


def test_login_required_but_enemy_skill_not_restricted(app):
    assert app.test_client().post('/api/drill/match',json=body()).status_code==401
    result=client(app).post('/api/drill/match',json=body())
    assert result.status_code==200
    assert result.json['probabilities']['win']==1


@pytest.mark.parametrize('data', [None,[],{}, {'actor':[]},
    {**body(),'actor':{'params':'bad'}}, {**body(),'target':{'states':[1]}},
    {**body(),'skill_id':None}, {**body(),'skill_id':'missing'},
    {**body(),'target_skill_id':4}, {**body(),'actor':{'hp':100001}},
    {**body(),'actor':{'hp':float('inf')}},
    {**body(),'actor':{'hp':'100001'}}, {**body(),'actor':{'hp':'bad'}},
    {**body(),'actor':{'name':'x'*2049}},
    {**body(),'actor':{'states':[{}]*129}},
    {**body(),'actor':{'a':{'b':{'c':{'d':{'e':{'f':{'g':{'h':{'i':1}}}}}}}}}},
])
def test_invalid_input_is_422(app,data):
    result=client(app).post('/api/drill/match',json=data)
    assert result.status_code==422
    assert result.json['error']


def test_oversized_body_is_422(app):
    result=client(app).post('/api/drill/match',data=' '*131073,content_type='application/json')
    assert result.status_code==422


def test_bad_json_and_deep_json_are_422(app):
    for text in ('{bad', '['*1200+'0'+']'*1200):
        assert client(app).post('/api/drill/match',data=text,content_type='application/json').status_code==422
