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


def project_relics(run):
    if "mana_load" not in run:
        return
    definitions = prepare_rewards().get("relic", {})
    fields = ("id", "name", "category", "rank", "image", "flavor", "target", "buff_id", "cost_buff_id")

    def cards(keys):
        return [{field: definitions[key].get(field) for field in fields} for key in keys if key in definitions]

    run["relic_cards"] = cards(run["relics"])
    if reward := run.get("reward"):
        reward["cards"] = cards(reward["relic_ids"])
    stages = sorted(row["threshold"] for row in available("hollow_load_stage").values())
    load = run["mana_load"]
    run["load_stage"] = {"level": sum(threshold <= load for threshold in stages),
                         "next_threshold": next((threshold for threshold in stages if threshold > load), None)}
