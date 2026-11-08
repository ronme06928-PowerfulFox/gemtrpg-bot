"""スキルの相場の注意。CLIと管理用検査で共通に使う。"""
import re
from manager.json_rule_v2 import JsonRuleV2Error, extract_and_normalize_skill_rule_data

_PREFIX_RE = re.compile(r"^([A-Za-z]+)")
_DICE_AVG_RE = re.compile(r"\+1d(\d+)")

# ---------------------------------------------------------------------------
# 相場逸脱 WARN（計画書31 Phase 3）
# ---------------------------------------------------------------------------
#
# 基準値は F02_Battle_Balance_Designer_Skill_Manual.md の
# 「スキルバランス調整基準（確定版）」（人手管理の正本）から転記した定数。
# F02 の確定基準を更新した場合は、この定数群も見直すこと（決定事項ログ §8 参照）。

# 威力段階（F02: 段階1=8 / 段階2=11 / 段階3=15）。取得コストをそのまま段階とみなす。
POWER_STAGE_BASELINE = {1: 8, 2: 11, 3: 15}
POWER_STAGE_TOLERANCE = 4  # 期待威力がこの許容差を超えて外れたら WARN

# 使用コストの基準（F02: 物理FP1/3/5前後、魔法MP2/3/6・FP0/1.5/3前後）。
COST_BASELINE = {
    ("P", 1): {"FP": 1},
    ("P", 2): {"FP": 3},
    ("P", 3): {"FP": 5},
    ("M", 1): {"MP": 2, "FP": 0},
    ("M", 2): {"MP": 3, "FP": 1.5},
    ("M", 3): {"MP": 6, "FP": 3},
}
COST_TOLERANCE = 2

# 状態異常付与量の実勢レンジ（F02: 出血3〜6中心/破裂2〜8/亀裂1〜3/戦慄3〜6）。
# PC用スキル（P/M系）のみ対象。敵専用(E系)は意図的に高い値を取りうるため対象外。
STATE_VALUE_RANGE = {
    "出血": (3, 6),
    "破裂": (2, 8),
    "亀裂": (1, 3),
    "戦慄": (3, 6),
}

# 取得コスト3以上（希少枠）として既に確定基準で承認済みのスキルID。
ACQUIRE_HIGH_APPROVED = {"Ms-07"}

# 行動経済に直結する効果タイプを、既に確定基準で承認済みのスキルID。
ACTION_ECONOMY_APPROVED = {
    "USE_SKILL_AGAIN": {"Ps-04", "Mp-09", "Mp-14"},
    "SUMMON_CHARACTER": {"E-19"},
    "GRANT_SKILL": {"E-21"},
}

# skill_id 単位の許容リスト。(category, skill_id) -> 理由。
# 該当する WARN カテゴリを個別に無効化する（F02 に明記済みの意図的な例外向け）。
WARN_ALLOWLIST = {
    ("power_stage", "Ms-09"): "HP消費前提のため期待威力22は妥当（瀉血、F02記載の既知例外）",
    ("power_stage", "Mp-08"): "F02「主要確定調整レコード」で承認済み（高威力・亀裂付与だが重コストで通常大技枠として妥当）",
    ("cost", "Mp-08"): "F02「主要確定調整レコード」で承認済み（MP6・FP4 は高威力・亀裂付与の対価）",
    ("state_value", "Ps-13"): "F02「主要確定調整レコード」で承認済み（出血7と蓄力消費FP回収の安定性込みで妥当）",
}


def _is_pc_prefix(prefix):
    return len(prefix) == 2 and prefix[0] in ("P", "M")


def _has_conditional_power_scaling(rule):
    """power_bonus[] や条件付き DAMAGE_BONUS/MODIFY_ROLL を持つスキルか。

    これらは「基礎威力+ダイス期待値」だけでは実質威力を表せないため、
    power_stage の乖離チェック対象から外す（誤検知防止）。
    """
    if rule.get("power_bonus"):
        return True
    for effect in rule.get("effects", []) or []:
        if effect.get("type") in ("DAMAGE_BONUS", "MODIFY_ROLL") and effect.get("condition"):
            return True
    return False


def _warn_power_stage(skills, *, buff_resolver=None):
    warnings = []
    for skill_id, skill_data, rule in _iter_rule_effects(skills, buff_resolver=buff_resolver):
        prefix = _skill_prefix(skill_id)
        if not _is_pc_prefix(prefix):
            continue
        if ("power_stage", skill_id) in WARN_ALLOWLIST:
            continue
        if _has_conditional_power_scaling(rule):
            continue
        acquire = _safe_int(skill_data.get("取得コスト"), None)
        base_power = _safe_int(skill_data.get("基礎威力"), None)
        if acquire is None or acquire <= 0 or base_power is None:
            continue
        tier = min(acquire, 3)
        baseline = POWER_STAGE_BASELINE.get(tier)
        if baseline is None:
            continue
        expected = base_power + _dice_avg(skill_data.get("ダイス威力"))
        if abs(expected - baseline) > POWER_STAGE_TOLERANCE:
            warnings.append({
                "category": "power_stage",
                "skill_id": skill_id,
                "message": (
                    f"期待威力{expected:.1f}が取得{acquire}の目安{baseline}から乖離"
                    f"（許容±{POWER_STAGE_TOLERANCE}）"
                ),
            })
    return warnings


def _warn_cost(skills, *, buff_resolver=None):
    warnings = []
    for skill_id, skill_data, rule in _iter_rule_effects(skills, buff_resolver=buff_resolver):
        prefix = _skill_prefix(skill_id)
        if not _is_pc_prefix(prefix):
            continue
        if ("cost", skill_id) in WARN_ALLOWLIST:
            continue
        acquire = _safe_int(skill_data.get("取得コスト"), None)
        if acquire is None or acquire <= 0:
            continue
        tier = min(acquire, 3)
        baseline = COST_BASELINE.get((prefix[0], tier))
        if not baseline:
            continue
        actual = {}
        for entry in rule.get("cost", []) or []:
            c_type = entry.get("type")
            try:
                actual[c_type] = actual.get(c_type, 0) + int(entry.get("value", 0))
            except (TypeError, ValueError):
                continue
        for cost_type, base_value in baseline.items():
            actual_value = actual.get(cost_type, 0)
            if abs(actual_value - base_value) > COST_TOLERANCE:
                warnings.append({
                    "category": "cost",
                    "skill_id": skill_id,
                    "message": (
                        f"{cost_type}コスト{actual_value}が取得{acquire}の目安{base_value}から乖離"
                        f"（許容±{COST_TOLERANCE}）"
                    ),
                })
    return warnings


def _warn_state_values(skills, *, buff_resolver=None):
    warnings = []
    for skill_id, skill_data, rule in _iter_rule_effects(skills, buff_resolver=buff_resolver):
        prefix = _skill_prefix(skill_id)
        if not _is_pc_prefix(prefix):
            continue
        if ("state_value", skill_id) in WARN_ALLOWLIST:
            continue
        for effect in rule.get("effects", []) or []:
            if effect.get("type") != "APPLY_STATE":
                continue
            # 基準値は「的中時(HIT)」を前提に定義されている（F02: 出血4〜5的中時が基準）。
            # WIN 等の非HITタイミングは意図的に別の値を取りうるため対象外にする。
            if effect.get("timing") != "HIT":
                continue
            state_name = str(effect.get("state_name") or effect.get("name") or "")
            value_range = STATE_VALUE_RANGE.get(state_name)
            if not value_range:
                continue
            value = effect.get("value")
            if not isinstance(value, (int, float)):
                continue
            lo, hi = value_range
            if not (lo <= value <= hi):
                warnings.append({
                    "category": "state_value",
                    "skill_id": skill_id,
                    "message": f"{state_name}付与量{value}が実勢レンジ{lo}〜{hi}から外れている",
                })
    return warnings


def _warn_acquire_high(skills, *, buff_resolver=None):
    warnings = []
    for skill_id, skill_data in skills.items():
        if not isinstance(skill_data, dict):
            continue
        prefix = _skill_prefix(skill_id)
        if not _is_pc_prefix(prefix):
            continue
        acquire = _safe_int(skill_data.get("取得コスト"), None)
        if acquire is None or acquire < 3:
            continue
        if skill_id in ACQUIRE_HIGH_APPROVED or ("acquire_cost", skill_id) in WARN_ALLOWLIST:
            continue
        warnings.append({
            "category": "acquire_cost",
            "skill_id": skill_id,
            "message": f"取得コスト{acquire}は希少枠。承認済みリストにない新規追加のため要確認",
        })
    return warnings


def _warn_action_economy(skills, *, buff_resolver=None):
    warnings = []
    for skill_id, _skill_data, rule in _iter_rule_effects(skills, buff_resolver=buff_resolver):
        seen = set()
        for effect in rule.get("effects", []) or []:
            etype = str(effect.get("type") or "")
            approved = ACTION_ECONOMY_APPROVED.get(etype)
            if approved is None or etype in seen:
                continue
            seen.add(etype)
            if skill_id in approved or ("action_economy", skill_id) in WARN_ALLOWLIST:
                continue
            warnings.append({
                "category": "action_economy",
                "skill_id": skill_id,
                "message": f"`{etype}` を新規保有。行動経済に直結するためバランス相談を通すこと",
            })
    return warnings


def warn_catalog(skills: dict, *, buff_resolver=None) -> list:
    """F02確定基準からの相場逸脱を検出する（WARNのみ。exit codeには影響しない）。"""
    warnings = []
    warnings.extend(_warn_power_stage(skills, buff_resolver=buff_resolver))
    warnings.extend(_warn_cost(skills, buff_resolver=buff_resolver))
    warnings.extend(_warn_state_values(skills, buff_resolver=buff_resolver))
    warnings.extend(_warn_acquire_high(skills, buff_resolver=buff_resolver))
    warnings.extend(_warn_action_economy(skills, buff_resolver=buff_resolver))
    return warnings


def _skill_prefix(skill_id):
    m = _PREFIX_RE.match(str(skill_id or ""))
    return m.group(1) if m else str(skill_id or "")


def _dice_avg(dice_text):
    m = _DICE_AVG_RE.match(str(dice_text or ""))
    if not m:
        return 0.0
    faces = int(m.group(1))
    return (faces + 1) / 2


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _iter_rule_effects(skills, *, buff_resolver=None):
    """全スキルの (skill_id, skill_data, normalized_rule) を返す。

    strict 正規化に失敗するスキルは lint 側の責務なのでここでは黙って読み飛ばす
    （build-market-rate は lint 済みのカタログに対して実行する運用を想定）。
    """
    for skill_id, skill_data in skills.items():
        if not isinstance(skill_data, dict):
            continue
        try:
            rule = extract_and_normalize_skill_rule_data(skill_data, skill_id=skill_id, strict=True, buff_resolver=buff_resolver)
        except JsonRuleV2Error:
            continue
        yield skill_id, skill_data, rule


