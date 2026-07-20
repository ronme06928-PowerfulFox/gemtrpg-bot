# manager/user_manager.py
from extensions import db, active_room_states
from models import User, Room
from datetime import datetime
import hashlib
import secrets
from werkzeug.security import check_password_hash, generate_password_hash


RECOVERY_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_recovery_code():
    """ユーザーが控える復旧コードを生成する。UUIDはユーザーに扱わせない。"""
    part1 = ''.join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(4))
    part2 = ''.join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(4))
    return f"GEM-{part1}-{part2}"


def generate_recovery_token():
    """ブラウザ保存用の長い復旧トークンを生成する。"""
    return secrets.token_urlsafe(32)


def _hash_recovery_token(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _normalize_recovery_code(code):
    return str(code or "").strip().upper()


def upsert_user(user_id, name, *, issue_recovery=False):
    """ログイン時にユーザー情報を保存・更新する"""
    if not user_id:
        return None
    user = User.query.get(user_id)
    recovery_code = None
    recovery_token = None
    if not user:
        user = User(id=user_id, name=name)
        db.session.add(user)
    else:
        user.name = name # 名前が変わっていれば更新
        user.last_login = datetime.utcnow()

    if issue_recovery and not getattr(user, "recovery_code_hash", None):
        recovery_code = generate_recovery_code()
        user.recovery_code_hash = generate_password_hash(_normalize_recovery_code(recovery_code))
        user.recovery_code_issued_at = datetime.utcnow()

    # 端末トークンは「未発行のユーザーへ一度だけ」発行する。
    # 以前はログイン確認(get_session_user)や再入場(entry)のたびに再発行しており、
    # クライアントに保存済みのトークンが毎回陳腐化していた。これを止めることで、
    # 既存ユーザーの保存済みトークンが安定して照合でき、移行アンカーとして使える。
    if issue_recovery and not getattr(user, "recovery_token_hash", None):
        recovery_token = generate_recovery_token()
        user.recovery_token_hash = _hash_recovery_token(recovery_token)

    db.session.commit()
    return {
        "user": user,
        "recovery_code": recovery_code,
        "recovery_token": recovery_token,
    }


def regenerate_user_recovery_code(user_id):
    """ログイン中ユーザー用に復旧コードを再発行する。古いコードは無効になる。"""
    user = User.query.get(user_id)
    if not user:
        return None
    recovery_code = generate_recovery_code()
    recovery_token = generate_recovery_token()
    user.recovery_code_hash = generate_password_hash(_normalize_recovery_code(recovery_code))
    user.recovery_token_hash = _hash_recovery_token(recovery_token)
    user.recovery_code_issued_at = datetime.utcnow()
    db.session.commit()
    return {
        "user": user,
        "recovery_code": recovery_code,
        "recovery_token": recovery_token,
    }


def recover_user_by_name_and_code(name, recovery_code):
    """名前と復旧コードでユーザーを復帰する。UUIDは入力させない。"""
    username = str(name or "").strip()
    code = _normalize_recovery_code(recovery_code)
    if not username or not code:
        return None
    users = User.query.filter_by(name=username).all()
    for user in users:
        code_hash = getattr(user, "recovery_code_hash", None)
        if code_hash and check_password_hash(code_hash, code):
            user.last_login = datetime.utcnow()
            recovery_token = generate_recovery_token()
            user.recovery_token_hash = _hash_recovery_token(recovery_token)
            db.session.commit()
            return {"user": user, "recovery_token": recovery_token}
    return None


def recover_user_by_local_token(user_id, recovery_token):
    """localStorageに保存した内部トークンでセッションを復帰する。"""
    if not user_id or not recovery_token:
        return None
    user = User.query.get(user_id)
    if not user or not getattr(user, "recovery_token_hash", None):
        return None
    if not secrets.compare_digest(user.recovery_token_hash, _hash_recovery_token(recovery_token)):
        return None
    user.last_login = datetime.utcnow()
    db.session.commit()
    return user

def get_all_users():
    """全ユーザーのリストを返す（最終ログイン降順）"""
    users = User.query.order_by(User.last_login.desc()).all()
    return [{
        "id": u.id,
        "name": u.name,
        "last_login": u.last_login.strftime('%Y-%m-%d %H:%M:%S'),
        "is_app_admin": bool(getattr(u, "is_app_admin", False)),
    } for u in users]

def is_user_management_admin(user_id):
    """ユーザー管理のアプリ管理権限を持つか返す。ルームGM権限とは分離する。"""
    if not user_id:
        return False
    try:
        # HTTP routes authenticated by session_required already loaded the
        # account from the database. Reuse that authoritative object rather
        # than trusting a value stored inside the browser session.
        from flask import g, has_request_context
        if has_request_context():
            authenticated_user = getattr(g, 'authenticated_user', None)
            if authenticated_user is not None and str(authenticated_user.id) == str(user_id):
                return bool(getattr(authenticated_user, 'is_app_admin', False))
    except RuntimeError:
        pass
    # Socket handlers do not pass through session_required. Resolve the
    # account from the database for every authorization decision so a socket
    # opened before an admin grant cannot retain obsolete privileges.
    user = db.session.get(User, user_id)
    return bool(user and getattr(user, "is_app_admin", False))

def set_user_management_admin(user_id, enabled):
    """指定ユーザーにユーザー管理権限を付与/解除する。"""
    user = User.query.get(user_id)
    if not user:
        return False
    user.is_app_admin = bool(enabled)
    db.session.commit()
    return True

def delete_user(user_id):
    """ユーザーを削除する（所有権はNoneになる）"""
    user = User.query.get(user_id)
    if user:
        # ルームの所有権を解除
        rooms = Room.query.filter_by(owner_id=user_id).all()
        for r in rooms:
            r.owner_id = None
        
        db.session.delete(user)
        db.session.commit()
        return True
    return False

def get_user_owned_items(user_id):
    """指定したユーザーが所有するルームとキャラクターのリストを返す"""
    # 1. 所有ルームの取得
    rooms = Room.query.filter_by(owner_id=user_id).all()
    room_list = [{"name": r.name} for r in rooms]
    
    # 2. 所有キャラクターの取得 (全ルームを走査)
    char_list = []
    all_rooms = Room.query.all()
    
    for r in all_rooms:
        # 稼働中の状態があればそれを優先、なければDBの保存データを使用
        state = active_room_states.get(r.name)
        if not state:
            state = r.data
            
        if state and 'characters' in state:
            for char in state['characters']:
                if char.get('owner_id') == user_id:
                    char_list.append({
                        "name": char.get('name', 'Unknown'),
                        "room": r.name
                    })
    
    return {
        "rooms": room_list,
        "characters": char_list
    }

def transfer_ownership(old_id, new_id):
    """
    指定したユーザー(old_id)の全所有権(ルーム・キャラ)を
    別のユーザー(new_id)に譲渡する
    """
    # 1. ルームの所有権移動
    rooms = Room.query.filter_by(owner_id=old_id).all()
    for r in rooms:
        r.owner_id = new_id
    
    # 2. キャラクターの所有権移動 (全ルームのJSONデータを走査)
    all_rooms = Room.query.all()
    updated_count = 0
    
    for r in all_rooms:
        # メモリ上で稼働中ならそちらを優先、なければDBデータ
        state = active_room_states.get(r.name, r.data)
        if not state: continue
        
        changed = False
        if 'characters' in state:
            for char in state['characters']:
                if char.get('owner_id') == old_id:
                    char['owner_id'] = new_id
                    # 表示用オーナー名も更新したいが、新名称が不明な場合もあるためIDのみ更新
                    # (必要なら new_name を引数に追加して char['owner'] も更新可)
                    changed = True
                    updated_count += 1
        
        if changed:
            # DBとメモリの両方を更新
            r.data = state 
            if r.name in active_room_states:
                active_room_states[r.name] = state
                
    db.session.commit()
    return updated_count
