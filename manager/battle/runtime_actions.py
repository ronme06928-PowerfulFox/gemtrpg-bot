import re

from manager.game_logic import (
    process_skill_effects,
    apply_buff,
    remove_buff,
    get_status_value,
)
from manager.logs import setup_logger
from manager.buff_catalog import resolve_runtime_buff_effect
from manager.room_manager import (
    get_room_state,
    broadcast_log,
    broadcast_state_update,
    save_specific_room_state,
    _update_char_stat,
)
from manager.summons.service import apply_summon_change, process_summon_round_end
from manager.granted_skills.service import apply_grant_skill_change, process_granted_skill_round_end
from manager.battle.skill_rules import _extract_rule_data_from_skill
from manager.utils import set_status_value, apply_origin_bonus_buffs, get_round_end_origin_recoveries


logger = setup_logger(__name__)

def calculate_opponent_skill_modifiers(actor_char, target_char, actor_skill_data, target_skill_data, all_skill_data_ref):
    """
    相手スキルの PRE_MATCH 効果を評価し、対象に適用される威力補正を返す。
    """
    modifiers = {
        "base_power_mod": 0,
        "final_power_mod": 0,
        "dice_power_mod": 0,
        "stat_correction_mod": 0,
        "additional_power": 0
    }

    if not actor_skill_data:
        return modifiers

    try:
        rule_data = _extract_rule_data_from_skill(actor_skill_data)
        effects_array = rule_data.get("effects", []) if isinstance(rule_data, dict) else []

        # PRE_MATCH タイミングの効果を評価
        _, logs, changes = process_skill_effects(
            effects_array, "PRE_MATCH", actor_char, target_char, target_skill_data
        )

        for (char, effect_type, name, value) in changes:
            if effect_type == "MODIFY_BASE_POWER":
                # ターゲットへの基礎威力補正
                if char and target_char and char.get('id') == target_char.get('id'):
                    modifiers["base_power_mod"] += value
            elif effect_type == "MODIFY_FINAL_POWER":
                if char and target_char and char.get('id') == target_char.get('id'):
                    modifiers["final_power_mod"] += value
    except Exception as e:
        logger.error(f"calculate_opponent_skill_modifiers: {e}")

    return modifiers

def extract_cost_from_text(text):
    """
    テキストログからコスト表記を抽出する。
    """
    if not text:
        return "なし"
    match = re.search(r'\[(:コスト|使用時)\]:([^\n]+)', text)
    if match:
        return match.group(1).strip()
    return "なし"

def extract_custom_skill_name(character, skill_id):
    """
    キャラクターの `commands` から、指定スキルIDのカスタム名を抽出する。

    Args:
        character (dict): キャラクターデータ
        skill_id (str): スキルID (例: "Pp-01")

    Returns:
        str | None: カスタムスキル名
    """
    if not character or not skill_id:
        return None

    commands = character.get('commands', '')
    if not commands:
        return None

    # 例: "【Pp-01 斬り込む】" / "【Pp-01: 斬り込む】"
    pattern = rf'【{re.escape(skill_id)}[\s:：]+(.*)】'
    match = re.search(pattern, commands)

    if match:
        return match.group(1).strip()

    return None

def format_skill_name_for_log(skill_id, skill_data, character=None):
    """
    ログ表示用のスキル名をフォーマットする。
    キャラ固有のカスタム名があれば優先し、なければスキル定義の名称を使う。

    Args:
        skill_id (str): スキルID (例: "Pp-01")
        skill_data (dict): スキルデータ
        character (dict): キャラクターデータ（任意）

    Returns:
        str: 例 "Pp-01: 斬り込む"
    """
    if not skill_id:
        return "不明"

    # カスタム名を優先
    custom_name = None
    if character:
        custom_name = extract_custom_skill_name(character, skill_id)

    # カスタム名がなければスキル定義名
    if custom_name:
        return f"{skill_id}: {custom_name}"
    elif skill_data:
        default_name = (
            skill_data.get('デフォルト名称')
            or skill_data.get('name')
            or skill_data.get('名称')
        )
        if default_name:
            return f"{skill_id}: {default_name}"

    # フォールバック: スキルIDのみ
    return skill_id

def format_skill_display_from_command(command_str, skill_id, skill_data, character=None):
    """
    Build a highlighted skill display string for battle logs.
    Priority:
    1) custom name from character command palette
    2) explicit [ ... ] section from command string
    3) fallback to skill id + skill name
    """
    custom_name = None
    if character and skill_id:
        custom_name = extract_custom_skill_name(character, skill_id)

    text = ""
    if custom_name:
        text = f"【{skill_id}: {custom_name}】"
    else:
        command_text = str(command_str or "")
        match = re.search(r'【(.*)】', command_text)
        if match:
            text = f"【{match.group(1)}】"
        elif skill_id and skill_data:
            name = (
                skill_data.get('デフォルト名称')
                or skill_data.get('name')
                or skill_data.get('名称')
                or '不明'
            )
            text = f"【{skill_id}: {name}】"
        else:
            return ""

    return f"<span style='color: #d63384; font-weight: bold;'>{text}</span>"

def verify_skill_cost(char, skill_d):
    """Validate whether actor can pay skill cost."""
    if not skill_d:
        return True, None

    try:
        rule_data = _extract_rule_data_from_skill(skill_d)
        tags = rule_data.get('tags', skill_d.get('tags', [])) if isinstance(rule_data, dict) else skill_d.get('tags', [])
        if isinstance(tags, list) and ("即時発動" in tags):
            if "星見の加護スキル" in tags and char.get('used_gem_protect_this_battle', False):
                return False, "星見の加護スキルは1ラウンドに1回までです。"
            return True, None

        for cost in (rule_data.get("cost", []) if isinstance(rule_data, dict) else []):
            if not isinstance(cost, dict):
                continue
            c_type = cost.get("type")
            c_val = int(cost.get("value", 0) or 0)
            if c_val > 0 and c_type:
                curr = int(get_status_value(char, c_type) or 0)
                if curr < c_val:
                    return False, f"{c_type}不足 (必要:{c_val}, 現在:{curr})"
    except Exception:
        pass

    return True, None

def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _iter_reaction_entries(payload):
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _resolve_reaction_targets(target_key, owner_char, attacker_char):
    target_name = str(target_key or 'attacker').strip().lower()
    if target_name in {'self', 'owner'}:
        return [owner_char] if isinstance(owner_char, dict) else []
    if target_name in {'attacker', 'source'}:
        return [attacker_char] if isinstance(attacker_char, dict) else []
    return []


def _passes_on_damage_reaction_condition(reaction_conf, damage_val):
    if not isinstance(reaction_conf, dict):
        return False
    condition = reaction_conf.get('condition')
    if not isinstance(condition, dict):
        return True
    damage_gte = _safe_int(condition.get('damage_gte'), None)
    if damage_gte is not None and int(damage_val or 0) < damage_gte:
        return False
    return True


def _is_on_damage_reaction_suppressed(context):
    if not isinstance(context, dict):
        return False
    if context.get('suppress_on_damage_reaction'):
        return True
    damage_source = str(context.get('damage_source') or context.get('damage_origin') or '').strip().lower()
    return damage_source in {'on_damage_reaction', 'retaliation', 'reaction'}


def _append_on_damage_log(room, log_snippets, message):
    if not isinstance(log_snippets, list):
        if message and room:
            try:
                broadcast_log(room, str(message), 'state-change')
            except Exception as e:
                logger.warning("[被弾反応ログ] broadcast_log失敗 room=%s msg=%s err=%s", room, message, e)
        return
    if not message:
        return
    msg = str(message)
    log_snippets.append(msg)
    if room:
        try:
            broadcast_log(room, msg, 'state-change')
        except Exception as e:
            logger.warning("[被弾反応ログ] broadcast_log失敗 room=%s msg=%s err=%s", room, msg, e)
    else:
        logger.warning("[被弾反応ログ] room=Noneのためbroadcast_log未呼び出し msg=%s", msg)


def _format_on_damage_damage_log(owner_name, target_name, damage_amount):
    return f"[\u88ab\u5f3e\u53cd\u5fdc] {owner_name}\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067{target_name}\u306b{int(damage_amount)}\u30c0\u30e1\u30fc\u30b8\u3002"


def _format_on_damage_state_log(owner_name, target_name, state_name, state_value, rounds=None):
    value = int(state_value or 0)
    if state_name == '\u4e80\u88c2' and value > 0 and int(rounds or 0) > 0:
        return f"[\u88ab\u5f3e\u53cd\u5fdc] {owner_name}\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067{target_name}\u306b{int(rounds)}\u30e9\u30a6\u30f3\u30c9\u306e\u4e80\u88c2{value}\u3092\u4ed8\u4e0e\u3002"
    if value > 0:
        return f"[\u88ab\u5f3e\u53cd\u5fdc] {owner_name}\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067{target_name}\u306b{state_name}{value}\u3092\u4ed8\u4e0e\u3002"
    return f"[\u88ab\u5f3e\u53cd\u5fdc] {owner_name}\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067{target_name}\u306e{state_name}\u3092{abs(value)}\u5909\u5316\u3002"


def _format_on_damage_buff_log(owner_name, target_name, buff_name):
    return f"[\u88ab\u5f3e\u53cd\u5fdc] {owner_name}\u306e\u88ab\u5f3e\u53cd\u5fdc\u3067{target_name}\u306b{buff_name}\u3092\u4ed8\u4e0e\u3002"


def _format_on_damage_skip_log(owner_name, target_name, reason):
    return f"[\u88ab\u5f3e\u53cd\u5fdc] {owner_name}\u306e\u88ab\u5f3e\u53cd\u5fdc\u306f\u767a\u52d5\u3057\u305f\u304c\u3001{target_name}\u3078\u306e\u52b9\u679c\u306f\u4e0d\u767a\u3002({reason})"


def _apply_on_damage_state(room, owner_name, reaction_target, target_name, state_row, log_snippets):
    if not isinstance(reaction_target, dict) or not isinstance(state_row, dict):
        return

    state_name = str(state_row.get('name') or state_row.get('stat') or '').strip()
    state_value = _safe_int(state_row.get('value'), 0)
    if not state_name or state_value == 0:
        return

    if state_name == '\u4e80\u88c2' and state_value > 0:
        rounds = _safe_int(state_row.get('rounds'), 0)
        if rounds <= 0:
            _append_on_damage_log(room, log_snippets, _format_on_damage_skip_log(owner_name, target_name, "\u4e80\u88c2\u306f\u7d99\u7d9a\u30e9\u30a6\u30f3\u30c9\u672a\u6307\u5b9a"))
            return
        apply_buff(
            reaction_target,
            f"\u4e80\u88c2_R{rounds}",
            rounds,
            0,
            data={
                "buff_id": "Bu-Fissure",
                "source": "on_damage_reaction",
                "count": state_value,
                "fissure_count": state_value,
                "original_rounds": rounds,
            },
        )
        _append_on_damage_log(room, log_snippets, _format_on_damage_state_log(owner_name, target_name, state_name, state_value, rounds=rounds))
        return

    if state_name == '亀裂' and state_value > 0:
        rounds = _safe_int(state_row.get('rounds'), 0)
        if rounds <= 0:
            _append_on_damage_log(room, log_snippets, _format_on_damage_skip_log(owner_name, target_name, "亀裂は継続ラウンド未指定"))
            return
        apply_buff(
            reaction_target,
            f"亀裂_R{rounds}",
            rounds,
            0,
            data={
                "buff_id": "Bu-Fissure",
                "source": "on_damage_reaction",
                "count": state_value,
                "fissure_count": state_value,
                "original_rounds": rounds,
            },
        )
        _append_on_damage_log(room, log_snippets, _format_on_damage_state_log(owner_name, target_name, state_name, state_value, rounds=rounds))
        return

    current_value = int(get_status_value(reaction_target, state_name) or 0)
    _update_char_stat(room, reaction_target, state_name, current_value + state_value, username=f"[{owner_name}]", suppress_log=True)
    _append_on_damage_log(room, log_snippets, _format_on_damage_state_log(owner_name, target_name, state_name, state_value))


def _apply_on_damage_reaction(room, owner_char, reaction_conf, attacker_char, log_snippets):
    if not isinstance(owner_char, dict) or not isinstance(reaction_conf, dict):
        return

    owner_name = str(owner_char.get('name') or owner_char.get('id') or 'on_damage').strip() or 'on_damage'
    targets = _resolve_reaction_targets(reaction_conf.get('target'), owner_char, attacker_char)
    if not targets:
        return

    damage_amount = max(0, _safe_int(reaction_conf.get('damage'), 0))
    state_rows = _iter_reaction_entries(reaction_conf.get('apply_state'))
    buff_rows = _iter_reaction_entries(reaction_conf.get('apply_buff'))

    for reaction_target in targets:
        if not isinstance(reaction_target, dict):
            continue
        target_name = str(reaction_target.get('name') or reaction_target.get('id') or 'target').strip() or 'target'

        if damage_amount > 0:
            current_hp = int(reaction_target.get('hp', 0) or 0)
            next_hp = max(0, current_hp - damage_amount)
            _update_char_stat(room, reaction_target, 'HP', next_hp, username=f"[{owner_name}]", suppress_log=True)
            _append_on_damage_log(room, log_snippets, _format_on_damage_damage_log(owner_name, target_name, damage_amount))

        for state_row in state_rows:
            _apply_on_damage_state(room, owner_name, reaction_target, target_name, state_row, log_snippets)

        for buff_row in buff_rows:
            buff_id = str(buff_row.get('buff_id') or '').strip()
            buff_name = str(buff_row.get('buff_name') or buff_row.get('name') or '').strip()
            if not buff_id and not buff_name:
                continue
            display_name = buff_name or buff_id
            lasting = _safe_int(buff_row.get('lasting'), 0)
            delay = _safe_int(buff_row.get('delay'), 0)
            payload = dict(buff_row.get('data') or {}) if isinstance(buff_row.get('data'), dict) else {}
            if buff_id and not payload.get('buff_id'):
                payload['buff_id'] = buff_id
            # count: top-level > data.count の順で取得
            count = buff_row.get('count')
            if count is None:
                count = payload.get('count')
            apply_buff(
                reaction_target,
                display_name,
                lasting,
                delay,
                data=payload,
                count=_safe_int(count, 0) if count is not None else None,
            )
            _append_on_damage_log(room, log_snippets, _format_on_damage_buff_log(owner_name, target_name, display_name))


def process_on_damage_buffs(room, char, damage_val, username, log_snippets, attacker_char=None, context=None):
    """
    被ダメージ時トリガーバフの処理。
    """
    _ = (username, context)
    total_applied_damage = 0
    if damage_val <= 0:
        return 0
    if _is_on_damage_reaction_suppressed(context):
        return 0

    for b in char.get('special_buffs', []):
        # このターン新規付与のバフは発動させない
        if b.get('newly_applied'):
            continue
        # Resolve full effect data (catalog + instance data + value-driven buff_id)
        effect_data = resolve_runtime_buff_effect(b)
        if not effect_data:
            continue

        conf = effect_data.get('on_damage_state')
        if not conf:
            reaction_conf = effect_data.get('on_damage_reaction')
            if reaction_conf and _passes_on_damage_reaction_condition(reaction_conf, damage_val):
                _apply_on_damage_reaction(room, char, reaction_conf, attacker_char, log_snippets)
            continue

        s_name = conf.get('stat')
        s_val = conf.get('value', 0)


        if s_name and s_val > 0:
            curr = get_status_value(char, s_name)
            # print(f"[DEBUG] Triggering on_damage_state: {s_name} {curr} -> {curr + s_val}")
            _update_char_stat(room, char, s_name, curr + s_val, username=f"[{b.get('name')}]")
            log_snippets.append(f"[{b.get('name')}→{s_name}+{s_val}]")
            if s_name == 'HP':
                total_applied_damage += s_val

        reaction_conf = effect_data.get('on_damage_reaction')
        if reaction_conf and _passes_on_damage_reaction_condition(reaction_conf, damage_val):
            _apply_on_damage_reaction(room, char, reaction_conf, attacker_char, log_snippets)

    return total_applied_damage

def process_on_hit_buffs(actor, target, damage_val, log_snippets):
    """
    的中時トリガーバフの処理（追加ダメージ計算）。
    Returns: extra_damage (int)
    """
    from plugins.buffs.registry import buff_registry

    total_extra_damage = 0
    if not actor or 'special_buffs' not in actor:
        return 0

    logger.info(f"[process_on_hit_buffs] Checking buffs for {actor.get('name')}. Count: {len(actor['special_buffs'])}")

    # スナップショットを取り、差分で追加ダメージを計上
    for buff_entry in list(actor['special_buffs']):
        buff_id = buff_entry.get('buff_id')
        handler_cls = buff_registry.get_handler(buff_id)

        if handler_cls and hasattr(handler_cls, 'on_hit_damage_calculation'):
            logger.info(f"[process_on_hit_buffs] Executing {handler_cls.__name__} for {buff_id}")
            # クラスメソッドとして呼び出し
            new_damage, logs = handler_cls.on_hit_damage_calculation(actor, target, damage_val + total_extra_damage)

            diff = new_damage - (damage_val + total_extra_damage)
            if diff != 0:
                logger.info(f"[process_on_hit_buffs] {handler_cls.__name__} added {diff} damage")
                total_extra_damage += diff

            if logs:
                log_snippets.extend(logs)
        else:
            logger.info(f"[process_on_hit_buffs] No handler or hook for {buff_id} ({buff_entry.get('name')}). Has Handler: {bool(handler_cls)}")

    return total_extra_damage

def execute_pre_match_effects(room, actor, target, skill_data, target_skill_data=None):
    """
    マッチ解決前の PRE_MATCH 効果を適用する。
    """
    if not skill_data or not actor: return
    state = get_room_state(room)
    # Select/Resolve delegated clash already applies PRE_MATCH before preview.
    # Skip legacy PRE_MATCH here to avoid duplicate application.
    if isinstance(state, dict) and state.get('__select_resolve_delegate__', False):
        return

    # 直近に使用したスキルID（ログ表示用）
    skill_id = None
    if 'used_skills_this_round' in actor and actor['used_skills_this_round']:
        skill_id = actor['used_skills_this_round'][-1]

    try:
        rule_data = _extract_rule_data_from_skill(skill_data)
        effects_array = rule_data.get("effects", []) if isinstance(rule_data, dict) else []

        # Room state for context
        context = {
            "characters": state['characters'],
            "timeline": state.get('timeline', [])
        } if state else None

        _, logs, changes = process_skill_effects(effects_array, "PRE_MATCH", actor, target, target_skill_data, context=context)

        for (char, type, name, value) in changes:
            if type == "APPLY_STATE":
                current_val = get_status_value(char, name)
                _update_char_stat(room, char, name, current_val + value, username=f"[{format_skill_name_for_log(skill_id, skill_data, actor)}]")
            elif type == "APPLY_BUFF":
                apply_buff(char, name, value["lasting"], value["delay"], data=value.get("data"))
                broadcast_log(room, f"[{name}] が {char['name']} に付与されました。", 'state-change')
            elif type == "REMOVE_BUFF":
                remove_buff(char, name)
            elif type == "SET_FLAG":
                if 'flags' not in char:
                    char['flags'] = {}
                char['flags'][name] = value
            elif type == "MODIFY_BASE_POWER":
                # 基礎威力補正を蓄積
                char['_base_power_bonus'] = char.get('_base_power_bonus', 0) + value
                broadcast_log(room, f"[{char['name']}] 基礎威力 {value:+}", 'state-change')
            elif type == "MODIFY_FINAL_POWER":
                char['_final_power_bonus'] = char.get('_final_power_bonus', 0) + value
                broadcast_log(room, f"[{char['name']}] 最終威力 {value:+}", 'state-change')
            elif type == "SUMMON_CHARACTER":
                res = apply_summon_change(room, state, char, value)
                if res.get("ok"):
                    broadcast_log(room, res.get("message", "召喚が発生した。"), "state-change")
                else:
                    logger.warning("[pre_match summon failed] %s", res.get("message"))
            elif type == "GRANT_SKILL":
                grant_payload = dict(value) if isinstance(value, dict) else {}
                if "skill_id" not in grant_payload:
                    grant_payload["skill_id"] = name
                res = apply_grant_skill_change(room, state, actor, char, grant_payload)
                if res.get("ok"):
                    broadcast_log(room, res.get("message", "スキル付与が発生した。"), "state-change")
                else:
                    logger.warning("[pre_match grant_skill failed] %s", res.get("message"))
    except Exception:
        pass

def proceed_next_turn(room, suppress_logs=False, suppress_state_emit=False):
    """
    ターン進行ロジック。
    """
    state = get_room_state(room)
    if not state: return
    try:
        from manager.battle.common_manager import ensure_battle_state_vNext
        ensure_battle_state_vNext(state, round_value=state.get('round', 0))
    except Exception as e:
        logger.error(f"battle_state ensure failed in proceed_next_turn room={room}: {e}")

    timeline = state.get('timeline', [])
    current_entry_id = state.get('turn_entry_id')
    current_char_id = state.get('turn_char_id') # Maintain for compatibility

    if not timeline:
        return

    # 現在のエントリIDからタイムライン上の位置を特定
    current_idx = -1
    if current_entry_id:
        # Find index by entry ID
        for idx, entry in enumerate(timeline):
            if entry['id'] == current_entry_id:
                current_idx = idx
                break

    next_entry = None

    # 行動不能系バフを評価して次の行動者を探す
    from plugins.buffs.confusion import ConfusionBuff
    from plugins.buffs.immobilize import ImmobilizeBuff

    for i in range(current_idx + 1, len(timeline)):
        entry = timeline[i]

        # 既に処理済みのエントリはスキップ
        if entry.get('acted', False):
            continue

        cid = entry['char_id']
        # キャラクター参照
        char = next((c for c in state['characters'] if c['id'] == cid), None)

        # 生存者のみ
        if char and char.get('hp', 0) > 0:
            # 行動不能（混乱）
            if ConfusionBuff.is_incapacitated(char):
                logger.info(f"Skipping {char['name']} due to incapacitation (Confusion)")
                # entry is skipped but not consumed Or consumed
                # Usually incapacitation consumes the turn.
                entry['acted'] = True
                continue

            # 行動不能（Immobilize/Bu-04）
            can_act, reason = ImmobilizeBuff.can_act(char, {})
            if not can_act:
                logger.info(f"[TurnSkip] Skipping {char['name']} due to Immobilize: {reason}")
                entry['acted'] = True
                continue

            next_entry = entry
            break

    if next_entry:
        state['turn_entry_id'] = next_entry['id']
        state['turn_char_id'] = next_entry['char_id'] # Sync for frontend 'currentTurnId'

        next_char = next((c for c in state['characters'] if c['id'] == next_entry['char_id']), None)
        logger.info(f"[proceed_next_turn] Next turn: {next_char['name']} (EntryID: {next_entry['id']})")

        if not suppress_logs:
            broadcast_log(room, f"--- {next_char['name']} の行動です ---", 'turn-change')
    else:
        state['turn_char_id'] = None
        state['turn_entry_id'] = None
        if not suppress_logs:
            broadcast_log(room, "全ての行動可能キャラクターが行動済みです。ラウンド終了処理を行ってください。", 'info')

    if not suppress_state_emit:
        broadcast_state_update(room)
        save_specific_room_state(room)

def process_simple_round_end(state, room):
    """
    ラウンド終了時の共通処理（バフ時間経過、利用回数リセットなど）。
    """
    logger.debug("===== process_simple_round_end start =====")

    for char in state.get("characters", []):
        # バフの delay/lasting を進める
        if "special_buffs" in char:
            active_buffs = []
            for buff in char['special_buffs']:
                delay = buff.get("delay", 0)
                lasting = buff.get("lasting", 0)

                if delay > 0:
                    buff["delay"] = delay - 1
                    active_buffs.append(buff)
                elif lasting > 0:
                    buff["lasting"] = lasting - 1
                    if buff["lasting"] > 0:
                        if buff.get("buff_id") == "Bu-Fissure":
                            buff["name"] = f"亀裂_R{buff['lasting']}"
                        active_buffs.append(buff)
                    else:
                        if buff.get("buff_id") == "Bu-Fissure":
                            remove_count = int(buff.get("count", 0) or 0)
                            if remove_count > 0:
                                current_fissure = int(get_status_value(char, "亀裂") or 0)
                                set_status_value(char, "亀裂", max(0, current_fissure - remove_count))
                elif buff.get('is_permanent', False):
                    active_buffs.append(buff)

            char['special_buffs'] = active_buffs
            apply_origin_bonus_buffs(char)

        # アイテム使用回数リセット
        if 'round_item_usage' in char:
            char['round_item_usage'] = {}

        # スキル使用回数リセット
        if 'used_immediate_skills_this_round' in char:
            char['used_immediate_skills_this_round'] = []
        if 'used_gem_protect_this_round' in char:
            char['used_gem_protect_this_round'] = False
        if 'used_skills_this_round' in char:
            char['used_skills_this_round'] = []

    removed_summons = process_summon_round_end(state, room=room)
    for summoned in removed_summons:
        try:
            broadcast_log(room, f"{summoned.get('name', '召喚体')} は時間切れで消滅した。", "state-change")
        except Exception:
            pass

    expired_granted = process_granted_skill_round_end(state, room=room)
    for row in expired_granted:
        try:
            char_name = row.get("char_name") or "キャラクター"
            skill_id = row.get("skill_id") or "UNKNOWN"
            broadcast_log(room, f"{char_name} から付与スキル {skill_id} が解除された。", "state-change")
        except Exception:
            pass

    round_end_origin_targets = {}
    for char in state.get('characters', []):
        if char.get('hp', 0) <= 0: continue

        recoveries = get_round_end_origin_recoveries(char)
        for status_name, amount in recoveries.items():
            if int(amount or 0) <= 0:
                continue
            new_value = int(get_status_value(char, status_name)) + int(amount)
            _update_char_stat(room, char, status_name, new_value, username=f"[origin_round_end:{status_name}]")
            round_end_origin_targets.setdefault(status_name, []).append(char['name'])

    if round_end_origin_targets.get('HP'):
        broadcast_log(room, f"[マホロバ恩恵] {', '.join(round_end_origin_targets['HP'])} のHPが回復しました。", 'info')
    if round_end_origin_targets.get('MP'):
        broadcast_log(room, f"[アルトマギア恩恵] {', '.join(round_end_origin_targets['MP'])} のMPが1回復しました。", 'info')

    logger.debug("===== process_simple_round_end end =====")

