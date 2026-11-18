"""Authenticated, read-only drill calculations."""
import json
from flask import Blueprint, jsonify, request
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
