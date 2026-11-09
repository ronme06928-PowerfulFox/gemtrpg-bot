"""アイテム・特殊パッシブ・輝化・召喚の保存項目と参照検査。"""
from manager.cache_paths import ITEMS_CACHE_FILE, PASSIVES_CACHE_FILE, RADIANCE_CACHE_FILE, SUMMON_TEMPLATES_CACHE_FILE


def _definition(prefix, cache, fields, defaults, memory, id_field="id"):
    return {"id_prefix": prefix + "-", "id_pattern": prefix + r"-\d{2,}", "cache_file": cache,
            "fields": {"name": str, **fields}, "required": ("name",), "defaults": defaults,
            "memory_name": memory, "id_field": id_field}


RESOURCE_DEFINITIONS = {
    "item": _definition("I", ITEMS_CACHE_FILE,
        {"description": str, "flavor": str, "consumable": bool, "usable": bool, "round_limit": int, "effect": dict},
        {"description": "", "flavor": "", "consumable": False, "usable": False, "round_limit": -1, "effect": {}}, "all_item_data"),
    "passive": _definition("Pa", PASSIVES_CACHE_FILE,
        {"cost": int, "description": str, "flavor": str, "effect": dict},
        {"cost": 0, "description": "", "flavor": "", "effect": {}}, "all_passive_data"),
    "radiance": _definition("S", RADIANCE_CACHE_FILE,
        {"cost": int, "description": str, "flavor": str, "effect": dict, "duration": int, "granted_tag_ids": list},
        {"cost": 0, "description": "", "flavor": "", "effect": {}, "duration": -1, "granted_tag_ids": []}, "all_radiance_data"),
    "summon": _definition("U", SUMMON_TEMPLATES_CACHE_FILE,
        {"hp": int, "maxHp": int, "mp": int, "maxMp": int, "initial_skill_ids": list, "SPassive": list,
         "radiance_skills": list, "hidden_skills": list, "inventory": dict, "summon_duration_mode": str,
         "summon_duration": int, "allow_duplicate_same_team": bool, "params": list, "tag_ids": list,
         "disabled_tag_ids": list, "special_buffs": list, "flags": dict},
        {"hp": 0, "maxHp": 0, "mp": 0, "maxMp": 0, "initial_skill_ids": [], "SPassive": [],
         "radiance_skills": [], "hidden_skills": [], "inventory": {}, "summon_duration_mode": "permanent",
         "summon_duration": 0, "allow_duplicate_same_team": True, "params": [], "tag_ids": [],
         "disabled_tag_ids": [], "special_buffs": [], "flags": {}}, "all_summon_template_data", "baseName"),
}
STRING_LIST_FIELDS = {"radiance": ("granted_tag_ids",), "summon": (
    "initial_skill_ids", "hidden_skills", "SPassive", "radiance_skills", "tag_ids", "disabled_tag_ids")}
SUMMON_REFERENCES = {"initial_skill_ids": "skill", "hidden_skills": "skill", "SPassive": "passive", "radiance_skills": "radiance"}


def inspect_resource(kind, payload, invalid, add):
    for field in STRING_LIST_FIELDS.get(kind, ()):
        value = payload.get(field, [])
        if field not in invalid and any(not isinstance(item, str) for item in value):
            add(field, "文字列の配列が必要です")
            invalid.add(field)
    if kind != "summon":
        return
    from flask import has_app_context
    from models import CatalogEntry, CatalogDraft
    for field, target_kind in SUMMON_REFERENCES.items():
        if field in invalid:
            continue
        entries = {row.entry_id: row for row in CatalogEntry.query.filter_by(kind=target_kind).all()} if has_app_context() else {}
        drafts = {row.target_id for row in CatalogDraft.query.filter_by(kind=target_kind, base_revision=None).all()} if has_app_context() else set()
        for index, target in enumerate(payload.get(field, [])):
            path = f"{field}[{index}]"
            if target not in entries and target not in drafts:
                add(path, f"参照先が存在しません: {target}")
            elif target in entries and entries[target].deprecated:
                add(path, f"参照先は廃止されています: {target}", "warning")
