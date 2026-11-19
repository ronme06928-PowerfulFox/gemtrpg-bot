"""The room and drill share the same owned/unit runtime builders."""
from copy import deepcopy
from models import OwnedCharacter
from manager.character_runtime import build_owned_character_for_play
from manager.encyclopedia import unit_entries
from manager.units.characters import build_character
from manager.utils import apply_passive_effect_buffs


class CharacterNotFound(ValueError):
    pass


def build_selection(user,selection,side,*,allow_blank=False):
    if not isinstance(selection,dict) or selection.keys()-{'source','id','name'}:
        raise ValueError('選択元とIDだけを指定してください。')
    source=selection.get('source')
    key=selection.get('id')
    if source=='blank' and allow_blank:
        from extensions import all_skill_data
        name=selection.get('name') or ('使う人' if side=='ally' else '相手')
        if not isinstance(name,str) or len(name)>100:
            raise ValueError('名前は100字以内で指定してください。')
        raw={'name':name,'hp':20,'mp':20,'maxHp':20,'maxMp':20,'params':[],
             'commands':all_skill_data.get('Ps-00',{}).get('チャットパレット','')}
        return build_owned_character_for_play(raw,side)
    if source not in ('owned','unit') or not isinstance(key,str) or not 1<=len(key)<=80:
        raise ValueError('選択元とIDを確認してください。')
    if source=='owned':
        row=OwnedCharacter.query.filter_by(id=key,user_id=user.id,deleted_at=None).first()
        if row is None:
            raise CharacterNotFound('キャラクターが見つかりません。')
        return build_owned_character_for_play(row.data,side)
    row=next((row for row,readable in unit_entries(user,full=user.is_catalog_author or user.is_app_admin)
              if row.entry_id==key and readable),None)
    if row is None:
        raise CharacterNotFound('キャラクターが見つかりません。')
    payload=deepcopy(row.payload)
    payload['allow_'+side]=True
    character=build_character(payload,side,0,source_unit_id=row.entry_id)
    apply_passive_effect_buffs(character)
    return character
