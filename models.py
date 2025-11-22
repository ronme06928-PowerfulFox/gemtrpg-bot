from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
import json

# SQLAlchemyのインスタンス作成
db = SQLAlchemy()

class Room(db.Model):
    """
    ルーム情報を保存するテーブル
    """
    __tablename__ = 'rooms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    # ルームの状態（キャラクター、TL、ログなど）を丸ごとJSONで保存
    # SQLite等では Text 型として扱い、PostgreSQLでは JSONB として扱えるように互換性を持たせます
    data = db.Column(db.JSON, default={})

    def __repr__(self):
        return f'<Room {self.name}>'