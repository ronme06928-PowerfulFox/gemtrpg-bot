"""Opt-in timing must preserve business behavior and isolate requests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from events.battle.intent_performance import measure_intent, measure_stage, tag_state_payload


@pytest.mark.parametrize("data", [{}, {"_intent_perf_id": "short"}, {"_intent_perf_id": "x" * 65}, {"_intent_perf_id": []}])
def test_disabled_or_invalid_measurement_preserves_result_and_arguments(data):
    result = object()

    @measure_intent
    def handler(payload):
        assert payload is data
        return result

    assert handler(data) is result


def test_timing_metadata_never_mutates_or_persists_in_source_state():
    payload = {"intents": {"slot": {"committed": True}}}
    emitted = []

    @measure_stage("redirect_ms")
    def redirect():
        return 7

    @measure_intent
    def handler(_data):
        assert redirect() == 7
        emitted.append(tag_state_payload(payload))

    ack = handler({"_intent_perf_id": "request-0123456789"})["intent_perf"]
    assert ack["id"] == "request-0123456789"
    assert ack["state_emitted"] is True
    assert ack["handler_ms"] >= ack["stages_ms"]["redirect_ms"] >= 0
    assert emitted[0]["_intent_perf"] == {"id": ack["id"]}
    assert "_intent_perf" not in payload
    assert emitted[0]["intents"] is payload["intents"]
    assert tag_state_payload(payload) is payload


def test_rejected_handler_is_not_reported_as_a_state_update():
    @measure_intent
    def rejected(_data):
        return None

    ack = rejected({"_intent_perf_id": "rejected-0123456789"})
    assert ack["intent_perf"]["state_emitted"] is False


def test_exception_propagates_and_context_is_cleared():
    @measure_intent
    def broken(_data):
        raise RuntimeError("business failure")

    with pytest.raises(RuntimeError, match="business failure"):
        broken({"_intent_perf_id": "exception-0123456789"})
    payload = {}
    assert tag_state_payload(payload) is payload


def test_concurrent_requests_have_independent_ids():
    barrier = Barrier(2)

    @measure_intent
    def handler(_data):
        barrier.wait(timeout=5)
        assert tag_state_payload({})["_intent_perf"]["id"] == _data["_intent_perf_id"]

    ids = ["thread-first-0123456789", "thread-second-0123456789"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(handler, [{"_intent_perf_id": value} for value in ids]))
    assert [row["intent_perf"]["id"] for row in results] == ids


def test_greenlet_switches_keep_independent_measurement_contexts():
    from greenlet import getcurrent, greenlet

    @measure_intent
    def handler(data):
        getcurrent().parent.switch()
        assert tag_state_payload({})["_intent_perf"]["id"] == data["_intent_perf_id"]

    first, second = greenlet(handler), greenlet(handler)
    first.switch({"_intent_perf_id": "greenlet-first-0123456789"})
    second.switch({"_intent_perf_id": "greenlet-second-0123456789"})
    assert first.switch()["intent_perf"]["id"] == "greenlet-first-0123456789"
    assert second.switch()["intent_perf"]["id"] == "greenlet-second-0123456789"
    assert tag_state_payload({}) == {}


def test_socketio_returns_ack_and_existing_state_event():
    from flask import Flask
    from flask_socketio import SocketIO, emit

    app = Flask("timing_probe")
    app.config["SECRET_KEY"] = "synthetic-test"
    io = SocketIO(app, async_mode="threading")

    @io.on("probe")
    @measure_intent
    def probe(_data):
        emit("battle_state_updated", tag_state_payload({"intents": {}}))

    client = io.test_client(app)
    try:
        ack = client.emit("probe", {"_intent_perf_id": "socket-0123456789"}, callback=True)
        assert ack["intent_perf"]["state_emitted"] is True
        events = client.get_received()
        assert events[0]["name"] == "battle_state_updated"
        assert events[0]["args"][0]["_intent_perf"]["id"] == ack["intent_perf"]["id"]
        assert client.emit("probe", {}, callback=True) == []
        assert "_intent_perf" not in client.get_received()[0]["args"][0]
    finally:
        client.disconnect()
