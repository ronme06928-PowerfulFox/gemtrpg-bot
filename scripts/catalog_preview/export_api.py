"""PR60-19 の試作用に、管理画面が読む API の返事を本物のサーバーから書き出す。

メモリ上の SQLite に7種類を取り込み、管理者として各 API を呼んだ結果を JSON で標準出力へ出す。
手元の instance/ の DB には触らない。
"""
import contextlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"
sys.stdout.reconfigure(encoding="utf-8")

with contextlib.redirect_stdout(sys.stderr):
    from app import create_app
    from extensions import db
    from manager.catalog import repository as repo
    from manager.catalog.kinds import KINDS
    from models import User

    app = create_app(config={"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "SQLALCHEMY_ENGINE_OPTIONS": {}},
                     run_startup=False, register_sockets=False)
    out = {"lists": {}}
    with app.app_context():
        db.create_all()
        db.session.add_all([User(id="admin", name="管理者", is_app_admin=True),
                            User(id="author", name="制作者", is_catalog_author=True)])
        db.session.commit()
        # 参照の検査があるので、参照される側から取り込む。
        for kind in ("glossary", "buff", "skill", "item", "passive", "radiance", "summon"):
            repo.seed_kind_if_empty(kind)
            repo.load_kind_into_memory(kind)
        client = app.test_client()
        with client.session_transaction() as session:
            session.update(user_id="admin", username="admin", auth_version=1, is_app_admin=True, is_catalog_author=True)
        # 承認待ちが1件ずつある状態にする（件数の札と承認待ちの一覧を見るため）。
        for kind, target, change in [("skill", "Ps-01", ("使用時効果", " 追記した文")), ("buff", "Bu-00", ("description", "（改）"))]:
            created = client.post(f"/api/catalog/{kind}/drafts", json={"target_id": target}).get_json()
            payload = dict(created["payload"])
            payload[change[0]] = str(payload.get(change[0], "")) + change[1]
            client.put(f"/api/catalog/drafts/{created['id']}", json={"payload": payload})
            client.post(f"/api/catalog/drafts/{created['id']}/submit")
        out["user"] = {"user_id": "admin", "username": "管理者", "is_app_admin": True, "is_catalog_author": True}
        for kind in KINDS:
            out["lists"][kind] = client.get(f"/api/catalog/{kind}").get_json()
        out["overview"] = client.get("/api/catalog/overview").get_json()
        out["effect_schemas"] = client.get("/api/effect_schemas").get_json()
        out["text_references"] = client.get("/api/catalog/skill/text_references").get_json()
        out["sample_history"] = client.get("/api/catalog/skill/Ps-00/history").get_json()
        out["sample_references"] = client.get("/api/catalog/buff/Bu-00/references").get_json()

json.dump(out, sys.stdout, ensure_ascii=False)
sys.stdout.write("\n")
