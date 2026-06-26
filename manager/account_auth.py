"""Phase 2: アカウント認証のロジック層。

責務:
- ログイン識別子(login_name)の正規化と一意性チェック
- パスワードポリシー検証とハッシュ（werkzeug）
- パスワード設定・照合、auth_version の増加

session 発行や reset grant などのフロー制御はルート層が担う。ここは
DB と純粋ロジックに留め、`app.py` へロジックを積み増さない。
"""
import unicodedata
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import User

# パスワードはtrim・Unicode正規化しない。長さのみ検証する（仕様）。
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128


class PasswordPolicyError(ValueError):
    """パスワードがポリシー（長さ等）に反する。"""


class LoginNameError(ValueError):
    """login_name が不正、または既に使用されている。"""


def normalize_login_name(raw):
    """login_name を NFKC + casefold で正規化する。

    SQLite/PostgreSQL の collation 差へ依存せず一意判定するための正規化値。
    表示名(User.name)とは別物。空なら空文字を返す。
    """
    s = unicodedata.normalize("NFKC", str(raw or "")).strip()
    if not s:
        return ""
    return s.casefold()


def validate_password(password):
    """パスワードの長さポリシーを検証する。入力文字列はそのまま扱う。"""
    if password is None:
        raise PasswordPolicyError("パスワードを入力してください")
    length = len(password)
    if length < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError(f"パスワードは{PASSWORD_MIN_LENGTH}文字以上で入力してください")
    if length > PASSWORD_MAX_LENGTH:
        raise PasswordPolicyError(f"パスワードは{PASSWORD_MAX_LENGTH}文字以下で入力してください")
    return password


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password_hash, password):
    if not password_hash or password is None:
        return False
    return check_password_hash(password_hash, password)


def is_login_name_taken(normalized, exclude_user_id=None):
    """正規化済み login_name が既に使われているか。"""
    if not normalized:
        return False
    query = User.query.filter_by(login_name_normalized=normalized)
    if exclude_user_id:
        query = query.filter(User.id != exclude_user_id)
    return query.first() is not None


def find_user_by_login_name(login_name):
    """login_name（生入力）からユーザーを引く。無ければ None。"""
    normalized = normalize_login_name(login_name)
    if not normalized:
        return None
    return User.query.filter_by(login_name_normalized=normalized).first()


def set_login_name(user, login_name, *, commit=True):
    """ユーザーへ login_name を設定する（正規化・一意チェック付き）。"""
    normalized = normalize_login_name(login_name)
    if not normalized:
        raise LoginNameError("ログインIDを入力してください")
    if is_login_name_taken(normalized, exclude_user_id=user.id):
        raise LoginNameError("このログインIDは既に使われています")
    user.login_name_normalized = normalized
    if commit:
        db.session.commit()
    return user


def set_password(user, raw_password, *, bump_auth_version=False, commit=True):
    """パスワードを設定・更新する。

    bump_auth_version=True で auth_version を増やす（パスワード再設定・全端末
    失効に使う）。初回設定では既定で増やさない。
    """
    validate_password(raw_password)
    user.password_hash = hash_password(raw_password)
    user.password_changed_at = datetime.utcnow()
    if bump_auth_version:
        user.auth_version = (user.auth_version or 1) + 1
    if commit:
        db.session.commit()
    return user


def bump_auth_version(user, *, commit=True):
    """auth_version を増やして既存 session を失効させる（全端末ログアウト等）。"""
    user.auth_version = (user.auth_version or 1) + 1
    if commit:
        db.session.commit()
    return user


def verify_user_password(user, raw_password):
    """ユーザーのパスワードを照合する。未設定なら常に False。"""
    if user is None:
        return False
    return verify_password(getattr(user, "password_hash", None), raw_password)
