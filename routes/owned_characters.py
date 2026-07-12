"""アカウント紐づけの持ちキャラ（計画36）CRUD ハンドラ。

list_owned_characters / get_owned_character / create_owned_character /
update_owned_character / delete_owned_character を担う。
持ちキャラは所有者本人のみ参照・変更できる。
"""

import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from extensions import db
from models import OwnedCharacter
from manager.utils import session_required

owned_characters_bp = Blueprint('owned_characters', __name__)

# 1アカウントあたりの保存上限（DB肥大化の抑制。運用を見て緩める前提の初期値）。
OWNED_CHARACTER_LIMIT = 20


def _extract_character_payload(payload):
    """POST/PUT本文からキャラJSONの `data` 部を取り出し、最低限の検証を行う。

    CharaCreator出力は `{kind:"character", data:{...}}` の形。data直下を渡された
    場合もそのまま受け付ける（JSONインポート導線での柔軟性のため）。
    """
    if not isinstance(payload, dict):
        return None, "リクエストボディがJSONオブジェクトではありません。"

    raw = payload.get('data') if isinstance(payload.get('data'), dict) else payload
    if not isinstance(raw, dict):
        return None, "キャラクターデータ(data)が見つかりません。"

    name = str(raw.get('name') or '').strip()
    if not name:
        return None, "キャラクター名(name)が空です。"

    return raw, None


def _get_owned_character_or_404(character_id, user_id):
    character = OwnedCharacter.query.filter_by(
        id=character_id, user_id=user_id, deleted_at=None
    ).first()
    return character


@owned_characters_bp.route('/api/owned_characters', methods=['GET'])
@session_required
def list_owned_characters():
    user_id = session.get('user_id')
    characters = (
        OwnedCharacter.query
        .filter_by(user_id=user_id, deleted_at=None)
        .order_by(OwnedCharacter.updated_at.desc())
        .all()
    )
    return jsonify({"characters": [c.to_dict() for c in characters]})


@owned_characters_bp.route('/api/owned_characters/<character_id>', methods=['GET'])
@session_required
def get_owned_character(character_id):
    user_id = session.get('user_id')
    character = _get_owned_character_or_404(character_id, user_id)
    if not character:
        return jsonify({"error": "指定された持ちキャラが見つかりません。"}), 404
    return jsonify({"character": character.to_dict()})


@owned_characters_bp.route('/api/owned_characters', methods=['POST'])
@session_required
def create_owned_character():
    user_id = session.get('user_id')

    existing_count = OwnedCharacter.query.filter_by(user_id=user_id, deleted_at=None).count()
    if existing_count >= OWNED_CHARACTER_LIMIT:
        return jsonify({
            "error": f"持ちキャラの保存上限（{OWNED_CHARACTER_LIMIT}体）に達しています。"
        }), 400

    payload = request.get_json(silent=True) or {}
    data, error = _extract_character_payload(payload)
    if error:
        return jsonify({"error": error}), 400

    character = OwnedCharacter(
        id=f"owned_{uuid.uuid4().hex}",
        user_id=user_id,
        name=str(data.get('name') or '').strip(),
        data=data,
        exp_total=0,
        growth_log=[],
    )
    db.session.add(character)
    db.session.commit()
    return jsonify({"character": character.to_dict()}), 201


@owned_characters_bp.route('/api/owned_characters/<character_id>', methods=['PUT'])
@session_required
def update_owned_character(character_id):
    user_id = session.get('user_id')
    character = _get_owned_character_or_404(character_id, user_id)
    if not character:
        return jsonify({"error": "指定された持ちキャラが見つかりません。"}), 404

    payload = request.get_json(silent=True) or {}
    data, error = _extract_character_payload(payload)
    if error:
        return jsonify({"error": error}), 400

    character.data = data
    character.name = str(data.get('name') or '').strip()
    character.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"character": character.to_dict()})


@owned_characters_bp.route('/api/owned_characters/<character_id>', methods=['DELETE'])
@session_required
def delete_owned_character(character_id):
    user_id = session.get('user_id')
    character = _get_owned_character_or_404(character_id, user_id)
    if not character:
        return jsonify({"error": "指定された持ちキャラが見つかりません。"}), 404

    character.deleted_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "削除しました。"})
