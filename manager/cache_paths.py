"""Shared cache file paths and legacy migration helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cache"

SKILLS_CACHE_FILE = CACHE_DIR / "skills_cache.json"
ITEMS_CACHE_FILE = CACHE_DIR / "items_cache.json"
RADIANCE_CACHE_FILE = CACHE_DIR / "radiance_skills_cache.json"
PASSIVES_CACHE_FILE = CACHE_DIR / "passives_cache.json"
BUFF_CATALOG_CACHE_FILE = CACHE_DIR / "buff_catalog_cache.json"
GLOSSARY_CACHE_FILE = CACHE_DIR / "glossary_catalog_cache.json"

LEGACY_SKILLS_CACHE_FILE = REPO_ROOT / "skills_cache.json"
LEGACY_ITEMS_CACHE_FILE = REPO_ROOT / "items_cache.json"
LEGACY_RADIANCE_CACHE_FILE = REPO_ROOT / "radiance_skills_cache.json"
LEGACY_PASSIVES_CACHE_FILE = REPO_ROOT / "passives_cache.json"
LEGACY_BUFF_CATALOG_CACHE_FILE = REPO_ROOT / "buff_catalog_cache.json"
LEGACY_GLOSSARY_CACHE_FILE = REPO_ROOT / "glossary_catalog_cache.json"


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def save_json_cache(cache_file: Path, data) -> None:
    ensure_cache_dir()
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json_cache(cache_file: Path, legacy_paths: Optional[Iterable[Path]] = None):
    if cache_file.exists():
        with cache_file.open("r", encoding="utf-8") as f:
            return json.load(f)

    for legacy_path in legacy_paths or []:
        if not legacy_path.exists():
            continue
        with legacy_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        save_json_cache(cache_file, data)
        return data

    return None

