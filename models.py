from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
import json
from extensions import db
from datetime import datetime

class User(db.Model):
    """ユーザー情報を管理するテーブル"""
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True)  # UUID
    name = db.Column(db.String(100), nullable=False)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)

class Room(db.Model):
    """ルーム情報を保存するテーブル"""
    __tablename__ = 'rooms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    # ★追加: ルーム作成者のIDを記録
    owner_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)

    data = db.Column(db.JSON, default={})

    def __repr__(self):
        return f'<Room {self.name}>'


class ImageRegistry(db.Model):
    """画像レジストリテーブル - Cloudinaryにアップロードされた画像のメタデータを管理"""
    __tablename__ = 'image_registry'

    id = db.Column(db.String(36), primary_key=True)  # UUID
    name = db.Column(db.String(200), nullable=False)  # 画像名
    url = db.Column(db.String(500), nullable=False)   # Cloudinary URL
    public_id = db.Column(db.String(200), nullable=True)  # Cloudinary public_id
    type = db.Column(db.String(20), default='user')   # 'user' or 'default'
    uploader = db.Column(db.String(100), nullable=True)  # アップロードしたユーザー名
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """辞書形式に変換（API互換性のため）"""
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'public_id': self.public_id,
            'type': self.type,
            'uploader': self.uploader,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f'<ImageRegistry {self.name}>'
