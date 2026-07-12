"""アカウント紐づけの持ちキャラ（計画36）CRUD ハンドラ。

list_owned_characters / get_owned_character / create_owned_character /
update_owned_character / delete_owned_character / grow_owned_character を担う。
持ちキャラは所有者本人のみ参照・変更できる。
"""

import re
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session

from extensions import db, all_skill_data
from manager.radiance.loader import radiance_loader
from models import OwnedCharacter
from manager.utils import session_required

owned_characters_bp = Blueprint('owned_characters', __name__)

# 1アカウントあたりの保存上限（DB肥大化の抑制。運用を見て緩める前提の初期値）。
OWNED_CHARACTER_LIMIT = 20

# commandsの1行から「【スキルID 表示名】」のIDだけを抜き出す。
# CharaCreatorのrestoreFromCommands()と同じ正規表現（挙動を合わせるため）。
_SKILL_ID_RE = re.compile(r'【([A-Za-z0-9\-]+)\s+.*?】')
# CharaCreatorの魔法カテゴリ判定（Ms/Mb/Mp シート由来のIDプレフィックス）。
_MAGIC_ID_PREFIXES = ('Ms', 'Mb', 'Mp')
_SKILL_COST_FIELD = '取得コスト'
_RADIANCE_COST_FIELD = 'cost'


def _get_param_value(data, label, default=0):
    for p in (data.get('params') or []):
        if isinstance(p, dict) and p.get('label') == label:
            try:
                return int(p.get('value'))
            except (TypeError, ValueError):
                return default
    return default


def _get_origin_id(data):
    return _get_param_value(data, '出身', 0)


def compute_exp_limit(data):
    """CharaCreator側 calculateStats() の `expLimit` 算出をそのまま移植したもの。

    経験＋シナリオ経験を基本とし、出身7（ラグラゼシス/非都市部）のみ+1される。
    """
    base_exp = _get_param_value(data, '経験', 0)
    scenario_exp = _get_param_value(data, 'シナリオ経験', 0)
    limit = base_exp + scenario_exp
    if _get_origin_id(data) == 7:
        limit += 1
    return limit


def _skill_cost(skill_id):
    skill = all_skill_data.get(skill_id)
    if not skill:
        return 0
    try:
        return int(skill.get(_SKILL_COST_FIELD, 0) or 0)
    except (TypeError, ValueError):
        return 0


def compute_used_exp(data):
    """CharaCreator側 calculateStats() の `normalCostUsed` 算出をそのまま移植したもの。

    commandsに含まれるスキルIDのコスト合計。出身6（ラグラゼシス/都市部）のみ、
    魔法カテゴリ（Ms/Mb/Mp）スキルの先頭コスト1点分がボーナス扱いで割引かれる。
    """
    magic_bonus_limit = 1 if _get_origin_id(data) == 6 else 0
    magic_bonus_used = 0
    normal_cost_used = 0
    for skill_id in _SKILL_ID_RE.findall(data.get('commands') or ''):
        cost = _skill_cost(skill_id)
        is_magic = skill_id.startswith(_MAGIC_ID_PREFIXES)
        if is_magic and magic_bonus_used < magic_bonus_limit:
            consume_bonus = min(cost, magic_bonus_limit - magic_bonus_used)
            magic_bonus_used += consume_bonus
            normal_cost_used += (cost - consume_bonus)
        else:
            normal_cost_used += cost
    return normal_cost_used


def compute_param_growth_spent(growth_log):
    """成長画面のパラメータ上昇に使った経験値の累計（growth_logから逆算）。

    スキルのコストは`commands`から`compute_used_exp`で逆算できるが、パラメータ
    上昇はcommandsに現れないため、growth_logの'growth'種別エントリに記録した
    `param_increases`の合計を別途積み上げて使用済み扱いにする。
    """
    total = 0
    for entry in (growth_log or []):
        if not isinstance(entry, dict) or entry.get('kind') != 'growth':
            continue
        increases = entry.get('param_increases')
        if isinstance(increases, dict):
            for v in increases.values():
                try:
                    total += int(v)
                except (TypeError, ValueError):
                    continue
    return total


def compute_total_used_exp(character):
    return compute_used_exp(character.data or {}) + compute_param_growth_spent(character.growth_log or [])


def compute_radiance_limit(data):
    """CharaCreator側の「通過点」（radiance-points）を輝化スキルの予算上限として扱う。"""
    return _get_param_value(data, '通過点', 0)


def _radiance_cost(skill_id, radiance_skills):
    skill = radiance_skills.get(skill_id)
    if not skill:
        return 0
    try:
        return int(skill.get(_RADIANCE_COST_FIELD, 0) or 0)
    except (TypeError, ValueError):
        return 0


def compute_radiance_used(data, radiance_skills):
    """`SPassive`配列のうち輝化スキルデータに存在するIDのコスト合計。

    `SPassive`には輝化スキルと特殊パッシブのIDが混在するが、パッシブ側のIDは
    輝化スキル辞書に存在しないため、ここでは自然に0コスト扱いとなり除外される。
    """
    total = 0
    for skill_id in (data.get('SPassive') or []):
        if isinstance(skill_id, str):
            total += _radiance_cost(skill_id, radiance_skills)
    return total


def _character_to_dict_with_exp(character):
    payload = character.to_dict()
    param_spent = compute_param_growth_spent(character.growth_log or [])
    skill_used_exp = compute_used_exp(character.data or {})
    used_exp = skill_used_exp + param_spent
    payload['used_exp'] = used_exp
    payload['remaining_exp'] = int(character.exp_total or 0) - used_exp
    # CharaCreator再編集時の「経験」欄に入れるべき予算。CharaCreator自身は現在選択中の
    # スキルコスト(skill_used_exp)を含めて上限判定するため、パラメータ成長で既に
    # 消費した分だけを exp_total から差し引いた値を渡す（残り経験値そのものではない。
    # 残り経験値を渡すと既存スキルのコストを二重に差し引いてしまう）。
    payload['skill_exp_budget'] = int(character.exp_total or 0) - param_spent

    radiance_skills = radiance_loader.load_skills()
    radiance_limit = compute_radiance_limit(character.data or {})
    radiance_used = compute_radiance_used(character.data or {}, radiance_skills)
    payload['radiance_limit'] = radiance_limit
    payload['radiance_used'] = radiance_used
    payload['radiance_remaining'] = radiance_limit - radiance_used
    return payload


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
    return jsonify({"characters": [_character_to_dict_with_exp(c) for c in characters]})


@owned_characters_bp.route('/api/owned_characters/<character_id>', methods=['GET'])
@session_required
def get_owned_character(character_id):
    user_id = session.get('user_id')
    character = _get_owned_character_or_404(character_id, user_id)
    if not character:
        return jsonify({"error": "指定された持ちキャラが見つかりません。"}), 404
    return jsonify({"character": _character_to_dict_with_exp(character)})


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
        # 作成時点の経験＋シナリオ経験を初期予算として蓄積経験値の起点にする。
        # 以後の成長（成果反映・成長画面）はここに加算され、使用済み分はdataから
        # 毎回逆算するため exp_total 自体は据え置く（決定 → 計画36 §9）。
        exp_total=compute_exp_limit(data),
        growth_log=[],
    )
    db.session.add(character)
    db.session.commit()
    return jsonify({"character": _character_to_dict_with_exp(character)}), 201


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
    return jsonify({"character": _character_to_dict_with_exp(character)})


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


@owned_characters_bp.route('/api/owned_characters/<character_id>/growth', methods=['POST'])
@session_required
def grow_owned_character(character_id):
    """計画36 Phase 5: 軽量成長画面からのスキル追加・パラメータ上昇。

    残り経験値（exp_total − 使用済み経験値）の範囲でのみ許可する。
    使用済み経験値は毎回 `data` から逆算するため、`exp_total` 自体は更新しない
    （消費すれば自動的に remaining_exp が減るだけ、という決定 → 計画36 §9）。
    パラメータ上昇は house rule として 1ポットあたり経験値1消費とする。
    """
    user_id = session.get('user_id')
    character = _get_owned_character_or_404(character_id, user_id)
    if not character:
        return jsonify({"error": "指定された持ちキャラが見つかりません。"}), 404

    payload = request.get_json(silent=True) or {}
    add_skill_ids = payload.get('add_skill_ids')
    add_skill_ids = [str(s).strip() for s in add_skill_ids if str(s).strip()] if isinstance(add_skill_ids, list) else []
    add_radiance_ids = payload.get('add_radiance_ids')
    add_radiance_ids = [str(s).strip() for s in add_radiance_ids if str(s).strip()] if isinstance(add_radiance_ids, list) else []
    param_increases_raw = payload.get('param_increases') if isinstance(payload.get('param_increases'), dict) else {}
    param_increases = {}
    for label, delta in param_increases_raw.items():
        try:
            delta_int = int(delta)
        except (TypeError, ValueError):
            continue
        if delta_int > 0:
            param_increases[str(label)] = delta_int

    if not add_skill_ids and not add_radiance_ids and not param_increases:
        return jsonify({"error": "追加するスキルまたはパラメータ上昇を指定してください。"}), 400

    data = dict(character.data or {})
    old_skill_used_exp = compute_used_exp(data)
    old_used_exp = old_skill_used_exp + compute_param_growth_spent(character.growth_log or [])

    unknown_skill_ids = [sid for sid in add_skill_ids if sid not in all_skill_data]
    if unknown_skill_ids:
        return jsonify({"error": f"未知のスキルIDです: {', '.join(unknown_skill_ids)}"}), 400

    radiance_skills = radiance_loader.load_skills()
    unknown_radiance_ids = [sid for sid in add_radiance_ids if sid not in radiance_skills]
    if unknown_radiance_ids:
        return jsonify({"error": f"未知の輝化スキルIDです: {', '.join(unknown_radiance_ids)}"}), 400

    existing_spassive = [s for s in (data.get('SPassive') or []) if isinstance(s, str)]
    duplicate_radiance_ids = [sid for sid in add_radiance_ids if sid in existing_spassive]
    if duplicate_radiance_ids:
        return jsonify({"error": f"既に習得済みの輝化スキルです: {', '.join(duplicate_radiance_ids)}"}), 400

    new_commands_lines = [str(data.get('commands') or '')]
    for skill_id in add_skill_ids:
        skill = all_skill_data.get(skill_id) or {}
        palette = str(skill.get('チャットパレット') or f"0+0 【{skill_id}】").strip()
        new_commands_lines.append(palette)
    new_commands = "\n".join(line for line in new_commands_lines if line)

    new_skill_used_exp = compute_used_exp({**data, 'commands': new_commands})
    skill_cost = new_skill_used_exp - old_skill_used_exp
    param_cost = sum(param_increases.values())
    total_cost = skill_cost + param_cost

    remaining_exp = int(character.exp_total or 0) - old_used_exp
    if total_cost > remaining_exp:
        return jsonify({
            "error": f"経験値が不足しています（必要: {total_cost} / 残り: {remaining_exp}）。",
            "remaining_exp": remaining_exp,
            "required_exp": total_cost,
        }), 400

    radiance_cost = sum(_radiance_cost(sid, radiance_skills) for sid in add_radiance_ids)
    radiance_remaining = compute_radiance_limit(data) - compute_radiance_used(data, radiance_skills)
    if radiance_cost > radiance_remaining:
        return jsonify({
            "error": f"通過点が不足しています（必要: {radiance_cost} / 残り: {radiance_remaining}）。",
            "radiance_remaining": radiance_remaining,
            "required_radiance": radiance_cost,
        }), 400

    data['commands'] = new_commands
    data['SPassive'] = existing_spassive + add_radiance_ids
    # `data`はcharacter.dataの浅いコピーのため、paramsの各要素(dict)は元のオブジェクトと
    # 共有されたままになる。ここでインプレース変更すると「変更前」スナップショットまで
    # 一緒に書き換わってしまい、SQLAlchemyの変更検知が「差分なし」と誤判定してUPDATEを
    # 発行しなくなる（コミット後に値が元に戻る）。paramsの要素は必ずコピーしてから変更する。
    params = [dict(p) if isinstance(p, dict) else p for p in (data.get('params') or [])]
    for label, delta in param_increases.items():
        found = False
        for p in params:
            if isinstance(p, dict) and p.get('label') == label:
                try:
                    p['value'] = str(int(p.get('value') or 0) + delta)
                except (TypeError, ValueError):
                    p['value'] = str(delta)
                found = True
                break
        if not found:
            params.append({'label': label, 'value': str(delta)})
    data['params'] = params

    character.data = data
    character.name = str(data.get('name') or character.name).strip()
    character.updated_at = datetime.utcnow()

    growth_log = list(character.growth_log or [])
    growth_log.append({
        'date': datetime.now(timezone.utc).isoformat(),
        'kind': 'growth',
        'added_skill_ids': add_skill_ids,
        'added_radiance_ids': add_radiance_ids,
        'param_increases': param_increases,
        'cost': total_cost,
        'radiance_cost': radiance_cost,
    })
    character.growth_log = growth_log

    db.session.commit()
    return jsonify({"character": _character_to_dict_with_exp(character)})
