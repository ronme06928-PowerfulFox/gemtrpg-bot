# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

# インスタンスの「枠」だけ作成
db = SQLAlchemy()
socketio = SocketIO()

# グローバル変数（状態管理）をここに集約
# app.py や data_manager.py にあった変数を移動
all_skill_data = {}
active_room_states = {}
user_sids = {}