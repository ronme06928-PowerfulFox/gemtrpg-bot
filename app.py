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

from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS
from flask_compress import Compress # 追加: 圧縮転送用ライブラリ
from whitenoise import WhiteNoise # 追加: 静的ファイル配信高速化

# ★ 拡張機能（共有インスタンス）のインポート
from extensions import db, socketio, active_room_states, all_skill_data, all_glossary_data
from models import Room

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

# ★ イベントハンドラ（SocketIO層）のインポート
# これをインポートすることで、@socketio.on デコレータが登録されます
import events.socket_main
import events.socket_char
import events.socket_battle_only
import events.socket_room_presets
import events.battle # Refactored battle events
import events.socket_wide_calculate

import events.socket_items  # ★Phase 4: アイテムシステム
import events.socket_exploration # ★Phase XX: 探索モード

import uuid
import cloudinary
import cloudinary.uploader

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

app = Flask(__name__, static_folder=None)
app.config['JSON_AS_ASCII'] = False

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


app.config['SECRET_KEY'] = _get_secret_key()
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///gemtrpg.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
cors_origins = _get_cors_origins()

# ★ WhiteNoise設定: Staticファイル配信の高速化
# Flaskを通さずに直接配信することでCPU負荷を低減
app.wsgi_app = WhiteNoise(app.wsgi_app, root=os.path.join(app.root_path, 'static'), prefix='static/')

# データベース接続プールの設定（PostgreSQL SSL接続切断対策）
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # 接続前に健全性チェック
    'pool_recycle': 300,    # 5分ごとに接続を再利用
    'pool_size': 10,        # 接続プールサイズ
    'max_overflow': 20      # プールがフルの時の追加接続数
}

# 静的ファイルのパス
STATIC_DIR = os.path.join(app.root_path, 'static')

# === Cloudinary設定 ===
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)

# === 初期化 ===
CORS(app, supports_credentials=True, origins=cors_origins)
Compress(app) # 追加: 圧縮転送の有効化 (デフォルトでGzip圧縮)
db.init_app(app)

# ★ DB初期化とマイグレーション
# ★ DBスキーマ自動修正 (Renderデプロイ対策 - Global execution for Gunicorn)
# アプリケーション初期化時に実行
print("--- Checking Database Schema (Global) ---")
from manager.db_migration import run_auto_migration
run_auto_migration(app)
print()

# ★ 起動時のデータ読み込み
with app.app_context():
    db.create_all()  # テーブル作成 (既存の場合はスキップ)

    # バフプラグインの自動検出（ここでも呼んでおく）
    from plugins.buffs.registry import buff_registry
    buff_registry.auto_discover()

    init_app_data()
    read_saved_rooms_with_owners()

async_mode = 'eventlet' if IS_RENDER else 'threading'
# extensionsにあるsocketioをアプリと紐付け
socketio.init_app(app, cors_allowed_origins=cors_origins, async_mode=async_mode)

# ==========================================
#  HTTP Routes
# ==========================================

@app.route('/')
def serve_index():
    print(f"[INFO] Accessing Root! Serving from: {STATIC_DIR}")
    return send_from_directory(STATIC_DIR, 'index.html')

@app.after_request
def add_header(response):
    """
    静的ファイル(画像, CSS, JS)に強力なキャッシュヘッダーを付与する
    (WhiteNoiseが処理しきれない場合や、動的生成コンテンツへのキャッシュ適用のため)
    """
    if request.path.startswith('/static/') or request.path.startswith('/images/'):
        # Cache for 1 year
        response.headers['Cache-Control'] = 'public, max-age=31536000'
    return response

@app.route('/mobile')
def serve_mobile_index():
    print(f"[INFO] Accessing Mobile Root! Serving from: {STATIC_DIR}/mobile")
    return send_from_directory(os.path.join(STATIC_DIR, 'mobile'), 'index.html')

@app.route('/<path:filename>')
def serve_static_files(filename):
    return send_from_directory(STATIC_DIR, filename)

@app.route('/api/entry', methods=['POST'])
def entry():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username') or '').strip()

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

    return jsonify({
        "message": "セッション開始",
        "username": username,
        "attribute": session.get('attribute', PLAYER_ATTRIBUTE),
        "user_id": session['user_id'],
        "is_app_admin": is_user_management_admin(session['user_id']),
        "recovery_code": user_result.get("recovery_code"),
        "recovery_token": user_result.get("recovery_token"),
    })

@app.route('/api/recover_user', methods=['POST'])
def recover_user():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username') or '').strip()
    recovery_code = str(data.get('recovery_code') or '').strip()
    result = recover_user_by_name_and_code(username, recovery_code)
    if not result:
        return jsonify({"error": "名前または復旧コードが正しくありません"}), 403

    user = result["user"]
    session['user_id'] = user.id
    session['username'] = user.name
    session['attribute'] = PLAYER_ATTRIBUTE

    return jsonify({
        "message": "ユーザーを復旧しました",
        "username": user.name,
        "attribute": PLAYER_ATTRIBUTE,
        "user_id": user.id,
        "is_app_admin": is_user_management_admin(user.id),
        "recovery_token": result.get("recovery_token"),
    })

@app.route('/api/recover_from_local_token', methods=['POST'])
def recover_from_local_token():
    data = request.get_json(silent=True) or {}
    user = recover_user_by_local_token(
        str(data.get('user_id') or '').strip(),
        str(data.get('recovery_token') or '').strip(),
    )
    if not user:
        return jsonify({"error": "保存済み復旧トークンが無効です"}), 403

    session['user_id'] = user.id
    session['username'] = user.name
    session['attribute'] = PLAYER_ATTRIBUTE

    return jsonify({
        "message": "保存済み復旧トークンで復帰しました",
        "username": user.name,
        "attribute": PLAYER_ATTRIBUTE,
        "user_id": user.id,
        "is_app_admin": is_user_management_admin(user.id),
    })

@app.route('/api/regenerate_recovery_code', methods=['POST'])
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

@app.route('/api/enter_room', methods=['POST'])
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
    return jsonify({
        "message": "Room entry accepted",
        "room_name": room_name,
        "attribute": attribute,
    })

@app.route('/api/leave_room_context', methods=['POST'])
@session_required
def leave_room_context():
    # Room GM status is scoped to the room. Returning to the lobby must not
    # leave the user with GM-like powers in app-wide management surfaces.
    session['attribute'] = PLAYER_ATTRIBUTE
    return jsonify({"message": "Room context cleared", "attribute": PLAYER_ATTRIBUTE})

@app.route('/api/admin/user_details', methods=['GET'])
@session_required
def admin_get_user_details():
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

@app.route('/api/get_session_user', methods=['GET'])
def get_session_user():
    if 'username' in session:
        username = session.get('username')
        attribute = session.get('attribute')
        user_id = session.get('user_id')
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
    else:
        return jsonify({"username": None, "attribute": None, "user_id": None}), 401

@app.route('/list_rooms', methods=['GET'])
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

@app.route('/load_room', methods=['GET'])
@session_required
def load_room():
    room_name = request.args.get('name')
    state = get_room_state(room_name)
    return jsonify(state)

@app.route('/create_room', methods=['POST'])
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

@app.route('/api/admin/users', methods=['GET'])
@session_required
def admin_get_users():
    return jsonify({
        "users": get_all_users(),
        "can_manage_users": is_user_management_admin(session.get('user_id')),
    })

@app.route('/api/admin/delete_user', methods=['POST'])
@session_required
def admin_delete_user():
    data = request.get_json(silent=True) or {}
    if not _can_manage_users_with_payload(data):
        return jsonify({"error": "ユーザー管理権限またはマスターキーが必要です"}), 403
    user_id = data.get('user_id')
    if delete_user(user_id):
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Failed"}), 500

@app.route('/api/admin/transfer', methods=['POST'])
@session_required
def admin_transfer_user():
    data = request.get_json(silent=True) or {}
    if not _can_manage_users_with_payload(data):
        return jsonify({"error": "ユーザー管理権限またはマスターキーが必要です"}), 403
    count = transfer_ownership(data['old_id'], data['new_id'])
    return jsonify({"message": f"Transferred {count} characters/rooms."})

@app.route('/api/admin/set_user_management_admin', methods=['POST'])
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

@app.route('/delete_room', methods=['POST'])
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

    if delete_room_from_db(room_name):
        if room_name in active_room_states:
            del active_room_states[room_name]
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Delete failed"}), 500

@app.route('/save_room', methods=['POST'])
@session_required
def save_room_route():
    data = request.json
    room_name = data.get('room_name')
    state = data.get('state')
    active_room_states[room_name] = state
    save_room_to_db(room_name, state)
    return jsonify({"message": "Saved"})

@app.route('/get_skill')
def get_skill():
    skill_id = request.args.get('id')
    return jsonify(all_skill_data.get(skill_id, {}))

@app.route('/api/get_skill_metadata', methods=['GET'])
def get_skill_metadata():
    metadata = {}
    for sid, data in all_skill_data.items():
        metadata[sid] = {
            "tags": data.get("tags", []),
            "category": data.get("分類", ""),
            "distance": data.get("距離", "")
        }
    return jsonify(metadata)

@app.route('/api/get_skill_data', methods=['GET'])
def get_skill_data():
    """フロントエンドにスキルマスターデータを提供するAPI"""
    return jsonify(all_skill_data)

@app.route('/api/get_item_data', methods=['GET'])
def get_item_data():
    """フロントエンドにアイテムマスターデータを提供するAPI"""
    from manager.items.loader import item_loader
    items = item_loader.load_items()
    return jsonify(items)

# ★ バフプラグインシステム
from plugins.buffs.registry import buff_registry

@app.route('/api/get_radiance_data', methods=['GET'])
def get_radiance_data():
    """フロントエンドに輝化スキルマスターデータを提供するAPI"""
    from manager.radiance.loader import radiance_loader
    radiance_skills = radiance_loader.load_skills()
    return jsonify(radiance_skills)

@app.route('/api/get_passive_data', methods=['GET'])
def get_passive_data():
    """フロントエンドに特殊パッシブマスターデータを提供するAPI"""
    from manager.passives.loader import passive_loader
    passives = passive_loader.load_passives()
    return jsonify(passives)

@app.route('/api/get_buff_data', methods=['GET'])
def get_buff_data():
    """フロントエンドにバフ図鑑データを提供するAPI"""
    from manager.buffs.loader import buff_catalog_loader
    buffs = buff_catalog_loader.load_buffs()
    return jsonify(buffs)

@app.route('/api/get_glossary_data', methods=['GET'])
def get_glossary_data():
    """フロントエンドに用語辞書データを提供するAPI"""
    if not all_glossary_data:
        from manager.glossary.loader import glossary_catalog_loader
        glossary_catalog_loader.load_terms()
    return jsonify(all_glossary_data)

@app.route('/api/json_nl_builder_audit', methods=['POST'])
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


@app.route('/api/upload_image', methods=['POST'])
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

        registered_image = register_image(
            url=secure_url,
            public_id=public_id,
            name=image_name,
            uploader=user_id,
            image_type=db_image_type
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


@app.route('/api/images', methods=['GET'])
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
    query = request.args.get('q')
    image_type = request.args.get('type')

    images = get_images(user_id=user_id, query=query, image_type=image_type)
    return jsonify(images)


@app.route('/api/images/<image_id>', methods=['DELETE'])
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


@app.route('/api/get_room_users', methods=['GET'])
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


@app.route('/api/local_images', methods=['GET'])
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
        # static_folderがNoneの場合もあるので、app.root_path基点で作成
        img_dir = os.path.join(app.root_path, 'static', 'images', subdir)

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
    buff_registry.auto_discover()
    print()

    print("Starting Flask-SocketIO server...")
    socketio.run(app, host='127.0.0.1', port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
