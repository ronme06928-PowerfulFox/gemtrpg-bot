"""Queue first clears and reflect them at the end of a Hollow expedition."""

from copy import deepcopy
from datetime import datetime, timezone

from extensions import db
from manager.owned_growth import add_passage_points, locked_characters
from models import OwnedCharacter


def _clears(history):
    return {row["tier"]: row for row in (history or []) if row.get("kind") == "hollow_results"}


def cleared_tiers(history):
    return sorted(_clears(history))


def queue_boss_growth(state, run, event):
    party = {char["id"]: char for char in state["characters"]}
    names = {}
    for char_id in run["party_order"]:
        char = party.get(char_id)
        if char and (key := char.get("owned_character_id")):
            names.setdefault(key, char["name"])
    pending = run["growth_pending"]
    tier = run["map"]["tier"]
    exp, radiance = event["boss_exp"], event["boss_radiance"]
    if not names:
        return f"T{tier} 持ちキャラなし（経験なし）"
    owned = {row.id: row for row in OwnedCharacter.query.filter(
        OwnedCharacter.id.in_(names), OwnedCharacter.deleted_at.is_(None))}
    names_to_award = []
    for key, name in names.items():
        row = owned.get(key)
        if (row is None or tier in _clears(row.growth_log)
                or any(clear["tier"] == tier for clear in pending.get(key, []))):
            continue
        pending.setdefault(key, []).append({"tier": tier, "name": name, "exp_gain": exp, "radiance_gain": radiance})
        names_to_award.append(name)
    if not names_to_award:
        return f"T{tier} 踏破済み（経験なし）" if owned else f"T{tier} 持ちキャラなし（経験なし）"
    return f"T{tier} 初踏破：{'・'.join(names_to_award)}（経験＋{exp}・通過点＋{radiance}）"


def settle(room, run):
    pending = run.get("growth_pending")
    if not pending:
        return []
    owned = locked_characters(pending)
    result = []
    for key, pending_rows in pending.items():
        char = owned.get(key)
        if char is None:
            continue
        awarded = _settle_character(char, pending_rows, room, run["run_id"])
        if awarded:
            result.append({
                "name": pending_rows[0]["name"],
                "tiers": sorted(row["tier"] for row in awarded),
                "exp_gain": sum(row["exp_gain"] for row in awarded),
                "radiance_gain": sum(row["radiance_gain"] for row in awarded),
            })
    db.session.commit()
    return result


def _settle_character(char, pending, room, run_id):
    history = list(char.growth_log or [])
    clears = _clears(history)
    awarded, new = [], []
    for queued in pending:
        tier = queued["tier"]
        previous = clears.get(tier)
        if previous is not None:
            if previous.get("run_id") == run_id:
                awarded.append(previous)
            continue
        entry = {"date": datetime.now(timezone.utc).isoformat(), "kind": "hollow_results",
                 "room": room, "run_id": run_id, "tier": tier,
                 "exp_gain": queued["exp_gain"], "radiance_gain": queued["radiance_gain"]}
        awarded.append(entry)
        new.append(entry)
    if new:
        char.exp_total += sum(row["exp_gain"] for row in new)
        total = sum(row["radiance_gain"] for row in new)
        if total:
            data = deepcopy(char.data)
            add_passage_points(data, total)
            char.data = data
        char.growth_log = history + new
    return awarded
