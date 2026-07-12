from __future__ import annotations

import argparse
import json
import random
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class _StdoutSink:
    def write(self, _text):
        return 0

    def flush(self):
        return None


if __name__ == "__main__":
    with redirect_stdout(_StdoutSink()):
        from manager.sim import battle_runner
        from manager.sim.battle_runner import (
            AllyTargetPolicy,
            IntentProvider,
            RollMode,
            auto_commit_ally_intents,
            build_deterministic_roll_dice,
            run_battle,
        )
        from manager.sim.preset_loader import (
            PresetSide,
            build_room_state_from_presets,
            load_preset_store_from_path,
        )
        from manager.sim.reporting import (
            BattleReport,
            BattleSummary,
            CharacterSnapshot,
            RoundSummary,
            SideSummary,
            aggregate_reports,
            format_aggregate,
            format_report,
        )
else:
    from manager.sim import battle_runner
    from manager.sim.battle_runner import (
        AllyTargetPolicy,
        IntentProvider,
        RollMode,
        auto_commit_ally_intents,
        build_deterministic_roll_dice,
        run_battle,
    )
    from manager.sim.preset_loader import (
        PresetSide,
        build_room_state_from_presets,
        load_preset_store_from_path,
    )
    from manager.sim.reporting import (
        BattleReport,
        BattleSummary,
        CharacterSnapshot,
        RoundSummary,
        SideSummary,
        aggregate_reports,
        format_aggregate,
        format_report,
    )


def _load_room_state(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError("input JSON must be a room_state object")
    return payload


def _using_preset_cli_input(args) -> bool:
    return any(
        [
            args.preset_store,
            args.ally_preset_id,
            args.enemy_preset_id,
            args.ally_formation_id,
            args.enemy_formation_id,
            args.stage_id,
        ]
    )


def _using_list_cli(args) -> bool:
    return any([
        args.list_presets,
        args.list_stages,
        args.list_ally_formations,
        args.list_enemy_formations,
    ])


def _entry_name(entry: dict) -> str:
    return str(entry.get("name") or entry.get("title") or entry.get("id") or "")


def _sorted_entries(mapping: dict) -> list[dict]:
    if not isinstance(mapping, dict):
        return []
    entries = []
    for key, value in mapping.items():
        if not isinstance(value, dict):
            continue
        row = dict(value)
        row["id"] = str(row.get("id") or key)
        entries.append(row)
    entries.sort(key=lambda row: row.get("id", ""))
    return entries


def _catalog_payload(args) -> dict:
    store = load_preset_store_from_path(args.preset_store)
    payload = {}
    if args.list_presets:
        payload["character_presets"] = [
            {
                "id": row.get("id"),
                "name": _entry_name(row),
                "allow_ally": row.get("allow_ally"),
                "allow_enemy": row.get("allow_enemy"),
            }
            for row in _sorted_entries(store.get("character_presets", {}))
        ]
    if args.list_stages:
        payload["stage_presets"] = [
            {
                "id": row.get("id"),
                "name": _entry_name(row),
                "ally_formation_id": row.get("ally_formation_id"),
                "enemy_formation_id": row.get("enemy_formation_id"),
                "required_ally_count": row.get("required_ally_count"),
            }
            for row in _sorted_entries(store.get("stage_presets", {}))
        ]
    if args.list_ally_formations:
        payload["ally_formations"] = [
            {
                "id": row.get("id"),
                "name": _entry_name(row),
                "member_count": len(row.get("members") or []),
            }
            for row in _sorted_entries(store.get("ally_formations", {}))
        ]
    if args.list_enemy_formations:
        payload["enemy_formations"] = [
            {
                "id": row.get("id"),
                "name": _entry_name(row),
                "member_count": len(row.get("members") or []),
            }
            for row in _sorted_entries(store.get("enemy_formations", {}))
        ]
    return payload


def _format_catalog(payload: dict) -> str:
    lines = []
    for section, rows in payload.items():
        lines.append(f"{section}:")
        if not rows:
            lines.append("  - (none)")
            continue
        for row in rows:
            extras = []
            for key, value in row.items():
                if key in {"id", "name"} or value in (None, ""):
                    continue
                extras.append(f"{key}={value}")
            suffix = f" | {', '.join(extras)}" if extras else ""
            lines.append(f"  - {row.get('id')} | {row.get('name')}{suffix}")
    return "\n".join(lines)


def _load_room_state_from_args(args) -> dict:
    if args.input and _using_preset_cli_input(args):
        raise ValueError("--input cannot be combined with preset or formation options")
    if args.input:
        return _load_room_state(args.input)
    if not _using_preset_cli_input(args):
        raise ValueError("--input or preset/formation/stage options are required")

    store = load_preset_store_from_path(args.preset_store)
    return build_room_state_from_presets(
        store=store,
        ally_preset_ids=args.ally_preset_id,
        enemy_preset_ids=args.enemy_preset_id,
        ally_formation_id=args.ally_formation_id,
        enemy_formation_id=args.enemy_formation_id,
        stage_id=args.stage_id,
    )


def _report_payload(report: BattleReport, roll_mode: str, run_index: int | None = None) -> dict:
    payload = report.to_dict()
    payload["roll_mode"] = roll_mode
    if run_index is not None:
        payload["run_index"] = run_index
    return payload


def _run_cli_reports(args) -> list[tuple[str, list[BattleReport]]]:
    if args.runs <= 0:
        raise ValueError("--runs must be positive")
    room_state = _load_room_state_from_args(args)
    roll_modes = ["low", "median", "high"] if args.roll_mode == "all" else [args.roll_mode]
    reports = []
    for mode_index, roll_mode in enumerate(roll_modes):
        run_reports = []
        for run_index in range(args.runs):
            if args.seed is not None:
                random.seed(int(args.seed) + (mode_index * 100000) + run_index)
            report = run_battle(
                room_state,
                room=args.room,
                max_rounds=args.max_rounds,
                roll_mode=roll_mode,
                auto_ally_intents=args.auto_ally_intents,
                ally_target_policy=args.ally_target_policy,
            )
            run_reports.append(report)
        reports.append((roll_mode, run_reports))
    return reports


def _format_cli_reports(reports: list[tuple[str, list[BattleReport]]]) -> str:
    chunks = []
    for roll_mode, run_reports in reports:
        if len(run_reports) == 1:
            chunks.append(f"roll_mode: {roll_mode}\n{format_report(run_reports[0])}")
            continue
        aggregate = aggregate_reports(run_reports)
        run_lines = [
            f"  - run {idx}: result={report.result}, rounds={report.rounds}, "
            f"stalled={str(report.stalled).lower()}, stall_reason={report.stall_reason or '-'}"
            for idx, report in enumerate(run_reports, start=1)
        ]
        chunks.append(
            f"roll_mode: {roll_mode}\n"
            f"{format_aggregate(aggregate)}\n"
            "runs_detail:\n"
            + "\n".join(run_lines)
        )
    return "\n\n".join(chunks)


def _json_output_for_reports(reports: list[tuple[str, list[BattleReport]]]):
    if all(len(run_reports) == 1 for _roll_mode, run_reports in reports):
        payloads = [_report_payload(run_reports[0], roll_mode) for roll_mode, run_reports in reports]
        return payloads[0] if len(payloads) == 1 else payloads

    payloads = []
    for roll_mode, run_reports in reports:
        payloads.append({
            "roll_mode": roll_mode,
            "aggregate": aggregate_reports(run_reports).to_dict(),
            "runs": [
                _report_payload(report, roll_mode, run_index=idx)
                for idx, report in enumerate(run_reports, start=1)
            ],
        })
    return payloads[0] if len(payloads) == 1 else payloads


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a headless battle balance simulation.")
    parser.add_argument("--input", help="Path to a room_state JSON file.")
    parser.add_argument(
        "--preset-store",
        help="Optional path to a battle_only_presets cache JSON. Defaults to the app cache.",
    )
    parser.add_argument(
        "--ally-preset-id",
        action="append",
        help="Character preset id to add as an ally. Can be specified multiple times.",
    )
    parser.add_argument(
        "--enemy-preset-id",
        action="append",
        help="Character preset id to add as an enemy. Can be specified multiple times.",
    )
    parser.add_argument("--ally-formation-id", help="Ally formation id from the battle-only preset store.")
    parser.add_argument("--enemy-formation-id", help="Enemy formation id from the battle-only preset store.")
    parser.add_argument("--stage-id", help="Stage preset id. Formation ids are inherited from the stage unless overridden.")
    parser.add_argument("--list-presets", action="store_true", help="List character presets and exit.")
    parser.add_argument("--list-stages", action="store_true", help="List stage presets and exit.")
    parser.add_argument("--list-ally-formations", action="store_true", help="List ally formations and exit.")
    parser.add_argument("--list-enemy-formations", action="store_true", help="List enemy formations and exit.")
    parser.add_argument(
        "--roll-mode",
        choices=["random", "low", "median", "high", "all"],
        default="median",
        help="Dice mode. 'all' runs low/median/high.",
    )
    parser.add_argument("--max-rounds", type=int, default=10, help="Maximum rounds before reporting a stall.")
    parser.add_argument("--runs", type=int, default=1, help="Number of simulations to run per roll mode.")
    parser.add_argument("--seed", type=int, help="Base random seed. Each run offsets this value by run index.")
    parser.add_argument("--room", default="sim_room", help="Synthetic room id used during the simulation.")
    parser.add_argument(
        "--auto-ally-intents",
        action="store_true",
        help="Auto-commit ally intents with the simulator's simple ally AI wrapper.",
    )
    parser.add_argument(
        "--ally-target-policy",
        choices=["first_alive_enemy", "lowest_hp_enemy"],
        default="first_alive_enemy",
        help="Target policy used with --auto-ally-intents.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a console report.")
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        if _using_list_cli(args):
            with redirect_stdout(_StdoutSink()):
                catalog = _catalog_payload(args)
            if args.json:
                print(json.dumps(catalog, ensure_ascii=False, indent=2))
            else:
                print(_format_catalog(catalog))
            return 0
        with redirect_stdout(_StdoutSink()):
            reports = _run_cli_reports(args)
    except Exception as exc:
        parser.exit(2, f"simulate_battle: {exc}\n")

    if args.json:
        print(json.dumps(_json_output_for_reports(reports), ensure_ascii=False, indent=2))
    else:
        print(_format_cli_reports(reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BattleReport",
    "CharacterSnapshot",
    "AllyTargetPolicy",
    "BattleSummary",
    "IntentProvider",
    "PresetSide",
    "RoundSummary",
    "RollMode",
    "SideSummary",
    "auto_commit_ally_intents",
    "battle_runner",
    "build_deterministic_roll_dice",
    "build_arg_parser",
    "build_room_state_from_presets",
    "format_report",
    "main",
    "run_battle",
]
