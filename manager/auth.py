import os
import re
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

from models import Room


PLAYER_ATTRIBUTE = "Player"
GM_ATTRIBUTE = "GM"


def normalize_entry_role(value):
    role = str(value or PLAYER_ATTRIBUTE).strip().lower()
    if role in {"gm", "game_master", "gamemaster"}:
        return GM_ATTRIBUTE
    return PLAYER_ATTRIBUTE


def is_valid_gm_pin(value):
    return bool(re.fullmatch(r"\d{4}", str(value or "").strip()))


def is_valid_master_key(value):
    return bool(re.fullmatch(r"\d{8}", str(value or "").strip()))


def hash_gm_pin(pin):
    pin_text = str(pin or "").strip()
    if not is_valid_gm_pin(pin_text):
        raise ValueError("GM PIN must be exactly 4 digits.")
    return generate_password_hash(pin_text)


def verify_gm_pin(room, pin):
    if not room or not getattr(room, "gm_pin_hash", None):
        return False
    pin_text = str(pin or "").strip()
    if not is_valid_gm_pin(pin_text):
        return False
    return check_password_hash(room.gm_pin_hash, pin_text)


def verify_master_key(key):
    configured = str(os.environ.get("GM_MASTER_KEY") or "").strip()
    provided = str(key or "").strip()
    if not is_valid_master_key(configured) or not is_valid_master_key(provided):
        return False
    return secrets.compare_digest(configured, provided)


def verify_room_gm_key(room, key):
    return verify_gm_pin(room, key) or verify_master_key(key)


def resolve_room_attribute(room_name, requested_role=PLAYER_ATTRIBUTE, gm_key=None):
    role = normalize_entry_role(requested_role)
    if role != GM_ATTRIBUTE:
        return PLAYER_ATTRIBUTE

    room = Room.query.filter_by(name=room_name).first()
    if not room:
        return None
    if verify_room_gm_key(room, gm_key):
        return GM_ATTRIBUTE
    return None

