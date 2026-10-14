"""requirements.txt の全依存固定を検証する（F01 Part 3 §7）。

2026-10-15: SQLAlchemy 未固定のため Render の新規ビルドに 2.1.4 が入り、
postgresql:// の既定ドライバが未導入の psycopg v3 になって起動失敗した。
間接依存も含め、本番に入る版をテスト環境の版へ固定する。
"""
import re
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"
INDIRECT_HEADER = "# --- 間接依存"
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;=]+)$")

# Render 本番（Linux x86_64 / CPython 3.11）としてマーカーを評価する
RENDER_ENV = {
    **default_environment(),
    "sys_platform": "linux",
    "platform_system": "Linux",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "implementation_name": "cpython",
    "platform_python_implementation": "CPython",
    "python_version": "3.11",
    "extra": "",
}


def _read_pins():
    """(直接依存の名前一覧, {正規化名: (表記, 版)}) を返す。"""
    direct = []
    pins = {}
    in_indirect = False
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        if line.startswith(INDIRECT_HEADER):
            in_indirect = True
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.match(line)
        assert match, f"== で固定されていない行: {line}"
        name, version = match.groups()
        key = canonicalize_name(name)
        assert key not in pins, f"重複: {name}"
        pins[key] = (name, version)
        if not in_indirect:
            direct.append(key)
    return direct, pins


def _dependency_closure(roots):
    seen = set()
    queue = list(roots)
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        for spec in metadata.requires(name) or []:
            req = Requirement(spec)
            if req.marker is None or req.marker.evaluate(RENDER_ENV):
                queue.append(canonicalize_name(req.name))
    return seen


def test_requirements_has_direct_and_indirect_sections():
    direct, pins = _read_pins()
    assert direct
    assert len(pins) > len(direct)


def test_pinned_versions_match_test_environment():
    _, pins = _read_pins()
    mismatched = {
        name: (version, metadata.version(name))
        for name, version in pins.values()
        if metadata.version(name) != version
    }
    assert mismatched == {}, "固定値 → テスト環境の版"


def test_requirements_pin_exactly_the_dependency_closure():
    direct, pins = _read_pins()
    closure = _dependency_closure(direct)
    assert sorted(closure - pins.keys()) == [], "固定漏れの間接依存"
    assert sorted(pins.keys() - closure) == [], "どこからも要求されない固定"
