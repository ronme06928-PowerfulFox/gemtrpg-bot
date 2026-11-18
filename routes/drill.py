"""Authenticated, read-only drill calculations."""
import json
from flask import Blueprint, jsonify, request, g
from manager.utils import session_required
from manager.drill.match import calculate_match

drill_bp = Blueprint('drill', __name__)


@drill_bp.post('/api/drill/match')
@session_required
def match():
    if (request.content_length or 0) > 131072:
        return jsonify(error='要求は128KiBまでです。'), 422
    raw = request.stream.read(131073)
    if len(raw) > 131072:
        return jsonify(error='要求は128KiBまでです。'), 422
    try:
        body = json.loads(raw) if request.is_json else None
    except (ValueError, UnicodeError, RecursionError):
        body = None
    if not isinstance(body, dict) or body.keys() - {'actor','target','skill_id','target_skill_id'}:
        return jsonify(error='actor・target・skill_idを含むJSONオブジェクトで指定してください。'), 422
    try:
        return jsonify(calculate_match(body.get('actor'),body.get('target'),body.get('skill_id'),
                                       body.get('target_skill_id')))
    except ValueError as error:
        return jsonify(error=str(error)), 422


@drill_bp.post('/api/drill/character')
@session_required
def character():
    from copy import deepcopy
    from models import OwnedCharacter
    from manager.character_runtime import build_owned_character_for_play
    from manager.units.characters import build_character
    from manager.utils import apply_passive_effect_buffs
    from manager.encyclopedia import unit_entries

    if (request.content_length or 0) > 131072:
        return jsonify(error='要求は128KiBまでです。'), 422
    body=request.get_json(silent=True)
    if (not isinstance(body,dict) or body.keys() != {'source','id','side'}
            or body.get('source') not in ('owned','unit') or body.get('side') not in ('ally','enemy')
            or not isinstance(body.get('id'),str) or not 1 <= len(body['id']) <= 80):
        return jsonify(error='source・id・sideを確認してください。'), 422
    user=g.authenticated_user
    try:
        if body['source']=='owned':
            row=OwnedCharacter.query.filter_by(id=body['id'],user_id=user.id,deleted_at=None).first()
            if row is None:
                return jsonify(error='キャラクターが見つかりません。'), 404
            result=build_owned_character_for_play(row.data,body['side'])
        else:
            row=next((row for row,readable in unit_entries(user,full=user.is_catalog_author or user.is_app_admin)
                      if row.entry_id==body['id'] and readable),None)
            if row is None:
                return jsonify(error='キャラクターが見つかりません。'), 404
            payload=deepcopy(row.payload)
            payload['allow_'+body['side']]=True
            result=build_character(payload,body['side'],0,source_unit_id=row.entry_id)
            apply_passive_effect_buffs(result)
        return jsonify(character=result)
    except (ValueError,TypeError,KeyError) as error:
        return jsonify(error=str(error)), 422
