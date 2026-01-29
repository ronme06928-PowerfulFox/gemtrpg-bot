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
from extensions import db, socketio, active_room_states, all_skill_data
from models import Room

# ★ マネージャー（ロジック層）からのインポート
from manager.data_manager import (
    init_app_data, read_saved_rooms, read_saved_rooms_with_owners, save_room_to_db, delete_room_from_db
)
from manager.room_manager import get_room_state
from manager.utils import session_required

# ★ イベントハンドラ（SocketIO層）のインポート
# これをインポートすることで、@socketio.on デコレータが登録されます
import events.socket_main
import events.socket_char
import events.battle # Refactored battle events
import events.socket_wide_calculate

import events.socket_items  # ★Phase 4: アイテムシステム

import uuid
import cloudinary
import cloudinary.uploader

# ★追加インポート
from manager.user_manager import upsert_user, get_all_users, delete_user, transfer_ownership, get_user_owned_items

# === アプリ設定 ===
load_dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(load_dotenv_path):
    from dotenv import load_dotenv
    load_dotenv(load_dotenv_path)

app = Flask(__name__, static_folder=None)
app.config['JSON_AS_ASCII'] = False
app.config['SECRET_KEY'] = 'gem_trpg_secret_key' # SECRET_KEYを直接設定
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///gemtrpg.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
CORS(app, supports_credentials=True)
Compress(app) # 追加: 圧縮転送の有効化 (デフォルトでGzip圧縮)
db.init_app(app)

async_mode = 'eventlet' if IS_RENDER else 'threading'
# extensionsにあるsocketioをアプリと紐付け
socketio.init_app(app, cors_allowed_origins="*", async_mode=async_mode)

# データ初期化実行
with app.app_context():
    # テーブル作成（Render初回起動時などに必要）
    db.create_all()
    init_app_data()

# ==========================================
#  HTTP Routes
# ==========================================

@app.route('/')
def serve_index():
    print(f"[INFO] Accessing Root! Serving from: {STATIC_DIR}")
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/mobile')
def serve_mobile_index():
    print(f"[INFO] Accessing Mobile Root! Serving from: {STATIC_DIR}/mobile")
    return send_from_directory(os.path.join(STATIC_DIR, 'mobile'), 'index.html')

@app.route('/<path:filename>')
def serve_static_files(filename):
    return send_from_directory(STATIC_DIR, filename)

@app.route('/api/entry', methods=['POST'])
def entry():
    data = request.json
    username = data.get('username')
    attribute = data.get('attribute')

    if not username or not attribute:
        return jsonify({"error": "ユーザー名と属性は必須です"}), 400

    session['username'] = username
    session['attribute'] = attribute

    # ▼▼▼ 修正: ID発行とDB保存 ▼▼▼
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

    # ユーザー情報をDBに記録
    upsert_user(session['user_id'], username)
    # ▲▲▲ 修正ここまで ▲▲▲

    return jsonify({
        "message": "セッション開始",
        "username": username,
        "attribute": attribute,
        "user_id": session['user_id']
    })

@app.route('/api/admin/user_details', methods=['GET'])
@session_required
def admin_get_user_details():
    if session.get('attribute') != 'GM':
        return jsonify({"error": "Forbidden"}), 403

    target_user_id = request.args.get('user_id')
    if not target_user_id:
        return jsonify({"error": "User ID required"}), 400

    data = get_user_owned_items(target_user_id)
    return jsonify(data)

@app.route('/api/get_session_user', methods=['GET'])
def get_session_user():
    if 'username' in session:
        username = session.get('username')
        attribute = session.get('attribute')
        user_id = session.get('user_id')
        logging.info(f"[SESSION CHECK] User: {username}, Attribute: {attribute}, UserID: {user_id}")
        return jsonify({"username": username, "attribute": attribute, "user_id": user_id})
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
        'is_gm': attribute == 'GM'
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
    data = request.json
    room_name = data.get('room_name')
    if not room_name: return jsonify({"error": "No name"}), 400

    # DBに存在するかチェック
    if Room.query.filter_by(name=room_name).first():
        return jsonify({"error": "Room exists"}), 409

    new_state = { "characters": [], "timeline": [], "round": 0, "logs": [] }
    active_room_states[room_name] = new_state

    # ▼▼▼ 修正: Room作成時に owner_id を保存 ▼▼▼
    # save_room_to_db はデータ保存用なので、ここでは Roomモデルを直接作って owner_id を入れる
    new_room = Room(name=room_name, data=new_state, owner_id=session.get('user_id'))
    db.session.add(new_room)
    db.session.commit()
    # ▲▲▲ 修正ここまで ▲▲▲

    return jsonify({"message": "Created", "state": new_state}), 201

@app.route('/api/admin/users', methods=['GET'])
@session_required
def admin_get_users():
    if session.get('attribute') != 'GM':
        return jsonify({"error": "Forbidden"}), 403
    return jsonify(get_all_users())

@app.route('/api/admin/delete_user', methods=['POST'])
@session_required
def admin_delete_user():
    if session.get('attribute') != 'GM': return jsonify({"error": "Forbidden"}), 403
    user_id = request.json.get('user_id')
    if delete_user(user_id):
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Failed"}), 500

@app.route('/api/admin/transfer', methods=['POST'])
@session_required
def admin_transfer_user():
    if session.get('attribute') != 'GM': return jsonify({"error": "Forbidden"}), 403
    data = request.json
    count = transfer_ownership(data['old_id'], data['new_id'])
    return jsonify({"message": f"Transferred {count} characters/rooms."})

@app.route('/delete_room', methods=['POST'])
@session_required
def delete_room():
    """ルーム削除 - オーナーまたはGMのみ許可"""
    room_name = request.json.get('room_name')
    user_id = session.get('user_id')
    attribute = session.get('attribute')

    # ルームのオーナーを取得
    room = Room.query.filter_by(name=room_name).first()
    if not room:
        return jsonify({"error": "Room not found"}), 404

    # 権限チェック: オーナーまたはGMのみ削除可能
    if room.owner_id != user_id and attribute != 'GM':
        return jsonify({"error": "Permission denied"}), 403

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

    # オプション: 画像名を取得（未指定の場合はファイル名）
    image_name = request.form.get('name', file.filename)

    try:
        # Cloudinaryへアップロード
        # folder: 保存先フォルダ名（整理用）
        # transformation: 自動軽量化・リサイズ設定
        result = cloudinary.uploader.upload(
            file,
            folder="gemtrpg/characters",  # フォルダ分け（任意）
            transformation=[
                {'width': 300, 'crop': "limit"},  # 幅300pxに制限
                {'quality': "auto", 'fetch_format': "auto"}  # 自動最適化
            ]
        )

        # アップロード成功: セキュアURL（https）を返す
        secure_url = result['secure_url']
        public_id = result['public_id']

        logging.info(f"[Cloudinary] Image uploaded: {secure_url}")

        # ★ 画像レジストリに登録
        from manager.image_manager import register_image
        user_id = session.get('username', 'unknown')
        registered_image = register_image(
            url=secure_url,
            public_id=public_id,
            name=image_name,
            uploader=user_id,
            image_type='user'
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
    ローカル（static/images/characters）にある画像一覧を取得するAPI
    Cloudinaryを使わずにデフォルト素材を提供するため
    """
    try:
        # 画像ディレクトリのパス
        # static_folderがNoneの場合もあるので、app.root_path基点で作成
        img_dir = os.path.join(app.root_path, 'static', 'images', 'characters')

        if not os.path.exists(img_dir):
            return jsonify([])

        # 対応する拡張子
        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')

        images = []
        for filename in os.listdir(img_dir):
            if filename.lower().endswith(valid_extensions):
                # URLは images/characters/ファイル名 (staticフォルダがルートとして配信されているため)
                url = f"images/characters/{filename}"
                name = os.path.splitext(filename)[0]

                images.append({
                    "name": name,
                    "url": url,
                    "type": "default" # フロントエンド互換性のため
                })

        # 名前順でソート
        images.sort(key=lambda x: x['name'])

        return jsonify(images)
    except Exception as e:
        print(f"Error listing local images: {e}")
        return jsonify([]), 500



# ==========================================
#  Main Execution
# ==========================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--update', action='store_true', help='スキル・アイテム・輝化スキル・特殊パッシブの全データを更新')
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