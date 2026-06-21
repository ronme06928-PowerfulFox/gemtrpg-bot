"""HTTP/Socket共通のルーム認可ヘルパー（Phase 0 暫定版）。

Phase 0時点では RoomMembership テーブルが無いため、暫定的に
- Room.owner_id（DB上のルーム作成者）
- アクティブな Socket 接続(user_sids)の在室情報
- room state 内のキャラクター owner_id
から参加可否・role を判定する。

Phase 5 で membership 正本へ差し替える際も、本モジュールの公開関数
シグネチャ（resolve_room_role / user_can_access_room / is_user_in_room /
is_sid_in_room）は変更しない。HTTP と Socket はこの共通境界だけを使い、
権限ロジックを各所へ複製しない。
"""
from extensions import user_sids
from models import Room

OWNER = "owner"
PLAYER = "player"


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


def resolve_room_role(user_id, room_name):
    """暫定のルーム role を返す（owner / player / None）。

    Phase 0 では gm/player の永続区別がまだ無いため、owner でない参加者は
    すべて player 扱いとする。Phase 5 で membership の role に置き換える。
    """
    if is_room_owner(user_id, room_name):
        return OWNER
    if is_user_in_room(user_id, room_name) or owns_character_in_room(user_id, room_name):
        return PLAYER
    return None


def user_can_access_room(user_id, room_name):
    """参加者向けルーム状態の読み書きを許可してよいか（暫定判定）。"""
    return resolve_room_role(user_id, room_name) is not None
