import json
import re
import subprocess
from pathlib import Path


def _select(presentation, live_store, legacy, same_object=False):
    source = Path("static/js/visual/visual_map.js").read_text(encoding="utf-8")
    match = re.search(r"window\.selectBoardRenderState = function[\s\S]+?\n\};", source)
    assert match, "selectBoardRenderState not found"
    script = f"""
const window = {{}};
{match.group(0)}
const live = {json.dumps(live_store)};
const presentation = {"live" if same_object else json.dumps(presentation)};
const picked = window.selectBoardRenderState(presentation, live, {json.dumps(legacy)});
process.stdout.write(JSON.stringify(picked ? picked.name : null));
"""
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


OLD = {"name": "legacy", "characters": [{"id": "c1"}]}


def test_full_reset_uses_empty_live_store_instead_of_stale_legacy():
    live = {"name": "store", "characters": []}
    assert _select(None, live, OLD, same_object=True) == "store"


def test_frozen_presentation_snapshot_is_kept_during_animation():
    presentation = {"name": "presentation", "characters": [{"id": "c1"}]}
    live = {"name": "store", "characters": []}
    assert _select(presentation, live, OLD) == "presentation"


def test_live_store_with_characters_is_used():
    presentation = {"name": "presentation", "characters": []}
    live = {"name": "store", "characters": [{"id": "c2"}]}
    assert _select(presentation, live, OLD) == "store"


def test_legacy_is_used_only_when_store_has_no_server_state():
    presentation = {"name": "presentation", "characters": []}
    live = {"name": "store", "characters": []}
    assert _select(presentation, live, OLD) == "legacy"
