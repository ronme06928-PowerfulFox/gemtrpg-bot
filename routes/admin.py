"""アプリ管理者向けユーザー管理と画像使用量の HTTP ハンドラ。"""

from contextlib import nullcontext
from datetime import datetime
from math import isfinite

import cloudinary.api
from flask import Blueprint, current_app, jsonify, request, session
from urllib3.exceptions import MaxRetryError, NewConnectionError, TimeoutError as HTTPTimeoutError

from extensions import socketio
from manager.auth import verify_master_key
from manager.user_manager import (
    get_all_users,
    delete_user,
    transfer_ownership,
    get_user_owned_items,
    is_user_management_admin,
    set_user_management_admin,
    set_catalog_author,
)
from manager.utils import session_required
from routes.common import require_app_admin

admin_bp = Blueprint('admin', __name__)
IMAGE_USAGE_TIMEOUT = 3


def _can_manage_users_with_payload(payload=None):
    payload = payload or {}
    if is_user_management_admin(session.get('user_id')):
        return True
    master_key = payload.get('master_key') or payload.get('gm_master_key') or ''
    return verify_master_key(master_key)


@admin_bp.route('/api/admin/user_details', methods=['GET'])
@session_required
def admin_get_user_details():
    denied = require_app_admin()
    if denied:
        return denied
    target_user_id = request.args.get('user_id')
    if not target_user_id:
        return jsonify({"error": "User ID required"}), 400

    data = get_user_owned_items(target_user_id)
    return jsonify(data)


@admin_bp.route('/api/admin/users', methods=['GET'])
@session_required
def admin_get_users():
    denied = require_app_admin()
    if denied:
        return denied
    return jsonify({
        "users": get_all_users(),
        "can_manage_users": True,
    })


def _image_usage_deadline():
    if getattr(socketio, 'async_mode', None) == 'eventlet':
        from eventlet import Timeout

        # 通信単位のタイムアウトに加え、SDK 内の再試行を含む全体を制限する。
        return Timeout(IMAGE_USAGE_TIMEOUT, TimeoutError())
    return nullcontext()


def _image_usage_timed_out(exc):
    # SDK は urllib3 の例外を GeneralError に包む。
    while exc is not None:
        if isinstance(exc, NewConnectionError):
            return False
        if isinstance(exc, (TimeoutError, HTTPTimeoutError)):
            return True
        exc = exc.reason if isinstance(exc, MaxRetryError) else exc.__cause__ or exc.__context__
    return False


def _usage_number(value):
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise ValueError('Invalid Cloudinary usage metric')
    return value


@admin_bp.route('/api/admin/image_usage', methods=['GET'])
@session_required
def admin_image_usage():
    denied = require_app_admin()
    if denied:
        return denied

    config = cloudinary.config()
    if not all((config.cloud_name, config.api_key, config.api_secret)):
        return jsonify(available=False, reason='Cloudinary の鍵が未設定です')

    try:
        with _image_usage_deadline():
            usage = cloudinary.api.usage(timeout=IMAGE_USAGE_TIMEOUT)
    except Exception as exc:
        reason = ('Cloudinary の応答が時間切れです' if _image_usage_timed_out(exc)
                  else 'Cloudinary との通信に失敗しました')
        current_app.logger.warning('画像の使用量: %s', reason)
        return jsonify(available=False, reason=reason)

    try:
        used = _usage_number(usage['credits']['usage'])
        limit = _usage_number(usage['credits']['limit'])
        ratio = used / limit
        breakdown = {
            key: {'usage': _usage_number(usage[key]['usage']),
                  'credits': _usage_number(usage[key]['credits_usage'])}
            for key in ('storage', 'bandwidth', 'transformations')
        }
        last_updated = usage['last_updated']
        datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError):
        current_app.logger.warning('画像の使用量: Cloudinary の応答形式が不正です')
        return jsonify(available=False, reason='Cloudinary の応答形式が不正です')

    return jsonify(available=True, credits={'usage': used, 'limit': limit, 'percent': ratio * 100},
                   breakdown=breakdown, last_updated=last_updated, over_half=ratio > 0.5)


@admin_bp.route('/api/admin/delete_user', methods=['POST'])
@session_required
def admin_delete_user():
    data = request.get_json(silent=True) or {}
    if not _can_manage_users_with_payload(data):
        return jsonify({"error": "ユーザー管理権限またはマスターキーが必要です"}), 403
    user_id = data.get('user_id')
    if delete_user(user_id):
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Failed"}), 500


@admin_bp.route('/api/admin/transfer', methods=['POST'])
@session_required
def admin_transfer_user():
    data = request.get_json(silent=True) or {}
    if not _can_manage_users_with_payload(data):
        return jsonify({"error": "ユーザー管理権限またはマスターキーが必要です"}), 403
    try:
        result = transfer_ownership(data.get('old_id'), data.get('new_id'))
        return jsonify({"message": "Transferred.", "result": result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@admin_bp.route('/api/admin/set_user_management_admin', methods=['POST'])
@session_required
def admin_set_user_management_admin():
    data = request.get_json(silent=True) or {}
    if not verify_master_key(data.get('master_key') or ''):
        return jsonify({"error": "マスターキーが正しくありません"}), 403
    target_user_id = data.get('user_id')
    enabled = bool(data.get('enabled'))
    if not target_user_id:
        return jsonify({"error": "User ID required"}), 400
    if not set_user_management_admin(target_user_id, enabled):
        return jsonify({"error": "User not found"}), 404
    return jsonify({"message": "Updated", "user_id": target_user_id, "is_app_admin": enabled})


@admin_bp.route('/api/admin/set_catalog_author', methods=['POST'])
@session_required
def admin_set_catalog_author():
    denied = require_app_admin()
    if denied:
        return denied
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('user_id'), str) or not data['user_id'] or type(data.get('enabled')) is not bool:
        return jsonify({"error": "user_id と enabled（真偽値）が必要です"}), 400
    if not set_catalog_author(data['user_id'], data['enabled']):
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user_id": data['user_id'], "is_catalog_author": data['enabled']})
