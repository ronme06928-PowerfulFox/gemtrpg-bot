"""Phase 4: 管理者発行のワンタイム・パスワード再設定コード。

- app admin がユーザー単位で発行・再発行・失効する（権限チェックはルート層）。
- コード実値は発行直後の一度だけ返す。DB にはハッシュのみ保存する。
- 有効期限・失敗上限・一回使用・旧コード失効を持つ（Q26-007: 10文字/15分/5回）。
- 使用判定と used_at 更新は同一トランザクションで行う。
"""
from datetime import datetime, timedelta

import secrets
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import OneTimeLoginCode

# 読み間違えにくい英数字（0/O/1/I/L を除外）。
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10
DEFAULT_TTL_MINUTES = 15
MAX_FAILED_ATTEMPTS = 5


def generate_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _normalize(code):
    return str(code or "").strip().upper()


def issue_login_code(target_user_id, created_by_user_id, *, ttl_minutes=DEFAULT_TTL_MINUTES, commit=True):
    """対象ユーザーへワンタイムコードを発行する。既存の未使用コードは失効する。

    返り値はコード実値（呼び出し側が一度だけ表示する）。
    """
    if not target_user_id:
        return None
    now = datetime.utcnow()

    # 同一ユーザーの未使用・未失効コードを失効させる（新規発行で旧コード無効化）。
    actives = OneTimeLoginCode.query.filter_by(
        user_id=target_user_id, used_at=None, revoked_at=None
    ).all()
    for row in actives:
        row.revoked_at = now

    code = generate_code()
    record = OneTimeLoginCode(
        user_id=target_user_id,
        code_hash=generate_password_hash(_normalize(code)),
        created_by_user_id=created_by_user_id,
        created_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
        failed_attempts=0,
    )
    db.session.add(record)
    if commit:
        db.session.commit()
    return code


def verify_and_consume(target_user_id, code, *, max_failed=MAX_FAILED_ATTEMPTS):
    """対象ユーザーの最新有効コードを照合し、成功なら used_at を立てて consume する。

    成功時は OneTimeLoginCode 行を返す。失敗時は None（失敗回数を加算し、上限で失効）。
    """
    if not target_user_id or not code:
        return None
    now = datetime.utcnow()
    row = (
        OneTimeLoginCode.query
        .filter_by(user_id=target_user_id, used_at=None, revoked_at=None)
        .order_by(OneTimeLoginCode.created_at.desc())
        .first()
    )
    if row is None:
        return None
    if row.expires_at is not None and row.expires_at < now:
        return None
    if (row.failed_attempts or 0) >= max_failed:
        row.revoked_at = now
        db.session.commit()
        return None

    if not check_password_hash(row.code_hash, _normalize(code)):
        row.failed_attempts = (row.failed_attempts or 0) + 1
        if row.failed_attempts >= max_failed:
            row.revoked_at = now
        db.session.commit()
        return None

    # 成功: 使用済みにする（判定と更新を同一トランザクションで）。
    row.used_at = now
    db.session.commit()
    return row


def revoke_codes_for_user(target_user_id, *, commit=True):
    """対象ユーザーの未使用コードを全て失効する。失効件数を返す。"""
    if not target_user_id:
        return 0
    now = datetime.utcnow()
    actives = OneTimeLoginCode.query.filter_by(
        user_id=target_user_id, used_at=None, revoked_at=None
    ).all()
    for row in actives:
        row.revoked_at = now
    if commit:
        db.session.commit()
    return len(actives)
