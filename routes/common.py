"""Blueprint をまたいで共有する小さなガードヘルパー。"""

from flask import jsonify, session

from manager.user_manager import is_user_management_admin


def require_app_admin():
    """app admin でなければ 403 を返す。app admin なら None を返す。"""
    if not is_user_management_admin(session.get('user_id')):
        return jsonify({"error": "アプリ管理者権限が必要です"}), 403
    return None
