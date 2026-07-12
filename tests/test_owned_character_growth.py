"""計画36 Phase 5: コスト計算(compute_exp_limit/compute_used_exp)と
POST /api/owned_characters/<id>/growth の回帰テスト。
"""
import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

import pytest

from app import create_app
from extensions import db
import extensions
from models import User, OwnedCharacter
from routes import owned_characters as oc


FAKE_SKILLS = {
    "B-01": {"取得コスト": "2", "チャットパレット": "0+0 【B-01 テスト魔法】"},
    "Ps-01": {"取得コスト": "1", "チャットパレット": "1d6 【Ps-01 斬撃】"},
    "Ms-01": {"取得コスト": "3", "チャットパレット": "2d6 【Ms-01 魔法斬撃】"},
}


@pytest.fixture(autouse=True)
def patch_skill_data(monkeypatch):
    monkeypatch.setattr(extensions, "all_skill_data", FAKE_SKILLS)
    monkeypatch.setattr(oc, "all_skill_data", FAKE_SKILLS)
    yield


@pytest.fixture
def app_ctx(tmp_path):
    db_path = tmp_path / "owned_growth.db"
    app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )
    with app.app_context():
        db.create_all()
        db.session.add(User(id="owner", name="owner"))
        db.session.add(User(id="stranger", name="stranger"))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app_ctx):
    return app_ctx.test_client()


def _login(client, user_id):
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s["username"] = user_id
        s["attribute"] = "Player"
        s["auth_version"] = 1


# ---------------------------------------------------------------------------
# compute_exp_limit / compute_used_exp: CharaCreatorのcalculateStats()と同値になること
# ---------------------------------------------------------------------------

def test_compute_exp_limit_basic():
    data = {"params": [{"label": "経験", "value": "5"}, {"label": "シナリオ経験", "value": "2"}]}
    assert oc.compute_exp_limit(data) == 7


def test_compute_exp_limit_origin7_bonus():
    data = {"params": [
        {"label": "経験", "value": "5"}, {"label": "シナリオ経験", "value": "0"},
        {"label": "出身", "value": "7"},
    ]}
    assert oc.compute_exp_limit(data) == 6


def test_compute_used_exp_sums_skill_costs():
    data = {"commands": "1d6 【Ps-01 斬撃】\n0+0 【B-01 テスト魔法】"}
    # Ps-01(1) + B-01(2) = 3, no magic bonus (origin != 6)
    assert oc.compute_used_exp(data) == 3


def test_compute_used_exp_ignores_unknown_skill():
    data = {"commands": "1d6 【ZZZ-99 未知】"}
    assert oc.compute_used_exp(data) == 0


def test_compute_used_exp_origin6_magic_bonus_discount():
    data = {
        "commands": "2d6 【Ms-01 魔法斬撃】",
        "params": [{"label": "出身", "value": "6"}],
    }
    # Ms-01 cost=3, origin6 gives 1 point magic bonus discount -> 3-1=2
    assert oc.compute_used_exp(data) == 2


def test_compute_used_exp_origin6_bonus_only_applies_to_magic():
    data = {
        "commands": "1d6 【Ps-01 斬撃】",
        "params": [{"label": "出身", "value": "6"}],
    }
    # Ps-01 is not a magic category (Ps != Ms/Mb/Mp), bonus doesn't apply
    assert oc.compute_used_exp(data) == 1


# ---------------------------------------------------------------------------
# POST /api/owned_characters/<id>/growth
# ---------------------------------------------------------------------------

def _make_owned_character(exp_total=5, commands=""):
    return OwnedCharacter(
        id="owned_1",
        user_id="owner",
        name="成長テストキャラ",
        data={"name": "成長テストキャラ", "commands": commands, "params": [{"label": "筋力", "value": "3"}]},
        exp_total=exp_total,
        growth_log=[],
    )


def test_growth_adds_skill_within_budget(client, app_ctx):
    with app_ctx.app_context():
        db.session.add(_make_owned_character(exp_total=5))
        db.session.commit()

    _login(client, "owner")
    resp = client.post("/api/owned_characters/owned_1/growth", json={"add_skill_ids": ["Ps-01"]})
    assert resp.status_code == 200
    body = resp.get_json()["character"]
    assert "【Ps-01" in body["data"]["commands"]
    assert body["used_exp"] == 1
    assert body["remaining_exp"] == 4
    assert body["exp_total"] == 5  # exp_total itself is untouched


def test_growth_rejects_when_over_budget(client, app_ctx):
    with app_ctx.app_context():
        db.session.add(_make_owned_character(exp_total=1))
        db.session.commit()

    _login(client, "owner")
    resp = client.post("/api/owned_characters/owned_1/growth", json={"add_skill_ids": ["B-01"]})  # cost 2 > budget 1
    assert resp.status_code == 400
    assert "経験値が不足" in resp.get_json()["error"]

    with app_ctx.app_context():
        owned = OwnedCharacter.query.get("owned_1")
        assert owned.data["commands"] == ""  # not mutated
        assert owned.growth_log == []


def test_growth_param_increase_via_endpoint(client, app_ctx):
    with app_ctx.app_context():
        db.session.add(_make_owned_character(exp_total=3))
        db.session.commit()

    _login(client, "owner")
    resp = client.post("/api/owned_characters/owned_1/growth", json={"param_increases": {"筋力": 2}})
    assert resp.status_code == 200
    body = resp.get_json()["character"]
    strength = next(p for p in body["data"]["params"] if p["label"] == "筋力")
    assert strength["value"] == "5"  # 3 + 2
    assert body["remaining_exp"] == 1  # 3 - 2


def test_growth_rejects_unknown_skill_id(client, app_ctx):
    with app_ctx.app_context():
        db.session.add(_make_owned_character(exp_total=10))
        db.session.commit()

    _login(client, "owner")
    resp = client.post("/api/owned_characters/owned_1/growth", json={"add_skill_ids": ["NOPE-1"]})
    assert resp.status_code == 400
    assert "未知のスキルID" in resp.get_json()["error"]


def test_growth_records_growth_log(client, app_ctx):
    with app_ctx.app_context():
        db.session.add(_make_owned_character(exp_total=5))
        db.session.commit()

    _login(client, "owner")
    client.post("/api/owned_characters/owned_1/growth", json={"add_skill_ids": ["Ps-01"]})

    with app_ctx.app_context():
        owned = OwnedCharacter.query.get("owned_1")
        assert len(owned.growth_log) == 1
        assert owned.growth_log[0]["kind"] == "growth"
        assert owned.growth_log[0]["added_skill_ids"] == ["Ps-01"]
        assert owned.growth_log[0]["cost"] == 1


def test_growth_cross_user_isolation(client, app_ctx):
    with app_ctx.app_context():
        db.session.add(_make_owned_character(exp_total=5))
        db.session.commit()

    _login(client, "stranger")
    resp = client.post("/api/owned_characters/owned_1/growth", json={"add_skill_ids": ["Ps-01"]})
    assert resp.status_code == 404


def test_growth_param_spend_persists_and_accumulates_across_calls(client, app_ctx):
    """パラメータ上昇の消費が正しく永続化され、2回目以降の呼び出しでも
    正しい残り経験値を基準に予算チェックされることを確認する
    （SQLAlchemyのJSON列変更検知の別名参照バグの再発防止テスト）。
    """
    with app_ctx.app_context():
        db.session.add(_make_owned_character(exp_total=5))
        db.session.commit()

    _login(client, "owner")
    resp1 = client.post("/api/owned_characters/owned_1/growth", json={"param_increases": {"筋力": 2}})
    assert resp1.status_code == 200
    assert resp1.get_json()["character"]["remaining_exp"] == 3

    # 2回目: 残り3のところへコスト3を要求 -> ちょうど使い切れる
    resp2 = client.post("/api/owned_characters/owned_1/growth", json={"param_increases": {"筋力": 3}})
    assert resp2.status_code == 200
    body2 = resp2.get_json()["character"]
    assert body2["remaining_exp"] == 0
    strength = next(p for p in body2["data"]["params"] if p["label"] == "筋力")
    assert strength["value"] == "8"  # 3 + 2 + 3

    # 3回目: 残り0のところへさらに要求 -> 拒否され、値は変化しない
    resp3 = client.post("/api/owned_characters/owned_1/growth", json={"param_increases": {"筋力": 1}})
    assert resp3.status_code == 400

    with app_ctx.app_context():
        owned = OwnedCharacter.query.get("owned_1")
        strength_final = next(p for p in owned.data["params"] if p["label"] == "筋力")
        assert strength_final["value"] == "8"  # 拒否された3回目の影響を受けていない
        assert len(owned.growth_log) == 2  # 成功した1・2回目のみ記録


def test_skill_exp_budget_excludes_param_spend_but_not_skill_spend(client, app_ctx):
    """CharaCreator再編集時に渡す`skill_exp_budget`は、パラメータ成長で消費した分だけを
    exp_totalから差し引いた値であること（スキルコスト分は、CharaCreator側が現在選択中の
    スキルとして別途カウントするため、ここでは差し引かない）。
    """
    with app_ctx.app_context():
        db.session.add(_make_owned_character(exp_total=10))
        db.session.commit()

    _login(client, "owner")
    resp1 = client.post("/api/owned_characters/owned_1/growth", json={"add_skill_ids": ["Ps-01"]})  # cost 1
    assert resp1.status_code == 200
    body1 = resp1.get_json()["character"]
    assert body1["remaining_exp"] == 9
    # スキルコストはCharaCreator側が commands から数えるため、skill_exp_budget には未反映のまま。
    assert body1["skill_exp_budget"] == 10

    resp2 = client.post("/api/owned_characters/owned_1/growth", json={"param_increases": {"筋力": 3}})
    assert resp2.status_code == 200
    body2 = resp2.get_json()["character"]
    assert body2["remaining_exp"] == 6  # 10 - 1(skill) - 3(param)
    # パラメータ成長の消費分だけが skill_exp_budget から差し引かれる。
    assert body2["skill_exp_budget"] == 7  # 10 - 3(param only)


def test_creation_seeds_exp_total_from_params(client, app_ctx):
    _login(client, "owner")
    resp = client.post("/api/owned_characters", json={
        "kind": "character",
        "data": {
            "name": "初期予算テスト",
            "params": [{"label": "経験", "value": "4"}, {"label": "シナリオ経験", "value": "1"}],
        },
    })
    assert resp.status_code == 201
    body = resp.get_json()["character"]
    assert body["exp_total"] == 5
    assert body["remaining_exp"] == 5
