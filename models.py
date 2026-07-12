from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
import json
from extensions import db
from datetime import datetime

class User(db.Model):
    """ユーザー情報を管理するテーブル"""
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True)  # UUID
    name = db.Column(db.String(100), nullable=False)  # 表示名（重複可）
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    is_app_admin = db.Column(db.Boolean, default=False, nullable=False)
    recovery_code_hash = db.Column(db.String(255), nullable=True)
    recovery_token_hash = db.Column(db.String(64), nullable=True)
    recovery_code_issued_at = db.Column(db.DateTime, nullable=True)

    # --- Phase 1 拡張（expand: 既存コード互換のため nullable で先行導入） ---
    # ログイン識別子の正規化値（NFKC+casefold等）。重複可の表示名と分離する。
    login_name_normalized = db.Column(db.String(100), unique=True, nullable=True)
    # パスワードハッシュ。既存ユーザー移行中のみ null を許可する。
    password_hash = db.Column(db.String(255), nullable=True)
    password_changed_at = db.Column(db.DateTime, nullable=True)
    # パスワード再設定や「全端末ログアウト」で増やし、session 側の値と突き合わせる。
    auth_version = db.Column(db.Integer, default=1, nullable=False)

class Room(db.Model):
    """ルーム情報を保存するテーブル"""
    __tablename__ = 'rooms'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    # ★追加: ルーム作成者のIDを記録
    owner_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)

    gm_pin_hash = db.Column(db.String(255), nullable=True)
    data = db.Column(db.JSON, default=dict)

    # --- Phase 1 拡張（expand: nullable で先行導入） ---
    description = db.Column(db.Text, nullable=True)
    # hidden | listed | closed。既存ルームは最小露出のため hidden を既定にする。
    lobby_visibility = db.Column(db.String(20), default='hidden', nullable=True)
    recruitment_status = db.Column(db.String(20), nullable=True)
    # 参加コードは GM PIN とは別の秘密値として扱う（流用しない）。
    join_code_hash = db.Column(db.String(255), nullable=True)
    join_code_rotated_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<Room {self.name}>'


class RoomLogArchive(db.Model):
    """切り捨て前のルームログを長期保全するテーブル。"""
    __tablename__ = 'room_log_archives'

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False, index=True)
    room_name = db.Column(db.String(100), nullable=False, index=True)
    log_id = db.Column(db.Integer, nullable=True)
    timestamp_ms = db.Column(db.BigInteger, nullable=True)
    log_type = db.Column(db.String(50), nullable=True)
    user_name = db.Column(db.String(100), nullable=True)
    secret = db.Column(db.Boolean, default=False, nullable=False)
    message = db.Column(db.Text, nullable=True)
    payload = db.Column(db.JSON, nullable=True)
    archived_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        db.Index('ix_room_log_archives_room_time', 'room_id', 'timestamp_ms', 'log_id'),
    )

    def to_log_dict(self):
        payload = self.payload if isinstance(self.payload, dict) else {}
        data = dict(payload)
        if self.log_id is not None:
            data['log_id'] = self.log_id
        if self.timestamp_ms is not None:
            data['timestamp'] = self.timestamp_ms
        if self.message is not None:
            data['message'] = self.message
        if self.log_type is not None:
            data['type'] = self.log_type
        if self.user_name is not None:
            data['user'] = self.user_name
        data['secret'] = bool(self.secret)
        return data

    def __repr__(self):
        return f'<RoomLogArchive room={self.room_name} log={self.log_id}>'


class TrustedDeviceToken(db.Model):
    """信頼済み端末トークン（端末単位の自動ログイン）。

    User.recovery_token_hash 1個ではなく端末ごとの行で管理する。
    localStorage には selector + secret を保存し、DB には secret 平文を置かない。
    """
    __tablename__ = 'trusted_device_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    selector = db.Column(db.String(32), unique=True, nullable=False)  # 公開側識別子
    token_hash = db.Column(db.String(64), nullable=False)  # secret部分のハッシュ
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<TrustedDeviceToken {self.selector} user={self.user_id}>'


class OneTimeLoginCode(db.Model):
    """管理者発行のワンタイム・パスワード再設定コード。

    User 列へ直接置かず発行履歴を独立管理する。コード実値は保存しない。
    """
    __tablename__ = 'one_time_login_codes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    code_hash = db.Column(db.String(255), nullable=False)
    created_by_user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    failed_attempts = db.Column(db.Integer, default=0, nullable=False)

    def __repr__(self):
        return f'<OneTimeLoginCode user={self.user_id} used={self.used_at is not None}>'


class RoomMember(db.Model):
    """ルーム会員（owner/gm/player）。

    本番Neonに手動作成済みの `room_members` を採用し、スキーマの正をコード側へ
    寄せる。既存列（id/room_id/user_id/role/joined_at/granted_by_user_id）を踏襲し、
    manual 6.4 の `updated_at`／`revoked_at` を追加する。
    有効membership（revoked_at IS NULL）について (room_id, user_id) を一意にする。
    """
    __tablename__ = 'room_members'

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String(20), default='player', nullable=False)  # owner | gm | player
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    granted_by_user_id = db.Column(db.String(36), nullable=True)  # 既存prod列を踏襲（付与者）
    # --- 追加（manual 6.4） ---
    updated_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.Index(
            'uq_room_members_active', 'room_id', 'user_id', unique=True,
            sqlite_where=db.text('revoked_at IS NULL'),
            postgresql_where=db.text('revoked_at IS NULL'),
        ),
    )

    def __repr__(self):
        return f'<RoomMember room={self.room_id} user={self.user_id} role={self.role}>'


class OwnedCharacter(db.Model):
    """アカウントに紐づく持ちキャラ（計画36）。

    ルーム従属の `Room.data['characters']` とは別に、ユーザーが自分の
    キャラクターシートを永続保存し、複数ルーム・ホロウへ使い回せるようにする。
    `data` は CharaCreator 出力の `data` 部をそのまま格納し、スキーマの細分化はしない。
    """
    __tablename__ = 'owned_characters'

    id = db.Column(db.String(36), primary_key=True)  # UUID
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    data = db.Column(db.JSON, nullable=False)
    exp_total = db.Column(db.Integer, default=0, nullable=False)
    growth_log = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'data': self.data,
            'exp_total': self.exp_total,
            'growth_log': self.growth_log or [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f'<OwnedCharacter {self.id} user={self.user_id} name={self.name}>'


class ImageRegistry(db.Model):
    """画像レジストリテーブル - Cloudinaryにアップロードされた画像のメタデータを管理"""
    __tablename__ = 'image_registry'

    id = db.Column(db.String(36), primary_key=True)  # UUID
    name = db.Column(db.String(200), nullable=False)  # 画像名
    url = db.Column(db.String(500), nullable=False)   # Cloudinary URL
    public_id = db.Column(db.String(200), nullable=True)  # Cloudinary public_id
    type = db.Column(db.String(20), default='user')   # 'user' or 'default'
    visibility = db.Column(db.String(20), default='public') # 'public' or 'gm'
    uploader = db.Column(db.String(100), nullable=True)  # アップロードしたユーザー名
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """辞書形式に変換（API互換性のため）"""
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'public_id': self.public_id,
            'url': self.url,
            'public_id': self.public_id,
            'type': self.type,
            'visibility': self.visibility,
            'uploader': self.uploader,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f'<ImageRegistry {self.name}>'
