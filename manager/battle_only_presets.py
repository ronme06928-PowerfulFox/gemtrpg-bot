import copy
import threading
import time

from manager.cache_paths import (
    BATTLE_ONLY_PRESETS_CACHE_FILE,
    LEGACY_BATTLE_ONLY_PRESETS_CACHE_FILE,
    load_json_cache,
    save_json_cache,
)


_STORE_LOCK = threading.Lock()
_STORE_CACHE = None


def _now_ms():
    return int(time.time() * 1000)


def _default_store():
    return {
        "version": 2,
        "character_presets": {},
        "enemy_formations": {},
        "ally_formations": {},
        "stage_presets": {},
        "updated_at": _now_ms(),
    }


def _coerce_dict(raw_value):
    return raw_value if isinstance(raw_value, dict) else {}


def _normalize_character_presets(src):
    # v2キーを優先し、なければ旧v1の presets から移行する。
    presets_src = src.get("character_presets")
    if not isinstance(presets_src, dict):
        presets_src = src.get("presets")
    if not isinstance(presets_src, dict):
        presets_src = {}

    out = {}
    for key, value in presets_src.items():
        if not isinstance(value, dict):
            continue
        rec = copy.deepcopy(value)
        rec_id = str(rec.get("id", "")).strip() or str(key).strip()
        if not rec_id:
            continue
        rec["id"] = rec_id
        out[rec_id] = rec
    return out


def _normalize_enemy_formations(src):
    formations_src = src.get("enemy_formations")
    if not isinstance(formations_src, dict):
        formations_src = {}

    out = {}
    for key, value in formations_src.items():
        if not isinstance(value, dict):
            continue
        rec = copy.deepcopy(value)
        rec_id = str(rec.get("id", "")).strip() or str(key).strip()
        if not rec_id:
            continue
        rec["id"] = rec_id
        members = rec.get("members")
        if not isinstance(members, list):
            rec["members"] = []
        out[rec_id] = rec
    return out


def _normalize_ally_formations(src):
    formations_src = src.get("ally_formations")
    if not isinstance(formations_src, dict):
        formations_src = {}

    out = {}
    for key, value in formations_src.items():
        if not isinstance(value, dict):
            continue
        rec = copy.deepcopy(value)
        rec_id = str(rec.get("id", "")).strip() or str(key).strip()
        if not rec_id:
            continue
        rec["id"] = rec_id
        members = rec.get("members")
        if not isinstance(members, list):
            rec["members"] = []
        out[rec_id] = rec
    return out


def _normalize_stage_presets(src):
    stages_src = src.get("stage_presets")
    if not isinstance(stages_src, dict):
        stages_src = {}

    out = {}
    for key, value in stages_src.items():
        if not isinstance(value, dict):
            continue
        rec = copy.deepcopy(value)
        rec_id = str(rec.get("id", "")).strip() or str(key).strip()
        if not rec_id:
            continue
        rec["id"] = rec_id
        rec["enemy_formation_id"] = str(rec.get("enemy_formation_id", "")).strip() or None
        rec["ally_formation_id"] = str(rec.get("ally_formation_id", "")).strip() or None
        try:
            rec["required_ally_count"] = int(rec.get("required_ally_count", 0) or 0)
        except Exception:
            rec["required_ally_count"] = 0
        if rec["required_ally_count"] < 0:
            rec["required_ally_count"] = 0
        tags = rec.get("tags")
        if not isinstance(tags, list):
            rec["tags"] = []
        else:
            rec["tags"] = [str(x).strip() for x in tags if str(x).strip()]
        out[rec_id] = rec
    return out


def _normalize_store(raw):
    src = _coerce_dict(raw)
    store = _default_store()
    store["character_presets"] = _normalize_character_presets(src)
    store["enemy_formations"] = _normalize_enemy_formations(src)
    store["ally_formations"] = _normalize_ally_formations(src)
    store["stage_presets"] = _normalize_stage_presets(src)
    try:
        store["updated_at"] = int(src.get("updated_at", _now_ms()) or _now_ms())
    except Exception:
        store["updated_at"] = _now_ms()
    return store


def _ensure_loaded_unlocked():
    global _STORE_CACHE
    if _STORE_CACHE is not None:
        return
    loaded = load_json_cache(
        BATTLE_ONLY_PRESETS_CACHE_FILE,
        legacy_paths=[LEGACY_BATTLE_ONLY_PRESETS_CACHE_FILE],
    )
    _STORE_CACHE = _normalize_store(loaded) if loaded else _default_store()


def load_store():
    with _STORE_LOCK:
        _ensure_loaded_unlocked()
        return copy.deepcopy(_STORE_CACHE)


def save_store(new_store):
    with _STORE_LOCK:
        global _STORE_CACHE
        _STORE_CACHE = _normalize_store(new_store)
        _STORE_CACHE["updated_at"] = _now_ms()
        save_json_cache(BATTLE_ONLY_PRESETS_CACHE_FILE, _STORE_CACHE)
        return copy.deepcopy(_STORE_CACHE)


def mutate_store(mutator):
    with _STORE_LOCK:
        global _STORE_CACHE
        _ensure_loaded_unlocked()
        working = copy.deepcopy(_STORE_CACHE)
        mutator(working)
        _STORE_CACHE = _normalize_store(working)
        _STORE_CACHE["updated_at"] = _now_ms()
        save_json_cache(BATTLE_ONLY_PRESETS_CACHE_FILE, _STORE_CACHE)
        return copy.deepcopy(_STORE_CACHE)
