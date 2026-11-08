#!/usr/bin/env python
# test_buff_plugin.py
"""
バフプラグインシステムのテストスクリプト
"""

from plugins.buffs.registry import buff_registry
from manager.buff_catalog import get_buff_by_id

def test_registry():
    """レジストリの基本機能テスト"""
    print("=" * 60)
    print("Test 1: Registry Auto-Discovery")
    print("=" * 60)

    # 自動検出を実行
    buff_registry.auto_discover()

    # 登録済みバフを表示
    registered = buff_registry.list_registered()
    print(f"\n登録済みバフ: {len(registered)}件")
    for buff_id, class_name in registered.items():
        print(f"  - {buff_id}: {class_name}")


def test_stat_mod_buff():
    """StatModBuffのテスト"""
    print("\n" + "=" * 60)
    print("Test 2: StatModBuff Plugin")
    print("=" * 60)

    # バフ図鑑からデータ取得
    buff_data = get_buff_by_id('Bu-00')
    if not buff_data:
        print("❌ バフ図鑑に Bu-00 が見つかりません")
        return

    print(f"\nバフデータ: {buff_data}")

    # プラグインを取得
    handler_class = buff_registry.get_handler('Bu-00')
    if not handler_class:
        print("❌ Bu-00 のプラグインが見つかりません")
        return

    print(f"\nプラグインクラス: {handler_class.__name__}")

    # プラグインインスタンスを作成
    buff_instance = handler_class(buff_data)
    print(f"バフインスタンス: {buff_instance.name}")

    # テスト用キャラクター
    test_char = {
        'name': 'テストキャラ',
        'special_buffs': []
    }

    # バフを適用
    context = {'source': 'item', 'room': 'test_room'}
    result = buff_instance.apply(test_char, context)

    print(f"\n適用結果:")
    print(f"  success: {result['success']}")
    print(f"  logs: {result['logs']}")
    print(f"  special_buffs: {len(test_char['special_buffs'])}件")

    if test_char['special_buffs']:
        buff = test_char['special_buffs'][0]
        print(f"\n追加されたバフ:")
        print(f"  name: {buff['name']}")
        print(f"  source: {buff['source']}")
        print(f"  lasting: {buff['lasting']}")
        print(f"  stat_mods: {buff['stat_mods']}")

    # on_skill_declare のテスト
    print("\n" + "-" * 60)
    print("スキル宣言時の補正テスト")
    print("-" * 60)

    skill = {'id': 'test_skill'}
    mods = buff_instance.on_skill_declare(test_char, skill, context)
    print(f"stat_mods: {mods.get('stat_mods', {})}")


if __name__ == '__main__':
    print("🧪 バフプラグインシステム テスト\n")

    test_registry()
    test_stat_mod_buff()

    print("\n" + "=" * 60)
    print("✅ テスト完了")
    print("=" * 60)
