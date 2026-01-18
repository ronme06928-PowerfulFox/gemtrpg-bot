import requests
import csv
import json
from io import StringIO

# CSV公開URL
ITEMS_CSV_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTkulkkIx6AQEHBKJiAqnjyzEQX5itUVV3SDwi40sLmXeiVQbXvg0RmMS3-XLSwNo2YHsF3WybyHjMu/pub?gid=110236529&single=true&output=csv'
ITEMS_CACHE_FILE = 'items_cache.json'

class ItemLoader:
    """アイテムのCSV URL読み込み"""

    def __init__(self):
        self._cache = None

    def fetch_from_csv(self):
        """CSV URLからアイテムを取得"""
        print(f"CSV URLからアイテムを取得中...")

        try:
            response = requests.get(ITEMS_CSV_URL, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'

            csv_content = StringIO(response.text)
            reader = csv.DictReader(csv_content)

            items = {}
            for row in reader:
                item_id = row.get("アイテムID", "").strip()
                if not item_id:
                    continue

                try:
                    # JSON定義をパース
                    json_str = row.get("JSON定義", "").strip()
                    effect = json.loads(json_str) if json_str else {}

                    # targetが指定されていない場合はデフォルトで"single"
                    if "target" not in effect:
                        effect["target"] = "single"

                    items[item_id] = {
                        "id": item_id,
                        "name": row.get("アイテム名", ""),
                        "description": row.get("効果説明", ""),
                        "flavor": row.get("フレーバーテキスト", ""),
                        "consumable": row.get("消耗", "").upper() == "TRUE",
                        "usable": row.get("使用可能", "").upper() == "TRUE",
                        "round_limit": int(row.get("ラウンド制限", "-1") or -1),
                        "effect": effect
                    }
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"[WARNING] アイテム {item_id} のパースに失敗: {e}")
                    continue

            print(f"[OK] {len(items)} 件のアイテムを読み込みました")
            self._cache = items

            # キャッシュに保存
            self._save_cache(items)

            return items

        except requests.RequestException as e:
            print(f"[ERROR] CSV取得エラー: {e}")
            return {}
        except Exception as e:
            print(f"[ERROR] データ取得エラー: {e}")
            return {}

    def _save_cache(self, items):
        """キャッシュファイルに保存"""
        try:
            with open(ITEMS_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            print(f"[OK] アイテムをキャッシュに保存しました")
        except Exception as e:
            print(f"[ERROR] キャッシュ保存エラー: {e}")

    def _load_cache(self):
        """キャッシュファイルから読み込み"""
        try:
            with open(ITEMS_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:
            print(f"[ERROR] キャッシュ読み込みエラー: {e}")
            return None

    def load_items(self, force_refresh=False):
        """アイテムをロード（キャッシュ優先）"""
        if self._cache is not None and not force_refresh:
            return self._cache

        # まずキャッシュを試す
        if not force_refresh:
            cached = self._load_cache()
            if cached:
                self._cache = cached
                print(f"[OK] キャッシュから {len(cached)} 件のアイテムを読み込みました")
                return cached

        # キャッシュがない場合はCSV URLから取得
        return self.fetch_from_csv()

    def get_item(self, item_id):
        """特定のアイテムを取得"""
        items = self.load_items()
        return items.get(item_id)

    def refresh(self):
        """強制的にCSV URLから再取得"""
        return self.load_items(force_refresh=True)

# グローバルインスタンス
item_loader = ItemLoader()
