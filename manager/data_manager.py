# manager/data_manager.py
import gspread
import json
import os
import sys
from dotenv import load_dotenv

# ★ extensions から db と all_skill_data をインポートするように変更
from extensions import db, all_skill_data
from models import Room
from manager.cache_paths import (
    SKILLS_CACHE_FILE,
    LEGACY_SKILLS_CACHE_FILE,
    load_json_cache,
    save_json_cache,
)

# .env ファイルをロード
load_dotenv()

# --- 設定 ---
# 環境変数から取得。なければデフォルトのファイル名を使用
GOOGLE_CREDENTIALS_SOURCE = os.environ.get('GOOGLE_CREDENTIALS_JSON', 'gemtrpgdicebot-ee5a4f0c50df.json')
SPREADSHEET_NAME = 'ジェムリアTRPG_スキル一覧'
SKILL_CACHE_FILE = SKILLS_CACHE_FILE

TOC_WORKSHEET_NAME = '参照リスト'
SHEETS_TO_SKIP = ['参照リスト', 'スキル検索']


def get_gspread_client():
    """環境変数またはファイルパスから認証してクライアントを返す"""
    try:
        # もし環境変数がJSON文字列そのものなら（Render等での運用想定）
        if GOOGLE_CREDENTIALS_SOURCE.startswith('{'):
            creds_dict = json.loads(GOOGLE_CREDENTIALS_SOURCE)
            return gspread.service_account_from_dict(creds_dict)
        else:
            # ファイルパスとして扱う
            return gspread.service_account(filename=GOOGLE_CREDENTIALS_SOURCE)
    except Exception as e:
        print(f"[ERROR] Google Auth Error: {e}")
        return None

def fetch_and_save_sheets_data():
    print("Google Sheets への接続を開始...")
    gc = get_gspread_client()
    if not gc:
        return False

    try:
        sh = gc.open(SPREADSHEET_NAME)
        print(f"[OK] スプレッドシート '{SPREADSHEET_NAME}' への接続に成功。")
    except Exception as e:
        print(f"[ERROR] スプレッドシート接続エラー: {e}")
        return False

    try:
        toc_worksheet = sh.worksheet(TOC_WORKSHEET_NAME)
        worksheet_names = toc_worksheet.col_values(2)[2:13]
        sheets_to_process = [
            name for name in worksheet_names
            if name and name not in SHEETS_TO_SKIP
        ]
    except Exception as e:
        print(f"[ERROR] 目次読み込みエラー: {e}")
        return False

    # === ▼▼▼ 修正: グローバル変数を上書きせず、辞書の中身を更新する ▼▼▼
    # global all_skill_data  <-- 不要なので削除しても良いですが、念のため残すなら以下のように操作
    # all_skill_data = {}    <-- これがNG（参照が切れる）

    # 一時的な辞書にデータを集める
    temp_skill_data = {}
    total_skills_processed = 0

    for sheet_name in sheets_to_process:
        try:
            # ... (中略: データの取得ロジックはそのまま) ...
            print(f"    ... 処理中: '{sheet_name}'")
            worksheet = sh.worksheet(sheet_name)

            try:
                header_cell = worksheet.find("スキルID")
            except Exception:  # ← どのようなエラーでもスキップするように変更
                continue

            if not header_cell: continue
            header_row_index = header_cell.row
            data_rows = worksheet.get_all_values()[header_row_index:]

            for row in data_rows:
                try:
                    skill_id = row[0]
                    if not skill_id: continue

                    category = row[3]
                    effect_text = row[11]
                    tokki_json_str = row[12] if len(row) > 12 else ""

                    # カテゴリベースのタグ
                    tags_list = []
                    if category in ["防御", "回避"]:
                        tags_list.append("守備")
                        tags_list.append(category)
                    elif category in ["物理", "魔法"]:
                        tags_list.append("攻撃")
                    elif category == "補助":
                        # 後方互換: テキストから[即時発動]をパース
                        if "[即時発動]" in effect_text:
                            tags_list.append("即時発動")

                    # 特記処理JSONからタグを読み取り
                    tokki_data = {}
                    if tokki_json_str:
                        try:
                            tokki_data = json.loads(tokki_json_str)
                            # JSONに明示的なtagsがあればマージ
                            json_tags = tokki_data.get("tags", [])
                            for tag in json_tags:
                                if tag not in tags_list:
                                    tags_list.append(tag)
                        except json.JSONDecodeError:
                            pass  # JSONパース失敗は無視

                    # temp_skill_data に格納
                    temp_skill_data[skill_id] = {
                        'スキルID': skill_id,
                        'チャットパレット': row[1],
                        'デフォルト名称': row[2],
                        '分類': category,
                        '距離': row[4],
                        '属性': row[5],
                        '取得コスト': row[6],
                        '基礎威力': row[7],
                        'ダイス威力': row[8],
                        '使用時効果': row[9],
                        '特記': row[10],
                        '発動時効果': effect_text,
                        '特記処理': tokki_json_str,
                        'tags': tags_list,
                    }
                    total_skills_processed += 1
                except IndexError:
                    continue
        except Exception as e:
            print(f"[ERROR] タブ '{sheet_name}' エラー: {e}")

    # 最後に本物の all_skill_data を更新
    all_skill_data.clear()
    all_skill_data.update(temp_skill_data)
    # === ▲▲▲ 修正ここまで ▲▲▲

    try:
        save_json_cache(SKILL_CACHE_FILE, all_skill_data)
        print(f"[OK] {total_skills_processed} 件のスキルを保存しました。")
        return True
    except Exception as e:
        print(f"[ERROR] キャッシュ保存エラー: {e}")
        return False

def load_skills_from_cache():
    try:
        data = load_json_cache(SKILL_CACHE_FILE, legacy_paths=[LEGACY_SKILLS_CACHE_FILE])
        if not data:
            print("Cache not found.")
            return None

        # === ▼▼▼ 修正: 辞書の中身を更新する ▼▼▼
        all_skill_data.clear()
        all_skill_data.update(data)
        # === ▲▲▲ 修正ここまで ▲▲▲

        return all_skill_data
    except Exception as e:
        print(f"Cache load error: {e}")
        return None

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

def read_saved_rooms_with_owners():
    """DBから全ルームとオーナー情報を取得して返す"""
    try:
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

def save_room_to_db(room_name, room_state):
    """特定のルームをDBに保存（新規作成 or 更新）"""
    try:
        room = Room.query.filter_by(name=room_name).first()
        if room:
            room.data = room_state
            # ★ Explicitly mark as modified for JSON field changes
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(room, "data")
        else:
            new_room = Room(name=room_name, data=room_state)
            db.session.add(new_room)

        db.session.commit()
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
    全てのデータ（スキル、アイテム、輝化スキル、特殊パッシブ、バフ図鑑、用語辞書、召喚テンプレート）を更新

    Returns:
        bool: 全ての更新が成功したかどうか
    """
    print("\n" + "="*60)
    print("全データ更新を開始...")
    print("="*60 + "\n")

    success = True

    # 1. スキルデータ更新
    print("【1/7】スキルデータを更新中...")
    try:
        if fetch_and_save_sheets_data():
            print("✅ スキルデータの更新に成功しました\n")
        else:
            print("❌ スキルデータの更新に失敗しました\n")
            success = False
    except Exception as e:
        print(f"❌ スキルデータ更新エラー: {e}\n")
        success = False

    # 2. アイテムデータ更新
    print("【2/7】アイテムデータを更新中...")
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

    # 3. 輝化スキルデータ更新
    print("【3/7】輝化スキルデータを更新中...")
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

    # 4. 特殊パッシブデータ更新
    print("【4/7】特殊パッシブデータを更新中...")
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

    # 5. バフ図鑑データ更新 ★追加
    print("【5/7】バフ図鑑データを更新中...")
    try:
        from manager.buffs.loader import buff_catalog_loader
        buffs = buff_catalog_loader.refresh()
        if buffs:
            print(f"✅ バフ図鑑データの更新に成功しました ({len(buffs)}件)\n")
        else:
            print("❌ バフ図鑑データの更新に失敗しました\n")
            success = False
    except Exception as e:
        print(f"❌ バフ図鑑データ更新エラー: {e}\n")
        success = False

    # 6. 用語辞書データ更新
    print("【6/7】用語辞書データを更新中...")
    try:
        from manager.glossary.loader import glossary_catalog_loader
        terms = glossary_catalog_loader.refresh()
        if terms:
            print(f"✅ 用語辞書データの更新に成功しました ({len(terms)}件)\n")
        else:
            print("❌ 用語辞書データの更新に失敗しました\n")
            success = False
    except Exception as e:
        print(f"❌ 用語辞書データ更新エラー: {e}\n")
        success = False

    # 7. 召喚テンプレート更新
    print("【7/7】召喚テンプレートを更新中...")
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

if __name__ == '__main__':
    print("--- スキルデータの手動アップデートを開始 ---")
    # DBを扱うため、Flaskアプリコンテキストを作成して実行
    from app import app
    with app.app_context():
        if fetch_and_save_sheets_data():
            print("--- 正常に終了しました ---")
        else:
            print("--- エラーが発生しました ---")
            sys.exit(1)

# データベースとキャッシュの初期化を行う関数
def init_app_data():
        # 1. DBテーブル作成
        db.create_all()
        print("[OK] Database tables checked/created.")

        # 2. スキルデータの読み込み
        # global all_skill_data  <- 不要なので削除（all_skill_data自体を書き換えないため）
        print("--- Initializing Data ---")

        # ★修正: 直接 all_skill_data に代入せず、戻り値チェックだけ行う
        cached_data = load_skills_from_cache()

        if not cached_data:
            print("Cache not found or empty. Fetching from Google Sheets...")
            try:
                # スプレッドシート読み込み
                fetch_and_save_sheets_data()
                # 既に fetch_and_save_sheets_data 内で all_skill_data は更新されているため再ロードは不要
                # (load_skills_from_cache() を呼んでも良いが、必須ではない)
                print(f"[OK] Data loaded: {len(all_skill_data)} skills.")
            except Exception as e:
                print(f"[ERROR] Error during initial fetch: {e}")
        else:
            print(f"[OK] Data loaded from cache: {len(all_skill_data)} skills.")

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
            from manager.buffs.loader import buff_catalog_loader
            buff_catalog_loader.load_buffs()
            print("[OK] Buff catalog data initialized.")
        except Exception as e:
            print(f"[WARNING] Buff catalog data initialization warning: {e}")

        # 7. 用語辞書データの読み込み
        try:
            from manager.glossary.loader import glossary_catalog_loader
            glossary_catalog_loader.load_terms()
            print("[OK] Glossary data initialized.")
        except Exception as e:
            print(f"[WARNING] Glossary data initialization warning: {e}")

        # 8. 召喚テンプレートデータの読み込み
        try:
            from manager.summons.loader import load_summon_templates
            templates = load_summon_templates()
            print(f"[OK] Summon template data initialized. ({len(templates)} entries)")
        except Exception as e:
            print(f"[WARNING] Summon template data initialization warning: {e}")
