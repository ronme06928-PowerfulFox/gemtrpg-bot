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

    assert len(test_app.url_map._rules) == 50
    assert "/" in routes
    assert "/healthz" in routes
    assert "/api/get_session_user" in routes
    assert "/api/upload_image" in routes
    assert "/api/local_images" in routes
    # Phase 2: アカウント認証ルート
    assert "/api/register" in routes
    assert "/api/login" in routes
    assert "/api/set_password" in routes
    assert "/api/change_display_name" in routes
    # Phase 3: ログアウト
    assert "/api/logout" in routes
    # Phase 4: 管理者ワンタイムコード
    assert "/api/admin/issue_login_code" in routes
    assert "/api/redeem_login_code" in routes
    # Phase 5: ルームメンバー管理
    assert "/api/room/grant_gm" in routes
    assert "/api/room/transfer_owner" in routes
    # Phase 6: 参加コード・公開ロビー
    assert "/api/join_room_by_code" in routes
    assert "/api/room/set_join_code" in routes
