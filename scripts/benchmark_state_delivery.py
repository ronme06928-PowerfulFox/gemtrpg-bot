"""Measure synthetic state delivery offline, without starting the application."""

from contextlib import contextmanager, ExitStack
import copy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import logging
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from unittest.mock import patch
import argparse


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (("small", 6, 0, 20), ("medium", 12, 6, 200), ("stress", 48, 20, 500))


def _forbidden(*_args, **_kwargs):
    raise RuntimeError("Network, database and persistence access disabled for benchmark")


@contextmanager
def isolated_runtime():
    with ExitStack() as stack:
        stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
        stack.enter_context(patch("socket.socket.connect", _forbidden))
        stack.enter_context(patch("socket.socket.connect_ex", _forbidden))
        stack.enter_context(patch("sqlalchemy.engine.Engine.connect", _forbidden))
        yield stack


def summarize(values):
    steady = sorted(values[1:])
    return {
        "first_ms": round(values[0], 6),
        "p50_ms": round(statistics.median(steady), 6),
        "p95_ms": round(steady[math.ceil(len(steady) * .95) - 1], 6),
        "max_ms": round(max(steady), 6),
    }


class Capture:
    def __init__(self):
        self.events = []
        self.encode_ms = 0

    def emit(self, name, payload, **_kwargs):
        from socketio.packet import Packet, EVENT

        started = time.perf_counter()
        encoded = Packet(EVENT, [name, payload]).encode()
        self.encode_ms += (time.perf_counter() - started) * 1000
        self.events.append({"name": name, "packet_bytes": len(encoded.encode("utf-8"))})


def synthetic_state(character_count, buffs_per_character, log_count):
    characters, timeline = [], []
    for index in range(character_count):
        actor_id = f"actor-{index:03}"
        characters.append({
            "id": actor_id, "name": f"合成キャラ{index}", "type": "ally" if index % 2 else "enemy",
            "hp": 100, "maxHp": 100, "mp": 50, "maxMp": 50, "x": index % 10, "y": index // 10,
            "states": [{"name": "FP", "value": 3}],
            "params": [{"label": "敏捷", "value": 10}], "flags": {}, "skills": [],
            "special_buffs": [{"name": f"合成バフ{buff}", "buff_id": f"synthetic-{buff}",
                               "lasting": 3, "delay": 0, "count": 1}
                              for buff in range(buffs_per_character)],
        })
        for slot in range(2):
            timeline.append({"id": f"{actor_id}:r1:s{slot}", "char_id": actor_id,
                             "speed": 10 + slot, "acted": False})
    return {
        "round": 1, "play_mode": "normal", "characters": characters, "timeline": timeline,
        "logs": [{"log_id": index, "message": f"合成ログ{index}: " + "効果と状態の確認。" * 8,
                  "type": "info", "timestamp": 0} for index in range(log_count)],
        "battle_only": {"preset_bookmarks": ["synthetic-private-metadata"]},
        "character_owners": {}, "battle_state": {},
    }


def measure_case(spec, samples, warmup):
    from manager import room_manager
    from manager.battle import common_manager
    from manager.battle import select_resolve_state

    name, chars, buffs, logs = spec
    baseline = synthetic_state(chars, buffs, logs)
    common_manager.ensure_battle_state_vNext(baseline, battle_id="battle_synthetic", round_value=1)
    state = None
    durations = {key: [] for key in ("total_ms", "participant_build_ms", "battle_payload_build_ms", "packet_encode_ms")}
    original_participant = room_manager.build_participant_state
    original_battle = common_manager.build_select_resolve_state_payload
    measurements = {}

    def timed(key, function):
        def call(*args, **kwargs):
            started = time.perf_counter()
            result = function(*args, **kwargs)
            measurements[key] = measurements.get(key, 0) + (time.perf_counter() - started) * 1000
            return result
        return call

    with ExitStack() as stack:
        for module in (room_manager, common_manager, select_resolve_state):
            stack.enter_context(patch.object(module, "get_room_state", lambda _room: state))
        stack.enter_context(patch.object(room_manager, "_PERF_LOG", False))
        stack.enter_context(patch.object(room_manager, "_read_room_db_row", _forbidden))
        stack.enter_context(patch.object(room_manager, "save_specific_room_state", _forbidden))
        stack.enter_context(patch.object(room_manager.socketio, "start_background_task", _forbidden))
        stack.enter_context(patch.object(room_manager, "build_participant_state", timed("participant_build_ms", original_participant)))
        stack.enter_context(patch.object(common_manager, "build_select_resolve_state_payload", timed("battle_payload_build_ms", original_battle)))
        for index in range(1 + warmup + samples):
            state = copy.deepcopy(baseline)
            capture = Capture()
            measurements.clear()
            with patch.object(room_manager.socketio, "emit", capture.emit):
                started = time.perf_counter()
                room_manager.broadcast_state_update("synthetic")
                total = (time.perf_counter() - started) * 1000
            if [event["name"] for event in capture.events] != ["state_updated", "battle_state_updated"]:
                raise RuntimeError("Expected both state delivery events; measurement is incomplete")
            measurements.update(total_ms=total, packet_encode_ms=capture.encode_ms)
            if index == 0 or index > warmup:
                for key in durations:
                    durations[key].append(measurements[key])
    participant = original_participant(baseline)
    return {
        "scenario": name, "character_count": chars, "slot_count": chars * 2,
        "buffs_per_character": buffs, "log_count": logs, "samples": samples, "warmup": warmup,
        "intent_count": 0, "trace_count": 0, "startup_skill_catalog": "not loaded; system skills registered",
        "events": capture.events, "total_packet_bytes": sum(event["packet_bytes"] for event in capture.events),
        "participant_json_field_bytes": {
            key: len(json.dumps(participant[key], ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
            for key in ("characters", "logs", "battle_state", "timeline")
        },
        "timings": {key: summarize(values) for key, values in durations.items()},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--output", type=Path, default=ROOT / "_local/performance/state_delivery.json")
    args = parser.parse_args(argv)
    if not 1 <= args.samples <= 10000 or not 0 <= args.warmup <= 1000:
        parser.error("samples must be 1..10000 and warmup 0..1000")
    sys.path.insert(0, str(ROOT))
    disabled_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with isolated_runtime():
            cases = [measure_case(spec, args.samples, args.warmup) for spec in SCENARIOS]
    finally:
        logging.disable(disabled_level)
    sources = ("manager/room_manager.py", "manager/battle/common_manager.py", "manager/battle/select_resolve_state.py", "scripts/benchmark_state_delivery.py")
    report = {
        "scope": "synthetic-local-state-delivery", "created_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "python_socketio": version("python-socketio"),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "worktree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
        "excludes": ["application startup", "DB", "network", "compression", "Engine.IO framing", "browser", "combat calculation"],
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Synthetic state delivery measurement saved: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
