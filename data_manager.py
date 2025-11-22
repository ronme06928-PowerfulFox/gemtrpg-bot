import gspread
import json
import os
import sys
from dotenv import load_dotenv
from models import db, Room

# .env ファイルをロード
load_dotenv()

# --- 設定 ---
# 環境変数から取得。なければデフォルトのファイル名を使用
GOOGLE_CREDENTIALS_SOURCE = os.environ.get('GOOGLE_CREDENTIALS_JSON', 'gemtrpgdicebot-ee5a4f0c50df.json')
SPREADSHEET_NAME = 'ジェムリアTRPG_スキル一覧'
SKILL_CACHE_FILE = 'skills_cache.json'

TOC_WORKSHEET_NAME = '参照リスト'
SHEETS_TO_SKIP = ['参照リスト', 'スキル検索']

# --- グローバル変数 ---
all_skill_data = {}

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
        print(f"❌ Google Auth Error: {e}")
        return None

def fetch_and_save_sheets_data():
    print("Google Sheets への接続を開始...")
    gc = get_gspread_client()
    if not gc:
        return False

    try:
        sh = gc.open(SPREADSHEET_NAME)
        print(f"✅ スプレッドシート '{SPREADSHEET_NAME}' への接続に成功。")
    except Exception as e:
        print(f"❌ スプレッドシート接続エラー: {e}")
        return False

    try:
        toc_worksheet = sh.worksheet(TOC_WORKSHEET_NAME)
        worksheet_names = toc_worksheet.col_values(2)[2:13]
        sheets_to_process = [
            name for name in worksheet_names
            if name and name not in SHEETS_TO_SKIP
        ]
    except Exception as e:
        print(f"❌ 目次読み込みエラー: {e}")
        return False

    global all_skill_data
    all_skill_data = {}
    total_skills_processed = 0

    for sheet_name in sheets_to_process:
        try:
            print(f"    ... 処理中: '{sheet_name}'")
            worksheet = sh.worksheet(sheet_name)

            try:
                header_cell = worksheet.find("スキルID")
            except gspread.exceptions.CellNotFound:
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
                    tags_list = []

                    if category in ["防御", "回避"]:
                        tags_list.append("守備")
                        tags_list.append(category)
                    elif category in ["物理", "魔法"]:
                        tags_list.append("攻撃")
                    elif category == "補助":
                        if "[即時発動]" in effect_text:
                            tags_list.append("即時発動")

                    all_skill_data[skill_id] = {
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
                        '特記処理': row[12],
                        'tags': tags_list,
                    }
                    total_skills_processed += 1
                except IndexError:
                    continue
        except Exception as e:
            print(f"❌ タブ '{sheet_name}' エラー: {e}")

    try:
        with open(SKILL_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_skill_data, f, ensure_ascii=False, indent=2)
        print(f"✅ {total_skills_processed} 件のスキルを保存しました。")
        return True
    except Exception as e:
        print(f"❌ キャッシュ保存エラー: {e}")
        return False

def load_skills_from_cache():
    global all_skill_data
    if not os.path.exists(SKILL_CACHE_FILE):
        print(f"Cache not found.")
        return None
    try:
        with open(SKILL_CACHE_FILE, 'r', encoding='utf-8') as f:
            all_skill_data = json.load(f)
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
        print(f"❌ DB Read Error: {e}")
        return {}

def save_room_to_db(room_name, room_state):
    """特定のルームをDBに保存（新規作成 or 更新）"""
    try:
        room = Room.query.filter_by(name=room_name).first()
        if room:
            room.data = room_state
        else:
            new_room = Room(name=room_name, data=room_state)
            db.session.add(new_room)

        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"❌ DB Save Error ({room_name}): {e}")
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
        print(f"❌ DB Delete Error ({room_name}): {e}")
        return False

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