"""PR63-5: only readable published skills are added to disposable characters."""
import copy
import json
import subprocess
from datetime import datetime

import pytest

from tests.test_practice_rooms import app, client, create
from extensions import all_skill_data, db, active_room_states
from models import CatalogEntry, CatalogEncounter, OwnedCharacter, User
from manager import practice_rooms as practice
from manager.battle.skill_access import list_regular_usable_skill_ids


@pytest.fixture
def skills(app, monkeypatch):
    from manager.battle import skill_access
    # Some older rule tests replace this module's catalog directly; use our fixture's catalog.
    monkeypatch.setattr(skill_access, 'all_skill_data', all_skill_data)
    rows = {
        'Ps-00': {}, 'Pb-03': {}, 'E-12': {}, 'E-13': {'marks': ['known']},
        'E-14': {}, 'Ps-20': {},
        'E-15': {}, 'Ps-21': {'deprecated': True},
        'SYS-STRUGGLE': {},
    }
    for key, extra in rows.items():
        payload = {'デフォルト名称': key, 'チャットパレット': f'1d6+{{物理補正}} 【{key} {key}】',
                   '分類': '物理', '距離': '近接', '特記処理': {}, **extra}
        db.session.add(CatalogEntry(kind='skill', entry_id=key, payload=payload,
                                    deprecated=bool(extra.get('deprecated'))))
        monkeypatch.setitem(all_skill_data, key, payload)
    db.session.add(CatalogEncounter(user_id='me', kind='skill', entry_id='E-14',
                                   first_seen_at=datetime(2026, 11, 20), room_name='normal'))
    db.session.add(User(id='author', name='author', is_catalog_author=True))
    db.session.commit()
    return rows


@pytest.mark.parametrize('source', ['blank', 'owned', 'unit'])
def test_both_sides_add_skills_without_changing_source_and_reset_keeps_them(app, skills, source):
    owned = db.session.get(OwnedCharacter, 'mine')
    unit = CatalogEntry.query.filter_by(kind='unit', entry_id='U-001').one()
    original = copy.deepcopy((owned.data, unit.payload))
    selection = {'source': source, 'skills': ['Pb-03', 'E-13', 'Pb-03']}
    if source != 'blank':
        selection['id'] = 'mine' if source == 'owned' else 'U-001'
    response = create(app, actor=selection, target=selection)
    assert response.status_code == 201, response.json
    name = response.json['room_name']
    for character in active_room_states[name]['characters']:
        assert character['commands'].count('【Pb-03 ') == 1
        assert character['commands'].count('【E-13 ') == 1
        assert '{物理補正}' in character['commands']
        assert 'Pb-03' in list_regular_usable_skill_ids(character)
    active_room_states[name]['characters'][0]['commands'] = ''
    practice.control(name, 'reset')
    assert '【Pb-03 ' in active_room_states[name]['characters'][0]['commands']
    assert active_room_states[name]['practice']['selection']['actor']['skills'] == ['Pb-03', 'E-13']
    assert (owned.data, unit.payload) == original


@pytest.mark.parametrize('key', ['E-12', 'E-15', 'Ps-21', 'No-404', 'SYS-STRUGGLE'])
def test_unreadable_missing_and_deprecated_ids_are_rejected_without_replacing_room(app, skills, key):
    name = create(app).json['room_name']
    original = active_room_states[name]
    response = create(app, actor={'source': 'blank', 'skills': [key]})
    assert response.status_code in (404, 422)
    assert key in response.json['error']
    assert active_room_states[name] is original


@pytest.mark.parametrize('who', ['me', 'author', 'admin'])
def test_visibility_matches_client_encyclopedia(app, skills, who):
    from manager.encyclopedia import skill_entries
    user = db.session.get(User, who)
    full = user.is_catalog_author or user.is_app_admin
    actual = [row.entry_id for row in skill_entries(user)]
    masters = {'skill': {row.entry_id: {**row.payload, 'deprecated': row.deprecated}
                         for row in CatalogEntry.query.filter_by(kind='skill')}}
    extra = {'can_view_all': full, 'units': [], 'encounters': [
        {'kind': 'skill', 'entry_id': 'E-14', 'first_seen_at': '2026-11-20'}] if who == 'me' else []}
    script = """
const fs=require('fs'),vm=require('vm');
const window={CatalogSkill:{groups:[]}};
for(const name of ['encyclopedia/data','drill/data'])
  vm.runInNewContext(fs.readFileSync('static/js/'+name+'.js','utf8'),{window});
const [masters,extra]=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(window.DrillData.readable(masters,extra).skill.map(row=>row.id)));
"""
    result = subprocess.run(['node', '-e', script], input=json.dumps([masters, extra]),
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
    assert set(actual) == set(json.loads(result.stdout))
    keys = ['Pb-03', 'E-13', 'E-14', 'Ps-20'] if who == 'me' else ['E-12', 'Ps-20', 'E-15']
    response = client(app, who).post('/api/drill/practice', json={
        'actor': {'source': 'blank', 'skills': keys}, 'target': {'source': 'blank'}})
    assert response.status_code == 201, response.json


def test_held_skills_are_not_added_twice_and_missing_skills_remains_optional(app, skills):
    row = db.session.get(OwnedCharacter, 'mine')
    row.data = {**row.data, 'commands': '2d6 【Pb-03 alias】'}
    db.session.commit()
    result = create(app, actor={'source': 'owned', 'id': 'mine', 'skills': ['Pb-03']})
    assert result.status_code == 201
    assert active_room_states[result.json['room_name']]['characters'][0]['commands'] == '2d6 【Pb-03 alias】'
    assert create(app).status_code == 201


@pytest.mark.parametrize('value', [None, 'Pb-03', {}, [4], [['Pb-03']], [''], ['x' * 81]])
def test_skills_shape_is_checked(app, skills, value):
    response = create(app, actor={'source': 'blank', 'skills': value})
    assert response.status_code == 422


def test_no_count_limit_and_bounded_request_body(app, skills):
    response = create(app, actor={'source': 'blank', 'skills': ['Pb-03'] * 2000})
    assert response.status_code == 201, response.json
    assert active_room_states[response.json['room_name']]['characters'][0]['commands'].count('【Pb-03 ') == 1
    response = client(app).post('/api/drill/practice', data=' ' * (1048576 + 1), content_type='application/json')
    assert response.status_code == 422
