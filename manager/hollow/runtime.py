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
            definitions = {kind: {} for kind in REWARD_KINDS}
            for row in CatalogEntry.query.filter(CatalogEntry.kind.in_(REWARD_KINDS)):
                definitions[row.kind][row.entry_id] = {**row.payload, "id": row.entry_id}
            extensions[_CACHE_KEY] = definitions
        return extensions[_CACHE_KEY]


@event.listens_for(Session, "before_flush")
def _mark_reward_changes(session, _ctx, _instances):
    if has_app_context() and any(isinstance(record, CatalogEntry) and record.kind in REWARD_KINDS
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
