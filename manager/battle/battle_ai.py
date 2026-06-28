import random

from extensions import all_skill_data
from manager.battle.skill_access import list_usable_skill_ids
from manager.logs import setup_logger
from manager.room_manager import broadcast_log

logger = setup_logger(__name__)


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
            msg = f"{enemy['name']} → 全員 (広域攻撃)"
        else:
            target = random.choice(allies)
            new_arrows.append({"from_id": enemy["id"], "to_id": target["id"], "type": "attack", "visible": True})
            enemy["ai_current_target_id"] = target["id"]
            msg = f"{enemy['name']} → {target['name']}"

        if enemy.get("flags", {}).get("show_planned_skill"):
            skill_id = ai_suggest_skill(enemy)
            if skill_id:
                skill_name = "Unknown"
                sd = all_skill_data.get(skill_id)
                if isinstance(sd, dict):
                    skill_name = sd.get("name", skill_id)
                msg += f" (予定: {skill_name})"
        log_messages.append(msg)

    state["ai_target_arrows"] = new_arrows
    logger.info("[AI] Updated targets for %d enemies.", len(enemies))
    if room_id and log_messages:
        full_msg = "<strong>[AIターゲット確認]</strong><br>" + "<br>".join(log_messages)
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
