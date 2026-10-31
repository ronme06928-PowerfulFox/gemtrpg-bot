"""Ephemeral, opt-in timing for one Socket.IO intent request."""

from contextvars import ContextVar
from functools import wraps
import re
import time


_measurement = ContextVar("intent_performance", default=None)
_VALID_ID = re.compile(r"[A-Za-z0-9_-]{16,64}\Z")


def measure_intent(handler):
    @wraps(handler)
    def measured(data):
        request_id = data.get("_intent_perf_id") if isinstance(data, dict) else None
        if not isinstance(request_id, str) or not _VALID_ID.fullmatch(request_id):
            return handler(data)
        record = {"id": request_id, "stages_ms": {}, "state_emitted": False}
        token = _measurement.set(record)
        started = time.perf_counter()
        try:
            handler(data)
            record["handler_ms"] = (time.perf_counter() - started) * 1000
            return {"intent_perf": record}
        finally:
            _measurement.reset(token)
    return measured


def measure_stage(name):
    def decorate(function):
        @wraps(function)
        def measured(*args, **kwargs):
            record = _measurement.get()
            if record is None:
                return function(*args, **kwargs)
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                stages = record["stages_ms"]
                stages[name] = stages.get(name, 0) + (time.perf_counter() - started) * 1000
        return measured
    return decorate


def tag_state_payload(payload):
    record = _measurement.get()
    if record is None:
        return payload
    record["state_emitted"] = True
    # Do not put diagnostic IDs into the memory state or a persisted intent.
    return {**payload, "_intent_perf": {"id": record["id"]}}
