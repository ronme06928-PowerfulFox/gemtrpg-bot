# manager/buffs/loader.py
"""
バフ図鑑データをCSVから読み込むローダー
"""

import csv
import json
import requests
from pathlib import Path

# バフ図鑑CSVのURL
BUFF_CATALOG_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTkulkkIx6AQEHBKJiAqnjyzEQX5itUVV3SDwi40sLmXeiVQbXvg0RmMS3-XLSwNo2YHsF3WybyHjMu/pub?gid=1708552572&single=true&output=csv"

# キャッシュファイルのパス
CACHE_FILE = Path(__file__).parent.parent.parent / 'buff_catalog_cache.json'


class BuffCatalogLoader:
    """バフ図鑑データのローダー"""

    def __init__(self):
        self.buffs = {}

    def fetch_from_csv(self):
        """
        CSVからバフ図鑑データを取得

        Returns:
            dict: バフ名をキーとしたバフデータ辞書
        """
        try:
            print(f"[INFO] バフ図鑑データを取得中: {BUFF_CATALOG_CSV_URL}")
            response = requests.get(BUFF_CATALOG_CSV_URL, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'

            lines = response.text.strip().split('\n')
            reader = csv.DictReader(lines)

            buffs = {}
            for row in reader:
                buff_id = row.get('バフID', '').strip()
                buff_name = row.get('バフ名称', '').strip()

                if not buff_id or not buff_name:
                    continue

                # ★ JSON定義を読み込み
                json_def_str = row.get('JSON定義', '').strip()
                effect = {}
                if json_def_str:
                    try:
                        effect = json.loads(json_def_str)
                    except json.JSONDecodeError as e:
                        print(f"[WARNING] バフ {buff_id} のJSON定義が不正: {e}")

                # ★ 持続ラウンドを読み込み
                duration_str = row.get('持続ラウンド', '1').strip()
                try:
                    default_duration = int(duration_str) if duration_str else 1
                except ValueError:
                    default_duration = 1

                # ★ バフIDをキーとして格納
                buffs[buff_id] = {
                    'id': buff_id,
                    'name': buff_name,
                    'description': row.get('バフ説明', '').strip(),
                    'flavor': row.get('フレーバーテキスト', '').strip(),
                    'effect': effect,
                    'default_duration': default_duration
                }

            print(f"[OK] バフ図鑑データを {len(buffs)} 件取得しました")
            return buffs

        except Exception as e:
            print(f"[ERROR] バフ図鑑データの取得に失敗: {e}")
            return {}

    def save_to_cache(self, buffs):
        """
        バフ図鑑データをキャッシュに保存

        Args:
            buffs (dict): バフデータ辞書
        """
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(buffs, f, ensure_ascii=False, indent=2)
            print(f"[OK] バフ図鑑データをキャッシュに保存しました: {CACHE_FILE}")
        except Exception as e:
            print(f"[ERROR] バフ図鑑データのキャッシュ保存に失敗: {e}")

    def load_from_cache(self):
        """
        キャッシュからバフ図鑑データを読み込み

        Returns:
            dict: バフデータ辞書、失敗時は空辞書
        """
        if not CACHE_FILE.exists():
            return {}

        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                buffs = json.load(f)
            print(f"[OK] キャッシュから {len(buffs)} 件のバフ図鑑データを読み込みました")
            return buffs
        except Exception as e:
            print(f"[ERROR] バフ図鑑キャッシュの読み込みに失敗: {e}")
            return {}

    def refresh(self):
        """
        CSVからデータを取得し、キャッシュを更新

        Returns:
            dict: 最新のバフデータ辞書
        """
        buffs = self.fetch_from_csv()
        if buffs:
            self.save_to_cache(buffs)
            self.buffs = buffs
        return buffs

    def load_buffs(self):
        """
        バフ図鑑データを読み込み（キャッシュ優先、なければフェッチ）

        Returns:
            dict: バフデータ辞書
        """
        # キャッシュから読み込み
        self.buffs = self.load_from_cache()

        # キャッシュがなければCSVから取得
        if not self.buffs:
            print("[INFO] キャッシュが見つかりません。CSVから取得します...")
            self.buffs = self.fetch_from_csv()
            if self.buffs:
                self.save_to_cache(self.buffs)

        return self.buffs

    def get_buff(self, buff_name):
        """
        バフ名からバフデータを取得

        Args:
            buff_name (str): バフ名

        Returns:
            dict: バフデータ、見つからない場合はNone
        """
        return self.buffs.get(buff_name)


# グローバルインスタンス
buff_catalog_loader = BuffCatalogLoader()
