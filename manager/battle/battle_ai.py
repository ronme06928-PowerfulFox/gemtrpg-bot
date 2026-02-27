import random
import json
from manager.battle.core import verify_skill_cost
from extensions import all_skill_data
from manager.logs import setup_logger

logger = setup_logger(__name__)

from manager.room_manager import broadcast_log

import re


def _extract_skill_rule_data(skill_data):
    if not isinstance(skill_data, dict):
        return {}

    for key in ['rule_data', 'rule_json', 'rule', '特記処理']:
        raw = skill_data.get(key)
        if not raw:
            continue
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            text = raw.strip()
            if not text.startswith('{'):
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
        raw_tags = skill_data.get('tags', [])
        if isinstance(raw_tags, list):
            tags.extend(raw_tags)

    rule_data = _extract_skill_rule_data(skill_data)
    rule_tags = rule_data.get('tags', []) if isinstance(rule_data, dict) else []
    if isinstance(rule_tags, list):
        tags.extend(rule_tags)

    normalized = []
    for tag in tags:
        text = str(tag or '').strip().lower()
        if text:
            normalized.append(text)
    return normalized


def _extract_skill_ids_from_commands(commands_text):
    if not commands_text:
        return []

    # Examples:
    # - 【S-01: 斬撃】
    # - 【S-01：斬撃】
    # - 【S-01 斬撃】
    # - [S-01 Slash]
    bracket_pattern = re.compile(r'[【\[]\s*([A-Za-z0-9][A-Za-z0-9_-]*)[^\]】]*[】\]]')
    matches = bracket_pattern.findall(str(commands_text))
    ordered = []
    seen = set()
    for skill_id in matches:
        sid = str(skill_id or '').strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        ordered.append(sid)
    return ordered


def _extract_granted_skill_ids(char):
    out = []
    seen = set()
    rows = char.get('granted_skills', []) if isinstance(char, dict) else []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = str(row.get('skill_id', '') or '').strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def list_usable_skill_ids(char, allow_instant=False):
    """
    Returns skill IDs that:
    1) are declared in character commands
    2) exist in all_skill_data
    3) pass cost check
    4) are not instant (unless allow_instant=True)
    """
    if not isinstance(char, dict):
        return []

    commands_text = char.get('commands', '')
    skill_ids_in_command = _extract_skill_ids_from_commands(commands_text)
    granted_skill_ids = _extract_granted_skill_ids(char)
    skill_ids_in_command = list(dict.fromkeys(skill_ids_in_command + granted_skill_ids))
    if not skill_ids_in_command:
        return []

    usable_skills = []
    for skill_id in skill_ids_in_command:
        skill_data = all_skill_data.get(skill_id)
        if not isinstance(skill_data, dict):
            continue

        tags = _extract_skill_tags(skill_data)
        tags_text = ' '.join(tags)
        if (not allow_instant) and (
            'instant' in tags
            or '即時' in tags_text
            or '即時発動' in tags_text
        ):
            continue

        can_use, _reason = verify_skill_cost(char, skill_data)
        if can_use:
            usable_skills.append(skill_id)

    return usable_skills

def ai_select_targets(state, room_id=None):
    """
    敵キャラクター(type='enemy')のターゲットを決定し、state['ai_target_arrows']を更新する。

    Args:
        state (dict): ルーム状態
        room_id (str): ログ出力用のルームID
    """
    if not state:
        return

    # Initialize if missing
    if 'ai_target_arrows' not in state:
        state['ai_target_arrows'] = []

    # Clear existing arrows
    state['ai_target_arrows'] = []

    characters = state.get('characters', [])
    # Filter 1: Exclude Unplaced Enemies
    enemies = [c for c in characters if c.get('type') == 'enemy' and c.get('hp', 0) > 0 and c.get('x', -1) >= 0]

    # Filter 2: Exclude Unplaced Allies
    allies = [c for c in characters if c.get('type') == 'ally' and c.get('hp', 0) > 0 and c.get('x', -1) >= 0]

    if not allies:
        logger.info("[AI] No valid allies to target.")
        return

    new_arrows = []
    log_messages = []

    for enemy in enemies:
        if enemy.get('isWideUser', False):
            # Wide Attack: Target ALL allies
            for ally in allies:
                arrow = {
                    "from_id": enemy['id'],
                    "to_id": ally['id'],
                    "type": "attack",
                    "visible": True
                }
                new_arrows.append(arrow)

            msg = f"{enemy['name']} ➔ 全員 (広域攻撃)"
        else:
            # Random Target Selection (Normal)
            target = random.choice(allies)

            arrow = {
                "from_id": enemy['id'],
                "to_id": target['id'],
                "type": "attack",
                "visible": True
            }
            new_arrows.append(arrow)

            # Update enemy internal state
            enemy['ai_current_target_id'] = target['id']

            # Log Message Construction
            msg = f"{enemy['name']} ➔ {target['name']}"

        # Planned Skill Display
        if enemy.get('flags', {}).get('show_planned_skill'):
            skill_id = ai_suggest_skill(enemy) # Reuse existing logic
            if skill_id:
                skill_name = "不明なスキル"
                # Try to extract custom name from commands
                # Pattern: 【ID: CustomName】 or 【ID】
                # specific pattern for this skill_id
                pattern = re.compile(rf"【{re.escape(skill_id)}(?:[:\s]+(.*?))?】")
                commands = enemy.get('commands', '')
                match = pattern.search(commands)
                if match and match.group(1):
                    skill_name = match.group(1).strip()
                else:
                    # Fallback to default data
                    sd = all_skill_data.get(skill_id)
                    if sd: skill_name = sd.get('name', skill_id)

                msg += f" (予定: {skill_name})"

        log_messages.append(msg)

    state['ai_target_arrows'] = new_arrows
    logger.info(f"[AI] Updated targets for {len(enemies)} enemies.")

    if room_id and log_messages:
        full_msg = "<strong>[AIターゲット確認]</strong><br>" + "<br>".join(log_messages)
        broadcast_log(room_id, full_msg, 'info')



def ai_suggest_skill(char):
    """
    キャラクターの使用可能なスキルをランダムに一つ提案する。
    コスト不足、即時発動、広域スキルは除外する。

    Args:
        char (dict): キャラクターデータ

    Returns:
        str or None: 推奨スキルのID
    """
    if not char:
        return None

    usable_skills = list_usable_skill_ids(char, allow_instant=False)

    if not usable_skills:
        return None

    # Random selection
    suggested = random.choice(usable_skills)
    logger.info(
        "[AI] Suggested skill %s for %s (pool=%d)",
        suggested,
        char.get('name', 'Unknown'),
        len(usable_skills)
    )
    return suggested
