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
    from manager.drill.characters import build_selection, CharacterNotFound
    if (request.content_length or 0)>131072:
        return jsonify(error='要求は128KiBまでです。'),422
    body=request.get_json(silent=True)
    if (not isinstance(body,dict) or body.keys()!={'source','id','side'}
            or body.get('side') not in ('ally','enemy')):
        return jsonify(error='source・id・sideを確認してください。'),422
    try:
        result=build_selection(g.authenticated_user,{'source':body['source'],'id':body['id']},body['side'])
        return jsonify(character=result)
    except CharacterNotFound as error:
        return jsonify(error=str(error)),404
    except (ValueError,TypeError,KeyError) as error:
        return jsonify(error=str(error)),422


@drill_bp.post('/api/drill/practice')
@session_required
def create_practice():
    from manager import practice_rooms
    from manager.drill.characters import build_selection, CharacterNotFound
    from manager.room_manager import get_room_state, build_participant_state
    if (request.content_length or 0)>8192:
        return jsonify(error='要求が大きすぎます。'),422
    try:
        body=request.get_json(silent=True)
    except (ValueError,UnicodeError,RecursionError):
        body=None
    if (not isinstance(body,dict) or body.keys()-{'actor','target','mode'}
            or body.get('mode','manual') not in ('manual','auto')):
        return jsonify(error='2人の選択を確認してください。'),422
    try:
        selection={key:body.get(key) for key in ('actor','target')}
        characters=[build_selection(g.authenticated_user,selection[key],side,allow_blank=True)
                    for key,side in (('actor','ally'),('target','enemy'))]
        name,_=practice_rooms.create(g.authenticated_user,selection,characters,body.get('mode','manual'))
        return jsonify(room_name=name,state=build_participant_state(get_room_state(name))),201
    except CharacterNotFound as error:
        return jsonify(error=str(error)),404
    except (ValueError,TypeError,KeyError) as error:
        return jsonify(error=str(error)),422
