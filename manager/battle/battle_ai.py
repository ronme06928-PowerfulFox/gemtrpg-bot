import random
import json
from manager.battle.core import verify_skill_cost
from extensions import all_skill_data
from manager.logs import setup_logger

logger = setup_logger(__name__)

from manager.room_manager import broadcast_log

import re

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
        # Random Target Selection
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

    commands_text = char.get('commands', '')
    if not commands_text:
        return None

    usable_skills = []

    # Simple parsing of commands (assuming standard format)
    # This logic mimics the client-side parsing or should leverage a shared parser if available.
    # For now, we iterate through all known skills in all_skill_data and check if present in commands.
    # (Checking raw text for "【ID: 名称】" or similar is safer if commands are free text)

    # 既存のコマンド解析ロジック（簡易版）
    # コアロジックと重複するが、サーバーサイドで信頼できるリストを作る

    # 1. Extract skill IDs from command text
    import re
    # Pattern: 【(ID)(: space? Name)?】
    # e.g. 【S-01: 斬撃】 or 【S-01】
    # Also handle the hidden ID format if any

    cmd_lines = commands_text.split('\n')
    skill_ids_in_command = []

    for line in cmd_lines:
        match = re.search(r'【([a-zA-Z0-9-]+)(?:[:\s].*)?】', line)
        if match:
            skill_ids_in_command.append(match.group(1))

    # 2. Filter valid skills
    for skill_id in skill_ids_in_command:
        skill_data = all_skill_data.get(skill_id)
        if not skill_data:
            continue

        # Parse rule data
        rule_json = skill_data.get('特記処理', '{}')
        try:
            rule = json.loads(rule_json)
            tags = rule.get('tags', skill_data.get('tags', []))

            # Filter: Instant or Wide
            if "即時発動" in tags:
                continue
            if "広域" in tags:
                continue

            # Filter: Cost Check
            can_use, reason = verify_skill_cost(char, skill_data)
            if can_use:
                usable_skills.append(skill_id)
            else:
                pass
                # logger.debug(f"[AI] Skill {skill_id} rejected for {char['name']}: {reason}")

        except json.JSONDecodeError:
            continue

    if not usable_skills:
        return None

    # Random selection
    suggested = random.choice(usable_skills)
    logger.info(f"[AI] Suggested skill {suggested} for {char['name']}")
    return suggested
