"""Shared paths and JSON I/O for the current data/cache directory."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cache"

SKILLS_CACHE_FILE = CACHE_DIR / "skills_cache.json"
ITEMS_CACHE_FILE = CACHE_DIR / "items_cache.json"
RADIANCE_CACHE_FILE = CACHE_DIR / "radiance_skills_cache.json"
PASSIVES_CACHE_FILE = CACHE_DIR / "passives_cache.json"
BUFF_CATALOG_CACHE_FILE = CACHE_DIR / "buff_catalog_cache.json"
GLOSSARY_CACHE_FILE = CACHE_DIR / "glossary_catalog_cache.json"
SUMMON_TEMPLATES_CACHE_FILE = CACHE_DIR / "summon_templates_cache.json"
BATTLE_ONLY_PRESETS_CACHE_FILE = CACHE_DIR / "battle_only_presets_cache.json"


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def save_json_cache(cache_file: Path, data) -> None:
    ensure_cache_dir()
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json_cache(cache_file: Path):
    if cache_file.exists():
        with cache_file.open("r", encoding="utf-8") as f:
            return json.load(f)

    return None
