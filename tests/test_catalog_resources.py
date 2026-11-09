"""PR60-14: 残る4種類のDB・参照・公開辞書の契約。"""
import copy
import os

os.environ['GEMTRPG_SKIP_IMPORT_STARTUP'] = '1'

import pytest
import extensions
from app import create_app, run_cli
from extensions import db
from models import CatalogEntry, CatalogDraft, CatalogHistory, User
from manager.cache_paths import load_json_cache
from manager.catalog import repository as repo
from manager.catalog.kinds import get_kind, inspect_payload
from manager.catalog.references import find_references

KINDS = ('glossary', 'buff', 'skill', 'item', 'passive', 'radiance', 'summon')
RESOURCES = [('item', 'I-00', 3), ('passive', 'Pa-00', 8), ('radiance', 'S-00', 9), ('summon', 'U-00', 3)]


@pytest.fixture
def catalog():
    app = create_app(config={'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                            'SQLALCHEMY_ENGINE_OPTIONS': {}}, run_startup=False, register_sockets=False)
    memories = [getattr(extensions, get_kind(kind)['memory_name']) for kind in KINDS]
    previous = [copy.deepcopy(data) for data in memories]
    with app.app_context():
        db.create_all()
        db.session.add_all([User(id='author', name='作者', is_catalog_author=True),
                            User(id='admin', name='管理者', is_app_admin=True)])
        db.session.commit()
        for kind in KINDS:
            repo.seed_kind_if_empty(kind)
            repo.load_kind_into_memory(kind)
        yield app
        db.session.remove()
        db.drop_all()
    for data, saved in zip(memories, previous):
        data.clear()
        data.update(saved)


def actor(app, name):
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(user_id=name, username=name, auth_version=1)
    return client


@pytest.mark.parametrize('kind,entry_id,count', RESOURCES)
def test_seed_matches_cache_without_loader_cache_or_fetch(catalog, kind, entry_id, count):
    definition = get_kind(kind)
    memory = getattr(extensions, definition['memory_name'])
    assert memory == load_json_cache(definition['cache_file'])
    assert len(memory) == count
    assert CatalogHistory.query.filter_by(kind=kind, action='import').count() == count
    assert repo.seed_kind_if_empty(kind) == 0
    row = CatalogEntry.query.filter_by(kind=kind, entry_id=entry_id).one()
    assert definition['id_field'] not in row.payload
    assert catalog.test_client().get(f'/api/get_{kind}_data').get_json() == memory


@pytest.mark.parametrize('kind,entry_id,count', RESOURCES)
def test_management_api_approval_updates_readers_and_public_api(catalog, kind, entry_id, count):
    author, admin = actor(catalog, 'author'), actor(catalog, 'admin')
    original = copy.deepcopy(getattr(extensions, get_kind(kind)['memory_name']))
    draft = author.post(f'/api/catalog/{kind}/drafts', json={'target_id': entry_id}).get_json()
    payload = draft['payload']
    payload['name'] = '変更後の名前'
    response = author.put(f"/api/catalog/drafts/{draft['id']}", json={'payload': payload})
    assert response.status_code == 200, response.get_json()
    assert not [p for p in response.get_json()['problems'] if p['level'] == 'error']
    assert author.post(f"/api/catalog/drafts/{draft['id']}/submit").status_code == 200
    assert admin.post(f"/api/catalog/drafts/{draft['id']}/approve", json={}).status_code == 200
    assert catalog.test_client().get(f'/api/get_{kind}_data').get_json()[entry_id]['name'] == '変更後の名前'
    if kind == 'summon':
        from manager.summons.loader import get_summon_template, load_summon_templates
        assert load_summon_templates()[entry_id]['name'] == '変更後の名前'
        copied = get_summon_template(entry_id)
        copied['params'].clear()
        assert get_summon_template(entry_id)['params']
    else:
        from manager.items.loader import item_loader
        from manager.passives.loader import passive_loader
        from manager.radiance.loader import radiance_loader
        reader = {'item': item_loader.get_item, 'passive': passive_loader.get_passive, 'radiance': radiance_loader.get_skill}[kind]
        assert reader(entry_id)['name'] == '変更後の名前'
    assert original[entry_id]['name'] != '変更後の名前'


def test_summon_reference_validation_drafts_deprecation_and_types(catalog):
    payload = copy.deepcopy(CatalogEntry.query.filter_by(kind='summon', entry_id='U-00').one().payload)
    for field, kind, valid_id in [('initial_skill_ids','skill','Ps-00'), ('hidden_skills','skill','E-17'),
                                 ('SPassive','passive','Pa-00'), ('radiance_skills','radiance','S-00')]:
        trial = {**payload, field: ['does-not-exist']}
        assert any(p['field'].startswith(field) and p['level']=='error' for p in inspect_payload('summon', trial, stage='submit'))
        target = CatalogEntry.query.filter_by(kind=kind, entry_id=valid_id).one()
        target.deprecated = True
        db.session.commit()
        assert any(p['level']=='warning' for p in inspect_payload('summon', {**payload,field:[valid_id]}, stage='submit'))
        draft = repo.create_draft(kind, 'author', **({'id_prefix':'Ps'} if kind=='skill' else {}))
        trial = {**payload,field:[draft.target_id]}
        assert not [p for p in inspect_payload('summon',trial,stage='submit') if p['level']=='error']
        assert any(p['level']=='error' for p in inspect_payload('summon',trial,stage='approve'))
        assert any(p['level']=='error' for p in inspect_payload('summon',{**payload,field:[True]},stage='draft'))
    # 公開版が--pullなどで消えた場合、正式IDの編集下書きだけでは参照先にならない。
    repo.create_draft('passive', 'author', target_id='Pa-00')
    db.session.delete(CatalogEntry.query.filter_by(kind='passive', entry_id='Pa-00').one())
    db.session.commit()
    assert any(p['field']=='SPassive[0]' and p['level']=='error'
               for p in inspect_payload('summon',{**payload,'SPassive':['Pa-00']},stage='submit'))
    assert any(p['field']=='hp' for p in inspect_payload('summon',{**payload,'hp':True},stage='draft'))
    assert any(p['field']=='unknown' for p in inspect_payload('summon',{**payload,'unknown':1},stage='draft'))
    assert any(p['field']=='granted_tag_ids' for p in inspect_payload('radiance',{'name':'名前','granted_tag_ids':[1]},stage='draft'))


def test_resource_references_use_current_public_dictionaries(catalog):
    source = extensions.all_summon_template_data['U-00']
    source.update(SPassive=['Pa-00'],radiance_skills=['S-00'],inventory={'I-00':2})
    for kind, entry_id, path in [('item','I-00','inventory.I-00'),('passive','Pa-00','SPassive[0]'),('radiance','S-00','radiance_skills[0]')]:
        assert any(r['kind']=='summon' and r['entry_id']=='U-00' and r['path']==path for r in find_references(kind,entry_id))
    extensions.all_skill_data['Ps-00']['特記処理']='{"effects":[{"summon_template_id":"U-00"}]}'
    assert any(r['kind']=='skill' and r['entry_id']=='Ps-00' and r['path']=='特記処理.effects[0].summon_template_id' for r in find_references('summon','U-00'))


def test_removed_update_and_sheet_fetchers():
    import manager.data_manager as data
    from manager.items.loader import item_loader
    from manager.passives.loader import passive_loader
    from manager.radiance.loader import radiance_loader
    from manager.summons import loader
    assert not hasattr(data,'update_all_data')
    for reader in [item_loader,passive_loader,radiance_loader]:
        assert not hasattr(reader,'fetch_from_csv')
        assert not hasattr(reader,'_cache')
    assert not hasattr(loader,'refresh_summon_templates')
    with pytest.raises(SystemExit) as error:
        run_cli(['--update'])
    assert error.value.code == 2
