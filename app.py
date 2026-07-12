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
from extensions import db, socketio, all_skill_data, all_glossary_data

# ★ マネージャー（ロジック層）からのインポート
from manager.data_manager import init_app_data, read_saved_rooms_with_owners
from manager.utils import session_required
from manager.json_rule_audit import append_audit

import cloudinary
import cloudinary.uploader

# === アプリ設定 ===
load_dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(load_dotenv_path):
    from dotenv import load_dotenv
    load_dotenv(load_dotenv_path)

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
# 計画36: キャラ作成ツール（単体HTML）。static/ 配下ではなくリポジトリ直下にあるため専用に配信する。
CHARA_CREATOR_DIR = os.path.join(os.path.dirname(__file__), 'CharaCreator')
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


def serve_chara_creator():
    """計画36: キャラ作成ツール（CharaCreator/GEMDICEBOT_CharaCreator.html）を配信する。

    最小統合方針のため既存HTMLはそのまま配信し、アカウント保存/持ちキャラ読込の
    追加分のみをファイル側に埋め込んでいる（ここではルーティングのみ担う）。
    """
    return send_from_directory(CHARA_CREATOR_DIR, 'GEMDICEBOT_CharaCreator.html')


def serve_static_files(filename):
    # モバイル版アセットの直接読み出しも停止する（/mobile 停止の裏口を塞ぐ）。
    normalized = str(filename or '').lstrip('/')
    if normalized == 'mobile' or normalized.startswith('mobile/'):
        return MOBILE_SUSPENDED_HTML, 404, {'Content-Type': 'text/html; charset=utf-8'}
    return send_from_directory(STATIC_DIR, filename)


def register_http_routes(flask_app):
    # account / room / admin 系のハンドラは routes/ パッケージの Blueprint に
    # 分割している（app.py は薄い入出力変換に留める方針）。
    from routes.account import account_bp
    from routes.room import room_bp
    from routes.admin import admin_bp
    from routes.owned_characters import owned_characters_bp

    flask_app.add_url_rule('/', 'serve_index', serve_index)
    flask_app.add_url_rule('/healthz', 'healthz', healthz)
    # perf計測: after_request は登録の逆順で実行されるため、_perf_after を先に
    # 登録して add_header の後（=最終レスポンス確定後）に計測させる。
    flask_app.before_request(_perf_before)
    flask_app.after_request(_perf_after)
    flask_app.after_request(add_header)
    flask_app.add_url_rule('/mobile', 'serve_mobile_index', serve_mobile_index)
    flask_app.add_url_rule('/chara_creator', 'serve_chara_creator', serve_chara_creator)
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
    flask_app.add_url_rule('/api/json_nl_builder_audit', 'json_nl_builder_audit', json_nl_builder_audit, methods=['POST'])

    flask_app.register_blueprint(account_bp)
    flask_app.register_blueprint(room_bp)
    flask_app.register_blueprint(admin_bp)
    flask_app.register_blueprint(owned_characters_bp)


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
