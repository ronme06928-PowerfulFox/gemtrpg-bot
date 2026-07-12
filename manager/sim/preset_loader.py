from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Literal

from events.battle_only.runtime_builders import (
    _apply_enemy_behavior_override,
    _bo_assign_auto_positions,
    _build_runtime_character_from_preset,
)
from manager.battle_only_presets import load_store as load_bo_preset_store
from manager.sim.reporting import safe_int


PresetSide = Literal["ally", "enemy"]


def empty_room_state_for_presets() -> dict:
    return {
        "round": 0,
        "play_mode": "battle_only",
        "battle_mode": "pve",
        "characters": [],
        "timeline": [],
        "character_owners": {},
        "map_data": {"width": 20, "height": 15, "gridSize": 64},
        "battle_state": {
            "battle_id": "sim_test",
            "round": 0,
            "phase": "round_end",
            "slots": {},
            "timeline": [],
            "tiebreak": [],
            "intents": {},
            "redirects": [],
            "resolve": {
                "mass_queue": [],
                "single_queue": [],
                "resolved_slots": [],
                "trace": [],
            },
        },
        "battle_only": {"status": "in_battle", "simulator": True},
    }


def load_preset_store_from_path(path: str | None) -> dict:
    if not path:
        return load_bo_preset_store()
    with Path(path).open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError("preset store JSON must be an object")
    return payload


def _preset_map(store: dict) -> dict:
    presets = store.get("character_presets") if isinstance(store, dict) else None
    return presets if isinstance(presets, dict) else {}


def _formation_map(store: dict, side: PresetSide) -> dict:
    key = "ally_formations" if side == "ally" else "enemy_formations"
    formations = store.get(key) if isinstance(store, dict) else None
    return formations if isinstance(formations, dict) else {}


def _stage_map(store: dict) -> dict:
    stages = store.get("stage_presets") if isinstance(store, dict) else None
    return stages if isinstance(stages, dict) else {}


def _require_preset(store: dict, preset_id: str, side: PresetSide) -> dict:
    preset_id = str(preset_id or "").strip()
    if not preset_id:
        raise ValueError("preset id must not be empty")
    rec = _preset_map(store).get(preset_id)
    if not isinstance(rec, dict):
        raise ValueError(f"character preset not found: {preset_id}")

    allow_key = "allow_ally" if side == "ally" else "allow_enemy"
    if allow_key in rec and rec.get(allow_key) is False:
        raise ValueError(f"character preset {preset_id} is not allowed for {side}")
    return rec


def _build_character_from_preset(store: dict, preset_id: str, side: PresetSide, serial_no: int) -> dict:
    rec = _require_preset(store, preset_id, side)
    return _build_runtime_character_from_preset(rec, side, serial_no)


def _build_characters_from_preset_ids(
    store: dict,
    preset_ids: list[str] | None,
    side: PresetSide,
    start_serial: int,
) -> list[dict]:
    chars = []
    serial_no = int(start_serial)
    for preset_id in preset_ids or []:
        chars.append(_build_character_from_preset(store, preset_id, side, serial_no))
        serial_no += 1
    return chars


def _build_characters_from_formation(store: dict, formation_id: str | None, side: PresetSide, start_serial: int) -> list[dict]:
    formation_id = str(formation_id or "").strip()
    if not formation_id:
        return []
    formation = _formation_map(store, side).get(formation_id)
    if not isinstance(formation, dict):
        raise ValueError(f"{side} formation not found: {formation_id}")

    chars = []
    serial_no = int(start_serial)
    for member in formation.get("members") or []:
        if not isinstance(member, dict):
            continue
        preset_id = str(member.get("preset_id") or "").strip()
        if not preset_id:
            continue
        count = safe_int(member.get("count"), 1)
        if count <= 0:
            count = 1
        for _ in range(count):
            char = _build_character_from_preset(store, preset_id, side, serial_no)
            if side == "enemy":
                _apply_enemy_behavior_override(char, member.get("behavior_profile_override"))
            chars.append(char)
            serial_no += 1
    return chars


def build_room_state_from_presets(
    *,
    store: dict | None = None,
    ally_preset_ids: list[str] | None = None,
    enemy_preset_ids: list[str] | None = None,
    ally_formation_id: str | None = None,
    enemy_formation_id: str | None = None,
    stage_id: str | None = None,
    anchor: dict | None = None,
) -> dict:
    store = copy.deepcopy(store) if isinstance(store, dict) else load_bo_preset_store()
    state = empty_room_state_for_presets()

    if stage_id:
        stage = _stage_map(store).get(str(stage_id).strip())
        if not isinstance(stage, dict):
            raise ValueError(f"stage preset not found: {stage_id}")
        ally_formation_id = ally_formation_id or stage.get("ally_formation_id")
        enemy_formation_id = enemy_formation_id or stage.get("enemy_formation_id")
        state["battle_only"]["selected_stage_id"] = str(stage.get("id") or stage_id)
        if isinstance(stage.get("field_effect_profile"), dict):
            state["battle_only"]["field_effect_profile"] = copy.deepcopy(stage.get("field_effect_profile"))

    allies = []
    enemies = []
    allies.extend(_build_characters_from_formation(store, ally_formation_id, "ally", 1))
    allies.extend(_build_characters_from_preset_ids(store, ally_preset_ids, "ally", len(allies) + 1))
    enemies.extend(_build_characters_from_formation(store, enemy_formation_id, "enemy", len(allies) + 1))
    enemies.extend(_build_characters_from_preset_ids(store, enemy_preset_ids, "enemy", len(allies) + len(enemies) + 1))

    if not allies:
        raise ValueError("at least one ally preset or ally formation is required")
    if not enemies:
        raise ValueError("at least one enemy preset or enemy formation is required")

    state["characters"] = allies + enemies
    state["character_owners"] = {str(char.get("id")): "simulator" for char in state["characters"] if char.get("id")}
    _bo_assign_auto_positions(allies, enemies, state, anchor=anchor)
    return state

