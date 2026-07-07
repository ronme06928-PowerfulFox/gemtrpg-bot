# manager/battle/effect_handlers/buff_effects.py
# バフ系 effect ハンドラ（計画書29 Phase 3 で game_logic.process_skill_effects から移設）。
# ロジック・ログ文字列・changes_to_apply の形式は移設前と同一。
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
    "REMOVE_BUFF": handle_remove_buff,
}
