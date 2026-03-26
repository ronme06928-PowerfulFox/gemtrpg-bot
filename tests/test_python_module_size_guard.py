from pathlib import Path


MAX_LINES = 1500

# Temporary legacy ceilings: large files can exist for now, but must not grow.
LEGACY_FILE_CEILINGS = {
    "manager/battle/core.py": 4370,
    "events/battle/common_routes.py": 1888,
    "manager/game_logic.py": 1773,
}


def _iter_python_files(repo_root: Path):
    for path in repo_root.rglob("*.py"):
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith("tests/"):
            continue
        if rel.startswith(".venv/"):
            continue
        if rel.startswith("venv/"):
            continue
        if "/__pycache__/" in rel:
            continue
        yield path, rel


def test_python_module_line_limits():
    repo_root = Path(__file__).resolve().parents[1]
    violations = []

    for path, rel in _iter_python_files(repo_root):
        with path.open("r", encoding="utf-8") as f:
            line_count = sum(1 for _ in f)

        if rel in LEGACY_FILE_CEILINGS:
            ceiling = LEGACY_FILE_CEILINGS[rel]
            if line_count > ceiling:
                violations.append(f"{rel}: {line_count} > legacy ceiling {ceiling}")
            continue

        if line_count > MAX_LINES:
            violations.append(f"{rel}: {line_count} > {MAX_LINES}")

    assert not violations, "Python module size guard violations:\n" + "\n".join(violations)
