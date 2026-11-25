"""Export resource sets and preview or atomically confirm an import."""
from manager.catalog.repository import _transaction
from manager.units import repository
from manager.units.validation import IDS, inspect_payload, links, valid_id
from extensions import db

FORMAT = "gemtrpg-units-v1"


def export_package(collection_id=None, *, include_deprecated=True, domain=None):
    """Export payloads with their domains and all resource dependencies."""
    resources = repository.entries(domain=domain)
    selected = {key for key, row in resources.items() if include_deprecated or not row["deprecated"]}
    if collection_id:
        collection = ("unit_collection", collection_id)
        if collection not in resources:
            raise repository.CatalogValidationError({"collection_id": "分類が見つかりません"})
        selected = {collection} | {key for key in selected
                                   if resources[key]["payload"].get("collection_id") == collection_id}
    pending = list(selected)
    while pending:
        key = pending.pop()
        for kind, entry_id, _ in links(key[0], resources[key]["payload"]):
            if kind in ("buff", "item"):
                continue
            target = (kind, entry_id)
            if target not in selected:
                if target not in resources:
                    raise repository.CatalogValidationError({"references": f"参照先がありません: {entry_id}"})
                selected.add(target)
                pending.append(target)
    return {"format": FORMAT, "entries": [
        {field: value for field, value in resources[key].items() if field != "revision"}
        for key in sorted(selected)]}


def package_entries(package):
    if not isinstance(package, dict) or package.get("format") != FORMAT:
        raise repository.CatalogValidationError({"format": "ユニット資源の書き出し形式が必要です"})
    rows = package.get("entries")
    if not isinstance(rows, list):
        raise repository.CatalogValidationError({"entries": "資源の配列が必要です"})
    incoming = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise repository.CatalogValidationError({f"entries[{index}]": "資源が不正です"})
        kind, entry_id = row.get("kind"), row.get("entry_id")
        key = (kind, entry_id)
        if (not isinstance(kind, str) or kind not in IDS or not valid_id(kind, entry_id)
                or key in incoming or not isinstance(row.get("payload"), dict)
                or type(row.get("deprecated")) is not bool or row.get("visibility") not in ("public", "staff")):
            raise repository.CatalogValidationError({f"entries[{index}]": "資源の項目またはIDが不正です"})
        incoming[key] = dict(row)
    return incoming


def _prepare(package):
    incoming = package_entries(package)
    current = repository.entries()
    # Resolve links against the final set, so either domain can arrive in the same package.
    combined = current | incoming
    report = []
    for kind in IDS:
        for key, row in incoming.items():
            if key[0] != kind:
                continue
            previous = current.get(key, {})
            errors, warnings, payload = inspect_payload(
                kind, row["payload"], row["visibility"], combined, previous=previous.get("payload"),
                entry_id=key[1], deprecated=row["deprecated"])
            row["payload"] = payload
            if not previous and repository.history(*key):
                errors["entry_id"] = "このIDは削除済みです"
            report.append({"kind": kind, "entry_id": key[1], "operation": "overwrite" if previous else "new",
                           "base_revision": previous.get("revision"), "errors": errors, "warnings": warnings})
    if not any(item["errors"] for item in report):
        for item in report:
            key = (item["kind"], item["entry_id"])
            item["errors"].update(repository.dependent_errors(*key, incoming[key]["payload"], combined))
    return incoming, report


def preview(package):
    _, report = _prepare(package)
    return report


@_transaction
def confirm(package, revisions, actor_user_id=None):
    repository.lock_writes()
    incoming, report = _prepare(package)
    expected = {f"{item['kind']}:{item['entry_id']}": item["base_revision"] for item in report}
    if not isinstance(revisions, dict) or revisions != expected or any(
        value is not None and type(value) is not int for value in revisions.values()
    ):
        raise repository.CatalogConflictError("取り込み対象の版が変わりました。確認し直してください")
    errors = {item["entry_id"]: item["errors"] for item in report if item["errors"]}
    if errors:
        raise repository.CatalogValidationError(errors)
    rows = [repository.write(*key, row["payload"], row["visibility"], row["deprecated"],
                             "import", actor_user_id, row=repository.get(*key))
            for key, row in incoming.items()]
    db.session.commit()
    return [repository.entry_json(row) for row in rows], report
