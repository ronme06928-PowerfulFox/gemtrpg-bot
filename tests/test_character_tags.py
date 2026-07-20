import pytest

from manager.character_tags import (
    CharacterTagValidationError,
    apply_character_tag_policy,
    derive_player_tag_ids,
    get_effective_tag_ids,
    normalize_disabled_tag_ids,
    normalize_tag_ids,
    validate_gm_tag_ids,
    validate_player_radiance_budget,
)
from manager.radiance.loader import parse_granted_tag_ids


RADIANCE_SKILLS = {
    "S-TAG": {
        "id": "S-TAG",
        "cost": 2,
        "granted_tag_ids": ["特性:機械知識", "特性:機械知識"],
    }
}


def _player_data(*, origin="1", bonus="2", points="2"):
    return {
        "characterType": "player",
        "params": [
            {"label": "出身", "value": origin},
            {"label": "ボーナス", "value": bonus},
            {"label": "通過点", "value": points},
        ],
        "SPassive": ["S-TAG", "Pa-01"],
    }


def test_normalize_tag_ids_trims_deduplicates_and_preserves_order():
    assert normalize_tag_ids([" 種別:瓦礫 ", "機械", "種別:瓦礫", "", None]) == [
        "種別:瓦礫",
        "機械",
        "None",
    ]
    assert normalize_tag_ids("種別:瓦礫") == []


def test_disabled_tags_are_restricted_to_known_tags():
    tags = ["種別:瓦礫", "機械"]
    assert normalize_disabled_tag_ids(["機械", "未知", "機械"], tags) == ["機械"]
    assert get_effective_tag_ids({"tag_ids": tags, "disabled_tag_ids": ["機械"]}) == ["種別:瓦礫"]


def test_gm_tag_validation_rejects_newlines_and_more_than_25_codepoints():
    assert validate_gm_tag_ids(["あ" * 25]) == ["あ" * 25]
    with pytest.raises(CharacterTagValidationError, match="25文字以内"):
        validate_gm_tag_ids(["あ" * 26])
    with pytest.raises(CharacterTagValidationError, match="改行"):
        validate_gm_tag_ids(["種別:\n瓦礫"])


def test_player_tags_are_derived_from_both_countries_and_radiance_skills():
    assert derive_player_tag_ids(_player_data(), RADIANCE_SKILLS) == [
        "出身:ヨキューク・ツォー",
        "出身:アーク・ジェムリア",
        "特性:機械知識",
    ]


def test_duplicate_origin_and_bonus_country_is_deduplicated():
    assert derive_player_tag_ids(_player_data(origin="10", bonus="10"), RADIANCE_SKILLS) == [
        "出身:シンシア",
        "特性:機械知識",
    ]


def test_player_policy_discards_submitted_free_and_disabled_tags():
    data = _player_data()
    data["tag_ids"] = ["種別:瓦礫"]
    data["disabled_tag_ids"] = ["出身:ヨキューク・ツォー"]

    apply_character_tag_policy(data, allow_gm_tags=True, radiance_catalog=RADIANCE_SKILLS)

    assert data["tag_ids"] == [
        "出身:ヨキューク・ツォー",
        "出身:アーク・ジェムリア",
        "特性:機械知識",
    ]
    assert data["disabled_tag_ids"] == []


def test_gm_scenario_policy_preserves_valid_free_tags_and_disabled_subset():
    data = {
        "characterType": "scenario",
        "tag_ids": [" 種別:瓦礫 ", "機械", "種別:瓦礫"],
        "disabled_tag_ids": ["機械", "未知"],
    }

    apply_character_tag_policy(data, allow_gm_tags=True, radiance_catalog=RADIANCE_SKILLS)

    assert data["tag_ids"] == ["種別:瓦礫", "機械"]
    assert data["disabled_tag_ids"] == ["機械"]


def test_non_gm_scenario_policy_does_not_trust_free_tags():
    data = {
        "characterType": "scenario",
        "params": [{"label": "出身", "value": "10"}],
        "tag_ids": ["種別:瓦礫"],
        "disabled_tag_ids": ["種別:瓦礫"],
    }

    apply_character_tag_policy(data, allow_gm_tags=False, radiance_catalog=RADIANCE_SKILLS)

    assert data["tag_ids"] == ["出身:シンシア"]
    assert data["disabled_tag_ids"] == []


def test_player_radiance_budget_rejects_overspend():
    with pytest.raises(CharacterTagValidationError, match="通過点が不足"):
        validate_player_radiance_budget(_player_data(points="1"), RADIANCE_SKILLS)

    assert validate_player_radiance_budget(_player_data(points="2"), RADIANCE_SKILLS) == (2, 2)


def test_radiance_granted_tags_accept_json_and_delimited_cells():
    assert parse_granted_tag_ids('["特性:機械知識", "所属:工房"]') == [
        "特性:機械知識",
        "所属:工房",
    ]
    assert parse_granted_tag_ids("特性:機械知識、所属:工房\n種別:技術者") == [
        "特性:機械知識",
        "所属:工房",
        "種別:技術者",
    ]
