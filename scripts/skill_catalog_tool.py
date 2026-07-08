"""
スキルカタログ lint / 相場自動集計ツール
--------------------------------------
計画書 manuals/planned/31_Skill_Data_Lint_Market_Rate_Plan.md に基づく統合CLI。

サブコマンド:
    lint              スキルJSON定義（特記処理 / skill_constraints）のスキーマ・参照整合を検査する（ERROR）。
                      --update / CI ではこの ERROR 検査のみを行う（fail-closed）。
                      F02 確定基準からの相場逸脱（WARN）はデフォルトでは表示しない。
                      データが壊れていなければ相場の多少の逸脱は運用上気にしない方針のため、
                      日常運用（--update・CI）には組み込んでいない。任意で確認したい時だけ
                      `--warn` を付けて実行する（exit code には影響しない、あくまで参考情報）。
    build-market-rate F02 相場表の自動再集計

実行:
    python scripts/skill_catalog_tool.py lint
    python scripts/skill_catalog_tool.py lint --warn      # 相場逸脱WARNも見る場合
    python scripts/skill_catalog_tool.py lint --json
    python scripts/skill_catalog_tool.py build-market-rate
    python scripts/skill_catalog_tool.py build-market-rate --check
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

# Windows の CP932 コンソールで UTF-8 文字が化けないよう強制
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from manager.cache_paths import SKILLS_CACHE_FILE, load_json_cache  # noqa: E402
from manager.json_rule_v2 import (  # noqa: E402
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


def _warn_power_stage(skills):
    warnings = []
    for skill_id, skill_data, rule in _iter_rule_effects(skills):
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


def _warn_cost(skills):
    warnings = []
    for skill_id, skill_data, rule in _iter_rule_effects(skills):
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


def _warn_state_values(skills):
    warnings = []
    for skill_id, skill_data, rule in _iter_rule_effects(skills):
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


def _warn_acquire_high(skills):
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


def _warn_action_economy(skills):
    warnings = []
    for skill_id, _skill_data, rule in _iter_rule_effects(skills):
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


def warn_catalog(skills: dict) -> list:
    """F02確定基準からの相場逸脱を検出する（WARNのみ。exit codeには影響しない）。"""
    warnings = []
    warnings.extend(_warn_power_stage(skills))
    warnings.extend(_warn_cost(skills))
    warnings.extend(_warn_state_values(skills))
    warnings.extend(_warn_acquire_high(skills))
    warnings.extend(_warn_action_economy(skills))
    return warnings


def _print_report(errors, warnings, total, *, warn_checked):
    print("=" * 70)
    print("スキルカタログ lint — JSON rule v2 スキーマ・参照整合チェック")
    print("=" * 70)
    print(f"検査対象: {total} スキル")
    if not errors:
        print(">>> OK: エラーなし")
    else:
        print(f">>> NG: {len(errors)} 件のエラー")
        for err in errors:
            print(f"  [{err['skill_id']}] {err['path']}: {err['error']}")
    print("-" * 70)
    if not warn_checked:
        print("相場逸脱 WARN: 未確認（--warn を付けると表示されます。運用上は必須ではありません）")
    elif not warnings:
        print("相場逸脱 WARN: なし")
    else:
        print(f"相場逸脱 WARN: {len(warnings)} 件（参考情報。exit code には影響しません）")
        for w in warnings:
            print(f"  [{w['skill_id']}] ({w['category']}) {w['message']}")
    print("=" * 70)


def cmd_lint(args):
    skills = load_skills()
    errors = lint_catalog(skills)
    # 相場逸脱WARNはデータ破損とは無関係の参考情報であり、日常運用（--update・CI）には
    # 組み込んでいない。明示的に --warn を指定した時だけ計算・表示する。
    warnings = warn_catalog(skills) if args.warn else []
    if args.json:
        payload = {"total": len(skills), "errors": errors, "warnings_checked": bool(args.warn)}
        if args.warn:
            payload["warnings"] = warnings
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_report(errors, warnings, len(skills), warn_checked=bool(args.warn))
    return 1 if errors else 0


# ---------------------------------------------------------------------------
# build-market-rate（計画書31 Phase 2）
# ---------------------------------------------------------------------------

F02_PATH = REPO_ROOT / "manuals" / "implemented" / "F02_Battle_Balance_Designer_Skill_Manual.md"
MARKET_RATE_BEGIN = "<!-- BEGIN:market-rate -->"
MARKET_RATE_END = "<!-- END:market-rate -->"

_PREFIX_RE = re.compile(r"^([A-Za-z]+)")
_DICE_AVG_RE = re.compile(r"\+1d(\d+)")

_CATALOG_GROUPS = [
    (("Ps", "Pb", "Pp"), "物理（斬撃/打撃/貫通）。コストは FP 主体"),
    (("Ms", "Mb", "Mp"), "魔法（斬撃/打撃/貫通）。コストは MP+FP 併用"),
    (("E",), "敵専用。広域・自爆・強硬・牽制・召喚・伝授などギミック持ち"),
    (("D",), "守備（防御/回避）"),
    (("B",), "宝石の加護（即時発動の補助）"),
    (("C",), "魔力回復等（マッチ不可・自己対象）"),
]

_TIMING_LABELS = {
    "HIT": "HIT（的中時）",
    "PRE_MATCH": "PRE_MATCH（使用時）",
    "WIN": "WIN（マッチ勝利時）",
    "END_ROUND": "END_ROUND",
}
_TIMING_NOTES = {
    "HIT": "標準。数値は確定基準の相場どおり",
    "PRE_MATCH": "的中不要で確実に成立するため、同じ数値でも HIT より強い。自己バフ・準備向け",
    "WIN": "成立条件が最も重いため、HIT より1〜2段強い数値を許容できる",
    "END_ROUND": "基本技のリソース回復など、遅延リターン",
}
_TIMING_MINOR_LABEL = "その他（LOSE / UNOPPOSED / END_MATCH 等）"
_TIMING_MINOR_NOTE = "敗北補償・非対抗時ボーナスなどの補助設計"

_STATE_NOTES = {
    "出血": "標準状態異常。取得1スターターは出血4〜5的中時が基準",
    "破裂": "起爆が必要なぶん出血よりやや大きい数値を許容",
    "亀裂": "攻撃回数で膨れるため、低数値・継続制限で抑える方針が実データにも表れている",
    "戦慄": "事例が少ない。追加時は既存件数と比較する",
    "荊棘": "敵専用が中心。PC 用に持ち込む場合は要バランス相談",
}
_STATE_NOTE_DEFAULT = "新規状態異常。追加時はバランス相談を推奨"

_ACTION_ECONOMY_TYPES = ("USE_SKILL_AGAIN", "SUMMON_CHARACTER", "GRANT_SKILL")
_ACTION_ECONOMY_NOTES = {
    "USE_SKILL_AGAIN": "追加行動に等しく行動経済を直接増幅するため、新規追加時は必ずバランス相談を通す。",
    "SUMMON_CHARACTER": "召喚は行動スロット増加の影響が大きく、単独判断で追加しない。",
    "GRANT_SKILL": "スキル付与は行動スロット増加の影響が大きく、単独判断で追加しない。",
}
_EXTREME_BASE_POWER_THRESHOLD = 50
# APPLY_STATE は FP/MP/HP 等のリソース増減にも使われるため、
# 「状態異常の付与量相場」表からはリソース系 state_name を除外する。
_RESOURCE_STATE_NAMES = {"HP", "MP", "FP"}


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


def _iter_rule_effects(skills):
    """全スキルの (skill_id, skill_data, normalized_rule) を返す。

    strict 正規化に失敗するスキルは lint 側の責務なのでここでは黙って読み飛ばす
    （build-market-rate は lint 済みのカタログに対して実行する運用を想定）。
    """
    for skill_id, skill_data in skills.items():
        if not isinstance(skill_data, dict):
            continue
        try:
            rule = extract_and_normalize_skill_rule_data(skill_data, skill_id=skill_id, strict=True)
        except JsonRuleV2Error:
            continue
        yield skill_id, skill_data, rule


def _render_table(headers, aligns, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(aligns) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def build_catalog_composition_section(skills):
    counts = Counter(_skill_prefix(sid) for sid in skills)
    rows = []
    for prefixes, desc in _CATALOG_GROUPS:
        label = " / ".join(prefixes)
        count_label = " / ".join(str(counts.get(p, 0)) for p in prefixes)
        rows.append((label, count_label, desc))
    table = _render_table(["系統", "件数", "内容"], ["---", "---:", "---"], rows)

    acquire_counter = Counter(_safe_int(sd.get("取得コスト"), -1) for sd in skills.values() if isinstance(sd, dict))
    acquire_counter.pop(-1, None)
    dist_text = " / ".join(f"{k}={v}" for k, v in sorted(acquire_counter.items()))
    max_acquire = max(acquire_counter) if acquire_counter else 0
    high_ids = [sid for sid, sd in skills.items() if isinstance(sd, dict) and _safe_int(sd.get("取得コスト"), -1) == max_acquire]
    high_label = "・".join(high_ids) if high_ids else "該当なし"
    prose = (
        f"取得コスト分布は {dist_text}。**取得{max_acquire}は {high_label} のみ**であり、"
        "「取得3以上はビルドの質を変える希少枠」という確定基準が実データでも守られている。"
        "新スキルもこの分布を崩さないこと（取得2を乱発しない）。"
    )
    return f"### 現行カタログの構成\n\n{table}\n\n{prose}"


def build_power_stats_section(skills):
    groups = {}
    for skill_id, skill_data in skills.items():
        if not isinstance(skill_data, dict):
            continue
        prefix = _skill_prefix(skill_id)
        if len(prefix) != 2 or prefix[0] not in ("P", "M"):
            continue
        base_power = _safe_int(skill_data.get("基礎威力"), None)
        if base_power is None:
            continue
        dice_avg = _dice_avg(skill_data.get("ダイス威力"))
        acquire = _safe_int(skill_data.get("取得コスト"), None)
        if acquire is None:
            continue
        key = (prefix[0], acquire)
        groups.setdefault(key, []).append((base_power, base_power + dice_avg))

    label_map = {"P": "物理", "M": "魔法"}
    rows = []
    for (kind, acquire) in sorted(groups):
        vals = groups[(kind, acquire)]
        n = len(vals)
        avg_total = mean(v[1] for v in vals)
        max_total = max(v[1] for v in vals)
        rows.append((f"{label_map[kind]} 取得{acquire}", n, f"約{avg_total:.1f}", f"{max_total:.1f}"))
    table = _render_table(["区分", "件数", "期待威力平均", "上限付近"], ["---", "---:", "---:", "---:"], rows)

    prose1 = (
        "確定基準の威力段階（8/11/15）と実データはほぼ一致している。"
        "新スキルの期待威力（基礎+ダイス面数÷2+0.5）がこの帯を超える場合は、"
        "HP消費・後続依存・成立条件などの明確な代償を付けること。"
    )

    cost_counter = Counter()
    for _sid, _sd, rule in _iter_rule_effects(skills):
        for entry in rule.get("cost", []) or []:
            cost_counter[(entry.get("type"), entry.get("value"))] += 1

    def _top(cost_type, n=2):
        items = [(v, c) for (t, v), c in cost_counter.items() if t == cost_type]
        items.sort(key=lambda x: -x[1])
        return items[:n]

    fp_top = _top("FP")
    mp_top = _top("MP")
    hp_items = sorted({v for (t, v) in cost_counter if t == "HP"})
    fp_max = max((v for (t, v) in cost_counter if t == "FP"), default=0)
    mp_max = max((v for (t, v) in cost_counter if t == "MP"), default=0)

    fp_text = "と".join(f"FP{v}（{c}件）" for v, c in fp_top)
    mp_text = "と".join(f"MP{v}（{c}件）" for v, c in mp_top)
    hp_text = "・".join(str(v) for v in hp_items) if hp_items else "なし"
    prose2 = (
        f"使用コストの実勢: {fp_text}が物理の中心、{mp_text}が魔法の中心。"
        f"HPコストは{len(hp_items)}件（{hp_text}）のみで希少。"
        f"FP{fp_max}/MP{mp_max} は段階3級の重コスト帯。"
    )

    return (
        "### 期待威力の相場（基礎威力＋ダイス期待値、PC用 P/M 系のみ）\n\n"
        f"{table}\n\n{prose1}\n\n{prose2}"
    )


def build_timing_section(skills):
    counter = Counter()
    for _sid, _sd, rule in _iter_rule_effects(skills):
        for effect in rule.get("effects", []) or []:
            counter[str(effect.get("timing") or "")] += 1

    rows = []
    minor_total = 0
    minor_keys = []
    for timing, n in counter.most_common():
        if timing in _TIMING_LABELS:
            rows.append((_TIMING_LABELS[timing], n, _TIMING_NOTES[timing]))
        else:
            minor_total += n
            minor_keys.append(timing)
    # 主要4種を確定基準の並び順に整列
    order = ["HIT", "PRE_MATCH", "WIN", "END_ROUND"]
    rows.sort(key=lambda r: next((i for i, t in enumerate(order) if _TIMING_LABELS.get(t) == r[0]), 99))
    if minor_total:
        rows.append((_TIMING_MINOR_LABEL, minor_total, _TIMING_MINOR_NOTE))

    table = _render_table(["timing", "件数", "設計上の意味"], ["---", "---:", "---"], rows)
    return f"### 効果タイミングの相場と使い分け\n\n{table}"


def build_state_apply_section(skills):
    values_by_state = {}
    for _sid, _sd, rule in _iter_rule_effects(skills):
        for effect in rule.get("effects", []) or []:
            if effect.get("type") != "APPLY_STATE":
                continue
            state_name = effect.get("state_name") or effect.get("name")
            value = effect.get("value")
            if not state_name or not isinstance(value, (int, float)):
                continue
            if str(state_name) in _RESOURCE_STATE_NAMES:
                continue
            values_by_state.setdefault(str(state_name), []).append(value)

    rows = []
    for state_name, vals in sorted(values_by_state.items(), key=lambda kv: -len(kv[1])):
        n = len(vals)
        avg = mean(vals)
        note = _STATE_NOTES.get(state_name, _STATE_NOTE_DEFAULT)
        rows.append((state_name, n, f"{avg:.1f}", f"{min(vals)}〜{max(vals)}", note))
    table = _render_table(
        ["状態異常", "件数", "平均", "実勢レンジ", "設計指針（確定基準と対応）"],
        ["---", "---:", "---:", "---", "---"],
        rows,
    )
    return f"### 状態異常の付与量相場（APPLY_STATE 集計）\n\n{table}"


def build_effect_type_notes_section(skills):
    type_counter = Counter()
    holders = {t: [] for t in _ACTION_ECONOMY_TYPES}
    for skill_id, skill_data, rule in _iter_rule_effects(skills):
        seen_types_this_skill = set()
        for effect in rule.get("effects", []) or []:
            etype = str(effect.get("type") or "")
            type_counter[etype] += 1
            if etype in _ACTION_ECONOMY_TYPES and etype not in seen_types_this_skill:
                name = str(skill_data.get("デフォルト名称", "") or "")
                holders[etype].append(f"{skill_id} {name}".strip())
                seen_types_this_skill.add(etype)

    bullets = []
    n_state = type_counter.get("APPLY_STATE", 0)
    n_buff = type_counter.get("APPLY_BUFF", 0)
    bullets.append(f"`APPLY_STATE`（{n_state}件）と `APPLY_BUFF`（{n_buff}件）が主流。まずこの2つで表現できないか考える。")

    n_gain = type_counter.get("CONSUME_BUFF_COUNT_FOR_GAIN", 0)
    n_convert = type_counter.get("CONVERT_STACK_RESOURCE_VARIANT", 0)
    bullets.append(
        f"蓄積消費系（`CONSUME_BUFF_COUNT_FOR_GAIN` {n_gain}件、`CONVERT_STACK_RESOURCE_VARIANT` {n_convert}件など）"
        "は「溜める技＋放つ技」のセット運用で評価する（確定基準「セット運用」参照）。"
    )

    for etype in _ACTION_ECONOMY_TYPES:
        n = type_counter.get(etype, 0)
        names = holders.get(etype, [])
        names_text = " / ".join(names) if names else "該当なし"
        bullets.append(f"`{etype}` は現在{n}件（{names_text}）。{_ACTION_ECONOMY_NOTES[etype]}")

    extreme = []
    for skill_id, skill_data in skills.items():
        if not isinstance(skill_data, dict):
            continue
        power = _safe_int(skill_data.get("基礎威力"), None)
        if power is not None and power >= _EXTREME_BASE_POWER_THRESHOLD:
            name = str(skill_data.get("デフォルト名称", "") or "")
            extreme.append(f"{skill_id}（{name}・威力{power}）")
    if extreme:
        bullets.append(
            "・".join(extreme) + " はデバッグ/敵ギミック用の極端値。**PC 用スキルの参考値にしないこと。**"
        )

    body = "\n".join(f"- {b}" for b in bullets)
    return f"### 効果タイプ別の注意（実装済み構造の使用実績）\n\n{body}"


def build_market_rate_markdown(skills):
    total = len(skills)
    header = (
        f"*本セクションは `scripts/skill_catalog_tool.py build-market-rate` により自動生成される"
        f"（全{total}件、`data/cache/skills_cache.json` 集計）。"
        "手動で編集しないこと。数値基準の正本は引き続き上記「スキルバランス調整基準」（確定版）。*"
    )
    sections = [
        header,
        build_catalog_composition_section(skills),
        build_power_stats_section(skills),
        build_timing_section(skills),
        build_state_apply_section(skills),
        build_effect_type_notes_section(skills),
    ]
    return "\n\n".join(sections)


def _splice_market_rate_section(doc_text, new_body):
    begin_idx = doc_text.find(MARKET_RATE_BEGIN)
    end_idx = doc_text.find(MARKET_RATE_END)
    if begin_idx == -1 or end_idx == -1 or end_idx < begin_idx:
        raise RuntimeError(
            f"{MARKET_RATE_BEGIN} / {MARKET_RATE_END} マーカーが {F02_PATH} に見つかりません。"
        )
    before = doc_text[: begin_idx + len(MARKET_RATE_BEGIN)]
    after = doc_text[end_idx:]
    return f"{before}\n\n{new_body}\n\n{after}"


def cmd_build_market_rate(args):
    skills = load_skills()
    new_body = build_market_rate_markdown(skills)

    current_text = F02_PATH.read_text(encoding="utf-8")
    new_text = _splice_market_rate_section(current_text, new_body)

    if new_text == current_text:
        print("F02 の相場表は最新です（差分なし）。")
        return 0

    if args.check:
        print("NG: F02 の相場表がキャッシュの実データと乖離しています。", file=sys.stderr)
        print("再生成するには `python scripts/skill_catalog_tool.py build-market-rate` を実行してください。", file=sys.stderr)
        return 1

    F02_PATH.write_text(new_text, encoding="utf-8")
    print(f"OK: F02 の相場表を更新しました（全{len(skills)}件）。")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_lint = sub.add_parser("lint", help="スキルJSON定義のスキーマ・参照整合を検査する")
    p_lint.add_argument("--json", action="store_true", help="JSON形式で出力")
    p_lint.add_argument(
        "--warn", action="store_true",
        help="F02確定基準からの相場逸脱も表示する（任意確認用。exit codeには影響しない）",
    )
    p_lint.set_defaults(func=cmd_lint)

    p_market = sub.add_parser("build-market-rate", help="F02 相場表の自動再集計")
    p_market.add_argument("--check", action="store_true", help="差分があれば失敗させる（CI向け）")
    p_market.set_defaults(func=cmd_build_market_rate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
