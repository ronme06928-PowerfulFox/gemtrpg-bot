"""アカウント認証・セッション系の HTTP ハンドラ。

entry / register / login / logout / set_password / change_display_name /
recover_* / regenerate_recovery_code / get_session_user /
admin_issue_login_code / redeem_login_code を担う。
"""

import logging
import os
import time as _time
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from extensions import db
from models import User
from manager import account_auth, device_token, one_time_code
from manager.auth import GM_ATTRIBUTE, PLAYER_ATTRIBUTE
from manager.auth_rate_limit import password_login_limiter, one_time_code_limiter
from manager.user_manager import (
    upsert_user,
    is_user_management_admin,
    recover_user_by_local_token,
    recover_user_by_name_and_code,
    regenerate_user_recovery_code,
)
from manager.utils import session_required
from routes.common import require_app_admin

account_bp = Blueprint('account', __name__)

# ログイン失敗時のタイミング差を縮めるためのダミーハッシュ（存在判別を防ぐ）。
_DUMMY_PASSWORD_HASH = account_auth.hash_password("timing-dummy-password")


def _set_authenticated_session(user, *, attribute=PLAYER_ATTRIBUTE, clear=True):
    """ログイン成立時のセッションを統一して張る。

    session.clear() で古いルーム権限を持ち越さず、auth_version を必ず載せる
    （session_required の auth_version 検証と整合させる）。
    """
    if clear:
        session.clear()
    session['user_id'] = user.id
    session['username'] = user.name
    session['auth_version'] = user.auth_version or 1
    session['attribute'] = attribute


def _name_only_login_disabled():
    """名前だけログイン(/api/entry)を無効化するか（cutover用フラグ、既定off）。"""
    return str(os.environ.get('ACCOUNT_DISABLE_NAME_ONLY_LOGIN') or '').strip() == '1'


# パスワード設定専用grant（ワンタイムコード認証後の短命許可）。
# 通常sessionとは別物で、ルーム・管理APIには入れない（session_required を通らない）。
PW_RESET_GRANT_TTL_SECONDS = 600  # コード確認後、パスワード設定までの猶予


def _set_pw_reset_grant(user_id):
    session.clear()
    session['pw_reset_user_id'] = user_id
    session['pw_reset_expires'] = _time.time() + PW_RESET_GRANT_TTL_SECONDS


def _valid_pw_reset_grant():
    uid = session.get('pw_reset_user_id')
    exp = session.get('pw_reset_expires')
    if not uid or not exp:
        return None
    if _time.time() > exp:
        return None
    return uid


@account_bp.route('/api/entry', methods=['POST'])
def entry():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username') or '').strip()

    if _name_only_login_disabled():
        return jsonify({"error": "ログインIDとパスワードでログインしてください"}), 403

    if not username:
        return jsonify({"error": "ユーザー名は必須です"}), 400

    session['username'] = username
    # Client-supplied GM attributes are not trusted.  GM is granted only by
    # room PIN verification in /api/enter_room or /create_room.
    if session.get('attribute') != GM_ATTRIBUTE:
        session['attribute'] = PLAYER_ATTRIBUTE

    # ▼▼▼ 修正: ID発行とDB保存 ▼▼▼
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

    # ユーザー情報をDBに記録。新規/未発行ユーザーには復旧コードを一度だけ返す。
    user_result = upsert_user(session['user_id'], username, issue_recovery=True) or {}
    # ▲▲▲ 修正ここまで ▲▲▲

    # auth_version をセッションへ載せる（session_required の検証と整合）。
    user_obj = user_result.get("user")
    session['auth_version'] = (getattr(user_obj, 'auth_version', None) or 1)

    return jsonify({
        "message": "セッション開始",
        "username": username,
        "attribute": session.get('attribute', PLAYER_ATTRIBUTE),
        "user_id": session['user_id'],
        "is_app_admin": is_user_management_admin(session['user_id']),
        "recovery_code": user_result.get("recovery_code"),
        "recovery_token": user_result.get("recovery_token"),
    })


@account_bp.route('/api/recover_user', methods=['POST'])
def recover_user():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username') or '').strip()
    recovery_code = str(data.get('recovery_code') or '').strip()
    result = recover_user_by_name_and_code(username, recovery_code)
    if not result:
        return jsonify({"error": "名前または復旧コードが正しくありません"}), 403

    user = result["user"]
    _set_authenticated_session(user)

    return jsonify({
        "message": "ユーザーを復旧しました",
        "username": user.name,
        "attribute": PLAYER_ATTRIBUTE,
        "user_id": user.id,
        "is_app_admin": is_user_management_admin(user.id),
        "recovery_token": result.get("recovery_token"),
    })


@account_bp.route('/api/recover_from_local_token', methods=['POST'])
def recover_from_local_token():
    data = request.get_json(silent=True) or {}
    user = recover_user_by_local_token(
        str(data.get('user_id') or '').strip(),
        str(data.get('recovery_token') or '').strip(),
    )
    if not user:
        return jsonify({"error": "保存済み復旧トークンが無効です"}), 403

    _set_authenticated_session(user)

    return jsonify({
        "message": "保存済み復旧トークンで復帰しました",
        "username": user.name,
        "attribute": PLAYER_ATTRIBUTE,
        "user_id": user.id,
        "is_app_admin": is_user_management_admin(user.id),
    })


def _account_profile(user):
    return {
        "username": user.name,
        "user_id": user.id,
        "attribute": PLAYER_ATTRIBUTE,
        "is_app_admin": is_user_management_admin(user.id),
    }


@account_bp.route('/api/register', methods=['POST'])
def register_account():
    """新規アカウント登録（login_name + password）。"""
    data = request.get_json(silent=True) or {}
    login_name = str(data.get('login_name') or '').strip()
    password = data.get('password')
    display_name = str(data.get('display_name') or '').strip() or login_name

    normalized = account_auth.normalize_login_name(login_name)
    if not normalized:
        return jsonify({"error": "ログインIDを入力してください"}), 400
    if account_auth.is_login_name_taken(normalized):
        return jsonify({"error": "このログインIDは既に使われています"}), 409
    try:
        account_auth.validate_password(password)
    except account_auth.PasswordPolicyError as e:
        return jsonify({"error": str(e)}), 400

    user = User(id=str(uuid.uuid4()), name=display_name)
    db.session.add(user)
    db.session.flush()
    account_auth.set_login_name(user, login_name, commit=False)
    account_auth.set_password(user, password, commit=False)
    user.last_login = datetime.utcnow()
    db.session.commit()

    _set_authenticated_session(user)
    return jsonify({"message": "アカウントを作成しました", **_account_profile(user)}), 201


@account_bp.route('/api/login', methods=['POST'])
def login_account():
    """login_name + password でログインする。"""
    data = request.get_json(silent=True) or {}
    login_name = str(data.get('login_name') or '').strip()
    password = data.get('password')
    normalized = account_auth.normalize_login_name(login_name)
    limiter_key = normalized or 'unknown'

    if not password_login_limiter.is_allowed(limiter_key):
        return jsonify({"error": "試行回数が多すぎます。しばらくしてからお試しください"}), 429

    generic = "ログインIDまたはパスワードが正しくありません"
    user = account_auth.find_user_by_login_name(login_name) if normalized else None

    # 存在判別の時間差を縮める: 未登録/未設定でもダミー照合を行う。
    if user is None or not getattr(user, 'password_hash', None):
        account_auth.verify_password(_DUMMY_PASSWORD_HASH, password or '')
        password_login_limiter.record_failure(limiter_key)
        return jsonify({"error": generic}), 401

    if not account_auth.verify_user_password(user, password):
        password_login_limiter.record_failure(limiter_key)
        return jsonify({"error": generic}), 401

    password_login_limiter.reset(limiter_key)
    user.last_login = datetime.utcnow()
    db.session.commit()
    _set_authenticated_session(user)
    return jsonify({"message": "ログインしました", **_account_profile(user)})


@account_bp.route('/api/set_password', methods=['POST'])
def set_account_password():
    """パスワード設定。次の2経路を受け付ける。

    1) 通常の認証済みセッション（既存ユーザーの初回移行: recover 後に設定）。
    2) パスワード設定専用grant（管理者ワンタイムコード認証後）。grant 経路では
       設定完了時に auth_version 増加＋全端末トークン失効を行い、通常sessionへ昇格する。
    """
    data = request.get_json(silent=True) or {}
    login_name = str(data.get('login_name') or '').strip()
    password = data.get('password')

    reset_user_id = _valid_pw_reset_grant()
    if reset_user_id:
        user = User.query.get(reset_user_id)
        is_reset = True
    else:
        uid = session.get('user_id')
        if 'username' not in session or not uid:
            return jsonify({"error": "認証が必要です"}), 401
        user = User.query.get(uid)
        if user is None or session.get('auth_version') != user.auth_version:
            session.clear()
            return jsonify({"error": "認証が必要です"}), 401
        is_reset = False

    if user is None:
        session.clear()
        return jsonify({"error": "認証が必要です"}), 401

    try:
        account_auth.validate_password(password)
    except account_auth.PasswordPolicyError as e:
        return jsonify({"error": str(e)}), 400

    if login_name:
        try:
            account_auth.set_login_name(user, login_name, commit=False)
        except account_auth.LoginNameError as e:
            return jsonify({"error": str(e)}), 409
    elif not user.login_name_normalized:
        return jsonify({"error": "ログインIDを設定してください"}), 400

    account_auth.set_password(user, password, bump_auth_version=is_reset, commit=False)
    if is_reset:
        # 再設定: 全端末トークン失効＋全セッション失効。このセッションは昇格する。
        device_token.revoke_all_device_tokens(user.id, commit=False)
        db.session.commit()
        _set_authenticated_session(user)
    else:
        db.session.commit()
        session['auth_version'] = user.auth_version
    return jsonify({"message": "パスワードを設定しました", **_account_profile(user)})


@account_bp.route('/api/change_display_name', methods=['POST'])
@session_required
def change_display_name():
    """表示名(User.name)を変更する。ログイン/認可とは独立。"""
    data = request.get_json(silent=True) or {}
    new_name = str(data.get('display_name') or '').strip()
    if not new_name:
        return jsonify({"error": "表示名を入力してください"}), 400
    user = User.query.get(session.get('user_id'))
    if user is None:
        return jsonify({"error": "認証が必要です"}), 401
    user.name = new_name
    db.session.commit()
    session['username'] = new_name
    return jsonify({"message": "表示名を変更しました", "username": new_name, "user_id": user.id})


@account_bp.route('/api/logout', methods=['POST'])
def logout_account():
    """ログアウト。mode: session(通常) | device(完全) | all(全端末)。

    - session: Flask session を破棄するだけ。端末トークンは保持する
      （自動復旧の停止はクライアント側の明示操作まで＝Phase 7）。
    - device: session 破棄 + 現端末トークンを失効。payload に selector があれば
      該当 TrustedDeviceToken を失効。併せて旧 recovery_token_hash も無効化し、
      レガシー自動復旧を止める。
    - all: session 破棄 + auth_version 増加（全セッション失効）+ 全端末トークン
      失効（TrustedDeviceToken 全件 + recovery_token_hash クリア）。
    """
    data = request.get_json(silent=True) or {}
    mode = str(data.get('mode') or 'session').strip().lower()
    if mode not in ('session', 'device', 'all'):
        return jsonify({"error": "不正なログアウト種別です"}), 400

    user_id = session.get('user_id')
    selector = str(data.get('selector') or '').strip()

    if mode == 'session':
        session.clear()
        return jsonify({"message": "ログアウトしました", "mode": mode})

    user = User.query.get(user_id) if user_id else None

    if mode == 'device':
        if selector:
            device_token.revoke_device_token(selector)
        if user is not None and getattr(user, 'recovery_token_hash', None):
            user.recovery_token_hash = None
            db.session.commit()
        session.clear()
        return jsonify({"message": "この端末からログアウトしました", "mode": mode})

    # mode == 'all'
    if user is not None:
        device_token.revoke_all_device_tokens(user.id)
        user.recovery_token_hash = None
        account_auth.bump_auth_version(user)  # commit を含む
    session.clear()
    return jsonify({"message": "全端末からログアウトしました", "mode": mode})


@account_bp.route('/api/admin/issue_login_code', methods=['POST'])
@session_required
def admin_issue_login_code():
    """app admin が対象ユーザーへワンタイム・パスワード再設定コードを発行する。"""
    denied = require_app_admin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    target_user_id = str(data.get('user_id') or '').strip()
    if not target_user_id:
        return jsonify({"error": "User ID required"}), 400
    target = User.query.get(target_user_id)
    if target is None:
        return jsonify({"error": "User not found"}), 404

    code = one_time_code.issue_login_code(target_user_id, session.get('user_id'))
    # 監査: 発行者・対象・時刻を記録する（コード値は記録しない）。
    logging.info(f"[AUDIT] one-time login code issued by={session.get('user_id')} target={target_user_id}")
    return jsonify({
        "message": "ワンタイムコードを発行しました",
        "code": code,  # 発行直後の一度だけ表示する
        "user_id": target_user_id,
        "username": target.name,
        "expires_in_minutes": one_time_code.DEFAULT_TTL_MINUTES,
    })


@account_bp.route('/api/redeem_login_code', methods=['POST'])
def redeem_login_code():
    """ワンタイムコードを使用し、パスワード設定専用grantを発行する。"""
    data = request.get_json(silent=True) or {}
    login_name = str(data.get('login_name') or '').strip()
    code = str(data.get('code') or '').strip()
    limiter_key = account_auth.normalize_login_name(login_name) or 'unknown'

    if not one_time_code_limiter.is_allowed(limiter_key):
        return jsonify({"error": "試行回数が多すぎます。しばらくしてからお試しください"}), 429

    generic = "ログインIDまたはコードが正しくありません"
    user = account_auth.find_user_by_login_name(login_name) if login_name else None
    if user is None:
        one_time_code_limiter.record_failure(limiter_key)
        return jsonify({"error": generic}), 401

    consumed = one_time_code.verify_and_consume(user.id, code)
    if consumed is None:
        one_time_code_limiter.record_failure(limiter_key)
        return jsonify({"error": generic}), 401

    one_time_code_limiter.reset(limiter_key)
    _set_pw_reset_grant(user.id)
    logging.info(f"[AUDIT] one-time login code redeemed target={user.id}")
    return jsonify({
        "message": "コードを確認しました。新しいパスワードを設定してください",
        "require_password_set": True,
    })


@account_bp.route('/api/regenerate_recovery_code', methods=['POST'])
@session_required
def regenerate_recovery_code():
    result = regenerate_user_recovery_code(session.get('user_id'))
    if not result:
        return jsonify({"error": "ユーザーが見つかりません"}), 404
    user = result["user"]
    return jsonify({
        "message": "復旧コードを再発行しました",
        "username": user.name,
        "user_id": user.id,
        "recovery_code": result.get("recovery_code"),
        "recovery_token": result.get("recovery_token"),
    })


@account_bp.route('/api/get_session_user', methods=['GET'])
def get_session_user():
    username = session.get('username')
    user_id = session.get('user_id')
    if not username or not user_id:
        return jsonify({"username": None, "attribute": None, "user_id": None}), 401

    # 削除済みユーザーのセッションでここに来た場合、upsert_user に渡すと
    # ユーザーを復活させてしまう。先に実在を確認し、無ければ失効させる。
    _user = User.query.get(user_id)
    if _user is None:
        session.clear()
        return jsonify({"username": None, "attribute": None, "user_id": None}), 401
    # auth_version 不一致のセッションは失効させる（Q26-015）。
    if session.get('auth_version') != _user.auth_version:
        session.clear()
        return jsonify({"username": None, "attribute": None, "user_id": None}), 401

    attribute = session.get('attribute')
    # トークン未発行の既存ユーザーには一度だけ発行する（再発行はしない）。
    user_result = upsert_user(user_id, username, issue_recovery=True) or {}
    logging.info(f"[SESSION CHECK] User: {username}, Attribute: {attribute}, UserID: {user_id}")
    return jsonify({
        "username": username,
        "attribute": attribute,
        "user_id": user_id,
        "is_app_admin": is_user_management_admin(user_id),
        "recovery_code": user_result.get("recovery_code"),
        "recovery_token": user_result.get("recovery_token"),
    })
