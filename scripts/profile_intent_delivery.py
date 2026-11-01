"""Offline diagnostic: real payload code, synthetic state, in-memory SQLite."""

from contextlib import ExitStack
import argparse
import copy
import cProfile
import hashlib
import json
import logging
from pathlib import Path
import pstats
import socket
import statistics
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def forbidden(*args, **kwargs):
    raise RuntimeError("External connection or persistence forbidden in diagnostic")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memo-only", action="store_true", help="Reuse prior profiling rows and run the isolated comparison")
    parser.add_argument("--output", type=Path, default=ROOT / "_local/performance/intent_delivery_profile.json")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    logging.disable(logging.CRITICAL)
    with ExitStack() as guard:
        guard.enter_context(patch("dotenv.load_dotenv", return_value=False))
        guard.enter_context(patch.object(socket.socket, "connect", forbidden))
        guard.enter_context(patch.object(socket.socket, "connect_ex", forbidden))
        from flask import Flask
        from sqlalchemy import event
        from extensions import db, active_room_states, all_skill_data
        from models import User, Room
        from manager import room_manager
        from manager import json_rule_audit
        from manager.battle import common_manager, skill_access, skill_rules
        from events.battle import common_routes
        from scripts.benchmark_state_delivery import synthetic_state

        audit_path = ROOT / "_local/performance/intent_profile_audit.jsonl"
        guard.enter_context(patch.object(json_rule_audit, "AUDIT_LOG_DIR", audit_path.parent))
        guard.enter_context(patch.object(json_rule_audit, "AUDIT_LOG_FILE", audit_path))
        guard.enter_context(patch.object(json_rule_audit, "_dir_ready", False))

        app = Flask("isolated_intent_diagnostic")
        app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
        db.init_app(app)
        cache = json.loads((ROOT / "data/cache/skills_cache.json").read_text(encoding="utf-8"))
        all_skill_data.update(cache)
        skill_ids = list(cache)[:30]
        guard.enter_context(patch.object(room_manager, "save_specific_room_state", forbidden))
        guard.enter_context(patch.object(room_manager.socketio, "start_background_task", forbidden))
        guard.enter_context(patch.object(common_routes, "request", SimpleNamespace(sid="synthetic")))
        with app.app_context():
            db.create_all()
            db.session.add(User(id="synthetic-owner", name="Synthetic owner"))
            db.session.add(Room(name="synthetic", owner_id="synthetic-owner", data={}))
            db.session.commit()
            counters = {"sql": 0, "skill_evaluations": 0, "emits": 0}

            def count_sql(*_args):
                counters["sql"] += 1

            event.listen(db.engine, "before_cursor_execute", count_sql)
            evaluate = skill_access.evaluate_skill_access

            def counted_evaluate(*args, **kwargs):
                counters["skill_evaluations"] += 1
                return evaluate(*args, **kwargs)

            def capture(*_args, **_kwargs):
                counters["emits"] += 1

            guard.enter_context(patch.object(skill_access, "evaluate_skill_access", counted_evaluate))
            guard.enter_context(patch.object(room_manager.socketio, "emit", capture))
            rows = []
            for chars, skills in (() if args.memo_only else ((4, 0), (4, 10), (4, 30), (12, 30))):
                baseline = synthetic_state(chars, 0, 20)
                for actor in baseline["characters"]:
                    actor["commands"] = "\n".join(f"【{sid}】" for sid in skill_ids[:skills])
                common_manager.ensure_battle_state_vNext(baseline, battle_id="synthetic", round_value=1)
                for ready in (False, True):
                    for mode in ("delivery", "delivery_then_commit_ready_check"):
                        times, last_counts = [], None
                        profile = cProfile.Profile()
                        for trial in range(4):
                            state = copy.deepcopy(baseline)
                            battle = state["battle_state"]
                            if ready:
                                battle["intents"] = {sid: {"committed": True} for sid in battle["slots"]}
                            active_room_states["synthetic"] = state
                            counters.update(sql=0, skill_evaluations=0, emits=0)
                            if trial == 3:
                                profile.enable()
                            started = time.perf_counter()
                            common_routes._emit_battle_state_updated("synthetic", "synthetic")
                            if mode != "delivery":
                                common_routes._maybe_advance_phase_to_resolve_mass("synthetic", "synthetic", battle)
                            elapsed = (time.perf_counter() - started) * 1000
                            if trial == 3:
                                profile.disable()
                            else:
                                times.append(elapsed)
                            last_counts = dict(counters)
                        stats = pstats.Stats(profile)
                        top = sorted(stats.stats.items(), key=lambda pair: pair[1][3], reverse=True)[:15]
                        rows.append({
                            "characters": chars, "skills_each": skills, "all_committed": ready, "mode": mode,
                            "median_ms": statistics.median(times), **last_counts,
                            "profile": [{"file": Path(key[0]).name, "line": key[1], "function": key[2],
                                         "calls": value[1], "cumulative_ms": value[3] * 1000}
                                        for key, value in top],
                        })
            # Counterfactual only: no production code or long-lived cache changes.
            baseline = synthetic_state(12, 0, 20)
            for actor in baseline["characters"]:
                actor["commands"] = "\n".join(f"【{sid}】" for sid in skill_ids)
            common_manager.ensure_battle_state_vNext(baseline, battle_id="synthetic", round_value=1)
            normalize = skill_rules.extract_and_normalize_skill_rule_data
            comparison = []
            expected_payload = None
            master_before = json.dumps(cache, sort_keys=True)
            for trial in range(4):
                for memoize in (False, True):
                    active_room_states["synthetic"] = copy.deepcopy(baseline)
                    counters.update(sql=0, skill_evaluations=0, emits=0)
                    memo = {}
                    normalizations = [0]
                    payload_hashes = []

                    def normalize_once(data, **kwargs):
                        key = (id(data), tuple(sorted(kwargs.items())))
                        if not memoize or key not in memo:
                            normalizations[0] += 1
                            value = normalize(data, **kwargs)
                            if not memoize:
                                return value
                            memo[key] = value
                        return copy.deepcopy(memo[key])

                    def capture_payload(name, payload, **kwargs):
                        counters["emits"] += 1
                        payload_hashes.append(hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())

                    with patch.object(skill_rules, "extract_and_normalize_skill_rule_data", normalize_once), patch.object(room_manager.socketio, "emit", capture_payload):
                        started = time.perf_counter()
                        common_routes._emit_battle_state_updated("synthetic", "synthetic")
                        elapsed = (time.perf_counter() - started) * 1000
                    assert len(payload_hashes) == 1
                    if expected_payload is None:
                        expected_payload = payload_hashes[0]
                    assert payload_hashes[0] == expected_payload, "Counterfactual changed the state payload"
                    if trial:
                        comparison.append({"memoize": memoize, "elapsed_ms": elapsed,
                                           "normalizations": normalizations[0], **counters})
            assert master_before == json.dumps(cache, sort_keys=True), "Master input changed"
            active_room_states.clear()
            db.session.remove()
            db.engine.dispose()
    path = args.output
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                     for name in ("manager/room_manager.py", "manager/battle/skill_access.py",
                                  "manager/battle/select_resolve_state.py", "events/battle/common_routes.py")}
    if args.memo_only:
        previous = json.loads(path.read_text(encoding="utf-8"))
        assert previous["source_sha256"] == source_hashes, "Sources changed; rerun the full profile"
        rows = previous["rows"]
    report = {"scope": "synthetic-offline-not-production", "rows": rows,
              "counterfactual": {"characters": 12, "skills_each": len(skill_ids), "trials": comparison,
                                 "equal_payload_sha256": expected_payload, "master_unchanged": True},
              "source_sha256": source_hashes}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    for row in rows:
        print({key: value for key, value in row.items() if key != "profile"})
    print("COUNTERFACTUAL", comparison)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
