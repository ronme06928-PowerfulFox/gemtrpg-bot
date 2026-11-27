"""Resolve Hollow definitions by ID without modifying the public catalogs."""
from contextlib import contextmanager
from contextvars import ContextVar
from itertools import chain
from threading import RLock

from flask import current_app, has_app_context
from sqlalchemy import event
from sqlalchemy.orm import Session

from manager.hollow.resources import REWARD_KINDS
from models import CatalogEntry

_simulation_rewards = ContextVar("simulation_hollow_rewards", default=None)
_cache_lock = RLock()
_CACHE_KEY = "hollow_reward_definitions"
_RUNTIME_KINDS = (*REWARD_KINDS, "relic", "hollow_load_stage", "hollow_recipe", "hollow_map")


@contextmanager
def simulation_rewards(definitions):
    token = _simulation_rewards.set(definitions)
    try:
        yield
    finally:
        _simulation_rewards.reset(token)


def prepare_rewards():
    if not has_app_context():
        return {}
    extensions = current_app.extensions
    cached = extensions.get(_CACHE_KEY)
    if cached is not None:
        return cached
    with _cache_lock:
        if _CACHE_KEY not in extensions:
            definitions = {kind: {} for kind in _RUNTIME_KINDS}
            for row in CatalogEntry.query.filter(CatalogEntry.kind.in_(_RUNTIME_KINDS)):
                definitions[row.kind][row.entry_id] = {**row.payload, "id": row.entry_id, "deprecated": row.deprecated}
            extensions[_CACHE_KEY] = definitions
        return extensions[_CACHE_KEY]


@event.listens_for(Session, "before_flush")
def _mark_reward_changes(session, _ctx, _instances):
    if has_app_context() and any(isinstance(record, CatalogEntry) and record.kind in _RUNTIME_KINDS
                                 for record in chain(session.new, session.dirty, session.deleted)):
        session.info[_CACHE_KEY] = current_app._get_current_object()


@event.listens_for(Session, "after_commit")
def _invalidate_reward_definitions(session):
    app = session.info.pop(_CACHE_KEY, None)
    if app is not None:
        with _cache_lock:
            app.extensions.pop(_CACHE_KEY, None)


@event.listens_for(Session, "after_rollback")
def _forget_reward_changes(session):
    session.info.pop(_CACHE_KEY, None)


def get_reward(kind, entry_id):
    definitions = _simulation_rewards.get()
    if definitions is not None and entry_id in definitions.get(kind, {}):
        return definitions[kind][entry_id]
    return prepare_rewards().get(kind, {}).get(entry_id)


def available(kind):
    return {key: row for key, row in prepare_rewards().get(kind, {}).items() if not row["deprecated"]}


def _buff_display(key, *, description=False):
    from manager.buff_catalog import get_buff_by_id

    if not key:
        return ""
    buff = get_buff_by_id(key) or {}
    return (buff.get("description") if description else None) or buff.get("display_name") or buff.get("name") or key


def relic_card(item):
    target = item.get("target") or {"type": "all"}
    condition = target.get("condition", "")
    if target["type"] == "nth":
        label = f"開始時の並びで{target['n']}番目"
    elif target["type"] == "condition":
        label = {"hp_lowest": "HPが最も低い味方", "bled_last_round": "前ラウンドで出血した味方"}.get(
            condition, f"タグ「{condition.removeprefix('has_tag:')}」の味方")
    else:
        label = "パーティ全員（控えを含む）"
    return {key: item.get(key) for key in ("id", "name", "category", "rank", "image", "flavor", "buff_id", "cost_buff_id")} | {
        "target": dict(target),
        "target_text": label, "effect_text": _buff_display(item.get("buff_id"), description=True),
        "cost_text": _buff_display(item.get("cost_buff_id"), description=True),
    }


def project_relics(run):
    if "mana_load" not in run:
        return
    definitions = prepare_rewards().get("relic", {})
    def cards(keys):
        return [relic_card(definitions[key]) for key in keys if key in definitions]

    run["relic_cards"] = cards(run["relics"])
    if reward := run.get("reward"):
        reward["cards"] = cards(reward["relic_ids"])
    stages = [{"threshold": row["threshold"], "name": _buff_display(row["buff_id"])}
              for row in sorted(available("hollow_load_stage").values(), key=lambda row: row["threshold"])]
    load = run["mana_load"]
    run["load_stage"] = {"level": sum(row["threshold"] <= load for row in stages), "stages": stages,
                         "next_threshold": next((row["threshold"] for row in stages if row["threshold"] > load), None)}
    for buff in run.get("temp_buffs", []):
        buff["name"] = _buff_display(buff["buff_id"])
