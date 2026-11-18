"""Read-only odds for the currently declared single-slot pairing."""
from copy import deepcopy
import logging

from extensions import all_skill_data
from manager.drill.match import calculate_match
from manager.battle.skill_rules import (is_reciprocal_clash, _is_same_team_slot_pair,
    _infer_target_scope_from_skill_data, _get_inherent_skill_cancel_reason)
from manager.battle.match_rules import is_unmatchable_skill
from manager.battle.resolve_queue_helpers import _build_resolve_queues, _compute_single_contention
from manager.battle.evade_slot_selector import select_evade_insert_slot
from manager.battle.timeline_helpers import _is_actor_placed

logger=logging.getLogger(__name__)


def calculate_room_odds(room, source, target, candidates, yield_work=lambda: None):
    from events.battle.intent_targets import _build_tags, _infer_mass_type_from_skill, _normalize_target_by_skill
    snapshot=deepcopy({'characters':room.get('characters',[]),'battle_state':room['battle_state']})
    battle=snapshot['battle_state']
    battle.setdefault('resolve',{})
    slots=battle['slots']
    if source==target or slots[source].get('actor_id')==slots[target].get('actor_id'):
        return {}
    if any(slots[key].get('disabled') or not _is_actor_placed(snapshot,slots[key].get('actor_id'))
           for key in (source,target)):
        return {}
    intents=battle.setdefault('intents',{})
    for intent in intents.values():
        if intent.get('skill_id'):
            intent['committed']=True  # Forecast the announced selection after commitment.
    opponent=intents.get(target,{})
    opponent_id=opponent.get('skill_id')
    opponent_skill=all_skill_data.get(opponent_id)
    if (not opponent_skill or _infer_mass_type_from_skill(opponent_id) or is_unmatchable_skill(opponent_skill)
            or _infer_target_scope_from_skill_data(opponent_skill)=='self'):
        return {}
    characters={char['id']:char for char in snapshot.get('characters',[])}
    result={}
    failed=[]
    for skill_id in dict.fromkeys(candidates):
        yield_work()
        skill=all_skill_data.get(skill_id)
        if not skill or _infer_mass_type_from_skill(skill_id) or is_unmatchable_skill(skill):
            continue
        if _infer_target_scope_from_skill_data(skill)=='self':
            continue
        if _get_inherent_skill_cancel_reason(skill,opponent_skill):
            continue
        selection={'type':'single_slot','slot_id':target}
        selection,error=_normalize_target_by_skill(skill_id,selection,state=battle,source_slot_id=source,allow_none=False)
        if error:
            continue
        intents[source]={**intents.get(source,{}),'skill_id':skill_id,'committed':True,
                         'target':selection,'tags':_build_tags(skill_id,selection)}
        _build_resolve_queues(battle,intents)
        queue=battle['resolve']['single_queue']
        if source not in queue or target not in queue:
            continue
        losers=_compute_single_contention(intents,queue)['contested_losers']
        paired=is_reciprocal_clash(slots,source,target,opponent,skill,opponent_skill,contested=source in losers)
        if not paired and not _is_same_team_slot_pair(slots,source,target):
            inserted,_=select_evade_insert_slot(snapshot,battle,slots[target]['actor_id'],source)
            paired=inserted==target
        if not paired:
            continue
        try:
            odds=calculate_match(characters[slots[source]['actor_id']],characters[slots[target]['actor_id']],skill_id,opponent_id,
                                 trusted=True)
        except Exception as error:
            failed.append(f'{skill_id}: {error}')
            continue
        result[skill_id]={key:odds[key] for key in ('advantage','win_rate','has_excluded_effects')}
    if failed:
        logger.warning('Forecast skipped %d of %d skills (%s)',len(failed),len(candidates),'; '.join(failed[:3]))
    return result
