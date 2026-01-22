"""
鳩尾殴りの順次効果処理テスト

このテストは、スキル効果の順次処理中に条件を満たした場合、
後続の条件付き効果が正しく発動することを確認します。

テストケース：
Pb-02「鳩尾殴り」
- 効果1: 破裂5を付与
- 効果2: 対象の破裂が8以上なら、破裂5を付与

期待される動作：
1. 対象の初期破裂値が3の場合
   - 効果1で破裂5付与 → 破裂=8
   - 効果2の条件判定（破裂≧8）→ True
   - 効果2で破裂5付与 → 破裂=13
   - 最終破裂値: 13

2. 対象の初期破裂値が2の場合
   - 効果1で破裂5付与 → 破裂=7
   - 効果2の条件判定（破裂≧8）→ False
   - 効果2は発動しない
   - 最終破裂値: 7
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from manager.game_logic import process_skill_effects
from manager.utils import get_status_value, set_status_value

def test_sequential_condition_check():
    """順次効果処理での条件判定テスト"""

    # テストケース1: 初期破裂3 → 効果1で8 → 効果2発動 → 最終13
    print("=" * 60)
    print("テストケース1: 初期破裂3 → 最終破裂13を期待")
    print("=" * 60)

    actor = {"id": "actor1", "name": "攻撃者"}
    target = {"id": "target1", "name": "対象", "破裂": 3}

    # 鳩尾殴りの効果定義
    effects = [
        {
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "破裂",
            "value": 5
        },
        {
            "timing": "HIT",
            "type": "APPLY_STATE",
            "target": "target",
            "state_name": "破裂",
            "value": 5,
            "condition": {
                "source": "target",
                "param": "破裂",
                "operator": "GTE",
                "value": 8
            }
        }
    ]

    # 効果処理実行
    bonus_dmg, logs, changes = process_skill_effects(effects, "HIT", actor, target)

    # 結果確認
    final_rupture = get_status_value(target, "破裂")
    print(f"初期破裂値: 3")
    print(f"最終破裂値: {final_rupture}")
    print(f"ログ: {logs}")
    print(f"変更: {len(changes)}件")

    if final_rupture == 13:
        print("[PASS] Test 1: Rupture is 13 as expected")
    else:
        print(f"[FAIL] Test 1: Expected 13, got {final_rupture}")

    print()

    # テストケース2: 初期破裂2 → 効果1で7 → 効果2発動しない → 最終7
    print("=" * 60)
    print("テストケース2: 初期破裂2 → 最終破裂7を期待")
    print("=" * 60)

    target2 = {"id": "target2", "name": "対象2", "破裂": 2}

    # 効果処理実行
    bonus_dmg2, logs2, changes2 = process_skill_effects(effects, "HIT", actor, target2)

    # 結果確認
    final_rupture2 = get_status_value(target2, "破裂")
    print(f"初期破裂値: 2")
    print(f"最終破裂値: {final_rupture2}")
    print(f"ログ: {logs2}")
    print(f"変更: {len(changes2)}件")

    if final_rupture2 == 7:
        print("[PASS] Test 2: Rupture is 7 as expected")
    else:
        print(f"[FAIL] Test 2: Expected 7, got {final_rupture2}")

    print()

    # テストケース3: 初期破裂8 → 効果1で13 → 効果2発動 → 最終18
    print("=" * 60)
    print("テストケース3: 初期破裂8 → 最終破裂18を期待")
    print("=" * 60)

    target3 = {"id": "target3", "name": "対象3", "破裂": 8}

    # 効果処理実行
    bonus_dmg3, logs3, changes3 = process_skill_effects(effects, "HIT", actor, target3)

    # 結果確認
    final_rupture3 = get_status_value(target3, "破裂")
    print(f"初期破裂値: 8")
    print(f"最終破裂値: {final_rupture3}")
    print(f"ログ: {logs3}")
    print(f"変更: {len(changes3)}件")

    if final_rupture3 == 18:
        print("[PASS] Test 3: Rupture is 18 as expected")
    else:
        print(f"[FAIL] Test 3: Expected 18, got {final_rupture3}")

    print()
    print("=" * 60)
    print("全テスト完了")
    print("=" * 60)

if __name__ == "__main__":
    test_sequential_condition_check()
