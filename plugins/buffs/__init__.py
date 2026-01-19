# plugins/buffs/__init__.py
"""
バフプラグインシステム

バフの効果ロジックをプラグイン化し、データとロジックを分離します。
"""

from .registry import buff_registry

__all__ = ['buff_registry']
