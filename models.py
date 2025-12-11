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