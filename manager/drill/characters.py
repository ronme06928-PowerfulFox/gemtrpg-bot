"""The room and drill share the same owned/unit runtime builders."""
from copy import deepcopy
from models import OwnedCharacter
from manager.character_runtime import build_owned_character_for_play
from manager.encyclopedia import unit_entries
from manager.units.characters import build_character
from manager.utils import apply_passive_effect_buffs


class CharacterNotFound(ValueError):
    pass


def add_practice_skills(user, character, skills):
    from manager.encyclopedia import skill_entries
    from manager.battle.skill_access import _extract_skill_ids_from_commands

    if not isinstance(skills, list) or any(not isinstance(key, str) or not 1 <= len(key) <= 80 for key in skills):
        raise ValueError('skillsはスキルID（1〜80字）の配列で指定してください。')
    ids = list(dict.fromkeys(skills))
    if not ids:
        return ids
    readable = {row.entry_id: row.payload for row in skill_entries(user)}
    for key in ids:
        if key not in readable:
            raise ValueError(f'図鑑で読める公開スキルではありません: {key}')
        if not readable[key].get('チャットパレット', '').strip():
            raise ValueError(f'チャットパレットがありません: {key}')
    commands = character.get('commands') or ''
    held = set(_extract_skill_ids_from_commands(commands))
    lines = [readable[key]['チャットパレット'].strip() for key in ids if key not in held]
    if lines:
        character['commands'] = '\n'.join(([commands.rstrip()] if commands else []) + lines)
    return ids


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
