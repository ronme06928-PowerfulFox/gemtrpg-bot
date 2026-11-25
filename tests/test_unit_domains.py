from tests.test_units import unit_app

import pytest


@pytest.mark.parametrize("kind,fields", [
    ("unit", {}), ("formation", {"type": "enemy", "members": []}),
    ("stage", {}), ("unit_collection", {}),
])
@pytest.mark.parametrize("domain", [{}, {"domain": "other"}, {"domain": None}, {"domain": ["session"]}])
def test_unit_resources_require_domain(unit_app, kind, fields, domain):
    from manager.units import repository
    from manager.catalog.kinds import CatalogValidationError

    payload = {"name": "Resource", **fields, **domain}
    assert "domain" in repository.check(kind, payload)[0]
    with pytest.raises(CatalogValidationError):
        repository.save(kind, None, payload)


@pytest.mark.parametrize("side", ["ally", "enemy"])
def test_domain_checks_all_links_including_reverse_and_transfer(unit_app, side):
    from manager.catalog.kinds import CatalogValidationError
    from manager.units import repository, transfer
    from manager.units.runtime import deployment_store

    def save(kind, name, domain="session", **fields):
        return repository.save(kind, None, {"name": name, "domain": domain, **fields})[0]

    collection = save("unit_collection", "Collection")
    unit = save("unit", "Unit", collection_id=collection.entry_id)
    hollow_unit = save("unit", "Hollow", "hollow", tags=["等級:鉄級"])
    members = [{"unit_id": unit.entry_id, "count": 1}]
    formation = save("formation", "Formation", type=side, members=members)
    stage_field = side + "_formation_id"
    for kind, fields, path in (
        ("unit", {"collection_id": collection.entry_id, "tags": ["等級:鉄級"]}, "collection_id"),
        ("formation", {"type": side, "members": members}, "members[0].unit_id"),
        ("formation", {"type": side, "members": [], "collection_id": collection.entry_id}, "collection_id"),
        ("stage", {stage_field: formation.entry_id}, stage_field),
        ("stage", {"collection_id": collection.entry_id}, "collection_id"),
    ):
        payload = {"name": "Cross-domain", "domain": "hollow", **fields}
        assert path in repository.check(kind, payload)[0]
        with pytest.raises(CatalogValidationError) as exc:
            repository.save(kind, None, payload)
        assert path in exc.value.errors

    for row in (unit, collection):
        new_payload = {**row.payload, "domain": "hollow", "collection_id": None}
        if row.kind == "unit":
            new_payload["tags"] = ["等級:鉄級"]
        assert repository.check(row.kind, new_payload, entry_id=row.entry_id)[0]
        with pytest.raises(CatalogValidationError):
            repository.save(row.kind, row.entry_id, new_payload, base_revision=row.revision)

    save("stage", "Stage", **{stage_field: formation.entry_id})
    hollow_formation = save("formation", "Hollow Formation", "hollow", type=side,
                            members=[{"unit_id": hollow_unit.entry_id, "count": 1}])
    package = transfer.export_package()
    assert {row["payload"]["domain"] for row in package["entries"]} == {"session", "hollow"}
    report = transfer.preview(package)
    assert not any(row["errors"] for row in report)
    assert len(transfer.confirm(package, {f"{row['kind']}:{row['entry_id']}": row["base_revision"]
                                          for row in report})[0]) == len(report)
    assert hollow_formation.entry_id in deployment_store()[side + "_formations"]
    assert hollow_formation.entry_id not in deployment_store(domain="session")[side + "_formations"]
    assert set(deployment_store(domain="hollow")["character_presets"]) == {hollow_unit.entry_id}
    entry = next(row for row in package["entries"] if row["entry_id"] == hollow_formation.entry_id)
    entry["payload"]["members"] = members
    report = transfer.preview(package)
    assert next(row for row in report if row["entry_id"] == hollow_formation.entry_id)["errors"]
    with pytest.raises(CatalogValidationError):
        transfer.confirm(package, {f"{row['kind']}:{row['entry_id']}": row["base_revision"] for row in report})
    assert repository.get("formation", hollow_formation.entry_id).payload["members"][0]["unit_id"] == hollow_unit.entry_id


def test_migrates_domain_and_removes_legacy_marks_twice(unit_app, caplog):
    from copy import deepcopy
    from extensions import db
    from models import CatalogDraft, CatalogEntry, CatalogHistory
    from manager.db_migration import run_auto_migration

    fixtures = [
        ("unit", "U-001", {"marks": ["hollow", "known"]}),
        ("unit", "U-002", {"marks": ["hollow"]}),
        ("unit", "U-003", {"marks": ["hollow"], "collection_id": "SC-01"}),
        ("formation", "F-001", {"type": "enemy", "members": [{"unit_id": "U-002", "count": 1}]}),
        ("unit_collection", "SC-01", {}),
        ("stage", "ST-001", {"enemy_formation_id": "F-001"}),
        ("buff", "Bu-01", {"marks": ["enemy", "hollow"]}),
    ]
    for kind, key, values in fixtures:
        payload = {"name": key, **values}
        db.session.add(CatalogEntry(kind=kind, entry_id=key, payload=payload, revision=1))
        db.session.add(CatalogHistory(kind=kind, entry_id=key, payload=payload, revision=1, action="publish"))
    db.session.commit()

    db.session.add(CatalogDraft(kind="buff", target_id="Bu-02", payload={"marks": ["hollow"]}))
    db.session.commit()

    run_auto_migration(unit_app)
    assert CatalogDraft.query.one().payload == {"marks": []}
    assert "Bu-02" in caplog.text
    before = {row.entry_id: deepcopy(row.payload) for row in CatalogEntry.query}
    assert before["U-001"] == {"name": "U-001", "domain": "hollow", "marks": ["known"]}
    for key in ["U-002", "U-003", "F-001", "ST-001", "SC-01"]:
        assert before[key]["domain"] == "session"
        assert "hollow" not in before[key].get("marks", [])
    assert before["Bu-01"] == {"name": "Bu-01", "marks": ["enemy"]}
    assert all(key in caplog.text for key in ("U-002", "U-003", "Bu-01"))
    assert all(row.payload == before[row.entry_id] for row in CatalogHistory.query)
    caplog.clear()
    run_auto_migration(unit_app)
    assert {row.entry_id: row.payload for row in CatalogEntry.query} == before
    assert not any(key in caplog.text for key in ("U-002", "U-003", "Bu-01"))
