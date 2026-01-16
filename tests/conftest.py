# tests/conftest.py
"""
pytest共通フィクスチャ
"""
import pytest
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def sample_actor():
    """テスト用の攻撃者キャラクター"""
    return {
        'id': 'actor1',
        'name': 'Attacker',
        'type': 'ally',
        'hp': 100,
        'maxHp': 100,
        'mp': 50,
        'maxMp': 50,
        'params': [
            {'label': '物理補正', 'value': 10},
            {'label': '魔法補正', 'value': 8},
            {'label': '速度', 'value': 12}
        ],
        'states': [
            {'name': 'FP', 'value': 3},
            {'name': '出血', 'value': 0},
            {'name': '破裂', 'value': 0},
            {'name': '亀裂', 'value': 0},
            {'name': '戦慄', 'value': 0},
            {'name': '荊棘', 'value': 0}
        ],
        'special_buffs': [],
        'flags': {},
        'hasActed': False
    }

@pytest.fixture
def sample_target():
    """テスト用のターゲットキャラクター"""
    return {
        'id': 'target1',
        'name': 'Target',
        'type': 'enemy',
        'hp': 80,
        'maxHp': 80,
        'mp': 30,
        'maxMp': 30,
        'params': [
            {'label': '物理補正', 'value': 5},
            {'label': '魔法補正', 'value': 12},
            {'label': '速度', 'value': 8}
        ],
        'states': [
            {'name': 'FP', 'value': 2},
            {'name': '出血', 'value': 0},
            {'name': '破裂', 'value': 0},
            {'name': '亀裂', 'value': 0},
            {'name': '戦慄', 'value': 0},
            {'name': '荊棘', 'value': 0}
        ],
        'special_buffs': [],
        'flags': {},
        'hasActed': False
    }
