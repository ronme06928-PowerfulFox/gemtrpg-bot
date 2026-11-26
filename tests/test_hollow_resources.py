import pytest

from extensions import db
from manager.catalog.repository import CatalogConflictError
from manager.catalog.kinds import CatalogValidationError
from manager.units import repository, transfer
from models import CatalogEntry
from tests.test_units import unit_app


PAYLOADS = {
    "tier": ("HT-01", {"tier": 1}),
    "hollow_map": ("HM-01", {"tier": 1, "image": "/static/images/cave.webp",
                              "event_weights": {"normal": 1, "chest": 2, "miasma": 3},
                              "encounters": {"normal": [{"formation_id": "F-001", "weight": 1}]},
                              "category_weights": {"出血": 3},
                              "boss_formation_id": "F-001", "boss_stage_id": "ST-001"}),
    "fixed_floor": ("HF-01", {"floor": 10, "type": "camp"}),
    "relic": ("HR-01", {"rarity": "鉄級", "target": {"type": "condition", "condition": "has_tag:前衛"},
                       "buff_id": "HBu-01"}),
    "hollow_event": ("HE-01", {"type": "miasma", "choices": [
        {"label": "触れる", "difficulty": 9, "effect": {"kind": "item", "id": "I-01"},
         "failure_effect": {"kind": "buff", "id": "HBu-01", "battles": 2}, "failure_target": "selected"},
    ]}),
    "treasure_chest": ("HC-01", {"drop_table_id": "HD-01"}),
    "drop_table": ("HD-01", {"rows": [{"kind": "item", "id": "HI-01", "weight": 2},
                                     {"kind": "relic", "id": "HR-01", "weight": 1}]}),
    "hollow_buff": ("HBu-01", {"effect": {"power_bonus": [{"value": 3}]}}),
    "hollow_item": ("HI-01", {"usable": True, "effect": {"type": "buff", "buff_id": "HBu-01"}}),
}


def save(kind, **fields):
    return repository.save(kind, None, {"name": kind, **fields})[0]


@pytest.fixture
def library(unit_app):
    db.session.add_all([CatalogEntry(kind=kind, entry_id=key, payload={"name": key})
                        for kind, key in [("item", "I-01"), ("buff", "Bu-01")]])
    db.session.commit()
    save("formation", domain="hollow", type="enemy", members=[])
    save("stage", domain="hollow", enemy_formation_id="F-001")
    save("formation", domain="session", type="enemy", members=[])
    save("stage", domain="session", enemy_formation_id="F-002")
    save("formation", domain="hollow", type="ally", members=[])


@pytest.fixture
def resource_set(library):
    for kind in ("hollow_buff", "hollow_item", "relic", "drop_table", "treasure_chest",
                 "hollow_event", "tier", "hollow_map", "fixed_floor"):
        entry_id, payload = PAYLOADS[kind]
        assert save(kind, **payload).entry_id == entry_id


@pytest.mark.parametrize("kind", PAYLOADS)
def test_direct_save_lifecycle(library, kind):
    for dependency in ("hollow_buff", "hollow_item", "relic", "drop_table"):
        if dependency != kind:
            _, payload = PAYLOADS[dependency]
            if dependency == "hollow_item" and kind == "hollow_buff":
                payload = {"usable": True}
            if dependency == "relic" and kind == "hollow_buff":
                payload = {**payload, "buff_id": "Bu-01"}
            if dependency == "drop_table":
                payload = {"rows": [{"kind": "item", "id": "I-01", "weight": 1}]}
            save(dependency, **payload)
    entry_id, payload = PAYLOADS[kind]
    row = save(kind, **payload)
    assert row.entry_id == entry_id and row.revision == 1 and row.payload["domain"] == "hollow"
    repository.save(kind, entry_id, {**payload, "name": kind + "改"}, base_revision=1)
    restored, _ = repository.restore(kind, entry_id, 1, base_revision=2)
    assert restored.revision == 3 and restored.payload["name"] == kind
    assert repository.set_deprecated(kind, entry_id, True, base_revision=3).deprecated
    assert [row.action for row in repository.history(kind, entry_id)] == ["deprecate", "restore", "publish", "publish"]
    repository.delete(kind, entry_id, base_revision=4)
    assert repository.get(kind, entry_id) is None
    assert save(kind, **payload).entry_id.endswith("-02")


def test_transfer_includes_all_kinds_and_checks_references(resource_set):
    package = transfer.export_package(domain="hollow")
    assert set(PAYLOADS) < {row["kind"] for row in package["entries"]}
    assert {row["payload"]["domain"] for row in package["entries"]} == {"hollow"}
    assert {row["kind"] for row in transfer.export_package(domain="session")["entries"]} == {"formation", "stage"}
    # Simulate a fresh destination with only the shared master data.
    for kind, entry_id in repository.entries(domain="hollow"):
        db.session.delete(repository.get(kind, entry_id))
        for row in repository.history(kind, entry_id):
            db.session.delete(row)
    db.session.commit()
    report = transfer.preview(package)
    assert all(not row["errors"] and row["operation"] == "new" for row in report), report
    bases = {f"{row['kind']}:{row['entry_id']}": None for row in report}
    saved, _ = transfer.confirm(package, bases)
    assert {row["kind"] for row in saved} >= set(PAYLOADS)
    for kind in ("hollow_buff", "hollow_item", "relic", "drop_table", "formation", "stage"):
        key = PAYLOADS.get(kind, ({"formation": "F-001", "stage": "ST-001"}.get(kind),))[0]
        assert repository.references(kind, key)
        with pytest.raises(CatalogConflictError):
            repository.delete(kind, key, base_revision=1)


@pytest.mark.parametrize("kind,fields,error", [
    ("hollow_map", {"encounters": {"normal": [{"formation_id": "F-999", "weight": 1}]}}, "encounters.normal[0].formation_id"),
    ("hollow_map", {"encounters": {"normal": [{"formation_id": "F-002", "weight": 1}]}}, "encounters.normal[0].formation_id"),
    ("hollow_map", {"encounters": {"normal": [{"formation_id": "F-003", "weight": 1}]}}, "encounters.normal[0].formation_id"),
    ("tier", {"tier": 0}, "tier"),
    ("tier", {"tier": 6}, "tier"),
    ("tier", {"tier": True}, "tier"),
    ("tier", {"tier": 1.5}, "tier"),
    ("tier", {"tier": "1"}, "tier"),
    ("tier", {"event_weights": {}}, "event_weights"),
    ("tier", {"encounters": {}}, "encounters"),
    ("fixed_floor", {"type": "boss"}, "type"),
    ("fixed_floor", {"formation_id": "F-001"}, "formation_id"),
    ("fixed_floor", {"stage_id": "ST-001"}, "stage_id"),
    ("hollow_map", {"tier": 0}, "tier"),
    ("hollow_map", {"tier": 6}, "tier"),
    ("hollow_map", {"tier": True}, "tier"),
    ("hollow_map", {"image": 5}, "image"),
    ("hollow_map", {"event_weights": {"camp": 1}}, "event_weights.camp"),
    ("hollow_map", {"category_weights": {"不明": 1}}, "category_weights.不明"),
    ("hollow_map", {"category_weights": {"出血": -1}}, "category_weights.出血"),
    ("hollow_map", {"category_weights": {"打撃": 1.5}}, "category_weights.打撃"),
    ("hollow_map", {"boss_formation_id": "F-003"}, "boss_formation_id"),
    ("hollow_map", {"boss_stage_id": ""}, "boss_stage_id"),
    ("hollow_map", {"boss_stage_id": "ST-002"}, "boss_stage_id"),
    ("hollow_map", {"boss_stage_id": "F-001"}, "boss_stage_id"),
    ("relic", {"buff_id": "HI-01"}, "buff_id"),
    ("relic", {"rarity": "伝説"}, "rarity"),
    ("relic", {"cost": 1}, "cost"),
    ("relic", {"target": {"type": "nth", "n": 0}}, "target.n"),
    ("relic", {"target": {"type": "condition", "condition": "has_tag: "}}, "target.condition"),
    ("hollow_event", {"choices": [{"label": "A", "effect": {"kind": "item", "id": "HBu-01"}}]}, "choices[0].effect.id"),
    ("hollow_event", {"choices": [{"label": "A", "effect": {"kind": "buff", "id": "Bu-01", "battles": 0}}]}, "choices[0].effect.battles"),
    ("hollow_event", {"choices": [{"label": "A"}] * 5}, "choices"),
    ("treasure_chest", {"drop_table_id": "HR-01"}, "drop_table_id"),
    ("drop_table", {"rows": [{"kind": "relic", "id": "HI-01", "weight": 1}]}, "rows[0].id"),
    ("drop_table", {"rows": [{"kind": "item", "id": "HI-01", "weight": 1, "rarity": "鉄級"}]}, "rows[0].rarity"),
    ("hollow_item", {"effect": {"type": "buff", "buff_id": "I-01"}}, "effect.buff_id"),
    ("hollow_item", {"effect": []}, "effect"),
    ("hollow_buff", {"effect": {"type": "plugin"}}, "effect.type"),
    ("hollow_buff", {"domain": "session"}, "domain"),
])
def test_invalid_resources_cannot_be_saved(resource_set, kind, fields, error):
    key, original = PAYLOADS[kind]
    payload = {"name": kind, **original, **fields}
    assert error in repository.check(kind, payload, entry_id=key)[0]
    with pytest.raises(CatalogValidationError) as exc:
        repository.save(kind, key, payload, base_revision=1)
    assert error in exc.value.errors
    assert repository.get(kind, key).revision == 1


def test_tier_number_is_unique_among_active_records(unit_app):
    first = save("tier", tier=1)
    first_id = first.entry_id
    assert "tier" not in repository.check("tier", first.payload, entry_id=first_id)[0]
    assert "tier" in repository.check("tier", {"name": "重複", "tier": 1})[0]
    with pytest.raises(CatalogValidationError, match="tier"):
        save("tier", tier=1)
    repository.save("tier", first_id, {"name": "変更", "tier": 5}, base_revision=1)
    second = save("tier", tier=1)
    with pytest.raises(CatalogValidationError, match="tier"):
        repository.restore("tier", first_id, 1, base_revision=2)

    repository.set_deprecated("tier", first_id, True, base_revision=2)
    archived, _ = repository.save("tier", first_id, {"name": "廃止", "tier": 1}, base_revision=3)
    assert archived.deprecated
    with pytest.raises(CatalogValidationError, match="tier"):
        repository.set_deprecated("tier", first_id, False, base_revision=4)
    with pytest.raises(CatalogValidationError, match="tier"):
        repository.restore("tier", first_id, 1, base_revision=4)
    repository.set_deprecated("tier", second.entry_id, True, base_revision=1)
    assert not repository.set_deprecated("tier", first_id, False, base_revision=4).deprecated


def test_tier_import_checks_final_active_numbers(unit_app):
    first, second = save("tier", tier=1), save("tier", tier=2)
    package = transfer.export_package(domain="hollow")
    left, right = package["entries"]
    left["payload"]["tier"] = 2
    report = transfer.preview(package)
    assert all("tier" in row["errors"] for row in report)
    revisions = {f"tier:{row.entry_id}": 1 for row in (first, second)}
    with pytest.raises(CatalogValidationError, match="tier"):
        transfer.confirm(package, revisions)
    assert first.payload["tier"] == 1
    right["payload"]["tier"] = 1
    assert all(not row["errors"] for row in transfer.preview(package))
    transfer.confirm(package, revisions)
    assert (first.payload["tier"], second.payload["tier"]) == (2, 1)


def test_grade_and_inventory_checks_leave_existing_units_readable(resource_set, unit_app):
    for tags in ([], ["等級:金級", "等級:銀級"], ["等級:金級", "等級:金級"], ["等級:未知"]):
        assert "tags" in repository.check("unit", {"name": "敵", "domain": "hollow", "tags": tags})[0]
    save("unit", domain="hollow", allow_enemy=False)
    tags = ["等級:金級"]
    gear = {"items": [{"id": "HI-01", "count": 1}], "special_buffs": [{"buff_id": "HBu-01"}]}
    assert set(repository.check("unit", {"name": "敵", "domain": "session", **gear})[0]) == {
        "items[0]", "special_buffs[0].buff_id",
    }
    assert save("unit", domain="hollow", tags=tags, **gear).payload["items"] == gear["items"]
    assert "items[0]" in repository.check("unit", {"name": "敵", "domain": "hollow", "tags": tags,
                                                    "items": [{"id": "HI-99", "count": 1}]})[0]
    missing_grade = save("unit", domain="session")
    with pytest.raises(CatalogValidationError):
        repository.duplicate_to_hollow(missing_grade.entry_id)
    db.session.add(CatalogEntry(kind="unit", entry_id="U-901", payload={"name": "旧版", "domain": "hollow"}))
    db.session.commit()
    from manager.db_migration import run_auto_migration
    from manager.units.runtime import deployment_store
    run_auto_migration(unit_app)
    assert deployment_store(domain="hollow")["character_presets"]["U-901"]["name"] == "旧版"


def test_battle_and_simulator_look_up_hollow_gear(resource_set, tmp_path):
    import json
    from manager.battle.buff_power import calculate_buff_power_bonus
    from manager.items.loader import item_loader
    from manager.items.usage_manager import ItemUsageManager
    from manager.sim.battle_runner import run_battle
    from manager.sim.preset_loader import build_room_state_from_presets, load_preset_store_from_path
    from manager.units.characters import build_character
    from manager.buff_catalog import get_buff_by_id

    unit = save("unit", domain="hollow", tags=["等級:鉄級"], hp=20,
                items=[{"id": "HI-01", "count": 1}])
    user = build_character(unit.payload, "ally", 1)
    assert item_loader.get_item("HI-01")["id"] == "HI-01"
    assert "HI-01" not in item_loader.load_items()
    assert get_buff_by_id("HBu-01")["id"] == "HBu-01"
    assert ItemUsageManager().use_item(user, user, "HI-01", {})["success"]
    assert calculate_buff_power_bonus(user, {}, {}) == 3

    preset = tmp_path / "hollow.json"
    preset.write_text(json.dumps(transfer.export_package(domain="hollow")), encoding="utf-8")
    state = build_room_state_from_presets(store=load_preset_store_from_path(str(preset)),
                                         ally_preset_ids=[unit.entry_id], enemy_preset_ids=[unit.entry_id])
    # Prove the packaged definitions are used during a run, without DB rows.
    for kind in ("hollow_buff", "hollow_item"):
        db.session.delete(repository.get(kind, PAYLOADS[kind][0]))
    db.session.commit()
    def intent(room, _battle):
        actor = room["characters"][0]
        assert ItemUsageManager().use_item(actor, actor, "HI-01", {})["success"]
        assert calculate_buff_power_bonus(actor, {}, {}) == 3
    run_battle(state, max_rounds=1, intent_provider=intent)
    assert item_loader.get_item("HI-01") is None


def test_hollow_stat_buff_on_character_resolves_by_id(unit_app):
    from manager.utils import get_buff_stat_mod

    buff = save("hollow_buff", name="蓄力", effect={"type": "stat_mod", "stat": "物理補正", "value": 4})
    character = {"special_buffs": [{"buff_id": buff.entry_id, "name": "蓄力"}]}
    assert get_buff_stat_mod(character, "物理補正") == 4
