"""PR66-5 one-request classification/mark changes use the normal publishing checks."""
import copy
import os
os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
from app import create_app
from extensions import db, all_buff_data, all_glossary_data
from models import User, CatalogEntry, CatalogDraft, CatalogHistory
from manager.catalog import repository as repo
from manager.catalog.kinds import validate_payload, CatalogValidationError


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI":"sqlite://",
                      "SQLALCHEMY_ENGINE_OPTIONS":{}}, run_startup=False, register_sockets=False)
    saved = copy.deepcopy(all_buff_data)
    saved_glossary = copy.deepcopy(all_glossary_data)
    with app.app_context():
        db.create_all()
        db.session.add_all([User(id="admin",name="admin",is_app_admin=True),
                            User(id="author",name="author",is_catalog_author=True), User(id="reader",name="reader")])
        for index in range(60, 65):
            payload = {"name":f"buff{index}", "description":"KEEP", "effect":{}, "marks":["enemy"]}
            if index == 62:
                payload["default_duration"] = 0
            db.session.add(CatalogEntry(kind="buff",entry_id=f"Bu-{index}",payload=payload,revision=1))
        db.session.commit()
        pending = repo.create_draft("buff","author",target_id="Bu-61")
        repo.submit_draft(pending.id)
        yield app
        db.session.remove()
        db.drop_all()
    all_buff_data.clear()
    all_buff_data.update(saved)
    all_glossary_data.clear()
    all_glossary_data.update(saved_glossary)


def client(app, actor):
    result=app.test_client()
    if actor:
        with result.session_transaction() as session:
            session.update(user_id=actor,username=actor,auth_version=1)
    return result


def body(ids=("Bu-60","Bu-61","Bu-62","Bu-63")):
    return {"entries":[{"entry_id":key,"base_revision":9 if key=="Bu-63" else 1} for key in ids],
            "changes":{"category":"能力の増減","marks_add":["known"],"marks_remove":["enemy"]}}


@pytest.mark.parametrize("actor",["author","admin"])
def test_bulk_success_skips_and_preserves_payload(app,actor):
    response=client(app,actor).post("/api/catalog/buff/bulk",json=body())
    assert response.status_code==200
    data=response.json
    assert data["changed"]==1 and data["skipped"]==3
    assert {row["entry_id"] for row in data["results"] if row["status"]=="skipped"}=={"Bu-61","Bu-62","Bu-63"}
    assert all(row.get("reason") for row in data["results"] if row["status"]=="skipped")
    current=CatalogEntry.query.filter_by(kind="buff",entry_id="Bu-60").one()
    if actor=="admin":
        assert current.payload["category"]=="能力の増減"
        assert current.payload["description"]=="KEEP"
        assert current.payload["effect"]=={}
        assert current.payload["marks"]==["known"]
        history=CatalogHistory.query.filter_by(kind="buff",entry_id="Bu-60").one()
        assert history.action=="publish" and history.actor_user_id=="admin"
        assert CatalogDraft.query.filter_by(target_id="Bu-60").first() is None
    else:
        assert current.revision==1 and current.payload["marks"]==["enemy"]
        draft=CatalogDraft.query.filter_by(target_id="Bu-60").one()
        assert draft.status=="pending" and draft.payload["description"]=="KEEP"
    assert CatalogDraft.query.filter_by(target_id="Bu-62").first() is None


@pytest.mark.parametrize("actor,status",[(None,401),("reader",403)])
def test_bulk_requires_author(app,actor,status):
    assert client(app,actor).post("/api/catalog/buff/bulk",json=body()).status_code==status


def test_bulk_rejects_unknown_operations_and_duplicate_entries(app):
    for changes in ({"name":"bad"},{"category":"bad"},{"marks_add":["bad"]}, {"marks_add":["hollow"]}, {"marks_remove":["hollow"]},
                    {"marks_add":["known"],"marks_remove":["known"]},{}):
        data=body(("Bu-60",))
        data["changes"]=changes
        assert client(app,"admin").post("/api/catalog/buff/bulk",json=data).status_code==422
    data=body(("Bu-60","Bu-60"))
    assert client(app,"admin").post("/api/catalog/buff/bulk",json=data).status_code==422
    assert CatalogEntry.query.filter_by(entry_id="Bu-60").one().revision==1


def test_buff_category_optional_and_validated(app):
    assert validate_payload("buff",{"name":"optional"})["category"]==""
    for category in ("","能力の増減","状態異常の強化","特殊スタック","出身の恩恵","物語"):
        assert validate_payload("buff",{"name":"good","category":category})["category"]==category
    for category in ("bad",None,[]):
        with pytest.raises(CatalogValidationError):
            validate_payload("buff",{"name":"bad","category":category})


def test_failed_approval_rolls_back_whole_item(app,monkeypatch):
    def reject(*args,**kwargs):
        raise CatalogValidationError({"effect":"approve check"})
    monkeypatch.setattr(repo,"approve_draft",reject)
    response=client(app,"admin").post("/api/catalog/buff/bulk",json=body(("Bu-60",)))
    assert response.json["skipped"]==1
    assert CatalogDraft.query.filter_by(target_id="Bu-60").first() is None
    assert CatalogEntry.query.filter_by(entry_id="Bu-60").one().revision==1


def test_glossary_bulk_preserves_content_and_repeated_changes(app):
    payload=validate_payload('glossary',{'display_name':'KEEP','category':'ルール','short':'KEEP','long':'KEEP','links':[]})
    db.session.add(CatalogEntry(kind='glossary',entry_id='W-60',payload=payload,revision=1))
    db.session.commit()
    data={'entries':[{'entry_id':'W-60','base_revision':1}],'changes':{'category':'タイミング'}}
    assert client(app,'admin').post('/api/catalog/glossary/bulk',json=data).json['changed']==1
    current=CatalogEntry.query.filter_by(entry_id='W-60').one()
    assert current.payload=={**payload,'category':'タイミング'}
    data['entries'][0]['base_revision']=current.revision
    assert client(app,'admin').post('/api/catalog/glossary/bulk',json=data).json['skipped']==1
