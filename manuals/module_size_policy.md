# Module Size Policy

## Goal
- Keep each Python module at or below `1500` lines.
- Add new functionality by creating focused modules instead of extending large legacy files.

## Rules
1. New Python files must be `<= 1500` lines.
2. Existing large legacy files must not grow.
3. When adding a feature, prefer extracting or adding a dedicated module and wiring imports.

## Enforcement
- `tests/test_python_module_size_guard.py` enforces:
  - `<= 1500` lines for normal modules
  - fixed ceilings for current legacy modules until they are split further

## Current Legacy Ceilings
- `manager/battle/core.py`: `4370`
- `events/battle/common_routes.py`: `1888`
- `manager/game_logic.py`: `1773`
