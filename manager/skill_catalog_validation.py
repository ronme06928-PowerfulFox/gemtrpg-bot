"""Skill cache loading and strict validation shared by runtime updates and CLI."""

from pathlib import Path

from manager.cache_paths import SKILLS_CACHE_FILE, load_json_cache
from manager.json_rule_v2 import (
    JsonRuleV2Error,
    extract_and_normalize_skill_rule_data,
    normalize_skill_constraints_rows,
)


def load_skills(cache_file: Path = SKILLS_CACHE_FILE):
    return load_json_cache(cache_file) or {}


def _lint_embedded_skill_constraints(effects, *, skill_id, source_path):
    """APPLY_BUFF 系 effect の data.skill_constraints を検査する。

    skill_constraints はスキル本体の直下ではなく、C01 §6 の記載どおり
    effect.data.skill_constraints（封印/コスト増バフの中身）として埋め込まれる。
    """
    errors = []
    if not isinstance(effects, list):
        return errors
    for idx, effect in enumerate(effects):
        if not isinstance(effect, dict):
            continue
        data = effect.get("data")
        if not isinstance(data, dict) or "skill_constraints" not in data:
            continue
        c_path = f"{source_path}.effects[{idx}].data.skill_constraints"
        try:
            normalize_skill_constraints_rows(data.get("skill_constraints"), source_path=c_path)
        except JsonRuleV2Error as exc:
            errors.append({"skill_id": skill_id, "path": exc.path, "error": str(exc)})
    return errors


def lint_catalog(skills: dict) -> list:
    """全スキルの特記処理(JSON rule v2)を strict 正規化し、エラーを集計する。

    戻り値: [{"skill_id": ..., "path": ..., "error": ...}, ...]（空リストなら合格）
    """
    errors = []
    for skill_id, skill_data in skills.items():
        source_path = f"skill[{skill_id}]"
        try:
            normalized = extract_and_normalize_skill_rule_data(
                skill_data, skill_id=skill_id, strict=True
            )
        except JsonRuleV2Error as exc:
            errors.append({"skill_id": skill_id, "path": exc.path, "error": str(exc)})
            continue
        errors.extend(
            _lint_embedded_skill_constraints(
                normalized.get("effects"), skill_id=skill_id, source_path=source_path
            )
        )
    return errors
