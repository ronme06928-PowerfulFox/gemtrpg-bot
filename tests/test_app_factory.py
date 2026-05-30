import os

os.environ["GEMTRPG_SKIP_IMPORT_STARTUP"] = "1"

from app import create_app


def test_create_app_without_startup_registers_http_routes():
    test_app = create_app(
        config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        },
        run_startup=False,
        register_sockets=False,
    )

    routes = {rule.rule for rule in test_app.url_map.iter_rules()}

    assert len(test_app.url_map._rules) == 34
    assert "/" in routes
    assert "/api/get_session_user" in routes
    assert "/api/upload_image" in routes
    assert "/api/local_images" in routes
