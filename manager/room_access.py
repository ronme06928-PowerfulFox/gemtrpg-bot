"""HTTP/Socket共通のルーム認可ヘルパー。

権限の正本は DB 上の RoomMember（owner/gm/player）。membership が無いルーム/
ユーザー（移行期）は、暫定判定（Room.owner_id・在室・キャラ所有）へフォール
バックする。Phase 0 で固定した公開シグネチャ（resolve_room_role /
user_can_access_room / is_user_in_room / is_sid_in_room）は変更していない。

HTTP と Socket はこの共通境界だけを使い、権限ロジックを各所へ複製しない。
session['attribute'] や user_sids[].attribute は権限の正本にしない。
"""
from datetime import datetime

from extensions import db, user_sids
from models import Room, RoomMember

OWNER = "owner"
GM = "gm"
PLAYER = "player"

# GM相当（GM専用操作が可能）の role 集合。
GM_ROLES = frozenset({OWNER, GM})

# ロビー可視性。
VIS_HIDDEN = "hidden"
VIS_LISTED = "listed"
VIS_CLOSED = "closed"


def _get_room(room_name):
    if not room_name:
        return None
    return Room.query.filter_by(name=room_name).first()


def get_room_owner_id(room_name):
    if not room_name:
        return None
    room = Room.query.filter_by(name=room_name).first()
    return room.owner_id if room else None


def is_room_owner(user_id, room_name):
    if not user_id:
        return False
    return get_room_owner_id(room_name) == user_id


def is_user_in_room(user_id, room_name):
    """user_id がアクティブな Socket 接続で当該ルームに在室しているか。"""
    if not user_id or not room_name:
        return False
    for info in user_sids.values():
        if info.get("user_id") == user_id and info.get("room") == room_name:
            return True
    return False


def is_sid_in_room(sid, room_name):
    """Socketイベント用: 当該 SID が対象ルームへ参加済みか。"""
    if not sid or not room_name:
        return False
    return (user_sids.get(sid) or {}).get("room") == room_name


def owns_character_in_room(user_id, room_name):
    """room state 内に user_id 所有のキャラクターが居るか（再入室者の暫定判定）。"""
    if not user_id or not room_name:
        return False
    # 循環インポート回避のため遅延インポート。
    from manager.room_manager import get_room_state
    state = get_room_state(room_name) or {}
    for char in state.get("characters", []) or []:
        if isinstance(char, dict) and char.get("owner_id") == user_id:
            return True
    return False


def get_membership_role(user_id, room_name):
    """有効な RoomMember の role を返す（owner/gm/player）。無ければ None。"""
    if not user_id or not room_name:
        return None
    room = _get_room(room_name)
    if room is None:
        return None
    m = RoomMember.query.filter_by(room_id=room.id, user_id=user_id, revoked_at=None).first()
    return m.role if m else None


def resolve_room_role(user_id, room_name):
    """ルーム role を返す（owner / gm / player / None）。

    正本は RoomMember。membership が無い場合のみ移行期の暫定判定へフォール
    バックする（owner_id 一致→owner、在室/キャラ所有→player）。
    """
    role = get_membership_role(user_id, room_name)
    if role:
        return role
    # 移行期フォールバック（membership 未整備のルーム/ユーザー）。
    if is_room_owner(user_id, room_name):
        return OWNER
    if is_user_in_room(user_id, room_name) or owns_character_in_room(user_id, room_name):
        return PLAYER
    return None


def has_room_role(user_id, room_name, allowed_roles):
    """user_id の role が allowed_roles に含まれるか。"""
    return resolve_room_role(user_id, room_name) in allowed_roles


def sid_has_room_role(sid, room_name, allowed_roles):
    """Socketイベント用: SID が当該ルームに在室し、role が allowed_roles か。"""
    info = user_sids.get(sid) or {}
    if info.get("room") != room_name:
        return False
    return resolve_room_role(info.get("user_id"), room_name) in allowed_roles


def user_can_access_room(user_id, room_name):
    """参加者向けルーム状態の読み書きを許可してよいか。"""
    return resolve_room_role(user_id, room_name) is not None


# ---------------------------------------------------------------------------
# membership 管理（owner/gm 付与・解除、移譲、除名）。owner-only 等の権限
# チェックはルート層で行い、ここは整合性のある書き込みに徹する。
# ---------------------------------------------------------------------------

def ensure_membership(room_id, user_id, role, *, granted_by=None, commit=True):
    """有効 membership を作成または role 変更する（冪等）。"""
    if not user_id:
        return None
    now = datetime.utcnow()
    m = RoomMember.query.filter_by(room_id=room_id, user_id=user_id, revoked_at=None).first()
    if m is None:
        m = RoomMember(room_id=room_id, user_id=user_id, role=role,
                       joined_at=now, granted_by_user_id=granted_by)
        db.session.add(m)
    elif m.role != role:
        m.role = role
        m.updated_at = now
        m.granted_by_user_id = granted_by
    if commit:
        db.session.commit()
    return m


def ensure_join_membership(room_id, user_id, is_gm, *, commit=True):
    """入室時に membership を整える。owner は降格しない。player→gm の昇格のみ行う。"""
    if not user_id:
        return None
    m = RoomMember.query.filter_by(room_id=room_id, user_id=user_id, revoked_at=None).first()
    target = GM if is_gm else PLAYER
    now = datetime.utcnow()
    if m is None:
        m = RoomMember(room_id=room_id, user_id=user_id, role=target,
                       joined_at=now)
        db.session.add(m)
    elif m.role == OWNER:
        return m  # owner は維持
    elif is_gm and m.role == PLAYER:
        m.role = GM
        m.updated_at = now
    if commit:
        db.session.commit()
    return m


def ensure_join_membership_by_name(room_name, user_id, is_gm, *, commit=True):
    """ルーム名で入室 membership を整える（Socket join_room 用）。"""
    room = _get_room(room_name)
    if room is None:
        return None
    return ensure_join_membership(room.id, user_id, is_gm, commit=commit)


def count_owners(room_id):
    return RoomMember.query.filter_by(room_id=room_id, role=OWNER, revoked_at=None).count()


def set_room_role(room_name, target_user_id, role, *, granted_by=None):
    """対象ユーザーの role を設定する（gm 付与/解除等）。成功で membership を返す。"""
    room = _get_room(room_name)
    if room is None:
        return None
    return ensure_membership(room.id, target_user_id, role, granted_by=granted_by)


def revoke_membership(room_name, target_user_id, *, commit=True):
    """対象ユーザーの有効 membership を失効する（除名）。失効したら True。"""
    room = _get_room(room_name)
    if room is None:
        return False
    m = RoomMember.query.filter_by(room_id=room.id, user_id=target_user_id, revoked_at=None).first()
    if m is None:
        return False
    if m.role == OWNER and count_owners(room.id) <= 1:
        # 最後の owner は除名できない（先に移譲が必要）。
        raise ValueError("最後のオーナーは除名できません。先にオーナーを移譲してください")
    m.revoked_at = datetime.utcnow()
    if commit:
        db.session.commit()
    return True


def _lobby_role(user_id, room):
    """ロビー一覧用の軽量 role 解決（room state を読まない）。"""
    if user_id:
        m = RoomMember.query.filter_by(room_id=room.id, user_id=user_id, revoked_at=None).first()
        if m:
            return m.role
        if room.owner_id == user_id:
            return OWNER  # 移行期: membership未整備の owner
    return None


def build_lobby_cards(user_id):
    """未参加者にも安全なロビーカード一覧を返す。

    内部識別子（owner_id, join_code, ログ, キャラ, 画像URL 等）は含めない。
    hidden は非メンバーへ出さない。closed はカード表示するが新規参加不可。
    """
    cards = []
    for room in Room.query.order_by(Room.name).all():
        role = _lobby_role(user_id, room)
        is_member = role is not None
        vis = room.lobby_visibility or VIS_HIDDEN
        if vis == VIS_HIDDEN and not is_member:
            continue
        play_mode = "normal"
        if isinstance(room.data, dict):
            pm = str(room.data.get("play_mode") or "normal").strip().lower()
            play_mode = pm if pm in ("normal", "battle_only") else "normal"
        joinable = (not is_member) and (vis == VIS_LISTED)
        cards.append({
            "name": room.name,
            "play_mode": play_mode,
            "visibility": vis,
            "recruitment_status": room.recruitment_status,
            "description": room.description,
            "your_role": role,
            "is_member": is_member,
            "requires_code": bool(room.join_code_hash),
            "joinable": joinable,
        })
    return cards


def join_room_as_player(room_name, user_id, *, commit=True):
    """player membership を作成して参加させる（既に member ならそのまま）。"""
    room = _get_room(room_name)
    if room is None:
        return None
    existing = get_membership_role(user_id, room_name)
    if existing:
        return existing
    ensure_membership(room.id, user_id, PLAYER, commit=commit)
    return PLAYER


def transfer_owner(room_name, new_owner_id, *, acting_user_id=None, commit=True):
    """owner を new_owner へ移譲する。旧 owner は gm へ降格し、Room.owner_id も更新。"""
    room = _get_room(room_name)
    if room is None:
        return False
    now = datetime.utcnow()
    # 既存 owner を gm へ降格。
    owners = RoomMember.query.filter_by(room_id=room.id, role=OWNER, revoked_at=None).all()
    for o in owners:
        if o.user_id != new_owner_id:
            o.role = GM
            o.updated_at = now
            o.granted_by_user_id = acting_user_id
    # 新 owner の membership を owner に。
    ensure_membership(room.id, new_owner_id, OWNER, granted_by=acting_user_id, commit=False)
    # Room.owner_id も同一トランザクションで更新（移行期間の互換維持）。
    room.owner_id = new_owner_id
    if commit:
        db.session.commit()
    return True
