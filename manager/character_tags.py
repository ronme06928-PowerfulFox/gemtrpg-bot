"""Character tag normalization and trusted derivation helpers."""

from __future__ import annotations

from collections.abc import Mapping


MAX_GM_TAG_LENGTH = 25

ORIGIN_COUNTRY_NAMES = {
    1: "ヨキューク・ツォー",
    2: "アーク・ジェムリア",
    3: "ラティウム",
    4: "アヌッサ・ホロウ",
    5: "マホロバ",
    6: "ラグラゼシス(都市部)",
    7: "ラグラゼシス(非都市部)",
    8: "ギァン・バルフ",
    9: "綿津見",
    10: "シンシア",
    11: "グラン・リテラール・ブラン",
    12: "オーセクト",
    13: "ヴァルヴァイレ",
    14: "フローディアス",
    15: "アル・カルメイル",
    16: "アルトマギア",
    17: "エムリダ",
}


class CharacterTagValidationError(ValueError):
    """Raised when a GM-authored tag does not satisfy the public contract."""


def normalize_tag_ids(raw_values):
    """Return trimmed, stable-order unique tag strings."""
    if not isinstance(raw_values, (list, tuple)):
        return []

    result = []
    seen = set()
    for raw_value in raw_values:
        value = str(raw_value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def normalize_disabled_tag_ids(raw_values, tag_ids):
    """Return normalized disabled tags restricted to existing tag IDs."""
    known = set(normalize_tag_ids(tag_ids))
    return [tag_id for tag_id in normalize_tag_ids(raw_values) if tag_id in known]


def get_effective_tag_ids(character_data):
    """Return tags that currently participate in rules and targeting."""
    data = character_data if isinstance(character_data, Mapping) else {}
    tag_ids = normalize_tag_ids(data.get("tag_ids"))
    disabled = set(normalize_disabled_tag_ids(data.get("disabled_tag_ids"), tag_ids))
    return [tag_id for tag_id in tag_ids if tag_id not in disabled]


def validate_gm_tag_ids(tag_ids):
    """Validate already-normalized GM-authored tags and return them."""
    normalized = normalize_tag_ids(tag_ids)
    for tag_id in normalized:
        if "\n" in tag_id or "\r" in tag_id:
            raise CharacterTagValidationError("タグ名に改行は使用できません。")
        if len(tag_id) > MAX_GM_TAG_LENGTH:
            raise CharacterTagValidationError(
                f"タグ名は{MAX_GM_TAG_LENGTH}文字以内で入力してください: {tag_id}"
            )
    return normalized


def normalize_character_tag_state(character_data, *, validate_gm_tags=False):
    """Normalize stored tag arrays without deriving or changing their source."""
    if not isinstance(character_data, dict):
        return character_data
    tag_ids = (
        validate_gm_tag_ids(character_data.get("tag_ids"))
        if validate_gm_tags
        else normalize_tag_ids(character_data.get("tag_ids"))
    )
    character_data["tag_ids"] = tag_ids
    character_data["disabled_tag_ids"] = normalize_disabled_tag_ids(
        character_data.get("disabled_tag_ids"),
        tag_ids,
    )
    return character_data


def is_scenario_character(character_data):
    data = character_data if isinstance(character_data, Mapping) else {}
    character_type = str(data.get("characterType") or "").strip().lower()
    if character_type in {"scenario", "npc", "enemy"}:
        return True
    return data.get("isNPC") is True


def _get_param_int(character_data, label, default=0):
    data = character_data if isinstance(character_data, Mapping) else {}
    for row in data.get("params") or []:
        if not isinstance(row, Mapping) or row.get("label") != label:
            continue
        try:
            return int(row.get("value"))
        except (TypeError, ValueError):
            return default
    return default


def derive_player_tag_ids(character_data, radiance_catalog=None):
    """Rebuild trusted player tags from origin and selected radiance skills."""
    data = character_data if isinstance(character_data, Mapping) else {}
    tags = []

    for label in ("出身", "ボーナス"):
        country_name = ORIGIN_COUNTRY_NAMES.get(_get_param_int(data, label, 0))
        if country_name:
            tags.append(f"出身:{country_name}")

    catalog = radiance_catalog if isinstance(radiance_catalog, Mapping) else {}
    for skill_id in data.get("SPassive") or []:
        skill = catalog.get(str(skill_id).strip())
        if not isinstance(skill, Mapping):
            continue
        tags.extend(normalize_tag_ids(skill.get("granted_tag_ids")))

    return normalize_tag_ids(tags)


def compute_radiance_budget(character_data, radiance_catalog=None):
    """Return the passage-point limit and selected radiance skill cost."""
    data = character_data if isinstance(character_data, Mapping) else {}
    catalog = radiance_catalog if isinstance(radiance_catalog, Mapping) else {}
    limit = _get_param_int(data, "通過点", 0)
    used = 0
    for skill_id in data.get("SPassive") or []:
        skill = catalog.get(str(skill_id).strip())
        if not isinstance(skill, Mapping):
            continue
        try:
            used += int(skill.get("cost", 0) or 0)
        except (TypeError, ValueError):
            continue
    return limit, used


def validate_player_radiance_budget(character_data, radiance_catalog=None):
    limit, used = compute_radiance_budget(character_data, radiance_catalog)
    if used > limit:
        raise CharacterTagValidationError(
            f"通過点が不足しています（使用: {used} / 上限: {limit}）。"
        )
    return limit, used


def apply_character_tag_policy(
    character_data,
    *,
    allow_gm_tags=False,
    radiance_catalog=None,
):
    """Normalize tags in-place according to actor permission and character type."""
    if not isinstance(character_data, dict):
        return character_data

    if allow_gm_tags and is_scenario_character(character_data):
        return normalize_character_tag_state(character_data, validate_gm_tags=True)

    character_data["tag_ids"] = derive_player_tag_ids(character_data, radiance_catalog)
    character_data["disabled_tag_ids"] = []
    return character_data
