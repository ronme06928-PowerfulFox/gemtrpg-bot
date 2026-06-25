"""Phase 6: ルーム参加コード（join code）の管理。

参加コードは GM PIN とは別の秘密値として扱う（同じ列・用途に流用しない）。
DB にはハッシュのみ保存し、実値は発行時のみ返す。
"""
from datetime import datetime

import secrets
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import Room

# 読み間違えにくい英数字（0/O/1/I/L を除外）。
JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 6


def generate_join_code():
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


def _normalize(code):
    return str(code or "").strip().upper()


def _get_room(room_name):
    if not room_name:
        return None
    return Room.query.filter_by(name=room_name).first()


def set_join_code(room_name, *, commit=True):
    """参加コードを発行/再発行する。実値を返す（呼び出し側が一度だけ表示）。"""
    room = _get_room(room_name)
    if room is None:
        return None
    code = generate_join_code()
    room.join_code_hash = generate_password_hash(_normalize(code))
    room.join_code_rotated_at = datetime.utcnow()
    if commit:
        db.session.commit()
    return code


def clear_join_code(room_name, *, commit=True):
    """参加コードを失効する（以後コードでは参加不可に）。"""
    room = _get_room(room_name)
    if room is None:
        return False
    room.join_code_hash = None
    room.join_code_rotated_at = datetime.utcnow()
    if commit:
        db.session.commit()
    return True


def has_join_code(room_name):
    room = _get_room(room_name)
    return bool(room and room.join_code_hash)


def verify_join_code(room_name, code):
    room = _get_room(room_name)
    if room is None or not room.join_code_hash:
        return False
    return check_password_hash(room.join_code_hash, _normalize(code))
