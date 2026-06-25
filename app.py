import os
import logging

# ロギング設定 - DEBUGレベルのログを有効化
log_level = logging.INFO if 'RENDER' in os.environ else logging.DEBUG
logging.basicConfig(
    level=log_level,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 1. 【最優先】Render環境ならパッチを当てる
# eventlet.monkey_patch() は、他の標準ライブラリ（socket, threading等）がインポートされる前に実行する必要があります。
# os は安全ですが、他は極力後にインポートします。
if 'RENDER' in os.environ:
    import eventlet
    eventlet.monkey_patch()

import sys
import argparse

IS_RENDER = 'RENDER' in os.environ

from flask import Flask, current_app, g, jsonify, request, send_from_directory, session
from flask_cors import CORS
from flask_compress import Compress # 追加: 圧縮転送用ライブラリ
from whitenoise import WhiteNoise # 追加: 静的ファイル配信高速化

# ★ 拡張機能（共有インスタンス）のインポート
from extensions import db, socketio, active_room_states, all_skill_data, all_glossary_data
from models import Room, User

# ★ マネージャー（ロジック層）からのインポート
from manager.data_manager import (
    init_app_data, read_saved_rooms, read_saved_rooms_with_owners, save_room_to_db, delete_room_from_db
)
from manager.room_manager import get_room_state
from manager.utils import session_required
from manager.json_rule_audit import append_audit
from manager.auth import (
    GM_ATTRIBUTE,
    PLAYER_ATTRIBUTE,
    hash_gm_pin,
    is_valid_gm_pin,
    resolve_room_attribute,
    verify_master_key,
    verify_room_gm_key,
)

import uuid
from datetime import datetime
import cloudinary
import cloudinary.uploader

from manager import account_auth, device_token, one_time_code
from manager.auth_rate_limit import password_login_limiter, one_time_code_limiter

# ★追加インポート
from manager.user_manager import (
    upsert_user,
    get_all_users,
    delete_user,
    transfer_ownership,
    get_user_owned_items,
    is_user_management_admin,
    recover_user_by_local_token,
    recover_user_by_name_and_code,
    regenerate_user_recovery_code,
    set_user_management_admin,
)

# === アプリ設定 ===
load_dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(load_dotenv_path):
    from dotenv import load_dotenv
    load_dotenv(load_dotenv_path)

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
_SOCKET_HANDLERS_REGISTERED = False

def _is_production_env():
    return (
        IS_RENDER
        or str(os.environ.get('FLASK_ENV') or '').lower() == 'production'
        or str(os.environ.get('APP_ENV') or '').lower() == 'production'
    )


def _get_secret_key():
    secret_key = str(os.environ.get('SECRET_KEY') or '').strip()
    if secret_key:
        return secret_key
    if _is_production_env():
        raise RuntimeError('SECRET_KEY must be set in production.')
    logging.warning('SECRET_KEY is not set; using development fallback.')
    return 'dev-gem-trpg-secret-key'


def _get_cors_origins():
    raw = str(os.environ.get('CORS_ORIGINS') or '').strip()
    if raw:
        origins = [origin.strip() for origin in raw.split(',') if origin.strip()]
        if origins:
            return origins
    if _is_production_env():
        raise RuntimeError('CORS_ORIGINS must be set in production.')
    return [
        'http://localhost:5000',
        'http://127.0.0.1:5000',
        'http://localhost:3000',
        'http://127.0.0.1:3000',
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ]


def _get_database_uri():
    # Local runs must never use DATABASE_URL.  DATABASE_URL belongs to Render.
    if not IS_RENDER:
        return 'sqlite:///gemtrpg.db'
    # Render must fail closed: a missing or non-PostgreSQL DATABASE_URL would
    # silently boot a separate empty SQLite DB and look like data loss, instead
    # of honoring the local/Render separation guarantee.
    url = str(os.environ.get('DATABASE_URL') or '').strip()
    if not url:
        raise RuntimeError(
            'DATABASE_URL must be set on Render. Refusing to fall back to SQLite.'
        )
    if not url.startswith(('postgres://', 'postgresql://', 'postgresql+')):
        raise RuntimeError(
            'DATABASE_URL on Render must point to PostgreSQL. '
            f'Refusing to start with: {url.split("://", 1)[0]}://...'
        )
    return url


def configure_app(flask_app, config=None):
    global STATIC_DIR
    flask_app.config['JSON_AS_ASCII'] = False
    flask_app.config['SECRET_KEY'] = _get_secret_key()
    # Session cookie hardening (同一オリジン構成のため SameSite=Lax で十分。
    # 公開環境では Secure を強制し、平文HTTP越しにCookieを送らせない)。
    flask_app.config['SESSION_COOKIE_HTTPONLY'] = True
    flask_app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    flask_app.config['SESSION_COOKIE_SECURE'] = _is_production_env()
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = _get_database_uri()
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    flask_app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
    flask_app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 10,
        'max_overflow': 20
    }
    if config:
        flask_app.config.update(config)
    STATIC_DIR = os.path.join(flask_app.root_path, 'static')
    return flask_app


def init_extensions(flask_app, cors_origins=None):
    cors_origins = cors_origins or _get_cors_origins()
    flask_app.wsgi_app = WhiteNoise(flask_app.wsgi_app, root=STATIC_DIR, prefix='static/')
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET')
    )
    CORS(flask_app, supports_credentials=True, origins=cors_origins)
    Compress(flask_app)
    db.init_app(flask_app)
    async_mode = 'eventlet' if IS_RENDER else 'threading'
    socketio.init_app(flask_app, cors_allowed_origins=cors_origins, async_mode=async_mode)
    return flask_app


def run_startup_tasks(flask_app):
    with flask_app.app_context():
        if IS_RENDER:
            print("--- Checking Render Database Schema ---")
            from manager.db_migration import run_auto_migration
            run_auto_migration(flask_app)
            print()

        db.create_all()

        from plugins.buffs.registry import buff_registry
        buff_registry.auto_discover()

        init_app_data(create_db_tables=False)
        read_saved_rooms_with_owners()


def register_socket_handlers():
    global _SOCKET_HANDLERS_REGISTERED
    if _SOCKET_HANDLERS_REGISTERED:
        return

    import events.socket_main
    import events.socket_char
    import events.socket_battle_only
    import events.socket_room_presets
    import events.battle
    import events.socket_wide_calculate
    import events.socket_items
    import events.socket_exploration

    _SOCKET_HANDLERS_REGISTERED = True


def create_app(config=None, run_startup=True, register_sockets=True, register_routes=True):
    flask_app = Flask(__name__, static_folder=None)
    configure_app(flask_app, config=config)
    cors_origins = _get_cors_origins()
    init_extensions(flask_app, cors_origins=cors_origins)
    if register_routes:
        register_http_routes(flask_app)
    if run_startup:
        run_startup_tasks(flask_app)
    if register_sockets:
        register_socket_handlers()
    return flask_app


def _should_run_startup_on_import():
    return os.environ.get('GEMTRPG_SKIP_IMPORT_STARTUP') != '1'


def _should_create_default_app():
    return os.environ.get('GEMTRPG_DISABLE_DEFAULT_APP') != '1'

# ==========================================
#  HTTP Routes
# ==========================================

def serve_index():
    print(f"[INFO] Accessing Root! Serving from: {STATIC_DIR}")
    return send_from_directory(STATIC_DIR, 'index.html')


def healthz():
    """
    死活監視/スピンダウン防止用の軽量エンドポイント。
    DBや外部APIに触れず即応するため、外部pingサービス(UptimeRobot等)から
    短間隔で叩いてもインスタンスへの負荷はほぼ無い。
    """
    return 'ok', 200, {'Content-Type': 'text/plain; charset=utf-8'}


# マスターデータ系API（スキル・アイテム等）。`--update` 実行時にしか内容が
# 変わらないため、ブラウザキャッシュ + ETag条件付きリクエストで再取得を抑制する。
MASTER_DATA_CACHE_PATHS = frozenset({
    '/api/get_skill_data',
    '/api/get_skill_metadata',
    '/api/get_item_data',
    '/api/get_radiance_data',
    '/api/get_passive_data',
    '/api/get_buff_data',
    '/api/get_glossary_data',
})


def add_header(response):
    """
    静的ファイル(画像, CSS, JS)に強力なキャッシュヘッダーを付与する
    (WhiteNoiseが処理しきれない場合や、動的生成コンテンツへのキャッシュ適用のため)
    """
    if (
        request.path.startswith('/static/')
        or request.path.startswith('/images/')
        or request.path.startswith('/dist/')
    ):
        # Cache for 1 year. /dist のバンドルは ?v=<contenthash> でバスティングされるため
        # 内容変更時はURLが変わる → 1年immutableキャッシュにして再検証を不要にする。
        response.headers['Cache-Control'] = 'public, max-age=31536000'
    elif (
        request.method == 'GET'
        and response.status_code == 200
        and request.path in MASTER_DATA_CACHE_PATHS
    ):
        # 短期キャッシュ + ETagで条件付き再検証。max-age内は再取得なし、
        # 期限切れ後も内容が同じなら304(本文なし)で済むため転送・パースを削減。
        response.headers['Cache-Control'] = 'public, max-age=300'
        response.add_etag()
        return response.make_conditional(request)
    return response


# === パフォーマンス計測（実測用） ===
# 環境変数で制御:
#   PERF_LOG=1        … 全リクエストの所要時間を [PERF] 行で出力（詳細計測モード）
#   SLOW_REQUEST_MS   … この閾値(ms)以上のリクエストは PERF_LOG 無しでも警告（既定 500）
# Render の Logs を "[PERF]" で絞り込めば、遅いエンドポイントが一覧できる。
import time as _time

PERF_LOG = os.environ.get('PERF_LOG') == '1'
try:
    SLOW_REQUEST_MS = float(os.environ.get('SLOW_REQUEST_MS', '500'))
except (TypeError, ValueError):
    SLOW_REQUEST_MS = 500.0


def _perf_before():
    g._perf_start = _time.perf_counter()


def _perf_after(response):
    start = getattr(g, '_perf_start', None)
    if start is None:
        return response
    dur_ms = (_time.perf_counter() - start) * 1000.0
    if PERF_LOG or dur_ms >= SLOW_REQUEST_MS:
        try:
            size = response.calculate_content_length()
        except Exception:
            size = None
        logging.info(
            "[PERF] %s %s -> %s %.0fms %sB",
            request.method, request.path, response.status_code,
            dur_ms, size if size is not None else '?',
        )
    return response


# モバイル版は開発停止中（PC Web版中心の方針）。公開導線として /mobile を
# 明示的に停止し、安全化されていない旧導線が裏口として残らないようにする。
MOBILE_SUSPENDED_HTML = (
    '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<title>モバイル版は停止中です</title></head>'
    '<body style="font-family:sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem;line-height:1.7">'
    '<h1>モバイル版は現在停止中です</h1>'
    '<p>モバイル版は開発を一時停止しています。PC（Web）版をご利用ください。</p>'
    '<p><a href="/">PC版を開く</a></p>'
    '</body></html>'
)


def serve_mobile_index():
    return MOBILE_SUSPENDED_HTML, 404, {'Content-Type': 'text/html; charset=utf-8'}


def serve_static_files(filename):
    # モバイル版アセットの直接読み出しも停止する（/mobile 停止の裏口を塞ぐ）。
    normalized = str(filename or '').lstrip('/')
    if normalized == 'mobile' or normalized.startswith('mobile/'):
        return MOBILE_SUSPENDED_HTML, 404, {'Content-Type': 'text/html; charset=utf-8'}
    return send_from_directory(STATIC_DIR, filename)


def register_http_routes(flask_app):
    flask_app.add_url_rule('/', 'serve_index', serve_index)
    flask_app.add_url_rule('/healthz', 'healthz', healthz)
    # perf計測: after_request は登録の逆順で実行されるため、_perf_after を先に
    # 登録して add_header の後（=最終レスポンス確定後）に計測させる。
    flask_app.before_request(_perf_before)
    flask_app.after_request(_perf_after)
    flask_app.after_request(add_header)
    flask_app.add_url_rule('/mobile', 'serve_mobile_index', serve_mobile_index)
    flask_app.add_url_rule('/<path:filename>', 'serve_static_files', serve_static_files)
    flask_app.add_url_rule('/get_skill', 'get_skill', get_skill)
    flask_app.add_url_rule('/api/get_skill_metadata', 'get_skill_metadata', get_skill_metadata, methods=['GET'])
    flask_app.add_url_rule('/api/get_skill_data', 'get_skill_data', get_skill_data, methods=['GET'])
    flask_app.add_url_rule('/api/get_item_data', 'get_item_data', get_item_data, methods=['GET'])
    flask_app.add_url_rule('/api/get_radiance_data', 'get_radiance_data', get_radiance_data, methods=['GET'])
    flask_app.add_url_rule('/api/get_passive_data', 'get_passive_data', get_passive_data, methods=['GET'])
    flask_app.add_url_rule('/api/get_buff_data', 'get_buff_data', get_buff_data, methods=['GET'])
    flask_app.add_url_rule('/api/get_glossary_data', 'get_glossary_data', get_glossary_data, methods=['GET'])
    flask_app.add_url_rule('/api/upload_image', 'upload_image', upload_image, methods=['POST'])
    flask_app.add_url_rule('/api/images', 'get_images_api', get_images_api, methods=['GET'])
    flask_app.add_url_rule('/api/images/<image_id>', 'delete_image_api', delete_image_api, methods=['DELETE'])
    flask_app.add_url_rule('/api/local_images', 'get_local_images', get_local_images, methods=['GET'])
    flask_app.add_url_rule('/api/entry', 'entry', entry, methods=['POST'])
    flask_app.add_url_rule('/api/register', 'register_account', register_account, methods=['POST'])
    flask_app.add_url_rule('/api/login', 'login_account', login_account, methods=['POST'])
    flask_app.add_url_rule('/api/set_password', 'set_account_password', set_account_password, methods=['POST'])
    flask_app.add_url_rule('/api/change_display_name', 'change_display_name', change_display_name, methods=['POST'])
    flask_app.add_url_rule('/api/logout', 'logout_account', logout_account, methods=['POST'])
    flask_app.add_url_rule('/api/admin/issue_login_code', 'admin_issue_login_code', admin_issue_login_code, methods=['POST'])
    flask_app.add_url_rule('/api/redeem_login_code', 'redeem_login_code', redeem_login_code, methods=['POST'])
    flask_app.add_url_rule('/api/recover_user', 'recover_user', recover_user, methods=['POST'])
    flask_app.add_url_rule('/api/recover_from_local_token', 'recover_from_local_token', recover_from_local_token, methods=['POST'])
    flask_app.add_url_rule('/api/regenerate_recovery_code', 'regenerate_recovery_code', regenerate_recovery_code, methods=['POST'])
    flask_app.add_url_rule('/api/enter_room', 'enter_room', enter_room, methods=['POST'])
    flask_app.add_url_rule('/api/leave_room_context', 'leave_room_context', leave_room_context, methods=['POST'])
    flask_app.add_url_rule('/api/get_session_user', 'get_session_user', get_session_user, methods=['GET'])
    flask_app.add_url_rule('/list_rooms', 'list_rooms', list_rooms, methods=['GET'])
    flask_app.add_url_rule('/load_room', 'load_room', load_room, methods=['GET'])
    flask_app.add_url_rule('/create_room', 'create_room', create_room, methods=['POST'])
    flask_app.add_url_rule('/delete_room', 'delete_room', delete_room, methods=['POST'])
    flask_app.add_url_rule('/save_room', 'save_room_route', save_room_route, methods=['POST'])
    flask_app.add_url_rule('/api/get_room_users', 'get_room_users', get_room_users, methods=['GET'])
    flask_app.add_url_rule('/api/admin/user_details', 'admin_get_user_details', admin_get_user_details, methods=['GET'])
    flask_app.add_url_rule('/api/admin/users', 'admin_get_users', admin_get_users, methods=['GET'])
    flask_app.add_url_rule('/api/admin/delete_user', 'admin_delete_user', admin_delete_user, methods=['POST'])
    flask_app.add_url_rule('/api/admin/transfer', 'admin_transfer_user', admin_transfer_user, methods=['POST'])
    flask_app.add_url_rule('/api/admin/set_user_management_admin', 'admin_set_user_management_admin', admin_set_user_management_admin, methods=['POST'])
    flask_app.add_url_rule('/api/json_nl_builder_audit', 'json_nl_builder_audit', json_nl_builder_audit, methods=['POST'])

# ログイン失敗時のタイミング差を縮めるためのダミーハッシュ（存在判別を防ぐ）。
_DUMMY_PASSWORD_HASH = account_auth.hash_password("timing-dummy-password")


def _set_authenticated_session(user, *, attribute=PLAYER_ATTRIBUTE, clear=True):
    """ログイン成立時のセッションを統一して張る。

    session.clear() で古いルーム権限を持ち越さず、auth_version を必ず載せる
    （session_required の auth_version 検証と整合させる）。
    """
    if clear:
        session.clear()
    session['user_id'] = user.id
    session['username'] = user.name
    session['auth_version'] = user.auth_version or 1
    session['attribute'] = attribute


def _name_only_login_disabled():
    """名前だけログイン(/api/entry)を無効化するか（cutover用フラグ、既定off）。"""
    return str(os.environ.get('ACCOUNT_DISABLE_NAME_ONLY_LOGIN') or '').strip() == '1'


# パスワード設定専用grant（ワンタイムコード認証後の短命許可）。
# 通常sessionとは別物で、ルーム・管理APIには入れない（session_required を通らない）。
PW_RESET_GRANT_TTL_SECONDS = 600  # コード確認後、パスワード設定までの猶予


def _set_pw_reset_grant(user_id):
    session.clear()
    session['pw_reset_user_id'] = user_id
    session['pw_reset_expires'] = _time.time() + PW_RESET_GRANT_TTL_SECONDS


def _valid_pw_reset_grant():
    uid = session.get('pw_reset_user_id')
    exp = session.get('pw_reset_expires')
    if not uid or not exp:
        return None
    if _time.time() > exp:
        return None
    return uid


def entry():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username') or '').strip()

    if _name_only_login_disabled():
        return jsonify({"error": "ログインIDとパスワードでログインしてください"}), 403

    if not username:
        return jsonify({"error": "ユーザー名は必須です"}), 400

    session['username'] = username
    # Client-supplied GM attributes are not trusted.  GM is granted only by
    # room PIN verification in /api/enter_room or /create_room.
    if session.get('attribute') != GM_ATTRIBUTE:
        session['attribute'] = PLAYER_ATTRIBUTE

    # ▼▼▼ 修正: ID発行とDB保存 ▼▼▼
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

    # ユーザー情報をDBに記録。新規/未発行ユーザーには復旧コードを一度だけ返す。
    user_result = upsert_user(session['user_id'], username, issue_recovery=True) or {}
    # ▲▲▲ 修正ここまで ▲▲▲

    # auth_version をセッションへ載せる（session_required の検証と整合）。
    user_obj = user_result.get("user")
    session['auth_version'] = (getattr(user_obj, 'auth_version', None) or 1)

    return jsonify({
        "message": "セッション開始",
        "username": username,
        "attribute": session.get('attribute', PLAYER_ATTRIBUTE),
        "user_id": session['user_id'],
        "is_app_admin": is_user_management_admin(session['user_id']),
        "recovery_code": user_result.get("recovery_code"),
        "recovery_token": user_result.get("recovery_token"),
    })

def recover_user():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username') or '').strip()
    recovery_code = str(data.get('recovery_code') or '').strip()
    result = recover_user_by_name_and_code(username, recovery_code)
    if not result:
        return jsonify({"error": "名前または復旧コードが正しくありません"}), 403

    user = result["user"]
    _set_authenticated_session(user)

    return jsonify({
        "message": "ユーザーを復旧しました",
        "username": user.name,
        "attribute": PLAYER_ATTRIBUTE,
        "user_id": user.id,
        "is_app_admin": is_user_management_admin(user.id),
        "recovery_token": result.get("recovery_token"),
    })

def recover_from_local_token():
    data = request.get_json(silent=True) or {}
    user = recover_user_by_local_token(
        str(data.get('user_id') or '').strip(),
        str(data.get('recovery_token') or '').strip(),
    )
    if not user:
        return jsonify({"error": "保存済み復旧トークンが無効です"}), 403

    _set_authenticated_session(user)

    return jsonify({
        "message": "保存済み復旧トークンで復帰しました",
        "username": user.name,
        "attribute": PLAYER_ATTRIBUTE,
        "user_id": user.id,
        "is_app_admin": is_user_management_admin(user.id),
    })

def _account_profile(user):
    return {
        "username": user.name,
        "user_id": user.id,
        "attribute": PLAYER_ATTRIBUTE,
        "is_app_admin": is_user_management_admin(user.id),
    }


def register_account():
    """新規アカウント登録（login_name + password）。"""
    data = request.get_json(silent=True) or {}
    login_name = str(data.get('login_name') or '').strip()
    password = data.get('password')
    display_name = str(data.get('display_name') or '').strip() or login_name

    normalized = account_auth.normalize_login_name(login_name)
    if not normalized:
        return jsonify({"error": "ログインIDを入力してください"}), 400
    if account_auth.is_login_name_taken(normalized):
        return jsonify({"error": "このログインIDは既に使われています"}), 409
    try:
        account_auth.validate_password(password)
    except account_auth.PasswordPolicyError as e:
        return jsonify({"error": str(e)}), 400

    user = User(id=str(uuid.uuid4()), name=display_name)
    db.session.add(user)
    db.session.flush()
    account_auth.set_login_name(user, login_name, commit=False)
    account_auth.set_password(user, password, commit=False)
    user.last_login = datetime.utcnow()
    db.session.commit()

    _set_authenticated_session(user)
    return jsonify({"message": "アカウントを作成しました", **_account_profile(user)}), 201


def login_account():
    """login_name + password でログインする。"""
    data = request.get_json(silent=True) or {}
    login_name = str(data.get('login_name') or '').strip()
    password = data.get('password')
    normalized = account_auth.normalize_login_name(login_name)
    limiter_key = normalized or 'unknown'

    if not password_login_limiter.is_allowed(limiter_key):
        return jsonify({"error": "試行回数が多すぎます。しばらくしてからお試しください"}), 429

    generic = "ログインIDまたはパスワードが正しくありません"
    user = account_auth.find_user_by_login_name(login_name) if normalized else None

    # 存在判別の時間差を縮める: 未登録/未設定でもダミー照合を行う。
    if user is None or not getattr(user, 'password_hash', None):
        account_auth.verify_password(_DUMMY_PASSWORD_HASH, password or '')
        password_login_limiter.record_failure(limiter_key)
        return jsonify({"error": generic}), 401

    if not account_auth.verify_user_password(user, password):
        password_login_limiter.record_failure(limiter_key)
        return jsonify({"error": generic}), 401

    password_login_limiter.reset(limiter_key)
    user.last_login = datetime.utcnow()
    db.session.commit()
    _set_authenticated_session(user)
    return jsonify({"message": "ログインしました", **_account_profile(user)})


def set_account_password():
    """パスワード設定。次の2経路を受け付ける。

    1) 通常の認証済みセッション（既存ユーザーの初回移行: recover 後に設定）。
    2) パスワード設定専用grant（管理者ワンタイムコード認証後）。grant 経路では
       設定完了時に auth_version 増加＋全端末トークン失効を行い、通常sessionへ昇格する。
    """
    data = request.get_json(silent=True) or {}
    login_name = str(data.get('login_name') or '').strip()
    password = data.get('password')

    reset_user_id = _valid_pw_reset_grant()
    if reset_user_id:
        user = User.query.get(reset_user_id)
        is_reset = True
    else:
        uid = session.get('user_id')
        if 'username' not in session or not uid:
            return jsonify({"error": "認証が必要です"}), 401
        user = User.query.get(uid)
        if user is None or session.get('auth_version') != user.auth_version:
            session.clear()
            return jsonify({"error": "認証が必要です"}), 401
        is_reset = False

    if user is None:
        session.clear()
        return jsonify({"error": "認証が必要です"}), 401

    try:
        account_auth.validate_password(password)
    except account_auth.PasswordPolicyError as e:
        return jsonify({"error": str(e)}), 400

    if login_name:
        try:
            account_auth.set_login_name(user, login_name, commit=False)
        except account_auth.LoginNameError as e:
            return jsonify({"error": str(e)}), 409
    elif not user.login_name_normalized:
        return jsonify({"error": "ログインIDを設定してください"}), 400

    account_auth.set_password(user, password, bump_auth_version=is_reset, commit=False)
    if is_reset:
        # 再設定: 全端末トークン失効＋全セッション失効。このセッションは昇格する。
        device_token.revoke_all_device_tokens(user.id, commit=False)
        db.session.commit()
        _set_authenticated_session(user)
    else:
        db.session.commit()
        session['auth_version'] = user.auth_version
    return jsonify({"message": "パスワードを設定しました", **_account_profile(user)})


@session_required
def change_display_name():
    """表示名(User.name)を変更する。ログイン/認可とは独立。"""
    data = request.get_json(silent=True) or {}
    new_name = str(data.get('display_name') or '').strip()
    if not new_name:
        return jsonify({"error": "表示名を入力してください"}), 400
    user = User.query.get(session.get('user_id'))
    if user is None:
        return jsonify({"error": "認証が必要です"}), 401
    user.name = new_name
    db.session.commit()
    session['username'] = new_name
    return jsonify({"message": "表示名を変更しました", "username": new_name, "user_id": user.id})


def logout_account():
    """ログアウト。mode: session(通常) | device(完全) | all(全端末)。

    - session: Flask session を破棄するだけ。端末トークンは保持する
      （自動復旧の停止はクライアント側の明示操作まで＝Phase 7）。
    - device: session 破棄 + 現端末トークンを失効。payload に selector があれば
      該当 TrustedDeviceToken を失効。併せて旧 recovery_token_hash も無効化し、
      レガシー自動復旧を止める。
    - all: session 破棄 + auth_version 増加（全セッション失効）+ 全端末トークン
      失効（TrustedDeviceToken 全件 + recovery_token_hash クリア）。
    """
    data = request.get_json(silent=True) or {}
    mode = str(data.get('mode') or 'session').strip().lower()
    if mode not in ('session', 'device', 'all'):
        return jsonify({"error": "不正なログアウト種別です"}), 400

    user_id = session.get('user_id')
    selector = str(data.get('selector') or '').strip()

    if mode == 'session':
        session.clear()
        return jsonify({"message": "ログアウトしました", "mode": mode})

    user = User.query.get(user_id) if user_id else None

    if mode == 'device':
        if selector:
            device_token.revoke_device_token(selector)
        if user is not None and getattr(user, 'recovery_token_hash', None):
            user.recovery_token_hash = None
            db.session.commit()
        session.clear()
        return jsonify({"message": "この端末からログアウトしました", "mode": mode})

    # mode == 'all'
    if user is not None:
        device_token.revoke_all_device_tokens(user.id)
        user.recovery_token_hash = None
        account_auth.bump_auth_version(user)  # commit を含む
    session.clear()
    return jsonify({"message": "全端末からログアウトしました", "mode": mode})


@session_required
def admin_issue_login_code():
    """app admin が対象ユーザーへワンタイム・パスワード再設定コードを発行する。"""
    denied = _require_app_admin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    target_user_id = str(data.get('user_id') or '').strip()
    if not target_user_id:
        return jsonify({"error": "User ID required"}), 400
    target = User.query.get(target_user_id)
    if target is None:
        return jsonify({"error": "User not found"}), 404

    code = one_time_code.issue_login_code(target_user_id, session.get('user_id'))
    # 監査: 発行者・対象・時刻を記録する（コード値は記録しない）。
    logging.info(f"[AUDIT] one-time login code issued by={session.get('user_id')} target={target_user_id}")
    return jsonify({
        "message": "ワンタイムコードを発行しました",
        "code": code,  # 発行直後の一度だけ表示する
        "user_id": target_user_id,
        "username": target.name,
        "expires_in_minutes": one_time_code.DEFAULT_TTL_MINUTES,
    })


def redeem_login_code():
    """ワンタイムコードを使用し、パスワード設定専用grantを発行する。"""
    data = request.get_json(silent=True) or {}
    login_name = str(data.get('login_name') or '').strip()
    code = str(data.get('code') or '').strip()
    limiter_key = account_auth.normalize_login_name(login_name) or 'unknown'

    if not one_time_code_limiter.is_allowed(limiter_key):
        return jsonify({"error": "試行回数が多すぎます。しばらくしてからお試しください"}), 429

    generic = "ログインIDまたはコードが正しくありません"
    user = account_auth.find_user_by_login_name(login_name) if login_name else None
    if user is None:
        one_time_code_limiter.record_failure(limiter_key)
        return jsonify({"error": generic}), 401

    consumed = one_time_code.verify_and_consume(user.id, code)
    if consumed is None:
        one_time_code_limiter.record_failure(limiter_key)
        return jsonify({"error": generic}), 401

    one_time_code_limiter.reset(limiter_key)
    _set_pw_reset_grant(user.id)
    logging.info(f"[AUDIT] one-time login code redeemed target={user.id}")
    return jsonify({
        "message": "コードを確認しました。新しいパスワードを設定してください",
        "require_password_set": True,
    })


@session_required
def regenerate_recovery_code():
    result = regenerate_user_recovery_code(session.get('user_id'))
    if not result:
        return jsonify({"error": "ユーザーが見つかりません"}), 404
    user = result["user"]
    return jsonify({
        "message": "復旧コードを再発行しました",
        "username": user.name,
        "user_id": user.id,
        "recovery_code": result.get("recovery_code"),
        "recovery_token": result.get("recovery_token"),
    })

@session_required
def enter_room():
    data = request.get_json(silent=True) or {}
    room_name = str(data.get('room_name') or '').strip()
    role = data.get('role') or data.get('attribute') or PLAYER_ATTRIBUTE
    gm_key = data.get('gm_pin') or data.get('gm_key') or ''

    if not room_name:
        return jsonify({"error": "Room name required"}), 400
    if not Room.query.filter_by(name=room_name).first():
        return jsonify({"error": "Room not found"}), 404

    if str(role or '').strip().lower() in {"gm", "game_master", "gamemaster"} and is_user_management_admin(session.get('user_id')):
        attribute = GM_ATTRIBUTE
    else:
        attribute = resolve_room_attribute(room_name, role, gm_key)
    if attribute is None:
        return jsonify({"error": "GM PINが正しくありません"}), 403

    session['attribute'] = attribute
    # 入室成功を session に記録する。/load_room はこの記録（または owner/参加者）
    # でアクセス可否を判定し、任意ルーム名の直接読み出しを防ぐ。
    entered = set(session.get('entered_rooms') or [])
    entered.add(room_name)
    session['entered_rooms'] = list(entered)
    return jsonify({
        "message": "Room entry accepted",
        "room_name": room_name,
        "attribute": attribute,
    })

@session_required
def leave_room_context():
    # Room GM status is scoped to the room. Returning to the lobby must not
    # leave the user with GM-like powers in app-wide management surfaces.
    session['attribute'] = PLAYER_ATTRIBUTE
    return jsonify({"message": "Room context cleared", "attribute": PLAYER_ATTRIBUTE})

def _require_app_admin():
    """app admin でなければ 403 を返す。app adminでなければ None 以外を返す。"""
    if not is_user_management_admin(session.get('user_id')):
        return jsonify({"error": "アプリ管理者権限が必要です"}), 403
    return None

@session_required
def admin_get_user_details():
    denied = _require_app_admin()
    if denied:
        return denied
    target_user_id = request.args.get('user_id')
    if not target_user_id:
        return jsonify({"error": "User ID required"}), 400

    data = get_user_owned_items(target_user_id)
    return jsonify(data)

def _can_manage_users_with_payload(payload=None):
    payload = payload or {}
    if is_user_management_admin(session.get('user_id')):
        return True
    master_key = payload.get('master_key') or payload.get('gm_master_key') or ''
    return verify_master_key(master_key)

def get_session_user():
    username = session.get('username')
    user_id = session.get('user_id')
    if not username or not user_id:
        return jsonify({"username": None, "attribute": None, "user_id": None}), 401

    # 削除済みユーザーのセッションでここに来た場合、upsert_user に渡すと
    # ユーザーを復活させてしまう。先に実在を確認し、無ければ失効させる。
    _user = User.query.get(user_id)
    if _user is None:
        session.clear()
        return jsonify({"username": None, "attribute": None, "user_id": None}), 401
    # auth_version 不一致のセッションは失効させる（Q26-015）。
    if session.get('auth_version') != _user.auth_version:
        session.clear()
        return jsonify({"username": None, "attribute": None, "user_id": None}), 401

    attribute = session.get('attribute')
    # トークン未発行の既存ユーザーには一度だけ発行する（再発行はしない）。
    user_result = upsert_user(user_id, username, issue_recovery=True) or {}
    logging.info(f"[SESSION CHECK] User: {username}, Attribute: {attribute}, UserID: {user_id}")
    return jsonify({
        "username": username,
        "attribute": attribute,
        "user_id": user_id,
        "is_app_admin": is_user_management_admin(user_id),
        "recovery_code": user_result.get("recovery_code"),
        "recovery_token": user_result.get("recovery_token"),
    })

@session_required
def list_rooms():
    """ルーム一覧とオーナー情報を返す"""
    rooms = read_saved_rooms_with_owners()
    user_id = session.get('user_id')
    attribute = session.get('attribute')
    return jsonify({
        'rooms': rooms,
        'current_user_id': user_id,
        'is_gm': attribute == 'GM',
        'is_app_admin': is_user_management_admin(user_id),
    })

@session_required
def load_room():
    room_name = request.args.get('name')
    if not room_name:
        return jsonify({"error": "Room name required"}), 400
    # 参加者向けルーム状態は、入室済み（enter_room）か owner/参加者のみ返す。
    # mobile は開発停止につき考慮不要（/mobile は停止済み）。
    from manager.room_access import user_can_access_room
    entered = session.get('entered_rooms') or []
    if room_name not in entered and not user_can_access_room(session.get('user_id'), room_name):
        return jsonify({"error": "このルームにアクセスする権限がありません"}), 403
    state = get_room_state(room_name)
    return jsonify(state)

@session_required
def create_room():
    data = request.get_json(silent=True) or {}
    room_name = str(data.get('room_name') or '').strip()
    gm_pin = str(data.get('gm_pin') or '').strip()
    if not room_name:
        return jsonify({"error": "No name"}), 400
    if not is_valid_gm_pin(gm_pin):
        return jsonify({"error": "GM PINは4桁の数字で入力してください"}), 400

    # DBに存在するかチェック
    if Room.query.filter_by(name=room_name).first():
        return jsonify({"error": "Room exists"}), 409

    play_mode = str(data.get('play_mode') or 'normal').strip().lower()
    if play_mode not in ('normal', 'battle_only'):
        play_mode = 'normal'

    new_state = {
        "characters": [],
        "timeline": [],
        "round": 0,
        "logs": [],
        "play_mode": play_mode,
    }
    if play_mode == 'battle_only':
        new_state["battle_only"] = {"status": "lobby", "ally_entries": [], "enemy_entries": []}
    active_room_states[room_name] = new_state

    # ▼▼▼ 修正: Room作成時に owner_id を保存 ▼▼▼
    # save_room_to_db はデータ保存用なので、ここでは Roomモデルを直接作って owner_id を入れる
    new_room = Room(
        name=room_name,
        data=new_state,
        owner_id=session.get('user_id'),
        gm_pin_hash=hash_gm_pin(gm_pin),
    )
    db.session.add(new_room)
    db.session.commit()
    session['attribute'] = GM_ATTRIBUTE
    # ▲▲▲ 修正ここまで ▲▲▲

    normalized_state = get_room_state(room_name)
    return jsonify({"message": "Created", "state": normalized_state, "attribute": GM_ATTRIBUTE}), 201

@session_required
def admin_get_users():
    denied = _require_app_admin()
    if denied:
        return denied
    return jsonify({
        "users": get_all_users(),
        "can_manage_users": True,
    })

@session_required
def admin_delete_user():
    data = request.get_json(silent=True) or {}
    if not _can_manage_users_with_payload(data):
        return jsonify({"error": "ユーザー管理権限またはマスターキーが必要です"}), 403
    user_id = data.get('user_id')
    if delete_user(user_id):
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Failed"}), 500

@session_required
def admin_transfer_user():
    data = request.get_json(silent=True) or {}
    if not _can_manage_users_with_payload(data):
        return jsonify({"error": "ユーザー管理権限またはマスターキーが必要です"}), 403
    count = transfer_ownership(data['old_id'], data['new_id'])
    return jsonify({"message": f"Transferred {count} characters/rooms."})

@session_required
def admin_set_user_management_admin():
    data = request.get_json(silent=True) or {}
    if not verify_master_key(data.get('master_key') or ''):
        return jsonify({"error": "マスターキーが正しくありません"}), 403
    target_user_id = data.get('user_id')
    enabled = bool(data.get('enabled'))
    if not target_user_id:
        return jsonify({"error": "User ID required"}), 400
    if not set_user_management_admin(target_user_id, enabled):
        return jsonify({"error": "User not found"}), 404
    return jsonify({"message": "Updated", "user_id": target_user_id, "is_app_admin": enabled})

@session_required
def delete_room():
    """ルーム削除 - オーナーまたはGMのみ許可"""
    data = request.get_json(silent=True) or {}
    room_name = data.get('room_name')
    gm_key = data.get('gm_pin') or data.get('gm_key') or ''

    # ルームのオーナーを取得
    room = Room.query.filter_by(name=room_name).first()
    if not room:
        return jsonify({"error": "Room not found"}), 404

    # ルーム削除はロビー操作のため、セッション属性ではなくGM PIN/マスターキーで確認する。
    if not verify_room_gm_key(room, gm_key):
        return jsonify({"error": "GM PINまたはマスターキーが正しくありません"}), 403

    # DB削除の前に保留中の自動保存を破棄しメモリからも除去する。
    # 削除後にデバウンスのフラッシュが走ってルームを復活させる事故を防ぐ。
    from manager.room_manager import discard_pending_save
    discard_pending_save(room_name)
    active_room_states.pop(room_name, None)

    if delete_room_from_db(room_name):
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Delete failed"}), 500

@session_required
def save_room_route():
    data = request.get_json(silent=True) or {}
    room_name = data.get('room_name')
    state = data.get('state')
    if not room_name:
        return jsonify({"error": "Room name required"}), 400
    # ルーム全状態の上書きは、当該ルームの owner か在室参加者に限定する。
    # （無認可の任意ルーム上書きを塞ぐ。判定は共通の room_access へ集約）
    from manager.room_access import user_can_access_room
    if not user_can_access_room(session.get('user_id'), room_name):
        return jsonify({"error": "このルームを更新する権限がありません"}), 403
    active_room_states[room_name] = state
    save_room_to_db(room_name, state)
    return jsonify({"message": "Saved"})

def get_skill():
    skill_id = request.args.get('id')
    return jsonify(all_skill_data.get(skill_id, {}))

def get_skill_metadata():
    metadata = {}
    for sid, data in all_skill_data.items():
        metadata[sid] = {
            "tags": data.get("tags", []),
            "category": data.get("分類", ""),
            "distance": data.get("距離", "")
        }
    return jsonify(metadata)

def get_skill_data():
    """フロントエンドにスキルマスターデータを提供するAPI"""
    return jsonify(all_skill_data)

def get_item_data():
    """フロントエンドにアイテムマスターデータを提供するAPI"""
    from manager.items.loader import item_loader
    items = item_loader.load_items()
    return jsonify(items)

# ★ バフプラグインシステム
from plugins.buffs.registry import buff_registry

def get_radiance_data():
    """フロントエンドに輝化スキルマスターデータを提供するAPI"""
    from manager.radiance.loader import radiance_loader
    radiance_skills = radiance_loader.load_skills()
    return jsonify(radiance_skills)

def get_passive_data():
    """フロントエンドに特殊パッシブマスターデータを提供するAPI"""
    from manager.passives.loader import passive_loader
    passives = passive_loader.load_passives()
    return jsonify(passives)

def get_buff_data():
    """フロントエンドにバフ図鑑データを提供するAPI"""
    from manager.buffs.loader import buff_catalog_loader
    buffs = buff_catalog_loader.load_buffs()
    return jsonify(buffs)

def get_glossary_data():
    """フロントエンドに用語辞書データを提供するAPI"""
    if not all_glossary_data:
        from manager.glossary.loader import glossary_catalog_loader
        glossary_catalog_loader.load_terms()
    return jsonify(all_glossary_data)

def json_nl_builder_audit():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid payload"}), 400
    raw = payload.get("payload", {})
    try:
        raw_len = len(str(raw))
    except Exception:
        raw_len = 0
    if raw_len > 30000:
        return jsonify({"error": "payload too large"}), 400

    append_audit(
        "json_nl_builder",
        outcome=str(payload.get("outcome", "") or "unknown"),
        user_id=session.get("user_id"),
        username=session.get("username"),
        attribute=session.get("attribute"),
        payload=raw,
    )
    return jsonify({"ok": True})


@session_required
def upload_image():
    """
    Cloudinaryへ画像をアップロードするエンドポイント
    キャラクター立ち絵などの画像をクラウドストレージに保存
    """
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルがありません'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400

    # オプション: 画像名とタイプを取得
    image_name = request.form.get('name', file.filename)
    from manager.image_upload_validation import validate_image_upload
    validation = validate_image_upload(file)
    if not validation.ok:
        return jsonify({'error': validation.error}), 400
    file.stream.seek(0)

    upload_type = request.form.get('type', 'character') # 'character' or 'background'

    cloudinary_folder = "gemtrpg/characters"
    if upload_type == 'background':
        cloudinary_folder = "gemtrpg/backgrounds"

    try:
        # Cloudinaryへアップロード
        # ユーザー要望により圧縮制限を緩和 (10MB制限内なら画質維持)
        # width制限を撤廃し、画質のみauto設定
        result = cloudinary.uploader.upload(
            file,
            folder=cloudinary_folder,
            transformation=[
                {'quality': "auto", 'fetch_format': "auto"}  # 自動最適化のみ
            ]
        )

        # アップロード成功: セキュアURL（https）を返す
        secure_url = result['secure_url']
        public_id = result['public_id']

        logging.info(f"[Cloudinary] Image uploaded: {secure_url} (Type: {upload_type})")

        # ★ 画像レジストリに登録
        from manager.image_manager import register_image
        user_id = session.get('username', 'unknown')

        # db_type: DB上の分類。frontendのエロフィルタなどと競合しないか確認が必要だが
        # ここでは 'user' (キャラ) or 'background' としてみる
        # 既存の 'user' はキャラ扱い。
        db_image_type = 'user'
        if upload_type == 'background':
            db_image_type = 'background'

        requested_visibility = str(request.form.get('visibility') or 'public').strip().lower()
        image_visibility = 'gm' if requested_visibility == 'gm' and session.get('attribute') == 'GM' else 'public'

        registered_image = register_image(
            url=secure_url,
            public_id=public_id,
            name=image_name,
            uploader=user_id,
            image_type=db_image_type,
            visibility=image_visibility
        )

        logging.info(f"[ImageRegistry] Registered image: {registered_image['id']}")

        return jsonify({
            'url': secure_url,
            'id': registered_image['id'],
            'name': registered_image['name']
        })

    except Exception as e:
        # エラーログ出力
        logging.error(f"[Cloudinary] Upload Error: {e}")
        return jsonify({'error': 'アップロードに失敗しました'}), 500


@session_required
def get_images_api():
    """
    画像一覧を取得するAPI
    クエリパラメータ:
        q: 検索クエリ（画像名で検索）
        type: 'user' または 'default'
    """
    from manager.image_manager import get_images

    user_id = session.get('username')
    is_gm = (session.get('attribute') == 'GM')
    query = request.args.get('q')
    image_type = request.args.get('type')

    images = get_images(user_id=user_id, query=query, image_type=image_type, is_gm=is_gm)
    return jsonify(images)


@session_required
def delete_image_api(image_id):
    """
    画像を削除するAPI（Cloudinary + レジストリ）
    """
    from manager.image_manager import delete_image, get_image_by_id

    user_id = session.get('username')
    is_gm = (session.get('attribute') == 'GM')

    # 画像情報を取得
    image_obj = get_image_by_id(image_id)
    if not image_obj:
        return jsonify({'error': '画像が見つかりません'}), 404

    # 権限チェックとレジストリから削除
    if not delete_image(image_id, user_id, is_gm):
        return jsonify({'error': '削除権限がありません'}), 403

    # Cloudinaryから削除
    try:
        import cloudinary.uploader
        cloudinary.uploader.destroy(image_obj['public_id'])
        logging.info(f"[Cloudinary] Deleted image: {image_obj['public_id']}")
    except Exception as e:
        logging.warning(f"[Cloudinary] Failed to delete from cloud: {e}")
        # クラウド削除失敗してもレジストリは削除済みなので続行

    return jsonify({'success': True})


@session_required
def get_room_users():
    """指定されたルームに参加しているユーザーの一覧を取得"""
    from extensions import user_sids
    room_name = request.args.get('room')
    if not room_name:
        return jsonify({"error": "Room name required"}), 400

    # user_sidsから該当ルームのユーザーを抽出
    room_users = []
    for sid, user_info in user_sids.items():
        if user_info.get('room') == room_name:
            room_users.append({
                'username': user_info.get('username'),
                'user_id': user_info.get('user_id'),
                'attribute': user_info.get('attribute')
            })

    return jsonify(room_users)


def get_local_images():
    """
    ローカル（static/images/characters|backgrounds）にある画像一覧を取得するAPI
    Cloudinaryを使わずにデフォルト素材を提供するため
    """
    try:
        # 画像タイプを取得 ('character' or 'background')
        image_type = request.args.get('type', 'character')
        subdir = 'backgrounds' if image_type == 'background' else 'characters'

        # 画像ディレクトリのパス
        # static_folderがNoneの場合もあるので、current_app.root_path基点で作成
        img_dir = os.path.join(current_app.root_path, 'static', 'images', subdir)

        if not os.path.exists(img_dir):
            return jsonify([])

        # 対応する拡張子
        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')

        images = []
        for filename in os.listdir(img_dir):
            if filename.lower().endswith(valid_extensions):
                # URLは images/subdir/ファイル名
                images.append({
                    'id': f'local_{subdir}_{filename}',
                    'name': filename,
                    'url': f'images/{subdir}/{filename}',
                    'type': 'default'
                })

        return jsonify(images)

    except Exception as e:
        logging.error(f"[LocalImages] Error: {e}")
        return jsonify([])


app = create_app(run_startup=_should_run_startup_on_import()) if _should_create_default_app() else None




# ==========================================
#  Main Execution
# ==========================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--update', action='store_true', help='スキル・アイテム・輝化スキル・特殊パッシブ・バフ図鑑・用語辞書の全データを更新')
    args = parser.parse_args()

    if args.update:
        # 全データ更新モード
        print("\n" + "="*60)
        print("【データ更新モード】")
        print("="*60)
        from manager.data_manager import update_all_data
        with app.app_context():
            if update_all_data():
                print("✅ 全データの更新が完了しました。")
                sys.exit(0)
            else:
                print("❌ 一部のデータ更新に失敗しました。")
                sys.exit(1)

    # ★ バフプラグイン自動検出
    print("--- Initializing Buff Plugins ---")
    from plugins.buffs.registry import buff_registry
    buff_registry.auto_discover()
    print()

    print("Starting Flask-SocketIO server...")
    socketio.run(app, host='127.0.0.1', port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
