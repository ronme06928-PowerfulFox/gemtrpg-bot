from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import Mock

import cloudinary
import cloudinary.api
from cloudinary.exceptions import GeneralError
from eventlet import sleep
from flask import Flask
import pytest
from urllib3.exceptions import MaxRetryError, NewConnectionError, ReadTimeoutError

from extensions import db, socketio
from models import User
from routes.admin import admin_bp


URL = "/api/admin/image_usage"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test", SQLALCHEMY_DATABASE_URI="sqlite://")
    db.init_app(app)
    app.register_blueprint(admin_bp)
    with app.app_context():
        db.create_all()
        db.session.add_all([
            User(id="admin", name="管理者", is_app_admin=True),
            User(id="reader", name="一般"),
        ])
        db.session.commit()
    return app


@pytest.fixture
def usage(monkeypatch):
    config = SimpleNamespace(cloud_name="test", api_key="fake-key", api_secret="fake-secret")
    monkeypatch.setattr(cloudinary, "config", lambda: config)
    usage = Mock()
    monkeypatch.setattr(cloudinary.api, "usage", usage)
    return config, usage


def get_usage(app, actor):
    client = app.test_client()
    if actor:
        with client.session_transaction() as session:
            session.update(user_id=actor, username=actor, auth_version=1, is_app_admin=True)
    return client.get(URL)


@pytest.mark.parametrize("used, over_half", [(20, False), (20.01, True)])
def test_admin_gets_current_usage_and_half_limit(app, usage, used, over_half):
    _, fetch = usage
    fetch.return_value = {
        "credits": {"usage": used, "limit": 40, "used_percent": 50},
        "storage": {"usage": 6_000_000_000, "credits_usage": 6},
        "bandwidth": {"usage": 5_000_000_000, "credits_usage": 5},
        "transformations": {"usage": 9000, "credits_usage": 9},
        "last_updated": "2026-11-21",
        "extra": "fake-secret",
    }
    response = get_usage(app, "admin")
    assert response.status_code == 200
    assert response.json == {
        "available": True,
        "credits": {"usage": used, "limit": 40, "percent": used / 40 * 100},
        "breakdown": {
            "storage": {"usage": 6_000_000_000, "credits": 6},
            "bandwidth": {"usage": 5_000_000_000, "credits": 5},
            "transformations": {"usage": 9000, "credits": 9},
        },
        "last_updated": "2026-11-21",
        "over_half": over_half,
    }
    fetch.assert_called_once_with(timeout=3)


@pytest.mark.parametrize("actor, status", [(None, 401), ("reader", 403)])
def test_only_app_admin_can_fetch_usage(app, usage, actor, status):
    _, fetch = usage
    assert get_usage(app, actor).status_code == status
    fetch.assert_not_called()


def test_missing_credentials(app, usage):
    config, fetch = usage
    config.api_key = None
    response = get_usage(app, "admin")
    assert response.status_code == 200
    assert response.json == {"available": False, "reason": "Cloudinary の鍵が未設定です"}
    fetch.assert_not_called()


def test_cloudinary_failure_hides_exception_text(app, usage, caplog):
    _, fetch = usage
    fetch.side_effect = GeneralError("fake-key fake-secret")
    response = get_usage(app, "admin")
    assert response.status_code == 200
    assert response.json == {"available": False, "reason": "Cloudinary との通信に失敗しました"}
    assert "fake-key" not in caplog.text and "fake-secret" not in caplog.text
    fetch.assert_called_once()


def test_sdk_wrapped_network_timeout(app, usage, caplog):
    _, fetch = usage

    def fail(**_):
        try:
            raise MaxRetryError(None, "/", ReadTimeoutError(None, "/", "fake-secret"))
        except MaxRetryError:
            raise GeneralError("fake-key fake-secret")

    fetch.side_effect = fail
    response = get_usage(app, "admin")
    assert response.status_code == 200
    assert response.json == {"available": False, "reason": "Cloudinary の応答が時間切れです"}
    assert "fake-key" not in caplog.text and "fake-secret" not in caplog.text


def test_connection_refused_is_a_communication_failure(app, usage):
    _, fetch = usage
    fetch.side_effect = MaxRetryError(None, "/", NewConnectionError(None, "Connection refused"))
    assert get_usage(app, "admin").json == {
        "available": False, "reason": "Cloudinary との通信に失敗しました",
    }


def test_eventlet_deadline_interrupts_waiting_sdk(app, usage, monkeypatch):
    _, fetch = usage
    monkeypatch.setattr(socketio, "async_mode", "eventlet", raising=False)
    monkeypatch.setattr("routes.admin.IMAGE_USAGE_TIMEOUT", 0.01)

    def wait(**_):
        sleep(0.2)
        pytest.fail("Cloudinary call outlived its deadline")

    fetch.side_effect = wait
    response = get_usage(app, "admin")
    assert response.status_code == 200
    assert response.json == {"available": False, "reason": "Cloudinary の応答が時間切れです"}
    fetch.assert_called_once()


def test_image_usage_card_is_in_user_management_and_bundles():
    page = (ROOT / "static/index.html").read_text(encoding="utf-8")
    assert page.index("画像の使用量（Cloudinary）") < page.index('id="user-list-container"')
    for path in ("static/js/user_management.js", "static/dist/app.bundle.js"):
        script = (ROOT / path).read_text(encoding="utf-8")
        script = re.sub(r'\\u([0-9a-fA-F]{4})', lambda match: chr(int(match[1], 16)), script)
        assert URL in script
        assert "使用量を取得できませんでした" in script
        assert "無料枠の半分を超えました。保存先の移行を検討してください" in script
    css = (ROOT / "static/dist/app.bundle.css").read_text(encoding="utf-8")
    assert ".image-usage-card.is-over-half" in css
