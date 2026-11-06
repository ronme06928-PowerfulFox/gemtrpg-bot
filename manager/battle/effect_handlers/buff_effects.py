# manager/battle/effect_handlers/buff_effects.py
# バフ系 effect ハンドラ（計画書29 Phase 3 で game_logic.process_skill_effects から移設）。
# ロジック・ログ文字列・changes_to_apply の形式は移設前と同一。
import copy

from manager.battle import skill_effect_helpers as helpers
from manager.logs import setup_logger

logger = setup_logger(__name__)


def handle_apply_buff_per_n(effect, target_obj, sim_target, session):
    from manager.game_logic import _get_value_for_condition

    sim_actor = session.get_simulated_char(session.actor)
    original_sim_target = session.original_sim_target
    changes_to_apply = session.changes_to_apply
    log_snippets = session.log_snippets

    source_type = effect.get("source", "self")
    if source_type == "self":
        source_obj = sim_actor
    else:
        source_obj = original_sim_target if effect.get("target") == "self" and original_sim_target else sim_target
    source_param = effect.get("source_param")
    if not source_obj or not source_param:
        return

    try:
        per_n = int(effect.get("per_N", 1))
    except (TypeError, ValueError):
        per_n = 1
    if per_n <= 0:
        return

    try:
        value_per_step = int(effect.get("value", 1))
    except (TypeError, ValueError):
        value_per_step = 1
    if value_per_step <= 0:
        return

    source_value = _get_value_for_condition(
        source_obj,
        source_param,
        context=session.context,
        actor=sim_actor,
        target=sim_target,
        source_type=source_type,
    )
    if source_value is None:
        source_value = 0
    apply_count = (source_value // per_n) * value_per_step
    try:
        max_count = int(effect.get("max_count", 0))
    except (TypeError, ValueError):
        max_count = 0
    if max_count > 0:
        apply_count = min(apply_count, max_count)
    if apply_count <= 0:
        return

    buff_name = effect.get("buff_name")
    buff_id = effect.get("buff_id")
    if not buff_name and buff_id:
        from manager.buff_catalog import get_buff_by_id
        buff_data = get_buff_by_id(buff_id)
        if buff_data:
            buff_name = buff_data.get("name")
    if not buff_name:
        return

    effect_data = effect.get("data")
    if effect_data is None:
        effect_data = {}
    elif isinstance(effect_data, dict):
        effect_data = effect_data.copy()
    else:
        effect_data = {}
    if buff_id:
        effect_data["buff_id"] = buff_id
    effect_data["count"] = apply_count

    try:
        parsed_lasting = int(effect.get("lasting", 1))
    except (TypeError, ValueError):
        parsed_lasting = 1
    try:
        parsed_delay = int(effect.get("delay", 0))
    except (TypeError, ValueError):
        parsed_delay = 0
    buff_payload = {
        "lasting": parsed_lasting,
        "delay": parsed_delay,
        "data": effect_data,
        "explicit_lasting": ("lasting" in effect),
        "count": apply_count,
    }
    changes_to_apply.append((target_obj, "APPLY_BUFF", buff_name, buff_payload))
    before_count, after_count, delta_count = helpers.simulate_apply_buff_stack(sim_target, buff_name, buff_payload)
    log_snippets.append(f"[{buff_name} 付与]")
    if delta_count != 0:
        log_snippets.append(f"[{buff_name} スタック +{delta_count} ({before_count}->{after_count})]")
    log_snippets.append(f"[{buff_name} 条件: {source_param}={source_value}, per={per_n}]")


def handle_apply_buff(effect, target_obj, sim_target, session):
    from manager.buff_catalog import get_buff_by_id, get_buff_effect

    changes_to_apply = session.changes_to_apply
    log_snippets = session.log_snippets

    buff_name = effect.get("buff_name")
    buff_id = effect.get("buff_id")
    # 移設前は「'buff_data' in locals()」で参照していたが、関数化に伴い
    # 「この effect 自身の buff_id 解決で得たカタログ情報」だけを使う挙動に固定する
    # （ループ前イテレーションの変数リーク経由で別バフの情報を引く経路は廃止）。
    buff_data = None

    if not buff_name and buff_id:
        buff_data = get_buff_by_id(buff_id)
        if buff_data:
            buff_name = buff_data.get("name")
            logger.debug(f"Resolved buff_id '{buff_id}' to buff_name '{buff_name}'")
        else:
            logger.warning(f"buff_id '{buff_id}' not found in catalog")

    if buff_name:
        effect_data = effect.get("data")
        if effect_data is None:
            effect_data = {}
        else:
            effect_data = effect_data.copy()

        if buff_id:
            effect_data["buff_id"] = buff_id

            if buff_data:
                if "description" not in effect_data:
                    effect_data["description"] = buff_data.get("description", "")
                if "flavor" not in effect_data:
                    effect_data["flavor"] = buff_data.get("flavor", "")

                catalog_effect = buff_data.get("effect", {})
                if catalog_effect.get("type") == "stat_mod":
                    stat_name = catalog_effect.get("stat")
                    mod_value = catalog_effect.get("value")

                    if stat_name and mod_value is not None:
                        if "stat_mods" not in effect_data:
                            effect_data["stat_mods"] = {}
                        effect_data["stat_mods"][stat_name] = mod_value

        catalog_effect_data = get_buff_effect(buff_name)
        if isinstance(catalog_effect_data, dict):
            for k, v in catalog_effect_data.items():
                if k not in effect_data:
                    effect_data[k] = v
                elif k == "stat_mods" and isinstance(v, dict):
                    if "stat_mods" not in effect_data:
                        effect_data["stat_mods"] = {}
                    for sk, sv in v.items():
                        if sk not in effect_data["stat_mods"]:
                            effect_data["stat_mods"][sk] = sv

        if "flavor" in effect:
            effect_data["flavor"] = effect["flavor"]

        default_lasting = -1 if helpers.normalize_buff_name(buff_name) in {"蓄力", "凝魔"} else 1
        raw_lasting = effect.get("lasting", default_lasting)
        try:
            parsed_lasting = int(raw_lasting)
        except (TypeError, ValueError):
            parsed_lasting = default_lasting
        try:
            parsed_delay = int(effect.get("delay", 0))
        except (TypeError, ValueError):
            parsed_delay = 0
        buff_payload = {
            "lasting": parsed_lasting,
            "delay": parsed_delay,
            "data": effect_data,
            "explicit_lasting": ("lasting" in effect),
        }
        if "count" in effect:
            try:
                parsed_count = int(effect.get("count"))
            except (TypeError, ValueError):
                parsed_count = 0
            if parsed_count > 0:
                buff_payload["count"] = parsed_count
                if isinstance(effect_data, dict) and "count" not in effect_data:
                    effect_data["count"] = parsed_count
        changes_to_apply.append((target_obj, "APPLY_BUFF", buff_name, buff_payload))
        before_count, after_count, delta_count = helpers.simulate_apply_buff_stack(sim_target, buff_name, buff_payload)
        log_snippets.append(f"[{buff_name} 付与]")
        if delta_count != 0:
            log_snippets.append(f"[{buff_name} スタック +{delta_count} ({before_count}->{after_count})]")


def handle_apply_buff_from_character_count(effect, target_obj, sim_target, session):
    from manager.battle.field_character_effects import count_filtered_characters

    context = session.context if isinstance(session.context, dict) else {}
    count = count_filtered_characters(
        session.actor,
        context.get("characters"),
        effect.get("character_filter"),
    )
    try:
        value_per_character = int(effect.get("value_per_character", 1) or 1)
    except (TypeError, ValueError):
        value_per_character = 1
    value = count * value_per_character
    if count <= 0 or value == 0:
        return

    dynamic_effect = copy.deepcopy(effect)
    dynamic_effect["type"] = "APPLY_BUFF"
    dynamic_effect.setdefault("target", "self")
    dynamic_effect.setdefault("lasting", 1)
    dynamic_effect.setdefault("delay", 0)
    data = dynamic_effect.get("data")
    data = copy.deepcopy(data) if isinstance(data, dict) else {}
    data["power_bonus"] = [
        {
            "operation": "FIXED",
            "value": value,
            "apply_to": str(effect.get("apply_to") or "final"),
        }
    ]
    data["character_count"] = count
    data["value_per_character"] = value_per_character
    dynamic_effect["data"] = data
    handle_apply_buff(dynamic_effect, target_obj, sim_target, session)
    session.log_snippets.append(f"[フィールド集計 {count}体 x{value_per_character}]")


def handle_remove_buff(effect, target_obj, sim_target, session):
    buff_name = effect.get("buff_name")
    if buff_name:
        session.changes_to_apply.append((target_obj, "REMOVE_BUFF", buff_name, 0))
        before_count, _after_count = helpers.simulate_remove_buff_stack(sim_target, buff_name)
        session.log_snippets.append(f"[{buff_name} 解除]")
        if before_count > 0:
            session.log_snippets.append(f"[{buff_name} スタック -{before_count} ({before_count}->0)]")


HANDLERS = {
    "APPLY_BUFF_PER_N": handle_apply_buff_per_n,
    "APPLY_BUFF": handle_apply_buff,
    "APPLY_BUFF_FROM_CHARACTER_COUNT": handle_apply_buff_from_character_count,
    "REMOVE_BUFF": handle_remove_buff,
}


SCHEMAS = {
    "APPLY_BUFF": {
        "label": "バフを付与",
        "description": "IDまたは名前でバフを付与する。未指定の効果データをカタログから補う。",
        "internal": False,
        "fields": {
            "buff_id": {"type": "buff_ref", "required": True, "label": "バフID", "description": "buff_nameとのいずれかが必要。"},
            "buff_name": {"type": "string", "required": False, "label": "バフ名", "description": "IDから解決可能。両方指定時は一致させる。"},
            "lasting": {"type": "int", "required": False, "label": "持続ラウンド", "description": "省略時1。"},
            "delay": {"type": "int", "required": False, "label": "有効化遅延", "description": "省略時0。"},
            "data": {"type": "json", "required": False, "label": "バフの効果データ", "description": "オブジェクト。カタログ効果に優先する。"},
            "data.value": {"type": "int", "required": False, "label": "効果強度", "description": "Bu-32〜Bu-47で使用する整数値。"},
            "count": {"type": "int", "required": False, "label": "付与スタック数", "description": "正数の場合に使用。"},
            "data.count": {"type": "int", "required": False, "label": "データ内スタック数"},
            "flavor": {"type": "string", "required": False, "label": "フレーバー文", "description": "data.flavorを上書きする。"},
        },
        "summary": "{target}にバフ{buff_id}を付与",
        "example": {
            "timing": "HIT",
            "type": "APPLY_BUFF",
            "target": "target",
            "buff_id": "Bu-30",
            "count": 2,
        },
    },
    "APPLY_BUFF_PER_N": {
        "label": "参照値ごとにバフを付与",
        "description": "参照値÷per_Nの整数部×valueだけバフを付与する。data.countは計算結果で上書きする。",
        "internal": False,
        "fields": {
            "buff_id": {"type": "buff_ref", "required": True, "label": "バフID", "description": "buff_nameとのいずれかが必要。"},
            "buff_name": {"type": "string", "required": False, "label": "バフ名", "description": "IDから解決可能。両方指定時は一致させる。"},
            "lasting": {"type": "int", "required": False, "label": "持続ラウンド", "description": "省略時1。"},
            "delay": {"type": "int", "required": False, "label": "有効化遅延", "description": "省略時0。"},
            "data": {"type": "json", "required": False, "label": "バフの効果データ", "description": "オブジェクト。カタログ効果に優先する。"},
            "data.value": {"type": "int", "required": False, "label": "効果強度", "description": "Bu-32〜Bu-47で使用する整数値。"},
            "source": {"type": "string", "required": False, "label": "参照元", "description": "省略時self。self以外は対象。"},
            "source_param": {"type": "string", "required": True, "label": "参照項目"},
            "per_N": {"type": "int", "required": False, "label": "区切り", "description": "省略時1。正数。"},
            "value": {"type": "int", "required": False, "label": "区切りごとのスタック", "description": "省略時1。正数。"},
            "max_count": {"type": "int", "required": False, "label": "上限スタック数", "description": "省略時0（上限なし）。"},
        },
        "summary": "{target}に{source_param}の{per_N}ごとにバフ{buff_id}を{value}付与",
        "example": {
            "timing": "HIT",
            "type": "APPLY_BUFF_PER_N",
            "target": "target",
            "buff_id": "Bu-30",
            "source_param": "出血",
            "per_N": 3,
            "value": 1,
        },
    },
    "APPLY_BUFF_FROM_CHARACTER_COUNT": {
        "label": "人数から威力バフを付与",
        "description": "フィルター一致人数×value_per_characterをdata.power_bonusに設定してバフを付与する。",
        "internal": False,
        "fields": {
            "buff_id": {"type": "buff_ref", "required": False, "label": "バフID", "description": "buff_nameとのいずれかが必要。"},
            "buff_name": {"type": "string", "required": False, "label": "バフ名", "description": "IDから解決可能。両方指定時は一致させる。"},
            "lasting": {"type": "int", "required": False, "label": "持続ラウンド", "description": "省略時1。"},
            "delay": {"type": "int", "required": False, "label": "有効化遅延", "description": "省略時0。"},
            "data": {"type": "json", "required": False, "label": "バフの効果データ", "description": "オブジェクト。カタログ効果に優先する。"},
            "data.value": {"type": "int", "required": False, "label": "効果強度", "description": "Bu-32〜Bu-47で使用する整数値。"},
            "character_filter": {"type": "json", "required": False, "label": "キャラクターフィルター"},
            "value_per_character": {"type": "int", "required": False, "label": "1体あたりの威力", "description": "省略時1。0も1として扱う。"},
            "apply_to": {"type": "string", "required": False, "label": "威力の適用先", "description": "省略時final。baseまたはfinal。"},
            "flavor": {"type": "string", "required": False, "label": "フレーバー文"},
            "count": {"type": "int", "required": False, "label": "付与スタック数"},
            "data.count": {"type": "int", "required": False, "label": "データ内スタック数"},
        },
        "summary": "{target}に人数×{value_per_character}の威力バフ{buff_name}を付与",
        "example": {
            "timing": "RESOLVE_START",
            "type": "APPLY_BUFF_FROM_CHARACTER_COUNT",
            "target": "self",
            "buff_name": "瓦礫吸収",
            "value_per_character": 1,
            "character_filter": {
                "team": "same_team",
                "alive": True,
                "placed": True,
            },
        },
    },
    "REMOVE_BUFF": {
        "label": "バフを解除",
        "description": "名前でバフを解除する。strict正規化でbuff_idを名前へ解決する。",
        "internal": False,
        "fields": {
            "buff_name": {"type": "string", "required": False, "label": "バフ名", "description": "ハンドラには必要。strict入力ではbuff_idから解決。"},
            "buff_id": {"type": "buff_ref", "required": True, "label": "バフID", "description": "strict v2入力では必須。"},
        },
        "summary": "{target}のバフ{buff_id}を解除",
        "example": {
            "timing": "HIT",
            "type": "REMOVE_BUFF",
            "target": "target",
            "buff_id": "Bu-30",
        },
    },
}
