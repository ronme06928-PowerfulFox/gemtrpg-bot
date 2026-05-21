import pytest
from flask import Flask

from extensions import db
from manager.user_manager import (
    recover_user_by_local_token,
    recover_user_by_name_and_code,
    regenerate_user_recovery_code,
    upsert_user,
)
from models import User


@pytest.fixture()
def recovery_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_new_user_gets_one_time_recovery_code_and_token(recovery_app):
    with recovery_app.app_context():
        result = upsert_user("user-1", "Alice", issue_recovery=True)
        user = User.query.get("user-1")

        assert user is not None
        assert result["recovery_code"].startswith("GEM-")
        assert result["recovery_token"]
        assert user.recovery_code_hash
        assert user.recovery_token_hash

        second = upsert_user("user-1", "Alice", issue_recovery=True)
        assert second["recovery_code"] is None
        assert second["recovery_token"]


def test_recover_user_by_name_and_code_restores_existing_user(recovery_app):
    with recovery_app.app_context():
        result = upsert_user("user-2", "Bob", issue_recovery=True)

        recovered = recover_user_by_name_and_code("Bob", result["recovery_code"])

        assert recovered is not None
        assert recovered["user"].id == "user-2"
        assert recovered["recovery_token"]
        assert recover_user_by_name_and_code("Bob", "GEM-XXXX-XXXX") is None


def test_local_token_recovery_uses_saved_internal_token(recovery_app):
    with recovery_app.app_context():
        result = upsert_user("user-3", "Carol", issue_recovery=True)

        recovered = recover_user_by_local_token("user-3", result["recovery_token"])

        assert recovered is not None
        assert recovered.id == "user-3"
        assert recover_user_by_local_token("user-3", "wrong-token") is None


def test_regenerate_recovery_code_invalidates_old_code(recovery_app):
    with recovery_app.app_context():
        first = upsert_user("user-4", "Dana", issue_recovery=True)
        second = regenerate_user_recovery_code("user-4")

        assert second["recovery_code"].startswith("GEM-")
        assert second["recovery_code"] != first["recovery_code"]
        assert recover_user_by_name_and_code("Dana", first["recovery_code"]) is None
        assert recover_user_by_name_and_code("Dana", second["recovery_code"]) is not None

