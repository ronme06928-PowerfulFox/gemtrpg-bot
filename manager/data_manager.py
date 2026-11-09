# manager/data_manager.py
import logging
import os
import time
from dotenv import load_dotenv

# パフォーマンス計測（PERF_LOG=1 のときのみ DB 書込時間を出力）
_PERF_LOG = os.environ.get('PERF_LOG') == '1'

# ★ extensions から db と all_skill_data をインポートするように変更
from extensions import db, all_skill_data
from models import Room
from manager.cache_paths import (
    SKILLS_CACHE_FILE,
    load_json_cache,
)

# .env ファイルをロード
load_dotenv()

SKILL_CACHE_FILE = SKILLS_CACHE_FILE


def load_skills_from_cache():
    """シミュレーター等の単独ツール用。アプリ起動ではDBを読む。"""
    data = load_json_cache(SKILL_CACHE_FILE)
    if not data:
        return None
    all_skill_data.clear()
    all_skill_data.update(data)
    from manager.battle.system_skills import ensure_system_skills_registered
    ensure_system_skills_registered()
    return all_skill_data


# === ▼▼▼ DB対応: ルームの読み書き ▼▼▼ ===

def read_saved_rooms():
    """DBから全ルームを取得して辞書形式で返す"""
    try:
        rooms = Room.query.all()
        rooms_data = {}
        for r in rooms:
            # DBのJSONデータをそのまま辞書として展開
            rooms_data[r.name] = r.data
        return rooms_data
    except Exception as e:
        print(f"[ERROR] DB Read Error: {e}")
        return {}

def read_saved_room(room_name):
    """DBから単一ルームのデータのみを取得する（無ければNone）。

    get_room_state のキャッシュミス時に全ルームをロードしないための軽量版。
    """
    try:
        room = Room.query.filter_by(name=room_name).first()
        return room.data if room else None
    except Exception as e:
        print(f"[ERROR] DB Read Error ({room_name}): {e}")
        try:
            db.session.rollback()
        except Exception:
            pass
        return None

def _read_saved_rooms_with_owners_full():
    """全ルームの data(JSON) を丸ごとロードする従来実装（フォールバック用）。"""
    rooms = Room.query.all()
    rooms_list = []
    for r in rooms:
        state = r.data if isinstance(r.data, dict) else {}
        play_mode = str(state.get('play_mode', 'normal') or 'normal').strip().lower()
        if play_mode not in ('normal', 'battle_only'):
            play_mode = 'normal'

        rooms_list.append({
            'name': r.name,
            'owner_id': r.owner_id,
            'play_mode': play_mode,
            'battle_only_stage_id': None,
        })
    return rooms_list

def read_saved_rooms_with_owners():
    """DBから全ルームとオーナー情報を取得して返す（一覧表示用・軽量クエリ）。

    一覧では name / owner_id / play_mode しか使わないため、巨大な data(JSON)
    全体ではなく必要な値だけをDB側で抽出する。JSONパス抽出に対応しない
    バックエンドでは従来の全ロード方式へフォールバックする。
    """
    try:
        try:
            play_mode_expr = Room.data['play_mode'].as_string()
            rows = db.session.query(Room.name, Room.owner_id, play_mode_expr).all()
            rooms_list = []
            for name, owner_id, play_mode in rows:
                pm = str(play_mode or 'normal').strip().lower()
                if pm not in ('normal', 'battle_only'):
                    pm = 'normal'
                rooms_list.append({
                    'name': name,
                    'owner_id': owner_id,
                    'play_mode': pm,
                    'battle_only_stage_id': None,
                })
            return rooms_list
        except Exception as opt_err:
            # JSONパス抽出が使えない場合は従来の全ロードへフォールバック
            print(f"[WARN] light room query unavailable, fallback to full load: {opt_err}")
            try:
                db.session.rollback()
            except Exception:
                pass
            return _read_saved_rooms_with_owners_full()
    except Exception as e:
        import traceback
        print(f"[ERROR] DB Read Error: {e}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        # データベース接続エラーの場合、セッションをクリーンアップ
        try:
            db.session.rollback()
        except:
            pass
        return []

def save_room_to_db(room_name, room_state, update_only=False):
    """特定のルームをDBに保存（新規作成 or 更新）。

    update_only=True のときは既存ルームの更新のみ行い、存在しなければ作成しない。
    デバウンス自動保存が削除直後のルームを gm_pin_hash 等を欠落させたまま
    復活させる事故を防ぐために使う。
    """
    _t0 = time.perf_counter() if _PERF_LOG else None
    try:
        room = Room.query.filter_by(name=room_name).first()
        if room:
            room.data = room_state
            # ★ Explicitly mark as modified for JSON field changes
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(room, "data")
        elif update_only:
            return False
        else:
            new_room = Room(name=room_name, data=room_state)
            db.session.add(new_room)

        db.session.commit()
        if _t0 is not None:
            logging.info("[PERF] save_room_to_db %s %.0fms", room_name, (time.perf_counter() - _t0) * 1000.0)
        return True
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] DB Save Error ({room_name}): {e}")
        return False

def delete_room_from_db(room_name):
    """特定のルームをDBから削除"""
    try:
        room = Room.query.filter_by(name=room_name).first()
        if room:
            db.session.delete(room)
            db.session.commit()
            return True
        return False
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] DB Delete Error ({room_name}): {e}")
        return False

def init_app_data(create_db_tables=True):
    if create_db_tables:
        db.create_all()
    from manager.catalog.repository import seed_kind_if_empty, load_kind_into_memory
    for kind in ('glossary', 'buff', 'skill', 'item', 'passive', 'radiance', 'summon'):
        seed_kind_if_empty(kind)
        load_kind_into_memory(kind)
        print(f"[OK] {kind} data initialized from DB.")
