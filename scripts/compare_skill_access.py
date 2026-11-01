"""Compare current skill access with committed pre-optimization code offline."""

from contextlib import ExitStack
import copy
import hashlib
import json
import logging
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "7934f4d"


def forbidden(*args, **kwargs):
    raise RuntimeError("External connections forbidden in comparison")


def main():
    sys.path.insert(0, str(ROOT))
    logging.disable(logging.CRITICAL)
    with ExitStack() as stack:
        stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
        stack.enter_context(patch.object(socket.socket, "connect", forbidden))
        stack.enter_context(patch.object(socket.socket, "connect_ex", forbidden))
        from manager.battle import skill_access, skill_rules, select_resolve_state
        from manager import json_rule_audit
        from scripts.benchmark_state_delivery import synthetic_state

        audit_errors = []
        stack.enter_context(patch.object(json_rule_audit, "append_audit", lambda *args, **kwargs: audit_errors.append(args[0])))
        # json_rule_v2 holds direct references to these audit functions.
        from manager import json_rule_v2
        stack.enter_context(patch.object(json_rule_v2, "append_audit", lambda *args, **kwargs: audit_errors.append(args[0])))
        stack.enter_context(patch.object(json_rule_v2, "append_audit_verbose", lambda *args, **kwargs: None))
        old_source = subprocess.check_output(["git", "show", BASELINE + ":manager/battle/skill_access.py"], cwd=ROOT).decode("utf-8")
        old = ModuleType("skill_access_baseline")
        exec(compile(old_source, "baseline_skill_access.py", "exec"), old.__dict__)
        catalog = json.loads((ROOT / "data/cache/skills_cache.json").read_text(encoding="utf-8"))
        stack.enter_context(patch.object(old, "all_skill_data", catalog))
        stack.enter_context(patch.object(skill_access, "all_skill_data", catalog))
        before_catalog = copy.deepcopy(catalog)
        checked = 0
        for skill_id in list(catalog):
            for fp, instant, slot in ((0, False, "one"), (10, False, "two"), (10, True, "one"), (10, True, "two")):
                actor = {"id": "A", "type": "ally", "mp": fp, "hp": 100,
                         "states": [{"name": "FP", "value": fp}], "flags": {}, "special_buffs": []}
                battle = {"field_effects": [{"scope": "except_source", "source_slot_id": "one", "skill_constraints": [
                    {"id": "extra", "mode": "add_cost", "match": {}, "add_cost": [{"type": "FP", "value": 1}]},
                ]}]}
                expected = old.evaluate_skill_access(copy.deepcopy(actor), skill_id, battle_state=copy.deepcopy(battle), slot_id=slot, allow_instant=instant)
                actual = skill_access.evaluate_skill_access(copy.deepcopy(actor), skill_id, battle_state=copy.deepcopy(battle), slot_id=slot, allow_instant=instant)
                assert expected == actual, f"Different result for {skill_id}"
                checked += 1
        assert before_catalog == catalog, "Input master changed"

        state = synthetic_state(12, 0, 20)
        selected = list(catalog)[:30]
        for actor in state["characters"]:
            actor["commands"] = "\n".join(f"【{skill_id}】" for skill_id in selected)
        from manager.battle.common_manager import ensure_battle_state_vNext
        battle = ensure_battle_state_vNext(state, battle_id="synthetic", round_value=1)
        normalizer = skill_rules.extract_and_normalize_skill_rule_data
        rows = []
        expected_payload = None
        for trial in range(6):
            for label, module in (("before", old), ("after", skill_access)):
                calls = [0]

                def counted(data, **kwargs):
                    calls[0] += 1
                    return normalizer(data, **kwargs)

                sample = copy.deepcopy(state)
                with patch.object(skill_rules, "extract_and_normalize_skill_rule_data", counted):
                    started = time.perf_counter()
                    payload = module_payload = {}
                    for slot_id, slot_info in sample["battle_state"]["slots"].items():
                        actor = next(char for char in sample["characters"] if char["id"] == slot_info["actor_id"])
                        module_payload[slot_id] = module.list_regular_usable_skill_ids(actor, room_state=sample,
                            battle_state=sample["battle_state"], slot_id=slot_id)
                    elapsed_ms = (time.perf_counter() - started) * 1000
                digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                if expected_payload is None:
                    expected_payload = digest
                assert expected_payload == digest, "Available skill lists changed"
                if trial:
                    rows.append({"version": label, "elapsed_ms": elapsed_ms, "normalizations": calls[0]})

        # Check the complete battle payload, not only the available-skill lists.
        snapshots = []
        for module in (old, skill_access):
            sample = copy.deepcopy(state)
            with patch.object(select_resolve_state, "get_room_state", lambda _room: sample), patch.object(
                select_resolve_state, "list_regular_usable_skill_ids", module.list_regular_usable_skill_ids
            ):
                snapshots.append(select_resolve_state.build_select_resolve_state_payload("synthetic", "synthetic"))
        assert snapshots[0] == snapshots[1]
        assert catalog == before_catalog
    report = {"baseline": BASELINE, "scope": "synthetic-offline-not-production", "catalog_skills": len(catalog),
              "equal_access_results": checked, "equal_full_battle_payload": True,
              "characters": 12, "slots": 24, "skills_each": len(selected), "trials": rows,
              "median_ms": {label: statistics.median(row["elapsed_ms"] for row in rows if row["version"] == label)
                            for label in ("before", "after")},
              "normalization_counts": {label: sorted({row["normalizations"] for row in rows if row["version"] == label})
                                       for label in ("before", "after")},
              "master_unchanged": True,
              "source_sha256": hashlib.sha256((ROOT / "manager/battle/skill_access.py").read_bytes()).hexdigest()}
    path = ROOT / "_local/performance/skill_access_comparison.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: value for key, value in report.items() if key != "trials"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
