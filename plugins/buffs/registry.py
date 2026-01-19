# plugins/buffs/registry.py
"""
バフプラグインのレジストリ

バフIDとプラグインクラスのマッピングを管理します。
"""

import os
import importlib
import inspect
from .base import BaseBuff


class BuffRegistry:
    """バフプラグインのレジストリ"""

    def __init__(self):
        self._handlers = {}  # {buff_id: BuffClass}
        print("[BuffRegistry] Initialized")

    def register(self, buff_id, buff_class):
        """
        バフプラグインを登録

        Args:
            buff_id (str): バフID（例: 'Bu-00'）
            buff_class (class): BaseBuff を継承したクラス
        """
        if not issubclass(buff_class, BaseBuff):
            raise ValueError(f"{buff_class} must extend BaseBuff")

        self._handlers[buff_id] = buff_class
        print(f"[BuffRegistry] Registered {buff_id} -> {buff_class.__name__}")

    def get_handler(self, buff_id):
        """
        バフプラグインクラスを取得

        Args:
            buff_id (str): バフID

        Returns:
            class or None: BuffClass or None
        """
        return self._handlers.get(buff_id)

    def auto_discover(self):
        """
        plugins/buffs/ 以下のプラグインを自動検出して登録

        各プラグインファイルで定義されたBaseBuff継承クラスを探し、
        そのクラスのBUFF_IDS属性に基づいて自動登録します。
        """
        print("[BuffRegistry] Auto-discovering buff plugins...")

        # plugins/buffs/ ディレクトリのパス
        buffs_dir = os.path.dirname(__file__)

        # すべてのPythonファイルを探す（__init__.py, base.py, registry.pyを除く）
        for filename in os.listdir(buffs_dir):
            if not filename.endswith('.py'):
                continue
            if filename in ('__init__.py', 'base.py', 'registry.py'):
                continue

            module_name = filename[:-3]  # .py を除去

            try:
                # モジュールをインポート
                module = importlib.import_module(f'plugins.buffs.{module_name}')

                # モジュール内のすべてのクラスを検査
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # BaseBuff を継承していて、BaseBuff自身ではないクラス
                    if issubclass(obj, BaseBuff) and obj is not BaseBuff:
                        # BUFF_IDS が定義されているか確認
                        if hasattr(obj, 'BUFF_IDS') and obj.BUFF_IDS:
                            # 各バフIDを登録
                            for buff_id in obj.BUFF_IDS:
                                self.register(buff_id, obj)
                        else:
                            print(f"[BuffRegistry] Warning: {name} has no BUFF_IDS, skipping")

            except Exception as e:
                print(f"[BuffRegistry] Error loading {module_name}: {e}")

        print(f"[BuffRegistry] Auto-discovery complete. {len(self._handlers)} buff(s) registered.")

    def list_registered(self):
        """
        登録済みのバフIDとクラスのリストを取得

        Returns:
            dict: {buff_id: class_name}
        """
        return {buff_id: cls.__name__ for buff_id, cls in self._handlers.items()}


# グローバルインスタンス
buff_registry = BuffRegistry()
