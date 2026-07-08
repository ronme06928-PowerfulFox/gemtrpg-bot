# manager/buff_apply.py
# バフ付与本体（計画書33 Phase 1で manager/utils.py から移設）。
# ロジック・分岐・ログは移設前と同一。utils.py 側は本モジュールを re-export する。
#
# 循環import回避のため、manager.utils への依存はすべて関数内の遅延importにする
# （utils.py がロード時に本モジュールを import するため、トップレベルで utils を
# import し返すと循環になる）。
from manager.logs import setup_logger

logger = setup_logger(__name__)


def _safe_int(value, default=0):
    # utils.py の _safe_int（複数モジュールで共有される汎用ヘルパ）へ委譲する。
    from manager.utils import _safe_int as _impl
    return _impl(value, default)


def _resolve_fissure_original_rounds(payload, fallback_lasting=0):
    if not isinstance(payload, dict):
        return _safe_int(fallback_lasting, 0)
    if "original_rounds" in payload:
        return _safe_int(payload.get("original_rounds"), _safe_int(fallback_lasting, 0))
    data = payload.get("data")
    if isinstance(data, dict) and "original_rounds" in data:
        return _safe_int(data.get("original_rounds"), _safe_int(fallback_lasting, 0))
    if "rounds" in payload:
        return _safe_int(payload.get("rounds"), _safe_int(fallback_lasting, 0))
    return _safe_int(fallback_lasting, 0)


def _resolve_fissure_add_amount(payload, explicit_count=None):
    if explicit_count is not None:
        return max(0, _safe_int(explicit_count, 0))
    if not isinstance(payload, dict):
        return 0
    for key in ("count", "fissure_count", "value"):
        if key in payload:
            return max(0, _safe_int(payload.get(key), 0))
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("count", "fissure_count", "value"):
            if key in data:
                return max(0, _safe_int(data.get(key), 0))
    return 0


def _resolve_stack_count(payload, explicit_count=None, default=0):
    if explicit_count is not None:
        return max(0, _safe_int(explicit_count, default))
    if not isinstance(payload, dict):
        return max(0, _safe_int(default, 0))
    if "count" in payload:
        return max(0, _safe_int(payload.get("count"), default))
    data = payload.get("data")
    if isinstance(data, dict) and "count" in data:
        return max(0, _safe_int(data.get("count"), default))
    return max(0, _safe_int(default, 0))


def apply_buff(char_obj, buff_name, lasting, delay, data=None, count=None):
    """バフを付与・更新する"""
    from manager.utils import (
        normalize_buff_name,
        get_status_value,
        set_status_value,
        _resolve_buff_count_from_row,
        STACK_RESOURCE_BUFF_NAMES,
        STACK_RESOURCE_BUFF_IDS,
        STACK_RESOURCE_VARIANT_KEY,
    )
    if not char_obj: return
    buff_name = normalize_buff_name(buff_name)
    if 'special_buffs' not in char_obj: char_obj['special_buffs'] = []

    existing = next((b for b in char_obj['special_buffs'] if normalize_buff_name(b.get('name')) == buff_name), None)
    payload = data if data is not None else {}
    payload['name'] = buff_name
    payload['lasting'] = lasting
    payload['delay'] = delay
    if isinstance(payload.get('data'), dict):
        inst_display_name = str(payload['data'].get('display_name', '') or '').strip()
        if inst_display_name and not str(payload.get('display_name', '') or '').strip():
            payload['display_name'] = inst_display_name
    if count is not None:
        payload['count'] = count
    if int(lasting or 0) < 0:
        payload['is_permanent'] = True

    payload['newly_applied'] = True # ★追加: 今回のアクションで適用されたことを示すフラグ

    # バフ情報の自動補完 (description, flavor, buff_idなど)
    if 'description' not in payload or 'flavor' not in payload or 'buff_id' not in payload:
        from manager.buff_catalog import get_buff_by_id, get_buff_effect
        from extensions import all_buff_data

        # ID解決
        if 'buff_id' not in payload:
            found_data = next((d for d in all_buff_data.values() if d.get('name') == buff_name), None)
            if found_data:
                payload['buff_id'] = found_data.get('id')

        catalog_data = None
        if payload.get('buff_id'):
            catalog_data = get_buff_by_id(payload.get('buff_id'))

        if catalog_data:
            if not str(payload.get('display_name', '') or '').strip():
                payload['display_name'] = (
                    str(catalog_data.get('display_name', '') or '').strip()
                    or str(catalog_data.get('name', '') or '').strip()
                    or buff_name
                )
            if 'description' not in payload and catalog_data.get('description'):
                payload['description'] = catalog_data['description']
            if 'flavor' not in payload and catalog_data.get('flavor'):
                payload['flavor'] = catalog_data['flavor']
        else:
            effect_data = get_buff_effect(buff_name)
            if effect_data:
                if 'description' not in payload and 'description' in effect_data:
                    payload['description'] = effect_data['description']
                if 'flavor' not in payload and 'flavor' in effect_data:
                    payload['flavor'] = effect_data['flavor']

    # 亀裂ラウンド管理（Bu-Fissure）:
    # - 同じ「残りラウンド(lasting)」のエントリへ count を加算
    # - 残りラウンドが異なる亀裂バケットは分離して保持
    # - 付与成功時に「亀裂」ステータスへ同量加算
    if payload.get('buff_id') == 'Bu-Fissure':
        rounds = _resolve_fissure_original_rounds(payload, fallback_lasting=lasting)
        add_amount = _resolve_fissure_add_amount(payload, explicit_count=count)
        if rounds <= 0 or add_amount <= 0:
            return

        fissure_name = f"亀裂_R{rounds}"
        payload['name'] = fissure_name
        payload['lasting'] = rounds
        payload['delay'] = max(0, _safe_int(delay, 0))
        payload['is_permanent'] = False
        payload['count'] = add_amount
        if not isinstance(payload.get('data'), dict):
            payload['data'] = {}
        payload['data']['original_rounds'] = rounds
        payload['data']['fissure_count'] = add_amount
        payload['data']['count'] = add_amount

        existing_bucket = next((
            b for b in char_obj['special_buffs']
            if isinstance(b, dict)
            and b.get('buff_id') == 'Bu-Fissure'
            and _safe_int(b.get('delay'), 0) == _safe_int(delay, 0)
            and (
                _safe_int(b.get('lasting'), 0) == rounds
                or (
                    _safe_int(b.get('lasting'), 0) <= 0
                    and _safe_int((b.get('data') or {}).get('original_rounds'), 0) == rounds
                )
            )
        ), None)

        if existing_bucket:
            prev_count = max(0, _safe_int(existing_bucket.get('count'), 0))
            new_count = prev_count + add_amount
            existing_bucket['name'] = fissure_name
            existing_bucket['count'] = new_count
            existing_bucket['delay'] = max(_safe_int(existing_bucket.get('delay'), 0), _safe_int(delay, 0))
            if _safe_int(existing_bucket.get('lasting'), 0) <= 0:
                existing_bucket['lasting'] = rounds
            if not isinstance(existing_bucket.get('data'), dict):
                existing_bucket['data'] = {}
            if 'original_rounds' not in existing_bucket['data']:
                existing_bucket['data']['original_rounds'] = rounds
            existing_bucket['data']['fissure_count'] = new_count
            existing_bucket['data']['count'] = new_count
            if payload.get('description') and not existing_bucket.get('description'):
                existing_bucket['description'] = payload.get('description')
            if payload.get('flavor') and not existing_bucket.get('flavor'):
                existing_bucket['flavor'] = payload.get('flavor')
            existing_bucket['newly_applied'] = True
        else:
            char_obj['special_buffs'].append({
                'name': fissure_name,
                'source': payload.get('source', 'skill'),
                'buff_id': 'Bu-Fissure',
                'delay': max(0, _safe_int(delay, 0)),
                'lasting': rounds,
                'is_permanent': False,
                'description': payload.get('description', ''),
                'flavor': payload.get('flavor', ''),
                'count': add_amount,
                'data': {
                    'original_rounds': rounds,
                    'fissure_count': add_amount,
                    'count': add_amount,
                },
                'newly_applied': True,
            })

        current_fissure = get_status_value(char_obj, '亀裂')
        set_status_value(char_obj, '亀裂', current_fissure + add_amount)
        return

    # 荊棘重絡 (Bu-50): スタック数を states["荊棘重絡"] に直接加算（消費コードと整合）
    if payload.get('buff_id') == 'Bu-50':
        add_amount = max(1, _safe_int(count, 1)) if count is not None else 1
        current = get_status_value(char_obj, '荊棘重絡')
        set_status_value(char_obj, '荊棘重絡', current + add_amount)
        return

    # ★ 追加: 加速(Bu-11)・減速(Bu-12) の特殊処理
    # これらは永続(lasting=-1)であり、スタック加算される
    if payload.get('buff_id') in ['Bu-11', 'Bu-12']:
        if not isinstance(payload.get('data'), dict):
            payload['data'] = {}

        added_count = _resolve_stack_count(payload, explicit_count=count, default=1)
        if added_count <= 0:
            return

        target_delay = max(1, _safe_int(delay, 0))
        target_lasting = 1
        target_buff_id = payload.get('buff_id')

        existing_bucket = next((
            b for b in char_obj.get('special_buffs', [])
            if isinstance(b, dict)
            and b.get('buff_id') == target_buff_id
            and _safe_int(b.get('delay'), 0) == target_delay
        ), None)

        if existing_bucket:
            prev_count = _resolve_stack_count(existing_bucket, default=0)
            new_count = prev_count + added_count
            existing_bucket['count'] = new_count
            existing_bucket['delay'] = target_delay
            existing_bucket['lasting'] = max(_safe_int(existing_bucket.get('lasting'), 0), target_lasting)
            existing_bucket['is_permanent'] = False
            if not isinstance(existing_bucket.get('data'), dict):
                existing_bucket['data'] = {}
            existing_bucket['data']['count'] = new_count
            existing_bucket['newly_applied'] = True
            if payload.get('description') and not existing_bucket.get('description'):
                existing_bucket['description'] = payload.get('description')
            if payload.get('flavor') and not existing_bucket.get('flavor'):
                existing_bucket['flavor'] = payload.get('flavor')
            logger.debug(
                "[SpeedMod] bucket stack buff=%s delay=%s count=%s->%s",
                buff_name,
                target_delay,
                prev_count,
                new_count,
            )
        else:
            payload['delay'] = target_delay
            payload['lasting'] = target_lasting
            payload['is_permanent'] = False
            payload['count'] = added_count
            payload['data']['count'] = added_count
            char_obj['special_buffs'].append(payload)
            logger.debug(
                "[SpeedMod] bucket create buff=%s delay=%s count=%s",
                buff_name,
                target_delay,
                added_count,
            )
        return

    # 凝魔/蓄力:
    # - count スタック加算型の特殊リソースバフ
    # - lasting 未指定時は永続(-1)として扱う
    # - 明示 lasting (>0) がある場合のみラウンド減衰させる
    normalized_name = normalize_buff_name(payload.get('name') or buff_name)
    is_stack_resource = (
        normalized_name in STACK_RESOURCE_BUFF_NAMES
        or payload.get('buff_id') in STACK_RESOURCE_BUFF_IDS
    )
    if is_stack_resource:
        added_count = _resolve_buff_count_from_row(payload, default=(count if count is not None else 1))
        if added_count <= 0:
            added_count = max(1, _safe_int(count, 1)) if count is not None else 1

        if not isinstance(payload.get('data'), dict):
            payload['data'] = {}
        existing_data = dict(existing.get('data') or {}) if isinstance(existing, dict) else {}
        incoming_variant = str(
            payload.get(STACK_RESOURCE_VARIANT_KEY)
            or payload['data'].get(STACK_RESOURCE_VARIANT_KEY)
            or ""
        ).strip()
        if not incoming_variant:
            preserved_variant = str(
                (existing.get(STACK_RESOURCE_VARIANT_KEY) if isinstance(existing, dict) else "")
                or existing_data.get(STACK_RESOURCE_VARIANT_KEY)
                or ""
            ).strip()
            if preserved_variant:
                payload[STACK_RESOURCE_VARIANT_KEY] = preserved_variant
                payload['data'][STACK_RESOURCE_VARIANT_KEY] = preserved_variant
        elif STACK_RESOURCE_VARIANT_KEY not in payload['data']:
            payload['data'][STACK_RESOURCE_VARIANT_KEY] = incoming_variant

        explicit_lasting = payload.pop("explicit_lasting", None)
        if not explicit_lasting:
            explicit_lasting = bool(payload.pop("_explicit_lasting", False))
        if not explicit_lasting and isinstance(payload.get("data"), dict):
            explicit_lasting = bool(payload["data"].pop("_explicit_lasting", False))
        if not explicit_lasting and isinstance(payload.get("data"), dict):
            explicit_lasting = bool(payload["data"].pop("_explicit_lasting", False))
        finite_lasting = _safe_int(lasting, -1) if explicit_lasting else -1

        current_count = 0
        if existing:
            current_count = _resolve_buff_count_from_row(existing, default=0)

        new_count = current_count + added_count
        payload['count'] = new_count
        payload['data']['count'] = new_count

        if finite_lasting > 0:
            payload['lasting'] = finite_lasting
            payload['is_permanent'] = False
        else:
            payload['lasting'] = -1
            payload['is_permanent'] = True

        if existing:
            existing['delay'] = max(_safe_int(existing.get('delay'), 0), _safe_int(delay, 0))
            if _safe_int(existing.get('lasting'), -1) < 0 or payload['lasting'] < 0:
                existing['lasting'] = -1
                existing['is_permanent'] = True
            else:
                existing['lasting'] = max(_safe_int(existing.get('lasting'), 0), _safe_int(payload.get('lasting'), 0))
                existing['is_permanent'] = False
            merged = dict(payload)
            if isinstance(existing.get("data"), dict) and isinstance(payload.get("data"), dict):
                merged_data = dict(existing.get("data") or {})
                merged_data.update(payload.get("data") or {})
                merged["data"] = merged_data
            existing.update(merged)
        else:
            char_obj['special_buffs'].append(payload)
        return

    # ★ 追加: 出血遷延(Bu-08) は lasting ではなく count 消費型として扱う
    # 出血遷延(Bu-08) は count 消費型として扱う
    # rule v2 の lasting は継続ラウンドなので count とは別に扱う
    if payload.get('buff_id') == 'Bu-08':
        def _resolve_count_from_payload(row):
            if isinstance(row.get('count'), (int, str)):
                try:
                    return int(row.get('count'))
                except (TypeError, ValueError):
                    pass
            d = row.get('data')
            if isinstance(d, dict) and isinstance(d.get('count'), (int, str)):
                try:
                    return int(d.get('count'))
                except (TypeError, ValueError):
                    pass
            return None

        explicit_lasting = payload.pop("explicit_lasting", None)
        if not explicit_lasting:
            explicit_lasting = bool(payload.pop("_explicit_lasting", False))
        if not explicit_lasting and isinstance(payload.get("data"), dict):
            explicit_lasting = bool(payload["data"].pop("_explicit_lasting", False))
        added_count = _resolve_count_from_payload(payload)
        if added_count is None and count is not None:
            try:
                added_count = int(count)
            except (TypeError, ValueError):
                added_count = None
        if added_count is None and explicit_lasting:
            try:
                parsed_lasting = int(lasting)
            except (TypeError, ValueError):
                parsed_lasting = 0
            if parsed_lasting > 0:
                added_count = parsed_lasting
        if added_count is None:
            added_count = 1
        added_count = max(1, int(added_count))

        payload['is_permanent'] = True
        payload['lasting'] = -1
        if not isinstance(payload.get('data'), dict):
            payload['data'] = {}

        current_count = 0
        if existing and existing.get('buff_id') == 'Bu-08':
            current_count = _resolve_count_from_payload(existing) or 1
        new_count = current_count + added_count
        payload['count'] = new_count
        payload['data']['count'] = new_count

        if existing:
            existing['delay'] = max(existing.get('delay', 0), delay)
            existing.update(payload)
        else:
            char_obj['special_buffs'].append(payload)
        return

    # ★ 追加: 震盪(Bu-29) は count 加算 + 初回付与時の lasting を維持
    if payload.get('buff_id') == 'Bu-29':
        incoming_count = _resolve_stack_count(payload, explicit_count=count, default=1)
        existing_count = _resolve_stack_count(existing, default=1) if existing else 0
        new_count = existing_count + incoming_count

        payload_lasting = _safe_int(lasting, 0)
        payload_delay = _safe_int(delay, 0)
        fixed_lasting = payload_lasting
        max_delay = payload_delay
        if existing:
            # 既存がある場合は lasting を上書きせず、最初に付与された継続ラウンドを維持する
            fixed_lasting = _safe_int(existing.get('lasting'), payload_lasting)
            max_delay = max(_safe_int(existing.get('delay'), 0), payload_delay)

        payload['lasting'] = fixed_lasting
        payload['delay'] = max_delay
        payload['count'] = new_count
        if not isinstance(payload.get('data'), dict):
            payload['data'] = {}
        payload['data']['count'] = new_count

        if existing:
            existing['lasting'] = fixed_lasting
            existing['delay'] = max_delay
            existing.update(payload)
        else:
            char_obj['special_buffs'].append(payload)
        return

    if existing:
        existing['lasting'] = max(existing.get('lasting', 0), lasting)
        existing['delay'] = max(existing.get('delay', 0), delay)
        existing.update(payload)
    else:
        char_obj['special_buffs'].append(payload)
