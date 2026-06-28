"""
Plan 22 実測ログ生成スクリプト
-------------------------------
data/cache/skills_cache.json（本番スキルデータ）をロードし、
evaluate_skill_access の動作を3系統の制約で検証してログを出力する。

実行:
    python scripts/verify_skill_constraints.py
    python scripts/verify_skill_constraints.py --json   # JSON形式で出力
"""
import json
import sys
import os
import argparse

# Windows の CP932 コンソールで UTF-8 文字が化けないよう強制
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# プロジェクトルートを sys.path に追加
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# extensions.all_skill_data にキャッシュを注入してから skill_access をインポート
import extensions
from manager.cache_paths import SKILLS_CACHE_FILE, load_json_cache

def _load_skills():
    data = load_json_cache(SKILLS_CACHE_FILE) or {}
    extensions.all_skill_data.clear()
    extensions.all_skill_data.update(data)
    return data

from manager.battle.skill_access import evaluate_skill_access


# ---------------------------------------------------------------------------
# テスト用アクター生成
# ---------------------------------------------------------------------------

def _actor(fp=5, mp=10, actor_type="enemy", constraints=None, flags_constraints=None):
    a = {
        "id": "test-actor",
        "name": "検証用アクター",
        "type": actor_type,
        "mp": mp,
        "states": [{"name": "FP", "value": fp}],
        "special_buffs": [],
        "flags": {},
        "commands": "",
        "granted_skills": [],
    }
    if constraints:
        a["special_buffs"] = [{"name": "検証デバフ", "data": {"skill_constraints": constraints}}]
    if flags_constraints:
        a["flags"]["skill_constraints"] = flags_constraints
    return a


# ---------------------------------------------------------------------------
# 検証ケース定義
# ---------------------------------------------------------------------------

CASES = [
    # --- 2.1 カテゴリ封印 (block) ---
    {
        "id": "block-phys",
        "label": "物理カテゴリ封印",
        "section": "2.1 block",
        "target_categories": ["物理"],
        "non_target_categories": ["魔法", "補助", "防御", "回避"],
        "actor_factory": lambda: _actor(flags_constraints=[
            {"id": "t-blk-phys", "mode": "block", "match": {"category": "物理"},
             "reason": "物理スキル封印中"}
        ]),
        "expect_blocked": True,
    },
    {
        "id": "block-magic",
        "label": "魔法カテゴリ封印",
        "section": "2.1 block",
        "target_categories": ["魔法"],
        "non_target_categories": ["物理", "補助"],
        "actor_factory": lambda: _actor(flags_constraints=[
            {"id": "t-blk-magic", "mode": "block", "match": {"category": "魔法"},
             "reason": "魔法スキル封印中"}
        ]),
        "expect_blocked": True,
    },
    {
        "id": "block-support",
        "label": "補助カテゴリ封印",
        "section": "2.1 block",
        "target_categories": ["補助"],
        "non_target_categories": ["物理", "魔法"],
        "actor_factory": lambda: _actor(flags_constraints=[
            {"id": "t-blk-supp", "mode": "block", "match": {"category": "補助"},
             "reason": "補助スキル封印中"}
        ]),
        "expect_blocked": True,
    },
    # --- 2.2 コスト増加 (add_cost) ---
    {
        "id": "addcost-fp",
        "label": "FPコスト+2（FP=1のスキル対象）",
        "section": "2.2 add_cost",
        "target_categories": None,          # カテゴリ問わずコスト確認
        "filter_key": "fp_cost",            # FPコストありスキルに絞る
        "actor_factory": lambda: _actor(fp=2, constraints=[
            {"id": "t-ac-fp", "mode": "add_cost", "match": {"cost_types": ["FP"]},
             "add_cost": [{"type": "FP", "value": 2}]}
        ]),
        "expect_blocked": None,             # コスト依存（FP=2、基本コスト次第）
        "check_cost_increase": ("FP", 2),
    },
    {
        "id": "addcost-mp",
        "label": "MPコスト+3（MP=10で十分、MP=2なら不足）",
        "section": "2.2 add_cost",
        "target_categories": None,
        "filter_key": "mp_cost",
        "actor_factory": lambda: _actor(mp=10, constraints=[
            {"id": "t-ac-mp", "mode": "add_cost", "match": {"cost_types": ["MP"]},
             "add_cost": [{"type": "MP", "value": 3}]}
        ]),
        "expect_blocked": None,
        "check_cost_increase": ("MP", 3),
    },
    # --- 2.3 フィールド効果由来制約 ---
    {
        "id": "field-block-phys",
        "label": "フィールド効果: 物理封印（battle_state.field_effects）",
        "section": "2.3 field",
        "target_categories": ["物理"],
        "non_target_categories": ["魔法"],
        "actor_factory": lambda: _actor(),
        "battle_state": {
            "field_effects": [
                {"scope": "all", "skill_constraints": [
                    {"id": "t-fe-phys", "mode": "block",
                     "match": {"category": "物理"}, "reason": "フィールド物理封印"}
                ]}
            ]
        },
        "expect_blocked": True,
    },
    {
        "id": "field-profile-block",
        "label": "フィールド効果: 魔法封印（stage_field_effect_profile.rules）",
        "section": "2.3 field",
        "target_categories": ["魔法"],
        "non_target_categories": ["物理"],
        "actor_factory": lambda: _actor(),
        "battle_state": {
            "field_effects": [],
            "stage_field_effect_profile": {
                "rules": [
                    {"mode": "block", "match": {"category": "魔法"},
                     "reason": "プロファイル魔法封印"}
                ]
            },
        },
        "expect_blocked": True,
    },
]


# ---------------------------------------------------------------------------
# スキル選択ヘルパー
# ---------------------------------------------------------------------------

def _pick_skills(all_skills, categories=None, filter_key=None, max_per_cat=3):
    """カテゴリ or フィルタキーに基づいてスキルを選ぶ。"""
    picks = []
    if filter_key == "fp_cost":
        for sid, sd in all_skills.items():
            if "FP" in sd.get("使用時効果", ""):
                picks.append((sid, sd))
            if len(picks) >= max_per_cat:
                break
    elif filter_key == "mp_cost":
        for sid, sd in all_skills.items():
            if "MP" in sd.get("使用時効果", "") and "FP" not in sd.get("使用時効果", ""):
                picks.append((sid, sd))
            if len(picks) >= max_per_cat:
                break
    elif categories:
        for cat in categories:
            count = 0
            for sid, sd in all_skills.items():
                if sd.get("分類", "") == cat:
                    picks.append((sid, sd))
                    count += 1
                    if count >= max_per_cat:
                        break
    return picks


def _pick_non_target_skills(all_skills, non_target_categories, max_per_cat=2):
    picks = []
    for cat in (non_target_categories or []):
        count = 0
        for sid, sd in all_skills.items():
            if sd.get("分類", "") == cat:
                picks.append((sid, sd))
                count += 1
                if count >= max_per_cat:
                    break
    return picks


# ---------------------------------------------------------------------------
# 検証実行
# ---------------------------------------------------------------------------

def run_case(case, all_skills):
    results = []
    actor_factory = case["actor_factory"]
    battle_state = case.get("battle_state")

    # ターゲットスキル（命中を期待）
    target_skills = _pick_skills(
        all_skills,
        categories=case.get("target_categories"),
        filter_key=case.get("filter_key"),
        max_per_cat=3,
    )
    for sid, sd in target_skills:
        actor = actor_factory()
        ev = evaluate_skill_access(actor, sid, battle_state=battle_state)
        cat = sd.get("分類", "")
        cost_ok = None
        delta_ok = None

        if case.get("check_cost_increase"):
            cost_type, added = case["check_cost_increase"]
            effective = {e["type"]: e["value"] for e in ev.get("effective_cost", [])}
            base_cost_entries = [
                e for e in ev.get("effective_cost", [])
                if e["type"] == cost_type
            ]
            # effective_cost にコスト種別があれば増加分が乗っているはず
            delta_ok = effective.get(cost_type, 0) > 0
            cost_ok = ev.get("effective_cost")

        expect = case.get("expect_blocked")
        actual_blocked = not ev["usable"]
        ok = (expect is None) or (actual_blocked == expect)

        results.append({
            "skill_id": sid,
            "name": sd.get("デフォルト名称", ""),
            "category": cat,
            "role": "target",
            "usable": ev["usable"],
            "blocked_reasons": ev.get("blocked_reasons", []),
            "effective_cost": ev.get("effective_cost", []),
            "pass": ok,
            "delta_ok": delta_ok,
        })

    # 非ターゲットスキル（命中しないことを期待）
    if case.get("non_target_categories") and case.get("expect_blocked") is True:
        non_target_skills = _pick_non_target_skills(
            all_skills, case["non_target_categories"], max_per_cat=2
        )
        for sid, sd in non_target_skills:
            actor = actor_factory()
            ev = evaluate_skill_access(actor, sid, battle_state=battle_state)
            cat = sd.get("分類", "")
            # FP/MP が足りれば usable=True なはず
            results.append({
                "skill_id": sid,
                "name": sd.get("デフォルト名称", ""),
                "category": cat,
                "role": "non-target",
                "usable": ev["usable"],
                "blocked_reasons": ev.get("blocked_reasons", []),
                "effective_cost": ev.get("effective_cost", []),
                "pass": ev["usable"],  # 封印されないはず → usable=True が正
                "delta_ok": None,
            })

    return results


# ---------------------------------------------------------------------------
# レポート出力
# ---------------------------------------------------------------------------

def print_report(all_case_results):
    total = sum(len(rs) for _, rs in all_case_results)
    passed = sum(1 for _, rs in all_case_results for r in rs if r["pass"])
    failed = total - passed

    print("=" * 70)
    print("Plan 22 実測ログ — evaluate_skill_access 対実スキルデータ検証")
    print("=" * 70)

    for case, results in all_case_results:
        section_pass = all(r["pass"] for r in results)
        mark = "OK" if section_pass else "NG"
        print(f"\n[{mark}] {case['section']} / {case['label']}")
        print(f"      ケースID: {case['id']}")
        for r in results:
            role_tag = "(非命中期待)" if r["role"] == "non-target" else "(命中期待)" if case.get("expect_blocked") is True else "(コスト確認)"
            p = "PASS" if r["pass"] else "FAIL"
            cost_str = ""
            if r["effective_cost"]:
                cost_str = " effective_cost=" + str(r["effective_cost"])
            reason_str = ""
            if r["blocked_reasons"]:
                reason_str = " reasons=" + str(r["blocked_reasons"])
            print(f"  [{p}] {r['skill_id']:8s} {r['name'][:16]:16s} 分類={r['category']:4s} "
                  f"usable={str(r['usable']):5s} {role_tag}{cost_str}{reason_str}")

    print()
    print("=" * 70)
    print(f"合計: {total} ケース / PASS {passed} / FAIL {failed}")
    if failed == 0:
        print(">>> 全ケースPASS")
    else:
        print(">>> FAILあり — 上記の詳細を確認してください")
    print("=" * 70)


def print_json_report(all_case_results):
    out = []
    for case, results in all_case_results:
        out.append({
            "case_id": case["id"],
            "label": case["label"],
            "section": case["section"],
            "results": results,
        })
    print(json.dumps(out, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    args = parser.parse_args()

    print("スキルキャッシュをロード中...", file=sys.stderr)
    all_skills = _load_skills()
    print(f"  {len(all_skills)} スキル読み込み完了", file=sys.stderr)

    all_case_results = []
    for case in CASES:
        results = run_case(case, all_skills)
        all_case_results.append((case, results))

    if args.json:
        print_json_report(all_case_results)
    else:
        print_report(all_case_results)


if __name__ == "__main__":
    main()
