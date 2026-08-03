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
        "version": 3,
        "character_presets": {},
        "enemy_formations": {},
        "ally_formations": {},
        "stage_presets": {},
        "catalog_collections": {},
        "updated_at": _now_ms(),
    }


def _coerce_dict(raw_value):
    return raw_value if isinstance(raw_value, dict) else {}


def _dedupe_strings(raw_value, *, exclude=None):
    excluded = {str(value).strip() for value in (exclude or []) if str(value).strip()}
    result = []
    seen = set(excluded)
    for value in raw_value if isinstance(raw_value, list) else []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def normalize_access_control(raw_value, *, legacy_visibility="public", owner_user_id=None):
    src = raw_value if isinstance(raw_value, dict) else {}
    owner = str(src.get("owner_user_id") or owner_user_id or "").strip() or None
    mode = str(src.get("viewer_mode") or legacy_visibility or "public").strip().lower()
    if mode == "private":
        mode = "gm"
    if mode not in {"public", "gm", "restricted"}:
        mode = "public"
    editors = _dedupe_strings(src.get("editor_user_ids"), exclude=[owner])
    viewers = _dedupe_strings(src.get("viewer_user_ids"), exclude=[owner, *editors])
    return {
        "owner_user_id": owner,
        "editor_user_ids": editors,
        "viewer_mode": mode,
        "viewer_user_ids": viewers,
    }


def normalize_catalog_meta(raw_value):
    src = raw_value if isinstance(raw_value, dict) else {}
    collection_id = str(src.get("collection_id") or "").strip() or None
    section_id = str(src.get("section_id") or "").strip() or None
    try:
        sort_order = int(src.get("sort_order", 2147483647))
    except (TypeError, ValueError):
        sort_order = 2147483647
    try:
        last_used_at = int(src.get("last_used_at", 0) or 0)
    except (TypeError, ValueError):
        last_used_at = 0
    return {
        "collection_id": collection_id,
        "section_id": section_id,
        "sort_order": sort_order,
        "labels": _dedupe_strings(src.get("labels")),
        "archived": bool(src.get("archived", False)),
        "last_used_at": max(0, last_used_at),
    }


def normalize_collection_record(raw_value, *, fallback_id=""):
    src = raw_value if isinstance(raw_value, dict) else {}
    rec = copy.deepcopy(src)
    rec_id = str(src.get("id") or fallback_id or "").strip()
    if not rec_id:
        return None
    sections = []
    seen_sections = set()
    for row in src.get("sections") if isinstance(src.get("sections"), list) else []:
        if not isinstance(row, dict):
            continue
        section_id = str(row.get("id") or "").strip()
        if not section_id or section_id in seen_sections:
            continue
        seen_sections.add(section_id)
        try:
            order = int(row.get("sort_order", 2147483647))
        except (TypeError, ValueError):
            order = 2147483647
        sections.append({
            "id": section_id,
            "name": str(row.get("name") or section_id).strip() or section_id,
            "sort_order": order,
        })
    sections.sort(key=lambda row: (row["sort_order"], row["name"].lower(), row["id"]))
    try:
        sort_order = int(src.get("sort_order", 2147483647))
    except (TypeError, ValueError):
        sort_order = 2147483647
    access_control = normalize_access_control(
        src.get("access_control"),
        legacy_visibility=src.get("visibility", "public"),
    )
    rec.update({
        "id": rec_id,
        "name": str(src.get("name") or rec_id).strip() or rec_id,
        "description": str(src.get("description") or "").strip(),
        "sort_order": sort_order,
        "archived": bool(src.get("archived", False)),
        "sections": sections,
        "access_control": access_control,
        "visibility": access_control["viewer_mode"],
    })
    return rec


def _normalize_record_envelope(rec):
    visibility = str(rec.get("visibility") or "public").strip().lower()
    access_control = normalize_access_control(
        rec.get("access_control"),
        legacy_visibility=visibility,
    )
    rec["access_control"] = access_control
    rec["visibility"] = access_control["viewer_mode"]
    rec["catalog_meta"] = normalize_catalog_meta(rec.get("catalog_meta"))
    return rec


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
        out[rec_id] = _normalize_record_envelope(rec)
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
        out[rec_id] = _normalize_record_envelope(rec)
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
        out[rec_id] = _normalize_record_envelope(rec)
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
        out[rec_id] = _normalize_record_envelope(rec)
    return out


def _normalize_catalog_collections(src):
    raw = src.get("catalog_collections")
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        rec = normalize_collection_record(value, fallback_id=key)
        if rec:
            out[rec["id"]] = rec
    return out


def _normalize_store(raw):
    src = _coerce_dict(raw)
    store = _default_store()
    store["character_presets"] = _normalize_character_presets(src)
    store["enemy_formations"] = _normalize_enemy_formations(src)
    store["ally_formations"] = _normalize_ally_formations(src)
    store["stage_presets"] = _normalize_stage_presets(src)
    store["catalog_collections"] = _normalize_catalog_collections(src)
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
