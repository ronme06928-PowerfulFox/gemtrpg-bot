# manager/data_manager.py
import gspread
import json
import os
import sys
from dotenv import load_dotenv

# ★ extensions から db と all_skill_data をインポートするように変更
from extensions import db, all_skill_data
from models import Room

# .env ファイルをロード
load_dotenv()

# --- 設定 ---
# 環境変数から取得。なければデフォルトのファイル名を使用
GOOGLE_CREDENTIALS_SOURCE = os.environ.get('GOOGLE_CREDENTIALS_JSON', 'gemtrpgdicebot-ee5a4f0c50df.json')
SPREADSHEET_NAME = 'ジェムリアTRPG_スキル一覧'
SKILL_CACHE_FILE = 'skills_cache.json'

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
        with open(SKILL_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_skill_data, f, ensure_ascii=False, indent=2)
        print(f"[OK] {total_skills_processed} 件のスキルを保存しました。")
        return True
    except Exception as e:
        print(f"[ERROR] キャッシュ保存エラー: {e}")
        return False

def load_skills_from_cache():
    if not os.path.exists(SKILL_CACHE_FILE):
        print(f"Cache not found.")
        return None
    try:
        with open(SKILL_CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

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
        # global all_skill_data  <-- 不要なので削除（all_skill_data自体を書き換えないため）
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