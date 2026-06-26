"""Phase 3: 信頼済み端末トークン（TrustedDeviceToken）の管理。

端末ごとの行で自動ログインを管理する（User.recovery_token_hash 1個に依存しない）。
- クライアントは `selector + secret` を localStorage に保存する。
- DB には secret 平文を置かず、ハッシュのみ保存する。
- selector で行を引き、secret のハッシュを定数時間比較で照合する。

Phase 7 のUIがこの方式へ移行する。発行/照合/失効のロジックをここへ集約する。
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from extensions import db
from models import TrustedDeviceToken

# Q26-005: 端末トークンの有効期限は 30日を初期値とする。
DEFAULT_TTL_DAYS = 30


def _hash_secret(secret):
    return hashlib.sha256(str(secret or "").encode("utf-8")).hexdigest()


def issue_device_token(user_id, *, ttl_days=DEFAULT_TTL_DAYS, commit=True):
    """新しい端末トークンを発行し、selector と secret を返す（保存はハッシュのみ）。"""
    if not user_id:
        return None
    selector = secrets.token_urlsafe(12)
    secret = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    row = TrustedDeviceToken(
        user_id=user_id,
        selector=selector,
        token_hash=_hash_secret(secret),
        created_at=now,
        expires_at=now + timedelta(days=ttl_days),
    )
    db.session.add(row)
    if commit:
        db.session.commit()
    return {"selector": selector, "secret": secret}


def verify_device_token(selector, secret):
    """selector + secret を照合し、有効なら user_id を返す。無効なら None。"""
    if not selector or not secret:
        return None
    row = TrustedDeviceToken.query.filter_by(selector=selector).first()
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at is not None and row.expires_at < datetime.utcnow():
        return None
    if not secrets.compare_digest(row.token_hash, _hash_secret(secret)):
        return None
    # 利用時刻を更新する（有効期限の延長は現状しない / Q26-005 未決）。
    row.last_used_at = datetime.utcnow()
    db.session.commit()
    return row.user_id


def revoke_device_token(selector, *, commit=True):
    """単一端末トークンを失効する（完全ログアウト用）。失効したら True。"""
    if not selector:
        return False
    row = TrustedDeviceToken.query.filter_by(selector=selector, revoked_at=None).first()
    if row is None:
        return False
    row.revoked_at = datetime.utcnow()
    if commit:
        db.session.commit()
    return True


def revoke_all_device_tokens(user_id, *, commit=True):
    """ユーザーの全端末トークンを失効する（全端末ログアウト用）。失効件数を返す。"""
    if not user_id:
        return 0
    rows = TrustedDeviceToken.query.filter_by(user_id=user_id, revoked_at=None).all()
    now = datetime.utcnow()
    for row in rows:
        row.revoked_at = now
    if commit:
        db.session.commit()
    return len(rows)
