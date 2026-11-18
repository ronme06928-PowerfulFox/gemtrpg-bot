"""Bound client snapshots before calling the battle preview helpers."""
import math


def validate_snapshot(value):
    if not isinstance(value, dict):
        raise ValueError('キャラクターはJSONオブジェクトで指定してください。')
    remaining = 4096

    def visit(item, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 8:
            raise ValueError('キャラクターの構造が大きすぎます。')
        if isinstance(item, dict):
            if len(item) > 128 or any(not isinstance(key, str) or len(key) > 128 for key in item):
                raise ValueError('辞書の項目が多すぎるか、キーが長すぎます。')
            for child in item.values():
                visit(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 128:
                raise ValueError('配列は128件までです。')
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str):
            if len(item) > 2048:
                raise ValueError('文字列は2048字までです。')
        elif type(item) in (int, float):
            if not math.isfinite(item) or abs(item) > 100000:
                raise ValueError('数値は絶対値100000以内の有限値で指定してください。')
        elif item is not None and not isinstance(item, bool):
            raise ValueError('JSONで表せる値を指定してください。')
    visit(value)
    for field in ('hp','maxHp','mp','maxMp','speed','totalSpeed','initiative'):
        if field not in value:
            continue
        try:
            amount = float(value[field])
        except (ValueError,TypeError,OverflowError) as error:
            raise ValueError(f'{field}は数値で指定してください。') from error
        if isinstance(value[field],bool) or not math.isfinite(amount) or abs(amount) > 100000:
            raise ValueError(f'{field}は絶対値100000以内の有限値で指定してください。')
    for field in ('params', 'states', 'special_buffs'):
        rows = value.get(field, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f'{field}は辞書の配列で指定してください。')
        for row in rows:
            if field in ('params', 'states'):
                name = row.get('label' if field == 'params' else 'name', '')
                if not isinstance(name, str):
                    raise ValueError(f'{field}の名前は文字列で指定してください。')
                try:
                    amount = float(row.get('value', 0))
                except (ValueError, TypeError, OverflowError) as error:
                    raise ValueError(f'{field}の値は数値で指定してください。') from error
                if not math.isfinite(amount) or abs(amount) > 100000:
                    raise ValueError(f'{field}の値が範囲外です。')


def skill_id(value, *, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > 80:
        raise ValueError('スキルIDは1〜80字の文字列で指定してください。')
    return value
