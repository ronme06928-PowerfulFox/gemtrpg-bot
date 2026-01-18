"""
輝化スキル、アイテム、特殊パッシブローダーのテストスクリプト
"""
import sys
sys.path.insert(0, '.')

from manager.radiance.loader import radiance_loader
from manager.items.loader import item_loader
from manager.passives.loader import passive_loader

def test_radiance_loader():
    """輝化スキルローダーのテスト"""
    print("=" * 60)
    print("輝化スキルローダーのテスト開始")
    print("=" * 60)

    skills = radiance_loader.load_skills()

    print(f"\n読み込まれたスキル数: {len(skills)}")
    print("\n--- スキル一覧 ---")
    for skill_id, skill_data in skills.items():
        print(f"\n{skill_id}: {skill_data['name']}")
        print(f"  コスト: {skill_data['cost']}")
        print(f"  説明: {skill_data['description']}")
        print(f"  効果: {skill_data['effect']}")

    return len(skills) > 0

def test_item_loader():
    """アイテムローダーのテスト"""
    print("\n" + "=" * 60)
    print("アイテムローダーのテスト開始")
    print("=" * 60)

    items = item_loader.load_items()

    print(f"\n読み込まれたアイテム数: {len(items)}")
    print("\n--- アイテム一覧 ---")
    for item_id, item_data in items.items():
        print(f"\n{item_id}: {item_data['name']}")
        print(f"  説明: {item_data['description']}")
        print(f"  消耗: {item_data['consumable']}")
        print(f"  使用可能: {item_data['usable']}")
        print(f"  ラウンド制限: {item_data['round_limit']}")
        print(f"  効果: {item_data['effect']}")

    return len(items) > 0

def test_passive_loader():
    """特殊パッシブローダーのテスト"""
    print("\n" + "=" * 60)
    print("特殊パッシブローダーのテスト開始")
    print("=" * 60)

    passives = passive_loader.load_passives()

    print(f"\n読み込まれたパッシブ数: {len(passives)}")
    if len(passives) > 0:
        print("\n--- パッシブ一覧 ---")
        for passive_id, passive_data in passives.items():
            print(f"\n{passive_id}: {passive_data['name']}")
            print(f"  コスト: {passive_data['cost']}")
            print(f"  説明: {passive_data['description']}")
            print(f"  効果: {passive_data['effect']}")
    else:
        print("  (データはまだ登録されていません)")

    # パッシブは0件でも成功とみなす（まだデータがない場合）
    return True

if __name__ == "__main__":
    try:
        skill_success = test_radiance_loader()
        item_success = test_item_loader()
        passive_success = test_passive_loader()

        print("\n" + "=" * 60)
        print("テスト結果")
        print("=" * 60)
        print(f"輝化スキルローダー: {'✓ 成功' if skill_success else '✗ 失敗'}")
        print(f"アイテムローダー: {'✓ 成功' if item_success else '✗ 失敗'}")
        print(f"特殊パッシブローダー: {'✓ 成功' if passive_success else '✗ 失敗'}")

        if skill_success and item_success and passive_success:
            print("\n✅ 全てのテストが成功しました！")
            sys.exit(0)
        else:
            print("\n❌ テストに失敗しました")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
