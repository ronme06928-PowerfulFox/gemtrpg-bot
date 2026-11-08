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

def update_all_data():
    """
    Sheetsのデータ（アイテム、輝化スキル、特殊パッシブ、召喚テンプレート）を更新（用語・バフ・スキルはDBが正本）

    Returns:
        bool: 全ての更新が成功したかどうか
    """
    print("\n" + "="*60)
    print("全データ更新を開始...")
    print("="*60 + "\n")

    success = True

    # 1. アイテムデータ更新
    print("【1/4】アイテムデータを更新中...")
    try:
        from manager.items.loader import item_loader
        items = item_loader.refresh()
        if items:
            print(f"✅ アイテムデータの更新に成功しました ({len(items)}件)\n")
        else:
            print("❌ アイテムデータの更新に失敗しました\n")
            success = False
    except Exception as e:
        print(f"❌ アイテムデータ更新エラー: {e}\n")
        success = False

    # 2. 輝化スキルデータ更新
    print("【2/4】輝化スキルデータを更新中...")
    try:
        from manager.radiance.loader import radiance_loader
        radiance_skills = radiance_loader.refresh()
        if radiance_skills:
            print(f"✅ 輝化スキルデータの更新に成功しました ({len(radiance_skills)}件)\n")
        else:
            print("❌ 輝化スキルデータの更新に失敗しました\n")
            success = False
    except Exception as e:
        print(f"❌ 輝化スキルデータ更新エラー: {e}\n")
        success = False

    # 3. 特殊パッシブデータ更新
    print("【3/4】特殊パッシブデータを更新中...")
    try:
        from manager.passives.loader import passive_loader
        passives = passive_loader.refresh()
        if passives:
            print(f"✅ 特殊パッシブデータの更新に成功しました ({len(passives)}件)\n")
        else:
            print("❌ 特殊パッシブデータの更新に失敗しました\n")
            success = False
    except Exception as e:
        print(f"❌ 特殊パッシブデータ更新エラー: {e}\n")
        success = False

    # 4. 召喚テンプレート更新
    print("【4/4】召喚テンプレートを更新中...")
    try:
        from manager.summons.loader import refresh_summon_templates
        summon_templates = refresh_summon_templates()
        if summon_templates:
            print(f"✅ 召喚テンプレートの更新に成功しました ({len(summon_templates)}件)\n")
        else:
            print("❌ 召喚テンプレートの更新に失敗しました\n")
            success = False
    except Exception as e:
        print(f"❌ 召喚テンプレート更新エラー: {e}\n")
        success = False

    print("="*60)
    if success:
        print("✅ 全データの更新が完了しました")
    else:
        print("⚠️  一部のデータ更新に失敗しました")
    print("="*60 + "\n")

    return success

# データベースとキャッシュの初期化を行う関数
def init_app_data(create_db_tables=True):
        # 1. DBテーブル作成
        if create_db_tables:
            db.create_all()
            print("[OK] Database tables checked/created.")

        print("--- Initializing Data ---")

        # 3. アイテムデータの読み込み
        try:
            from manager.items.loader import item_loader
            item_loader.load_items()
            print("[OK] Item data initialized.")
        except Exception as e:
            print(f"[WARNING] Item data initialization warning: {e}")

        # 4. 輝化スキルデータの読み込み
        try:
            from manager.radiance.loader import radiance_loader
            radiance_loader.load_skills()
            print("[OK] Radiance skill data initialized.")
        except Exception as e:
            print(f"[WARNING] Radiance skill data initialization warning: {e}")

        # 5. 特殊パッシブデータの読み込み
        try:
            from manager.passives.loader import passive_loader
            passive_loader.load_passives()
            print("[OK] Passive data initialized.")
        except Exception as e:
            print(f"[WARNING] Passive data initialization warning: {e}")

        # 6. バフ図鑑データの読み込み
        try:
            from manager.catalog.repository import seed_kind_if_empty, load_kind_into_memory
            seed_kind_if_empty('buff')
            load_kind_into_memory('buff')
            print("[OK] Buff catalog data initialized.")
        except Exception as e:
            print(f"[WARNING] Buff catalog data initialization warning: {e}")

        # 7. 用語辞書データの読み込み
        try:
            from manager.catalog.repository import seed_kind_if_empty, load_kind_into_memory
            seed_kind_if_empty('glossary')
            load_kind_into_memory('glossary')
            print("[OK] Glossary data initialized.")
        except Exception as e:
            print(f"[WARNING] Glossary data initialization warning: {e}")

        # スキルの検査に使うバフ・用語のあとで読む。
        seed_kind_if_empty('skill')
        load_kind_into_memory('skill')
        print("[OK] Skill data initialized from DB.")

        # 8. 召喚テンプレートデータの読み込み
        try:
            from manager.summons.loader import load_summon_templates
            templates = load_summon_templates()
            print(f"[OK] Summon template data initialized. ({len(templates)} entries)")
        except Exception as e:
            print(f"[WARNING] Summon template data initialization warning: {e}")
