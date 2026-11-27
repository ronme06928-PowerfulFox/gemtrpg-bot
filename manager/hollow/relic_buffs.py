"""Apply, retarget and release the buffs owned by an expedition."""
from collections import defaultdict

from manager.buff_apply import apply_buff
from manager.buff_catalog import VALUE_DRIVEN_BUFF_IDS, get_buff_by_id
from manager.character_tags import get_effective_tag_ids
from manager.hollow.runtime import available, get_reward
from manager.utils import normalize_buff_name

_MARKER = "hollow_expedition_buff"


def _targets(target, party, run, previous_round):
    if target["type"] == "all":
        return party
    if target["type"] == "nth":
        return party[target["n"] - 1:target["n"]]
    condition = target["condition"]
    living = [char for char in party if char and char.get("hp", 0) > 0]
    if condition == "hp_lowest":
        return [min(living, key=lambda char: char["hp"])] if living else []
    if condition == "bled_last_round":
        bled = run.get("bled") or {}
        return [char for char in living if bled.get("round") == previous_round and char["id"] in bled["ids"]]
    tag = condition.removeprefix("has_tag:")
    return [char for char in living if tag in get_effective_tag_ids(char)]


def load_stages():
    return sorted(available("hollow_load_stage").values(), key=lambda row: row["threshold"])


def sync_expedition_buffs(state, run, *, previous_round=None):
    roster = {char["id"]: char for char in state["characters"]}
    party = [roster.get(key) for key in run["party_order"]]
    desired = defaultdict(dict)

    def add(char, key, *, conditional=False, temporary=False):
        definition = get_buff_by_id(key) if key else None
        if char is not None and definition:
            name = normalize_buff_name(definition["name"])
            lasting = definition.get("default_duration", 1) if temporary else -1
            previous = desired[char["id"]].get(name)
            if previous is None or previous[0] != key or previous[2] != -1:
                desired[char["id"]][name] = (key, conditional, lasting)

    for relic_id in run["relics"]:
        relic = get_reward("relic", relic_id)
        if relic:
            conditional = relic["target"]["type"] == "condition"
            for char in _targets(relic["target"], party, run, previous_round):
                add(char, relic["buff_id"], conditional=conditional)
                add(char, relic.get("cost_buff_id"), conditional=conditional)
    for stage in load_stages():
        if run["mana_load"] < stage["threshold"]:
            break
        for char in party:
            add(char, stage["buff_id"])
    for row in run["temp_buffs"]:
        if row["battles_left"] > 0 and row["char_id"] in run["party_order"]:
            add(roster.get(row["char_id"]), row["buff_id"], temporary=True)

    for char in state["characters"]:
        wanted = desired.get(char["id"], {})
        buffs = char.setdefault("special_buffs", [])
        buffs[:] = [
            buff for buff in buffs
            if not buff.get(_MARKER) or (previous_round is not None and not buff.get("hollow_conditional"))
            or (wanted.get(normalize_buff_name(buff.get("name")), (None, None))[:2]
                == (buff.get("buff_id"), buff.get("hollow_conditional")))
        ]
        current = {(normalize_buff_name(buff.get("name")), buff.get("buff_id"))
                   for buff in buffs if buff.get(_MARKER)}
        for name, (key, conditional, lasting) in wanted.items():
            if previous_round is not None and not conditional:
                continue
            if (name, key) not in current:
                data = {"buff_id": key, _MARKER: True, "hollow_conditional": conditional}
                if key in VALUE_DRIVEN_BUFF_IDS:
                    data["value"] = 0
                apply_buff(char, name, lasting, 0, data=data)


def clear_expedition_buffs(state):
    for char in state.get("characters", []):
        if "special_buffs" in char:
            char["special_buffs"] = [row for row in char["special_buffs"] if not row.get(_MARKER)]


def record_bleed(state, char_id):
    run = state.get("hollow", {}).get("run")
    if run and run.get("status") == "in_progress" and char_id in run["party_order"]:
        current = state.get("round", 0)
        bled = run.get("bled")
        if not bled or bled["round"] != current:
            bled = run["bled"] = {"round": current, "ids": []}
        if char_id not in bled["ids"]:
            bled["ids"].append(char_id)
