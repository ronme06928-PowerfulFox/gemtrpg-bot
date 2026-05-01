import json
import random
import re

from extensions import all_skill_data
from manager.battle.core import verify_skill_cost
from manager.logs import setup_logger
from manager.room_manager import broadcast_log

logger = setup_logger(__name__)


def _extract_skill_rule_data(skill_data):
    if not isinstance(skill_data, dict):
        return {}
    for key in ["rule_data", "rule_json", "rule", "迚ｹ險伜・逅・"]:
        raw = skill_data.get(key)
        if not raw:
            continue
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            text = raw.strip()
            if not text.startswith("{"):
                continue
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    return {}


def _extract_skill_tags(skill_data):
    tags = []
    if isinstance(skill_data, dict):
        raw_tags = skill_data.get("tags", [])
        if isinstance(raw_tags, list):
            tags.extend(raw_tags)
    rule_data = _extract_skill_rule_data(skill_data)
    rule_tags = rule_data.get("tags", []) if isinstance(rule_data, dict) else []
    if isinstance(rule_tags, list):
        tags.extend(rule_tags)
    normalized = []
    for tag in tags:
        text = str(tag or "").strip().lower()
        if text:
            normalized.append(text)
    return normalized


def _extract_skill_ids_from_commands(commands_text):
    if not commands_text:
        return []
    bracket_pattern = re.compile(r"[【\[]\s*([A-Za-z0-9][A-Za-z0-9_-]*)[^\]】]*[】\]]")
    matches = bracket_pattern.findall(str(commands_text))
    ordered = []
    seen = set()
    for skill_id in matches:
        sid = str(skill_id or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        ordered.append(sid)
    return ordered


def _extract_granted_skill_ids(char):
    out = []
    seen = set()
    rows = char.get("granted_skills", []) if isinstance(char, dict) else []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("skill_id", "") or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def list_usable_skill_ids(char, allow_instant=False):
    if not isinstance(char, dict):
        return []

    commands_text = char.get("commands", "")
    skill_ids = _extract_skill_ids_from_commands(commands_text)
    skill_ids.extend(_extract_granted_skill_ids(char))
    skill_ids = list(dict.fromkeys(skill_ids))
    usable = []

    for skill_id in skill_ids:
        skill_data = all_skill_data.get(skill_id)
        if not isinstance(skill_data, dict):
            continue
        tags = _extract_skill_tags(skill_data)
        tags_text = " ".join(tags)
        if (not allow_instant) and (("instant" in tags) or ("immediate" in tags) or ("instant" in tags_text) or ("即時" in tags_text)):
            continue
        can_use, _reason = verify_skill_cost(char, skill_data)
        if can_use:
            usable.append(skill_id)
    return usable


def ai_select_targets(state, room_id=None):
    if not state:
        return
    if "ai_target_arrows" not in state:
        state["ai_target_arrows"] = []
    state["ai_target_arrows"] = []

    characters = state.get("characters", [])
    enemies = [c for c in characters if c.get("type") == "enemy" and c.get("hp", 0) > 0 and c.get("x", -1) >= 0]
    allies = [c for c in characters if c.get("type") == "ally" and c.get("hp", 0) > 0 and c.get("x", -1) >= 0]
    if not allies:
        logger.info("[AI] No valid allies to target.")
        return

    new_arrows = []
    log_messages = []
    for enemy in enemies:
        if enemy.get("isWideUser", False):
            for ally in allies:
                new_arrows.append({"from_id": enemy["id"], "to_id": ally["id"], "type": "attack", "visible": True})
            msg = f"{enemy['name']} 筐・蜈ｨ蜩｡ (蠎・沺謾ｻ謦・"
        else:
            target = random.choice(allies)
            new_arrows.append({"from_id": enemy["id"], "to_id": target["id"], "type": "attack", "visible": True})
            enemy["ai_current_target_id"] = target["id"]
            msg = f"{enemy['name']} 筐・{target['name']}"

        if enemy.get("flags", {}).get("show_planned_skill"):
            skill_id = ai_suggest_skill(enemy)
            if skill_id:
                skill_name = "Unknown"
                sd = all_skill_data.get(skill_id)
                if isinstance(sd, dict):
                    skill_name = sd.get("name", skill_id)
                msg += f" (莠亥ｮ・ {skill_name})"
        log_messages.append(msg)

    state["ai_target_arrows"] = new_arrows
    logger.info("[AI] Updated targets for %d enemies.", len(enemies))
    if room_id and log_messages:
        full_msg = "<strong>[AI繧ｿ繝ｼ繧ｲ繝・ヨ遒ｺ隱江</strong><br>" + "<br>".join(log_messages)
        broadcast_log(room_id, full_msg, "info")


def ai_suggest_skill(char):
    if not char:
        return None
    usable_skills = list_usable_skill_ids(char, allow_instant=False)
    if not usable_skills:
        return None
    suggested = random.choice(usable_skills)
    logger.info("[AI] Suggested skill %s for %s (pool=%d)", suggested, char.get("name", "Unknown"), len(usable_skills))
    return suggested
