"""Contracts for isolated, repeatable state delivery measurements."""

import json
import os
import subprocess
import sys

import pytest

from scripts import benchmark_state_delivery as benchmark


def test_summary_uses_nearest_rank_percentile_and_separates_first_call():
    result = benchmark.summarize([100, *range(1, 101)])
    assert result == {"first_ms": 100, "p50_ms": 50.5, "p95_ms": 95, "max_ms": 100}


def test_capture_counts_encoded_utf8_not_character_length():
    from socketio.packet import Packet, EVENT

    capture = benchmark.Capture()
    capture.emit("state_updated", {"message": "合成ログ"}, to="synthetic")
    encoded = Packet(EVENT, ["state_updated", {"message": "合成ログ"}]).encode()
    assert capture.events == [{"name": "state_updated", "packet_bytes": len(encoded.encode("utf-8"))}]
    assert capture.encode_ms >= 0


def test_network_and_database_access_are_rejected():
    import socket
    from sqlalchemy import create_engine

    with benchmark.isolated_runtime():
        with socket.socket() as client:
            with pytest.raises(RuntimeError, match="disabled"):
                client.connect(("127.0.0.1", 1))
        with pytest.raises(RuntimeError, match="disabled"):
            create_engine("sqlite://").connect()


def test_standalone_measurement_reports_two_real_events_without_payload(tmp_path):
    output = tmp_path / "measurement.json"
    env = os.environ.copy()
    env.update(PYTHONIOENCODING="utf-8", DATABASE_URL="forbidden-secret-url")
    result = subprocess.run(
        [sys.executable, str(benchmark.ROOT / "scripts/benchmark_state_delivery.py"),
         "--samples", "3", "--warmup", "1", "--output", str(output)],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    text = output.read_text(encoding="utf-8")
    assert "forbidden-secret-url" not in text + result.stdout + result.stderr
    report = json.loads(text)
    assert report["scope"] == "synthetic-local-state-delivery"
    for case in report["cases"]:
        assert [event["name"] for event in case["events"]] == ["state_updated", "battle_state_updated"]
        assert case["samples"] == 3
        assert case["total_packet_bytes"] == sum(event["packet_bytes"] for event in case["events"])
        assert case["timings"]["total_ms"]["max_ms"] >= 0
        assert "characters" not in case and "payload" not in case
    assert report["cases"][2]["total_packet_bytes"] > report["cases"][0]["total_packet_bytes"]


def test_invalid_sample_count_is_rejected_before_measurement(tmp_path):
    result = subprocess.run(
        [sys.executable, str(benchmark.ROOT / "scripts/benchmark_state_delivery.py"),
         "--samples", "0", "--output", str(tmp_path / "invalid.json")],
        capture_output=True, timeout=30,
    )
    assert result.returncode != 0
    assert not (tmp_path / "invalid.json").exists()
