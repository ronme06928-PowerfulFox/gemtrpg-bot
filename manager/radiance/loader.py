import requests
import csv
import json
from io import StringIO
from manager.logs import setup_logger

logger = setup_logger(__name__)

# CSV公開URL
RADIANCE_CSV_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTkulkkIx6AQEHBKJiAqnjyzEQX5itUVV3SDwi40sLmXeiVQbXvg0RmMS3-XLSwNo2YHsF3WybyHjMu/pub?gid=0&single=true&output=csv'
RADIANCE_CACHE_FILE = 'radiance_skills_cache.json'

class RadianceSkillLoader:
    """輝化スキルのCSV URL読み込み"""

    def __init__(self):
        self._cache = None

    def fetch_from_csv(self):
        """CSV URLから輝化スキルを取得"""
        logger.info("CSV URLから輝化スキルを取得中...")

        try:
            response = requests.get(RADIANCE_CSV_URL, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'

            csv_content = StringIO(response.text)
            reader = csv.DictReader(csv_content)

            skills = {}
            for row in reader:
                skill_id = row.get("スキルID", "").strip()
                if not skill_id:
                    continue

                try:
                    # JSON定義をパース
                    json_str = row.get("JSON定義", "").strip()
                    effect = json.loads(json_str) if json_str else {}

                    # ★ 持続ラウンドを読み込み（-1=永続、0以上=一時的）
                    duration_str = row.get("持続ラウンド", "-1").strip()
                    try:
                        duration = int(duration_str) if duration_str else -1
                    except ValueError:
                        duration = -1  # デフォルトは永続

                    skills[skill_id] = {
                        "id": skill_id,
                        "name": row.get("スキル名", ""),
                        "cost": int(row.get("習得コスト", "0") or 0),
                        "description": row.get("スキル効果", ""),
                        "flavor": row.get("フレーバーテキスト", ""),
                        "effect": effect,
                        "duration": duration  # ★ 追加
                    }
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"スキル {skill_id} のパースに失敗: {e}")
                    continue

            logger.info(f"{len(skills)} 件の輝化スキルを読み込みました")
            self._cache = skills

            # キャッシュに保存
            self._save_cache(skills)

            return skills

        except requests.RequestException as e:
            logger.error(f"CSV取得エラー: {e}")
            return {}
        except Exception as e:
            logger.error(f"データ取得エラー: {e}")
            return {}

    def _save_cache(self, skills):
        """キャッシュファイルに保存"""
        try:
            with open(RADIANCE_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(skills, f, ensure_ascii=False, indent=2)
            logger.info("輝化スキルをキャッシュに保存しました")
        except Exception as e:
            logger.error(f"キャッシュ保存エラー: {e}")

    def _load_cache(self):
        """キャッシュファイルから読み込み"""
        try:
            with open(RADIANCE_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f"キャッシュ読み込みエラー: {e}")
            return None

    def load_skills(self, force_refresh=False):
        """輝化スキルをロード（キャッシュ優先）"""
        if self._cache is not None and not force_refresh:
            return self._cache

        # まずキャッシュを試す
        if not force_refresh:
            cached = self._load_cache()
            if cached:
                self._cache = cached
                logger.info(f"キャッシュから {len(cached)} 件の輝化スキルを読み込みました")
                return cached

        # キャッシュがない場合はCSV URLから取得
        return self.fetch_from_csv()

    def get_skill(self, skill_id):
        """特定のスキルを取得"""
        skills = self.load_skills()
        return skills.get(skill_id)

    def refresh(self):
        """強制的にCSV URLから再取得"""
        return self.load_skills(force_refresh=True)

# グローバルインスタンス
radiance_loader = RadianceSkillLoader()
