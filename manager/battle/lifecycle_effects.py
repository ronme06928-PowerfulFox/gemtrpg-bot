from manager.battle.hidden_passives import reveal_passive
import copy


def process_on_death(room, char, username, ctx, death_context=None):
    """Execute on-death effects."""
    if not char: return
    logs = []


    for buff in char.get('special_buffs', []):
        effect_data = ctx['get_buff_effect'](buff.get('name'))
        if not effect_data:
            if 'data' in buff: effect_data = buff['data']
            else: continue

        on_death_effects = effect_data.get('on_death', [])
        if on_death_effects:

            from manager.room_manager import get_room_state, broadcast_log, _update_char_stat
            state = get_room_state(room)
            cause = death_context if isinstance(death_context, dict) else {}
            cause_actor = cause.get("actor") if isinstance(cause.get("actor"), dict) else None
            cause_skill_data = (
                cause.get("skill_data")
                if isinstance(cause.get("skill_data"), dict)
                else None
            )
            if cause_skill_data is None and cause.get("skill_id"):
                cause_skill_data = {"id": str(cause.get("skill_id"))}
            from manager.battle.effect_presentation import step_effects_collector
            context = {
                "characters": state['characters'],
                "room": room,
                "death_context": cause,
            }
            if step_effects_collector() is not None:
                context["fired_effects"] = step_effects_collector()

            _, l, changes = ctx['process_skill_effects'](
                on_death_effects,
                "IMMEDIATE",
                char,
                cause_actor,
                cause_skill_data,
                context=context,
            )

            if l:
                broadcast_log(room, f"[{char['name']} on_death] " + " ".join(l), "state-change")

            for (c, type, name, value) in changes:
                if type == "APPLY_STATE":
                    current = ctx['get_status_value'](c, name)
                    from manager.battle.damage_context import build_damage_context

                    _update_char_stat(
                        room,
                        c,
                        name,
                        current + value,
                        username=f"[{char['name']}:死亡時]",
                        damage_context=build_damage_context(
                            actor=char,
                            skill_id=buff.get("name"),
                            damage_type="on_death",
                        ),
                    )
                elif type == "CUSTOM_DAMAGE":
                    from manager.battle.damage_context import build_damage_context

                    current = ctx['get_status_value'](c, "HP")
                    _update_char_stat(
                        room,
                        c,
                        "HP",
                        max(0, current - int(value or 0)),
                        username=f"[{char['name']}:死亡時:{name}]",
                        damage_context=build_damage_context(
                            actor=char,
                            skill_id=buff.get("name"),
                            damage_type="on_death",
                        ),
                    )
                elif type == "APPLY_BUFF":
                    ctx['apply_buff'](c, name, value["lasting"], value["delay"], data=value.get("data"), count=value.get("count"))
                    broadcast_log(room, f"[{name}] applied to {c['name']}", "state-change")
                elif type == "SUMMON_CHARACTER":
                    from manager.summons.service import apply_summon_change

                    res = apply_summon_change(room, state, c, value)
                    if res.get("ok"):
                        broadcast_log(room, res.get("message", "Summon applied"), "state-change")
                    else:
                        ctx['logger'].warning("[on_death summon failed] %s", res.get("message"))
                elif type == "REVEAL_PASSIVE":
                    reveal_passive(room, c, name, (state or {}).get("round", 0))
                elif type == "GRANT_SKILL":
                    from manager.granted_skills.service import apply_grant_skill_change

                    grant_payload = dict(value) if isinstance(value, dict) else {}
                    if "skill_id" not in grant_payload:
                        grant_payload["skill_id"] = name
                    res = apply_grant_skill_change(room, state, char, c, grant_payload)
                    if res.get("ok"):
                        broadcast_log(room, res.get("message", "Skill grant applied"), "state-change")
                    else:
                        ctx['logger'].warning("[on_death grant_skill failed] %s", res.get("message"))


def process_battle_start(room, characters, ctx, *, state=None):
    """Apply entry effects to a live room or its isolated deployment candidate."""
    from collections import deque

    from manager.granted_skills.service import apply_grant_skill_change
    from manager.room_manager import (
        _update_char_stat, broadcast_log, broadcast_state_update,
        get_room_state, save_specific_room_state,
    )
    from manager.summons.service import apply_summon_change
    from manager.battle.timed_buffs import run_timed_buffs

    pending = deque(char for char in characters if isinstance(char, dict))
    if not pending:
        return []
    live = room is not None
    state = get_room_state(room) if state is None else state
    logs = []
    executed = False
    processed = 0

    def log(message):
        if live:
            broadcast_log(room, message, "state-change")
        else:
            logs.append(message)

    while pending:
        char = pending.popleft()
        processed += 1
        if not live and processed > 512:
            raise ValueError("戦闘突入時効果の連鎖が上限を超えました。")
        for buff in list(char.get("special_buffs") or []):
            if not isinstance(buff, dict):
                continue
            buff_name = buff.get("name")
            effect_data = ctx["get_buff_effect"](buff_name) or buff.get("data")
            if not isinstance(effect_data, dict):
                continue
            raw_effects = effect_data.get("battle_start_effect")
            if not isinstance(raw_effects, list):
                continue
            effects = [
                {**copy.deepcopy(effect), "timing": "BATTLE_START", "target": effect.get("target") or "self"}
                for effect in raw_effects if isinstance(effect, dict)
            ]
            if not effects:
                continue
            context = {"characters": state["characters"], **({"room": room} if live else {"state": state})}
            _, snippets, changes = ctx["process_skill_effects"](
                effects, "BATTLE_START", char, None, None, context=context,
            )
            if snippets:
                log(f"[{char.get('name', '')} battle_start] " + " ".join(snippets))
            for target, change_type, name, value in changes:
                if change_type == "APPLY_STATE":
                    new_value = ctx["get_status_value"](target, name) + value
                    if live:
                        _update_char_stat(room, target, name, new_value, username=f"[{buff_name}]")
                    else:
                        _set_candidate_status(target, name, new_value, ctx["set_status_value"])
                elif change_type == "APPLY_BUFF":
                    ctx["apply_buff"](target, name, value.get("lasting", 0), value.get("delay", 0),
                                      data=value.get("data"), count=value.get("count"))
                    log(f"[{name}] applied to {target.get('name', '')}")
                elif change_type == "SUMMON_CHARACTER":
                    result = apply_summon_change(room, state, target, value, run_battle_start=live)
                    if result.get("ok"):
                        if not live:
                            pending.append(result["char"])
                        log(result.get("message") or "Summon applied")
                    elif live:
                        ctx["logger"].warning("[battle_start summon failed] %s", result.get("message"))
                elif change_type == "REVEAL_PASSIVE":
                    reveal_passive(room, target, name, (state or {}).get("round", 0))
                elif change_type == "GRANT_SKILL":
                    payload = dict(value) if isinstance(value, dict) else {}
                    payload.setdefault("skill_id", name)
                    result = apply_grant_skill_change(room, state, char, target, payload)
                    if result.get("ok"):
                        log(result.get("message") or "Skill grant applied")
                    elif live:
                        ctx["logger"].warning("[battle_start grant_skill failed] %s", result.get("message"))
            executed = True

        timed_logs, _ = run_timed_buffs(room, state, char, "BATTLE_START", on_summon=pending.append)
        if timed_logs:
            executed = True
            if not live:
                logs.extend(timed_logs)

    if live and executed:
        save_specific_room_state(room)
        broadcast_state_update(room)
    return logs


def _set_candidate_status(char, name, value, set_status_value):
    limit_key = {"HP": "maxHp", "MP": "maxMp"}.get(name)
    try:
        cap = int(float(char.get(limit_key, 0)))
    except (TypeError, ValueError, OverflowError):
        cap = 0
    set_status_value(char, name, min(value, cap) if cap > 0 else value)
