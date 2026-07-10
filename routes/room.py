"""ルーム操作・メンバー権限・参加コード系の HTTP ハンドラ。

list_rooms / load_room / create_room / delete_room / save_room /
enter_room / leave_room_context / get_room_users / room_grant_gm /
room_revoke_gm / room_remove_member / room_transfer_owner /
join_room_by_code / room_set_join_code / room_clear_join_code /
room_update_settings を担う。
"""

from flask import Blueprint, Response, jsonify, request, session

from extensions import db, active_room_states
from models import Room, User
from manager.auth import (
    GM_ATTRIBUTE,
    PLAYER_ATTRIBUTE,
    hash_gm_pin,
    is_valid_gm_pin,
    resolve_room_attribute,
    verify_room_gm_key,
)
from manager.room_manager import get_room_state
from manager.data_manager import save_room_to_db, delete_room_from_db
from manager.user_manager import is_user_management_admin
from manager.utils import session_required

room_bp = Blueprint('room', __name__)


@room_bp.route('/api/enter_room', methods=['POST'])
@session_required
def enter_room():
    data = request.get_json(silent=True) or {}
    room_name = str(data.get('room_name') or '').strip()
    gm_key = data.get('gm_pin') or data.get('gm_key') or ''
    user_id = session.get('user_id')

    if not room_name:
        return jsonify({"error": "Room name required"}), 400
    if not Room.query.filter_by(name=room_name).first():
        return jsonify({"error": "Room not found"}), 404

    from manager.room_access import (
        resolve_room_role, ensure_join_membership_by_name, GM_ROLES,
    )

    # resolve_room_role は membership 正本＋移行期フォールバック(owner_id/在室/
    # キャラ所有)。既存ルームの owner がロックアウトされないようにする。
    role = resolve_room_role(user_id, room_name)
    if role is None:
        # 非メンバーは原則入室不可（参加コードで参加してから）。ただし移行期は
        # 正しい GM PIN を gm membership の取得手段として認める。
        if gm_key and resolve_room_attribute(room_name, 'GM', gm_key) == GM_ATTRIBUTE:
            ensure_join_membership_by_name(room_name, user_id, True)
            role = 'gm'
        else:
            return jsonify({"error": "このルームに参加していません。参加コードで参加してください"}), 403

    attribute = GM_ATTRIBUTE if role in GM_ROLES else PLAYER_ATTRIBUTE
    # player メンバーが GM PIN を入力した場合は GM へ昇格（移行期の取得手段）。
    if attribute != GM_ATTRIBUTE and gm_key:
        if resolve_room_attribute(room_name, 'GM', gm_key) == GM_ATTRIBUTE:
            ensure_join_membership_by_name(room_name, user_id, True)
            attribute = GM_ATTRIBUTE

    session['attribute'] = attribute
    # 入室済みを session に記録（/load_room の判定に使う）。membership がある
    # 場合のみここに到達するため、entered_rooms は安全な参加者シグナルになる。
    entered = set(session.get('entered_rooms') or [])
    entered.add(room_name)
    session['entered_rooms'] = list(entered)
    return jsonify({
        "message": "Room entry accepted",
        "room_name": room_name,
        "attribute": attribute,
    })


@room_bp.route('/api/leave_room_context', methods=['POST'])
@session_required
def leave_room_context():
    # Room GM status is scoped to the room. Returning to the lobby must not
    # leave the user with GM-like powers in app-wide management surfaces.
    session['attribute'] = PLAYER_ATTRIBUTE
    return jsonify({"message": "Room context cleared", "attribute": PLAYER_ATTRIBUTE})


@room_bp.route('/list_rooms', methods=['GET'])
@session_required
def list_rooms():
    """安全な公開ロビーDTOを返す（未参加者に内部識別子を出さない）。"""
    from manager.room_access import build_lobby_cards
    user_id = session.get('user_id')
    return jsonify({
        'rooms': build_lobby_cards(user_id),
        'current_user_id': user_id,
        'is_app_admin': is_user_management_admin(user_id),
    })


@room_bp.route('/load_room', methods=['GET'])
@session_required
def load_room():
    room_name = request.args.get('name')
    if not room_name:
        return jsonify({"error": "Room name required"}), 400
    # 参加者向けルーム状態は、入室済み（enter_room）か owner/参加者のみ返す。
    # mobile は開発停止につき考慮不要（/mobile は停止済み）。
    from manager.room_access import user_can_access_room
    entered = session.get('entered_rooms') or []
    if room_name not in entered and not user_can_access_room(session.get('user_id'), room_name):
        return jsonify({"error": "このルームにアクセスする権限がありません"}), 403
    state = get_room_state(room_name)
    return jsonify(state)


@room_bp.route('/create_room', methods=['POST'])
@session_required
def create_room():
    data = request.get_json(silent=True) or {}
    room_name = str(data.get('room_name') or '').strip()
    gm_pin = str(data.get('gm_pin') or '').strip()
    if not room_name:
        return jsonify({"error": "No name"}), 400
    if not is_valid_gm_pin(gm_pin):
        return jsonify({"error": "GM PINは4桁の数字で入力してください"}), 400

    # DBに存在するかチェック
    if Room.query.filter_by(name=room_name).first():
        return jsonify({"error": "Room exists"}), 409

    play_mode = str(data.get('play_mode') or 'normal').strip().lower()
    if play_mode not in ('normal', 'battle_only'):
        play_mode = 'normal'

    new_state = {
        "characters": [],
        "timeline": [],
        "round": 0,
        "logs": [],
        "play_mode": play_mode,
    }
    if play_mode == 'battle_only':
        new_state["battle_only"] = {"status": "lobby", "ally_entries": [], "enemy_entries": []}
    active_room_states[room_name] = new_state

    # ▼▼▼ 修正: Room作成時に owner_id を保存 ▼▼▼
    # save_room_to_db はデータ保存用なので、ここでは Roomモデルを直接作って owner_id を入れる
    new_room = Room(
        name=room_name,
        data=new_state,
        owner_id=session.get('user_id'),
        gm_pin_hash=hash_gm_pin(gm_pin),
    )
    db.session.add(new_room)
    db.session.flush()  # new_room.id を確定させ、同一トランザクションで owner membership を作る
    from manager.room_access import ensure_membership, OWNER
    ensure_membership(new_room.id, session.get('user_id'), OWNER,
                      granted_by=session.get('user_id'), commit=False)
    db.session.commit()
    session['attribute'] = GM_ATTRIBUTE
    # ▲▲▲ 修正ここまで ▲▲▲

    normalized_state = get_room_state(room_name)
    return jsonify({"message": "Created", "state": normalized_state, "attribute": GM_ATTRIBUTE}), 201


@room_bp.route('/delete_room', methods=['POST'])
@session_required
def delete_room():
    """ルーム削除 - オーナーまたはGMのみ許可"""
    data = request.get_json(silent=True) or {}
    room_name = data.get('room_name')
    gm_key = data.get('gm_pin') or data.get('gm_key') or ''

    # ルームのオーナーを取得
    room = Room.query.filter_by(name=room_name).first()
    if not room:
        return jsonify({"error": "Room not found"}), 404

    # ルーム削除はロビー操作のため、セッション属性ではなくGM PIN/マスターキーで確認する。
    if not verify_room_gm_key(room, gm_key):
        return jsonify({"error": "GM PINまたはマスターキーが正しくありません"}), 403

    # DB削除の前に保留中の自動保存を破棄しメモリからも除去する。
    # 削除後にデバウンスのフラッシュが走ってルームを復活させる事故を防ぐ。
    from manager.room_manager import discard_pending_save
    discard_pending_save(room_name)
    active_room_states.pop(room_name, None)

    if delete_room_from_db(room_name):
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Delete failed"}), 500


@room_bp.route('/save_room', methods=['POST'])
@session_required
def save_room_route():
    data = request.get_json(silent=True) or {}
    room_name = data.get('room_name')
    state = data.get('state')
    if not room_name:
        return jsonify({"error": "Room name required"}), 400
    # ルーム全状態の上書きは、当該ルームの owner か在室参加者に限定する。
    # （無認可の任意ルーム上書きを塞ぐ。判定は共通の room_access へ集約）
    from manager.room_access import user_can_access_room
    if not user_can_access_room(session.get('user_id'), room_name):
        return jsonify({"error": "このルームを更新する権限がありません"}), 403
    active_room_states[room_name] = state
    save_room_to_db(room_name, state)
    return jsonify({"message": "Saved"})


@room_bp.route('/api/room/export_logs', methods=['GET'])
@session_required
def room_export_logs():
    room_name = str(request.args.get('room_name') or request.args.get('room') or '').strip()
    export_format = str(request.args.get('format') or 'json').strip().lower()
    if not room_name:
        return jsonify({"error": "room_name が必要です"}), 400
    if export_format not in ('json', 'text'):
        return jsonify({"error": "format は json または text を指定してください"}), 400

    from manager.room_access import has_room_role, GM_ROLES
    if not has_room_role(session.get('user_id'), room_name, GM_ROLES):
        return jsonify({"error": "GM権限が必要です"}), 403

    state = get_room_state(room_name)
    if not isinstance(state, dict):
        return jsonify({"error": "Room not found"}), 404

    from manager.log_archive import build_room_log_export
    exported = build_room_log_export(room_name, state.get('logs', []), export_format)
    response = Response(exported['content'], content_type=exported['content_type'])
    response.headers['Content-Disposition'] = f'attachment; filename="{exported["filename"]}"'
    response.headers['X-Log-Count'] = str(exported.get('count', 0))
    return response


# ---- ルームメンバー管理（owner専用）----

def _require_room_owner(room_name):
    from manager.room_access import has_room_role, OWNER
    if not has_room_role(session.get('user_id'), room_name, {OWNER}):
        return jsonify({"error": "オーナー権限が必要です"}), 403
    return None


def _sync_room_member_session(room_name, target_user_id):
    """role変更を既存Socket(user_sids)へ反映する（再ログイン不要。best-effort）。"""
    from manager.room_access import resolve_room_role, GM_ROLES
    from extensions import user_sids
    role = resolve_room_role(target_user_id, room_name)
    attribute = GM_ATTRIBUTE if role in GM_ROLES else PLAYER_ATTRIBUTE
    for info in user_sids.values():
        if info.get('user_id') == target_user_id and info.get('room') == room_name:
            info['attribute'] = attribute
    try:
        from manager.room_manager import broadcast_user_list
        broadcast_user_list(room_name)
    except Exception:
        pass


def _room_member_request():
    data = request.get_json(silent=True) or {}
    room_name = str(data.get('room_name') or '').strip()
    target_user_id = str(data.get('user_id') or '').strip()
    return room_name, target_user_id


@room_bp.route('/api/room/grant_gm', methods=['POST'])
@session_required
def room_grant_gm():
    from manager.room_access import set_room_role, GM
    room_name, target_user_id = _room_member_request()
    if not room_name or not target_user_id:
        return jsonify({"error": "room_name と user_id が必要です"}), 400
    denied = _require_room_owner(room_name)
    if denied:
        return denied
    if User.query.get(target_user_id) is None:
        return jsonify({"error": "User not found"}), 404
    set_room_role(room_name, target_user_id, GM, granted_by=session.get('user_id'))
    _sync_room_member_session(room_name, target_user_id)
    return jsonify({"message": "GMを付与しました", "user_id": target_user_id, "role": GM})


@room_bp.route('/api/room/revoke_gm', methods=['POST'])
@session_required
def room_revoke_gm():
    from manager.room_access import set_room_role, PLAYER
    room_name, target_user_id = _room_member_request()
    if not room_name or not target_user_id:
        return jsonify({"error": "room_name と user_id が必要です"}), 400
    denied = _require_room_owner(room_name)
    if denied:
        return denied
    set_room_role(room_name, target_user_id, PLAYER, granted_by=session.get('user_id'))
    _sync_room_member_session(room_name, target_user_id)
    return jsonify({"message": "GMを解除しました", "user_id": target_user_id, "role": PLAYER})


@room_bp.route('/api/room/remove_member', methods=['POST'])
@session_required
def room_remove_member():
    from manager.room_access import revoke_membership
    room_name, target_user_id = _room_member_request()
    if not room_name or not target_user_id:
        return jsonify({"error": "room_name と user_id が必要です"}), 400
    denied = _require_room_owner(room_name)
    if denied:
        return denied
    try:
        ok = revoke_membership(room_name, target_user_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not ok:
        return jsonify({"error": "メンバーが見つかりません"}), 404
    _sync_room_member_session(room_name, target_user_id)
    return jsonify({"message": "メンバーを除名しました", "user_id": target_user_id})


@room_bp.route('/api/room/transfer_owner', methods=['POST'])
@session_required
def room_transfer_owner():
    from manager.room_access import transfer_owner
    room_name, target_user_id = _room_member_request()
    if not room_name or not target_user_id:
        return jsonify({"error": "room_name と user_id が必要です"}), 400
    denied = _require_room_owner(room_name)
    if denied:
        return denied
    if User.query.get(target_user_id) is None:
        return jsonify({"error": "User not found"}), 404
    if not transfer_owner(room_name, target_user_id, acting_user_id=session.get('user_id')):
        return jsonify({"error": "Room not found"}), 404
    _sync_room_member_session(room_name, target_user_id)
    _sync_room_member_session(room_name, session.get('user_id'))
    return jsonify({"message": "オーナーを移譲しました", "user_id": target_user_id})


# ---- 参加コード・ロビー（Phase 6）----

@room_bp.route('/api/join_room_by_code', methods=['POST'])
@session_required
def join_room_by_code():
    """参加コードでルームに参加する（成功時のみ player membership を作成）。"""
    from manager import join_code
    from manager.room_access import (
        get_membership_role, join_room_as_player, VIS_LISTED,
    )
    from manager.auth_rate_limit import join_code_limiter
    data = request.get_json(silent=True) or {}
    room_name = str(data.get('room_name') or '').strip()
    code = str(data.get('join_code') or data.get('code') or '').strip()
    user_id = session.get('user_id')

    room = Room.query.filter_by(name=room_name).first()
    if room is None:
        return jsonify({"error": "Room not found"}), 404

    # 既メンバーはコード不要で再入室できる。
    existing = get_membership_role(user_id, room_name)
    if existing:
        return jsonify({"message": "既に参加済みです", "role": existing, "room_name": room_name})

    if (room.lobby_visibility or 'hidden') != VIS_LISTED:
        return jsonify({"error": "このルームは新規参加を受け付けていません"}), 403

    if join_code.has_join_code(room_name):
        key = f"{room_name}:{user_id}"
        if not join_code_limiter.is_allowed(key):
            return jsonify({"error": "試行回数が多すぎます。しばらくしてからお試しください"}), 429
        if not join_code.verify_join_code(room_name, code):
            join_code_limiter.record_failure(key)
            return jsonify({"error": "参加コードが正しくありません"}), 403
        join_code_limiter.reset(key)
    # listed でコード未設定なら公開参加を許可する。

    role = join_room_as_player(room_name, user_id)
    return jsonify({"message": "ルームに参加しました", "role": role, "room_name": room_name})


@room_bp.route('/api/room/set_join_code', methods=['POST'])
@session_required
def room_set_join_code():
    """参加コードを設定する（owner専用）。

    payload に join_code があればオーナー指定値（4桁PIN等）を使う。無ければ自動生成。
    """
    from manager import join_code
    data = request.get_json(silent=True) or {}
    room_name = str(data.get('room_name') or '').strip()
    requested = data.get('join_code')
    if not room_name:
        return jsonify({"error": "room_name が必要です"}), 400
    denied = _require_room_owner(room_name)
    if denied:
        return denied
    try:
        # 空文字の指定は「自動生成」扱いにせず誤入力として弾く。未指定(None)のみ自動生成。
        code = join_code.set_join_code(room_name, requested if requested is not None else None)
    except join_code.JoinCodeError as e:
        return jsonify({"error": str(e)}), 400
    if code is None:
        return jsonify({"error": "Room not found"}), 404
    return jsonify({"message": "参加コードを設定しました", "join_code": code, "room_name": room_name})


@room_bp.route('/api/room/clear_join_code', methods=['POST'])
@session_required
def room_clear_join_code():
    """参加コードを失効する（owner専用）。"""
    from manager import join_code
    room_name, _ = _room_member_request()
    if not room_name:
        return jsonify({"error": "room_name が必要です"}), 400
    denied = _require_room_owner(room_name)
    if denied:
        return denied
    if not join_code.clear_join_code(room_name):
        return jsonify({"error": "Room not found"}), 404
    return jsonify({"message": "参加コードを失効しました", "room_name": room_name})


@room_bp.route('/api/room/update_settings', methods=['POST'])
@session_required
def room_update_settings():
    """ルーム設定を更新する。owner: visibility/recruitment/description、gm: recruitment のみ。"""
    from manager.room_access import has_room_role, OWNER, GM_ROLES, VIS_HIDDEN, VIS_LISTED, VIS_CLOSED
    data = request.get_json(silent=True) or {}
    room_name = str(data.get('room_name') or '').strip()
    if not room_name:
        return jsonify({"error": "room_name が必要です"}), 400
    room = Room.query.filter_by(name=room_name).first()
    if room is None:
        return jsonify({"error": "Room not found"}), 404

    user_id = session.get('user_id')
    is_owner = has_room_role(user_id, room_name, {OWNER})
    is_gm = has_room_role(user_id, room_name, GM_ROLES)
    if not is_gm:
        return jsonify({"error": "GM権限が必要です"}), 403

    # gm は募集状態のみ編集可。owner はそれに加え可視性・説明を編集可。
    if 'recruitment_status' in data:
        room.recruitment_status = (str(data.get('recruitment_status') or '').strip() or None)
    if is_owner:
        if 'description' in data:
            room.description = (str(data.get('description') or '').strip() or None)
        if 'lobby_visibility' in data:
            vis = str(data.get('lobby_visibility') or '').strip().lower()
            if vis not in (VIS_HIDDEN, VIS_LISTED, VIS_CLOSED):
                return jsonify({"error": "不正な可視性です"}), 400
            room.lobby_visibility = vis
    elif ('description' in data) or ('lobby_visibility' in data):
        return jsonify({"error": "可視性・説明の変更はオーナーのみです"}), 403

    db.session.commit()
    return jsonify({
        "message": "ルーム設定を更新しました",
        "room_name": room_name,
        "lobby_visibility": room.lobby_visibility,
        "recruitment_status": room.recruitment_status,
        "description": room.description,
    })


@room_bp.route('/api/get_room_users', methods=['GET'])
@session_required
def get_room_users():
    """指定されたルームに参加しているユーザーの一覧を取得"""
    from extensions import user_sids
    room_name = request.args.get('room')
    if not room_name:
        return jsonify({"error": "Room name required"}), 400

    # user_sidsから該当ルームのユーザーを抽出
    room_users = []
    for sid, user_info in user_sids.items():
        if user_info.get('room') == room_name:
            room_users.append({
                'username': user_info.get('username'),
                'user_id': user_info.get('user_id'),
                'attribute': user_info.get('attribute')
            })

    return jsonify(room_users)
