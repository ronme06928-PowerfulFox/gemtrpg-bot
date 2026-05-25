import copy


def process_on_death(room, char, username, ctx):
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
            context = {"characters": state['characters'], "room": room}

            _, l, changes = ctx['process_skill_effects'](on_death_effects, "IMMEDIATE", char, None, None, context=context)

            if l:
                broadcast_log(room, f"[{char['name']} on_death] " + " ".join(l), "state-change")

            for (c, type, name, value) in changes:
                if type == "APPLY_STATE":
                    current = ctx['get_status_value'](c, name)
                    _update_char_stat(room, c, name, current + value, username=f"[{char['name']}:死亡時]")
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


def process_battle_start(room, char, ctx):
    """Execute battle-start effects such as initial FP grants."""
    if not char: return

    executed = False

    for buff in char.get('special_buffs', []):
        buff_name = buff.get('name')
        effect_data = ctx['get_buff_effect'](buff_name)

        if not effect_data:
             if 'data' in buff:
                 effect_data = buff['data']
             else:
                 continue

        start_effects = effect_data.get('battle_start_effect', [])
        if start_effects:


            effects_to_run = copy.deepcopy(start_effects)
            for eff in effects_to_run:
                eff['timing'] = 'BATTLE_START'
                if not eff.get('target'):
                    eff['target'] = 'self'

            from manager.room_manager import get_room_state, broadcast_log, _update_char_stat
            state = get_room_state(room)
            context = {"characters": state['characters'], "room": room}

            _, l, changes = ctx['process_skill_effects'](effects_to_run, "BATTLE_START", char, None, None, context=context)

            if l:
                broadcast_log(room, f"[{char['name']} battle_start] " + " ".join(l), "state-change")

            for (c, type, name, value) in changes:
                if type == "APPLY_STATE":
                    current = ctx['get_status_value'](c, name)
                    _update_char_stat(room, c, name, current + value, username=f"[{buff_name}]")
                elif type == "APPLY_BUFF":
                     ctx['apply_buff'](c, name, value["lasting"], value["delay"], data=value.get("data"), count=value.get("count"))
                     broadcast_log(room, f"[{name}] applied to {c['name']}", "state-change")
                elif type == "SUMMON_CHARACTER":
                     from manager.summons.service import apply_summon_change

                     res = apply_summon_change(room, state, c, value)
                     if res.get("ok"):
                         broadcast_log(room, res.get("message", "Summon applied"), "state-change")
                     else:
                         ctx['logger'].warning("[battle_start summon failed] %s", res.get("message"))
                elif type == "GRANT_SKILL":
                     from manager.granted_skills.service import apply_grant_skill_change

                     grant_payload = dict(value) if isinstance(value, dict) else {}
                     if "skill_id" not in grant_payload:
                         grant_payload["skill_id"] = name
                     res = apply_grant_skill_change(room, state, char, c, grant_payload)
                     if res.get("ok"):
                         broadcast_log(room, res.get("message", "Skill grant applied"), "state-change")
                     else:
                         ctx['logger'].warning("[battle_start grant_skill failed] %s", res.get("message"))

            executed = True

    if executed:
        from manager.room_manager import save_specific_room_state, broadcast_state_update
        save_specific_room_state(room)
        broadcast_state_update(room)
