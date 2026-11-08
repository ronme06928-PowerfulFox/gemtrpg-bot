"""
スキルカタログ lint / 相場レポート生成ツール
--------------------------------------
計画書 manuals/planned/31_Skill_Data_Lint_Market_Rate_Plan.md に基づく統合CLI。

サブコマンド:
    lint              スキルJSON定義（特記処理 / skill_constraints）のスキーマ・参照整合を検査する（ERROR）。
                      CI ではこの ERROR 検査のみを行う（fail-closed）。
                      F02 確定基準からの相場逸脱（WARN）はデフォルトでは表示しない。
                      データが壊れていなければ相場の多少の逸脱は運用上気にしない方針のため、
                      CIには組み込んでいない。任意で確認したい時だけ
                      `--warn` を付けて実行する（exit code には影響しない、あくまで参考情報）。
    build-market-rate 現在のキャッシュから相場レポートを標準出力する（任意確認用）

実行:
    python scripts/skill_catalog_tool.py lint
    python scripts/skill_catalog_tool.py lint --warn      # 相場逸脱WARNも見る場合
    python scripts/skill_catalog_tool.py lint --json
    python scripts/skill_catalog_tool.py build-market-rate
"""
import argparse
from contextlib import redirect_stdout
import json
import os
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

from manager.skill_catalog_validation import lint_catalog, load_skills  # noqa: E402
from manager.skill_catalog_warnings import (warn_catalog, _skill_prefix, _dice_avg,
    _safe_int, _iter_rule_effects)  # noqa: E402


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


def _load_buff_catalog_for_lint():
    from flask import has_app_context
    from extensions import all_buff_data, db
    from manager.catalog.repository import seed_kind_if_empty, load_kind_into_memory
    if all_buff_data:
        return
    if has_app_context():
        seed_kind_if_empty("buff")
        load_kind_into_memory("buff")
        return
    # CLIはバフだけを準備する。app.pyの既定アプリや全種類の起動処理は実行しない。
    previous = os.environ.get("GEMTRPG_DISABLE_DEFAULT_APP")
    os.environ["GEMTRPG_DISABLE_DEFAULT_APP"] = "1"
    try:
        with redirect_stdout(sys.stderr):
            from app import create_app
            application = create_app(run_startup=False, register_sockets=False, register_routes=False)
            with application.app_context():
                db.create_all()
                seed_kind_if_empty("buff")
                load_kind_into_memory("buff")
    finally:
        if previous is None:
            os.environ.pop("GEMTRPG_DISABLE_DEFAULT_APP", None)
        else:
            os.environ["GEMTRPG_DISABLE_DEFAULT_APP"] = previous


def cmd_lint(args):
    _load_buff_catalog_for_lint()
    skills = load_skills()
    errors = lint_catalog(skills)
    # 相場逸脱WARNはデータ破損とは無関係の参考情報であり、CIには
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
# build-market-rate（オンデマンド相場レポート）
# ---------------------------------------------------------------------------


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
        f"*本レポートは `scripts/skill_catalog_tool.py build-market-rate` によりオンデマンド生成された"
        f"（全{total}件、`data/cache/skills_cache.json` 集計）。"
        "数値基準の正本は `manuals/implemented/F02_Battle_Balance_Designer_Skill_Manual.md` の"
        "「スキルバランス調整基準」（確定版）。*"
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


def cmd_build_market_rate(args):
    skills = load_skills()
    print(build_market_rate_markdown(skills))
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

    p_market = sub.add_parser("build-market-rate", help="現在のキャッシュから相場レポートを表示する")
    p_market.set_defaults(func=cmd_build_market_rate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
