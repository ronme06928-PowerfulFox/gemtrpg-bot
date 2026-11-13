import pytest
from sqlalchemy import text

from extensions import db
from tests.test_catalog_skill import catalog, client

URL = "/api/catalog/effect_requests"
BODY = {"title": "手番を遅らせる", "want": "対象の行動順を1つ遅らせる。", "near_type": "SCHEDULE_EFFECT"}


def test_permissions_and_review(catalog):
    author, admin, reader = (client(catalog, actor) for actor in ("author", "admin", "reader"))
    row = author.post(URL, json=BODY).get_json()
    path = f"{URL}/{row['id']}"
    assert row["created_by_name"] == "制作者" and row["status"] == "open"
    for method, endpoint in [("GET", URL), ("POST", URL), ("PATCH", path), ("DELETE", path), ("POST", path + "/review")]:
        assert reader.open(endpoint, method=method, json=BODY).status_code == 403
    assert "open_requests" not in reader.get("/api/catalog/overview").get_json()
    assert author.get("/api/catalog/overview").get_json()["open_requests"] == 1
    assert admin.patch(path, json={"title": "他人の依頼"}).status_code == 403
    assert admin.delete(path).status_code == 403
    assert author.post(path + "/review", json={"status": "done", "memo": "回答"}).status_code == 403
    assert author.patch(path, json={"title": "手番を1つ遅らせる"}).get_json()["title"] == "手番を1つ遅らせる"
    assert admin.post(path + "/review", json={"status": "in_progress", "memo": "確認中"}).status_code == 200
    assert author.patch(path, json={"title": "変更"}).status_code == 409
    assert author.delete(path).status_code == 409
    assert author.get("/api/catalog/overview").get_json()["open_requests"] == 1
    assert admin.post(path + "/review", json={"status": "done", "memo": "SCHEDULE_EFFECT を使う"}).status_code == 200
    assert author.get("/api/catalog/overview").get_json()["open_requests"] == 0
    assert author.get(URL).get_json()["requests"][0]["memo"] == "SCHEDULE_EFFECT を使う"
    other = author.post(URL, json=BODY).get_json()
    assert author.get(URL).get_json()["requests"][0]["id"] == other["id"]
    assert author.delete(f"{URL}/{other['id']}").status_code == 200


@pytest.mark.parametrize("extra", [{"title": " "}, {"title": "題" * 81}, {"want": []}, {"near_type": "UNKNOWN"}, {"draft_id": True}])
def test_invalid_fields(catalog, extra):
    author = client(catalog, "author")
    assert author.post(URL, json=BODY | extra).status_code == 422
    assert author.get(URL).get_json()["requests"] == []


def test_draft_snapshot_survives_publication_and_withdrawal(catalog):
    db.session.execute(text("PRAGMA foreign_keys = ON"))
    author, admin = client(catalog, "author"), client(catalog, "admin")
    for kind in ("glossary", "summon"):
        draft = author.post(f"/api/catalog/{kind}/drafts", json={}).get_json()
        assert author.post(URL, json=BODY | {"draft_id": draft["id"]}).status_code == 422
    draft = author.post("/api/catalog/skill/drafts", json={"id_prefix": "Ps"}).get_json()
    draft_path = f"/api/catalog/drafts/{draft['id']}"
    assert author.put(draft_path, json={"payload": {"デフォルト名称": "確認", "分類": "物理"}}).status_code == 200
    linked = author.post(URL, json=BODY | {"draft_id": draft["id"]}).get_json()
    assert (linked["draft_kind"], linked["draft_target_id"], linked["draft_name"]) == ("skill", draft["target_id"], "確認")
    unlinked = author.post(URL, json=BODY | {"draft_id": draft["id"]}).get_json()
    assert author.patch(f"{URL}/{unlinked['id']}", json={"draft_id": draft["id"]}).status_code == 422
    unlinked = author.patch(f"{URL}/{unlinked['id']}", json={"draft_id": None}).get_json()
    assert unlinked["draft_id"] is None and unlinked["draft_kind"] is None
    assert author.post(draft_path + "/submit").status_code == 200
    assert admin.post(draft_path + "/approve", json={"entry_id": "Ps-99"}).status_code == 200
    row = next(row for row in author.get(URL).get_json()["requests"] if row["id"] == linked["id"])
    assert (row["draft_id"], row["draft_kind"], row["draft_target_id"], row["draft_name"]) == (None, "skill", "Ps-99", "確認")
    buff = author.post("/api/catalog/buff/drafts", json={"target_id": "Bu-00"}).get_json()
    row = author.post(URL, json=BODY | {"draft_id": buff["id"]}).get_json()
    assert author.delete(f"/api/catalog/drafts/{buff['id']}").status_code == 200
    saved = author.get(URL).get_json()["requests"][0]
    assert saved["id"] == row["id"] and saved["draft_id"] is None and saved["draft_target_id"] == "Bu-00"

