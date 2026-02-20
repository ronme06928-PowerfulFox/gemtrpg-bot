"""Glossary catalog loader (CSV -> cache -> extensions global dict)."""

import csv
import json
from io import StringIO

import requests

from manager.cache_paths import (
    GLOSSARY_CACHE_FILE,
    LEGACY_GLOSSARY_CACHE_FILE,
    load_json_cache,
    save_json_cache,
)

# 用語図鑑CSVのURL（ユーザー提供）
GLOSSARY_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vTkulkkIx6AQEHBKJiAqnjyzEQX5itUVV3SDwi40sLmXeiVQbXvg0RmMS3-"
    "XLSwNo2YHsF3WybyHjMu/pub?gid=1131733208&single=true&output=csv"
)

CACHE_FILE = GLOSSARY_CACHE_FILE


def _split_csv_text(value: str):
    if not value:
        return []
    normalized = value.replace("、", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _parse_bool(value: str, default=True) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if not normalized:
        return default
    if normalized in ("1", "true", "yes", "y", "on"):
        return True
    if normalized in ("0", "false", "no", "n", "off"):
        return False
    return default


def _pick(row: dict, *keys: str) -> str:
    for key in keys:
        if key in row and row[key] is not None:
            return str(row[key]).strip()
    return ""


class GlossaryCatalogLoader:
    """用語辞書データのローダー"""

    def __init__(self):
        self.terms = {}

    def fetch_from_csv(self):
        try:
            print(f"[INFO] 用語辞書データを取得中: {GLOSSARY_CSV_URL}")
            response = requests.get(GLOSSARY_CSV_URL, timeout=10)
            response.raise_for_status()
            response.encoding = "utf-8"

            reader = csv.DictReader(StringIO(response.text))
            terms = {}

            for raw_row in reader:
                row = {}
                for key, value in (raw_row or {}).items():
                    cleaned_key = (key or "").replace("\ufeff", "").strip()
                    row[cleaned_key] = (value or "").strip()

                term_id = _pick(row, "term_id", "ID", "id", "TERM_ID")
                if not term_id:
                    continue

                enabled = _parse_bool(_pick(row, "is_enabled", "表示の有無"), default=True)
                if not enabled:
                    continue

                sort_order = None
                sort_order_raw = _pick(row, "sort_order", "表示順")
                if sort_order_raw:
                    try:
                        sort_order = int(sort_order_raw)
                    except ValueError:
                        sort_order = None

                extra_json = None
                extra_json_raw = _pick(row, "extra_json", "追加JSON")
                if extra_json_raw:
                    try:
                        extra_json = json.loads(extra_json_raw)
                    except json.JSONDecodeError:
                        print(f"[WARNING] 用語 {term_id} の追加JSONが不正です")

                term_data = {
                    "term_id": term_id,
                    "display_name": _pick(row, "display_name", "名称", "name") or term_id,
                    "category": _pick(row, "category", "分類"),
                    "short": _pick(row, "short", "短文説明"),
                    "long": _pick(row, "long", "本説明", "説明"),
                    "flavor": _pick(row, "flavor", "フレーバー", "フレーバーテキスト"),
                    "links": _split_csv_text(_pick(row, "links", "関連用語ID")),
                    "synonyms": _split_csv_text(_pick(row, "synonyms", "別名")),
                    "icon": _pick(row, "icon", "アイコン"),
                    "sort_order": sort_order,
                    "is_enabled": True,
                }
                if extra_json is not None:
                    term_data["extra_json"] = extra_json

                terms[term_id] = term_data

            print(f"[OK] 用語辞書データを {len(terms)} 件取得しました")
            return terms
        except Exception as e:
            print(f"[ERROR] 用語辞書データの取得に失敗: {e}")
            return {}

    def save_to_cache(self, terms):
        try:
            save_json_cache(CACHE_FILE, terms)
            print(f"[OK] 用語辞書データをキャッシュに保存しました: {CACHE_FILE}")
        except Exception as e:
            print(f"[ERROR] 用語辞書データのキャッシュ保存に失敗: {e}")

    def load_from_cache(self):
        try:
            data = load_json_cache(CACHE_FILE, legacy_paths=[LEGACY_GLOSSARY_CACHE_FILE])
            if not data:
                return {}
            print(f"[OK] キャッシュから {len(data)} 件の用語辞書データを読み込みました")
            return data
        except Exception as e:
            print(f"[ERROR] 用語辞書キャッシュの読み込みに失敗: {e}")
            return {}

    def refresh(self):
        terms = self.fetch_from_csv()
        if terms:
            self.save_to_cache(terms)
            self.terms = terms

            try:
                from extensions import all_glossary_data

                all_glossary_data.clear()
                all_glossary_data.update(terms)
            except Exception:
                pass
        return terms

    def load_terms(self):
        from extensions import all_glossary_data

        self.terms = self.load_from_cache()
        if not self.terms:
            print("[INFO] 用語辞書キャッシュが見つかりません。CSVから取得します...")
            self.terms = self.fetch_from_csv()
            if self.terms:
                self.save_to_cache(self.terms)

        all_glossary_data.clear()
        all_glossary_data.update(self.terms)
        return self.terms

    def get_term(self, term_id):
        return self.terms.get(term_id)


glossary_catalog_loader = GlossaryCatalogLoader()

