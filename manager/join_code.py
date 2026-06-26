"""Phase 6: ルーム参加コード（join code）の管理。

参加コードは GM PIN とは別の秘密値として扱う（同じ列・用途に流用しない）。
DB にはハッシュのみ保存し、実値は発行時のみ返す。
"""
from datetime import datetime

import secrets
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import Room

# 読み間違えにくい英数字（0/O/1/I/L を除外）。自動生成時に使う。
JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 6

# オーナーが自由に設定する場合の長さ制限（4桁PIN〜）。総当たりは
# join_code_limiter で律速する（GM PIN と同等の扱い）。
JOIN_CODE_MIN_LENGTH = 4
JOIN_CODE_MAX_LENGTH = 32


class JoinCodeError(ValueError):
    """参加コードの形式が不正。"""


def generate_join_code():
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


def _normalize(code):
    # 大文字小文字を無視して照合する（数字PINには影響しない）。
    return str(code or "").strip().upper()


def validate_join_code(code):
    """オーナー指定コードを検証して正規化値を返す。空白は不可。"""
    raw = str(code or "").strip()
    if not raw:
        raise JoinCodeError("参加コードを入力してください")
    if any(ch.isspace() for ch in raw):
        raise JoinCodeError("参加コードに空白は使えません")
    if len(raw) < JOIN_CODE_MIN_LENGTH:
        raise JoinCodeError(f"参加コードは{JOIN_CODE_MIN_LENGTH}文字以上で入力してください")
    if len(raw) > JOIN_CODE_MAX_LENGTH:
        raise JoinCodeError(f"参加コードは{JOIN_CODE_MAX_LENGTH}文字以下で入力してください")
    return raw


def _get_room(room_name):
    if not room_name:
        return None
    return Room.query.filter_by(name=room_name).first()


def set_join_code(room_name, code=None, *, commit=True):
    """参加コードを設定する。

    code を指定すればオーナーが決めた値（4桁PIN等）を使う。未指定なら自動生成。
    設定した実値を返す（呼び出し側が表示）。不正な指定は JoinCodeError。
    """
    room = _get_room(room_name)
    if room is None:
        return None
    if code is None:
        value = generate_join_code()
    else:
        value = validate_join_code(code)
    room.join_code_hash = generate_password_hash(_normalize(value))
    room.join_code_rotated_at = datetime.utcnow()
    if commit:
        db.session.commit()
    return value


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
