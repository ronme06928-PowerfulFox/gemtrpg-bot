"""Resolve Hollow definitions by ID without modifying the public catalogs."""
from contextlib import contextmanager
from contextvars import ContextVar

from flask import has_app_context
from models import CatalogEntry

_simulation_rewards = ContextVar("simulation_hollow_rewards", default=None)


@contextmanager
def simulation_rewards(definitions):
    token = _simulation_rewards.set(definitions)
    try:
        yield
    finally:
        _simulation_rewards.reset(token)


def get_reward(kind, entry_id):
    definitions = _simulation_rewards.get()
    if definitions is not None and entry_id in definitions.get(kind, {}):
        return definitions[kind][entry_id]
    if not has_app_context():
        return None
    row = CatalogEntry.query.filter_by(kind=kind, entry_id=entry_id).first()
    return {**row.payload, "id": entry_id} if row is not None else None
