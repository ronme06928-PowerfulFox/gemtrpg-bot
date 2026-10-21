import json
import re
import subprocess
from pathlib import Path

import pytest


def _restore(stored, info_mod):
    html = Path("CharaCreator/GEMDICEBOT_CharaCreator.html").read_text(encoding="utf-8")
    match = re.search(r"function restoreInfoSkillAllocation\([\s\S]+?\n        \}", html)
    assert match, "restoreInfoSkillAllocation not found"
    script = f"{match.group(0)}\nprocess.stdout.write(JSON.stringify(restoreInfoSkillAllocation({stored}, {info_mod})));"
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("stored,info_mod,allocation", [
    # 非都市部(-1): 0に丸めて保存した値は割り振り0として戻す（D38）
    (0, -1, 0), (1, -1, 2), (2, -1, 3),
    # 都市部(+1)と補正なしはこれまでどおり
    (1, 1, 0), (4, 1, 3), (0, 0, 0), (2, 0, 2),
    # 割り振りの上限は3
    (5, -1, 3),
])
def test_info_skill_allocation_restore(stored, info_mod, allocation):
    assert _restore(stored, info_mod) == allocation
