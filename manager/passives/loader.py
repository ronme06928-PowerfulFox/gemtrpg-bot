import requests
import csv
import json
from io import StringIO
from manager.logs import setup_logger
from manager.cache_paths import (
    PASSIVES_CACHE_FILE,
    LEGACY_PASSIVES_CACHE_FILE,
    load_json_cache,
    save_json_cache,
)

logger = setup_logger(__name__)

# CSV公開URL
PASSIVES_CSV_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTkulkkIx6AQEHBKJiAqnjyzEQX5itUVV3SDwi40sLmXeiVQbXvg0RmMS3-XLSwNo2YHsF3WybyHjMu/pub?gid=9160848&single=true&output=csv'
class PassiveLoader:
    """特殊パッシブのCSV URL読み込み"""

    def __init__(self):
        self._cache = None

    def fetch_from_csv(self):
        """CSV URLから特殊パッシブを取得"""
        logger.info("CSV URLから特殊パッシブを取得中...")

        try:
            response = requests.get(PASSIVES_CSV_URL, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'

            csv_content = StringIO(response.text)
            reader = csv.DictReader(csv_content)

            passives = {}
            for row in reader:
                passive_id = row.get("スキルID", "").strip()
                if not passive_id:
                    continue

                try:
                    # JSON定義をパース
                    json_str = row.get("JSON定義", "").strip()
                    effect = json.loads(json_str) if json_str else {}

                    passives[passive_id] = {
                        "id": passive_id,
                        "name": row.get("スキル名", ""),
                        "cost": int(row.get("習得コスト", "0") or 0),
                        "description": row.get("スキル効果", ""),
                        "flavor": row.get("フレーバーテキスト", ""),
                        "effect": effect
                    }
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"パッシブ {passive_id} のパースに失敗: {e}")
                    continue

            logger.info(f"{len(passives)} 件の特殊パッシブを読み込みました")
            self._cache = passives

            # キャッシュに保存
            self._save_cache(passives)

            return passives

        except requests.RequestException as e:
            logger.error(f"CSV取得エラー: {e}")
            return {}
        except Exception as e:
            logger.error(f"データ取得エラー: {e}")
            return {}

    def _save_cache(self, passives):
        """キャッシュファイルに保存"""
        try:
            save_json_cache(PASSIVES_CACHE_FILE, passives)
            logger.info("特殊パッシブをキャッシュに保存しました")
        except Exception as e:
            logger.error(f"キャッシュ保存エラー: {e}")

    def _load_cache(self):
        """キャッシュファイルから読み込み"""
        try:
            return load_json_cache(PASSIVES_CACHE_FILE, legacy_paths=[LEGACY_PASSIVES_CACHE_FILE])
        except Exception as e:
            logger.error(f"キャッシュ読み込みエラー: {e}")
            return None

    def load_passives(self, force_refresh=False):
        """特殊パッシブをロード（キャッシュ優先）"""
        if self._cache is not None and not force_refresh:
            return self._cache

        # まずキャッシュを試す
        if not force_refresh:
            cached = self._load_cache()
            if cached:
                self._cache = cached
                logger.info(f"キャッシュから {len(cached)} 件の特殊パッシブを読み込みました")
                return cached

        # キャッシュがない場合はCSV URLから取得
        return self.fetch_from_csv()

    def get_passive(self, passive_id):
        """特定のパッシブを取得"""
        passives = self.load_passives()
        return passives.get(passive_id)

    def refresh(self):
        """強制的にCSV URLから再取得"""
        return self.load_passives(force_refresh=True)

# グローバルインスタンス
passive_loader = PassiveLoader()
