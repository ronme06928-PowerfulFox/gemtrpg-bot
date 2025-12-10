import os
import sys
import argparse

# === 環境判定とEventletパッチ ===
IS_RENDER = 'RENDER' in os.environ
if IS_RENDER:
    import eventlet
    eventlet.monkey_patch()

from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS

# ★ 拡張機能（共有インスタンス）のインポート
from extensions import db, socketio, active_room_states, all_skill_data
from models import Room

# ★ マネージャー（ロジック層）からのインポート
from manager.data_manager import (
    init_app_data, read_saved_rooms, save_room_to_db, delete_room_from_db
)
from manager.room_manager import get_room_state
from manager.utils import session_required

# ★ イベントハンドラ（SocketIO層）のインポート
# これをインポートすることで、@socketio.on デコレータが登録されます
import events.socket_main
import events.socket_battle
import events.socket_char

# === アプリ設定 ===
load_dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(load_dotenv_path):
    from dotenv import load_dotenv
    load_dotenv(load_dotenv_path)

app = Flask(__name__, static_folder=None)
app.config['JSON_AS_ASCII'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default_insecure_key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///gemtrpg.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 静的ファイルのパス
STATIC_DIR = os.path.join(app.root_path, 'static')

# === 初期化 ===
CORS(app, supports_credentials=True)
db.init_app(app)

async_mode = 'eventlet' if IS_RENDER else 'threading'
# extensionsにあるsocketioをアプリと紐付け
socketio.init_app(app, cors_allowed_origins="*", async_mode=async_mode)

# データ初期化実行
with app.app_context():
    init_app_data()

# ==========================================
#  HTTP Routes
# ==========================================

@app.route('/')
def serve_index():
    print(f"👀 Accessing Root! Serving from: {STATIC_DIR}")
    return send_from_directory(STATIC_DIR, 'index.html')

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
    return jsonify({"message": "セッション開始", "username": username, "attribute": attribute})

@app.route('/api/get_session_user', methods=['GET'])
def get_session_user():
    if 'username' in session:
        return jsonify({"username": session.get('username'), "attribute": session.get('attribute')})
    else:
        return jsonify({"username": None, "attribute": None}), 401

@app.route('/list_rooms', methods=['GET'])
@session_required
def list_rooms():
    rooms = read_saved_rooms()
    return jsonify(list(rooms.keys()))

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
    save_room_to_db(room_name, new_state)
    return jsonify({"message": "Created", "state": new_state}), 201

@app.route('/delete_room', methods=['POST'])
@session_required
def delete_room():
    room_name = request.json.get('room_name')
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


# ==========================================
#  Main Execution
# ==========================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--update', action='store_true')
    args = parser.parse_args()

    if args.update:
        from manager.data_manager import fetch_and_save_sheets_data
        fetch_and_save_sheets_data()
        sys.exit()

    print("Starting Flask-SocketIO server...")
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)