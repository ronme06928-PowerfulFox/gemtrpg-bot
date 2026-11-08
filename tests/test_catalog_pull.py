"""PR60-9: 公開スナップショットの取得とローカルへの一括反映。"""
import copy
import json
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest
import requests

import app as app_module
from extensions import db, all_glossary_data, all_buff_data
from models import CatalogEntry, CatalogHistory, CatalogDraft
from manager.catalog import pull


@pytest.fixture
def local(tmp_path, monkeypatch):
    app = app_module.create_app(config={"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_ENGINE_OPTIONS": {}}, run_startup=False, register_sockets=False)
    memories = [all_glossary_data, all_buff_data]
    before = [copy.deepcopy(data) for data in memories]
    files = {kind: tmp_path / f"{kind}.json" for kind in pull.SOURCES}
    monkeypatch.setattr(pull, "CACHE_FILES", files)
    for path in files.values():
        path.write_text('{"old": true}', encoding="utf-8")
    with app.app_context():
        db.create_all()
        for kind, entry_id, payload in (("glossary", "W-00", {"display_name": "手元", "category": "ルール"}),
                                        ("buff", "Bu-00", {"name": "手元バフ"})):
            db.session.add(CatalogEntry(kind=kind, entry_id=entry_id, payload=payload, revision=1))
            db.session.add(CatalogHistory(kind=kind, entry_id=entry_id, payload=payload,
                                          revision=1, action="import"))
        db.session.add(CatalogDraft(kind="glossary", target_id="W-00", payload={"short": "書きかけ"}, base_revision=1))
        db.session.add(CatalogEntry(kind="item", entry_id="I-00", payload={"keep": True}, revision=1))
        db.session.commit()
        yield app, files
        db.session.remove()
        db.drop_all()
    for data, saved in zip(memories, before):
        data.clear()
        data.update(saved)


@pytest.fixture
def remote(monkeypatch):
    data = {"glossary": {"W-00": {"term_id": "W-00", "display_name": "本番", "category": "ルール",
                                   "links": [], "synonyms": [], "deprecated": True}},
            "buff": {"Bu-01": {"id": "Bu-01", "name": "本番バフ", "effect": {}, "default_duration": -1}},
            "skill": {"Ps-00": {"スキルID": "Ps-00", "デフォルト名称": "本番スキル", "特記処理": "", "tags": []}}}
    calls = []

    def get(url, **options):
        kind = next(kind for kind, path in pull.SOURCES.items() if url.endswith(path))
        calls.append((url, options))
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(data[kind], ensure_ascii=False).encode("utf-8")
        response.headers["Content-Type"] = "application/json"
        return response

    monkeypatch.setattr(pull.requests, "get", get)
    return data, calls


def test_pull_replaces_files_and_public_db_preserving_drafts_and_history(local, remote, monkeypatch):
    app, files = local
    data, calls = remote
    monkeypatch.setenv("CATALOG_PULL_BASE_URL", "https://example.test/")
    result = pull.pull_catalogs()
    assert result == {"glossary": 1, "buff": 1, "skill": 1}
    assert len(calls) == 3 and all(url.startswith("https://example.test/api/") for url, _ in calls)
    assert all(options["timeout"] >= 30 and options["headers"]["Cache-Control"] == "no-cache" for _, options in calls)
    for kind, path in files.items():
        assert json.loads(path.read_text(encoding="utf-8")) == data[kind]
    assert CatalogEntry.query.filter_by(kind="buff", entry_id="Bu-00").first() is None
    assert CatalogEntry.query.filter_by(kind="glossary", entry_id="W-00").one().deprecated is True
    assert CatalogEntry.query.filter_by(kind="skill").count() == 0
    assert CatalogEntry.query.filter_by(kind="item").one().payload == {"keep": True}
    draft = CatalogDraft.query.one()
    assert draft.payload == {"short": "書きかけ"} and draft.base_revision == 1
    # 取り込んだ行は既存の import として履歴に残す（変わった W-00 と新しい Bu-01）。
    assert CatalogHistory.query.filter_by(action="import").count() == 4
    assert CatalogEntry.query.filter_by(kind="glossary", entry_id="W-00").one().revision == 2
    assert all_glossary_data["W-00"]["display_name"] == "本番"
    assert all_buff_data["Bu-01"]["name"] == "本番バフ"
    # 中身が同じなら版も履歴も増えない。
    pull.pull_catalogs()
    assert CatalogHistory.query.count() == 4
    assert CatalogEntry.query.filter_by(kind="glossary", entry_id="W-00").one().revision == 2
    # 消えたIDが再登場しても履歴の版と重ならない。
    data["buff"] = {"Bu-00": {"id": "Bu-00", "name": "再登場"}}
    pull.pull_catalogs()
    assert CatalogEntry.query.filter_by(kind="buff", entry_id="Bu-00").one().revision == 2


@pytest.mark.parametrize("broken", [None, [], {}, {"Ps-00": []},
    {"Ps-00": {"スキルID": "Ps-99", "デフォルト名称": "不一致"}}])
def test_bad_response_changes_nothing(local, remote, broken):
    _, files = local
    data, _ = remote
    data["skill"] = broken
    with pytest.raises(pull.CatalogPullError):
        pull.pull_catalogs()
    assert all(path.read_text(encoding="utf-8") == '{"old": true}' for path in files.values())
    assert CatalogEntry.query.filter_by(kind="glossary").one().payload["display_name"] == "手元"
    assert CatalogHistory.query.count() == 2 and CatalogDraft.query.count() == 1


@pytest.mark.parametrize("failure", ["network", "status", "json", "file", "commit"])
def test_failures_leave_files_db_and_memory_unchanged(local, remote, monkeypatch, failure):
    _, files = local
    original_get = pull.requests.get
    original_replace = pull.os.replace
    original_memory = copy.deepcopy(all_buff_data)

    def get(url, **options):
        if url.endswith("get_skill_data"):
            if failure == "network":
                raise requests.Timeout("timeout")
            response = original_get(url, **options)
            if failure == "status":
                response.status_code = 503
            elif failure == "json":
                response._content = b"not json"
            return response
        return original_get(url, **options)

    def replace(source, target):
        if failure == "file" and target == files["buff"] and str(source).endswith(".download"):
            raise OSError("cannot write")
        original_replace(source, target)

    monkeypatch.setattr(pull.requests, "get", get)
    monkeypatch.setattr(pull.os, "replace", replace)
    if failure == "commit":
        monkeypatch.setattr(db.session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
    with pytest.raises(pull.CatalogPullError):
        pull.pull_catalogs()
    assert all(path.read_text(encoding="utf-8") == '{"old": true}' for path in files.values())
    assert CatalogHistory.query.count() == 2 and CatalogDraft.query.count() == 1
    assert CatalogEntry.query.filter_by(kind="buff").one().entry_id == "Bu-00"
    assert all_buff_data == original_memory
    assert not list(next(iter(files.values())).parent.glob("*.download"))


def test_render_guard_precedes_database_and_network(monkeypatch):
    monkeypatch.setattr(app_module, "IS_RENDER", True)
    monkeypatch.setattr(app_module, "create_app", lambda **_: pytest.fail("RenderでDBを開かない"))
    monkeypatch.setattr(pull.requests, "get", lambda *_a, **_kw: pytest.fail("Renderで通信しない"))
    assert app_module.run_cli(["--pull"]) == 1


def test_pull_cli_skips_startup_and_does_not_start_server(local, remote, monkeypatch):
    application, _ = local
    calls = []

    def factory(**options):
        calls.append(options)
        return application

    monkeypatch.setattr(app_module, "create_app", factory)
    assert app_module.run_cli(["--pull"]) == 0
    assert calls == [{"run_startup": False, "register_sockets": False, "register_routes": False}]
    with pytest.raises(SystemExit):
        app_module.run_cli(["--pull", "--update"])


@pytest.mark.parametrize("kind,field,value", [("glossary", "category", "不明"),
    ("glossary", "links", [1]), ("glossary", "deprecated", "false"),
    ("buff", "effect", []), ("buff", "default_duration", True),
    ("buff", "default_duration", 0), ("buff", "name", ""),
    ("skill", "特記処理", {}), ("skill", "tags", [1])])
def test_invalid_record_shapes_are_rejected_before_writes(local, remote, kind, field, value):
    _, files = local
    records, _ = remote
    next(iter(records[kind].values()))[field] = value
    with pytest.raises(pull.CatalogPullError):
        pull.pull_catalogs()
    assert all(path.read_text(encoding="utf-8") == '{"old": true}' for path in files.values())
    assert CatalogHistory.query.count() == 2


def test_missing_cache_files_are_removed_again_on_failure(local, remote, monkeypatch):
    _, files = local
    for path in files.values():
        path.unlink()
    original = pull.os.replace

    def replace(source, target):
        if target == files["buff"]:
            raise OSError("cannot replace")
        return original(source, target)

    monkeypatch.setattr(pull.os, "replace", replace)
    with pytest.raises(pull.CatalogPullError):
        pull.pull_catalogs()
    assert not any(path.exists() for path in files.values())
    assert CatalogHistory.query.count() == 2


def test_pull_process_does_not_create_default_app(monkeypatch):
    monkeypatch.delenv("GEMTRPG_DISABLE_DEFAULT_APP", raising=False)
    monkeypatch.setattr(app_module, "__name__", "__main__")
    monkeypatch.setattr(app_module.sys, "argv", ["app.py", "--pull"])
    assert not app_module._should_create_default_app()


def test_skill_snapshot_drops_runtime_system_skills(local, remote):
    """システムスキルはコードが正本で起動時に足されるため、写さない。"""
    from manager.battle.system_skills import SYSTEM_SKILLS
    _, files = local
    data, _ = remote
    expected = copy.deepcopy(data["skill"])
    data["skill"].update(copy.deepcopy(SYSTEM_SKILLS))
    assert pull.pull_catalogs()["skill"] == len(expected)
    assert json.loads(files["skill"].read_text(encoding="utf-8")) == expected
    assert CatalogEntry.query.filter_by(kind="skill").count() == 0


def test_seed_keeps_deprecated_mark_from_cache(local, monkeypatch, tmp_path):
    from manager.catalog import repository
    from manager.catalog.kinds import KINDS
    cache = tmp_path / "buff_seed.json"
    cache.write_text(json.dumps({"Bu-05": {"id": "Bu-05", "name": "廃止済み", "deprecated": True}},
                                ensure_ascii=False), encoding="utf-8")
    monkeypatch.setitem(KINDS["buff"], "cache_file", cache)
    CatalogHistory.query.filter_by(kind="buff").delete()
    CatalogEntry.query.filter_by(kind="buff").delete()
    db.session.commit()
    assert repository.seed_kind_if_empty("buff") == 1
    entry = CatalogEntry.query.filter_by(kind="buff", entry_id="Bu-05").one()
    assert entry.deprecated is True and "deprecated" not in entry.payload


def test_failed_restore_keeps_original_backup(local, remote, monkeypatch):
    _, files = local
    replace = pull.os.replace

    def blocked_restore(source, target):
        if str(source).endswith(".backup") and target == files["buff"]:
            raise OSError("restore blocked")
        return replace(source, target)

    monkeypatch.setattr(pull.os, "replace", blocked_restore)
    monkeypatch.setattr(db.session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
    with pytest.raises(pull.CatalogPullError, match="復元できません"):
        pull.pull_catalogs()
    backups = list(files["buff"].parent.glob("*.backup"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == '{"old": true}'
    assert CatalogHistory.query.count() == 2
