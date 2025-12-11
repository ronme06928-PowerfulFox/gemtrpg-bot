# manager/user_manager.py
from extensions import db, active_room_states
from models import User, Room
from datetime import datetime

def upsert_user(user_id, name):
    """ログイン時にユーザー情報を保存・更新する"""
    if not user_id: return
    user = User.query.get(user_id)
    if not user:
        user = User(id=user_id, name=name)
        db.session.add(user)
    else:
        user.name = name # 名前が変わっていれば更新
        user.last_login = datetime.utcnow()
    db.session.commit()

def get_all_users():
    """全ユーザーのリストを返す（最終ログイン降順）"""
    users = User.query.order_by(User.last_login.desc()).all()
    return [{
        "id": u.id,
        "name": u.name,
        "last_login": u.last_login.strftime('%Y-%m-%d %H:%M:%S')
    } for u in users]

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