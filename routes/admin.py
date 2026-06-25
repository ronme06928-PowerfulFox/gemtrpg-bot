"""アプリ管理者向けユーザー管理系の HTTP ハンドラ。

admin_get_users / admin_get_user_details / admin_delete_user /
admin_transfer_user / admin_set_user_management_admin を担う。
"""

from flask import Blueprint, jsonify, request, session

from manager.auth import verify_master_key
from manager.user_manager import (
    get_all_users,
    delete_user,
    transfer_ownership,
    get_user_owned_items,
    is_user_management_admin,
    set_user_management_admin,
)
from manager.utils import session_required
from routes.common import require_app_admin

admin_bp = Blueprint('admin', __name__)


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
    count = transfer_ownership(data['old_id'], data['new_id'])
    return jsonify({"message": f"Transferred {count} characters/rooms."})


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
