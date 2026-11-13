"""未対応の効果のリクエストの保存と入力検査。"""
from datetime import datetime

from extensions import db
from manager.battle.effect_handlers import EFFECT_SCHEMAS
from models import CatalogDraft, CatalogEffectRequest
from .kinds import CatalogValidationError
from .repository import CatalogConflictError, _transaction

KINDS_WITH_EFFECTS = {"skill", "buff", "item", "passive", "radiance"}
ACTIVE_STATUSES = ("open", "in_progress")
STATUSES = (*ACTIVE_STATUSES, "done", "declined")


def count_open():
    return CatalogEffectRequest.query.filter(CatalogEffectRequest.status.in_(ACTIVE_STATUSES)).count()


def _fields(data, row):
    values = {}
    for name, label in (("title", "題"), ("want", "欲しい効果"), ("example", "文の例"),
                        ("near_type", "近い効果タイプ")):
        value = data.get(name, getattr(row, name, ""))
        if not isinstance(value, str):
            raise CatalogValidationError({name: f"{label}は文字列で指定してください。"})
        values[name] = value.strip()
    if not values["title"] or not values["want"]:
        raise CatalogValidationError({"title": "題と欲しい効果は必ず書いてください。"})
    if len(values["title"]) > 80:
        raise CatalogValidationError({"title": "題は80字までです。"})
    if values["near_type"] and values["near_type"] not in EFFECT_SCHEMAS:
        raise CatalogValidationError({"near_type": "効果タイプがありません。"})
    return values


@_transaction
def create(data, user_id):
    row = CatalogEffectRequest(**_fields(data, None), created_by=user_id)
    draft_id = data.get("draft_id")
    if draft_id is not None:
        if type(draft_id) is not int:
            raise CatalogValidationError({"draft_id": "下書きの番号を指定してください。"})
        draft = CatalogDraft.query.filter_by(id=draft_id).with_for_update().first()
        if draft is None or draft.kind not in KINDS_WITH_EFFECTS:
            raise CatalogValidationError({"draft_id": "効果を持つ種類の下書きを指定してください。"})
        row.draft_id, row.draft_kind, row.draft_target_id = draft.id, draft.kind, draft.target_id
        row.draft_name = next(
            (value for key in ("デフォルト名称", "display_name", "name")
             if isinstance(value := draft.payload.get(key), str) and value.strip()),
            "名前未入力",
        )
    db.session.add(row)
    db.session.commit()
    return row


def _editable(row, user_id):
    if row.created_by != user_id:
        raise PermissionError
    if row.status != "open":
        raise CatalogConflictError("受付のリクエストだけ変更できます。", field="status")


@_transaction
def update(row, data, user_id):
    _editable(row, user_id)
    values = _fields(data, row)
    if "draft_id" in data:
        if data["draft_id"] is not None:
            raise CatalogValidationError({"draft_id": "ひもづけは解除だけできます。"})
        values.update(draft_id=None, draft_kind=None, draft_target_id=None, draft_name=None)
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return row


@_transaction
def withdraw(row, user_id):
    _editable(row, user_id)
    db.session.delete(row)
    db.session.commit()


@_transaction
def review(row, data):
    status, memo = data.get("status"), data.get("memo", "")
    if status not in STATUSES:
        raise CatalogValidationError({"status": "状態を選んでください。"})
    if not isinstance(memo, str) or (status == "done" and not memo.strip()):
        raise CatalogValidationError({"memo": "実装済みの場合は使う効果タイプをメモに書いてください。"})
    row.status, row.memo, row.updated_at = status, memo.strip(), datetime.utcnow()
    db.session.commit()
    return row

