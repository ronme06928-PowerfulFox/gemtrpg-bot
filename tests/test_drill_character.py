"""Drill snapshots use the room builders and enforce encyclopedia visibility."""
import copy
import json
import os
from pathlib import Path
import subprocess
os.environ['GEMTRPG_SKIP_IMPORT_STARTUP']='1'

import pytest
from app import create_app
from extensions import db
from models import User, OwnedCharacter, CatalogEntry, CatalogEncounter
from manager.character_runtime import build_owned_character_for_play
from manager.units.characters import build_character
from manager.utils import apply_passive_effect_buffs


@pytest.fixture
def app():
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite://',
                    'SQLALCHEMY_ENGINE_OPTIONS':{}},run_startup=False,register_sockets=False)
    with app.app_context():
        db.create_all()
        db.session.add_all([User(id='reader',name='reader'),User(id='other',name='other'),
            User(id='author',name='author',is_catalog_author=True),User(id='admin',name='admin',is_app_admin=True)])
        db.session.add(OwnedCharacter(id='mine',user_id='reader',name='hero',data={
            'name':'hero','status':[{'label':'HP','value':17,'max':20},
            {'label':'MP','value':5,'max':10},{'label':'FP','value':3}],
            'params':[{'label':'物理補正','value':'4'}],'commands':'','SPassive':[]}))
        for index,visibility,marks,enemy in [(1,'public',[],True),(2,'public',['known'],True),
                (3,'staff',[],True),(4,'staff',['known'],True),(5,'public',['known'],True),
                (6,'public',['known'],False),(7,'public',[],True)]:
            db.session.add(CatalogEntry(kind='unit',entry_id=f'U-{index:03}',visibility=visibility,
                payload={'name':f'unit{index}','domain':'hollow' if index == 5 else 'session',
                         'allow_enemy':enemy,'allow_ally':False,
                         'hp':20,'mp':10,'params':[],'skills':[],'marks':marks}))
        from datetime import datetime
        db.session.add(CatalogEncounter(user_id='reader',kind='unit',entry_id='U-007',
            first_seen_at=datetime(2026,11,19),room_name='check'))
        db.session.commit()
        yield app
        db.session.remove(); db.drop_all()


def client(app,actor='reader'):
    client=app.test_client()
    if actor:
        with client.session_transaction() as session:
            session.update(user_id=actor,username=actor,auth_version=1)
    return client


def post(app,source,key,actor='reader',side='ally'):
    return client(app,actor).post('/api/drill/character',json={'source':source,'id':key,'side':side})


def test_owned_is_private_and_matches_room_preparation(app):
    row=db.session.get(OwnedCharacter,'mine')
    before=copy.deepcopy(row.data)
    expected=build_owned_character_for_play(row.data,'ally')
    result=post(app,'owned','mine')
    assert result.status_code==200
    assert result.json['character']==expected
    assert expected['hp']==17 and expected['maxHp']==20
    assert next(s['value'] for s in expected['states'] if s['name']=='FP')==3
    assert row.data==before
    for actor in ('other','admin','author'):
        assert post(app,'owned','mine',actor).status_code==404


def test_owned_snapshot_matches_real_room_parser_and_preparation(app):
    from manager.character_runtime import apply_play_character_policy, prepare_character_for_play
    row=db.session.get(OwnedCharacter,'mine')
    # Stored status is canonical, even when a previous export also contains runtime fields.
    row.data={**row.data,'hp':99,'states':[{'name':'FP','value':99}], 'initial_status':[]}
    db.session.commit()
    script="""
const fs=require('fs'), vm=require('vm'); const context={window:{}};
vm.runInNewContext(fs.readFileSync('static/js/common/char_json.js','utf8'),context);
const result=context.window.parseCharacterJsonToCharacterData('ally',process.argv[1],{gmOnly:false});
if(!result.ok) throw Error(result.message);
process.stdout.write(JSON.stringify(result.charData));
"""
    parsed=subprocess.run(['node','-e',script,json.dumps({'data':row.data},ensure_ascii=False)],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert parsed.returncode==0,parsed.stderr
    expected=json.loads(parsed.stdout)
    apply_play_character_policy(expected)
    expected=prepare_character_for_play(expected)
    assert post(app,'owned','mine').json['character']==expected


@pytest.mark.parametrize('actor,visible', [('reader',{2,7}),('author',{1,2,3,4,5,7}),('admin',{1,2,3,4,5,7})])
def test_unit_gate_and_shape(app,actor,visible,monkeypatch):
    from types import SimpleNamespace
    import manager.units.characters as characters
    monkeypatch.setattr(characters,'uuid4',lambda:SimpleNamespace(hex='stable'))
    for index in range(1,8):
        result=post(app,'unit',f'U-{index:03}',actor)
        assert result.status_code==(200 if index in visible else 404)
        if index not in visible:
            continue
        row=CatalogEntry.query.filter_by(entry_id=f'U-{index:03}').one()
        before=copy.deepcopy(row.payload)
        expected=build_character({**row.payload,'allow_ally':True},'ally',0,source_unit_id=row.entry_id)
        apply_passive_effect_buffs(expected)
        assert result.json['character']==expected
        assert row.payload==before


def test_unknown_deleted_and_malformed_requests(app):
    assert post(app,'owned','mine',None).status_code==401
    assert post(app,'unit','U-999').status_code==404
    row=CatalogEntry.query.filter_by(entry_id='U-002').one(); row.deprecated=True; db.session.commit()
    assert post(app,'unit','U-002').status_code==404
    for data in ({},{'source':'bad','id':'mine','side':'ally'},
                 {'source':'owned','id':[],'side':'ally'}, {'source':'owned','id':'mine','side':'bad'}):
        assert client(app).post('/api/drill/character',json=data).status_code==422
    assert client(app).post('/api/drill/character',data=' '*131073,content_type='application/json').status_code==422
    from datetime import datetime
    db.session.get(OwnedCharacter,'mine').deleted_at=datetime(2026,11,19)
    db.session.commit()
    assert post(app,'owned','mine').status_code==404
