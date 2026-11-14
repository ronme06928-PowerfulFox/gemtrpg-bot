"""Project unit resources into the existing room deployment and draft protocols."""
from copy import deepcopy

from manager.room_access import GM_ROLES
from manager.units import repository

MAPS = {"character": "character_presets", "enemy_formation": "enemy_formations",
        "ally_formation": "ally_formations", "stage": "stage_presets",
        "collection": "catalog_collections"}


def deployment_store(resources=None):
    resources = repository.entries() if resources is None else resources
    store = {key: {} for key in MAPS.values()}
    for (kind, entry_id), row in resources.items():
        payload = deepcopy(row["payload"])
        if kind == "formation":
            record_type = payload["type"] + "_formation"
        else:
            record_type = {"unit": "character", "stage": "stage", "unit_collection": "collection"}[kind]
        payload.update(id=entry_id, visibility=row["visibility"], revision=row.get("revision"),
                       deprecated=row["deprecated"])
        payload["catalog_meta"] = {"collection_id": payload.get("collection_id"),
                                   "archived": row["deprecated"]}
        store[MAPS[record_type]][entry_id] = payload
    return store


def record_map(store, record_type):
    return store.get(MAPS[record_type], {})


def get_record(store, record_type, entry_id):
    return record_map(store, record_type).get(entry_id)


def can_read(record, *, is_author=False, room_role=None):
    return record.get("visibility", "public") == "public" or is_author or room_role in GM_ROLES


def visible_records(records, *, is_author=False, room_role=None, include_deprecated=False):
    return {key: row for key, row in records.items()
            if can_read(row, is_author=is_author, room_role=room_role)
            and (include_deprecated or not row.get("deprecated"))}


def usable_formation(store, formation, side):
    members = formation.get("members", [])
    for member in members:
        unit = get_record(store, "character", member.get("unit_id"))
        if not unit or not unit.get("allow_" + side, True):
            return False
        pattern = member.get("pattern_id")
        if pattern and not any(item["id"] == pattern for item in unit.get("patterns", [])):
            return False
    return True


def valid_deployment_target(store, record_type, record):
    if record_type in ("enemy_formation", "ally_formation"):
        return usable_formation(store, record, record_type.split("_")[0])
    if record_type == "stage":
        for side in ("ally", "enemy"):
            key = record.get(side + "_formation_id")
            if key:
                target = get_record(store, side + "_formation", key)
                if not target or not usable_formation(store, target, side):
                    return False
    return True


def draft_reference_failures(store, draft):
    refs = [(kind, draft.get(field)) for kind, field in (
        ("stage", "selected_stage_id"), ("enemy_formation", "enemy_formation_id"),
        ("ally_formation", "ally_formation_id"),
    )]
    for field in ("ally_entries", "enemy_entries"):
        refs.extend(("character", row.get("preset_id")) for row in draft.get(field) or []
                    if isinstance(row, dict))
    failures = []
    for kind, entry_id in dict.fromkeys((kind, entry_id) for kind, entry_id in refs if entry_id):
        row = get_record(store, kind, entry_id)
        if row is None or not valid_deployment_target(store, kind, row):
            failures.append({"record_type": kind, "record_id": entry_id,
                             "message": f"参照先を利用できません: {entry_id}"})
    return failures
