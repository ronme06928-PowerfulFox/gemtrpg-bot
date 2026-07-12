from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class CharacterSnapshot:
    id: str
    name: str
    team: str
    hp: int
    max_hp: int


@dataclass
class SideSummary:
    alive_count: int = 0
    total_count: int = 0
    hp: int = 0
    max_hp: int = 0
    hp_rate: float = 0.0


@dataclass
class BattleSummary:
    ally: SideSummary = field(default_factory=SideSummary)
    enemy: SideSummary = field(default_factory=SideSummary)


@dataclass
class RoundSummary:
    round: int
    result: str
    committed_intents: int
    ally_hp: int
    enemy_hp: int
    hp_delta: int


@dataclass
class BattleReport:
    result: str
    rounds: int
    stalled: bool
    max_rounds: int
    characters: list[CharacterSnapshot]
    summary: BattleSummary = field(default_factory=BattleSummary)
    stall_reason: str | None = None
    rounds_detail: list[RoundSummary] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SimulationAggregate:
    runs: int
    result_counts: dict[str, int]
    stall_reason_counts: dict[str, int]
    ally_win_rate: float
    enemy_win_rate: float
    draw_rate: float
    stall_rate: float
    avg_rounds: float
    avg_ally_hp_rate: float
    avg_enemy_hp_rate: float

    def to_dict(self) -> dict:
        return asdict(self)


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def snapshot_characters(state: dict) -> list[CharacterSnapshot]:
    snapshots = []
    for char in state.get("characters", []) or []:
        if not isinstance(char, dict):
            continue
        snapshots.append(
            CharacterSnapshot(
                id=str(char.get("id") or ""),
                name=str(char.get("name") or char.get("id") or ""),
                team=str(char.get("type") or char.get("team") or ""),
                hp=safe_int(char.get("hp"), 0),
                max_hp=safe_int(char.get("maxHp"), 0),
            )
        )
    return snapshots


def _team_key(char: dict | CharacterSnapshot) -> str:
    if isinstance(char, CharacterSnapshot):
        return str(char.team or "").strip().lower()
    if not isinstance(char, dict):
        return ""
    return str(char.get("type") or char.get("team") or "").strip().lower()


def _hp_pair(char: dict | CharacterSnapshot) -> tuple[int, int]:
    if isinstance(char, CharacterSnapshot):
        return safe_int(char.hp), safe_int(char.max_hp)
    if not isinstance(char, dict):
        return 0, 0
    return safe_int(char.get("hp"), 0), safe_int(char.get("maxHp"), 0)


def side_summary(characters: list[dict] | list[CharacterSnapshot], side: str) -> SideSummary:
    total_count = 0
    alive_count = 0
    hp_total = 0
    max_hp_total = 0
    for char in characters:
        if _team_key(char) != side:
            continue
        hp, max_hp = _hp_pair(char)
        total_count += 1
        if hp > 0:
            alive_count += 1
        hp_total += max(0, hp)
        max_hp_total += max(0, max_hp)
    hp_rate = round(hp_total / max_hp_total, 4) if max_hp_total > 0 else 0.0
    return SideSummary(
        alive_count=alive_count,
        total_count=total_count,
        hp=hp_total,
        max_hp=max_hp_total,
        hp_rate=hp_rate,
    )


def battle_summary_from_characters(characters: list[dict] | list[CharacterSnapshot]) -> BattleSummary:
    return BattleSummary(
        ally=side_summary(characters, "ally"),
        enemy=side_summary(characters, "enemy"),
    )


def battle_summary(state: dict) -> BattleSummary:
    characters = state.get("characters", []) if isinstance(state, dict) else []
    return battle_summary_from_characters(characters if isinstance(characters, list) else [])


def total_hp_for_progress(state: dict) -> int:
    summary = battle_summary(state)
    return summary.ally.hp + summary.enemy.hp


def committed_intent_count(battle_state: dict) -> int:
    intents = battle_state.get("intents", {}) if isinstance(battle_state, dict) else {}
    if not isinstance(intents, dict):
        return 0
    return sum(1 for intent in intents.values() if isinstance(intent, dict) and intent.get("committed") is True)


def round_summary(state: dict, round_value: int, result: str, committed_intents: int, hp_before: int) -> RoundSummary:
    summary = battle_summary(state)
    hp_after = summary.ally.hp + summary.enemy.hp
    return RoundSummary(
        round=round_value,
        result=result,
        committed_intents=committed_intents,
        ally_hp=summary.ally.hp,
        enemy_hp=summary.enemy.hp,
        hp_delta=hp_before - hp_after,
    )


def stall_reason(result: str, rounds: int, max_rounds: int, rounds_detail: list[RoundSummary]) -> str | None:
    if result == "invalid_state":
        return "invalid_battle_state"
    if result != "in_progress":
        return None
    if rounds < max_rounds:
        return "unknown"
    if rounds_detail and rounds_detail[-1].committed_intents <= 0:
        return "no_committed_intents"
    if rounds_detail and all(row.hp_delta <= 0 for row in rounds_detail):
        return "no_damage_progress"
    return "max_rounds_reached"


def format_report(report: BattleReport) -> str:
    lines = [
        f"result: {report.result}",
        f"rounds: {report.rounds}",
        f"stalled: {str(report.stalled).lower()}",
        f"stall_reason: {report.stall_reason or '-'}",
        (
            "summary: "
            f"ally {report.summary.ally.alive_count}/{report.summary.ally.total_count} "
            f"HP {report.summary.ally.hp}/{report.summary.ally.max_hp} "
            f"({report.summary.ally.hp_rate:.0%}), "
            f"enemy {report.summary.enemy.alive_count}/{report.summary.enemy.total_count} "
            f"HP {report.summary.enemy.hp}/{report.summary.enemy.max_hp} "
            f"({report.summary.enemy.hp_rate:.0%})"
        ),
        "rounds_detail:",
    ]
    for row in report.rounds_detail:
        lines.append(
            "  - "
            f"round {row.round}: result={row.result}, intents={row.committed_intents}, "
            f"hp_delta={row.hp_delta}, ally_hp={row.ally_hp}, enemy_hp={row.enemy_hp}"
        )
    lines.append("characters:")
    for char in report.characters:
        lines.append(f"  - {char.id} ({char.team}) HP {char.hp}/{char.max_hp}")
    return "\n".join(lines)


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total > 0 else 0.0


def aggregate_reports(reports: list[BattleReport]) -> SimulationAggregate:
    total = len(reports)
    result_counts: dict[str, int] = {}
    stall_reason_counts: dict[str, int] = {}
    rounds_total = 0
    ally_hp_rate_total = 0.0
    enemy_hp_rate_total = 0.0

    for report in reports:
        result_counts[report.result] = result_counts.get(report.result, 0) + 1
        if report.stall_reason:
            stall_reason_counts[report.stall_reason] = stall_reason_counts.get(report.stall_reason, 0) + 1
        rounds_total += safe_int(report.rounds, 0)
        ally_hp_rate_total += float(report.summary.ally.hp_rate)
        enemy_hp_rate_total += float(report.summary.enemy.hp_rate)

    return SimulationAggregate(
        runs=total,
        result_counts=result_counts,
        stall_reason_counts=stall_reason_counts,
        ally_win_rate=_rate(result_counts.get("ally_win", 0), total),
        enemy_win_rate=_rate(result_counts.get("enemy_win", 0), total),
        draw_rate=_rate(result_counts.get("draw", 0), total),
        stall_rate=_rate(sum(1 for report in reports if report.stalled), total),
        avg_rounds=round(rounds_total / total, 2) if total > 0 else 0.0,
        avg_ally_hp_rate=round(ally_hp_rate_total / total, 4) if total > 0 else 0.0,
        avg_enemy_hp_rate=round(enemy_hp_rate_total / total, 4) if total > 0 else 0.0,
    )


def format_aggregate(aggregate: SimulationAggregate) -> str:
    return "\n".join([
        f"runs: {aggregate.runs}",
        f"result_counts: {aggregate.result_counts}",
        f"stall_reason_counts: {aggregate.stall_reason_counts}",
        (
            "rates: "
            f"ally_win={aggregate.ally_win_rate:.0%}, "
            f"enemy_win={aggregate.enemy_win_rate:.0%}, "
            f"draw={aggregate.draw_rate:.0%}, "
            f"stall={aggregate.stall_rate:.0%}"
        ),
        (
            "averages: "
            f"rounds={aggregate.avg_rounds}, "
            f"ally_hp_rate={aggregate.avg_ally_hp_rate:.0%}, "
            f"enemy_hp_rate={aggregate.avg_enemy_hp_rate:.0%}"
        ),
    ])
